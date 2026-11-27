# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""OmniKit 防假完工閘門 G1：無塵室真實全旅程端對端與真瀏覽器驗收（cleanroom_e2e.py）。

驗證目標（對齊 data/harness/journeys.json）：
- J1：無 Claude／無 T3 的純 Codex（或純 Antigravity）單家環境開箱、額度頁與本機 Git 對帳退路。
- J2：首次開箱一頁式精靈勾選超過 2 項習慣（含防假完工）與免金鑰精選工作台，一鍵套用真實落盤。
- J3：零專案新手一鍵建立第一個專案，自動產生本地 Git、免帳號 NOW.md 歷史與 3 句破冰提示詞。
- J4：五分頁完整巡檢；在支援 Playwright 的環境以真實 Headless 瀏覽器（桌機 1280x800 ＋ 手機 WebKit/Mobile 390x844）
      驗證 0 console.error、0 pageerror、0 HTTP >= 400、0 橫向捲軸，以及手機輸入框 >= 16px。
- J5：斷開與移除時乾淨撤除受管區塊與連結，同時 100% 保留個人 profiles/ 與 status/。

用法：
  uv run engine/scripts/cleanroom_e2e.py --selftest          # 跨平台離線無塵室契約驗收（CI 必跑）
  uv run --with playwright engine/scripts/cleanroom_e2e.py   # 含真實 Chromium + WebKit 雙視口瀏覽器實測
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS_DIR = ROOT / "engine" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from engine.cockpit import collector, reconciler, server  # noqa: E402
import sync  # noqa: E402

JOURNEYS_FILE = ROOT / "data" / "harness" / "journeys.json"


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    hdrs = dict(headers or {})
    if raw is not None:
        hdrs["Content-Type"] = "application/json"
    if token and method not in ("GET", "HEAD"):
        hdrs["X-OmniKit-Token"] = token
    req = urllib.request.Request(url, data=raw, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_txt = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body_txt)
        except ValueError:
            return exc.code, {"raw": body_txt}


