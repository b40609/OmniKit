# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""OmniKit 單一事實來源（~/.omnikit/kit.yaml）與工作台套件管理核心。

回應跨家兩階段盲審（P0-2、P0-4、P1-8、P1-9、P1-10、P1-12、P2-1）：
1. 唯一寫入權威：GUI、精靈、CLI 統一透過 kit.patch() 寫入 ~/.omnikit/kit.yaml，
   具備跨行程排他鎖（locks/kit.lock）、rev 樂觀鎖、未知鍵完整保留，並在同把鎖內鏡像寫入 profile.json。
2. 純讀取零副作用：kit.load() 在檔案不存在時只回傳記憶體預設結構（rev=0），絕不在 -WhatIf 或 --check 時偷寫檔案。
3. 三方漂移偵測（state/applied.json）：比對「意圖（kit.yaml）」、「上次套用指紋（applied.json）」、「即時現況」，
   區分「尚未套用」與「使用者外部手改」；支援 adopt（收進設定）、restore（還原面板設定）、snooze（暫緩 7 天）。
4. 精選工作台套件目錄、Context 預算價目表與本機鎖定版本外掛啟停器：
   marketplace 一律指向本機鎖定版本（~/.omnikit/current），對全部設定目錄同步啟用與停用，離線時優雅標記「待連網再裝」。

用法：
  uv run engine/scripts/kit.py show [--json]
  uv run engine/scripts/kit.py check [--json]
  uv run engine/scripts/kit.py set-profile <名稱>
  uv run engine/scripts/kit.py toggle <tool_id> --tier <resident|on_demand|disabled> [--json]
  uv run engine/scripts/kit.py drift [--resolve <id> --action <adopt|restore|snooze>] [--json]
  uv run engine/scripts/kit.py dump [--out <檔案>]
  uv run engine/scripts/kit.py --selftest
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edition  # noqa: E402
import homes  # noqa: E402
import profiles  # noqa: E402
import statedir  # noqa: E402
from fsretry import retry  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1
KIT_HEADER = (
    "# ~/.omnikit/kit.yaml — 由 OmniKit 控制面板與 CLI 統一管理（單一事實來源）\n"
    "# 可手動編輯，但 YAML 註解在下次寫入時會重新排版；備註請寫在 notes 欄位。\n"
)

# 開場 Context 成本估算表（token 數；0 代表按需讀取不占開場常駐額度）
# 分母基準：200,000 tokens（5% = 10,000 tokens 轉黃提醒，10% = 20,000 tokens 轉紅警告）
CONTEXT_WINDOW_REF = 200_000
WARN_TOKENS = 10_000
DANGER_TOKENS = 20_000

BUILTIN_COSTS = {
    "baseline_rules": {"claude-code": 1350, "codex": 1350, "antigravity": 1350},
    "core_skills": {"claude-code": 620, "codex": 620, "antigravity": 620},
    "chrome-devtools-mcp": {"claude-code": 280, "codex": 1850, "antigravity": 1850},
}

TOOL_COSTS: dict[str, dict[str, int]] = {
    "chrome-devtools-mcp": {"claude-code": 280, "codex": 1850, "antigravity": 1850},
    "gitleaks": {"claude-code": 0, "codex": 0, "antigravity": 0},
    "frontend-design": {"claude-code": 140, "codex": 140, "antigravity": 140},
    "skill-creator": {"claude-code": 140, "codex": 0, "antigravity": 140},
    "claude-code-setup": {"claude-code": 120, "codex": 0, "antigravity": 0},
    "impeccable": {"claude-code": 180, "codex": 180, "antigravity": 180},
    "bmad": {"claude-code": 320, "codex": 320, "antigravity": 320},
    "rea": {"claude-code": 260, "codex": 1400, "antigravity": 1400},
    "deja-vu": {"claude-code": 0, "codex": 0, "antigravity": 0},
    "exa": {"claude-code": 220, "codex": 950, "antigravity": 950},
    "t3-code": {"claude-code": 0, "codex": 0, "antigravity": 0},
}

# L1 / L2 免金鑰開箱預設勾選清單（status 皆為 default 且無須外部 API Key）
DEFAULT_ENABLED_TOOLS = (
    "chrome-devtools-mcp",
    "gitleaks",
    "frontend-design",
    "skill-creator",
    "claude-code-setup",
)

NEEDS_API_KEY = {"exa": "EXA_API_KEY"}

MANUAL_INSTALL_HINTS: dict[str, str] = {
    "gitleaks": "winget install Gitleaks.Gitleaks",
    "impeccable": "npx skills add pbakaus/impeccable",
    "bmad": "npx bmad-method install",
    "deja-vu": "gh release download -R vshulcz/deja-vu",
    "t3-code": "前往 https://t3.codes 下載安裝桌面版",
    "exa": "設定環境變數 EXA_API_KEY 後於終端機登記 MCP",
}


def normalize_done_check(val: Any) -> str:
    """正規化 done_check 設定值（處理 YAML 無引號 off 被讀成 False 的情況，預設為 log）。"""
    if val is False:
        return "off"
    if val is True or val is None:
        return "log"
    s = str(val).strip().lower()
    if s in ("0", "off", "false", "no"):
        return "off"
    if s == "block":
        return "block"
    return "log"


def normalize_agent_ids(works_with: list[str] | None) -> list[str]:
    """將工具卡的 works_with（如 claude）統一對齊為 installed_agents 代號（claude-code、codex、antigravity），修 P0-1。"""
    mapping = {
        "claude": "claude-code",
        "claude-code": "claude-code",
        "codex": "codex",
        "antigravity": "antigravity",
        "agy": "antigravity",
    }
    out: list[str] = []
    for raw in works_with or ["claude-code", "codex", "antigravity"]:
        mapped = mapping.get(str(raw).strip().lower(), str(raw).strip().lower())
        if mapped and mapped not in out:
            out.append(mapped)
    return out


def resolve_install_mechanism(tid: str, tool_doc: dict[str, Any]) -> dict[str, str]:
    """回傳工作台工具的真實安裝機制分類（auto_mcp / auto_plugin / manual），杜絕假啟用誤導（修 M-P1-2）。"""
    if tid == "chrome-devtools-mcp":
        return {"mode": "auto_mcp", "badge": "一鍵啟停 MCP", "manual_hint": ""}
    if str(tool_doc.get("status") or "") == "default" and bool(tool_doc.get("plugin")):
        return {"mode": "auto_plugin", "badge": "一鍵安裝外掛", "manual_hint": ""}
    hint = MANUAL_INSTALL_HINTS.get(tid) or f"請參閱 {tool_doc.get('url') or '工具官方文件'} 手動安裝"
    return {"mode": "manual", "badge": "記錄偏好（需手動裝）", "manual_hint": hint}

