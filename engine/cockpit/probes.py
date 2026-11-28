"""OmniKit 控制面板：零改碼主動探針與正交三軸運行態引擎（控制平面 L1＋L2）。

為什麼：專案狀態板（NOW.md）只說「做到哪」，不說「現在有沒有在跑、跑的是不是最新的碼、有沒有真的產出」。
這支不用改任何專案的程式碼，由面板這一方主動去看事實，每個服務固定輸出三個互不混淆的軸：

- alive（活著嗎）：UP、DEGRADED、DOWN、PAUSED、NO_DATA。UP 再分 proof_level：
  output_verified（有新鮮產出或內容斷言通過，實心綠）與 liveness_only（只證實行程或埠活著，空心綠）。
- sync（版本對嗎）：SYNCED、DRIFT（行程啟動早於最後一次非文件 commit、回報版本不是 HEAD、建置輸出比原始碼舊、
  有未提交改動晚於行程啟動）、DIRTY（心跳自報 x_dirty）、NO_DATA、N/A。
- fresh（資料新嗎）：FRESH、STALE、DOWN、PAUSED、N/A。

探針類型（一個服務可以掛好幾種證據）：tcp、process、http、win_task、artifact（產出檔或唯讀 SQLite）、heartbeat。

設定兩層疊加：專案根目錄選配的 omnikit.probes.yaml（跟著 Git 走，團隊共用）是預設，
個人的 ~/.omnikit/cockpit/config.json 的 probes.<專案代號>.services 蓋過它（同 id 的服務以個人為準，可用 enabled: false 停用）。

安全邊界（不能放寬）：
- http 與 tcp 只准連 127.0.0.1、localhost、::1，不跟隨轉址、不走代理、不帶任何標頭，回應內容不外流（只留斷言結果與版本字串）。
- SQLite 一律 file:…?mode=ro 唯讀開啟，表名與欄位名要過 ^[A-Za-z_][A-Za-z0-9_]*$，沒有任何地方接受原始 SQL。
- 路徑不接受 UNC、裝置路徑與 ..；專案共用設定只能用專案內的相對路徑。
- 行程比對只看命令列有沒有包含指定字串，命令列本身不輸出（裡面可能有金鑰）。
- 不讀任何金鑰或 token；win_task 的名稱用環境變數傳給 PowerShell，不拼進指令。

明確不做（Q4）：不存時間序列、不當行程管理員、不自動重啟業務服務、不改專案的碼。
"""
from __future__ import annotations

import fnmatch
import glob as glob_mod
import hashlib
import itertools
import json
import math
import os
import re
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import collector

if str(collector.SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(collector.SCRIPTS_DIR))
import stale_check  # type: ignore

PROJECT_FILE = "omnikit.probes.yaml"
PROBE_TYPES = ("tcp", "process", "http", "win_task", "artifact", "heartbeat")
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LISTEN_ANY = frozenset({"0.0.0.0", "::", "::1", "127.0.0.1", "*"})

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")          # SQLite 表名、欄位名白名單
SERVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,47}$")
JSON_PATH_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}(?:\.[A-Za-z0-9_-]{1,40}){0,7}$")
TASK_NAME_RE = re.compile(r"^[^\x00-\x1f\"'`$;|&<>*?]{1,200}$")
HOURS_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)\s*-\s*([01]?\d|2[0-4]):([0-5]\d)$")
OFFSET_RE = re.compile(r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)
HEX_RE = re.compile(r"^[0-9a-f]{7,40}$")

MAX_SERVICES = 20
MAX_PROBES = 8
MAX_FILE_BYTES = 64 * 1024
HTTP_TIMEOUT_S = 2.0
HTTP_MAX_BODY = 64 * 1024
TCP_TIMEOUT_S = 0.4
SQLITE_BUDGET_S = 1.0
GIT_TIMEOUT_S = 2.0
PS_TIMEOUT_S = 6.0
WIN_TASK_TTL_S = 120.0
GLOB_MAX_MATCHES = 2000
DIR_SCAN_MAX_FILES = 20000
WAKE_JUMP_S = 120.0     # 掛鐘比「醒著的時間」多跳這麼多秒，就當成剛從休眠醒來
WAKE_GRACE_S = 180.0    # 醒來後這麼久之內，只因超時的異常都先標 PAUSED
DEFAULT_POLL_S = 60.0
POLL_ENV = "OMNIKIT_COCKPIT_POLL_S"

# 不算「改了碼」的檔案：文件、授權、CI 設定。sync.ignore 可以再加
DOC_PATTERNS = ("*.md", "*.mdx", "*.markdown", "*.rst", "docs/*", "doc/*", "LICENSE*", "CHANGELOG*", ".github/*",
                ".gitignore", ".gitattributes")
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"})
DAY_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
# 工作排程器的 LastTaskResult：0 成功、0x41301 正在跑、0x41303 還沒跑過、0x41300 就緒、0x41325 已排入佇列
TASK_RESULT_FINE = frozenset({0, 0x41300, 0x41301, 0x41303, 0x41325})

ALIVE_STATES = ("UP", "DEGRADED", "DOWN", "PAUSED", "NO_DATA")
SYNC_STATES = ("SYNCED", "DRIFT", "DIRTY", "NO_DATA", "N/A")
FRESH_STATES = ("FRESH", "STALE", "DOWN", "PAUSED", "N/A")
_OUT_ORDER = {"DOWN": 3, "STALE": 2, "PAUSED": 1, "FRESH": 0}


# ---------- 小工具 ----------

def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec="seconds") if dt is not None else None


def _short(text: Any, limit: int = 200) -> str:
    return collector.sanitize(text, limit)


