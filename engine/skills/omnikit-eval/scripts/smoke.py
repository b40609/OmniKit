# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""第 1c 層煙霧測試（FR-24）：候選工具在隔離環境安裝，跑一次縮小版的情境，記錄
裝不裝得起來、有沒有被叫用、Claude Code 與 Codex 的非互動模式能不能跑、每回合的 context 成本。

隔離做法（2026-11-05 在這台實測，見 docs/v2/HANDOFF.md）：
- 獨立的使用者設定資料夾：Claude 用 CLAUDE_CONFIG_DIR、Codex 用 CODEX_HOME，每次重建。
  Codex 還會讀 ~/.agents/skills，所以在隔離的 config.toml 對每一個加 [[skills.config]] enabled = false。
- worktree 與執行目錄放在使用者資料夾外（預設 %SystemDrive%\\omnikit-eval，可用 OMNIKIT_EVAL_ROOT 改）：
  放在 C:\\Users\\<你> 底下時，Claude 會往上找到 ~/.claude/CLAUDE.md 當成專案指示。
- context 成本不花 token：把 API 位址指向本機的攔截伺服器（回 400），拿到每回合實際送出的請求，
  比較「沒裝」與「有裝」的大小。隔離後的基準約為 Claude 97 KB、Codex 70 KB。
- 有 hook、MCP 或可執行程式的工具，未經程式碼審查不在本機啟動：用 sandbox 指令在 Windows Sandbox 裡
  安裝並做 MCP 交握（沙箱裡沒有任何登入資訊）；審查過後加 --reviewed 才在本機跑 agent。
  WSL2 這台已啟用但沒有發行版，暫不支援。

真實執行需要登入隔離的設定資料夾（login 指令會說怎麼做）；沒登入的項目記「未知」，不當作通過。
結果寫到 data/funnel/smoke/<id>.json（契約 contracts/smoke.schema.json）。

用法：uv run scripts/smoke.py env [--live]                      檢查哪些隔離方式可用（--live 實際啟動一次沙箱）
      uv run scripts/smoke.py login                             印出隔離設定資料夾的登入方式
      uv run scripts/smoke.py context <id> <來源>               不花 token 量每回合 context 成本
      uv run scripts/smoke.py run <id> <來源> --prompt "…"      真實非互動執行，看有沒有被叫用
      uv run scripts/smoke.py sandbox <id> <來源> [--install "npm i -g x@1.2.3"]   在 Windows Sandbox 安裝與 MCP 交握
      來源：--repo owner/repo[@ref] 或 --path <資料夾>，可加 --mcp 名稱='{"command":…,"args":[…]}'（可重複）
      uv run scripts/smoke.py --selftest
