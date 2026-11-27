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