GOAL_PRESETS: dict[str, dict[str, Any]] = {
    "fullstack-app": {
        "id": "fullstack-app",
        "name": "做網站、介面或實用小工具",
        "summary": "預載瀏覽器實測、前端設計、防假完工驗收與金鑰檢查",
        "domains": ["software-dev"],
        "tools": ["chrome-devtools-mcp", "gitleaks", "frontend-design", "skill-creator", "claude-code-setup"],
    },
    "data-automation": {
        "id": "data-automation",
        "name": "跑數據分析、圖表或自動化腳本",
        "summary": "重視數值單位、來源可重現與真實執行輸出驗證",
        "domains": ["data-science", "software-dev"],
        "tools": ["chrome-devtools-mcp", "gitleaks", "skill-creator"],
    },
    "research-docs": {
        "id": "research-docs",
        "name": "查業界資料、比較方案與寫報告",
        "summary": "啟用多管道飽和調研、證據核實與結構化交接",
        "domains": ["research"],
        "tools": ["chrome-devtools-mcp", "gitleaks"],
    },
    "minimal-safe": {
        "id": "minimal-safe",
        "name": "極簡安全底座（只開護欄與核心技能）",
        "summary": "最省開場額度，保留安全護欄、防假完工與本機狀態板",
        "domains": ["software-dev"],
        "tools": ["gitleaks"],
    },
}


class RevConflictError(ValueError):
    """kit.yaml 的 rev 與預期不符（樂觀鎖衝突）。"""


def kit_path(state: Path | None = None) -> Path:
    base = state if state is not None else statedir.state_dir()
    return base / "kit.yaml"


def applied_path(state: Path | None = None) -> Path:
    base = state if state is not None else statedir.state_dir()
    return base / "state" / "applied.json"


@contextlib.contextmanager
def kit_lock(state: Path | None = None):
    base = state if state is not None else statedir.state_dir()
    lock_file = base / "locks" / "kit.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if not lock_file.is_file() or lock_file.stat().st_size == 0:
        lock_file.write_bytes(b"0")
    f = open(lock_file, "r+b")
    try:
        f.seek(0)
        if os.name == "nt":
            import msvcrt

            for _ in range(100):
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    finally:
        f.close()


def _atomic_write_bytes(path: Path, data: bytes) -> bool:
    if path.is_file() and retry(path.read_bytes) == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".kit-tmp-", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        retry(os.replace, tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return True


def default_profile_spec() -> dict[str, Any]:
    return {
        "preset": ["fullstack-app"],
        "tools": {tid: {"tier": "resident"} for tid in DEFAULT_ENABLED_TOOLS},
        "done_check": "log",
        "overrides": {},
        "notes": "",
    }


def _default_doc(active_profile: str = "default") -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "rev": 0,
        "active_profile": active_profile,
        "onboarding_completed": active_profile != "default",
        "profiles": {
            active_profile: default_profile_spec(),
        },
        "machine": {
            "server": {"mode": "on_demand", "port": 3780, "autostart": False},
            "status": {"mode": "local", "remote": None, "auto_push": False},
            "budget": {"claude-code": WARN_TOKENS, "codex": WARN_TOKENS, "antigravity": WARN_TOKENS},
        },
    }


def load(state: Path | None = None) -> dict[str, Any]:
    """純讀取 ~/.omnikit/kit.yaml，檔案不存在時回傳記憶體預設結構（絕不寫檔）。"""
    base = state if state is not None else statedir.state_dir()
    p = kit_path(base)
    legacy_prof = profiles.chosen(base) or "default"
    if not p.is_file():
        doc = _default_doc(legacy_prof)
        doc["_exists"] = False
        return doc
    try:
        raw = retry(p.read_bytes).decode("utf-8-sig")
        parsed = yaml.safe_load(raw)
    except (OSError, UnicodeError, yaml.YAMLError):
        doc = _default_doc(legacy_prof)
        doc["_exists"] = False
        doc["_corrupt"] = True
        return doc
    if not isinstance(parsed, dict):
        doc = _default_doc(legacy_prof)
        doc["_exists"] = False
        doc["_corrupt"] = True
        return doc

    base_def = _default_doc(str(parsed.get("active_profile") or legacy_prof))
    merged = copy.deepcopy(parsed)
    merged.setdefault("schema", SCHEMA_VERSION)
    merged.setdefault("rev", 0)
    merged.setdefault("active_profile", legacy_prof)
    merged.setdefault("onboarding_completed", merged["active_profile"] != "default")
    if not isinstance(merged.get("profiles"), dict):
        merged["profiles"] = {}
    act = str(merged["active_profile"])
    if act not in merged["profiles"] or not isinstance(merged["profiles"][act], dict):
        merged["profiles"][act] = default_profile_spec()
    else:
        pspec = merged["profiles"][act]
        pspec.setdefault("preset", ["fullstack-app"])
        if not isinstance(pspec.get("tools"), dict):
            pspec["tools"] = {tid: {"tier": "resident"} for tid in DEFAULT_ENABLED_TOOLS}
        pspec["done_check"] = normalize_done_check(pspec.get("done_check", "log"))
        pspec.setdefault("overrides", {})
        pspec.setdefault("notes", "")

    if not isinstance(merged.get("machine"), dict):
        merged["machine"] = base_def["machine"]
    else:
        for subk, subv in base_def["machine"].items():
            if not isinstance(merged["machine"].get(subk), dict):
                merged["machine"][subk] = copy.deepcopy(subv)
            else:
                for k2, v2 in subv.items():
                    merged["machine"][subk].setdefault(k2, copy.deepcopy(v2))
    merged["_exists"] = True
    return merged


def save_unlocked(state: Path, doc: dict[str, Any], *, expected_rev: int | None = None,
                  mirror_profile: bool = True) -> dict[str, Any]:
    """在已持有 kit_lock 的情況下寫入 kit.yaml 並鏡像更新 profile.json（保留未知鍵；原檔損壞時自動先備份 .bak）。"""
    cur = load(state)
    kp = kit_path(state)
    if cur.get("_corrupt") and kp.is_file():
        bak_path = Path(f"{kp}.bak")
        try:
            _atomic_write_bytes(bak_path, retry(kp.read_bytes))
        except OSError:
            pass
    cur_schema = int(cur.get("schema") or SCHEMA_VERSION)
    if cur_schema > SCHEMA_VERSION:
        raise ValueError(f"kit.yaml 的 schema 版本（{cur_schema}）比目前程式（{SCHEMA_VERSION}）新，拒絕覆寫以免遺失設定")
    cur_rev = int(cur.get("rev") or 0)
    if expected_rev is not None and expected_rev != cur_rev:
        raise RevConflictError(f"設定已被其他視窗或指令更新（目前 rev={cur_rev}，送出 rev={expected_rev}），請重新整理後再套用")

    clean = {k: v for k, v in copy.deepcopy(doc).items() if not str(k).startswith("_")}
    clean["schema"] = SCHEMA_VERSION
    clean["rev"] = cur_rev + 1
    active = str(clean.get("active_profile") or "default").strip() or "default"
    clean["active_profile"] = active

    dumped = KIT_HEADER + yaml.safe_dump(clean, allow_unicode=True, sort_keys=False, width=120)
    _atomic_write_bytes(kp, dumped.replace("\r\n", "\n").encode("utf-8"))

    if mirror_profile:
        prof_file = state / "profile.json"
        if active != "default" or clean.get("onboarding_completed") or prof_file.exists():
            prof_bytes = (json.dumps({"profile": active}, ensure_ascii=False) + "\n").encode("utf-8")
            _atomic_write_bytes(prof_file, prof_bytes)

    clean["_exists"] = True
    return clean


