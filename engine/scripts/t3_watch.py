# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SessionStart hook（Claude Code 與 Codex）：開對話時 T3 Code 的 MCP 埠連不上，就先試著把 T3 叫起來，並提醒 agent。

為什麼要有這支（2026-11-21 查證，Claude Code 2.1.329、T3 0.1.12-nightly.20261120.4994）：
t3 MCP 是 user scope 的 http server（http://127.0.0.1:3773/mcp），伺服器跑在 T3 桌面程式裡。T3 nightly 自動更新
或重啟的那幾十秒內開的對話，會回報 `t3 (ECONNREFUSED)`，之後整段對話都沒有 T3 工具；user-config 的 MCP server
agent 不能自己重撥，只能使用者在該對話打 /mcp 按 Reconnect。`t3` CLI 每次都重新連線，不受影響。

做的事：
1. 讀 ~/.t3/userdata/server-runtime.json 拿 port（沒有或壞掉就用 3773），測 127.0.0.1 的 TCP 連線。
2. 連得上：什麼都不輸出。
3. 連不上：T3 程式沒在跑、也不是正在自動更新（%LOCALAPPDATA%\\t3code-updater\\installer.exe 3 分鐘內有寫入），
   就在背景啟動它（最小化、不搶焦點），最多等約 20 秒直到埠開。
4. 只要一開始連不上，就用 hookSpecificOutput.additionalContext 告訴 agent：t3 MCP 這次可能沒接上，
   請使用者 /mcp 重連，在那之前改用 `t3 thread` CLI。

全部時間壓在 25 秒內（hook 設定 30 秒，見 claude_allow.HOOKS）；任何錯誤都安靜結束（exit 0），不能讓對話開不起來。

註冊：claude_allow.py（Claude 每個設定目錄的 settings.json）與 codex_hooks.py（~/.codex/config.toml）。
自我測試：uv run engine/scripts/t3_watch.py --selftest
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_PORT = 3773
WAIT = 20  # 啟動後最多等幾秒
BUDGET = 25  # 整支最多跑幾秒（hook 設定 30 秒）
UPDATING = 180  # installer.exe 幾秒內有寫入就當成正在自動更新，不要搶著開
EXES = ("T3 Code (Nightly).exe", "T3 Code.exe")
BREAKAWAY = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB：hook 結束後 T3 要繼續跑
DETACHED = 0x00000008  # DETACHED_PROCESS

MESSAGE = ("OmniKit：開這段對話時 T3 Code 的 MCP（127.0.0.1:{port}）連不上{state}，所以 t3 MCP 這次可能沒接上"
           "（工具清單沒有 mcp__t3__*，或 /mcp 顯示 t3 ECONNREFUSED、failed）。這代表 T3 當時在重啟、自動更新或沒開，"
           "不是沒裝，也不是派不了。處理：1) 請使用者在本對話打 /mcp，選 t3 按 Reconnect；"
           "2) 在那之前要開 T3 對話、派子任務就改用 `t3 thread` CLI（PowerShell 打 t3，Git Bash 打 t3.cmd，"
           "見 omnikit-dispatch 的 t3_cli 管道），不要回答派不了。")


def runtime_port(home: Path) -> int:
    try:
        port = json.loads((home / ".t3" / "userdata" / "server-runtime.json").read_text(encoding="utf-8")).get("port")
        return port if isinstance(port, int) and 0 < port < 65536 else DEFAULT_PORT
    except (OSError, ValueError, AttributeError):
        return DEFAULT_PORT


def is_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def find_exe(environ) -> Path | None:
    base = Path(environ.get("LOCALAPPDATA", "")) / "Programs" / "t3code"
    return next((base / n for n in EXES if (base / n).is_file()), None) if environ.get("LOCALAPPDATA") else None


def is_running(name: str) -> bool:
    if os.name != "nt":
        return False
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH", "/FO", "CSV"], capture_output=True,
                         timeout=5, creationflags=subprocess.CREATE_NO_WINDOW).stdout.decode("utf-8", "replace")
    return f'"{name.lower()}"' in out.lower()


def updating(environ, now: float) -> bool:
    try:
        f = Path(environ["LOCALAPPDATA"]) / "t3code-updater" / "installer.exe"
        return now - f.stat().st_mtime < UPDATING
    except (KeyError, OSError):
        return False


def launch(exe: Path):
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7  # SW_SHOWMINNOACTIVE：最小化、不搶焦點
    opts = {"cwd": str(exe.parent), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL, "startupinfo": si, "close_fds": True}
    flags = DETACHED | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([str(exe)], creationflags=flags | BREAKAWAY, **opts)
    except OSError:  # 所在的 job 不允許脫離：照樣啟動
        subprocess.Popen([str(exe)], creationflags=flags, **opts)


def check(home: Path = Path.home(), environ=None, probe=is_open, running=is_running, start=launch,
          sleep=time.sleep, clock=time.monotonic, now=None):
    """回傳要給 agent 的 additionalContext；連得上就是 None。"""
    environ = os.environ if environ is None else environ
    begin = clock()
    port = runtime_port(home)
    if probe(port):
        return None
    state = ""
    exe = find_exe(environ)
    if os.name != "nt" and start is launch:
        state = "（不是 Windows，沒有自動啟動）"
    elif exe is None:
        state = "（找不到 T3 Code 的程式，沒有自動啟動）"
    elif updating(environ, time.time() if now is None else now):
        state = "（T3 正在自動更新，沒有搶著開，更新完會自己重開）"
    elif running(exe.name):
        state = "（T3 程式在跑，可能正在重啟）"
    else:
        start(exe)
        deadline = begin + min(WAIT, BUDGET)
        while clock() < deadline:
            sleep(1)
            if probe(port):
                state = "（T3 原本沒開，已在背景啟動，現在埠已開）"
                break
        else:
            state = f"（T3 原本沒開，已在背景啟動，等了 {WAIT} 秒埠還沒開）"
    return MESSAGE.format(port=port, state=state)


