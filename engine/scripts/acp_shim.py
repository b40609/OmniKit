# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""T3 Code 的 Antigravity 轉接程式：讓 T3 裡的 Antigravity 也讀得到使用者的全域規則（~/.gemini/GEMINI.md，含 OmniKit 規則）。

為什麼要轉接：T3 Code 給每個 Antigravity 實例一個自己的 GEMINI_HOME（~/.t3/userdata/providers/antigravity/<雜湊>），
用 ACP 模式跑 T3 自己裝的 agy_acp_server。這個 server 不從任何檔案讀全域規則（GEMINI.md、hooks.json 的
SessionStart 都不吃），唯一的入口是 session/new 的 _meta.antigravity.systemPrompt.append（T3 自己也用它放
PR 連結的說明）。所以這支站在 T3 與 server 中間，只做兩件事：
1. 開新對話、載入、恢復對話（session/new、session/load、session/resume）時，把 GEMINI.md 接在 append 前面；
   T3 原本要 append 的內容照樣接在後面。T3 自己的暫時對話（文字生成、設定、驗證，工作目錄是
   t3-antigravity-*）不帶，那些不是寫程式的對話。
2. 讓 T3 送出的內容跟它直接跑自己裝的版本時一樣：T3 對自訂的執行檔不知道版本，initialize 的 clientInfo
   與 fs.readTextFile 會跟用自己裝的版本時不同，這裡照 T3 的規則改回來；T3 裝的是 agy CLI 型的版本時，
   完全存取與自動接受修改的模式照 T3 的規則改成 default。
其他訊息原樣轉送，stdout 與 stderr 也原樣轉回 T3。

怎麼接上：agents.py（t3_acp.py）把這支複製到 ~/.omnikit/acp/，旁邊放啟動檔 omnikit-acp.cmd 與一個空的
localharness_external.exe（T3 認自訂執行檔的條件：旁邊要有這個檔；它的路徑這裡會換成 T3 裝的那一份），
再把 T3 每個 Antigravity 實例的 Binary path 設成 omnikit-acp.cmd。T3 會監看設定檔，改了馬上生效（新的對話起）。
T3 更新 ACP server 時，這支照 T3 的 active.json 找新的版本，不用重裝。
server 會另外再開一個自己，原本那個先結束、關 stdin 也不停，所以整組程序放進 Windows Job Object，
這支結束（T3 用 taskkill 結束它也一樣）就全部一起結束。

紀錄：這支旁邊的 shim.log（裝好後是 ~/.omnikit/acp/shim.log），只記哪一種對話帶了多少字，不記規則內容。

