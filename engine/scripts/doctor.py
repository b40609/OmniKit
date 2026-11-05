# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""doctor（FR-11）：逐項確認 OmniKit 寫進這台的設定都還在、跟記錄一樣，再用各 agent 自己的清單確認。
只讀不寫。查不到的標「未知」，不當作通過；有任何一項失敗就 exit 1。

寫入檢查（照 %LOCALAPPDATA%\\omnikit 的 agents.json 與 install-record.json）：
- 規則：~/.claude/CLAUDE.md、~/.codex/AGENTS.md、~/.gemini/GEMINI.md 的受管區塊，跟這台選的 profile 產生的一樣。
- skills：記錄裡的每個 skill 都在；連結指向 repo，複製品的雜湊跟 repo 一樣。
- MCP：帳本裡的每個 server 都在，OmniKit 管的欄位雜湊跟寫入時一樣（被改過就用 agents.py resolve 決定）。
- 免問核准與提醒 hook：記錄裡的 Claude 權限規則還在 ~/.claude/settings.json；兩邊的提醒 hook 有註冊。
agent 自己的清單：
- MCP：claude mcp list（會順便測連線）、codex mcp list --json、agy mcp list。
- skills：三個 agent 都沒有列出 skill 的指令，記「未知」；檔案在不在由寫入檢查確認。
安裝前檢查：加 --preflight 時一併跑 preflight.ps1（FR-35）。

用法：uv run engine/scripts/doctor.py [--preflight] [--json] [--no-lists]
      uv run engine/scripts/doctor.py --selftest
