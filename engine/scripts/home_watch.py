# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code 的 SessionStart hook：這台多了新的 agent 設定目錄，就在背景把 OmniKit 接上去。

安裝時（install.ps1 → agents.py connect）會接上當時找得到的每個設定目錄（homes.py）；之後才新增的帳號
（T3 Code 加一個 Claude 實例、開一個 ~/.claude-work、設了 CODEX_HOME）不會自己出現在記錄裡。
這支在每次開新對話時比對：homes.py 現在找得到的，跟 agents.json 記的 homes 不一樣，就在背景跑
agents.py sync（規則、skills、MCP、權限規則與 hook 都會接上），並用 systemMessage 說一聲。
新帳號自己的第一段對話讀不到（它的設定目錄這時才建立），下一段就讀得到。

不擋開新對話：只做比對（讀 agents.json、T3 設定、看幾個資料夾在不在），要接才另開背景行程。
同一組新目錄 6 小時內只試一次；背景同步的輸出留在 %LOCALAPPDATA%\\omnikit\\home_watch.log。
任何錯誤都安靜結束（exit 0），檢查壞掉不能干擾對話。還沒用 agents.py 接上過的（沒有 agents.json）不動。

註冊：claude_allow.py 寫進每個 Claude 設定目錄的 settings.json 的 hooks.SessionStart。
自我測試：uv run engine/scripts/home_watch.py --selftest
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import homes  # noqa: E402  同一個資料夾，沒有相依套件

ROOT = Path(__file__).resolve().parents[2]
STATE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "omnikit"
RETRY = 6 * 3600
BREAKAWAY = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB：hook 結束後背景同步還要跑完


def pending(state, found):
    """找得到、該接上，但 agents.json 還沒記的設定目錄。只看接上了的 agent；還沒接上過就不動。"""
    try:
        rec = json.loads((state / "agents.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    agents = rec.get("agents") if isinstance(rec, dict) else None
    if not isinstance(agents, list) or not agents:
        return []
    known = rec.get("homes")
    if not isinstance(known, list):  # 舊版記錄沒有 homes：其他 Claude 設定目錄當時有放 skills
        known = [k for k in rec.get("skills") or {} if "@" in k]
    known = {os.path.normcase(k) for k in known}
    return [f for f in found if f.writable and f.agent in agents and os.path.normcase(f.key) not in known]


def due(state, keys, now):
    """同一組新目錄 6 小時內只試一次（接不上的，不要每開一段對話就重跑）。"""
    try:
        last = json.loads((state / "home_watch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = {}
    return not (isinstance(last, dict) and last.get("keys") == sorted(keys) and now - last.get("at", 0) < RETRY)


def start_sync(state, popen=subprocess.Popen):
    """背景跑 agents.py sync，不等它；輸出接到 home_watch.log。"""
    uv = os.environ.get("UV") or shutil.which("uv") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "uv" / "uv.exe")
    cmd = [uv, "run", "--quiet", str(ROOT / "engine" / "scripts" / "agents.py"), "sync"]
    state.mkdir(parents=True, exist_ok=True)
    log = open(state / "home_watch.log", "ab")
    log.write(f"\n== {time.strftime('%Y-%m-%d %H:%M:%S')} agents.py sync（home_watch）\n".encode("utf-8"))
    log.flush()
    opts = {"cwd": str(ROOT), "stdin": subprocess.DEVNULL, "stdout": log, "stderr": subprocess.STDOUT}
    if os.name != "nt":
        return popen(cmd, start_new_session=True, **opts)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        return popen(cmd, creationflags=flags | BREAKAWAY, **opts)
    except OSError:  # 所在的 job 不允許脫離：照樣啟動
        return popen(cmd, creationflags=flags, **opts)


def check(state=STATE, home=homes.HOME, environ=None, now=None, popen=subprocess.Popen):
    """回傳要給使用者看的訊息；沒事就是 None。"""
    new = pending(state, homes.discover(home, environ))
    if not new:
        return None
    keys = sorted(f.key for f in new)
    now = time.time() if now is None else now
    if not due(state, keys, now):
        return None
    state.mkdir(parents=True, exist_ok=True)
    (state / "home_watch.json").write_text(json.dumps({"keys": keys, "at": now}, ensure_ascii=False), encoding="utf-8")
    start_sync(state, popen)
    where = "、".join(f"{f.path}（{f.source}）" for f in new)
    return (f"OmniKit：找到還沒接上的設定目錄 {where}，已在背景接上（規則、skills、MCP、hook）；"
            f"那個帳號下一段對話起就讀得到 OmniKit。過程記在 {state / 'home_watch.log'}")


def selftest():
    fails = []

    def ok(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as t:
        h, state = Path(t) / "home", Path(t) / "state"
        for d in (".claude", ".claude-kai", ".claude-new"):
            (h / d).mkdir(parents=True)
        (h / ".claude-new" / ".claude.json").write_text("{}", encoding="utf-8")
        (h / ".claude-kai" / ".claude.json").write_text("{}", encoding="utf-8")
        kai = homes.key("claude-code", (h / ".claude-kai").resolve())
        calls = []

        def fake(cmd, **kw):
            calls.append(cmd)
            return None

        ok("沒有 agents.json：不動", check(state, h, {}, 0, fake) is None and not calls)
        state.mkdir(parents=True)
        (state / "agents.json").write_text(json.dumps({"agents": ["claude-code"], "homes": [kai]}), encoding="utf-8")
        msg = check(state, h, {}, 1000, fake)
        ok("有新的設定目錄：背景跑 agents.py sync，說一聲在哪裡", msg is not None and ".claude-new" in msg
           and ".claude-kai" not in msg.split("，已在")[0] and len(calls) == 1 and calls[0][-1] == "sync")
        ok("同一組 6 小時內不重跑", check(state, h, {}, 1000 + 3600, fake) is None and len(calls) == 1)
        ok("超過 6 小時還沒接上：再試一次", check(state, h, {}, 1000 + RETRY + 1, fake) is not None and len(calls) == 2)
        (state / "agents.json").write_text(json.dumps({"agents": ["claude-code"], "homes": [
            kai, homes.key("claude-code", (h / ".claude-new").resolve()).upper()]}), encoding="utf-8")
        ok("都記過了（Windows 大小寫不同也算）：不動", os.name != "nt" or check(state, h, {}, 99999, fake) is None)
        (state / "agents.json").write_text(json.dumps({"agents": ["codex"]}), encoding="utf-8")
        ok("Claude 沒接上：Claude 的設定目錄不管", check(state, h, {}, 99999, fake) is None)
        (state / "agents.json").write_text(json.dumps({"agents": ["claude-code"], "skills": {
            "claude-code": [], f"claude-code@{(h / '.claude-kai').resolve()}": [],
            f"claude-code@{(h / '.claude-new').resolve()}": []}}), encoding="utf-8")
        ok("舊版記錄沒有 homes：用 skills 的 key 判斷", check(state, h, {}, 99999, fake) is None)
        (state / "agents.json").write_text("{壞掉", encoding="utf-8")
        ok("agents.json 壞掉：不動", check(state, h, {}, 99999, fake) is None)
    print("home_watch selftest", "FAIL" if fails else "OK")
    return 1 if fails else 0


def main():
    if "--selftest" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        return selftest()
    try:
        sys.stdin.read()  # hook 輸入用不到，讀掉就好
        msg = check()
        if msg:
            sys.stdout.reconfigure(encoding="utf-8")
            print(json.dumps({"systemMessage": msg}, ensure_ascii=False))
    except Exception:  # noqa: BLE001  檢查壞掉不能干擾對話
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
