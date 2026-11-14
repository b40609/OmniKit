# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""通知（FR-16，含 FR-19 的頻率與靜音）：有更好的選擇或試用到期時，在 session 的第一回合結束時顯示一行。

證據等級（PRD 的 E0 到 E4）只取 OmniKit 自己的紀錄，工具卡上沒有這個欄位：
- E4（實測勝出）：data/evals/*/result.json 依規則判定 Update、勝出的是名冊上的工具；或槽位在這個 agent 的答案是
  「裝某張卡」，而且依據指到 data/evals/ 裡真的存在的實測紀錄（維護者依實測決定）。
- E3（初測通過）：data/funnel/smoke/<id>.json 裝得起來、有被叫用，而且 data/funnel/layer1/<id>.json 建議深評。
  PRD 的 E3 還要「資格賽贏過現任」，資格賽目前沒有獨立紀錄，先用第 1 層的深評建議代替（待驗證）。
- E0 到 E2 不通知，這裡也不算。
E4 主動通知一次；E3 只進個人週報（weekly.py 第 3 區）。

怎麼顯示（照 gh、update-notifier 的做法：背景算、下次顯示，一天最多算一次）：
1. plan：讀名冊、實測紀錄與這台裝了什麼，算出每個 agent 還沒裝的 E3、E4 候選，存到
   %LOCALAPPDATA%\\omnikit\\notify\\queue.json。要讀名冊（pyyaml），所以由 hook 在背景開一個 uv 跑，不擋對話。
2. due：session_nudge.py（Stop hook）在一個主線 session 的第一回合呼叫，只讀 JSON（不用 pyyaml）：
   - 試用到期（swaps.json 裡試用中、已過試用期限的）先提，每個替換提一次。
   - 再來是 E4：每週最多 1 則；同一個工具同一份證據只提一次；同一個槽位提過之後 30 天內不再提，除非證據換了。
   - 試用到期與 E4 合計每週最多 3 則；每個 session 最多 1 則。
   - 不顯示：子對話、CI（環境變數 CI）、OMNIKIT_NO_NOTIFY、Codex 的 exec（非互動），以及靜音。
   顯示過的記在 notify\\shown.json（只有槽位、工具 id、依據的路徑與日期）。
3. mute：說「OmniKit 通知靜音」就全部靜音；也可以只靜音一個工具。unmute 打開。

這支腳本只讀名冊與紀錄、只寫 %LOCALAPPDATA%\\omnikit\\notify\\，不安裝、不連網；要換工具一律走「給我建議」與 swap.py。

用法：
  uv run engine/scripts/notify.py plan [--print]
  uv run engine/scripts/notify.py list
  uv run engine/scripts/notify.py mute [--tool <卡片 id>]
  uv run engine/scripts/notify.py unmute [--tool <卡片 id>]
  uv run engine/scripts/notify.py --selftest
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STATE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "omnikit"  # 跟 profiles.STATE 一樣；這裡不能匯入 pyyaml
AGENTS = {"claude": "claude-code", "codex": "codex"}
LABELS = {"claude": "Claude Code", "codex": "Codex"}
WEEK_BETTER = 1   # FR-16：主動通知每人每週最多 1 則
WEEK_TOTAL = 3    # FR-19：通知與主動建議合計每週最多 3 則
QUIET_DAYS = 30   # FR-16：同一個槽位判定之後，30 天內不再通知同一類工具，除非有新證據
STALE_DAYS = 3    # 候選清單超過這麼多天沒更新就不拿來通知（可能已經裝了）
LEVELS = {"E4": "實測勝出", "E3": "初測通過"}


# ---------- 檔案 ----------

def folder(state):
    return state / "notify"


def read_json(path, default):
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return doc if isinstance(doc, type(default)) else default


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes((json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    os.replace(tmp, path)


def days_between(a, b):
    try:
        return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
    except ValueError:
        return None


def same_week(a, b):
    try:
        return date.fromisoformat(str(a)[:10]).isocalendar()[:2] == b.isocalendar()[:2]
    except ValueError:
        return False


# ---------- 證據等級（要讀名冊，只在 plan 與週報用） ----------

def levels(roster, repo):
    """[{slot, tool, level, evidence, source, agents}]；agents 是 None 表示每個 agent 都適用。"""
    tools, slots = roster["tools"], {s["id"]: s for s in roster["slots"]}
    out = []
    for path in sorted((repo / "data" / "evals").glob("*/result.json")):
        r = read_json(path, {})
        if (r.get("verdict") == "Update" and r.get("decided_by") == "rule" and r.get("winner") in tools
                and r.get("slot") in slots):
            out.append({"slot": r["slot"], "tool": r["winner"], "level": "E4", "agents": None, "source": "result",
                        "evidence": r.get("eval_doc") or path.relative_to(repo).as_posix()})
    for s in roster["slots"]:
        for agent, a in (s.get("answers") or {}).items():
            ev = str(a.get("evidence") or "")
            if (a.get("verdict") == "tool" and a.get("tool") in tools and ev.startswith("data/evals/")
                    and (repo / ev).exists()):
                out.append({"slot": s["id"], "tool": a["tool"], "level": "E4", "agents": [agent], "source": "answer",
                            "evidence": ev})
    funnel = repo / "data" / "funnel"
    for card in tools.values():
        smoke = read_json(funnel / "smoke" / f"{card['id']}.json", {})
        layer1 = read_json(funnel / "layer1" / f"{card['id']}.json", {})
        invoked = any(isinstance(r, dict) and r.get("invoked") is True for r in (smoke.get("run") or {}).values())
        if (smoke.get("install") or {}).get("ok") is True and invoked and layer1.get("recommendation") == "deep_eval":
            for slot in card.get("slots") or []:
                # 已經有每個 agent 都適用的 E4 就不另列 E3；E4 只適用某個 agent 時，其他 agent 還是 E3
                if slot in slots and not any(x["slot"] == slot and x["tool"] == card["id"] and x["agents"] is None for x in out):
                    out.append({"slot": slot, "tool": card["id"], "level": "E3", "agents": None, "source": "smoke",
                                "evidence": f"data/funnel/smoke/{card['id']}.json"})
    return out


