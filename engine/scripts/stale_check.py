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
- DOWN：讀不到檔、不是 JSON、欄位缺、時間解析失敗或沒帶時區、pid 不存在、pid 啟動時間對不上、
  時鐘錯亂（last_attempt_ts 晚於現在）、存了狀態字、build 不是預期的版本、行程是部署前就在跑的那一個。

用法：
  uv run engine/scripts/stale_check.py <狀態檔…> [--expect-build <build>] [--started-after <ISO 時間>]
      [--max-data-age-days <天>] [--skip-pid] [--json] [--self-heartbeat <檔> --self-period-s <秒>]
  uv run engine/scripts/stale_check.py --selftest

  --expect-build    build 要等於這個（兩邊都是 7 碼以上十六進位時，前綴相同就算）
  --started-after   部署開始時間：pid_start_ts 要晚於它，last_success_ts 也要晚於它
  --max-data-age-days  progress.data_date 最多落後幾天（狀態檔的 max_data_age_days 也算，這裡優先）
  --skip-pid        不查 pid（狀態檔來自別台機器時）；輸出會註明沒查
  --now             測試用：把「現在」固定成這個時間；pid 照樣查這台的真實行程
  --self-heartbeat  檢查完把檢查器自己的心跳寫到這個檔（規格第 6 條），給另一個觸發點用同一支檢查器看

