"""OmniKit 個人面板（Cockpit）單元與端到端契約測試。"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.cockpit import collector, server


def _http_json(url: str, *, method: str = "GET", payload: dict | None = None, content_type: str | None = "application/json") -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {}
    if data is not None and content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"raw": raw}
        return exc.code, body


@pytest.fixture
def short_tmp():
    """在系統 TEMP（含 windows-ci 長路徑與中文空白）下建立簡短暫存目錄，避免 pytest 多層前綴讓 Windows git init 超出 260 字元。"""
    with tempfile.TemporaryDirectory(prefix="ck") as d:
        yield Path(d)


def _init_git_repo(path: Path, message: str = "init") -> None:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["git", "-c", "core.longpaths=true", "init", "--template="],
        ["git", "-c", "core.longpaths=true", "config", "core.longpaths", "true"],
        ["git", "-c", "core.longpaths=true", "config", "user.name", "Test"],
        ["git", "-c", "core.longpaths=true", "config", "user.email", "test@example.com"],
    ):
        subprocess.run(args, cwd=str(path), check=True, capture_output=True)
    (path / "README.md").write_text("demo\n", encoding="utf-8")
    subprocess.run(["git", "-c", "core.longpaths=true", "add", "README.md"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "-c", "core.longpaths=true", "commit", "-m", message], cwd=str(path), check=True, capture_output=True)


def test_parse_now_md_four_quadrants_and_legacy_compat():
    text = """# CatOS 狀態板

- 更新時間：2026-11-24 14:30
- 專案路徑：`C:\\dev\\CatOS`（分支 main）
- 主線對話：模擬盤 Bot 後續工作

## 完工路徑
還有 2 步，完成 3 步（上坡探索中）
- [x] 完成 WebSocket 斷線重連
- [ ] 補齊壓測紀錄

## 目前結論
- 一律先跑 Demo 沙盒，嚴禁直連實盤
- 狀態統一落進 SQLite

## 不滿意待改
- [ ] 面板字太擠 -> 行動端卡片資訊重疊 -> 橫向溢位為 0 且字級 >= 16px
- [x] 舊版按鈕顏色太淡

## 等使用者決定的事
- 確認報警門檻

