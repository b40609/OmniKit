# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""由讀取方判定的心跳檢查器（D10 改動 2，規格在 engine/schema/heartbeat.schema.json）。

為什麼：做事的程式自己寫「running」「ok」，行程死了、斷線了、資料沒進來，狀態檔照樣說正常；
部署腳本重開失敗也照印「verified」。這支只讀事實與時間，自己算每個狀態檔是 FRESH、STALE 還是 DOWN：

- FRESH：現在減 last_success_ts 在 expected_period_s 加 grace_s 以內，其他檢查也都過。
- STALE：超過週期加寬限沒有新的成功；資料最新日期落後超過上限；部署開始後還沒有成功紀錄。
- DOWN：讀不到檔、不是標準 JSON（含 Infinity、NaN 這類常數）、欄位缺、數字是無限大、時間解析失敗或沒帶時區、
  pid 不存在或超出 1 到 0xFFFFFFFF、pid 啟動時間對不上、時鐘錯亂（last_attempt_ts 晚於現在）、
  存了狀態字（巢狀物件、陣列裡也算，不分大小寫）、build 不是預期的版本、行程是部署前就在跑的那一個、
  指定了部署開始時間卻沒有 pid 可以查證（狀態檔來自別台機器就加 --skip-pid）。
- PAUSED：預期中的灰色態，不是綠燈也不算異常（結束碼照 0）。兩種來源：狀態檔寫了還沒到期的 paused_until_ts
  （純事實的時間，到期自動恢復嚴格判定；不准存 paused: true 這種狀態字），或讀取方說系統剛從休眠醒來
  （--wake-grace-remaining-s 大於 0），原本只因為「時間過太久」的 STALE 先降成 PAUSED，不亮假紅燈。

2026-11-28 向下相容補強（舊的狀態檔不用改）：
- 讀取方覆寫期望（--override-period-s、--override-grace-s）：狀態檔自報週期 10 年也沒用，以讀的一方為準。
- max_run_s（--max-run-s）：last_attempt_ts 晚於 last_success_ts，而且開始後超過這麼久還沒成功，判 STALE（啟動後卡死）。
- min_items_out（--min-items-out）：progress.items_out 低於下限、或設了下限卻沒有 items_out，判 STALE（exit 0 空跑）。
- host：狀態檔來自別台主機（跟本機主機名不同，不分大小寫）就自動不查 pid，不會誤判 DOWN。
- x_dirty：做事那方記下「工作樹有沒提交的改動」這個事實，讀取方附註出來。

用法：
  uv run engine/scripts/stale_check.py <狀態檔…> [--expect-build <build>] [--started-after <ISO 時間>]
      [--max-data-age-days <天>] [--skip-pid] [--json] [--self-heartbeat <檔> --self-period-s <秒>]
      [--override-period-s <秒>] [--override-grace-s <秒>] [--max-run-s <秒>] [--min-items-out <筆>]
      [--wake-grace-remaining-s <秒>]
  uv run engine/scripts/stale_check.py --selftest

  --expect-build    build 要等於這個（兩邊都是 7 碼以上十六進位時，前綴相同就算）
  --started-after   部署開始時間：pid_start_ts 要晚於它，last_success_ts 也要晚於它
  --max-data-age-days  progress.data_date 最多落後幾天（狀態檔的 max_data_age_days 也算，這裡優先）
  --skip-pid        不查 pid（狀態檔來自別台機器時）；輸出會註明沒查
  --now             測試用：把「現在」固定成這個時間；pid 照樣查這台的真實行程
  --self-heartbeat  檢查完把檢查器自己的心跳寫到這個檔（規格第 6 條），給另一個觸發點用同一支檢查器看