def _parse_iso(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00") if raw.strip().endswith("Z") else raw.strip())
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _slug_id(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(name or "").strip()).strip("-.")[:40]
    if cleaned and SERVICE_ID_RE.match(cleaned):
        return cleaned.lower()
    return "svc-" + hashlib.sha1(str(name or "").encode("utf-8")).hexdigest()[:8]


def _is_num(v: Any) -> bool:
    return not isinstance(v, bool) and isinstance(v, int | float) and math.isfinite(v)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def tz_for(name: Any) -> tuple[Any, str]:
    """回傳（tzinfo, 備註）。空字串或 local 是系統時區；UTC、+08:00 這類固定位移不需要 tzdata；其他當 IANA 名稱。"""
    s = str(name or "").strip()
    if not s or s.lower() == "local":
        return datetime.now().astimezone().tzinfo or UTC, ""
    if s.upper() in ("UTC", "Z", "GMT"):
        return UTC, ""
    m = OFFSET_RE.match(s)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        delta = timedelta(hours=int(m.group(2)), minutes=int(m.group(3) or 0))
        if delta <= timedelta(hours=14):
            return timezone(sign * delta), ""
    try:
        import zoneinfo

        return zoneinfo.ZoneInfo(s), ""
    except Exception:  # noqa: BLE001  沒裝 tzdata 或名稱不存在：退回系統時區並註明
        return datetime.now().astimezone().tzinfo or UTC, f"找不到時區 {s}，改用系統時區"


def poll_interval(cfg: dict[str, Any] | None = None, environ: dict[str, str] | None = None) -> float:
    """背景巡檢多久一輪（秒）：環境變數 OMNIKIT_COCKPIT_POLL_S 優先，其次設定的 runtime.poll_interval_s，預設 60。"""
    env = os.environ if environ is None else environ
    raw: Any = env.get(POLL_ENV)
    if raw in (None, ""):
        raw = ((cfg or {}).get("runtime") or {}).get("poll_interval_s") if isinstance((cfg or {}).get("runtime"), dict) else None
    try:
        val = float(raw) if raw not in (None, "") else DEFAULT_POLL_S
    except (TypeError, ValueError):
        val = DEFAULT_POLL_S
    return max(5.0, min(3600.0, val))


# ---------- 設定檢查與正規化 ----------

def _safe_path_text(raw: Any, what: str) -> str:
    s = str(raw or "").strip()
    if not s:
        raise ValueError(f"{what} 不可為空")
    if len(s) > 400 or "\x00" in s or any(ord(c) < 32 for c in s):
        raise ValueError(f"{what} 太長或含控制字元")
    if s.replace("/", "\\").startswith("\\\\"):
        raise ValueError(f"{what} 不接受網路路徑（UNC）或裝置路徑")
    if any(part == ".." for part in re.split(r"[\\/]+", s)):
        raise ValueError(f"{what} 不可包含 ..")
    return s


def _loopback_host(raw: Any) -> str:
    h = str(raw or "127.0.0.1").strip().lower().strip("[]")
    if h not in LOOPBACK_HOSTS:
        raise ValueError("探針只能連本機（127.0.0.1、localhost、::1）")
    return h


def validate_loopback_url(raw: Any) -> str:
    url = str(raw or "").strip()
    if not url or len(url) > 300 or any(ord(c) < 33 for c in url):
        raise ValueError("url 不可為空、不可含空白，長度上限 300")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url 只接受 http:// 或 https://")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise ValueError("url 不可帶帳號密碼")
    if (parsed.hostname or "").lower() not in LOOPBACK_HOSTS:
        raise ValueError("http 探針只能連本機（127.0.0.1、localhost、::1）")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("url 的連接埠不合法") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("url 的連接埠不合法")
    if parsed.fragment:
        raise ValueError("url 不可帶 # 片段")
    return url


def _norm_probe(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("探針要是物件")
    ptype = str(raw.get("type") or "").strip().lower()
    if ptype not in PROBE_TYPES:
        raise ValueError(f"不支援的探針類型：{ptype or '（空）'}（可用：{'、'.join(PROBE_TYPES)}）")

    def only(*keys: str) -> None:
        extra = sorted(set(raw) - {"type", "label", *keys})
        if extra:
            raise ValueError(f"{ptype} 探針不認得欄位：{'、'.join(extra)}")

    def pos_num(key: str, *, allow_zero: bool = False) -> float | None:
        if raw.get(key) is None:
            return None
        v = raw[key]
        if not _is_num(v) or v < 0 or (v == 0 and not allow_zero):
            raise ValueError(f"{key} 要是{'0 以上' if allow_zero else '大於 0'}的數字")
        return v

    def nat(key: str) -> int | None:
        if raw.get(key) is None:
            return None
        if not _is_int(raw[key]) or raw[key] < 0:
            raise ValueError(f"{key} 要是 0 以上的整數")
        return raw[key]

    out: dict[str, Any] = {"type": ptype}
    if raw.get("label"):
        out["label"] = str(raw["label"]).strip()[:60]

    if ptype == "tcp":
        only("host", "port")
        out["host"] = _loopback_host(raw.get("host"))
        if not _is_int(raw.get("port")) or not 1 <= raw["port"] <= 65535:
            raise ValueError("tcp 探針的 port 要是 1 到 65535 的整數")
        out["port"] = raw["port"]
    elif ptype == "process":
        only("match", "match_all")
        match = str(raw.get("match") or "").strip()
        if not 3 <= len(match) <= 200:
            raise ValueError("process 探針的 match 要 3 到 200 個字（命令列裡的特徵字串）")
        out["match"] = match
        extra_match = raw.get("match_all") or []
        if not isinstance(extra_match, list) or len(extra_match) > 5 or not all(isinstance(x, str) and 1 <= len(x.strip()) <= 200 for x in extra_match):
            raise ValueError("match_all 要是最多 5 個非空字串")
        if extra_match:
            out["match_all"] = [x.strip() for x in extra_match]
    elif ptype == "http":
        only("url", "expect_status", "expect_json", "version_json_path")
        out["url"] = validate_loopback_url(raw.get("url"))
        status = raw.get("expect_status", 200)
        if not _is_int(status) or not 100 <= status <= 599:
            raise ValueError("expect_status 要是 100 到 599 的整數")
        out["expect_status"] = status
        ej = raw.get("expect_json")
        if ej is not None:
            if not isinstance(ej, dict) or not ej or len(ej) > 10:
                raise ValueError("expect_json 要是 1 到 10 個欄位的物件")
            for k, v in ej.items():
                if not JSON_PATH_RE.match(str(k)):
                    raise ValueError(f"expect_json 的欄位路徑不合法：{k}")
                if not (v is None or isinstance(v, str | int | float | bool)) or (isinstance(v, str) and len(v) > 200):
                    raise ValueError(f"expect_json.{k} 的期望值要是字串、數字、布林或 null")
            out["expect_json"] = {str(k): v for k, v in ej.items()}
        vp = raw.get("version_json_path")
        if vp is not None:
            if not JSON_PATH_RE.match(str(vp)):
                raise ValueError("version_json_path 要像 commit 或 build.sha 這樣的欄位路徑")
            out["version_json_path"] = str(vp)
    elif ptype == "win_task":
        only("name", "max_age_s")
        name = str(raw.get("name") or "").strip()
        if not TASK_NAME_RE.match(name):
            raise ValueError("win_task 探針的 name 不合法（工作排程器的工作名稱，可帶 \\ 資料夾）")
        out["name"] = name
        if (v := pos_num("max_age_s")) is not None:
            out["max_age_s"] = v
    elif ptype == "artifact":
        only("glob", "max_age_s", "min_bytes", "sqlite_path", "table", "ts_col", "max_age_days", "min_rows", "ts_naive_tz")
        has_glob, has_db = bool(raw.get("glob")), bool(raw.get("sqlite_path"))
        if has_glob == has_db:
            raise ValueError("artifact 探針要給 glob（產出檔）或 sqlite_path（資料庫）其中一個")
        if has_glob:
            if any(raw.get(k) is not None for k in ("table", "ts_col", "max_age_days", "min_rows", "ts_naive_tz")):
                raise ValueError("產出檔探針不用 table、ts_col、max_age_days、min_rows")
            out["glob"] = _safe_path_text(raw["glob"], "glob")
            if (v := pos_num("max_age_s")) is not None:
                out["max_age_s"] = v
            if (n := nat("min_bytes")) is not None:
                out["min_bytes"] = n
        else:
            if any(raw.get(k) is not None for k in ("max_age_s", "min_bytes")):
                raise ValueError("SQLite 探針不用 max_age_s、min_bytes（用 max_age_days、min_rows）")
            out["sqlite_path"] = _safe_path_text(raw["sqlite_path"], "sqlite_path")
            if any(c in out["sqlite_path"] for c in "*?[]"):
                raise ValueError("sqlite_path 不可含萬用字元")
            for key in ("table", "ts_col"):
                ident = str(raw.get(key) or "")
                if not IDENT_RE.match(ident) or len(ident) > 64:
                    raise ValueError(f"{key} 只能是英數與底線、不能數字開頭（^[A-Za-z_][A-Za-z0-9_]*$）")
                out[key] = ident
            if (v := pos_num("max_age_days")) is not None:
                out["max_age_days"] = v
            if (n := nat("min_rows")) is not None:
                out["min_rows"] = n
            naive = str(raw.get("ts_naive_tz") or "local").strip().lower()
            if naive not in ("local", "utc"):
                raise ValueError("ts_naive_tz 只能是 local 或 utc")
            out["ts_naive_tz"] = naive
    else:  # heartbeat
        only("path", "override_period_s", "override_grace_s", "max_run_s", "min_items_out", "max_data_age_days", "skip_pid")
        out["path"] = _safe_path_text(raw.get("path"), "path")
        if any(c in out["path"] for c in "*?[]"):
            raise ValueError("心跳檔的 path 不可含萬用字元")
        if (v := pos_num("override_period_s")) is not None:
            out["override_period_s"] = v
        if (v := pos_num("override_grace_s", allow_zero=True)) is not None:
            out["override_grace_s"] = v
        if (v := pos_num("max_run_s")) is not None:
            out["max_run_s"] = v
        if (n := nat("min_items_out")) is not None:
            out["min_items_out"] = n
        if (v := pos_num("max_data_age_days", allow_zero=True)) is not None:
            out["max_data_age_days"] = v
        if raw.get("skip_pid") is not None:
            out["skip_pid"] = bool(raw["skip_pid"])
    return out


def _norm_days(raw: Any) -> list[int]:
    if raw in (None, "", []):
        return []
    items = raw if isinstance(raw, list) else re.split(r"[,\s]+", str(raw).strip())
    days: set[int] = set()
    for it in items:
        if _is_int(it) and 1 <= it <= 7:
            days.add(it - 1)
            continue
        key = str(it).strip().lower()[:3]
        if key not in DAY_NAMES:
            raise ValueError(f"active_days 不認得 {it!r}（用 mon、tue、wed、thu、fri、sat、sun 或 1 到 7）")
        days.add(DAY_NAMES[key])
    return sorted(days)


def _norm_hours(raw: Any) -> list[list[int]]:
    if raw in (None, "", []):
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[list[int]] = []
    for it in items[:6]:
        m = HOURS_RE.match(str(it).strip())
        if not m:
            raise ValueError(f"active_hours 要像 09:00-17:30（可跨夜，例如 22:00-06:00）：{it!r}")
        start, end = int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))
        if end > 1440 or start == end:
            raise ValueError(f"active_hours 的時間範圍不合法：{it!r}")
        out.append([start, end])
    return out


def normalize_service(raw: Any, *, partial: bool = False) -> dict[str, Any]:
    """檢查並正規化一個服務設定；不合法就丟 ValueError（訊息給人看）。partial 給個人疊層用：可以只有 id 加要蓋掉的欄位。"""
    if not isinstance(raw, dict):
        raise TypeError("服務設定要是物件")
    known = {"id", "name", "enabled", "probes", "sync", "active_days", "active_hours", "timezone", "acknowledged_until", "note"}
    extra = sorted(set(raw) - known)
    if extra:
        raise ValueError(f"服務設定不認得欄位：{'、'.join(extra)}")
    name = str(raw.get("name") or "").strip()[:60]
    sid = str(raw.get("id") or "").strip() or (_slug_id(name) if name else "")
    if not SERVICE_ID_RE.match(sid):
        raise ValueError("服務的 id 只能用英數、點、底線與連字號（最多 48 字），或改填 name 讓系統自動產生")
    out: dict[str, Any] = {"id": sid}
    if name:
        out["name"] = name
    if "enabled" in raw:
        out["enabled"] = bool(raw["enabled"])
    if raw.get("note"):
        out["note"] = str(raw["note"]).strip()[:120]

    if "probes" in raw:
        probes = raw["probes"]
        if not isinstance(probes, list) or len(probes) > MAX_PROBES:
            raise ValueError(f"probes 要是清單，最多 {MAX_PROBES} 個")
        out["probes"] = [_norm_probe(p) for p in probes]
    elif not partial:
        raise ValueError("服務至少要有 probes 清單")
    if not partial and not out.get("probes") and out.get("enabled", True):
        raise ValueError("服務至少要有一個探針")

    if raw.get("sync") is not None:
        sync = raw["sync"]
        if not isinstance(sync, dict):
            raise ValueError("sync 要是物件")
        bad = sorted(set(sync) - {"enabled", "src_dir", "build_dir", "ignore", "paths", "check_worktree"})
        if bad:
            raise ValueError(f"sync 不認得欄位：{'、'.join(bad)}")
        s_out: dict[str, Any] = {}
        for key in ("enabled", "check_worktree"):
            if key in sync:
                s_out[key] = bool(sync[key])
        for key in ("src_dir", "build_dir"):
            if sync.get(key):
                s_out[key] = _safe_path_text(sync[key], f"sync.{key}")
        if bool(s_out.get("src_dir")) != bool(s_out.get("build_dir")):
            raise ValueError("sync 的 src_dir 與 build_dir 要一起給")
        for key in ("ignore", "paths"):
            vals = sync.get(key) or []
            if not isinstance(vals, list) or len(vals) > 20 or not all(isinstance(x, str) and 1 <= len(x) <= 120 for x in vals):
                raise ValueError(f"sync.{key} 要是最多 20 個字串")
            if vals:
                s_out[key] = [_safe_path_text(x, f"sync.{key}") for x in vals]
        out["sync"] = s_out
    if "active_days" in raw:
        out["active_days"] = _norm_days(raw["active_days"])
    if "active_hours" in raw:
        out["active_hours"] = _norm_hours(raw["active_hours"])
    if raw.get("timezone"):
        tzname = str(raw["timezone"]).strip()
        if len(tzname) > 64 or not re.match(r"^[A-Za-z0-9_+:/\- ]+$", tzname):
            raise ValueError("timezone 要是 IANA 名稱（例如 Asia/Taipei）、UTC 或 +08:00")
        out["timezone"] = tzname
    if raw.get("acknowledged_until"):
        if _parse_iso(raw["acknowledged_until"]) is None:
            raise ValueError("acknowledged_until 要是帶時區的 ISO 8601 時間")
        out["acknowledged_until"] = str(raw["acknowledged_until"]).strip()
    return out


def _norm_list(raw: Any, *, partial: bool, errors: list[str], where: str) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append(f"{where}：services 要是清單")
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, item in enumerate(raw[:MAX_SERVICES]):
        try:
            svc = normalize_service(item, partial=partial)
        except (ValueError, TypeError) as exc:
            label = (item.get("name") or item.get("id") or f"第 {i + 1} 個") if isinstance(item, dict) else f"第 {i + 1} 個"
            errors.append(f"{where}「{_short(label, 40)}」：{_short(exc)}")
            continue
        if svc["id"].lower() in seen:
            errors.append(f"{where}：服務 id 重複（{svc['id']}），只留第一個")
            continue
        seen.add(svc["id"].lower())
        out.append(svc)
    if len(raw) > MAX_SERVICES:
        errors.append(f"{where}：服務超過 {MAX_SERVICES} 個，後面的略過")
    return out


