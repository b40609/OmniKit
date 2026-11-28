"""監控者自保與背景快照（控制平面 L1 模組 3）的 pytest。

涵蓋：運行態三軸併進總覽與 snapshot.json、背景巡檢與它的自心跳、/api/runtime 與探針設定 API 的本機限定
（經 Tailscale 一律 403）、看門狗 watchdog-tick 的熔斷，以及工作排程的登記（一律注入假的 schtasks，不動這台的排程器）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.cockpit import collector, probes, server

TOKEN = "test-token"
TAILSCALE = {"Host": "box.example.ts.net:2389", "X-Forwarded-For": "100.64.0.9", "Tailscale-User-Login": "u@example.test"}
NOW = datetime(2026, 11, 27, 4, 0, 0, tzinfo=UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _load_cli():
    spec = importlib.util.spec_from_file_location("cockpit_cli_runtime", str(ROOT / "scripts" / "cockpit.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def http_json(url: str, *, method: str = "GET", payload: dict | None = None, headers: dict | None = None,
              token: str | None = TOKEN) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = dict(headers or {})
    if data is not None:
        headers["Content-Type"] = "application/json"
    if method != "GET" and token:
        headers.setdefault("X-OmniKit-Token", token)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"raw": raw}


class FakeSystem(probes.System):
    def __init__(self, listeners=None, starts=None):
        super().__init__()
        self.rows = listeners if listeners is not None else []
        self.starts = starts or {}

    def listeners(self):
        return self.rows

    def process_info(self, pid):
        return ("alive", self.starts[pid], "") if pid in self.starts else ("dead", None, "")

    def processes(self):
        return []


@pytest.fixture
def box():
    with tempfile.TemporaryDirectory(prefix="rt") as d:
        base = Path(d)
        for name in ("state", "proj", "home"):
            (base / name).mkdir()
        collector.register_project(base / "state", name="Demo", path=str(base / "proj"), project_id="Demo")
        yield base


def set_probes(box: Path, services: list[dict]) -> None:
    cfg = collector.load_config(box / "state")
    cfg["probes"] = {"Demo": {"services": services}}
    collector.save_config(box / "state", cfg)


def make_app(box: Path, system: probes.System | None = None) -> server.CockpitApp:
    return server.CockpitApp(state_dir=box / "state", home_dir=box / "home", default_repo_root=None, t3_runner=lambda _p: [],
                             cache_ttl=0, allowed_hosts={"box.example.ts.net"}, token=TOKEN, probe_system=system or FakeSystem())


@pytest.fixture
def served(box):
    """起一個真的 HTTP 伺服器（臨時埠、隔離狀態目錄、假的系統事實）。"""
    system = FakeSystem(listeners=[("127.0.0.1", 9100, 5)], starts={5: datetime.now(UTC) - timedelta(hours=1)})
    app = make_app(box, system)
    httpd = server.create_server("127.0.0.1", 0, app=app)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield box, app, f"http://127.0.0.1:{httpd.server_address[1]}", system
    finally:
        app.stop_runtime_poller()
        httpd.shutdown()
        httpd.server_close()


# ---------- 總覽整合 ----------

def test_overview_merges_runtime_into_blocked_lane_without_touching_now_contract(box):
    set_probes(box, [
        {"id": "up", "probes": [{"type": "tcp", "port": 9100}]},
        {"id": "dead", "name": "報價服務", "probes": [{"type": "tcp", "port": 9101}]},
    ])
    system = FakeSystem(listeners=[("127.0.0.1", 9100, 5)], starts={5: NOW - timedelta(hours=1)})
    runtime = probes.scan_all(box / "state", home=box / "home", now=NOW, system=system, default_repo_root=None)
    baseline = collector.collect_overview(box / "state", now=NOW, default_repo_root=None, t3_runner=lambda _p: [], runtime={"projects": {}})
    ov = collector.collect_overview(box / "state", now=NOW, default_repo_root=None, t3_runner=lambda _p: [], runtime=runtime)
    proj, base_proj = ov["projects"][0], baseline["projects"][0]

    assert base_proj["lane"] != "blocked_on_me" and base_proj["runtime"] is None
    assert proj["lane"] == "blocked_on_me" and proj["health"] == "blocked"
    assert any("1 個服務異常" in r and "報價服務" in r and "沒在跑" in r for r in proj["block_reasons"])
    # NOW.md、Git、T3 三源對帳的契約不受影響：過期判定與原因一個字都沒變
    assert proj["stale"] == base_proj["stale"] and proj["stale_reasons"] == base_proj["stale_reasons"]
    assert proj["commands"] == base_proj["commands"]
    assert proj["runtime_counts"] == {"services": 2, "ok": 1, "warn": 0, "bad": 1, "idle": 0}
    assert [s["id"] for s in proj["runtime"]["services"]] == ["up", "dead"]
    assert (ov["summary"]["runtime_services"], ov["summary"]["runtime_bad"], ov["summary"]["runtime_warn"]) == (2, 1, 0)
    assert ov["runtime"]["summary"]["bad"] == 1 and "projects" not in ov["runtime"]
    assert baseline["summary"]["runtime_services"] == 0

    # 已確認（acknowledged_until 還沒到）的異常不再把專案推進「卡在你身上」，但面板上仍看得到
    set_probes(box, [{"id": "dead", "probes": [{"type": "tcp", "port": 9101}], "acknowledged_until": iso(NOW + timedelta(hours=2))}])
    runtime = probes.scan_all(box / "state", home=box / "home", now=NOW, system=system, default_repo_root=None)
    proj = collector.collect_overview(box / "state", now=NOW, default_repo_root=None, t3_runner=lambda _p: [], runtime=runtime)["projects"][0]
    assert not any("服務異常" in r for r in proj["block_reasons"]) and proj["runtime_counts"]["bad"] == 1


def test_drift_also_goes_to_blocked_lane(box):
    set_probes(box, [{"id": "api", "probes": [{"type": "tcp", "port": 9100}]}])
    runtime = probes.scan_all(box / "state", home=box / "home", now=NOW, system=FakeSystem([("127.0.0.1", 9100, 5)], {5: NOW}),
                              default_repo_root=None)
    svc = runtime["projects"]["Demo"]["services"][0]
    svc["sync"] = {"state": "DRIFT", "reason": "改碼後沒有重啟", "facts": [], "sources": []}
    svc["level"] = "warn"
    proj = collector.collect_overview(box / "state", now=NOW, default_repo_root=None, t3_runner=lambda _p: [], runtime=runtime)["projects"][0]
    assert proj["lane"] == "blocked_on_me" and any("要留意" in r and "改碼後沒重啟" in r for r in proj["block_reasons"])


def test_snapshot_merge_keeps_overview_and_stays_bounded(box):
    state = box / "state"
    set_probes(box, [{"id": "up", "probes": [{"type": "tcp", "port": 9100}]}])
    system = FakeSystem(listeners=[("127.0.0.1", 9100, 5)], starts={5: NOW - timedelta(hours=1)})
    rt1 = probes.scan_all(state, home=box / "home", now=NOW, system=system, default_repo_root=None)
    ov = collector.collect_overview(state, now=NOW, default_repo_root=None, t3_runner=lambda _p: [], runtime=rt1)
    path = collector.write_snapshot(state, ov, runtime=rt1)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["generated_at"] == iso(NOW) and doc["overview_generated_at"] == iso(NOW) and doc["wake_grace_active"] is False
    assert doc["summary"]["total"] == 1 and doc["runtime"]["projects"]["Demo"]["services"][0]["alive"]["state"] == "UP"

    # 背景巡檢之後每輪只給運行態：總覽留著，generated_at 往前走，各專案底下的三軸一起換新
    system.rows = []
    sizes = []
    for i in range(1, 6):
        later = NOW + timedelta(minutes=i)
        rt = probes.scan_all(state, home=box / "home", now=later, system=system, default_repo_root=None, wake_grace_remaining_s=30 if i == 5 else 0)
        collector.write_snapshot(state, runtime=rt)
        sizes.append(path.stat().st_size)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["generated_at"] == iso(NOW + timedelta(minutes=5)) and doc["overview_generated_at"] == iso(NOW)
    assert doc["summary"]["total"] == 1 and doc["projects"][0]["id"] == "Demo"
    assert doc["projects"][0]["runtime"]["services"][0]["alive"]["state"] == "DOWN"
    assert doc["wake_grace_active"] is True
    assert max(sizes[:4]) - min(sizes[:4]) < 64, sizes      # 寫再多輪大小也不會長大
    assert not list(path.parent.glob(".omnikit-tmp-*"))      # 原子寫入沒留下暫存檔

    # 較舊的總覽晚一步寫進來：不會把比較新的運行態蓋回去
    collector.write_snapshot(state, ov, runtime=rt1)
    assert json.loads(path.read_text(encoding="utf-8"))["generated_at"] == iso(NOW + timedelta(minutes=5))


def test_latest_runtime_prefers_fresh_snapshot_then_falls_back_to_live_scan(box):
    state = box / "state"
    set_probes(box, [{"id": "f", "probes": [{"type": "artifact", "glob": "out.txt", "max_age_s": 3600}]}])
    canned = {"generated_at": iso(NOW - timedelta(minutes=2)), "summary": {}, "alerts": [], "projects": {"Demo": {"id": "Demo", "services": [], "marker": 1}}}
    collector.write_snapshot(state, runtime=canned)
    assert collector.latest_runtime(state, now=NOW, default_repo_root=None)["projects"]["Demo"]["marker"] == 1

    live = collector.latest_runtime(state, now=NOW + timedelta(minutes=10), default_repo_root=None)   # 快照超過 5 分鐘：不採信
    svc = live["projects"]["Demo"]["services"][0]
    assert "marker" not in live["projects"]["Demo"] and svc["fresh"]["state"] == "DOWN"                # 當場掃：產出檔不存在

    ov = collector.collect_overview(state, now=NOW + timedelta(minutes=10), default_repo_root=None, t3_runner=lambda _p: [])
    assert ov["projects"][0]["lane"] == "blocked_on_me" and ov["summary"]["runtime_bad"] == 1


# ---------- API：本機可寫、Tailscale 只能看 ----------

def test_runtime_api_local_write_and_tailscale_read_only(served):
    box, _app, base, _system = served
    st, body = http_json(f"{base}/api/runtime")
    assert st == 200 and body["summary"]["services"] == 0 and body["poller"]["running"] is False and body["watchdog"]["installed"] is False
    # server_time：前端拿它當時間基準判斷快照過期，不靠看面板那台裝置的時鐘
    assert abs((datetime.fromisoformat(body["server_time"]) - datetime.now(UTC)).total_seconds()) < 30

    add = {"op": "add_probe", "service": {"name": "API"}, "probe": {"type": "tcp", "port": 9100}}
    st, body = http_json(f"{base}/api/projects/Demo/probes", method="POST", payload=add)
    assert st == 200 and body["ok"] is True
    svc = body["runtime"]["services"][0]
    assert svc["alive"]["state"] == "UP" and svc["alive"]["proof_level"] == "liveness_only" and svc["id"] == "api"
    assert collector.load_config(box / "state")["probes"]["Demo"]["services"][0]["probes"] == [{"type": "tcp", "host": "127.0.0.1", "port": 9100}]

    st, layers = http_json(f"{base}/api/projects/Demo/probes")
    assert st == 200 and [s["id"] for s in layers["personal_services"]] == ["api"] and layers["merged"][0]["source"] == "personal"

    # 經 Tailscale：看得到三軸與探針設定，改不了任何東西（帶對的 token 也一樣）
    st, body = http_json(f"{base}/api/runtime", headers=TAILSCALE)
    assert st == 200 and body["summary"]["ok"] == 1
    assert http_json(f"{base}/api/projects/Demo/probes", headers=TAILSCALE)[0] == 200
    before = (box / "state" / "cockpit" / "config.json").read_bytes()
    for path, payload in (("/api/projects/Demo/probes", add), ("/api/runtime/refresh", {}),
                          ("/api/projects/Demo/probes", {"op": "remove", "service_id": "api"})):
        st, err = http_json(f"{base}{path}", method="POST", payload=payload, headers=TAILSCALE)
        assert st == 403 and "Tailscale" in err["error"], path
        st, _ = http_json(f"{base}{path}", method="POST", payload=payload, headers={"Host": "box.example.ts.net"})
        assert st == 403, path
    assert (box / "state" / "cockpit" / "config.json").read_bytes() == before

    # 本機寫入的其他防線照舊：沒 token、跨站、Origin 埠號不對都 403
    assert http_json(f"{base}/api/runtime/refresh", method="POST", payload={}, token=None)[0] == 403
    assert http_json(f"{base}/api/runtime/refresh", method="POST", payload={}, headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert http_json(f"{base}/api/projects/Demo/probes", method="POST", payload=add, headers={"Origin": "http://127.0.0.1:1"})[0] == 403
    assert http_json(f"{base}/api/runtime", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert http_json(f"{base}/api/runtime", headers={"Host": "evil.example"})[0] == 403


def test_probes_api_validation_and_refresh(served):
    box, _app, base, system = served
    url = f"{base}/api/projects/Demo/probes"
    bad_cases = [
        {"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "http", "url": "http://example.com/"}},
        {"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "http", "url": "http://169.254.169.254/"}},
        {"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "tcp", "host": "10.0.0.1", "port": 22}},
        {"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "artifact", "sqlite_path": "a.db", "table": "t; DROP TABLE t", "ts_col": "ts"}},
        {"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "artifact", "glob": "..\\..\\x.txt"}},
        {"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "heartbeat", "path": "\\\\server\\share\\hb.json"}},
        {"op": "add_probe", "service": {"name": "x"}, "probe": {"type": "exec", "command": "calc"}},
        {"op": "bogus"},
    ]
    for payload in bad_cases:
        st, err = http_json(url, method="POST", payload=payload)
        assert st == 400 and err.get("error"), payload
    assert "probes" not in json.loads((box / "state" / "cockpit" / "config.json").read_text(encoding="utf-8"))   # 一個都沒存進去
    assert http_json(f"{base}/api/projects/NoSuch/probes", method="POST", payload=bad_cases[0])[0] == 404
    assert http_json(f"{base}/api/projects/NoSuch/probes")[0] == 404
    assert http_json(f"{base}/api/projects/..%2Fevil/probes", method="POST", payload=bad_cases[0])[0] == 400
    assert http_json(url, method="POST", payload={"op": "remove", "service_id": "nope"})[0] == 404

    add = {"op": "add_probe", "service": {"name": "API"}, "probe": {"type": "tcp", "port": 9100}}
    assert http_json(url, method="POST", payload=add)[0] == 200
    st, ov = http_json(f"{base}/api/overview")
    assert st == 200 and ov["projects"][0]["runtime"]["services"][0]["level"] == "ok" and ov["summary"]["runtime_bad"] == 0

    system.rows = []                                                         # 服務死了
    st, body = http_json(f"{base}/api/runtime/refresh", method="POST", payload={})
    assert st == 200 and body["summary"]["bad"] == 1 and body["alerts"][0]["service_id"] == "api" and body["alerts"][0]["fingerprint"]
    st, ov = http_json(f"{base}/api/overview")
    assert ov["projects"][0]["lane"] == "blocked_on_me" and ov["runtime"]["summary"]["bad"] == 1

    st, body = http_json(url, method="POST", payload={"op": "set_enabled", "service_id": "api", "enabled": False})
    assert st == 200 and body["runtime"] is None                             # 停用後不再巡這個服務
    st, ov = http_json(f"{base}/api/overview")
    assert ov["projects"][0]["lane"] != "blocked_on_me" and ov["summary"]["runtime_services"] == 0


# ---------- 背景巡檢與自心跳 ----------

def test_poller_writes_snapshot_and_self_heartbeat(box):
    set_probes(box, [{"id": "up", "probes": [{"type": "tcp", "port": 9100}]}])
    app = make_app(box, FakeSystem(listeners=[("127.0.0.1", 9100, 5)], starts={5: datetime.now(UTC) - timedelta(hours=1)}))
    cdir = box / "state" / "cockpit"
    poller = app.start_runtime_poller(interval=0.2)
    try:
        assert app.start_runtime_poller() is poller                # 不會開出第二條
        deadline = time.monotonic() + 10
        while poller.rounds < 3 and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        app.stop_runtime_poller()
        poller.join(timeout=10)
    assert poller.rounds >= 3 and poller.errors == 0 and not poller.is_alive()

    snap = json.loads((cdir / "snapshot.json").read_text(encoding="utf-8"))
    assert snap["runtime"]["projects"]["Demo"]["services"][0]["alive"]["state"] == "UP"
    assert snap["generated_at"] == snap["runtime"]["generated_at"] and snap["wake_grace_active"] is False

    hb_doc = json.loads((cdir / "poller-heartbeat.json").read_text(encoding="utf-8"))
    assert hb_doc["name"] == "cockpit-poller" and hb_doc["pid"] == os.getpid() and hb_doc["build"] == server.SERVER_VERSION
    assert hb_doc["progress"]["items_out"] == 1
    assert not any(k in hb_doc for k in ("status", "state", "ok", "healthy", "running"))     # 只有事實，沒有狀態字
    res = probes.stale_check.check_file(cdir / "poller-heartbeat.json", datetime.now(UTC), {})
    assert res["verdict"] == "FRESH", res["reasons"]
    import jsonschema

    schema = json.loads((ROOT / "engine" / "schema" / "heartbeat.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(hb_doc, schema)

    status = app.poller_status()
    assert status["running"] is False and status["rounds"] >= 3 and status["heartbeat"]["verdict"] == "FRESH"
    # 巡檢停了以後，心跳自己會過期：這就是看門狗看的訊號
    later = probes.stale_check.check_file(cdir / "poller-heartbeat.json", datetime.now(UTC) + timedelta(minutes=10), {"skip_pid": True})
    assert later["verdict"] == "STALE"


def test_poller_failed_round_does_not_refresh_heartbeat(box, monkeypatch):
    app = make_app(box)
    hb = app.poller_heartbeat_path()
    app.poll_once()
    first = hb.read_bytes()

    def boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(collector, "write_snapshot", boom)
    with pytest.raises(OSError):
        app.poll_once()
    assert hb.read_bytes() == first                                # 這一輪沒成功：心跳不能更新
    poller = app.start_runtime_poller(interval=0.1)
    deadline = time.monotonic() + 10
    while poller.errors < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    app.stop_runtime_poller()
    poller.join(timeout=10)
    assert poller.errors >= 2 and poller.rounds == 0 and "disk full" in (poller.last_error or "")   # 失敗不會讓執行緒死掉
    assert hb.read_bytes() == first
    assert app.poller_status()["snapshot_error"]


def test_wake_grace_flows_into_runtime_and_snapshot(box):
    out = box / "proj" / "out.txt"
    out.write_text("x\n", encoding="utf-8")
    old = time.time() - 8 * 3600
    os.utime(out, (old, old))
    set_probes(box, [{"id": "job", "probes": [{"type": "artifact", "glob": "out.txt", "max_age_s": 3600}]}])
    app = make_app(box)
    clock = {"awake": 100.0, "wall": time.time()}
    app.wake = probes.WakeDetector(awake_clock=lambda: clock["awake"], wall_clock=lambda: clock["wall"])

    rt = app.poll_once()
    assert rt["wake_grace_active"] is False and rt["projects"]["Demo"]["services"][0]["fresh"]["state"] == "STALE"
    assert rt["summary"]["bad"] == 1

    clock["awake"] += 60
    clock["wall"] += 60 + 8 * 3600                                 # 電腦睡了 8 小時
    rt = app.poll_once()
    svc = rt["projects"]["Demo"]["services"][0]
    assert rt["wake_grace_active"] is True and rt["wake_grace_remaining_s"] == 180 and rt["last_wake_at"]
    assert svc["fresh"]["state"] == "PAUSED" and rt["summary"]["bad"] == 0 and rt["alerts"] == []
    snap = json.loads((box / "state" / "cockpit" / "snapshot.json").read_text(encoding="utf-8"))
    assert snap["wake_grace_active"] is True

    for step in (90, 100):                                         # 寬限照醒著的時間倒數：90 秒後還在，190 秒後結束
        clock["awake"] += step
        clock["wall"] += step
        rt = app.poll_once()
        assert rt["wake_grace_active"] is (step == 90)
    assert rt["wake_grace_active"] is False and rt["projects"]["Demo"]["services"][0]["fresh"]["state"] == "STALE"


# ---------- 看門狗 ----------

class World:
    """假的面板：alive、version 可以改；記下看門狗重啟與停止了幾次。"""

    def __init__(self, cli, state: Path):
        self.cli = cli
        self.state = state
        self.alive = False
        self.version = server.SERVER_VERSION
        self.launch_ok = True
        self.launched: list[int] = []
        self.stopped: list[int] = []

    def health(self, _host, _port, **_kw):
        return (True, {"service": "omnikit-cockpit", "version": self.version}) if self.alive else (False, {})

    def launch(self, _state, **kw):
        self.launched.append(kw["preferred_port"])
        assert kw["open_browser"] is False
        return {"ok": True, "url": "http://127.0.0.1:1/"} if self.launch_ok else {"ok": False, "error": "啟動逾時"}

    def stop(self, _state, **kw):
        self.stopped.append(kw["default_port"])
        return {"ok": True}

    def tick(self, minutes: float) -> dict:
        return self.cli.watchdog_tick(self.state, repo_root=ROOT, port=37811, now=NOW + timedelta(minutes=minutes),
                                      health=self.health, launcher=self.launch, stopper=self.stop)


def test_watchdog_restarts_dead_panel_with_circuit_breaker(box):
    cli = _load_cli()
    w = World(cli, box / "state")
    results = [w.tick(m) for m in (0, 10, 20, 30, 40, 50)]
    assert [r["last_action"] for r in results] == ["restarted"] * 3 + ["breaker_open"] * 3
    assert len(w.launched) == 3 and w.stopped == []                # 一小時最多 3 次，之後停手；死掉的面板不用先停
    assert results[2]["ok"] is True and results[3]["ok"] is False and results[3]["breaker_open"] is True
    doc = json.loads((box / "state" / "cockpit" / "watchdog-state.json").read_text(encoding="utf-8"))
    assert doc["breaker_open"] is True and len(doc["restarts"]) == 3 and doc["max_restarts_per_hour"] == 3
    assert "沒有回應" in doc["last_reason"]
    log = (box / "state" / "cockpit" / "watchdog.log").read_text(encoding="utf-8")
    assert log.count("restarted") == 3 and log.count("breaker_open") == 3

    app = make_app(box)
    status = app.watchdog_status()
    assert status["breaker_open"] is True and status["last_action"] == "breaker_open" and status["installed"] is False

    assert w.tick(61)["last_action"] == "restarted" and len(w.launched) == 4      # 最舊那次滑出一小時：解除熔斷
    w.launch_ok = False
    failed = w.tick(71)
    assert failed["last_action"] == "restart_failed" and failed["ok"] is False


def test_watchdog_poller_heartbeat_needs_two_stale_ticks(box):
    cli = _load_cli()
    state = box / "state"
    w = World(cli, state)
    w.alive = True
    hb = state / "cockpit" / "poller-heartbeat.json"

    def beat(minutes: float) -> None:
        probes.stale_check.write_self_heartbeat(hb, NOW + timedelta(minutes=minutes), 60, 60, [], name="cockpit-poller")

    # 面板剛啟動、還沒寫出第一份心跳：不算異常
    collector.write_utf8_atomic(state / "cockpit" / "server.json", json.dumps({"host": "127.0.0.1", "port": 37811, "started_at": iso(NOW)}))
    assert w.tick(1)["last_action"] == "none" and w.tick(1)["consecutive_poller_stale"] == 0

    beat(9)
    assert w.tick(10)["last_action"] == "none"
    first = w.tick(20)                                             # 心跳過期第一次：先記著（電腦可能剛醒）
    assert first["last_action"] == "none" and first["consecutive_poller_stale"] == 1 and w.launched == []
    beat(29)
    assert w.tick(30)["consecutive_poller_stale"] == 0             # 下一次恢復了：歸零，沒有誤殺

    assert w.tick(40)["consecutive_poller_stale"] == 1
    second = w.tick(50)                                            # 連續兩次都過期：停掉卡住的面板再拉起來
    assert second["last_action"] == "restarted" and w.stopped == [37811] and w.launched == [37811]
    assert "連續 2 次" in second["last_reason"]

    # 心跳檔一直沒出現（面板早就啟動了）也一樣處理
    hb.unlink()
    collector.write_utf8_atomic(state / "cockpit" / "server.json", json.dumps({"host": "127.0.0.1", "port": 37811, "started_at": iso(NOW)}))
    assert w.tick(120)["consecutive_poller_stale"] == 1
    assert w.tick(130)["last_action"] == "restarted"

    w.version = "0.0.1"                                            # 面板跑的是舊碼：換新
    old = w.tick(300)
    assert old["last_action"] == "restarted" and "舊版" in old["last_reason"]


def test_watchdog_task_registration_uses_injected_scheduler_only(box, monkeypatch):
    cli = _load_cli()
    state = box / "state"

    def never(_args):
        raise AssertionError("測試不可以動這台真的工作排程器")

    monkeypatch.setattr(cli, "_run_schtasks", never)
    monkeypatch.setattr(cli, "probe_cockpit_health", lambda *_a, **_kw: (False, {}))
    monkeypatch.setenv("OMNIKIT_NO_LAUNCH", "1")
    appdata = box / "Roaming"

    # 預設（沒注入排程器）：測試用的 appdata、OMNIKIT_NO_LAUNCH 都會讓它跳過，不會呼叫 schtasks
    res = cli.manage_autostart(state, action="install", repo_root=ROOT, port=37811, appdata=appdata, start_now=False)
    assert res["watchdog"]["managed"] is False
    assert cli._real_scheduler_allowed(None, "install")[0] is False
    off = cli.manage_autostart(state, action="install", repo_root=ROOT, port=37811, appdata=appdata, start_now=False, watchdog=False)
    assert off["watchdog"]["managed"] is False

    calls: list[list[str]] = []
    registered: set[str] = set()

    def fake(args):
        calls.append(list(args))
        name = args[args.index("/TN") + 1]
        if args[0] == "/Create":
            registered.add(name)
            return 0, "SUCCESS"
        if args[0] == "/Delete":
            return (0, "SUCCESS") if name in registered and not registered.discard(name) else (1, "ERROR")
        return (0, name) if name in registered else (1, "ERROR")

    res = cli.manage_autostart(state, action="install", repo_root=ROOT, port=37811, appdata=appdata, start_now=False, scheduler=fake)
    wd = res["watchdog"]
    name = wd["task_name"]
    assert wd["installed"] is True and name.startswith("OmniKit Cockpit Watchdog ") and registered == {name}
    create = calls[0]
    assert create[:3] == ["/Create", "/TN", name] and "/XML" in create and "/F" in create
    assert not {"/RU", "/RP", "/RL"} & set(create)                 # 不指定帳號密碼、不要求最高權限：登記不用系統管理員
    xml = (state / "cockpit" / "watchdog-task.xml").read_text(encoding="utf-16")
    assert "<Interval>PT10M</Interval>" in xml and "<RunLevel>LeastPrivilege</RunLevel>" in xml
    assert "<LogonType>InteractiveToken</LogonType>" in xml and "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "HighestAvailable" not in xml and "Password" not in xml and "S4U" not in xml
    ps1 = (state / "cockpit" / "watchdog-tick.ps1").read_text(encoding="utf-8")
    assert "watchdog-tick" in ps1 and "--port 37811" in ps1 and str(state) in ps1
    marker = json.loads((state / "cockpit" / "watchdog-task.json").read_text(encoding="utf-8"))
    assert marker["task_name"] == name and marker["interval_min"] == 10
    assert make_app(box).watchdog_status()["installed"] is True

    assert cli.manage_autostart(state, action="status", repo_root=ROOT, port=37811, appdata=appdata, scheduler=fake)["watchdog"]["installed"] is True
    gone = cli.manage_autostart(state, action="uninstall", repo_root=ROOT, port=37811, appdata=appdata, scheduler=fake)["watchdog"]
    assert gone["installed"] is False and registered == set()
    for leftover in ("watchdog-task.xml", "watchdog-tick.ps1", "watchdog-task.json"):
        assert not (state / "cockpit" / leftover).exists()
    assert make_app(box).watchdog_status()["installed"] is False
    again = cli.manage_autostart(state, action="uninstall", repo_root=ROOT, port=37811, appdata=appdata, scheduler=fake)["watchdog"]
    assert again["installed"] is False                             # 本來就沒有也算移除成功

    # 登記失敗要講明，不能當成裝好了
    failed = cli.manage_watchdog_task(state, action="install", repo_root=ROOT, port=37811, scheduler=lambda _a: (1, "ERROR: Access is denied."))
    assert failed["installed"] is False and "Access is denied" in failed["error"]
    assert not (state / "cockpit" / "watchdog-task.json").exists()

    assert cli.watchdog_task_name(collector.default_state_dir()) == "OmniKit Cockpit Watchdog"
    assert cli.watchdog_task_name(box / "other") != cli.watchdog_task_name(state)


# ---------- 面板 UI 的接線（真瀏覽器實測另外跑；這裡擋的是有人把接點改掉卻沒發現） ----------

def test_panel_ui_wires_three_axes_probe_form_and_stale_banner():
    static = ROOT / "engine" / "cockpit" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    js = (static / "app.js").read_text(encoding="utf-8")
    css = (static / "style.css").read_text(encoding="utf-8")
    sw = (static / "sw.js").read_text(encoding="utf-8")

    # 快照過期橫幅：純前端判斷，連續 2 輪失聯或 generated_at 凍結超過 5 分鐘
    assert 'id="stale-banner"' in html and 'role="alert"' in html and "控制平面失聯或快照過期" in html
    assert html.index('id="stale-banner"') < html.index('id="home-root"')
    assert "const RT_FROZEN_MS = 5 * 60 * 1000;" in js and "state.rtFails >= 2" in js and "frozenMs > RT_FROZEN_MS" in js
    assert "data.server_time" in js

    # 三軸：三個問題各自一顆燈，五種長相都有文字
    for needle in ('["alive", "活著嗎"], ["sync", "版本對嗎"], ["fresh", "資料新嗎"]', "在跑，已證實有產出", "在跑，只證實活著",
                   "版本漂移", "資料沒更新", "/api/runtime/refresh", 'op: "add_probe"', 'op: "set_enabled"'):
        assert needle in js, needle
    for cls in (".rt-dot.rt-solid", ".rt-dot.rt-hollow", ".rt-dot.rt-amber", ".rt-dot.rt-red", ".rt-dot.rt-gray", ".stale-banner"):
        assert cls in css, cls

    # 會寫入的控制項一律掛 data-write-only：經 Tailscale 開啟（body.is-readonly）時整個藏起來
    assert "body.is-readonly [data-write-only]" in css
    for control in ('data-rt-probe-form="${esc(p.id)}" data-write-only', "data-rt-refresh data-write-only",
                    'class="rt-add" data-write-only'):
        assert control in js, control
    assert js.count("data-rt-enable=") == js.count('data-name="${esc(s.name)}" data-write-only') + js.count('data-name="${esc(svc.name)}" data-write-only') == 2

    # 靜態外殼有改就要換快取名，舊的 service worker 快取才會被清掉
    assert 'CACHE_NAME = "omnikit-cockpit-v6"' in sw
