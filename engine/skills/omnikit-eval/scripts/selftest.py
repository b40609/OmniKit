# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""評估 skill 的離線自我測試：不連網，預期值從名冊本身推導，名冊改了也不會誤報。CI 也會跑。

用法：uv run scripts/selftest.py
"""
import io
import json
import os
import sys
import tempfile
from contextlib import contextmanager, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import _omnikit
import layer0

HERE = Path(__file__).parent


def run(script, *args):
    """在同一個 Python 裡執行另一支腳本的 main()，回傳它印出的文字。"""
    module = __import__(script)
    sys.argv = [script, *args]
    out = io.StringIO()
    with redirect_stdout(out):
        module.main()
    return out.getvalue()


class FakeProc:
    def __init__(self, stdout="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, "", returncode


@contextmanager
def patched_env(**values):
    """暫時設定環境變數（值是 None 代表拿掉），結束後還原。"""
    saved = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _guard(fn):
    """修正前呼叫可能直接丟例外（參數不存在），要算失敗而不是讓整個自我測試中斷。"""
    try:
        return bool(fn())
    except Exception as err:  # noqa: BLE001
        print(f"  （例外：{type(err).__name__}: {str(err)[:120]}）")
        return False


def isolation_checks():
    """評測隔離（2026-11-27 跨家複審 P2-4）：只檢查組出來的參數與環境變數，subprocess.run 一律 mock，不呼叫模型。"""
    import _cheap
    import layer2
    import smoke

    out = []
    calls = []

    def fake_run(cmd, **kw):
        calls.append((list(cmd), kw))
        if "-p" in cmd and "--json-schema" in cmd:
            return FakeProc(json.dumps({"structured_output": {"ok": 1}, "usage": {}}))
        if "exec" in cmd:
            return FakeProc(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "{\"ok\": 1}"}}))
        return FakeProc()

    def cheap_cmd(agent):
        calls.clear()
        with mock.patch.object(_cheap.shutil, "which", lambda name: f"/bin/{name}"), \
                mock.patch.object(_cheap.subprocess, "run", fake_run), \
                mock.patch.object(_cheap, "user_codex_base_url", lambda: "http://127.0.0.1:9/v1", create=True):
            _cheap.call("p", {"type": "object"}, agent=agent)
        return calls[-1]

    def claude_strict():
        cmd, _ = cheap_cmd("claude")
        i = cmd.index("--mcp-config")
        return "--strict-mcp-config" in cmd and json.loads(cmd[i + 1]) == {"mcpServers": {}} and "--setting-sources" in cmd
    out.append(("隔離：_cheap 的 claude -p 帶 --strict-mcp-config 與空的 --mcp-config", _guard(claude_strict)))

    def codex_ignore_user_config():
        cmd, kw = cheap_cmd("codex")
        overrides = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-c"]
        env = kw.get("env")
        untouched_home = env is None or env.get("CODEX_HOME") == os.environ.get("CODEX_HOME")
        return ("--ignore-user-config" in cmd and 'openai_base_url="http://127.0.0.1:9/v1"' in overrides and untouched_home)
    out.append(("隔離：_cheap 的 codex exec 不載入 user config.toml（--ignore-user-config），只補回 openai_base_url，不換 CODEX_HOME",
                _guard(codex_ignore_user_config)))

    with tempfile.TemporaryDirectory(prefix="okiso-") as td:
        td = Path(td)
        leaks = {"HERMES_HOME": "x", "GEMINI_CLI_HOME": "x", "CODEX_HOME": "x", "REASONIX_HOME": "x", "CURSOR_DATA_DIR": "x",
                 "CLINE_DIR": "x", "GOOSE_PATH_ROOT": "x", "OPENCODE_DB": "x", "DEJA_RECALL_GLOBAL": "1", "ENGRAM_DATA_DIR": "x",
                 "XDG_RUNTIME_DIR": "x", "CLAUDE_CONFIG_DIR": "x", "CLAUDE_CODE_SELFTEST_FLAG": "1", "JAVA_HOME": "keep"}

        def fake_home_env():
            fh = td / "fh"
            with patched_env(**leaks):
                env = smoke.clean_env(fake_home=fh, CODEX_HOME="iso")
            homes = all(Path(env[k]) == fh for k in ("USERPROFILE", "HOME"))
            dirs = all(fh in Path(env[k]).parents for k in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                                                             "XDG_STATE_HOME", "XDG_CACHE_HOME"))
            gone = not any(k in env for k in ("HERMES_HOME", "GEMINI_CLI_HOME", "REASONIX_HOME", "CURSOR_DATA_DIR", "CLINE_DIR",
                                              "GOOSE_PATH_ROOT", "OPENCODE_DB", "DEJA_RECALL_GLOBAL", "ENGRAM_DATA_DIR",
                                              "XDG_RUNTIME_DIR", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_SELFTEST_FLAG", "fake_home"))
            return homes and dirs and gone and env["CODEX_HOME"] == "iso" and env.get("JAVA_HOME") == "keep" \
                and "PATH" in {k.upper() for k in env} and (fh / "AppData" / "Roaming").is_dir()
        out.append(("隔離：clean_env(fake_home=…) 換掉家目錄類變數、清掉各 harness 的 *_HOME 與 DEJA_*／ENGRAM_*，指定的保留",
                    _guard(fake_home_env)))

        def default_on():
            return smoke.use_fake_home(None, ["MCP：x"]) and smoke.use_fake_home(None, ["skill 附可執行檔（.py）"]) \
                and not smoke.use_fake_home(None, []) and not smoke.use_fake_home(False, ["MCP：x"]) and smoke.use_fake_home(True, [])
        out.append(("隔離：可執行檔與 MCP 類的評測預設開假家目錄，可用 --no-fake-home 關掉", _guard(default_on)))

        def smoke_measure_passes_env():
            calls.clear()

            class Cap:
                url, bodies = "http://127.0.0.1:9", []

                def largest(self, _suffix):
                    return b"x"
            with mock.patch.object(smoke.subprocess, "run", fake_run), patched_env(HERMES_HOME="x"):
                smoke.measure_once("claude", td / "h", td, Cap(), [], None, fake_home=td / "fh2")
            env = calls[-1][1]["env"]
            return Path(env["USERPROFILE"]) == td / "fh2" and "HERMES_HOME" not in env
        out.append(("隔離：smoke 量 context 時子行程走假家目錄", _guard(smoke_measure_passes_env)))

        def layer2_exec_env():
            calls.clear()
            work = td / "work"
            work.mkdir(exist_ok=True)
            (work / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
            with mock.patch.object(layer2.subprocess, "run", fake_run), \
                    patched_env(OMNIKIT_EVAL_ROOT=str(td / "root"), CLAUDE_CODE_OAUTH_TOKEN=None, **leaks):
                layer2.exec_claude("q", {"id": "a", "tools": []}, "m", work, work / "mcp.json")
            env = calls[-1][1].get("env")
            return env is not None and work in Path(env["USERPROFILE"]).parents and "HERMES_HOME" not in env \
                and "DEJA_RECALL_GLOBAL" not in env and "CLAUDE_CODE_SELFTEST_FLAG" not in env and env.get("CLAUDE_CONFIG_DIR")
        out.append(("隔離：layer2 受測 claude -p 傳 env=，走假家目錄並清掉外層變數", _guard(layer2_exec_env)))

        def layer2_mcp_children():
            folder = td / "2026-01-01-x-Y1"
            folder.mkdir(exist_ok=True)
            seen = {}

            def fake_exec(prompt, arm, model, workdir, mcp_path):
                seen["mcp"] = json.loads(Path(mcp_path).read_text(encoding="utf-8"))
                seen["work"] = Path(workdir)
                return 0, [], ""
            spec = {"task": "{question}", "questions": {"Q1": "q"}, "model": "m"}
            arm = {"id": "c", "mcp": {"deja": {"command": "deja", "args": ["mcp"], "env": {"DEJA_INDEX": "i"}},
                                      "web": {"type": "http", "url": "https://example.com/mcp"}}}
            with patched_env(OMNIKIT_EVAL_ROOT=str(td / "root")):
                layer2.run_one(folder, spec, arm, "Q1", 1, executor=fake_exec)
            deja = seen["mcp"]["mcpServers"]["deja"]["env"]
            return seen["work"] in Path(deja["CLAUDE_CONFIG_DIR"]).parents and seen["work"] in Path(deja["CODEX_HOME"]).parents \
                and deja["DEJA_INDEX"] == "i" and "env" not in seen["mcp"]["mcpServers"]["web"]
        out.append(("隔離：layer2 受測 MCP 子行程的 CLAUDE_CONFIG_DIR／CODEX_HOME 指向假家目錄（spec 寫的 env 優先）",
                    _guard(layer2_mcp_children)))

        def judge_neutral():
            calls.clear()
            folder = td / "judge-folder"
            folder.mkdir(exist_ok=True)
            (folder / "judge-1.txt").write_text("材料", encoding="utf-8")
            spec = {"slot": "s", "scenario": "S1", "judge": {"provider": "p", "model": "m"}}

            def t3_run(cmd, **kw):
                calls.append((list(cmd), kw))
                if "start" in cmd:
                    return FakeProc(json.dumps({"threadId": "t1"}))
                if "show" in cmd:
                    return FakeProc(json.dumps({"messages": [{"text": "```json\n{\"pairs\": []}\n```"}], "thread": {}}))
                return FakeProc()
            with mock.patch.object(layer2.subprocess, "run", t3_run), mock.patch.object(layer2.shutil, "which", lambda n: "t3"), \
                    patched_env(OMNIKIT_EVAL_ROOT=str(td / "root")):
                layer2.judge_t3(folder, spec, 1, None)
            start = next(c for c, _ in calls if "start" in c)
            project = Path(start[start.index("start") + 1])
            return project != _omnikit.ROOT and _omnikit.ROOT not in project.parents and (td / "root") in project.parents \
                and "--worktree" not in start and smoke.outside_profile(project) is not None
        out.append(("隔離：layer2 的 T3 評審子對話開在中性目錄，不在 OmniKit repo、不開 worktree", _guard(judge_neutral)))
    return out


def main():
    _omnikit.utf8_stdout()
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    for text, want in [
        ("https://github.com/pbakaus/impeccable", "pbakaus/impeccable"),
        ("github.com/pbakaus/impeccable/tree/main/skill", "pbakaus/impeccable"),
        ("git@github.com:pbakaus/impeccable.git", "pbakaus/impeccable"),
        ("pbakaus/impeccable", "pbakaus/impeccable"),
        ("https://example.com/x", None),
    ]:
        check(f"解析網址 {text}", layer0.parse_repo(text) == want)

    roster = _omnikit.roster()
    tools = list(roster["tools"].values())
    ids = lambda hits: [h["id"] for h in hits]  # noqa: E731

    by_url = next(t for t in tools if layer0.repo_key(t.get("url")))
    check(f"名冊比對：用卡片網址找到 {by_url['id']}",
          by_url["id"] in ids(layer0.roster_matches(layer0.repo_key(by_url["url"]), roster)))
    for t in tools:
        source = next((s for s in (t.get("plugin") or {}).values() if isinstance(s, dict) and layer0.repo_key(s.get("url"))), None)
        if source:
            check(f"名冊比對：用 plugin 來源找到 {t['id']}",
                  t["id"] in ids(layer0.roster_matches(layer0.repo_key(source["url"]), roster)))
            break
    check("名冊比對：沒收錄的回空陣列", layer0.roster_matches("nobody/nothing-here", roster) == [])

    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    stale = {"archived": True, "pushed_at": "2024-01-01T00:00:00Z", "license": None, "stars": 3}
    check("門檻：封存是 fail，其他是 warn",
          {c["rule"]: c["level"] for c in layer0.thresholds(stale, now)} == {"archived": "fail", "stale": "warn", "license": "warn", "adoption": "warn"})
    fresh = {"archived": False, "pushed_at": "2026-11-01T00:00:00Z", "license": "MIT", "stars": 900}
    check("門檻：健康的 repo 沒有警告", layer0.thresholds(fresh, now) == [])

    merged = layer0.summarize([
        {"path": "a", "findings": [{"severity": "MEDIUM", "rule": "NET", "where": "x.js"}] * 3},
        {"path": "b", "findings": [{"severity": "MEDIUM", "rule": "NET", "where": "x.js"}] * 2},
    ])
    check("掃描摘要：同一份 skill 重複標記只算一份", [(f["skills"], f["hits"]) for f in merged] == [(2, 5)])

    import tempfile
    safe_scanner = lambda _p: {"max_severity": "SAFE", "findings": []}  # noqa: E731
    high_scanner = lambda _p: {"max_severity": "HIGH", "findings": [{"severity": "HIGH", "rule": "EXEC", "where": "SKILL.md"}]}  # noqa: E731
    with tempfile.TemporaryDirectory(prefix="okl0-badge-") as td:
        base = Path(td)
        pure = base / "pure"
        pure.mkdir()
        (pure / "SKILL.md").write_text("# Pure Skill\n", encoding="utf-8")
        check("安全徽章：純靜態 SKILL.md 判為 skill_scan_pass",
              layer0.scan_local(pure, scanner_fn=safe_scanner)["security_badge"] == "skill_scan_pass")
        exec_repo = base / "exec"
        exec_repo.mkdir()
        (exec_repo / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
        (exec_repo / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
        check("安全徽章：含 package.json 判為 executable_needs_review",
              layer0.scan_local(exec_repo, scanner_fn=safe_scanner)["security_badge"] == "executable_needs_review")
        empty_repo = base / "no-skill"
        empty_repo.mkdir()
        (empty_repo / "README.md").write_text("# No skill\n", encoding="utf-8")
        check("安全徽章：掃出 0 個 SKILL.md 判為 executable_needs_review",
              layer0.scan_local(empty_repo, scanner_fn=safe_scanner)["security_badge"] == "executable_needs_review")
        check("安全徽章：檢出高風險規則判為 risk_flagged",
              layer0.scan_local(pure, scanner_fn=high_scanner)["security_badge"] == "risk_flagged")

    for slot in roster["slots"]:
        expected = {t["id"] for t in tools if slot["id"] in t["slots"] and t["status"] in ("default", "trial")}
        if expected:
            got = {t["id"] for t in json.loads(run("peers", slot["id"]))["incumbents"]}
            check(f"配對：{slot['id']} 槽位的現任", got == expected)
            break

    trial = next((t for t in tools if t["status"] == "trial"), None)
    if trial:
        today = date.fromisoformat(trial["trial_until"]) - timedelta(days=6)
        digest = run("digest", "--today", today.isoformat(), "--no-usage")
        check(f"彙整：列出快到期的試用（{trial['name']}）", trial["name"] in digest and "剩 6 天" in digest)
    digest = run("digest")
    active_pending = any(s["focus"] == "active" and any(s["id"] in t["slots"] and t["status"] == "pending" for t in tools)
                         for s in roster["slots"])
    if active_pending:
        check("彙整：列出建議評估的槽位", "- [ ] " in digest)
    if (_omnikit.ROOT / "data" / "funnel" / "layer0.json").exists():
        check("彙整：有漏斗資料時列出第 0 層", "## 評估漏斗" in digest and "- 第 0 層（" in digest)
        check("彙整：證據卡與自動排程已停用，不再列出", "值得實測的外部證據" not in digest and "第 2 層排程提案" not in digest)
    if (_omnikit.ROOT / "data" / "funnel" / "layer2-todo.md").exists():
        check("彙整：列出手寫的第 2 層待測清單", "- 第 2 層待測清單（" in digest and "  - behavior-rules：" in digest)
    check("彙整：舊使用統計已移除，不再列出沒用到的 skill 與 plugin", "沒用到的 skill 與 plugin" not in digest)

    for name, ok in isolation_checks():
        check(name, ok)

    for path in sorted((HERE.parent / "contracts").glob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
            check(f"契約是合法 JSON：{path.name}", True)
        except json.JSONDecodeError:
            check(f"契約是合法 JSON：{path.name}", False)

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"自我測試：{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
