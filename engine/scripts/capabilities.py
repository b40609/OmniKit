# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""能力清點：說「做不到／沒有工具／請你手動做」之前，先看這台電腦上 agent 能用什麼。

為什麼有這支：2026-11-18 查出來，agent 好幾週回答使用者「這裡沒有 T3 工具，沒辦法派」，其實本機有 t3 CLI
（%USERPROFILE%\\.t3\\bin\\t3.cmd，t3 thread start 就能開 T3 對話、指定帳號與模型），也有 T3 的本機 MCP 端點
可以接。Git Bash 的 command -v t3 找不到，是因為那個資料夾只有 t3.cmd，Bash 只會自動補 .exe、不會補 .cmd；
agent 就誤判成沒裝。這支把這類「其實有」的東西一次列出來，並印出省事的做法。

列出四類（只看檔案、PATH 與本機連線；不執行被清點的工具，除非加 --versions；不讀也不印金鑰）：
1. 指令：agent 相關的 CLI 在哪裡、各種找法看不看得到。
   - 這個行程的 PATH（照 PATHEXT 補 .exe、.cmd、.bat…，PowerShell 另外認 .ps1）
   - Bash 的找法（只認沒有副檔名或 .exe 的檔名）：只在 Windows 判斷
   - 登錄檔的使用者與系統 PATH（新開的 PowerShell 讀這個）：只在 Windows
   - 常見的安裝資料夾（不在 PATH 也找）
2. MCP：Claude Code（~/.claude.json 的 user 與這個資料夾的 local、專案的 .mcp.json、CLAUDE_CONFIG_DIR）、
   Codex（config.toml）、Antigravity（~/.gemini/config/mcp_config.json）、Gemini CLI（~/.gemini/settings.json）
   登記的 server。只印名稱、類型與目標（URL 去掉帳密與查詢字串；stdio 只印指令檔名），不印 env、headers、args。
3. 本機端點：已知的本機 MCP 端點（目前是 T3 Code 的 http://127.0.0.1:3773/mcp）有沒有開、要不要登入、
   哪些 agent 已經接上。
4. 建議：最省事、現在就能做的先列；要使用者做的只有登入核准這類非他不可的步驟。

沒列在這裡不代表做不到：新工具、新功能常比模型的訓練資料新，還要看該工具的 --help、最新官方文件與原始碼。

用法：
  uv run engine/scripts/capabilities.py                 全部（幾秒內）
  uv run engine/scripts/capabilities.py --cmd ffmpeg    多找幾個指令（可重複）
  uv run engine/scripts/capabilities.py --versions      加跑每個找到的指令的 --version（每個最多 5 秒）
  uv run engine/scripts/capabilities.py --json
  uv run engine/scripts/capabilities.py --selftest