用法：T3 Code 執行，不用手動跑。自我測試：uv run engine/scripts/acp_shim.py --selftest
"""
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SESSION_METHODS = ("session/new", "session/load", "session/resume")
HELPER_PREFIX = "t3-antigravity-"  # T3 自己的暫時工作目錄：t3-antigravity-text-、-setup-、-validate-
HEADER = ("以下是使用者的 Antigravity 全域規則（~/.gemini/GEMINI.md）。T3 Code 不會自己載入它，"
          "由 OmniKit 轉接程式帶入；照它做，跟它衝突時以使用者在對話裡說的為準。")
OPEN_MODEL_ACCESS = (1, 5, 1)  # 照 T3：這版起 clientInfo 用 t3-code，之前的用 zed
QUALIFIED = "1.4.5"  # 照 T3：這版不開 fs.readTextFile
CLI_MODES = {"yolo": "default", "auto_edit": "default"}  # 照 T3 的 antigravityCliSessionMode
WATCHED = tuple(f'"{m}"'.encode() for m in ("initialize", *SESSION_METHODS, "session/set_mode"))


def log_path():
    return Path(__file__).resolve().parent / "shim.log"


def log(line):
    try:
        path = log_path()
        if path.exists() and path.stat().st_size > 256 * 1024:
            path.replace(path.with_suffix(".log.old"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except OSError:
        pass


def target():
    """T3 的 tools 資料夾名稱，跟 Node 的 process.platform-process.arch 一樣（例如 win32-x64）。"""
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    return f"{sys.platform if sys.platform != 'darwin' else 'darwin'}-{arch}"


def release(home=None, environ=None):
    """T3 現在用的 Antigravity ACP：(執行檔, harness 或 None, 版本)。照 T3 的 active.json 與 .install-complete.json。"""
    home = Path.home() if home is None else home
    environ = os.environ if environ is None else environ
    if environ.get("OMNIKIT_ACP_RELEASE"):  # 測試用：放 .install-complete.json 的資料夾
        folder = Path(environ["OMNIKIT_ACP_RELEASE"])
    else:
        base = home / ".t3" / "tools" / "antigravity-acp" / target()
        active = json.loads((base / "active.json").read_text(encoding="utf-8"))["releaseId"]
        folder = base / "versions" / active
    record = json.loads((folder / ".install-complete.json").read_text(encoding="utf-8"))
    harness = record.get("harness")
    return (folder / record["executable"]["name"], folder / harness["name"] if harness else None, record.get("version"))


def rules_text(home=None, warn=None):
    """要帶入的規則：~/.gemini/GEMINI.md；沒有或是空的就不帶，讀不到（不是 UTF-8 等）交給 warn 記一筆。"""
    path = (Path.home() if home is None else home) / ".gemini" / "GEMINI.md"
    try:
        content = path.read_bytes().decode("utf-8-sig").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        if warn:
            warn(f"讀不到 {path}（{type(e).__name__}），這次沒有帶規則")
        return None
    return f"{HEADER}\n\n{content}" if content else None


def parse_version(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("-")[0].split("."))
    except ValueError:
        return None


def helper_session(params):
    cwd = params.get("cwd")
    return isinstance(cwd, str) and Path(cwd).name.startswith(HELPER_PREFIX)


def encode(msg):
    """改過的訊息轉回一行。字串裡有落單的 surrogate（JSON 的 \\ud800 這類）編不成 UTF-8，就用 \\u 跳脫寫回去。"""
    try:
        return (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    except UnicodeEncodeError:
        return (json.dumps(msg, separators=(",", ":")) + "\n").encode("ascii")


def transform(line, rules, version, cli):
    """改一行 T3 送給 server 的訊息；不用改的原樣回傳。回傳（新的一行, 要記的事或 None）。
    rules 可以是字串或函式（要帶的時候才讀，GEMINI.md 改了，下一段對話就是新的）。"""
    body = line.strip()
    # 只有這幾種要改；其他訊息（例如帶附圖的 session/prompt，可能很大）不解析，原樣轉送
    if not body.startswith(b"{") or not any(m in body for m in WATCHED):
        return line, None
    try:
        msg = json.loads(body)
    except ValueError:
        return line, None
    params = msg.get("params") if isinstance(msg, dict) else None
    if not isinstance(params, dict):
        return line, None
    method, note = msg.get("method"), None
    if method == "initialize":
        parsed = parse_version(version)
        if parsed is not None and parsed >= OPEN_MODEL_ACCESS:
            params["clientInfo"] = {"name": "t3-code", "title": "T3 Code", "version": version}
            note = f"initialize：clientInfo 照 T3 對 {version} 的設定"
        if str(version).strip() == QUALIFIED:
            caps = params.setdefault("clientCapabilities", {})
            fs = caps.setdefault("fs", {}) if isinstance(caps, dict) else None
            if isinstance(fs, dict) and fs.get("readTextFile") is not False:
                fs["readTextFile"] = False
                note = f"initialize：fs.readTextFile 照 T3 對 {version} 的設定關掉"
    elif method in SESSION_METHODS and not helper_session(params):
        if callable(rules):
            rules = rules()
        if not rules:
            return line, None
        meta = params.setdefault("_meta", {})
        ag = meta.setdefault("antigravity", {}) if isinstance(meta, dict) else None
        prompt = ag.setdefault("systemPrompt", {}) if isinstance(ag, dict) else None
        if not isinstance(prompt, dict):
            return line, f"{method}：_meta 的格式看不懂，沒有帶規則"
        old = prompt.get("append")
        prompt["append"] = f"{rules}\n\n{old}" if isinstance(old, str) and old.strip() else rules
        note = f"{method}：帶入規則 {len(rules)} 字（工作目錄 {Path(str(params.get('cwd', ''))).name}）"
    elif method == "session/set_mode" and cli and params.get("modeId") in CLI_MODES:
        params["modeId"] = CLI_MODES[params["modeId"]]
        note = f"session/set_mode：agy CLI 型的版本，模式改成 {params['modeId']}"
    if note is None:
        return line, None
    return encode(msg), note


# ---- Windows Job Object：這支結束時，server 與它再開的程序一起結束 ----

def kill_on_close_job():
    """建一個 KILL_ON_JOB_CLOSE 的 job；失敗回 None。"""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class Io(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                   "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    job = k.CreateJobObjectW(None, None)
    if not job:
        return None
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info)):
        k.CloseHandle(wintypes.HANDLE(job))
        return None
    return job


def assign(job, pid=None):
    """把程序（沒給 pid 就是自己）放進 job；成功回 True。"""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.OpenProcess.restype = wintypes.HANDLE
    handle = k.GetCurrentProcess() if pid is None else k.OpenProcess(0x0101, False, pid)  # TERMINATE | SET_QUOTA
    ok = bool(handle) and bool(k.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(handle)))
    if pid is not None and handle:
        k.CloseHandle(wintypes.HANDLE(handle))
    return ok


def command(environ):
    """要跑的 server 指令與環境變數。"""
    env = dict(environ)
    if env.get("OMNIKIT_ACP_COMMAND"):  # 測試用：整個指令（JSON 陣列）
        return json.loads(env["OMNIKIT_ACP_COMMAND"]), env, None, False
    exe, harness, version = release(environ=environ)
    if harness is not None:
        env["ANTIGRAVITY_HARNESS_PATH"] = str(harness)  # T3 給的是旁邊那個空檔，換成 T3 裝的
        return [str(exe)], env, version, False
    env.pop("ANTIGRAVITY_HARNESS_PATH", None)  # agy CLI 型：照 T3 跑 agy 的方式
    return [str(exe), "acp", "--gemini-dir", env.get("GEMINI_HOME", ""), "--app-data-dir", "antigravity-acp"], env, version, True


def run():
    try:
        cmd, env, version, cli = command(os.environ)
    except (OSError, KeyError, ValueError, TypeError) as e:
        sys.stderr.buffer.write(f"OmniKit 轉接程式找不到 T3 Code 裝的 Antigravity ACP server（{e}）。"
                                "到 T3 的 Antigravity 設定安裝，或把這個實例的 Binary path 清空、改回自動。\n".encode("utf-8"))
        sys.stderr.flush()
        log(f"找不到 server：{e}")
        return 1
    version = env.get("OMNIKIT_ACP_VERSION", version)  # 測試用

    def rules():  # 每次開對話才讀：GEMINI.md 改了（例如 OmniKit sync），下一段對話就是新的
        return rules_text(warn=log)

    first = rules()
    job = kill_on_close_job()
    in_job = bool(job) and assign(job)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    if job and not in_job and not assign(job, proc.pid):
        job_note = "job 建了但放不進去，T3 結束時 server 可能留著"
    else:
        job_note = ("job 有" if in_job else "job 只放 server") if job else "job 沒有，T3 結束時 server 可能留著"
    log(f"啟動 {Path(cmd[0]).name}（版本 {version}，{'agy CLI 型' if cli else 'harness 型'}，"
        f"規則 {len(first) if first else 0} 字，{job_note}）")
    out = sys.stdout.buffer

    def pump():
        while True:
            chunk = proc.stdout.read1(65536)
            if not chunk:
                break
            out.write(chunk)
            out.flush()
        try:  # server 的輸出結束：整組一起結束（job 收掉剩下的）
            code = proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            code = 0
        os._exit(code)

    pumping = threading.Thread(target=pump, daemon=True)
    pumping.start()
    try:
        for line in sys.stdin.buffer:
            try:
                new, note = transform(line, rules, version, cli)
            except Exception as e:  # noqa: BLE001  改不了就原樣轉送，對話不能因為轉接程式斷掉
                new, note = line, f"沒改這則訊息（{type(e).__name__}: {e}），原樣轉送"
            if note:
                log(note)
            proc.stdin.write(new)
            proc.stdin.flush()
    except (BrokenPipeError, OSError):
        pass
    try:
        proc.stdin.close()
    except OSError:
        pass
    # T3 關掉 stdin：等 server 的輸出結束（pump 會自己結束整組），最多 3 秒，之後整組結束。
    # 不看 proc.poll()：server 會再開一個自己、原本那個先結束，看它會以為已經結束了
    pumping.join(3)
    os._exit(0)


FAKE_SERVER = r'''
import json, os, sys
for line in sys.stdin.buffer:
    msg = json.loads(line)
    reply = {"jsonrpc": "2.0", "id": msg.get("id"), "result": {"echo": msg, "harness": os.environ.get("ANTIGRAVITY_HARNESS_PATH")}}
    sys.stdout.buffer.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()
'''

# 像 agy_acp_server：再開一個自己（接手 stdin、stdout），原本那個馬上結束；T3 關 stdin 後新的那個還會再講一句
FAKE_RESPAWN = r'''
import json, subprocess, sys, time
if len(sys.argv) == 1:
    subprocess.Popen([sys.executable, __file__, "child"], stdin=sys.stdin, stdout=sys.stdout)
    sys.exit(0)
for line in sys.stdin.buffer:
    msg = json.loads(line)
    sys.stdout.buffer.write((json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": {}}) + "\n").encode())
    sys.stdout.buffer.flush()
time.sleep(0.5)
sys.stdout.buffer.write(b'{"jsonrpc":"2.0","method":"bye"}\n')
sys.stdout.buffer.flush()
'''


def selftest():
    fails = []

    def check(name, ok):
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            fails.append(name)

    def msg(method, params, i=1):
        return (json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}, ensure_ascii=False) + "\n").encode()

    rules = "RULES"
    new, note = transform(msg("session/new", {"cwd": "C:\\dev\\x", "mcpServers": []}), rules, "1.4.5", False)
    check("session/new：帶入規則", json.loads(new)["params"]["_meta"]["antigravity"]["systemPrompt"]["append"] == rules and note)
    t3 = {"cwd": "C:\\dev\\x", "_meta": {"antigravity": {"disabledTools": ["run_workflow"], "systemPrompt": {"append": "PR 說明"}}}}
    got = json.loads(transform(msg("session/load", t3), rules, "1.4.5", False)[0])["params"]["_meta"]["antigravity"]
    check("session/load：T3 原本的 append 接在規則後面，其他 _meta 不動",
          got["systemPrompt"]["append"] == "RULES\n\nPR 說明" and got["disabledTools"] == ["run_workflow"])
    check("session/resume 也帶", "_meta" in json.loads(transform(msg("session/resume", {"cwd": "C:\\a"}), rules, None, False)[0])["params"])
    line = msg("session/new", {"cwd": "C:\\Users\\u\\AppData\\Local\\Temp\\t3-antigravity-text-abc"})
    check("T3 自己的暫時對話（t3-antigravity-*）不帶", transform(line, rules, "1.4.5", False) == (line, None))
    line = msg("session/new", {"cwd": "C:\\dev\\x"})
    check("沒有規則（GEMINI.md 不在或是空的）：原樣", transform(line, None, "1.4.5", False) == (line, None))
    init = msg("initialize", {"protocolVersion": 1, "clientInfo": {"name": "zed", "version": "0.0.0"},
                              "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": False}, "terminal": False}})
    p = json.loads(transform(init, rules, "1.4.5", False)[0])["params"]
    check("initialize：1.4.5 照 T3 關掉 fs.readTextFile，clientInfo 維持 zed",
          p["clientCapabilities"]["fs"] == {"readTextFile": False, "writeTextFile": False} and p["clientInfo"]["name"] == "zed")
    p = json.loads(transform(init, rules, "1.5.2", False)[0])["params"]
    check("initialize：1.5.1 以後照 T3 用 t3-code 的 clientInfo，readTextFile 不動",
          p["clientInfo"] == {"name": "t3-code", "title": "T3 Code", "version": "1.5.2"} and p["clientCapabilities"]["fs"]["readTextFile"] is True)
    mode = msg("session/set_mode", {"sessionId": "s", "modeId": "yolo"})
    check("agy CLI 型：yolo 照 T3 改成 default；harness 型不改",
          json.loads(transform(mode, rules, "1.6.0", True)[0])["params"]["modeId"] == "default"
          and transform(mode, rules, "1.4.5", False) == (mode, None))
    big = msg("session/prompt", {"sessionId": "s", "prompt": [{"type": "image", "data": "A" * 5_000_000}]})
    started = time.monotonic()
    check("大的 session/prompt（附圖）不解析，原樣轉送", transform(big, rules, "1.4.5", False) == (big, None)
          and time.monotonic() - started < 0.5)
    for raw in (b"not json\n", b'{"jsonrpc":"2.0","id":3,"result":{}}\n', b"\n"):
        check(f"不是要改的訊息原樣轉送：{raw[:20]!r}", transform(raw, rules, "1.4.5", False) == (raw, None))
    lone = rb'{"jsonrpc":"2.0","id":4,"method":"session/new","params":{"cwd":"C:\\dev\\x","name":"\ud800"}}' + b"\n"
    got = json.loads(transform(lone, rules, "1.4.5", False)[0])["params"]
    check("字串有落單的 surrogate：照樣帶規則，用 \\u 跳脫寫回、內容不變",
          got["name"] == "\ud800" and got["_meta"]["antigravity"]["systemPrompt"]["append"] == rules)
    calls = []

    def lazy():
        calls.append(1)
        return "LAZY"

    got = json.loads(transform(msg("session/new", {"cwd": "C:\\dev\\x"}), lazy, "1.4.5", False)[0])["params"]
    transform(init, lazy, "1.4.5", False)
    check("規則用函式：開對話時才讀，其他訊息不讀", got["_meta"]["antigravity"]["systemPrompt"]["append"] == "LAZY" and calls == [1])

    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "bad" / ".gemini").mkdir(parents=True)
        (t / "bad" / ".gemini" / "GEMINI.md").write_bytes(b"\xff\xfe\x00bad")
        warned = []
        check("GEMINI.md 不是 UTF-8：不帶規則、記一筆；沒有這個檔：不記",
              rules_text(t / "bad", warned.append) is None and len(warned) == 1 and "UnicodeDecodeError" in warned[0]
              and rules_text(t / "none", warned.append) is None and len(warned) == 1)
        base = t / ".t3" / "tools" / "antigravity-acp" / target()
        (base / "versions" / "abc").mkdir(parents=True)
        (base / "active.json").write_text('{"releaseId":"abc"}', encoding="utf-8")
        (base / "versions" / "abc" / ".install-complete.json").write_text(json.dumps({
            "releaseId": "abc", "version": "1.4.5", "executable": {"name": "agy_acp_server.exe", "bytes": 1},
            "harness": {"name": "localharness_external.exe", "bytes": 1}}), encoding="utf-8")
        exe, harness, version = release(t, {})
        check("照 T3 的 active.json 找到 server、harness 與版本",
              exe.name == "agy_acp_server.exe" and harness.name == "localharness_external.exe" and version == "1.4.5")
        (base / "versions" / "abc" / ".install-complete.json").write_text(json.dumps({
            "releaseId": "abc", "version": "1.6.0", "executable": {"name": "agy.exe", "bytes": 1}, "harness": None}), encoding="utf-8")
        cmd, env, version, cli = command({"OMNIKIT_ACP_RELEASE": str(base / "versions" / "abc"), "GEMINI_HOME": "G",
                                          "ANTIGRAVITY_HARNESS_PATH": "x"})
        check("agy CLI 型的版本：照 T3 跑 agy acp，不帶 harness",
              cmd[1:] == ["acp", "--gemini-dir", "G", "--app-data-dir", "antigravity-acp"] and cli
              and "ANTIGRAVITY_HARNESS_PATH" not in env)
        check("找不到 server：拋出錯誤（run 會轉成給 T3 看的訊息）", _raises(lambda: release(t / "none", {})))

        # 端到端：假的 server 把收到的訊息回傳；真的開一個轉接程式，從 stdin 送、從 stdout 收
        (t / ".gemini").mkdir()
        (t / ".gemini" / "GEMINI.md").write_text("\ufeff# 規則\n狀態標籤：【完成待收尾】\n", encoding="utf-8")
        fake = t / "fake_server.py"
        fake.write_text(FAKE_SERVER, encoding="utf-8")
        env = {**os.environ, "USERPROFILE": str(t), "HOME": str(t),
               "OMNIKIT_ACP_COMMAND": json.dumps([sys.executable, str(fake)]), "OMNIKIT_ACP_VERSION": "1.4.5",
               "PYTHONIOENCODING": "utf-8"}
        shim = t / "acp" / "acp_shim.py"  # 跟裝好時一樣放在自己的資料夾，紀錄寫在旁邊
        shim.parent.mkdir()
        shim.write_bytes(Path(__file__).read_bytes())
        lines = msg("initialize", {"protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": True}}}, 1) \
            + msg("session/new", {"cwd": str(t), "mcpServers": []}, 2) + msg("session/prompt", {"sessionId": "s", "prompt": []}, 3)
        r = subprocess.run([sys.executable, str(shim)], input=lines, capture_output=True, env=env, timeout=60)
        replies = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
        echo = {x["id"]: x["result"]["echo"] for x in replies}
        check("端到端：三則都轉送、回覆原樣傳回", sorted(echo) == [1, 2, 3])
        check("端到端：session/new 帶了 GEMINI.md（去掉 BOM），前面有說明",
              echo.get(2, {}).get("params", {}).get("_meta", {}).get("antigravity", {}).get("systemPrompt", {}).get("append", "")
              .startswith(HEADER) and "【完成待收尾】" in echo[2]["params"]["_meta"]["antigravity"]["systemPrompt"]["append"]
              and "\ufeff" not in echo[2]["params"]["_meta"]["antigravity"]["systemPrompt"]["append"])
        check("端到端：initialize 照 1.4.5 關掉 readTextFile；session/prompt 原樣",
              echo.get(1, {}).get("params", {}).get("clientCapabilities", {}).get("fs", {}).get("readTextFile") is False
              and echo.get(3, {}).get("params") == {"sessionId": "s", "prompt": []})
        logged = (shim.parent / "shim.log").read_text(encoding="utf-8")
        check("紀錄只寫帶了幾個字，不寫規則內容", "帶入規則" in logged and "【完成待收尾】" not in logged)
        check("結束碼 0", r.returncode == 0)
        respawn = t / "respawn_server.py"
        respawn.write_text(FAKE_RESPAWN, encoding="utf-8")
        r = subprocess.run([sys.executable, str(shim)], input=msg("session/prompt", {"sessionId": "s", "prompt": []}, 5),
                           capture_output=True, env={**env, "OMNIKIT_ACP_COMMAND": json.dumps([sys.executable, str(respawn)])},
                           timeout=60)
        got = [json.loads(x) for x in r.stdout.splitlines() if x.strip()]
        check("server 再開一個自己、原本的先結束：T3 關 stdin 後仍等新的那個把話講完",
              [x.get("id") for x in got if "id" in x] == [5] and any(x.get("method") == "bye" for x in got))
    print("acp_shim selftest", "FAIL" if fails else "OK")
    return 1 if fails else 0


def _raises(fn):
    try:
        fn()
    except (OSError, KeyError, ValueError):
        return True
    return False


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.exit(selftest())
    sys.exit(run())