def installed(home, tools):
    """這台每個 agent 裝了哪些名冊上的工具：{agent: {卡片 id}}。只讀清單檔，不跑 agent 的指令。"""
    import cost
    import scan
    import usage
    have = {a: set() for a in AGENTS}
    items = usage.inventory(home, set(), usage.created)
    for agent, uid in AGENTS.items():
        names = scan.mcp_names(uid, home)
        items += [{"kind": "mcp", "name": n, "agents": [uid], "match": []} for n in names if isinstance(names, list)]
    third = {k: v for k, v in tools.items() if v.get("kind") != "native"}
    for item in items:
        card = cost.roster_card(item, third)
        for agent, uid in AGENTS.items():
            if card and uid in item["agents"]:
                have[agent].add(card["id"])
    return have


def candidates(roster, repo, have, found, edition, swaps, today):
    """每個 agent 還沒裝、E3 以上的工具：{agent: [候選]}。打平或判定維持現任的不會在 levels 裡，所以不會通知。"""
    import swap
    tools = roster["tools"]
    hidden = {m["id"] for m in roster["modules"] if m.get("maintainer_only") and edition != "maintainer"}
    enabled = roster.get("enabled")
    slots = {s["id"]: s for s in roster["slots"]
             if s["module"] not in hidden and (enabled is None or s["module"] in enabled)}
    out = {a: [] for a in AGENTS}
    for agent in AGENTS:
        if not found.get(agent):
            continue
        quiet = swap.recent(swaps, agent, today)
        for e in levels(roster, repo):
            card, slot = tools.get(e["tool"]), slots.get(e["slot"])
            if (not card or not slot or card.get("kind") == "native" or card["status"] in ("rejected", "retired")
                    or (card.get("works_with") and agent not in card["works_with"])
                    or (e["agents"] and agent not in e["agents"]) or card["id"] in have.get(agent, set())
                    or (slot["id"], card["id"]) in quiet):
                continue
            if any(c["key"] == f"{slot['id']}:{card['id']}" for c in out[agent]):
                continue  # levels 先列 E4 再列 E3，先到的等級比較高
            out[agent].append({"key": f"{slot['id']}:{card['id']}", "slot": slot["id"], "slot_name": slot.get("name", slot["id"]),
                               "tool": card["id"], "name": card.get("name", card["id"]), "level": e["level"],
                               "evidence": e["evidence"], "source": e["source"]})
    return out


