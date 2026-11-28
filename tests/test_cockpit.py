"""OmniKit 個人面板（Cockpit）單元與端到端契約測試。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.cockpit import collector, reconciler, server


TOKEN = "test-token"


def _http_json(url: str, *, method: str = "GET", payload: dict | None = None, content_type: str | None = "application/json",
               token: str | None = TOKEN, headers: dict | None = None) -> tuple[int, dict]:
    """寫入（POST、PATCH）預設帶測試用的 token；token=None 測沒帶的情況。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = dict(headers or {})
    if data is not None and content_type:
        headers["Content-Type"] = content_type
    if method not in ("GET", "HEAD") and token:
        headers.setdefault("X-OmniKit-Token", token)
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

    app = server.CockpitApp(state_dir=state, default_repo_root=None, t3_runner=lambda _: [], cache_ttl=0,
                            allowed_hosts=set(), token=TOKEN)
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
        allowed_hosts=set(),
        token=TOKEN,
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


def test_write_guard_host_allowlist_token_and_tailscale_readonly(short_tmp: Path):
    """KIT-A-01：不在白名單的 Host 一律 403；經 Tailscale（MagicDNS Host 或反代標頭）只能讀；本機寫入要 token；
    KIT-B-16：全部重新對帳要 confirm_all。"""
    state = short_tmp / "state"
    repo = short_tmp / "GuardApp"
    _init_git_repo(repo)
    collector.register_project(state, name="GuardApp", path=str(repo))
    app = server.CockpitApp(state_dir=state, default_repo_root=None, t3_runner=lambda _: [], cache_ttl=0,
                            allowed_hosts={"box.example.ts.net"}, token=TOKEN, reconcile_runner=lambda **_kw: {})
    httpd = server.create_server("127.0.0.1", 0, app=app)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        ts = {"Host": "box.example.ts.net:2389", "X-Forwarded-For": "100.64.0.9", "Tailscale-User-Login": "u@example.test"}
        assert _http_json(f"{base}/api/health", headers={"Host": "evil.example"})[0] == 403
        assert _http_json(f"{base}/", headers={"Host": "evil.example:3780"})[0] == 403
        st, ses = _http_json(f"{base}/api/session")
        assert st == 200 and ses == {"writable": True, "mode": "local", "token": TOKEN}
        st, ses = _http_json(f"{base}/api/session", headers=ts)
        assert st == 200 and ses["writable"] is False and ses["token"] is None
        assert _http_json(f"{base}/api/overview", headers=ts)[0] == 200
        add = f"{base}/api/projects/GuardApp/critiques"
        assert _http_json(add, method="POST", payload={"text": "x"}, headers=ts)[0] == 403
        assert _http_json(add, method="POST", payload={"text": "x"}, headers={"X-Forwarded-For": "100.64.0.9"})[0] == 403
        assert _http_json(add, method="POST", payload={"text": "x"}, token=None)[0] == 403
        assert _http_json(add, method="POST", payload={"text": "x"}, token="wrong")[0] == 403
        assert _http_json(add, method="POST", payload={"text": "x"}, headers={"Origin": "https://evil.example"})[0] == 403
        assert _http_json(f"{base}/api/settings", method="PATCH", payload={"t3_base_url": ""}, headers=ts)[0] == 403
        assert _http_json(add, method="POST", payload={"text": "本機可以寫"},
                          headers={"Origin": f"http://127.0.0.1:{httpd.server_address[1]}"})[0] == 201
        st_all, body = _http_json(f"{base}/api/reconcile-all", method="POST", payload={"only_stale": False})
        assert st_all == 400 and "confirm_all" in body["error"]
        assert _http_json(f"{base}/api/reconcile-all", method="POST", payload={"only_stale": False, "confirm_all": True})[0] == 202
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_host_name_and_tailnet_hosts():
    assert server.host_name("Box.Example.ts.net.:2389") == "box.example.ts.net"
    assert server.host_name("[::1]:3780") == "::1"
    assert server.host_name("127.0.0.1:3780") == "127.0.0.1"

    class R:
        returncode = 0
        stdout = json.dumps({"Self": {"DNSName": "box.example.ts.net."}})

    got = server.tailnet_hosts({"OMNIKIT_COCKPIT_HOSTS": "a.example.ts.net, "}, run=lambda *a, **k: R(), exe="tailscale")
    assert got == {"a.example.ts.net", "box.example.ts.net"}

    def boom(*a, **k):
        raise OSError("沒有 tailscale")

    assert server.tailnet_hosts({}, run=boom, exe="tailscale") == set()