def _patch_in_lock(
    base: Path,
    *,
    active_profile: str | None = None,
    onboarding_completed: bool | None = None,
    profile_patch: dict[str, Any] | None = None,
    machine_patch: dict[str, Any] | None = None,
    expected_rev: int | None = None,
    mirror_profile: bool = True,
) -> dict[str, Any]:
    doc = load(base)
    if active_profile is not None:
        if not profiles.NAME.match(active_profile):
            raise ValueError(f"profile 名稱只能用小寫英數與 -：{active_profile}")
        doc["active_profile"] = active_profile
    act = str(doc["active_profile"])
    if act not in doc["profiles"] or not isinstance(doc["profiles"][act], dict):
        doc["profiles"][act] = default_profile_spec()
    if onboarding_completed is not None:
        doc["onboarding_completed"] = bool(onboarding_completed)
    if profile_patch:
        target_p = doc["profiles"][act]
        for k, v in profile_patch.items():
            if k == "tools" and isinstance(v, dict) and isinstance(target_p.get("tools"), dict):
                merged_t = dict(target_p["tools"])
                for tid, tspec in v.items():
                    if tspec is None:
                        merged_t.pop(tid, None)
                    elif isinstance(tspec, dict):
                        merged_t[tid] = {**(merged_t.get(tid) or {}), **tspec}
                target_p["tools"] = merged_t
            elif k == "done_check":
                target_p["done_check"] = normalize_done_check(v)
            else:
                target_p[k] = copy.deepcopy(v)
    if machine_patch:
        for mk, mv in machine_patch.items():
            if isinstance(mv, dict) and isinstance(doc["machine"].get(mk), dict):
                doc["machine"][mk].update(copy.deepcopy(mv))
            else:
                doc["machine"][mk] = copy.deepcopy(mv)
    return save_unlocked(base, doc, expected_rev=expected_rev, mirror_profile=mirror_profile)


def patch(
    state: Path | None = None,
    *,
    active_profile: str | None = None,
    onboarding_completed: bool | None = None,
    profile_patch: dict[str, Any] | None = None,
    machine_patch: dict[str, Any] | None = None,
    expected_rev: int | None = None,
    mirror_profile: bool = True,
) -> dict[str, Any]:
    """執行緒與跨行程安全的宣告式局部更新（保留所有未知鍵，同步鏡像 profile.json）。"""
    base = state if state is not None else statedir.state_dir()
    with kit_lock(base):
        return _patch_in_lock(
            base,
            active_profile=active_profile,
            onboarding_completed=onboarding_completed,
            profile_patch=profile_patch,
            machine_patch=machine_patch,
            expected_rev=expected_rev,
            mirror_profile=mirror_profile,
        )


def sync_profile_choice(state: Path, profile_name: str) -> None:
    """供 profiles.py --set / profile_new --apply / sync.py connect 統一寫入 active_profile。"""
    patch(
        state,
        active_profile=profile_name,
        onboarding_completed=(profile_name != "default") or load(state).get("onboarding_completed", False),
    )


# ---------- 三方漂移偵測（applied.json） ----------

def load_applied(state: Path | None = None) -> dict[str, Any]:
    base = state if state is not None else statedir.state_dir()
    p = applied_path(base)
    if not p.is_file():
        return {"files": {}, "profile": None, "snoozed": {}, "adopted": []}
    try:
        doc = json.loads(retry(p.read_bytes).decode("utf-8-sig"))
        if isinstance(doc, dict):
            doc.setdefault("files", {})
            doc.setdefault("profile", None)
            doc.setdefault("snoozed", {})
            doc.setdefault("adopted", [])
            return doc
    except (OSError, ValueError):
        pass
    return {"files": {}, "profile": None, "snoozed": {}, "adopted": []}


def save_applied(state: Path | None = None, applied: dict[str, Any] | None = None) -> None:
    base = state if state is not None else statedir.state_dir()
    doc = applied or {"files": {}, "profile": None, "snoozed": {}}
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write_bytes(applied_path(base), raw)


def _block_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        txt = path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError:
        return None
    m = profiles.BLOCK.search(txt)
    if not m:
        return "MISSING_BLOCK"
    norm = m.group(0).replace("\r\n", "\n").strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def managed_rule_targets(home: Path | None = None, state: Path | None = None) -> list[tuple[str, str, Path]]:
    h = home if home is not None else Path.home()
    s = state if state is not None else statedir.state_dir()
    cfg_p = s / "config.json"
    agents = ["claude-code", "codex", "antigravity"]
    if cfg_p.is_file():
        try:
            agents = json.loads(cfg_p.read_text(encoding="utf-8-sig")).get("agents") or agents
        except (OSError, ValueError):
            pass
    out: list[tuple[str, str, Path]] = []
    if "claude-code" in agents and (h / ".claude").is_dir():
        out.append(("rule:claude-code", "Claude Code 全域規則區塊（~/.claude/CLAUDE.md）", h / ".claude" / "CLAUDE.md"))
    if "codex" in agents and (h / ".codex").is_dir():
        out.append(("rule:codex", "Codex 全域規則區塊（~/.codex/AGENTS.md）", h / ".codex" / "AGENTS.md"))
    if "antigravity" in agents and (h / ".gemini").is_dir():
        out.append(("rule:antigravity-shared", "Antigravity 共用規則區塊（~/.gemini/AGENTS.md）", h / ".gemini" / "AGENTS.md"))
        out.append(("rule:antigravity-personal", "Antigravity 個人規則區塊（~/.gemini/GEMINI.md）", h / ".gemini" / "GEMINI.md"))
    return out


