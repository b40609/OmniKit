# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""成本監測（FR-40 到 FR-44）：給個人週報（weekly.py）用。只讀本機的紀錄與設定，不連網、不花 token。

不相信工具自己報的數字，以 agent 實際載入與記錄的內容為準：
- Claude Code：對話紀錄在第一個回應之前，會用 attachment 記下實際給模型的 skill 清單（skill_listing）、
  SessionStart hook 加進 context 的內容（hook_additional_context；hook_system_message 是顯示給使用者看的，
  不算）、MCP 的說明（mcp_instructions_delta）與延後載入的工具名稱（deferred_tools_delta）。
  hook_additional_context 是所有 SessionStart hook 合併的：只有一個 hook（hook_success 的指令）就歸給它，
  有好幾個就標成「多個 hook 合併」。
  `claude plugin details` 的 Always-on 只在 plugin 還沒在對話裡載入過時當估計：它不算 MCP 的工具定義，
  也把 hook 當成沒有 context 成本。
- Codex：最近一次 rollout 開頭的 skill 清單（usage.skills_block）。MCP 讀不到，不列。
字數換成 token 是估計：英數約 4 個字元 1 token，其他字元 1 個算 1 token。

- A（FR-40）新裝的工具：有安裝時間的看安裝時間，沒有的（MCP）跟上一次存的清單比。
- B（FR-41）成本乘上使用量：開頭成本達門檻、14 天內與最近 10 段對話都沒用到的，列為「成本高又沒在用」；
  裝好之後還不到 10 段對話的先不判斷。
- C（FR-42）背景用量：entrypoint 是 sdk 開頭的 Claude Code 對話、source 是 exec 的 Codex rollout，依工作資料夾
  分組；同一個回應拆成多行的用 message.id 去重。
- D（FR-43）對話開頭的大小：使用者自己的對話第一回合的 prompt 大小，每週記中位數；比上週多 10% 以上，
  列出開頭成本變多的工具。
- E（FR-44）名冊比對：裝著、但名冊上不是 default 或 trial 的。

狀態存在 %LOCALAPPDATA%\\omnikit\\weekly\\：inventory.json（上次看到的清單）、startup.json（每週的開頭大小）。

用法：
  uv run engine/scripts/cost.py [--json]      印出這台的成本監測（不寫任何檔案）
  uv run engine/scripts/cost.py --selftest