def plan(home, data, state, today):
    """算出候選並存成 queue.json。名冊驗證沒過就記下原因、沒有候選。"""
    import edition as editions
    import swap
    import validate
    repo = data.parent
    errors, roster = validate.check(data, state=state, private=True)
    doc = {"generated": today.isoformat(), "agents": {a: [] for a in AGENTS}}
    if errors:
        doc["error"] = f"名冊驗證沒過（{len(errors)} 項），這次沒有候選"
    else:
        found = {"claude": (home / ".claude").is_dir(), "codex": (home / ".codex").is_dir()}
        doc["agents"] = candidates(roster, repo, installed(home, roster["tools"]), found,
                                   editions.resolve(state, repo)[0], swap.load(state), today)
    write_json(folder(state) / "queue.json", doc)
    return doc


# ---------- 挑哪一則（只讀 JSON，給 hook 用） ----------

def better_text(c, agent):
    return (f"「{c['slot_name']}」有 OmniKit {LEVELS[c['level']]}的 {c['name']}（{LABELS[agent]} 還沒裝；依據 {c['evidence']}）。"
            "想試 14 天就說「OmniKit 給我建議」；不想再看到這類通知就說「OmniKit 通知靜音」。")


SHADOW_DAYS = 3  # 到期前幾天提醒可以做影子比對


def trial_text(s, shadow=None):
    evidence = (f"{shadow}（細節：shadow.py status {s['id']}）。" if shadow else
                "這次沒有影子比對，只能憑使用感覺決定。")
    return (f"{s['old']['name']} 換成 {s['new']['name']} 的 14 天試用在 {s['trial_until']} 到期了。{evidence}"
            f"說「留下 {s['new']['name']}」或「換回 {s['old']['name']}」（swap.py keep／revert {s['id']}）。")


def shadow_text(s, left):
    return (f"{s['old']['name']} 換成 {s['new']['name']} 的試用 {left} 天後（{s['trial_until']}）到期。"
            f"想在決定前並排比比看，就說「OmniKit 影子比對」：拿試用期間的真實任務用 {s['old']['name']} 重跑，讓你盲選"
            f"（shadow.py record {s['id']}）。")


def shadows_of(state, swaps):
    """每個替換的影子比對結果（只讀 JSON，給 hook 用）。"""
    out = {}
    for s in swaps:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        doc = read_json(state / "shadow" / str(s["id"]) / "result.json", {})
        if isinstance(doc, dict) and doc.get("summary"):
            out[s["id"]] = doc["summary"]
    return out


def pick(queue, shown, mute, swaps, agent, today, shadows=None):
    """回傳（訊息, 要記下的紀錄）或 None。"""
    if mute.get("all"):
        return None
    week = [s for s in shown if same_week(s.get("date"), today)]
    if len(week) >= WEEK_TOTAL:
        return None
    keys = {s.get("key") for s in shown}
    shadows = shadows or {}
    for s in swaps:
        left = days_between(today, s.get("trial_until"))
        if (s.get("agent") == agent and s.get("state") == "trial" and left is not None and left < 0
                and f"trial:{s['id']}" not in keys):
            return trial_text(s, shadows.get(s["id"])), {"key": f"trial:{s['id']}", "kind": "trial", "agent": agent,
                                                          "date": today.isoformat()}
    for s in swaps:
        left = days_between(today, s.get("trial_until"))
        if (s.get("agent") == agent and s.get("state") == "trial" and left is not None and 0 <= left <= SHADOW_DAYS
                and s["id"] not in shadows and f"shadow:{s['id']}" not in keys):
            return shadow_text(s, left), {"key": f"shadow:{s['id']}", "kind": "trial", "agent": agent, "date": today.isoformat()}
    if sum(1 for s in week if s.get("kind") == "better") >= WEEK_BETTER:
        return None
    age = days_between(queue.get("generated"), today)
    if age is None or age > STALE_DAYS:
        return None
    muted = set(mute.get("tools") or [])
    for c in (queue.get("agents") or {}).get(agent) or []:
        if c.get("level") != "E4" or c.get("tool") in muted:
            continue
        before = [s for s in shown if s.get("kind") == "better" and s.get("slot") == c["slot"]]
        if any(s.get("key") == c["key"] and s.get("evidence") == c["evidence"] for s in before):
            continue  # 主動通知一次
        if any((days_between(s.get("date"), today) or 0) < QUIET_DAYS and s.get("evidence") == c["evidence"] for s in before):
            continue  # 同一個槽位 30 天內不再提，除非證據換了
        return better_text(c, agent), {"key": c["key"], "kind": "better", "agent": agent, "slot": c["slot"],
                                       "tool": c["tool"], "evidence": c["evidence"], "date": today.isoformat()}
    return None