def output(msg: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}},
                      ensure_ascii=False)


def selftest() -> int:
    fails = []

    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as t:
        home, local = Path(t) / "home", Path(t) / "local"
        rt = home / ".t3" / "userdata" / "server-runtime.json"
        exe = local / "Programs" / "t3code" / "T3 Code (Nightly).exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        env = {"LOCALAPPDATA": str(local)}
        started, probed = [], []

        # 1. 埠開著：用真的 socket 聽一個埠，runtime 檔寫那個埠
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        live = srv.getsockname()[1]
        rt.parent.mkdir(parents=True)
        rt.write_text(json.dumps({"pid": 1, "port": live}), encoding="utf-8")
        msg = check(home, env, running=lambda n: False, start=started.append)
        ok(f"埠開著（{live}）：不輸出、不啟動", msg is None and not started)
        srv.close()

        # 2. 埠關著（剛關掉的埠）、T3 沒在跑：啟動它，等到埠開
        state = {"t": 0.0, "up": False}

        def fake_start(e):
            started.append(e)
            state["up"] = True

        def fake_probe(p):
            probed.append(p)
            return state["up"] and state["t"] >= 3

        def fake_sleep(s):
            state["t"] += s

        closed_msg = check(home, env, probe=is_open, running=lambda n: False, start=lambda e: None,
                           sleep=fake_sleep, clock=lambda: state["t"])
        ok(f"埠關著（真的連 {live} 連不上）：輸出提醒 /mcp 重連與 t3 CLI", closed_msg is not None
           and "/mcp" in closed_msg and "t3.cmd" in closed_msg and str(live) in closed_msg and "等了 20 秒" in closed_msg)
        state["t"] = 0.0
        msg = check(home, env, probe=fake_probe, running=lambda n: False, start=fake_start,
                    sleep=fake_sleep, clock=lambda: state["t"])
        ok("埠關著、T3 沒在跑：背景啟動，埠開了還是提醒（MCP 已錯過）", started == [exe] and msg is not None
           and "已在背景啟動，現在埠已開" in msg and state["t"] <= WAIT)
        started.clear()
        msg = check(home, env, probe=lambda p: False, running=lambda n: True, start=started.append)
        ok("埠關著、T3 在跑（重啟中）：不重複啟動，提醒", not started and "可能正在重啟" in msg)
        inst = local / "t3code-updater" / "installer.exe"
        inst.parent.mkdir(parents=True)
        inst.write_bytes(b"")
        msg = check(home, env, probe=lambda p: False, running=lambda n: False, start=started.append)
        ok("埠關著、installer.exe 剛寫入（自動更新中）：不搶著開，提醒", not started and "自動更新" in msg)
        msg = check(home, env, probe=lambda p: False, running=lambda n: False, start=started.append,
                    now=time.time() + UPDATING + 10)
        ok("installer.exe 是很久以前的：照常啟動", started == [exe] and msg is not None)
        started.clear()
        msg = check(home, {}, probe=lambda p: False, running=lambda n: False, start=started.append)
        ok("找不到 T3 程式：不啟動，提醒", not started and "找不到 T3 Code" in msg)

        # 3. runtime 檔不存在、壞掉、port 不合理：用 3773
        probed.clear()
        rt.unlink()
        check(home, env, probe=lambda p: probed.append(p) or True)
        rt.write_text("{壞掉", encoding="utf-8")
        check(home, env, probe=lambda p: probed.append(p) or True)
        rt.write_text(json.dumps({"port": "x"}), encoding="utf-8")
        check(home, env, probe=lambda p: probed.append(p) or True)
        ok("runtime 檔不存在、壞掉、port 不是數字：都用 3773", probed == [DEFAULT_PORT] * 3)
        rt.unlink()
        msg = check(home, env, probe=lambda p: False, running=lambda n: True, start=started.append)
        ok("runtime 檔不存在且 3773 連不上：提醒寫 3773", "127.0.0.1:3773" in msg)

        out = json.loads(output("x"))
        ok("輸出格式：hookSpecificOutput.additionalContext", out["hookSpecificOutput"] == {
            "hookEventName": "SessionStart", "additionalContext": "x"})

        # 主程式：錯誤一律安靜結束
        def boom(*a, **k):
            raise RuntimeError("壞掉")
        ok("check 丟例外：main 安靜結束", run(lambda: boom()) == (0, ""))
    print("t3_watch selftest", "FAIL" if fails else "OK")
    return 1 if fails else 0


def run(fn=check):
    """跑一次 hook；回傳（exit code, 輸出）。"""
    try:
        msg = fn()
        return 0, output(msg) if msg else ""
    except Exception:  # noqa: BLE001  檢查壞掉不能干擾對話
        return 0, ""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if "--selftest" in sys.argv:
        return selftest()
    try:
        sys.stdin.read()  # hook 輸入用不到，讀掉就好
    except Exception:  # noqa: BLE001
        pass
    code, text = run()
    if text:
        print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
