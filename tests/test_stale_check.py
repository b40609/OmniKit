"""由讀取方判定的心跳（engine/scripts/stale_check.py、engine/schema/heartbeat.schema.json）的 pytest。

D10 改動 2：做事的程式自己寫「running」「ok」，行程死了、斷線了、資料沒進來，狀態檔照樣說正常。
規格改成狀態檔只存事實與時間，正不正常由讀的一方算：FRESH、STALE、DOWN，全部 FRESH 才 exit 0。

前 4 個是設計裡的重現測試（案例泛化成 demo-bot、daily-job），其餘是邊界。
用到真實行程（pid 與啟動時間）的測試用現在時間；其餘用固定的 --now，結果不受執行時間影響。
"""
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "engine" / "scripts" / "stale_check.py"
SCHEMA = ROOT / "engine" / "schema" / "heartbeat.schema.json"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 27, 12, 0, 0, tzinfo=TPE)
DROP = object()


def iso(dt):
    return dt.isoformat(timespec="seconds")


def heartbeat(name="demo-bot", **fields):
    base = {
        "spec": 1,
        "name": name,
        "last_attempt_ts": iso(NOW - timedelta(minutes=1)),
        "last_success_ts": iso(NOW - timedelta(minutes=1)),
        "expected_period_s": 300,
        "grace_s": 120,
    }
    base.update(fields)
    return {k: v for k, v in base.items() if v is not DROP}


def write(tmp_path, filename="heartbeat.json", **fields):
    f = tmp_path / filename
    f.write_text(json.dumps(heartbeat(**fields), ensure_ascii=False), encoding="utf-8")
    return f


def run(*args, now=NOW):
    extra = ["--now", iso(now)] if now is not None else []
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args), *extra], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV, timeout=120, check=False)


def verdict_lines(stdout):
    return [ln for ln in stdout.splitlines() if ln.startswith(("FRESH", "STALE", "DOWN"))]


def dead_pid():
    """一個剛結束的行程的 pid。"""
    r = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True,
                       check=True)
    return int(r.stdout.strip())


@pytest.fixture
def live_process():
    """背景跑一個會活 60 秒的行程，回傳 (pid, 它自己記下的啟動時間)。像真的程式一樣，啟動時間由做事那方在啟動時記下。"""
    procs = []

    def start():
        t0 = datetime.now(UTC)
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        procs.append(p)
        return p.pid, t0

    yield start
    for p in procs:
        p.kill()
        p.wait(timeout=10)


# ---- 設計的 4 個重現測試 ----

def test_dead_process_but_status_file_still_says_running(tmp_path):
    """行程已死 6 天，狀態檔仍寫 running：不能讀狀態字，要由時間差與 pid 判定。"""
    f = write(tmp_path, status="running", last_attempt_ts=iso(NOW - timedelta(days=6)),
              last_success_ts=iso(NOW - timedelta(days=6)), pid=dead_pid(),
              pid_start_ts=iso(NOW - timedelta(days=7)))
    r = run(f)
    assert r.returncode != 0, r.stdout + r.stderr
    assert "STALE" in r.stdout                        # 訊號：時間差超過週期加寬限
    assert verdict_lines(r.stdout)[0].startswith("DOWN")  # 規格第 3 條：pid 不存在一律 DOWN，比 STALE 嚴重
    assert "不存在" in r.stdout
    assert "狀態字" in r.stdout                        # 規格第 1 條：狀態檔不准存狀態字
    assert "全部 FRESH" not in r.stdout


def test_watchdog_returns_zero_during_outage(tmp_path):
    """斷線 13.8 小時：watchdog 還在嘗試（last_attempt 很新），但最後一次成功是 13.8 小時前。"""
    f = write(tmp_path, last_attempt_ts=iso(NOW - timedelta(minutes=2)),
              last_success_ts=iso(NOW - timedelta(hours=13.8)))
    r = run(f)
    assert r.returncode != 0, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("STALE")
    assert "13 小時" in r.stdout