def record_applied_snapshot(
    state: Path | None = None,
    home: Path | None = None,
    *,
    preserve_keys: set[str] | None = None,
    reset_adopted: bool = False,
) -> dict[str, Any]:
    """記錄目前受管區塊與 profile 指紋至 applied.json；preserve_keys 內的目標保留舊指紋不覆蓋（供背景同步與保護外部手改用）。"""
    base = state if state is not None else statedir.state_dir()
    prev = load_applied(base)
    prev_files = prev.get("files") or {}
    keep = preserve_keys or set()
    kdoc = load(base)
    files_map: dict[str, str] = {}
    for key, _label, path in managed_rule_targets(home, base):
        if key in keep and key in prev_files:
            files_map[key] = prev_files[key]
            continue
        bh = _block_hash(path)
        if bh is not None:
            files_map[key] = bh
    updated = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "profile": kdoc.get("active_profile"),
        "kit_rev": kdoc.get("rev", 0),
        "files": files_map,
        "snoozed": {} if reset_adopted else (prev.get("snoozed") or {}),
        "adopted": [] if reset_adopted else list(prev.get("adopted") or []),
    }
    save_applied(base, updated)
    return updated


def detect_drift(state: Path | None = None, home: Path | None = None, *, today: str | None = None) -> list[dict[str, Any]]:
    """三方比對偵測外部手改漂移（背景 sync 遇有漂移的項目應略過覆寫）。"""
    base = state if state is not None else statedir.state_dir()
    h = home if home is not None else Path.home()
    today_iso = today or datetime.now().date().isoformat()
    kdoc = load(base)
    app = load_applied(base)
    snoozed = app.get("snoozed") or {}
    drifts: list[dict[str, Any]] = []

    # 1. 檢查 profile.json 與 kit.yaml 是否被外部改到不一致
    pfile_choice = profiles.chosen(base)
    if kdoc.get("_exists") and pfile_choice and pfile_choice != kdoc.get("active_profile"):
        did = "profile:active"
        if snoozed.get(did, "") <= today_iso:
            drifts.append({
                "id": did,
                "kind": "profile",
                "title": f"設定檔 profile.json 被外部改為「{pfile_choice}」（控制面板記的是「{kdoc.get('active_profile')}」）",
                "observed": pfile_choice,
                "expected": kdoc.get("active_profile"),
            })

    # 2. 檢查受管規則區塊是否與上次套用指紋不同
    recorded_files = app.get("files") or {}
    for key, label, path in managed_rule_targets(h, base):
        prev_hash = recorded_files.get(key)
        if not prev_hash:
            continue
        cur_hash = _block_hash(path)
        if cur_hash is not None and cur_hash != prev_hash:
            if snoozed.get(key, "") <= today_iso:
                detail = "受管區塊已被移除" if cur_hash == "MISSING_BLOCK" else "受管區塊內容被外部手動修改"
                drifts.append({
                    "id": key,
                    "kind": "rule_block",
                    "title": f"{label}：{detail}",
                    "path": str(path),
                    "observed": cur_hash,
                    "expected": prev_hash,
                })
    return drifts


def drifted_rule_keys(state: Path | None = None, home: Path | None = None) -> set[str]:
    """回傳目前所有被外部手改過、或使用者已按「採用外部修改 (adopted)」的規則目標 key（背景與一般前景同步皆不覆寫）。"""
    base = state if state is not None else statedir.state_dir()
    h = home if home is not None else Path.home()
    app = load_applied(base)
    recorded_files = app.get("files") or {}
    out: set[str] = {str(x) for x in (app.get("adopted") or []) if str(x).startswith("rule:")}
    for key, _label, path in managed_rule_targets(h, base):
        prev_hash = recorded_files.get(key)
        if not prev_hash:
            continue
        cur_hash = _block_hash(path)
        if cur_hash is not None and cur_hash != prev_hash:
            out.add(key)
    return out