"""
import argparse
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import tomllib
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

# 名稱 → 一句話用途。只放 agent 工作會用到的；要找別的用 --cmd。
KNOWN = {
    "claude": "Claude Code",
    "codex": "Codex CLI",
    "agy": "Antigravity CLI：無頭派工作給 Gemini 與 Antigravity 上的模型",
    "gemini": "Gemini CLI",
    "t3": "T3 Code：t3 thread start 開 T3 對話、指定帳號實例與模型",
    "opencode": "OpenCode",
    "aider": "Aider",
    "cursor-agent": "Cursor CLI",
    "copilot": "GitHub Copilot CLI",
    "ollama": "Ollama 本機模型",
    "gh": "GitHub CLI",
    "git": "Git",
    "uv": "uv：跑 OmniKit 的腳本",
    "node": "Node.js",
    "npm": "npm",
    "npx": "npx",
    "python": "Python",
    "pwsh": "PowerShell 7",
    "docker": "Docker",
    "wsl": "WSL",
}

# 已知的本機 MCP 端點。gives 寫接上之後多了什麼；connect 的 {url} 換成端點位址。
ENDPOINTS = [{
    "id": "t3",
    "label": "T3 Code",
    "url": "http://127.0.0.1:3773/mcp",
    "doc": "https://github.com/pingdotgg/t3code/blob/main/docs/user/outside-agents.md",
    "gives": "t3_thread_launch 開對話可帶思考程度（modelSelection.options）、t3_thread_organize 可以 settle、"
             "t3_thread_read／t3_thread_wait 讀結果",
    "connect": {
        # 2026-11-18 實測通過：login 要互動式終端機（Bash 工具會回 this isn't an interactive terminal）
        "Claude Code": ("claude", "claude mcp add --scope user --transport http t3 {url}，再請使用者在終端機分頁跑 "
                                  "claude mcp login t3（要 Sign-in code 時用 t3 auth pairing create --ttl 10m，預設 scope）"),
        "Codex": ("codex", "codex mcp add t3 --url {url}，再 codex mcp login t3"),
    },
    # 已登記但可能還沒登入：怎麼看、怎麼登入
    "login": {
        "Claude Code": "claude mcp list 看 t3 是不是 Needs authentication，是的話請使用者在終端機分頁跑 claude mcp login t3"
                       "（每個 CLAUDE_CONFIG_DIR 各一次，有效 30 天）",
        "Codex": "codex mcp list 看 t3 有沒有登入，沒有的話 codex mcp login t3",
    },
}]

DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


# ---------- 指令 ----------

def known_dirs(home, env, windows):
    """不在 PATH 也要看的安裝資料夾。"""
    h = Path(home)
    dirs = [h / ".t3" / "bin", h / ".local" / "bin", h / ".bun" / "bin", h / ".cargo" / "bin"]
    if windows:
        if env.get("APPDATA"):
            dirs.append(Path(env["APPDATA"]) / "npm")
        if env.get("LOCALAPPDATA"):
            local = Path(env["LOCALAPPDATA"])
            dirs += [local / "agy" / "bin", local / "Microsoft" / "WinGet" / "Links"]
    else:
        dirs += [h / ".npm-global" / "bin", Path("/usr/local/bin"), Path("/opt/homebrew/bin")]
    return dirs


def registry_dirs():
    """登錄檔的系統與使用者 PATH：新開的 PowerShell、cmd 讀的就是這個（舊的行程拿不到安裝後才加的資料夾）。"""
    if os.name != "nt":
        return []
    import winreg
    out = []
    for root, sub in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(root, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        out += [os.path.expandvars(p.strip()) for p in str(value).split(";") if p.strip()]
    return out


def split_dirs(value, skip=()):
    """PATH → 資料夾清單；skip 裡的資料夾（uv run 臨時環境的 Scripts、bin）不算，不然 python 會指到臨時環境。"""
    skip = [Path(s).resolve() for s in skip]
    out = []
    for p in (value or "").split(os.pathsep):
        if not p.strip():
            continue
        try:
            if any(Path(p).resolve().is_relative_to(s) for s in skip):
                continue
        except (OSError, ValueError):
            pass
        out.append(p)
    return out


def locate(name, dirs, exts, need_exec=False):
    """在 dirs 裡依序找 name 加上每個副檔名；找到第一個就回傳完整路徑。"""
    for d in dirs:
        for ext in exts:
            p = Path(d) / (name + ext)
            try:
                if p.is_file() and (not need_exec or os.access(p, os.X_OK)):
                    return str(p)
            except OSError:
                continue
    return None


def ext_lists(windows, pathext, name=""):
    """PowerShell、cmd 只執行 PATHEXT 的副檔名（PowerShell 另外認 .ps1），沒有副檔名的檔案不算；
    Bash 只認沒有副檔名或 .exe。名稱自己帶了副檔名（t3.cmd）就照原名找。"""
    if not windows:
        return {"shell": [""]}
    exts = [e.lower() for e in (pathext or DEFAULT_PATHEXT).split(";") if e.strip()] + [".ps1"]
    own = Path(name).suffix.lower()
    return {"shell": [""] if own in exts else exts, "bash": [""] if own else ["", ".exe"]}


def scan_commands(names, path_dirs, reg_dirs, extra_dirs, windows, pathext=None):
    """每個指令：各種找法找到的路徑，以及要提醒的事。"""
    need_exec = not windows
    rows = []
    for name in names:
        exts = ext_lists(windows, pathext, name)
        seen = {"process": locate(name, path_dirs, exts["shell"], need_exec)}
        if windows:
            seen["bash"] = locate(name, path_dirs, exts["bash"])
            seen["registry"] = locate(name, reg_dirs, exts["shell"])
        seen["known"] = locate(name, extra_dirs, exts["shell"], need_exec)
        path = seen["process"] or seen.get("registry") or seen["known"]
        notes = []
        if path:
            fname = Path(path).name
            if windows and seen["process"] and not seen["bash"]:
                notes.append(f"Git Bash 打 {name} 找不到：這裡只有 {fname}，Bash 不會自動補 {Path(fname).suffix}；"
                             f"在 PowerShell 跑，或在 Bash 打 {fname}（或完整路徑）")
            if not seen["process"] and seen.get("registry"):
                notes.append("這個行程的 PATH 沒有，新開的 PowerShell 有（裝好之後才加進 PATH，舊的行程拿不到）：用完整路徑")
            elif not seen["process"]:
                notes.append("不在 PATH：用完整路徑")
        rows.append({"name": name, "what": KNOWN.get(name, ""), "path": path, "seen": seen, "notes": notes})
    return rows


def add_versions(rows, timeout=5):
    for row in rows:
        p = row["path"]
        if not p or p.lower().endswith(".ps1"):
            continue
        try:
            r = subprocess.run([p, "--version"], capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
            text = (r.stdout or r.stderr).decode("utf-8", "replace").strip().splitlines()
            row["version"] = text[0][:80] if text else None
        except (OSError, subprocess.SubprocessError):
            row["version"] = None


# ---------- MCP 設定 ----------

def read_doc(path):
    """設定檔 → dict；不存在回 None，讀不懂回 {"_error": ...}（不附內容，裡面可能有金鑰）。"""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8-sig")
        return tomllib.loads(text) if p.suffix == ".toml" else json.loads(text)
    except (OSError, ValueError) as e:
        return {"_error": type(e).__name__}


def clean_url(url):
    """只留 scheme、主機、埠與路徑：帳密、查詢字串與 fragment 可能帶金鑰。"""
    try:
        p = urlsplit(str(url))
        port = f":{p.port}" if p.port else ""
        host = p.hostname or ""
        host = f"[{host}]" if ":" in host else host
        return f"{p.scheme}://{host}{port}{p.path}"
    except ValueError:
        return "（URL 讀不懂）"


def describe(cfg):
    if not isinstance(cfg, dict):
        return {"kind": "?", "target": ""}
    url = cfg.get("url") or cfg.get("serverUrl") or cfg.get("httpUrl")
    off = cfg.get("enabled") is False or cfg.get("disabled") is True
    if url:
        return {"kind": str(cfg.get("type") or "http"), "target": clean_url(url), "off": off}
    if cfg.get("command"):
        return {"kind": "stdio", "target": Path(str(cfg["command"]).replace("\\", "/")).name, "off": off}
    return {"kind": str(cfg.get("type") or "?"), "target": "", "off": off}


def same_dir(a, b):
    norm = lambda s: str(s).replace("\\", "/").rstrip("/").lower()  # noqa: E731
    return norm(a) == norm(b)


def mcp_sources(home, cwd, env):
    """(agent, 範圍, 設定檔, 取出 server 表的函式)"""
    h, here = Path(home), Path(cwd)

    def local_scope(doc):
        for key, proj in (doc.get("projects") or {}).items():
            if same_dir(key, here) and isinstance(proj, dict):
                return proj.get("mcpServers") or {}
        return {}

    claude_files = [h / ".claude.json"]
    if env.get("CLAUDE_CONFIG_DIR"):
        claude_files.append(Path(env["CLAUDE_CONFIG_DIR"]) / ".claude.json")
    out = []
    for f in claude_files:
        out.append(("Claude Code", "user", f, lambda d: d.get("mcpServers") or {}))
        out.append(("Claude Code", "local", f, local_scope))
    out.append(("Claude Code", "project", here / ".mcp.json", lambda d: d.get("mcpServers") or {}))
    codex_home = Path(env["CODEX_HOME"]) if env.get("CODEX_HOME") else h / ".codex"
    out.append(("Codex", "user", codex_home / "config.toml", lambda d: d.get("mcp_servers") or {}))
    out.append(("Antigravity", "user", h / ".gemini" / "config" / "mcp_config.json", lambda d: d.get("mcpServers") or {}))
    out.append(("Gemini CLI", "user", h / ".gemini" / "settings.json", lambda d: d.get("mcpServers") or {}))
    return out


def scan_mcp(home, cwd, env):
    rows, cache = [], {}
    for agent, scope, path, pick in mcp_sources(home, cwd, env):
        key = str(path)
        if key not in cache:
            cache[key] = read_doc(path)
        doc = cache[key]
        if doc is None:
            continue
        if "_error" in doc:
            if scope != "local":  # 同一份檔案只報一次
                rows.append({"agent": agent, "scope": scope, "file": key, "error": f"讀不懂（{doc['_error']}）"})
            continue
        servers = pick(doc)
        if not isinstance(servers, dict):
            continue
        for name, cfg in servers.items():
            rows.append({"agent": agent, "scope": scope, "file": key, "name": str(name), **describe(cfg)})
    return rows


# ---------- 本機端點 ----------

def probe(url, timeout=2.0):
    """GET 一次：開著不開、要不要登入。不帶任何憑證，不走 proxy。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json, text/event-stream"})
    try:
        with opener.open(req, timeout=timeout) as r:
            return {"state": "open", "status": r.status}
    except urllib.error.HTTPError as e:
        auth = e.headers.get("WWW-Authenticate", "") if e.headers else ""
        return {"state": "login" if e.code == 401 else "open", "status": e.code,
                "oauth": "resource_metadata" in auth or "Bearer" in auth}
    except (urllib.error.URLError, OSError) as e:
        return {"state": "closed", "error": type(getattr(e, "reason", e)).__name__}


