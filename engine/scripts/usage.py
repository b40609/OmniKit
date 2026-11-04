# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit 使用統計：這台電腦裝的 skill 與 plugin，最近有沒有被用到。給每週彙整找「裝了沒在用」的。

只讀本機的紀錄，不上傳；只輸出名稱、對話數與日期，不輸出對話內容。

算「用到」的，都是實際讀取或呼叫，不是每段對話開頭列出來的 skill 清單：
- Claude Code：~/.claude/projects 對話紀錄裡的 Skill 工具呼叫與 slash 指令；~/.claude.json 的 skillUsage
  （最後使用時間）。plugin 另外看 pluginUsage 的累計使用次數：用過一次就不算「沒用到」
- Codex：~/.codex/sessions 的 rollout 裡，執行指令讀了 skills/<名稱>/SKILL.md；路徑在
  ~/.codex/plugins/cache/<marketplace>/<plugin>/ 底下的，算那個 plugin 用到
- Antigravity：~/.gemini/antigravity*/conversations/*.db 裡 view_file 讀 SKILL.md、IsSkill 是 true 的步驟；
  時間用資料庫檔的修改時間

列出的項目：
- skills：~/.claude/skills、~/.agents/skills（Codex 與 Antigravity 共用）、~/.codex/skills、
  ~/.gemini/config/skills 裡的 skill；OmniKit 自己的（engine/skills）不列
- plugins：Claude Code 裝的 plugin（~/.claude/plugins/installed_plugins.json）；Codex 最近一次對話實際載入的
  plugin skill，依 plugin 分組（停用的 plugin 與 skill 不會出現，沒有 skill 的 plugin 不列）。
  Codex 的快取裡有很多沒安裝的 plugin、帳號同步的 plugin 也不記在 config.toml，所以用載入清單當準
裝不到 <天數> 天的先不判斷，免得剛裝的就被建議移除。

用法：
  uv run engine/scripts/usage.py [--days 30]           印出摘要
  uv run engine/scripts/usage.py [--days 30] --json    輸出 JSON（digest.py 用）
  uv run engine/scripts/usage.py --selftest
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAY = 86400
NAMES = {"claude-code": "Claude Code", "codex": "Codex", "antigravity": "Antigravity"}

# 位置（相對家目錄）與讀它的 agent
SKILL_DIRS = [
    (".claude/skills", ("claude-code",)),
    (".agents/skills", ("codex", "antigravity")),
    (".codex/skills", ("codex",)),
    (".gemini/config/skills", ("antigravity",)),
]
ANTIGRAVITY_HOMES = ("antigravity", "antigravity-cli", "antigravity-ide")

TOOL = re.compile(rb'"name":"Skill","input":\{"skill":"([^"]+)"')
SLASH = re.compile(rb"<command-name>/?([A-Za-z0-9_.:-]+)</command-name>")
STAMP = re.compile(rb'"timestamp":"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+)Z?"')
SKILL_PATH = re.compile(r"skills[\\/]+([A-Za-z0-9_.:-]+)[\\/]+SKILL\.md")
AG_READ = re.compile(rb'"AbsolutePath":"((?:[^"\\]|\\.)*?)SKILL\.md","IsSkill":true')
CODEX_CALLS = {"function_call", "custom_tool_call", "local_shell_call"}
# plugins/cache/<marketplace>/<plugin>/<版本>/skills/<skill>/SKILL.md
PLUGIN_SKILL = re.compile(r"plugins[\\/]+cache[\\/]+([^\\/\s'\"`]+)[\\/]+([^\\/\s'\"`]+)[\\/]+[^\\/\s'\"`]+"
                          r"[\\/]+skills[\\/]+[A-Za-z0-9_.:-]+[\\/]+SKILL\.md")
PLUGIN_DIR = re.compile(r"plugins[\\/]+cache[\\/]+([^\\/]+)[\\/]+([^\\/]+)[\\/]")
SKILL_ROOT = re.compile(r"(?m)^- `(r\d+)` = `([^`]+)`")
SKILL_ENTRY = re.compile(r"(?m)^- (\S+?): .*\(file: (r\d+)/([^)\r\n]+)\)\s*$")
FRONT_NAME = re.compile(r"(?m)^name:\s*['\"]?([^'\"\r\n]+?)['\"]?\s*$")


def parse_time(text):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def created(path):
    """建立時間：Windows 的 st_birthtime（舊版 Python 用 st_ctime）。連結看連結本身。"""
    st = os.lstat(path)
    return getattr(st, "st_birthtime", None) or st.st_ctime


def recent(paths, since):
    out = []
    for p in paths:
        try:
            if p.is_file() and p.stat().st_mtime >= since:
                out.append(p)
        except OSError:
            continue
    return out


def note(events, agent, name, session, when):
    use = events.setdefault(agent, {}).setdefault(name, {"sessions": set(), "last": 0.0})
    use["sessions"].add(session)
    use["last"] = max(use["last"], when)


def claude_events(home, since, events):
    root = home / ".claude" / "projects"
    files = recent(root.rglob("*.jsonl"), since) if root.is_dir() else []
    for p in files:
        try:
            f = p.open("rb")
        except OSError:
            continue
        with f:
            for line in f:
                if b'"Skill"' not in line and b"command-name" not in line:
                    continue
                names = [m.group(1) for m in TOOL.finditer(line)] + [m.group(1) for m in SLASH.finditer(line)]
                if not names:
                    continue
                m = STAMP.search(line)
                when = (parse_time(m.group(1).decode()) if m else None) or p.stat().st_mtime
                if when < since:
                    continue
                for name in names:
                    note(events, "claude-code", name.decode("utf-8", "replace"), str(p), when)
    try:
        doc = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    for name, v in (doc.get("skillUsage") or {}).items():
        when = (v.get("lastUsedAt") or 0) / 1000 if isinstance(v, dict) else 0
        if when >= since:
            note(events, "claude-code", name, "skillUsage", when)
    return len(files), {k: (v.get("usageCount") or 0) for k, v in (doc.get("pluginUsage") or {}).items()
                        if isinstance(v, dict)}


def codex_events(home, since, events):
    root = home / ".codex" / "sessions"
    files = recent(root.glob("*/*/*/rollout-*.jsonl"), since) if root.is_dir() else []
    for p in files:
        try:
            f = p.open("rb")
        except OSError:
            continue
        with f:
            for raw in f:
                if b"SKILL.md" not in raw:
                    continue
                try:
                    d = json.loads(raw)
                except ValueError:
                    continue
                payload = d.get("payload") or {}
                text = ""
                if d.get("type") == "event_msg" and payload.get("type") == "item_completed":
                    item = payload.get("item") or {}
                    if item.get("type") == "CommandExecution":
                        cmd = item.get("command")
                        text = " ".join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or "")
                elif d.get("type") == "response_item" and payload.get("type") in CODEX_CALLS:
                    text = str(payload.get("arguments") or payload.get("input") or payload.get("action") or "")
                if not text:
                    continue  # 對話開頭的 skill 清單、工具輸出等都不算
                when = parse_time(d.get("timestamp")) or p.stat().st_mtime
                if when < since:
                    continue
                for m in PLUGIN_SKILL.finditer(text):
                    note(events, "codex", f"{m.group(2)}@{m.group(1)}", str(p), when)
                # plugin 裡的 skill 只算 plugin 用到，免得同名的獨立 skill 被誤判成用到
                for name in set(SKILL_PATH.findall(PLUGIN_SKILL.sub("", text))):
                    note(events, "codex", name, str(p), when)
    return len(files)


def skills_block(path, max_lines=60):
    """rollout 開頭給模型的 skill 清單（<skills_instructions> 那段）；找不到回 None。"""
    try:
        f = path.open("rb")
    except OSError:
        return None
    with f:
        for i, raw in enumerate(f):
            if i >= max_lines:
                break
            if b"<skills_instructions>" not in raw:
                continue
            try:
                payload = json.loads(raw).get("payload") or {}
            except ValueError:
                continue
            for c in payload.get("content") or []:
                text = c.get("text", "") if isinstance(c, dict) else ""
                if "<skills_instructions>" in text:
                    return text[text.find("<skills_instructions>"):]
    return None


def codex_loaded_plugins(home):
    """Codex 最近一次對話實際載入的 plugin skill：{"<plugin>@<marketplace>": {skill 名稱}}。"""
    root = home / ".codex" / "sessions"
    if not root.is_dir():
        return {}
    for p in sorted(root.glob("*/*/*/rollout-*.jsonl"), reverse=True):  # 路徑含日期與時間，新的排前面
        block = skills_block(p)
        if block is None:
            continue
        roots = dict(SKILL_ROOT.findall(block))
        plugins = {}
        for name, r, rel in SKILL_ENTRY.findall(block):
            m = PLUGIN_DIR.search(f"{roots.get(r, '')}/{rel}")
            if m:
                plugins.setdefault(f"{m.group(2)}@{m.group(1)}", set()).add(name)
        return plugins
    return {}


def antigravity_events(home, since, events):
    dbs = recent([db for sub in ANTIGRAVITY_HOMES for db in (home / ".gemini" / sub / "conversations").glob("*.db")], since)
    for db in dbs:
        when = db.stat().st_mtime
        try:
            con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
            try:
                blobs = [row[0] for row in con.execute("select step_payload from steps") if row[0]]
            finally:
                con.close()
        except sqlite3.Error:
            continue
        for blob in blobs:
            for m in AG_READ.finditer(blob if isinstance(blob, bytes) else str(blob).encode()):
                try:
                    path = json.loads(b'"' + m.group(1) + b'SKILL.md"')
                except ValueError:
                    continue
                parts = [x for x in re.split(r"[\\/]+", path) if x]
                if len(parts) >= 2:
                    note(events, "antigravity", parts[-2], str(db), when)
    return len(dbs)


def front_name(folder):
    try:
        head = (folder / "SKILL.md").read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return None
    m = FRONT_NAME.search(head)
    return m.group(1).strip() if m else None


def inventory(home, ours, created_at):
    items = []
    for rel, agents in SKILL_DIRS:
        folder = home / rel
        if not folder.is_dir():
            continue
        for entry in sorted(folder.iterdir()):
            if entry.name.startswith(".") or entry.name in ours or not (entry / "SKILL.md").is_file():
                continue
            names = {entry.name} | ({n} if (n := front_name(entry)) else set())
            items.append({"kind": "skill", "name": entry.name, "where": f"~/{rel}", "agents": list(agents),
                          "match": sorted(names), "installed": created_at(entry)})
    try:
        plugins = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        plugins = {}
    for key, entries in (plugins.get("plugins") or {}).items():
        entries = entries if isinstance(entries, list) else [entries]
        times = [t for e in entries if isinstance(e, dict) and (t := parse_time(e.get("installedAt")))]
        items.append({"kind": "plugin", "name": key, "where": "~/.claude/plugins", "agents": ["claude-code"],
                      "match": [], "prefix": key.split("@")[0] + ":", "installed": min(times) if times else None})
    for key, skills in sorted(codex_loaded_plugins(home).items()):
        plugin, market = key.split("@", 1)
        try:
            when = created_at(home / ".codex" / "plugins" / "cache" / market / plugin)
        except OSError:
            when = None
        items.append({"kind": "plugin", "name": key, "where": "~/.codex/plugins", "agents": ["codex"],
                      "match": [key], "skills": len(skills), "installed": when})
    return items


def judge(item, events, plugin_counts, now, days):
    sessions, last = set(), 0.0
    for agent in item["agents"]:
        for name, use in (events.get(agent) or {}).items():
            if name in item["match"] or (item.get("prefix") and name.startswith(item["prefix"])):
                sessions |= use["sessions"]
                last = max(last, use["last"])
    age = int((now - item["installed"]) / DAY) if item.get("installed") else None
    if sessions:
        status = "used"
    elif item["kind"] == "plugin" and "claude-code" in item["agents"] and plugin_counts.get(item["name"], 0) > 0:
        status = "used"  # Claude Code 記的累計次數：用過就不建議移除（Codex 的同名 plugin 不適用）
    elif age is not None and age < days:
        status = "new"
    else:
        status = "unused"
    out = {k: item[k] for k in ("kind", "name", "where", "agents", "skills") if k in item}
    out.update(status=status, conversations=len(sessions), installed_days=age,
               last_used=datetime.fromtimestamp(last, timezone.utc).astimezone().date().isoformat() if last else None)
    return out


def collect(home, days=30, now=None, ours=None, created_at=created):
    now = now or time.time()
    since = now - days * DAY
    ours = ours if ours is not None else {p.name for p in (ROOT / "engine" / "skills").iterdir() if p.is_dir()}
    events = {}
    claude_files, plugin_counts = claude_events(home, since, events)
    sources = {"claude-code": claude_files, "codex": codex_events(home, since, events),
               "antigravity": antigravity_events(home, since, events)}
    items = [judge(i, events, plugin_counts, now, days) for i in inventory(home, ours, created_at)]
    return {
        "days": days,
        "since": datetime.fromtimestamp(since).date().isoformat(),
        "until": datetime.fromtimestamp(now).date().isoformat(),
        "sources": sources,
        "items": items,
    }


def agents_label(item):
    return "、".join(NAMES[a] for a in item["agents"])


def describe(item, used):
    """同名 skill 在別的位置有在用：同一個 agent 讀得到兩份，就是重複安裝；不然只註明哪個 agent 有在用。"""
    age = f"，裝了 {item['installed_days']} 天" if item["installed_days"] is not None else ""
    if item.get("skills"):
        age = f"，載入 {item['skills']} 個 skill{age}"
    same = [u for u in used if u["kind"] == "skill" and u["name"] == item["name"] and u["where"] != item["where"]]
    dup = sorted({u["where"] for u in same if set(u["agents"]) & set(item["agents"])})
    others = sorted({NAMES[a] for u in same for a in u["agents"]} - {NAMES[a] for a in item["agents"]})
    note = ""
    if dup:
        note = f"；{'、'.join(dup)} 的同名 skill 有在用，這份可能是重複的"
    elif others:
        note = f"；{'、'.join(others)} 有在用同名的 skill"
    return f"{item['name']}（{agents_label(item)}，{item['where']}{age}{note}）"


def report(result, limit=None):
    """Markdown 清單：使用紀錄來源、有用到的、沒用到的（可以考慮移除）、太新先不判斷的。"""
    days, items = result["days"], result["items"]
    used = sorted((i for i in items if i["status"] == "used"), key=lambda i: -i["conversations"])
    unused = [i for i in items if i["status"] == "unused"]
    new = [i for i in items if i["status"] == "new"]
    src = result["sources"]
    lines = [f"- 讀了 {result['since']} ～ {result['until']} 的紀錄：Claude Code {src['claude-code']} 段對話、"
             f"Codex {src['codex']} 段、Antigravity {src['antigravity']} 段"]
    top = "、".join(f"{i['name']}（{agents_label(i)}，{i['conversations']} 段）" for i in used[:5] if i["conversations"])
    lines.append(f"- 有用到：{len(used)} 個" + (f"，最常用的是 {top}" if top else ""))
    lines.append(f"- {days} 天沒用到：{len(unused)} 個" + ("，可以考慮移除：" if unused else ""))
    shown = unused if limit is None else unused[:limit]
    for kind, label in (("skill", "skills"), ("plugin", "plugins")):
        group = [i for i in shown if i["kind"] == kind]
        if group:
            lines.append(f"  - {label}：" + "、".join(describe(i, used) for i in group))
    if limit is not None and len(unused) > limit:
        lines.append(f"  - 還有 {len(unused) - limit} 個，完整清單：uv run engine/scripts/usage.py")
    if new:
        lines.append(f"- 裝不到 {days} 天，先不判斷：{len(new)} 個")
    return lines


def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc).timestamp()

    def iso(days_ago):
        return datetime.fromtimestamp(now - days_ago * DAY, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)

        def put(rel, text):
            p = home / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            return p

        def skill(rel, name, front=None):
            put(f"{rel}/{name}/SKILL.md", f"---\nname: {front or name}\ndescription: x\n---\n")

        for name in ("caveman", "graphify", "unused-one", "new-one", "oldie", "omnikit-eval"):
            skill(".claude/skills", name)
        skill(".claude/skills", "renamed", front="real-name")
        for name in ("agent-reach", "ria", "okx"):
            skill(".agents/skills", name)
        for name in ("hatch-pet", "itri-work-agent", "build"):
            skill(".codex/skills", name)
        for name in ("search-first", "lean-build", "agent-reach", "itri-work-agent"):
            skill(".gemini/config/skills", name)

        put(".claude/projects/p/a.jsonl", "\n".join([
            json.dumps({"timestamp": iso(2), "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "caveman"}}]}}, separators=(",", ":")),
            json.dumps({"timestamp": iso(3), "message": {"content": "<command-name>/ponytail:ponytail</command-name> 秘密內容"}}),
            json.dumps({"timestamp": iso(1), "message": {"content": "<command-name>/real-name</command-name>"}}),
            json.dumps({"timestamp": iso(40), "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "oldie"}}]}}, separators=(",", ":")),
        ]) + "\n")
        put(".claude.json", json.dumps({
            "skillUsage": {"graphify": {"usageCount": 2, "lastUsedAt": (now - DAY) * 1000}},
            "pluginUsage": {"ponytail@ponytail": {"usageCount": 0}, "floorplan@floorplan": {"usageCount": 0},
                            "claude-mem@thedotmack": {"usageCount": 4845}, "shared@x": {"usageCount": 5}}}))
        put(".claude/plugins/installed_plugins.json", json.dumps({"version": 2, "plugins": {
            "ponytail@ponytail": [{"scope": "user", "installedAt": iso(60)}],
            "floorplan@floorplan": [{"scope": "user", "installedAt": iso(60)}],
            "claude-mem@thedotmack": [{"scope": "user", "installedAt": iso(60)}],
            "shared@x": [{"scope": "user", "installedAt": iso(60)}],
            "fresh@x": [{"scope": "user", "installedAt": iso(2)}]}}))

        put(".codex/sessions/2026/11/04/rollout-1.jsonl", "\n".join(json.dumps(x) for x in [
            {"timestamp": iso(1), "type": "response_item", "payload": {"type": "message", "role": "developer", "content": [
                {"type": "input_text", "text": "<skills_instructions>\n- ria: (file: C:\\Users\\u\\.agents\\skills\\ria\\SKILL.md)\n"
                 "- `r9` = `C:/Users/u/.codex/plugins/cache/old/old-plugin/1.0/skills`\n"
                 "- old-plugin:x: 舊對話才有的 (file: r9/x/SKILL.md)"}]}},
            {"timestamp": iso(1), "type": "event_msg", "payload": {"type": "item_completed", "item": {
                "type": "CommandExecution", "command": ["pwsh.exe", "-Command",
                                                        "Get-Content C:\\Users\\u\\.agents\\skills\\agent-reach\\SKILL.md"]}}},
            {"timestamp": iso(2), "type": "response_item", "payload": {
                "type": "function_call", "arguments": '{"cmd": "cat ~/.codex/skills/itri-work-agent/SKILL.md"}'}},
            {"timestamp": iso(1), "type": "response_item", "payload": {
                "type": "custom_tool_call_output", "output": "skills/okx/SKILL.md"}},
        ]) + "\n")
        # 較新的一段：開頭的載入清單當 Codex plugin 的盤點；讀了 claude-mem 的 build
        cache = "C:/Users/u/.codex/plugins/cache"
        loaded = "\n".join([
            "<skills_instructions>", "## Skills", "### Skill roots",
            "- `r0` = `C:/Users/u/.codex/skills`",
            f"- `r1` = `{cache}/claude-mem-local/claude-mem/15.9.0/skills`",
            f"- `r2` = `{cache}/openai-bundled`",
            f"- `r3` = `{cache}/anthropic-agent-skills/document-skills/local/skills/docx`",
            f"- `r4` = `{cache}/ponytail/ponytail/5.3.3/skills`",
            f"- `r5` = `{cache}/x/shared/1.0/skills`",
            "### Available skills",
            "- hatch-pet: x (file: r0/hatch-pet/SKILL.md)",
            "- claude-mem:build: 說明裡有括號 (例如這樣) (file: r1/build/SKILL.md)",
            "- claude-mem:do: x (file: r1/do/SKILL.md)",
            "- computer-use:computer-use: x (file: r2/computer-use/26.1/skills/computer-use/SKILL.md)",
            "- document-skills:docx: x (file: r3/SKILL.md)",
            "- ponytail:ponytail: x (file: r4/ponytail/SKILL.md)",
            "- shared:s: x (file: r5/s/SKILL.md)",
        ])
        put(".codex/sessions/2026/11/04/rollout-2.jsonl", "\n".join(json.dumps(x) for x in [
            {"timestamp": iso(1), "type": "response_item", "payload": {"type": "message", "role": "developer", "content": [
                {"type": "input_text", "text": loaded}]}},
            {"timestamp": iso(1), "type": "event_msg", "payload": {"type": "item_completed", "item": {
                "type": "CommandExecution", "command": ["pwsh.exe", "-Command", "Get-Content -LiteralPath "
                    "'C:\\Users\\u\\.codex\\plugins\\cache\\claude-mem-local\\claude-mem\\15.9.0\\skills\\build\\SKILL.md'"]}}},
        ]) + "\n")

        db = home / ".gemini" / "antigravity-cli" / "conversations" / "c1.db"
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(db)
        con.execute("create table steps (idx integer, step_payload blob)")
        con.execute("insert into steps values (0, ?)", (b"Available skills:\n- lean-build (C:\\x\\skills\\lean-build\\SKILL.md): y",))
        con.execute("insert into steps values (1, ?)", (b'..view_file...{"AbsolutePath":"C:\\\\Users\\\\u\\\\.gemini\\\\config'
                                                        b'\\\\skills\\\\search-first\\\\SKILL.md","IsSkill":true}',))
        con.commit()
        con.close()

        ages = {"new-one": 5, "computer-use": 3}
        result = collect(home, days=30, now=now, ours={"omnikit-eval"},
                         created_at=lambda p: now - ages.get(p.name, 60) * DAY)
        by = {(i["name"], i["where"]): i for i in result["items"]}

        def status(name, where):
            return by[(name, where)]["status"]

        check("Claude：Skill 工具呼叫算用到", status("caveman", "~/.claude/skills") == "used")
        check("Claude：skillUsage 的最後使用時間算用到", status("graphify", "~/.claude/skills") == "used")
        check("Claude：用 SKILL.md 裡的 name 叫出來也算", status("renamed", "~/.claude/skills") == "used")
        check("Claude：超過天數的呼叫不算", status("oldie", "~/.claude/skills") == "unused")
        check("沒用到的 skill", status("unused-one", "~/.claude/skills") == "unused")
        check("裝不到 30 天：先不判斷", status("new-one", "~/.claude/skills") == "new")
        check("OmniKit 自己的 skill 不列", ("omnikit-eval", "~/.claude/skills") not in by)
        check("Codex：執行指令讀了 SKILL.md 算用到", status("agent-reach", "~/.agents/skills") == "used")
        check("Codex：對話開頭的 skill 清單與工具輸出不算",
              status("ria", "~/.agents/skills") == "unused" and status("okx", "~/.agents/skills") == "unused")
        check("Codex 自己的 skill 沒用到", status("hatch-pet", "~/.codex/skills") == "unused")
        check("Antigravity：view_file 讀 SKILL.md（IsSkill）算用到", status("search-first", "~/.gemini/config/skills") == "used")
        check("Antigravity：開頭的 skill 清單不算", status("lean-build", "~/.gemini/config/skills") == "unused")
        check("plugin：slash 指令用到", status("ponytail@ponytail", "~/.claude/plugins") == "used")
        check("plugin：累計用過就不列為沒用到", status("claude-mem@thedotmack", "~/.claude/plugins") == "used")
        check("plugin：裝了 60 天從沒用過", status("floorplan@floorplan", "~/.claude/plugins") == "unused")
        check("plugin：剛裝的先不判斷", status("fresh@x", "~/.claude/plugins") == "new")
        check("記錄對話數與最後使用日期", by[("caveman", "~/.claude/skills")]["conversations"] == 1
              and by[("caveman", "~/.claude/skills")]["last_used"] is not None)
        cx = "~/.codex/plugins"
        check("Codex plugin：讀了 plugin 裡的 SKILL.md 算那個 plugin 用到",
              status("claude-mem@claude-mem-local", cx) == "used" and by[("claude-mem@claude-mem-local", cx)]["skills"] == 2)
        check("Codex plugin：讀 plugin 裡的 skill，不算同名的獨立 skill 用到", status("build", "~/.codex/skills") == "unused")
        check("Codex plugin：版本資料夾在 skill 路徑裡、或 root 直接指到單一 skill，都歸得到 plugin",
              status("computer-use@openai-bundled", cx) == "new" and status("document-skills@anthropic-agent-skills", cx) == "unused")
        check("Codex plugin：Claude Code 同名 plugin 的累計次數不算 Codex 用到",
              status("shared@x", "~/.claude/plugins") == "used" and status("shared@x", cx) == "unused")
        check("Codex plugin：只看最新一段對話的載入清單",
              sorted(i["name"] for i in result["items"] if i["where"] == cx) == [
                  "claude-mem@claude-mem-local", "computer-use@openai-bundled",
                  "document-skills@anthropic-agent-skills", "ponytail@ponytail", "shared@x"])
        check("摘要：Codex plugin 標出載入幾個 skill",
              "document-skills@anthropic-agent-skills（Codex，~/.codex/plugins，載入 1 個 skill，裝了 60 天）" in "\n".join(report(result)))
        check("統計來源的對話數", result["sources"] == {"claude-code": 1, "codex": 2, "antigravity": 1})
        text = json.dumps(result, ensure_ascii=False) + "\n".join(report(result))
        check("不輸出對話內容", "秘密內容" not in text and "Get-Content" not in text)
        lines = report(result, limit=2)
        check("摘要：列出沒用到的，超過上限只顯示前幾個", any("可以考慮移除" in line for line in lines)
              and any("還有" in line for line in lines) and any("先不判斷" in line for line in lines))
        full = "\n".join(report(result))
        check("摘要：同名 skill 在別的位置有用到，標成可能重複",
              status("agent-reach", "~/.gemini/config/skills") == "unused"
              and "~/.agents/skills 的同名 skill 有在用，這份可能是重複的" in full)
        check("摘要：最常用的標出是哪個 agent", "caveman（Claude Code，1 段）" in full)
        check("摘要：別的 agent 讀不到的同名 skill，不算重複，只註明誰有在用",
              status("itri-work-agent", "~/.gemini/config/skills") == "unused"
              and "~/.gemini/config/skills，裝了 60 天；Codex 有在用同名的 skill" in full)

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="這台電腦的 skill 與 plugin 最近有沒有被用到")
    parser.add_argument("--days", type=int, default=30, help="看幾天內的紀錄，預設 30")
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    result = collect(Path.home(), days=args.days)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n".join(report(result)))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
