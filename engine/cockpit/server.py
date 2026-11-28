"""OmniKit 本機控制面板（Control Panel / Cockpit）私有 HTTP + PWA 伺服器。

安全邊界：
- 預設只綁定 127.0.0.1:3780，在 Windows 強制啟用 SO_EXCLUSIVEADDRUSE 防雙進程搶同埠（P0-1），埠被佔用時支援自動順移 3780..3789。
- 所有 API 回傳 no-store 與安全標頭；日誌自動剝離 URL query 防止任何參數外洩至 server.err.log（P1-1）。
- Host 白名單：只接受 127.0.0.1、localhost、::1，以及這台的 Tailscale MagicDNS 名稱。其他 Host 一律 403，擋 DNS rebinding。
- 經 Tailscale 進來的（Host 不是本機名稱，或帶 Tailscale-User-Login、X-Forwarded-For 這類反代標頭）只能讀：
  POST、PATCH 一律 403；寫入、套用工作台與對帳只在這台電腦上開本機網址時可做。
- 本機寫入要帶 X-OmniKit-Token（前端從同源 GET /api/session 取得；跨站 Fetch 由 Sec-Fetch-Site 擋下），
  且若有 Origin 標頭，其 host 與 port 都必須與目前伺服器完全一致。
"""
from __future__ import annotations

import contextlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import collector, reconciler

SCRIPTS_DIR = collector.ROOT / "engine" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAP_FILE = collector.ROOT / "engine" / "site" / "map.html"
MAX_BODY_BYTES = 128 * 1024  # 128 KB 支援匯入設定包，防畸形大封包
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
FORWARD_HEADERS = (
    "Tailscale-User-Login",
    "Tailscale-User-Name",
    "Tailscale-Headers-Info",
    "X-Forwarded-For",
    "X-Forwarded-Host",
    "X-Forwarded-Proto",
    "Forwarded",
)
TOKEN_HEADER = "X-OmniKit-Token"
HOSTS_ENV = "OMNIKIT_COCKPIT_HOSTS"
SERVER_VERSION = "0.2.1"
QUERY_IN_REQ_RE = re.compile(r'(\"[A-Z]+\s+[^\s?\"]+)\?[^\s\"]*(\s+HTTP/[^\"]+\")')

HABIT_CATALOG = [
    {"id": "anti-fake-done", "label": "防假完工（真跑實測＋瀏覽器 0 錯誤才准報完工）", "recommended": True},
    {"id": "no-verification", "label": "改完必須附上真實測試或執行輸出", "recommended": True},
    {"id": "guesses", "label": "不確定時先查證（程式碼／文件／上網），禁止瞎猜", "recommended": True},
    {"id": "too-long", "label": "回覆精簡扼要，能一句講完不寫長篇", "recommended": False},
    {"id": "scope-creep", "label": "嚴守需求邊界，不順手亂改無關程式碼", "recommended": True},
    {"id": "breaks-existing", "label": "修改前先確認呼叫端與既有測試不被改壞", "recommended": False},
    {"id": "manual-steps", "label": "能自動完成的步驟自己做完，別丟回給我手動跑", "recommended": True},
    {"id": "english-drift", "label": "全程維持指定語言，不夾雜英文段落或簡體詞", "recommended": False},
    {"id": "no-plan", "label": "跨多檔或需求模糊時，先列簡短步驟對焦再動手", "recommended": False},
]


def host_name(value: str | None) -> str:
    """Host 標頭去掉連接埠與結尾的點、轉小寫；IPv6 的中括號拿掉。"""
    v = str(value or "").strip().lower()
    if v.startswith("["):
        v = v[1:].split("]", 1)[0]
    elif v.count(":") == 1:
        v = v.split(":", 1)[0]
    return v.rstrip(".")


def _origin_matches_server(origin: str, server_port: int) -> bool:
    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https"):
        return False
    if host_name(parsed.netloc) not in LOCAL_HOSTS:
        return False
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return port == server_port


def strip_log_query(text: str) -> str:
    """剝除 HTTP 請求紀錄列中的 ?query 參數，防止敏感參數落入日誌檔。"""
    return QUERY_IN_REQ_RE.sub(r"\1\2", text)


def _tailscale_exe() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    default = Path(os.environ.get("ProgramFiles") or "C:/Program Files") / "Tailscale" / "tailscale.exe"
    return str(default) if default.is_file() else None


