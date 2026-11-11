# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""診斷後給建議：這台裝了什麼、最近用了什麼，對照名冊列出三類候選，讓 agent 挑選並寫理由。

分工：
- 腳本給事實與候選（這支，輸出 JSON）：只讀本機的紀錄與設定，不連網、不花 token、不寫檔。
- agent 在候選裡挑選，每一項寫理由，存成一個 JSON 檔。候選以外的不能挑。
- 腳本驗證挑選並寫出建議（--picks）：每一項都要在候選裡、都要有理由，通過才寫。建議存在
  %LOCALAPPDATA%\\omnikit\\advice\\<日期>-<agent>.md，附上使用者同意後要跑的指令。
- 安裝、停用、移除不在這支腳本裡做：交給各 agent 原生的指令（claude plugin、codex plugin、claude mcp、codex mcp）。

三類候選，Claude Code 與 Codex 各算各的；這台沒裝、或這段期間沒有對話紀錄的 agent 不出建議：
- 裝（install）：槽位的答案是「建議裝某張卡」而這台還沒裝；槽位還沒有答案時，名冊上是預設或試用、
  支援這個 agent、這台還沒裝的卡（註明還沒有分 agent 的實測）。
- 拿掉（remove）：30 天沒用到（裝不到 30 天的不列）；開頭成本高、14 天內與最近 10 段對話都沒用到；
  裝著、但名冊上是拒絕或退役；同一件事名冊記了內建功能，而這份裝了一週以上從沒用到。
  沒有使用紀錄可以判斷的（例如 MCP），不會只因為「沒看到用」就列進來。
- 用內建的就好（native）：槽位的答案是「內建就夠」；還沒實測的，名冊記了內建功能也列（註明還沒實測）。
  同一個槽位這台裝了第三方工具的，一併列出來給 agent 判斷。
OmniKit 自己的 skill 與 MCP、只有維護者才啟用的模組（同事版）不列。只輸出名稱、次數與日期，不輸出對話內容。

用法：
  uv run engine/scripts/advise.py [--agent claude|codex] [--days 30]    印出事實與候選（JSON）
  uv run engine/scripts/advise.py --picks <檔> [--no-save]              驗證挑選，印出並存下建議
  uv run engine/scripts/advise.py --selftest