def resolve_drift(
    drift_id: str,
    action: str,
    *,
    state: Path | None = None,
    home: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """處理漂移橫幅三選一：adopt（採用現況並持續保護）／restore（僅還原該目標成面板設定）／snooze（暫緩 7 天）。"""
    base = state if state is not None else statedir.state_dir()
    h = home if home is not None else Path.home()
    if action not in ("adopt", "restore", "snooze"):
        raise ValueError(f"不支援的漂移處理動作：{action}")

    with kit_lock(base):
        app = load_applied(base)
        if action == "snooze":
            until = (datetime.now().date() + timedelta(days=7)).isoformat()
            app.setdefault("snoozed", {})[drift_id] = until
            save_applied(base, app)
            return {"ok": True, "id": drift_id, "action": "snooze", "snoozed_until": until}

        if drift_id == "profile:active":
            pfile_choice = profiles.chosen(base) or "default"
            if action == "adopt":
                _patch_in_lock(base, active_profile=pfile_choice)
                record_applied_snapshot(base, h, preserve_keys=drifted_rule_keys(base, h))
                return {"ok": True, "id": drift_id, "action": "adopt", "active_profile": pfile_choice}
            kdoc = load(base)
            want_p = str(kdoc.get("active_profile") or "default")
            _patch_in_lock(base, active_profile=want_p)
            profiles.apply(repo_root / "data", base, wanted=want_p)
            record_applied_snapshot(base, h, preserve_keys=drifted_rule_keys(base, h))
            return {"ok": True, "id": drift_id, "action": "restore", "active_profile": want_p}

        if drift_id.startswith("rule:"):
            targets = {k: p for k, _, p in managed_rule_targets(h, base)}
            target_path = targets.get(drift_id)
            if action == "adopt":
                if target_path:
                    bh = _block_hash(target_path)
                    if bh:
                        app.setdefault("files", {})[drift_id] = bh
                adopted_set = set(app.get("adopted") or [])
                adopted_set.add(drift_id)
                app["adopted"] = sorted(adopted_set)
                app.get("snoozed", {}).pop(drift_id, None)
                save_applied(base, app)
                return {"ok": True, "id": drift_id, "action": "adopt"}

            # restore：僅單獨還原指定的這一個 Agent 規則檔，不連坐改寫其他家的手改區塊（修盲審 P1-2）
            kdoc = load(base)
            want_p = str(kdoc.get("active_profile") or "default")
            agent_for_key = {
                "rule:claude-code": "claude-code",
                "rule:codex": "codex",
                "rule:antigravity-shared": "antigravity",
                "rule:antigravity-personal": "antigravity",
            }.get(drift_id)
            if not agent_for_key:
                raise ValueError(f"未知的規則目標：{drift_id}")
            paths = {
                "claude-code": h / ".claude" / "CLAUDE.md",
                "codex": h / ".codex" / "AGENTS.md",
                "antigravity": h / ".gemini" / "GEMINI.md",
            }
            profiles.apply(repo_root / "data", base, paths=paths, wanted=want_p, agents=[agent_for_key], take_over=True)
            app["adopted"] = [x for x in (app.get("adopted") or []) if x != drift_id]
            app.get("snoozed", {}).pop(drift_id, None)
            if target_path:
                bh = _block_hash(target_path)
                if bh:
                    app.setdefault("files", {})[drift_id] = bh
            save_applied(base, app)
            return {"ok": True, "id": drift_id, "action": "restore"}

    raise ValueError(f"找不到漂移項目：{drift_id}")


# ---------- 工作台目錄、Context 預算與一鍵啟停 ----------

def infer_trust_badge(tool_doc: dict[str, Any]) -> dict[str, str]:
    explicit = tool_doc.get("trust")
    status = tool_doc.get("status") or "pending"
    if explicit == "builtin":
        return {"id": "builtin", "label": "內建防護"}
    if explicit == "custom" or tool_doc.get("private"):
        return {"id": "custom", "label": "本機自訂"}
    if explicit == "curated" or status in ("default", "trial", "on_demand"):
        return {"id": "curated", "label": "實測精選"}
    return {"id": "community", "label": "社群觀察"}


def infer_layer(tid: str, status: str) -> str:
    if tid in ("chrome-devtools-mcp", "gitleaks"):
        return "L1"
    if status == "trial":
        return "L4"
    if tid in DEFAULT_ENABLED_TOOLS and tid not in NEEDS_API_KEY:
        return "L2"
    return "L3"


def compute_context_budget(enabled_tool_ids: list[str] | set[str]) -> dict[str, Any]:
    """計算三家 Agent 開場常駐 Context token 估算與預算狀態。"""
    enabled = set(enabled_tool_ids)
    agents = ("claude-code", "codex", "antigravity")
    totals = {a: BUILTIN_COSTS["baseline_rules"][a] + BUILTIN_COSTS["core_skills"][a] for a in agents}
    for tid in enabled:
        cost = TOOL_COSTS.get(tid)
        if cost:
            for a in agents:
                totals[a] += int(cost.get(a, 0))
    summary = {}
    for a in agents:
        tok = totals[a]
        pct = round((tok / CONTEXT_WINDOW_REF) * 100, 2)
        level = "danger" if tok >= DANGER_TOKENS else ("warn" if tok >= WARN_TOKENS else "ok")
        summary[a] = {
            "tokens": tok,
            "percent_of_200k": pct,
            "level": level,
            "warn_at": WARN_TOKENS,
            "danger_at": DANGER_TOKENS,
        }
    return summary


def build_workbench_catalog(
    state: Path | None = None,
    data_dir: Path | None = None,
    *,
    project_files: list[str] | None = None,
) -> dict[str, Any]:
    """整合名冊與 kit.yaml 狀態，產出前端工作台商店與開箱精靈需要的精選卡片清單。"""
    base = state if state is not None else statedir.state_dir()
    ddir = data_dir if data_dir is not None else (ROOT / "data")
    import validate as validate_mod

    _errs, roster = validate_mod.check(ddir, state=base, private=True)
    kdoc = load(base)
    act = str(kdoc.get("active_profile") or "default")
    pspec = (kdoc.get("profiles") or {}).get(act) or default_profile_spec()
    tool_choices: dict[str, dict[str, Any]] = pspec.get("tools") or {}

    slots_by_id = {s["id"]: s for s in roster.get("slots") or []}
    pfiles = {f.lower() for f in (project_files or [])}
    has_web_files = bool(pfiles & {"package.json", "vite.config.ts", "vite.config.js", "next.config.js", "index.html", "tsconfig.json"})
    has_py_files = bool(pfiles & {"pyproject.toml", "requirements.txt", "setup.py"})

    items: list[dict[str, Any]] = []
    enabled_ids: list[str] = []
    for tid, doc in sorted((roster.get("tools") or {}).items()):
        st = str(doc.get("status") or "pending")
        if st not in ("default", "trial", "on_demand"):
            continue
        layer = infer_layer(tid, st)
        choice = tool_choices.get(tid)
        if isinstance(choice, dict) and choice.get("tier"):
            tier = str(choice["tier"])
        else:
            tier = "resident" if tid in DEFAULT_ENABLED_TOOLS and tid not in NEEDS_API_KEY else "disabled"
        enabled = tier in ("resident", "on_demand")
        if enabled:
            enabled_ids.append(tid)

        rec_reason = ""
        if tid in ("frontend-design", "impeccable", "chrome-devtools-mcp") and has_web_files:
            rec_reason = "偵測到前端專案檔案（package.json／HTML）"
        elif tid in ("gitleaks", "claude-code-setup") and (has_web_files or has_py_files):
            rec_reason = "偵測到程式碼專案，建議啟用"

        costs = TOOL_COSTS.get(tid) or {"claude-code": 0, "codex": 0, "antigravity": 0}
        mech = resolve_install_mechanism(tid, doc)
        raw_works = doc.get("works_with") or ["claude", "codex", "antigravity"]
        items.append({
            "id": tid,
            "name": doc.get("name") or tid,
            "kind": doc.get("kind") or "tool",
            "status": st,
            "layer": layer,
            "tier": tier,
            "enabled": enabled,
            "default_checked": tid in DEFAULT_ENABLED_TOOLS and tid not in NEEDS_API_KEY,
            "needs_key": NEEDS_API_KEY.get(tid),
            "trust": infer_trust_badge(doc),
            "works_with": raw_works,
            "compatible_agents": normalize_agent_ids(raw_works),
            "has_plugin": bool(doc.get("plugin")),
            "install_mode": mech["mode"],
            "install_badge": mech["badge"],
            "manual_hint": mech["manual_hint"],
            "slot_names": [slots_by_id[s]["name"] for s in (doc.get("slots") or []) if s in slots_by_id],
            "summary": doc.get("reason") or "",
            "trigger_when": doc.get("trigger_when") or "",
            "trial_until": doc.get("trial_until") or "",
            "url": doc.get("url") or "",
            "context_cost": costs,
            "recommended_reason": rec_reason,
        })

    layer_order = {"L1": 0, "L2": 1, "L3": 2, "L4": 3}
    items.sort(key=lambda x: (layer_order.get(x["layer"], 9), 0 if x["enabled"] else 1, x["name"].lower()))
    return {
        "active_profile": act,
        "rev": kdoc.get("rev", 0),
        "onboarding_completed": bool(kdoc.get("onboarding_completed")),
        "done_check": normalize_done_check(pspec.get("done_check", "log")),
        "presets": list(GOAL_PRESETS.values()),
        "items": items,
        "budget": compute_context_budget(enabled_ids),
    }


def apply_tool_toggle(
    tool_id: str,
    tier: str,
    *,
    state: Path | None = None,
    home: Path | None = None,
    repo_root: Path = ROOT,
    runner=None,
) -> dict[str, Any]:
    """更新 kit.yaml 內的單項工具狀態，並實際對本機已安裝的 Agent 同步啟用或停用（指向本機鎖定版本 marketplace）。"""
    if tier not in ("resident", "on_demand", "disabled"):
        raise ValueError(f"不合法的 tier：{tier}")
    clean_tid = str(tool_id or "").strip()
    if not profiles.NAME.match(clean_tid):
        raise ValueError(f"不合法的工具代號：{tool_id!r}")
    tool_id = clean_tid
    base = state if state is not None else statedir.state_dir()
    h = home if home is not None else Path.home()
    ddir = repo_root / "data"
    tool_file = ddir / "tools" / f"{tool_id}.yaml"
    if not tool_file.is_file():
        raise FileNotFoundError(f"名冊找不到工具：{tool_id}")
    tdoc = yaml.safe_load(tool_file.read_text(encoding="utf-8")) or {}
    if tier != "disabled" and tool_id in NEEDS_API_KEY:
        key_env = NEEDS_API_KEY[tool_id]
        if not os.environ.get(key_env):
            return {
                "ok": False,
                "deferred": True,
                "tool_id": tool_id,
                "message": f"{tdoc.get('name', tool_id)} 需要先設定環境變數 {key_env}（安全底線禁止明文寫入設定檔），已先維持關閉。",
            }

    mech = resolve_install_mechanism(tool_id, tdoc)
    updated_kit = patch(base, profile_patch={"tools": {tool_id: {"tier": tier}}})
    enable = tier in ("resident", "on_demand")
    actions: list[str] = []
    warnings: list[str] = []

    def _exec(cmd: list[str], env_extra: dict[str, str] | None = None, timeout: int = 180) -> tuple[int, str, str]:
        if runner is not None:
            return runner(cmd, env_extra or {})
        merged_env = dict(os.environ)
        if os.path.normcase(str(h.resolve())) != os.path.normcase(str(Path.home().resolve())):
            merged_env["USERPROFILE"] = str(h)
            merged_env["HOME"] = str(h)
        if env_extra:
            merged_env.update(env_extra)
        kw: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": timeout,
            "stdin": subprocess.DEVNULL,
            "env": merged_env,
        }
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(cmd, check=False, **kw)
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except (OSError, subprocess.SubprocessError) as exc:
            return 127, "", str(exc)

    # 1. 若是 servers.yaml 管理的內建 MCP（如 chrome-devtools-mcp -> chrome_devtools），同步免問核准與實際 MCP server 啟停
    if tool_id == "chrome-devtools-mcp":
        edition.record(base, "chrome_devtools", enable)
        actions.append(f"chrome_devtools 免問核准與 MCP 狀態已設為 {'開啟' if enable else '停用並移除'}")
        if not enable:
            codex_exe_m = shutil.which("codex") or ("codex" if runner is not None else None)
            if codex_exe_m:
                found_homes_m = homes.discover(h)
                for xdir in [h / ".codex", *[f.path for f in found_homes_m if f.agent == "codex" and f.writable]]:
                    if xdir.is_dir():
                        _exec([codex_exe_m, "mcp", "remove", "chrome_devtools"], {"CODEX_HOME": str(xdir)})

    # 2. 若工具卡帶有 plugin 宣告，透過本機鎖定版本目錄（~/.omnikit/current 或 repo_root）對全部設定目錄啟停
    plug_spec = tdoc.get("plugin") or {}
    cfg_doc = yaml.safe_load((ddir / "omnikit.yaml").read_text(encoding="utf-8")) or {}
    mkt_name = str(cfg_doc.get("marketplace") or "omnikit-b40609")
    plug_name = str(plug_spec.get("name") or tool_id)
    plugin_id = f"{plug_name}@{mkt_name}"
    local_mkt = (base / "current") if ((base / "current" / ".claude-plugin" / "marketplace.json").is_file()) else repo_root

    attempted_cli = 0
    if "claude" in plug_spec and tdoc.get("status") == "default":
        claude_exe = shutil.which("claude") or ("claude" if runner is not None else None)
        if claude_exe:
            found_homes = homes.discover(h)
            cdirs = [h / ".claude", *[f.path for f in found_homes if f.agent == "claude-code" and f.writable]]
            for cdir in cdirs:
                if not cdir.is_dir():
                    continue
                attempted_cli += 1
                cenv = {} if os.path.normcase(str(cdir.resolve())) == os.path.normcase(str((h / ".claude").resolve())) else {"CLAUDE_CONFIG_DIR": str(cdir)}
                if enable:
                    _exec([claude_exe, "plugin", "marketplace", "add", str(local_mkt), "--scope", "user"], cenv)
                    rc_i, _, err_i = _exec([claude_exe, "plugin", "install", plugin_id, "--scope", "user"], cenv)
                    if rc_i == 0:
                        _exec([claude_exe, "plugin", "enable", plugin_id, "--scope", "user"], cenv)
                        actions.append(f"Claude（{cdir.name}）已安裝並啟用 {plugin_id}")
                    else:
                        warnings.append(f"Claude（{cdir.name}）暫無法安裝 {plugin_id}（待連網或稍後重試）：{err_i.strip()[:120]}")
                else:
                    rc_d, _, _ = _exec([claude_exe, "plugin", "disable", plugin_id, "--scope", "user"], cenv)
                    if rc_d == 0:
                        actions.append(f"Claude（{cdir.name}）已停用 {plugin_id}")

    if "codex" in plug_spec and tdoc.get("status") == "default":
        codex_exe = shutil.which("codex") or ("codex" if runner is not None else None)
        if codex_exe:
            found_homes = homes.discover(h)
            xdirs = [h / ".codex", *[f.path for f in found_homes if f.agent == "codex" and f.writable]]
            for xdir in xdirs:
                if not xdir.is_dir():
                    continue
                attempted_cli += 1
                xenv = {"CODEX_HOME": str(xdir)}
                if enable:
                    _exec([codex_exe, "plugin", "marketplace", "add", str(local_mkt)], xenv)
                    rc_x, _, err_x = _exec([codex_exe, "plugin", "add", plugin_id], xenv)
                    if rc_x == 0:
                        actions.append(f"Codex（{xdir.name}）已啟用 {plugin_id}")
                    else:
                        warnings.append(f"Codex（{xdir.name}）略過遠端安裝（{err_x.strip()[:100] or '待連網'}）")
                else:
                    rc_rx, _, _ = _exec([codex_exe, "plugin", "remove", plugin_id], xenv)
                    if rc_rx == 0:
                        actions.append(f"Codex（{xdir.name}）已停用 {plugin_id}")

    if mech["mode"] == "manual" and enable:
        actions.append(f"已在設定檔記錄偏好：{tdoc.get('name', tool_id)}（手動安裝指令：{mech['manual_hint']}）")

    cli_all_failed = bool(mech["mode"] == "auto_plugin" and attempted_cli > 0 and not actions and warnings)
    return {
        "ok": not cli_all_failed,
        "deferred": bool(warnings and not actions),
        "tool_id": tool_id,
        "tier": tier,
        "install_mode": mech["mode"],
        "manual_hint": mech["manual_hint"],
        "rev": updated_kit.get("rev", 0),
        "actions": actions,
        "warnings": warnings,
        **({"message": warnings[0]} if cli_all_failed else {}),
    }