def tailnet_hosts(
    environ: dict[str, str] | None = None,
    run: Callable[..., Any] = subprocess.run,
    exe: str | None = None,
) -> set[str]:
    """這台的 Tailscale MagicDNS 名稱：環境變數 OMNIKIT_COCKPIT_HOSTS（逗號分隔）加上 tailscale status --json 的
    Self.DNSName。沒裝 Tailscale、查不到或逾時都只回環境變數的（只剩本機名稱能進來）。"""
    environ = os.environ if environ is None else environ
    hosts = {host_name(h) for h in str(environ.get(HOSTS_ENV) or "").split(",") if h.strip()}
    exe = exe or _tailscale_exe()
    if exe:
        try:
            r = run(
                [exe, "status", "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            name = (json.loads(r.stdout or "{}").get("Self") or {}).get("DNSName") if r.returncode == 0 else None
            if isinstance(name, str) and name.strip():
                hosts.add(host_name(name))
        except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
            pass
    return {h for h in hosts if h}


def _collect_tripwire_summary(state_dir: Path) -> dict[str, Any]:
    hits_file = state_dir / "harness" / "tripwire-hits.jsonl"
    if not hits_file.is_file():
        return {"recent_30d": 0, "blocked_30d": 0, "logged_30d": 0, "total": 0, "by_rule": {}, "recent_events": []}
    cutoff = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_rule: dict[str, int] = {}
    recent_30d = 0
    blocked_30d = 0
    logged_30d = 0
    total = 0
    events: list[dict[str, str]] = []
    try:
        lines = hits_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"recent_30d": 0, "blocked_30d": 0, "logged_30d": 0, "total": 0, "by_rule": {}, "recent_events": []}
    for ln in lines:
        if not ln.strip():
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        hook = str(d.get("hook") or "guard")
        rule = str(d.get("rule") or "unknown")
        ts = str(d.get("ts") or "")
        mode = str(d.get("mode") or d.get("action") or "block").lower()
        key = f"{hook}:{rule}"
        by_rule[key] = by_rule.get(key, 0) + 1
        total += 1
        if ts >= cutoff:
            recent_30d += 1
            if mode == "log":
                logged_30d += 1
            else:
                blocked_30d += 1
        events.append({
            "ts": ts,
            "hook": hook,
            "rule": rule,
            "agent": str(d.get("agent") or ""),
            "action": mode,
        })
    return {
        "recent_30d": recent_30d,
        "blocked_30d": blocked_30d,
        "logged_30d": logged_30d,
        "total": total,
        "by_rule": dict(sorted(by_rule.items(), key=lambda kv: (-kv[1], kv[0]))[:8]),
        "recent_events": list(reversed(events[-5:])),
    }


def _autostart_installed(state_dir: Path) -> bool:
    if os.name == "nt":
        appdata = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        lnk = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "OmniKit Cockpit 自動啟動.lnk"
        return lnk.is_file()
    return (state_dir / "cockpit" / "autostart-cockpit.ps1").is_file()


MIME_MAP = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class ExclusiveHTTPServer(ThreadingHTTPServer):
    """禁用 SO_REUSEADDR 並在 Windows 啟用 SO_EXCLUSIVEADDRUSE，根絕雙進程同綁 3780 的幽靈 403 問題（P0-1）。"""

    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class CockpitApp:
    """可注入 state_dir、home_dir、t3_runner、reconcile_runner 與 cache 的控制面板應用狀態。"""

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        data_dir: Path | None = None,
        home_dir: Path | None = None,
        default_repo_root: Path | None = collector.ROOT,
        t3_runner: Callable[[Path], list[dict[str, Any]] | None] | None = None,
        reconcile_runner: Callable[..., dict[str, Any]] | None = None,
        cli_runner: Callable[..., tuple[int, str, str]] | None = None,
        cache_ttl: float = 15.0,
        allowed_hosts: set[str] | None = None,
        token: str | None = None,
    ):
        self.state_dir = state_dir if state_dir is not None else collector.default_state_dir()
        self.data_dir = data_dir if data_dir is not None else (collector.ROOT / "data")
        self.home_dir = home_dir if home_dir is not None else Path.home()
        self.repo_root = self.data_dir.parent if (self.data_dir.parent / "engine").is_dir() else collector.ROOT
        self.default_repo_root = default_repo_root
        self.t3_runner = t3_runner
        self.cli_runner = cli_runner
        self.cache_ttl = cache_ttl
        found = tailnet_hosts() if allowed_hosts is None else allowed_hosts
        self.remote_hosts = {host_name(h) for h in found} - LOCAL_HOSTS
        self.token = token or secrets.token_urlsafe(32)
        self.instance = secrets.token_hex(8)
        self.version = SERVER_VERSION
        self._lock = threading.Lock()
        self._mutate_lock = threading.Lock()
        self._cache: dict[str, tuple[float, Any]] = {}
        self.reconciler = reconciler.ReconcileManager(
            state_dir=self.state_dir,
            on_done=lambda: self.invalidate("overview", "bootstrap"),
            runner=reconcile_runner,
        )

    def invalidate(self, *keys: str) -> None:
        with self._lock:
            if not keys:
                self._cache.clear()
            else:
                for k in keys:
                    self._cache.pop(k, None)

    def _is_isolated_home(self) -> bool:
        return os.path.normcase(str(self.home_dir.resolve())) != os.path.normcase(str(Path.home().resolve()))

    def _scoped_which(self, name: str) -> str | None:
        if self._is_isolated_home():
            if name == "claude" and not (self.home_dir / ".claude").is_dir():
                return None
            if name == "codex" and not (self.home_dir / ".codex").is_dir():
                return None
            if name in ("agy", "antigravity") and not (
                (self.home_dir / ".gemini" / "config").is_dir() or (self.home_dir / ".gemini" / "antigravity").is_dir()
            ):
                return None
        return shutil.which(name)

    def _make_sync_env(self):
        import sync as sync_mod  # type: ignore

        if (
            self.cli_runner is None
            and self.home_dir == Path.home()
            and self.state_dir == collector.default_state_dir()
            and self.repo_root == collector.ROOT
        ):
            return sync_mod.real_env()
        iso_env = {
            **os.environ,
            "USERPROFILE": str(self.home_dir),
            "HOME": str(self.home_dir),
            "OMNIKIT_STATE_DIR": str(self.state_dir),
        }
        return sync_mod.Env(
            home=self.home_dir,
            repo=self.repo_root,
            state=self.state_dir,
            which=self._scoped_which,
            runner=self.cli_runner,
            environ=iso_env,
        )

    def get_overview(self, *, force_sync: bool = False) -> dict[str, Any]:
        now_m = time.monotonic()
        data = None
        if not force_sync:
            with self._lock:
                cached = self._cache.get("overview")
                if cached and (now_m - cached[0]) < self.cache_ttl:
                    data = cached[1]
        if data is None:
            data = collector.collect_overview(
                self.state_dir,
                sync=force_sync,
                default_repo_root=self.default_repo_root,
                t3_runner=self.t3_runner,
            )
            try:
                collector.write_snapshot(self.state_dir, data)
            except OSError:
                pass
            with self._lock:
                self._cache["overview"] = (time.monotonic(), data)
        return {**data, "reconcile": self.reconciler.snapshot()}

    def get_tools(self, *, force: bool = False) -> dict[str, Any]:
        now_m = time.monotonic()
        if not force:
            with self._lock:
                cached = self._cache.get("tools")
                if cached and (now_m - cached[0]) < max(30.0, self.cache_ttl):
                    return cached[1]
        data = collector.collect_tools_overlay(self.state_dir, data_dir=self.data_dir)
        with self._lock:
            self._cache["tools"] = (time.monotonic(), data)
        return data

    def get_accounts(self, *, refresh_agy: bool = False) -> dict[str, Any]:
        now_m = time.monotonic()
        if not refresh_agy:
            with self._lock:
                cached = self._cache.get("accounts")
                if cached and (now_m - cached[0]) < max(20.0, self.cache_ttl):
                    return cached[1]
        data = collector.collect_accounts(self.state_dir, refresh_agy=refresh_agy, home=self.home_dir)
        with self._lock:
            self._cache["accounts"] = (time.monotonic(), data)
        return data

    def get_bootstrap(self, *, force: bool = False) -> dict[str, Any]:
        now_m = time.monotonic()
        if not force:
            with self._lock:
                cached = self._cache.get("bootstrap")
                if cached and (now_m - cached[0]) < max(10.0, self.cache_ttl):
                    return cached[1]

        import kit as kit_mod  # type: ignore
        import profiles as profiles_mod  # type: ignore
        import scan as scan_mod  # type: ignore
        import status as status_mod  # type: ignore

        candidates = collector.scan_candidate_projects(self.home_dir, self.state_dir)
        cfg = collector.load_config(self.state_dir)
        sample_project_dir: Path | None = None
        if cfg.get("projects"):
            first_p = cfg["projects"][0]
            if isinstance(first_p, dict) and first_p.get("path"):
                sample_project_dir = Path(str(first_p["path"]))
        elif candidates:
            sample_project_dir = Path(candidates[0]["path"])

        sample_files = scan_mod.project_names(sample_project_dir) if sample_project_dir and sample_project_dir.is_dir() else []
        if not hasattr(self, "_git_user_cache"):
            if self._is_isolated_home():
                self._git_user_cache = None
            else:
                _, g_out, _ = collector._run_cmd(["git", "config", "--global", "user.name"], timeout=3)
                self._git_user_cache = g_out.strip() or None
        # 控制面板首頁只需快速檢查 PATH 是否存在，不逐一啟動 pwsh/node/gh --version 子行程，根除冷啟動 Windows 15s 逾時
        scan_res = scan_mod.scan(
            self.home_dir,
            self.data_dir,
            self.state_dir,
            which=self._scoped_which,
            run=lambda _path, *_a: ("", None),
            git_name=self._git_user_cache,
            project=sample_project_dir,
        )
        catalog = kit_mod.build_workbench_catalog(self.state_dir, self.data_dir, project_files=sample_files)
        drifts = kit_mod.detect_drift(self.state_dir, self.home_dir)
        active_prof = catalog["active_profile"]
        prof_dir = profiles_mod.folder(self.data_dir, self.state_dir, active_prof)
        prev_answers = profiles_mod.answers(self.data_dir, self.state_dir, active_prof)
        is_handwritten = bool(
            active_prof != "default"
            and prof_dir is not None
            and (not (prof_dir / "answers.json").is_file() or (self.data_dir / "profiles" / active_prof / "AGENTS.md").is_file())
        )
        status_mode = status_mod.detect_mode(status_mod.status_dir(self.state_dir))
        tripwire = _collect_tripwire_summary(self.state_dir)

        supported_agents = [a for a in (scan_res.get("agents") or []) if a.get("omnikit_supported")]
        installed_agent_ids = [str(a["id"]) for a in supported_agents if a.get("found")]
        codex_only = installed_agent_ids == ["codex"]
        ok_prefix = "$ok" if codex_only else "/ok"
        ok_agent_label = "Codex" if codex_only else "三端通用（Codex 輸入 $ok）"
        shortcuts = [
            {
                "agent": ok_agent_label,
                "cmd": f"{ok_prefix} 面板",
                "desc": f"隨時一鍵開啟本機控制面板網頁（也可直接輸入 {ok_prefix} 查看快捷選單）",
            },
            {
                "agent": ok_agent_label,
                "cmd": f"{ok_prefix} 驗收",
                "desc": "防假完工實體驗收：自動檢查斷線參考、假綠燈跳過測試，並真開服務與瀏覽器確認 0 錯誤",
            },
            {
                "agent": "Claude / Codex / AGY",
                "cmd": "/plan（AGY 亦可用 /grill-me）",
                "desc": "動手寫程式前先互動釐清需求邊界與實作計畫，避免做白工",
            },
        ]
        if not codex_only:
            shortcuts.insert(
                2,
                {
                    "agent": "Claude Code",
                    "cmd": "/claude-automation-recommender",
                    "desc": "依目前程式碼倉庫結構，自動推薦適合的 hooks、subagents 與自動化流程（claude-code-setup）",
                },
            )
        data = {
            "version": self.version,
            "active_profile": active_prof,
            "is_handwritten_profile": is_handwritten,
            "onboarding_completed": catalog["onboarding_completed"],
            "rev": catalog["rev"],
            "done_check": catalog["done_check"],
            "ok_prefix": ok_prefix,
            "installed_agents": installed_agent_ids,
            "suggested_profile": scan_res.get("suggested_profile") or "personal",
            "previous_answers": prev_answers or {
                "language": "zh-TW",
                "verbosity": "concise",
                "autonomy": "balanced",
                "domains": [d["id"] for d in (scan_res.get("omnikit", {}).get("domains") or []) if d.get("suggested")] or ["software-dev"],
                "pains": [h["id"] for h in HABIT_CATALOG if h["recommended"]],
                "evaluate_tools": False,
            },
            "habits_catalog": HABIT_CATALOG,
            "domains": scan_res.get("omnikit", {}).get("domains") or [],
            "agents": supported_agents,
            "cli_tools": scan_res.get("tools") or {},
            "workbench": catalog,
            "drifts": drifts,
            "candidate_projects": candidates,
            "registered_projects_count": len(cfg.get("projects") or []),
            "status_repo": status_mode,
            "tripwire": tripwire,
            "autostart_enabled": _autostart_installed(self.state_dir),
            "cli_shortcuts": shortcuts,
        }
        with self._lock:
            self._cache["bootstrap"] = (time.monotonic(), data)
        return data

    def preview_kit(self, body: dict[str, Any]) -> dict[str, Any]:
        import kit as kit_mod  # type: ignore

        cur_cat = kit_mod.build_workbench_catalog(self.state_dir, self.data_dir)
        tools_in = body.get("tools")
        if isinstance(tools_in, dict):
            enabled_ids = [tid for tid, tier in tools_in.items() if tier in ("resident", "on_demand")]
        elif isinstance(tools_in, list):
            enabled_ids = [str(tid) for tid in tools_in]
        else:
            enabled_ids = [it["id"] for it in cur_cat["items"] if it["enabled"]]
        budget = kit_mod.compute_context_budget(enabled_ids)
        cur_enabled = {it["id"] for it in cur_cat["items"] if it["enabled"]}
        new_enabled = set(enabled_ids)
        return {
            "ok": True,
            "budget": budget,
            "added_tools": sorted(new_enabled - cur_enabled),
            "removed_tools": sorted(cur_enabled - new_enabled),
            "enabled_count": len(new_enabled),
        }

    def apply_kit(self, body: dict[str, Any]) -> dict[str, Any]:
        import kit as kit_mod  # type: ignore
        import profile_new as pnew_mod  # type: ignore
        import profiles as profiles_mod  # type: ignore
        import status as status_mod  # type: ignore
        import sync as sync_mod  # type: ignore

        kdoc = kit_mod.load(self.state_dir)
        cur_profile = str(kdoc.get("active_profile") or "default")
        expected_rev = body.get("expected_rev")
        if expected_rev is not None:
            expected_rev = int(expected_rev)
            cur_rev = int(kdoc.get("rev") or 0)
            if expected_rev != cur_rev:
                raise kit_mod.RevConflictError(
                    f"設定已被其他視窗或指令更新（目前 rev={cur_rev}，送出 rev={expected_rev}），請重新整理後再套用"
                )

        answers_in = body.get("answers")
        target_profile = str(body.get("profile_name") or cur_profile).strip() or cur_profile
        profile_notes: list[str] = []

        if isinstance(answers_in, dict) and answers_in:
            req_name = str(answers_in.get("name") or target_profile).strip().lower()
            if not req_name or req_name == "default":
                req_name = "personal"
            prof_dir = profiles_mod.folder(self.data_dir, self.state_dir, req_name)
            in_repo_handwritten = (self.data_dir / "profiles" / req_name / "AGENTS.md").is_file()
            local_handwritten = bool(prof_dir and prof_dir.exists() and not (prof_dir / "answers.json").is_file())
            if in_repo_handwritten or local_handwritten:
                target_profile = req_name
                profile_notes.append(f"目前使用手寫規則檔「{req_name}」，保留原 AGENTS.md 不覆蓋；工作台與護欄設定已更新。")
            else:
                existing_ans = profiles_mod.answers(self.data_dir, self.state_dir, req_name) or {}
                eval_flag = (
                    bool(answers_in["evaluate_tools"])
                    if "evaluate_tools" in answers_in and answers_in["evaluate_tools"] is not None
                    else bool(existing_ans.get("evaluate_tools", False))
                )
                payload = {
                    "name": req_name,
                    "language": str(answers_in.get("language") or existing_ans.get("language") or "zh-TW"),
                    "verbosity": str(answers_in.get("verbosity") or existing_ans.get("verbosity") or "concise"),
                    "autonomy": str(answers_in.get("autonomy") or existing_ans.get("autonomy") or "balanced"),
                    "domains": list(answers_in.get("domains") or existing_ans.get("domains") or ["software-dev"]),
                    "pains": list(answers_in.get("pains") if "pains" in answers_in else (existing_ans.get("pains") or ["anti-fake-done", "no-verification"])),
                    "evaluate_tools": eval_flag,
                }
                if payload["verbosity"] == "detailed" and "too-long" in payload["pains"]:
                    payload["pains"] = [p for p in payload["pains"] if p != "too-long"]
                bg_val = answers_in.get("background") if "background" in answers_in else existing_ans.get("background")
                if bg_val:
                    payload["background"] = str(bg_val).strip()
                if payload["evaluate_tools"]:
                    projs = answers_in.get("projects") if "projects" in answers_in else existing_ans.get("projects")
                    if isinstance(projs, dict) and projs.get("main"):
                        payload["projects"] = projs
                    else:
                        payload["projects"] = {"main": "我的主要專案", "frontend": "前端介面"}

                with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as tf:
                    json.dump(payload, tf, ensure_ascii=False)
                    tmp_ans = Path(tf.name)
                buf = io.StringIO()
                try:
                    with self._mutate_lock, contextlib.redirect_stdout(buf):
                        rc = pnew_mod.run(tmp_ans, self.data_dir, state=self.state_dir, write=True, apply=False, force=True)
                finally:
                    tmp_ans.unlink(missing_ok=True)
                if rc != 0:
                    raise ValueError(buf.getvalue().strip() or "個人規則產生失敗")
                target_profile = req_name
                profile_notes.append(f"已更新個人設定檔「{target_profile}」")

        prev_cat = kit_mod.build_workbench_catalog(self.state_dir, self.data_dir)
        prev_tiers = {it["id"]: it["tier"] for it in prev_cat["items"]}
        first_onboarding = not bool(kdoc.get("onboarding_completed"))

        tools_patch: dict[str, dict[str, str]] = {}
        changed_toggles: dict[str, str] = {}
        tools_in = body.get("tools")
        if isinstance(tools_in, dict):
            for tid, tier in tools_in.items():
                st = str(tier)
                if st in ("resident", "on_demand", "disabled"):
                    tools_patch[str(tid)] = {"tier": st}
                    if prev_tiers.get(str(tid)) != st or (first_onboarding and st != "disabled"):
                        changed_toggles[str(tid)] = st
        elif isinstance(tools_in, list):
            wanted_set = {str(x) for x in tools_in}
            for item in prev_cat["items"]:
                tid = item["id"]
                st = "resident" if tid in wanted_set else "disabled"
                tools_patch[tid] = {"tier": st}
                if prev_tiers.get(tid) != st or (first_onboarding and st != "disabled"):
                    changed_toggles[tid] = st

        warnings: list[str] = []
        for tid in list(tools_patch.keys()):
            st = tools_patch[tid]["tier"]
            req_env = kit_mod.NEEDS_API_KEY.get(tid)
            if st != "disabled" and req_env and not os.environ.get(req_env, "").strip():
                tools_patch[tid] = {"tier": "disabled"}
                if prev_tiers.get(tid) in ("disabled", None):
                    changed_toggles.pop(tid, None)
                else:
                    changed_toggles[tid] = "disabled"
                warnings.append(f"尚未設定環境變數 {req_env}，{tid} 維持停用狀態")

        prof_patch: dict[str, Any] = {}
        if tools_patch:
            prof_patch["tools"] = tools_patch
        if body.get("done_check") in ("block", "log", "off"):
            prof_patch["done_check"] = str(body["done_check"])
        if isinstance(body.get("preset"), list):
            prof_patch["preset"] = [str(x) for x in body["preset"]]

        updated_doc = kit_mod.patch(
            self.state_dir,
            active_profile=target_profile,
            onboarding_completed=True,
            profile_patch=prof_patch or None,
            expected_rev=expected_rev,
        )

        actions: list[str] = list(profile_notes)
        for tid, st in changed_toggles.items():
            try:
                res_t = kit_mod.apply_tool_toggle(
                    tid,
                    st,
                    state=self.state_dir,
                    home=self.home_dir,
                    repo_root=self.repo_root,
                    runner=self.cli_runner,
                )
                actions.extend(res_t.get("actions") or [])
                warnings.extend(res_t.get("warnings") or [])
                if res_t.get("deferred") and res_t.get("message"):
                    warnings.append(str(res_t["message"]))
            except FileNotFoundError:
                continue

        # 同步三家 Agent 規則、skills、hooks、MCP（保護已標記 adopted / snoozed 的外部手改規則）
        env = self._make_sync_env()
        detected_agents = sync_mod.detect_agents(env)
        is_iso = os.path.normcase(str(self.home_dir.resolve())) != os.path.normcase(str(Path.home().resolve()))
        if detected_agents or (self.state_dir / "config.json").is_file():
            try:
                buf_s = io.StringIO()
                with self._mutate_lock, contextlib.redirect_stdout(buf_s), contextlib.redirect_stderr(buf_s):
                    sync_mod.run_sync(
                        env,
                        profile=target_profile,
                        dev=True if (is_iso and self.cli_runner is not None) else None,
                        take_over=True,
                        respect_drift=True,
                    )
                actions.append("已同步本機 Agent 規則、核心技能、防假完工護欄與 MCP 設定")
            except SystemExit as exc:
                if exc.code not in (0, None):
                    warnings.append(f"Agent 同步提示：{exc.code}")

        status_mod.init_status(self.state_dir)
        preserved = kit_mod.drifted_rule_keys(self.state_dir, self.home_dir)
        kit_mod.record_applied_snapshot(self.state_dir, self.home_dir, preserve_keys=preserved)
        self.invalidate()
        return {
            "ok": True,
            "active_profile": target_profile,
            "rev": kit_mod.load(self.state_dir).get("rev", updated_doc.get("rev", 1)),
            "actions": actions,
            "warnings": warnings,
            "bootstrap": self.get_bootstrap(force=True),
        }

    def get_doctor(self) -> dict[str, Any]:
        import doctor as doctor_mod  # type: ignore

        env = self._make_sync_env()
        rows = doctor_mod.collect(env, lists=False, pre=False)
        counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("ok", "warn", "fail", "unknown")}
        return {"ok": counts["fail"] == 0, "counts": counts, "rows": rows}

    def fix_doctor(self, *, force_overwrite: bool = False) -> dict[str, Any]:
        import kit as kit_mod  # type: ignore
        import status as status_mod  # type: ignore
        import sync as sync_mod  # type: ignore

        env = self._make_sync_env()
        kdoc = kit_mod.load(self.state_dir)
        prof = str(kdoc.get("active_profile") or "default")
        preserved = set() if force_overwrite else kit_mod.drifted_rule_keys(self.state_dir, self.home_dir)
        buf = io.StringIO()
        with self._mutate_lock, contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            sync_mod.run_sync(env, profile=prof, take_over=True, respect_drift=not force_overwrite)
        status_mod.init_status(self.state_dir)
        kit_mod.record_applied_snapshot(
            self.state_dir,
            self.home_dir,
            preserve_keys=preserved,
            reset_adopted=force_overwrite,
        )
        self.invalidate()
        doc_after = self.get_doctor()
        return {
            "ok": doc_after["ok"],
            "preserved_drift_count": len(preserved),
            "log": buf.getvalue().strip(),
            "doctor": doc_after,
        }

    def enqueue_reconcile(self, project_id: str) -> dict[str, Any]:
        ov = self.get_overview(force_sync=False)
        target = next((p for p in ov["projects"] if p["id"].lower() == project_id.lower()), None)
        if target is None:
            raise FileNotFoundError(f"找不到專案：{project_id}")
        job = self.reconciler.enqueue(target, t3_base_url=ov["settings"].get("t3_base_url") or "")
        return {"ok": True, "job": job, "reconcile": self.reconciler.snapshot()}

    def enqueue_reconcile_all(self, *, only_stale: bool = True, confirm_all: bool = False) -> dict[str, Any]:
        if not only_stale and not confirm_all:
            raise ValueError("全部重新對帳會替每個本機專案各開一條對話：要帶 confirm_all=true 才會排入")
        ov = self.get_overview(force_sync=False)
        t3_base = ov["settings"].get("t3_base_url") or ""
        queued: list[dict[str, Any]] = []
        skipped: list[str] = []
        for p in ov["projects"]:
            if only_stale and not p.get("stale"):
                continue
            if p.get("remote_only") or not p.get("local_available"):
                skipped.append(p["id"])
                continue
            queued.append(self.reconciler.enqueue(p, t3_base_url=t3_base))
        return {"ok": True, "queued": queued, "skipped": skipped, "reconcile": self.reconciler.snapshot()}