"""
import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agents  # noqa: E402
import claude_allow  # noqa: E402
import profiles  # noqa: E402

OK, FAIL, UNKNOWN = "ok", "fail", "unknown"
MARK = {OK: "✓", FAIL: "✗", UNKNOWN: "？"}
CODEX_NUDGE = re.compile(r"(?m)^command\s*=.*" + re.escape(claude_allow.NUDGE))


def row(area, agent, item, status, detail=""):
    return {"area": area, "agent": agent, "item": item, "status": status, "detail": detail}


def same_text(a, b):
    return a.replace("\r\n", "\n").strip() == b.replace("\r\n", "\n").strip()


# ---------- 寫入檢查 ----------

def check_rules(env, rec):
    try:
        name, _ = profiles.resolve(env.data, env.state)
    except SystemExit as e:
        return [row("規則", profiles.NAMES.get(a, a), "受管區塊", UNKNOWN, str(e.code)) for a in rec["agents"]]
    out = []
    for agent in rec["agents"]:
        path = env.rules[agent]
        want = profiles.claude_block(env.data, name) if agent == "claude-code" else profiles.content_block(profiles.compose(env.data, name))
        found = profiles.BLOCK.search(profiles.text(path)) if path.exists() else None
        label = profiles.NAMES[agent]
        if not found:
            out.append(row("規則", label, path.name, FAIL, f"{path} 沒有 OmniKit 受管區塊：重跑 install.ps1"))
        elif same_text(found.group(0), want):
            out.append(row("規則", label, path.name, OK, f"跟 profile {name} 一致"))
        else:
            out.append(row("規則", label, path.name, FAIL, f"受管區塊跟 profile {name} 不同（區塊裡被手改，或規則更新了還沒同步）"))
    return out


def check_skills(env, rec):
    out = []
    for key, names in rec["skills"].items():
        if key not in env.skill_dirs:
            continue
        folder, _ = env.skill_dirs[key]
        label = "Claude Code" if key == "claude-code" else "Codex、Antigravity"
        for name in names:
            dest, src = folder / name, env.skills_src / name
            if not agents.present(dest):
                out.append(row("skills", label, name, FAIL, f"{dest} 不見了：跑 agents.py sync"))
            elif not src.is_dir():
                out.append(row("skills", label, name, FAIL, "repo 已經沒有這個 skill：跑 agents.py sync 拿掉"))
            elif agents.is_link(dest):
                ok = agents.same_path(agents.link_target(dest), src)
                out.append(row("skills", label, name, OK if ok else FAIL, "連結指向 repo" if ok else "連結指到別的地方"))
            else:
                try:
                    recorded = json.loads((dest / agents.MARKER).read_text(encoding="utf-8")).get("hash")
                except (OSError, ValueError):
                    recorded = None
                ok = recorded == agents.tree_hash(src) and agents.tree_hash(dest) == agents.tree_hash(src)
                out.append(row("skills", label, name, OK if ok else FAIL, "複製品跟 repo 一樣" if ok else "複製品跟 repo 不同：跑 agents.py sync"))
    return out


def check_mcp(env, rec):
    out = []
    for agent, ledger in rec["mcp"].items():
        label = profiles.NAMES.get(agent, agent)
        try:
            current = agents.read_servers(env, agent)
        except SystemExit as e:
            out += [row("MCP", label, n, UNKNOWN, f"讀不到設定：{e.code}") for n in ledger]
            continue
        for name, entry in ledger.items():
            cur = current.get(name)
            if cur is None:
                out.append(row("MCP", label, name, FAIL, "設定裡沒有這個 server：跑 agents.py sync"))
            elif entry is None:
                out.append(row("MCP", label, name, UNKNOWN, "舊版記錄沒有雜湊，下次同步後才能比對"))
            elif agents.digest(cur, entry["keys"]) == entry["sha256"]:
                out.append(row("MCP", label, name, OK, "OmniKit 管的欄位跟寫入時一樣"))
            else:
                out.append(row("MCP", label, name, FAIL, f"OmniKit 管的欄位被改過：{agents.RESOLVE.replace('<名稱>', name)}"))
    return out


def check_harness(home, record_path):
    out = []
    record = claude_allow.load(record_path) if record_path.exists() else {}
    settings_path = home / ".claude" / "settings.json"
    try:
        settings = claude_allow.load(settings_path)
    except ValueError:
        return [row("權限", "Claude Code", "settings.json", UNKNOWN, f"{settings_path} 不是合法的 JSON")]
    allow = settings.get("permissions", {}).get("allow", [])
    for rule in record.get("claude_allow", []):
        out.append(row("權限", "Claude Code", rule, OK if rule in allow else FAIL,
                       "在 permissions.allow" if rule in allow else "記錄有、設定裡沒有：重跑 install.ps1"))
    if record.get("claude_hooks"):
        hooked = any(claude_allow.is_nudge(h) for g in settings.get("hooks", {}).get("Stop", []) for h in g.get("hooks", []))
        out.append(row("hook", "Claude Code", "開新對話提醒", OK if hooked else FAIL, "" if hooked else "Stop hook 不見了：重跑 install.ps1"))
    if record.get("codex_hooks"):
        toml = home / ".codex" / "config.toml"
        hooked = toml.exists() and bool(CODEX_NUDGE.search(toml.read_text(encoding="utf-8", errors="replace")))
        out.append(row("hook", "Codex", "開新對話提醒", OK if hooked else FAIL,
                       "要在 Codex 的 /hooks 信任後才會執行" if hooked else "config.toml 裡沒有：重跑 install.ps1"))
    return out


# ---------- agent 自己的清單 ----------

def run_cli(cmd, run=subprocess.run):
    try:
        r = run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    return (r.stdout, None) if r.returncode == 0 else (None, (r.stderr or r.stdout).strip()[-200:])


def claude_mcp_status(text, name):
    for line in text.splitlines():
        if line.startswith(f"{name}: "):
            tail = line.rsplit(" - ", 1)[-1]
            if "Connected" in tail:
                return OK, "已連線"
            if "Failed" in tail or "✗" in tail:
                return FAIL, "列在清單裡但連不上"
            return UNKNOWN, tail.strip()
    return FAIL, "claude mcp list 裡沒有"


def agent_lists(rec, run=subprocess.run, which=shutil.which):
    out = []
    wanted = {a: list(ledger) for a, ledger in rec["mcp"].items()}
    if wanted.get("claude-code"):
        exe = which("claude")
        text, err = run_cli([exe, "mcp", "list"], run) if exe else (None, "找不到 claude 指令")
        for name in wanted["claude-code"]:
            out.append(row("清單", "Claude Code", f"MCP {name}", *(claude_mcp_status(text, name) if text is not None else (UNKNOWN, err))))
    if wanted.get("codex"):
        exe = which("codex")
        text, err = run_cli([exe, "mcp", "list", "--json"], run) if exe else (None, "找不到 codex 指令")
        try:
            listed = {s["name"]: s for s in json.loads(text)} if text is not None else None
        except (ValueError, TypeError, KeyError):
            listed, err = None, "codex mcp list 的輸出看不懂"
        for name in wanted["codex"]:
            if listed is None:
                out.append(row("清單", "Codex", f"MCP {name}", UNKNOWN, err))
            elif name not in listed:
                out.append(row("清單", "Codex", f"MCP {name}", FAIL, "codex mcp list 裡沒有"))
            else:
                enabled = listed[name].get("enabled") is not False
                out.append(row("清單", "Codex", f"MCP {name}", OK if enabled else FAIL, "已啟用" if enabled else "被停用了"))
    if wanted.get("antigravity"):
        exe = which("agy")
        text, err = run_cli([exe, "mcp", "list"], run) if exe else (None, "找不到 agy 指令")
        # 表格：NAME TYPE STATUS COMMAND/URL
        listed = {parts[0]: parts[2] for line in (text or "").splitlines()[1:] if len(parts := line.split()) >= 3}
        for name in wanted["antigravity"]:
            if text is None:
                out.append(row("清單", "Antigravity", f"MCP {name}", UNKNOWN, err))
            elif name not in listed:
                out.append(row("清單", "Antigravity", f"MCP {name}", FAIL, "agy mcp list 裡沒有"))
            else:
                enabled = listed[name] == "enabled"
                out.append(row("清單", "Antigravity", f"MCP {name}", OK if enabled else FAIL, "已啟用" if enabled else f"狀態是 {listed[name]}"))
    for agent in rec["agents"]:
        out.append(row("清單", profiles.NAMES[agent], "skills", UNKNOWN, "沒有列出 skill 的指令；檔案在不在看上面的寫入檢查"))
    return out


def preflight(run=subprocess.run):
    script = Path(__file__).with_name("preflight.ps1")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        return [row("安裝前", "", "preflight.ps1", UNKNOWN, "找不到 PowerShell")]
    try:
        # 有項目不通過時 preflight.ps1 會 exit 1，但 JSON 還是印出來了，所以不看結束碼
        r = run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Json"], capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=180, stdin=subprocess.DEVNULL)
        text = r.stdout or ""
        items = json.loads(text[text.index("["):])
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        return [row("安裝前", "", "preflight.ps1", UNKNOWN, str(e)[:200])]
    return [row("安裝前", "", i["name"], OK if i["ok"] else FAIL) for i in items]


# ---------- 彙整 ----------

def installed_repo(env, rec):
    """安裝時接上的 repo：Claude 的 skill 連結指向 <repo>/engine/skills/<名稱>，複製品的 .omnikit.json 記了 repo。"""
    for key, names in rec["skills"].items():
        folder, _ = env.skill_dirs.get(key, (None, None))
        for name in names if folder else []:
            dest = folder / name
            try:
                if agents.is_link(dest):
                    return agents.link_target(dest).parents[2]
                return Path(json.loads((dest / agents.MARKER).read_text(encoding="utf-8"))["repo"])
            except (OSError, ValueError, KeyError, IndexError):
                continue
    return None


def collect(env, record_path, lists=True, pre=False, run=subprocess.run, which=shutil.which):
    rec = agents.load_record(env)
    if not rec["agents"]:
        return [row("記錄", "", "agents.json", FAIL, "這台還沒接上 OmniKit（沒有 agents.json）：跑 install.ps1")]
    rows = []
    repo = installed_repo(env, rec)
    if repo and not agents.same_path(repo, env.repo) and (repo / "data").is_dir():
        rows.append(row("記錄", "", "repo", OK, f"這台接的是 {repo}，以它為準比對（doctor 是從 {env.repo} 執行的）"))
        env = dataclasses.replace(env, repo=repo)
    rows += check_rules(env, rec) + check_skills(env, rec) + check_mcp(env, rec) + check_harness(env.home, record_path)
    if lists:
        rows += agent_lists(rec, run, which)
    if pre:
        rows += preflight(run)
    return rows


def report(rows):
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in (OK, FAIL, UNKNOWN)}
    lines = [f"# OmniKit doctor：通過 {counts[OK]}、失敗 {counts[FAIL]}、未知 {counts[UNKNOWN]}（未知不算通過）", ""]
    for r in rows:
        who = f"{r['agent']}／" if r["agent"] else ""
        lines.append(f"{MARK[r['status']]} {r['area']}：{who}{r['item']}" + (f"（{r['detail']}）" if r["detail"] else ""))
    return lines


# ---------- 自我測試 ----------

def selftest():
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        home, repo, state = tmp / "home", tmp / "repo", tmp / "state"

        def put(path, content):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        put(repo / "data" / "rules" / "baseline.md", "# 底線\n不碰金鑰\n")
        put(repo / "data" / "profiles" / "default" / "AGENTS.md", "# default\n保守\n")
        put(repo / "engine" / "skills" / "alpha" / "SKILL.md", "---\nname: alpha\n---\n")
        put(repo / "engine" / "skills" / "beta" / "SKILL.md", "---\nname: beta\n---\n")
        put(repo / "data" / "mcp" / "servers.yaml", "servers:\n  devtools:\n    command: cmd\n    args: [/c, node, x.js]\n"
                                                    "    targets: [claude, codex, antigravity]\n")
        (home / ".claude").mkdir(parents=True)
        (home / ".codex").mkdir(parents=True)
        (home / ".gemini" / "config").mkdir(parents=True)
        env = agents.Env(home=home, repo=repo, state=state, skillshare=tmp / "appdata" / "skillshare", which=lambda _: None)
        agents.connect(env, profile="default", agents=["claude-code", "codex", "antigravity"])
        record_path = state / "install-record.json"
        put(record_path, json.dumps({"claude_allow": ["mcp__devtools"], "claude_hooks": [claude_allow.NUDGE], "codex_hooks": ["x"]}))
        put(home / ".claude" / "settings.json", json.dumps({"permissions": {"allow": ["mcp__devtools"]},
                                                            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": f"uv run {claude_allow.NUDGE}"}]}]}}))
        toml = home / ".codex" / "config.toml"
        toml.write_text(toml.read_text(encoding="utf-8") + f'\n[[hooks.Stop]]\n[[hooks.Stop.hooks]]\ncommand = "& uv run {claude_allow.NUDGE}"\n', encoding="utf-8")

        claude_out = "Checking MCP server health…\n\ndevtools: cmd /c node x.js - ✓ Connected\nclaude.ai Gmail: https://x - ✓ Connected\n"
        codex_out = json.dumps([{"name": "devtools", "enabled": True}])
        agy_out = "NAME      TYPE   STATUS   COMMAND/URL\ndevtools  stdio  enabled  cmd /c node x.js\n"

        def fake_run(cmd, **kw):
            out = {"claude": claude_out, "codex": codex_out, "agy": agy_out}[cmd[0]]
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

        which = lambda name: name if name in ("claude", "codex", "agy") else None  # noqa: E731
        rows = collect(env, record_path, run=fake_run, which=which)
        status = {(r["area"], r["agent"], r["item"]): r["status"] for r in rows}
        check("剛接上：寫入檢查全部通過", all(r["status"] == OK for r in rows if r["area"] != "清單"))
        check("規則：三個 agent 的受管區塊都比對了", sum(1 for k in status if k[0] == "規則") == 3)
        check("skills：兩邊各 2 個", sum(1 for k in status if k[0] == "skills") == 4)
        check("MCP：三邊帳本都比對了", sum(1 for k in status if k[0] == "MCP" and status[k] == OK) == 3)
        check("權限與兩邊的提醒 hook", status[("權限", "Claude Code", "mcp__devtools")] == OK
              and status[("hook", "Claude Code", "開新對話提醒")] == OK and status[("hook", "Codex", "開新對話提醒")] == OK)
        check("agent 清單：Claude 已連線、Codex 與 Antigravity 已啟用", status[("清單", "Claude Code", "MCP devtools")] == OK
              and status[("清單", "Codex", "MCP devtools")] == OK and status[("清單", "Antigravity", "MCP devtools")] == OK)
        check("查不到的標未知：三個 agent 的 skill 清單", all(status[("清單", a, "skills")] == UNKNOWN
                                                        for a in ("Claude Code", "Codex", "Antigravity")))

        codex_md = home / ".codex" / "AGENTS.md"
        codex_md.write_text(codex_md.read_text(encoding="utf-8").replace("保守", "大膽"), encoding="utf-8")
        shutil.rmtree(home / ".agents" / "skills" / "beta")
        (home / ".agents" / "skills" / "alpha" / "SKILL.md").write_text("改過", encoding="utf-8")
        cj = home / ".claude.json"
        doc = json.loads(cj.read_text(encoding="utf-8"))
        doc["mcpServers"]["devtools"]["args"] = ["/c", "node", "evil.js"]
        cj.write_text(json.dumps(doc), encoding="utf-8")
        rec = agents.load_record(env)
        rec["mcp"]["antigravity"]["devtools"] = None
        agents.save_record(env, rec)
        (home / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": []}}), encoding="utf-8")
        claude_out = "devtools: cmd /c node evil.js - ✗ Failed to connect\n"
        codex_out = json.dumps([{"name": "devtools", "enabled": False}])
        agy_out = "NAME  TYPE  STATUS  COMMAND/URL\n"
        rows = collect(env, record_path, run=fake_run, which=which)
        status = {(r["area"], r["agent"], r["item"]): r["status"] for r in rows}
        check("規則區塊被手改：失敗", status[("規則", "Codex", "AGENTS.md")] == FAIL and status[("規則", "Claude Code", "CLAUDE.md")] == OK)
        check("skill 不見了、複製品被改：失敗", status[("skills", "Codex、Antigravity", "beta")] == FAIL
              and status[("skills", "Codex、Antigravity", "alpha")] == FAIL and status[("skills", "Claude Code", "alpha")] == OK)
        check("MCP 被改過：失敗，並提示 resolve", status[("MCP", "Claude Code", "devtools")] == FAIL
              and any("resolve devtools" in r["detail"] for r in rows))
        check("舊版沒有雜湊：未知", status[("MCP", "Antigravity", "devtools")] == UNKNOWN)
        check("權限規則與 hook 不見了：失敗", status[("權限", "Claude Code", "mcp__devtools")] == FAIL
              and status[("hook", "Claude Code", "開新對話提醒")] == FAIL)
        check("清單：連不上、被停用、不在清單裡都是失敗", status[("清單", "Claude Code", "MCP devtools")] == FAIL
              and status[("清單", "Codex", "MCP devtools")] == FAIL and status[("清單", "Antigravity", "MCP devtools")] == FAIL)
        nothing = collect(env, record_path, run=fake_run, which=lambda _: None)
        check("找不到 agent 指令：清單記未知", {r["status"] for r in nothing if r["area"] == "清單"} == {UNKNOWN})
        text = "\n".join(report(rows))
        check("報告列出通過、失敗、未知的數量", text.startswith("# OmniKit doctor：通過 ") and "✗ 規則：Codex／AGENTS.md" in text)
        empty = agents.Env(home=tmp / "nohome", repo=repo, state=tmp / "nostate", skillshare=tmp / "x")
        other = tmp / "other-checkout"
        shutil.copytree(repo, other)
        moved = collect(dataclasses.replace(env, repo=other), record_path, lists=False)
        check("從別的 checkout 執行：以安裝時的 repo 為準", moved[0]["item"] == "repo"
              and next(r for r in moved if r["area"] == "skills" and r["agent"] == "Claude Code")["status"] == OK)
        check("還沒接上：直接說要跑 install.ps1", collect(empty, tmp / "none.json", lists=False)[0]["status"] == FAIL)

        def fake_pwsh(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, stdout='[{"name":"git","ok":true},{"name":"npm","ok":false}]', stderr="")
        pre = preflight(fake_pwsh) if (shutil.which("pwsh") or shutil.which("powershell")) else [row("安裝前", "", "git", OK), row("安裝前", "", "npm", FAIL)]
        check("安裝前檢查：沒通過時也讀得到結果", [(r["item"], r["status"]) for r in pre] == [("git", OK), ("npm", FAIL)])

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"doctor 自我測試：{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description="OmniKit doctor：確認寫入的設定還在、agent 看得到")
    parser.add_argument("--preflight", action="store_true", help="一併跑安裝前檢查（preflight.ps1）")
    parser.add_argument("--no-lists", action="store_true", help="不呼叫 agent 的清單指令（比較快）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.selftest:
        return selftest()
    env = agents.real_env()
    rows = collect(env, claude_allow.RECORD, lists=not args.no_lists, pre=args.preflight)
    print(json.dumps(rows, ensure_ascii=False, indent=1) if args.json else "\n".join(report(rows)))
    return 1 if any(r["status"] == FAIL for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