def test_resolve_default_provider_reads_personal_dispatch_and_skips_manual_only(tmp_path: Path):
    """回歸測試：reconciler._resolve_default_provider 應正確讀個人 dispatch.md，跳過 manual_only（classes 空）。"""
    state = tmp_path / "state"
    pdir = state / "profiles" / "colleague"
    pdir.mkdir(parents=True)
    (state / "profile.json").write_text(json.dumps({"profile": "colleague"}), encoding="utf-8")
    (pdir / "AGENTS.md").write_text("# 測試規則\n", encoding="utf-8")
    (pdir / "dispatch.md").write_text(
        "# 分派\n\n```yaml\ninstances:\n"
        "  antigravity_manual: {driver: antigravity, classes: []}\n"
        "  antigravity_auto:   {driver: antigravity, classes: [gemini-fast, gemini-pro]}\n"
        "```\n",
        encoding="utf-8",
    )
    assert reconciler._resolve_default_provider(state_dir=state, environ={}) == "antigravity_auto"
    assert reconciler._resolve_default_provider(
        state_dir=state, environ={"OMNIKIT_RECONCILE_PROVIDER": "antigravity_override"}
    ) == "antigravity_override"

    # 沒有 dispatch.md 時退回預設 "antigravity"
    (pdir / "dispatch.md").unlink()
    assert reconciler._resolve_default_provider(state_dir=state, environ={}) == "antigravity"


def test_find_t3_cli_fallback_t3code_home_and_user_home(tmp_path: Path):
    """回歸測試：PATH 無 t3 時應自動 fallback 查 $T3CODE_HOME/bin 與 ~/.t3/bin（collector 與 t3_acp 一致）。"""
    import os
    import t3_acp

    exe_name = "t3.cmd" if os.name == "nt" else "t3"
    home_dir = tmp_path / "home"
    home_bin = home_dir / ".t3" / "bin" / exe_name
    home_bin.parent.mkdir(parents=True)
    home_bin.write_text("@echo off\n", encoding="utf-8")

    # 僅 ~/.t3/bin 存在
    assert collector._find_t3_cli(environ={"PATH": ""}, home=home_dir) == str(home_bin)
    assert t3_acp.find_t3_cli(environ={"PATH": ""}, home=home_dir) == str(home_bin)

    # 同時設 T3CODE_HOME 時優先於 ~/.t3/bin
    custom_home = tmp_path / "custom-t3"
    custom_bin = custom_home / "bin" / exe_name
    custom_bin.parent.mkdir(parents=True)
    custom_bin.write_text("@echo off\n", encoding="utf-8")
    env = {"PATH": "", "T3CODE_HOME": str(custom_home)}
    assert collector._find_t3_cli(environ=env, home=home_dir) == str(custom_bin)
    assert t3_acp.find_t3_cli(environ=env, home=home_dir) == str(custom_bin)