def silenced(env):
    return bool(env.get("CI") or env.get("OMNIKIT_NO_NOTIFY"))


def refresh(state, today, spawn=None):
    """候選清單不是今天算的，而且今天還沒開始算：在背景開一個 uv 算（一天最多一次），這次照舊用舊的。"""
    queue = read_json(folder(state) / "queue.json", {})
    mark = folder(state) / "planning"
    if queue.get("generated") == today.isoformat() or read_json(mark, {}).get("date") == today.isoformat():
        return False
    write_json(mark, {"date": today.isoformat()})
    (spawn or spawn_plan)()
    return True


def spawn_plan():
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        return
    flags = (subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    subprocess.Popen([uv, "run", "--quiet", "--script", str(Path(__file__).resolve()), "plan"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, start_new_session=os.name != "nt", close_fds=True)


def due(agent, state=STATE, today=None, env=None, spawn=None):
    """session 第一回合要顯示的一則通知（沒有就是 None），顯示了就記下來。任何錯誤都當成沒有。"""
    env = os.environ if env is None else env
    if silenced(env):
        return None
    today = today or date.today()
    try:
        refresh(state, today, spawn)
    except Exception:  # 背景更新失敗不影響這次
        pass
    d = folder(state)
    shown = read_json(d / "shown.json", {}).get("shown") or []
    swaps = read_json(state / "swaps.json", {}).get("swaps") or []
    got = pick(read_json(d / "queue.json", {}), shown, read_json(d / "mute.json", {}), swaps, agent, today, shadows_of(state, swaps))
    if not got:
        return None
    write_json(d / "shown.json", {"shown": [*shown, got[1]]})
    return got[0]


# ---------- 週報與指令 ----------

def week_count(state, today):
    return sum(1 for s in read_json(folder(state) / "shown.json", {}).get("shown") or [] if same_week(s.get("date"), today))


def report(found_candidates, state, today):
    """個人週報第 3 區「有更好的選擇（E3、E4）」的內容。"""
    lines = []
    for agent, items in found_candidates.items():
        for c in sorted(items, key=lambda c: (c["level"], c["slot"]), reverse=True):
            how = "會主動通知一次" if c["level"] == "E4" else "只列在週報"
            lines.append(f"- {c['level']}（{LEVELS[c['level']]}，{how}）：{LABELS[agent]}「{c['slot_name']}」：{c['name']}"
                         f"（依據 {c['evidence']}）")
    if not lines:
        lines.append("- 沒有：名冊裡 E3 以上、這台還沒裝的工具一個都沒有（打平或判定維持現任的不列）")
    else:
        lines.append("- 要試就跟 agent 說「OmniKit 給我建議」，走預覽、同意、14 天試用、可以換回的流程")
    mute = read_json(folder(state) / "mute.json", {})
    lines.append(f"- 這週已經通知 {week_count(state, today)} 則（每週最多 {WEEK_TOTAL} 則，其中更好的選擇最多 {WEEK_BETTER} 則）"
                 + ("；通知已全部靜音，說「OmniKit 通知打開」可以打開" if mute.get("all") else ""))
    return lines


def better_section(env, today):
    """weekly.py 用：重新算一次（不用 queue），回傳第 3 區的行。"""
    import edition as editions
    import swap
    import validate
    errors, roster = validate.check(env.data, state=env.state, private=True)
    if errors:
        return [f"- 未知：名冊驗證沒過（{len(errors)} 項）"]
    found = {"claude": (env.home / ".claude").is_dir(), "codex": (env.home / ".codex").is_dir()}
    cands = candidates(roster, env.repo, installed(env.home, roster["tools"]), found,
                       editions.resolve(env.state, env.repo)[0], swap.load(env.state), today)
    return report(cands, env.state, today)


def set_mute(state, tool=None, on=True):
    path = folder(state) / "mute.json"
    mute = read_json(path, {})
    if tool:
        tools = set(mute.get("tools") or [])
        mute["tools"] = sorted(tools | {tool} if on else tools - {tool})
    else:
        mute["all"] = on
    write_json(path, mute)
    return mute


def listing(state, today):
    d = folder(state)
    queue, mute = read_json(d / "queue.json", {}), read_json(d / "mute.json", {})
    lines = [f"候選清單：{queue.get('generated') or '還沒算過'}" + (f"（{queue['error']}）" if queue.get("error") else "")]
    for agent, items in (queue.get("agents") or {}).items():
        for c in items:
            lines.append(f"- {LABELS.get(agent, agent)}：{c['level']} {c['slot_name']}：{c['name']}（{c['evidence']}）")
    lines.append(f"這週通知了 {week_count(state, today)} 則；靜音：" + ("全部" if mute.get("all") else
                                                                 "、".join(mute.get("tools") or []) or "沒有"))
    return lines


# ---------- 自我測試 ----------

def selftest():
    import yaml
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    import profiles
    check("狀態資料夾跟 profiles.STATE 一樣", STATE == profiles.STATE)

    today = date(2026, 11, 16)  # 星期一
    cand = {"key": "web:acme", "slot": "web", "slot_name": "網頁", "tool": "acme", "name": "Acme", "level": "E4",
            "evidence": "data/evals/a.md", "source": "result"}
    e3 = {**cand, "key": "web:beta", "tool": "beta", "name": "Beta", "level": "E3", "evidence": "data/funnel/smoke/beta.json"}
    queue = {"generated": "2026-11-16", "agents": {"claude": [e3, cand], "codex": []}}
    got = pick(queue, [], {}, [], "claude", today)
    check("E4 主動通知；E3 不通知", got and "Acme" in got[0] and "Beta" not in got[0] and got[1]["kind"] == "better")
    check("通知寫明怎麼試、怎麼靜音", got and "OmniKit 給我建議" in got[0] and "通知靜音" in got[0])
    check("別的 agent 沒有候選就不通知", pick(queue, [], {}, [], "codex", today) is None)
    rec = got[1]
    check("同一個工具同一份證據只通知一次（過了 30 天也不再提）",
          pick(queue, [{**rec, "date": "2026-09-01"}], {}, [], "claude", today) is None)
    check("同一週已經主動通知過 1 則：這週不再通知更好的選擇",
          pick(queue, [{"key": "x:y", "kind": "better", "slot": "x", "evidence": "e", "date": "2026-11-17"}], {}, [],
               "claude", date(2026, 11, 18)) is None)
    other = {**cand, "key": "web:gamma", "tool": "gamma", "name": "Gamma"}
    q2 = {"generated": "2026-11-16", "agents": {"claude": [other]}}
    check("同一個槽位 30 天內不再提同一份證據的另一個工具",
          pick(q2, [{**rec, "date": "2026-10-30"}], {}, [], "claude", today) is None)
    check("同一個槽位有新證據：30 天內也可以提",
          pick({"generated": "2026-11-16", "agents": {"claude": [{**other, "evidence": "data/evals/b.md"}]}},
               [{**rec, "date": "2026-10-30"}], {}, [], "claude", today) is not None)
    check("同一個槽位過了 30 天：可以提另一個工具", pick(q2, [{**rec, "date": "2026-10-01"}], {}, [], "claude", today) is not None)
    check("全部靜音：什麼都不提", pick(queue, [], {"all": True}, [], "claude", today) is None)
    check("只靜音這個工具：不提它", pick(queue, [], {"tools": ["acme"]}, [], "claude", today) is None)
    check("候選清單太舊（可能已經裝了）：不拿來通知",
          pick({**queue, "generated": "2026-11-10"}, [], {}, [], "claude", today) is None)

    trial = {"id": "s1", "agent": "claude", "state": "trial", "trial_until": "2026-11-15", "old": {"name": "Old"},
             "new": {"name": "New"}}
    got = pick(queue, [], {}, [trial], "claude", today)
    check("試用到期先提，寫明留下或換回", got and got[1]["key"] == "trial:s1" and "留下 New" in got[0] and "換回 Old" in got[0])
    check("試用還沒到期、離到期還超過 3 天：不提", pick({}, [], {}, [{**trial, "trial_until": "2026-11-20"}], "claude", today) is None)
    check("到期通知沒有影子比對：照實說只能憑感覺", "沒有影子比對" in got[0])
    got = pick({}, [], {}, [trial], "claude", today, {"s1": "影子比對 2 筆：New 勝 2"})
    check("到期通知附上影子比對的結果", got and "影子比對 2 筆：New 勝 2" in got[0] and "shadow.py status s1" in got[0])
    soon = {**trial, "trial_until": "2026-11-19"}
    got = pick({}, [], {}, [soon], "claude", today)
    check("到期前 3 天內：提醒可以做影子比對", got and got[1]["key"] == "shadow:s1" and "OmniKit 影子比對" in got[0] and "3 天後" in got[0])
    check("影子比對的提醒只提一次", pick({}, [{"key": "shadow:s1", "kind": "trial", "date": "2026-11-16"}], {}, [soon],
                                       "claude", today) is None)
    check("已經有影子比對結果：不再提醒", pick({}, [], {}, [soon], "claude", today, {"s1": "x"}) is None)
    check("到期當天（還剩 0 天）也提醒", pick({}, [], {}, [{**trial, "trial_until": "2026-11-16"}], "claude", today)[1]["key"] == "shadow:s1")
    check("已經換回或留下的：不提", pick({}, [], {}, [{**trial, "state": "kept"}], "claude", today) is None)
    check("別的 agent 的試用：不提", pick({}, [], {}, [{**trial, "agent": "codex"}], "claude", today) is None)
    check("試用到期每個替換只提一次", pick({}, [{"key": "trial:s1", "kind": "trial", "date": "2026-11-16"}], {}, [trial],
                                         "claude", date(2026, 11, 17)) is None)
    full = [{"key": f"k{i}", "kind": "trial", "date": "2026-11-16"} for i in range(WEEK_TOTAL)]
    check("這週已經 3 則：連試用到期也不提", pick(queue, full, {}, [trial], "claude", today) is None)
    check("上週的不算進這週", pick(queue, [{**s, "date": "2026-11-15"} for s in full], {}, [], "claude", today) is not None)
    check("試用到期不佔更好的選擇的每週 1 則",
          pick(queue, [{"key": "trial:s0", "kind": "trial", "date": "2026-11-16"}], {}, [], "claude", today) is not None)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        state = tmp / "state"
        spawned = []
        write_json(folder(state) / "queue.json", queue)
        msg = due("claude", state, today, env={}, spawn=lambda: spawned.append(1))
        check("due：顯示一則並記下來", msg and "Acme" in msg
              and read_json(folder(state) / "shown.json", {})["shown"][0]["tool"] == "acme")
        check("due：候選清單今天算過就不在背景重算", spawned == [])
        check("due：同一份候選第二個 session 不再提", due("claude", state, today, env={}, spawn=lambda: None) is None)
        quiet_state = tmp / "quiet"
        write_json(folder(quiet_state) / "queue.json", queue)
        check("due：CI 與 OMNIKIT_NO_NOTIFY 不顯示、也不記",
              due("claude", quiet_state, today, env={"CI": "true"}) is None
              and due("claude", quiet_state, today, env={"OMNIKIT_NO_NOTIFY": "1"}) is None and spawned == []
              and not (folder(quiet_state) / "shown.json").exists()
              and due("claude", quiet_state, today, env={}, spawn=lambda: None) is not None)
        write_json(folder(state) / "queue.json", {**queue, "generated": "2026-11-15"})
        due("claude", state, today, env={}, spawn=lambda: spawned.append(1))
        due("claude", state, today, env={}, spawn=lambda: spawned.append(1))
        check("due：候選清單舊了就在背景重算，一天最多一次", spawned == [1])
        broken = tmp / "broken"
        for name in ("queue.json", "shown.json", "mute.json"):
            write_json(folder(broken) / name, "壞掉")
        write_json(broken / "swaps.json", ["壞掉"])
        check("due：檔案壞了當成沒有，不丟例外", due("claude", broken, today, env={}, spawn=lambda: None) is None)
        st2 = tmp / "shadowed"
        write_json(st2 / "swaps.json", {"swaps": [trial, "壞掉"]})
        write_json(st2 / "shadow" / "s1" / "result.json", {"summary": "影子比對 3 筆：New 勝 2、Old 勝 1"})
        msg = due("claude", st2, today, env={}, spawn=lambda: None)
        check("due：到期通知讀得到影子比對的結果", msg and "New 勝 2、Old 勝 1" in msg)
        set_mute(state, tool="acme")
        set_mute(state)
        check("mute：全部與單一工具分開記", read_json(folder(state) / "mute.json", {}) == {"tools": ["acme"], "all": True})
        set_mute(state, on=False)
        set_mute(state, tool="acme", on=False)
        check("unmute：打開", read_json(folder(state) / "mute.json", {}) == {"tools": [], "all": False})

        # 證據等級與候選：用最小的名冊
        repo = tmp / "repo"
        (repo / "data" / "evals" / "x").mkdir(parents=True)
        (repo / "data" / "evals" / "x.md").write_text("紀錄", encoding="utf-8")
        write_json(repo / "data" / "evals" / "x" / "result.json",
                   {"slot": "web", "verdict": "Update", "winner": "acme", "eval_doc": "data/evals/x.md", "decided_by": "rule"})
        write_json(repo / "data" / "evals" / "k" / "result.json",
                   {"slot": "web", "verdict": "Keep", "winner": "zeta", "eval_doc": "data/evals/k.md", "decided_by": "rule"})
        write_json(repo / "data" / "evals" / "u" / "result.json",
                   {"slot": "web", "verdict": "Update", "winner": "zeta", "eval_doc": "data/evals/u.md", "decided_by": "user"})
        write_json(repo / "data" / "funnel" / "smoke" / "beta.json",
                   {"tool": "beta", "install": {"ok": True}, "run": {"claude": {"invoked": True, "noninteractive": True}}})
        write_json(repo / "data" / "funnel" / "layer1" / "beta.json", {"recommendation": "deep_eval"})
        write_json(repo / "data" / "funnel" / "smoke" / "zeta.json",
                   {"tool": "zeta", "install": {"ok": True}, "run": {"claude": {"invoked": False}}})
        write_json(repo / "data" / "funnel" / "layer1" / "zeta.json", {"recommendation": "deep_eval"})
        for tid, ok, rec in (("bad", False, "deep_eval"), ("keep", True, "keep_pending"), ("cdx", True, "deep_eval"),
                             ("wcx", True, "deep_eval")):
            write_json(repo / "data" / "funnel" / "smoke" / f"{tid}.json",
                       {"tool": tid, "install": {"ok": ok}, "run": {"claude": {"invoked": True}}})
            write_json(repo / "data" / "funnel" / "layer1" / f"{tid}.json", {"recommendation": rec})

        def card(i, **kw):
            return {"id": i, "name": i.title(), "kind": "plugin", "status": "pending", "slots": ["web"], **kw}

        roster = {"tools": {"acme": card("acme"), "beta": card("beta"), "zeta": card("zeta"), "rej": card("rej", status="rejected"),
                            "cdx": card("cdx"), "dev": card("dev", slots=["ops"]), "bad": card("bad"),
                            "keep": card("keep"), "wcx": card("wcx", works_with=["codex"]), "ans": card("ans"),
                            "url": card("url"), "gone": card("gone")},
                  "modules": [{"id": "core"}, {"id": "maint", "maintainer_only": True}],
                  "slots": [{"id": "web", "name": "網頁", "module": "core", "answers": {
                                "codex": {"verdict": "tool", "tool": "cdx", "evidence": "data/evals/x.md"},
                                "claude": {"verdict": "tool", "tool": "rej", "evidence": "data/evals/x.md"}}},
                            {"id": "web2", "name": "網頁二", "module": "core", "answers": {
                                "codex": {"verdict": "tool", "tool": "ans", "evidence": "data/evals/x.md"},
                                "claude": {"verdict": "tool", "tool": "url", "evidence": "data/funnel/smoke/beta.json"}}},
                            {"id": "web3", "name": "網頁三", "module": "core", "answers": {
                                "claude": {"verdict": "tool", "tool": "gone", "evidence": "data/evals/missing.md"}}},
                            {"id": "ops", "name": "維運", "module": "maint", "answers": {
                                "claude": {"verdict": "tool", "tool": "dev", "evidence": "data/evals/x.md"}}}]}
        found = levels(roster, repo)
        got = {(e["tool"], e["level"]) for e in found}
        check("E4：依規則判定 Update 的勝出者；依使用者決定或 Keep 的不算",
              ("acme", "E4") in got and ("zeta", "E4") not in got)
        check("E4：答案指到 data/evals/ 裡存在的紀錄；只適用那個 agent",
              any(e["tool"] == "cdx" and e["agents"] == ["codex"] for e in found))
        check("E3：裝得起來、有被叫用、第 1 層建議深評；沒被叫用的不算", ("beta", "E3") in got and ("zeta", "E3") not in got)
        cands = candidates(roster, repo, {"claude": set(), "codex": {"acme"}}, {"claude": True, "codex": True},
                           "colleague", [], today)
        names = {a: sorted((c["tool"], c["level"]) for c in v) for a, v in cands.items()}
        check("候選：拒絕的、不支援這個 agent 的、維護者限定模組的都不列",
              names["claude"] == [("acme", "E4"), ("beta", "E3"), ("cdx", "E3")])
        check("候選：裝了的不列；答案只給 codex 的只列給 codex（同一個工具在 codex 是 E4、在 claude 是 E3）",
              names["codex"] == [("ans", "E4"), ("beta", "E3"), ("cdx", "E4"), ("wcx", "E3")])
        check("E3、E4 不算：裝不起來、第 1 層沒建議深評、依據不是 data/evals/ 或檔案不存在",
              not {"bad", "keep", "url", "gone"} & {e["tool"] for e in found})
        check("候選：只看 profile 選的模組",
              candidates({**roster, "enabled": ["other"]}, repo, {}, {"claude": True}, "colleague", [], today)["claude"] == [])
        check("維護者版：維護者限定模組也看",
              ("dev", "E4") in [(c["tool"], c["level"]) for c in candidates(roster, repo, {}, {"claude": True}, "maintainer",
                                                                             [], today)["claude"]])
        check("這台沒裝的 agent 不列", candidates(roster, repo, {}, {"claude": True}, "colleague", [], today)["codex"] == [])
        reverted = [{"agent": "claude", "state": "reverted", "reverted": "2026-11-10", "slot": "web", "new": {"tool": "acme"}}]
        check("換回不到 30 天的工具不列",
              "acme" not in [c["tool"] for c in candidates(roster, repo, {}, {"claude": True}, "colleague", reverted, today)["claude"]])
        check("週報：E4 寫會通知、E3 寫只列在週報，並附這週通知了幾則",
              (lambda t: "E4（實測勝出，會主動通知一次）：Claude Code「網頁」：Acme" in t and "E3（初測通過，只列在週報）" in t
               and "這週已經通知" in t)("\n".join(report(cands, state, today))))
        check("週報：沒有候選時照實說沒有", report({"claude": []}, state, today)[0].startswith("- 沒有："))

        # 用真的名冊與真的 data/ 跑一次 levels：證據路徑都要存在
        import validate
        errors, real = validate.check(REPO / "data", state=tmp / "empty")
        check("真的名冊：驗證通過", not errors)
        real_levels = levels(real, REPO) if not errors else []
        check("真的名冊：每個 E3、E4 的依據都指到存在的檔案", all((REPO / e["evidence"]).exists() for e in real_levels))
        del yaml

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="OmniKit 通知")
    parser.add_argument("action", nargs="?", choices=["plan", "list", "mute", "unmute"])
    parser.add_argument("--tool", help="只靜音或打開這張卡片 id 的通知")
    parser.add_argument("--print", action="store_true", help="plan 算完印出候選")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.action == "plan":
        doc = plan(Path.home(), REPO / "data", STATE, args.today)
        if args.print:
            print("\n".join(listing(STATE, args.today)))
        return 1 if doc.get("error") else 0
    if args.action in ("mute", "unmute"):
        set_mute(STATE, args.tool, on=args.action == "mute")
        what = f"工具 {args.tool} 的通知" if args.tool else "全部通知"
        print(f"已{'靜音' if args.action == 'mute' else '打開'}{what}（記在 {folder(STATE) / 'mute.json'}）")
        return 0
    if args.action == "list":
        print("\n".join(listing(STATE, args.today)))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
