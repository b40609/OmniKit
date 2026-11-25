"""確定性護欄 hook（engine/scripts/harness_hooks.py）的 pytest：不誤擋正常開發指令、Stop 不無限迴圈。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "scripts"))
import harness_hooks as hh  # noqa: E402


def pre(tool, **inp):
    return hh.handle({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": inp}, env={})


def is_deny(r):
    return bool(r) and r["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("cmd", [
    "git commit --no-verify -m x", "git commit -n -m x", "git commit -anm wip",
    "git -c core.hooksPath=/dev/null commit -m x", "HUSKY=0 git commit -m x", "git push --no-verify",
])
def test_bypass_blocked(cmd):
    assert is_deny(pre("Bash", command=cmd))


@pytest.mark.parametrize("cmd", [
    "git commit -m 'docs: explain --no-verify and -n'", "git commit -am msg", "git log -n 3", "git status",
    "uv run pytest -q", "npm run build", "git commit --amend --no-edit", "ruff check .", "git push origin main",
    "ls -la .env", "cp .env.example .env", "cat README.md",
])
def test_normal_commands_allowed(cmd):
    assert pre("Bash", command=cmd) is None


@pytest.mark.parametrize("path,blocked", [
    (".env", True), ("app/.env.production", True), ("certs/server.pem", True), ("x.secret.key", True),
    ("cookies.txt", True), ("cookies-chrome.txt", True),
    (".env.example", False), (".env.sample", False), ("src/env.py", False), ("README.md", False),
])
def test_secret_read(path, blocked):
    assert is_deny(pre("Read", file_path=path)) is blocked


def test_stop_never_loops(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIKIT_STATE", str(tmp_path))
    py = tmp_path / "a.py"
    py.write_text("import os\n", encoding="utf-8")
    bad = lambda cmd: (1, f"{cmd[-1]}:1:8: F401 `os` imported but unused\n")  # noqa: E731
    hh.handle({"hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "t",
               "tool_input": {"file_path": str(py)}}, runner=bad, env={})
    first = hh.handle({"hook_event_name": "Stop", "session_id": "t"}, runner=bad, env={})
    second = hh.handle({"hook_event_name": "Stop", "session_id": "t", "stop_hook_active": True}, runner=bad, env={})
    assert first and first["decision"] == "block"
    assert second is None


def test_cli_silent_on_garbage():
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "scripts" / "harness_hooks.py")],
                       input=b"\xff\xfe not json", capture_output=True)
    assert r.returncode == 0 and r.stdout == b""


def test_selftest_passes():
    r = subprocess.run([sys.executable, str(ROOT / "engine" / "scripts" / "harness_hooks.py"), "--selftest"],
                       capture_output=True)
    assert r.returncode == 0, r.stdout.decode("utf-8", "replace")[-2000:]


def test_antigravity_camelcase(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIKIT_STATE", str(tmp_path))
    agy_pre = {"hookEventName": "PreToolUse", "toolCall": {"name": "run_command", "args": {"CommandLine": "git commit -n -m x"}}}
    res_pre = hh.handle(agy_pre, env={})
    assert res_pre and res_pre.get("decision") == "deny" and "hookSpecificOutput" not in res_pre
    agy_ok = {"hookEventName": "PreToolUse", "toolCall": {"name": "edit_file", "args": {"TargetFile": str(tmp_path / "a.ts")}}}
    assert hh.handle(agy_ok, env={}) == {"decision": "allow"}
    py = tmp_path / "b.py"
    py.write_text("import os\n", encoding="utf-8")

    def bad(cmd):
        return 1, f"{cmd[-1]}:1:8: F401 `os` imported but unused\n"
    post = {"hookEventName": "PostToolUse", "sessionId": "ag", "toolCall": {"name": "write_file", "args": {"TargetFile": str(py)}}}
    assert hh.handle(post, runner=bad, env={}) == {}
    assert hh.handle({"hookEventName": "Stop", "sessionId": "ag"}, runner=bad, env={})["decision"] == "continue"
    assert hh.handle({"hookEventName": "Stop", "sessionId": "ag", "continuationActive": True}, runner=bad, env={}) in ({}, None)
