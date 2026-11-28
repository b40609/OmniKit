"""控制面板零改碼主動探針與正交三軸引擎（engine/cockpit/probes.py）的 pytest。

四個故障注入（規格的必跑驗證）：
1. 改了碼沒重啟：行程啟動早於最後一次非文件 commit → sync 是 DRIFT。
2. 排程 exit 0 但產出沒更新：win_task 正常、產出檔過期 → fresh 是 STALE，而且不是實心綠。
3. 休眠後時鐘跳變：180 秒寬限內，只因超時的異常標 PAUSED，不誤報；寬限過了照樣報。
4. 狀態檔自報 10 年週期：讀取方的 override_period_s 蓋過它，照樣抓出 STALE。

系統事實（聽埠、行程、排程、HTTP）用假的 System 注入，所以在 Linux CI 也跑得了；Git、SQLite、檔案用真的。
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.cockpit import collector, probes

NOW = datetime(2026, 11, 27, 4, 0, 0, tzinfo=UTC)   # 台北時間週五 12:00


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


class FakeSystem(probes.System):
    """把向作業系統查的事實換成測試給的；git 照樣用真的。"""

    def __init__(self, *, listeners=None, processes=None, starts=None, http=None, tasks=None, connect=(False, False)):
        super().__init__()
        self._listeners = listeners
        self._processes = processes
        self._starts = starts or {}
        self._http = http or {}
        self._tasks = tasks or {}
        self._connect = connect
        self.http_calls: list[str] = []

    def process_info(self, pid):
        if pid in self._starts:
            return "alive", self._starts[pid], ""
        return "dead", None, "沒有這個行程"

    def listeners(self):
        return self._listeners

    def can_connect(self, host, port, timeout=0.4):
        return self._connect

    def processes(self):
        return self._processes

    def http_get(self, url, timeout=2.0):
        probes.validate_loopback_url(url)
        self.http_calls.append(url)
        got = self._http.get(url)
        if got is None:
            return {"status": None, "body": b"", "error": "連線被拒", "timed_out": False}
        if isinstance(got, dict) and "status" in got and "body" in got:
            return got
        status, doc = got
        return {"status": status, "body": json.dumps(doc).encode("utf-8"), "error": None, "timed_out": False}

    def win_tasks(self, names, *, force=False):
        return {n: self._tasks.get(n) or {"found": False, "error": "找不到"} for n in names}


@pytest.fixture
def box():
    """簡短的暫存目錄：state（面板狀態）、proj（專案）、home（假家目錄）。"""
    with tempfile.TemporaryDirectory(prefix="pb") as d:
        base = Path(d)
        for name in ("state", "proj", "home"):
            (base / name).mkdir()
        yield base


def scan(box: Path, services: list[dict], system: probes.System, *, now: datetime = NOW, wake: float = 0.0, cfg_extra: dict | None = None):
    cfg = {"probes": {"demo": {"services": services}}, **(cfg_extra or {})}
    entries = [{"id": "demo", "name": "Demo", "path": str(box / "proj")}]
    return probes.scan_all(box / "state", entries=entries, cfg=cfg, home=box / "home", now=now, system=system,
                           wake_grace_remaining_s=wake)


def one(box: Path, service: dict, system: probes.System, **kw) -> dict:
    snap = scan(box, [service], system, **kw)
    assert snap["projects"]["demo"]["config_errors"] == []
    return snap["projects"]["demo"]["services"][0]


def git(repo: Path, *args: str, when: datetime | None = None) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    if when is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = iso(when)
    out = subprocess.run(["git", "-c", "core.longpaths=true", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                          "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                         cwd=str(repo), check=True, capture_output=True, text=True, env=env)
    return out.stdout.strip()


def make_repo(repo: Path, *, code_at: datetime) -> str:
    git(repo, "init", "--template=", "-q")
    (repo / "app.py").write_text("print('v1')\n", encoding="utf-8")
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    git(repo, "add", "app.py", "README.md")
    git(repo, "commit", "-q", "-m", "code", when=code_at)
    return git(repo, "rev-parse", "HEAD")


def write_heartbeat(path: Path, **fields) -> None:
    doc = {"spec": 1, "name": "demo-bot", "last_attempt_ts": iso(NOW - timedelta(minutes=1)),
           "last_success_ts": iso(NOW - timedelta(minutes=1)), "expected_period_s": 300, "grace_s": 120, **fields}
    path.write_text(json.dumps(doc), encoding="utf-8")


# ---------- 故障注入 1：改了碼沒重啟 ----------

def test_fault_code_changed_without_restart_is_drift(box):
    repo = box / "proj"
    commit_at = NOW - timedelta(hours=2)
    make_repo(repo, code_at=commit_at)
    svc = {"id": "api", "probes": [{"type": "tcp", "port": 8765}]}

    stale_proc = FakeSystem(listeners=[("127.0.0.1", 8765, 4242)], starts={4242: commit_at - timedelta(hours=5)})
    got = one(box, svc, stale_proc)
    assert got["alive"]["state"] == "UP"                      # 活著
    assert got["sync"]["state"] == "DRIFT"                    # 但跑的是舊碼
    assert "改碼後沒有重啟" in got["sync"]["reason"]
    assert got["level"] == "warn" and got["fingerprint"]

    restarted = FakeSystem(listeners=[("127.0.0.1", 8765, 4242)], starts={4242: commit_at + timedelta(minutes=5)})
    got = one(box, svc, restarted)
    assert got["sync"]["state"] == "SYNCED"
    assert got["level"] == "ok" and got["fingerprint"] is None


def test_doc_only_commit_after_start_is_not_drift(box):
    repo = box / "proj"
    make_repo(repo, code_at=NOW - timedelta(hours=6))
    (repo / "README.md").write_text("demo v2\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.txt").write_text("guide\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "docs only", when=NOW - timedelta(minutes=10))
    system = FakeSystem(listeners=[("0.0.0.0", 8765, 7)], starts={7: NOW - timedelta(hours=1)})
    got = one(box, {"id": "api", "probes": [{"type": "tcp", "port": 8765}]}, system)
    assert got["sync"]["state"] == "SYNCED"   # 行程啟動後只改了文件，不算漂移


def test_uncommitted_code_edit_after_start_is_drift(box):
    repo = box / "proj"
    make_repo(repo, code_at=NOW - timedelta(hours=6))
    start = NOW - timedelta(hours=1)
    system = FakeSystem(listeners=[("127.0.0.1", 8765, 7)], starts={7: start})
    svc = {"id": "api", "probes": [{"type": "tcp", "port": 8765}]}
    assert one(box, svc, system)["sync"]["state"] == "SYNCED"

    (repo / "app.py").write_text("print('v2')\n", encoding="utf-8")
    edited = (start + timedelta(minutes=20)).timestamp()
    os.utime(repo / "app.py", (edited, edited))
    got = one(box, svc, system)
    assert got["sync"]["state"] == "DRIFT"
    assert "未提交改動" in got["sync"]["reason"]

    relaxed = {**svc, "sync": {"check_worktree": False}}
    assert one(box, relaxed, system)["sync"]["state"] == "SYNCED"
    assert one(box, {**svc, "sync": {"enabled": False}}, system)["sync"]["state"] == "N/A"


def test_reported_version_vs_head(box):
    repo = box / "proj"
    head = make_repo(repo, code_at=NOW - timedelta(hours=3))
    url = "http://127.0.0.1:8765/health"
    svc = {"id": "api", "probes": [{"type": "http", "url": url, "expect_json": {"ok": True}, "version_json_path": "build.sha"}]}

    same = FakeSystem(http={url: (200, {"ok": True, "build": {"sha": head[:10]}})})
    got = one(box, svc, same)
    assert got["sync"]["state"] == "SYNCED"
    assert got["alive"] == {**got["alive"], "state": "UP", "proof_level": "output_verified"}   # 內容斷言通過算實心綠

    old = FakeSystem(http={url: (200, {"ok": True, "build": {"sha": "0123456789abcdef0123456789abcdef01234567"}})})
    got = one(box, svc, old)
    assert got["sync"]["state"] == "DRIFT" and "跑的不是最新的碼" in got["sync"]["reason"]

    semver = FakeSystem(http={url: (200, {"ok": True, "build": {"sha": "1.4.2"}})})
    got = one(box, svc, semver)
    assert got["sync"]["state"] == "NO_DATA"   # 不是 commit SHA 就不硬比，也不假裝同步

    # HEAD 之後只多了文件 commit：回報舊的 code commit 仍算同步
    (repo / "README.md").write_text("more\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "docs", when=NOW - timedelta(hours=1))
    assert git(repo, "rev-parse", "HEAD") != head
    assert one(box, svc, same)["sync"]["state"] == "SYNCED"


def test_build_dir_older_than_src_dir_is_drift(box):
    repo = box / "proj"
    (repo / "src").mkdir()
    (repo / "dist").mkdir()
    (repo / "src" / "main.ts").write_text("x", encoding="utf-8")
    (repo / "dist" / "main.js").write_text("x", encoding="utf-8")
    old, new = (NOW - timedelta(hours=3)).timestamp(), (NOW - timedelta(hours=1)).timestamp()
    os.utime(repo / "src" / "main.ts", (new, new))
    os.utime(repo / "dist" / "main.js", (old, old))
    system = FakeSystem(listeners=[])
    svc = {"id": "web", "probes": [{"type": "artifact", "glob": "dist/*.js"}], "sync": {"src_dir": "src", "build_dir": "dist"}}
    got = one(box, svc, system)
    assert got["sync"]["state"] == "DRIFT" and "沒有重建" in got["sync"]["reason"]
    os.utime(repo / "dist" / "main.js", (new + 60, new + 60))
    assert one(box, svc, system)["sync"]["state"] == "SYNCED"


# ---------- 故障注入 2：排程 exit 0 但產出沒更新 ----------

def test_fault_task_exit_zero_but_output_not_updated_is_stale(box):
    out = box / "proj" / "out"
    out.mkdir()
    report = out / "daily.csv"
    report.write_text("a,b\n1,2\n", encoding="utf-8")
    old = (NOW - timedelta(days=3)).timestamp()
    os.utime(report, (old, old))
    task = {"found": True, "state": "Ready", "last_run": iso(NOW - timedelta(hours=1)), "last_result": 0, "missed": 0}
    system = FakeSystem(tasks={"Demo Daily": task})
    svc = {"id": "daily", "probes": [{"type": "win_task", "name": "Demo Daily"},
                                     {"type": "artifact", "glob": "out/*.csv", "max_age_s": 86400}]}
    got = one(box, svc, system)
    assert got["alive"]["state"] == "UP"
    assert got["alive"]["proof_level"] == "liveness_only"    # 排程說成功，但沒有新鮮產出：只能是空心綠
    assert got["fresh"]["state"] == "STALE"
    assert got["level"] == "bad"

    fresh = (NOW - timedelta(minutes=30)).timestamp()
    os.utime(report, (fresh, fresh))
    got = one(box, svc, system)
    assert got["fresh"]["state"] == "FRESH" and got["alive"]["proof_level"] == "output_verified" and got["level"] == "ok"


def test_win_task_states(box):
    def run(task, **probe_extra):
        system = FakeSystem(tasks={"T": task} if task else {})
        return one(box, {"id": "t", "probes": [{"type": "win_task", "name": "T", **probe_extra}]}, system)

    ok = {"found": True, "state": "Ready", "last_run": iso(NOW - timedelta(hours=1)), "last_result": 0, "missed": 0}
    got = run(ok)
    assert got["alive"]["state"] == "UP" and got["alive"]["proof_level"] == "liveness_only"
    assert got["fresh"]["state"] == "N/A" and "只有排程探針" in got["fresh"]["reason"]   # 排程成功不等於有產出

    assert run({**ok, "state": "Disabled"})["alive"]["state"] == "DOWN"
    assert run(None)["alive"]["state"] == "DOWN"
    assert run({**ok, "last_result": 1})["alive"]["state"] == "DEGRADED"
    assert run({**ok, "missed": 2})["alive"]["state"] == "DEGRADED"
    assert run({**ok, "last_result": 0x41301})["alive"]["state"] == "UP"       # 正在跑
    assert run(ok, max_age_s=600)["alive"]["state"] == "DEGRADED"              # 超過期限沒執行
    assert run({"found": False, "error": "查不到", "query_failed": True})["alive"]["state"] == "NO_DATA"


# ---------- 故障注入 3：休眠後時鐘跳變 ----------

def test_fault_sleep_clock_jump_gives_180s_grace(box):
    clock = {"awake": 1000.0, "wall": 1_800_000_000.0}
    det = probes.WakeDetector(awake_clock=lambda: clock["awake"], wall_clock=lambda: clock["wall"])
    assert det.tick(60) == 0
    clock["awake"] += 60
    clock["wall"] += 60
    assert det.tick(60) == 0                      # 正常一輪：兩個時鐘走一樣多
    clock["awake"] += 61
    clock["wall"] += 61 + 100
    assert det.tick(60) == 0                      # 落差 100 秒，沒超過 120：不算休眠
    clock["awake"] += 60
    clock["wall"] += 60 + 8 * 3600                # 睡了 8 小時：掛鐘跳了，醒著的時間沒動
    assert det.tick(60) == 180
    assert det.last_wake_at and det.last_jump_s == 8 * 3600
    clock["awake"] += 60
    clock["wall"] += 60
    assert det.tick(60) == 120                    # 寬限照醒著的時間倒數
    clock["awake"] += 121
    clock["wall"] += 121
    assert det.tick(60) == 0

    # 後備：單調時鐘休眠時也照走（兩個增量一樣大），改看這一輪是不是晚了超過 120 秒
    clock2 = {"t": 0.0}
    det2 = probes.WakeDetector(awake_clock=lambda: clock2["t"], wall_clock=lambda: clock2["t"] + 1e9)
    det2.tick(60)
    clock2["t"] += 3600
    assert det2.tick(60) == 180


def test_fault_wake_grace_does_not_false_alarm(box):
    proj = box / "proj"
    hb = proj / "hb.json"
    write_heartbeat(hb, last_attempt_ts=iso(NOW - timedelta(hours=8)), last_success_ts=iso(NOW - timedelta(hours=8)))
    report = proj / "out.csv"
    report.write_text("x\n", encoding="utf-8")
    old = (NOW - timedelta(hours=8)).timestamp()
    os.utime(report, (old, old))
    svc = {"id": "bot", "probes": [{"type": "heartbeat", "path": "hb.json"},
                                   {"type": "artifact", "glob": "out.csv", "max_age_s": 3600}]}
    system = FakeSystem()

    during = scan(box, [svc], system, wake=180)
    got = during["projects"]["demo"]["services"][0]
    assert got["fresh"]["state"] == "PAUSED"          # 寬限內：只是超時，先不報
    assert "剛自休眠喚醒" in got["fresh"]["reason"] or "休眠喚醒" in got["fresh"]["reason"]
    assert got["level"] == "idle" and during["alerts"] == []
    assert during["wake_grace_active"] is True and during["wake_grace_remaining_s"] == 180

    after = scan(box, [svc], system, wake=0)
    got = after["projects"]["demo"]["services"][0]
    assert got["fresh"]["state"] == "STALE"           # 寬限過了還沒追上：照樣報
    assert got["level"] == "bad" and len(after["alerts"]) == 1

    # 寬限只蓋「時間過太久」，蓋不掉內容問題：產出太小照樣 STALE
    tiny = {"id": "bot", "probes": [{"type": "artifact", "glob": "out.csv", "min_bytes": 10_000}]}
    assert one(box, tiny, system, wake=180)["fresh"]["state"] == "STALE"
    # 也蓋不掉真的沒在聽的埠
    dead = {"id": "bot", "probes": [{"type": "tcp", "port": 9}]}
    assert one(box, dead, FakeSystem(listeners=[]), wake=180)["alive"]["state"] == "DOWN"


# ---------- 故障注入 4：狀態檔自報 10 年週期 ----------

def test_fault_ten_year_self_report_is_overridden_by_manifest(box):
    hb = box / "proj" / "hb.json"
    write_heartbeat(hb, expected_period_s=315_360_000, grace_s=0,
                    last_attempt_ts=iso(NOW - timedelta(days=2)), last_success_ts=iso(NOW - timedelta(days=2)))
    system = FakeSystem()
    trusting = {"id": "bot", "probes": [{"type": "heartbeat", "path": "hb.json"}]}
    assert one(box, trusting, system)["fresh"]["state"] == "FRESH"     # 只信檔案自己說的：兩天沒動還是綠的

    strict = {"id": "bot", "probes": [{"type": "heartbeat", "path": "hb.json", "override_period_s": 300, "override_grace_s": 60}]}
    got = one(box, strict, system)
    assert got["fresh"]["state"] == "STALE"                            # 讀取方的期望蓋過自報
    assert got["level"] == "bad"
    assert got["alive"]["state"] == "NO_DATA"                          # 沒有存活證據，不會顯示成綠的


# ---------- 設定檢查：安全邊界 ----------

@pytest.mark.parametrize("probe", [
    {"type": "tcp", "host": "10.0.0.5", "port": 80},
    {"type": "tcp", "host": "example.com", "port": 80},
    {"type": "tcp", "port": 0},
    {"type": "tcp", "port": 70000},
    {"type": "tcp", "port": "80"},
    {"type": "http", "url": "http://example.com/health"},
    {"type": "http", "url": "http://169.254.169.254/latest/meta-data/"},
    {"type": "http", "url": "http://127.0.0.1@example.com/"},
    {"type": "http", "url": "http://user:pw@127.0.0.1/"},
    {"type": "http", "url": "http://localhost.example.com/"},
    {"type": "http", "url": "http://127.0.0.1.example.com/"},
    {"type": "http", "url": "http://[::ffff:8.8.8.8]/"},
    {"type": "http", "url": "http://0.0.0.0/"},
    {"type": "http", "url": "file:///etc/passwd"},
    {"type": "http", "url": "ftp://127.0.0.1/"},
    {"type": "http", "url": "http://127.0.0.1:99999/"},
    {"type": "http", "url": "http://127.0.0.1/ a"},
    {"type": "http", "url": "http://127.0.0.1/", "headers": {"Authorization": "x"}},
    {"type": "http", "url": "http://127.0.0.1/", "method": "POST"},
    {"type": "http", "url": "http://127.0.0.1/", "expect_json": {"a b": 1}},
    {"type": "artifact", "sqlite_path": "a.db", "table": "t; DROP TABLE t", "ts_col": "ts"},
    {"type": "artifact", "sqlite_path": "a.db", "table": 't"', "ts_col": "ts"},
    {"type": "artifact", "sqlite_path": "a.db", "table": "t", "ts_col": "ts) FROM t; --"},
    {"type": "artifact", "sqlite_path": "a.db", "table": "1abc", "ts_col": "ts"},
    {"type": "artifact", "sqlite_path": "a.db", "table": "a-b", "ts_col": "ts"},
    {"type": "artifact", "sqlite_path": "a.db", "table": "a b", "ts_col": "ts"},
    {"type": "artifact", "sqlite_path": "a.db", "table": "t", "ts_col": ""},
    {"type": "artifact", "sqlite_path": "a.db", "table": "t", "ts_col": "ts", "sql": "SELECT 1"},
    {"type": "artifact", "sqlite_path": "a.db", "table": "t", "ts_col": "ts", "glob": "*.csv"},
    {"type": "artifact"},
    {"type": "artifact", "glob": "../secret/*.txt"},
    {"type": "artifact", "glob": "\\\\server\\share\\*.txt"},
    {"type": "artifact", "glob": "//server/share/*.txt"},
    {"type": "artifact", "glob": "\\\\.\\PhysicalDrive0"},
    {"type": "artifact", "glob": "out/*.csv", "max_age_s": -1},
    {"type": "heartbeat", "path": "a/../../b.json"},
    {"type": "heartbeat", "path": "hb*.json"},
    {"type": "heartbeat", "path": "hb.json", "override_period_s": 0},
    {"type": "process", "match": "py"},
    {"type": "win_task", "name": "x'; Remove-Item C:\\ -Recurse; '"},
    {"type": "win_task", "name": "a$(calc)"},
    {"type": "shell", "command": "whoami"},
    {"type": ""},
    "tcp",
])
def test_normalize_rejects_unsafe_probes(probe):
    with pytest.raises((ValueError, TypeError)):
        probes.normalize_service({"id": "svc", "probes": [probe]})


def test_normalize_accepts_good_service_and_fills_defaults():
    svc = probes.normalize_service({
        "name": "Demo API",
        "probes": [
            {"type": "tcp", "port": 8080},
            {"type": "http", "url": "http://localhost:8080/health", "expect_json": {"status": "ok", "db": "*"}},
            {"type": "http", "url": "http://[::1]:8080/health"},
            {"type": "artifact", "sqlite_path": "data/app.db", "table": "ticks_1m", "ts_col": "ts", "max_age_days": 3, "min_rows": 1},
            {"type": "process", "match": "uvicorn app:main"},
            {"type": "win_task", "name": "\\OmniKit\\Demo Daily"},
        ],
        "active_days": "mon-fri".replace("-", ",").replace("mon,fri", "mon,tue,wed,thu,fri"),
        "active_hours": "08:45-13:45",
        "timezone": "Asia/Taipei",
    })
    assert svc["id"] == "demo-api"
    assert svc["probes"][0] == {"type": "tcp", "host": "127.0.0.1", "port": 8080}
    assert svc["probes"][1]["expect_status"] == 200
    assert svc["active_days"] == [0, 1, 2, 3, 4] and svc["active_hours"] == [[525, 825]]
    for bad in ({"id": "a b"}, {"id": "x", "probes": []}, {"id": "x", "probes": [{"type": "tcp", "port": 1}], "run": "x"},
                {"id": "x", "probes": [{"type": "tcp", "port": 1}], "active_hours": "25:00-26:00"},
                {"id": "x", "probes": [{"type": "tcp", "port": 1}], "active_days": ["funday"]},
                {"id": "x", "probes": [{"type": "tcp", "port": 1}], "sync": {"src_dir": "src"}},
                {"id": "x", "probes": [{"type": "tcp", "port": 1}] * (probes.MAX_PROBES + 1)}):
        with pytest.raises((ValueError, TypeError)):
            probes.normalize_service(bad)


def test_project_layer_paths_must_stay_inside_project(box):
    proj, home = box / "proj", box / "home"
    outside = box / "outside.txt"
    with pytest.raises(ValueError):
        probes.resolve_local_path(str(outside), project_root=proj, home=home, layer="project")
    with pytest.raises(ValueError):
        probes.resolve_local_path("~/x.json", project_root=proj, home=home, layer="project")
    with pytest.raises(ValueError):
        probes.resolve_local_path("../x.json", project_root=proj, home=home, layer="personal")
    assert probes.resolve_local_path("out/a.json", project_root=proj, home=home, layer="project") == proj / "out" / "a.json"
    assert probes.resolve_local_path(str(outside), project_root=proj, home=home, layer="personal") == outside
    assert probes.resolve_local_path("~/x.json", project_root=proj, home=home, layer="personal") == home / "x.json"

    # 專案共用設定寫了絕對路徑：那個探針是 DOWN 並講明原因，不會去讀專案外的檔案
    outside.write_text("secret", encoding="utf-8")
    (proj / probes.PROJECT_FILE).write_text(
        "services:\n  - id: leak\n    probes:\n      - type: artifact\n        glob: " + json.dumps(str(outside)) + "\n", encoding="utf-8")
    snap = probes.scan_all(box / "state", entries=[{"id": "demo", "name": "Demo", "path": str(proj)}], cfg={}, home=home, now=NOW,
                           system=FakeSystem())
    got = snap["projects"]["demo"]["services"][0]
    assert got["fresh"]["state"] == "DOWN" and "相對路徑" in got["fresh"]["reason"]


def test_http_probe_real_server_no_redirect_and_loopback_only():
    hits: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path == "/redir":
                self.send_response(302)
                self.send_header("Location", "http://example.com/steal")
                self.end_headers()
                return
            body = json.dumps({"status": "ok", "commit": "abc1234"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_address[1]
        system = probes.System()
        got = system.http_get(f"http://127.0.0.1:{port}/health")
        assert got["status"] == 200 and json.loads(got["body"])["status"] == "ok"
        redirected = system.http_get(f"http://127.0.0.1:{port}/redir")
        assert redirected["status"] == 302            # 轉址不跟：拿到 302 本身，沒有去連外部網址
        assert hits == ["/health", "/redir"]
        for url in ("http://example.com/", "http://169.254.169.254/", "http://127.0.0.1@example.com/"):
            with pytest.raises(ValueError):
                system.http_get(url)                  # 連都不會連
        # 真的 tcp 探針：查得到是這個測試行程在聽
        rows = system.listeners()
        if rows is not None:
            assert any(p == port for _a, p, _pid in rows)
    finally:
        srv.shutdown()
        srv.server_close()


def test_http_probe_states(box):
    url = "http://127.0.0.1:8765/health"
    svc = {"id": "api", "probes": [{"type": "http", "url": url, "expect_json": {"status": "ok", "db": "*"}}]}
    assert one(box, svc, FakeSystem(http={url: (200, {"status": "ok", "db": "up"})}))["alive"]["state"] == "UP"
    assert one(box, svc, FakeSystem(http={url: (200, {"status": "bad", "db": "up"})}))["alive"]["state"] == "DEGRADED"
    assert one(box, svc, FakeSystem(http={url: (200, {"status": "ok"})}))["alive"]["state"] == "DEGRADED"
    assert one(box, svc, FakeSystem(http={url: (200, {"status": "ok", "db": ""})}))["alive"]["state"] == "DEGRADED"
    assert one(box, svc, FakeSystem(http={url: (500, {})}))["alive"]["state"] == "DEGRADED"
    assert one(box, svc, FakeSystem(http={url: {"status": 200, "body": b"<html>", "error": None, "timed_out": False}}))["alive"]["state"] == "DEGRADED"
    assert one(box, svc, FakeSystem())["alive"]["state"] == "DOWN"
    plain = {"id": "api", "probes": [{"type": "http", "url": url}]}
    got = one(box, plain, FakeSystem(http={url: {"status": 200, "body": b"ok", "error": None, "timed_out": False}}))
    assert got["alive"]["state"] == "UP" and got["alive"]["proof_level"] == "liveness_only"   # 只看狀態碼是空心綠
    # 回應內容不外流：機密字串不會出現在快照裡
    leaky = FakeSystem(http={url: (200, {"status": "ok", "db": "up", "api_key": "sk-THIS-MUST-NOT-LEAK"})})
    assert "THIS-MUST-NOT-LEAK" not in json.dumps(scan(box, [svc], leaky))


# ---------- 各探針 ----------

def test_tcp_and_process_probes(box):
    started = NOW - timedelta(hours=1)
    system = FakeSystem(listeners=[("0.0.0.0", 3780, 11), ("192.168.1.5", 9000, 12), ("::", 5000, 13)], starts={11: started, 13: started})
    assert one(box, {"id": "a", "probes": [{"type": "tcp", "port": 3780}]}, system)["alive"]["state"] == "UP"
    assert one(box, {"id": "a", "probes": [{"type": "tcp", "port": 5000}]}, system)["alive"]["state"] == "UP"
    assert one(box, {"id": "a", "probes": [{"type": "tcp", "port": 9000}]}, system)["alive"]["state"] == "DOWN"   # 只聽外部網卡不算本機服務
    assert one(box, {"id": "a", "probes": [{"type": "tcp", "port": 1234}]}, system)["alive"]["state"] == "DOWN"
    got = one(box, {"id": "a", "probes": [{"type": "tcp", "port": 3780}]}, system)
    assert got["alive"]["proof_level"] == "liveness_only"
    assert any(f["label"] == "行程啟動時間" and f["value"] == iso(started) for f in got["alive"]["facts"])

    # 查不到聽埠表時退回連線測試
    assert one(box, {"id": "a", "probes": [{"type": "tcp", "port": 3780}]}, FakeSystem(connect=(True, False)))["alive"]["state"] == "UP"
    assert one(box, {"id": "a", "probes": [{"type": "tcp", "port": 3780}]}, FakeSystem(connect=(False, False)))["alive"]["state"] == "DOWN"

    procs = [{"pid": 21, "cmdline": "python bot.py --token SUPER-SECRET-TOKEN --mode live"},
             {"pid": 22, "cmdline": "python other.py"}]
    psys = FakeSystem(processes=procs, starts={21: started, 22: started})
    snap = scan(box, [{"id": "bot", "probes": [{"type": "process", "match": "bot.py", "match_all": ["--mode live"]}]}], psys)
    got = snap["projects"]["demo"]["services"][0]
    assert got["alive"]["state"] == "UP"
    assert "SUPER-SECRET-TOKEN" not in json.dumps(snap)          # 命令列不輸出（裡面可能有金鑰）
    assert one(box, {"id": "bot", "probes": [{"type": "process", "match": "bot.py", "match_all": ["--mode paper"]}]}, psys)["alive"]["state"] == "DOWN"
    assert one(box, {"id": "bot", "probes": [{"type": "process", "match": "bot.py"}]}, FakeSystem(processes=None))["alive"]["state"] == "NO_DATA"


def test_real_process_and_listener_lookup():
    system = probes.System()
    procs = system.processes()
    assert procs, "這台列不出行程清單"
    mine = [p for p in procs if p["pid"] == os.getpid()]
    assert mine and mine[0]["cmdline"]
    state, started, _note = system.process_info(os.getpid())
    assert state == "alive" and started is not None
    assert probes.awake_seconds() > 0


def test_artifact_file_probe(box):
    out = box / "proj" / "out"
    out.mkdir()
    system = FakeSystem()
    svc = {"id": "job", "probes": [{"type": "artifact", "glob": "out/*.json", "max_age_s": 3600, "min_bytes": 5}]}
    got = one(box, svc, system)
    assert got["fresh"]["state"] == "DOWN" and got["alive"]["state"] == "NO_DATA"
    old, new = out / "a.json", out / "b.json"
    old.write_text('{"n": 1}', encoding="utf-8")
    new.write_text('{"n": 2}', encoding="utf-8")
    t_old, t_new = (NOW - timedelta(hours=5)).timestamp(), (NOW - timedelta(minutes=10)).timestamp()
    os.utime(old, (t_old, t_old))
    os.utime(new, (t_new, t_new))
    got = one(box, svc, system)
    assert got["fresh"]["state"] == "FRESH"                    # 看最新的那個檔
    assert got["alive"]["state"] == "UP" and got["alive"]["proof_level"] == "output_verified"
    assert got["fresh"]["data_at"] == iso(datetime.fromtimestamp(t_new, UTC))
    os.utime(new, (t_old, t_old))
    assert one(box, svc, system)["fresh"]["state"] == "STALE"
    os.utime(new, (t_new, t_new))
    new.write_text("{}", encoding="utf-8")
    os.utime(new, (t_new, t_new))
    got = one(box, svc, system)
    assert got["fresh"]["state"] == "STALE" and "低於下限" in got["fresh"]["reason"]   # 檔案是新的但幾乎是空的


def _make_db(path: Path, rows: list) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ticks_1m (ts TEXT, price REAL)")
    conn.execute("CREATE TABLE secrets (k TEXT)")
    conn.execute("INSERT INTO secrets VALUES ('DB-SECRET-VALUE')")
    conn.executemany("INSERT INTO ticks_1m VALUES (?, ?)", [(r, 1.0) for r in rows])
    conn.commit()
    conn.close()


def test_artifact_sqlite_probe_is_read_only_and_injection_proof(box):
    db = box / "proj" / "data.db"
    _make_db(db, [iso(NOW - timedelta(days=5)), iso(NOW - timedelta(hours=2))])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    system = FakeSystem()
    base = {"type": "artifact", "sqlite_path": "data.db", "table": "ticks_1m", "ts_col": "ts"}

    got = one(box, {"id": "db", "probes": [{**base, "max_age_days": 1, "min_rows": 2}]}, system)
    assert got["fresh"]["state"] == "FRESH" and got["fresh"]["data_at"] == iso(NOW - timedelta(hours=2))
    assert one(box, {"id": "db", "probes": [{**base, "max_age_days": 0.01}]}, system)["fresh"]["state"] == "STALE"
    got = one(box, {"id": "db", "probes": [{**base, "min_rows": 100}]}, system)
    assert got["fresh"]["state"] == "STALE" and "低於下限" in got["fresh"]["reason"]
    assert one(box, {"id": "db", "probes": [{**base, "table": "nope"}]}, system)["fresh"]["state"] == "DOWN"
    assert one(box, {"id": "db", "probes": [{**base, "sqlite_path": "missing.db"}]}, system)["fresh"]["state"] == "DOWN"
    assert not (box / "proj" / "missing.db").exists()            # 唯讀開啟不會憑空建出資料庫

    # 繞過設定檢查、直接把惡意識別字塞給探針：照樣擋下來，資料表還在
    ctx = probes._Ctx(probes._Scan(system=system, now=NOW, home=box / "home", wake_grace_remaining_s=0), box / "proj", "project")
    for table, col in (('ticks_1m"; DROP TABLE ticks_1m; --', "ts"), ("ticks_1m", 'ts") FROM secrets; --'),
                       ("secrets WHERE 1=1 --", "k"), ("ticks_1m", "ts, (SELECT k FROM secrets)")):
        res = probes.run_probe({**base, "table": table, "ts_col": col}, ctx)
        assert res["output"] == "DOWN" and "不合法" in res["summary"]
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM ticks_1m").fetchone()[0] == 2
    conn.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before  # 探針前後資料庫檔一個位元組都沒變
    assert not list((box / "proj").glob("data.db-*"))             # 沒留下 journal、wal
    assert "DB-SECRET-VALUE" not in json.dumps(scan(box, [{"id": "db", "probes": [base]}], system))

    # 連線真的是唯讀的
    ro = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO ticks_1m VALUES ('x', 1)")
    ro.close()


def test_sqlite_timestamp_formats(box):
    epoch = (NOW - timedelta(hours=1)).timestamp()
    for value in (int(epoch), int(epoch * 1000), iso(NOW - timedelta(hours=1)), (NOW - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")):
        db = box / "proj" / "t.db"
        if db.exists():
            db.unlink()
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE t (ts)")
        conn.execute("INSERT INTO t VALUES (?)", (value,))
        conn.commit()
        conn.close()
        probe = {"type": "artifact", "sqlite_path": "t.db", "table": "t", "ts_col": "ts", "max_age_days": 1, "ts_naive_tz": "utc"}
        got = one(box, {"id": "db", "probes": [probe]}, FakeSystem())
        assert got["fresh"]["state"] == "FRESH", value
        assert got["fresh"]["data_at"] == iso(NOW - timedelta(hours=1)), value
    empty = box / "proj" / "e.db"
    conn = sqlite3.connect(empty)
    conn.execute("CREATE TABLE t (ts)")
    conn.commit()
    conn.close()
    got = one(box, {"id": "db", "probes": [{"type": "artifact", "sqlite_path": "e.db", "table": "t", "ts_col": "ts"}]}, FakeSystem())
    assert got["fresh"]["state"] == "STALE" and "沒有任何資料" in got["fresh"]["reason"]


def test_heartbeat_probe_uses_stale_check(box):
    proj = box / "proj"
    system = FakeSystem()
    svc = {"id": "bot", "probes": [{"type": "heartbeat", "path": "hb.json"}]}
    assert one(box, svc, system)["fresh"]["state"] == "DOWN"                 # 檔案不存在

    write_heartbeat(proj / "hb.json", build="abc1234", progress={"items_out": 12})
    got = one(box, svc, system)
    assert got["fresh"]["state"] == "FRESH" and got["alive"]["state"] == "UP" and got["alive"]["proof_level"] == "output_verified"

    write_heartbeat(proj / "hb.json", status="running")                      # 自報狀態字：一律 DOWN
    assert one(box, svc, system)["fresh"]["state"] == "DOWN"

    write_heartbeat(proj / "hb.json", progress={"items_out": 0})
    strict = {"id": "bot", "probes": [{"type": "heartbeat", "path": "hb.json", "min_items_out": 1}]}
    assert one(box, strict, system)["fresh"]["state"] == "STALE"             # 空跑

    write_heartbeat(proj / "hb.json", paused_until_ts=iso(NOW + timedelta(hours=2)),
                    last_attempt_ts=iso(NOW - timedelta(hours=5)), last_success_ts=iso(NOW - timedelta(hours=5)))
    got = one(box, svc, system)
    assert got["fresh"]["state"] == "PAUSED" and got["level"] == "idle"      # 預期暫停：灰色，不是綠也不是紅

    write_heartbeat(proj / "hb.json", x_dirty=True)
    got = one(box, svc, system)
    assert got["sync"]["state"] == "DIRTY" and got["level"] == "ok"          # 提示，不算異常

    write_heartbeat(proj / "hb.json", host="some-other-box", pid=4, pid_start_ts=iso(NOW - timedelta(days=1)))
    got = one(box, svc, system)
    assert got["fresh"]["state"] == "FRESH" and got["sync"]["state"] == "NO_DATA" and "遠端主機" in got["sync"]["reason"]

    # 真的行程：心跳帶自己的 pid 與啟動時間 → 存活證據來自心跳
    _state, started, _ = probes.System().process_info(os.getpid())
    now = datetime.now(UTC)
    write_heartbeat(proj / "hb.json", pid=os.getpid(), pid_start_ts=iso(started),
                    last_attempt_ts=iso(now), last_success_ts=iso(now))
    got = one(box, svc, probes.System(), now=now)
    assert got["alive"]["state"] == "UP" and got["fresh"]["state"] == "FRESH"
    assert any(f["label"] == "行程啟動時間" for f in got["alive"]["facts"])


# ---------- 三軸與時段 ----------

def test_active_window_pauses_instead_of_alarming(box):
    report = box / "proj" / "out.csv"
    report.write_text("x\n", encoding="utf-8")
    old = (NOW - timedelta(hours=20)).timestamp()
    os.utime(report, (old, old))
    probe_list = [{"type": "tcp", "port": 9100}, {"type": "artifact", "glob": "out.csv", "max_age_s": 600}]
    system = FakeSystem(listeners=[])
    base = {"id": "feed", "probes": probe_list, "timezone": "+08:00"}   # 固定位移：不靠這台有沒有裝 tzdata

    inside = one(box, {**base, "active_days": ["mon", "tue", "wed", "thu", "fri"], "active_hours": "08:45-13:45"}, system)
    assert inside["active"] is True and inside["alive"]["state"] == "DOWN" and inside["fresh"]["state"] == "STALE"

    night = one(box, {**base, "active_hours": "15:00-05:00"}, system)        # 跨夜時段，台北 12:00 不在裡面
    assert night["active"] is False and night["alive"]["state"] == "PAUSED" and night["fresh"]["state"] == "PAUSED"
    assert night["level"] == "idle" and night["fingerprint"] is None

    weekend = one(box, {**base, "active_days": ["sat", "sun"]}, system)
    assert weekend["active"] is False and weekend["level"] == "idle"

    overnight_in = one(box, {**base, "active_hours": "22:00-13:00"}, system)
    assert overnight_in["active"] is True and overnight_in["level"] == "bad"

    utc = one(box, {"id": "feed", "probes": probe_list, "timezone": "UTC", "active_hours": "03:00-05:00"}, system)
    assert utc["active"] is True
    fixed = one(box, {"id": "feed", "probes": probe_list, "timezone": "+08:00", "active_hours": "11:00-12:30"}, system)
    assert fixed["active"] is True


def test_proof_level_and_levels(box):
    started = NOW - timedelta(hours=1)
    report = box / "proj" / "out.csv"
    report.write_text("x\n", encoding="utf-8")
    fresh = (NOW - timedelta(minutes=5)).timestamp()
    os.utime(report, (fresh, fresh))
    system = FakeSystem(listeners=[("127.0.0.1", 9100, 5)], starts={5: started})
    hollow = one(box, {"id": "s", "probes": [{"type": "tcp", "port": 9100}]}, system)
    solid = one(box, {"id": "s", "probes": [{"type": "tcp", "port": 9100}, {"type": "artifact", "glob": "out.csv", "max_age_s": 3600}]}, system)
    assert (hollow["alive"]["state"], hollow["alive"]["proof_level"]) == ("UP", "liveness_only")
    assert (solid["alive"]["state"], solid["alive"]["proof_level"]) == ("UP", "output_verified")
    assert hollow["fresh"]["state"] == "N/A" and solid["fresh"]["state"] == "FRESH"

    mixed = one(box, {"id": "s", "probes": [{"type": "tcp", "port": 9100}, {"type": "tcp", "port": 9101}]}, system)
    assert mixed["alive"]["state"] == "DEGRADED" and mixed["level"] == "warn"

    fp1 = one(box, {"id": "s", "probes": [{"type": "tcp", "port": 9101}]}, system)["fingerprint"]
    fp2 = one(box, {"id": "s", "probes": [{"type": "tcp", "port": 9101}]}, system, now=NOW + timedelta(hours=3))["fingerprint"]
    assert fp1 and fp1 == fp2                                   # 同一個異常的指紋不隨時間變
    assert fp1 != mixed["fingerprint"]
    acked = one(box, {"id": "s", "probes": [{"type": "tcp", "port": 9101}], "acknowledged_until": iso(NOW + timedelta(hours=1))}, system)
    assert acked["acknowledged"] is True and acked["level"] == "bad"
    expired = one(box, {"id": "s", "probes": [{"type": "tcp", "port": 9101}], "acknowledged_until": iso(NOW - timedelta(hours=1))}, system)
    assert expired["acknowledged"] is False


def test_scan_all_summary_alerts_and_speed(box):
    report = box / "proj" / "out.csv"
    report.write_text("x\n", encoding="utf-8")
    fresh = (NOW - timedelta(minutes=5)).timestamp()
    os.utime(report, (fresh, fresh))
    system = FakeSystem(listeners=[("127.0.0.1", 9100, 5)], starts={5: NOW - timedelta(hours=1)})
    services = [
        {"id": "solid", "probes": [{"type": "tcp", "port": 9100}, {"type": "artifact", "glob": "out.csv", "max_age_s": 3600}]},
        {"id": "hollow", "probes": [{"type": "tcp", "port": 9100}]},
        {"id": "dead", "name": "死掉的服務", "probes": [{"type": "tcp", "port": 9101}]},
        {"id": "off", "enabled": False, "probes": [{"type": "tcp", "port": 9102}]},
        {"id": "broken", "probes": [{"type": "http", "url": "http://example.com/"}]},
    ]
    t0 = time.monotonic()
    snap = scan(box, services, system)
    assert time.monotonic() - t0 < 2.0 and snap["scan_ms"] < 2000
    summary = snap["summary"]
    assert (summary["services"], summary["ok"], summary["bad"], summary["warn"]) == (3, 2, 1, 0)
    assert (summary["output_verified"], summary["liveness_only"]) == (1, 1)
    assert summary["oldest_evidence_at"] == iso(NOW)
    assert [a["service_id"] for a in snap["alerts"]] == ["dead"]
    assert snap["alerts"][0]["text"] == "活著嗎 DOWN" and snap["alerts"][0]["fingerprint"]
    proj = snap["projects"]["demo"]
    assert proj["level"] == "bad" and [s["id"] for s in proj["services"]] == ["solid", "hollow", "dead"]
    assert len(proj["config_errors"]) == 1 and "broken" in proj["config_errors"][0]   # 壞設定講明，不拖垮其他服務
    assert probes.runtime_meta(snap)["summary"] == summary and "projects" not in probes.runtime_meta(snap)
    json.dumps(snap)   # 整份可序列化

    # 沒設任何探針的專案不出現；空的整體摘要
    empty = probes.scan_all(box / "state", entries=[{"id": "demo", "name": "Demo", "path": str(box / "proj")}], cfg={},
                            home=box / "home", now=NOW, system=system)
    assert empty["projects"] == {} and empty["summary"]["services"] == 0 and empty["summary"]["oldest_evidence_at"] is None


# ---------- 兩層設定 ----------

def test_two_layer_overlay_personal_overrides_project(box):
    proj = box / "proj"
    (proj / probes.PROJECT_FILE).write_text(
        "services:\n"
        "  - id: api\n    name: 共用 API\n    probes:\n      - {type: tcp, port: 8000}\n"
        "  - id: worker\n    probes:\n      - {type: process, match: worker.py}\n"
        "  - id: bad\n    probes:\n      - {type: http, url: 'http://example.com/'}\n", encoding="utf-8")
    cfg = {"probes": {"DEMO": {"services": [
        {"id": "api", "probes": [{"type": "tcp", "port": 9000}]},     # 同 id：個人蓋過專案
        {"id": "worker", "enabled": False},                           # 個人停用專案的服務
        {"id": "mine", "probes": [{"type": "tcp", "port": 9001}]},    # 只有個人有
        {"id": "ghost", "active_hours": "09:00-10:00"},               # 沒探針、專案也沒有：錯誤
    ]}}}
    services, errors, layers = probes.merged_services("demo", proj, cfg)
    by_id = {s["id"]: s for s in services}
    assert set(by_id) == {"api", "mine"}
    assert by_id["api"]["probes"][0]["port"] == 9000 and by_id["api"]["name"] == "共用 API"
    assert by_id["api"]["_source"] == "project+personal" and by_id["api"]["_probe_layer"] == "personal"
    assert by_id["mine"]["_source"] == "personal"
    assert layers == {"project": 2, "personal": 4}   # 各層讀到幾個合法的設定（ghost 格式合法，疊加時才被擋下）
    assert any("bad" in e for e in errors) and any("ghost" in e for e in errors)

    # 只蓋時段、不蓋探針：探針仍算專案層（路徑照專案層的規則）
    cfg2 = {"probes": {"demo": {"services": [{"id": "api", "active_hours": "09:00-18:00"}]}}}
    services, _errors, _layers = probes.merged_services("demo", proj, cfg2)
    api = next(s for s in services if s["id"] == "api")
    assert api["probes"][0]["port"] == 8000 and api["_probe_layer"] == "project" and api["active_hours"] == [[540, 1080]]

    (proj / probes.PROJECT_FILE).write_text("services: [oops\n", encoding="utf-8")
    services, errors, _ = probes.merged_services("demo", proj, {})
    assert services == [] and errors and probes.PROJECT_FILE in errors[0]
    assert probes.merged_services("demo", None, {}) == ([], [], {"project": 0, "personal": 0})


def test_apply_probe_op_writes_only_personal_layer(box):
    state, proj, home = box / "state", box / "proj", box / "home"
    collector.save_config(state, {**collector.load_config(state), "projects": [{"id": "demo", "path": str(proj)}], "parked_days": 7})
    (proj / probes.PROJECT_FILE).write_text("services:\n  - id: shared\n    probes:\n      - {type: tcp, port: 8000}\n", encoding="utf-8")
    project_file_before = (proj / probes.PROJECT_FILE).read_bytes()

    out = probes.apply_probe_op(state, "demo", {"op": "add_probe", "service": {"name": "My API"}, "probe": {"type": "tcp", "port": 9000}},
                                project_root=proj, home=home)
    assert out["personal_services"][0]["id"] == "my-api"
    probes.apply_probe_op(state, "demo", {"op": "add_probe", "service": {"id": "my-api"},
                                          "probe": {"type": "http", "url": "http://localhost:9000/health"}}, project_root=proj, home=home)
    cfg = collector.load_config(state)
    assert [p["type"] for p in cfg["probes"]["demo"]["services"][0]["probes"]] == ["tcp", "http"]
    assert cfg["projects"] == [{"id": "demo", "path": str(proj)}] and cfg["parked_days"] == 7   # 其他設定不受影響

    probes.apply_probe_op(state, "demo", {"op": "set_enabled", "service_id": "shared", "enabled": False}, project_root=proj, home=home)
    services, _e, _l = probes.merged_services("demo", proj, collector.load_config(state))
    assert [s["id"] for s in services] == ["my-api"]
    layers = probes.describe_layers(state, "demo", proj)
    assert [s["id"] for s in layers["project_services"]] == ["shared"] and len(layers["personal_services"]) == 2

    for bad in ({"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "http", "url": "http://example.com/"}},
                {"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "artifact", "sqlite_path": "a.db", "table": "t;x", "ts_col": "ts"}},
                {"op": "add_probe", "service": {}, "probe": {"type": "tcp", "port": 1}},
                {"op": "upsert", "service": {"id": "x", "probes": [{"type": "artifact", "glob": "\\\\srv\\share\\*"}]}},
                {"op": "nope"}, {"op": "replace", "services": "x"}, "nope"):
        with pytest.raises((ValueError, TypeError)):
            probes.apply_probe_op(state, "demo", bad, project_root=proj, home=home)
    with pytest.raises(FileNotFoundError):
        probes.apply_probe_op(state, "demo", {"op": "remove", "service_id": "nope"}, project_root=proj, home=home)
    with pytest.raises(ValueError):
        probes.apply_probe_op(state, "../evil", {"op": "replace", "services": []}, project_root=proj, home=home)

    probes.apply_probe_op(state, "demo", {"op": "remove", "service_id": "my-api"}, project_root=proj, home=home)
    probes.apply_probe_op(state, "demo", {"op": "replace", "services": []}, project_root=proj, home=home)
    assert "demo" not in collector.load_config(state)["probes"]
    assert (proj / probes.PROJECT_FILE).read_bytes() == project_file_before      # 專案的共用設定檔從頭到尾沒被動過


def test_poll_interval_and_timezones():
    assert probes.poll_interval({}, {}) == 60
    assert probes.poll_interval({"runtime": {"poll_interval_s": 30}}, {}) == 30
    assert probes.poll_interval({"runtime": {"poll_interval_s": 30}}, {probes.POLL_ENV: "15"}) == 15
    assert probes.poll_interval({"runtime": {"poll_interval_s": 1}}, {}) == 5
    assert probes.poll_interval({"runtime": "x"}, {probes.POLL_ENV: "abc"}) == 60
    assert probes.tz_for("UTC")[0] is UTC
    assert probes.tz_for("+08:00")[0].utcoffset(None) == timedelta(hours=8)
    tz, note = probes.tz_for("Not/AZone")
    assert tz is not None and "找不到時區" in note


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 真機排程查詢回歸測試")
def test_win_task_ps51_unrolls_multiple_names():
    """回歸測試：Windows PowerShell 5.1 的 ConvertFrom-Json 回傳陣列不可被 @(...) 包成二維並拼成單一字串。"""
    names = ["__omnikit_nonexistent_task_a__", "__omnikit_nonexistent_task_b__"]
    res = probes.System().query_win_tasks(names)
    assert set(res.keys()) == set(names)
    for name in names:
        assert res[name]["found"] is False
        assert res[name].get("error") != "沒有回傳這個工作"
        assert " ".join(names) not in str(res[name].get("error") or "")