def test_exit_zero_but_data_date_behind(tmp_path):
    """每日工作 exit 0、last_success 很新，但資料最新日期停在 7 天前：看產出，不看 exit code。"""
    f = write(tmp_path, name="daily-job", progress={"items_out": 0, "data_date": "2026-11-20"}, max_data_age_days=2)
    r = run(f)
    assert r.returncode != 0, r.stdout + r.stderr
    assert "STALE" in r.stdout                        # 訊號：資料日期落後
    assert "2026-11-20" in r.stdout

    g = write(tmp_path, "cli.json", name="daily-job", progress={"data_date": "2026-11-20"})
    r = run(g, "--max-data-age-days", 2)              # 上限也可以由讀的一方指定
    assert r.returncode != 0 and verdict_lines(r.stdout)[0].startswith("STALE"), r.stdout + r.stderr

    h = write(tmp_path, "ok.json", name="daily-job", progress={"data_date": "2026-11-27"}, max_data_age_days=2)
    r = run(h)
    assert r.returncode == 0, r.stdout + r.stderr


def test_deploy_reports_verified_but_build_unchanged(tmp_path, live_process):
    """部署腳本說已上線，但跑的還是舊 build、行程也是部署前就在跑的那一個。"""
    pid, started = live_process()
    time.sleep(1.5)
    deploy_start = datetime.now(UTC)
    now = datetime.now(UTC)
    f = write(tmp_path, build="OLD", pid=pid, pid_start_ts=iso(started),
              last_attempt_ts=iso(now), last_success_ts=iso(now))
    r = run(f, "--expect-build", "NEW", "--started-after", iso(deploy_start), now=None)
    assert r.returncode != 0, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "build" in r.stdout and "OLD" in r.stdout
    assert "部署" in r.stdout

    # 對照：部署之後才啟動、帶新 build、部署後有成功紀錄的行程，才是真的上線
    before_new = datetime.now(UTC) - timedelta(seconds=1)
    pid2, started2 = live_process()
    now2 = datetime.now(UTC)
    g = write(tmp_path, "new.json", build="NEW", pid=pid2, pid_start_ts=iso(started2),
              last_attempt_ts=iso(now2), last_success_ts=iso(now2))
    r = run(g, "--expect-build", "NEW", "--started-after", iso(before_new), now=None)
    assert r.returncode == 0, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("FRESH")


# ---- DOWN：讀不到、欄位缺、時間錯、pid 不符、時鐘錯亂 ----

