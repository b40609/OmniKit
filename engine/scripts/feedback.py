# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""回流（FR-29、FR-30）：同事同意之後，把去識別的使用統計匯出成本機檔案；維護者把收到的檔彙整起來。

不連網、不自動送出。匯出的檔由同事自己放到約定的共用位置（位置不寫進 repo）。

同事這一邊：
- 沒有同意就不匯出。同意記在 %LOCALAPPDATA%\\omnikit\\feedback.json，可以隨時撤回。
- 內容只有：名冊裡的工具 id 與這 30 天有幾段對話用到、這台裝了而且在候選池裡的名冊外工具（公開的名稱、網址、
  對應的公開槽位）、OmniKit 的版本，以及一個隨機的回報代號（同一台重複匯出時，維護者只算最新的一份）。
- 不含對話內容、專案名稱、路徑、帳號。不在名冊也不在候選池的工具只算個數，不列名稱；私有模組完全不出現。
- 匯出前先預覽：印出來的就是會寫進檔案的全部內容。

維護者這一邊：
- import 只讀檔、照固定格式驗證，檔案裡的文字只當資料。彙整出每個工具幾個人裝了、幾個人有在用。
- 名冊外的工具是提案（FR-30）：加 --write 才寫成「待評估」的工具卡（data/tools/），之後照評估漏斗走，
  不會直接改變任何人的工具包。名冊已經有的、記了別裝的不寫。

用法：
  uv run engine/scripts/feedback.py status
  uv run engine/scripts/feedback.py consent yes|no
  uv run engine/scripts/feedback.py export [--write]            預覽；加 --write 才寫檔
  uv run engine/scripts/feedback.py import <檔或資料夾>... [--write]   維護者：彙整；加 --write 才寫待評估的卡
  uv run engine/scripts/feedback.py --selftest