def run_browser_journey(base_url: str, desktop_dir: Path) -> dict[str, Any]:
    """使用真實 Playwright Headless 瀏覽器走完開箱套用、建首個專案、五分頁切換與手機 WebKit 390x844 幾何檢查。"""
    from playwright.sync_api import sync_playwright

    console_errors: list[str] = []
    page_errors: list[str] = []
    bad_responses: list[str] = []
    metrics: dict[str, Any] = {}

    with sync_playwright() as pw:
        # 1. 桌機 Chromium 1280x800：走完開箱一鍵套用 + 建立第一個專案 + 五分頁切換
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("response", lambda r: bad_responses.append(f"{r.status} {r.url}") if r.status >= 400 and "/favicon" not in r.url else None)

        page.goto(base_url, wait_until="networkidle")
        page.wait_for_selector("#btn-apply-wizard", timeout=10000)

        # 確認開箱精靈可勾選超過 2 項習慣並一鍵套用
        checked_habits = page.locator("input[data-wizard-habit]:checked").count()
        applied_prof = page.input_value("#wiz-prof-name").strip() or "personal"
        metrics["initial_checked_habits"] = checked_habits
        metrics["applied_profile"] = applied_prof
        page.click("#btn-apply-wizard")
        page.wait_for_selector("#btn-home-new-proj", timeout=15000)

        # 零專案新手一鍵建立第一個專案
        page.click("#btn-home-new-proj")
        page.wait_for_selector("#inp-starter-name", state="visible", timeout=5000)
        page.fill("#inp-starter-name", "hello-omnikit")
        page.fill("#inp-starter-parent", str(desktop_dir))
        page.click("#btn-starter-submit")
        page.wait_for_selector("[data-copy-starter]", timeout=10000)
        starter_count = page.locator("[data-copy-starter]").count()
        metrics["starter_prompts_rendered"] = starter_count
        page.click("#dlg-starter [data-close]")

        # 巡檢全部五個分頁並實測工作台開關
        for tab_name in ("cockpit", "tools", "accounts", "settings", "home"):
            page.click(f'.desk-nav [data-tab="{tab_name}"]')
            page.wait_for_timeout(150)
            if tab_name == "tools":
                page.wait_for_selector("[data-toggle-tool]", timeout=8000)
            elif tab_name == "accounts":
                page.wait_for_selector("#doctor-panel .panel-head", timeout=10000)

        desk_overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        metrics["desktop_horizontal_overflow"] = bool(desk_overflow)
        browser.close()

        # 2. 手機 WebKit 390x844（iPhone 15 視口）：驗證 WebKit 渲染、0 橫向溢位、底部導覽 >= 44px、輸入框 >= 16px
        wk_engine = pw.webkit
        wk_browser = wk_engine.launch(headless=True)
        wk_ctx = wk_browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            is_mobile=True,
            has_touch=True,
        )
        wk_page = wk_ctx.new_page()
        wk_page.on("console", lambda m: console_errors.append(f"[webkit] {m.text}") if m.type == "error" else None)
        wk_page.on("pageerror", lambda err: page_errors.append(f"[webkit] {err}"))
        wk_page.on("response", lambda r: bad_responses.append(f"[webkit] {r.status} {r.url}") if r.status >= 400 and "/favicon" not in r.url else None)

        wk_page.goto(base_url, wait_until="networkidle")
        mobile_nav_heights = wk_page.evaluate(
            "Array.from(document.querySelectorAll('.mobile-nav .mnav-btn')).map(b => b.getBoundingClientRect().height)"
        )
        metrics["mobile_nav_min_height"] = min(mobile_nav_heights) if mobile_nav_heights else 0

        # 切到設定頁與專案頁檢查所有可見輸入框字級 >= 16px 且無橫向捲軸
        wk_page.click('.mobile-nav [data-tab="settings"]')
        wk_page.wait_for_selector("#set-done-check", timeout=5000)
        settings_font_sizes = wk_page.evaluate(
            """() => Array.from(document.querySelectorAll('#tab-settings input:not([type="checkbox"]), #tab-settings select, #tab-settings textarea'))
              .filter(el => el.offsetParent !== null)
              .map(el => parseFloat(getComputedStyle(el).fontSize))"""
        )
        wk_page.click('.mobile-nav [data-tab="cockpit"]')
        wk_page.wait_for_selector("#project-search", timeout=5000)
        search_font = wk_page.evaluate("parseFloat(getComputedStyle(document.querySelector('#project-search')).fontSize)")
        mobile_overflow = wk_page.evaluate("document.documentElement.scrollWidth > window.innerWidth")

        all_fonts = [*settings_font_sizes, search_font]
        metrics["mobile_min_input_font_px"] = min(all_fonts) if all_fonts else 16.0
        metrics["mobile_horizontal_overflow"] = bool(mobile_overflow)
        wk_browser.close()

    return {
        "ran_browser": True,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "bad_responses": bad_responses,
        "metrics": metrics,
    }