def test_unregistered_t3_project_friendly_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """回歸測試：資料夾未註冊為 T3 專案時，探測與對帳應回傳明確中文引導訊息。"""
    proj = tmp_path / "UnregisteredRepo"
    proj.mkdir()
    now_path = tmp_path / "NOW.md"

    monkeypatch.setattr(collector, "_find_t3_cli", lambda **_kw: "fake-t3")
    monkeypatch.setattr(
        collector,
        "_run_cmd",
        lambda *_a, **_kw: (1, "", f"Error: No T3 Code project matches '{proj}'"),
    )
    probed = collector.probe_t3_threads(proj)
    assert probed["available"] is False
    assert probed.get("unregistered") is True
    assert "尚未在 T3 Code 註冊" in probed["reason"]

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = f"Error: No T3 Code project matches '{proj}'"

    monkeypatch.setattr(reconciler.subprocess, "run", lambda *_a, **_kw: FakeProc())
    with pytest.raises(RuntimeError) as exc_info:
        reconciler.run_t3_reconcile(
            project_id="UnregisteredRepo",
            project_name="UnregisteredRepo",
            project_path=proj,
            now_path=now_path,
            provider="antigravity_auto",
        )
    assert "尚未加入 T3 Code 專案" in str(exc_info.value)
    assert "開啟並註冊" in str(exc_info.value)

    # 當面板佇列允許降級（allow_local_fallback=True）或無 t3 CLI 時，應無縫退回本機 Git 狀態同步而不報錯
    _init_git_repo(proj, message="initial local")
    fallback_res = reconciler.run_t3_reconcile(
        project_id="UnregisteredRepo",
        project_name="UnregisteredRepo",
        project_path=proj,
        now_path=now_path,
        provider="antigravity_auto",
        state_dir=tmp_path / "state",
        allow_local_fallback=True,
    )
    assert fallback_res["mode"] == "local_git"
    assert now_path.is_file()
    assert "UnregisteredRepo" in now_path.read_text(encoding="utf-8")