def read_project_layer(project_root: Path | None, errors: list[str]) -> list[dict[str, Any]]:
    """讀專案根目錄選配的 omnikit.probes.yaml。沒有就回空清單；壞掉的記進 errors，不讓整個面板掛掉。"""
    if project_root is None:
        return []
    path = project_root / PROJECT_FILE
    try:
        if not path.is_file():
            return []
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"{PROJECT_FILE} 超過 {MAX_FILE_BYTES // 1024} KB，略過")
            return []
        import yaml

        doc = yaml.safe_load(collector.read_utf8(path))
    except ImportError:
        errors.append(f"讀 {PROJECT_FILE} 需要 pyyaml")
        return []
    except Exception as exc:  # noqa: BLE001  YAML 格式錯、讀檔失敗都只是這個專案沒有共用設定
        errors.append(f"{PROJECT_FILE} 讀不懂：{_short(exc, 120)}")
        return []
    if doc is None:
        return []
    if not isinstance(doc, dict):
        errors.append(f"{PROJECT_FILE} 的最外層要是物件（services: […]）")
        return []
    return _norm_list(doc.get("services"), partial=False, errors=errors, where=PROJECT_FILE)


def personal_layer_raw(cfg: dict[str, Any], project_id: str) -> list[Any]:
    table = cfg.get("probes")
    if not isinstance(table, dict):
        return []
    for key, val in table.items():
        if str(key).lower() == project_id.lower() and isinstance(val, dict) and isinstance(val.get("services"), list):
            return val["services"]
    return []


def merged_services(project_id: str, project_root: Path | None, cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], dict[str, int]]:
    """兩層疊加：專案檔是預設，個人設定蓋過同 id 的服務。回傳（服務清單, 設定錯誤, 各層服務數）。

    每個服務帶 _source（project、personal、project+personal）與 _probe_layer（探針與路徑來自哪一層，決定准不准用絕對路徑）。
    """
    errors: list[str] = []
    project = read_project_layer(project_root, errors)
    personal = _norm_list(personal_layer_raw(cfg, project_id), partial=True, errors=errors, where="個人設定")
    merged: dict[str, dict[str, Any]] = {}
    for svc in project:
        merged[svc["id"].lower()] = {**svc, "_source": "project", "_probe_layer": "project", "_sync_layer": "project"}
    for svc in personal:
        key = svc["id"].lower()
        base = merged.get(key)
        if base is None:
            if not svc.get("probes") and svc.get("enabled", True):
                errors.append(f"個人設定「{svc['id']}」：沒有探針，專案共用設定裡也沒有這個服務")
                continue
            merged[key] = {**svc, "_source": "personal", "_probe_layer": "personal", "_sync_layer": "personal"}
            continue
        combo = {**base, **svc, "_source": "project+personal"}
        combo["_probe_layer"] = "personal" if "probes" in svc else "project"
        combo["_sync_layer"] = "personal" if "sync" in svc else "project"
        merged[key] = combo
    services = [s for s in merged.values() if s.get("enabled", True) and s.get("probes")]
    return services, errors, {"project": len(project), "personal": len(personal)}


def resolve_local_path(raw: str, *, project_root: Path | None, home: Path, layer: str) -> Path:
    """把設定裡的路徑變成本機路徑。專案共用設定只能用專案內的相對路徑；個人設定可以用絕對路徑與 ~。"""
    text = _safe_path_text(raw, "路徑")
    if text.startswith("~") and (len(text) == 1 or text[1] in "/\\"):
        if layer != "personal":
            raise ValueError("專案共用設定只能用專案內的相對路徑")
        text = str(home) + text[1:]
    p = Path(text)
    if p.is_absolute() or p.anchor or p.drive:
        if layer != "personal":
            raise ValueError("專案共用設定只能用專案內的相對路徑")
        return p
    if project_root is None:
        raise ValueError("相對路徑需要這台有專案目錄")
    return project_root / p


# ---------- 系統事實（可替換，測試時注入假的） ----------