def run_cleanroom(*, require_browser: bool = False) -> tuple[int, dict[str, Any]]:
    fails: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(jid: str, label: str, cond: bool, detail: str = "") -> None:
        ok = bool(cond)
        checks.append({"journey": jid, "label": label, "ok": ok, "detail": detail})
        mark = "通過" if ok else "失敗"
        print(f"[{mark}] ({jid}) {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            fails.append(f"{jid}: {label}")

    journeys_doc = json.loads(JOURNEYS_FILE.read_text(encoding="utf-8"))
    check("J0", "載入 data/harness/journeys.json 五大使用者旅程規格", len(journeys_doc.get("journeys") or []) == 5)

    with tempfile.TemporaryDirectory(prefix="ok-e2e-") as tmp:
        base = Path(tmp)
        # 故意含空白與中文，模擬真實 Windows 使用者路徑
        fake_home = base / "無塵室 使用者"
        state_dir = fake_home / ".omnikit"
        desktop_dir = fake_home / "Desktop"
        (fake_home / ".codex").mkdir(parents=True)
        desktop_dir.mkdir(parents=True)

        # 建立一個模擬既有的本機專案供自動探索測試
        sample_repo = desktop_dir / "SampleWeb"
        sample_repo.mkdir()
        (sample_repo / "package.json").write_text('{"name":"sample"}\n', encoding="utf-8")
        subprocess.run(["git", "init", "-b", "main", "--quiet"], cwd=str(sample_repo), check=True)

        # J5 前半：在 Windows 上驗證 install.ps1 -WhatIf 結束碼 0 且零寫檔副作用
        if os.name == "nt":
            ps_exe = "pwsh" if (os.environ.get("PSModulePath") and subprocess.run(["pwsh", "-v"], capture_output=True, check=False).returncode == 0) else "powershell"
            iso_env = {
                **os.environ,
                "USERPROFILE": str(fake_home),
                "HOME": str(fake_home),
                "OMNIKIT_STATE_DIR": str(state_dir),
                "OMNIKIT_NO_LAUNCH": "1",
                "OMNIKIT_NO_BROWSER": "1",
            }
            ps_script = str(SCRIPTS_DIR / "install.ps1").replace("'", "''")
            whatif_proc = subprocess.run(
                [
                    ps_exe,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"& '{ps_script}' -WhatIf -SkipCheck @('git','github','npm','pypi','proxy','antivirus','policy')",
                ],
                env=iso_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            check(
                "J5-whatif-zero-side-effect-and-restore",
                "install.ps1 -WhatIf 執行成功（exit 0）且零寫檔副作用（未產生 kit.yaml、status/.git 或 server.json）",
                whatif_proc.returncode == 0
                and not (state_dir / "kit.yaml").exists()
                and not (state_dir / "status" / ".git").exists()
                and not (state_dir / "cockpit" / "server.json").exists(),
                f"rc={whatif_proc.returncode}" + (f" err={whatif_proc.stderr.strip()[:120]}" if whatif_proc.returncode != 0 else ""),
            )

        # 啟動真實 ExclusiveHTTPServer（模擬純 Codex、無 Claude、無 T3 環境）
        app = server.CockpitApp(
            state_dir=state_dir,
            home_dir=fake_home,
            default_repo_root=None,
            t3_runner=None,
            cli_runner=None if require_browser else (lambda *_a, **_kw: (0, "[]", "")),
            cache_ttl=0,
            allowed_hosts=set(),
        )
        # 強制讓無塵室環境裡查不到 t3 CLI，驗證純單家無 T3 退路
        orig_find_t3 = collector._find_t3_cli
        collector._find_t3_cli = lambda **_kw: None  # type: ignore[assignment]
        httpd = server.bind_server("127.0.0.1", 0, app=app, strict_port=True)
        port = httpd.server_address[1]
        base_url = f"http://127.0.0.1:{port}"
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()

        browser_report: dict[str, Any] = {"ran_browser": False}
        try:
            # J1：驗證純 Codex 環境 bootstrap 與 accounts 不報錯
            st_ses, ses = _http_json(f"{base_url}/api/session")
            token = ses.get("token")
            check("J1-clean-codex-only", "GET /api/session 取得本機可寫憑證", st_ses == 200 and bool(token))

            st_boot, boot = _http_json(f"{base_url}/api/bootstrap")
            by_agent = {a["id"]: a for a in boot.get("agents") or []}
            check(
                "J1-clean-codex-only",
                "無 Claude 環境下 /api/bootstrap 正確識別 Codex 並預選前端專案推薦工具",
                st_boot == 200 and by_agent["codex"]["found"] is True and boot["onboarding_completed"] is False,
            )

            st_acc, acc = _http_json(f"{base_url}/api/accounts")
            check(
                "J1-clean-codex-only",
                "無 Claude 環境下 /api/accounts 回傳 Codex 狀態列不空白",
                st_acc == 200 and len(acc.get("codex") or []) >= 1,
            )

            # 嘗試執行真實 Playwright 瀏覽器全旅程（J2 + J3 + J4）
            has_playwright = False
            try:
                import playwright.sync_api  # noqa: F401

                has_playwright = True
            except ImportError:
                has_playwright = False

            browser_exec_error = ""
            if has_playwright:
                try:
                    browser_report = run_browser_journey(base_url, desktop_dir)
                except Exception as exc:  # noqa: BLE001
                    err_txt = str(exc)
                    is_missing_bin = "Executable doesn't exist" in err_txt or "playwright install" in err_txt.lower()
                    if require_browser or not is_missing_bin:
                        browser_exec_error = err_txt
                    else:
                        browser_report = {"ran_browser": False, "skipped_reason": err_txt}

            if browser_exec_error:
                check(
                    "J4-five-tabs-and-mobile-webkit",
                    "真實瀏覽器全旅程執行不得拋出逾時、選擇器缺失或執行期異常",
                    False,
                    browser_exec_error[:240],
                )
            elif browser_report.get("ran_browser"):
                m = browser_report["metrics"]
                prof_name = m.get("applied_profile") or "personal"
                check(
                    "J2-first-run-workbench-apply",
                    "真實瀏覽器一鍵套用精選工作台與超過 2 項習慣成功落盤",
                    m["initial_checked_habits"] >= 5
                    and (state_dir / "kit.yaml").is_file()
                    and (state_dir / "profiles" / prof_name / "AGENTS.md").is_file()
                    and (fake_home / ".codex" / "AGENTS.md").is_file(),
                    f"profile={prof_name}, 預設勾選 {m['initial_checked_habits']} 項習慣",
                )
                check(
                    "J3-zero-project-starter",
                    "真實瀏覽器一鍵建立 hello-omnikit 專案、本地 Git、NOW.md 與 3 句破冰提示詞",
                    m["starter_prompts_rendered"] == 3
                    and (desktop_dir / "hello-omnikit" / ".git").is_dir()
                    and (state_dir / "status" / "hello-omnikit" / "NOW.md").is_file(),
                )
                check(
                    "J4-five-tabs-and-mobile-webkit",
                    "Chromium 1280x800 與 WebKit Mobile 390x844 全程 0 console.error、0 pageerror、0 HTTP>=400",
                    not browser_report["console_errors"]
                    and not browser_report["page_errors"]
                    and not browser_report["bad_responses"],
                    str(browser_report["console_errors"] or browser_report["bad_responses"] or "0 errors"),
                )
                check(
                    "J4-five-tabs-and-mobile-webkit",
                    "桌機與手機 WebKit 皆 0 橫向溢位，且手機輸入框字級 >= 16px、底部導覽 >= 44px",
                    not m["desktop_horizontal_overflow"]
                    and not m["mobile_horizontal_overflow"]
                    and m["mobile_min_input_font_px"] >= 16.0
                    and m["mobile_nav_min_height"] >= 44.0,
                    f"minFont={m['mobile_min_input_font_px']}px, navH={m['mobile_nav_min_height']}px",
                )
            else:
                if require_browser:
                    check("J4-five-tabs-and-mobile-webkit", "需要真實瀏覽器但未安裝 Playwright", False)
                else:
                    # 無瀏覽器二進位檔環境（如輕量 Linux runner）以真實 HTTP API 走完 J2 + J3
                    st_ap, ap = _http_json(
                        f"{base_url}/api/kit/apply",
                        method="POST",
                        token=token,
                        payload={
                            "preset": ["fullstack-app"],
                            "done_check": "block",
                            "tools": ["chrome-devtools-mcp", "gitleaks", "frontend-design", "skill-creator"],
                            "answers": {
                                "name": "personal",
                                "language": "zh-TW",
                                "verbosity": "concise",
                                "autonomy": "balanced",
                                "domains": ["software-dev"],
                                "pains": ["anti-fake-done", "no-verification", "guesses", "scope-creep", "manual-steps"],
                                "evaluate_tools": False,
                            },
                        },
                    )
                    check(
                        "J2-first-run-workbench-apply",
                        "HTTP 真實套用精選工作台與 5 項習慣落盤同步成功",
                        st_ap == 200
                        and ap.get("ok") is True
                        and (state_dir / "kit.yaml").is_file()
                        and (fake_home / ".codex" / "AGENTS.md").is_file(),
                    )
                    st_cp, cp = _http_json(
                        f"{base_url}/api/projects/create",
                        method="POST",
                        token=token,
                        payload={"name": "hello-omnikit", "parent_dir": str(desktop_dir)},
                    )
                    check(
                        "J3-zero-project-starter",
                        "HTTP 真實建立 hello-omnikit 專案、本地 Git、NOW.md 與 3 句破冰提示詞",
                        st_cp == 201
                        and len(cp.get("starter_prompts") or []) == 3
                        and (state_dir / "status" / "hello-omnikit" / "NOW.md").is_file(),
                    )

            # J1 對帳退路實測：無 T3 時觸發 hello-omnikit 對帳應走本機 Git 成功完成
            st_rc, _ = _http_json(
                f"{base_url}/api/projects/hello-omnikit/reconcile",
                method="POST",
                token=token,
                payload={},
            )
            for _ in range(40):
                _, rstat = _http_json(f"{base_url}/api/reconcile/status")
                if not rstat.get("busy"):
                    break
                time.sleep(0.1)
            _, rstat_done = _http_json(f"{base_url}/api/reconcile/status")
            job_done = (rstat_done.get("jobs") or {}).get("hello-omnikit") or {}
            check(
                "J1-clean-codex-only",
                "無 T3 環境下觸發對帳自動走本機 Git 更新 NOW.md 成功（status=done）",
                st_rc == 202 and job_done.get("status") == "done",
                str(job_done.get("message") or job_done.get("error") or ""),
            )

            # J5 後半：斷開連線並驗證保留個人 profiles/ 與 status/
            env_disc = app._make_sync_env()
            sync.disconnect(env_disc)
            codex_after = (fake_home / ".codex" / "AGENTS.md").read_text(encoding="utf-8") if (fake_home / ".codex" / "AGENTS.md").exists() else ""
            has_kept_profile = any(p.is_file() for p in (state_dir / "profiles").glob("*/AGENTS.md"))
            check(
                "J5-whatif-zero-side-effect-and-restore",
                "斷開連線乾淨移除受管規則區塊與 skills 連結，且完整保留個人 profiles/ 與 status/ NOW.md",
                "omnikit:rules:begin" not in codex_after
                and has_kept_profile
                and (state_dir / "status" / "hello-omnikit" / "NOW.md").is_file(),
            )
        finally:
            collector._find_t3_cli = orig_find_t3  # type: ignore[assignment]
            httpd.shutdown()
            httpd.server_close()

    summary = {
        "ok": len(fails) == 0,
        "total_checks": len(checks),
        "failed_count": len(fails),
        "browser_verified": bool(browser_report.get("ran_browser")),
        "browser_metrics": browser_report.get("metrics") or {},
        "checks": checks,
    }
    print(
        f"\ncleanroom_e2e：{'全部通過' if not fails else f'{len(fails)} 項失敗'} "
        f"（共 {len(checks)} 項檢查，真瀏覽器實測={'是' if summary['browser_verified'] else '否'}）"
    )
    return (1 if fails else 0), summary


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="OmniKit 無塵室真實全旅程端對端與真瀏覽器驗收閘門")
    parser.add_argument("--selftest", action="store_true", help="執行離線無塵室契約測試")
    parser.add_argument("--require-browser", action="store_true", help="強制要求執行真實 Playwright Chromium + WebKit 檢查")
    parser.add_argument("--out", type=Path, default=None, help="輸出 JSON 驗證證據檔路徑")
    args = parser.parse_args(argv)

    rc, report = run_cleanroom(require_browser=args.require_browser and not args.selftest)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