def host_port(url):
    try:
        p = urlsplit(url)
        return (p.hostname or "").lower(), p.port or (443 if p.scheme == "https" else 80)
    except ValueError:
        return "", None


def scan_endpoints(endpoints, mcp_rows, commands, timeout=2.0):
    have = {r["name"] for r in commands if r["path"]}
    out = []
    for ep in endpoints:
        res = probe(ep["url"], timeout)
        _, port = host_port(ep["url"])
        wired = sorted({r["agent"] for r in mcp_rows if r.get("target", "").startswith("http")
                        and host_port(r["target"])[0] in LOCAL_HOSTS and host_port(r["target"])[1] == port})
        missing = {agent: how.format(url=ep["url"]) for agent, (cmd, how) in ep["connect"].items()
                   if agent not in wired and cmd in have}
        login = {agent: how for agent, how in (ep.get("login") or {}).items() if agent in wired}
        out.append({**{k: ep[k] for k in ("id", "label", "url", "doc", "gives")}, **res,
                    "wired": wired, "connect": missing, "login": login})
    return out


# ---------- 建議與輸出 ----------

def suggestions(commands, endpoints, windows):
    tips = []
    by = {r["name"]: r for r in commands}
    t3 = by.get("t3")
    if t3 and t3["path"]:
        exe = Path(t3["path"]).name if windows and not t3["seen"].get("bash") else "t3"
        tips.append(f"派工作給 T3 Code（可指定帳號實例與模型）：{exe} thread start . \"<任務>\" --provider <實例> "
                    f"--model <模型> --json --wait；先看 {exe} thread start --help")
    for ep in endpoints:
        if ep["state"] == "closed":
            continue
        if ep["state"] == "login":
            for agent, how in ep["login"].items():
                tips.append(f"{agent} 已登記 {ep['label']} 的 MCP，端點要登入：{how}（登入會開瀏覽器，要使用者核准一次）。"
                            f"登入之後多了：{ep['gives']}")
        for agent, how in ep["connect"].items():
            tips.append(f"{ep['label']} 的 MCP 端點開著、{agent} 還沒接：{how}。接上之後多了：{ep['gives']}。"
                        f"登入那一步會開瀏覽器，要使用者核准一次（文件：{ep['doc']}）")
    tips.append("不熟的指令先跑 <指令> --help（子指令也有 --help），再查它最新的官方文件；新功能常比模型的訓練資料新")
    return tips