_WIN_TASK_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$names = @(($env:OMNIKIT_PROBE_TASKS | ConvertFrom-Json) | ForEach-Object { $_ })
$out = @()
foreach ($n in $names) {
  $full = [string]$n
  $idx = $full.LastIndexOf('\')
  try {
    if ($idx -ge 0) {
      $t = Get-ScheduledTask -TaskName $full.Substring($idx + 1) -TaskPath $full.Substring(0, $idx + 1) -ErrorAction Stop
    } else {
      $t = Get-ScheduledTask -TaskName $full -ErrorAction Stop | Select-Object -First 1
    }
    $i = $t | Get-ScheduledTaskInfo
    $last = $null
    if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $last = $i.LastRunTime.ToUniversalTime().ToString('o') }
    $next = $null
    if ($i.NextRunTime) { $next = $i.NextRunTime.ToUniversalTime().ToString('o') }
    $out += [pscustomobject]@{ name = $full; found = $true; state = [string]$t.State; last_run = $last; next_run = $next; last_result = [int64]$i.LastTaskResult; missed = [int]$i.NumberOfMissedRuns }
  } catch {
    $out += [pscustomobject]@{ name = $full; found = $false; error = [string]$_.Exception.Message }
  }
}
ConvertTo-Json -InputObject @($out) -Compress -Depth 3
"""

_LISTEN_PS = (
    "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
    "ConvertTo-Json -Compress -InputObject @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
    "Select-Object LocalAddress, LocalPort, OwningProcess)"
)


def _powershell_exe() -> str:
    return str(Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def _run_hidden(args: list[str], *, timeout: float, env: dict[str, str] | None = None, cwd: Path | None = None) -> tuple[int, str]:
    kw: dict[str, Any] = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace", "timeout": timeout,
                          "stdin": subprocess.DEVNULL}
    if env is not None:
        kw["env"] = env
    if cwd is not None:
        kw["cwd"] = str(cwd)
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(args, check=False, **kw)
        return proc.returncode, proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def awake_seconds() -> float:
    """「醒著的時間」的單調時鐘：電腦休眠時不走。

    Windows 的 time.monotonic()（QueryPerformanceCounter）休眠時照走，拿來跟掛鐘比看不出休眠，
    所以用 QueryUnbiasedInterruptTime（文件明講不含休眠與睡眠的時間）。其他平台的 time.monotonic() 本來就不含休眠。
    """
    if sys.platform == "win32":
        try:
            import ctypes

            val = ctypes.c_ulonglong()
            if ctypes.WinDLL("kernel32").QueryUnbiasedInterruptTime(ctypes.byref(val)):
                return val.value / 1e7
        except (OSError, AttributeError):
            pass
    return time.monotonic()


def _win_listeners_native() -> list[tuple[str, int, int]] | None:
    """GetExtendedTcpTable：跟 Get-NetTCPConnection 同一份核心資料，在行程內直接讀（毫秒級，不開 PowerShell）。"""
    import ctypes
    from ctypes import wintypes

    try:
        iphlpapi = ctypes.WinDLL("iphlpapi")
    except OSError:
        return None

    class Row4(ctypes.Structure):
        _fields_ = [("state", wintypes.DWORD), ("local_addr", wintypes.DWORD), ("local_port", wintypes.DWORD),
                    ("remote_addr", wintypes.DWORD), ("remote_port", wintypes.DWORD), ("pid", wintypes.DWORD)]

    class Row6(ctypes.Structure):
        _fields_ = [("local_addr", ctypes.c_ubyte * 16), ("local_scope", wintypes.DWORD), ("local_port", wintypes.DWORD),
                    ("remote_addr", ctypes.c_ubyte * 16), ("remote_scope", wintypes.DWORD), ("remote_port", wintypes.DWORD),
                    ("state", wintypes.DWORD), ("pid", wintypes.DWORD)]

    out: list[tuple[str, int, int]] = []
    ok_any = False
    for family, row_type in ((socket.AF_INET, Row4), (23, Row6)):   # 23 = AF_INET6
        size = wintypes.DWORD(0)
        iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, family, 3, 0)   # 3 = TCP_TABLE_OWNER_PID_LISTENER
        for _ in range(3):   # 兩次呼叫之間表可能變大
            buf = ctypes.create_string_buffer(max(size.value, 8))
            rc = iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, family, 3, 0)
            if rc == 0:
                break
            if rc != 122:   # ERROR_INSUFFICIENT_BUFFER 才重試
                buf = None
                break
        else:
            buf = None
        if buf is None:
            continue
        ok_any = True
        count = struct.unpack_from("<L", buf.raw, 0)[0]
        rows = (row_type * count).from_buffer_copy(buf.raw[4:4 + ctypes.sizeof(row_type) * count])
        for r in rows:
            port = socket.ntohs(r.local_port & 0xFFFF)
            if family == socket.AF_INET:
                addr = socket.inet_ntoa(struct.pack("<L", r.local_addr))
            else:
                addr = socket.inet_ntop(socket.AF_INET6, bytes(r.local_addr))
            out.append((addr, port, int(r.pid)))
    return out if ok_any else None


def _win_listeners_powershell() -> list[tuple[str, int, int]] | None:
    """後備：Get-NetTCPConnection -State Listen 的 OwningProcess（要開一次 PowerShell，慢）。"""
    rc, out = _run_hidden([_powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", _LISTEN_PS], timeout=PS_TIMEOUT_S)
    if rc != 0 or not out.strip():
        return None
    try:
        rows = json.loads(out)
    except ValueError:
        return None
    if isinstance(rows, dict):
        rows = [rows]
    res: list[tuple[str, int, int]] = []
    for r in rows if isinstance(rows, list) else []:
        try:
            res.append((str(r["LocalAddress"]), int(r["LocalPort"]), int(r["OwningProcess"])))
        except (KeyError, TypeError, ValueError):
            continue
    return res


def _unix_listeners() -> list[tuple[str, int, int]] | None:
    """Linux：ss -Hltnp（拿得到自己行程的 pid；沒有 ss 就回 None，改用連線測試）。"""
    rc, out = _run_hidden(["ss", "-Hltnp"], timeout=2.0)
    if rc != 0:
        return None
    res: list[tuple[str, int, int]] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        addr, _, port = local.rpartition(":")
        if not port.isdigit():
            continue
        m = re.search(r"pid=(\d+)", line)
        res.append((addr.strip("[]") or "*", int(port), int(m.group(1)) if m else 0))
    return res


def _win_processes() -> list[dict[str, Any]] | None:
    """列出看得到命令列的行程（NtQueryInformationProcess 的 ProcessCommandLineInformation，Windows 8.1 起）。"""
    import ctypes
    from ctypes import wintypes

    try:
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")
    except OSError:
        return None

    class UnicodeString(ctypes.Structure):
        _fields_ = [("length", wintypes.USHORT), ("max_length", wintypes.USHORT), ("buffer", ctypes.c_void_p)]

    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    ntdll.NtQueryInformationProcess.restype = ctypes.c_long
    ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                                                ctypes.POINTER(wintypes.ULONG)]
    arr = (wintypes.DWORD * 8192)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(needed)):
        return None
    out: list[dict[str, Any]] = []
    for pid in arr[: needed.value // ctypes.sizeof(wintypes.DWORD)]:
        if pid in (0, 4):
            continue
        handle = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        try:
            size = wintypes.ULONG(0)
            ntdll.NtQueryInformationProcess(handle, 60, None, 0, ctypes.byref(size))
            if not size.value:
                continue
            buf = ctypes.create_string_buffer(size.value)
            if ntdll.NtQueryInformationProcess(handle, 60, buf, size.value, ctypes.byref(size)) != 0:
                continue
            us = UnicodeString.from_buffer(buf)
            cmd = ctypes.wstring_at(us.buffer, us.length // 2) if us.buffer and us.length else ""
            if cmd:
                out.append({"pid": int(pid), "cmdline": cmd})
        finally:
            k32.CloseHandle(handle)
    return out


def _unix_processes() -> list[dict[str, Any]] | None:
    proc = Path("/proc")
    out: list[dict[str, Any]] = []
    if proc.is_dir() and (proc / "self" / "cmdline").exists():
        for child in proc.iterdir():
            if not child.name.isdigit():
                continue
            try:
                raw = (child / "cmdline").read_bytes()
            except OSError:
                continue
            cmd = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
            if cmd:
                out.append({"pid": int(child.name), "cmdline": cmd})
        return out
    rc, text = _run_hidden(["ps", "-axo", "pid=,args="], timeout=3.0)
    if rc != 0:
        return None
    for line in text.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit() and cmd.strip():
            out.append({"pid": int(pid), "cmdline": cmd.strip()})
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None   # 轉址一律不跟（轉到外部網址就是 SSRF）


class System:
    """探針要向作業系統查的事實都經過這裡；測試可以繼承後換掉任何一個方法。同一個實例跨輪重用（排程查詢有快取）。"""

    def __init__(self) -> None:
        self._task_lock = threading.Lock()
        self._task_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._task_refreshing = False

    # -- 行程與連接埠 --
    def process_info(self, pid: int) -> tuple[str, datetime | None, str]:
        return stale_check.process_info(pid)

    def listeners(self) -> list[tuple[str, int, int]] | None:
        """目前在聽的 TCP 埠：[(位址, 埠, pid)]；查不到回 None（呼叫端改用連線測試）。"""
        if sys.platform == "win32":
            rows = _win_listeners_native()
            return rows if rows is not None else _win_listeners_powershell()
        return _unix_listeners()

    def can_connect(self, host: str, port: int, timeout: float = TCP_TIMEOUT_S) -> tuple[bool, bool]:
        """回傳（連不連得上, 是不是逾時）。"""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True, False
        except TimeoutError:
            return False, True
        except OSError:
            return False, False

    def processes(self) -> list[dict[str, Any]] | None:
        return _win_processes() if sys.platform == "win32" else _unix_processes()

    # -- HTTP（只准本機） --
    def http_get(self, url: str, timeout: float = HTTP_TIMEOUT_S) -> dict[str, Any]:
        validate_loopback_url(url)   # 設定載入時驗過一次，真的要連之前再驗一次
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json, */*;q=0.5", "User-Agent": "omnikit-probe"})
        try:
            with opener.open(req, timeout=timeout) as resp:
                return {"status": resp.status, "body": resp.read(HTTP_MAX_BODY), "error": None, "timed_out": False}
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read(HTTP_MAX_BODY)
            except OSError:
                body = b""
            return {"status": exc.code, "body": body, "error": None, "timed_out": False}
        except TimeoutError:
            return {"status": None, "body": b"", "error": f"逾時（{timeout:g} 秒）", "timed_out": True}
        except (urllib.error.URLError, OSError, ValueError) as exc:
            reason = getattr(exc, "reason", exc)
            timed = isinstance(reason, TimeoutError)
            return {"status": None, "body": b"", "error": _short(reason, 120), "timed_out": timed}

    # -- Windows 工作排程器 --
    def query_win_tasks(self, names: list[str]) -> dict[str, dict[str, Any]]:
        if sys.platform != "win32":
            return {n: {"found": False, "error": "這台不是 Windows，沒有工作排程器", "unsupported": True} for n in names}
        env = {**os.environ, "OMNIKIT_PROBE_TASKS": json.dumps(names, ensure_ascii=False)}
        rc, out = _run_hidden([_powershell_exe(), "-NoProfile", "-NonInteractive", "-Command", _WIN_TASK_PS],
                              timeout=PS_TIMEOUT_S, env=env)
        try:
            rows = json.loads(out) if rc == 0 and out.strip() else None
        except ValueError:
            rows = None
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return {n: {"found": False, "error": "查不到工作排程器（PowerShell 沒有回應）", "query_failed": True} for n in names}
        res = {str(r.get("name")): r for r in rows if isinstance(r, dict)}
        return {n: res.get(n) or {"found": False, "error": "沒有回傳這個工作"} for n in names}

    def win_tasks(self, names: list[str], *, force: bool = False) -> dict[str, dict[str, Any]]:
        """帶快取的排程查詢：開 PowerShell 要一秒上下，所以結果留 120 秒；過期時先用舊的、背景更新，不拖慢這一輪。"""
        now = time.monotonic()
        with self._task_lock:
            cached = {n: self._task_cache[n] for n in names if n in self._task_cache}
        missing = [n for n in names if n not in cached]
        stale = [n for n, (ts, _) in cached.items() if now - ts >= WIN_TASK_TTL_S]
        if force or missing:
            fresh = self.query_win_tasks(names)
            stamp = time.monotonic()
            checked = _iso(datetime.now(UTC))
            with self._task_lock:
                for n, info in fresh.items():
                    self._task_cache[n] = (stamp, {**info, "checked_at": checked})
                return {n: self._task_cache[n][1] for n in names}
        if stale:
            with self._task_lock:
                start_bg = not self._task_refreshing
                self._task_refreshing = True
            if start_bg:
                threading.Thread(target=self._refresh_tasks_bg, args=(list(names),), daemon=True).start()
        return {n: cached[n][1] for n in names}

    def _refresh_tasks_bg(self, names: list[str]) -> None:
        try:
            fresh = self.query_win_tasks(names)
            stamp = time.monotonic()
            checked = _iso(datetime.now(UTC))
            with self._task_lock:
                for n, info in fresh.items():
                    self._task_cache[n] = (stamp, {**info, "checked_at": checked})
        finally:
            with self._task_lock:
                self._task_refreshing = False

    # -- Git（唯讀） --
    def git(self, cwd: Path, args: list[str], timeout: float = GIT_TIMEOUT_S) -> tuple[int, str]:
        env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
        return _run_hidden(["git", "-C", str(cwd), "-c", "core.longpaths=true", "-c", "core.quotepath=false", *args],
                           timeout=timeout, env=env)


class WakeDetector:
    """休眠喚醒偵測：每輪比「醒著的時間」與掛鐘各走了多少。掛鐘多跳超過 120 秒就是剛醒，給 180 秒寬限。

    後備：萬一這個平台的單調時鐘休眠時也照走（兩個增量一樣大），改看這一輪是不是比預期晚了超過 120 秒才輪到。
    """

    def __init__(self, *, jump_s: float = WAKE_JUMP_S, grace_s: float = WAKE_GRACE_S,
                 awake_clock: Callable[[], float] = awake_seconds, wall_clock: Callable[[], float] = time.time) -> None:
        self.jump_s = jump_s
        self.grace_s = grace_s
        self._awake = awake_clock
        self._wall = wall_clock
        self._last: tuple[float, float] | None = None
        self._grace_until: float | None = None
        self.last_wake_at: str | None = None
        self.last_jump_s: float = 0.0

    def tick(self, expected_gap_s: float | None = None) -> float:
        """每輪開始叫一次；回傳喚醒寬限還剩幾秒（0 表示不在寬限期）。"""
        awake, wall = self._awake(), self._wall()
        if self._last is not None:
            d_awake, d_wall = awake - self._last[0], wall - self._last[1]
            jumped = (d_wall - d_awake) > self.jump_s
            overslept = expected_gap_s is not None and d_awake > expected_gap_s + self.jump_s
            if jumped or overslept:
                self._grace_until = awake + self.grace_s
                self.last_jump_s = round(max(d_wall - d_awake, d_awake - (expected_gap_s or 0.0)), 1)
                self.last_wake_at = _iso(datetime.fromtimestamp(wall, UTC))
        self._last = (awake, wall)
        return self.remaining()

    def remaining(self) -> float:
        if self._grace_until is None:
            return 0.0
        left = self._grace_until - self._awake()
        return left if left > 0 else 0.0


# ---------- 探針 ----------

def _probe_base(probe: dict[str, Any], label: str) -> dict[str, Any]:
    return {"type": probe["type"], "label": probe.get("label") or label, "summary": "", "facts": [], "error": None,
            "liveness": None, "output": None, "content_verified": False, "timed_out": False, "stale_kind": None,
            "pid": None, "pid_start_ts": None, "version": None, "x_dirty": None, "remote_host": None, "data_at": None}


def _fact(label: str, value: Any) -> dict[str, str]:
    return {"label": label, "value": _short(value, 160)}


def _attach_pid(res: dict[str, Any], pid: int, ctx: _Ctx) -> None:
    res["pid"] = pid
    res["facts"].append(_fact("PID", pid))
    state, started, _note = ctx.system.process_info(pid)
    if state == "alive" and started is not None:
        res["pid_start_ts"] = _iso(started)
        res["facts"].append(_fact("行程啟動時間", _iso(started)))


def _probe_tcp(probe: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    host, port = probe["host"], probe["port"]
    res = _probe_base(probe, f"TCP {host}:{port}")
    rows = ctx.listeners()
    if rows is not None:
        hits = [(a, pid) for a, p, pid in rows if p == port and (a in LISTEN_ANY or a.startswith("127."))]
        if not hits:
            res.update(liveness="DOWN", summary=f"埠 {port} 沒有行程在聽")
            return res
        pid = next((pid for _a, pid in hits if pid > 0), 0)
        res.update(liveness="UP", summary=f"埠 {port} 有行程在聽")
        res["facts"].append(_fact("監聽位址", "、".join(sorted({a for a, _ in hits}))))
        if pid:
            _attach_pid(res, pid, ctx)
        return res
    ok, timed_out = ctx.system.can_connect(host, port)
    res.update(liveness="UP" if ok else "DOWN", timed_out=timed_out,
               summary=f"埠 {port} 連得上（這台查不到是哪個行程）" if ok else f"埠 {port} 連不上")
    return res


def _probe_process(probe: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    res = _probe_base(probe, f"行程 {probe['match'][:40]}")
    procs = ctx.processes()
    if procs is None:
        res.update(liveness="NO_DATA", summary="這台列不出行程清單", error="列不出行程清單")
        return res
    fold = (lambda s: s.lower()) if os.name == "nt" else (lambda s: s)
    needles = [fold(probe["match"]), *(fold(x) for x in probe.get("match_all", []))]
    me = os.getpid()
    found: list[tuple[datetime | None, int]] = []
    for p in procs:
        if p["pid"] == me:
            continue
        cmd = fold(p["cmdline"])
        if all(n in cmd for n in needles):
            state, started, _note = ctx.system.process_info(p["pid"])
            if state == "alive":
                found.append((started, p["pid"]))
    if not found:
        res.update(liveness="DOWN", summary="找不到命令列符合的行程")
        return res
    # 有好幾個符合時看最早啟動的那個：只要有一個是改碼前就在跑的舊行程，就該提醒
    found.sort(key=lambda t: (t[0] is None, t[0] or datetime.max.replace(tzinfo=UTC)))
    started, pid = found[0]
    res.update(liveness="UP", pid=pid, summary=f"找到 {len(found)} 個符合的行程")
    res["facts"].append(_fact("PID", "、".join(str(p) for _s, p in found[:6])))
    if started is not None:
        res["pid_start_ts"] = _iso(started)
        res["facts"].append(_fact("行程啟動時間（最早的）", _iso(started)))
    return res


def _json_at(doc: Any, path: str) -> tuple[bool, Any]:
    cur = doc
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def _probe_http(probe: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    res = _probe_base(probe, f"HTTP {probe['url']}")
    got = ctx.system.http_get(probe["url"], HTTP_TIMEOUT_S)
    status = got.get("status")
    if status is None:
        res.update(liveness="DOWN", timed_out=bool(got.get("timed_out")), error=_short(got.get("error"), 120),
                   summary=f"連不上：{_short(got.get('error'), 80)}")
        return res
    res["facts"].append(_fact("HTTP 狀態碼", status))
    if status != probe["expect_status"]:
        res.update(liveness="DEGRADED", summary=f"回應 {status}，預期 {probe['expect_status']}")
        return res
    need_json = bool(probe.get("expect_json") or probe.get("version_json_path"))
    doc: Any = None
    if need_json:
        try:
            doc = json.loads((got.get("body") or b"").decode("utf-8", errors="replace"))
        except ValueError:
            res.update(liveness="DEGRADED", summary="回應不是 JSON，無法斷言內容")
            return res
    problems: list[str] = []
    for path, want in (probe.get("expect_json") or {}).items():
        ok, val = _json_at(doc, path)
        if not ok:
            problems.append(f"少了 {path}")
        elif want == "*":
            if val in (None, "", [], {}):
                problems.append(f"{path} 是空的")
        elif val != want:
            problems.append(f"{path} 不是預期的值")
    if probe.get("version_json_path"):
        ok, val = _json_at(doc, probe["version_json_path"])
        if ok and isinstance(val, str | int | float) and not isinstance(val, bool) and str(val).strip():
            res["version"] = str(val).strip()[:64]
            res["facts"].append(_fact("回報版本", res["version"]))
        else:
            problems.append(f"回應裡沒有版本欄位 {probe['version_json_path']}")
    if problems:
        res.update(liveness="DEGRADED", summary="活著，但內容不符：" + "；".join(problems[:3]))
        return res
    res.update(liveness="UP", content_verified=bool(probe.get("expect_json")),
               summary=f"回應 {status}" + ("，內容斷言通過" if probe.get("expect_json") else ""))
    return res


def _probe_win_task(probe: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    name = probe["name"]
    res = _probe_base(probe, f"排程 {name[:40]}")
    info = ctx.win_task(name)
    if info.get("checked_at"):
        res["checked_at"] = info["checked_at"]
    if not info.get("found"):
        if info.get("unsupported") or info.get("query_failed"):
            res.update(liveness="NO_DATA", summary=_short(info.get("error"), 100), error=_short(info.get("error"), 100))
        else:
            res.update(liveness="DOWN", summary="工作排程器裡沒有這個工作", error=_short(info.get("error"), 100))
        return res
    state = str(info.get("state") or "")
    last_run = _parse_iso(info.get("last_run"))
    result = info.get("last_result")
    missed = int(info.get("missed") or 0)
    res["facts"] += [_fact("排程狀態", state), _fact("上次執行", info.get("last_run") or "還沒跑過"),
                     _fact("上次結果", f"0x{int(result):X}" if _is_int(result) else "未知"), _fact("漏跑次數", missed)]
    if info.get("next_run"):
        res["facts"].append(_fact("下次執行", info["next_run"]))
    res["data_at"] = _iso(last_run)
    if state.lower() == "disabled":
        res.update(liveness="DOWN", summary="排程已被停用")
        return res
    issues: list[str] = []
    if _is_int(result) and result not in TASK_RESULT_FINE:
        issues.append(f"上次結果 0x{result:X}（不是 0）")
    if missed > 0:
        issues.append(f"漏跑 {missed} 次")
    if probe.get("max_age_s") is not None:
        age = (ctx.now - last_run).total_seconds() if last_run else None
        if age is None or age > probe["max_age_s"]:
            issues.append("超過期限沒有執行" if age is not None else "還沒執行過")
            res["stale_kind"] = "age" if len(issues) == 1 else None
    if issues:
        res.update(liveness="DEGRADED", summary="；".join(issues))
    else:
        res.update(liveness="UP", summary=f"排程{state or '存在'}，上次結果正常")
    return res


def _parse_db_ts(val: Any, naive_tz: str) -> datetime | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, int | float):
        secs = float(val)
        if secs > 1e14:       # 微秒
            secs /= 1e6
        elif secs > 1e11:     # 毫秒
            secs /= 1e3
        if not 0 < secs < 4e9:
            return None
        return datetime.fromtimestamp(secs, UTC)
    text = str(val).strip()
    if re.fullmatch(r"\d{9,17}(\.\d+)?", text):
        return _parse_db_ts(float(text), naive_tz)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC if naive_tz == "utc" else (datetime.now().astimezone().tzinfo or UTC))
    return dt.astimezone(UTC)


def _probe_artifact_file(probe: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    res = _probe_base(probe, f"產出檔 {probe['glob'][-50:]}")
    try:
        pattern = resolve_local_path(probe["glob"], project_root=ctx.project_root, home=ctx.home, layer=ctx.probe_layer)
    except ValueError as exc:
        res.update(output="DOWN", summary=str(exc), error=str(exc))
        return res
    newest: tuple[float, Path, int] | None = None
    count = 0
    for hit in itertools.islice(glob_mod.iglob(str(pattern), recursive=True), GLOB_MAX_MATCHES):
        try:
            st = os.stat(hit)
        except OSError:
            continue
        if not os.path.isfile(hit):
            continue
        count += 1
        if newest is None or st.st_mtime > newest[0]:
            newest = (st.st_mtime, Path(hit), st.st_size)
    if newest is None:
        res.update(output="DOWN", summary="沒有符合的產出檔")
        return res
    mtime = datetime.fromtimestamp(newest[0], UTC)
    age = (ctx.now - mtime).total_seconds()
    res["data_at"] = _iso(mtime)
    res["facts"] += [_fact("最新產出檔", newest[1].name), _fact("產出時間", _iso(mtime)), _fact("檔案大小", f"{newest[2]} bytes"),
                     _fact("符合的檔案數", count)]
    if probe.get("min_bytes") is not None and newest[2] < probe["min_bytes"]:
        res.update(output="STALE", stale_kind="content", summary=f"產出檔只有 {newest[2]} bytes，低於下限 {probe['min_bytes']}")
        return res
    if probe.get("max_age_s") is not None and age > probe["max_age_s"]:
        res.update(output="STALE", stale_kind="age",
                   summary=f"最新產出是 {stale_check.human(age)}前，超過上限 {stale_check.human(probe['max_age_s'])}")
        return res
    res.update(output="FRESH", summary=f"最新產出是 {stale_check.human(max(age, 0))}前")
    return res


def _probe_artifact_sqlite(probe: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    table, col = probe["table"], probe["ts_col"]
    res = _probe_base(probe, f"SQLite {Path(probe['sqlite_path']).name} {table}.{col}")
    # 表名、欄位名在設定載入時驗過；組 SQL 之前再驗一次，確保沒有任何路徑能把別的字串帶進來
    if not IDENT_RE.match(table) or not IDENT_RE.match(col):
        res.update(output="DOWN", summary="表名或欄位名不合法", error="表名或欄位名不合法")
        return res
    try:
        db = resolve_local_path(probe["sqlite_path"], project_root=ctx.project_root, home=ctx.home, layer=ctx.probe_layer)
    except ValueError as exc:
        res.update(output="DOWN", summary=str(exc), error=str(exc))
        return res
    if not db.is_file():
        res.update(output="DOWN", summary="找不到資料庫檔")
        return res
    deadline = time.monotonic() + SQLITE_BUDGET_S
    conn = None
    try:
        conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True, timeout=0.5)
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 5000)
        latest = conn.execute(f'SELECT MAX("{col}") FROM "{table}"').fetchone()[0]
        rows = None
        if probe.get("min_rows") is not None:
            rows = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except sqlite3.Error as exc:
        timed = time.monotonic() > deadline
        msg = "查詢超過 1 秒（表太大的話請替時間欄建索引）" if timed else f"資料庫讀取失敗：{_short(exc, 100)}"
        res.update(output="DOWN", timed_out=timed, summary=msg, error=msg)
        return res
    finally:
        if conn is not None:
            conn.close()
    if rows is not None:
        res["facts"].append(_fact("資料筆數", rows))
    if latest is None:
        res.update(output="STALE", stale_kind="content", summary="資料表沒有任何資料")
        return res
    latest_dt = _parse_db_ts(latest, probe.get("ts_naive_tz", "local"))
    if latest_dt is None:
        res.update(output="DOWN", summary=f"看不懂時間欄的值：{_short(latest, 40)}", error="時間欄的值無法解析")
        return res
    age = (ctx.now - latest_dt).total_seconds()
    res["data_at"] = _iso(latest_dt)
    res["facts"].append(_fact("最新資料時間", _iso(latest_dt)))
    if rows is not None and rows < probe["min_rows"]:
        res.update(output="STALE", stale_kind="content", summary=f"資料只有 {rows} 筆，低於下限 {probe['min_rows']}")
        return res
    if probe.get("max_age_days") is not None and age > probe["max_age_days"] * 86400:
        res.update(output="STALE", stale_kind="age",
                   summary=f"最新資料是 {stale_check.human(age)}前，超過上限 {probe['max_age_days']:g} 天")
        return res
    res.update(output="FRESH", summary=f"最新資料是 {stale_check.human(max(age, 0))}前")
    return res


def _probe_heartbeat(probe: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    res = _probe_base(probe, f"心跳 {Path(probe['path']).name}")
    try:
        path = resolve_local_path(probe["path"], project_root=ctx.project_root, home=ctx.home, layer=ctx.probe_layer)
    except ValueError as exc:
        res.update(output="DOWN", summary=str(exc), error=str(exc))
        return res
    opts = {k: probe[k] for k in ("override_period_s", "override_grace_s", "max_run_s", "min_items_out", "max_data_age_days", "skip_pid")
            if k in probe}
    opts["wake_grace_remaining_s"] = ctx.wake_grace_remaining_s
    r = stale_check.check_file(path, ctx.now, opts)
    facts, meta, verdict = r.get("facts") or {}, r.get("meta") or {}, r["verdict"]
    top = next((msg for lvl, msg in r["reasons"] if lvl == verdict), None) or next((msg for _l, msg in r["reasons"]), "")
    res.update(output=verdict, summary=_short(top, 200))
    for label, key in (("上次成功", "last_success_ts"), ("上次嘗試", "last_attempt_ts"), ("這一輪寫出筆數", "items_out"),
                       ("資料最新日期", "data_date"), ("版本", "build"), ("主機", "host")):
        if key in facts:
            res["facts"].append(_fact(label, facts[key]))
    res["data_at"] = _iso(_parse_iso(facts.get("last_success_ts")))
    res["remote_host"] = meta.get("remote_host")
    if isinstance(facts.get("build"), str):
        res["version"] = facts["build"].strip()[:64]
    if isinstance(facts.get("x_dirty"), bool):
        res["x_dirty"] = facts["x_dirty"]
    kinds = meta.get("stale_kinds") or []
    if verdict == "STALE":
        res["stale_kind"] = "age" if kinds == ["timeout"] else "content"
    pid_state = meta.get("pid_state")
    if pid_state == "alive":
        res["liveness"] = "UP"
        res["pid"] = facts.get("pid")
        res["facts"].append(_fact("PID", facts.get("pid")))
        if meta.get("actual_start_ts"):
            res["pid_start_ts"] = _iso(_parse_iso(meta["actual_start_ts"]))
            res["facts"].append(_fact("行程啟動時間", res["pid_start_ts"]))
    elif pid_state == "dead":
        res["liveness"] = "PAUSED" if meta.get("paused") else "DOWN"
    return res


_RUNNERS: dict[str, Callable[[dict[str, Any], Any], dict[str, Any]]] = {
    "tcp": _probe_tcp,
    "process": _probe_process,
    "http": _probe_http,
    "win_task": _probe_win_task,
    "heartbeat": _probe_heartbeat,
}


class _Ctx:
    """跑一個服務的探針需要的東西；listeners、processes、win_task 整輪掃描只查一次。"""

    def __init__(self, scan: _Scan, project_root: Path | None, probe_layer: str) -> None:
        self.scan = scan
        self.system = scan.system
        self.now = scan.now
        self.home = scan.home
        self.wake_grace_remaining_s = scan.wake_grace_remaining_s
        self.project_root = project_root
        self.probe_layer = probe_layer

    def listeners(self) -> list[tuple[str, int, int]] | None:
        return self.scan.once("listeners", self.system.listeners)

    def processes(self) -> list[dict[str, Any]] | None:
        return self.scan.once("processes", self.system.processes)

    def win_task(self, name: str) -> dict[str, Any]:
        return self.scan.tasks.get(name) or {"found": False, "error": "沒有查到", "query_failed": True}


class _Scan:
    def __init__(self, *, system: System, now: datetime, home: Path, wake_grace_remaining_s: float) -> None:
        self.system = system
        self.now = now
        self.home = home
        self.wake_grace_remaining_s = max(0.0, float(wake_grace_remaining_s or 0.0))
        self.tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._memo: dict[str, Any] = {}
        self._memo_locks: dict[str, threading.Lock] = {}

    def once(self, key: str, fn: Callable[[], Any]) -> Any:
        with self._lock:
            lock = self._memo_locks.setdefault(key, threading.Lock())
        with lock:
            if key not in self._memo:
                try:
                    self._memo[key] = fn()
                except Exception:  # noqa: BLE001  查系統事實失敗只是沒資料，不讓整輪掛掉
                    self._memo[key] = None
            return self._memo[key]


def run_probe(probe: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    started = time.monotonic()
    try:
        if probe["type"] == "artifact":
            res = _probe_artifact_file(probe, ctx) if probe.get("glob") else _probe_artifact_sqlite(probe, ctx)
        else:
            res = _RUNNERS[probe["type"]](probe, ctx)
    except Exception as exc:  # noqa: BLE001  探針自己出錯不能當正常，也不能讓整輪掛掉
        res = _probe_base(probe, probe["type"])
        res.update(error=_short(f"{type(exc).__name__}: {exc}", 160), summary="探針執行失敗")
        if probe["type"] in ("artifact", "heartbeat"):
            res["output"] = "DOWN"
        else:
            res["liveness"] = "NO_DATA"
    res["duration_ms"] = int((time.monotonic() - started) * 1000)
    res.setdefault("checked_at", _iso(ctx.now))
    res["summary"] = _short(res.get("summary"), 220)
    return res


# ---------- Git 與建置輸出的事實 ----------

def _is_doc(rel: str, extra: list[str]) -> bool:
    rel = rel.replace("\\", "/")
    base = rel.rsplit("/", 1)[-1]
    for pat in (*DOC_PATTERNS, *extra):
        pat = pat.replace("\\", "/").replace("/**", "/*").replace("**/", "")
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(base, pat) or (pat.endswith("/*") and ("/" + rel).find("/" + pat[:-1]) >= 0):
            return True
    return False


def _pathspec_excludes(extra: list[str]) -> list[str]:
    specs: list[str] = []
    for pat in (*DOC_PATTERNS, *extra):
        pat = pat.replace("\\", "/")
        if pat.endswith(("/*", "/**")):
            stem = pat.rstrip("*").rstrip("/")
            specs.append(f":(exclude,glob){stem}/**")
            specs.append(f":(exclude,glob)**/{stem}/**")
        elif "/" in pat:
            specs.append(f":(exclude,glob){pat}")
        else:
            specs.append(f":(exclude,glob)**/{pat}")
    return specs


def git_facts(system: System, root: Path, sync_cfg: dict[str, Any]) -> dict[str, Any]:
    """專案的版本事實：HEAD、最後一次非文件 commit、晚於它的未提交改動。全部唯讀，不拿鎖。"""
    facts: dict[str, Any] = {"available": False}
    rc, out = system.git(root, ["rev-parse", "--is-inside-work-tree", "HEAD"])
    lines = out.split()
    if rc != 0 or len(lines) < 2 or lines[0] != "true":
        return facts
    facts.update(available=True, head=lines[1], head_short=lines[1][:7])
    ignore = list(sync_cfg.get("ignore") or [])
    paths = list(sync_cfg.get("paths") or []) or ["."]
    rc, out = system.git(root, ["log", "-1", "--format=%H%x1f%cI", "--", *paths, *_pathspec_excludes(ignore)])
    if rc == 0 and "\x1f" in out:
        sha, when = out.strip().split("\x1f", 1)
        facts.update(code_commit=sha, code_commit_short=sha[:7], code_commit_at=_iso(_parse_iso(when.strip())))
    if sync_cfg.get("check_worktree", True):
        rc, out = system.git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=no", "--", *paths])
        if rc == 0 and out:
            entries = out.split("\x00")
            newest: tuple[float, str] | None = None
            dirty = 0
            i = 0
            while i < len(entries) and dirty < 200:
                rec = entries[i]
                i += 1
                if len(rec) < 4:
                    continue
                code, rel = rec[:2], rec[3:]
                if code[0] in "RC":
                    i += 1   # 改名、複製的紀錄後面跟著舊路徑
                if _is_doc(rel, ignore):
                    continue
                dirty += 1
                try:
                    mt = (root / rel).stat().st_mtime
                except OSError:
                    continue
                if newest is None or mt > newest[0]:
                    newest = (mt, rel)
            facts["dirty_code_files"] = dirty
            if newest is not None:
                facts.update(dirty_latest_at=_iso(datetime.fromtimestamp(newest[0], UTC)), dirty_latest_file=newest[1])
    return facts


def _newest_mtime(root: Path) -> tuple[float, str] | None:
    newest: tuple[float, str] | None = None
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            seen += 1
            if seen > DIR_SCAN_MAX_FILES:
                return newest
            full = os.path.join(dirpath, name)
            try:
                mt = os.stat(full).st_mtime
            except OSError:
                continue
            if newest is None or mt > newest[0]:
                newest = (mt, os.path.relpath(full, root))
    return newest


# ---------- 三軸判定 ----------

def in_active_window(svc: dict[str, Any], now: datetime) -> tuple[bool, str]:
    days, hours = svc.get("active_days") or [], svc.get("active_hours") or []
    if not days and not hours:
        return True, ""
    tz, note = tz_for(svc.get("timezone"))
    local = now.astimezone(tz)
    minute = local.hour * 60 + local.minute
    day_ok = not days or local.weekday() in days
    hour_ok = not hours or any((s <= minute < e) if s < e else (minute >= s or minute < e) for s, e in hours)
    return day_ok and hour_ok, note


def _axis_alive(probes: list[dict[str, Any]], *, active: bool, wake: float) -> dict[str, Any]:
    live = [p for p in probes if p["liveness"] is not None]
    outs = [p for p in probes if p["output"] is not None]
    reason = ""
    if live:
        states = [p["liveness"] for p in live]
        decided = [s for s in states if s != "NO_DATA"]
        if not decided:
            state = "NO_DATA"
            reason = "；".join(p["summary"] for p in live[:2])
        elif all(s == "DOWN" for s in decided):
            state = "DOWN"
        elif any(s in ("DOWN", "DEGRADED") for s in decided):
            state = "DEGRADED"
        elif all(s == "PAUSED" for s in decided):
            state = "PAUSED"
        else:
            state = "UP"
        bad = [p for p in live if p["liveness"] in ("DOWN", "DEGRADED")]
        if bad:
            reason = "；".join(f"{p['label']}：{p['summary']}" for p in bad[:3])
        elif state == "UP":
            reason = "；".join(p["summary"] for p in live[:2])
        elif state == "PAUSED":
            reason = "預期暫停中"
        if state == "DOWN" and wake > 0 and all(p["timed_out"] for p in bad):
            state, reason = "PAUSED", f"剛自休眠喚醒（還有 {int(wake)} 秒緩衝）：{reason}"
    else:
        # 沒有存活類探針（例如只看產出檔的排程工作）：有新鮮產出就當它有在跑，否則沒有存活證據
        if any(p["output"] == "FRESH" for p in outs):
            state, reason = "UP", "沒有存活探針；由新鮮產出推定有在跑"
        elif outs and all(p["output"] == "PAUSED" for p in outs):
            state, reason = "PAUSED", "預期暫停中"
        else:
            state, reason = "NO_DATA", "沒有存活證據（只有產出類探針，而且產出不新鮮）"
    if state in ("DOWN", "DEGRADED") and not active:
        state, reason = "PAUSED", f"非運作時段：{reason}"
    proof = None
    if state in ("UP", "DEGRADED"):
        proven = any(p["output"] == "FRESH" for p in outs) or any(p["content_verified"] for p in live)
        proof = "output_verified" if proven else "liveness_only"
    facts: list[dict[str, str]] = []
    for p in live:
        facts += p["facts"]
    return {"state": state, "proof_level": proof, "reason": _short(reason, 240), "facts": facts[:12],
            "sources": [p["label"] for p in (live or outs)][:MAX_PROBES]}


def _axis_fresh(probes: list[dict[str, Any]], *, active: bool, wake: float) -> dict[str, Any]:
    outs = [p for p in probes if p["output"] is not None]
    if not outs:
        only_tasks = bool(probes) and all(p["type"] == "win_task" for p in probes)
        return {"state": "N/A", "reason": "只有排程探針，沒有產出證據" if only_tasks else "沒有設定產出或心跳探針",
                "facts": [], "sources": [], "data_at": None}
    state = max((p["output"] for p in outs), key=lambda s: _OUT_ORDER.get(s, 0))
    worst = [p for p in outs if p["output"] == state]
    reason = "；".join(f"{p['label']}：{p['summary']}" for p in worst[:3])
    if state == "STALE" and all(p["stale_kind"] == "age" for p in worst):
        if wake > 0:
            state, reason = "PAUSED", f"剛自休眠喚醒（還有 {int(wake)} 秒緩衝）：{reason}"
        elif not active:
            state, reason = "PAUSED", f"非運作時段：{reason}"
    elif state == "DOWN" and wake > 0 and all(p["timed_out"] for p in worst):
        state, reason = "PAUSED", f"剛自休眠喚醒（還有 {int(wake)} 秒緩衝）：{reason}"
    facts: list[dict[str, str]] = []
    for p in outs:
        facts += p["facts"]
    times = sorted(t for t in (p.get("data_at") for p in outs) if t)
    return {"state": state, "reason": _short(reason, 240), "facts": facts[:12], "sources": [p["label"] for p in outs][:MAX_PROBES],
            "data_at": times[0] if times else None}


def _version_matches(system: System, root: Path, reported: str, git: dict[str, Any]) -> bool | None:
    """回報的版本是不是目前的碼。True 相符、False 不符、None 沒辦法比（不是 commit SHA）。"""
    rep = reported.strip().lower()
    if not HEX_RE.match(rep):
        return None
    for key in ("head", "code_commit"):
        full = str(git.get(key) or "").lower()
        if full and (full.startswith(rep) or rep.startswith(full)):
            return True
    # HEAD 之後只多了文件 commit 也算同步：回報的版本要在「最後一次非文件 commit」之後（含）
    code = git.get("code_commit")
    if code:
        rc, _ = system.git(root, ["merge-base", "--is-ancestor", str(code), rep])
        if rc == 0:
            return True
    return False


def _axis_sync(svc: dict[str, Any], probes: list[dict[str, Any]], ctx: _Ctx) -> dict[str, Any]:
    sync_cfg = svc.get("sync") or {}
    if sync_cfg.get("enabled") is False:
        return {"state": "N/A", "reason": "這個服務關掉了版本比對", "facts": [], "sources": []}
    starts = sorted(t for t in (p.get("pid_start_ts") for p in probes) if t)
    versions = [(p["label"], p["version"]) for p in probes if p.get("version")]
    remote = next((p["remote_host"] for p in probes if p.get("remote_host")), None)
    dirty_flag = any(p.get("x_dirty") is True for p in probes)
    has_dirs = bool(sync_cfg.get("src_dir") and sync_cfg.get("build_dir"))
    facts: list[dict[str, str]] = []
    drift: list[str] = []
    compared: list[str] = []
    root = ctx.project_root

    if remote:
        facts.append(_fact("主機", remote))
        if dirty_flag:
            return {"state": "DIRTY", "reason": f"遠端主機 {remote} 自報工作樹有未提交改動", "facts": facts, "sources": []}
        return {"state": "NO_DATA", "reason": f"服務在遠端主機 {remote}，這台沒辦法比對版本", "facts": facts, "sources": []}
    if not starts and not versions and not has_dirs:
        if dirty_flag:
            return {"state": "DIRTY", "reason": "心跳自報執行工作樹含未提交改動（x_dirty）", "facts": facts, "sources": []}
        return {"state": "N/A", "reason": "沒有行程啟動時間、回報版本或建置目錄可以比對", "facts": [], "sources": []}

    git: dict[str, Any] = {"available": False}
    if root is not None and (starts or versions):
        git = ctx.scan.once(f"git:{root}:{json.dumps(sync_cfg, sort_keys=True, ensure_ascii=False)}",
                            lambda: git_facts(ctx.system, root, sync_cfg)) or {"available": False}
    if git.get("available"):
        facts.append(_fact("HEAD", git["head_short"]))
        if git.get("code_commit_at"):
            facts.append(_fact("最後一次非文件 commit", f"{git['code_commit_short']}（{git['code_commit_at']}）"))
    if starts:
        start_dt = _parse_iso(starts[0])
        facts.append(_fact("行程啟動時間", starts[0]))
        commit_dt = _parse_iso(git.get("code_commit_at"))
        if start_dt and commit_dt:
            compared.append("行程啟動時間對 commit")
            if start_dt < commit_dt:
                drift.append(f"行程啟動（{starts[0]}）早於最後一次非文件 commit {git['code_commit_short']}（{git['code_commit_at']}）：改碼後沒有重啟")
        dirty_dt = _parse_iso(git.get("dirty_latest_at"))
        if start_dt and dirty_dt:
            facts.append(_fact("未提交改動（最新）", f"{git.get('dirty_latest_file')}（{git['dirty_latest_at']}）"))
            if start_dt < dirty_dt:
                drift.append(f"未提交改動 {git.get('dirty_latest_file')}（{git['dirty_latest_at']}）晚於行程啟動：改碼後沒有重啟")
    for label, ver in versions:
        facts.append(_fact("回報版本", ver))
        if not git.get("available") or root is None:
            continue
        match = _version_matches(ctx.system, root, ver, git)
        if match is None:
            facts.append(_fact("版本比對", f"{ver} 不是 commit SHA，無法跟 HEAD 比"))
            continue
        compared.append("回報版本對 HEAD")
        if not match:
            drift.append(f"{label} 回報版本 {ver[:12]}，目前 HEAD 是 {git['head_short']}：跑的不是最新的碼")
    if has_dirs:
        try:
            layer = svc.get("_sync_layer", "project")
            src = resolve_local_path(sync_cfg["src_dir"], project_root=root, home=ctx.home, layer=layer)
            build = resolve_local_path(sync_cfg["build_dir"], project_root=root, home=ctx.home, layer=layer)
            newest_src = _newest_mtime(src) if src.is_dir() else None
            newest_build = _newest_mtime(build) if build.is_dir() else None
            if newest_src is None:
                facts.append(_fact("建置比對", "找不到原始碼目錄或裡面沒有檔案"))
            elif newest_build is None:
                compared.append("建置輸出對原始碼")
                drift.append("建置輸出目錄不存在或是空的：還沒建置")
            else:
                compared.append("建置輸出對原始碼")
                src_at, build_at = (_iso(datetime.fromtimestamp(t[0], UTC)) for t in (newest_src, newest_build))
                facts += [_fact("原始碼最新檔", f"{newest_src[1]}（{src_at}）"), _fact("建置輸出最新檔", f"{newest_build[1]}（{build_at}）")]
                if newest_build[0] < newest_src[0]:
                    drift.append(f"建置輸出（{build_at}）比原始碼 {newest_src[1]}（{src_at}）舊：改碼後沒有重建")
        except ValueError as exc:
            facts.append(_fact("建置比對", str(exc)))

    if drift:
        return {"state": "DRIFT", "reason": _short("；".join(drift), 320), "facts": facts[:12], "sources": compared}
    if dirty_flag:
        return {"state": "DIRTY", "reason": "心跳自報執行工作樹含未提交改動（x_dirty）", "facts": facts[:12], "sources": compared}
    if compared:
        return {"state": "SYNCED", "reason": "、".join(dict.fromkeys(compared)) + "：一致", "facts": facts[:12], "sources": compared}
    why = "這台沒有專案目錄或不是 Git 儲存庫" if not git.get("available") else "沒有可比對的版本來源"
    return {"state": "NO_DATA", "reason": f"{why}，無法判斷版本", "facts": facts[:12], "sources": []}


def _level(alive: str, sync: str, fresh: str) -> str:
    if alive == "DOWN" or fresh in ("DOWN", "STALE"):
        return "bad"
    if alive == "DEGRADED" or sync == "DRIFT":
        return "warn"
    return "ok" if alive == "UP" else "idle"


def evaluate_service(project_id: str, svc: dict[str, Any], ctx: _Ctx, pool: ThreadPoolExecutor | None = None) -> dict[str, Any]:
    probes_cfg = svc.get("probes") or []
    if pool is not None and len(probes_cfg) > 1:
        results = list(pool.map(lambda p: run_probe(p, ctx), probes_cfg))
    else:
        results = [run_probe(p, ctx) for p in probes_cfg]
    active, tz_note = in_active_window(svc, ctx.now)
    alive = _axis_alive(results, active=active, wake=ctx.wake_grace_remaining_s)
    fresh = _axis_fresh(results, active=active, wake=ctx.wake_grace_remaining_s)
    try:
        sync = _axis_sync(svc, results, ctx)
    except Exception as exc:  # noqa: BLE001  版本比對失敗只是沒資料
        sync = {"state": "NO_DATA", "reason": _short(f"版本比對失敗：{exc}", 160), "facts": [], "sources": []}
    level = _level(alive["state"], sync["state"], fresh["state"])
    fingerprint = None
    if level in ("bad", "warn"):
        sig = f"{project_id.lower()}|{svc['id'].lower()}|{alive['state']}|{sync['state']}|{fresh['state']}"
        fingerprint = hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]
    ack = svc.get("acknowledged_until")
    ack_dt = _parse_iso(ack)
    checked = sorted(t for t in (p.get("checked_at") for p in results) if t)
    return {
        "id": svc["id"],
        "name": svc.get("name") or svc["id"],
        "source": svc.get("_source", "personal"),
        "level": level,
        "fingerprint": fingerprint,
        "acknowledged_until": ack if ack_dt else None,
        "acknowledged": bool(ack_dt and ack_dt > ctx.now),
        "active": active,
        "note": tz_note or svc.get("note") or "",
        "alive": alive,
        "sync": sync,
        "fresh": fresh,
        "probes": [{"type": p["type"], "label": _short(p["label"], 80), "summary": p["summary"], "error": p.get("error"),
                    "liveness": p["liveness"], "output": p["output"], "duration_ms": p["duration_ms"],
                    "checked_at": p["checked_at"], "facts": p["facts"][:8]} for p in results],
        "checked_at": checked[0] if checked else _iso(ctx.now),
    }


def _alert_text(svc: dict[str, Any]) -> str:
    parts: list[str] = []
    if svc["alive"]["state"] in ("DOWN", "DEGRADED"):
        parts.append(f"活著嗎 {svc['alive']['state']}")
    if svc["sync"]["state"] == "DRIFT":
        parts.append("版本 DRIFT")
    if svc["fresh"]["state"] in ("DOWN", "STALE"):
        parts.append(f"資料 {svc['fresh']['state']}")
    return "、".join(parts)


def scan_all(
    state_dir: Path,
    *,
    entries: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
    home: Path | None = None,
    now: datetime | None = None,
    system: System | None = None,
    wake_grace_remaining_s: float = 0.0,
    default_repo_root: Path | None = collector.ROOT,
    force: bool = False,
    only_project: str | None = None,
) -> dict[str, Any]:
    """掃一輪所有專案的探針，回傳三軸運行態快照（大小只跟設定的服務數有關，不會越長越大）。"""
    t0 = time.monotonic()
    cfg = cfg if cfg is not None else collector.load_config(state_dir)
    ref_now = collector.utc_now(now)
    system = system or System()
    scan = _Scan(system=system, now=ref_now, home=home or Path.home(), wake_grace_remaining_s=wake_grace_remaining_s)
    if entries is None:
        entries = collector.discover_projects(state_dir, cfg, default_repo_root=default_repo_root)

    plans: list[tuple[dict[str, Any], Path | None, list[dict[str, Any]], list[str], dict[str, int]]] = []
    for entry in entries:
        pid = str(entry.get("id") or "")
        if not pid or (only_project and pid.lower() != only_project.lower()):
            continue
        raw_path = str(entry.get("path") or "")
        root = Path(raw_path) if raw_path else None
        if root is not None and not root.is_dir():
            root = None
        services, errors, layers = merged_services(pid, root, cfg)
        if services or errors:
            plans.append((entry, root, services, errors, layers))

    task_names = sorted({p["name"] for _e, _r, services, _er, _l in plans for s in services for p in s["probes"] if p["type"] == "win_task"})
    if task_names:
        try:
            scan.tasks = system.win_tasks(task_names, force=force)
        except Exception:  # noqa: BLE001
            scan.tasks = {}

    projects: dict[str, Any] = {}
    alerts: list[dict[str, Any]] = []
    counts = {"ok": 0, "warn": 0, "bad": 0, "idle": 0}
    proven = hollow = 0
    checked_all: list[str] = []
    jobs = [(entry, root, svc) for entry, root, services, _er, _l in plans for svc in services]
    with ThreadPoolExecutor(max_workers=max(4, min(16, len(jobs) * 2 or 4))) as pool:
        def run(job: tuple[dict[str, Any], Path | None, dict[str, Any]]) -> dict[str, Any]:
            entry, root, svc = job
            return evaluate_service(str(entry["id"]), svc, _Ctx(scan, root, svc.get("_probe_layer", "personal")), pool)

        evaluated = list(pool.map(run, jobs)) if jobs else []
    by_job = iter(evaluated)
    for entry, root, services, errors, layers in plans:
        pid = str(entry["id"])
        done = [next(by_job) for _ in services]
        worst = "idle"
        for svc in done:
            counts[svc["level"]] += 1
            checked_all.append(svc["checked_at"])
            if svc["alive"]["state"] in ("UP", "DEGRADED"):
                if svc["alive"]["proof_level"] == "output_verified":
                    proven += 1
                else:
                    hollow += 1
            if svc["level"] in ("bad", "warn"):
                alerts.append({"project_id": pid, "project_name": entry.get("name") or pid, "service_id": svc["id"],
                               "service_name": svc["name"], "level": svc["level"], "text": _alert_text(svc),
                               "fingerprint": svc["fingerprint"], "acknowledged": svc["acknowledged"]})
        for lvl in ("bad", "warn", "ok"):
            if any(s["level"] == lvl for s in done):
                worst = lvl
                break
        projects[pid] = {"id": pid, "name": entry.get("name") or pid, "level": worst if done else "idle", "services": done,
                         "config_errors": errors[:10], "layers": layers, "local_available": root is not None}

    alerts.sort(key=lambda a: (0 if a["level"] == "bad" else 1, a["project_name"].lower(), a["service_name"].lower()))
    checked_all.sort()
    return {
        "generated_at": _iso(ref_now),
        "generated_local": collector.fmt_local_time(ref_now),
        "host": socket.gethostname(),
        "scan_ms": int((time.monotonic() - t0) * 1000),
        "wake_grace_active": scan.wake_grace_remaining_s > 0,
        "wake_grace_remaining_s": int(scan.wake_grace_remaining_s),
        "summary": {
            "services": sum(counts.values()),
            "ok": counts["ok"],
            "warn": counts["warn"],
            "bad": counts["bad"],
            "idle": counts["idle"],
            "output_verified": proven,
            "liveness_only": hollow,
            "projects": len(projects),
            "oldest_evidence_at": checked_all[0] if checked_all else None,
        },
        "alerts": alerts[:50],
        "projects": projects,
    }


def runtime_meta(runtime: dict[str, Any] | None) -> dict[str, Any] | None:
    """快照去掉各專案明細後的摘要（放在 overview 最外層；明細掛在各專案底下）。"""
    if not runtime:
        return None
    return {k: v for k, v in runtime.items() if k != "projects"}


# ---------- 個人疊層的寫入（只給本機 API 用） ----------

def _personal_services(cfg: dict[str, Any], project_id: str) -> list[dict[str, Any]]:
    errors: list[str] = []
    return _norm_list(personal_layer_raw(cfg, project_id), partial=True, errors=errors, where="個人設定")


def _clean(svc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in svc.items() if not k.startswith("_")}


def describe_layers(state_dir: Path, project_id: str, project_root: Path | None) -> dict[str, Any]:
    cfg = collector.load_config(state_dir)
    errors: list[str] = []
    project = read_project_layer(project_root, errors)
    personal_errors: list[str] = []
    personal = _norm_list(personal_layer_raw(cfg, project_id), partial=True, errors=personal_errors, where="個人設定")
    merged, _all_errors, _layers = merged_services(project_id, project_root, cfg)
    return {
        "project_id": project_id,
        "project_file": str(project_root / PROJECT_FILE) if project_root is not None else None,
        "project_services": project,
        "personal_services": personal,
        "merged": [{**_clean(s), "source": s["_source"]} for s in merged],
        "errors": [*errors, *personal_errors],
    }


def apply_probe_op(state_dir: Path, project_id: str, body: dict[str, Any], *, project_root: Path | None, home: Path | None = None) -> dict[str, Any]:
    """更新某個專案的個人疊層探針設定（寫進 ~/.omnikit/cockpit/config.json，不碰專案的 Git）。

    op：add_probe（在服務上加一個探針，沒有這個服務就建立）、upsert（整個服務換掉）、set_enabled、remove、replace（整份換掉）。
    """
    pid = collector.validate_project_id(project_id)
    if not isinstance(body, dict):
        raise TypeError("請求內容要是物件")
    op = str(body.get("op") or ("replace" if "services" in body else "upsert" if "service" in body else "")).strip()
    cfg = collector.load_config(state_dir)
    current = _personal_services(cfg, pid)
    by_id = {s["id"].lower(): s for s in current}
    project_ids = {s["id"].lower() for s in read_project_layer(project_root, [])}
    home = home or Path.home()

    def check_paths(svc: dict[str, Any]) -> None:
        for p in svc.get("probes") or []:
            for key in ("glob", "sqlite_path", "path"):
                if p.get(key):
                    resolve_local_path(p[key], project_root=project_root, home=home, layer="personal")
        for key in ("src_dir", "build_dir"):
            if (svc.get("sync") or {}).get(key):
                resolve_local_path(svc["sync"][key], project_root=project_root, home=home, layer="personal")

    if op == "replace":
        raw = body.get("services")
        if not isinstance(raw, list) or len(raw) > MAX_SERVICES:
            raise ValueError(f"services 要是清單，最多 {MAX_SERVICES} 個")
        new = [normalize_service(s, partial=str((s or {}).get("id") or "").lower() in project_ids if isinstance(s, dict) else False)
               for s in raw]
        if len({s["id"].lower() for s in new}) != len(new):
            raise ValueError("服務 id 不可重複")
        for s in new:
            check_paths(s)
        current = new
    elif op == "upsert":
        raw = body.get("service")
        partial = isinstance(raw, dict) and str(raw.get("id") or "").lower() in project_ids
        svc = normalize_service(raw, partial=partial)
        check_paths(svc)
        by_id[svc["id"].lower()] = svc
        current = list(by_id.values())
    elif op == "add_probe":
        raw_svc = body.get("service") if isinstance(body.get("service"), dict) else {}
        name = str(raw_svc.get("name") or "").strip()[:60]
        sid = str(raw_svc.get("id") or "").strip() or (_slug_id(name) if name else "")
        if not SERVICE_ID_RE.match(sid):
            raise ValueError("請填服務名稱")
        probe = _norm_probe(body.get("probe"))
        base = dict(by_id.get(sid.lower()) or {"id": sid})
        if name:
            base["name"] = name
        probes = list(base.get("probes") or [])
        if len(probes) >= MAX_PROBES:
            raise ValueError(f"一個服務最多 {MAX_PROBES} 個探針")
        probes.append(probe)
        extra = {k: raw_svc[k] for k in ("sync", "active_days", "active_hours", "timezone") if raw_svc.get(k) not in (None, "", [])}
        svc = normalize_service({**_clean(base), **extra, "probes": probes, "enabled": True})
        check_paths(svc)
        by_id[sid.lower()] = svc
        current = list(by_id.values())
    elif op == "set_enabled":
        sid = str(body.get("service_id") or "").strip()
        if not SERVICE_ID_RE.match(sid):
            raise ValueError("service_id 不合法")
        base = dict(by_id.get(sid.lower()) or {"id": sid})
        if sid.lower() not in by_id and sid.lower() not in project_ids:
            raise FileNotFoundError(f"找不到服務：{sid}")
        base["enabled"] = bool(body.get("enabled"))
        by_id[sid.lower()] = base
        current = list(by_id.values())
    elif op == "remove":
        sid = str(body.get("service_id") or "").strip().lower()
        if sid not in by_id:
            raise FileNotFoundError(f"個人設定裡沒有這個服務：{sid}")
        by_id.pop(sid)
        current = list(by_id.values())
    else:
        raise ValueError("op 要是 add_probe、upsert、set_enabled、remove 或 replace")

    if len(current) > MAX_SERVICES:
        raise ValueError(f"一個專案最多 {MAX_SERVICES} 個服務")
    table = dict(cfg.get("probes")) if isinstance(cfg.get("probes"), dict) else {}
    for key in [k for k in table if str(k).lower() == pid.lower()]:
        table.pop(key)
    if current:
        table[pid] = {"services": [_clean(s) for s in current]}
    cfg["probes"] = table
    collector.save_config(state_dir, cfg)
    return {"ok": True, "project_id": pid, "personal_services": [_clean(s) for s in current]}