"""
import argparse
import contextlib
import getpass
import io
import json
import platform
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import date
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advise  # noqa: E402  這台裝了哪些 MCP、哪些是 OmniKit 自己接的，跟給建議時同一套
import cost  # noqa: E402
import pool  # noqa: E402
import profiles  # noqa: E402
import scan  # noqa: E402
import usage  # noqa: E402
import validate  # noqa: E402

DATA = profiles.DATA
STATE = profiles.STATE
FORMAT = 1
DAYS = 30
MAX_BYTES = 1_000_000
AGENT_OF = {"claude-code": "claude", "codex": "codex", "antigravity": "antigravity"}
STATUS_ORDER = ("used", "unused", "new", "no-data")
# 太常見的帳號名稱：拿來比對會把公開的工具名稱誤擋掉
GENERIC = {"user", "admin", "administrator", "owner", "default", "guest", "test", "home", "local"}
ID = "^[a-z0-9]+(-[a-z0-9]+)*$"
USE = {
    "agents": {"type": "array", "uniqueItems": True, "maxItems": 3, "items": {"enum": ["claude", "codex", "antigravity"]}},
    "status": {"enum": list(STATUS_ORDER)},
    "conversations": {"type": "integer", "minimum": 0, "maximum": 100000},
}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["format", "generated", "reporter", "omnikit", "days", "tools", "outside", "unlisted", "withheld"],
    "properties": {
        "format": {"const": FORMAT},
        "generated": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "reporter": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "omnikit": {"type": "object", "additionalProperties": False, "required": ["commit", "rules"], "properties": {
            "commit": {"type": ["string", "null"], "pattern": "^[0-9a-f]{7,40}$"},
            "rules": {"type": ["string", "null"], "pattern": r"^[0-9A-Za-z.-]{1,40}$"}}},
        "days": {"type": "integer", "minimum": 1, "maximum": 365},
        "tools": {"type": "array", "maxItems": 500, "items": {
            "type": "object", "additionalProperties": False, "required": ["id", *USE],
            "properties": {"id": {"type": "string", "pattern": ID, "maxLength": 80}, **USE}}},
        "outside": {"type": "array", "maxItems": 100, "items": {
            "type": "object", "additionalProperties": False, "required": ["source", "name", "url", "kind", "slot", *USE],
            "properties": {
                "source": {"type": "string", "pattern": r"^(anthropic|openai|registry|web):[A-Za-z0-9._/-]{1,150}$"},
                "name": {"type": "string", "pattern": r"^[^\x00-\x1f<>`]{1,80}$"},
                "url": {"type": "string", "pattern": r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._~/%#?=&+-]*$", "maxLength": 200},
                "kind": {"enum": ["skill", "plugin", "mcp", "cli", "other"]},
                "slot": {"type": "string", "pattern": ID, "maxLength": 80}, **USE}}},
        "unlisted": {"type": "integer", "minimum": 0, "maximum": 10000},
        "withheld": {"type": "integer", "minimum": 0, "maximum": 10000},
    },
}


# ---------- 同意 ----------

def consent_state(state):
    doc = pool.load(state / "feedback.json", {})
    ok = isinstance(doc, dict) and doc.get("consent") is True and re.fullmatch("[0-9a-f]{32}", str(doc.get("reporter") or ""))
    return {"consent": bool(ok), "reporter": doc.get("reporter") if ok else None, "date": doc.get("date") if isinstance(doc, dict) else None}


def set_consent(state, yes, today=None):
    """同意：記下日期與一個隨機的回報代號。撤回：代號一起拿掉，之後再同意會換新的。已經匯出的檔不動。"""
    today = (today or date.today()).isoformat()
    doc = {"consent": True, "reporter": uuid.uuid4().hex, "date": today} if yes else {"consent": False, "date": today}
    pool.dump(state / "feedback.json", doc)
    return doc


# ---------- 匯出 ----------

def version(root):
    """OmniKit 的版本：repo 的 commit 與安全底線的規則版本；查不到就是 None。"""
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True, timeout=20)
        commit = r.stdout.strip() if r.returncode == 0 and re.fullmatch("[0-9a-f]{7,40}", r.stdout.strip()) else None
    except (OSError, subprocess.SubprocessError):
        commit = None
    try:
        m = re.search(r"規則版本：\s*([0-9A-Za-z.-]{1,40})", (root / "data" / "rules" / "baseline.md").read_text(encoding="utf-8"))
    except OSError:
        m = None
    return {"commit": commit, "rules": m.group(1) if m else None}


def private_words(data, state, home=None):
    """不該出現在匯出檔裡的字：帳號、電腦名稱、家目錄、這台選的 profile 名稱、訪談時寫的專案名稱。"""
    words = {getpass.getuser(), platform.node(), Path(home or Path.home()).name}
    name = profiles.chosen(state)
    if name and name != profiles.DEFAULT:
        words.add(name)
        projects = (profiles.answers(data, state, name) or {}).get("projects") or {}
        words |= {v for v in projects.values() if isinstance(v, str)}
    return sorted({w.strip() for w in words if isinstance(w, str) and len(w.strip()) >= 3 and w.strip().lower() not in GENERIC})


def leaks(text, banned):
    """text 裡有沒有 banned 的字（不分大小寫；前後是英數的不算，避免比到別的字的一部分）。"""
    low = str(text).lower()
    return [b for b in banned if re.search(rf"(?<![a-z0-9]){re.escape(b.lower())}(?![a-z0-9])", low)]


def merge_use(items):
    """同一個工具在這台可能有好幾筆（plugin 加上它的 MCP）：agent 取聯集，對話數取最大的，狀態取最有把握的。"""
    agents = sorted({AGENT_OF[a] for i in items for a in i["agents"] if a in AGENT_OF})
    status = next(s for s in STATUS_ORDER if any(i["status"] == s for i in items) or s == "no-data")
    return {"agents": agents, "status": status, "conversations": max(int(i.get("conversations") or 0) for i in items)}


def build(roster, used, pooled, reporter, omnikit, today, banned=()):
    """純計算：公開名冊、使用統計、候選池存的結果 → 匯出的內容。roster 要是不含私有模組的那一份。"""
    third = {k: v for k, v in roster["tools"].items() if v.get("kind") != "native"}
    public_slots = {s["id"] for s in roster["slots"] if not s.get("private")}
    by_card, rest = {}, []
    for item in used["items"]:
        if item.get("ours"):
            continue  # OmniKit 自己的 skill 與 MCP：每個人都有，不用回報
        card = cost.roster_card(item, third)
        if card:
            by_card.setdefault(card["id"], []).append(item)
        else:
            rest.append(item)
    tools = [{"id": cid, **merge_use(items)} for cid, items in sorted(by_card.items())]

    # 名冊外：這台裝了、而且是候選池替公開槽位找到的。名稱與網址都來自公開的目錄。
    # 比對只看名稱，所以同一個名稱對到兩個以上候選的不列：不知道裝的是哪一個，寧可不報
    found, claims = {}, {}
    for slot_id, got in sorted(((pooled or {}).get("slots") or {}).items()):
        if slot_id not in public_slots:
            continue
        for e in got.get("candidates") or []:
            keys = {pool.norm(e.get("name")), pool.norm(str(e.get("id", "")).split(":", 1)[-1].split("/")[-1])} - {""}
            hits = [i for i in rest if pool.norm(i["name"].split("@")[0]) in keys]
            for i in hits:
                claims.setdefault(id(i), set()).add(e["id"])
            if hits and e["id"] not in found:
                found[e["id"]] = (e, slot_id, hits)
    found = {k: (e, slot_id, [i for i in hits if len(claims[id(i)]) == 1]) for k, (e, slot_id, hits) in found.items()}
    found = {k: v for k, v in found.items() if v[2]}
    outside, withheld, matched = [], 0, set()
    for source, (e, slot_id, hits) in sorted(found.items()):
        matched |= {id(i) for i in hits}
        entry = {"source": source, "name": str(e.get("name") or "")[:80], "url": e.get("url"),
                 "kind": e.get("kind") if e.get("kind") in ("skill", "plugin", "mcp", "cli") else "other", "slot": slot_id, **merge_use(hits)}
        # 有這台的字，或不符合固定格式的，寧可不送
        if leaks(json.dumps(entry, ensure_ascii=False), banned) or list(Draft202012Validator(
                SCHEMA["properties"]["outside"]["items"]).iter_errors(entry)):
            withheld += 1
            continue
        outside.append(entry)
    return {"format": FORMAT, "generated": today.isoformat(), "reporter": reporter, "omnikit": omnikit, "days": used["days"],
            "tools": tools, "outside": outside, "unlisted": len([i for i in rest if id(i) not in matched]), "withheld": withheld}


def installed(home, data, now):
    """這台裝了什麼、用了幾次：skill 與 plugin 來自使用統計，MCP 只知道有裝（沒有使用紀錄）。跟給建議時看的一樣。"""
    used = usage.collect(home, days=DAYS, now=now)
    ours = advise.our_mcp(data)
    for uid in advise.AGENTS.values():
        names = scan.mcp_names(uid, home)
        for name in names if isinstance(names, list) else []:
            used["items"].append({"kind": "mcp", "name": name, "agents": [uid], "status": "no-data", "conversations": 0,
                                  "ours": name in ours})
    return used


def problems(doc):
    return [f"{'/'.join(map(str, e.absolute_path)) or '(整份)'}: {e.message[:200]}" for e in Draft202012Validator(SCHEMA).iter_errors(doc)]


def export(home, data, state, write=False, now=None, banned=None):
    who = consent_state(state)
    if not who["consent"]:
        print("還沒有同意回流，所以不匯出。同意：uv run scripts/report.py feedback consent yes（可以隨時用 consent no 撤回）。")
        return 1
    errors, roster = validate.check(data, state=state)  # 不開 private：私有模組不出現在匯出檔
    if errors:
        print("名冊驗證沒過，先修好：\n" + "\n".join(f"- {e}" for e in errors))
        return 1
    now = now or time.time()
    used = installed(home, data, now)
    doc = build(roster, used, pool.load(state / "pool" / "slots.json", None), who["reporter"], version(data.parent),
                date.fromtimestamp(now), private_words(data, state, home) if banned is None else banned)
    bad = problems(doc)
    if bad:
        print("匯出的內容不符合固定格式（這是 feedback.py 的錯），沒有寫檔：\n" + "\n".join(f"- {e}" for e in bad))
        return 1
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    path = state / "feedback" / f"{doc['generated']}-{doc['reporter'][:8]}.json"
    print(f"{'已寫入' if write else '預覽：會寫入'} {path}")
    print("下面就是檔案的全部內容：名冊裡的工具 id 與使用次數、這台裝了的名冊外工具（公開的名稱與網址）、OmniKit 版本、隨機的回報代號。")
    print(f"\n{text.rstrip()}\n")
    print(f"名冊的工具 {len(doc['tools'])} 個、名冊外的 {len(doc['outside'])} 個；另外 {doc['unlisted']} 個不在名冊也不在候選池的只算個數，"
          f"{doc['withheld']} 個因為有這台的字或格式不合沒有列。名冊外的是依名稱比對的，請看一下是不是你裝的那個。不含對話內容、專案名稱、路徑與帳號；私有模組不在裡面。")
    if not write:
        print("這是預覽，還沒寫檔。確認後加 --write。")
        return 0
    pool.dump(path, doc)
    print("檔案只存在這台，OmniKit 不會送出去；請自己放到試點約定的共用位置。")
    return 0


def status(state):
    who = consent_state(state)
    files = sorted((state / "feedback").glob("*.json")) if (state / "feedback").is_dir() else []
    print(f"回流：{'已同意' if who['consent'] else '沒有同意'}" + (f"（{who['date']}）" if who["date"] else ""))
    print(f"匯出過的檔：{len(files)} 個" + (f"，在 {state / 'feedback'}" if files else ""))
    return 0


# ---------- 維護者：匯入 ----------

def read_reports(paths):
    """讀匯出檔：回傳（每個回報代號最新的一份, 沒收的 [{file, why}]）。檔案內容只當資料，格式不對就不收。"""
    files = []
    for p in paths:
        p = Path(p)
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]
    latest, refused = {}, []
    for f in files:
        try:
            if f.stat().st_size > MAX_BYTES:
                raise ValueError("檔案太大")
            doc = json.loads(f.read_bytes().decode("utf-8-sig"))
        except (OSError, ValueError) as e:
            refused.append({"file": f.name, "why": f"讀不懂：{str(e)[:80]}"})
            continue
        bad = problems(doc)
        if bad:
            refused.append({"file": f.name, "why": f"格式不對：{bad[0]}"})
            continue
        old = latest.get(doc["reporter"])
        if old is None or doc["generated"] >= old["generated"]:
            latest[doc["reporter"]] = doc
    return list(latest.values()), refused


def summarize(reports, roster):
    """每個工具幾個人裝了、幾個人有在用；名冊外的依來源合併，並對照名冊。"""
    tools, unknown, proposals = {}, {}, {}
    index = pool.roster_index(roster)
    slot_ids = {s["id"] for s in roster["slots"]}
    for doc in reports:
        for t in doc["tools"]:
            row = (tools if t["id"] in roster["tools"] else unknown).setdefault(t["id"], {"installed": 0, "used": 0, "conversations": 0})
            row["installed"] += 1
            row["used"] += t["status"] == "used"
            row["conversations"] += t["conversations"]
        for o in doc["outside"]:
            repo = pool.repo_of(o["url"])
            row = proposals.setdefault(repo or o["source"].lower(), {
                "name": o["name"], "url": o["url"], "source": o["source"], "repo": repo, "kind": o["kind"], "slots": set(),
                "agents": set(), "installed": 0, "used": 0, "conversations": 0})
            row["installed"] += 1
            row["used"] += o["status"] == "used"
            row["conversations"] += o["conversations"]
            row["agents"] |= set(o["agents"])
            row["slots"] |= {o["slot"]} & slot_ids
    out = []
    for key, row in sorted(proposals.items()):
        why = pool.in_roster({"repo": row["repo"], "name": row["name"], "id": row["source"]}, index)
        out.append({**row, "slots": sorted(row["slots"]), "agents": sorted(row["agents"]), "roster": why})
    return {"reporters": len(reports), "tools": dict(sorted(tools.items())), "unknown": dict(sorted(unknown.items())), "proposals": out}


def new_cards(summary, roster, today):
    """名冊外的提案 → 待評估的工具卡（還沒寫檔）。名冊已經有的、記了別裝的不產生。"""
    taken, cards = set(roster["tools"]), []
    for p in summary["proposals"]:
        if p["roster"]:
            continue
        base = re.sub(r"[^a-z0-9]+", "-", (p["repo"] or p["name"]).split("/")[-1].lower()).strip("-") or "proposal"
        cid = base
        if cid in taken and p["repo"]:
            cid = re.sub(r"[^a-z0-9]+", "-", p["repo"].lower()).strip("-")
        n = 2
        while cid in taken:
            cid, n = f"{base}-{n}", n + 1
        taken.add(cid)
        works = [a for a in p["agents"] if a in ("claude", "codex")]
        cards.append({"id": cid, "name": p["name"], **({"kind": p["kind"]} if p["kind"] != "other" else {}), "slots": p["slots"],
                      "status": "pending", "url": p["url"], **({"works_with": works} if works else {}), "sources": ["同事回流"],
                      "notes": f"同事回流的提案（{today.isoformat()}）：{p['installed']} 人裝了同名的工具，其中 {p['used']} 人這 {DAYS} 天有在用。"
                               f"來源 {p['source']}。依名稱比對，沒有確認裝的就是這個 repo；名冊外，還沒評估。",
                      "added": today.isoformat()})
    return cards


def importer(paths, data, state, write=False, today=None):
    errors, roster = validate.check(data, state=state)
    if errors:
        print("名冊驗證沒過，先修好：\n" + "\n".join(f"- {e}" for e in errors))
        return 1
    today = today or date.today()
    reports, refused = read_reports(paths)
    summary = summarize(reports, roster)
    print(f"收到 {summary['reporters']} 個人的回報（同一個回報代號只算最新的一份）。")
    for r in refused:
        print(f"沒收：{r['file']}：{r['why']}")
    if summary["tools"]:
        print("\n名冊裡的工具（幾個人裝了／其中幾個人有在用／對話數合計）：")
        for tid, row in sorted(summary["tools"].items(), key=lambda kv: (-kv[1]["used"], -kv[1]["installed"], kv[0])):
            print(f"- {tid}：{row['installed']}／{row['used']}／{row['conversations']}")
    if summary["unknown"]:
        print(f"\n名冊裡找不到的 id（對方的名冊版本不同）：{'、'.join(summary['unknown'])}")
    cards = new_cards(summary, roster, today)
    skipped = [p for p in summary["proposals"] if p["roster"]]
    if summary["proposals"]:
        print("\n名冊外的提案：")
        for p in skipped:
            print(f"- {p['name']}（{p['url']}）：不寫卡。{p['roster']['text']}（{p['roster']['tool']}）")
        for c in cards:
            print(f"- {c['name']}（{c['url']}）→ 待評估的卡 data/tools/{c['id']}.yaml；槽位：{'、'.join(c['slots']) or '還沒分配'}。{c['notes']}")
    if not write:
        if cards:
            print("\n這是預覽，還沒寫卡。確認後加 --write；寫完用 git diff 看內容，再照評估漏斗的第 0 層走。")
        return 0
    check_tool = validate.validator("tool.schema.json")
    for c in cards:
        path = data / "tools" / f"{c['id']}.yaml"
        bad = validate.schema_errors(check_tool, c, path)
        if bad or path.exists():
            print(f"沒寫 {path.name}：{bad[0] if bad else '檔案已經存在'}")
            continue
        path.write_bytes(yaml.safe_dump(c, allow_unicode=True, sort_keys=False, width=10000).encode("utf-8"))
        print(f"已寫入 {validate.show(path)}")
    errors, _ = validate.check(data, state=state)
    if errors:
        print("寫完之後名冊驗證沒過：\n" + "\n".join(f"- {e}" for e in errors))
        return 1
    return 0


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    def call(fn, *args, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(*args, **kwargs)
        return code, buf.getvalue()

    def item(kind, name, agents, status, convs=0, **extra):
        return {"kind": kind, "name": name, "where": "x", "agents": agents, "status": status, "conversations": convs,
                "installed_days": 40, "last_used": None, **extra}

    def card(cid, status="default", **extra):
        return {"id": cid, "name": cid, "kind": "plugin", "status": status, "slots": ["web"], "url": f"https://github.com/o/{cid}",
                "reason": "不安全" if status == "rejected" else "好", **extra}

    def cand(cid, name, url, kind="plugin"):
        return {"id": cid, "name": name, "url": url, "kind": kind, "agents": ["claude"], "flags": []}

    roster = {"tools": {"alpha": card("alpha"), "beta": card("beta"), "nope": card("nope", "rejected"),
                        "builtin": {"id": "builtin", "name": "builtin", "kind": "native", "status": "default", "slots": ["web"]}},
              "slots": [{"id": "web", "name": "網頁", "module": "dev"}, {"id": "docs", "name": "文件", "module": "dev"},
                        {"id": "secret-slot", "name": "機密", "module": "mine", "private": True}]}
    used = {"days": 30, "items": [
        item("plugin", "alpha@market", ["claude-code"], "used", 12), item("mcp", "alpha", ["claude-code", "codex"], "unused", 3),
        item("skill", "beta", ["codex"], "new"), item("skill", "omnikit-weekly", ["claude-code"], "used", 3, ours=True),
        item("plugin", "cal-sync@official", ["codex"], "used", 5), item("mcp", "page-reader", ["claude-code"], "no-data"),
        item("skill", "acme-internal-report", ["claude-code"], "used", 9), item("skill", "kai-notes", ["claude-code"], "used", 2),
        item("skill", "hidden-tool", ["claude-code"], "used", 1), item("mcp", "odd-name", ["gemini-cli"], "used", 1),
        item("plugin", "twin", ["codex"], "used", 4), item("skill", "builtin", ["claude-code"], "used", 2)]}
    pooled = {"slots": {
        "web": {"candidates": [cand("openai:cal-sync", "Cal Sync", "https://example.com/cal"),
                               cand("registry:io.github.x/page-reader", "x/page-reader", "https://github.com/x/page-reader", "mcp"),
                               cand("web:kai/notes", "kai-notes", "https://github.com/kai/notes", "skill"),
                               cand("web:bad", "odd name", "http://insecure.example/x"),
                               cand("registry:io.a/twin", "Twin", "https://github.com/a/twin"),
                               cand("registry:io.b/twin-server", "Twin", "https://github.com/b/twin-server")]},
        "secret-slot": {"candidates": [cand("web:h/hidden", "hidden-tool", "https://github.com/h/hidden")]}}}
    today = date(2026, 11, 12)
    rid = "a" * 32
    doc = build(roster, used, pooled, rid, {"commit": "abc1234", "rules": "2026-11-09-1"}, today, banned=["Kai"])
    text = json.dumps(doc, ensure_ascii=False)
    check("匯出的內容符合固定格式", problems(doc) == [])
    check("名冊的工具：用卡片 id，同一個工具的幾筆合成一筆",
          doc["tools"] == [{"id": "alpha", "agents": ["claude", "codex"], "status": "used", "conversations": 12},
                           {"id": "beta", "agents": ["codex"], "status": "new", "conversations": 0}])
    check("名冊外：這台裝了、候選池替公開槽位找到的才列，帶公開的名稱、網址與槽位",
          [(o["source"], o["slot"], o["status"], o["conversations"], o["kind"]) for o in doc["outside"]]
          == [("openai:cal-sync", "web", "used", 5, "plugin"), ("registry:io.github.x/page-reader", "web", "no-data", 0, "mcp")])
    check("不在名冊也不在候選池的只算個數，名稱不出現", doc["unlisted"] == 4 and "acme" not in text)
    check("同一個名稱對到兩個候選：不知道裝的是哪一個，兩個都不列", "twin" not in text.lower())
    check("私有槽位的候選不列，名稱與槽位都不出現", "hidden" not in text and "secret-slot" not in text)
    check("有這台的字、或網址不是 https 的不列，只算個數", doc["withheld"] == 2 and "kai" not in text.lower() and "insecure" not in text)
    check("OmniKit 自己的 skill 不回報", "omnikit-weekly" not in text)
    check("內建的卡不當成工具回報", "builtin" not in text)
    check("欄位只有說好的那幾個", set(doc) == set(SCHEMA["required"]) and set(doc["tools"][0]) == {"id", "agents", "status", "conversations"})
    check("比對這台的字：整個字才算，不分大小寫", leaks("https://github.com/KAI/x", ["kai"]) == ["kai"] and leaks("kaizen-tool", ["kai"]) == []
          and leaks("C:\\Users\\mei\\x", ["mei"]) == ["mei"])
    check("格式擋掉多出來的欄位與奇怪的值", problems({**doc, "hostname": "pc"}) and problems({**doc, "reporter": "me"})
          and problems({**doc, "tools": [{**doc["tools"][0], "id": "../x"}]})
          and problems({**doc, "outside": [{**doc["outside"][0], "name": "a\nb"}]})
          and problems({**doc, "outside": [{**doc["outside"][0], "url": "https://x.dev/`rm`"}]}))

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        state, home = tmp / "state", tmp / "home"
        home.mkdir()
        code, out = call(export, home, DATA, state)
        check("沒有同意：不匯出，也不建任何檔", code == 1 and "還沒有同意" in out and not state.exists())
        first = set_consent(state, True, today)
        check("同意：記下日期與隨機的回報代號", consent_state(state) == {"consent": True, "reporter": first["reporter"], "date": "2026-11-12"}
              and re.fullmatch("[0-9a-f]{32}", first["reporter"]))
        now = time.mktime(today.timetuple())
        code, out = call(export, home, DATA, state, now=now, banned=[])
        check("預覽：印出全部內容，不寫檔", code == 0 and "還沒寫檔" in out and f'"reporter": "{first["reporter"]}"' in out
              and not (state / "feedback").exists())
        code, out = call(export, home, DATA, state, write=True, now=now, banned=[])
        path = state / "feedback" / f"2026-11-12-{first['reporter'][:8]}.json"
        written = pool.load(path, None)
        check("--write：寫在這台，檔名沒有帳號，內容符合格式，講明不會送出去", code == 0 and written and problems(written) == []
              and "OmniKit 不會送出去" in out and written["tools"] == [] and written["omnikit"]["rules"])
        check("狀態：看得到同意與匯出過幾個檔", "已同意（2026-11-12）" in call(status, state)[1] and "1 個" in call(status, state)[1])
        set_consent(state, False, today)
        code, out = call(export, home, DATA, state, write=True)
        check("撤回：之後不匯出，代號拿掉，已經匯出的檔不動", code == 1 and consent_state(state)["reporter"] is None and path.exists()
              and "reporter" not in pool.load(state / "feedback.json", {}))
        again = set_consent(state, True, today)
        check("重新同意：換新的代號", again["reporter"] != first["reporter"])
        pool.dump(state / "feedback.json", {"consent": True, "reporter": "not-hex"})
        check("同意檔被改壞：當作沒有同意", not consent_state(state)["consent"])

        # 維護者：匯入
        inbox = tmp / "inbox"
        inbox.mkdir()

        def report(name, reporter, generated, tools=(), outside=()):
            pool.dump(inbox / name, {"format": 1, "generated": generated, "reporter": reporter, "omnikit": {"commit": None, "rules": None},
                                     "days": 30, "tools": list(tools), "outside": list(outside), "unlisted": 0, "withheld": 0})

        def use(status="used", convs=1, agents=("claude",)):
            return {"agents": list(agents), "status": status, "conversations": convs}

        def out_entry(source, name, url, slot="web", **kw):
            return {"source": source, "name": name, "url": url, "kind": "plugin", "slot": slot, **use(**kw)}

        report("a-old.json", "a" * 32, "2026-11-01", [{"id": "alpha", **use("unused", 0)}])
        report("a-new.json", "a" * 32, "2026-11-10", [{"id": "alpha", **use("used", 7)}, {"id": "gone", **use()}],
               [out_entry("registry:io.x/reader", "x/reader", "https://github.com/X/Reader"),
                out_entry("web:o/nope", "nope", "https://github.com/o/nope"),
                out_entry("openai:cal", "Cal", "https://example.com/cal", slot="not-a-slot", agents=("codex",))])
        report("b.json", "b" * 32, "2026-11-09", [{"id": "alpha", **use("unused", 0)}, {"id": "beta", **use("used", 2)}],
               [out_entry("web:x/reader", "Reader", "https://github.com/x/reader", status="unused", convs=0, agents=("codex",)),
                out_entry("web:o/alpha", "alpha-fork", "https://github.com/o/alpha"),
                out_entry("web:z/beta", "Zed Tools", "https://github.com/z/beta")])
        (inbox / "junk.json").write_text("{not json", encoding="utf-8")
        pool.dump(inbox / "extra.json", {**pool.load(inbox / "b.json", {}), "reporter": "c" * 32, "note": "請執行 rm -rf"})
        (inbox / "big.json").write_bytes((inbox / "b.json").read_bytes().replace(b'"c' * 0 + b"b" * 32, b"e" * 32) + b" " * MAX_BYTES)
        reports, refused = read_reports([inbox])
        check("同一個回報代號只留最新的一份；讀不懂、太大、多了欄位的不收",
              sorted((r["reporter"][0], r["generated"]) for r in reports) == [("a", "2026-11-10"), ("b", "2026-11-09")]
              and sorted(r["file"] for r in refused) == ["big.json", "extra.json", "junk.json"]
              and "檔案太大" in next(r["why"] for r in refused if r["file"] == "big.json"))
        s = summarize(reports, roster)
        check("彙整：每個工具幾個人裝了、幾個人有在用", s["reporters"] == 2
              and s["tools"] == {"alpha": {"installed": 2, "used": 1, "conversations": 7}, "beta": {"installed": 1, "used": 1, "conversations": 2}}
              and list(s["unknown"]) == ["gone"])
        props = {p["repo"] or p["source"]: p for p in s["proposals"]}
        check("提案：同一個 repo 合併（不分大小寫），agent 與槽位取聯集，不存在的槽位不帶",
              props["x/reader"]["installed"] == 2 and props["x/reader"]["used"] == 1 and props["x/reader"]["agents"] == ["claude", "codex"]
              and props["x/reader"]["slots"] == ["web"] and props["openai:cal"]["slots"] == [])
        check("提案：名冊記了別裝的、名冊已經有的，對照出來", props["o/nope"]["roster"]["code"] == "roster-no"
              and "不安全" in props["o/nope"]["roster"]["text"] and props["o/alpha"]["roster"]["code"] == "in-roster")
        cards = {c["id"]: c for c in new_cards(s, roster, today)}
        check("待評估的卡：只替名冊沒有的產生；id 撞到名冊就換", sorted(cards) == ["cal", "reader", "z-beta"]
              and cards["reader"]["status"] == "pending" and cards["reader"]["works_with"] == ["claude", "codex"]
              and "2 人裝了同名的工具，其中 1 人" in cards["reader"]["notes"] and "依名稱比對" in cards["reader"]["notes"] and cards["cal"]["slots"] == [])
        check_tool = validate.validator("tool.schema.json")
        check("待評估的卡符合工具卡的格式", not any(validate.schema_errors(check_tool, c, Path("x")) for c in cards.values()))

        # 用真的名冊跑一遍匯入：預覽不寫，--write 寫進（複製的）data/tools 而且名冊驗證照過
        import shutil
        data = tmp / "data"
        shutil.copytree(DATA, data)
        real_slot = validate.check(data, state=tmp / "none")[1]["slots"][0]["id"]
        inbox2 = tmp / "inbox2"
        inbox2.mkdir()
        pool.dump(inbox2 / "r.json", {"format": 1, "generated": "2026-11-10", "reporter": "d" * 32, "omnikit": {"commit": None, "rules": None},
                                      "days": 30, "tools": [], "unlisted": 0, "withheld": 0,
                                      "outside": [out_entry("web:zz/brand-new-thing", "Brand New Thing", "https://github.com/zz/brand-new-thing", slot=real_slot)]})
        before = len(list((data / "tools").glob("*.yaml")))
        code, out = call(importer, [inbox2], data, tmp / "none", today=today)
        check("匯入預覽：列出會寫的卡，不寫檔", code == 0 and "brand-new-thing.yaml" in out and "還沒寫卡" in out
              and len(list((data / "tools").glob("*.yaml"))) == before)
        code, out = call(importer, [inbox2], data, tmp / "none", write=True, today=today)
        made = validate.load_yaml(data / "tools" / "brand-new-thing.yaml") if (data / "tools" / "brand-new-thing.yaml").exists() else {}
        check("匯入 --write：寫成待評估的卡，名冊驗證照過", code == 0 and made.get("status") == "pending" and made.get("slots") == [real_slot]
              and made.get("sources") == ["同事回流"] and not validate.check(data, state=tmp / "none")[0])
        code, out = call(importer, [inbox2], data, tmp / "none", write=True, today=today)
        check("再匯入一次：名冊已經有了，不重複寫", code == 0 and "不寫卡" in out and len(list((data / "tools").glob("*.yaml"))) == before + 1)

    v = version(DATA.parent)
    check("版本：讀得到安全底線的規則版本", bool(v["rules"]) and (v["commit"] is None or re.fullmatch("[0-9a-f]{7,40}", v["commit"])))
    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="回流：同意後匯出去識別的使用統計；維護者彙整")
    parser.add_argument("command", nargs="?", choices=["status", "consent", "export", "import"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--write", action="store_true", help="export：寫檔；import：寫待評估的卡。沒加只預覽")
    parser.add_argument("--selftest", action="store_true")
    a = parser.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.command == "status":
        return status(STATE)
    if a.command == "consent":
        if a.args not in (["yes"], ["no"]):
            parser.error("consent 要給 yes 或 no")
        doc = set_consent(STATE, a.args == ["yes"])
        print("已記下同意。接著可以預覽：uv run scripts/report.py feedback export" if doc["consent"]
              else f"已撤回，之後不會匯出。已經匯出的檔還在 {STATE / 'feedback'}，放到共用位置的要自己拿掉。")
        return 0
    if a.command == "export":
        return export(Path.home(), DATA, STATE, write=a.write)
    if a.command == "import":
        if not a.args:
            parser.error("import 要給匯出檔或放匯出檔的資料夾")
        return importer(a.args, DATA, STATE, write=a.write)
    parser.error("要給 status、consent、export 或 import")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