def test_unreadable_file_is_down(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = run(tmp_path / "missing.json", bad)
    assert r.returncode == 2, r.stdout + r.stderr
    v = verdict_lines(r.stdout)
    assert len(v) == 2 and all(x.startswith("DOWN") for x in v)


@pytest.mark.parametrize("field", ["spec", "name", "last_attempt_ts", "last_success_ts", "expected_period_s", "grace_s"])
def test_missing_required_field_is_down(tmp_path, field):
    f = write(tmp_path, **{field: DROP})
    r = run(f)
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert field in r.stdout


@pytest.mark.parametrize("value", ["yesterday", "2026-11-27T10:00:00", "2026-13-01T00:00:00+08:00", 1764212400])
def test_bad_or_naive_timestamp_is_down(tmp_path, value):
    f = write(tmp_path, last_success_ts=value)
    r = run(f)
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")


def test_clock_skew_attempt_in_future_is_down(tmp_path):
    f = write(tmp_path, last_attempt_ts=iso(NOW + timedelta(hours=1)))
    r = run(f)
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "晚於現在" in r.stdout


def test_success_after_attempt_is_down(tmp_path):
    f = write(tmp_path, last_attempt_ts=iso(NOW - timedelta(minutes=10)), last_success_ts=iso(NOW - timedelta(minutes=1)))
    r = run(f)
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")


def test_pid_alive_but_start_time_mismatch_is_down(tmp_path, live_process):
    """pid 還在，但啟動時間對不上（pid 被別的行程重用，或是重開過）。"""
    pid, _ = live_process()
    now = datetime.now(UTC)
    f = write(tmp_path, pid=pid, pid_start_ts=iso(now - timedelta(days=6)),
              last_attempt_ts=iso(now), last_success_ts=iso(now))
    r = run(f, now=None)
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "啟動時間" in r.stdout


def test_fresh_heartbeat_with_live_pid_exits_zero(tmp_path, live_process):
    pid, started = live_process()
    now = datetime.now(UTC)
    f = write(tmp_path, pid=pid, pid_start_ts=iso(started), last_attempt_ts=iso(now), last_success_ts=iso(now),
              build="6940d7f", progress={"items_out": 412, "data_date": now.date().isoformat(), "errors_last_run": 0})
    r = run(f, now=None)
    assert r.returncode == 0, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("FRESH")


# ---- 規格第 1 條：狀態字 ----

@pytest.mark.parametrize("fields", [
    {"status": "ok"}, {"state": "running"}, {"healthy": True}, {"progress": {"health": "green"}},
    {"progress": {"phase": "running"}},
])
def test_status_words_are_rejected_even_when_fresh(tmp_path, fields):
    f = write(tmp_path, **fields)
    r = run(f)
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "狀態字" in r.stdout


# ---- 規格第 5 條：全部 FRESH 才 exit 0，成功字樣最後才印 ----

def test_one_stale_file_fails_the_whole_run(tmp_path):
    good = write(tmp_path, "good.json", name="demo-bot")
    stale = write(tmp_path, "stale.json", name="daily-job", last_attempt_ts=iso(NOW - timedelta(hours=2)),
                  last_success_ts=iso(NOW - timedelta(hours=2)))
    r = run(good, stale)
    assert r.returncode == 1, r.stdout + r.stderr
    v = verdict_lines(r.stdout)
    assert v[0].startswith("FRESH") and v[1].startswith("STALE")
    assert "全部 FRESH" not in r.stdout
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert lines[-1].startswith("stale_check：")      # 結論只在最後一行


def test_all_fresh_summary_is_last_line(tmp_path):
    a = write(tmp_path, "a.json", name="demo-bot")
    b = write(tmp_path, "b.json", name="daily-job", expected_period_s=86400, grace_s=3600,
              last_attempt_ts=iso(NOW - timedelta(hours=20)), last_success_ts=iso(NOW - timedelta(hours=20)))
    r = run(a, b)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert "全部 FRESH" in lines[-1]


def test_json_output(tmp_path):
    f = write(tmp_path, last_attempt_ts=iso(NOW - timedelta(hours=1)), last_success_ts=iso(NOW - timedelta(hours=1)))
    r = run(f, "--json")
    rep = json.loads(r.stdout)
    assert r.returncode == 1
    assert rep["results"][0]["verdict"] == "STALE" and rep["exit"] == 1


def test_no_files_is_usage_error():
    r = run()
    assert r.returncode == 2
    assert "至少要一個狀態檔" in r.stdout + r.stderr
    assert "全部 FRESH" not in r.stdout


# ---- 規格第 6 條：檢查器自己也寫心跳 ----

def test_checker_writes_its_own_heartbeat(tmp_path):
    f = write(tmp_path)
    own = tmp_path / "watch" / "stale_check.heartbeat.json"
    r = run(f, "--self-heartbeat", own, "--self-period-s", 3600, now=None)
    assert own.is_file(), r.stdout + r.stderr
    hb = json.loads(own.read_text(encoding="utf-8"))
    assert hb["spec"] == 1 and hb["expected_period_s"] == 3600 and hb["progress"]["files_checked"] == 1
    r2 = run(own, now=None)                           # 另一個觸發點拿同一支檢查器看它
    assert r2.returncode == 0, r2.stdout + r2.stderr


# ---- 規格檔 ----

def test_schema_accepts_example_and_rejects_status_words():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    example = heartbeat(pid=18244, pid_start_ts="2026-11-20T09:01:11+08:00", build="6940d7f",
                        progress={"items_out": 412, "data_date": "2026-11-26", "errors_last_run": 0})
    assert not list(v.iter_errors(example))
    for bad in (heartbeat(status="running"), heartbeat(last_success_ts=DROP), heartbeat(spec=2),
                heartbeat(progress={"running": 1}), heartbeat(progress={"phase": "ok"}),
                heartbeat(expected_period_s=0)):
        assert list(v.iter_errors(bad)), bad


def test_schema_status_lists_match_checker():
    """規格檔與參考檢查器的狀態字清單要一致（規格檔列小寫、首字大寫、全大寫三種，檢查器不分大小寫）。"""
    sys.path.insert(0, str(SCRIPT.parent))
    import stale_check

    defs = json.loads(SCHEMA.read_text(encoding="utf-8"))["$defs"]
    assert {w.lower() for w in defs["statusKey"]["enum"]} == set(stale_check.STATUS_KEYS)
    assert {w.lower() for w in defs["statusWord"]["enum"]} == set(stale_check.STATUS_WORDS)
    assert set(json.loads(SCHEMA.read_text(encoding="utf-8"))["required"]) == set(stale_check.REQUIRED)


def test_selftest_passes():
    r = subprocess.run([sys.executable, str(SCRIPT), "--selftest"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV, timeout=120, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


# ---- 審查修正 D10-R-01：非標準 JSON 常數、溢位成無限大的數字 ----

def write_raw(tmp_path, text, filename="raw.json"):
    f = tmp_path / filename
    f.write_text(text, encoding="utf-8")
    return f


def old_heartbeat_text(field, literal, **fields):
    """停在 2016 年的心跳，把某個數字欄位換成原樣的 JSON 字面值（Infinity、NaN、1e400 這類 json.dumps 寫不出來的）。"""
    doc = heartbeat(last_attempt_ts="2016-01-01T00:00:00+00:00", last_success_ts="2016-01-01T00:00:00+00:00", **fields)
    doc[field] = "__RAW__"
    return json.dumps(doc).replace('"__RAW__"', literal)


@pytest.mark.parametrize("field", ["expected_period_s", "grace_s"])
@pytest.mark.parametrize("literal", ["Infinity", "1e400"])
def test_infinite_period_or_grace_is_down(tmp_path, field, literal):
    """D10-R-01：json.loads 預設接受 Infinity，1e400 也會溢位成 inf；週期或寬限是無限大，停在 2016 年的心跳就永遠 FRESH。"""
    r = run(write_raw(tmp_path, old_heartbeat_text(field, literal)))
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "全部 FRESH" not in r.stdout


@pytest.mark.parametrize("literal", ["Infinity", "1e400"])
def test_infinite_max_data_age_is_down(tmp_path, literal):
    """D10-R-01：資料日期上限是無限大，資料停在 2016 年也不會 STALE。"""
    doc = heartbeat(progress={"data_date": "2016-01-01"}, max_data_age_days="__RAW__")
    r = run(write_raw(tmp_path, json.dumps(doc).replace('"__RAW__"', literal)))
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_non_standard_json_constant_anywhere_is_down(tmp_path, literal):
    """D10-R-01：Infinity、NaN 不是標準 JSON（RFC 8259），出現在哪個欄位都一樣判 DOWN，不只數字欄位。"""
    doc = heartbeat(x_ratio="__RAW__", progress={"items_out": 3, "x_rate": 1.5})
    r = run(write_raw(tmp_path, json.dumps(doc).replace('"__RAW__"', literal)))
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "JSON" in r.stdout


@pytest.mark.parametrize("args", [["--max-data-age-days", "inf"], ["--max-data-age-days", "nan"],
                                  ["--pid-start-tolerance-s", "inf"], ["--pid-start-tolerance-s", "nan"]])
def test_non_finite_cli_numbers_are_usage_errors(tmp_path, args):
    """順手：讀的一方用命令列傳 inf、nan，資料日期上限與啟動時間容許差也會失效；當用法錯誤，不檢查。"""
    f = write(tmp_path, progress={"data_date": "2016-01-01"})
    r = run(f, *args)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "全部 FRESH" not in r.stdout


def test_deeply_nested_json_is_down_not_a_crash(tmp_path):
    """順手：巢狀太深的 JSON 讓 json.loads 丟 RecursionError；要判 DOWN，不能讓檢查器整支當掉。"""
    r = run(write_raw(tmp_path, "[" * 100_000 + "]" * 100_000))
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "Traceback" not in r.stderr


# ---- 審查修正 D10-R-02：pid 超出 32 位元不能被截斷 ----

def test_pid_above_32_bits_is_not_truncated_to_a_live_process(tmp_path, live_process):
    """D10-R-02：Windows 的 OpenProcess 收 32 位元 DWORD，2**32 + 存活 pid 會被截斷成那個存活行程，啟動時間對得上就判 FRESH。"""
    sys.path.insert(0, str(SCRIPT.parent))
    import stale_check

    pid, _ = live_process()
    state, started, _ = stale_check.process_info(pid)
    assert state == "alive" and started is not None
    now = datetime.now(UTC)
    f = write(tmp_path, pid=2**32 + pid, pid_start_ts=started.isoformat(), last_attempt_ts=iso(now),
              last_success_ts=iso(now))
    r = run(f, now=None)
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")


@pytest.mark.parametrize("pid", [0, -1, 2**32, 2**32 + 4, 2**64 + 4])
def test_out_of_range_pid_is_dead(pid):
    """D10-R-02：pid <= 0 或大於 0xFFFFFFFF 一律判 dead，不交給系統呼叫去截斷（pid 4 在 Windows 是 System 行程）。"""
    sys.path.insert(0, str(SCRIPT.parent))
    import stale_check

    assert stale_check.process_info(pid)[0] == "dead"


@pytest.mark.parametrize("pid", [0, -1, 2**32])
def test_out_of_range_pid_in_heartbeat_is_down(tmp_path, pid):
    f = write(tmp_path, pid=pid)
    r = run(f)
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")


# ---- 審查修正 D10-R-03：--started-after 缺 pid、巢狀狀態字、規格檔不分大小寫 ----

def test_started_after_without_pid_is_down_unless_skip_pid(tmp_path):
    """D10-R-03 之 1：--started-after 只看到 pid_start_ts、沒有 pid，就沒向系統查證行程真的在部署後重啟過。"""
    f = write(tmp_path, pid_start_ts=iso(NOW - timedelta(minutes=5)))
    r = run(f, "--started-after", iso(NOW - timedelta(minutes=10)))
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "pid" in r.stdout
    # 狀態檔來自別台機器、明確加 --skip-pid：照舊只註明沒查證
    r = run(f, "--started-after", iso(NOW - timedelta(minutes=10)), "--skip-pid")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("fields", [
    {"x_meta": {"status": "running"}},
    {"x_meta": {"note": "OK"}},
    {"x_meta": {"inner": {"X_Health": 1}}},
    {"x_tags": ["healthy"]},
    {"x_runs": [{"phase": "succeeded"}]},
    {"progress": {"items_out": 3, "x_detail": {"state": "up"}}},
    {"progress": {"items_out": 3, "X_Status": 1}},
])
def test_nested_status_words_are_rejected(tmp_path, fields):
    """D10-R-03 之 2：狀態字藏在巢狀物件、陣列或混合大小寫的 x_ 欄位裡也算。"""
    r = run(write(tmp_path, **fields))
    assert r.returncode == 2, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("DOWN")
    assert "狀態字" in r.stdout


def test_nested_facts_without_status_words_stay_fresh(tmp_path):
    r = run(write(tmp_path, x_meta={"host": "demo-host", "counts": [1, 2], "inner": {"rows": 3}},
                  progress={"items_out": 3, "x_detail": {"rows": 5}}))
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("fields", [
    {"x_Status": 1}, {"x_RUNNING": 1}, {"x_oK": True}, {"progress": {"sTaTuS": 1}}, {"progress": {"x_ok": 1}},
    {"x_note": "rUnNiNg"}, {"x_note": " ok "}, {"progress": {"phase": "Succeeded "}},
    {"x_meta": {"status": 1}}, {"x_meta": {"inner": {"note": "healthy"}}}, {"x_tags": ["Green"]},
])
def test_schema_rejects_status_words_in_any_case_or_nesting(fields):
    """D10-R-03 之 3：規格檔的 propertyNames 要不分大小寫（x_Status、x_RUNNING），巢狀也一樣，跟檢查器一致。"""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    assert list(v.iter_errors(heartbeat(**fields))), fields


def test_schema_still_accepts_plain_extension_facts():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    doc = heartbeat(x_note="deployed by ci", x_meta={"host": "demo-host", "counts": [1, 2], "inner": {"rows": 3}},
                    progress={"items_out": 3, "x_rows": 5})
    assert not list(v.iter_errors(doc))


def test_schema_case_insensitive_patterns_match_checker_lists():
    """規格檔不分大小寫的比對式，跟檢查器的 STATUS_KEYS、STATUS_WORDS 是同一份清單。"""
    import re

    sys.path.insert(0, str(SCRIPT.parent))
    import stale_check

    defs = json.loads(SCHEMA.read_text(encoding="utf-8"))["$defs"]
    key_re = re.compile(defs["statusKeyName"]["pattern"])
    word_re = re.compile(defs["statusWordValue"]["pattern"])
    for w in stale_check.STATUS_KEYS:
        for variant in (w, w.upper(), w.title(), w[:1] + w[1:].upper(), f"x_{w}", f"X_{w.upper()}"):
            assert key_re.search(variant), variant
    for w in stale_check.STATUS_WORDS:
        for variant in (w, w.upper(), w.title(), f" {w} ", w[:1].upper() + w[1:]):
            assert word_re.search(variant), variant
    for fact in ("items_out", "x_note", "statuses", "x_stateful", "upload", "pid"):
        assert not key_re.search(fact), fact
    for fact in ("okay", "not running", "readyz", "2026-11-27", "demo-host"):
        assert not word_re.search(fact), fact



# ---- 2026-11-28 向下相容補強 7 項（控制平面 L1＋L2 規格模組 1）----

def lines_for(stdout, level):
    return [ln for ln in stdout.splitlines() if ln.strip().startswith(f"- [{level}]")]


def test_reader_override_beats_self_reported_ten_year_period(tmp_path):
    """狀態檔自報週期 10 年就永遠 FRESH：讀取方帶自己的期望時以讀取方為準，並註明檔案自報多少。"""
    f = write(tmp_path, expected_period_s=10 * 365 * 86400, last_attempt_ts=iso(NOW - timedelta(days=3)),
              last_success_ts=iso(NOW - timedelta(days=3)))
    assert run(f).returncode == 0                      # 沒有讀取方期望時被自報騙過
    r = run(f, "--override-period-s", 3600, "--override-grace-s", 600)
    assert r.returncode == 1, r.stdout + r.stderr
    assert verdict_lines(r.stdout)[0].startswith("STALE")
    assert "已套用讀取方期望（檔案自報 315360000 秒" in r.stdout
    assert "超過週期 3600 秒加寬限 600 秒" in r.stdout


def test_reader_override_can_also_relax_and_rejects_bad_values(tmp_path):
    f = write(tmp_path, last_attempt_ts=iso(NOW - timedelta(hours=2)), last_success_ts=iso(NOW - timedelta(hours=2)))
    assert run(f).returncode == 1
    assert run(f, "--override-period-s", 86400).returncode == 0
    for bad in (["--override-period-s", 0], ["--override-grace-s", -1], ["--override-period-s", "inf"],
                ["--max-run-s", 0], ["--min-items-out", -1], ["--wake-grace-remaining-s", -5]):
        r = run(f, *bad)
        assert r.returncode == 2, (bad, r.stdout, r.stderr)
        assert not verdict_lines(r.stdout)


def test_started_but_stuck_is_stale_with_max_run_s(tmp_path):
    """每天跑一次的工作 2 小時前開始、到現在沒成功：週期還沒過所以原本是 FRESH，max_run_s 才抓得到卡死。"""
    fields = dict(expected_period_s=86400, grace_s=3600, last_success_ts=iso(NOW - timedelta(hours=5)),
                  last_attempt_ts=iso(NOW - timedelta(hours=2)))
    f = write(tmp_path, **fields)
    assert run(f).returncode == 0
    r = run(f, "--max-run-s", 1800)
    assert r.returncode == 1 and "任務啟動後逾時疑似卡死" in r.stdout
    assert run(f, "--max-run-s", 3 * 3600).returncode == 0                # 還在上限內
    g = write(tmp_path, "self.json", max_run_s=1800, **fields)            # 做事那方自己宣告上限
    assert run(g).returncode == 1
    assert run(g, "--max-run-s", 86400).returncode == 0                   # 讀取方的值優先
    done = write(tmp_path, "done.json", max_run_s=60)                     # 這一輪已經成功，不算卡住
    assert run(done).returncode == 0
    bad = write(tmp_path, "bad.json", max_run_s=0, **fields)
    assert run(bad).returncode == 2


def test_exit_zero_with_no_output_is_stale_with_min_items_out(tmp_path):
    """排程 exit 0、心跳照寫，但這一輪寫出 0 筆：min_items_out 抓空跑；設了下限卻沒有 items_out 也算。"""
    empty = write(tmp_path, "empty.json", progress={"items_out": 0})
    assert run(empty).returncode == 0
    r = run(empty, "--min-items-out", 1)
    assert r.returncode == 1 and "產出筆數低於下限" in r.stdout
    missing = write(tmp_path, "missing.json")
    r = run(missing, "--min-items-out", 1)
    assert r.returncode == 1 and "沒有 progress.items_out" in r.stdout
    declared = write(tmp_path, "declared.json", min_items_out=100, progress={"items_out": 99})
    assert run(declared).returncode == 1
    enough = write(tmp_path, "enough.json", min_items_out=100, progress={"items_out": 412})
    assert run(enough).returncode == 0
    for i, bad in enumerate((-1, 1.5, "3", True)):
        assert run(write(tmp_path, f"bad{i}.json", min_items_out=bad)).returncode == 2, bad


def test_wake_grace_downgrades_only_timeout_stale_to_paused(tmp_path):
    """電腦剛從休眠醒來：只因為時間過太久的 STALE 先標 PAUSED（exit 0、不是 FRESH），緩衝用完恢復 STALE。"""
    f = write(tmp_path, last_attempt_ts=iso(NOW - timedelta(hours=9)), last_success_ts=iso(NOW - timedelta(hours=9)))
    assert run(f).returncode == 1
    r = run(f, "--wake-grace-remaining-s", 150)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines()[0].startswith("PAUSED")
    assert "系統剛自休眠喚醒緩衝中" in r.stdout and "全部 FRESH" not in r.stdout
    assert "1 個 PAUSED" in r.stdout.strip().splitlines()[-1]
    assert run(f, "--wake-grace-remaining-s", 0).returncode == 1
    # 寬限不蓋掉別的問題
    empty = write(tmp_path, "empty.json", last_attempt_ts=iso(NOW - timedelta(hours=9)),
                  last_success_ts=iso(NOW - timedelta(hours=9)), progress={"items_out": 0})
    assert run(empty, "--wake-grace-remaining-s", 150, "--min-items-out", 1).returncode == 1
    word = write(tmp_path, "word.json", status="running", last_attempt_ts=iso(NOW - timedelta(hours=9)),
                 last_success_ts=iso(NOW - timedelta(hours=9)))
    assert run(word, "--wake-grace-remaining-s", 150).returncode == 2
    fresh = write(tmp_path, "fresh.json")
    rf = run(fresh, "--wake-grace-remaining-s", 150)
    assert rf.returncode == 0 and rf.stdout.splitlines()[0].startswith("FRESH")


def test_remote_host_skips_pid_instead_of_down(tmp_path):
    """狀態檔是別台機器同步過來的：pid 在這台一定查不到，有 host 就自動不查，不誤判 DOWN；本機的照樣查。"""
    import socket

    pid = dead_pid()
    remote = write(tmp_path, "remote.json", pid=pid, host="some-other-box-9f3")
    r = run(remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "遠端主機 some-other-box-9f3" in r.stdout
    local = write(tmp_path, "local.json", pid=pid, host=socket.gethostname().upper())
    r = run(local)
    assert r.returncode == 2 and "不存在" in r.stdout
    nohost = write(tmp_path, "nohost.json", pid=pid)                      # 舊格式：沒有 host 照舊查 pid
    assert run(nohost).returncode == 2
    for i, bad in enumerate(("", "   ", 7)):
        assert run(write(tmp_path, f"bad{i}.json", host=bad)).returncode == 2, bad


def test_paused_until_ts_is_gray_then_recovers_strict(tmp_path):
    """預期暫停到某個時間：到期前 PAUSED（不是綠燈、不算異常），到期後自動恢復嚴格判定。"""
    old = dict(last_attempt_ts=iso(NOW - timedelta(days=2)), last_success_ts=iso(NOW - timedelta(days=2)))
    f = write(tmp_path, paused_until_ts=iso(NOW + timedelta(hours=6)), pid=dead_pid(), **old)
    r = run(f)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines()[0].startswith("PAUSED") and "預期暫停到" in r.stdout
    assert "全部 FRESH" not in r.stdout
    assert not lines_for(r.stdout, "STALE") and not lines_for(r.stdout, "DOWN")
    # 同一個檔，時間過了期限：恢復成原本該有的判定（pid 不在：DOWN）
    r = run(f, now=NOW + timedelta(hours=7))
    assert r.returncode == 2 and "暫停期限" in r.stdout
    stale_after = write(tmp_path, "after.json", paused_until_ts=iso(NOW - timedelta(minutes=1)), **old)
    assert run(stale_after).returncode == 1
    # 沒過期的心跳在暫停期間也不能顯示成 FRESH
    fresh_paused = write(tmp_path, "fp.json", paused_until_ts=iso(NOW + timedelta(hours=1)))
    assert run(fresh_paused).stdout.splitlines()[0].startswith("PAUSED")


@pytest.mark.parametrize("fields", [
    {"paused": True},                                   # 狀態字不是事實
    {"x_paused": True},
    {"x_mode": "Paused"},
    {"progress": {"paused": 1}},
    {"paused_until_ts": "2026-11-28T00:00:00"},         # 沒帶時區
    {"paused_until_ts": 1764212400},                    # epoch 數字
])
def test_paused_as_status_word_or_bad_timestamp_is_down(tmp_path, fields):
    r = run(write(tmp_path, **fields))
    assert r.returncode == 2, r.stdout + r.stderr


def test_pause_far_in_the_future_is_not_honoured(tmp_path):
    """paused_until_ts 寫 10 年後等於自報永遠正常：超過 30 天不採信，照常判定。"""
    f = write(tmp_path, paused_until_ts=iso(NOW + timedelta(days=3650)),
              last_attempt_ts=iso(NOW - timedelta(days=2)), last_success_ts=iso(NOW - timedelta(days=2)))
    r = run(f)
    assert r.returncode == 1 and "不當成暫停" in r.stdout


def test_x_dirty_fact_is_reported_but_does_not_change_verdict(tmp_path):
    r = run(write(tmp_path, x_dirty=True))
    assert r.returncode == 0 and "執行工作樹含未提交改動" in r.stdout
    r = run(write(tmp_path, "clean.json", x_dirty=False))
    assert r.returncode == 0 and "未提交改動" not in r.stdout


def test_json_output_carries_paused_count_and_facts(tmp_path):
    f = write(tmp_path, build="6940d7f", host="some-other-box-9f3", x_dirty=True, progress={"items_out": 7},
              paused_until_ts=iso(NOW + timedelta(hours=1)))
    rep = json.loads(run(f, "--json").stdout)
    assert rep["exit"] == 0 and rep["counts"] == {"FRESH": 0, "STALE": 0, "DOWN": 0, "PAUSED": 1}
    facts = rep["results"][0]["facts"]
    assert facts["build"] == "6940d7f" and facts["x_dirty"] is True and facts["items_out"] == 7
    assert any(r["level"] == "PAUSED" for r in rep["results"][0]["reasons"])


def test_schema_accepts_new_optional_fields_and_old_files_unchanged():
    """新欄位都是選填：舊格式照樣合規；新欄位型別錯或把暫停寫成狀態字就不合規。規格檔的選填欄位跟檢查器一致。"""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    assert not list(v.iter_errors(heartbeat()))
    full = heartbeat(max_run_s=1800, min_items_out=1, host="demo-host", x_dirty=True,
                     paused_until_ts="2026-12-01T09:00:00+08:00", progress={"items_out": 3})
    assert not list(v.iter_errors(full))
    for bad in (heartbeat(max_run_s=0), heartbeat(min_items_out=-1), heartbeat(min_items_out=1.5), heartbeat(host=""),
                heartbeat(paused_until_ts="2026-12-01T09:00:00"), heartbeat(paused=True), heartbeat(x_paused=True),
                heartbeat(x_dirty="yes"), heartbeat(x_mode="paused")):
        assert list(v.iter_errors(bad)), bad
    sys.path.insert(0, str(SCRIPT.parent))
    import stale_check

    declared = set(schema["properties"]) - set(stale_check.REQUIRED) - {"x_dirty"}
    assert declared == set(stale_check.OPTIONAL)


def test_self_heartbeat_helper_serves_other_monitors(tmp_path):
    """控制面板的背景巡檢借用同一個寫法寫自己的心跳（帶 pid、host、產出數），同一支檢查器照樣能判定。"""
    sys.path.insert(0, str(SCRIPT.parent))
    import socket

    import stale_check

    now = datetime.now(UTC)
    _, started, _ = stale_check.process_info(os.getpid())
    out = tmp_path / "cockpit" / "poller-heartbeat.json"
    stale_check.write_self_heartbeat(out, now, 60, 120, [], name="cockpit-poller", extra={
        "pid": os.getpid(), "pid_start_ts": started.isoformat(), "host": socket.gethostname(),
        "build": "0.3.0", "progress": {"items_out": 4}})
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["name"] == "cockpit-poller" and doc["pid"] == os.getpid() and doc["progress"]["items_out"] == 4
    res = stale_check.run_checks([out], min_items_out=1)[0]
    assert res["verdict"] == "FRESH", res["reasons"]
    late = stale_check.run_checks([out], now=now + timedelta(minutes=10))[0]
    assert late["verdict"] == "STALE"
