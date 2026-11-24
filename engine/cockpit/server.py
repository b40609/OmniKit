"""OmniKit 個人面板（Cockpit）本機私有 HTTP + PWA 伺服器。

安全邊界：
- 預設只綁定 127.0.0.1:3780（手機端透過 Tailscale Serve 走 HTTPS 反代，不直接對區網裸奔）。
- 所有 API 回傳 no-store 與基本安全標頭；寫入只限 ~/.omnikit/status/<id>/NOW.md 與 ~/.omnikit/cockpit/config.json。
- 背景自動對帳採單一 FIFO 佇列（一次一條可見 T3 對話），零外部相依。
"""
from __future__ import annotations

import json
import mimetypes
import sys
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import collector, reconciler

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAP_FILE = collector.ROOT / "engine" / "site" / "map.html"
MAX_BODY_BYTES = 64 * 1024  # 64 KB 防畸形大封包

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


class CockpitApp:
    """可注入 state_dir、t3_runner、reconcile_runner 與 cache 的伺服器應用狀態。"""

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        data_dir: Path | None = None,
        default_repo_root: Path | None = collector.ROOT,
        t3_runner: Callable[[Path], list[dict[str, Any]] | None] | None = None,
        reconcile_runner: Callable[..., dict[str, Any]] | None = None,
        cache_ttl: float = 15.0,
    ):
        self.state_dir = state_dir if state_dir is not None else collector.default_state_dir()
        self.data_dir = data_dir if data_dir is not None else (collector.ROOT / "data")
        self.default_repo_root = default_repo_root
        self.t3_runner = t3_runner
        self.cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, Any]] = {}
        self.reconciler = reconciler.ReconcileManager(
            state_dir=self.state_dir,
            on_done=lambda: self.invalidate("overview"),
            runner=reconcile_runner,
        )

    def invalidate(self, *keys: str) -> None:
        with self._lock:
            if not keys:
                self._cache.clear()
            else:
                for k in keys:
                    self._cache.pop(k, None)

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
        # 每次即時疊加對帳佇列狀態（不吃快取）
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
        data = collector.collect_accounts(self.state_dir, refresh_agy=refresh_agy)
        with self._lock:
            self._cache["accounts"] = (time.monotonic(), data)
        return data

    def enqueue_reconcile(self, project_id: str) -> dict[str, Any]:
        ov = self.get_overview(force_sync=False)
        target = next((p for p in ov["projects"] if p["id"].lower() == project_id.lower()), None)
        if target is None:
            raise FileNotFoundError(f"找不到專案：{project_id}")
        job = self.reconciler.enqueue(target, t3_base_url=ov["settings"].get("t3_base_url") or "")
        return {"ok": True, "job": job, "reconcile": self.reconciler.snapshot()}

    def enqueue_reconcile_all(self, *, only_stale: bool = True) -> dict[str, Any]:
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
            sys.stderr.write(f"[cockpit] {self.address_string()} - {format % args}\n")

        def _send_bytes(self, status: int, body: bytes, content_type: str, *, cache_control: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: Any) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, raw, "application/json; charset=utf-8")

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

            try:
                if path == "/api/health":
                    self._send_json(HTTPStatus.OK, {"ok": True, "service": "omnikit-cockpit", "map_available": MAP_FILE.is_file()})
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

                if path.startswith("/api/projects/") and path.endswith("/now"):
                    parts = [p for p in path.split("/") if p]
                    if len(parts) == 4:
                        pid = unquote(parts[2])
                        target = collector.safe_status_now_path(app.state_dir, pid)
                        if not target.is_file():
                            self._send_json(HTTPStatus.OK, {"project_id": pid, "exists": False, "content": ""})
                        else:
                            self._send_json(HTTPStatus.OK, {"project_id": pid, "exists": True, "path": str(target), "content": collector.read_utf8(target)})
                        return

                if not path.startswith("/api/"):
                    self._serve_static(path.lstrip("/"))
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "找不到 API 端點"})
            except (ValueError, TypeError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": collector.sanitize(exc)})
            except Exception as exc:  # noqa: BLE001  HTTP 請求兜底避免伺服器崩潰
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": collector.sanitize(exc)})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                body = self._read_json_body()

                if path == "/api/reconcile-all":
                    only_stale = bool(body.get("only_stale", True))
                    res = app.enqueue_reconcile_all(only_stale=only_stale)
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
                    app.invalidate("overview")
                    self._send_json(HTTPStatus.OK, {"ok": True, "project": res})
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

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "找不到 API 端點"})
            except (ValueError, TypeError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": collector.sanitize(exc)})
            except FileNotFoundError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": collector.sanitize(exc)})
            except Exception as exc:  # noqa: BLE001  HTTP 請求兜底避免伺服器崩潰
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": collector.sanitize(exc)})

        def do_PATCH(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                body = self._read_json_body()

                if path == "/api/settings":
                    updated = collector.update_settings(app.state_dir, body)
                    app.invalidate("overview")
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
                    app.invalidate("overview")
                    self._send_json(HTTPStatus.OK, {"ok": True, "project": res})
                    return

                self._send_json(HTTPStatus.NOT_FOUND, {"error": "找不到 API 端點"})
            except (ValueError, TypeError, IndexError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": collector.sanitize(exc)})
            except FileNotFoundError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": collector.sanitize(exc)})
            except Exception as exc:  # noqa: BLE001  HTTP 請求兜底避免伺服器崩潰
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": collector.sanitize(exc)})

    return Handler


def create_server(
    host: str = "127.0.0.1",
    port: int = 3780,
    app: CockpitApp | None = None,
) -> ThreadingHTTPServer:
    instance = app if app is not None else CockpitApp()
    server = ThreadingHTTPServer((host, port), _make_handler(instance))
    server.daemon_threads = True
    return server