def _make_handler(app: CockpitApp):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def handle(self) -> None:
            try:
                super().handle()
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass

        def log_message(self, format: str, *args: Any) -> None:
            msg = strip_log_query(format % args)
            sys.stderr.write(f"[cockpit] {self.address_string()} - {msg}\n")

        def _drain_body(self) -> None:
            """拒絕 POST/PATCH 請求前排空小尺寸請求內文並標記關閉連線，防止 Windows HTTP/1.1 發出 TCP RST (WinError 10053)。"""
            self.close_connection = True
            try:
                length = int(self.headers.get("Content-Length") or "0")
                if 0 < length <= MAX_BODY_BYTES:
                    self.rfile.read(length)
            except (OSError, ValueError):
                pass

        def _send_bytes(self, status: int, body: bytes, content_type: str, *, cache_control: str = "no-store") -> None:
            if status >= 400:
                self.close_connection = True
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            if getattr(self, "close_connection", False):
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: Any) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, raw, "application/json; charset=utf-8")

        def _access(self) -> tuple[str | None, bool]:
            """回傳（拒絕原因或 None, 是不是遠端／非本機迴路連線）。"""
            host = host_name(self.headers.get("Host"))
            if host not in LOCAL_HOSTS and host not in app.remote_hosts:
                return "Host 不在白名單（只接受本機與這台的 Tailscale 名稱）", True
            client_ip = str((self.client_address[0] if self.client_address else "") or "").strip().lower()
            is_loopback = client_ip in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
            remote = (not is_loopback) or (host not in LOCAL_HOSTS) or any(self.headers.get(h) for h in FORWARD_HEADERS)
            return None, remote

        def _guard_read(self) -> bool:
            why, _ = self._access()
            if not why and urlparse(self.path).path.startswith("/api/"):
                sfs = str(self.headers.get("Sec-Fetch-Site") or "").strip().lower()
                if sfs and sfs not in ("same-origin", "none"):
                    why = "跨站請求不得讀取控制面板 API"
            if why:
                self._drain_body()
                self._send_json(HTTPStatus.FORBIDDEN, {"error": why})
                return False
            return True

        def _guard_write(self) -> bool:
            """寫入只限這台電腦本機開的同源頁面：Host 白名單、非反代、Sec-Fetch-Site 同源、Origin 含埠號完全吻合、帶對 token。"""
            why, remote = self._access()
            if not why and remote:
                why = f"經 Tailscale 開啟時只能看：寫入與設定請在這台電腦上開 http://127.0.0.1:{self.server.server_address[1]}"
            sfs = str(self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            if not why and sfs and sfs not in ("same-origin", "none"):
                why = "跨站請求已被阻擋（Sec-Fetch-Site 非 same-origin）"
            origin = self.headers.get("Origin")
            if not why and origin and not _origin_matches_server(origin, self.server.server_address[1]):
                why = "來源（Origin）主機或連接埠與目前控制面板不一致"
            if not why and not hmac.compare_digest(str(self.headers.get(TOKEN_HEADER) or ""), app.token):
                why = f"缺少或錯誤的 {TOKEN_HEADER}：請重新整理頁面再試"
            if why:
                self._drain_body()
                self._send_json(HTTPStatus.FORBIDDEN, {"error": why})
                return False
            return True

        def _read_json_body(self) -> dict[str, Any]:
            ctype = str(self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                raise ValueError("請求標頭必須是 Content-Type: application/json")
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError as exc:
                raise ValueError("無效的 Content-Length") from exc
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("請求內文大小超過上限")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                obj = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError("無效的 JSON 內容") from exc
            if not isinstance(obj, dict):
                raise TypeError("JSON 根節點必須是物件")
            return obj

        def _serve_static(self, rel_path: str) -> None:
            if rel_path == "map.html":
                if MAP_FILE.is_file():
                    self._send_bytes(HTTPStatus.OK, MAP_FILE.read_bytes(), "text/html; charset=utf-8", cache_control="no-cache")
                else:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "尚未產出架構地圖 map.html"})
                return

            clean = rel_path.lstrip("/") or "index.html"
            if clean == "index":
                clean = "index.html"
            base = STATIC_DIR.resolve()
            target = (base / clean).resolve()
            if base not in target.parents and target != base:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "禁止存取路徑"})
                return
            if not target.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "找不到靜態資源"})
                return
            mime = MIME_MAP.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            cache = "no-cache" if target.suffix.lower() in (".html", ".js", ".css", ".webmanifest") else "public, max-age=3600"
            self._send_bytes(HTTPStatus.OK, target.read_bytes(), mime, cache_control=cache)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if not self._guard_read():
                return
            try:
                if path == "/api/session":
                    sfs = str(self.headers.get("Sec-Fetch-Site") or "").strip().lower()
                    if sfs and sfs not in ("same-origin", "none"):
                        self._send_json(HTTPStatus.FORBIDDEN, {"error": "跨站請求不得讀取工作階段憑證"})
                        return
                    origin = self.headers.get("Origin")
                    if origin and not _origin_matches_server(origin, self.server.server_address[1]):
                        self._send_json(HTTPStatus.FORBIDDEN, {"error": "跨來源請求不得讀取工作階段憑證"})
                        return
                    _, remote = self._access()
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "writable": not remote,
                            "mode": "remote" if remote else "local",
                            "token": None if remote else app.token,
                        },
                    )
                    return

                if path == "/api/health":
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "service": "omnikit-cockpit",
                            "version": app.version,
                            "instance": app.instance,
                            "map_available": MAP_FILE.is_file(),
                        },
                    )
                    return

                if path == "/api/bootstrap":
                    force = qs.get("refresh", ["0"])[0] in ("1", "true", "yes")
                    self._send_json(HTTPStatus.OK, app.get_bootstrap(force=force))
                    return

                if path == "/api/overview":
                    sync = qs.get("sync", ["0"])[0] in ("1", "true", "yes")
                    self._send_json(HTTPStatus.OK, app.get_overview(force_sync=sync))
                    return

                if path == "/api/reconcile/status":
                    self._send_json(HTTPStatus.OK, app.reconciler.snapshot())
                    return

                if path == "/api/tools":
                    force = qs.get("refresh", ["0"])[0] in ("1", "true", "yes")
                    self._send_json(HTTPStatus.OK, app.get_tools(force=force))
                    return

                if path == "/api/accounts":
                    refresh = qs.get("refresh", ["0"])[0] in ("1", "true", "yes")
                    self._send_json(HTTPStatus.OK, app.get_accounts(refresh_agy=refresh))
                    return

                if path == "/api/doctor":
                    self._send_json(HTTPStatus.OK, app.get_doctor())
                    return

                if path == "/api/kit/bundle":
                    import kit as kit_mod  # type: ignore

                    self._send_json(HTTPStatus.OK, kit_mod.export_bundle(app.state_dir))
                    return

                if path.startswith("/api/projects/"):
                    parts = [p for p in path.split("/") if p]
                    if len(parts) == 4:
                        pid = unquote(parts[2])
                        if parts[3] == "now":
                            target = collector.safe_status_now_path(app.state_dir, pid)
                            if not target.is_file():
                                self._send_json(HTTPStatus.OK, {"project_id": pid, "exists": False, "content": ""})
                            else:
                                self._send_json(
                                    HTTPStatus.OK,
                                    {"project_id": pid, "exists": True, "path": str(target), "content": collector.read_utf8(target)},
                                )
                            return
                        if parts[3] == "history":
                            import status as status_mod  # type: ignore

                            limit = int(qs.get("limit", ["12"])[0])
                            self._send_json(HTTPStatus.OK, status_mod.project_history(pid, state=app.state_dir, limit=limit))
                            return

                if not path.startswith("/api/"):
                    self._serve_static(path.lstrip("/"))
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "找不到 API 端點"})
            except (ValueError, TypeError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": collector.sanitize(exc)})
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"[cockpit-error] GET {self.path}: {traceback.format_exc()}\n")
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": collector.sanitize(exc)})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._guard_write():
                return
            try:
                import kit as kit_mod  # type: ignore

                body = self._read_json_body()

                if path == "/api/kit/preview":
                    self._send_json(HTTPStatus.OK, app.preview_kit(body))
                    return

                if path == "/api/kit/apply":
                    try:
                        res = app.apply_kit(body)
                        self._send_json(HTTPStatus.OK, res)
                    except kit_mod.RevConflictError as exc:
                        self._send_json(HTTPStatus.CONFLICT, {"error": collector.sanitize(exc), "code": "rev_conflict"})
                    return

                if path == "/api/kit/drift":
                    did = str(body.get("id") or "")
                    action = str(body.get("action") or "")
                    res = kit_mod.resolve_drift(did, action, state=app.state_dir, home=app.home_dir, repo_root=app.repo_root)
                    app.invalidate("bootstrap", "tools")
                    self._send_json(HTTPStatus.OK, res)
                    return

                if path == "/api/kit/import":
                    import profiles as profiles_mod  # type: ignore

                    bundle = body.get("bundle") if isinstance(body.get("bundle"), dict) else body
                    if not isinstance(bundle, dict) or not isinstance(bundle.get("tools"), dict):
                        raise ValueError("設定包格式不正確（必須包含 tools 欄位）")
                    clean_tools: dict[str, str] = {}
                    skipped_tools: list[str] = []
                    for tid, spec in bundle["tools"].items():
                        tid_s = str(tid).strip()
                        if not profiles_mod.NAME.match(tid_s) or not (app.data_dir / "tools" / f"{tid_s}.yaml").is_file():
                            skipped_tools.append(tid_s)
                            continue
                        tier = spec.get("tier") if isinstance(spec, dict) else spec
                        if str(tier) in ("resident", "on_demand", "disabled"):
                            clean_tools[tid_s] = str(tier)
                    res = app.apply_kit({
                        "tools": clean_tools,
                        "done_check": bundle.get("done_check") if bundle.get("done_check") in ("block", "log", "off") else None,
                        "preset": bundle.get("preset") if isinstance(bundle.get("preset"), list) else None,
                    })
                    if skipped_tools:
                        res["warnings"] = [*(res.get("warnings") or []), f"已略過不在名冊內的工具代號：{', '.join(skipped_tools[:8])}"]
                    self._send_json(HTTPStatus.OK, res)
                    return

                if path == "/api/tools/toggle":
                    tid = str(body.get("tool_id") or "").strip()
                    tier = str(body.get("tier") or "").strip()
                    res = kit_mod.apply_tool_toggle(
                        tid,
                        tier,
                        state=app.state_dir,
                        home=app.home_dir,
                        repo_root=app.repo_root,
                        runner=app.cli_runner,
                    )
                    if tid == "chrome-devtools-mcp" and res.get("ok"):
                        env = app._make_sync_env()
                        import sync as sync_mod  # type: ignore

                        if sync_mod.detect_agents(env) or (app.state_dir / "config.json").is_file():
                            with app._mutate_lock, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                                sync_mod.run_sync(env, take_over=True, respect_drift=True)
                    app.invalidate("bootstrap", "tools")
                    cat = kit_mod.build_workbench_catalog(app.state_dir, app.data_dir)
                    self._send_json(HTTPStatus.OK, {**res, "budget": cat["budget"], "workbench": cat})
                    return

                if path == "/api/doctor/fix":
                    self._send_json(HTTPStatus.OK, app.fix_doctor(force_overwrite=bool(body.get("force_overwrite", False))))
                    return

                if path == "/api/reconcile-all":
                    only_stale = bool(body.get("only_stale", True))
                    res = app.enqueue_reconcile_all(only_stale=only_stale, confirm_all=body.get("confirm_all") is True)
                    self._send_json(HTTPStatus.ACCEPTED, res)
                    return

                if path == "/api/projects/register":
                    res = collector.register_project(
                        app.state_dir,
                        name=str(body.get("name") or ""),
                        path=body.get("path"),
                        project_id=body.get("id"),
                        parked=body.get("parked"),
                        remove=bool(body.get("remove", False)),
                    )
                    if not body.get("remove") and body.get("ensure_now"):
                        import status as status_mod  # type: ignore

                        status_mod.project_now_path(res["id"], state=app.state_dir, project_path=str(body.get("path") or ""), ensure=True)
                    app.invalidate("overview", "bootstrap")
                    self._send_json(HTTPStatus.OK, {"ok": True, "project": res})
                    return

                if path == "/api/projects/create":
                    parent_raw = str(body.get("parent_dir") or "").strip()
                    pdir = Path(parent_raw) if parent_raw else collector._default_desktop_dir(app.home_dir)
                    ok_pref = str(app.get_bootstrap().get("ok_prefix") or "/ok")
                    res = collector.create_starter_project(
                        app.state_dir,
                        name=str(body.get("name") or ""),
                        parent_dir=pdir,
                        ok_prefix=ok_pref,
                    )
                    app.invalidate("overview", "bootstrap")
                    self._send_json(HTTPStatus.CREATED, res)
                    return

                if path == "/api/projects/import":
                    import status as status_mod  # type: ignore

                    items = body.get("projects")
                    if not isinstance(items, list) or not items:
                        raise ValueError("請提供至少一個要匯入的專案")
                    imported = []
                    for it in items[:20]:
                        if not isinstance(it, dict) or not it.get("path"):
                            continue
                        reg = collector.register_project(
                            app.state_dir,
                            name=str(it.get("name") or Path(str(it["path"])).name),
                            path=str(it["path"]),
                            project_id=it.get("id"),
                        )
                        status_mod.project_now_path(reg["id"], state=app.state_dir, project_path=str(it["path"]), ensure=True)
                        imported.append(reg)
                    app.invalidate("overview", "bootstrap")
                    self._send_json(HTTPStatus.OK, {"ok": True, "imported": imported})
                    return

                if path == "/api/autostart":
                    enable = bool(body.get("enabled", True))
                    cockpit_top = collector.ROOT / "scripts" / "cockpit.py"
                    import importlib.util

                    spec = importlib.util.spec_from_file_location("_omnikit_cockpit_cli", cockpit_top)
                    if spec is None or spec.loader is None:
                        raise RuntimeError("載入啟動管理模組失敗")
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    res = mod.manage_autostart(
                        app.state_dir,
                        action="install" if enable else "uninstall",
                        repo_root=app.repo_root,
                        port=self.server.server_address[1],
                        start_now=False,
                    )
                    kit_mod.patch(app.state_dir, machine_patch={"server": {"autostart": enable, "port": self.server.server_address[1]}})
                    app.invalidate("bootstrap")
                    self._send_json(HTTPStatus.OK, {"ok": True, "autostart": res})
                    return

                if path == "/api/server/stop":
                    srv = self.server
                    threading.Thread(target=lambda: (time.sleep(0.15), srv.shutdown()), daemon=True).start()
                    self._send_json(HTTPStatus.OK, {"ok": True, "stopping": True})
                    return

                parts = [p for p in path.split("/") if p]
                if len(parts) == 4 and parts[0] == "api" and parts[1] == "projects":
                    pid = unquote(parts[2])
                    if parts[3] == "reconcile":
                        res = app.enqueue_reconcile(pid)
                        self._send_json(HTTPStatus.ACCEPTED, res)
                        return
                    if parts[3] == "critiques":
                        res = collector.add_critique(
                            app.state_dir,
                            pid,
                            text=str(body.get("text") or ""),
                            symptom=str(body.get("symptom") or ""),
                            pain=str(body.get("pain") or ""),
                            criteria=str(body.get("criteria") or ""),
                            project_path=str(body.get("project_path") or ""),
                        )
                        app.invalidate("overview")
                        self._send_json(HTTPStatus.CREATED, res)
                        return
                    if parts[3] == "restore":
                        import status as status_mod  # type: ignore

                        rev = str(body.get("rev") or "")
                        res = status_mod.restore_project_now(pid, rev, state=app.state_dir)
                        app.invalidate("overview")
                        self._send_json(HTTPStatus.OK, res)
                        return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "找不到 API 端點"})
            except (ValueError, TypeError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": collector.sanitize(exc)})
            except FileExistsError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"error": collector.sanitize(exc)})
            except FileNotFoundError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": collector.sanitize(exc)})
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"[cockpit-error] POST {self.path}: {traceback.format_exc()}\n")
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": collector.sanitize(exc)})

        def do_PATCH(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._guard_write():
                return
            try:
                body = self._read_json_body()

                if path == "/api/settings":
                    updated = collector.update_settings(app.state_dir, body)
                    if body.get("done_check") in ("block", "log", "off"):
                        import kit as kit_mod  # type: ignore

                        kit_mod.patch(app.state_dir, profile_patch={"done_check": str(body["done_check"])})
                    app.invalidate("overview", "bootstrap")
                    self._send_json(HTTPStatus.OK, {"ok": True, "settings": updated})
                    return

                parts = [p for p in path.split("/") if p]
                if len(parts) == 5 and parts[0] == "api" and parts[1] == "projects" and parts[3] == "critiques":
                    pid = unquote(parts[2])
                    idx = int(parts[4])
                    done_val = body.get("done")
                    res = collector.toggle_critique(
                        app.state_dir,
                        pid,
                        idx,
                        done=None if done_val is None else bool(done_val),
                    )
                    app.invalidate("overview")
                    self._send_json(HTTPStatus.OK, res)
                    return

                if len(parts) == 3 and parts[0] == "api" and parts[1] == "projects":
                    pid = unquote(parts[2])
                    res = collector.register_project(
                        app.state_dir,
                        name=str(body.get("name") or pid),
                        path=body.get("path"),
                        project_id=pid,
                        parked=body.get("parked"),
                    )
                    app.invalidate("overview", "bootstrap")
                    self._send_json(HTTPStatus.OK, {"ok": True, "project": res})
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "找不到 API 端點"})
            except (ValueError, TypeError, IndexError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": collector.sanitize(exc)})
            except FileNotFoundError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": collector.sanitize(exc)})
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(f"[cockpit-error] PATCH {self.path}: {traceback.format_exc()}\n")
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": collector.sanitize(exc)})

    return Handler


def bind_server(
    host: str = "127.0.0.1",
    preferred_port: int = 3780,
    *,
    app: CockpitApp | None = None,
    strict_port: bool = False,
) -> ExclusiveHTTPServer:
    instance = app if app is not None else CockpitApp()
    handler = _make_handler(instance)
    if strict_port or preferred_port == 0:
        srv = ExclusiveHTTPServer((host, preferred_port), handler)
        srv.cockpit_app = instance  # type: ignore[attr-defined]
        return srv

    last_exc: OSError | None = None
    for candidate in range(preferred_port, preferred_port + 10):
        try:
            srv = ExclusiveHTTPServer((host, candidate), handler)
            srv.cockpit_app = instance  # type: ignore[attr-defined]
            return srv
        except OSError as exc:
            last_exc = exc
            continue
    raise OSError(f"無法綁定連接埠 {preferred_port}..{preferred_port + 9}：{last_exc}")


def create_server(
    host: str = "127.0.0.1",
    port: int = 3780,
    app: CockpitApp | None = None,
) -> ExclusiveHTTPServer:
    return bind_server(host, port, app=app, strict_port=True)