def gather(names, *, home, cwd, env, windows, path_dirs, reg_dirs, extra_dirs, endpoints, pathext=None, timeout=2.0):
    commands = scan_commands(names, path_dirs, reg_dirs, extra_dirs, windows, pathext)
    mcp = scan_mcp(home, cwd, env)
    eps = scan_endpoints(endpoints, mcp, commands, timeout)
    return {"generated": datetime.now().isoformat(timespec="seconds"), "windows": windows, "commands": commands,
            "mcp": mcp, "endpoints": eps, "suggestions": suggestions(commands, eps, windows)}


STATE_TEXT = {"open": "開著", "login": "開著，要登入", "closed": "沒開（或不在這個埠）"}


def render(rep):
    found = [r for r in rep["commands"] if r["path"]]
    missing = [r["name"] for r in rep["commands"] if not r["path"]]
    lines = [f"能力清點（{rep['generated']}）", "", f"指令：找到 {len(found)} 個"]
    for r in found:
        ver = f"  [{r['version']}]" if r.get("version") else ""
        what = f"  {r['what']}" if r["what"] else ""
        lines.append(f"  {r['name']:<12} {r['path']}{ver}{what}")
        lines += [f"  {'':<12} 注意：{n}" for n in r["notes"]]
    if missing:
        lines.append(f"  沒找到（PATH、登錄檔 PATH、常見安裝資料夾都沒有）：{'、'.join(missing)}")
    lines += ["", "MCP server（各 agent 設定檔登記的；不含 plugin 與雲端 connector）："]
    if not rep["mcp"]:
        lines.append("  （沒有）")
    for agent in dict.fromkeys(r["agent"] for r in rep["mcp"]):
        items = []
        for r in rep["mcp"]:
            if r["agent"] != agent:
                continue
            if "error" in r:
                items.append(f"{Path(r['file']).name} {r['error']}")
            else:
                off = "，停用" if r.get("off") else ""
                items.append(f"{r['name']}（{r['scope']}，{r['kind']} {r['target']}{off}）".replace(" ）", "）"))
        lines.append(f"  {agent}：{'；'.join(items)}")
    lines += ["", "本機端點："]
    for ep in rep["endpoints"]:
        status = STATE_TEXT.get(ep["state"], ep["state"])
        wired = (f"；設定檔已登記：{'、'.join(ep['wired'])}（登入了沒有，在那個 agent 看 mcp list）"
                 if ep["wired"] else "；還沒有 agent 登記")
        lines.append(f"  {ep['label']}  {ep['url']}  {status}{wired if ep['state'] != 'closed' else ''}")
    lines += ["", "建議（省事的先）："]
    lines += [f"  {i}. {t}" for i, t in enumerate(rep["suggestions"], 1)]
    lines += ["", "沒列在這裡不代表做不到：還要看該工具的 --help、最新官方文件與原始碼。"]
    return "\n".join(lines)