def init_workbench(state: Path | None = None, *, repo_root: Path = ROOT) -> list[str]:
    """安裝時初始化或刷新 kit.yaml 與預設免金鑰精選工具，且在未選 profile 時保留首次破冰引導狀態。"""
    base = state if state is not None else statedir.state_dir()
    warns: list[str] = []
    if not kit_path(base).is_file():
        prof = profiles.chosen(base) or "default"
        patch(base, active_profile=prof, onboarding_completed=(prof != "default"))
        for tid in DEFAULT_ENABLED_TOOLS:
            try:
                res = apply_tool_toggle(tid, "resident", state=base, repo_root=repo_root)
                warns.extend(res.get("warnings") or [])
            except Exception as exc:  # noqa: BLE001
                warns.append(f"{tid}: {exc}")
    record_applied_snapshot(base)
    return warns


def export_bundle(state: Path | None = None) -> dict[str, Any]:
    """匯出安全的純名冊 ID 工作台設定包（盲審 P2-3：絕不含遠端網址、shell 指令、sha 或私人路徑）。"""
    base = state if state is not None else statedir.state_dir()
    kdoc = load(base)
    act = str(kdoc.get("active_profile") or "default")
    pspec = (kdoc.get("profiles") or {}).get(act) or default_profile_spec()
    safe_tools = {
        tid: {"tier": str(spec.get("tier") or "disabled")}
        for tid, spec in (pspec.get("tools") or {}).items()
        if isinstance(spec, dict) and profiles.NAME.match(str(tid))
    }
    return {
        "omnikit_bundle": 1,
        "exported_at": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "preset": [p for p in (pspec.get("preset") or []) if isinstance(p, str)],
        "done_check": normalize_done_check(pspec.get("done_check", "log")),
        "tools": safe_tools,
    }