"""
import argparse
import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime
from pathlib import Path

import _cheap
import _omnikit
import batch0
import layer0

FUNNEL = _omnikit.ROOT / "data" / "funnel"
CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
NODE = {"version": "v24.22.1", "sha256": "d2046d28c2c3dcd211ac5145c0bf30e2047ef9dfb306693c8c6e2eccd8b95fa5"}
CLAUDE_KEEP = {".credentials.json", ".claude.json"}
CODEX_KEEP = {"auth.json"}
EXEC_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".ps1", ".sh", ".bat", ".cmd", ".exe"}
DUMMY_KEY = "omnikit-capture-not-a-key"  # 只送到本機攔截伺服器
SANDBOX_DIR = r"C:\okrun"


def rmtree(path):
    # git 的 pack 檔是唯讀的，Windows 上要先拿掉唯讀才刪得掉
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=layer0.remove_readonly)
    else:
        shutil.rmtree(path, onerror=layer0.remove_readonly)


# 從外層 agent 繼承來的環境變數（例如桌面版的 ANTHROPIC_BASE_URL、CLAUDE_CODE_* 功能旗標）會讓隔離環境多出工具或改走別的端點
HOST_PREFIXES = ("CLAUDE_CODE_", "CLAUDECODE", "CLAUDE_AGENT_SDK", "CLAUDE_EFFORT", "CLAUDE_PID", "CLAUDE_PREVIEW",
                 "ANTHROPIC_", "CODEX_", "OPENAI_", "MCP_CONNECTION", "MCP_SERVER_CONNECTION", "AI_AGENT", "LEVEL_ZERO")


def clean_env(keep=(), **extra):
    env = {k: v for k, v in os.environ.items() if k in keep or not k.upper().startswith(HOST_PREFIXES)}
    env.update(extra)
    return env


def eval_root():
    root = os.environ.get("OMNIKIT_EVAL_ROOT") or (os.environ.get("SystemDrive", "C:") + "\\omnikit-eval")
    return Path(root)


def outside_profile(path):
    home = Path.home().resolve()
    path = Path(path).resolve()
    return home != path and home not in path.parents


# ---------- 工具來源 ----------

def find_skills(src):
    """所有 SKILL.md 所在的資料夾；內容完全一樣的只留一份。"""
    seen, out = set(), []
    for skill_md in sorted(src.rglob("SKILL.md")):
        if any(part in (".git", "node_modules") for part in skill_md.parts):
            continue
        digest = layer0.tree_digest(skill_md.parent)
        if digest not in seen:
            seen.add(digest)
            out.append(skill_md.parent)
    return out


def plugin_dir(src):
    return src if (src / ".claude-plugin" / "plugin.json").exists() else None


def executable_reasons(src, skills, mcp):
    """會在本機執行程式的線索：skill 裡的腳本、plugin 的 hook、MCP。"""
    reasons = []
    scripts = sorted({p.suffix for d in skills for p in d.rglob("*") if p.is_file() and p.suffix.lower() in EXEC_SUFFIXES})
    if scripts:
        reasons.append(f"skill 附可執行檔（{'、'.join(scripts)}）")
    plug = plugin_dir(src) if src else None
    if plug:
        manifest = json.loads((plug / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        if (plug / "hooks" / "hooks.json").exists() or manifest.get("hooks"):
            reasons.append("plugin 有 hook")
        if (plug / ".mcp.json").exists() or manifest.get("mcpServers"):
            reasons.append("plugin 有 MCP")
    if mcp:
        reasons.append(f"MCP：{'、'.join(mcp)}")
    return reasons


def parse_mcp(items):
    out = {}
    for item in items or []:
        name, _, spec = item.partition("=")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            sys.exit(f"MCP 名稱只能用英數、_ 與 -：{name}")
        cfg = json.loads(spec)
        out[name] = {"command": cfg["command"], "args": cfg.get("args", []), **({"env": cfg["env"]} if cfg.get("env") else {})}
    return out


def windows_command(cfg):
    """Windows 上 npx 這類 .cmd 要經 cmd /c 執行（addendum A.3）。"""
    if os.name == "nt" and cfg["command"] in ("npx", "npm", "pnpm", "yarn", "bunx"):
        return {**cfg, "command": "cmd", "args": ["/c", cfg["command"], *cfg["args"]]}
    return cfg


def fetch_source(args, run_dir):
    """回傳（來源資料夾, 來源紀錄）。repo 用淺層 clone，記下實際的 commit。"""
    if args.path:
        return Path(args.path).resolve(), {"path": Path(args.path).name}
    if not args.repo:
        return None, {}
    repo, _, ref = args.repo.partition("@")
    dest = run_dir / "src"
    cmd = ["git", "-c", "core.longpaths=true", "clone", "--depth", "1", "--quiet"] + (["--branch", ref] if ref else [])
    subprocess.run(cmd + [f"https://github.com/{repo}.git", str(dest)], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return dest, {"repo": repo, "sha": sha}


# ---------- 隔離的設定資料夾 ----------

def reset_home(home, keep):
    """清空隔離的設定資料夾，只留登入檔（不開啟、不讀取）；.claude.json 拿掉 MCP 與專案紀錄。"""
    home.mkdir(parents=True, exist_ok=True)
    for entry in home.iterdir():
        if entry.name in keep:
            continue
        rmtree(entry) if entry.is_dir() else entry.unlink()
    state = home / ".claude.json"
    if ".claude.json" in keep and state.exists():
        doc = json.loads(state.read_text(encoding="utf-8"))
        for key in ("mcpServers", "projects"):
            doc.pop(key, None)
        state.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def user_agent_skills():
    root = Path.home() / ".agents" / "skills"
    return sorted(p / "SKILL.md" for p in root.iterdir() if (p / "SKILL.md").exists()) if root.is_dir() else []


def toml_str(text):
    return json.dumps(str(text), ensure_ascii=False)


def codex_config(base_url, mcp, disable):
    lines = [f"openai_base_url = {toml_str(base_url)}"] if base_url else []
    for path in disable:
        lines += ["", "[[skills.config]]", f"path = {toml_str(path)}", "enabled = false"]
    for name, cfg in mcp.items():
        cfg = windows_command(cfg)
        lines += ["", f"[mcp_servers.{name}]", f"command = {toml_str(cfg['command'])}",
                  f"args = [{', '.join(toml_str(a) for a in cfg['args'])}]"]
        if cfg.get("env"):
            lines += [f"[mcp_servers.{name}.env]"] + [f"{k} = {toml_str(v)}" for k, v in cfg["env"].items()]
    return "\n".join(lines) + "\n"


def user_codex_base_url():
    """只讀使用者 config.toml 的 openai_base_url 這一行（這台經本機 proxy）；其他設定不帶進隔離環境。"""
    path = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    if not path.exists():
        return None
    m = re.search(r'(?m)^openai_base_url\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


def install(home_claude, home_codex, skills, mcp, base_url, disable):
    """skill 複製進兩邊的 skills/；Codex 的 MCP 與停用清單寫進 config.toml；Claude 的 MCP 另給 --mcp-config。"""
    for home in (home_claude, home_codex):
        if home is None:
            continue
        for skill in skills:
            dest = home / "skills" / skill.name
            if dest.exists():
                dest = home / "skills" / f"{skill.parent.name}-{skill.name}"
            n = 2
            while dest.exists():  # 三個以上同名（例如 claude-mem、ECC）
                dest = home / "skills" / f"{skill.parent.name}-{skill.name}-{n}"
                n += 1
            shutil.copytree(skill, dest)
    if home_codex is not None:
        (home_codex / "config.toml").write_text(codex_config(base_url, mcp, disable), encoding="utf-8")
    if home_claude is not None and mcp:
        path = home_claude / "omnikit-mcp.json"
        path.write_text(json.dumps({"mcpServers": {n: windows_command(c) for n, c in mcp.items()}}), encoding="utf-8")
        return path
    return None


# ---------- 零 token 量 context ----------

class Capture:
    """本機攔截伺服器：記下每個 POST 的內容，回 400 讓 CLI 結束。"""

    def __init__(self):
        bodies = self.bodies = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("content-length") or 0))
                bodies.append((self.path, body))
                self.send_response(400)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"type":"error","error":{"type":"invalid_request_error","message":"omnikit capture"}}')

            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def log_message(self, *_):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def largest(self, suffix):
        sizes = [b for p, b in self.bodies if p.split("?")[0].endswith(suffix)]
        return max(sizes, key=len) if sizes else None

    def close(self):
        self.server.shutdown()


def est_tokens(text):
    """粗估：ASCII 每 4 字元 1 token，其他每字 1 token。"""
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return round(ascii_chars / 4 + (len(text) - ascii_chars))


def measure_once(agent, home, cwd, capture, extra_args, base_url_for_codex):
    if agent == "claude":
        env = clean_env(CLAUDE_CONFIG_DIR=str(home), ANTHROPIC_BASE_URL=capture.url, ANTHROPIC_API_KEY=DUMMY_KEY)
        cmd = [shutil.which("claude"), "-p", "Reply OK", "--output-format", "json", "--max-turns", "1", *extra_args]
        suffix = "/v1/messages"
    else:
        env = clean_env(CODEX_HOME=str(home), OPENAI_API_KEY=DUMMY_KEY)
        cmd = [shutil.which("codex"), "exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral", "Reply OK"]
        suffix = "/responses"
    capture.bodies.clear()
    subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=180, stdin=subprocess.DEVNULL)
    body = capture.largest(suffix)
    return body.decode("utf-8", "replace") if body else None


def measure_context(name, skills, plugin, mcp, run_dir, agents, allow_exec):
    """回傳 {agent: {baseline_bytes, with_bytes, delta_bytes, delta_tokens_est, mentions}}。"""
    cwd = fixture_repo()  # 在 git repo 裡量：跟實際使用一樣（不是 git repo 時 Claude 會直接列出更多工具）
    capture = Capture()
    out = {}
    try:
        for agent in agents:
            if not shutil.which(agent):
                out[agent] = {"error": f"找不到 {agent}"}
                continue
            sizes = {}
            for label, with_tool in (("baseline", False), ("with", True)):
                home = run_dir / f"ctx-{agent}-{label}"
                reset_home(home, set())
                use_mcp = mcp if (with_tool and allow_exec) else {}
                mcp_file = install(home if agent == "claude" else None, home if agent == "codex" else None,
                                   skills if with_tool else [], use_mcp, capture.url + "/v1", user_agent_skills())
                extra = []
                if agent == "claude" and with_tool and plugin and allow_exec:
                    extra += ["--plugin-dir", str(plugin)]
                if mcp_file:
                    extra += ["--mcp-config", str(mcp_file), "--strict-mcp-config"]
                sizes[label] = measure_once(agent, home, cwd, capture, extra, capture.url)
            if not sizes["baseline"] or not sizes["with"]:
                out[agent] = {"error": "沒攔截到請求"}
                continue
            names = [s.name for s in skills] + list(mcp if allow_exec else [])
            out[agent] = {
                "baseline_bytes": len(sizes["baseline"].encode()), "with_bytes": len(sizes["with"].encode()),
                "delta_bytes": len(sizes["with"].encode()) - len(sizes["baseline"].encode()),
                "delta_tokens_est": est_tokens(sizes["with"]) - est_tokens(sizes["baseline"]),
                "mentions": sorted({n for n in names if n in sizes["with"]}),
            }
    finally:
        capture.close()
    return out


# ---------- 真實非互動執行 ----------

def parse_claude(lines, skills, servers):
    invoked, evidence, result = False, [], None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") != "tool_use":
                    continue
                name, text = block.get("name", ""), json.dumps(block.get("input") or {}, ensure_ascii=False)
                hit = ((name == "Skill" and any(s in text for s in skills))
                       or any(name.startswith(f"mcp__{srv}__") for srv in servers)
                       or (name == "Read" and "SKILL.md" in text and any(s in text for s in skills)))
                if hit:
                    invoked = True
                    evidence.append(f"{name} {text[:120]}")
        elif event.get("type") == "result":
            result = event
    ok = bool(result) and result.get("subtype") == "success" and not result.get("is_error")
    return {"noninteractive": ok, "invoked": invoked, "evidence": evidence[:5],
            "usage": _cheap.normalize_usage("claude", (result or {}).get("usage")),
            "error": None if ok else str((result or {}).get("result") or (result or {}).get("terminal_reason") or "沒有結果")[:300]}


def parse_codex(lines, skills, servers):
    invoked, evidence, usage, error, done = False, [], None, None, False
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item") or {}
        if event.get("type") == "item.completed":
            text = json.dumps(item, ensure_ascii=False)
            if (item.get("type") == "command_execution" and "SKILL.md" in text and any(s in text for s in skills)) \
                    or (item.get("type") == "mcp_tool_call" and item.get("server") in servers):
                invoked = True
                evidence.append(text[:160])
        elif event.get("type") == "turn.completed":
            usage, done = event.get("usage"), True
        elif event.get("type") in ("turn.failed", "error"):
            error = (event.get("error") or {}).get("message") or event.get("message")
    return {"noninteractive": done, "invoked": invoked, "evidence": evidence[:5],
            "usage": _cheap.normalize_usage("codex", usage), "error": None if done else (error or "沒有完成")[:300]}


def auth_state():
    root = eval_root()
    claude = "env" if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN") else ("home" if (root / "claude-home" / ".credentials.json").exists() else None)
    codex = "home" if (root / "codex-home" / "auth.json").exists() else None
    return {"claude": claude, "codex": codex}


def fixture_repo():
    """沒指定專案時用的小型 git repo（放在使用者資料夾外）。"""
    repo = eval_root() / "fixture"
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "README.md").write_text("# OmniKit smoke fixture\n\nA tiny project for smoke tests.\n", encoding="utf-8")
        git = ["git", "-C", str(repo), "-c", "user.name=omnikit-smoke", "-c", "user.email=omnikit-smoke@localhost"]
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "fixture"], check=True)
    return repo


def worktree(project, dest):
    subprocess.run(["git", "-C", str(project), "worktree", "add", "--detach", str(dest), "HEAD"], check=True, capture_output=True)


def drop_worktree(project, dest):
    subprocess.run(["git", "-C", str(project), "worktree", "remove", "--force", str(dest)], capture_output=True)


def real_run(name, skills, plugin, mcp, run_dir, agents, prompt, project, model, allow_exec):
    auth = auth_state()
    out = {}
    skill_names = [s.name for s in skills]
    for agent in agents:
        if not auth[agent]:
            out[agent] = {"noninteractive": None, "invoked": None, "error": "隔離的設定資料夾沒有登入（smoke.py login）"}
            continue
        wt = run_dir / f"wt-{agent}"
        worktree(project, wt)
        try:
            if agent == "claude":
                home = run_dir / "claude" if auth["claude"] == "env" else eval_root() / "claude-home"
                reset_home(home, set() if auth["claude"] == "env" else CLAUDE_KEEP)
                mcp_file = install(home, None, skills, mcp if allow_exec else {}, None, [])
                cmd = [shutil.which("claude"), "-p", prompt, "--output-format", "stream-json", "--verbose", "--max-turns", "6",
                       "--model", model or "haiku", "--no-session-persistence",
                       "--allowedTools", ",".join(["Read", "Grep", "Glob", "Skill"] + [f"mcp__{n}" for n in (mcp if allow_exec else {})])]
                if plugin and allow_exec:
                    cmd += ["--plugin-dir", str(plugin)]
                if mcp_file:
                    cmd += ["--mcp-config", str(mcp_file), "--strict-mcp-config"]
                env = clean_env(keep=("CLAUDE_CODE_OAUTH_TOKEN",), CLAUDE_CONFIG_DIR=str(home))
                proc = subprocess.run(cmd, cwd=wt, env=env, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=900, stdin=subprocess.DEVNULL)
                out[agent] = parse_claude(proc.stdout.splitlines(), skill_names, list(mcp))
            else:
                home = eval_root() / "codex-home"
                reset_home(home, CODEX_KEEP)
                install(None, home, skills, mcp if allow_exec else {}, user_codex_base_url(), user_agent_skills())
                cmd = [shutil.which("codex"), "exec", "--json", "--skip-git-repo-check", "--sandbox", "read-only", "--ephemeral",
                       "-C", str(wt)] + (["-m", model] if model else []) + [prompt]
                env = clean_env(CODEX_HOME=str(home))
                proc = subprocess.run(cmd, cwd=wt, env=env, capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=900, stdin=subprocess.DEVNULL)
                out[agent] = parse_codex(proc.stdout.splitlines(), skill_names, list(mcp))
        except subprocess.TimeoutExpired:
            out[agent] = {"noninteractive": False, "invoked": None, "error": "超過 900 秒"}
        finally:
            drop_worktree(project, wt)
    return out


# ---------- Windows Sandbox ----------

HANDSHAKE = r"""
// MCP stdio 交握：initialize → tools/list，記下工具數與工具定義大小。只在 Windows Sandbox 裡執行。
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
const [cfgPath, outPath] = process.argv.slice(2);
const servers = JSON.parse(readFileSync(cfgPath, "utf8"));
const results = {};
for (const [name, cfg] of Object.entries(servers)) {
  results[name] = await new Promise((resolve) => {
    const child = spawn(cfg.command, cfg.args || [], { env: { ...process.env, ...(cfg.env || {}) }, stdio: ["pipe", "pipe", "pipe"] });
    let buf = "", stderr = "";
    const done = (r) => { clearTimeout(timer); try { child.kill(); } catch {} resolve(r); };
    const timer = setTimeout(() => done({ ok: false, error: "timeout", stderr: stderr.slice(-400) }), 240000);
    const send = (m) => child.stdin.write(JSON.stringify(m) + "\n");
    child.on("error", (e) => done({ ok: false, error: String(e) }));
    child.on("exit", (code) => done({ ok: false, error: `exit ${code}`, stderr: stderr.slice(-400) }));
    child.stderr.on("data", (d) => { stderr += d; });
    child.stdout.on("data", (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
        if (!line) continue;
        let msg; try { msg = JSON.parse(line); } catch { continue; }
        if (msg.id === 1) { send({ jsonrpc: "2.0", method: "notifications/initialized" }); send({ jsonrpc: "2.0", id: 2, method: "tools/list" }); }
        if (msg.id === 2) {
          const tools = (msg.result && msg.result.tools) || [];
          done({ ok: !msg.error, tools: tools.length, bytes: Buffer.byteLength(JSON.stringify(tools)), names: tools.map((t) => t.name).slice(0, 50), error: msg.error && msg.error.message });
        }
      }
    });
    send({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "omnikit-smoke", version: "0" } } });
  });
}
writeFileSync(outPath, JSON.stringify(results));
"""


def sandbox_script(installs, mcp, need_node):
    """沙箱裡執行的 PowerShell：需要時下載固定版本的 Node 並核對 SHA256，再跑安裝指令與 MCP 交握，結果寫 result.json。"""
    node_dir = f"C:\\node\\node-{NODE['version']}-win-x64"
    lines = [
        "$ErrorActionPreference = 'Continue'",
        f"$dir = '{SANDBOX_DIR}'",
        "$steps = @()",
        "function Run-Step($name, $command) {",
        "  $log = Join-Path $dir ('step-' + $steps.Count + '.log')",
        "  $start = Get-Date",
        "  & cmd.exe /d /c $command *> $log",
        "  $code = $LASTEXITCODE",
        # 不用 Get-Content：PS 5.1 讀回的字串帶 PSDrive、PSProvider，ConvertTo-Json 會整串展開成約 47 MB
        "  $tail = if (Test-Path $log) { [System.IO.File]::ReadAllText($log) } else { $null }",
        "  if ($tail -and $tail.Length -gt 600) { $tail = $tail.Substring($tail.Length - 600) }",
        "  $script:steps += [ordered]@{ name = $name; ok = ($code -eq 0); code = $code; seconds = [int]((Get-Date) - $start).TotalSeconds; tail = $tail }",
        "}",
    ]
    if need_node:
        lines += [
            f"$zip = 'C:\\node.zip'; $url = 'https://nodejs.org/dist/{NODE['version']}/node-{NODE['version']}-win-x64.zip'",
            "try {",
            "  Invoke-WebRequest $url -OutFile $zip -UseBasicParsing",
            f"  if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne '{NODE['sha256']}') {{ throw 'Node SHA256 不符' }}",
            "  Expand-Archive $zip C:\\node -Force",
            f"  $env:Path = '{node_dir};' + $env:Path",
            "  $steps += [ordered]@{ name = 'node " + NODE["version"] + "'; ok = $true; code = 0 }",
            "} catch { $steps += [ordered]@{ name = 'node'; ok = $false; code = -1; tail = \"$_\" } }",
        ]
    for cmd in installs:
        lines.append(f"Run-Step {json.dumps('install: ' + cmd)} {json.dumps(cmd)}")
    if mcp:
        lines += [
            "$hs = Join-Path $dir 'handshake.json'",
            "Run-Step 'mcp handshake' ('node \"' + (Join-Path $dir 'handshake.mjs') + '\" \"' + (Join-Path $dir 'mcp.json') + '\" \"' + $hs + '\"')",
            "$mcp = if (Test-Path $hs) { Get-Content $hs -Raw | ConvertFrom-Json } else { $null }",
        ]
    else:
        lines.append("$mcp = $null")
    lines += [
        "[ordered]@{ steps = $steps; mcp = $mcp; os = [Environment]::OSVersion.VersionString } | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $dir 'result.json')",
    ]
    return "\r\n".join(lines) + "\r\n"


def wsb(*args, timeout=600):
    proc = subprocess.run(["wsb", *args, "--raw"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    try:
        return json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        return {"raw": proc.stdout[-300:], "stderr": proc.stderr[-300:]}


def run_sandbox(folder, script_name="run.ps1", timeout=1800):
    """啟動沙箱（不開視窗）、共用資料夾、以 System 執行腳本、讀 result.json、一定會關掉沙箱。"""
    if not shutil.which("wsb"):
        return {"error": "找不到 wsb（Windows Sandbox CLI）"}
    started = time.monotonic()
    box = wsb("start", timeout=180).get("Id")
    if not box:
        return {"error": "Windows Sandbox 啟動失敗"}
    try:
        wsb("share", "--id", box, "-f", str(folder), "-s", SANDBOX_DIR, "-w", timeout=120)
        command = f"powershell -NoProfile -ExecutionPolicy Bypass -File {SANDBOX_DIR}\\{script_name}"
        exec_result = wsb("exec", "--id", box, "-c", command, "-r", "System", timeout=timeout)
    finally:
        wsb("stop", "--id", box, timeout=120)
    result_path = folder / "result.json"
    doc = json.loads(result_path.read_text(encoding="utf-8-sig")) if result_path.exists() else {"error": "沒有 result.json"}
    doc["exit_code"] = exec_result.get("ExitCode")
    doc["seconds"] = int(time.monotonic() - started)
    return doc


def sandbox_check(src, installs, mcp, run_dir):
    folder = run_dir / "sbx"
    folder.mkdir(parents=True, exist_ok=True)
    if src:
        shutil.copytree(src, folder / "src", ignore=shutil.ignore_patterns(".git"))
    need_node = bool(mcp) or any(re.match(r"\s*(npm|npx|node|pnpm|yarn)\b", c) for c in installs)
    (folder / "run.ps1").write_text(sandbox_script(installs, mcp, need_node), encoding="utf-8-sig")
    if mcp:
        (folder / "handshake.mjs").write_text(HANDSHAKE, encoding="utf-8")
        (folder / "mcp.json").write_text(json.dumps({n: windows_command(c) for n, c in mcp.items()}), encoding="utf-8")
    return run_sandbox(folder)


# ---------- 環境檢查 ----------

def env_check(live=False):
    root = eval_root()
    out = {"eval_root_outside_profile": outside_profile(root), "agents": {}, "auth": auth_state()}
    for agent in ("claude", "codex"):
        exe = shutil.which(agent)
        version = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout.strip() if exe else None
        out["agents"][agent] = version
    out["windows_sandbox"] = {"cli": bool(shutil.which("wsb"))}
    if live and shutil.which("wsb"):
        with tempfile.TemporaryDirectory(prefix="okwsb-", dir=root if root.exists() else None) as tmp:
            folder = Path(tmp)
            (folder / "probe.ps1").write_text(
                f"[ordered]@{{ steps = @(); git = [bool](Get-Command git -EA SilentlyContinue); node = [bool](Get-Command node -EA SilentlyContinue); "
                f"github = try {{ (Invoke-WebRequest https://api.github.com -UseBasicParsing).StatusCode }} catch {{ 0 }} }} | ConvertTo-Json | "
                f"Set-Content -Encoding utf8 '{SANDBOX_DIR}\\result.json'\r\n", encoding="utf-8-sig")
            out["windows_sandbox"]["live"] = run_sandbox(folder, "probe.ps1", timeout=300)
    wsl = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, env={**os.environ, "WSL_UTF8": "1"}) if shutil.which("wsl.exe") else None
    distros = [d.strip() for d in (wsl.stdout.decode("utf-8", "replace") if wsl else "").splitlines() if d.strip()] if wsl and wsl.returncode == 0 else []
    out["wsl"] = {"installed": bool(shutil.which("wsl.exe")), "distros": distros}
    return out


def env_lines(doc):
    a = doc["auth"]
    live = doc["windows_sandbox"].get("live") or {}
    return [
        f"- 執行目錄在使用者資料夾外：{'是' if doc['eval_root_outside_profile'] else '否（Claude 會讀到 ~/.claude/CLAUDE.md，請設 OMNIKIT_EVAL_ROOT）'}（{eval_root()}）",
        f"- Claude Code：{doc['agents']['claude'] or '沒裝'}；隔離登入：{a['claude'] or '沒有（smoke.py login）'}",
        f"- Codex：{doc['agents']['codex'] or '沒裝'}；隔離登入：{a['codex'] or '沒有（smoke.py login）'}",
        f"- Windows Sandbox：{'有 wsb' if doc['windows_sandbox']['cli'] else '沒有 wsb'}"
        + (f"；實測 {live.get('seconds')} 秒、GitHub {live.get('github')}、沙箱裡有 git {live.get('git')}、node {live.get('node')}" if live else ""),
        f"- WSL2：{('發行版 ' + '、'.join(doc['wsl']['distros'])) if doc['wsl']['distros'] else ('已啟用但沒有發行版' if doc['wsl']['installed'] else '沒有')}",
    ]


def login_lines():
    root = eval_root()
    return [
        "隔離的設定資料夾要各登入一次（登入資訊只留在這些資料夾，OmniKit 不讀不傳）：",
        f"- Claude（二選一）：執行 `claude setup-token`，把產生的 token 設成使用者環境變數 CLAUDE_CODE_OAUTH_TOKEN；"
        f"或在 PowerShell 執行 `$env:CLAUDE_CONFIG_DIR='{root}\\claude-home'; claude`，在裡面打 /login。",
        f"- Codex：在 PowerShell 執行 `$env:CODEX_HOME='{root}\\codex-home'; codex login`。",
        "- 登入完跑 smoke.py env 確認。",
    ]


# ---------- 結果 ----------

def save_result(tool_id, kind, payload, source, reasons, today):
    path = FUNNEL / "smoke" / f"{tool_id}.json"
    doc = (json.loads(path.read_text(encoding="utf-8")) if path.exists() else None) or {"tool": tool_id}
    doc.update({"date": today.isoformat(), "source": source, "executable": reasons})
    doc[kind] = payload
    batch0.dump_json(path, doc)
    return doc


def summarize(doc):
    lines = [f"# 煙霧測試：{doc['tool']}（{doc['date']}）"]
    if doc.get("executable"):
        lines.append(f"- 會執行程式：{'、'.join(doc['executable'])}")
    if doc.get("install") is not None:
        lines.append(f"- 裝得起來：{'是' if doc['install'].get('ok') else '否'}（{doc['install'].get('detail', '')}）")
    for agent, r in (doc.get("context") or {}).items():
        if not isinstance(r, dict):
            lines.append(f"  - {r}")
            continue
        lines.append(f"- {agent} 每回合 context：" + (r.get("error") or f"多 {r['delta_bytes']:,} bytes，約 {r['delta_tokens_est']:,} token（基準 {r['baseline_bytes']:,} bytes）"))
    for agent, r in (doc.get("run") or {}).items():
        state = {True: "是", False: "否", None: "未知"}
        lines.append(f"- {agent} 非互動：{state[r.get('noninteractive')]}；被叫用：{state[r.get('invoked')]}" + (f"；{r['error']}" if r.get("error") else ""))
    box = doc.get("sandbox")
    if box:
        steps = "、".join(f"{s['name']} {'✓' if s.get('ok') else '✗'}" for s in box.get("steps") or [])
        lines.append(f"- Windows Sandbox（{box.get('seconds')} 秒）：{steps or box.get('error')}")
        for name, r in (box.get("mcp") or {}).items():
            lines.append(f"  - MCP {name}：" + (f"{r.get('tools')} 個工具、定義 {r.get('bytes'):,} bytes" if r.get("ok") else f"失敗（{r.get('error')}）"))
    return lines


# ---------- 自我測試 ----------

def selftest():
    import jsonschema
    import urllib.request

    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    tmp = Path(tempfile.mkdtemp(prefix="oksmoke-"))
    try:
        src = tmp / "src"
        for d in ("skills/a", "skills/b", "copies/a"):
            (src / d).mkdir(parents=True)
            (src / d / "SKILL.md").write_text("---\nname: a\n---\nbody\n" if d.endswith("a") else "---\nname: b\n---\n", encoding="utf-8")
        (src / "skills" / "b" / "run.py").write_text("print(1)", encoding="utf-8")
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "plugin.json").write_text('{"name": "p"}', encoding="utf-8")
        (src / "hooks").mkdir()
        (src / "hooks" / "hooks.json").write_text("{}", encoding="utf-8")
        skills = find_skills(src)
        check("找 skill：內容一樣的複本只留一份", [s.relative_to(src).as_posix() for s in skills] == ["copies/a", "skills/b"])
        mcp = parse_mcp(['dt={"command": "npx", "args": ["-y", "chrome-devtools-mcp@0.9.0"]}'])
        reasons = executable_reasons(src, skills, mcp)
        check("會執行程式的線索：腳本、hook、MCP", len(reasons) == 3 and "plugin 有 hook" in reasons)

        cfg = codex_config("http://127.0.0.1:9/v1", mcp, [Path("C:/Users/x/.agents/skills/okx/SKILL.md")])
        check("Codex 隔離設定：停用使用者層級 skill、npx 經 cmd /c", "[[skills.config]]" in cfg and "enabled = false" in cfg
              and ('command = "cmd"' in cfg if os.name == "nt" else 'command = "npx"' in cfg) and "[mcp_servers.dt]" in cfg)

        home = tmp / "home"
        (home / "skills" / "x").mkdir(parents=True)
        (home / ".credentials.json").write_text("{}", encoding="utf-8")
        (home / ".claude.json").write_text(json.dumps({"oauthAccount": {"a": 1}, "mcpServers": {"x": {}}, "projects": {}}), encoding="utf-8")
        (home / "settings.json").write_text("{}", encoding="utf-8")
        reset_home(home, CLAUDE_KEEP)
        state = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
        check("重設隔離資料夾：只留登入檔，.claude.json 拿掉 MCP 與專案", sorted(p.name for p in home.iterdir()) == [".claude.json", ".credentials.json"]
              and state == {"oauthAccount": {"a": 1}})

        c_home, x_home = tmp / "c", tmp / "x"
        c_home.mkdir()
        x_home.mkdir()
        mcp_file = install(c_home, x_home, skills, mcp, "http://127.0.0.1:9/v1", [])
        check("安裝：skill 複製到兩邊、同名的加上層資料夾名稱", (c_home / "skills" / "a" / "SKILL.md").exists()
              and (x_home / "skills" / "b" / "run.py").exists() and (x_home / "config.toml").exists())
        check("Claude 的 MCP 寫成 --mcp-config 檔", json.loads(mcp_file.read_text(encoding="utf-8"))["mcpServers"]["dt"]["args"][-1] == "chrome-devtools-mcp@0.9.0")
        trio = []
        for i in range(3):
            d = tmp / "trio" / f"p{i}" / "skills" / "same"
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: same\n---\n{i}", encoding="utf-8")
            trio.append(d)
        (tmp / "t").mkdir()
        install(tmp / "t", None, trio, {}, None, [])
        check("安裝：三個以上同名的 skill 也不會撞名", len(list((tmp / "t" / "skills").iterdir())) == 3)

        claude_lines = [
            json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "p:a"}}]}}),
            json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__dt__navigate", "input": {}}]}}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False,
                        "usage": {"input_tokens": 5, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 900, "output_tokens": 40}}),
        ]
        r = parse_claude(claude_lines, ["a", "b"], ["dt"])
        check("Claude 串流：Skill 與 MCP 都算被叫用、非互動成功、用量", r["invoked"] and r["noninteractive"] and len(r["evidence"]) == 2
              and r["usage"] == {"input": 1005, "cached": 900, "output": 40})
        r = parse_claude([json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "max turns"})], ["a"], [])
        check("Claude 串流：沒叫用、非互動失敗會記原因", not r["invoked"] and r["noninteractive"] is False and "max turns" in r["error"])
        codex_lines = [
            json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "Get-Content C:/h/skills/a/SKILL.md"}}),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 70000, "cached_input_tokens": 60000, "output_tokens": 30}}),
        ]
        r = parse_codex(codex_lines, ["a"], [])
        check("Codex 事件：讀 SKILL.md 算被叫用、turn.completed 算非互動成功", r["invoked"] and r["noninteractive"] and r["usage"]["cached"] == 60000)
        r = parse_codex([json.dumps({"type": "turn.failed", "error": {"message": "401"}})], ["a"], [])
        check("Codex 事件：失敗記原因", r["noninteractive"] is False and r["error"] == "401")

        cap = Capture()
        try:
            for size in (10, 300):
                req = urllib.request.Request(cap.url + "/v1/messages?beta=true", data=b"x" * size, method="POST")
                try:
                    urllib.request.urlopen(req, timeout=5)
                except Exception:  # 400 是預期的
                    pass
            check("攔截伺服器：記下請求、取最大的一份、回 400", len(cap.largest("/v1/messages")) == 300 and cap.largest("/responses") is None)
        finally:
            cap.close()
        check("token 粗估：ASCII 每 4 字 1 token、中文每字 1 token", est_tokens("abcd" * 10) == 10 and est_tokens("中文") == 2)

        script = sandbox_script(["npm i -g agent-browser@0.41.2"], mcp, True)
        check("沙箱腳本：Node 固定版本並核對 SHA256、跑安裝與 MCP 交握", NODE["sha256"] in script and "Get-FileHash" in script
              and "npm i -g agent-browser@0.41.2" in script and "mcp handshake" in script and "result.json" in script)
        check("沙箱腳本：步驟紀錄讀成純字串（Get-Content 讀回的帶 PS 屬性，會被 ConvertTo-Json 展開）",
              "ReadAllText($log)" in script and "Get-Content $log" not in script)
        check("沙箱腳本：沒有 MCP 也沒有 npm 時不下載 Node", "nodejs.org" not in sandbox_script(["pip install x==1.0"], {}, False))
        check("MCP 交握腳本：initialize 後送 tools/list", '"tools/list"' in HANDSHAKE.replace("'", '"') and "notifications/initialized" in HANDSHAKE)
        os.environ["CLAUDE_CODE_SELFTEST_FLAG"] = "1"
        env = clean_env(keep=("CLAUDE_CODE_SELFTEST_FLAG",), X="1")
        stripped = clean_env()
        del os.environ["CLAUDE_CODE_SELFTEST_FLAG"]
        check("子行程的環境：清掉外層 agent 的變數，指定的保留", env.get("CLAUDE_CODE_SELFTEST_FLAG") == "1" and env["X"] == "1"
              and "CLAUDE_CODE_SELFTEST_FLAG" not in stripped and "PATH" in {k.upper() for k in stripped})
        check("執行目錄要在使用者資料夾外", not outside_profile(Path.home() / "x") and outside_profile(Path(Path.home().anchor) / "omnikit-eval"))

        doc = {"tool": "t", "date": "2026-11-05", "source": {"repo": "o/r", "sha": "a" * 40}, "executable": reasons,
               "install": {"ok": True, "detail": "2 個 skill"},
               "context": {"claude": {"baseline_bytes": 96988, "with_bytes": 98000, "delta_bytes": 1012, "delta_tokens_est": 250, "mentions": ["a"]}},
               "run": {"codex": {"noninteractive": True, "invoked": True, "evidence": [], "usage": None, "error": None}},
               "sandbox": {"steps": [{"name": "install: x", "ok": True, "code": 0}], "mcp": {"dt": {"ok": True, "tools": 26, "bytes": 18000}}, "seconds": 120}}
        schema = json.loads((CONTRACTS / "smoke.schema.json").read_text(encoding="utf-8"))
        try:
            jsonschema.validate(doc, schema)
            check("結果符合 contracts/smoke.schema.json", True)
        except jsonschema.ValidationError as e:
            check(f"結果符合 contracts/smoke.schema.json（{e.message[:80]}）", False)
        bad = {**doc, "sandbox": {"steps": [{"name": "install: x", "ok": True, "code": 0, "tail": {"value": "ok", "PSDrive": {}}}]}}
        check("契約擋下被展開成物件的步驟輸出", not jsonschema.validators.validator_for(schema)(schema).is_valid(bad))
        text = "\n".join(summarize(doc))
        check("摘要列出四件事", "裝得起來：是" in text and "約 250 token" in text and "非互動：是；被叫用：是" in text and "26 個工具" in text)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"smoke 自我測試：{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


# ---------- 指令 ----------

def add_source(p):
    p.add_argument("id", help="工具卡 id")
    p.add_argument("--repo", help="owner/repo[@ref]")
    p.add_argument("--path", help="本機資料夾")
    p.add_argument("--mcp", action="append", help='名稱={"command": …, "args": […]}，可重複')


def main():
    parser = argparse.ArgumentParser(description="第 1c 層煙霧測試")
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    e = sub.add_parser("env", help="檢查隔離方式")
    e.add_argument("--live", action="store_true", help="實際啟動一次 Windows Sandbox")
    sub.add_parser("login", help="印出隔離設定資料夾的登入方式")
    c = sub.add_parser("context", help="不花 token 量 context 成本")
    add_source(c)
    c.add_argument("--agents", default="claude,codex")
    c.add_argument("--reviewed", action="store_true", help="程式碼已審查：連 hook 與 MCP 一起在本機量")
    r = sub.add_parser("run", help="真實非互動執行")
    add_source(r)
    r.add_argument("--prompt", required=True, help="縮小版的情境")
    r.add_argument("--agents", default="claude,codex")
    r.add_argument("--project", help="跑在哪個 git repo 的 worktree（預設是小型 fixture）")
    r.add_argument("--model", help="預設 Claude 用 haiku、Codex 用它的預設")
    r.add_argument("--reviewed", action="store_true", help="程式碼已審查：允許在本機啟動 hook 與 MCP")
    s = sub.add_parser("sandbox", help="在 Windows Sandbox 安裝與 MCP 交握")
    add_source(s)
    s.add_argument("--install", action="append", default=[], help="沙箱裡要跑的安裝指令（要釘版本），可重複")
    args = parser.parse_args()
    _omnikit.utf8_stdout()
    if args.selftest:
        return selftest()
    today = date.today()
    if args.cmd == "env":
        doc = env_check(args.live)
        print("\n".join(env_lines(doc)))
        return 0
    if args.cmd == "login":
        print("\n".join(login_lines()))
        return 0
    if args.cmd not in ("context", "run", "sandbox"):
        parser.print_help()
        return 0
    root = eval_root()
    if not outside_profile(root):
        sys.exit(f"{root} 在使用者資料夾底下，Claude 會讀到 ~/.claude/CLAUDE.md；請把 OMNIKIT_EVAL_ROOT 設到使用者資料夾外")
    run_dir = root / "runs" / f"{args.id}-{datetime.now():%Y%m%d-%H%M%S}"
    run_dir.mkdir(parents=True)
    try:
        try:
            src, source = fetch_source(args, run_dir)
        except subprocess.CalledProcessError as err:
            doc = save_result(args.id, "install", {"ok": False, "detail": f"clone 失敗：{(err.stderr or b'').decode(errors='replace')[-200:]}"}, {}, [], today)
            print("\n".join(summarize(doc)))
            return 1
        mcp = parse_mcp(args.mcp)
        skills = find_skills(src) if src else []
        plugin = plugin_dir(src) if src else None
        reasons = executable_reasons(src, skills, mcp) if src or mcp else []
        risky = any("hook" in r or "MCP" in r for r in reasons)
        allow_exec = getattr(args, "reviewed", False) or not risky
        install_info = {"ok": bool(skills or plugin or mcp), "detail": f"{len(skills)} 個 skill" + ("、plugin" if plugin else "") + (f"、MCP {len(mcp)} 個" if mcp else "")}
        if args.cmd == "context":
            payload = measure_context(args.id, skills, plugin, mcp, run_dir, args.agents.split(","), allow_exec)
            if not allow_exec:
                payload["note"] = "有 hook 或 MCP、還沒審查：只量 skill；MCP 的工具定義用 sandbox 指令量"
            doc = save_result(args.id, "context", payload, source, reasons, today)
            doc = save_result(args.id, "install", install_info, source, reasons, today)
        elif args.cmd == "run":
            if risky and not args.reviewed:
                sys.exit("這個工具有 hook 或 MCP：先做程式碼審查（FR-24），審查過再加 --reviewed；或先用 sandbox 指令")
            project = Path(args.project).resolve() if args.project else fixture_repo()
            payload = real_run(args.id, skills, plugin, mcp, run_dir, args.agents.split(","), args.prompt, project, args.model, allow_exec)
            doc = save_result(args.id, "run", payload, source, reasons, today)
            doc = save_result(args.id, "install", install_info, source, reasons, today)
        else:
            payload = sandbox_check(src, args.install, mcp, run_dir)
            doc = save_result(args.id, "sandbox", payload, source, reasons, today)
            ok = not payload.get("error") and all(s.get("ok") for s in payload.get("steps") or []) \
                and all(r.get("ok") for r in (payload.get("mcp") or {}).values())
            doc = save_result(args.id, "install", {"ok": ok, "detail": "Windows Sandbox：" + ("全部成功" if ok else "有步驟失敗")}, source, reasons, today)
        print("\n".join(summarize(doc)))
        return 0
    finally:
        rmtree(run_dir)


if __name__ == "__main__":
    sys.exit(main())