## 下一步
- 【等使用者】確認新風控門檻後開跑沙盒壓測
- 【agent 可直接做】整理結案報告
"""
    parsed = collector.parse_now_md(text)
    assert parsed["exists"] is True
    assert parsed["project_path"] == r"C:\dev\CatOS"
    assert parsed["progress"]["done"] == 3
    assert parsed["progress"]["total"] == 5
    assert parsed["progress"]["slope"] == "uphill"
    assert len(parsed["conclusions"]) == 2
    assert len(parsed["critiques"]) == 2
    assert parsed["critiques"][0]["done"] is False
    assert parsed["critiques"][0]["symptom"] == "面板字太擠"
    assert parsed["critiques"][0]["pain"] == "行動端卡片資訊重疊"
    assert parsed["critiques"][0]["criteria"] == "橫向溢位為 0 且字級 >= 16px"
    assert parsed["critiques"][1]["done"] is True
    assert parsed["decisions"] == ["確認報警門檻"]
    assert parsed["next_action"]["owner"] == "user"


def test_critique_write_preserves_header_timestamp_and_blocks_traversal(tmp_path: Path):
    state = tmp_path / "state"
    now_file = state / "status" / "DemoProj" / "NOW.md"
    now_file.parent.mkdir(parents=True)
    now_file.write_text(
        "# DemoProj\n\n- 更新時間：2026-11-20 09:00\n\n## 目前結論\n- 定案 A\n\n## 下一步\n- 【agent 可直接做】測試\n",
        encoding="utf-8",
    )

    res = collector.add_critique(
        state,
        "DemoProj",
        symptom="列表捲動卡頓",
        pain="手機滑起來會停住",
        criteria="WebKit 捲動流暢不鎖死",
    )
    assert res["ok"] is True
    assert len(res["critiques"]) == 1

    raw = now_file.read_text(encoding="utf-8")
    assert "- 更新時間：2026-11-20 09:00" in raw
    assert "定案 A" in raw
    assert "## 不滿意待改" in raw
    assert "列表捲動卡頓 -> 手機滑起來會停住 -> WebKit 捲動流暢不鎖死" in raw

    res2 = collector.toggle_critique(state, "DemoProj", 0, done=True)
    assert res2["critiques"][0]["done"] is True
    assert "- [x] 列表捲動卡頓" in now_file.read_text(encoding="utf-8")

    with pytest.raises(ValueError):
        collector.add_critique(state, "../escape", text="nope")


def test_lanes_reconciliation_and_multimachine_remote(short_tmp: Path):
    tmp_path = short_tmp
    state = tmp_path / "state"
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)

    # 1. Blocked 專案（有不滿意待改）
    p_blocked = tmp_path / "ProjBlocked"
    _init_git_repo(p_blocked)
    (state / "status" / "ProjBlocked").mkdir(parents=True)
    (state / "status" / "ProjBlocked" / "NOW.md").write_text(
        f"# ProjBlocked\n- 更新時間：2026-11-24 19:50\n- 專案路徑：`{p_blocked}`\n\n## 不滿意待改\n- [ ] 首屏太擁擠\n",
        encoding="utf-8",
    )

    # 2. Ready to settle 專案（有 completed 未結案對話）
    p_settle = tmp_path / "ProjSettle"
    _init_git_repo(p_settle)
    (state / "status" / "ProjSettle").mkdir(parents=True)
    (state / "status" / "ProjSettle" / "NOW.md").write_text(
        f"# ProjSettle\n- 更新時間：2026-11-24 19:50\n- 專案路徑：`{p_settle}`\n\n## 下一步\n- 【agent 可直接做】發布\n",
        encoding="utf-8",
    )

    # 3. Parked 遠端專案（10 天沒動、本機無目錄）
    (state / "status" / "RemoteOld").mkdir(parents=True)
    (state / "status" / "RemoteOld" / "NOW.md").write_text(
        "# RemoteOld\n- 更新時間：2026-11-10 10:00\n- 專案路徑：`Z:\\not-here\\RemoteOld`\n\n## 目前結論\n- 已封版\n",
        encoding="utf-8",
    )

    def fake_t3(path: Path):
        if path.resolve() == p_settle.resolve():
            return [{
                "threadId": "t-settle",
                "title": "已完成待結案",
                "status": "completed",
                "settled": False,
                "itemCount": 220,
                "updatedAt": "2026-11-24T11:55:00+00:00",
                "link": "https://app.t3.codes/threads/e1/t-settle",
            }]
        return []

    ov = collector.collect_overview(state, now=now, default_repo_root=None, t3_runner=fake_t3)
    by_id = {p["id"]: p for p in ov["projects"]}
    assert by_id["ProjBlocked"]["lane"] == "blocked_on_me"
    assert by_id["ProjSettle"]["lane"] == "ready_to_settle"
    assert by_id["RemoteOld"]["lane"] == "parked"
    assert by_id["RemoteOld"]["remote_only"] is True
    assert ov["summary"]["blocked_on_me"] == 1
    assert ov["summary"]["ready_to_settle"] == 1
    assert ov["summary"]["parked"] == 1


def test_http_server_crud_and_security(short_tmp: Path):
    tmp_path = short_tmp
    state = tmp_path / "state"
    repo = tmp_path / "MyApp"
    _init_git_repo(repo)
    collector.register_project(state, name="MyApp", path=str(repo))

    app = server.CockpitApp(state_dir=state, default_repo_root=None, t3_runner=lambda _: [], cache_ttl=0)
    httpd = server.create_server("127.0.0.1", 0, app=app)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{port}"
        st, body = _http_json(f"{base}/api/overview")
        assert st == 200
        assert body["summary"]["total"] == 1

        # 缺 Content-Type 應拒回 400
        st_ct, _ = _http_json(f"{base}/api/projects/MyApp/critiques", method="POST", payload={"text": "x"}, content_type="text/plain")
        assert st_ct == 400

        # 無 NOW.md 時新增不滿意待改應自動建檔
        st_add, add_res = _http_json(f"{base}/api/projects/MyApp/critiques", method="POST", payload={"text": "手機端按鈕太小"})
        assert st_add == 201
        assert len(add_res["critiques"]) == 1

        # 讀取 NOW.md 原文
        st_now, now_res = _http_json(f"{base}/api/projects/MyApp/now")
        assert st_now == 200
        assert now_res["exists"] is True
        assert "手機端按鈕太小" in now_res["content"]

        # 設定無效 URL 應拒回 400
        st_bad_url, _ = _http_json(f"{base}/api/settings", method="PATCH", payload={"t3_base_url": "javascript:alert(1)"})
        assert st_bad_url == 400

        # 讀取工具名冊疊層
        st_tools, tools_res = _http_json(f"{base}/api/tools")
        assert st_tools == 200
        assert tools_res["available"] is True
        assert tools_res["counts"]["total"] > 0
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_reconcile_queue_single_and_batch_api(short_tmp: Path):
    """驗證單專案與全部過期專案背景自動對帳佇列、遠端略過與狀態刷新。"""
    import time

    tmp_path = short_tmp
    state = tmp_path / "state"
    repo_local = tmp_path / "LocalProj"
    _init_git_repo(repo_local)
    collector.register_project(state, name="LocalProj", path=str(repo_local))

    # 遠端專案（無本機目錄）應在批次對帳時自動跳過
    (state / "status" / "RemoteProj").mkdir(parents=True)
    (state / "status" / "RemoteProj" / "NOW.md").write_text(
        "# RemoteProj\n- 更新時間：2026-11-10 10:00\n- 專案路徑：`Z:\\nonexistent\\RemoteProj`\n",
        encoding="utf-8",
    )

    called: list[str] = []

    def fake_reconcile(*, project_id: str, project_name: str, project_path: Path, now_path: Path, **_kw):
        called.append(project_id)
        now_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        now_path.parent.mkdir(parents=True, exist_ok=True)
        now_path.write_text(
            f"# {project_name}\n- 更新時間：{now_str}\n- 專案路徑：`{project_path}`\n\n"
            "## 完工路徑\n還有 1 步，完成 3 步（下坡）\n\n## 目前結論\n- 自動對帳完成\n\n## 下一步\n- 【agent 可直接做】發布\n",
            encoding="utf-8",
        )
        return {"thread_id": "th-rec-1", "thread_url": "https://t3.example.ts.net:2388/threads/e1/th-rec-1", "message": "ok"}

    app = server.CockpitApp(
        state_dir=state,
        default_repo_root=None,
        t3_runner=lambda _: [],
        reconcile_runner=fake_reconcile,
        cache_ttl=0,
    )
    httpd = server.create_server("127.0.0.1", 0, app=app)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{port}"
        # 遠端專案單獨觸發對帳應拒絕 400
        st_rem, _ = _http_json(f"{base}/api/projects/RemoteProj/reconcile", method="POST", payload={})
        assert st_rem == 400

        # 一鍵對帳全部過期專案
        st_all, res_all = _http_json(f"{base}/api/reconcile-all", method="POST", payload={"only_stale": True})
        assert st_all == 202
        assert len(res_all["queued"]) == 1
        assert res_all["queued"][0]["project_id"] == "LocalProj"

        # 等待單一背景 worker 完成
        for _ in range(40):
            _, st_rec = _http_json(f"{base}/api/reconcile/status")
            if not st_rec["busy"] and st_rec["jobs"].get("LocalProj", {}).get("status") == "done":
                break
            time.sleep(0.05)

        assert called == ["LocalProj"]
        _, ov_after = _http_json(f"{base}/api/overview")
        local_after = next(p for p in ov_after["projects"] if p["id"] == "LocalProj")
        assert local_after["stale"] is False
        assert local_after["now"]["conclusions"] == ["自動對帳完成"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_mobile_web_engineering_guardrails():
    """靜態守門：驗證 PWA 前端遵守行動端與 WebApp 工程底線。"""
    static_dir = ROOT / "engine" / "cockpit" / "static"
    css = (static_dir / "style.css").read_text(encoding="utf-8")
    html = (static_dir / "index.html").read_text(encoding="utf-8")

    # 禁用值檢查
    assert "100vh" not in css
    assert "background-attachment: fixed" not in css
    assert "content-visibility: auto" not in css
    assert "black-translucent" not in html

    # 必備行動端保護檢查
    assert "100dvh" in css
    assert "overscroll-behavior: contain" in css
    assert "touch-action: pan-y" in css
    assert "-webkit-overflow-scrolling: touch" in css
    assert "font-size: 16px" in css
    assert "@supports (-webkit-touch-callout: none)" in css
    assert "@media (display-mode: standalone)" in css
    assert "viewport-fit=cover" in html
    assert "manifest.webmanifest" in html