# ---------- 自我測試 ----------

def selftest() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    fails: list[str] = []

    def check(label: str, cond: bool) -> None:
        print(f"{'通過' if cond else '失敗'}：{label}")
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        state = root / "state"
        state.mkdir(parents=True)
        home = root / "home"
        (home / ".claude").mkdir(parents=True)
        (home / ".claude-kai").mkdir(parents=True)
        (home / ".codex").mkdir(parents=True)
        (state / "config.json").write_text(json.dumps({"agents": ["claude-code", "codex"]}), encoding="utf-8")

        # 1. 純讀取不寫檔（盲審 P0-4：-WhatIf 零副作用）
        d0 = load(state)
        check("load() 在 kit.yaml 不存在時純讀取不寫檔、rev=0",
              not kit_path(state).exists() and d0["rev"] == 0 and d0["active_profile"] == "default")

        # 1b. init_workbench 在全新環境建立 kit.yaml 但不誤寫 profile.json，確保首次破冰引導不被鎖死
        init_state = root / "init_state"
        init_state.mkdir(parents=True)
        (init_state / "config.json").write_text(json.dumps({"agents": []}), encoding="utf-8")
        init_workbench(init_state, repo_root=ROOT)
        d_init = load(init_state)
        check("init_workbench 建立預設 kit.yaml（onboarding_completed=False）且不誤寫 profile.json",
              kit_path(init_state).is_file()
              and d_init["onboarding_completed"] is False
              and not (init_state / "profile.json").exists()
              and profiles.onboarding_active(init_state, "default") is True)

        # 2. patch 寫入、鏡像 profile.json、保留未知鍵與樂觀鎖
        d1 = patch(state, active_profile="alice", onboarding_completed=True, profile_patch={"custom_unknown_flag": 42})
        pjson = json.loads((state / "profile.json").read_text(encoding="utf-8"))
        check("patch() 建立 kit.yaml（rev=1）並原子鏡像寫出 profile.json",
              kit_path(state).is_file() and d1["rev"] == 1 and pjson["profile"] == "alice")

        d2 = patch(state, expected_rev=1, machine_patch={"server": {"port": 3782}})
        check("patch() expected_rev 正確時遞增 rev=2 且保留未知鍵 custom_unknown_flag",
              d2["rev"] == 2 and d2["profiles"]["alice"]["custom_unknown_flag"] == 42
              and d2["machine"]["server"]["port"] == 3782)

        conflict = False
        try:
            patch(state, expected_rev=1, active_profile="bob")
        except RevConflictError:
            conflict = True
        check("patch() expected_rev 過期時拋出 RevConflictError 樂觀鎖保護", conflict)

        # 3. 三方漂移偵測與暫緩／採用
        claude_md = home / ".claude" / "CLAUDE.md"
        claude_md.write_text(f"{profiles.BEGIN}\n@baseline\n{profiles.END}\n", encoding="utf-8")
        record_applied_snapshot(state, home)
        check("剛套用完畢時 detect_drift 為空", detect_drift(state, home) == [])

        claude_md.write_text(f"{profiles.BEGIN}\n@baseline\n@hand-edited\n{profiles.END}\n", encoding="utf-8")
        drifts = detect_drift(state, home)
        check("使用者外部手改 CLAUDE.md 受管區塊後，detect_drift 精準抓出漂移且 drifted_rule_keys 含 rule:claude-code",
              len(drifts) == 1 and drifts[0]["id"] == "rule:claude-code" and "rule:claude-code" in drifted_rule_keys(state, home))

        resolve_drift("rule:claude-code", "snooze", state=state, home=home)
        check("漂移選 snooze 後 7 天內橫幅隱藏，但 drifted_rule_keys 仍保護不讓背景覆寫",
              detect_drift(state, home) == [] and "rule:claude-code" in drifted_rule_keys(state, home))

        resolve_drift("rule:claude-code", "adopt", state=state, home=home)
        check("漂移選 adopt 後橫幅不再告警，且 drifted_rule_keys 持續保護 adopted 手改不被覆寫",
              detect_drift(state, home) == [] and "rule:claude-code" in drifted_rule_keys(state, home))

        # 4. 多目錄 Claude plugin 同步啟用與停用（盲審 P1-9）
        t3_s = home / ".t3" / "userdata" / "settings.json"
        t3_s.parent.mkdir(parents=True)
        t3_s.write_text(json.dumps({"providerInstances": {"kai": {"driver": "claudeAgent", "config": {"homePath": str(home / ".claude-kai")}}}}), encoding="utf-8")
        seen_cmds: list[tuple[list[str], str | None]] = []

        def fake_run(cmd: list[str], env_map: dict[str, str]):
            seen_cmds.append((cmd[:4], env_map.get("CLAUDE_CONFIG_DIR")))
            return 0, "ok", ""

        res_on = apply_tool_toggle("frontend-design", "resident", state=state, home=home, repo_root=ROOT, runner=fake_run)
        seen_cmds.clear()
        res_off = apply_tool_toggle("frontend-design", "disabled", state=state, home=home, repo_root=ROOT, runner=fake_run)
        check("apply_tool_toggle 停用時對主目錄與額外設定目錄（.claude-kai）皆執行 plugin disable",
              res_on["ok"] and res_off["ok"]
              and any(Path(c[0][0]).stem.lower().startswith("claude") and c[0][1:3] == ["plugin", "disable"] and c[1] is None for c in seen_cmds)
              and any(Path(c[0][0]).stem.lower().startswith("claude") and c[0][1:3] == ["plugin", "disable"] and c[1] == str(home / ".claude-kai") for c in seen_cmds))

        # 5. Context 預算與安全匯出 Bundle（盲審 P2-1、P2-3）
        cat = build_workbench_catalog(state, ROOT / "data", project_files=["package.json"])
        bundle = export_bundle(state)
        check("build_workbench_catalog 含精選工具、預算數字與前端專案自動推薦標記，且 export_bundle 不含指令或網址",
              len(cat["items"]) >= 8 and cat["budget"]["claude-code"]["tokens"] > 0
              and any(i["recommended_reason"] for i in cat["items"])
              and "url" not in json.dumps(bundle))

        # 6. kit.yaml 損壞時寫入前自動備份 .bak，且無引號 done_check: off 解析為 "off"（修 M-P1-11、Opus P2-7）
        kit_path(state).write_text("active_profile: alice\nprofiles:\n  alice:\n    done_check: off\n", encoding="utf-8")
        check("無引號 done_check: off（YAML False）正規化為 'off'", load(state)["profiles"]["alice"]["done_check"] == "off")

        kit_path(state).write_text("active_profile: [\n", encoding="utf-8")
        patch(state, active_profile="alice")
        bak = Path(f"{kit_path(state)}.bak")
        check("損壞的 kit.yaml 在下次寫入前自動備份為 kit.yaml.bak", bak.is_file() and "active_profile: [" in bak.read_text(encoding="utf-8"))

    print(f"\n{'kit.py selftest：全部通過' if not fails else f'kit.py selftest：{len(fails)} 項失敗'}")
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="OmniKit 單一事實來源（kit.yaml）與工作台套件管理")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--state-dir", help="覆寫狀態資料夾路徑")
    parser.add_argument("--repo-root", help="覆寫 repo 根目錄路徑")
    sub = parser.add_subparsers(dest="cmd")

    p_show = sub.add_parser("show")
    p_show.add_argument("--json", action="store_true")

    p_chk = sub.add_parser("check")
    p_chk.add_argument("--json", action="store_true")

    p_sp = sub.add_parser("set-profile")
    p_sp.add_argument("name")

    p_tg = sub.add_parser("toggle")
    p_tg.add_argument("tool_id")
    p_tg.add_argument("--tier", choices=("resident", "on_demand", "disabled"), required=True)
    p_tg.add_argument("--json", action="store_true")

    p_dr = sub.add_parser("drift")
    p_dr.add_argument("--resolve")
    p_dr.add_argument("--action", choices=("adopt", "restore", "snooze"))
    p_dr.add_argument("--json", action="store_true")

    p_dm = sub.add_parser("dump")
    p_dm.add_argument("--out")

    sub.add_parser("init-workbench")

    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()

    state = Path(args.state_dir) if args.state_dir else statedir.state_dir()
    repo_root = Path(args.repo_root) if args.repo_root else ROOT

    if args.cmd == "init-workbench":
        warns = init_workbench(state, repo_root=repo_root)
        for w in warns[:5]:
            print(f"[提示] {w}", file=sys.stderr)
        return 0
    if args.cmd == "show":
        cat = build_workbench_catalog(state, ROOT / "data")
        if args.json:
            print(json.dumps(cat, ensure_ascii=False, indent=2))
        else:
            print(f"目前設定（profile）：{cat['active_profile']}（rev {cat['rev']}）")
            for a, b in cat["budget"].items():
                print(f"  開場額度估算 [{a}]：{b['tokens']} tokens（約 {b['percent_of_200k']}%，狀態：{b['level']}）")
            for item in cat["items"]:
                mark = "✓ 已啟用" if item["enabled"] else "· 未啟用"
                print(f"  {mark} [{item['layer']}] {item['name']} ({item['id']}) — {item['trust']['label']}")
        return 0

    if args.cmd == "check":
        drifts = detect_drift(state)
        cat = build_workbench_catalog(state, ROOT / "data")
        payload = {"ok": len(drifts) == 0, "drifts": drifts, "budget": cat["budget"]}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if not drifts:
                print("設定一致：無外部手改漂移。")
            for d in drifts:
                print(f"漂移：{d['title']}（id={d['id']}）")
        return 0 if not drifts else 1

    if args.cmd == "set-profile":
        sync_profile_choice(state, args.name)
        print(f"已更新 kit.yaml active_profile 為：{args.name}")
        return 0

    if args.cmd == "toggle":
        res = apply_tool_toggle(args.tool_id, args.tier, state=state, repo_root=ROOT)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            for a in res.get("actions") or []:
                print(a)
            for w in res.get("warnings") or []:
                print(f"提示：{w}")
            if res.get("message"):
                print(res["message"])
        return 0 if res.get("ok") else 1

    if args.cmd == "drift":
        if args.resolve and args.action:
            res = resolve_drift(args.resolve, args.action, state=state, repo_root=ROOT)
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"已處理漂移 {args.resolve}：{args.action}")
            return 0
        drifts = detect_drift(state)
        if args.json:
            print(json.dumps(drifts, ensure_ascii=False, indent=2))
        else:
            print(f"偵測到 {len(drifts)} 項外部手改漂移")
            for d in drifts:
                print(f"  - [{d['id']}] {d['title']}")
        return 0

    if args.cmd == "dump":
        b = export_bundle(state)
        txt = json.dumps(b, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            Path(args.out).write_text(txt, encoding="utf-8")
            print(f"已匯出工作台設定包：{args.out}")
        else:
            print(txt, end="")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
