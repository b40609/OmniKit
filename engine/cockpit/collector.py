"""OmniKit 個人面板核心採集與對帳引擎。

職責：
1. 專案探索（本機設定 ∪ ~/.omnikit/status/* 聯集，原生支援單機與多機專案）。
2. 三源自動對帳：本地 Git 實體狀態 ＋ `t3 thread list --json`（絕不讀 statev2.sqlite）＋ 私人 NOW.md 四格契約。
3. 球權分流（blocked_on_me / ready_to_settle / active / parked）與過期／超載紅燈偵測。
4. NOW.md「不滿意待改（Critique Delta）」無損新增與勾銷寫回（保留原對帳時間不洗掉過期紅燈）。
5. 個人疊層讀取：整合既有工具名冊（含私有模組與個人 profile 屏蔽模型）與多帳號額度（account_pool）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "engine" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import statedir  # type: ignore
except ImportError:
    statedir = None

try:
    from fsretry import retry as fs_retry  # type: ignore
except ImportError:
    def fs_retry(fn, *args, **kwargs):
        return fn(*args, **kwargs)


SAFE_PROJECT_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bya29\.[A-Za-z0-9._-]{10,}"),
    re.compile(r'(?i)(refresh_token|access_token|api_key|password|secret)["\']?\s*[:=]\s*["\']?[^\s"\',}]{6,}'),
)

DEFAULT_CONFIG: dict[str, Any] = {
    "t3_base_url": "",
    "parked_days": 3,
    "overload_items": 1000,
    "auto_commit_status": True,
    "auto_push_status": False,
    "projects": [],
}

LANE_META = {
    "blocked_on_me": {"label": "卡在你身上", "short": "等你", "order": 0},
    "ready_to_settle": {"label": "跑完待收尾／需對帳", "short": "待收尾", "order": 1},
    "active": {"label": "執行中／隨時可推進", "short": "執行中", "order": 2},
    "parked": {"label": "已停泊", "short": "停泊", "order": 3},
}

EMPTY_PLACEHOLDERS = {"無", "目前無", "沒有", "暫無", "無。", "none", "n/a", "-", "（無）", "(無)"}
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s*\[([ xX])\]\s*(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
PROGRESS_ZH_RE = re.compile(r"還有\s*(\d+)\s*步[^0-9]*完成\s*(\d+)\s*步")
PROGRESS_ZH_REV_RE = re.compile(r"完成\s*(\d+)\s*[/／]\s*(\d+)\s*步?")
PROGRESS_FRAC_RE = re.compile(r"(?:\[|\b)(\d+)\s*/\s*(\d+)(?:\s*步)?(?:\]|\b)")
TS_ISO_RE = re.compile(r"(\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)")


def sanitize(text: Any, limit: int = 240) -> str:
    """遮罩疑似金鑰並壓成安全字串。"""
    s = " ".join(str(text or "").split())
    for pat in SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    return s[:limit] + ("…" if len(s) > limit else "")


def default_state_dir() -> Path:
    if statedir is not None:
        return statedir.state_dir()
    env_dir = os.environ.get("OMNIKIT_STATE_DIR")
    return Path(env_dir) if env_dir else Path.home() / ".omnikit"


def utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return utc_now(dt).isoformat(timespec="seconds")


def parse_timestamp(raw: str | None) -> datetime | None:
    """寬鬆解析 ISO8601、YYYY-MM-DD HH:MM 或 YYYY-MM-DD（無時區時當成當地時間）。"""
    if not raw:
        return None
    m = TS_ISO_RE.search(str(raw).strip())
    if not m:
        return None
    token = m.group(1).strip().replace(" ", "T")
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    elif re.search(r"[+-]\d{4}$", token):
        token = token[:-2] + ":" + token[-2:]
    try:
        dt = datetime.fromisoformat(token)
    except ValueError:
        return None
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or UTC
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(UTC)


def fmt_local_time(dt: datetime | None) -> str:
    if dt is None:
        return "未知"
    return utc_now(dt).astimezone().strftime("%m-%d %H:%M")


def fmt_age(dt: datetime | None, now: datetime | None = None) -> str:
    if dt is None:
        return "無紀錄"
    ref = utc_now(now)
    diff = int((ref - utc_now(dt)).total_seconds())
    if diff < 60:
        return "剛剛"
    mins = diff // 60
    if mins < 60:
        return f"{mins} 分鐘前"
    hours = mins // 60
    if hours < 24:
        return f"{hours} 小時前"
    days = hours // 24
    return f"{days} 天前"


def _run_cmd(args: list[str], cwd: Path | None = None, timeout: int = 8) -> tuple[int, str, str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if cwd is not None:
        kwargs["cwd"] = str(cwd)
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if args and args[0] == "git" and "core.longpaths=true" not in args:
            args = ["git", "-c", "core.longpaths=true", *args[1:]]
    try:
        proc = subprocess.run(args, check=False, **kwargs)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", sanitize(exc)


def read_utf8(path: Path) -> str:
    return fs_retry(path.read_bytes).decode("utf-8-sig")


def write_utf8_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.replace("\r\n", "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=".omnikit-tmp-", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        fs_retry(os.replace, tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------- 設定與安全路徑 ----------

def cockpit_dir(state_dir: Path) -> Path:
    return state_dir / "cockpit"


def config_path(state_dir: Path) -> Path:
    return cockpit_dir(state_dir) / "config.json"


def status_repo_dir(state_dir: Path) -> Path:
    return state_dir / "status"


def validate_project_id(project_id: str) -> str:
    pid = str(project_id or "").strip()
    if not pid or pid in (".", "..") or not SAFE_PROJECT_ID.match(pid):
        raise ValueError("專案代號只允許英數字、點、底線與連字號")
    return pid


def safe_status_now_path(state_dir: Path, project_id: str) -> Path:
    pid = validate_project_id(project_id)
    base = status_repo_dir(state_dir).resolve()
    target = (base / pid / "NOW.md").resolve()
    if base not in target.parents:
        raise ValueError("不合法的專案路徑")
    return target


def load_config(state_dir: Path) -> dict[str, Any]:
    path = config_path(state_dir)
    doc: dict[str, Any] = {}
    if path.is_file():
        try:
            parsed = json.loads(read_utf8(path))
            if isinstance(parsed, dict):
                doc = parsed
        except (OSError, ValueError):
            doc = {}
    merged = {**DEFAULT_CONFIG, **doc}
    if not isinstance(merged.get("projects"), list):
        merged["projects"] = []
    merged["parked_days"] = max(1, min(60, int(merged.get("parked_days") or 3)))
    merged["overload_items"] = max(100, min(10000, int(merged.get("overload_items") or 1000)))
    merged["t3_base_url"] = str(merged.get("t3_base_url") or "").strip().rstrip("/")
    merged["auto_commit_status"] = bool(merged.get("auto_commit_status", True))
    merged["auto_push_status"] = bool(merged.get("auto_push_status", False))
    return merged


def save_config(state_dir: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "t3_base_url": str(cfg.get("t3_base_url") or "").strip().rstrip("/"),
        "parked_days": max(1, min(60, int(cfg.get("parked_days") or 3))),
        "overload_items": max(100, min(10000, int(cfg.get("overload_items") or 1000))),
        "auto_commit_status": bool(cfg.get("auto_commit_status", True)),
        "auto_push_status": bool(cfg.get("auto_push_status", False)),
        "projects": list(cfg.get("projects") or []),
    }
    write_utf8_atomic(config_path(state_dir), json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
    return normalized


def update_settings(state_dir: Path, patch: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config(state_dir)
    if "t3_base_url" in patch:
        url = str(patch["t3_base_url"] or "").strip().rstrip("/")
        if url:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("t3_base_url 必須是有效的 http:// 或 https:// 網址")
        cfg["t3_base_url"] = url
    if "parked_days" in patch:
        cfg["parked_days"] = max(1, min(60, int(patch["parked_days"])))
    if "overload_items" in patch:
        cfg["overload_items"] = max(100, min(10000, int(patch["overload_items"])))
    if "auto_commit_status" in patch:
        cfg["auto_commit_status"] = bool(patch["auto_commit_status"])
    if "auto_push_status" in patch:
        cfg["auto_push_status"] = bool(patch["auto_push_status"])
    return save_config(state_dir, cfg)


def register_project(
    state_dir: Path,
    *,
    name: str,
    path: str | None = None,
    project_id: str | None = None,
    parked: bool | None = None,
    remove: bool = False,
) -> dict[str, Any]:
    """在 ~/.omnikit/cockpit/config.json 登記、更新或移除專案設定。"""
    cfg = load_config(state_dir)
    raw_id = project_id or re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-")
    pid = validate_project_id(raw_id)
    projects = [p for p in cfg["projects"] if isinstance(p, dict)]
    existing_idx = next((i for i, p in enumerate(projects) if str(p.get("id", "")).lower() == pid.lower()), None)
    if remove:
        if existing_idx is not None:
            projects.pop(existing_idx)
        cfg["projects"] = projects
        save_config(state_dir, cfg)
        return {"id": pid, "removed": True}

    entry = dict(projects[existing_idx]) if existing_idx is not None else {"id": pid}
    entry["id"] = pid
    if name.strip():
        entry["name"] = name.strip()
    elif "name" not in entry:
        entry["name"] = pid
    if path is not None:
        entry["path"] = str(path).strip()
    if parked is not None:
        entry["parked"] = bool(parked)
    if existing_idx is not None:
        projects[existing_idx] = entry
    else:
        projects.append(entry)
    cfg["projects"] = projects
    save_config(state_dir, cfg)
    return entry


# ---------- NOW.md 解析與無損寫回 ----------

def _clean_line_value(raw: str) -> str:
    s = raw.strip()
    if s.startswith("`") and s.endswith("`") and len(s) >= 2:
        s = s[1:-1].strip()
    return s


def _strip_md_inline(raw: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", raw)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s.strip()


def _is_empty_item(text: str) -> bool:
    t = _strip_md_inline(text).strip().lower()
    return not t or t in EMPTY_PLACEHOLDERS


def _classify_section(title: str) -> str | None:
    t = title.strip().lower()
    if any(k in t for k in ("不滿意", "驗收差距", "critique", "待改")):
        return "critiques"
    if any(k in t for k in ("完工路徑", "里程碑", "roadmap", "完成度", "進度")):
        return "roadmap"
    if any(k in t for k in ("目前結論", "現行定案", "已定案", "現行結論", "結論")):
        return "conclusions"
    if any(k in t for k in ("等使用者", "等你決定", "待拍板", "等待決定", "需你決定")):
        return "decisions"
    if any(k in t for k in ("下一步", "next action", "next step")):
        return "next_actions"
    if any(k in t for k in ("進行中", "活躍", "active lane")):
        return "active_lines"
    return None


def _parse_critique_item(index: int, done: bool, text: str) -> dict[str, Any]:
    clean = text.strip()
    parts = [p.strip() for p in re.split(r"\s*(?:->|→)\s*", clean) if p.strip()]
    item: dict[str, Any] = {
        "index": index,
        "done": done,
        "text": clean,
        "symptom": "",
        "pain": "",
        "criteria": "",
    }
    if len(parts) >= 3:
        item["symptom"] = parts[0]
        item["pain"] = parts[1]
        item["criteria"] = " -> ".join(parts[2:])
    elif len(parts) == 2:
        item["pain"] = parts[0]
        item["criteria"] = parts[1]
    return item


def _parse_owner(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("等使用者", "等你決定", "等你驗收", "待拍板", "需使用者", "人工")):
        return "user"
    if any(k in low for k in ("agent 可直接", "可直接做", "可直接跑", "自動執行", "agent")):
        return "agent"
    return "unassigned"


def parse_now_md(text: str | None, mtime: datetime | None = None) -> dict[str, Any]:
    """寬鬆解析 NOW.md 成結構化 4 格契約，完整向下相容舊格式。"""
    if not text:
        return {
            "exists": False,
            "updated_at": None,
            "updated_source": "none",
            "project_path": "",
            "branch": "",
            "main_thread": "",
            "progress": {"done": None, "total": None, "slope": "unknown", "summary": "", "steps": []},
            "conclusions": [],
            "critiques": [],
            "decisions": [],
            "next_actions": [],
            "active_lines": [],
            "next_action": None,
            "raw_excerpt": "",
        }

    lines = text.replace("\r\n", "\n").splitlines()
    meta_updated: datetime | None = None
    project_path = ""
    branch = ""
    main_thread = ""

    sections: dict[str, list[str]] = {
        "roadmap": [],
        "conclusions": [],
        "critiques": [],
        "decisions": [],
        "next_actions": [],
        "active_lines": [],
    }
    current_sec: str | None = None

    for line in lines:
        hm = HEADING_RE.match(line)
        if hm:
            current_sec = _classify_section(hm.group(2))
            continue

        if current_sec is None:
            stripped = _strip_md_inline(line).lstrip("-* ").strip()
            for key_pat, field in (
                (r"^(?:更新時間|最後更新|updated)\s*[:：]\s*(.+)$", "updated"),
                (r"^(?:專案路徑|本機路徑|路徑|workspace|path)\s*[:：]\s*(.+)$", "path"),
                (r"^(?:分支|branch)\s*[:：]\s*(.+)$", "branch"),
                (r"^(?:主線對話|主線|main thread)\s*[:：]\s*(.+)$", "main_thread"),
            ):
                mm = re.match(key_pat, stripped, flags=re.IGNORECASE)
                if mm:
                    val = _clean_line_value(mm.group(1))
                    if field == "updated" and meta_updated is None:
                        meta_updated = parse_timestamp(val)
                    elif field == "path" and not project_path:
                        # 支援「C:\dev\CatOS（分支 main）」這類附註
                        path_only = re.split(r"\s*[（(｜|]\s*", val, maxsplit=1)[0].strip()
                        project_path = _clean_line_value(path_only)
                    elif field == "branch" and not branch:
                        branch = val
                    elif field == "main_thread" and not main_thread:
                        main_thread = val
        else:
            sections[current_sec].append(line)

    # 1. 完工路徑：解析 M/N 與坡度
    done_steps: int | None = None
    total_steps: int | None = None
    slope = "unknown"
    roadmap_steps: list[dict[str, Any]] = []
    roadmap_summary = ""
    cb_done = 0
    cb_total = 0

    for line in sections["roadmap"]:
        s = line.strip()
        if not s:
            continue
        if not roadmap_summary and not s.startswith(("-", "*", "#")):
            roadmap_summary = _strip_md_inline(s)
        if "上坡" in s or "⛰" in s:
            slope = "uphill"
        elif "下坡" in s or "🛷" in s:
            slope = "downhill"

        if total_steps is None:
            m_zh = PROGRESS_ZH_RE.search(s)
            if m_zh:
                rem, done_val = int(m_zh.group(1)), int(m_zh.group(2))
                done_steps = done_val
                total_steps = done_val + rem if rem + done_val > 0 else done_val
            else:
                m_rev = PROGRESS_ZH_REV_RE.search(s) or PROGRESS_FRAC_RE.search(s)
                if m_rev:
                    a, b = int(m_rev.group(1)), int(m_rev.group(2))
                    if 0 <= a <= b <= 200:
                        done_steps, total_steps = a, b

        cb = CHECKBOX_RE.match(line)
        if cb:
            is_done = cb.group(1).lower() == "x"
            cb_total += 1
            if is_done:
                cb_done += 1
            roadmap_steps.append({"done": is_done, "text": _strip_md_inline(cb.group(2))})
        else:
            bm = BULLET_RE.match(line)
            if bm and not _is_empty_item(bm.group(1)):
                item_txt = _strip_md_inline(bm.group(1))
                is_done = any(tok in item_txt for tok in ("已完成", "已通過", "✅", "[done]"))
                roadmap_steps.append({"done": is_done, "text": item_txt})

    if total_steps is None and cb_total > 0:
        done_steps, total_steps = cb_done, cb_total
    elif total_steps is None and roadmap_steps:
        total_steps = len(roadmap_steps)
        done_steps = sum(1 for st in roadmap_steps if st["done"])

    # 2. 目前結論
    conclusions: list[str] = []
    for line in sections["conclusions"]:
        bm = BULLET_RE.match(line)
        if bm and not _is_empty_item(bm.group(1)):
            conclusions.append(_strip_md_inline(bm.group(1)))
        elif line.strip() and not line.strip().startswith("#") and not conclusions and not _is_empty_item(line):
            conclusions.append(_strip_md_inline(line))

    # 3. 不滿意待改（Critique Delta）
    critiques: list[dict[str, Any]] = []
    for line in sections["critiques"]:
        cb = CHECKBOX_RE.match(line)
        if cb:
            if not _is_empty_item(cb.group(2)):
                critiques.append(_parse_critique_item(len(critiques), cb.group(1).lower() == "x", cb.group(2)))
            continue
        bm = BULLET_RE.match(line)
        if bm and not _is_empty_item(bm.group(1)):
            critiques.append(_parse_critique_item(len(critiques), False, bm.group(1)))

    # 4. 等使用者決定的事
    decisions: list[str] = []
    for line in sections["decisions"]:
        cb = CHECKBOX_RE.match(line)
        if cb:
            if cb.group(1).lower() != "x" and not _is_empty_item(cb.group(2)):
                decisions.append(_strip_md_inline(cb.group(2)))
            continue
        bm = BULLET_RE.match(line)
        if bm and not _is_empty_item(bm.group(1)):
            decisions.append(_strip_md_inline(bm.group(1)))

    # 5. 下一步
    next_actions: list[dict[str, Any]] = []
    for line in sections["next_actions"]:
        cb = CHECKBOX_RE.match(line)
        if cb:
            if cb.group(1).lower() == "x" or _is_empty_item(cb.group(2)):
                continue
            txt = _strip_md_inline(cb.group(2))
            next_actions.append({"text": txt, "owner": _parse_owner(txt)})
            continue
        bm = BULLET_RE.match(line)
        if bm and not _is_empty_item(bm.group(1)):
            txt = _strip_md_inline(bm.group(1))
            next_actions.append({"text": txt, "owner": _parse_owner(txt)})

    # 6. 進行中的線
    active_lines: list[str] = []
    for line in sections["active_lines"]:
        bm = BULLET_RE.match(line)
        if bm and not _is_empty_item(bm.group(1)):
            active_lines.append(_strip_md_inline(bm.group(1)))

    updated_dt = meta_updated or mtime
    updated_source = "header" if meta_updated else ("mtime" if mtime else "none")

    return {
        "exists": True,
        "updated_at": iso_utc(updated_dt),
        "updated_source": updated_source,
        "project_path": project_path,
        "branch": branch,
        "main_thread": main_thread,
        "progress": {
            "done": done_steps,
            "total": total_steps,
            "slope": slope,
            "summary": roadmap_summary,
            "steps": roadmap_steps[:8],
        },
        "conclusions": conclusions[:5],
        "critiques": critiques,
        "decisions": decisions[:8],
        "next_actions": next_actions[:6],
        "next_action": next_actions[0] if next_actions else None,
        "active_lines": active_lines[:8],
    }


def _find_critique_section_bounds(lines: list[str]) -> tuple[int, int] | None:
    """回傳不滿意待改區塊的 (標題行 index, 區塊結束行 index 不含)。"""
    start = None
    start_level = 2
    for idx, line in enumerate(lines):
        hm = HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            if start is None:
                if _classify_section(hm.group(2)) == "critiques":
                    start = idx
                    start_level = level
            elif level <= start_level:
                return start, idx
    if start is not None:
        return start, len(lines)
    return None


def _build_initial_now_md(project_id: str, project_path: str = "") -> str:
    now_str = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    path_line = f"`{project_path}`" if project_path else "（未指定）"
    return (
        f"# {project_id} 狀態板\n\n"
        f"- 更新時間：{now_str}\n"
        f"- 專案路徑：{path_line}\n\n"
        "## 完工路徑\n"
        "- （待補：寫明還有 N 步、完成 M 步與上坡／下坡）\n\n"
        "## 目前結論\n"
        "- （待補：最新生效的 1 到 3 條定案）\n\n"
        "## 不滿意待改\n\n"
        "## 等使用者決定的事\n"
        "- 無\n\n"
        "## 下一步\n"
        "- 【agent 可直接做】補齊本專案 NOW.md 四格現況\n"
    )


def _format_critique_line(text: str = "", symptom: str = "", pain: str = "", criteria: str = "") -> str:
    stamp = datetime.now().astimezone().strftime("%m-%d %H:%M")
    s, p, c = symptom.strip(), pain.strip(), criteria.strip()
    if s or p or c:
        parts = [x for x in (s, p, c) if x]
        body = " -> ".join(parts)
    else:
        body = " ".join(text.strip().splitlines())
    if not body:
        raise ValueError("不滿意待改內容不能空白")
    return f"- [ ] {body}（{stamp} 記）"


def _maybe_git_commit_status(state_dir: Path, target: Path, message: str) -> dict[str, Any]:
    repo = status_repo_dir(state_dir)
    if not (repo / ".git").exists():
        return {"committed": False, "pushed": False, "note": "狀態資料夾非 git repo，已寫入本機檔案"}
    cfg = load_config(state_dir)
    if not cfg.get("auto_commit_status", True):
        return {"committed": False, "pushed": False, "note": "已寫入檔案（未啟用自動 commit）"}
    rel = target.relative_to(repo).as_posix()
    rc_add, _, err_add = _run_cmd(["git", "add", "--", rel], cwd=repo, timeout=8)
    if rc_add != 0:
        return {"committed": False, "pushed": False, "note": f"git add 略過：{sanitize(err_add)}"}
    rc_c, _, err_c = _run_cmd(["git", "commit", "-m", message, "--", rel], cwd=repo, timeout=10)
    if rc_c != 0:
        return {"committed": False, "pushed": False, "note": f"已存檔，git commit 略過：{sanitize(err_c)}"}
    pushed = False
    note = "已寫入並 commit 至狀態庫"
    if cfg.get("auto_push_status", False):
        rc_p, _, err_p = _run_cmd(["git", "push"], cwd=repo, timeout=15)
        if rc_p == 0:
            pushed = True
            note = "已寫入、commit 並 push 至狀態庫"
        else:
            note = f"已 commit，但 push 失敗：{sanitize(err_p)}"
    return {"committed": True, "pushed": pushed, "note": note}


def add_critique(
    state_dir: Path,
    project_id: str,
    *,
    text: str = "",
    symptom: str = "",
    pain: str = "",
    criteria: str = "",
    project_path: str = "",
) -> dict[str, Any]:
    """新增一條不滿意待改到指定專案的 NOW.md；保留原頂部更新時間以免掩蓋 Git 過期紅燈。"""
    target = safe_status_now_path(state_dir, project_id)
    new_line = _format_critique_line(text=text, symptom=symptom, pain=pain, criteria=criteria)

    if not target.is_file():
        content = _build_initial_now_md(project_id, project_path=project_path)
    else:
        content = read_utf8(target)

    lines = content.replace("\r\n", "\n").splitlines()
    bounds = _find_critique_section_bounds(lines)
    if bounds is not None:
        sec_start, sec_end = bounds
        # 移除區塊裡原本的「- 無」佔位行
        cleaned_body = [
            ln for ln in lines[sec_start + 1 : sec_end]
            if not (BULLET_RE.match(ln) and _is_empty_item(BULLET_RE.match(ln).group(1)))  # type: ignore[union-attr]
        ]
        while cleaned_body and not cleaned_body[-1].strip():
            cleaned_body.pop()
        cleaned_body.append(new_line)
        cleaned_body.append("")
        lines = lines[: sec_start + 1] + cleaned_body + lines[sec_end:]
    else:
        # 找不到區塊時，插在「下一步」或「進行中的線」前面，或附加在尾端
        insert_at = len(lines)
        for idx, ln in enumerate(lines):
            hm = HEADING_RE.match(ln)
            if hm and _classify_section(hm.group(2)) in ("decisions", "next_actions", "active_lines"):
                insert_at = idx
                break
        block = ["## 不滿意待改", new_line, ""]
        if insert_at > 0 and lines[insert_at - 1].strip():
            block = [""] + block
        lines = lines[:insert_at] + block + lines[insert_at:]

    final_text = "\n".join(lines).rstrip("\n") + "\n"
    write_utf8_atomic(target, final_text)
    git_res = _maybe_git_commit_status(state_dir, target, f"cockpit({project_id}): 新增不滿意待改")
    parsed = parse_now_md(final_text)
    return {"ok": True, "project_id": project_id, "critiques": parsed["critiques"], "git": git_res}


def toggle_critique(state_dir: Path, project_id: str, index: int, done: bool | None = None) -> dict[str, Any]:
    """勾銷或重開指定專案 NOW.md 中第 index 條不滿意待改。"""
    target = safe_status_now_path(state_dir, project_id)
    if not target.is_file():
        raise FileNotFoundError(f"找不到 {project_id} 的 NOW.md")

    lines = read_utf8(target).replace("\r\n", "\n").splitlines()
    bounds = _find_critique_section_bounds(lines)
    if bounds is None:
        raise ValueError("NOW.md 中沒有不滿意待改區塊")
    sec_start, sec_end = bounds

    item_idx = 0
    changed = False
    for line_no in range(sec_start + 1, sec_end):
        ln = lines[line_no]
        cb = CHECKBOX_RE.match(ln)
        if cb and not _is_empty_item(cb.group(2)):
            if item_idx == index:
                cur_done = cb.group(1).lower() == "x"
                nxt_done = (not cur_done) if done is None else bool(done)
                mark = "x" if nxt_done else " "
                lines[line_no] = f"- [{mark}] {cb.group(2).strip()}"
                changed = True
                break
            item_idx += 1
            continue
        bm = BULLET_RE.match(ln)
        if bm and not _is_empty_item(bm.group(1)):
            if item_idx == index:
                nxt_done = True if done is None else bool(done)
                mark = "x" if nxt_done else " "
                lines[line_no] = f"- [{mark}] {bm.group(1).strip()}"
                changed = True
                break
            item_idx += 1

    if not changed:
        raise IndexError(f"找不到第 {index} 條不滿意待改項目")

    final_text = "\n".join(lines).rstrip("\n") + "\n"
    write_utf8_atomic(target, final_text)
    git_res = _maybe_git_commit_status(state_dir, target, f"cockpit({project_id}): 更新不滿意待改狀態")
    parsed = parse_now_md(final_text)
    return {"ok": True, "project_id": project_id, "critiques": parsed["critiques"], "git": git_res}


# ---------- 本地 Git 與 T3 CLI 探測 ----------

def probe_git(project_path: Path, now_updated_at: datetime | None = None) -> dict[str, Any]:
    """純唯讀探測本地 Git 狀態。"""
    if not project_path.is_dir():
        return {"available": False, "reason": "本機無此目錄"}
    rc_top, top_out, _ = _run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=project_path, timeout=5)
    if rc_top != 0 or top_out.strip() != "true":
        return {"available": False, "reason": "非 Git 儲存庫"}

    _, branch_out, _ = _run_cmd(["git", "branch", "--show-current"], cwd=project_path, timeout=5)
    branch = branch_out.strip() or "(detached)"

    _, status_out, _ = _run_cmd(["git", "status", "--porcelain"], cwd=project_path, timeout=6)
    dirty_lines = [ln for ln in status_out.splitlines() if ln.strip()]

    rc_log, log_out, _ = _run_cmd(["git", "log", "-1", "--format=%h%x1f%cI%x1f%s"], cwd=project_path, timeout=5)
    last_hash = ""
    last_commit_at: str | None = None
    last_subject = ""
    if rc_log == 0 and log_out.strip():
        parts = log_out.strip().split("\x1f")
        if len(parts) >= 3:
            last_hash = parts[0].strip()
            last_commit_at = iso_utc(parse_timestamp(parts[1]))
            last_subject = parts[2].strip()

    ahead, behind = 0, 0
    rc_ab, ab_out, _ = _run_cmd(["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"], cwd=project_path, timeout=5)
    if rc_ab == 0 and ab_out.strip():
        nums = ab_out.strip().split()
        if len(nums) == 2 and nums[0].isdigit() and nums[1].isdigit():
            ahead, behind = int(nums[0]), int(nums[1])

    commits_since_now = 0
    if now_updated_at is not None and last_commit_at:
        last_dt = parse_timestamp(last_commit_at)
        if last_dt and (last_dt - now_updated_at) > timedelta(minutes=10):
            since_iso = iso_utc(now_updated_at + timedelta(seconds=1))
            rc_cnt, cnt_out, _ = _run_cmd(["git", "rev-list", "--count", f"--since={since_iso}", "HEAD"], cwd=project_path, timeout=5)
            if rc_cnt == 0 and cnt_out.strip().isdigit():
                commits_since_now = int(cnt_out.strip())
            else:
                commits_since_now = 1

    return {
        "available": True,
        "branch": branch,
        "dirty_count": len(dirty_lines),
        "ahead": ahead,
        "behind": behind,
        "last_hash": last_hash,
        "last_commit_at": last_commit_at,
        "last_subject": last_subject,
        "commits_since_now": commits_since_now,
    }


def _find_t3_cli() -> str | None:
    if os.name == "nt":
        return shutil.which("t3.cmd") or shutil.which("t3.exe") or shutil.which("t3")
    return shutil.which("t3")


def rewrite_t3_link(original_link: str | None, t3_base_url: str) -> str:
    """若有設定個人 T3 base URL（如 Tailscale Serve），改寫成對應連結；否則保留原 link。"""
    link = str(original_link or "").strip()
    base = t3_base_url.strip().rstrip("/")
    if not link:
        return base
    if not base:
        return link
    parsed = urlparse(link)
    if parsed.path.startswith("/threads/"):
        return f"{base}{parsed.path}"
    return link


def probe_t3_threads(
    project_path: Path,
    *,
    overload_items: int = 1000,
    t3_base_url: str = "",
    t3_runner: Callable[[Path], list[dict[str, Any]] | None] | None = None,
) -> dict[str, Any]:
    """透過官方 `t3 thread list --project <path> --json` 抓該專案對話（絕不碰 statev2.sqlite）。"""
    raw_threads: list[dict[str, Any]] | None
    if t3_runner is not None:
        raw_threads = t3_runner(project_path)
    else:
        cli = _find_t3_cli()
        if not cli or not project_path.is_dir():
            return {"available": False, "reason": "找不到 t3 CLI 或本機目錄", "threads": []}
        rc, out, err = _run_cmd([cli, "thread", "list", "--project", str(project_path), "--json"], timeout=10)
        if rc != 0:
            return {"available": False, "reason": sanitize(err or "t3 thread list 執行失敗"), "threads": []}
        try:
            parsed = json.loads(out)
            raw_threads = parsed if isinstance(parsed, list) else []
        except ValueError:
            return {"available": False, "reason": "t3 回傳非合法 JSON", "threads": []}

    if raw_threads is None:
        return {"available": False, "reason": "略過 T3 探測", "threads": []}

    unsettled: list[dict[str, Any]] = []
    running_count = 0
    waiting_count = 0
    failed_count = 0
    ready_to_settle_count = 0
    overloaded: list[dict[str, Any]] = []
    latest_dt: datetime | None = None

    for th in raw_threads:
        if not isinstance(th, dict):
            continue
        if th.get("settled") or th.get("archived"):
            continue
        status = str(th.get("status") or "idle").lower()
        items = int(th.get("itemCount") or 0)
        is_sub = bool(th.get("parentThreadId") or str(th.get("creationSource") or "").lower() == "mcp")
        upd_dt = parse_timestamp(th.get("updatedAt"))
        if upd_dt and (latest_dt is None or upd_dt > latest_dt):
            latest_dt = upd_dt

        entry = {
            "thread_id": str(th.get("threadId") or ""),
            "title": str(th.get("title") or "未命名對話"),
            "status": status,
            "item_count": items,
            "updated_at": iso_utc(upd_dt),
            "model": str(th.get("model") or ""),
            "provider": str(th.get("providerInstanceId") or ""),
            "is_subagent": is_sub,
            "open_pr_count": int(th.get("openPullRequestCount") or 0),
            "overloaded": items >= overload_items,
            "link": rewrite_t3_link(th.get("link"), t3_base_url),
            "app_link": str(th.get("link") or ""),
        }
        unsettled.append(entry)

        if status in ("running", "starting", "preparing", "queued"):
            running_count += 1
        elif status == "waiting":
            waiting_count += 1
        elif status in ("failed", "interrupted"):
            failed_count += 1
        elif status == "completed" or (status == "idle" and is_sub):
            ready_to_settle_count += 1

        if items >= overload_items:
            overloaded.append(entry)

    unsettled.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return {
        "available": True,
        "total_threads": len(raw_threads),
        "unsettled_count": len(unsettled),
        "running_count": running_count,
        "waiting_count": waiting_count,
        "failed_count": failed_count,
        "ready_to_settle_count": ready_to_settle_count,
        "overloaded_count": len(overloaded),
        "overloaded_threads": overloaded[:5],
        "latest_updated_at": iso_utc(latest_dt),
        "threads": unsettled[:10],
    }


# ---------- 專案探索、球權分流與全景總覽 ----------

def sync_status_repo(state_dir: Path) -> dict[str, Any]:
    """對 ~/.omnikit/status 做唯讀安全同步（git pull --ff-only），不自動改檔或衝突覆蓋。"""
    repo = status_repo_dir(state_dir)
    if not (repo / ".git").exists():
        return {"synced": False, "reason": "狀態目錄尚未綁定 git repo"}
    rc, out, err = _run_cmd(["git", "pull", "--ff-only"], cwd=repo, timeout=15)
    if rc == 0:
        return {"synced": True, "message": sanitize(out or "已同步至最新")}
    return {"synced": False, "reason": sanitize(err or out or "git pull --ff-only 失敗")}


def discover_projects(state_dir: Path, cfg: dict[str, Any], default_repo_root: Path | None = ROOT) -> list[dict[str, Any]]:
    """合併「本機登記專案 ∪ ~/.omnikit/status/* ∪ 目前 OmniKit repo」成不重複清單。"""
    merged: dict[str, dict[str, Any]] = {}

    def _upsert(pid: str, *, name: str | None = None, path: str | None = None, source: str, parked: bool | None = None):
        key = pid.lower()
        cur = merged.get(key)
        if cur is None:
            cur = {
                "id": pid,
                "name": name or pid,
                "path": path or "",
                "sources": [source],
                "manual_parked": bool(parked) if parked is not None else False,
            }
            merged[key] = cur
        else:
            if source not in cur["sources"]:
                cur["sources"].append(source)
            if name and (not cur["name"] or cur["name"] == cur["id"]):
                cur["name"] = name
            if path and not cur["path"]:
                cur["path"] = path
            if parked is not None:
                cur["manual_parked"] = bool(parked)

    # 1. 個人 config 登記（優先權最高）
    for item in cfg.get("projects") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            pid = validate_project_id(str(item["id"]))
        except ValueError:
            continue
        _upsert(
            pid,
            name=str(item.get("name") or pid),
            path=str(item.get("path") or ""),
            source="config",
            parked=bool(item.get("parked", False)),
        )

    # 2. ~/.omnikit/status/*（多機同步來源）
    sdir = status_repo_dir(state_dir)
    if sdir.is_dir():
        for child in sorted(sdir.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir() or child.name.startswith(".") or child.name.startswith("_"):
                continue
            if not SAFE_PROJECT_ID.match(child.name):
                continue
            now_file = child / "NOW.md"
            hint_path = ""
            if now_file.is_file():
                try:
                    parsed_hdr = parse_now_md(read_utf8(now_file))
                    hint_path = parsed_hdr.get("project_path") or ""
                except OSError:
                    hint_path = ""
            _upsert(child.name, name=child.name, path=hint_path, source="status_repo")

    # 3. 保底：把 OmniKit 自己放進去（同事零設定開啟也看得到）
    if default_repo_root is not None and default_repo_root.is_dir():
        _upsert(default_repo_root.name, name=default_repo_root.name, path=str(default_repo_root), source="workspace")

    return list(merged.values())


def _build_commands(pid: str, now_rel: str, now_info: dict[str, Any], stale_reasons: list[str], t3_info: dict[str, Any]) -> dict[str, str]:
    nxt = now_info.get("next_action")
    open_crit = [c for c in now_info.get("critiques", []) if not c.get("done")]
    if open_crit:
        first_c = open_crit[0]["text"]
        next_prompt = f"請先讀 ~/.omnikit/status/{now_rel}，我們先處理這條不滿意待改：{first_c}"
    elif nxt and nxt.get("text"):
        next_prompt = f"請先讀 ~/.omnikit/status/{now_rel}，接著推進下一步：{nxt['text']}"
    else:
        next_prompt = f"請先讀 ~/.omnikit/status/{now_rel}，向我回報目前進度、結論與下一步。"

    parts = [f"請讀 ~/.omnikit/status/{now_rel} 並對照本專案最近 Git commit 與近期對話，更新 NOW.md 四格欄位（完工路徑步數與坡度、目前結論、不滿意待改、唯一球權下一步）。"]
    if stale_reasons:
        parts.append(f"偵測到狀態提醒：{'；'.join(stale_reasons)}。")
    if t3_info.get("ready_to_settle_count"):
        parts.append(f"另外請檢查 {t3_info['ready_to_settle_count']} 條已完成但未 settle 的子對話並協助收尾。")
    if t3_info.get("overloaded_count"):
        parts.append("主線對話已超載，請一併準備交接檔。")
    reconcile_prompt = "".join(parts)
    return {"next_prompt": next_prompt, "reconcile_prompt": reconcile_prompt}


def collect_project(
    entry: dict[str, Any],
    *,
    state_dir: Path,
    cfg: dict[str, Any],
    now: datetime,
    t3_runner: Callable[[Path], list[dict[str, Any]] | None] | None = None,
) -> dict[str, Any]:
    """採集並對帳單一專案的完整 4 格狀態與球權分流。"""
    pid = entry["id"]
    now_path = status_repo_dir(state_dir) / pid / "NOW.md"
    now_mtime = None
    now_raw = None
    if now_path.is_file():
        try:
            now_mtime = datetime.fromtimestamp(now_path.stat().st_mtime, UTC)
            now_raw = read_utf8(now_path)
        except OSError:
            now_raw = None

    now_info = parse_now_md(now_raw, mtime=now_mtime)
    now_dt = parse_timestamp(now_info.get("updated_at"))

    raw_path = entry.get("path") or now_info.get("project_path") or ""
    local_path = Path(raw_path) if raw_path else None
    local_available = bool(local_path and local_path.is_dir())
    remote_only = not local_available

    git_info = probe_git(local_path, now_updated_at=now_dt) if local_available and local_path else {"available": False, "reason": "遠端專案或未設定本機路徑"}
    t3_info = (
        probe_t3_threads(
            local_path,
            overload_items=cfg["overload_items"],
            t3_base_url=cfg["t3_base_url"],
            t3_runner=t3_runner,
        )
        if local_available and local_path
        else {"available": False, "reason": "遠端專案（無本機 T3 資訊）", "threads": []}
    )

    # 計算最近活動時間
    activity_candidates = [
        parse_timestamp(git_info.get("last_commit_at")),
        parse_timestamp(t3_info.get("latest_updated_at")),
        now_dt,
    ]
    valid_times = [dt for dt in activity_candidates if dt is not None]
    last_activity_dt = max(valid_times) if valid_times else None
    days_idle = (now - last_activity_dt).total_seconds() / 86400.0 if last_activity_dt else 999.0

    # 過期紅燈對帳
    stale_reasons: list[str] = []
    if not now_info["exists"]:
        stale_reasons.append("尚未建立 NOW.md")
    else:
        commits_behind = int(git_info.get("commits_since_now") or 0)
        if commits_behind > 0:
            stale_reasons.append(f"NOW.md 落後 Git {commits_behind} 個 commit")
        t3_latest_dt = parse_timestamp(t3_info.get("latest_updated_at"))
        if t3_latest_dt and now_dt and (t3_latest_dt - now_dt) > timedelta(hours=1):
            stale_reasons.append("T3 對話已推進，NOW.md 尚未更新")

    open_critiques = [c for c in now_info.get("critiques", []) if not c.get("done")]
    decisions = now_info.get("decisions", [])
    next_action = now_info.get("next_action")
    next_owner = next_action["owner"] if next_action else "unassigned"

    waiting_count = int(t3_info.get("waiting_count") or 0)
    failed_count = int(t3_info.get("failed_count") or 0)
    running_count = int(t3_info.get("running_count") or 0)
    ready_settle_count = int(t3_info.get("ready_to_settle_count") or 0)
    overloaded_count = int(t3_info.get("overloaded_count") or 0)
    dirty_count = int(git_info.get("dirty_count") or 0)

    # 球權分流判定
    block_reasons: list[str] = []
    if open_critiques:
        block_reasons.append(f"{len(open_critiques)} 條不滿意待改")
    if decisions:
        block_reasons.append(f"{len(decisions)} 件等你決定")
    if next_owner == "user":
        block_reasons.append("下一步卡在你身上")
    if waiting_count > 0:
        block_reasons.append(f"{waiting_count} 條對話等待回覆")
    if failed_count > 0:
        block_reasons.append(f"{failed_count} 條對話異常中斷")

    settle_reasons: list[str] = []
    if ready_settle_count > 0:
        settle_reasons.append(f"{ready_settle_count} 條對話待 settle")
    if overloaded_count > 0:
        settle_reasons.append(f"{overloaded_count} 條主線超載（>={cfg['overload_items']} 項）")
    if stale_reasons and days_idle <= cfg["parked_days"]:
        settle_reasons.append(stale_reasons[0])

    if block_reasons:
        lane = "blocked_on_me"
    elif entry.get("manual_parked"):
        lane = "parked"
    elif settle_reasons:
        lane = "ready_to_settle"
    elif running_count > 0 or dirty_count > 0 or days_idle <= cfg["parked_days"]:
        lane = "active"
    else:
        lane = "parked"

    # 健康三態（對應 Linear：Blocked on Me / Refining / On Track / Parked）
    if lane == "parked":
        health = "parked"
    elif open_critiques:
        health = "refining"
    elif block_reasons:
        health = "blocked"
    else:
        health = "on_track"

    commands = _build_commands(pid, f"{pid}/NOW.md", now_info, stale_reasons, t3_info)

    # 主入口連結：優先連最新未結案對話，其次 T3 首頁
    primary_thread = t3_info["threads"][0] if t3_info.get("threads") else None
    primary_t3_url = (primary_thread["link"] if primary_thread else "") or cfg["t3_base_url"]

    return {
        "id": pid,
        "name": entry.get("name") or pid,
        "path": str(local_path) if local_path else raw_path,
        "local_available": local_available,
        "remote_only": remote_only,
        "manual_parked": bool(entry.get("manual_parked", False)),
        "sources": entry.get("sources") or [],
        "lane": lane,
        "lane_label": LANE_META[lane]["label"],
        "health": health,
        "block_reasons": block_reasons,
        "settle_reasons": settle_reasons,
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "last_activity_at": iso_utc(last_activity_dt),
        "last_activity_age": fmt_age(last_activity_dt, now),
        "days_idle": round(days_idle, 2),
        "git": git_info,
        "t3": t3_info,
        "now": now_info,
        "open_critiques_count": len(open_critiques),
        "commands": commands,
        "primary_t3_url": primary_t3_url,
    }


def collect_overview(
    state_dir: Path | None = None,
    *,
    sync: bool = False,
    now: datetime | None = None,
    default_repo_root: Path | None = ROOT,
    t3_runner: Callable[[Path], list[dict[str, Any]] | None] | None = None,
) -> dict[str, Any]:
    """產出跨專案指揮台完整快照。"""
    sdir = state_dir if state_dir is not None else default_state_dir()
    ref_now = utc_now(now)
    sync_result = sync_status_repo(sdir) if sync else None
    cfg = load_config(sdir)
    entries = discover_projects(sdir, cfg, default_repo_root=default_repo_root)

    projects = [
        collect_project(e, state_dir=sdir, cfg=cfg, now=ref_now, t3_runner=t3_runner)
        for e in entries
    ]
    projects.sort(
        key=lambda p: (
            LANE_META[p["lane"]]["order"],
            -p["open_critiques_count"],
            -len(p["block_reasons"]),
            -(1 if p["stale"] else 0),
            p["days_idle"],
            p["name"].lower(),
        )
    )

    counts = {lane: 0 for lane in LANE_META}
    stale_count = 0
    overloaded_total = 0
    settle_total = 0
    open_critiques_total = 0
    for p in projects:
        counts[p["lane"]] += 1
        if p["stale"]:
            stale_count += 1
        overloaded_total += int(p["t3"].get("overloaded_count") or 0)
        settle_total += int(p["t3"].get("ready_to_settle_count") or 0)
        open_critiques_total += p["open_critiques_count"]

    return {
        "generated_at": iso_utc(ref_now),
        "generated_local": fmt_local_time(ref_now),
        "state_dir": str(sdir),
        "status_repo_exists": status_repo_dir(sdir).is_dir(),
        "sync": sync_result,
        "settings": {
            "t3_base_url": cfg["t3_base_url"],
            "parked_days": cfg["parked_days"],
            "overload_items": cfg["overload_items"],
            "auto_commit_status": cfg["auto_commit_status"],
            "auto_push_status": cfg["auto_push_status"],
        },
        "summary": {
            "total": len(projects),
            "blocked_on_me": counts["blocked_on_me"],
            "ready_to_settle": counts["ready_to_settle"],
            "active": counts["active"],
            "parked": counts["parked"],
            "stale": stale_count,
            "open_critiques": open_critiques_total,
            "ready_to_settle_threads": settle_total,
            "overloaded_threads": overloaded_total,
        },
        "projects": projects,
    }


def write_snapshot(state_dir: Path, overview: dict[str, Any]) -> Path:
    out = cockpit_dir(state_dir) / "snapshot.json"
    write_utf8_atomic(out, json.dumps(overview, ensure_ascii=False, indent=2) + "\n")
    return out


# ---------- 個人疊層：工具名冊與模型偏好 ----------

def collect_tools_overlay(state_dir: Path | None = None, data_dir: Path | None = None) -> dict[str, Any]:
    """讀取 OmniKit 共用名冊並疊加目前個人 profile、私有模組與模型偏好。"""
    sdir = state_dir if state_dir is not None else default_state_dir()
    ddir = data_dir if data_dir is not None else (ROOT / "data")
    try:
        import dispatch as dispatch_mod  # type: ignore
        import profiles as profiles_mod  # type: ignore
        import validate as validate_mod  # type: ignore
    except ImportError as exc:
        return {"available": False, "error": f"缺少必要相依套件（請以 uv run 執行）：{sanitize(exc)}"}

    errors, roster = validate_mod.check(ddir, state=sdir, private=True)
    profile_name = roster.get("profile") or "default"
    profile_dir_str = roster.get("profile_dir")
    profile_dir = Path(profile_dir_str) if profile_dir_str else profiles_mod.folder(ddir, sdir, profile_name)

    personal_dispatch: dict[str, Any] = {}
    try:
        personal_dispatch = dispatch_mod.personal(profile_dir) or {}
    except (OSError, ValueError, KeyError, TypeError):
        personal_dispatch = {}

    slots_by_id = {s["id"]: s for s in roster.get("slots") or []}
    modules_by_id = {m["id"]: m for m in roster.get("modules") or []}
    enabled_set = set(roster.get("enabled") or [])

    status_counts: dict[str, int] = {}
    tools_list: list[dict[str, Any]] = []
    for tid, doc in sorted((roster.get("tools") or {}).items()):
        st = str(doc.get("status") or "pending")
        status_counts[st] = status_counts.get(st, 0) + 1
        slot_names = [slots_by_id[s]["name"] for s in doc.get("slots", []) if s in slots_by_id]
        mod_ids = list(dict.fromkeys(slots_by_id[s].get("module", "") for s in doc.get("slots", []) if s in slots_by_id))
        tools_list.append({
            "id": tid,
            "name": doc.get("name") or tid,
            "status": st,
            "kind": doc.get("kind") or "",
            "slots": doc.get("slots") or [],
            "slot_names": slot_names,
            "modules": [modules_by_id[m]["name"] for m in mod_ids if m in modules_by_id],
            "enabled_in_profile": (not mod_ids) or any(m in enabled_set for m in mod_ids),
            "summary": doc.get("summary") or doc.get("reason") or "",
            "trigger_when": doc.get("trigger_when") or "",
            "url": doc.get("url") or "",
            "works_with": doc.get("works_with") or [],
            "trial_until": doc.get("trial_until") or "",
            "replaces": doc.get("replaces") or "",
        })

    order_map = {"default": 0, "trial": 1, "on_demand": 2, "assess": 3, "retired": 4, "rejected": 5, "pending": 6}
    tools_list.sort(key=lambda t: (order_map.get(t["status"], 9), t["name"].lower()))

    # 整理個人實例清單（絕不印出任何敏感資料）
    instances_summary = []
    for inst_id, info in (personal_dispatch.get("instances") or {}).items():
        if not isinstance(info, dict):
            continue
        instances_summary.append({
            "id": inst_id,
            "driver": info.get("driver") or "",
            "account": info.get("account") or "",
            "classes": info.get("classes") or [],
            "auto_dispatch": bool(info.get("classes")),
            "note": info.get("note") or "",
        })

    return {
        "available": True,
        "validation_errors": errors[:10],
        "profile": {
            "name": profile_name,
            "dir": str(profile_dir) if profile_dir else "",
            "domains": roster.get("domains"),
            "private_modules": (roster.get("private") or {}).get("loaded") or [],
            "visibility": personal_dispatch.get("visibility") or "visible",
            "thinking_preference": personal_dispatch.get("thinking_preference") or "default",
            "on_exhausted": personal_dispatch.get("on_exhausted") or "fail_closed",
            "exclude_models": personal_dispatch.get("exclude_models") or [],
            "instances": instances_summary,
        },
        "counts": {
            "total": len(tools_list),
            **status_counts,
        },
        "tools": tools_list,
    }


# ---------- 個人疊層：多帳號與額度 ----------

def collect_accounts(state_dir: Path | None = None, *, refresh_agy: bool = False) -> dict[str, Any]:
    """透過 account_pool.py 讀取 Claude + Antigravity 多帳號額度與警示（不存不印任何 token）。"""
    sdir = state_dir if state_dir is not None else default_state_dir()
    script = SCRIPTS_DIR / "account_pool.py"
    if not script.is_file():
        return {"available": False, "error": "找不到 account_pool.py"}

    env = dict(os.environ)
    env["OMNIKIT_STATE_DIR"] = str(sdir)
    env["PYTHONUTF8"] = "1"
    cmd = [sys.executable, str(script), "usage", "--json"]
    if refresh_agy:
        cmd.insert(-1, "--refresh-agy")

    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 25 if refresh_agy else 12,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(cmd, check=False, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "error": sanitize(exc)}

    if proc.returncode != 0:
        return {"available": False, "error": sanitize(proc.stderr or proc.stdout or "讀取帳號額度失敗")}
    try:
        doc = json.loads(proc.stdout)
    except ValueError:
        return {"available": False, "error": "帳號額度回傳非合法 JSON"}

    # 去除本機敏感絕對設定目錄不必要資訊，保留乾淨展示欄位
    return {
        "available": True,
        "refreshed_agy": refresh_agy,
        "generated_at": iso_utc(utc_now()),
        "claude": doc.get("claude") or [],
        "claude_selection": doc.get("claude_selection"),
        "antigravity": doc.get("antigravity") or [],
        "alerts": doc.get("alerts") or [],
    }