# ---------- 主程式 ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description="能力清點：說做不到之前，列出這台電腦上 agent 能用的指令、MCP 與本機端點")
    ap.add_argument("--cmd", action="append", default=[], help="多找這個指令（可重複）")
    ap.add_argument("--versions", action="store_true", help="加跑每個找到的指令的 --version")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if args.selftest:
        return selftest()
    windows = os.name == "nt"
    env = dict(os.environ)
    home = Path.home()
    names = list(dict.fromkeys([*KNOWN, *args.cmd]))
    rep = gather(names, home=home, cwd=Path.cwd(), env=env, windows=windows,
                 path_dirs=split_dirs(env.get("PATH"), [sys.prefix] if sys.prefix != sys.base_prefix else []),
                 reg_dirs=registry_dirs(),
                 extra_dirs=known_dirs(home, env, windows), endpoints=ENDPOINTS, pathext=env.get("PATHEXT"))
    if args.versions:
        add_versions(rep["commands"])
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else render(rep))
    return 0


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check(label, cond):
        print(f"{'通過' if cond else '失敗'}：{label}")
        if not cond:
            failures.append(label)

    class Auth401(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Bearer resource_metadata="http://127.0.0.1/.well-known/x"')
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Auth401)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    with socket.socket() as s:  # 一個沒人聽的埠
        s.bind(("127.0.0.1", 0))
        dead = s.getsockname()[1]

    def touch(p, text="", mode=0o755):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        p.chmod(mode)
        return p

    try:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            home, proj = t / "home", t / "proj"
            bin1, bin2, bin3 = t / "bin1", t / "bin2", t / "bin3"
            for f in ("t3.cmd", "claude.exe", "codex", "codex.cmd"):
                touch(bin1 / f)
            touch(bin2 / "gemini.cmd")
            touch(bin3 / "agy.exe")
            touch(home / ".claude.json", json.dumps({
                "oauthAccount": {"emailAddress": "SECRET-MAIL"},
                "mcpServers": {
                    "omnikit": {"command": "C:\\x\\uv.exe", "args": ["--token", "SECRET-ARG"], "env": {"API_KEY": "SECRET-ENV"}},
                    "t3": {"type": "http", "url": f"http://u:SECRET-PW@127.0.0.1:{port}/mcp?key=SECRET-Q",
                           "headers": {"Authorization": "Bearer SECRET-H"}}},
                "projects": {str(proj).replace("\\", "/") + "/": {"mcpServers": {"local1": {"command": "node"}}}}}))
            touch(proj / ".mcp.json", "{ 壞掉的 json SECRET-BROKEN")
            touch(home / ".codex" / "config.toml",
                  '[mcp_servers.exa]\nurl = "https://mcp.exa.ai/mcp"\n[mcp_servers.exa.env]\nKEY = "SECRET-T"\n'
                  '[mcp_servers.old]\ncommand = "npx"\nenabled = false\n')
            (home / ".gemini" / "config").mkdir(parents=True)
            (home / ".gemini" / "config" / "mcp_config.json").write_text(
                json.dumps({"mcpServers": {"omnikit": {"command": "uv"}}}), encoding="utf-8-sig")  # 有 BOM
            eps = [{**ENDPOINTS[0], "url": f"http://127.0.0.1:{port}/mcp"},
                   {**ENDPOINTS[0], "id": "dead", "label": "沒開的", "url": f"http://127.0.0.1:{dead}/mcp"}]
            names = ["t3", "claude", "codex", "gemini", "agy", "nope"]
            rep = gather(names, home=home, cwd=proj, env={}, windows=True, path_dirs=[str(bin1)], reg_dirs=[str(bin2)],
                         extra_dirs=[bin3], endpoints=eps, pathext=".COM;.EXE;.BAT;.CMD", timeout=3)
            by = {r["name"]: r for r in rep["commands"]}
            text, blob = render(rep), json.dumps(rep, ensure_ascii=False)

            check("t3：PowerShell 的找法找得到 t3.cmd", (by["t3"]["seen"]["process"] or "").endswith("t3.cmd"))
            check("t3：Bash 的找法找不到（Bash 不補 .cmd），並提醒改打 t3.cmd 或用 PowerShell",
                  by["t3"]["seen"]["bash"] is None and any("t3.cmd" in n and "PowerShell" in n for n in by["t3"]["notes"]))
            check("claude.exe 與 npm 式的 codex（codex 加 codex.cmd）：Bash 也找得到、不提醒；PowerShell 的找法用 codex.cmd",
                  by["claude"]["seen"]["bash"] and by["codex"]["seen"]["bash"] and not by["claude"]["notes"]
                  and not by["codex"]["notes"] and by["codex"]["seen"]["process"].endswith("codex.cmd"))
            named = scan_commands(["t3.cmd"], [str(bin1)], [], [], windows=True)[0]
            check("名稱自己帶副檔名（t3.cmd）：兩種找法都找得到", named["seen"]["process"] and named["seen"]["bash"])
            check("uv run 臨時環境的資料夾不算進 PATH",
                  split_dirs(os.pathsep.join([str(bin1), str(bin2 / "sub")]), [bin2]) == [str(bin1)])
            check("只在登錄檔 PATH 的 gemini：找得到，提醒用完整路徑",
                  (by["gemini"]["path"] or "").endswith("gemini.cmd") and "新開的 PowerShell" in by["gemini"]["notes"][0])
            check("不在 PATH、在安裝資料夾的 agy：找得到，提醒用完整路徑",
                  (by["agy"]["path"] or "").endswith("agy.exe") and "不在 PATH" in by["agy"]["notes"][0])
            check("找不到的列在沒找到", by["nope"]["path"] is None and "沒找到" in text and "nope" in text)
            check("金鑰、帳密、查詢字串、args、env、壞掉的設定內容都不會印出來", "SECRET" not in text and "SECRET" not in blob)
            mcp = {(r["agent"], r.get("name")): r for r in rep["mcp"]}
            check("Claude 的 user 與 local 範圍都讀到；URL 只留主機、埠與路徑",
                  mcp[("Claude Code", "t3")]["target"] == f"http://127.0.0.1:{port}/mcp"
                  and mcp[("Claude Code", "local1")]["scope"] == "local"
                  and mcp[("Claude Code", "omnikit")]["target"] == "uv.exe")
            check("專案的 .mcp.json 壞掉：記成讀不懂，不中斷",
                  any(r.get("error", "").startswith("讀不懂") and r["file"].endswith(".mcp.json") for r in rep["mcp"]))
            check("Codex 的 config.toml、Antigravity 有 BOM 的 mcp_config.json 都讀到；停用的標出來",
                  ("Codex", "exa") in mcp and mcp[("Codex", "old")]["off"] and ("Antigravity", "omnikit") in mcp)
            ep = {e["id"]: e for e in rep["endpoints"]}
            check("開著要登入的端點：判成 login，Claude 已接上、Codex 沒接",
                  ep["t3"]["state"] == "login" and ep["t3"]["oauth"] and ep["t3"]["wired"] == ["Claude Code"]
                  and list(ep["t3"]["connect"]) == ["Codex"])
            check("已登記、端點要登入：告訴已登記的 agent 怎麼看、怎麼登入",
                  any(s.startswith("Claude Code 已登記") and "claude mcp login t3" in s for s in rep["suggestions"])
                  and not any(s.startswith("Codex 已登記") for s in rep["suggestions"]))
            check("沒開的端點：判成 closed，不給接上的建議",
                  ep["dead"]["state"] == "closed" and not any("沒開的" in s for s in rep["suggestions"]))
            check("建議先給省事的路：Windows 的 Bash 看不到 t3 時寫 t3.cmd thread start；Codex 怎麼接、登入要使用者核准",
                  rep["suggestions"][0].startswith("派工作給 T3") and "t3.cmd thread start" in rep["suggestions"][0]
                  and any(f"codex mcp add t3 --url http://127.0.0.1:{port}/mcp" in s and "核准" in s
                          for s in rep["suggestions"]))
            check("文字輸出有四段與結尾提醒",
                  all(k in text for k in ("指令：找到", "MCP server", "本機端點", "建議", "不代表做不到")))

            # 非 Windows：沒有 Bash 與登錄檔的判斷；沒有執行權限的不算
            if os.name != "nt":
                touch(t / "posix" / "t3")
                touch(t / "posix" / "noexec", mode=0o644)
                rows = scan_commands(["t3", "noexec"], [str(t / "posix")], [], [], windows=False)
                check("POSIX：有執行權限才算，沒有 Bash 與登錄檔欄位",
                      rows[0]["path"] and rows[1]["path"] is None and set(rows[0]["seen"]) == {"process", "known"})
            # --versions：.ps1 不跑；跑得起來的取第一行
            fake = [{"name": "py", "path": sys.executable, "seen": {}, "notes": []},
                    {"name": "ps", "path": str(t / "x.ps1"), "seen": {}, "notes": []}]
            add_versions(fake)
            check("--versions：取第一行，.ps1 不跑", (fake[0].get("version") or "").startswith("Python") and "version" not in fake[1])
    finally:
        server.shutdown()
        server.server_close()
    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