def test_exclusive_port_bind_security_headers_and_control_panel_apis(short_tmp: Path):
    """驗證 P0-1 排他埠綁定與順移、P1-1 Origin 埠號比對與 Sec-Fetch-Site 防護，以及控制面板 bootstrap / kit apply / starter project。"""
    state = short_tmp / "state"
    home = short_tmp / "home"
    (home / ".codex").mkdir(parents=True)
    (home / "Desktop" / "ExistingRepo").mkdir(parents=True)
    _init_git_repo(home / "Desktop" / "ExistingRepo")

    app = server.CockpitApp(
        state_dir=state,
        home_dir=home,
        default_repo_root=None,
        t3_runner=lambda _: [],
        cli_runner=lambda *_a, **_kw: (0, "[]", ""),
        cache_ttl=0,
        allowed_hosts=set(),
        token=TOKEN,
    )
    httpd = server.create_server("127.0.0.1", 0, app=app)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        # 1. 同埠第二次綁定必須拋出 OSError，且 bind_server(strict_port=False) 會自動順移
        with pytest.raises(OSError):
            dup = server.create_server("127.0.0.1", port, app=app)
            dup.server_close()
        fb = server.bind_server("127.0.0.1", port, app=app, strict_port=False)
        assert fb.server_address[1] > port
        fb.server_close()

        base = f"http://127.0.0.1:{port}"
        # 2. Sec-Fetch-Site 跨站阻擋與 Origin 不同埠阻擋
        assert _http_json(f"{base}/api/session", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
        st_ses, ses = _http_json(f"{base}/api/session", headers={"Sec-Fetch-Site": "same-origin"})
        assert st_ses == 200 and ses == {"writable": True, "mode": "local", "token": TOKEN}
        assert _http_json(
            f"{base}/api/kit/preview",
            method="POST",
            payload={},
            headers={"Origin": f"http://127.0.0.1:{port + 5}"},
        )[0] == 403

        # 3. Bootstrap 探索候選專案、9 個習慣與預設工作台
        st_b, boot = _http_json(f"{base}/api/bootstrap")
        assert st_b == 200
        assert len(boot["habits_catalog"]) == 9
        assert any(c["name"] == "ExistingRepo" for c in boot["candidate_projects"])

        # 4. 一鍵套用個人設定與精選工作台（含防假完工習慣與全部複選不設上限）
        st_ap, ap = _http_json(
            f"{base}/api/kit/apply",
            method="POST",
            payload={
                "answers": {
                    "name": "starter",
                    "language": "zh-TW",
                    "verbosity": "concise",
                    "autonomy": "balanced",
                    "domains": ["software-dev"],
                    "pains": ["anti-fake-done", "no-verification", "guesses", "scope-creep", "manual-steps"],
                    "evaluate_tools": False,
                },
                "tools": ["chrome-devtools-mcp", "gitleaks", "frontend-design"],
                "done_check": "block",
            },
        )
        assert st_ap == 200 and ap["ok"] is True and ap["active_profile"] == "starter"
        assert (state / "kit.yaml").is_file()
        assert (state / "profiles" / "starter" / "AGENTS.md").is_file()
        assert (home / ".codex" / "AGENTS.md").is_file()

        # 5. 零專案新手一鍵建立第一個專案與本機 NOW.md 歷史還原
        st_cp, cp = _http_json(
            f"{base}/api/projects/create",
            method="POST",
            payload={"name": "FirstDemo", "parent_dir": str(home / "Desktop")},
        )
        assert st_cp == 201 and cp["ok"] is True
        assert len(cp["starter_prompts"]) == 3
        st_hist, hist = _http_json(f"{base}/api/projects/FirstDemo/history")
        assert st_hist == 200 and len(hist["entries"]) >= 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_chinese_project_names_and_win32_dot_traversal_guard(short_tmp: Path):
    """回歸測試（P1-6 & P1-7）：支援中文專案名稱且兩個中文專案不撞代號；Win32 結尾句點與純句點如 '...' 必須在 mkdir/git init 前拒絕。"""
    state = short_tmp / "state"
    desktop = short_tmp / "Desktop"
    desktop.mkdir(parents=True)

    # 1. 純句點、結尾句點或 Windows 保留字必須直接拋出 ValueError，絕不可在 desktop 初始化 .git 或寫 README.md
    for bad_name in ("...", "..", ".", "bad.", "CON", "NUL.txt", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            collector.create_starter_project(state, name=bad_name, parent_dir=desktop)
    assert not (desktop / ".git").exists()
    assert not (desktop / "README.md").exists()

    # 2. 兩個中文專案名稱建立成功且代號各自獨立不覆蓋
    r1 = collector.create_starter_project(state, name="我的第一個網站", parent_dir=desktop, ok_prefix="$ok")
    r2 = collector.create_starter_project(state, name="AI自動化助手", parent_dir=desktop, ok_prefix="$ok")
    assert r1["project"]["id"] == "我的第一個網站"
    assert r2["project"]["id"] == "AI自動化助手"
    assert r1["project"]["id"] != r2["project"]["id"]
    assert any("$ok 驗收" in s for s in r1["starter_prompts"])
    assert (state / "status" / "我的第一個網站" / "NOW.md").is_file()
    assert (state / "status" / "AI自動化助手" / "NOW.md").is_file()


def test_non_loopback_client_forced_readonly_and_cross_site_api_blocked(short_tmp: Path):
    """回歸測試（P1-11 & P2）：非本機迴路 IP 即使偽造 Host: 127.0.0.1 也強制唯讀；跨站 Sec-Fetch-Site 連 GET /api/* 一併 403。"""
    state = short_tmp / "state"
    app = server.CockpitApp(
        state_dir=state,
        default_repo_root=None,
        t3_runner=lambda _: [],
        cache_ttl=0,
        allowed_hosts=set(),
        token=TOKEN,
    )
    httpd = server.create_server("127.0.0.1", 0, app=app)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{port}"
        # Sec-Fetch-Site: cross-site 讀取任何 /api/* 皆應回 403，但靜態首頁 / 可開啟
        assert _http_json(f"{base}/api/bootstrap", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
        assert _http_json(f"{base}/api/overview", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403

        # 模擬非 loopback client_address（例如綁定 0.0.0.0 時區網電腦偽造 Host: 127.0.0.1）
        handler_cls = httpd.RequestHandlerClass
        dummy = object.__new__(handler_cls)
        dummy.headers = {"Host": f"127.0.0.1:{port}"}
        dummy.client_address = ("192.168.1.88", 54321)
        why, is_remote = dummy._access()
        assert why is None
        assert is_remote is True
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_adopted_drift_preserved_across_foreground_apply_kit(short_tmp: Path):
    """回歸測試（P1-2）：使用者點選『採用外部修改（adopt）』後，前台控制面板套用工作台不得覆蓋該外部手改規則檔。"""
    import kit as kit_mod  # type: ignore

    state = short_tmp / "state"
    home = short_tmp / "home"
    (home / ".codex").mkdir(parents=True)

    app = server.CockpitApp(
        state_dir=state,
        home_dir=home,
        default_repo_root=None,
        t3_runner=lambda _: [],
        cli_runner=lambda *_a, **_kw: (0, "[]", ""),
        cache_ttl=0,
        allowed_hosts=set(),
        token=TOKEN,
    )
    app.apply_kit({"tools": ["gitleaks"], "done_check": "block"})
    codex_rules = home / ".codex" / "AGENTS.md"
    assert codex_rules.is_file()

    # 模擬使用者手改 ~/.codex/AGENTS.md 受管區塊內部，並在面板點選「採用外部修改」
    custom_marker = "\n# 使用者手寫保留條款：嚴禁覆蓋此段\n"
    orig_txt = codex_rules.read_text(encoding="utf-8")
    assert "<!-- omnikit:rules:end -->" in orig_txt
    codex_rules.write_text(
        orig_txt.replace("<!-- omnikit:rules:end -->", custom_marker + "<!-- omnikit:rules:end -->", 1),
        encoding="utf-8",
    )
    drifts = kit_mod.detect_drift(state, home)
    assert any(d["id"] == "rule:codex" for d in drifts)

    kit_mod.resolve_drift("rule:codex", "adopt", state=state, home=home, repo_root=app.repo_root)
    assert kit_mod.detect_drift(state, home) == []

    # 再次透過面板前台 apply_kit 切換工具，手改內容必須被完整保留
    res2 = app.apply_kit({"tools": ["gitleaks", "frontend-design", "exa"], "done_check": "log"})
    assert custom_marker in codex_rules.read_text(encoding="utf-8")
    # 一鍵修復同步（fix_doctor 預設 force_overwrite=False）同樣不得洗掉使用者 adopted 手改區塊（修 M-P1-5）
    app.fix_doctor()
    assert custom_marker in codex_rules.read_text(encoding="utf-8")
    # 未設 EXA_API_KEY 時 exa 應自動維持 disabled 並附帶清楚提醒
    assert any("EXA_API_KEY" in w for w in res2.get("warnings") or [])
    kdoc = kit_mod.load(state)
    assert kdoc["profiles"][kdoc["active_profile"]]["tools"]["exa"]["tier"] == "disabled"


def test_v021_review_regressions_anti_framing_collision_and_answer_merge(short_tmp: Path):
    """回歸測試（v0.2.1 雙跨家審查修復）：X-Frame-Options 防嵌、新專案撞名 409、精靈保留訪談欄位、無 T3 對帳不消紅燈。"""
    state = short_tmp / "state"
    home = short_tmp / "home"
    (home / ".claude").mkdir(parents=True)
    desktop = home / "Desktop"
    desktop.mkdir(parents=True)

    app = server.CockpitApp(
        state_dir=state,
        home_dir=home,
        default_repo_root=None,
        t3_runner=lambda _: [],
        cli_runner=lambda *_a, **_kw: (0, "[]", ""),
        cache_ttl=0,
        allowed_hosts=set(),
        token=TOKEN,
    )
    httpd = server.create_server("127.0.0.1", 0, app=app)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(f"{base}/", timeout=5) as resp:
            assert resp.headers.get("X-Frame-Options") == "DENY"
            assert "frame-ancestors 'none'" in (resp.headers.get("Content-Security-Policy") or "")

        # 純 Claude 環境 compatible_agents 對齊預選 5 項免金鑰套件（修 M-P0-1）
        _, boot = _http_json(f"{base}/api/bootstrap")
        assert boot["installed_agents"] == ["claude-code"]
        assert boot["done_check"] == "log"
        compat_default = [
            it["id"]
            for it in boot["workbench"]["items"]
            if it["enabled"] and "claude-code" in (it.get("compatible_agents") or [])
        ]
        assert len(compat_default) >= 5 and "claude-code-setup" in compat_default

        # 訪談欄位合併保留（修 M-P1-12）
        _http_json(
            f"{base}/api/kit/apply",
            method="POST",
            payload={
                "answers": {
                    "name": "alice",
                    "language": "zh-TW",
                    "verbosity": "concise",
                    "autonomy": "balanced",
                    "domains": ["software-dev"],
                    "pains": ["anti-fake-done"],
                    "evaluate_tools": True,
                    "background": "嵌入式韌體開發",
                    "projects": {"main": "FWCore", "frontend": "Panel"},
                }
            },
        )
        # 再次送不含 background / evaluate_tools 的局部 answers，不得洗掉既有值
        _http_json(
            f"{base}/api/kit/apply",
            method="POST",
            payload={
                "answers": {
                    "name": "alice",
                    "language": "zh-TW",
                    "verbosity": "detailed",
                    "autonomy": "hands-off",
                    "domains": ["software-dev"],
                    "pains": ["anti-fake-done"],
                }
            },
        )
        saved_ans = json.loads((state / "profiles" / "alice" / "answers.json").read_text(encoding="utf-8"))
        assert saved_ans["evaluate_tools"] is True
        assert saved_ans["background"] == "嵌入式韌體開發"

        # 建立新專案後同名第二次建立必須回 409 Conflict（修 M-P1-10）
        st_c1, _ = _http_json(f"{base}/api/projects/create", method="POST", payload={"name": "UniqueApp", "parent_dir": str(desktop)})
        assert st_c1 == 201
        st_c2, _ = _http_json(f"{base}/api/projects/create", method="POST", payload={"name": "UniqueApp", "parent_dir": str(desktop)})
        assert st_c2 == 409

        # 無 T3 本機退路對帳不得覆寫舊更新時間戳（修 M-P1-13）
        now_f = state / "status" / "UniqueApp" / "NOW.md"
        now_f.write_text("# UniqueApp\n\n- 更新時間：2020-01-01 00:00\n\n## 目前結論\n- 舊結論\n", encoding="utf-8")
        reconciler._fallback_local_git_reconcile(
            project_id="UniqueApp",
            project_name="UniqueApp",
            project_path=desktop / "UniqueApp",
            now_path=now_f,
            state_dir=state,
        )
        assert "2020-01-01 00:00" in now_f.read_text(encoding="utf-8")

        # 連「更新時間」標頭都沒有的舊 NOW.md，本機退路對帳亦不得刷掉檔案 mtime（修 PR #12 P2-9）
        headerless_now = state / "status" / "UniqueApp" / "HEADERLESS_NOW.md"
        headerless_now.write_text("# UniqueApp\n\n## 目前結論\n- 舊結論\n", encoding="utf-8")
        old_epoch = 1577836800.0  # 2020-01-01T00:00:00Z
        os.utime(headerless_now, (old_epoch, old_epoch))
        reconciler._fallback_local_git_reconcile(
            project_id="UniqueApp",
            project_name="UniqueApp",
            project_path=desktop / "UniqueApp",
            now_path=headerless_now,
            state_dir=state,
        )
        assert abs(headerless_now.stat().st_mtime - old_epoch) < 2.0
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_drift_restore_no_reentrant_lock_deadlock_and_unicode_shortcut(short_tmp: Path):
    """回歸測試（PR #12 跨家複審 P1-A / P1-B / P2-6）：漂移還原不死結、全失敗回滾 tier、Windows 原生 Unicode 捷徑不失真。"""
    import importlib.util
    import kit as kit_mod  # type: ignore

    state = short_tmp / "state"
    home = short_tmp / "home"
    (home / ".claude").mkdir(parents=True)

    app = server.CockpitApp(
        state_dir=state,
        home_dir=home,
        default_repo_root=None,
        t3_runner=lambda _: [],
        cli_runner=lambda *_a, **_kw: (0, "[]", ""),
        cache_ttl=0,
        allowed_hosts=set(),
        token=TOKEN,
    )
    app.apply_kit({"tools": ["gitleaks"], "done_check": "log"})

    # 1. P1-B：外部竄改 ~/.claude/CLAUDE.md 與 profile.json 後呼叫 resolve_drift(..., "restore") 必須立即成功不死結
    claude_md = home / ".claude" / "CLAUDE.md"
    tampered = claude_md.read_text(encoding="utf-8").replace("<!-- omnikit:rules:end -->", "\n# 外部誤改測試\n<!-- omnikit:rules:end -->", 1)
    claude_md.write_text(tampered, encoding="utf-8")
    assert any(d["id"] == "rule:claude-code" for d in kit_mod.detect_drift(state, home))

    t0 = time.monotonic()
    res_rule = kit_mod.resolve_drift("rule:claude-code", "restore", state=state, home=home, repo_root=app.repo_root)
    assert res_rule["ok"] is True
    assert (time.monotonic() - t0) < 5.0
    assert "# 外部誤改測試" not in claude_md.read_text(encoding="utf-8")
    assert not any(d["id"] == "rule:claude-code" for d in kit_mod.detect_drift(state, home))

    (state / "profile.json").write_text('{"profile": "ryan"}\n', encoding="utf-8")
    assert any(d["id"] == "profile:active" for d in kit_mod.detect_drift(state, home))
    res_prof = kit_mod.resolve_drift("profile:active", "restore", state=state, home=home, repo_root=app.repo_root)
    assert res_prof["ok"] is True
    assert json.loads((state / "profile.json").read_text(encoding="utf-8"))["profile"] == "default"

    # 2. P2-6：auto_plugin 啟用時若 CLI 全數失敗，回 ok=False 且 kit.yaml 的 tier 必須自動回滾為先前狀態
    kit_mod.patch(state, profile_patch={"tools": {"frontend-design": {"tier": "disabled"}}})
    res_fail = kit_mod.apply_tool_toggle(
        "frontend-design",
        "resident",
        state=state,
        home=home,
        repo_root=app.repo_root,
        runner=lambda *_a, **_kw: (1, "", "simulated offline failure"),
    )
    assert res_fail["ok"] is False
    assert res_fail["tier"] == "disabled"
    after_doc = kit_mod.load(state)
    assert after_doc["profiles"][after_doc["active_profile"]]["tools"]["frontend-design"]["tier"] == "disabled"

    # 3. P1-A：Windows 原生 Unicode 捷徑在含非 cp950/cp1252 字元與長路徑下不變成 ????
    if os.name == "nt":
        spec = importlib.util.spec_from_file_location("cockpit_cli_mod", str(ROOT / "scripts" / "cockpit.py"))
        assert spec and spec.loader
        cp_cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cp_cli)
        long_uni = short_tmp / ("長路徑 王小明 ⚡テスト " + ("x" * 110))
        st_auto = cp_cli.manage_autostart(
            long_uni / "state",
            action="install",
            repo_root=long_uni / "OmniKit 副本",
            port=37819,
            appdata=long_uni / "Roaming ⚡テスト",
            start_now=False,
        )
        assert st_auto["installed"] is True
        with open(cp_cli._win_fs_path(Path(st_auto["shortcut"])), "rb") as fh:
            info = cp_cli._read_windows_shortcut_info(fh.read())
        assert "⚡テスト" in info["arguments"]
        assert "????" not in info["arguments"]
        st_un = cp_cli.manage_autostart(
            long_uni / "state",
            action="uninstall",
            repo_root=long_uni / "OmniKit 副本",
            port=37819,
            appdata=long_uni / "Roaming ⚡テスト",
            start_now=False,
        )
        assert st_un["installed"] is False


def _tree_snapshot(root: Path) -> dict[str, str]:
    """root 底下每個項目（含資料夾、連結）的相對路徑與內容雜湊，用來確認一個資料夾完全沒被動過。"""
    import hashlib

    snap: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames:
            snap[os.path.relpath(os.path.join(dirpath, name), root)] = "dir"
        for name in filenames:
            p = Path(dirpath) / name
            snap[os.path.relpath(p, root)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return snap


def test_isolated_home_never_touches_config_dirs_named_by_env(short_tmp: Path, monkeypatch: pytest.MonkeyPatch):
    """回歸測試（2026-11-28 全套 pytest 改壞真設定）：控制面板用隔離家目錄時，
    行程環境變數 CLAUDE_CONFIG_DIR、CODEX_HOME、T3CODE_HOME 指的是使用者真的設定資料夾，套用設定與同步都不得寫進去。"""
    import homes as homes_mod  # type: ignore
    import kit as kit_mod  # type: ignore

    real = short_tmp / "real"
    claude_real = real / ".claude-retis"
    codex_real = real / ".codex-alt"
    t3_real = real / ".t3"
    for d in (claude_real / "skills", codex_real, t3_real / "userdata"):
        d.mkdir(parents=True)
    (claude_real / "CLAUDE.md").write_text("# 使用者真規則\n", encoding="utf-8")
    (claude_real / "settings.json").write_text("{}\n", encoding="utf-8")
    (codex_real / "AGENTS.md").write_text("# 使用者真規則\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_real))
    monkeypatch.setenv("CODEX_HOME", str(codex_real))
    monkeypatch.setenv("T3CODE_HOME", str(t3_real))
    before = _tree_snapshot(real)

    state = short_tmp / "state"
    home = short_tmp / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir(parents=True)

    app = server.CockpitApp(
        state_dir=state,
        home_dir=home,
        default_repo_root=None,
        t3_runner=lambda _: [],
        cli_runner=lambda *_a, **_kw: (0, "[]", ""),
        cache_ttl=0,
        allowed_hosts=set(),
        token=TOKEN,
    )
    app.apply_kit({"tools": ["gitleaks"], "done_check": "log"})
    app.apply_kit(
        {
            "answers": {
                "name": "alice",
                "language": "zh-TW",
                "verbosity": "concise",
                "autonomy": "balanced",
                "domains": ["software-dev"],
                "pains": ["anti-fake-done"],
            }
        }
    )
    kit_mod.resolve_drift("rule:claude-code", "restore", state=state, home=home, repo_root=app.repo_root)

    assert (home / ".claude" / "CLAUDE.md").is_file(), "隔離家目錄本身應該照常寫入規則"
    assert _tree_snapshot(real) == before, "環境變數指的真設定資料夾被寫到了"

    # 設定目錄探索：隔離家目錄沒給 environ 時，不得沿用這個行程（使用者真環境）的環境變數
    found = homes_mod.discover(home)
    assert not [f.path for f in found if str(f.path).startswith(str(real))]
    # 明確給 environ 時照舊採用（doctor、home_watch、selftest 都靠這個）
    (home / "envclaude").mkdir()
    found_explicit = homes_mod.discover(home, {"CLAUDE_CONFIG_DIR": str(home / "envclaude")})
    assert any(f.path.name == "envclaude" for f in found_explicit)

    # 給隔離家目錄跑外部 CLI 的環境：家目錄換掉，指向真設定資料夾的變數拿掉
    iso = homes_mod.isolated_environ(home)
    assert iso["USERPROFILE"] == str(home) and iso["HOME"] == str(home)
    assert not {"CLAUDE_CONFIG_DIR", "CODEX_HOME", "T3CODE_HOME"} & set(iso)
    sync_env = app._make_sync_env()
    assert not {"CLAUDE_CONFIG_DIR", "CODEX_HOME", "T3CODE_HOME"} & set(sync_env.environ)