"""
import argparse
import json
import socket
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cost  # noqa: E402
import edition as editions  # noqa: E402
import profiles  # noqa: E402
import scan  # noqa: E402
import usage  # noqa: E402
import validate  # noqa: E402

AGENTS = {"claude": "claude-code", "codex": "codex"}  # 名冊與答案用的名稱 → 使用統計用的名稱
LABELS = {"claude": "Claude Code", "codex": "Codex"}
KINDS = ("install", "remove", "native")
TITLES = {"install": "裝", "remove": "拿掉", "native": "用內建的就好"}
STATUS = {"default": "預設", "trial": "試用", "pending": "待評估", "rejected": "拒絕", "retired": "退役"}
# 掃得到有沒有裝的種類；獨立程式、線上服務、命令列工具、程式庫、裝在專案裡的集合與規則包掃不到
DETECTABLE = {"skill", "plugin", "mcp"}
OVERLAP_DAYS = 7  # 跟內建功能重疊、裝了這麼多天都沒用到，才列進拿掉（不用等 30 天）
MCP_WHERE = {"claude": "~/.claude.json", "codex": "~/.codex/config.toml"}
CLIP = 400   # 內建卡的說明最多帶幾個字（給 agent 的 JSON）
BRIEF = 120  # 寫進建議時再縮短成幾個字（給使用者看）
REASON = 6   # 理由至少幾個字


def supports(card, agent):
    return not card.get("works_with") or agent in card["works_with"]


def clip(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= CLIP else text[:CLIP] + "…"


def brief(item, card):
    out = {k: item.get(k) for k in ("kind", "name", "where", "status", "conversations", "last_used", "installed_days")}
    if item.get("skills"):
        out["skills"] = item["skills"]
    if item.get("ours"):
        out["ours"] = True
    if card:
        out["card"] = {"id": card["id"], "status": card["status"], "slots": card["slots"]}
    return out


def how_install(card, agent, cfg, added):
    """同意後怎麼裝：名冊有這個 agent 的 plugin 來源、而且是預設的，才在 OmniKit 的 marketplace 裡。"""
    plugin = card.get("plugin") or {}
    if card["status"] == "default" and agent in plugin and cfg.get("marketplace") and cfg.get("repo"):
        name = f"{plugin.get('name', card['id'])}@{cfg['marketplace']}"
        tool = "claude plugin" if agent == "claude" else "codex plugin"
        commands = [] if added else [f"{tool} marketplace add {cfg['repo']}"]
        commands.append(f"{tool} {'install' if agent == 'claude' else 'add'} {name}")
        return {"commands": commands, "note": "裝好之後開新的對話才會載入" + ("。" if added else "；marketplace 加過就跳過第一行。")}
    return {"commands": [], "note": "名冊沒有這張卡的 plugin 來源，照官方說明安裝" + (f"：{card['url']}" if card.get("url") else "")}


def how_remove(item, agent):
    """同意後怎麼拿掉：plugin 與 MCP 用原生指令；單一 skill 兩邊都沒有原生指令，只能刪資料夾。"""
    kind, name = item["kind"], item["name"]
    if kind == "plugin":
        if agent == "claude":
            return {"disable": f"claude plugin disable {name}", "remove": f"claude plugin uninstall {name}"}
        note = "Codex 沒有停用 plugin 的指令"
        if name.split("@")[-1].startswith("openai-"):  # openai-bundled、openai-primary-runtime 這類 marketplace
            note += "；這是 Codex 自帶的 plugin，移除之後會不會再同步回來還沒驗證"
        return {"remove": f"codex plugin remove {name}", "note": note}
    if kind == "mcp":
        return {"remove": f"{'claude' if agent == 'claude' else 'codex'} mcp remove {name}"}
    return {"remove_path": f"{item['where']}/{name}"}


def diagnose(roster, used, costs, found, edition="colleague", added=None, today=None, notes=()):
    """純計算：名冊、使用統計（usage.collect 的結果，可以多帶 MCP）、成本（cost.measure 的結果或 None）→ 事實與候選。"""
    cfg, tools, added = roster.get("config") or {}, roster["tools"], added or {}
    third = {k: v for k, v in tools.items() if v.get("kind") != "native"}
    hidden = sorted(m["id"] for m in roster["modules"] if m.get("maintainer_only") and edition != "maintainer")
    slots = [s for s in roster["slots"] if s["module"] not in hidden]
    rows = {(r["agent"], r["tool"]): r for r in (costs or {}).get("rows", [])}
    out = {"generated": (today or date.today()).isoformat(), "days": used["days"], "profile": roster.get("profile"),
           "edition": edition,
           "roster": {"modules": len(roster["modules"]) - len(hidden), "slots": len(slots), "tools": len(tools),
                      "hidden_modules": hidden},
           "notes": list(notes), "agents": {}}

    for agent, uid in AGENTS.items():
        convs = (used.get("sources") or {}).get(uid, 0)
        entry = {"name": LABELS[agent], "found": bool(found.get(agent)), "active": bool(found.get(agent)) and convs > 0,
                 "conversations": convs, "installed": [], "candidates": {k: [] for k in KINDS},
                 "not_judged": {"new": [], "no_usage_data": []}}
        out["agents"][agent] = entry
        if not entry["active"]:
            entry["skip"] = ("這台沒有裝，不出建議" if not entry["found"]
                             else f"{used['days']} 天內沒有對話紀錄，不出建議")
            continue

        pairs = [(i, cost.roster_card(i, third)) for i in used["items"] if uid in i["agents"]]
        entry["installed"] = [brief(i, c) for i, c in pairs]
        entry["not_judged"] = {"new": sorted(i["name"] for i, _ in pairs if i["status"] == "new"),
                               "no_usage_data": sorted(i["name"] for i, _ in pairs if i["status"] == "no-data")}
        have = {c["id"] for _, c in pairs if c}
        by_slot = {}
        for i, c in pairs:
            for slot_id in (c or {}).get("slots", []):
                by_slot.setdefault(slot_id, []).append(brief(i, c))
        answers = {s["id"]: (s.get("answers") or {}).get(agent) or {} for s in slots}

        # 裝
        offered = set()

        def offer(card, slot, basis):
            if card["id"] in have or card["id"] in offered:
                return
            offered.add(card["id"])
            entry["candidates"]["install"].append({
                "id": f"install:{card['id']}", "tool": card["id"], "name": card["name"], "kind": card.get("kind"),
                "status": card["status"], "slot": slot["id"], "slot_name": slot["name"], "module": slot["module"],
                "basis": {k: v for k, v in basis.items() if v}, "url": card.get("url"),
                "detectable": card.get("kind") in DETECTABLE,
                "how": how_install(card, agent, cfg, added.get(agent))})

        for s in slots:
            a = answers[s["id"]]
            if a.get("verdict") == "tool" and a.get("tool") in third:
                offer(third[a["tool"]], s, {"code": "answer", "text": a.get("reason"), "evidence": a.get("evidence"),
                                            "decided_at": a.get("decided_at")})
        for card in third.values():
            if card["status"] not in ("default", "trial") or not supports(card, agent):
                continue
            undecided = [s for s in slots if s["id"] in card["slots"] and answers[s["id"]].get("verdict", "unknown") == "unknown"]
            if undecided:
                offer(card, undecided[0], {"code": f"roster-{card['status']}", "text": card.get("reason"),
                                           "decided_at": card.get("decided_at"), "trial_until": card.get("trial_until"),
                                           "caveat": f"名冊的{STATUS[card['status']]}，還沒有分 agent 的實測"})

        # 用內建的就好（先算：拿掉的其中一個依據是「跟內建功能重疊又沒用到」）
        for s in slots:
            a = answers[s["id"]]
            verdict = a.get("verdict")
            base = {"id": f"native:{s['id']}", "slot": s["id"], "slot_name": s["name"], "module": s["module"],
                    "installed_here": by_slot.get(s["id"], [])}
            if verdict == "native":
                basis = {"code": "answer-native", "text": a.get("reason"), "evidence": a.get("evidence"),
                         "decided_at": a.get("decided_at")}
                entry["candidates"]["native"].append({**base, "tested": True, "basis": {k: v for k, v in basis.items() if v}})
            elif verdict == "unknown" and a.get("reason"):
                entry["candidates"]["native"].append({**base, "tested": False, "basis": {
                    "code": "answer-unknown", "text": a["reason"], "caveat": "還沒實測內建的夠不夠"}})
            elif not verdict:
                card = next((c for c in tools.values() if c.get("kind") == "native" and c["status"] == "default"
                             and s["id"] in c["slots"] and supports(c, agent)), None)
                if card:
                    entry["candidates"]["native"].append({**base, "tested": False, "builtin": card["name"], "url": card.get("url"), "basis": {
                        "code": "roster-native", "text": clip(card.get("notes") or card.get("reason")),
                        "caveat": "名冊目前拿內建功能當比較基準，還沒有實測證明夠用"}})

        # 拿掉
        builtin = {c["slot"]: c for c in entry["candidates"]["native"]}
        for i, c in pairs:
            if i.get("ours"):
                continue
            basis = []
            if i["status"] == "unused":
                age = f"，裝了 {i['installed_days']} 天" if i.get("installed_days") is not None else ""
                basis.append({"code": "unused", "text": f"{used['days']} 天沒用到{age}"})
            row = rows.get((uid, cost.tool_keys(i).get(uid)))
            if row and row.get("idle") and row["tokens"] >= cost.THRESHOLD:
                basis.append({"code": "costly-idle", "text": f"每段對話開頭約 {row['tokens']:,} tokens，"
                                                               f"{cost.IDLE_DAYS} 天內與最近 {cost.IDLE_CONVS} 段對話都沒用到"})
            if c and c["status"] in ("rejected", "retired"):
                basis.append({"code": f"roster-{c['status']}", "text": f"名冊上是{STATUS[c['status']]}：{c.get('reason')}"})
            # 剛裝的本來先不判斷；但同一件事名冊記了內建功能、裝了一週以上又從沒用到，兩個事實都成立就列
            same = next((builtin[s] for s in (c or {}).get("slots", []) if s in builtin), None)
            if same and i["status"] == "new" and (i.get("installed_days") or 0) >= OVERLAP_DAYS:
                basis.append({"code": "native-overlap", "text": f"裝了 {i['installed_days']} 天沒用到；「{same['slot_name']}」"
                                                                 f"名冊記了內建功能" + ("" if same["tested"] else "（還沒實測夠不夠）")})
            if basis:
                shared = sorted(usage.NAMES[a] for a in i["agents"] if a != uid)
                entry["candidates"]["remove"].append({
                    "id": f"remove:{i['kind']}:{i['name']}@{i['where']}", **brief(i, c), "basis": basis,
                    "shared_with": shared, "how": how_remove(i, agent)})
    return out


def our_mcp(data):
    """OmniKit 自己接上的 MCP server（data/mcp/servers.yaml）：不列進拿掉。"""
    path = data / "mcp" / "servers.yaml"
    try:
        return set((validate.load_yaml(path) or {}).get("servers") or {}) if path.exists() else set()
    except Exception:  # 這份壞了由 validate 報，不擋建議
        return set()


def marketplace_added(home, name):
    try:
        doc = json.loads((home / ".claude" / "plugins" / "known_marketplaces.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and name in doc


def collect(home, data, state, days=30, now=None, plugin_details=cost.details):
    """讀這台的紀錄、設定與名冊，回傳事實與候選。只讀不寫、不連網。"""
    errors, roster = validate.check(data, state=state)
    if errors:
        raise SystemExit("名冊驗證沒過，先修好再給建議：\n" + "\n".join(f"- {e}" for e in errors))
    now = now or time.time()
    used = usage.collect(home, days=days, now=now)
    notes = ["profile 還不能選領域：先對照名冊全部的模組"]
    try:
        costs = cost.measure(home, state, now=now, plugin_details=plugin_details)
    except Exception as e:  # 成本量不到，不影響其他依據
        costs = None
        notes.append(f"開頭成本量不到（{e}）：這次沒有「成本高又沒在用」這個依據")
    ours = our_mcp(data)
    for agent, uid in AGENTS.items():
        names = scan.mcp_names(uid, home)
        for name in names if isinstance(names, list) else []:
            used["items"].append({"kind": "mcp", "name": name, "where": MCP_WHERE[agent], "agents": [uid], "status": "no-data",
                                  "conversations": 0, "installed_days": None, "last_used": None, "ours": name in ours})
    found = {"claude": (home / ".claude").is_dir(), "codex": (home / ".codex").is_dir()}
    added = {"claude": marketplace_added(home, (roster.get("config") or {}).get("marketplace"))}
    return diagnose(roster, used, costs, found, edition=editions.resolve(state, data.parent)[0], added=added,
                    today=date.fromtimestamp(now), notes=notes)


# ---------- 驗證挑選、寫出建議 ----------

def check_picks(facts, picks):
    """回傳（問題清單, agent, {類別: [(候選, 理由)]}）。候選以外的、沒寫理由的、重複的都算問題。"""
    if not isinstance(picks, dict) or not isinstance(picks.get("picks"), list):
        return ['挑選檔的格式要是 {"agent": "claude 或 codex", "picks": [{"id": "<候選的 id>", "reason": "<理由>"}]}'], None, None
    agent = picks.get("agent")
    entry = facts["agents"].get(agent) if isinstance(agent, str) else None
    if not entry:
        return [f"agent 要是 {' 或 '.join(AGENTS)}：{agent}"], None, None
    if not entry["active"]:
        return [f"{LABELS[agent]}：{entry['skip']}"], agent, None
    index = {c["id"]: (kind, c) for kind in KINDS for c in entry["candidates"][kind]}
    errors, chosen, seen = [], {k: [] for k in KINDS}, set()
    for n, pick in enumerate(picks["picks"], 1):
        pick = pick if isinstance(pick, dict) else {}
        pid, reason = pick.get("id"), " ".join(str(pick.get("reason") or "").split())
        if pid not in index:
            errors.append(f"第 {n} 項「{pid}」不在候選裡：只能挑腳本列出的候選")
            continue
        if pid in seen:
            errors.append(f"第 {n} 項「{pid}」重複了")
            continue
        seen.add(pid)
        if len(reason) < REASON:
            errors.append(f"第 {n} 項「{pid}」沒有寫理由")
            continue
        kind, cand = index[pid]
        chosen[kind].append((cand, reason))
    return errors, agent, chosen


def basis_text(basis):
    code, text = basis["code"], basis.get("text") or ""
    if code in ("answer", "answer-native"):
        proof = f"（紀錄：{basis['evidence']}）" if basis.get("evidence") else ""
        return f"名冊的答案：{text}{proof}"
    if code.startswith("roster-") and code[7:] in ("default", "trial"):
        until = f"，試用到 {basis['trial_until']}" if basis.get("trial_until") else ""
        return f"{basis['caveat']}{until}。名冊記的理由：{text}"
    if code in ("answer-unknown", "roster-native"):
        # 給 agent 的 JSON 帶比較長的說明；給使用者看的建議只留開頭
        return f"{basis['caveat']}。名冊記的內建功能：{text if len(text) <= BRIEF else text[:BRIEF] + '…'}"
    return text


def usage_text(item):
    if item["status"] == "used":
        return f"{item['conversations']} 段對話用到" if item.get("conversations") else "有用到"
    days = f"裝了 {item['installed_days']} 天" if item.get("installed_days") is not None else "裝了之後"
    return {"unused": "沒用到", "new": f"{days}沒用到", "no-data": "沒有使用紀錄"}.get(item["status"], item["status"])


def install_lines(cand, reason):
    how = cand["how"]
    lines = [f"- **{cand['name']}**（{cand['slot_name']}）", f"  - 理由：{reason}", f"  - 依據：{basis_text(cand['basis'])}"]
    if how["commands"]:
        lines.append("  - 同意後執行：" + "，再 ".join(f"`{c}`" for c in how["commands"]) + f"。{how['note']}")
    else:
        lines.append(f"  - 怎麼裝：{how['note']}")
    if not cand["detectable"]:
        lines.append("  - 注意：這類工具掃不到有沒有裝；已經在用就略過")
    return lines


def remove_lines(cand, reason):
    how = cand["how"]
    lines = [f"- **{cand['name']}**（{cand['kind']}，{cand['where']}）", f"  - 理由：{reason}",
             "  - 依據：" + "；".join(b["text"] for b in cand["basis"])]
    if how.get("disable"):
        lines.append(f"  - 先停用（可以再打開）：`{how['disable']}`")
    if how.get("remove"):
        lines.append(f"  - 移除（是刪除，會先問你）：`{how['remove']}`")
    if how.get("remove_path"):
        lines.append(f"  - 移除（是刪除，會先問你）：刪掉資料夾 `{how['remove_path']}`（skill 沒有原生的移除指令）")
    if how.get("note"):
        lines.append(f"  - 注意：{how['note']}")
    if cand["shared_with"]:
        lines.append(f"  - 注意：{'、'.join(cand['shared_with'])} 也在讀這一份")
    return lines


def native_lines(cand, reason):
    name = f"{cand['slot_name']}：{cand['builtin']}" if cand.get("builtin") else cand["slot_name"]
    lines = [f"- **{name}**", f"  - 理由：{reason}", f"  - 依據：{basis_text(cand['basis'])}"]
    if cand["installed_here"]:
        lines.append("  - 這台同一件事還裝了：" + "、".join(
            f"{i['name']}（{i['kind']}，{usage_text(i)}）" for i in cand["installed_here"]))
    return lines


SECTION = {"install": install_lines, "remove": remove_lines, "native": native_lines}


def render(facts, agent, chosen):
    """建議（Markdown 的每一行）：三類各一節，每一項有理由、依據與同意後要做的事。"""
    entry = facts["agents"][agent]
    total = sum(len(entry["candidates"][k]) for k in KINDS)
    picked = sum(len(v) for v in chosen.values())
    lines = [f"# OmniKit 建議：{LABELS[agent]}（{facts['generated']}）", "",
             f"依據：這台 {facts['days']} 天內的紀錄（{LABELS[agent]} {entry['conversations']} 段對話）、已安裝的 "
             f"{len(entry['installed'])} 項，對照名冊的 {facts['roster']['slots']} 個槽位。腳本列出 {total} 個候選，"
             f"下面是挑出來的 {picked} 個；理由是 agent 寫的，依據是腳本給的事實。"]
    for kind in KINDS:
        lines += ["", f"## {TITLES[kind]}（{len(chosen[kind])} 項）", ""]
        if not chosen[kind]:
            count = len(entry["candidates"][kind])
            lines.append("- 這一類這次沒有建議：" + (f"有 {count} 個候選，都沒有挑" if count else "沒有候選"))
        for cand, reason in chosen[kind]:
            lines += SECTION[kind](cand, reason)
    lines += ["", "## 沒有列進建議的", ""]
    left = [f"{TITLES[k]} {len(entry['candidates'][k]) - len(chosen[k])} 個" for k in KINDS
            if len(entry["candidates"][k]) > len(chosen[k])]
    lines.append("- 候選裡沒有挑的：" + ("、".join(left) if left else "沒有"))
    lines.append(f"- 裝不到 {facts['days']} 天，先不判斷：{len(entry['not_judged']['new'])} 個")
    lines.append(f"- 沒有使用紀錄可以判斷（例如 MCP）：{len(entry['not_judged']['no_usage_data'])} 個")
    lines += [f"- {note}" for note in facts["notes"]]
    lines += ["", "安裝、停用、移除都等你同意才做；拿掉是刪除，一項一項問。只讀這台的紀錄與設定，不連網、不含對話內容。"]
    return lines


def save(lines, state, generated, agent):
    path = state / "advice" / f"{generated}-{agent}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return path


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    def slot(sid, module, answers=None):
        return {"id": sid, "name": f"{sid} 槽位", "module": module, "kind": "domain", **({"answers": answers} if answers else {})}

    def card(cid, kind, status, slots, works=("claude", "codex"), **extra):
        return {"id": cid, "name": cid, "kind": kind, "status": status, "slots": slots, "works_with": list(works),
                "reason": f"{cid} 的理由", "decided_at": "2026-11-01", "url": f"https://example.com/{cid}", **extra}

    def item(kind, name, where, agents, status, days=60, convs=0, **extra):
        return {"kind": kind, "name": name, "where": where, "agents": agents, "status": status, "conversations": convs,
                "installed_days": days, "last_used": "2026-11-01" if convs else None, **extra}

    source = {"source": "url", "url": "https://example.com/x.git", "sha": "a" * 40}
    roster = {
        "config": {"marketplace": "mk", "repo": "owner/kit"}, "profile": "default",
        "modules": [{"id": "dev", "kind": "domain"}, {"id": "ops", "kind": "foundation"},
                    {"id": "toolkit", "kind": "foundation", "maintainer_only": True}],
        "slots": [
            slot("browser", "dev", {"claude": {"verdict": "native", "reason": "實測內建拿滿分", "evidence": "data/evals/b.md",
                                               "decided_at": "2026-11-04"},
                                    "codex": {"verdict": "tool", "tool": "devtools", "reason": "內建在非互動模式不能用",
                                              "decided_at": "2026-11-04"}}),
            slot("frontend", "dev"),
            slot("review", "dev", {"claude": {"verdict": "unknown", "reason": "內建有 /review"}, "codex": {"verdict": "unknown"}}),
            slot("memory", "ops"), slot("concise", "ops"), slot("authoring", "toolkit")],
        "tools": {c["id"]: c for c in [
            card("devtools", "mcp", "trial", ["browser"], trial_until="2026-11-18"),
            card("fe", "skill", "default", ["frontend"], plugin={"name": "fe-plugin", "claude": source, "codex": source}),
            card("desk", "app", "trial", ["frontend"], trial_until="2026-11-23"),
            card("maker", "skill", "default", ["authoring"], works=("claude",), plugin={"claude": source}),
            card("mem-tool", "plugin", "pending", ["memory"]),
            card("mem2", "skill", "pending", ["memory"]),
            card("terse", "skill", "pending", ["concise"]),
            card("bad", "skill", "rejected", ["review"]),
            card("native-browser", "native", "default", ["browser"]),  # 槽位已經有答案：以答案為準，不看這張卡
            card("native-memory", "native", "default", ["memory"], notes="內建的記憶功能 " + "很長的說明" * 100),
            card("native-concise", "native", "default", ["concise"], works=("claude",))]},
    }
    used = {"days": 30, "sources": {"claude-code": 12, "codex": 5, "antigravity": 3}, "items": [
        item("skill", "old", "~/.claude/skills", ["claude-code"], "unused", days=90),
        item("skill", "fresh", "~/.claude/skills", ["claude-code"], "new", days=5),
        item("skill", "quiet", "~/.claude/skills", ["claude-code"], "new", days=5),
        item("plugin", "mem-tool@m", "~/.claude/plugins", ["claude-code"], "used", convs=4),
        item("skill", "bad", "~/.claude/skills", ["claude-code"], "used", convs=2),
        item("skill", "mem2", "~/.claude/skills", ["claude-code"], "new", days=10),
        item("skill", "terse", "~/.claude/skills", ["claude-code"], "new", days=3),
        item("mcp", "kit-server", "~/.claude.json", ["claude-code"], "no-data", days=None, ours=True),
        item("mcp", "other-server", "~/.claude.json", ["claude-code"], "no-data", days=None),
        item("skill", "shared-old", "~/.agents/skills", ["codex", "antigravity"], "unused", days=70),
        item("plugin", "heavy@m", "~/.codex/plugins", ["codex"], "used", convs=1, skills=3),
        item("mcp", "devtools", "~/.codex/config.toml", ["codex"], "no-data", days=None)]}
    idle = {"idle": True, "used_14d": 0, "used_last10": 0}
    costs = {"rows": [{"agent": "codex", "tool": "plugin:heavy@m", "tokens": 3000, **idle},
                      {"agent": "claude-code", "tool": "skill:fresh", "tokens": 5000, **idle},
                      {"agent": "claude-code", "tool": "skill:quiet", "tokens": 200, **idle},
                      {"agent": "claude-code", "tool": "mcp:kit-server", "tokens": 9000, **idle},
                      {"agent": "claude-code", "tool": "plugin:mem-tool", "tokens": 4000, "idle": False}]}
    both = {"claude": True, "codex": True}
    today = date(2026, 11, 11)
    facts = diagnose(roster, used, costs, both, today=today, notes=["備註"])
    claude, codex = facts["agents"]["claude"], facts["agents"]["codex"]

    def ids(entry, kind):
        return [c["id"] for c in entry["candidates"][kind]]

    def cand(entry, cid):
        return next(c for k in KINDS for c in entry["candidates"][k] if c["id"] == cid)

    check("裝：槽位沒有答案時，名冊上預設與試用、支援這個 agent、還沒裝的卡；註明還沒有分 agent 的實測",
          ids(claude, "install") == ["install:fe", "install:desk"]
          and "還沒有分 agent 的實測" in cand(claude, "install:fe")["basis"]["caveat"]
          and cand(claude, "install:desk")["basis"]["trial_until"] == "2026-11-23")
    check("裝：槽位在這個 agent 的答案是內建就夠，不再推那個槽位的第三方卡", "install:devtools" not in ids(claude, "install"))
    check("裝：槽位的答案是建議裝某張卡、而這台已經裝了，不列", "install:devtools" not in ids(codex, "install"))
    bare = {**used, "items": [i for i in used["items"] if i["name"] != "devtools"]}
    answered = cand(diagnose(roster, bare, costs, both, today=today)["agents"]["codex"], "install:devtools")
    check("裝：槽位的答案是建議裝某張卡、這台還沒裝，依據是答案；沒有 plugin 來源的只給網址",
          answered["basis"] == {"code": "answer", "text": "內建在非互動模式不能用", "decided_at": "2026-11-04"}
          and answered["how"]["commands"] == [] and "https://example.com/devtools" in answered["how"]["note"])
    check("裝：只有維護者才啟用的模組，同事版不列、維護者版才列",
          "install:maker" not in ids(claude, "install") and facts["roster"]["hidden_modules"] == ["toolkit"]
          and "install:maker" in ids(diagnose(roster, used, costs, both, edition="maintainer")["agents"]["claude"], "install"))
    check("裝：卡片沒寫支援的 agent 不列", "install:maker" not in ids(
        diagnose(roster, used, costs, both, edition="maintainer")["agents"]["codex"], "install"))
    check("裝：同意後交給原生指令（先加 marketplace 再裝；plugin 名稱照卡片寫的）",
          cand(claude, "install:fe")["how"]["commands"] == ["claude plugin marketplace add owner/kit", "claude plugin install fe-plugin@mk"]
          and cand(codex, "install:fe")["how"]["commands"] == ["codex plugin marketplace add owner/kit", "codex plugin add fe-plugin@mk"])
    check("裝：marketplace 已經加過就只剩安裝那一行", cand(diagnose(roster, used, costs, both, added={"claude": True})["agents"]["claude"],
          "install:fe")["how"]["commands"] == ["claude plugin install fe-plugin@mk"])
    check("裝：獨立程式掃不到有沒有裝，標出來", not cand(claude, "install:desk")["detectable"] and cand(claude, "install:fe")["detectable"])

    check("拿掉：30 天沒用到、成本高又沒在用、名冊上是拒絕，各自帶依據",
          ids(claude, "remove")[:3] == ["remove:skill:old@~/.claude/skills", "remove:skill:fresh@~/.claude/skills",
                                        "remove:skill:bad@~/.claude/skills"]
          and cand(claude, "remove:skill:old@~/.claude/skills")["basis"] == [{"code": "unused", "text": "30 天沒用到，裝了 90 天"}]
          and cand(claude, "remove:skill:fresh@~/.claude/skills")["basis"][0]["code"] == "costly-idle"
          and "5,000 tokens" in cand(claude, "remove:skill:fresh@~/.claude/skills")["basis"][0]["text"]
          and cand(claude, "remove:skill:bad@~/.claude/skills")["basis"] == [{"code": "roster-rejected", "text": "名冊上是拒絕：bad 的理由"}])
    check("拿掉：剛裝的、有在用的、名冊上只是待評估的，不列", not any(n in " ".join(ids(claude, "remove")) for n in ("quiet", "mem-tool")))
    overlap = cand(claude, "remove:skill:mem2@~/.claude/skills")["basis"]
    check("拿掉：同一件事名冊記了內建功能、這份裝了一週以上從沒用到，才列；裝不到一週的不列",
          ids(claude, "remove")[3:] == ["remove:skill:mem2@~/.claude/skills"] and overlap[0]["code"] == "native-overlap"
          and "裝了 10 天沒用到" in overlap[0]["text"] and "還沒實測" in overlap[0]["text"]
          and "terse" not in " ".join(ids(claude, "remove")))
    check("拿掉：沒有使用紀錄的 MCP 不會只因為沒看到用就列；OmniKit 自己的 MCP 成本再高也不列",
          not any("mcp" in i for i in ids(claude, "remove")) and claude["not_judged"]["no_usage_data"] == ["kit-server", "other-server"])
    shared = cand(codex, "remove:skill:shared-old@~/.agents/skills")
    check("拿掉：skill 沒有原生指令，給資料夾路徑；別的 agent 也在讀的標出來",
          shared["how"]["remove_path"] == "~/.agents/skills/shared-old" and shared["shared_with"] == ["Antigravity"])
    check("拿掉：plugin 用原生指令；Claude Code 先給停用，Codex 只有移除",
          cand(codex, "remove:plugin:heavy@m@~/.codex/plugins")["how"]["remove"] == "codex plugin remove heavy@m"
          and "自帶" in how_remove({"kind": "plugin", "name": "pdf@openai-primary-runtime", "where": "~/.codex/plugins"}, "codex")["note"]
          and "自帶" not in cand(codex, "remove:plugin:heavy@m@~/.codex/plugins")["how"]["note"]
          and "disable" not in cand(codex, "remove:plugin:heavy@m@~/.codex/plugins")["how"]
          and how_remove({"kind": "plugin", "name": "p@m", "where": "~/.claude/plugins"}, "claude")
          == {"disable": "claude plugin disable p@m", "remove": "claude plugin uninstall p@m"}
          and how_remove({"kind": "mcp", "name": "s", "where": "~/.claude.json"}, "claude") == {"remove": "claude mcp remove s"})

    check("用內建的就好：答案是內建就夠（有實測）、還沒實測但記了內建功能、名冊的內建卡，三種依據分開標",
          ids(claude, "native") == ["native:browser", "native:review", "native:memory", "native:concise"]
          and cand(claude, "native:browser")["tested"] and cand(claude, "native:browser")["basis"]["evidence"] == "data/evals/b.md"
          and cand(claude, "native:review")["basis"]["code"] == "answer-unknown" and not cand(claude, "native:review")["tested"]
          and cand(claude, "native:memory")["basis"]["code"] == "roster-native" and cand(claude, "native:memory")["builtin"] == "native-memory")
    check("用內建的就好：同一個槽位這台裝的第三方工具一併列出",
          [i["name"] for i in cand(claude, "native:memory")["installed_here"]] == ["mem-tool@m", "mem2"]
          and [i["name"] for i in cand(claude, "native:review")["installed_here"]] == ["bad"])
    check("用內建的就好：分 agent，答案是裝工具的、沒寫內建功能的、內建卡不支援的都不列",
          ids(codex, "native") == ["native:memory"])
    check("內建卡的說明太長會截短", len(cand(claude, "native:memory")["basis"]["text"]) <= CLIP + 1)

    only = diagnose(roster, {**used, "sources": {"claude-code": 12, "codex": 0}}, costs, {"claude": True, "codex": True})
    none = diagnose(roster, used, costs, {"claude": True, "codex": False})
    check("只用一個 agent：沒裝的、這段期間沒有對話紀錄的，不出建議並說明原因",
          not only["agents"]["codex"]["active"] and "沒有對話紀錄" in only["agents"]["codex"]["skip"]
          and not none["agents"]["codex"]["active"] and "沒有裝" in none["agents"]["codex"]["skip"]
          and all(not none["agents"]["codex"]["candidates"][k] for k in KINDS) and only["agents"]["claude"]["active"])
    check("成本量不到（None）：其他依據照常", ids(diagnose(roster, used, None, both)["agents"]["claude"], "remove")
          == ["remove:skill:old@~/.claude/skills", "remove:skill:bad@~/.claude/skills", "remove:skill:mem2@~/.claude/skills"])

    good = {"agent": "claude", "picks": [
        {"id": "install:fe", "reason": "常做前端，名冊的預設還沒裝"},
        {"id": "remove:skill:old@~/.claude/skills", "reason": "三個月沒用到，留著只佔清單"},
        {"id": "native:browser", "reason": "實測內建就拿滿分，不用另外裝"}]}
    errors, agent, chosen = check_picks(facts, good)
    text = "\n".join(render(facts, agent, chosen))
    check("挑選都在候選裡、都有理由：通過", errors == [] and agent == "claude")
    check("建議分三節，每一項有理由、依據與同意後要做的事",
          all(h in text for h in ("## 裝（1 項）", "## 拿掉（1 項）", "## 用內建的就好（1 項）"))
          and "理由：常做前端，名冊的預設還沒裝" in text and "`claude plugin install fe-plugin@mk`" in text
          and "刪掉資料夾 `~/.claude/skills/old`（skill 沒有原生的移除指令）" in text and "（紀錄：data/evals/b.md）" in text
          and "會先問你" in text)
    errors, agent, chosen = check_picks(facts, {"agent": "claude", "picks": [{"id": "native:memory", "reason": "記憶用內建的就夠了"}]})
    check("建議：同一件事另外裝的工具，寫出有沒有在用", "這台同一件事還裝了：mem-tool@m（plugin，4 段對話用到）、mem2（skill，裝了 10 天沒用到）"
          in "\n".join(render(facts, agent, chosen)))
    check("建議：沒挑的候選只列數量；剛裝的與沒有使用紀錄的也交代",
          "候選裡沒有挑的：裝 1 個、拿掉 3 個、用內建的就好 3 個" in text and "先不判斷：4 個" in text
          and "沒有使用紀錄可以判斷（例如 MCP）：2 個" in text and "- 備註" in text)
    bad = {"agent": "claude", "picks": [{"id": "install:not-listed", "reason": "自己想到的工具"},
                                        {"id": "install:fe", "reason": ""}, {"id": "native:browser", "reason": "內建就夠用了"},
                                        {"id": "native:browser", "reason": "內建就夠用了"}]}
    errors, _, _ = check_picks(facts, bad)
    check("候選以外的、沒寫理由的、重複的：都擋下來，不寫建議",
          len(errors) == 3 and "不在候選裡" in errors[0] and "沒有寫理由" in errors[1] and "重複" in errors[2])
    check("挑選檔格式不對、agent 不對、那個 agent 不出建議：都擋下來",
          check_picks(facts, [])[0] and check_picks(facts, {"agent": "gemini", "picks": []})[0]
          and "沒有裝" in check_picks(none, {"agent": "codex", "picks": []})[0][0])
    errors, agent, chosen = check_picks(facts, {"agent": "codex", "picks": [
        {"id": "native:memory", "reason": "名冊沒有實測過更好的"}]})
    text = "\n".join(render(facts, agent, chosen))
    check("某一類沒有建議：照實寫是沒有候選還是沒有挑；Codex 的建議不混進 Claude 的",
          "## 裝（0 項）\n\n- 這一類這次沒有建議：有 2 個候選，都沒有挑" in text and "# OmniKit 建議：Codex" in text
          and "claude plugin" not in text and "還沒有實測證明夠用" in text)
    check("建議裡內建功能的說明只留開頭，不整段貼上", "很長的說明" * 30 not in text and "很長的說明" * 10 in text
          and "很長的說明" * 60 in cand(codex, "native:memory")["basis"]["text"])

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        path = save(["# 建議"], tmp / "state", "2026-11-11", "claude")
        check("建議存在 %LOCALAPPDATA%\\omnikit\\advice\\<日期>-<agent>.md",
              path == tmp / "state" / "advice" / "2026-11-11-claude.md" and path.read_text(encoding="utf-8") == "# 建議\n")

        def offline(*_a, **_k):
            raise RuntimeError("診斷不應該連網")

        real = socket.socket.connect, socket.create_connection
        socket.socket.connect, socket.create_connection = offline, offline
        try:
            empty = collect(tmp / "nobody", validate.ROOT / "data", tmp / "nostate", plugin_details=None)
        finally:
            socket.socket.connect, socket.create_connection = real
        check("真的名冊、空的電腦：不連網也能跑，兩個 agent 都不出建議",
              all(not a["active"] and a["skip"] for a in empty["agents"].values()) and empty["roster"]["slots"] > 0)
        check("只讀不寫：診斷不在狀態資料夾留下任何檔案", not (tmp / "nostate").exists())

        home = tmp / "home"
        (home / ".claude" / "plugins").mkdir(parents=True)
        (home / ".claude" / "plugins" / "known_marketplaces.json").write_text('{"mk": {}}', encoding="utf-8")
        check("marketplace 有沒有加過：看 Claude Code 記的清單", marketplace_added(home, "mk") and not marketplace_added(home, "other")
              and not marketplace_added(tmp / "nobody", "mk"))

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="OmniKit 診斷後給建議：事實與候選（JSON），或驗證挑選並寫出建議")
    parser.add_argument("--agent", choices=sorted(AGENTS), help="只看一個 agent；不給就兩個都列")
    parser.add_argument("--days", type=int, default=30, help="多少天沒用到算「沒在用」，預設 30")
    parser.add_argument("--picks", type=Path, help="agent 挑選的結果（JSON 檔）：驗證後寫出建議")
    parser.add_argument("--no-save", action="store_true", help="只印出來，不存到 %%LOCALAPPDATA%%\\omnikit\\advice")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    facts = collect(Path.home(), profiles.DATA, profiles.STATE, days=args.days)
    if not args.picks:
        if args.agent:
            facts["agents"] = {args.agent: facts["agents"][args.agent]}
        print(json.dumps(facts, ensure_ascii=False, indent=2))
        return 0
    try:
        picks = json.loads(args.picks.read_bytes().decode("utf-8-sig"))
    except (OSError, ValueError) as e:
        print(f"讀不到挑選檔 {args.picks}：{e}")
        return 1
    errors, agent, chosen = check_picks(facts, picks)
    if errors:
        print("挑選有問題，沒有寫出建議：")
        print("\n".join(f"- {e}" for e in errors))
        return 1
    lines = render(facts, agent, chosen)
    if not args.no_save:
        lines += ["", f"完整內容存在：{save(lines, profiles.STATE, facts['generated'], agent)}"]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
