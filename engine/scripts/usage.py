# /// script
# requires-python = ">=3.11"
# dependencies = ["zstandard"]
# ///
"""OmniKit 使用統計：這台電腦裝的 skill 與 plugin，最近有沒有被用到。給每週彙整找「裝了沒在用」的。

只讀本機的紀錄，不上傳；只輸出名稱、對話數與日期，不輸出對話內容。

算「用到」的，都是實際讀取或呼叫，不是每段對話開頭列出來的 skill 清單：
- Claude Code：~/.claude/projects 對話紀錄裡，assistant 的 Skill 工具呼叫，與使用者下的 slash 指令（使用者訊息
  一開頭就是指令標記）。agent 讀到的檔案內容、指令輸出、子 agent 與背景對話的任務說明、API 請求的副本裡出現
  同樣的字樣，不算。另外看 ~/.claude.json 的 skillUsage（最後使用時間）；plugin 再看 pluginUsage 的累計使用
  次數：用過一次就不算「沒用到」
- 時間：Claude Code 與 Codex 的紀錄都是 UTC；沒寫時區的也當 UTC，不當本地時間
- Codex：~/.codex/sessions 與 archived_sessions 的 rollout（含壓縮的 .jsonl.zst）裡，執行指令讀了
  skills/<名稱>/SKILL.md；路徑在 ~/.codex/plugins/cache/<marketplace>/<plugin>/ 底下的，算那個 plugin 用到。
  壓縮的讀不了（沒有 zstd 解碼器）時，Codex 讀得到的工具標「查不到」，不判沒用到
- Antigravity：~/.gemini/antigravity*/conversations/*.db 裡 view_file 讀 SKILL.md、IsSkill 是 true 的步驟；
  時間用資料庫檔的修改時間

列出的項目：
- skills：~/.claude/skills（Claude Code）、~/.agents/skills 與 ~/.codex/skills（Codex）、~/.gemini/config/skills
  與 Antigravity 另外讀的三個位置裡的 skill（見 SKILL_DIRS）；OmniKit 自己的（engine/skills）不列。
  Antigravity 不讀 ~/.agents/skills（.agents/skills 只在專案資料夾裡有效）
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
import io
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

# 位置（相對家目錄）與讀它的 agent。Antigravity 的 App、IDE 與 CLI 共用 ~/.gemini/config/skills，IDE 另外讀舊的
# ~/.gemini/antigravity/skills，CLI 另外讀 ~/.gemini/antigravity-cli/skills 與 ~/.gemini/skills；
# 不讀 ~/.agents/skills（https://antigravity.google/docs/skills.md，2026-11-17）
SKILL_DIRS = [
    (".claude/skills", ("claude-code",)),
    (".agents/skills", ("codex",)),
    (".codex/skills", ("codex",)),
    (".gemini/config/skills", ("antigravity",)),
    (".gemini/antigravity/skills", ("antigravity",)),
    (".gemini/antigravity-cli/skills", ("antigravity",)),
    (".gemini/skills", ("antigravity",)),
]
ANTIGRAVITY_HOMES = ("antigravity", "antigravity-cli", "antigravity-ide")

# 使用者下的 slash 指令：訊息一開頭就是指令標記（前面可以有 <command-message>）
COMMAND = re.compile(r"\s*(?:<command-message>[^<]*</command-message>\s*)?<command-name>/?([A-Za-z0-9_.:-]+)</command-name>")
STAMP = re.compile(rb'"timestamp":"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+(?:Z|[+-][0-9]{2}:?[0-9]{2})?)"')
SKILL_PATH = re.compile(r"skills[\\/]+([A-Za-z0-9_.:-]+)[\\/]+SKILL\.md")
# Antigravity 步驟裡讀 SKILL.md 的紀錄；鍵的順序與空白不固定，兩種順序都認（體檢 ADV-05）
AG_READ = re.compile(rb'"AbsolutePath"\s*:\s*"((?:[^"\\]|\\.)*?)SKILL\.md"\s*,\s*"IsSkill"\s*:\s*true'
                     rb'|"IsSkill"\s*:\s*true\s*,\s*"AbsolutePath"\s*:\s*"((?:[^"\\]|\\.)*?)SKILL\.md"')
CODEX_CALLS = {"function_call", "custom_tool_call", "local_shell_call"}
# plugins/cache/<marketplace>/<plugin>/<版本>/skills/<skill>/SKILL.md
PLUGIN_SKILL = re.compile(r"plugins[\\/]+cache[\\/]+([^\\/\s'\"`]+)[\\/]+([^\\/\s'\"`]+)[\\/]+[^\\/\s'\"`]+"
                          r"[\\/]+skills[\\/]+[A-Za-z0-9_.:-]+[\\/]+SKILL\.md")
PLUGIN_DIR = re.compile(r"plugins[\\/]+cache[\\/]+([^\\/]+)[\\/]+([^\\/]+)[\\/]")
SKILL_ROOT = re.compile(r"(?m)^- `(r\d+)` = `([^`]+)`")
SKILL_ENTRY = re.compile(r"(?m)^- (\S+?): .*\(file: (r\d+)/([^)\r\n]+)\)\s*$")
FRONT_NAME = re.compile(r"(?m)^name:\s*['\"]?([^'\"\r\n]+?)['\"]?\s*$")


def parse_time(text):
    """ISO 時間換成 epoch 秒。沒寫時區的當 UTC（agent 的紀錄都是 UTC），不當本地時間。"""
    try:
        when = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).timestamp()


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


try:  # Codex 把結束的對話壓成 .jsonl.zst（2026-11-16 這台：30 天 209 段只有 8 段沒壓縮）
    from compression.zstd import open as _zstd_open  # Python 3.14 起內建
except ImportError:
    try:
        import zstandard as _zstandard

        def _zstd_open(path, mode="rb"):
            """zstandard 套件開的讀取串流不能逐行讀（CI 的 Python 3.12 上 io.UnsupportedOperation）：整份解開放進記憶體。"""
            if "w" in mode:
                return _zstandard.open(path, mode)
            with open(path, "rb") as fh:
                return io.BytesIO(_zstandard.ZstdDecompressor().stream_reader(fh).read())
    except ImportError:
        _zstd_open = None
ZSTD = _zstd_open is not None
# Codex 隨程式附帶的 plugin（config.toml 的 marketplace 來源在 Codex 自己的暫存或 runtime 資料夾）：
# 是 Codex 的內建功能，名冊對 Codex 的「用內建的就好」就是指它們，不列進拿掉
CODEX_BUILTIN_MARKETS = ("openai-bundled", "openai-primary-runtime")


def codex_files(home, since=None):
    """Codex 的對話紀錄：~/.codex/sessions（年/月/日）與 archived_sessions，含壓縮的 .jsonl.zst；
    檔名有開始時間，新的排前面。同一段對話兩邊都有時只留一份。"""
    seen, out = set(), []
    for sub in ("sessions", "archived_sessions"):
        root = Path(home) / ".codex" / sub
        if not root.is_dir():
            continue
        for p in root.rglob("rollout-*"):
            if not p.name.endswith((".jsonl", ".jsonl.zst")):
                continue
            key = p.name.removesuffix(".zst").removesuffix(".jsonl")
            if key not in seen:
                seen.add(key)
                out.append(p)
    if since is not None:
        out = recent(out, since)
    return sorted(out, key=lambda p: p.name, reverse=True)


def open_rollout(path):
    """開一份 Codex 對話紀錄（二進位、可以逐行讀）。壓縮的而這台沒有 zstd 解碼器：丟 OSError，呼叫端當成讀不到。"""
    if path.name.endswith(".zst"):
        if _zstd_open is None:
            raise OSError(f"沒有 zstd 解碼器，讀不了 {path.name}")
        return _zstd_open(path, "rb")
    return path.open("rb")


def note(events, agent, name, session, when):
    """記一次用到。session 是 None：只知道最後使用時間（Claude Code 的 skillUsage），算用到，但不算一段對話。"""
    use = events.setdefault(agent, {}).setdefault(name, {"sessions": set(), "last": 0.0})
    if session is not None:
        use["sessions"].add(session)
    use["last"] = max(use["last"], when)


def claude_calls(raw):
    """Claude Code 對話紀錄的一行 → (實際呼叫的 skill 與 slash 指令名稱, 這一行的紀錄)。cost.py 也用。

    只算兩種：assistant 訊息裡的 Skill 工具呼叫；使用者訊息一開頭就是 slash 指令的標記（使用者下的指令）。
    同樣的字樣出現在工具輸出、訊息中間、子 agent 的任務說明（isSidechain，主 agent 寫的）、skill 載入後補的
    說明（isMeta）或 API 請求的副本（type 不是 user、assistant）裡，都是讀到的文字，不算。
    """
    if b'"Skill"' not in raw and b"<command-name>" not in raw:
        return [], None
    try:
        d = json.loads(raw)
    except ValueError:
        return [], None
    if not isinstance(d, dict):
        return [], None
    message = d.get("message") if isinstance(d.get("message"), dict) else {}
    content = message.get("content")
    blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
    names = []
    if d.get("type") == "assistant":
        for b in blocks:
            if b.get("type") == "tool_use" and b.get("name") == "Skill" and isinstance(b.get("input"), dict):
                names.append(b["input"].get("skill"))
    elif d.get("type") == "user" and not d.get("isSidechain") and not d.get("isMeta"):
        texts = [content] if isinstance(content, str) else [b.get("text") for b in blocks if b.get("type") == "text"]
        for text in texts:
            m = COMMAND.match(text) if isinstance(text, str) else None
            if m:
                names.append(m.group(1))
    return [n.lstrip("/") for n in names if isinstance(n, str) and n.strip("/")], d


def json_or_none(raw):
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def plugin_mcp_calls(raw):
    """assistant 呼叫 plugin 帶的 MCP 工具（mcp__plugin_<plugin>_<server>__<工具>）→ ["<plugin>:mcp"]，
    讓 plugin 的前綴比對得到；只靠 MCP 的 plugin 以前一律算沒用到（體檢 ADV-04）。"""
    d = json_or_none(raw)
    if not d or d.get("type") != "assistant":
        return []
    content = (d.get("message") or {}).get("content") if isinstance(d.get("message"), dict) else None
    out = []
    for b in content if isinstance(content, list) else []:
        name = b.get("name") if isinstance(b, dict) and b.get("type") == "tool_use" else None
        if isinstance(name, str) and name.startswith("mcp__plugin_"):
            plugin = name[len("mcp__plugin_"):].split("_", 1)[0]
            if plugin:
                out.append(f"{plugin}:mcp")
    return out


def claude_session(path):
    """子代理的紀錄（<對話>/subagents/x.jsonl）歸到它的主對話，不另算一段。"""
    return path.parent.parent.with_suffix(".jsonl") if path.parent.name == "subagents" else path


def claude_events(home, since, events):
    """回傳 (互動對話數, plugin 累計次數)。entrypoint 是 sdk 開頭的（claude -p、背景程序，例如 claude-mem 的
    observer、實測腳本）不是使用者在用，呼叫不算、也不算對話數：2026-11-16 這台 896 段裡 536 段是 observer。"""
    root = home / ".claude" / "projects"
    files = recent(root.rglob("*.jsonl"), since) if root.is_dir() else []
    talks = set()
    for p in files:
        try:
            f = p.open("rb")
        except OSError:
            continue
        found, background, origin = [], False, None
        with f:
            for line in f:
                # 只看紀錄頂層的 entrypoint（第一筆有寫的）；工具輸出裡出現同樣字樣不算（體檢 ADV-17）
                if origin is None and b'"entrypoint"' in line:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        d = None
                    if isinstance(d, dict) and isinstance(d.get("entrypoint"), str):
                        origin = d["entrypoint"]
                        if origin.startswith("sdk"):
                            background = True
                            break
                names, record = claude_calls(line)
                if b"mcp__plugin_" in line:
                    names, record = names + plugin_mcp_calls(line), record or json_or_none(line)
                if not names or not isinstance(record, dict):
                    continue
                when = parse_time(record.get("timestamp")) or p.stat().st_mtime
                if when >= since:
                    found += [(name, when) for name in names]
        if background:
            continue
        talks.add(claude_session(p))
        for name, when in found:
            note(events, "claude-code", name, str(claude_session(p)), when)
    try:
        doc = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    for name, v in (doc.get("skillUsage") or {}).items():
        when = (v.get("lastUsedAt") or 0) / 1000 if isinstance(v, dict) else 0
        if when >= since:
            note(events, "claude-code", name, None, when)
    return len(talks), {k: (v.get("usageCount") or 0) for k, v in (doc.get("pluginUsage") or {}).items()
                        if isinstance(v, dict)}


def codex_events(home, since, events):
    """回傳 (讀到的對話數, 讀不到的對話數)。讀不到的不能當成「沒用到」。"""
    read, unreadable = 0, 0
    for p in codex_files(home, since):
        try:
            f = open_rollout(p)
        except OSError:
            unreadable += 1
            continue
        read += 1
        with f:
            try:
                lines = list(f)
            except Exception:  # 壓縮檔損毀或還在寫：這一段算讀不到
                read, unreadable = read - 1, unreadable + 1
                continue
            for raw in lines:
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
    return read, unreadable


def skills_block(path, max_lines=60):
    """rollout 開頭給模型的 skill 清單（<skills_instructions> 那段）；找不到回 None。"""
    try:
        f = open_rollout(path)
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
    for p in codex_files(home):  # 新的排前面
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
    """回傳 (讀到的對話數, 讀不到的對話數)。資料庫被鎖或格式不同時算讀不到，不當成沒用到。"""
    dbs = recent([db for sub in ANTIGRAVITY_HOMES for db in (home / ".gemini" / sub / "conversations").glob("*.db")], since)
    unreadable = 0
    for db in dbs:
        when = db.stat().st_mtime
        try:
            con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
            try:
                blobs = [row[0] for row in con.execute("select step_payload from steps") if row[0]]
            finally:
                con.close()
        except sqlite3.Error:
            unreadable += 1
            continue
        for blob in blobs:
            for m in AG_READ.finditer(blob if isinstance(blob, bytes) else str(blob).encode()):
                try:
                    path = json.loads(b'"' + (m.group(1) or m.group(2)) + b'SKILL.md"')
                except ValueError:
                    continue
                parts = [x for x in re.split(r"[\\/]+", path) if x]
                if len(parts) >= 2:
                    note(events, "antigravity", parts[-2], str(db), when)
    return len(dbs) - unreadable, unreadable


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
    try:  # 停用中的 plugin（體檢 ADV-01）：例如換的試用期間被停用的舊工具，不能叫人拿掉
        enabled = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8")).get("enabledPlugins") or {}
    except (OSError, ValueError, AttributeError):
        enabled = {}
    for key, entries in (plugins.get("plugins") or {}).items():
        entries = entries if isinstance(entries, list) else [entries]
        times = [t for e in entries if isinstance(e, dict) and (t := parse_time(e.get("installedAt")))]
        # plugin 裡附帶的 skill（例如 document-skills 帶了 skill-creator）：名冊對卡片時算已安裝
        bundled = sorted({s.name for e in entries if isinstance(e, dict) and e.get("installPath")
                          for s in (Path(e["installPath"]) / "skills").glob("*") if (s / "SKILL.md").is_file()})
        items.append({"kind": "plugin", "name": key, "where": "~/.claude/plugins", "agents": ["claude-code"],
                      "match": [], "prefix": key.split("@")[0] + ":", "installed": min(times) if times else None,
                      **({"bundled": bundled} if bundled else {}),
                      **({"enabled": False} if isinstance(enabled, dict) and enabled.get(key) is False else {})})
    for key, skills in sorted(codex_loaded_plugins(home).items()):
        plugin, market = key.split("@", 1)
        try:
            when = created_at(home / ".codex" / "plugins" / "cache" / market / plugin)
        except OSError:
            when = None
        items.append({"kind": "plugin", "name": key, "where": "~/.codex/plugins", "agents": ["codex"],
                      "match": [key], "skills": len(skills), "installed": when,
                      # 附帶的 skill（claude-mem:build → build）：名冊對卡片時算已安裝（體檢 ADV-14）
                      "bundled": sorted({s.split(":")[-1] for s in skills}),
                      **({"builtin": True} if market in CODEX_BUILTIN_MARKETS else {})})
    return items


def judge(item, events, plugin_counts, now, days, blind=()):
    """blind：紀錄讀不完整的 agent。沒看到用過、而且有一個讀它的 agent 紀錄不完整，就是「查不到」，不是沒用到。"""
    sessions, last, seen = set(), 0.0, False
    for agent in item["agents"]:
        for name, use in (events.get(agent) or {}).items():
            if name in item["match"] or (item.get("prefix") and name.startswith(item["prefix"])):
                seen = True
                sessions |= use["sessions"]
                last = max(last, use["last"])
    age = int((now - item["installed"]) / DAY) if item.get("installed") else None
    if seen:
        status = "used"
    elif item["kind"] == "plugin" and "claude-code" in item["agents"] and plugin_counts.get(item["name"], 0) > 0:
        status = "used"  # Claude Code 記的累計次數：用過就不建議移除（Codex 的同名 plugin 不適用）
    elif age is not None and age < days:
        status = "new"
    elif age is None or set(item["agents"]) & set(blind):
        status = "no-data"  # 安裝時間不明（體檢 ADV-02）或紀錄讀不完整：查不到，不是沒用到
    else:
        status = "unused"
    out = {k: item[k] for k in ("kind", "name", "where", "agents", "skills", "bundled", "builtin", "enabled") if k in item}
    out.update(status=status, conversations=len(sessions), installed_days=age,
               last_used=datetime.fromtimestamp(last, timezone.utc).astimezone().date().isoformat() if last else None)
    return out


def collect(home, days=30, now=None, ours=None, created_at=created):
    now = now or time.time()
    since = now - days * DAY
    ours = ours if ours is not None else {p.name for p in (ROOT / "engine" / "skills").iterdir() if p.is_dir()}
    events = {}
    claude_files, plugin_counts = claude_events(home, since, events)
    codex_read, codex_unreadable = codex_events(home, since, events)
    ag_read, ag_unreadable = antigravity_events(home, since, events)
    sources = {"claude-code": claude_files, "codex": codex_read, "antigravity": ag_read}
    unreadable = {k: v for k, v in (("codex", codex_unreadable), ("antigravity", ag_unreadable)) if v}
    items = [judge(i, events, plugin_counts, now, days, blind=unreadable) for i in inventory(home, ours, created_at)]
    return {
        "days": days,
        "since": datetime.fromtimestamp(since).date().isoformat(),
        "until": datetime.fromtimestamp(now).date().isoformat(),
        "sources": sources,
        **({"unreadable": unreadable} if unreadable else {}),
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
    note = "；停用中" if item.get("enabled") is False else ""
    if dup:
        note = f"；{'、'.join(dup)} 的同名 skill 有在用，這份可能是重複的"
    elif others:
        note = f"；{'、'.join(others)} 有在用同名的 skill"
    return f"{item['name']}（{agents_label(item)}，{item['where']}{age}{note}）"


def report(result, limit=None):
    """Markdown 清單：使用紀錄來源、有用到的、沒用到的（可以考慮移除）、太新先不判斷的。"""
    days, items = result["days"], result["items"]
    used = sorted((i for i in items if i["status"] == "used"), key=lambda i: -i["conversations"])
    unused = [i for i in items if i["status"] == "unused" and not i.get("builtin")]  # Codex 隨附的不叫人移除
    new = [i for i in items if i["status"] == "new"]
    src = result["sources"]
    lines = [f"- 讀了 {result['since']} ～ {result['until']} 的紀錄：Claude Code {src['claude-code']} 段對話、"
             f"Codex {src['codex']} 段、Antigravity {src['antigravity']} 段"]
    if (result.get("unreadable") or {}).get("codex"):
        lines.append(f"- Codex 另有 {result['unreadable']['codex']} 段壓縮的紀錄讀不到（這台沒有 zstd 解碼器），"
                     "Codex 讀得到的工具這次不判斷有沒有用到")
    if (result.get("unreadable") or {}).get("antigravity"):
        lines.append(f"- Antigravity 另有 {result['unreadable']['antigravity']} 段對話的資料庫打不開（可能正在用），"
                     "Antigravity 讀得到的工具這次不判斷有沒有用到")
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
    global _zstd_open  # 有一項要模擬「沒有 zstd 解碼器」
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
        for name in ("search-first", "lean-build", "agent-reach", "itri-work-agent", "ag-reordered"):
            skill(".gemini/config/skills", name)
        skill(".gemini/antigravity-cli/skills", "cli-only")

        for name in ("read-only", "edge-one"):
            skill(".claude/skills", name)

        def line(record):
            return json.dumps(record, ensure_ascii=False, separators=(",", ":"))

        def skill_call(name, days_ago, kind="assistant"):
            return line({"type": kind, "timestamp": iso(days_ago), "message": {"content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}})

        marker = "<command-name>/read-only</command-name>"
        put(".claude/projects/p/a.jsonl", "\n".join([
            skill_call("caveman", 2),
            line({"type": "user", "timestamp": iso(3), "message": {"content": "<command-message>ponytail:ponytail</command-message>\n"
                  "<command-name>/ponytail:ponytail</command-name>\n<command-args>秘密內容</command-args>"}}),
            line({"type": "user", "timestamp": iso(1), "message": {"content": [
                {"type": "text", "text": "<command-name>/real-name</command-name>"}]}}),
            skill_call("oldie", 40),
            skill_call("edge-one", 29.9),  # 離 30 天的邊界 2.4 小時：UTC 被當成本地時間的話，在 UTC+8 會掉到範圍外
            # 以下都是 agent 讀到的文字，不是使用者下的指令，也不是 Skill 工具呼叫
            line({"type": "user", "timestamp": iso(1), "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": f"讀到的檔案內容 {marker}"}]},
                "toolUseResult": {"file": {"content": marker}}}),
            line({"type": "user", "timestamp": iso(1), "message": {"content": [
                {"type": "text", "text": f"Condense the tool payload below. {marker}"}]}}),
            line({"type": "user", "timestamp": iso(1), "isSidechain": True, "message": {"content": marker}}),
            line({"type": "user", "timestamp": iso(1), "isMeta": True, "message": {"content": marker}}),
            line({"type": "assistant", "timestamp": iso(1), "message": {"content": [{"type": "text", "text": f"說明用法：{marker}"}]}}),
            line({"type": "api-request-blob", "message": {"content": [{"type": "text", "text": marker}]}}),
            line({"type": "user", "timestamp": iso(1), "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "content": "x"}]},
                  "toolUseResult": {"name": "Skill", "input": {"skill": "read-only"}}}),
            skill_call("read-only", 1, kind="api-request-blob"),
        ]) + "\n")
        # 背景程序與 claude -p（entrypoint sdk-*）呼叫的不算；子代理的呼叫算，但歸到主對話
        for name in ("bg-only", "sub-used"):
            skill(".claude/skills", name)
        put(".claude/projects/obs/o1.jsonl", line({"type": "user", "entrypoint": "sdk-ts", "timestamp": iso(1),
                                                   "message": {"content": "x"}}) + "\n" + skill_call("bg-only", 1) + "\n")
        put(".claude/projects/p/a/subagents/agent-1.jsonl", line({"type": "user", "entrypoint": "claude-desktop",
                                                                  "isSidechain": True, "timestamp": iso(1), "message": {"content": "x"}})
            + "\n" + skill_call("sub-used", 1) + "\n")
        # 只靠 MCP 的 plugin：呼叫 mcp__plugin_<plugin>_<server>__<工具> 算那個 plugin 用到
        put(".claude/projects/p/mcp.jsonl", line({"type": "assistant", "entrypoint": "claude-desktop", "timestamp": iso(2),
                                                  "message": {"content": [{"type": "tool_use", "name": "mcp__plugin_mcp-only_srv__search",
                                                                           "input": {}}]}}) + "\n")
        put(".claude/settings.json", json.dumps({"enabledPlugins": {"parked@x": False, "mcp-only@x": True}}))
        put(".claude.json", json.dumps({
            "skillUsage": {"graphify": {"usageCount": 2, "lastUsedAt": (now - DAY) * 1000},
                           "caveman": {"usageCount": 3, "lastUsedAt": (now - DAY) * 1000}},
            "pluginUsage": {"ponytail@ponytail": {"usageCount": 0}, "floorplan@floorplan": {"usageCount": 0},
                            "claude-mem@thedotmack": {"usageCount": 4845}, "shared@x": {"usageCount": 5}}}))
        put(".claude/plugins/installed_plugins.json", json.dumps({"version": 2, "plugins": {
            "ponytail@ponytail": [{"scope": "user", "installedAt": iso(60)}],
            "floorplan@floorplan": [{"scope": "user", "installedAt": iso(60)}],
            "claude-mem@thedotmack": [{"scope": "user", "installedAt": iso(60)}],
            "shared@x": [{"scope": "user", "installedAt": iso(60)}],
            "fresh@x": [{"scope": "user", "installedAt": iso(2), "installPath": str(home / "pc" / "fresh")}],
            "parked@x": [{"scope": "user", "installedAt": iso(60)}],
            "mcp-only@x": [{"scope": "user", "installedAt": iso(60)}],
            "no-date@x": [{"scope": "user"}]}}))
        put("pc/fresh/skills/skill-creator/SKILL.md", "---\nname: skill-creator\n---\n")
        put("pc/fresh/skills/not-a-skill/README.md", "x")

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
        # 結束的對話：Codex 壓成 .jsonl.zst，有的在 archived_sessions；讀了 zipped-one
        for name in ("zipped-one", "zip-unused"):
            skill(".codex/skills", name)
        zipped = home / ".codex" / "archived_sessions" / "rollout-2026-11-01T09-00-00-z.jsonl.zst"
        zipped.parent.mkdir(parents=True, exist_ok=True)
        if ZSTD:
            with _zstd_open(zipped, "wb") as zf:
                zf.write((json.dumps({"timestamp": iso(3), "type": "response_item", "payload": {
                    "type": "function_call", "arguments": '{"cmd": "cat ~/.codex/skills/zipped-one/SKILL.md"}'}}) + "\n").encode())

        db = home / ".gemini" / "antigravity-cli" / "conversations" / "c1.db"
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(db)
        con.execute("create table steps (idx integer, step_payload blob)")
        con.execute("insert into steps values (0, ?)", (b"Available skills:\n- lean-build (C:\\x\\skills\\lean-build\\SKILL.md): y",))
        con.execute("insert into steps values (1, ?)", (b'..view_file...{"AbsolutePath":"C:\\\\Users\\\\u\\\\.gemini\\\\config'
                                                        b'\\\\skills\\\\search-first\\\\SKILL.md","IsSkill":true}',))
        con.execute("insert into steps values (2, ?)", (b'{"IsSkill": true, "AbsolutePath": "C:\\\\Users\\\\u\\\\.gemini\\\\config'
                                                        b'\\\\skills\\\\ag-reordered\\\\SKILL.md"}',))
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
        check("Claude：讀到的文字不算用到（工具輸出、任務說明、回答、API 請求副本裡的 slash 指令標記與 Skill 字樣）",
              status("read-only", "~/.claude/skills") == "unused")
        check("時間：紀錄的 UTC 照 UTC 算，沒寫時區的也當 UTC，不當本地時間",
              STAMP.search(b'{"timestamp":"2026-11-04T12:00:00.000Z"}').group(1) == b"2026-11-04T12:00:00.000Z"
              and parse_time("2026-11-04T12:00:00.000Z") == now and parse_time("2026-11-04T12:00:00") == now
              and parse_time("2026-11-04T20:00:00+08:00") == now)
        check("時間：離 30 天邊界幾小時內的呼叫照樣算", status("edge-one", "~/.claude/skills") == "used")
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
        check("plugin：列出附帶的 skill（有 SKILL.md 的才算），沒帶的不加這欄",
              by[("fresh@x", "~/.claude/plugins")].get("bundled") == ["skill-creator"]
              and "bundled" not in by[("floorplan@floorplan", "~/.claude/plugins")])
        check("記錄對話數與最後使用日期", by[("caveman", "~/.claude/skills")]["conversations"] == 1
              and by[("caveman", "~/.claude/skills")]["last_used"] is not None)
        check("對話數只算對話紀錄裡的呼叫：skillUsage 只有最後使用時間，算用到、更新日期，不多算一段對話",
              by[("graphify", "~/.claude/skills")]["conversations"] == 0 and by[("graphify", "~/.claude/skills")]["last_used"] is not None
              and by[("caveman", "~/.claude/skills")]["last_used"] == by[("graphify", "~/.claude/skills")]["last_used"]
              and by[("ponytail@ponytail", "~/.claude/plugins")]["conversations"] == 1)
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
        check("plugin：只靠 MCP 的，呼叫 mcp__plugin_<plugin>_ 的工具算用到（體檢 ADV-04）",
              status("mcp-only@x", "~/.claude/plugins") == "used")
        check("plugin：停用中的標出來；安裝時間不明的是查不到，不是沒用到（體檢 ADV-01、ADV-02）",
              by[("parked@x", "~/.claude/plugins")].get("enabled") is False and "enabled" not in by[("mcp-only@x", "~/.claude/plugins")]
              and status("no-date@x", "~/.claude/plugins") == "no-data")
        check("Antigravity：鍵的順序對調、有空白也認得（體檢 ADV-05）", status("ag-reordered", "~/.gemini/config/skills") == "used")
        check("Codex plugin：附帶的 skill 列出來（去掉 plugin 前綴）",
              by[("claude-mem@claude-mem-local", cx)].get("bundled") == ["build", "do"])
        check("Claude：背景程序與 claude -p（entrypoint sdk-*）的呼叫不算；子代理的算、對話數歸到主對話",
              status("bg-only", "~/.claude/skills") == "unused" and status("sub-used", "~/.claude/skills") == "used"
              and by[("sub-used", "~/.claude/skills")]["conversations"] == 1)
        check("統計來源的對話數（Claude 不算背景與子代理；Codex 含 archived_sessions 裡壓縮的）",
              result["sources"] == {"claude-code": 2, "codex": 3 if ZSTD else 2, "antigravity": 1})
        check("Codex：壓縮的 .jsonl.zst、archived_sessions 裡的也讀（2026-11-16 這台 209 段只讀到 8 段）",
              ZSTD and status("zipped-one", "~/.codex/skills") == "used" and status("zip-unused", "~/.codex/skills") == "unused")
        check("Codex 隨附的 plugin（openai-bundled）標成內建", by[("computer-use@openai-bundled", cx)].get("builtin") is True
              and "builtin" not in by[("claude-mem@claude-mem-local", cx)])
        saved, _zstd_open = _zstd_open, None
        try:
            blind = collect(home, days=30, now=now, ours={"omnikit-eval"}, created_at=lambda p: now - ages.get(p.name, 60) * DAY)
        finally:
            _zstd_open = saved
        bb = {(i["name"], i["where"]): i for i in blind["items"]}
        check("Codex：壓縮的讀不了時，Codex 讀得到的工具是「查不到」，不是沒用到；Claude Code 的照常判斷",
              blind["unreadable"] == {"codex": 1} and bb[("zip-unused", "~/.codex/skills")]["status"] == "no-data"
              and bb[("okx", "~/.agents/skills")]["status"] == "no-data"
              and bb[("unused-one", "~/.claude/skills")]["status"] == "unused"
              and "1 段壓縮的紀錄讀不到" in "\n".join(report(blind)))
        text = json.dumps(result, ensure_ascii=False) + "\n".join(report(result))
        check("不輸出對話內容", "秘密內容" not in text and "Get-Content" not in text)
        lines = report(result, limit=2)
        check("摘要：列出沒用到的，超過上限只顯示前幾個", any("可以考慮移除" in line for line in lines)
              and any("還有" in line for line in lines) and any("先不判斷" in line for line in lines))
        full = "\n".join(report(result))
        check("Antigravity 不讀 ~/.agents/skills：Codex 在那裡用到的，不算 Antigravity 那份的重複，只註明誰有在用",
              by[("agent-reach", "~/.agents/skills")]["agents"] == ["codex"]
              and status("agent-reach", "~/.gemini/config/skills") == "unused"
              and "~/.gemini/config/skills，裝了 60 天；Codex 有在用同名的 skill" in full
              and "可能是重複的" not in full)
        check("Antigravity CLI 另外讀的 ~/.gemini/antigravity-cli/skills 也列",
              by[("cli-only", "~/.gemini/antigravity-cli/skills")]["agents"] == ["antigravity"])
        dup_item = {"kind": "skill", "name": "x", "where": "~/.codex/skills", "agents": ["codex"], "installed_days": 60}
        dup_used = {"kind": "skill", "name": "x", "where": "~/.agents/skills", "agents": ["codex"]}
        check("摘要：同一個 agent 讀得到的另一份同名 skill 有在用，標成可能重複",
              "~/.agents/skills 的同名 skill 有在用，這份可能是重複的" in describe(dup_item, [dup_used]))
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