結束碼：0 全部 FRESH（PAUSED 不算異常，也是 0，但結論那行會寫出有幾個 PAUSED）；1 有 STALE、沒有 DOWN；
2 有 DOWN，或用法錯誤。
每個檔的結果與結論都在全部檢查跑完之後才印，結論在最後一行。
"""
import argparse
import collections
import contextlib
import io
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fsretry import retry  # 防毒短暫鎖住檔案時等一下再試（FR-34）

SPEC = 1
REQUIRED = ("spec", "name", "last_attempt_ts", "last_success_ts", "expected_period_s", "grace_s")
OPTIONAL = ("pid", "pid_start_ts", "build", "progress", "max_data_age_days",
            "max_run_s", "min_items_out", "host", "paused_until_ts")
# 規格第 1 條：這些欄位名稱與值都是「狀態字」，由做事那方寫的就不能信（不分大小寫；跟規格檔的 $defs 一致，測試會比對）
STATUS_KEYS = ("status", "state", "health", "healthy", "ok", "running", "alive", "up", "success", "verified", "passes",
               "paused")
STATUS_WORDS = ("running", "ok", "healthy", "alive", "green", "success", "succeeded", "online", "ready", "verified",
                "passing", "passed", "paused")
# PAUSED 是預期中的灰色態：嚴重度跟 FRESH 一樣是 0（不算 STALE、DOWN），但它不是 FRESH，顯示時不能當綠燈
SEVERITY = {"FRESH": 0, "PAUSED": 0, "STALE": 1, "DOWN": 2}
EXIT = {"FRESH": 0, "PAUSED": 0, "STALE": 1, "DOWN": 2}
VERDICTS = ("FRESH", "PAUSED", "STALE", "DOWN")
EXIT_USAGE = 2
CLOCK_SKEW_S = 60          # 時間晚於現在超過這麼多秒才算時鐘錯亂
ORDER_SLACK_S = 1          # last_success_ts 晚於 last_attempt_ts 不到 1 秒當成同一次寫入
PID_START_TOLERANCE_S = 60  # 狀態檔記的啟動時間與系統的差多少秒以內算對得上（程式通常啟動後才記）
PID_MAX = 0xFFFFFFFF       # Windows 的 pid 是 32 位元 DWORD；更大的值交給系統呼叫會被截斷成別的行程
MAX_PAUSE_S = 30 * 86400   # paused_until_ts 最多採信到現在之後這麼久；寫 10 年後等於自報永遠正常，不採信


# ---- 時間 ----

def parse_ts(value):
    """ISO 8601 而且要帶時區；回傳 (datetime, 錯誤)。數字（epoch）、沒有時區、格式錯一律算錯。"""
    if not isinstance(value, str):
        return None, f"要是 ISO 8601 字串，拿到 {type(value).__name__}"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None, f"不是 ISO 8601 時間：{value!r}"
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None, f"沒有時區：{value!r}（要像 2026-11-26T22:10:03+08:00 或 ...Z）"
    return dt, None


def human(seconds):
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d} 天" + (f" {h} 小時" if h else "")
    if h:
        return f"{h} 小時" + (f" {m} 分" if m else "")
    if m:
        return f"{m} 分鐘"
    return f"{s} 秒"


def _num(v):
    """有限的數字。整數一定有限；浮點數要排除 inf 與 nan（1e400 這種寫法 json.loads 會溢位成 inf）。"""
    if isinstance(v, bool):
        return False
    return isinstance(v, int) or (isinstance(v, float) and math.isfinite(v))


def _reject_constant(name):
    """json.loads 的 parse_constant：Infinity、-Infinity、NaN 不是標準 JSON（RFC 8259），一律不收。"""
    raise ValueError(f"不是標準 JSON 的數值常數 {name}")


# ---- 行程 ----

def _win_process(pid):
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.WaitForSingleObject.restype = wintypes.DWORD
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    query, synchronize = 0x1000, 0x00100000   # PROCESS_QUERY_LIMITED_INFORMATION、SYNCHRONIZE
    can_wait = True
    h = k32.OpenProcess(query | synchronize, False, pid)
    if not h:
        err = ctypes.get_last_error()
        if err == 5:                            # 存取被拒：不能等它，改只查資訊
            can_wait = False
            h = k32.OpenProcess(query, False, pid)
            err = ctypes.get_last_error() if not h else 0
        if not h:
            if err == 87:                       # ERROR_INVALID_PARAMETER：沒有這個 pid
                return "dead", None, ""
            if err == 5:
                return "alive", None, "權限不足，查不到啟動時間"
            return "unknown", None, f"OpenProcess 失敗（winerror {err}）"
    try:
        if can_wait:
            alive = k32.WaitForSingleObject(h, 0) == 0x102   # WAIT_TIMEOUT：還沒結束
        else:
            code = wintypes.DWORD()
            alive = bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        if not alive:
            return "dead", None, ""
        times = [wintypes.FILETIME() for _ in range(4)]
        if not k32.GetProcessTimes(h, *[ctypes.byref(t) for t in times]):
            return "alive", None, f"GetProcessTimes 失敗（winerror {ctypes.get_last_error()}）"
        ft = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return "alive", datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=ft // 10), ""
    finally:
        k32.CloseHandle(h)


def _linux_process(pid):
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return "dead", None, ""
    except OSError as e:
        return "unknown", None, f"讀不到 /proc/{pid}/stat：{e}"
    rest = raw[raw.rindex(")") + 2:].split()   # 行程名稱可能有空白與括號，從最後一個 ) 之後切
    if rest[0] in ("Z", "X"):
        return "dead", None, "殭屍行程"
    try:
        btime = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                     if line.startswith("btime "))
        start = btime + int(rest[19]) / os.sysconf("SC_CLK_TCK")
    except (OSError, StopIteration, ValueError, IndexError) as e:
        return "alive", None, f"算不出啟動時間：{e}"
    return "alive", datetime.fromtimestamp(start, UTC), ""


def _ps_process(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead", None, ""
    except PermissionError:
        pass
    except OSError as e:
        return "unknown", None, str(e)
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10,
                           env={**os.environ, "LC_ALL": "C"}, check=False)
        started = datetime.strptime(" ".join(r.stdout.split()), "%a %b %d %H:%M:%S %Y").astimezone()
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return "alive", None, f"ps 查不到啟動時間：{e}"
    return "alive", started, ""


def process_info(pid):
    """(狀態, 系統記錄的啟動時間, 備註)。狀態是 alive、dead 或 unknown。"""
    if isinstance(pid, bool) or not isinstance(pid, int) or not 0 < pid <= PID_MAX:
        return "dead", None, f"pid 超出範圍（要在 1 到 {PID_MAX}）"
    if sys.platform == "win32":
        return _win_process(pid)
    if Path("/proc/self/stat").exists():
        return _linux_process(pid)
    return _ps_process(pid)


# ---- 檢查一個狀態檔 ----

def _short(v):
    try:
        s = json.dumps(v, ensure_ascii=False)
    except (ValueError, RecursionError):
        s = type(v).__name__
    return s if len(s) <= 80 else s[:77] + "..."


def _status_words(doc):
    """規格第 1 條：找出狀態字（欄位名稱或值）。巢狀的物件與陣列一路往下看，不分大小寫。回傳說明字串清單。"""
    found = []

    def key_hit(k):
        return isinstance(k, str) and k.lower().removeprefix("x_") in STATUS_KEYS

    def val_hit(v):
        return isinstance(v, str) and v.strip().lower() in STATUS_WORDS

    nested = collections.deque()
    for k, v in doc.items():
        if k in ("name", "build"):
            continue
        if key_hit(k) or ((k.startswith("x_") or k not in REQUIRED + OPTIONAL) and val_hit(v)):
            found.append(f"{k}={_short(v)}")
        if isinstance(v, dict | list):
            nested.append((k, v))
    # 用佇列不用遞迴：巢狀很深的檔也不會讓檢查器自己爆掉
    while nested:
        path, v = nested.popleft()
        children = ((f"{path}.{k}", k, sub) for k, sub in v.items()) if isinstance(v, dict) \
            else ((f"{path}[{i}]", None, sub) for i, sub in enumerate(v))
        for where, k, sub in children:
            if key_hit(k) or val_hit(sub):
                found.append(f"{where}={_short(sub)}")
            if isinstance(sub, dict | list):
                nested.append((where, sub))
    return found


def _build_matches(actual, expected):
    a, e = actual.strip().lower(), expected.strip().lower()
    if a == e:
        return True
    hexchars = set("0123456789abcdef")
    if len(a) >= 7 and len(e) >= 7 and set(a) <= hexchars and set(e) <= hexchars:
        return a.startswith(e) or e.startswith(a)
    return False


def local_host_names():
    """這台機器可能被叫的主機名（小寫）。狀態檔的 host 對得上任何一個就算本機。"""
    names = set()
    for get in (socket.gethostname, lambda: os.environ.get("COMPUTERNAME", ""), lambda: os.environ.get("HOSTNAME", "")):
        try:
            n = str(get() or "").strip().lower()
        except OSError:
            n = ""
        if n:
            names.add(n)
    return names


def verdict_of(reasons):
    """由理由清單算判定：DOWN 最重，其次 STALE，再來 PAUSED，都沒有才是 FRESH。"""
    levels = {lvl for lvl, _ in reasons}
    for v in ("DOWN", "STALE", "PAUSED"):
        if v in levels:
            return v
    return "FRESH"


def check_doc(doc, now, opts):
    """回傳 reasons：[(等級, 說明)]，等級是 DOWN、STALE、PAUSED 或 info。

    opts 除了原本的 expect_build、started_after、max_data_age_days、skip_pid、pid_tolerance_s，另外支援：
    override_period_s、override_grace_s（讀取方覆寫期望）、max_run_s、min_items_out（優先於狀態檔的同名欄位）、
    wake_grace_remaining_s（剛從休眠醒來還剩幾秒緩衝）、local_host（測試用：把本機主機名固定成這個）、
    max_pause_s（paused_until_ts 最多採信多久，預設 30 天）、_meta（呼叫端給一個 dict，檢查完把機器可讀的事實填進去：
    pid_state、actual_start_ts、remote_host、paused、stale_kinds，給控制面板的探針分三軸用）。
    """
    reasons = []
    meta = opts.get("_meta") if isinstance(opts.get("_meta"), dict) else {}
    meta.update({"pid_state": None, "actual_start_ts": None, "remote_host": None, "paused": False, "stale_kinds": []})
    # 可以被「預期暫停」或「剛喚醒」降成 PAUSED 的理由記在這裡（存 reasons 的索引）：
    # timeout 是「時間過太久」這一類（休眠會造成假的），output 是產出不夠，liveness 是 pid 不在（暫停期間本來就可以不在跑）
    soft = {"timeout": [], "output": [], "liveness": []}

    def down(msg, kind=None):
        reasons.append(("DOWN", msg))
        if kind:
            soft[kind].append(len(reasons) - 1)

    def stale(msg, kind=None):
        reasons.append(("STALE", msg))
        if kind:
            soft[kind].append(len(reasons) - 1)

    def info(msg):
        reasons.append(("info", msg))

    if not isinstance(doc, dict):
        down("內容不是 JSON 物件")
        return reasons

    words = _status_words(doc)
    if words:
        down(f"狀態檔不准存狀態字：{'、'.join(words)}（規格第 1 條：正不正常由讀的一方算，狀態字一律不讀）")
    extra = [k for k in doc if k not in REQUIRED + OPTIONAL and not k.startswith("x_")]
    extra = [k for k in extra if not any(w.startswith(f"{k}=") for w in words)]
    if extra:
        down(f"不合規格：多了欄位 {'、'.join(extra)}（擴充欄位用 x_ 開頭）")
    missing = [k for k in REQUIRED if k not in doc]
    if missing:
        down(f"少了欄位 {'、'.join(missing)}")

    if "spec" in doc and doc["spec"] != SPEC:
        down(f"不支援的規格版本 spec={doc['spec']!r}（這支只懂 spec {SPEC}）")
    if "name" in doc and not (isinstance(doc["name"], str) and doc["name"].strip()):
        down("name 要是非空字串")
    period = doc.get("expected_period_s")
    grace = doc.get("grace_s")
    if "expected_period_s" in doc and not (_num(period) and period > 0):
        down(f"expected_period_s 要是大於 0 的秒數：{period!r}")
        period = None
    if "grace_s" in doc and not (_num(grace) and grace >= 0):
        down(f"grace_s 要是 0 以上的秒數：{grace!r}")
        grace = None

    ts = {}
    for field in ("last_attempt_ts", "last_success_ts", "pid_start_ts"):
        if field not in doc:
            continue
        dt, err = parse_ts(doc[field])
        if err:
            down(f"時間解析失敗：{field} {err}")
        else:
            ts[field] = dt
            if dt > now + timedelta(seconds=CLOCK_SKEW_S):
                down(f"{field} 晚於現在 {human((dt - now).total_seconds())}（{doc[field]}）：時鐘錯亂，不能當正常")

    attempt, success = ts.get("last_attempt_ts"), ts.get("last_success_ts")
    if attempt and success and success > attempt + timedelta(seconds=ORDER_SLACK_S):
        down("last_success_ts 晚於 last_attempt_ts：成功也是一次嘗試，時間順序不對")

    # 讀取方覆寫期望：狀態檔自報的週期是做事那方寫的，寫 10 年就永遠 FRESH；讀的一方有自己的期望時以它為準
    for key, floor_ok in (("override_period_s", lambda v: v > 0), ("override_grace_s", lambda v: v >= 0)):
        ov = opts.get(key)
        if ov is None:
            continue
        if not (_num(ov) and floor_ok(ov)):
            down(f"讀取方的 {key} 不合法：{ov!r}")
            continue
        if key == "override_period_s":
            if period != ov:
                info(f"已套用讀取方期望（檔案自報 {_short(doc.get('expected_period_s'))} 秒，改用週期 {ov:g} 秒）")
            period = ov
        else:
            if grace != ov:
                info(f"已套用讀取方期望（檔案自報 {_short(doc.get('grace_s'))} 秒，改用寬限 {ov:g} 秒）")
            grace = ov

    if success and period is not None and grace is not None:
        age = (now - success).total_seconds()
        limit = period + grace
        when = f"上次成功是 {human(age)}前（{doc['last_success_ts']}）"
        if age > limit:
            stale(f"{when}，超過週期 {period:g} 秒加寬限 {grace:g} 秒", "timeout")
        else:
            info(f"{when}，在週期 {period:g} 秒加寬限 {grace:g} 秒內")
    if attempt and success and attempt > success:
        info(f"上次嘗試是 {human((now - attempt).total_seconds())}前（{doc['last_attempt_ts']}）")

    # 啟動後卡死：開始嘗試了卻一直沒有成功，而且已經超過一輪該跑完的時間
    max_run = opts.get("max_run_s")
    if max_run is None and "max_run_s" in doc:
        max_run = doc["max_run_s"]
    if max_run is not None and not (_num(max_run) and max_run > 0):
        down(f"max_run_s 要是大於 0 的秒數：{max_run!r}")
        max_run = None
    if max_run is not None and attempt and success and attempt > success + timedelta(seconds=ORDER_SLACK_S):
        running_for = (now - attempt).total_seconds()
        if running_for > max_run:
            stale(f"任務啟動後逾時疑似卡死：{human(running_for)}前開始（{doc['last_attempt_ts']}），"
                  f"超過上限 {max_run:g} 秒還沒有成功", "timeout")

    # 規格第 4 條：看產出面的事實
    prog = doc.get("progress")
    if "progress" in doc and not isinstance(prog, dict):
        down("progress 要是物件")
        prog = None
    prog = prog or {}
    for k in ("items_out", "errors_last_run"):
        if k in prog and not (isinstance(prog[k], int) and not isinstance(prog[k], bool) and prog[k] >= 0):
            down(f"progress.{k} 要是 0 以上的整數：{prog[k]!r}")
    if _num(prog.get("errors_last_run")) and prog["errors_last_run"] > 0:
        info(f"上一輪錯誤 {prog['errors_last_run']} 筆")
    # 產出量下限：exit 0 但什麼都沒寫出來（空跑）不算成功
    min_items = opts.get("min_items_out")
    if min_items is None and "min_items_out" in doc:
        min_items = doc["min_items_out"]
    if min_items is not None and not (isinstance(min_items, int) and not isinstance(min_items, bool) and min_items >= 0):
        down(f"min_items_out 要是 0 以上的整數：{min_items!r}")
        min_items = None
    if min_items is not None:
        items = prog.get("items_out")
        if "items_out" not in prog:
            stale(f"產出筆數低於下限：要求至少 {min_items} 筆，但沒有 progress.items_out", "output")
        elif isinstance(items, int) and not isinstance(items, bool) and items < min_items:
            stale(f"產出筆數低於下限：這一輪寫出 {items} 筆，下限 {min_items} 筆（exit 0 不算數，看產出）", "output")
    max_age = opts.get("max_data_age_days")
    if max_age is None and "max_data_age_days" in doc:
        max_age = doc["max_data_age_days"]
        if not (_num(max_age) and max_age >= 0):
            down(f"max_data_age_days 要是 0 以上的天數：{max_age!r}")
            max_age = None
    if "data_date" in prog or max_age is not None:
        raw = prog.get("data_date")
        if raw is None:
            down("要求資料日期上限，但沒有 progress.data_date")
        else:
            try:
                if not (isinstance(raw, str) and len(raw) == 10):
                    raise ValueError
                d = date.fromisoformat(raw)
            except ValueError:
                down(f"progress.data_date 不是 YYYY-MM-DD：{raw!r}")
            else:
                tz = (success or now).tzinfo
                lag = (now.astimezone(tz).date() - d).days
                if max_age is not None and lag > max_age:
                    stale(f"資料最新日期 {raw}，落後 {lag} 天，超過上限 {max_age:g} 天（exit 0 不算數，看產出）",
                          "timeout")
                else:
                    info(f"資料最新日期 {raw}（落後 {lag} 天）")

    # 規格第 3 條：pid 與啟動時間由讀的一方向系統查證
    # 跨機：狀態檔記了 host 而且不是這台，pid 是別台機器的，在這台查一定查不到，不能因此判 DOWN
    skip_pid = bool(opts.get("skip_pid"))
    skip_why = "--skip-pid"
    if "host" in doc:
        host = doc["host"]
        if not (isinstance(host, str) and host.strip()):
            down(f"host 要是非空字串：{host!r}")
        else:
            mine = {str(opts["local_host"]).strip().lower()} if opts.get("local_host") else local_host_names()
            if host.strip().lower() not in mine:
                info(f"狀態檔來自遠端主機 {host.strip()}（不是這台）：不查 pid")
                meta["remote_host"] = host.strip()
                if not skip_pid:
                    skip_pid, skip_why = True, f"遠端主機 {host.strip()}"

    pid = doc.get("pid")
    recorded_start = ts.get("pid_start_ts")
    verified_start = False
    if "pid" in doc:
        if not (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0):
            down(f"pid 要是正整數：{pid!r}")
        elif pid > PID_MAX:
            down(f"pid 超出範圍（要在 1 到 {PID_MAX}）：{pid}；不能交給系統呼叫截斷成別的行程")
        elif skip_pid:
            info(f"沒查 pid {pid}（{skip_why}）")
            meta["pid_state"] = "skipped"
        else:
            state, actual, note = process_info(pid)
            meta["pid_state"] = state
            if state == "alive" and actual is not None:
                meta["actual_start_ts"] = actual.isoformat(timespec="seconds")
            if state == "dead":
                down(f"pid {pid} 不存在（行程已結束{'，' + note if note else ''}）", "liveness")
            elif state == "unknown":
                down(f"查不到 pid {pid} 在不在：{note}")
            elif recorded_start is None:
                if "pid_start_ts" not in doc:
                    info(f"pid {pid} 在跑，但沒有 pid_start_ts，無法排除 pid 被別的行程重用")
            elif actual is None:
                down(f"查不到 pid {pid} 的啟動時間，無法確認是同一個行程：{note}")
            else:
                diff = abs((actual - recorded_start).total_seconds())
                if diff > opts.get("pid_tolerance_s", PID_START_TOLERANCE_S):
                    down(f"pid {pid} 的啟動時間不符：狀態檔記 {doc['pid_start_ts']}，系統是 "
                         f"{actual.astimezone(recorded_start.tzinfo).isoformat(timespec='seconds')}"
                         f"（差 {human(diff)}，pid 可能被別的行程重用，或行程重開過）")
                else:
                    verified_start = True
    meta["pid_start_verified"] = verified_start

    # 規格第 7 條：「已上線」要對得上版本與重啟時間
    expect = opts.get("expect_build")
    if expect is not None:
        build = doc.get("build")
        if not isinstance(build, str) or not build.strip():
            down(f"沒有 build 欄位，無法確認跑的是 {expect}")
        elif not _build_matches(build, expect):
            down(f"build 是 {build}，預期 {expect}：部署後跑的還是別的版本")
    after = opts.get("started_after")
    if after is not None:
        if recorded_start is None:
            down("沒有 pid_start_ts，無法確認部署開始後重啟過")
        else:
            if recorded_start <= after:
                down(f"行程啟動時間 {doc['pid_start_ts']} 不晚於部署開始 {after.isoformat(timespec='seconds')}："
                     "還是部署前就在跑的那個行程")
            elif "pid" not in doc and not skip_pid:
                down("有部署開始時間（--started-after）但狀態檔沒有 pid：pid_start_ts 是做事那方自己寫的，"
                     "沒向系統查證就不能確認部署後真的重啟過（狀態檔來自別台機器就加 --skip-pid）")
            elif not verified_start:
                info("pid_start_ts 沒有向系統查證（沒有 pid、--skip-pid 或查不到）")
        if success and success <= after:
            stale(f"部署開始（{after.isoformat(timespec='seconds')}）之後還沒有成功紀錄")

    # 未提交改動：做事那方記下的事實，讀取方只附註（版本對不對由上層決定怎麼顯示）
    if doc.get("x_dirty") is True:
        info("執行工作樹含未提交改動（x_dirty）")

    # 預期暫停：paused_until_ts 是「到什麼時候為止」的事實，不是狀態字；到期自動恢復嚴格判定。
    # 暫停期間「時間過太久」「產出不夠」「行程不在」都是預期的，降成 PAUSED；格式錯、狀態字、版本不對照樣算。
    def demote(kinds, suffix):
        for kind in kinds:
            for i in soft[kind]:
                reasons[i] = ("PAUSED", f"{reasons[i][1]}（{suffix}）")

    if "paused_until_ts" in doc:
        until, err = parse_ts(doc["paused_until_ts"])
        max_pause = opts.get("max_pause_s", MAX_PAUSE_S)
        if err:
            down(f"時間解析失敗：paused_until_ts {err}")
        elif now < until:
            remain = (until - now).total_seconds()
            if remain > max_pause:
                info(f"paused_until_ts（{doc['paused_until_ts']}）距現在 {human(remain)}，超過最多採信的 "
                     f"{human(max_pause)}：不當成暫停，照常判定")
            else:
                reasons.append(("PAUSED", f"預期暫停到 {doc['paused_until_ts']}（還有 {human(remain)}），到期自動恢復判定"))
                demote(("timeout", "output", "liveness"), "預期暫停中")
                meta["paused"] = True
        else:
            info(f"暫停期限 {doc['paused_until_ts']} 已過，恢復嚴格判定")

    # 休眠喚醒寬限：電腦睡著的時候時鐘照走、工作沒跑，醒來那一刻每個心跳都「過期」。讀取方說還在緩衝期內，
    # 而且沒有別的問題（只有「時間過太久」這一類 STALE）時，先標 PAUSED，不亮假紅燈；其他 STALE、DOWN 照舊
    wake = opts.get("wake_grace_remaining_s")
    if wake is not None and _num(wake) and wake > 0:
        levels = [lvl for lvl, _ in reasons]
        timeout_idx = [i for i in soft["timeout"] if reasons[i][0] == "STALE"]
        other_stale = [i for i, lvl in enumerate(levels) if lvl == "STALE" and i not in timeout_idx]
        if timeout_idx and "DOWN" not in levels and not other_stale:
            for i in timeout_idx:
                reasons[i] = ("PAUSED", f"{reasons[i][1]}（系統剛自休眠喚醒緩衝中，還有 {human(wake)}）")
    # 還留著的 STALE 各是哪一類：timeout（時間過太久）、output（產出不夠）、other（例如部署後還沒有成功紀錄）
    kind_of = {i: kind for kind in ("timeout", "output") for i in soft[kind]}
    meta["stale_kinds"] = sorted({kind_of.get(i, "other") for i, (lvl, _) in enumerate(reasons) if lvl == "STALE"})
    return reasons


def check_file(path, now, opts):
    path = Path(path)
    result = {"path": str(path), "name": None, "verdict": "DOWN", "reasons": [], "facts": {}, "meta": {}}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        result["reasons"] = [("DOWN", f"讀不到狀態檔：{e}")]
        return result
    try:
        doc = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as e:   # JSONDecodeError 是 ValueError；巢狀太深是 RecursionError
        result["reasons"] = [("DOWN", f"不是合法的 JSON：{type(e).__name__}: {e}")]
        return result
    if isinstance(doc, dict) and isinstance(doc.get("name"), str):
        result["name"] = doc["name"]
    meta = {}
    try:
        reasons = check_doc(doc, now, {**opts, "_meta": meta})
    except Exception as e:  # noqa: BLE001  檢查器自己出錯也不能當正常
        reasons = [("DOWN", f"檢查器例外：{type(e).__name__}: {e}")]
    result["meta"] = meta
    order = {"DOWN": 0, "STALE": 1, "PAUSED": 2, "info": 3}
    reasons.sort(key=lambda r: order[r[0]])
    result["verdict"] = verdict_of(reasons)
    result["reasons"] = reasons
    result["facts"] = _facts(doc)
    return result


FACT_KEYS = ("last_attempt_ts", "last_success_ts", "expected_period_s", "grace_s", "pid", "pid_start_ts", "build",
             "host", "paused_until_ts", "max_run_s", "min_items_out", "x_dirty")


def _facts(doc):
    """給上層（例如控制面板探針）用的原始事實：只挑規格裡的欄位，不做任何判定。"""
    if not isinstance(doc, dict):
        return {}
    facts = {k: doc[k] for k in FACT_KEYS if k in doc and isinstance(doc[k], str | int | float | bool)}
    prog = doc.get("progress")
    if isinstance(prog, dict):
        for k in ("items_out", "data_date", "errors_last_run"):
            if isinstance(prog.get(k), str | int) and not isinstance(prog.get(k), bool):
                facts[k] = prog[k]
    return facts


def summarize(results):
    counts = {k: sum(1 for r in results if r["verdict"] == k) for k in ("FRESH", "STALE", "DOWN", "PAUSED")}
    worst = max((r["verdict"] for r in results), key=lambda v: SEVERITY[v])
    return counts, EXIT[worst]


def format_results(results):
    lines = []
    for r in results:
        lines.append(f"{r['verdict']:<6} {r['name'] or '（沒有 name）'}  {r['path']}")
        for lvl, msg in r["reasons"]:
            lines.append(f"  - [{lvl}] {msg}" if lvl != "info" else f"  - {msg}")
    counts, code = summarize(results)
    n = len(results)
    if code == 0 and not counts["PAUSED"]:
        lines.append(f"stale_check：全部 FRESH（{n} 個狀態檔）")
    elif code == 0:
        lines.append(f"stale_check：沒有 STALE 或 DOWN，但有 {counts['PAUSED']} 個 PAUSED（預期暫停或剛喚醒，不是綠燈；"
                     f"共 {n} 個狀態檔，FRESH {counts['FRESH']} 個）")
    else:
        lines.append(f"stale_check：有 {counts['STALE']} 個 STALE、{counts['DOWN']} 個 DOWN"
                     f"（共 {n} 個狀態檔，FRESH {counts['FRESH']} 個"
                     f"{'，PAUSED ' + str(counts['PAUSED']) + ' 個' if counts['PAUSED'] else ''}）")
    return "\n".join(lines)


def write_self_heartbeat(path, now, period, grace, results, *, name="stale_check", extra=None):
    """規格第 6 條：檢查器跑完就結束，不寫 pid；成功＝這一輪每個檔都檢查完了。

    name、extra 給其他「自己也要被看」的監控者用（例如控制面板的背景巡檢）：extra 是要併進心跳的事實欄位
    （pid、pid_start_ts、build、host、progress…），一樣不准放狀態字。
    """
    counts = summarize(results)[0] if results else {"STALE": 0, "DOWN": 0}
    hb = {
        "spec": SPEC,
        "name": name,
        "last_attempt_ts": now.isoformat(timespec="seconds"),
        "last_success_ts": now.isoformat(timespec="seconds"),
        "expected_period_s": period,
        "grace_s": grace,
        "progress": {"files_checked": len(results), "not_fresh": counts["STALE"] + counts["DOWN"]},
    }
    for k, v in (extra or {}).items():
        if k == "progress" and isinstance(v, dict):
            hb["progress"] = {**hb["progress"], **v}
        elif v is not None:
            hb[k] = v
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    retry(tmp.write_text, json.dumps(hb, ensure_ascii=False, indent=1), encoding="utf-8")
    retry(os.replace, tmp, path)


def run_checks(files, now=None, **opts):
    now = now or datetime.now(UTC)
    return [check_file(f, now, opts) for f in files]


# ---- 自我測試 ----

def selftest():
    failures = []

    def ok(name, cond):
        print(f"{'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    now = datetime.now(UTC)

    def hb(**kw):
        base = {"spec": 1, "name": "demo-bot", "last_attempt_ts": (now - timedelta(minutes=1)).isoformat(),
                "last_success_ts": (now - timedelta(minutes=1)).isoformat(), "expected_period_s": 300, "grace_s": 120}
        base.update(kw)
        return {k: v for k, v in base.items() if v is not None}

    def verdict(doc, **opts):
        reasons = check_doc(doc, now, opts)
        return verdict_of(reasons), reasons

    def said(reasons, text, level=None):
        return any(text in m and (level is None or lvl == level) for lvl, m in reasons)

    def ago(**kw):
        return (now - timedelta(**kw)).isoformat()

    ok("週期加寬限內：FRESH", verdict(hb())[0] == "FRESH")
    ok("超過週期加寬限：STALE", verdict(hb(last_attempt_ts=ago(hours=14), last_success_ts=ago(hours=14)))[0] == "STALE")
    ok("還在嘗試但很久沒成功：STALE", verdict(hb(last_success_ts=ago(hours=14)))[0] == "STALE")
    ok("存了狀態字 running：DOWN", verdict(hb(status="running"))[0] == "DOWN")
    ok("progress 裡的狀態字：DOWN", verdict(hb(progress={"phase": "OK"}))[0] == "DOWN")
    ok("少了 last_success_ts：DOWN", verdict(hb(last_success_ts=None))[0] == "DOWN")
    ok("時間沒有時區：DOWN", verdict(hb(last_success_ts="2026-11-27T10:00:00"))[0] == "DOWN")
    ok("時間是 epoch 數字：DOWN", verdict(hb(last_success_ts=1764212400))[0] == "DOWN")
    ok("last_attempt_ts 晚於現在（時鐘錯亂）：DOWN",
       verdict(hb(last_attempt_ts=(now + timedelta(hours=1)).isoformat()))[0] == "DOWN")
    ok("資料日期落後超過上限：STALE",
       verdict(hb(progress={"data_date": (now - timedelta(days=7)).date().isoformat()}), max_data_age_days=2)[0]
       == "STALE")
    ok("要求資料日期上限但沒有 data_date：DOWN", verdict(hb(), max_data_age_days=2)[0] == "DOWN")
    ok("build 不是預期的版本：DOWN", verdict(hb(build="OLD"), expect_build="NEW")[0] == "DOWN")
    ok("build 短 SHA 前綴相同：不擋", verdict(hb(build="6940d7f"), expect_build="6940d7f1a2b3")[0] == "FRESH")
    ok("週期或寬限是無限大：DOWN", verdict(hb(expected_period_s=float("inf")))[0] == "DOWN"
       and verdict(hb(grace_s=float("inf")))[0] == "DOWN")
    ok("巢狀物件、陣列、混合大小寫的狀態字：DOWN", all(verdict(hb(**kw))[0] == "DOWN" for kw in (
        {"x_meta": {"status": "running"}}, {"x_tags": ["Healthy"]}, {"progress": {"X_Ok": 1}})))
    ok("pid 超出 32 位元：DOWN，不截斷", verdict(hb(pid=2**32 + os.getpid()))[0] == "DOWN"
       and process_info(2**32 + os.getpid())[0] == "dead")
    ok("--started-after 卻沒有 pid：DOWN（--skip-pid 才放過）",
       verdict(hb(pid_start_ts=ago(minutes=5)), started_after=now - timedelta(minutes=10))[0] == "DOWN"
       and verdict(hb(pid_start_ts=ago(minutes=5)), started_after=now - timedelta(minutes=10), skip_pid=True)[0]
       == "FRESH")

    # ---- 2026-11-28 補強 7 項：每項都有正向（該放過的放過）與負向（該抓的抓到） ----
    ten_years = 10 * 365 * 86400
    liar = hb(expected_period_s=ten_years, last_attempt_ts=ago(days=3), last_success_ts=ago(days=3))
    v, rs = verdict(liar, override_period_s=3600, override_grace_s=600)
    ok("1 讀取方覆寫：自報週期 10 年、3 天沒成功，讀取方期望 1 小時：STALE 並註明檔案自報",
       verdict(liar)[0] == "FRESH" and v == "STALE" and said(rs, "已套用讀取方期望（檔案自報"))
    v, rs = verdict(hb(), override_period_s=300, override_grace_s=120)
    ok("1 讀取方覆寫：期望跟自報一樣時不多話，照樣 FRESH", v == "FRESH" and not said(rs, "已套用讀取方期望"))
    ok("1 讀取方覆寫：覆寫值不合法（0、無限大）：DOWN", verdict(hb(), override_period_s=0)[0] == "DOWN"
       and verdict(hb(), override_grace_s=float("inf"))[0] == "DOWN")

    stuck = hb(expected_period_s=86400, grace_s=3600, last_success_ts=ago(hours=5), last_attempt_ts=ago(hours=2))
    v, rs = verdict(stuck, max_run_s=1800)
    ok("2 啟動後卡死：2 小時前開始、上限 30 分鐘還沒成功：STALE", verdict(stuck)[0] == "FRESH" and v == "STALE"
       and said(rs, "任務啟動後逾時疑似卡死", "STALE"))
    ok("2 啟動後卡死：狀態檔自己寫 max_run_s 也算，讀取方的值優先",
       verdict({**stuck, "max_run_s": 1800})[0] == "STALE" and verdict({**stuck, "max_run_s": 1800}, max_run_s=86400)[0]
       == "FRESH")
    ok("2 啟動後卡死：還在上限內、或這一輪已經成功：不擋", verdict(stuck, max_run_s=3 * 3600)[0] == "FRESH"
       and verdict(hb(), max_run_s=1)[0] == "FRESH")
    ok("2 啟動後卡死：max_run_s 不是正數：DOWN", verdict({**stuck, "max_run_s": 0})[0] == "DOWN")

    v, rs = verdict(hb(progress={"items_out": 0}), min_items_out=1)
    ok("3 產出量下限：exit 0 但寫出 0 筆：STALE", v == "STALE" and said(rs, "產出筆數低於下限", "STALE"))
    ok("3 產出量下限：設了下限卻沒有 items_out：STALE", verdict(hb(), min_items_out=1)[0] == "STALE"
       and verdict(hb(min_items_out=5, progress={"errors_last_run": 0}))[0] == "STALE")
    ok("3 產出量下限：筆數達標：FRESH", verdict(hb(progress={"items_out": 412}), min_items_out=100)[0] == "FRESH"
       and verdict(hb(min_items_out=5, progress={"items_out": 5}))[0] == "FRESH")
    ok("3 產出量下限：min_items_out 不是 0 以上的整數：DOWN", verdict(hb(min_items_out=-1))[0] == "DOWN"
       and verdict(hb(min_items_out=1.5))[0] == "DOWN")

    overdue = hb(last_attempt_ts=ago(hours=14), last_success_ts=ago(hours=14))
    v, rs = verdict(overdue, wake_grace_remaining_s=150)
    ok("4 喚醒寬限：只因超時的 STALE 降成 PAUSED，不亮假紅燈", v == "PAUSED" and said(rs, "系統剛自休眠喚醒緩衝中", "PAUSED"))
    ok("4 喚醒寬限：緩衝用完（0 秒）就恢復 STALE", verdict(overdue, wake_grace_remaining_s=0)[0] == "STALE")
    ok("4 喚醒寬限：不蓋掉別的問題（產出不足照樣 STALE、狀態字照樣 DOWN）",
       verdict({**overdue, "progress": {"items_out": 0}}, wake_grace_remaining_s=150, min_items_out=1)[0] == "STALE"
       and verdict({**overdue, "status": "running"}, wake_grace_remaining_s=150)[0] == "DOWN")
    ok("4 喚醒寬限：本來就 FRESH 的不會變 PAUSED", verdict(hb(), wake_grace_remaining_s=150)[0] == "FRESH")

    gone_pid = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True,
                              check=True)
    dead_pid = int(gone_pid.stdout.strip())
    v, rs = verdict(hb(pid=dead_pid, host="Some-Other-Box"), local_host="this-box")
    ok("5 跨機：host 不是這台，pid 在這台查不到也不判 DOWN", v == "FRESH" and said(rs, "遠端主機 Some-Other-Box"))
    ok("5 跨機：host 就是這台（不分大小寫）照樣查 pid：DOWN",
       verdict(hb(pid=dead_pid, host="THIS-BOX"), local_host="this-box")[0] == "DOWN"
       and verdict(hb(pid=dead_pid, host=socket.gethostname().upper()))[0] == "DOWN")
    ok("5 跨機：host 是空字串或不是字串：DOWN", verdict(hb(host=" "))[0] == "DOWN" and verdict(hb(host=7))[0] == "DOWN")

    paused = {**overdue, "paused_until_ts": (now + timedelta(hours=6)).isoformat()}
    v, rs = verdict(paused)
    ok("6 預期暫停：還沒到 paused_until_ts：PAUSED，不是 STALE 也不是 FRESH",
       v == "PAUSED" and said(rs, "預期暫停到", "PAUSED"))
    ok("6 預期暫停：期限已過自動恢復嚴格判定：STALE",
       verdict({**overdue, "paused_until_ts": ago(minutes=5)})[0] == "STALE")
    ok("6 預期暫停：暫停中行程不在也算預期（PAUSED），期限過了就是 DOWN",
       verdict({**paused, "pid": dead_pid})[0] == "PAUSED"
       and verdict({**overdue, "pid": dead_pid, "paused_until_ts": ago(minutes=5)})[0] == "DOWN")
    ok("6 預期暫停：存 paused: true 這種狀態字或多餘欄位：DOWN", verdict(hb(paused=True))[0] == "DOWN"
       and verdict({**paused, "status": "paused", "x_state": "ok"})[0] == "DOWN")
    ok("6 預期暫停：沒帶時區：DOWN；寫 10 年後：不採信，照常 STALE",
       verdict({**overdue, "paused_until_ts": "2099-01-01T00:00:00"})[0] == "DOWN"
       and verdict({**overdue, "paused_until_ts": (now + timedelta(days=3650)).isoformat()})[0] == "STALE")
    ok("6 預期暫停：沒過期的心跳在暫停期間也不顯示成 FRESH", verdict({**hb(), "paused_until_ts": paused["paused_until_ts"]})[0]
       == "PAUSED")

    v, rs = verdict(hb(x_dirty=True))
    ok("7 未提交改動：x_dirty 是 true 時附註事實，不改判定", v == "FRESH" and said(rs, "執行工作樹含未提交改動", "info"))
    ok("7 未提交改動：x_dirty 是 false 或沒寫：不附註",
       not said(verdict(hb(x_dirty=False))[1], "未提交改動") and not said(verdict(hb())[1], "未提交改動"))

    me = os.getpid()
    state, started, _ = process_info(me)
    ok(f"查得到自己這個行程的啟動時間（{sys.platform}）", state == "alive" and started is not None)
    if started is not None:
        ok("pid 在跑、啟動時間對得上：FRESH", verdict(hb(pid=me, pid_start_ts=started.isoformat()))[0] == "FRESH")
        ok("pid 在跑、啟動時間差 6 天：DOWN",
           verdict(hb(pid=me, pid_start_ts=(started - timedelta(days=6)).isoformat()))[0] == "DOWN")
        ok("行程是部署前就在跑的那一個：DOWN",
           verdict(hb(pid=me, pid_start_ts=started.isoformat()), started_after=now)[0] == "DOWN")
    gone = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True,
                          check=True)
    dead = int(gone.stdout.strip())
    v, reasons = verdict(hb(pid=dead))
    ok("pid 不存在：DOWN", v == "DOWN" and any("不存在" in m for _, m in reasons))

    with tempfile.TemporaryDirectory(prefix="stale_check-") as td:
        base = Path(td)
        good = base / "good.json"
        good.write_text(json.dumps(hb()), encoding="utf-8")
        old = base / "old.json"
        old.write_text(json.dumps(hb(last_attempt_ts=ago(days=6), last_success_ts=ago(days=6))), encoding="utf-8")
        broken = base / "broken.json"
        broken.write_text("{oops", encoding="utf-8")
        res = run_checks([good, old, broken, base / "missing.json"], now=now)
        ok("讀不到檔、不是 JSON：DOWN", [r["verdict"] for r in res] == ["FRESH", "STALE", "DOWN", "DOWN"])
        inf = base / "inf.json"
        inf.write_text(json.dumps(hb(x_ratio="__RAW__")).replace('"__RAW__"', "NaN"), encoding="utf-8")
        ok("NaN、Infinity 不是標準 JSON：DOWN", run_checks([inf], now=now)[0]["verdict"] == "DOWN")
        text = format_results(res)
        ok("有 DOWN 時結束碼 2，結論在最後一行、沒有「全部 FRESH」",
           summarize(res)[1] == 2 and text.splitlines()[-1].startswith("stale_check：有 1 個 STALE、2 個 DOWN")
           and "全部 FRESH" not in text)
        ok("只有 STALE 時結束碼 1", summarize(run_checks([good, old], now=now))[1] == 1)
        ok("全部 FRESH 才 exit 0，成功字樣在最後一行",
           summarize(run_checks([good], now=now))[1] == 0
           and format_results(run_checks([good], now=now)).splitlines()[-1].startswith("stale_check：全部 FRESH"))
        napping = base / "napping.json"
        napping.write_text(json.dumps(paused), encoding="utf-8")
        res_p = run_checks([good, napping], now=now)
        last = format_results(res_p).splitlines()[-1]
        ok("有 PAUSED 時結束碼 0，但結論不說「全部 FRESH」",
           [r["verdict"] for r in res_p] == ["FRESH", "PAUSED"] and summarize(res_p)[1] == 0
           and "全部 FRESH" not in last and "1 個 PAUSED" in last)
        ok("舊格式的心跳檔（沒有新欄位）判定不變，並帶出原始事實",
           run_checks([good], now=now)[0]["verdict"] == "FRESH"
           and run_checks([good], now=now)[0]["facts"].get("expected_period_s") == 300)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_o = main([str(old), "--override-period-s", str(30 * 86400)])
            rc_w = main([str(old), "--wake-grace-remaining-s", "120"])
            rc_m = main([str(good), "--min-items-out", "1"])
        ok("CLI：--override-period-s 放寬後 exit 0；--wake-grace-remaining-s 降成 PAUSED exit 0；--min-items-out 抓空跑 exit 1",
           (rc_o, rc_w, rc_m) == (0, 0, 1))
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc_bad = main([str(good), "--override-period-s", "0"])
        ok("CLI：--override-period-s 0 是用法錯誤", rc_bad == EXIT_USAGE)

        own = base / "self" / "stale_check.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([str(good), "--self-heartbeat", str(own), "--self-period-s", "3600"])
        ok("檢查器寫自己的心跳，同一支檢查器看得懂", rc == 0 and own.is_file()
           and run_checks([own])[0]["verdict"] == "FRESH")
        other = base / "self" / "poller.json"
        write_self_heartbeat(other, now, 60, 120, [], name="demo-poller",
                             extra={"pid": me, "pid_start_ts": started.isoformat() if started else None,
                                    "host": socket.gethostname(), "progress": {"items_out": 3}})
        doc_o = json.loads(other.read_text(encoding="utf-8"))
        ok("其他監控者借用同一個寫法（name、pid、host、產出數），同一支檢查器看得懂",
           doc_o["name"] == "demo-poller" and doc_o["progress"]["items_out"] == 3
           and run_checks([other], min_items_out=1)[0]["verdict"] == "FRESH")

    print(f"\nstale_check.py selftest：{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(AttributeError, ValueError):
                stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="由讀取方判定的心跳檢查器：每個狀態檔輸出 FRESH、STALE、DOWN 或 PAUSED，"
                                             "沒有 STALE、DOWN 才 exit 0")
    ap.add_argument("files", nargs="*", help="心跳狀態檔（格式見 engine/schema/heartbeat.schema.json）")
    ap.add_argument("--expect-build", help="build 要等於這個版本")
    ap.add_argument("--started-after", help="部署開始時間（ISO 8601 帶時區）：行程要在這之後啟動、之後有成功紀錄")
    ap.add_argument("--max-data-age-days", type=float, help="progress.data_date 最多落後幾天")
    ap.add_argument("--skip-pid", action="store_true", help="不查 pid（狀態檔來自別台機器時）")
    ap.add_argument("--override-period-s", type=float, help="讀取方期望的週期（秒）：優先於狀態檔自報的 expected_period_s")
    ap.add_argument("--override-grace-s", type=float, help="讀取方期望的寬限（秒）：優先於狀態檔自報的 grace_s")
    ap.add_argument("--max-run-s", type=float, help="開始嘗試後最多可以跑多久（秒）；超過還沒成功判 STALE（啟動後卡死）")
    ap.add_argument("--min-items-out", type=int, help="progress.items_out 的下限；低於或沒有這個欄位判 STALE（exit 0 空跑）")
    ap.add_argument("--wake-grace-remaining-s", type=float, default=0.0,
                    help="系統剛從休眠醒來、還剩幾秒緩衝：大於 0 時只因超時的 STALE 降成 PAUSED（預設 0）")
    ap.add_argument("--pid-start-tolerance-s", type=float, default=PID_START_TOLERANCE_S,
                    help=f"啟動時間差多少秒內算對得上（預設 {PID_START_TOLERANCE_S}）")
    ap.add_argument("--now", help="測試用：把現在時間固定成這個（ISO 8601 帶時區）")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--self-heartbeat", help="檢查完把檢查器自己的心跳寫到這個檔")
    ap.add_argument("--self-period-s", type=float, default=3600, help="檢查器自己多久跑一次（預設 3600）")
    ap.add_argument("--self-grace-s", type=float, default=300, help="檢查器自己的寬限（預設 300）")
    ap.add_argument("--selftest", action="store_true", help="離線自我測試")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.files:
        print("stale_check：至少要一個狀態檔。用法：stale_check.py <狀態檔…>", file=sys.stderr)
        return EXIT_USAGE
    now = datetime.now(UTC)
    if args.now:
        now, err = parse_ts(args.now)
        if err:
            print(f"stale_check：--now {err}", file=sys.stderr)
            return EXIT_USAGE
    started_after = None
    if args.started_after:
        started_after, err = parse_ts(args.started_after)
        if err:
            print(f"stale_check：--started-after {err}", file=sys.stderr)
            return EXIT_USAGE
    for flag, value in (("--max-data-age-days", args.max_data_age_days),
                        ("--pid-start-tolerance-s", args.pid_start_tolerance_s),
                        ("--self-period-s", args.self_period_s), ("--self-grace-s", args.self_grace_s),
                        ("--override-period-s", args.override_period_s), ("--override-grace-s", args.override_grace_s),
                        ("--max-run-s", args.max_run_s), ("--wake-grace-remaining-s", args.wake_grace_remaining_s)):
        if value is not None and not math.isfinite(value):
            print(f"stale_check：{flag} 要是有限的數字，拿到 {value}", file=sys.stderr)
            return EXIT_USAGE
    for flag, value, ok in (("--override-period-s", args.override_period_s, lambda v: v > 0),
                            ("--override-grace-s", args.override_grace_s, lambda v: v >= 0),
                            ("--max-run-s", args.max_run_s, lambda v: v > 0),
                            ("--min-items-out", args.min_items_out, lambda v: v >= 0),
                            ("--wake-grace-remaining-s", args.wake_grace_remaining_s, lambda v: v >= 0)):
        if value is not None and not ok(value):
            print(f"stale_check：{flag} 的值不合法：{value}", file=sys.stderr)
            return EXIT_USAGE
    if args.max_data_age_days is not None and args.max_data_age_days < 0:
        print("stale_check：--max-data-age-days 要是 0 以上", file=sys.stderr)
        return EXIT_USAGE

    # 全部檢查跑完才印任何東西（規格第 5 條）
    results = run_checks(args.files, now=now, expect_build=args.expect_build, started_after=started_after,
                         max_data_age_days=args.max_data_age_days, skip_pid=args.skip_pid,
                         pid_tolerance_s=args.pid_start_tolerance_s,
                         override_period_s=args.override_period_s, override_grace_s=args.override_grace_s,
                         max_run_s=args.max_run_s, min_items_out=args.min_items_out,
                         wake_grace_remaining_s=args.wake_grace_remaining_s)
    counts, code = summarize(results)
    if args.self_heartbeat:
        write_self_heartbeat(args.self_heartbeat, now, args.self_period_s, args.self_grace_s, results)
    if args.json:
        out = [{**r, "reasons": [{"level": lvl, "text": msg} for lvl, msg in r["reasons"]]} for r in results]
        print(json.dumps({"results": out, "counts": counts, "exit": code}, ensure_ascii=False, indent=1))
    else:
        print(format_results(results))
    return code


if __name__ == "__main__":
    sys.exit(main())