結束碼：0 全部 FRESH；1 有 STALE、沒有 DOWN；2 有 DOWN，或用法錯誤。
每個檔的結果與結論都在全部檢查跑完之後才印，結論在最後一行。
"""
import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fsretry import retry  # 防毒短暫鎖住檔案時等一下再試（FR-34）

SPEC = 1
REQUIRED = ("spec", "name", "last_attempt_ts", "last_success_ts", "expected_period_s", "grace_s")
OPTIONAL = ("pid", "pid_start_ts", "build", "progress", "max_data_age_days")
# 規格第 1 條：這些欄位名稱與值都是「狀態字」，由做事那方寫的就不能信（不分大小寫；跟規格檔的 $defs 一致，測試會比對）
STATUS_KEYS = ("status", "state", "health", "healthy", "ok", "running", "alive", "up", "success", "verified", "passes")
STATUS_WORDS = ("running", "ok", "healthy", "alive", "green", "success", "succeeded", "online", "ready", "verified",
                "passing", "passed")
SEVERITY = {"FRESH": 0, "STALE": 1, "DOWN": 2}
EXIT = {"FRESH": 0, "STALE": 1, "DOWN": 2}
EXIT_USAGE = 2
CLOCK_SKEW_S = 60          # 時間晚於現在超過這麼多秒才算時鐘錯亂
ORDER_SLACK_S = 1          # last_success_ts 晚於 last_attempt_ts 不到 1 秒當成同一次寫入
PID_START_TOLERANCE_S = 60  # 狀態檔記的啟動時間與系統的差多少秒以內算對得上（程式通常啟動後才記）


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
    return isinstance(v, int | float) and not isinstance(v, bool)


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
    if sys.platform == "win32":
        return _win_process(pid)
    if Path("/proc/self/stat").exists():
        return _linux_process(pid)
    return _ps_process(pid)


# ---- 檢查一個狀態檔 ----

def _status_words(doc):
    """規格第 1 條：找出狀態字（欄位名稱或值）。回傳說明字串清單。"""
    found = []

    def key_hit(k):
        return k.removeprefix("x_").lower() in STATUS_KEYS

    def val_hit(v):
        return isinstance(v, str) and v.strip().lower() in STATUS_WORDS

    for k, v in doc.items():
        if k in ("name", "build"):
            continue
        if key_hit(k) or ((k.startswith("x_") or k not in REQUIRED + OPTIONAL) and val_hit(v)):
            found.append(f"{k}={json.dumps(v, ensure_ascii=False)}")
    prog = doc.get("progress")
    if isinstance(prog, dict):
        for k, v in prog.items():
            if key_hit(k) or val_hit(v):
                found.append(f"progress.{k}={json.dumps(v, ensure_ascii=False)}")
    return found


def _build_matches(actual, expected):
    a, e = actual.strip().lower(), expected.strip().lower()
    if a == e:
        return True
    hexchars = set("0123456789abcdef")
    if len(a) >= 7 and len(e) >= 7 and set(a) <= hexchars and set(e) <= hexchars:
        return a.startswith(e) or e.startswith(a)
    return False


def check_doc(doc, now, opts):
    """回傳 reasons：[(等級, 說明)]，等級是 DOWN、STALE 或 info。"""
    reasons = []

    def down(msg):
        reasons.append(("DOWN", msg))

    def stale(msg):
        reasons.append(("STALE", msg))

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

    if success and period is not None and grace is not None:
        age = (now - success).total_seconds()
        limit = period + grace
        when = f"上次成功是 {human(age)}前（{doc['last_success_ts']}）"
        if age > limit:
            stale(f"{when}，超過週期 {period:g} 秒加寬限 {grace:g} 秒")
        else:
            info(f"{when}，在週期 {period:g} 秒加寬限 {grace:g} 秒內")
    if attempt and success and attempt > success:
        info(f"上次嘗試是 {human((now - attempt).total_seconds())}前（{doc['last_attempt_ts']}）")

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
                    stale(f"資料最新日期 {raw}，落後 {lag} 天，超過上限 {max_age:g} 天（exit 0 不算數，看產出）")
                else:
                    info(f"資料最新日期 {raw}（落後 {lag} 天）")

    # 規格第 3 條：pid 與啟動時間由讀的一方向系統查證
    pid = doc.get("pid")
    recorded_start = ts.get("pid_start_ts")
    verified_start = False
    if "pid" in doc:
        if not (isinstance(pid, int) and not isinstance(pid, bool) and pid > 0):
            down(f"pid 要是正整數：{pid!r}")
        elif opts.get("skip_pid"):
            info(f"沒查 pid {pid}（--skip-pid）")
        else:
            state, actual, note = process_info(pid)
            if state == "dead":
                down(f"pid {pid} 不存在（行程已結束{'，' + note if note else ''}）")
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
            elif not verified_start:
                info("pid_start_ts 沒有向系統查證（沒有 pid、--skip-pid 或查不到）")
        if success and success <= after:
            stale(f"部署開始（{after.isoformat(timespec='seconds')}）之後還沒有成功紀錄")
    return reasons


def check_file(path, now, opts):
    path = Path(path)
    result = {"path": str(path), "name": None, "verdict": "DOWN", "reasons": []}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        result["reasons"] = [("DOWN", f"讀不到狀態檔：{e}")]
        return result
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        result["reasons"] = [("DOWN", f"不是合法的 JSON：{e}")]
        return result
    if isinstance(doc, dict) and isinstance(doc.get("name"), str):
        result["name"] = doc["name"]
    try:
        reasons = check_doc(doc, now, opts)
    except Exception as e:  # noqa: BLE001  檢查器自己出錯也不能當正常
        reasons = [("DOWN", f"檢查器例外：{type(e).__name__}: {e}")]
    order = {"DOWN": 0, "STALE": 1, "info": 2}
    reasons.sort(key=lambda r: order[r[0]])
    levels = {lvl for lvl, _ in reasons}
    result["verdict"] = "DOWN" if "DOWN" in levels else "STALE" if "STALE" in levels else "FRESH"
    result["reasons"] = reasons
    return result


def summarize(results):
    counts = {k: sum(1 for r in results if r["verdict"] == k) for k in ("FRESH", "STALE", "DOWN")}
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
    if code == 0:
        lines.append(f"stale_check：全部 FRESH（{n} 個狀態檔）")
    else:
        lines.append(f"stale_check：有 {counts['STALE']} 個 STALE、{counts['DOWN']} 個 DOWN"
                     f"（共 {n} 個狀態檔，FRESH {counts['FRESH']} 個）")
    return "\n".join(lines)


def write_self_heartbeat(path, now, period, grace, results):
    """規格第 6 條：檢查器跑完就結束，不寫 pid；成功＝這一輪每個檔都檢查完了。"""
    counts, _ = summarize(results)
    hb = {
        "spec": SPEC,
        "name": "stale_check",
        "last_attempt_ts": now.isoformat(timespec="seconds"),
        "last_success_ts": now.isoformat(timespec="seconds"),
        "expected_period_s": period,
        "grace_s": grace,
        "progress": {"files_checked": len(results), "not_fresh": counts["STALE"] + counts["DOWN"]},
    }
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
        levels = {lvl for lvl, _ in reasons}
        return ("DOWN" if "DOWN" in levels else "STALE" if "STALE" in levels else "FRESH"), reasons

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
        text = format_results(res)
        ok("有 DOWN 時結束碼 2，結論在最後一行、沒有「全部 FRESH」",
           summarize(res)[1] == 2 and text.splitlines()[-1].startswith("stale_check：有 1 個 STALE、2 個 DOWN")
           and "全部 FRESH" not in text)
        ok("只有 STALE 時結束碼 1", summarize(run_checks([good, old], now=now))[1] == 1)
        ok("全部 FRESH 才 exit 0，成功字樣在最後一行",
           summarize(run_checks([good], now=now))[1] == 0
           and format_results(run_checks([good], now=now)).splitlines()[-1].startswith("stale_check：全部 FRESH"))

        own = base / "self" / "stale_check.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([str(good), "--self-heartbeat", str(own), "--self-period-s", "3600"])
        ok("檢查器寫自己的心跳，同一支檢查器看得懂", rc == 0 and own.is_file()
           and run_checks([own])[0]["verdict"] == "FRESH")

    print(f"\nstale_check.py selftest：{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            with contextlib.suppress(AttributeError, ValueError):
                stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="由讀取方判定的心跳檢查器：每個狀態檔輸出 FRESH、STALE 或 DOWN，全部 FRESH 才 exit 0")
    ap.add_argument("files", nargs="*", help="心跳狀態檔（格式見 engine/schema/heartbeat.schema.json）")
    ap.add_argument("--expect-build", help="build 要等於這個版本")
    ap.add_argument("--started-after", help="部署開始時間（ISO 8601 帶時區）：行程要在這之後啟動、之後有成功紀錄")
    ap.add_argument("--max-data-age-days", type=float, help="progress.data_date 最多落後幾天")
    ap.add_argument("--skip-pid", action="store_true", help="不查 pid（狀態檔來自別台機器時）")
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
    if args.max_data_age_days is not None and args.max_data_age_days < 0:
        print("stale_check：--max-data-age-days 要是 0 以上", file=sys.stderr)
        return EXIT_USAGE

    # 全部檢查跑完才印任何東西（規格第 5 條）
    results = run_checks(args.files, now=now, expect_build=args.expect_build, started_after=started_after,
                         max_data_age_days=args.max_data_age_days, skip_pid=args.skip_pid,
                         pid_tolerance_s=args.pid_start_tolerance_s)
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