"""
import argparse
import json
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import usage  # noqa: E402

DAY = 86400
THRESHOLD = 1000   # FR-41：每段對話的開頭成本達這個 token 數算「成本高」
IDLE_DAYS = 14     # FR-41（同 FR-13）：14 天
IDLE_CONVS = 10    # FR-41（同 FR-13）：最近 10 段對話
GROWTH = 0.10      # FR-43：比上週多 10% 以上才提示原因
SCAN_DAYS = 30     # 讀多久以內的紀錄：最近 10 段對話可能比 14 天更早
NAMES = usage.NAMES
DETAILS = re.compile(r"Always-on:\s*~?([\d,]+)\s*tok")
MCP_CALL = re.compile(rb'"name":"mcp__(.+?)__')
PLUGIN_MCP = re.compile(r"^plugin_([^_]+)_(.+)$")
PLUGIN_CACHE = re.compile(r"plugins[\\/]+cache[\\/]+[^\\/]+[\\/]+([^\\/]+)[\\/]")


def estimate(text):
    """字數換成 token 的估計：英數約 4 個字元 1 token，其他字元（中日韓等）1 個算 1 token。"""
    ascii_n = sum(1 for ch in text if ord(ch) < 128)
    return int(round(ascii_n / 4 + (len(text) - ascii_n)))


def skill_tool(name):
    """skill 清單裡的名稱歸到哪個工具：plugin 的 skill 是 <plugin>:<skill>。"""
    return f"plugin:{name.split(':', 1)[0]}" if ":" in name else f"skill:{name}"


def mcp_tool(server):
    """MCP server 歸到哪個工具：plugin 帶的 server 叫 plugin_<plugin>_<server>。"""
    m = PLUGIN_MCP.match(server)
    return f"plugin:{m.group(1)}" if m else f"mcp:{server}"


def hook_tool(command, plugins):
    """SessionStart hook 歸到哪個工具：指令裡有 plugin 快取路徑就是那個 plugin；第一個字是已裝 plugin 的名稱也算；
    其他用第一個字（去掉路徑與副檔名）。"""
    text = str(command or "").strip()
    m = PLUGIN_CACHE.search(text)
    if m:
        return f"plugin:{m.group(1)}"
    first = re.split(r"[\\/]", text.split()[0].strip("\"'"))[-1] if text else "?"
    first = re.sub(r"\.(exe|cmd|bat|ps1|py|js|mjs|cjs|sh)$", "", first, flags=re.I)
    return f"plugin:{first}" if first in plugins else f"hook:{first}"


def label(tool):
    kind, name = tool.split(":", 1)
    return {"plugin": f"{name}（plugin）", "skill": name, "mcp": f"{name}（MCP）", "hook": f"{name}（hook）"}.get(kind, tool)


def place(cwd, home):
    """工作資料夾分組：家目錄底下取前兩層（~/.claude-mem/observer-sessions），其他取磁碟與前兩層。"""
    if not cwd:
        return "（不明）"
    p = Path(cwd)
    try:
        parts = p.relative_to(home).parts[:2]
        return "~/" + "/".join(parts) if parts else "~"
    except ValueError:
        return "/".join(p.parts[:3])


def loads(raw):
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


# ---------- Claude Code ----------

@dataclass
class Session:
    path: Path
    top: bool = True                      # 專案資料夾底下的對話；子 agent 的紀錄是 False
    entrypoint: str | None = None
    cwd: str | None = None
    start: float | None = None
    first_turn: int | None = None         # 第一個回應的 input + cache_creation + cache_read
    parts: dict = field(default_factory=dict)  # 第一回合的開頭成本 {工具: tokens}
    calls: int = 0                        # 以下是 since 之後的用量
    uncached: int = 0
    cache_read: int = 0
    output: int = 0
    used: set = field(default_factory=set)

    @property
    def background(self):
        return bool(self.entrypoint) and str(self.entrypoint).startswith("sdk")


def first_turn_parts(attachments, plugins):
    """第一個回應之前的 attachment → {工具: tokens}。"""
    texts, hooks, injected = {}, {}, []

    def add(tool, text):
        texts[tool] = texts.get(tool, "") + text

    for a in attachments:
        kind = a.get("type")
        if kind == "skill_listing" and "listing" not in texts:
            texts["listing"] = ""  # 只算第一份（之後的是增減）
            names = sorted((n for n in a.get("names") or [] if isinstance(n, str)), key=len, reverse=True)
            current = None
            for line in str(a.get("content") or "").splitlines():
                if line.startswith("- "):
                    current = next((n for n in names if line == f"- {n}" or line.startswith(f"- {n}:")), None)
                if current is not None:
                    add(skill_tool(current), line + "\n")
        elif kind == "hook_success" and a.get("hookEvent") == "SessionStart":
            hooks[a.get("toolUseID")] = hook_tool(a.get("command"), plugins)
        elif kind == "hook_additional_context" and a.get("hookEvent") == "SessionStart":
            injected.append((a.get("toolUseID"), str(a.get("content") or "")))
        elif kind == "mcp_instructions_delta":
            for name, block in zip(a.get("addedNames") or [], a.get("addedBlocks") or []):
                add(mcp_tool(str(name)), str(block))
        elif kind == "deferred_tools_delta":
            for name in a.get("addedNames") or []:
                parts = str(name).split("__")
                if len(parts) >= 3 and parts[0] == "mcp":
                    add(mcp_tool(parts[1]), str(name) + "\n")
    owners = set(hooks.values())
    for use_id, text in injected:
        owner = hooks.get(use_id) or (owners.pop() if len(owners) == 1 else None) or "hook:SessionStart（多個 hook 合併）"
        owners = set(hooks.values())
        add(owner, text)
    texts.pop("listing", None)
    return {tool: estimate(text) for tool, text in texts.items() if text}


def read_claude(path, plugins, since, top=True):
    s = Session(path=path, top=top)
    ids, attachments, answered = set(), [], False
    try:
        f = path.open("rb")
    except OSError:
        return None
    with f:
        for raw in f:
            if s.entrypoint is None and b'"entrypoint"' in raw and (d := loads(raw)):
                s.entrypoint, s.cwd = d.get("entrypoint"), s.cwd or d.get("cwd")
            if s.start is None and (m := usage.STAMP.search(raw)):
                s.start = usage.parse_time(m.group(1).decode())
            if not answered and b'"type":"attachment"' in raw and (d := loads(raw)) and d.get("type") == "attachment":
                if isinstance(d.get("attachment"), dict):
                    attachments.append(d["attachment"])
            if b'"type":"assistant"' in raw and (d := loads(raw)) and d.get("type") == "assistant":
                answered = True
                msg = d.get("message") if isinstance(d.get("message"), dict) else {}
                u = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
                key = msg.get("id") or d.get("requestId") or d.get("uuid")
                if u and key not in ids:
                    ids.add(key)
                    fresh, made, cached = (int(u.get(k) or 0) for k in
                                           ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                    if s.first_turn is None:
                        s.first_turn = fresh + made + cached
                    when = usage.parse_time(d.get("timestamp")) or 0
                    if when >= since:
                        s.calls += 1
                        s.uncached += fresh + made
                        s.cache_read += cached
                        s.output += int(u.get("output_tokens") or 0)
                for m in MCP_CALL.finditer(raw):
                    s.used.add(mcp_tool(m.group(1).decode("utf-8", "replace")))
            if b'"Skill"' in raw or b"command-name" in raw:
                for m in [*usage.TOOL.finditer(raw), *usage.SLASH.finditer(raw)]:
                    s.used.add(skill_tool(m.group(1).decode("utf-8", "replace")))
    s.parts = first_turn_parts(attachments, plugins)
    return s


def claude_sessions(home, plugins, now):
    """30 天內有更新的對話紀錄；子 agent 的紀錄（<專案>/<session>/subagents/*.jsonl）用到的工具算進主對話。"""
    root = home / ".claude" / "projects"
    if not root.is_dir():
        return []
    files = usage.recent(root.rglob("*.jsonl"), now - SCAN_DAYS * DAY)
    sessions = {}
    for p in files:
        top = p.parent.parent == root
        s = read_claude(p, plugins, now - 7 * DAY, top)
        if s:
            sessions[p] = s
    for p, s in list(sessions.items()):
        if not s.top:
            rel = p.relative_to(root).parts
            parent = sessions.get(root / rel[0] / f"{rel[1]}.jsonl") if len(rel) >= 3 else None
            if parent:
                parent.used |= s.used
    return list(sessions.values())


def claude_plugins(home):
    """{plugin 名稱: {"id", "installed", "enabled"}}；settings.json 沒寫的算啟用。"""
    try:
        doc = json.loads((home / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    try:
        enabled = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8")).get("enabledPlugins") or {}
    except (OSError, ValueError, AttributeError):
        enabled = {}
    out = {}
    for pid, entries in (doc.get("plugins") or {}).items():
        entries = entries if isinstance(entries, list) else [entries]
        times = [t for e in entries if isinstance(e, dict) and (t := usage.parse_time(e.get("installedAt")))]
        out[pid.split("@")[0]] = {"id": pid, "installed": min(times) if times else None, "enabled": enabled.get(pid) is not False}
    return out


def details(plugin_id, run=subprocess.run):
    """`claude plugin details` 的 Always-on 估計（不算 MCP 的工具定義與 hook 注入）；查不到回 None。"""
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        r = run([exe, "plugin", "details", plugin_id], capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = DETAILS.search(r.stdout or "")
    return int(m.group(1).replace(",", "")) if r.returncode == 0 and m else None


# ---------- Codex ----------

@dataclass
class Rollout:
    path: Path
    source: str | None = None
    cwd: str | None = None
    start: float | None = None
    first_turn: int | None = None
    calls: int = 0
    totals: dict | None = None

    @property
    def background(self):
        return self.source == "exec"


def read_codex(path):
    r = Rollout(path=path)
    try:
        f = path.open("rb")
    except OSError:
        return None
    with f:
        for raw in f:
            if r.start is None and b'"session_meta"' in raw and (d := loads(raw)):
                meta = d.get("payload") if isinstance(d.get("payload"), dict) else {}
                r.source, r.cwd = meta.get("source"), meta.get("cwd")
                r.start = usage.parse_time(meta.get("timestamp") or d.get("timestamp"))
            if b'"token_count"' in raw and (d := loads(raw)):
                info = (d.get("payload") or {}).get("info") if isinstance(d.get("payload"), dict) else None
                if not isinstance(info, dict):
                    continue
                r.calls += 1
                if r.first_turn is None:
                    r.first_turn = int((info.get("last_token_usage") or {}).get("input_tokens") or 0) or None
                r.totals = info.get("total_token_usage") or r.totals
    return r


def codex_rollouts(home, now):
    root = home / ".codex" / "sessions"
    files = usage.recent(root.glob("*/*/*/rollout-*.jsonl"), now - SCAN_DAYS * DAY) if root.is_dir() else []
    return [r for p in files if (r := read_codex(p))]


def codex_parts(rollouts):
    """最近一段互動 rollout 開頭的 skill 清單 → {工具: tokens}；plugin 的 skill 依路徑歸到 plugin。"""
    for r in sorted((r for r in rollouts if not r.background), key=lambda r: r.start or 0, reverse=True):
        block = usage.skills_block(r.path)
        if block is None:
            continue
        roots, texts = dict(usage.SKILL_ROOT.findall(block)), {}
        for m in usage.SKILL_ENTRY.finditer(block):
            name, root_id, rel = m.groups()
            plugin = usage.PLUGIN_DIR.search(f"{roots.get(root_id, '')}/{rel}")
            tool = f"plugin:{plugin.group(2)}@{plugin.group(1)}" if plugin else f"skill:{name}"
            texts[tool] = texts.get(tool, "") + m.group(0) + "\n"
        return {tool: estimate(text) for tool, text in texts.items()}
    return {}


# ---------- 清單（A、E） ----------

def inventory(home, plugins, created_at=usage.created):
    """三個 agent 裝的 skill、plugin、MCP：[{key, kind, name, where, agents, installed}]。不分是不是 OmniKit 裝的。"""
    items = []
    for i in usage.inventory(home, set(), created_at):
        items.append({"kind": i["kind"], "name": i["name"], "where": i["where"], "agents": i["agents"],
                      "installed": i.get("installed")})
    sources = [("~/.claude.json", ["claude-code"], lambda: json.loads((home / ".claude.json").read_text(encoding="utf-8")).get("mcpServers")),
               ("~/.codex/config.toml", ["codex"], lambda: tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8")).get("mcp_servers")),
               ("~/.gemini/config/mcp_config.json", ["antigravity"],
                lambda: json.loads((home / ".gemini" / "config" / "mcp_config.json").read_bytes().decode("utf-8-sig")).get("mcpServers"))]
    for where, agents, read in sources:
        try:
            servers = read() or {}
        except (OSError, ValueError, tomllib.TOMLDecodeError, AttributeError):
            servers = {}
        for name in sorted(servers if isinstance(servers, dict) else {}):
            items.append({"kind": "mcp", "name": name, "where": where, "agents": agents, "installed": None})
    for item in items:
        item["key"] = f"{item['kind']}:{item['name']}@{item['where']}"
        if item["kind"] == "plugin" and "claude-code" in item["agents"]:
            item["enabled"] = plugins.get(item["name"].split("@")[0], {}).get("enabled", True)
    return items


def tool_keys(item):
    """清單裡的一項，在各 agent 的開頭成本裡叫什麼：{agent: 工具}。"""
    name, kind = item["name"], item["kind"]
    out = {}
    for agent in item["agents"]:
        if kind == "plugin":
            out[agent] = f"plugin:{name.split('@')[0]}" if agent == "claude-code" else f"plugin:{name}"
        elif kind == "mcp":
            out[agent] = f"mcp:{name}"
        else:
            out[agent] = f"skill:{name}"
    return out


def norm(text):
    return re.sub(r"-mcp$", "", re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-"))


def roster_card(item, tools):
    """名冊上對應的工具卡：卡片 id、plugin 名稱或卡片名稱，跟工具名稱或 marketplace 名稱相符。"""
    names = {norm(n) for n in item["name"].split("@")} - {""}
    for card in tools.values():
        keys = {norm(card.get("id", "")), norm(card.get("name", "")), norm((card.get("plugin") or {}).get("name", ""))} - {""}
        if names & keys:
            return card
    return None


# ---------- 彙整 ----------

def median_line(values):
    if not values:
        return None
    return {"median": int(statistics.median(values)), "min": min(values), "max": max(values), "n": len(values)}


def week_of(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def read_state(path):
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def measure(home, state, now=None, roster=None, plugin_details=details, persist=False, created_at=usage.created, ours=None):
    """量這台的成本監測，回傳 dict（給 report 印）。persist：把清單與這週的開頭大小存起來（週報存檔時才存）。"""
    now = now or time.time()
    week_ago, idle_since = now - 7 * DAY, now - IDLE_DAYS * DAY
    plugins = claude_plugins(home)
    sessions = claude_sessions(home, set(plugins), now)
    rollouts = codex_rollouts(home, now)
    talks = sorted((s for s in sessions if s.top and not s.background and s.start), key=lambda s: s.start, reverse=True)
    latest = next((s for s in talks if s.parts), None)
    costs = {"claude-code": latest.parts if latest else {}, "codex": codex_parts(rollouts)}
    codex_talks = sorted((r for r in rollouts if not r.background and r.start), key=lambda r: r.start, reverse=True)
    codex_used = {}
    usage.codex_events(home, now - SCAN_DAYS * DAY, codex_used)
    try:
        skill_usage = json.loads((home / ".claude.json").read_text(encoding="utf-8")).get("skillUsage") or {}
    except (OSError, ValueError, AttributeError):
        skill_usage = {}

    # A：新裝的工具（有安装時間的看時間；沒有的跟上次存的清單比）
    items = inventory(home, plugins, created_at)
    inv_path = state / "weekly" / "inventory.json"
    before = read_state(inv_path)
    seen = (before or {}).get("items") or {}
    today = date.fromtimestamp(now).isoformat()
    first_seen = {i["key"]: seen.get(i["key"]) or (today if before else None) for i in items}

    def cost_of(item):
        """(tokens, 說明)：先用實際載入的；Claude 的 plugin 還沒載入過就用 claude plugin details 的估計。"""
        for agent, tool in tool_keys(item).items():
            if tool in costs.get(agent, {}):
                return costs[agent][tool], f"{NAMES[agent]} 實際載入"
        if item["kind"] == "plugin" and "claude-code" in item["agents"]:
            est = plugin_details(item["name"]) if plugin_details else None
            if est is not None:
                return est, "Claude Code 的估計，不含 MCP 的工具定義與 hook 注入"
        return None, "還沒在對話裡載入過，量不到"

    # OmniKit 自己的 skill（engine/skills）是 OmniKit 本身，不算新裝的工具；它們每次同步都會重新連結，建立時間會變
    ours = {p.name for p in (usage.ROOT / "engine" / "skills").iterdir() if p.is_dir()} if ours is None else ours
    new = []
    for item in items:
        if item["kind"] == "skill" and item["name"] in ours:
            continue
        when = item.get("installed")
        recent = (when and when >= week_ago) or (not when and first_seen[item["key"]] and first_seen[item["key"]] >= date.fromtimestamp(week_ago).isoformat()
                                                  and item["key"] not in seen and before)
        if recent:
            tokens, how = cost_of(item)
            new.append({**{k: item[k] for k in ("kind", "name", "where", "agents")}, "tokens": tokens, "how": how,
                        "installed": date.fromtimestamp(when).isoformat() if when else first_seen[item["key"]]})

    # B：成本乘上使用量
    installed_at = {}
    for item in items:
        for agent, tool in tool_keys(item).items():
            if item.get("installed"):
                installed_at[(agent, tool)] = min(item["installed"], installed_at.get((agent, tool), item["installed"]))
    rows = []
    for agent, convs, uses in (("claude-code", talks, lambda c, t: t in c.used),
                               ("codex", codex_talks, lambda r, t: any(str(r.path) in v["sessions"] for n, v in codex_used.get("codex", {}).items()
                                                                        if (t == f"skill:{n}" or t == f"plugin:{n}")))):
        week_convs = sum(1 for c in convs if c.start >= week_ago)
        for tool, tokens in costs[agent].items():
            used_14d = sum(1 for c in convs if c.start >= idle_since and uses(c, tool))
            if agent == "claude-code" and tool.startswith("skill:"):
                last = (skill_usage.get(tool[6:]) or {}).get("lastUsedAt") if isinstance(skill_usage.get(tool[6:]), dict) else None
                used_14d += 1 if last and last / 1000 >= idle_since and used_14d == 0 else 0
            used_10 = sum(1 for c in convs[:IDLE_CONVS] if uses(c, tool))
            since_install = installed_at.get((agent, tool))
            enough = since_install is None or sum(1 for c in convs if c.start >= since_install) >= IDLE_CONVS
            why = None if enough else f"裝好之後還不到 {IDLE_CONVS} 段對話"
            if tool.startswith("hook:"):
                enough, why = False, "hook 每段對話都會跑，沒有「用到」的紀錄可以判斷"
            rows.append({"agent": agent, "tool": tool, "tokens": tokens, "used_14d": used_14d, "used_last10": used_10,
                         "week": tokens * week_convs, "convs_week": week_convs, "judged": enough, "why": why,
                         "idle": enough and used_14d == 0 and used_10 == 0 and len(convs) > 0})
    rows.sort(key=lambda r: -r["tokens"])

    # C：背景用量
    groups, own = {}, {"sessions": set(), "calls": 0, "uncached": 0, "cache_read": 0, "output": 0}
    for s in sessions:
        if not s.calls:
            continue
        target = groups.setdefault((f"Claude Code（{s.entrypoint}）", place(s.cwd, home)),
                                   {"sessions": set(), "calls": 0, "uncached": 0, "cache_read": 0, "output": 0}) if s.background else own
        target["sessions"].add(s.path if s.top else s.path.parent.parent.with_suffix(".jsonl"))
        for k in ("calls", "uncached", "cache_read", "output"):
            target[k] += getattr(s, k)
    for r in rollouts:
        if not r.background or not r.totals or r.path.stat().st_mtime < week_ago:
            continue
        g = groups.setdefault(("Codex（exec）", place(r.cwd, home)), {"sessions": set(), "calls": 0, "uncached": 0, "cache_read": 0, "output": 0})
        cached = int(r.totals.get("cached_input_tokens") or 0)
        g["sessions"].add(r.path)
        g["calls"] += r.calls
        g["uncached"] += int(r.totals.get("input_tokens") or 0) - cached
        g["cache_read"] += cached
        g["output"] += int(r.totals.get("output_tokens") or 0)
    background = sorted(({"who": who, "where": where, **{k: (len(v) if k == "sessions" else v) for k, v in g.items()}}
                         for (who, where), g in groups.items()), key=lambda g: -(g["uncached"] + g["output"]))
    own = {k: (len(v) if k == "sessions" else v) for k, v in own.items()}

    # D：對話開頭的大小
    week = week_of(date.fromtimestamp(now))
    current = {"claude-code": median_line([s.first_turn for s in talks if s.start >= week_ago and s.first_turn]),
               "codex": median_line([r.first_turn for r in codex_talks if r.start >= week_ago and r.first_turn])}
    hist_path = state / "weekly" / "startup.json"
    history = (read_state(hist_path) or {}).get("weeks") or {}
    earlier = sorted(w for w in history if w < week)
    prev = history[earlier[-1]] if earlier else None
    growth = {}
    for agent in ("claude-code", "codex"):
        cur, old = current[agent], (prev or {}).get(agent)
        if not (cur and old and old.get("median")):
            continue
        change = (cur["median"] - old["median"]) / old["median"]
        reasons = []
        if change >= GROWTH:
            old_parts = old.get("parts") or {}
            deltas = [(tool, tokens - old_parts.get(tool, 0), tool not in old_parts) for tool, tokens in costs[agent].items()]
            reasons = [{"tool": t, "delta": d, "new": n} for t, d, n in sorted(deltas, key=lambda x: -x[1]) if d > 0][:5]
        growth[agent] = {"from_week": earlier[-1], "from": old["median"], "change": change, "reasons": reasons}

    # E：名冊比對
    off_roster, unknown = [], 0
    if roster is not None:
        for item in items:
            card = roster_card(item, roster)
            if card is None:
                unknown += 1
            elif card.get("status") not in ("default", "trial"):
                tokens, how = cost_of(item)
                if item.get("enabled") is False:
                    how = ("設定是停用的，但最近一段對話還有載入（可能是停用之前開的對話）" if "實際載入" in how
                           else f"停用中；啟用後 {how}")
                off_roster.append({"name": item["name"], "where": item["where"], "status": card.get("status"),
                                   "card": card.get("id"), "reason": card.get("reason"), "tokens": tokens, "how": how})

    if persist:
        inv_path.parent.mkdir(parents=True, exist_ok=True)
        inv_path.write_text(json.dumps({"date": today, "items": first_seen}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        history[week] = {a: {**v, "parts": costs[a]} for a, v in current.items() if v}
        hist_path.write_text(json.dumps({"weeks": history}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"new": new, "rows": rows, "background": background, "own": own, "startup": current, "growth": growth,
            "off_roster": off_roster, "unknown_roster": unknown, "roster_checked": roster is not None,
            "latest": latest is not None, "codex_measured": bool(costs["codex"]), "baseline": before is None,
            "measured_on": date.fromtimestamp(latest.start).isoformat() if latest else None}


def n(value):
    return f"{value:,}" if isinstance(value, int) else "未知"


def report(result):
    """個人週報第 6 區塊（Markdown 的每一行）。"""
    lines = []
    if result.get("measured_on"):
        lines += [f"Claude Code 的開頭成本取自 {result['measured_on']} 開始的對話（第一回合實際載入的內容）；"
                  "token 是用字數換算的估計。", ""]
    lines += ["### 新裝的工具（7 天內）", ""]
    if result["new"]:
        for i in result["new"]:
            cost = f"每段對話約 {n(i['tokens'])} tokens" if i["tokens"] is not None else "開頭成本未知"
            lines.append(f"- {i['name']}（{i['kind']}，{'、'.join(NAMES[a] for a in i['agents'])}，{i['installed']}）：{cost}（{i['how']}）")
    else:
        lines.append("- 沒有")
    if result["baseline"]:
        lines.append("- 第一次記錄清單：沒有安裝時間的（MCP）從下次開始比對")

    lines += ["", f"### 成本高又沒在用的（每段對話 {THRESHOLD:,} tokens 以上，{IDLE_DAYS} 天內與最近 {IDLE_CONVS} 段對話都沒用到）", ""]
    idle = [r for r in result["rows"] if r["idle"] and r["tokens"] >= THRESHOLD]
    for r in idle:
        lines.append(f"- {label(r['tool'])}（{NAMES[r['agent']]}）：每段對話約 {n(r['tokens'])} tokens，"
                     f"這 7 天 {r['convs_week']} 段對話共約 {n(r['week'])} tokens；不用等 30 天，可以考慮停用")
    pending = [r for r in result["rows"] if not r["judged"] and r["tokens"] >= THRESHOLD]
    for r in pending:
        lines.append(f"- {label(r['tool'])}（{NAMES[r['agent']]}）：每段對話約 {n(r['tokens'])} tokens，"
                     f"這 7 天共約 {n(r['week'])} tokens；{r['why']}，先不判斷")
    if not idle and not pending:
        lines.append("- 沒有" if result["latest"] or result["codex_measured"] else "- 未知：還沒有對話紀錄可以量開頭成本")
    top = result["rows"][:5]
    if top:
        lines.append("- 開頭成本最高的：" + "、".join(
            f"{label(r['tool'])}（{NAMES[r['agent']]}）約 {n(r['tokens'])}，14 天內用了 {r['used_14d']} 段" for r in top))

    lines += ["", "### 背景與非互動的模型用量（這 7 天，不是你在對話裡用的）", ""]
    if result["background"]:
        for g in result["background"]:
            lines.append(f"- {g['who']} {g['where']}：{n(g['sessions'])} 段、{n(g['calls'])} 次呼叫；未快取輸入 {n(g['uncached'])}、"
                         f"快取讀取 {n(g['cache_read'])}、輸出 {n(g['output'])}")
    else:
        lines.append("- 沒有")
    o = result["own"]
    lines.append(f"- 對照：你自己的對話 {n(o['sessions'])} 段、{n(o['calls'])} 次呼叫；未快取輸入 {n(o['uncached'])}、"
                 f"快取讀取 {n(o['cache_read'])}、輸出 {n(o['output'])}")

    lines += ["", "### 對話開頭的大小（新對話第一回合的 prompt，這 7 天的中位數）", ""]
    for agent in ("claude-code", "codex"):
        cur = result["startup"].get(agent)
        if not cur:
            lines.append(f"- {NAMES[agent]}：未知（這 7 天沒有讀得到的對話）")
            continue
        text = f"- {NAMES[agent]}：{n(cur['median'])} tokens（{cur['n']} 段，{n(cur['min'])} 到 {n(cur['max'])}）"
        g = result["growth"].get(agent)
        if g:
            text += f"；{g['from_week']} 是 {n(g['from'])}，{'多' if g['change'] >= 0 else '少'} {abs(g['change']):.0%}"
        lines.append(text)
        if g and g["reasons"]:
            lines.append("  - 主要原因（開頭成本變多的）：" + "、".join(
                f"{label(r['tool'])} +{n(r['delta'])}" + ("（新的）" if r["new"] else "") for r in g["reasons"]))
        elif g and g["change"] >= GROWTH:
            lines.append("  - 工具的開頭成本沒有變多：可能是規則、專案的 CLAUDE.md 或第一則訊息變長")
    if not result["growth"]:
        lines.append("- 還沒有上週的紀錄可以比較")

    lines += ["", "### 名冊比對（裝著、但名冊上不是預設或試用的）", ""]
    if not result["roster_checked"]:
        lines.append("- 未知：讀不到名冊")
    else:
        for i in result["off_roster"]:
            cost = f"每段對話約 {n(i['tokens'])} tokens" if i["tokens"] is not None else "開頭成本未知"
            reason = f"；理由：{i['reason']}" if i.get("reason") else ""
            lines.append(f"- {i['name']}（{i['where']}）：名冊上是 {i['status']}（{i['card']}）{reason}；{cost}（{i['how']}）")
        if not result["off_roster"]:
            lines.append("- 沒有")
        lines.append(f"- 名冊上沒有的：{result['unknown_roster']} 個（還沒評估過）")
    return lines


def summary(result):
    idle = sum(1 for r in result["rows"] if r["idle"] and r["tokens"] >= THRESHOLD)
    cur = result["startup"].get("claude-code")
    head = f"開頭約 {n(cur['median'])} tokens" if cur else "開頭大小未知"
    return f"新裝 {len(result['new'])} 個、成本高又沒在用 {idle} 個、{head}"


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check(name, ok):
        print(f"{'通過' if ok else '失敗'}：{name}")
        if not ok:
            failures.append(name)

    now = datetime(2026, 11, 6, 12, 0).timestamp()

    def iso(days_ago):
        return datetime.fromtimestamp(now - days_ago * DAY, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        home, state = tmp / "home", tmp / "state"

        def put(path, text):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        def jsonl(path, records):
            put(path, "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records))

        def assistant(mid, days_ago, fresh=0, made=0, cached=0, out=0, content=None):
            return {"type": "assistant", "timestamp": iso(days_ago), "message": {
                "id": mid, "usage": {"input_tokens": fresh, "cache_creation_input_tokens": made,
                                     "cache_read_input_tokens": cached, "output_tokens": out},
                "content": content or [{"type": "text", "text": "秘密回答乙"}]}}

        def start(days_ago, entrypoint="claude-desktop", cwd=None):
            return {"type": "user", "entrypoint": entrypoint, "cwd": cwd or str(home / "proj"), "timestamp": iso(days_ago),
                    "message": {"role": "user", "content": "秘密內容甲"}}

        heavy = "heavy-skill"
        listing = "\n".join([f"- caveman: {'短' * 40}", f"- claude-mem:mem-search: {'搜尋記憶 ' * 50}",
                             f"- {heavy}: " + "x" * 6000, "  接續的一行也算 heavy-skill", f"- claude-mem:do: {'執行' * 20}",
                             "- example-skills:algorithmic-art"])
        projects = home / ".claude" / "projects" / "proj"
        # 最新的互動對話：第一回合的 attachment 記了實際給模型的內容
        jsonl(projects / "s00.jsonl", [
            start(0.5),
            {"type": "attachment", "attachment": {"type": "skill_listing", "content": listing, "isInitial": True,
                                                   "names": ["caveman", "claude-mem:mem-search", heavy, "claude-mem:do",
                                                             "example-skills:algorithmic-art"]}},
            {"type": "attachment", "attachment": {"type": "hook_success", "hookEvent": "SessionStart", "toolUseID": "h1",
                                                   "command": "claude-mem hook claude-code context", "stdout": "x" * 9000}},
            {"type": "attachment", "attachment": {"type": "hook_system_message", "hookEvent": "SessionStart", "toolUseID": "h1",
                                                   "content": "顯示給使用者看的" * 1000}},
            {"type": "attachment", "attachment": {"type": "hook_additional_context", "hookEvent": "SessionStart",
                                                   "toolUseID": "SessionStart", "content": "記" * 3000}},
            {"type": "attachment", "attachment": {"type": "mcp_instructions_delta", "addedNames": ["chrome_devtools"],
                                                   "addedBlocks": ["y" * 2000]}},
            {"type": "attachment", "attachment": {"type": "deferred_tools_delta", "addedNames": [
                "mcp__chrome_devtools__click", "mcp__plugin_claude-mem_mcp-search__search"]}},
            assistant("m1", 0.5, fresh=5, made=80000, out=100),
            assistant("m1", 0.5, fresh=5, made=80000, out=100,
                      content=[{"type": "tool_use", "name": "mcp__chrome_devtools__click", "input": {}}]),
            assistant("m2", 0.4, fresh=3, made=200, cached=80000, out=50),
            {"type": "attachment", "attachment": {"type": "skill_listing", "content": "- late: 之後才加的", "names": ["late"]}},
        ])
        # 其他 12 段互動對話：1 到 20 天前；有一段用了 claude-mem 的 skill，一段用了 caveman
        for i, days in enumerate([1, 2, 3, 4, 5, 6, 8, 9, 11, 13, 16, 20], 1):
            content = None
            if i == 3:
                content = [{"type": "tool_use", "name": "Skill", "input": {"skill": "claude-mem:mem-search"}}]
            if i == 5:
                content = [{"type": "tool_use", "name": "Skill", "input": {"skill": "caveman"}}]
            jsonl(projects / f"s{i:02d}.jsonl", [start(days), assistant(f"a{i}", days, fresh=10, made=70000 + i, out=10, content=content)])
        # 子 agent 的紀錄：用到的工具算進主對話
        jsonl(projects / "s01" / "subagents" / "agent-x.jsonl", [start(1), assistant("sub1", 1, made=10, content=[
            {"type": "tool_use", "name": "Skill", "input": {"skill": "caveman"}}])])
        # 背景：記憶工具的 observer（sdk-ts）；同一個回應拆成兩行只算一次，10 天前的不算進這 7 天
        jsonl(home / ".claude" / "projects" / "observer" / "o1.jsonl", [
            start(2, "sdk-ts", str(home / ".claude-mem" / "observer-sessions")),
            assistant("o-1", 2, fresh=1000, made=500, cached=30, out=400),
            assistant("o-1", 2, fresh=1000, made=500, cached=30, out=400),
            assistant("o-2", 1, fresh=2000, made=0, cached=70, out=600)])
        jsonl(home / ".claude" / "projects" / "observer" / "o0.jsonl", [
            start(10, "sdk-ts", str(home / ".claude-mem" / "observer-sessions")), assistant("o-0", 10, fresh=99999, out=99999)])
        # 裝了的東西
        put(home / ".claude" / "plugins" / "installed_plugins.json", json.dumps({"plugins": {
            "claude-mem@thedotmack": [{"installedAt": iso(3)}],
            "fresh-plugin@market": [{"installedAt": iso(2)}],
            "agent-skills@addy-agent-skills": [{"installedAt": iso(3)}]}}))
        put(home / ".claude" / "settings.json", json.dumps({"enabledPlugins": {"agent-skills@addy-agent-skills": False}}))
        for name in ("caveman", heavy, "omnikit-weekly"):
            put(home / ".claude" / "skills" / name / "SKILL.md", f"---\nname: {name}\n---\n")
        put(home / ".claude.json", json.dumps({"mcpServers": {"chrome_devtools": {}, "new-mcp": {}}}))
        put(state / "weekly" / "inventory.json", json.dumps({"date": "2026-10-30", "items": {
            "mcp:chrome_devtools@~/.claude.json": "2026-10-01"}}))
        put(state / "weekly" / "startup.json", json.dumps({"weeks": {"2026-W44": {"claude-code": {
            "median": 60000, "min": 59000, "max": 61000, "n": 6, "parts": {"plugin:claude-mem": 100, "skill:caveman": 40}}}}}))
        # Codex：互動的 rollout（開頭有 skill 清單）與 exec 的
        block = ("<skills_instructions>\n### Available skills\n- `r0` = `" + str(home / ".agents" / "skills") + "`\n"
                 f"- codex-heavy: {'z' * 5000} (file: r0/codex-heavy/SKILL.md)\n- tiny: 小 (file: r0/tiny/SKILL.md)\n")
        codex_dir = home / ".codex" / "sessions" / "2026" / "11" / "05"
        jsonl(codex_dir / "rollout-2026-11-05T09-00-00-a.jsonl", [
            {"type": "session_meta", "payload": {"source": "vscode", "cwd": str(home / "proj"), "timestamp": iso(1)}},
            {"type": "response_item", "payload": {"type": "message", "content": [{"type": "input_text", "text": block}]}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 20000, "cached_input_tokens": 0, "output_tokens": 10},
                "last_token_usage": {"input_tokens": 20000}}}}])
        jsonl(codex_dir / "rollout-2026-11-05T10-00-00-b.jsonl", [
            {"type": "session_meta", "payload": {"source": "exec", "cwd": str(home / "tools" / "nightly" / "run"), "timestamp": iso(1)}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 3000, "cached_input_tokens": 1000, "output_tokens": 200},
                "last_token_usage": {"input_tokens": 3000}}}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 5000, "cached_input_tokens": 1000, "output_tokens": 300},
                "last_token_usage": {"input_tokens": 2000}}}}])
        roster = {"heavy-skill": {"id": "heavy-skill", "status": "rejected", "reason": "跟內建功能重複"},
                  "addy-agent-skills": {"id": "addy-agent-skills", "status": "pending"},
                  "chrome-devtools-mcp": {"id": "chrome-devtools-mcp", "status": "trial"},
                  "caveman": {"id": "caveman", "status": "default"}}
        asked = []

        def fake_details(plugin_id):
            asked.append(plugin_id)
            return {"fresh-plugin@market": 1500, "agent-skills@addy-agent-skills": 3779}.get(plugin_id)

        def created(path):
            # skill 資料夾 40 天前就有了；OmniKit 自己的 skill 剛重新連結過
            return now - (0.5 if Path(path).name == "omnikit-weekly" else 40) * DAY

        def offline(*_a, **_k):
            raise RuntimeError("成本監測不應該連網")

        real = socket.socket.connect, socket.create_connection
        socket.socket.connect, socket.create_connection = offline, offline
        try:
            result = measure(home, state, now, roster, fake_details, created_at=created, ours={"omnikit-weekly"})
        finally:
            socket.socket.connect, socket.create_connection = real
        rows = {(r["agent"], r["tool"]): r for r in result["rows"]}
        claude = {t: r["tokens"] for (a, t), r in rows.items() if a == "claude-code"}

        check("不連網也能量（連網的呼叫都換成會失敗的）", result["latest"])
        check("開頭成本照第一回合實際載入的量：skill 清單、hook 注入、MCP 說明與工具名稱，依工具歸類",
              set(claude) == {"skill:caveman", "plugin:claude-mem", f"skill:{heavy}", "mcp:chrome_devtools", "plugin:example-skills"})
        check("plugin 的 skill、hook 加進 context 的內容與 plugin 的 MCP 都算進 plugin；只有一個 hook 時合併的內容歸給它",
              3000 + 100 < claude["plugin:claude-mem"] < 4000)
        check("hook_system_message 是顯示給使用者看的，不算進開頭成本", claude["plugin:claude-mem"] < 8000)
        check("skill 清單裡只有名稱、沒有說明的也算", 0 < claude["plugin:example-skills"] < 20)
        two = first_turn_parts([
            {"type": "hook_success", "hookEvent": "SessionStart", "toolUseID": "a", "command": "claude-mem hook context"},
            {"type": "hook_success", "hookEvent": "SessionStart", "toolUseID": "b", "command": "python ~/scripts/greet.py"},
            {"type": "hook_additional_context", "hookEvent": "SessionStart", "toolUseID": "SessionStart", "content": "z" * 8000}],
            {"claude-mem"})
        check("好幾個 SessionStart hook：合併的內容分不出是誰的，標成多個 hook 合併", two == {"hook:SessionStart（多個 hook 合併）": 2000})
        check("skill 清單接續的行算前一個 skill；第一回合之後才加的不算",
              claude[f"skill:{heavy}"] >= 1500 and "skill:late" not in claude)
        new = {i["name"]: i for i in result["new"]}
        check("A：7 天內新裝的 plugin 與新出現的 MCP 都列出來", {"fresh-plugin@market", "new-mcp", "claude-mem@thedotmack"} <= set(new)
              and "chrome_devtools" not in new)
        check("A：還沒載入過的 plugin 用 claude plugin details 的估計，並註明少算的部分",
              new["fresh-plugin@market"]["tokens"] == 1500 and "不含 MCP" in new["fresh-plugin@market"]["how"])
        check("A：已經載入過的用實際的量", new["claude-mem@thedotmack"]["tokens"] == claude["plugin:claude-mem"]
              and "實際載入" in new["claude-mem@thedotmack"]["how"])
        check("A：MCP 還沒載入過就標未知", new["new-mcp"]["tokens"] is None)
        check("A：OmniKit 自己的 skill 重新連結過，不算新裝的", "omnikit-weekly" not in new)
        r = rows[("claude-code", f"skill:{heavy}")]
        check("B：成本高、14 天內與最近 10 段對話都沒用到：列為成本高又沒在用（不用等 30 天）",
              r["idle"] and r["used_14d"] == 0 and r["used_last10"] == 0 and r["week"] == r["tokens"] * r["convs_week"])
        check("B：這 7 天的對話數只算互動的", rows[("claude-code", "skill:caveman")]["convs_week"] == 7)
        mem = rows[("claude-code", "plugin:claude-mem")]
        check("B：裝好之後還不到 10 段對話：先不判斷", not mem["judged"] and not mem["idle"])
        cav = rows[("claude-code", "skill:caveman")]
        check("B：子 agent 用到的算進主對話；用過的不算沒在用", cav["used_14d"] == 2 and not cav["idle"])
        check("B：Codex 的開頭成本從 rollout 的 skill 清單量", rows[("codex", "skill:codex-heavy")]["tokens"] >= 1000
              and rows[("codex", "skill:codex-heavy")]["idle"])
        bg = {(g["who"], g["where"]): g for g in result["background"]}
        obs = bg.get(("Claude Code（sdk-ts）", "~/.claude-mem/observer-sessions"))
        check("C：背景用 entrypoint 判斷、依工作資料夾分組；同一個回應拆兩行只算一次；7 天前的不算",
              obs and obs["calls"] == 2 and obs["uncached"] == 1000 + 500 + 2000 and obs["cache_read"] == 100 and obs["output"] == 1000
              and obs["sessions"] == 1)
        cx = bg.get(("Codex（exec）", "~/tools/nightly"))
        check("C：Codex 的 exec 算非互動，用量取最後一個 token_count 的累計", cx and cx["uncached"] == 4000
              and cx["cache_read"] == 1000 and cx["output"] == 300 and cx["calls"] == 2)
        check("C：你自己的對話另外列出來對照（子 agent 的用量算進主對話）",
              result["own"]["calls"] == 2 + 6 + 1 and result["own"]["sessions"] == 7)
        cur = result["startup"]["claude-code"]
        check("D：只算這 7 天的互動對話，第一回合是輸入、快取寫入、快取讀取三項相加",
              cur["n"] == 7 and cur["max"] == 80005 and result["startup"]["codex"]["median"] == 20000)
        g = result["growth"]["claude-code"]
        check("D：比上週多 10% 以上：列出開頭成本變多的工具（含新的）",
              g["from_week"] == "2026-W44" and g["change"] >= 0.10 and g["reasons"][0]["tool"] in ("plugin:claude-mem", f"skill:{heavy}")
              and any(x["new"] for x in g["reasons"]))
        off = {i["name"]: i for i in result["off_roster"]}
        check("E：名冊上是 rejected 或 pending 的列出來，附開頭成本；default、trial 的不列",
              off[heavy]["status"] == "rejected" and off[heavy]["tokens"] == claude[f"skill:{heavy}"]
              and "agent-skills@addy-agent-skills" in off and "caveman" not in off and "chrome_devtools" not in off)
        check("E：停用中的 plugin 註明停用，用估計", "停用中" in off["agent-skills@addy-agent-skills"]["how"]
              and off["agent-skills@addy-agent-skills"]["tokens"] == 3779)
        check("E：名冊上沒有的算數量", result["unknown_roster"] >= 2)
        check("plugin details 只問還沒載入過的 plugin", "claude-mem@thedotmack" not in asked)

        text = "\n".join(report(result))
        check("報告：五個小節都在，數字有千分位", all(h in text for h in ("### 新裝的工具", "### 成本高又沒在用的", "### 背景與非互動",
                                                       "### 對話開頭的大小", "### 名冊比對")) and "80,005" in text)
        check("報告：不輸出對話內容", "秘密內容甲" not in text and "秘密回答乙" not in text)
        check("摘要一行", summary(result).startswith("新裝 ") and "成本高又沒在用 2 個" in summary(result))

        measure(home, state, now, roster, fake_details, persist=True, created_at=created)
        saved = json.loads((state / "weekly" / "startup.json").read_text(encoding="utf-8"))["weeks"]
        check("persist：這週的開頭大小與各工具的開頭成本存起來，下週拿來比", "2026-W45" in saved and "2026-W44" in saved
              and saved["2026-W45"]["claude-code"]["parts"][f"skill:{heavy}"] == claude[f"skill:{heavy}"])
        again = measure(home, state, now + DAY, roster, fake_details, created_at=created)
        check("persist：清單存過之後，MCP 不再當成新裝的", "new-mcp" not in {i["name"] for i in again["new"]})

        # 好幾個 SessionStart hook 合併的開頭成本：hook 沒有「用到」的紀錄，不判斷有沒有在用
        other = tmp / "other"
        jsonl(other / ".claude" / "projects" / "p" / "x.jsonl", [
            start(1),
            {"type": "attachment", "attachment": {"type": "hook_success", "hookEvent": "SessionStart", "toolUseID": "a",
                                                   "command": "node a.js"}},
            {"type": "attachment", "attachment": {"type": "hook_success", "hookEvent": "SessionStart", "toolUseID": "b",
                                                   "command": "node b.js"}},
            {"type": "attachment", "attachment": {"type": "hook_additional_context", "hookEvent": "SessionStart",
                                                   "toolUseID": "SessionStart", "content": "h" * 6000}},
            assistant("x1", 1, made=9000)])
        hooks = measure(other, tmp / "other-state", now, {}, None, created_at=created, ours=set())
        row = hooks["rows"][0]
        check("B：hook 每段對話都會跑，沒有用到的紀錄：不判斷，但成本照列",
              row["tool"].startswith("hook:") and row["tokens"] == 1500 and not row["judged"] and not row["idle"]
              and "hook" in row["why"] and "先不判斷" in "\n".join(report(hooks)))

        empty = measure(tmp / "nobody", tmp / "nostate", now, None, None)
        text = "\n".join(report(empty))
        check("什麼紀錄都沒有：照常產生，量不到的標未知", "未知" in text and "讀不到名冊" in text and empty["baseline"])

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="OmniKit 成本監測（FR-40 到 FR-44）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    import os
    state = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "omnikit"
    result = measure(Path.home(), state, plugin_details=details)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print("\n".join(report(result)))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
