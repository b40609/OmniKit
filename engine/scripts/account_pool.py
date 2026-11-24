# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""帳號池狀態機、錯誤分類、多帳號額度視圖、選帳號與接手順序（帳號池第二階段，docs/proposals/2026-11-23-account-pool.md）。

設計原則（對應提案第三、四、八節）：
- 設定是資料（profile 的 dispatch.md）、狀態另存本機（~/.omnikit/dispatch/pool-state.json，可刪重建、不進 git、絕不存 token）。
- 正交狀態維度互不覆寫：paused、auth_expired、validation_required、tos_banned、hard_forbidden、forbidden_models、cooldowns。
- 控制面查額度回 200 絕不清除 tos_banned、hard_forbidden、validation_required、auth_expired、paused
  （Antigravity 被封帳號查額度仍回 200，只有資料面真正對話才會回 403 TOS_VIOLATION）。
- 查不到最新額度時保留上次快照並標 stale: true，絕不當成 0% 或 100%。
- 頂層只匯入 Python 標準庫（不匯入 pyyaml），讓 session_nudge.py 等 hook 路徑可直接呼叫 due_alert，零額外負擔。

用法：
  uv run engine/scripts/account_pool.py status [--json]                          所有帳號的健康狀態、冷卻與未解決警示
  uv run engine/scripts/account_pool.py usage [--refresh-agy] [--json]           多目錄 Claude 快照＋Antigravity 額度視圖
  uv run engine/scripts/account_pool.py failover [--purpose general|cross_review_claude] [--json]
                                                                                 額度用完的接手順序（依 on_exhausted 與狀態）
  uv run engine/scripts/account_pool.py select-claude [--strategy ...] [--persist] [--json]
  uv run engine/scripts/account_pool.py set-claude-quota --instance <id> [--weekly-used <0-100>] [--weekly-resets-at <ISO>]
                                        [--weekday mon..sun --hour-utc <0-23>] [--five-hour-used <0-100>] [--clear]
                                                                                 T3 與狀態列都沒有時，手動登記剩餘額度與重置日
                                                                                 依策略（weekly-first＋黏著＋防震盪）挑 Claude 實例
  uv run engine/scripts/account_pool.py record-error --instance <id> (--kind <類別> | --text <訊息>)
        [--driver <driver>] [--model <模型>] [--resets-at <時間>] [--url <https://...>] [--note <文字>]
  uv run engine/scripts/account_pool.py record-ok --instance <id> [--driver <driver>] [--model <模型>]
  uv run engine/scripts/account_pool.py pause --instance <id> [--reason <原因>]
  uv run engine/scripts/account_pool.py unpause --instance <id>
  uv run engine/scripts/account_pool.py clear --instance <id> [--dimension <維度>] [--force]
  uv run engine/scripts/account_pool.py alerts [--notify none|hook|desktop|webhook] [--json]
  uv run engine/scripts/account_pool.py classify --text <錯誤訊息> [--status <HTTP 碼>] [--model <模型>] [--json]
  uv run engine/scripts/account_pool.py --selftest
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ERROR_KINDS = (
    "rate_limit",
    "quota_exhausted",
    "auth_expired",
    "validation_required",
    "tos_banned",
    "hard_forbidden",
    "model_forbidden",
    "timeout_15min",
    "other",
)
ON_EXHAUSTED_MODES = ("fail_closed", "prompt_manual_switch", "fallback_paid_api")
THINKING_PREFS = ("max_available", "balanced", "economy", "custom")
ACCOUNT_STRATEGIES = ("weekly-first", "least-used", "sticky", "priority")
NOTIFY_MODES = ("none", "hook", "desktop", "webhook")
DIMENSIONS = ("paused", "auth_expired", "validation_required", "tos_banned", "hard_forbidden", "forbidden_models", "cooldowns")

BUCKET_NAMES = {
    "gemini": "Gemini Models",
    "argon": "Gemini 4 Argon",
    "carbon": "Gemini Carbon",
    "3p": "Claude and GPT models",
    "default": "帳號額度",
}

LEVEL_SUFFIX = re.compile(r"-(low|medium|high|xhigh|max)$")
HTTPS_URL = re.compile(r"https://[^\s\"'<>()\[\]{}]+")
ISO_TS = re.compile(r"\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))\b")
SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bya29\.[A-Za-z0-9._-]{10,}"),
    re.compile(r'(?i)(refresh_token|access_token|api_key|password|secret)["\']?\s*[:=]\s*["\']?[^\s"\',}]{6,}'),
)

HYSTERESIS_PP = 5.0          # 防震盪：剩餘額度領先超過 5 個百分點才切
SWITCH_COOLDOWN_SEC = 300    # 防震盪：切完至少隔 5 分鐘再切
HEADROOM_FLOOR_PP = 10.0     # 原帳號剩餘低於此門檻時不受防震盪綁住
WEEKLY_EARLIER_SEC = 3600    # weekly-first：重置早於原帳號超過 1 小時才視為明顯更早
EXPIRING_SOON_SEC = 48 * 3600  # weekly-first：距每週重置不到 48 小時、還沒用完的帳號最優先（快過期的額度先燒完）
BACKOFF_BASE_SEC = 30        # 無重置時間時的 429 起始冷卻秒數
BACKOFF_MAX_SEC = 1800       # 指數退避上限：30 分鐘（參考 Subpool）
CLAUDE_STALE_HOURS = 12      # Claude 快照超過 12 小時標 stale
AGY_STALE_HOURS = 2          # Antigravity 快照超過 2 小時標 stale
ALERT_REPEAT_HOURS = 24      # 同一異常 24 小時內只透過 hook 提醒一次


# ---------- 時間與安全工具 ----------

def utc_now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, (int, float)):
        return datetime.fromtimestamp(now, timezone.utc)
    return now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)


def iso_utc(dt):
    return utc_now(dt).isoformat(timespec="seconds")


def parse_ts(val):
    """ISO8601 字串或 unix epoch → UTC datetime；讀不懂回 None。"""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(float(val), timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    s = str(val).strip()
    if s.isdigit():
        return parse_ts(int(s))
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fmt_remain(until_dt, now_dt):
    secs = max(0, int((until_dt - now_dt).total_seconds()))
    if secs < 60:
        return f"{secs} 秒"
    mins = secs // 60
    if mins < 60:
        return f"{mins} 分鐘"
    hours, rem_m = divmod(mins, 60)
    if hours < 24:
        return f"{hours} 小時 {rem_m} 分" if rem_m else f"{hours} 小時"
    days, rem_h = divmod(hours, 24)
    return f"{days} 天 {rem_h} 小時" if rem_h else f"{days} 天"


def fmt_local(dt):
    if dt is None:
        return "未知"
    return dt.astimezone().strftime("%m-%d %H:%M")


def sanitize(text, limit=240):
    """清理錯誤文字：遮罩疑似 token／金鑰並壓成單行短字串，絕不寫進 state 或 log。"""
    s = " ".join(str(text or "").split())
    for pat in SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    return s[:limit] + ("…" if len(s) > limit else "")


def safe_https_url(url):
    if not url:
        return None
    m = HTTPS_URL.search(str(url))
    if not m:
        return None
    clean = m.group(0).rstrip(".,;:")
    return clean if len(clean) <= 500 else None


def norm_model(model):
    return LEVEL_SUFFIX.sub("", (model or "").strip().lower())


def bucket_of(driver=None, model=None):
    """模型對應的額度桶（依 T3 summaryWindows 與 agy /usage 一手實測）。"""
    m = norm_model(model)
    if driver == "antigravity" or (driver is None and m.startswith(("gemini-", "gpt-oss-"))):
        if m.startswith(("claude-", "gpt-")):
            return "3p"
        if "argon" in m or "g1-pro" in m:
            return "argon"
        if "carbon" in m:
            return "carbon"
        return "gemini"
    return "default"


def norm_dir(path):
    """統一目錄路徑鍵：Windows 忽略大小寫與斜線方向，避免同一個帳號記成兩筆。"""
    p = Path(path)
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p.absolute()
    return os.path.normcase(str(resolved))


# ---------- 錯誤分類器 ----------

def _extract_retry_seconds(text):
    low = text.lower()
    # 先抓 Antigravity 常見的複合相對時間（例如 "Resets in 33m32s"、"Resets in 1h20m15s"）
    m_comp = re.search(
        r"(?:try again|retry|reset(?:s)?)\s+in\s+(?:(\d+)\s*h(?:ours?|rs?)?\s*)?(?:(\d+)\s*m(?:inutes?|ins?)?\s*)?(?:(\d+)\s*s(?:econds?|ecs?)?)?(?:\b|(?=\.))",
        low,
    )
    if m_comp and any(m_comp.groups()):
        h = int(m_comp.group(1) or 0)
        mn = int(m_comp.group(2) or 0)
        s = int(m_comp.group(3) or 0)
        total = h * 3600 + mn * 60 + s
        if total > 0:
            return total
    m = re.search(r"retry[- ]?after\s*[:=]?\s*(\d+)\s*(s|sec|seconds|m|min|minutes|h|hr|hours)?\b", low)
    if m:
        n, unit = int(m.group(1)), (m.group(2) or "s")
        return n * (3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1)
    return None


def classify_error(text, status_code=None, model=None, now=None):
    """把供應商／T3／CLI 的錯誤原文分類成正交狀態種類。回傳 dict，不含敏感資訊。"""
    now_dt = utc_now(now)
    raw = str(text or "")
    low = raw.lower()
    code = int(status_code) if status_code is not None else None
    if code is None:
        m = re.search(r"\b(?:http|status|code|error)?\s*(401|403|429|5\d\d)\b", low)
        if m:
            code = int(m.group(1))
    url = safe_https_url(raw)
    iso_m = ISO_TS.search(raw)
    retry_sec = _extract_retry_seconds(raw)
    resets_at = None
    if iso_m and parse_ts(iso_m.group(1)):
        resets_at = iso_utc(parse_ts(iso_m.group(1)))
    elif retry_sec is not None:
        resets_at = iso_utc(now_dt + timedelta(seconds=retry_sec))
    summary = sanitize(raw)

    if "sent nothing for 15 minutes" in low or "promptinactivitytimeout" in low:
        return {"kind": "timeout_15min", "retry_same": True, "url": None, "resets_at": None,
                "model": norm_model(model) or None, "summary": summary,
                "advice": "先檢查交付檔與 .done 標記，東西都在就照常驗收，不要直接重派"}

    # TOS 封禁（排除純 GCP 專案級 SERVICE_DISABLED）
    if ("tos_violation" in low or "account_banned" in low or "account has been suspended" in low
            or "service has been disabled in this account" in low or "terms of service violation" in low):
        return {"kind": "tos_banned", "retry_same": False, "url": url, "resets_at": None,
                "model": norm_model(model) or None, "summary": summary,
                "advice": "帳號被標記停權，永久移出可用池（不被 200 額度查詢覆寫）；有申訴連結請人工處理"}

    # 真人驗證鎖（不誤判成永久封禁）
    if ("validation_required" in low or "validation_url" in low or "verify your account" in low
            or "human verification" in low or "account verification required" in low):
        return {"kind": "validation_required", "retry_same": False, "url": url, "resets_at": resets_at,
                "model": norm_model(model) or None, "summary": summary,
                "advice": "需要本人點驗證連結解鎖，不當作永久封禁"}

    # 地區／出口限制
    if ("location not supported" in low or "region is not supported" in low
            or "not available in your country" in low or "unsupported_country" in low):
        return {"kind": "hard_forbidden", "retry_same": False, "url": url, "resets_at": None,
                "model": norm_model(model) or None, "summary": summary,
                "advice": "地區或網路出口不支援（403），維持隔離"}

    # 401／認證過期
    if (code == 401 or "invalid_grant" in low or "token expired" in low or "unauthenticated" in low
            or "login required" in low or "not logged in" in low or "session expired" in low
            or "authentication_error" in low or "re-authenticate" in low):
        return {"kind": "auth_expired", "retry_same": False, "url": url, "resets_at": None,
                "model": norm_model(model) or None, "summary": summary,
                "advice": "登入過期或權杖失效（401），移出可用池，請重新登入"}

    # 403 特定模型無權限
    if ((code == 403 or "permission_denied" in low or "forbidden" in low)
            and any(k in low for k in ("model", "tier", "ineligible", "not allowed", "not available for your"))):
        return {"kind": "model_forbidden", "retry_same": False, "url": url, "resets_at": None,
                "model": norm_model(model) or None, "summary": summary,
                "advice": "只停用這個帳號的這個模型，同帳號其他模型照常可用"}

    # 429 速率型 vs 額度型
    is_quota_word = any(k in low for k in (
        "quota", "usage limit", "limit reached", "exhausted", "weekly", "five hour", "5-hour",
        "5 hour", "resets at", "reset_time", "resets in", "out of credits", "resource_exhausted",
    ))
    is_rate_word = any(k in low for k in (
        "rate limit", "rate_limit", "too many requests", "slow down", "overloaded",
        "try again in a few seconds", "no capacity available", "experiencing high traffic",
    ))
    if code == 429 or is_quota_word or is_rate_word:
        if is_quota_word or (iso_m is not None) or (retry_sec is not None and retry_sec > 30):
            return {"kind": "quota_exhausted", "retry_same": False, "url": None, "resets_at": resets_at,
                    "model": norm_model(model) or None, "summary": summary,
                    "advice": "額度耗盡：寫入該桶冷卻至重置時間，照 on_exhausted 接手順序處理"}
        return {"kind": "rate_limit", "retry_same": True, "url": None, "resets_at": resets_at,
                "model": norm_model(model) or None, "summary": summary,
                "advice": "短暫速率限制：原帳號稍等重試，不換帳號"}

    return {"kind": "other", "retry_same": True, "url": None, "resets_at": None,
            "model": norm_model(model) or None, "summary": summary,
            "advice": "暫時性或未分類錯誤，不標壞帳號"}


# ---------- 狀態檔 pool-state.json（六維正交） ----------

def state_path(state):
    return Path(state) / "dispatch" / "pool-state.json"


def _empty_state():
    return {"schema_version": 1, "updated_at": None, "accounts": {}, "sticky": {}, "alerts_sent": {}}


def _empty_account():
    return {
        "paused": False,
        "paused_reason": None,
        "auth_expired": None,
        "validation_required": None,
        "tos_banned": None,
        "hard_forbidden": None,
        "forbidden_models": {},
        "cooldowns": {},
        "quota": None,
    }


def load_state(state):
    path = state_path(state)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            return _empty_state()
    except (OSError, ValueError):
        return _empty_state()
    out = _empty_state()
    out.update({k: doc[k] for k in ("schema_version", "updated_at", "accounts", "sticky", "alerts_sent") if k in doc})
    if not isinstance(out["accounts"], dict):
        out["accounts"] = {}
    if not isinstance(out["sticky"], dict):
        out["sticky"] = {}
    if not isinstance(out["alerts_sent"], dict):
        out["alerts_sent"] = {}
    return out


def save_state(state, doc, now=None):
    path = state_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {**doc, "schema_version": 1, "updated_at": iso_utc(now)}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return doc


def _acct(doc, instance):
    raw = doc["accounts"].get(instance)
    merged = _empty_account()
    if isinstance(raw, dict):
        merged.update(raw)
        if not isinstance(merged["forbidden_models"], dict):
            merged["forbidden_models"] = {}
        if not isinstance(merged["cooldowns"], dict):
            merged["cooldowns"] = {}
    doc["accounts"][instance] = merged
    return merged


def record_error(state, instance, kind, *, driver=None, model=None, bucket=None, resets_at=None, url=None, reason="", now=None):
    """記錄一次錯誤到 pool-state.json（不覆寫其他正交維度）。回傳 (更新後的 doc, 處理說明)。"""
    if kind not in ERROR_KINDS:
        raise ValueError(f"不認得的錯誤種類：{kind}，可選：{'、'.join(ERROR_KINDS)}")
    now_dt = utc_now(now)
    ts = iso_utc(now_dt)
    doc = load_state(state)
    acc = _acct(doc, instance)
    clean_reason = sanitize(reason)
    clean_url = safe_https_url(url)

    if kind == "rate_limit":
        return doc, f"{instance}：短暫速率限制（rate_limit），原帳號稍等重試，不寫入封鎖"
    if kind == "timeout_15min":
        return doc, f"{instance}：Antigravity 15 分鐘無活動逾時，先檢查交付檔與 .done，不封鎖帳號"
    if kind == "other":
        return doc, f"{instance}：一般錯誤（other），不封鎖帳號"

    if kind == "quota_exhausted":
        b = bucket or bucket_of(driver, model)
        prev = acc["cooldowns"].get(b) or {}
        streak = int(prev.get("streak", 0)) + 1 if prev.get("kind") == "quota_exhausted" else 1
        until_dt = parse_ts(resets_at)
        if until_dt is None or until_dt <= now_dt:
            wait = min(BACKOFF_MAX_SEC, BACKOFF_BASE_SEC * (2 ** (streak - 1)))
            until_dt = now_dt + timedelta(seconds=wait)
            source = f"指數退避 {wait} 秒（第 {streak} 次）"
        else:
            source = f"重置時間 {fmt_local(until_dt)}"
        acc["cooldowns"][b] = {
            "kind": "quota_exhausted", "since": ts, "until": iso_utc(until_dt),
            "streak": streak, "reason": clean_reason or source,
        }
        doc = save_state(state, doc, now_dt)
        return doc, f"{instance}（{BUCKET_NAMES.get(b, b)}）：額度冷卻到 {fmt_local(until_dt)}（{source}）"

    if kind == "auth_expired":
        acc["auth_expired"] = {"since": ts, "reason": clean_reason or "登入過期（401）"}
        doc = save_state(state, doc, now_dt)
        return doc, f"{instance}：已標記登入過期（auth_expired），移出可用池"

    if kind == "validation_required":
        entry = {"since": ts, "reason": clean_reason or "需要本人驗證（403）"}
        if clean_url:
            entry["url"] = clean_url
        if parse_ts(resets_at):
            entry["until"] = iso_utc(parse_ts(resets_at))
        acc["validation_required"] = entry
        doc = save_state(state, doc, now_dt)
        return doc, f"{instance}：已標記需要本人驗證（validation_required）" + (f"：{clean_url}" if clean_url else "")

    if kind == "tos_banned":
        entry = {"since": ts, "reason": clean_reason or "403 TOS_VIOLATION"}
        if clean_url:
            entry["url"] = clean_url
        acc["tos_banned"] = entry
        doc = save_state(state, doc, now_dt)
        return doc, f"{instance}：已永久標記停權（tos_banned），不會被額度查詢 200 沖刷"

    if kind == "hard_forbidden":
        acc["hard_forbidden"] = {"since": ts, "reason": clean_reason or "403 地區或出口不支援"}
        doc = save_state(state, doc, now_dt)
        return doc, f"{instance}：已標記地區或出口不支援（hard_forbidden）"

    if kind == "model_forbidden":
        m = norm_model(model)
        if not m:
            raise ValueError("model_forbidden 要帶 --model（只停用該帳號的該模型）")
        acc["forbidden_models"][m] = {"since": ts, "reason": clean_reason or "403 模型無權限"}
        doc = save_state(state, doc, now_dt)
        return doc, f"{instance}：只停用模型 {m}（model_forbidden），同帳號其他模型照常可用"

    return doc, ""


def record_ok(state, instance, *, driver=None, model=None, bucket=None, now=None):
    """資料面真正對話成功：清除暫時性鎖定（auth_expired、validation_required、對應冷卻與模型 403）。
    絕不清除 paused 與 tos_banned（這兩個必須由使用者明確解除）。"""
    now_dt = utc_now(now)
    doc = load_state(state)
    if instance not in doc["accounts"]:
        return doc, f"{instance}：原本沒有異常紀錄"
    acc = _acct(doc, instance)
    cleared = []
    for k in ("auth_expired", "validation_required"):
        if acc.get(k):
            acc[k] = None
            cleared.append(k)
    b = bucket or (bucket_of(driver, model) if (driver or model) else None)
    if b and b in acc["cooldowns"]:
        acc["cooldowns"].pop(b, None)
        cleared.append(f"cooldown:{b}")
    m = norm_model(model)
    if m and m in acc["forbidden_models"]:
        acc["forbidden_models"].pop(m, None)
        cleared.append(f"model:{m}")
    if cleared:
        doc = save_state(state, doc, now_dt)
        return doc, f"{instance}：資料面成功，已清除 {'、'.join(cleared)}"
    return doc, f"{instance}：沒有可清除的暫時鎖定"


def set_paused(state, instance, paused=True, reason="", now=None):
    doc = load_state(state)
    acc = _acct(doc, instance)
    acc["paused"] = bool(paused)
    acc["paused_reason"] = sanitize(reason) if paused and reason else None
    doc = save_state(state, doc, now)
    return doc, f"{instance}：{'已手動暫停' if paused else '已恢復啟用'}"


def clear_state(state, instance, *, dimension=None, force=False, now=None):
    """清除單一維度或全部狀態；tos_banned 必須 force=True 才清。"""
    doc = load_state(state)
    if instance not in doc["accounts"]:
        return doc, f"{instance}：沒有狀態紀錄"
    acc = _acct(doc, instance)
    dims = [dimension] if dimension else list(DIMENSIONS)
    cleared, kept = [], []
    for d in dims:
        if d not in DIMENSIONS:
            raise ValueError(f"不認得的維度：{d}，可選：{'、'.join(DIMENSIONS)}")
        if d == "tos_banned" and acc.get("tos_banned") and not force:
            kept.append("tos_banned（要加 --force 才清除）")
            continue
        if d == "paused":
            if acc.get("paused"):
                acc["paused"], acc["paused_reason"] = False, None
                cleared.append("paused")
        elif d in ("forbidden_models", "cooldowns"):
            if acc.get(d):
                acc[d] = {}
                cleared.append(d)
        else:
            if acc.get(d):
                acc[d] = None
                cleared.append(d)
    if cleared:
        doc = save_state(state, doc, now)
    msg = f"{instance}：已清除 {'、'.join(cleared) or '無'}"
    if kept:
        msg += f"；保留 {'、'.join(kept)}"
    return doc, msg


def is_blocked(doc, instance, *, driver=None, model=None, bucket=None, now=None):
    """這個實例（或它底下的某個模型／額度桶）現在是否被狀態檔擋住：(blocked, 原因, 代碼)。"""
    acc = (doc or {}).get("accounts", {}).get(instance)
    if not isinstance(acc, dict):
        return False, "", None
    now_dt = utc_now(now)
    if acc.get("paused"):
        why = f"已手動暫停（{acc['paused_reason']}）" if acc.get("paused_reason") else "已手動暫停"
        return True, why, "paused"
    if acc.get("tos_banned"):
        u = acc["tos_banned"].get("url")
        return True, "帳號已標記停權（tos_banned）" + (f"；申訴：{u}" if u else ""), "tos_banned"
    if acc.get("hard_forbidden"):
        return True, f"地區或網路出口不支援（{acc['hard_forbidden'].get('reason') or '403'}）", "hard_forbidden"
    if acc.get("auth_expired"):
        return True, "登入過期（auth_expired），需重新登入", "auth_expired"
    val = acc.get("validation_required")
    if isinstance(val, dict):
        until = parse_ts(val.get("until"))
        if until is None or until > now_dt:
            u = val.get("url")
            return True, "需要本人驗證（validation_required）" + (f"：{u}" if u else ""), "validation_required"
    m = norm_model(model)
    if m and m in (acc.get("forbidden_models") or {}):
        return True, f"這個帳號不支援模型 {m}（model_forbidden）", "model_forbidden"
    cds = acc.get("cooldowns") or {}
    check_buckets = [bucket or bucket_of(driver, model)]
    if "default" not in check_buckets:
        check_buckets.append("default")
    for b in check_buckets:
        cd = cds.get(b)
        if not isinstance(cd, dict):
            continue
        until = parse_ts(cd.get("until"))
        if until and until > now_dt:
            return True, f"{BUCKET_NAMES.get(b, b)} 冷卻中，{fmt_remain(until, now_dt)}後重置（{fmt_local(until)}）", "quota_exhausted"
    return False, "", None


# ---------- Antigravity 額度（agy -p /usage --output-format json） ----------

def parse_agy_usage(raw):
    """解析 agy -p /usage --output-format json 的輸出 → {ok, buckets, description, error}。"""
    text = str(raw or "")
    idx = text.find('{"conversation_id"')
    if idx < 0:
        idx = text.find("{")
    if idx < 0:
        return {"ok": False, "error": "看不到 agy /usage 的 JSON 輸出", "buckets": {}}
    try:
        doc, _ = json.JSONDecoder().raw_decode(text[idx:])
    except ValueError as e:
        return {"ok": False, "error": f"agy /usage 的 JSON 讀不懂：{e}", "buckets": {}}
    if doc.get("status") != "SUCCESS":
        err = sanitize(doc.get("response") or doc.get("error") or f"status={doc.get('status')}")
        return {"ok": False, "error": err, "buckets": {}}
    data = ((doc.get("command") or {}).get("data") or {})
    groups = data.get("groups") or []
    if not isinstance(groups, list) or not groups:
        return {"ok": False, "error": "agy /usage 沒有回傳任何額度分組（groups）", "buckets": {}}
    buckets = {}
    for g in groups:
        if not isinstance(g, dict):
            continue
        name = str(g.get("name") or "")
        low = name.lower()
        key = ("argon" if "argon" in low else
               "carbon" if "carbon" in low else
               "3p" if ("claude" in low or "gpt" in low) else
               "gemini" if "gemini" in low else re.sub(r"[^a-z0-9]+", "_", low).strip("_") or "other")
        entry = {"name": name, "description": g.get("description") or ""}
        for b in g.get("buckets") or []:
            if not isinstance(b, dict):
                continue
            win = b.get("window") or ("weekly" if "week" in str(b.get("id", "")).lower() else "5h")
            frac = b.get("remaining_fraction")
            pct = round(float(frac) * 100.0, 1) if isinstance(frac, (int, float)) else None
            prefix = "weekly" if win == "weekly" else "five_hour"
            entry[f"{prefix}_remaining_pct"] = pct
            if b.get("reset_time"):
                entry[f"{prefix}_resets_at"] = b["reset_time"]
        buckets[key] = entry
    return {"ok": True, "buckets": buckets, "description": data.get("description") or "", "error": None}


def agy_cli_target(rows, mine=None):
    """agy CLI 登入的是本機單一帳號（2026-11-23 實測 agy -p 沒有 --gemini-dir）；找對應的實例 id。"""
    reg = (mine or {}).get("instances") or {}
    for iid, spec in reg.items():
        if isinstance(spec, dict) and spec.get("agy_cli"):
            return iid
    autos = [r["id"] for r in rows if r.get("driver") == "antigravity" and r.get("auto", (False,))[0]]
    if len(autos) == 1:
        return autos[0]
    for r in rows:
        if r.get("driver") == "antigravity" and r.get("in_t3"):
            return r["id"]
    return "antigravity_ryan"


def refresh_agy_usage(state, instance, *, runner=None, now=None):
    """安全跑一次 `agy -p /usage --output-format json` 並更新 pool-state.json 的 quota。
    - 必帶 AGY_CLI_DISABLE_AUTO_UPDATE=true（小寫）與假 BROWSER 防彈窗。
    - 成功只更新 quota，絕不清除 tos_banned／hard_forbidden／validation_required／auth_expired／paused。
    - 失敗保留舊的 buckets 並標 stale: true，絕不歸零或寫成 100%。"""
    now_dt = utc_now(now)
    ts = iso_utc(now_dt)
    doc = load_state(state)
    acc = _acct(doc, instance)
    prev_q = acc.get("quota") if isinstance(acc.get("quota"), dict) else {}

    def _fail(msg):
        acc["quota"] = {
            "source": "agy_usage",
            "fetched_at": prev_q.get("fetched_at"),
            "checked_at": ts,
            "stale": True,
            "error": sanitize(msg),
            "buckets": prev_q.get("buckets") or {},
        }
        save_state(state, doc, now_dt)
        return {"ok": False, "instance": instance, "error": acc["quota"]["error"], "quota": acc["quota"]}

    if runner is None:
        exe = shutil.which("agy")
        if not exe:
            return _fail("找不到 agy 指令")
        env = {**os.environ, "AGY_CLI_DISABLE_AUTO_UPDATE": "true", "BROWSER": ""}
        try:
            r = subprocess.run(
                [exe, "-p", "/usage", "--output-format", "json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, env=env, timeout=20,
            )
            raw = (r.stdout or "") + "\n" + (r.stderr or "")
        except (OSError, subprocess.TimeoutExpired) as e:
            return _fail(f"執行 agy /usage 失敗：{e}")
    else:
        raw = runner()

    parsed = parse_agy_usage(raw)
    if not parsed["ok"]:
        return _fail(parsed["error"])

    acc["quota"] = {
        "source": "agy_usage",
        "fetched_at": ts,
        "checked_at": ts,
        "stale": False,
        "error": None,
        "buckets": parsed["buckets"],
        "note": "來自本機 agy CLI（agy -p /usage 不含帳號身分，僅代表 agy 登入帳號）",
    }
    save_state(state, doc, now_dt)
    return {"ok": True, "instance": instance, "error": None, "quota": acc["quota"]}


# ---------- Claude 多設定目錄額度快照 ----------

def claude_usage_path(state):
    return Path(state) / "dispatch" / "claude-usage.json"


def load_claude_snapshots(state):
    """回傳 {norm_dir: (原始鍵, snap)}，讓 Windows 大小寫與斜線不同也能對應同一個設定目錄。"""
    path = claude_usage_path(state)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        nk = norm_dir(k)
        # 同一個目錄如果有多筆舊鍵，留 recorded_at 較新的那筆
        if nk not in out or (v.get("recorded_at") or 0) > (out[nk][1].get("recorded_at") or 0):
            out[nk] = (k, v)
    return out


def claude_instance_dirs(home=None, mine=None, t3_raw=None):
    """每個 Claude 實例對應的設定目錄：{instance_id: Path}。
    來源：T3 settings.json 的 homePath（沒設就是 ~/.claude）、profile 的 config_dir。"""
    import homes
    home = Path(home) if home else homes.HOME
    if t3_raw is None:
        t3_raw = homes.t3_instances(home)
    reg = (mine or {}).get("instances") or {}
    out = {}
    for iid, inst in (t3_raw or {}).items():
        if not isinstance(inst, dict) or inst.get("driver") != "claudeAgent":
            continue
        cfg = inst.get("config") if isinstance(inst.get("config"), dict) else {}
        hp = cfg.get("homePath")
        p = homes.expand_home(hp, home) if isinstance(hp, str) and hp.strip() else home / ".claude"
        out[iid] = homes.canonical(p)
    for iid, spec in reg.items():
        if not isinstance(spec, dict) or spec.get("driver") != "claudeAgent":
            continue
        cd = spec.get("config_dir")
        if isinstance(cd, str) and cd.strip():
            out[iid] = homes.canonical(homes.expand_home(cd, home))
        elif iid not in out:
            out[iid] = homes.canonical(home / ".claude")
    return out


def t3_usage_snapshot(iid, home=None):
    """T3 Code 的供應商快取 ~/.t3/caches/<實例 id>.json 裡的 usageLimits（T3 自己定時查的 5 小時與每週額度）。
    2026-11-24 實測：T3 在 Claude 實例的快取寫 usageLimits.windows[{id: five_hour|seven_day, usedPercent, resetsAt}]
    與 checkedAt；同一個檔案也有 auth 區塊，這裡只取 usageLimits.windows 的數字與時間，絕不讀、不回傳其他欄位。
    回傳跟狀態列快照同形狀的 {five_hour, seven_day, recorded_at, source}；沒有就 None。"""
    import homes
    base = Path(home) if home else homes.HOME
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(iid or "")):
        return None
    try:
        raw = json.loads((base / ".t3" / "caches" / f"{iid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    lim = raw.get("usageLimits") if isinstance(raw, dict) else None
    if not isinstance(lim, dict) or not isinstance(lim.get("windows"), list):
        return None
    snap = {}
    for w in lim["windows"]:
        if not isinstance(w, dict) or w.get("id") not in ("five_hour", "seven_day"):
            continue
        used = w.get("usedPercent")
        if not isinstance(used, (int, float)):
            continue
        ent = {"used_percentage": float(used)}
        rst = parse_ts(w.get("resetsAt"))
        if rst:
            ent["resets_at"] = int(rst.timestamp())
        snap[w["id"]] = ent
    if "seven_day" not in snap:
        return None
    chk = parse_ts(lim.get("checkedAt"))
    snap["recorded_at"] = int(chk.timestamp()) if chk else None
    snap["source"] = "t3_cache"
    return snap


def next_weekly_reset(weekday, hour, now_dt):
    """依登記的「每週幾、幾點（UTC）重置」算出下一次重置時間。weekday：0=週一 … 6=週日。"""
    base = now_dt.replace(hour=int(hour), minute=0, second=0, microsecond=0)
    days = (int(weekday) - base.weekday()) % 7
    cand = base + timedelta(days=days)
    if cand <= now_dt:
        cand += timedelta(days=7)
    return cand


WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def manual_claude_snapshot(state_doc, iid, now_dt):
    """使用者用 set-claude-quota 登記的額度（pool-state.json 的 accounts.<id>.claude_quota）→ 跟狀態列快照同形狀。
    只登記每週幾重置、沒登記 resets_at 時，用 weekly_reset_weekday＋weekly_reset_hour_utc 推下一次重置。"""
    acc = ((state_doc or {}).get("accounts") or {}).get(iid) or {}
    mq = acc.get("claude_quota") if isinstance(acc, dict) else None
    if not isinstance(mq, dict):
        return None
    week = {}
    if isinstance(mq.get("weekly_used_pct"), (int, float)):
        week["used_percentage"] = float(mq["weekly_used_pct"])
    rst = parse_ts(mq.get("weekly_resets_at"))
    wd = mq.get("weekly_reset_weekday")
    if (not rst or rst <= now_dt) and wd in WEEKDAYS:
        nxt = next_weekly_reset(WEEKDAYS[wd], mq.get("weekly_reset_hour_utc") or 0, now_dt)
        if rst and rst <= now_dt:
            week.pop("used_percentage", None)  # 登記的用量屬於已過去的那一週，不沿用
        rst = nxt
    if rst:
        week["resets_at"] = int(rst.timestamp())
    if not week:
        return None
    snap = {"seven_day": week, "source": "manual"}
    if isinstance(mq.get("five_hour_used_pct"), (int, float)):
        five = {"used_percentage": float(mq["five_hour_used_pct"])}
        f_rst = parse_ts(mq.get("five_hour_resets_at"))
        if f_rst:
            five["resets_at"] = int(f_rst.timestamp())
        snap["five_hour"] = five
    rec = parse_ts(mq.get("recorded_at"))
    snap["recorded_at"] = int(rec.timestamp()) if rec else None
    return snap


def set_claude_quota(state, instance, *, weekly_used=None, weekly_resets_at=None, weekday=None, hour_utc=None,
                     five_hour_used=None, five_hour_resets_at=None, clear=False, now=None):
    """登記（或清除）一個 Claude 實例的剩餘額度與重置日，寫進 pool-state.json。不碰任何 token。"""
    now_dt = utc_now(now)
    doc = load_state(state)
    acc = _acct(doc, instance)
    if clear:
        acc.pop("claude_quota", None)
        save_state(state, doc, now_dt)
        return doc, f"已清除 {instance} 的手動額度登記"
    for name, val in (("weekly_used", weekly_used), ("five_hour_used", five_hour_used)):
        if val is not None and not (0 <= float(val) <= 100):
            raise ValueError(f"{name} 要在 0 到 100 之間")
    if weekday is not None and weekday not in WEEKDAYS:
        raise ValueError(f"weekday 要是 {'、'.join(WEEKDAYS)} 其中之一")
    if hour_utc is not None and not (0 <= int(hour_utc) <= 23):
        raise ValueError("hour_utc 要在 0 到 23 之間")
    mq = dict(acc.get("claude_quota") or {})
    if weekly_used is not None:
        mq["weekly_used_pct"] = round(float(weekly_used), 1)
    if weekly_resets_at is not None:
        rst = parse_ts(weekly_resets_at)
        if not rst:
            raise ValueError("weekly_resets_at 讀不懂（要 ISO8601 或 unix timestamp）")
        mq["weekly_resets_at"] = iso_utc(rst)
    if weekday is not None:
        mq["weekly_reset_weekday"] = weekday
        mq["weekly_reset_hour_utc"] = int(hour_utc or 0)
    if five_hour_used is not None:
        mq["five_hour_used_pct"] = round(float(five_hour_used), 1)
    if five_hour_resets_at is not None:
        f_rst = parse_ts(five_hour_resets_at)
        if not f_rst:
            raise ValueError("five_hour_resets_at 讀不懂")
        mq["five_hour_resets_at"] = iso_utc(f_rst)
    mq["recorded_at"] = iso_utc(now_dt)
    acc["claude_quota"] = mq
    save_state(state, doc, now_dt)
    return doc, f"已登記 {instance} 的額度：{json.dumps(mq, ensure_ascii=False)}"


def _pick_snapshot(cands, now_ts):
    """多個來源（狀態列、T3 快取、手動登記）挑一個：週重置還沒過、紀錄時間最新的優先；手動登記只在其他都沒有時用。"""
    live = []
    for snap in cands:
        if not snap:
            continue
        w = snap.get("seven_day") or {}
        rst = w.get("resets_at")
        expired = isinstance(rst, (int, float)) and rst <= now_ts
        live.append((0 if not expired else 1, 1 if snap.get("source") == "manual" else 0, -(snap.get("recorded_at") or 0), snap))
    if not live:
        return None
    live.sort(key=lambda t: t[:3])
    return live[0][3]


def claude_quotas(state, rows, mine=None, threshold=80, home=None, t3_raw=None, now=None, state_doc=None):
    """全部 Claude 實例（含三個設定目錄）的額度快照列表。
    來源依序：Claude Code 狀態列快照（dispatch.py statusline）、T3 Code 的供應商快取（~/.t3/caches/<id>.json，
    在 T3 裡跑 Claude 不會觸發狀態列時靠它）、使用者手動登記（set-claude-quota）。同時有多個時取最新的。"""
    now_dt = utc_now(now)
    now_ts = now_dt.timestamp()
    snaps = load_claude_snapshots(state)
    dirs = claude_instance_dirs(home, mine, t3_raw)
    doc = state_doc if state_doc is not None else load_state(state)
    out = []
    for r in rows:
        if r.get("driver") != "claudeAgent":
            continue
        iid = r["id"]
        cdir = dirs.get(iid)
        sl = snaps.get(norm_dir(cdir)) if cdir else None
        sl_snap = dict(sl[1], source="statusline") if sl else None
        picked = _pick_snapshot([sl_snap, t3_usage_snapshot(iid, home), manual_claude_snapshot(doc, iid, now_dt)], now_ts)
        hit = (None, picked) if picked else None
        base = {
            "instance": iid,
            "account": r.get("account") or r.get("label") or iid,
            "config_dir": str(cdir) if cdir else None,
            "threshold": threshold,
            "status": "unknown",
            "five_hour_used_pct": None,
            "five_hour_remaining_pct": None,
            "five_hour_resets_at": None,
            "weekly_used_pct": None,
            "weekly_remaining_pct": None,
            "weekly_resets_at": None,
            "over_threshold": None,
            "age_hours": None,
            "source": None,
            "why": "沒有快照：狀態列、T3 快取（~/.t3/caches）都沒有，也沒手動登記（account_pool.py set-claude-quota）",
        }
        if not hit:
            out.append(base)
            continue
        _, snap = hit
        base["source"] = snap.get("source")
        week = snap.get("seven_day") or {}
        five = snap.get("five_hour") or {}
        rec_ts = snap.get("recorded_at")
        age_h = round(max(0.0, (now_ts - rec_ts) / 3600.0), 1) if isinstance(rec_ts, (int, float)) else None
        base["age_hours"] = age_h
        w_reset = parse_ts(week.get("resets_at"))
        f_reset = parse_ts(five.get("resets_at"))
        if w_reset:
            base["weekly_resets_at"] = iso_utc(w_reset)
        if f_reset:
            base["five_hour_resets_at"] = iso_utc(f_reset)
        if "used_percentage" in five:
            f_used = round(float(five["used_percentage"]), 1)
            base["five_hour_used_pct"] = f_used
            base["five_hour_remaining_pct"] = round(max(0.0, 100.0 - f_used), 1)
        if "used_percentage" in week:
            w_used = round(float(week["used_percentage"]), 1)
            base["weekly_used_pct"] = w_used
            base["weekly_remaining_pct"] = round(max(0.0, 100.0 - w_used), 1)
            base["over_threshold"] = w_used >= threshold
        if "used_percentage" not in week:
            out.append(base)
            continue
        if w_reset and w_reset <= now_dt:
            # 保留上次讀到的數字當參考但標 stale（不歸零也不當成 100%）
            base["status"] = "stale"
            base["over_threshold"] = None
            base["why"] = "快照的這一週已過重置時間，等待新快照（數值為舊資料，不當成 0% 或 100%）"
        elif age_h is not None and age_h > CLAUDE_STALE_HOURS:
            base["status"] = "stale"
            base["why"] = f"快照是 {age_h} 小時前的（舊資料，實際用量可能更高）"
        else:
            base["status"] = "ok"
            base["why"] = None
        out.append(base)
    return out


# ---------- Claude 多帳號選擇器（weekly-first＋黏著＋防震盪） ----------

def select_claude_instance(rows, mine, quotas, state_doc, *, strategy=None, now=None, persist_state=None):
    """依策略從允許自動挑（auto_select）且沒被狀態檔擋住的 Claude 實例挑出推薦順序。
    只在工作包邊界挑，同一條對話不中途換。"""
    import accounts
    now_dt = utc_now(now)
    qmap = {q["instance"]: q for q in quotas}
    order = {iid: idx for idx, iid in enumerate(((mine or {}).get("instances") or {}).keys())}
    cands = []
    for r in rows:
        if r.get("driver") != "claudeAgent":
            continue
        iid = r["id"]
        sel_ok, sel_why = accounts.can_auto(r, "auto_select")
        blk, blk_why, blk_code = is_blocked(state_doc, iid, driver="claudeAgent", now=now_dt)
        q = qmap.get(iid) or {}
        w_rem = q.get("weekly_remaining_pct") if q.get("status") in ("ok", "stale") else None
        h_rem = q.get("five_hour_remaining_pct") if q.get("status") == "ok" else None
        f_reset = parse_ts(q.get("five_hour_resets_at"))
        w_reset = parse_ts(q.get("weekly_resets_at"))
        if f_reset and f_reset <= now_dt:
            h_rem = None  # 5 小時窗口已過，不算見底
        if w_reset and w_reset <= now_dt:
            w_rem = None
        depleted = (h_rem is not None and h_rem <= 0) or (w_rem is not None and w_rem <= 0)
        eligible = sel_ok and not blk and not depleted
        if not sel_ok:
            why = sel_why
        elif blk:
            why = blk_why
        elif depleted:
            why = "快照顯示 5 小時或每週額度已見底"
        elif q.get("status") == "ok":
            reset_part = f"，週重置 {fmt_local(w_reset)}" if w_reset else ""
            why = f"週剩 {w_rem:.0f}%" + (f"、5h 剩 {h_rem:.0f}%" if h_rem is not None else "") + reset_part
        elif q.get("status") == "stale":
            why = f"舊快照（{q.get('why')}）"
        else:
            why = "尚無額度快照（照 profile 順序）"
        expiring = bool(eligible and w_reset and w_reset > now_dt
                        and (w_reset - now_dt).total_seconds() < EXPIRING_SOON_SEC)
        if expiring:
            why = f"距週重置剩 {fmt_remain(w_reset, now_dt)}（< 48 小時，快過期的額度先燒完）；" + why
        cands.append({
            "instance": iid, "account": r.get("account") or r.get("label") or iid,
            "eligible": eligible, "w_rem": w_rem, "h_rem": h_rem, "expiring_soon": expiring,
            "w_reset_ts": w_reset.timestamp() if w_reset else None,
            "has_fresh": q.get("status") == "ok" and w_rem is not None,
            "order": order.get(iid, 999), "why": why,
        })

    elig = [c for c in cands if c["eligible"]]
    strat = strategy or (mine or {}).get("account_strategy") or ("weekly-first" if len(elig) > 1 else "sticky")
    if strat not in ACCOUNT_STRATEGIES:
        strat = "weekly-first"
    if not elig:
        return {"chosen": None, "strategy": strat, "reason": "沒有可自動挑的 Claude 實例", "ordered": [], "candidates": cands}

    def sort_key(c):
        if strat == "priority":
            return (c["order"],)
        if strat == "least-used":
            return (0 if c["w_rem"] is not None else 1, -(c["w_rem"] or -1.0), c["order"])
        if strat == "weekly-first":
            # 第一優先：48 小時內就要重置、還沒用完的帳號（快過期的額度先燒完），最快重置的排最前；
            # 其次有新鮮額度且有重置時間者：最快重置排最前，次看剩餘多寡；未知快照排在後面照 profile 順序
            return (
                0 if c["expiring_soon"] else (1 if (c["has_fresh"] and c["w_reset_ts"] is not None) else (2 if c["has_fresh"] else 3)),
                c["w_reset_ts"] if c["w_reset_ts"] is not None else float("inf"),
                -(c["w_rem"] or -1.0),
                c["order"],
            )
        return (c["order"],)

    ranked = sorted(elig, key=sort_key)
    best = ranked[0]
    sticky = ((state_doc or {}).get("sticky") or {}).get("claudeAgent") or {}
    cur = next((c for c in elig if c["instance"] == sticky.get("instance")), None)
    chosen = best
    reason = f"策略 {strat}：{best['why']}"

    if cur:
        cur_ok = (cur["w_rem"] is None or cur["w_rem"] > HEADROOM_FLOOR_PP) and (cur["h_rem"] is None or cur["h_rem"] > HEADROOM_FLOOR_PP)
        sw = parse_ts(sticky.get("switched_at"))
        within_cd = sw is not None and (now_dt - sw).total_seconds() < SWITCH_COOLDOWN_SEC
        if strat == "sticky":
            chosen, reason = cur, f"策略 sticky：維持黏著 {cur['instance']}（{cur['why']}）"
        elif cur["instance"] == best["instance"]:
            chosen, reason = cur, f"策略 {strat}：維持 {cur['instance']}（{cur['why']}）"
        elif strat == "weekly-first" and best["expiring_soon"] and not cur["expiring_soon"]:
            # 快過期優先壓過防震盪：原帳號的額度下週還在，best 的不燒就作廢
            chosen, reason = best, f"策略 weekly-first：{best['instance']} 快重置優先（{best['why']}），不受防震盪綁住"
        elif cur_ok and within_cd:
            chosen = cur
            reason = f"防震盪冷卻中（距上次切換不到 {SWITCH_COOLDOWN_SEC // 60} 分鐘）：維持 {cur['instance']}"
        elif cur_ok and best["w_rem"] is not None and cur["w_rem"] is not None:
            gap = best["w_rem"] - cur["w_rem"]
            earlier = (strat == "weekly-first" and best["w_reset_ts"] is not None and cur["w_reset_ts"] is not None
                       and (cur["w_reset_ts"] - best["w_reset_ts"]) >= WEEKLY_EARLIER_SEC)
            if not earlier and gap <= HYSTERESIS_PP:
                chosen = cur
                reason = f"防震盪遲滯（{best['instance']} 只領先 {gap:.1f} 個百分點，門檻 > {HYSTERESIS_PP:.0f}）：維持 {cur['instance']}"
        elif cur_ok and not best["has_fresh"]:
            chosen, reason = cur, f"候選無新鮮額度快照：維持黏著 {cur['instance']}"

    ordered = [chosen["instance"]] + [c["instance"] for c in ranked if c["instance"] != chosen["instance"]]
    if persist_state is not None and chosen["instance"] != sticky.get("instance"):
        doc = load_state(persist_state)
        doc["sticky"]["claudeAgent"] = {"instance": chosen["instance"], "switched_at": iso_utc(now_dt), "reason": reason}
        save_state(persist_state, doc, now_dt)
    return {"chosen": chosen["instance"], "strategy": strat, "reason": reason, "ordered": ordered, "candidates": cands}


# ---------- 額度用完接手順序（提案第四節 D1/D2） ----------

def _agy_bucket_status(acc, bucket_key, now_dt):
    """檢視 pool-state 裡一個 Antigravity 帳號的單一額度桶狀態。"""
    q = (acc or {}).get("quota") if isinstance(acc, dict) else None
    if not isinstance(q, dict):
        return None
    b = (q.get("buckets") or {}).get(bucket_key)
    if not isinstance(b, dict):
        return None
    fetched = parse_ts(q.get("fetched_at"))
    age_h = round(max(0.0, (now_dt - fetched).total_seconds() / 3600.0), 1) if fetched else None
    stale = bool(q.get("stale")) or (age_h is not None and age_h > AGY_STALE_HOURS)
    f_rem, w_rem = b.get("five_hour_remaining_pct"), b.get("weekly_remaining_pct")
    f_rst, w_rst = parse_ts(b.get("five_hour_resets_at")), parse_ts(b.get("weekly_resets_at"))
    parts = []
    if f_rem is not None:
        parts.append(f"5h 剩 {f_rem:.0f}%" + (f"（{fmt_local(f_rst)} 重置）" if f_rst else ""))
    if w_rem is not None:
        parts.append(f"週剩 {w_rem:.0f}%" + (f"（{fmt_local(w_rst)} 重置）" if w_rst else ""))
    if stale:
        parts.append("舊資料")
    exhausted = ((not stale) and ((f_rem is not None and f_rem <= 0 and (not f_rst or f_rst > now_dt))
                                  or (w_rem is not None and w_rem <= 0 and (not w_rst or w_rst > now_dt))))
    return {"text": "、".join(parts), "stale": stale, "exhausted": exhausted,
            "five_hour_remaining_pct": f_rem, "weekly_remaining_pct": w_rem,
            "five_hour_resets_at": b.get("five_hour_resets_at"), "weekly_resets_at": b.get("weekly_resets_at")}


def failover_plan(pol, mine, rows, state_doc, quotas, *, purpose="general", now=None):
    """計算額度用完的接手順序（提案第四節 D1/D2）。
    purpose: 'general' 或 'cross_review_claude'（跨家審查 Claude 寫的東西時跳過換成 Claude 的兩步）。"""
    import accounts
    now_dt = utc_now(now)
    mode = (mine or {}).get("on_exhausted") or "prompt_manual_switch"
    if mode not in ON_EXHAUSTED_MODES:
        mode = "prompt_manual_switch"
    cross_review = purpose == "cross_review_claude"
    steps = []

    auto_agy = [r for r in rows if r["driver"] == "antigravity" and r["auto"][0]]
    manual_agy = [r for r in rows if r["driver"] == "antigravity" and r["usage_scope"] == "manual_only" and r.get("in_t3") is not False]
    paid_api = [r for r in rows if r["terms"].get("verdict") == "ok" and r["auto"][0]]
    rates = accounts.rates_index()
    agy_roles = accounts.role_models(pol, "antigravity")

    # Step 1–3：自動派工 Antigravity 實例的三個桶（Gemini → Argon → Claude & GPT 桶 Opus）
    for r in auto_agy:
        iid = r["id"]
        acc = (state_doc or {}).get("accounts", {}).get(iid)
        # 1. Gemini 桶
        blk, why, _ = is_blocked(state_doc, iid, driver="antigravity", bucket="gemini", now=now_dt)
        bstat = _agy_bucket_status(acc, "gemini", now_dt)
        if blk:
            steps.append({"step": 1, "stage": "antigravity_gemini", "instance": iid, "bucket": "gemini",
                          "models": ["gemini-4-neon", "gemini-4-hydrogen"], "status": "skipped", "why": why})
        elif bstat and bstat["exhausted"]:
            steps.append({"step": 1, "stage": "antigravity_gemini", "instance": iid, "bucket": "gemini",
                          "models": ["gemini-4-neon", "gemini-4-hydrogen"], "status": "skipped", "why": f"額度見底（{bstat['text']}）"})
        else:
            steps.append({"step": 1, "stage": "antigravity_gemini", "instance": iid, "bucket": "gemini",
                          "models": ["gemini-4-neon", "gemini-4-hydrogen"], "status": "available",
                          "why": f"預設自動派工帳號" + (f"（{bstat['text']}）" if bstat and bstat["text"] else "（未刷 agy /usage）")})

        # 2. 同帳號 Argon 桶
        st_arg, why_arg = accounts.model_status("gemini-4-argon", None, mine, rates, agy_roles, driver="antigravity")
        blk_a, why_a, _ = is_blocked(state_doc, iid, driver="antigravity", model="gemini-4-argon", bucket="argon", now=now_dt)
        bstat_a = _agy_bucket_status(acc, "argon", now_dt)
        if st_arg == "filtered":
            steps.append({"step": 2, "stage": "antigravity_argon", "instance": iid, "bucket": "argon",
                          "models": ["gemini-4-argon"], "status": "skipped", "why": f"模型已過濾（{why_arg}）"})
        elif blk_a:
            steps.append({"step": 2, "stage": "antigravity_argon", "instance": iid, "bucket": "argon",
                          "models": ["gemini-4-argon"], "status": "skipped", "why": why_a})
        elif bstat_a and bstat_a["exhausted"]:
            steps.append({"step": 2, "stage": "antigravity_argon", "instance": iid, "bucket": "argon",
                          "models": ["gemini-4-argon"], "status": "skipped", "why": f"Argon 桶額度見底（{bstat_a['text']}）"})
        else:
            steps.append({"step": 2, "stage": "antigravity_argon", "instance": iid, "bucket": "argon",
                          "models": ["gemini-4-argon"], "status": "available",
                          "why": "同帳號獨立 Argon 桶（試用中，只接適合的角色）" + (f"；{bstat_a['text']}" if bstat_a and bstat_a["text"] else "")})

        # 3. 同帳號 Claude & GPT 桶（只用 Opus；Sonnet 同桶已被規則 2 過濾）
        if cross_review:
            steps.append({"step": 3, "stage": "antigravity_3p", "instance": iid, "bucket": "3p",
                          "models": ["claude-opus-5-5"], "status": "skipped",
                          "why": "跨家審查 Claude 寫的東西：跳過換成 Claude，避免失去跨家審查意義"})
        else:
            blk_3p, why_3p, _ = is_blocked(state_doc, iid, driver="antigravity", model="claude-opus-5-5", bucket="3p", now=now_dt)
            bstat_3p = _agy_bucket_status(acc, "3p", now_dt)
            if blk_3p:
                steps.append({"step": 3, "stage": "antigravity_3p", "instance": iid, "bucket": "3p",
                              "models": ["claude-opus-5-5"], "status": "skipped", "why": why_3p})
            elif bstat_3p and bstat_3p["exhausted"]:
                steps.append({"step": 3, "stage": "antigravity_3p", "instance": iid, "bucket": "3p",
                              "models": ["claude-opus-5-5"], "status": "skipped", "why": f"Claude & GPT 桶額度見底（{bstat_3p['text']}）"})
            else:
                steps.append({"step": 3, "stage": "antigravity_3p", "instance": iid, "bucket": "3p",
                              "models": ["claude-opus-5-5"], "status": "available",
                              "why": "同帳號 Claude & GPT 桶（Opus，不算輪換；Sonnet 同桶已過濾）" + (f"；{bstat_3p['text']}" if bstat_3p and bstat_3p["text"] else "")})

    # Step 4：三個 Claude 實例在工作包邊界依額度挑（D3）
    sel = select_claude_instance(rows, mine, quotas, state_doc, now=now_dt)
    if cross_review:
        steps.append({"step": 4, "stage": "claude_pool", "instances": [], "status": "skipped",
                      "why": "跨家審查 Claude 寫的東西：跳過換成 Claude 實例，改走第 5 步或用同模型新對話審"})
    elif sel["chosen"]:
        steps.append({"step": 4, "stage": "claude_pool", "instances": sel["ordered"], "chosen": sel["chosen"],
                      "status": "available", "why": f"工作包邊界依額度挑（{sel['reason']}）；同一條對話不中途換"})
    else:
        steps.append({"step": 4, "stage": "claude_pool", "instances": [], "status": "skipped", "why": sel["reason"]})

    # Step 5：最後防線（依 on_exhausted）
    manual_suggestions = []
    for r in manual_agy:
        blk, why, _ = is_blocked(state_doc, r["id"], driver="antigravity", bucket="gemini", now=now_dt)
        acc = (state_doc or {}).get("accounts", {}).get(r["id"])
        bstat = _agy_bucket_status(acc, "gemini", now_dt)
        manual_suggestions.append({
            "instance": r["id"], "account": r.get("account") or r.get("label") or r["id"],
            "blocked": blk, "why": why if blk else (bstat["text"] if bstat and bstat["text"] else "無異常紀錄（額度請看 T3 Usage → Limits）"),
        })
    if mode == "fallback_paid_api" and paid_api:
        steps.append({"step": 5, "stage": "fallback_paid_api", "instances": [r["id"] for r in paid_api],
                      "status": "fallback", "why": "訂閱用完改走 API 金鑰／Vertex 備援（規約 ok）"})
    elif mode == "fail_closed":
        steps.append({"step": 5, "stage": "fail_closed", "status": "stop",
                      "why": "fail_closed：訂閱額度用完即停，不自動花付費 API，等窗口重置"})
    else:
        rec_names = [m["instance"] for m in manual_suggestions if not m["blocked"]]
        hint = f"可手動切換：{'、'.join(rec_names[:3])}" if rec_names else "沒有標記可用的手動帳號，請對照 T3 Usage → Limits"
        steps.append({"step": 5, "stage": "prompt_manual_switch", "status": "manual",
                      "manual_accounts": manual_suggestions,
                      "why": f"停下來列出各帳號狀態與重置時間由你決定（{hint}；換帳號接續靠交接檔）"})

    active = next((s for s in steps if s["status"] in ("available", "fallback")), steps[-1] if steps else None)
    return {"on_exhausted": mode, "purpose": purpose, "active_step": active, "steps": steps, "claude_selection": sel}


# ---------- 警示與通知（提案第八節、第十節） ----------

def pending_alerts(state_doc, rows=None, now=None):
    """列出所有需要使用者介入的帳號異常（validation_required、auth_expired、tos_banned、hard_forbidden）。"""
    now_dt = utc_now(now)
    alerts = []
    for iid, acc in sorted(((state_doc or {}).get("accounts") or {}).items()):
        if not isinstance(acc, dict):
            continue
        if acc.get("tos_banned"):
            info = acc["tos_banned"]
            alerts.append({"instance": iid, "kind": "tos_banned", "severity": "critical",
                           "since": info.get("since"), "url": info.get("url"),
                           "message": f"帳號 {iid} 被標記停權（TOS_VIOLATION）" + (f"，申訴：{info['url']}" if info.get("url") else "")})
        val = acc.get("validation_required")
        if isinstance(val, dict):
            until = parse_ts(val.get("until"))
            if until is None or until > now_dt:
                alerts.append({"instance": iid, "kind": "validation_required", "severity": "high",
                               "since": val.get("since"), "url": val.get("url"),
                               "message": f"帳號 {iid} 需要本人驗證" + (f"：{val['url']}" if val.get("url") else "（請開 T3 或瀏覽器驗證）")})
        if acc.get("auth_expired"):
            info = acc["auth_expired"]
            alerts.append({"instance": iid, "kind": "auth_expired", "severity": "high",
                           "since": info.get("since"), "url": None,
                           "message": f"帳號 {iid} 登入過期（401），請重新登入"})
        if acc.get("hard_forbidden"):
            info = acc["hard_forbidden"]
            alerts.append({"instance": iid, "kind": "hard_forbidden", "severity": "medium",
                           "since": info.get("since"), "url": None,
                           "message": f"帳號 {iid} 遭遇地區或出口限制（403）"})
    if rows:
        autos = [r for r in rows if r.get("auto", (False,))[0]]
        if autos and all(is_blocked(state_doc, r["id"], driver=r.get("driver"), now=now_dt)[0] for r in autos):
            alerts.append({"instance": "all", "kind": "all_auto_blocked", "severity": "high",
                           "since": iso_utc(now_dt), "url": None,
                           "message": "所有可自動派工的帳號都處於冷卻或異常，請檢視額度或手動切帳號（account_pool.py failover）"})
    return alerts


def due_alert(state, now=None, env=None):
    """給 session_nudge.py Hook 用：純讀 JSON（不 import pyyaml），有高優先帳號異常時回傳一行提醒。
    同一個 (instance, kind, since) 24 小時內只提醒一次；CI 或 OMNIKIT_NO_NOTIFY 不提醒。"""
    env = os.environ if env is None else env
    if env.get("CI") or env.get("OMNIKIT_NO_NOTIFY"):
        return None
    if not state_path(state).is_file():
        return None
    now_dt = utc_now(now)
    doc = load_state(state)
    high = [a for a in pending_alerts(doc, now=now_dt) if a["kind"] in ("validation_required", "auth_expired", "tos_banned")]
    if not high:
        return None
    sent = doc.setdefault("alerts_sent", {})
    fresh = []
    for a in high:
        key = f"{a['instance']}:{a['kind']}:{a.get('since') or ''}"
        prev = parse_ts(sent.get(key))
        if prev and (now_dt - prev).total_seconds() < ALERT_REPEAT_HOURS * 3600:
            continue
        sent[key] = iso_utc(now_dt)
        fresh.append(a["message"])
    if not fresh:
        return None
    try:
        save_state(state, doc, now_dt)
    except OSError:
        pass
    return "帳號警示：" + "；".join(fresh[:3]) + "（看細節：uv run engine/scripts/account_pool.py status）"


def send_notification(alerts, mode="hook", *, env=None, runner=None, poster=None):
    """依使用者偏好的通知管道發送警示：none / hook / desktop（Windows Toast）/ webhook（讀環境變數）。"""
    env = os.environ if env is None else env
    if not alerts or mode in ("none", "hook"):
        return {"sent": False, "mode": mode, "reason": "無警示或由對話 hook 顯示"}
    body = "；".join(a["message"] for a in alerts[:3])
    if mode == "desktop":
        if os.name != "nt" and runner is None:
            return {"sent": False, "mode": mode, "reason": "桌面 Toast 目前只在 Windows 實作"}
        ps_msg = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "''")
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
            "$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            "$t = $xml.GetElementsByTagName('text');"
            "$t.Item(0).AppendChild($xml.CreateTextNode('OmniKit 帳號警示')) > $null;"
            f"$t.Item(1).AppendChild($xml.CreateTextNode('{ps_msg}')) > $null;"
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('OmniKit').Show($toast)"
        )
        if runner is not None:
            ok = runner(script)
            return {"sent": bool(ok), "mode": mode, "reason": None if ok else "桌面通知執行失敗"}
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return {"sent": r.returncode == 0, "mode": mode, "reason": None if r.returncode == 0 else f"exit {r.returncode}"}
        except (OSError, subprocess.SubprocessError) as e:
            return {"sent": False, "mode": mode, "reason": str(e)}
    if mode == "webhook":
        url = (env.get("OMNIKIT_NOTIFY_WEBHOOK_URL") or "").strip()
        if not url:
            return {"sent": False, "mode": mode, "reason": "未設定環境變數 OMNIKIT_NOTIFY_WEBHOOK_URL"}
        if not (url.startswith("https://") or url.startswith("http://127.0.0.1") or url.startswith("http://localhost")):
            return {"sent": False, "mode": mode, "reason": "Webhook 網址必須是 https://（或本機 127.0.0.1）"}
        payload = json.dumps({"title": "OmniKit 帳號警示", "message": body, "count": len(alerts)}, ensure_ascii=False).encode("utf-8")
        if poster is not None:
            ok = poster(url, payload)
            return {"sent": bool(ok), "mode": mode, "reason": None if ok else "webhook 推播失敗"}
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "omnikit-pool"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"sent": 200 <= resp.status < 300, "mode": mode, "reason": None}
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return {"sent": False, "mode": mode, "reason": str(e)}
    return {"sent": False, "mode": mode, "reason": f"不支援的通知模式：{mode}"}


# ---------- 文字格式化 ----------

def quota_view_data(state, pol, mine, rows, home=None, now=None):
    """整理所有 Claude 與 Antigravity 實例的整合額度與狀態視圖。"""
    now_dt = utc_now(now)
    doc = load_state(state)
    th = ((pol or {}).get("usage_signal") or {}).get("claude_weekly_threshold_pct", 80)
    c_quotas = claude_quotas(state, rows, mine, th, home=home, now=now_dt)
    sel = select_claude_instance(rows, mine, c_quotas, doc, now=now_dt)
    agy_rows = []
    for r in rows:
        if r.get("driver") != "antigravity":
            continue
        iid = r["id"]
        acc = doc["accounts"].get(iid) or {}
        blk, why, code = is_blocked(doc, iid, driver="antigravity", now=now_dt)
        buckets = {}
        for bk in ("gemini", "argon", "3p"):
            bs = _agy_bucket_status(acc, bk, now_dt)
            b_blk, b_why, _ = is_blocked(doc, iid, driver="antigravity", bucket=bk, now=now_dt)
            if bs or b_blk:
                buckets[bk] = {**(bs or {}), "cooldown": b_why if b_blk else None}
        agy_rows.append({
            "instance": iid, "account": r.get("account") or r.get("label") or iid,
            "usage_scope": r.get("usage_scope"), "auto": r["auto"][0],
            "blocked": blk, "blocked_reason": why, "blocked_code": code,
            "quota_fetched_at": (acc.get("quota") or {}).get("fetched_at") if isinstance(acc.get("quota"), dict) else None,
            "quota_stale": (acc.get("quota") or {}).get("stale") if isinstance(acc.get("quota"), dict) else None,
            "quota_error": (acc.get("quota") or {}).get("error") if isinstance(acc.get("quota"), dict) else None,
            "buckets": buckets,
        })
    return {"claude": c_quotas, "claude_selection": sel, "antigravity": agy_rows, "alerts": pending_alerts(doc, rows, now_dt)}


def usage_view_text(view):
    lines = ["Claude 帳號額度（多設定目錄快照）："]
    for q in view["claude"]:
        if q["status"] == "unknown":
            lines.append(f"  {q['instance']}（{q['account']}，{q['config_dir']}）：未知（尚無快照）")
        else:
            f_part = f"5h 已用 {q['five_hour_used_pct']:.0f}%" if q["five_hour_used_pct"] is not None else "5h 未知"
            w_part = f"週已用 {q['weekly_used_pct']:.0f}%（剩 {q['weekly_remaining_pct']:.0f}%）" if q["weekly_used_pct"] is not None else "週未知"
            rst = parse_ts(q.get("weekly_resets_at"))
            r_part = f"，週重置 {fmt_local(rst)}" if rst else ""
            stale = f"【舊資料：{q['why']}】" if q["status"] == "stale" else ""
            src = {"statusline": "狀態列", "t3_cache": "T3 快取", "manual": "手動登記"}.get(q.get("source"), q.get("source") or "?")
            lines.append(f"  {q['instance']}（{q['account']}）：{w_part}、{f_part}{r_part}（來源：{src}）{stale}")
    sel = view["claude_selection"]
    if sel.get("chosen"):
        lines.append(f"  推薦下一個工作包用：{sel['chosen']}（{sel['reason']}）")

    lines.append("\nAntigravity 帳號額度（agy -p /usage 只查本機 agy 帳號；其餘請看 T3 Usage → Limits）：")
    for a in view["antigravity"]:
        tag = "自動派" if a["auto"] else "手動"
        if a["blocked"]:
            lines.append(f"  {a['instance']}（{a['account']}，{tag}）：不可用 — {a['blocked_reason']}")
            continue
        if a["buckets"]:
            b_parts = []
            for bk, info in a["buckets"].items():
                txt = info.get("cooldown") or info.get("text") or "未知"
                b_parts.append(f"{BUCKET_NAMES.get(bk, bk)}：{txt}")
            lines.append(f"  {a['instance']}（{a['account']}，{tag}）：" + "；".join(b_parts))
        else:
            note = f"刷新失敗：{a['quota_error']}" if a.get("quota_error") else "尚無快照（加 --refresh-agy 查 agy 帳號，其餘看 T3 Usage → Limits）"
            lines.append(f"  {a['instance']}（{a['account']}，{tag}）：{note}")

    if view["alerts"]:
        lines.append("\n未解決警示：")
        for al in view["alerts"]:
            lines.append(f"  [{al['severity']}] {al['message']}")
    return "\n".join(lines)


def failover_text(plan):
    tag = "跨家審查 Claude 產出" if plan["purpose"] == "cross_review_claude" else "一般自動派工"
    lines = [f"額度用完接手順序（on_exhausted: {plan['on_exhausted']}；情境：{tag}）："]
    for s in plan["steps"]:
        mark = {"available": "可用", "skipped": "跳過", "fallback": "備援", "manual": "人工決定", "stop": "停止"}.get(s["status"], s["status"])
        who = s.get("instance") or ("、".join(s.get("instances") or [])) or s["stage"]
        b = f" / {BUCKET_NAMES.get(s['bucket'], s['bucket'])}" if s.get("bucket") else ""
        lines.append(f"  {s['step']}. [{mark}] {who}{b}：{s['why']}")
        for m in s.get("manual_accounts") or []:
            lines.append(f"     - {m['instance']}（{m['account']}）：{'不可用：' if m['blocked'] else ''}{m['why']}")
    return "\n".join(lines)


def status_text(rows, doc, now=None):
    now_dt = utc_now(now)
    lines = ["帳號池狀態（~/.omnikit/dispatch/pool-state.json）："]
    for r in rows:
        iid = r["id"]
        acc = (doc.get("accounts") or {}).get(iid) or {}
        blk, why, _ = is_blocked(doc, iid, driver=r["driver"], now=now_dt)
        flags = []
        if acc.get("paused"):
            flags.append("paused")
        if acc.get("tos_banned"):
            flags.append("tos_banned")
        if acc.get("hard_forbidden"):
            flags.append("hard_forbidden")
        if acc.get("auth_expired"):
            flags.append("auth_expired")
        if acc.get("validation_required"):
            flags.append("validation_required")
        for m in sorted(acc.get("forbidden_models") or {}):
            flags.append(f"model_forbidden:{m}")
        for b, cd in sorted((acc.get("cooldowns") or {}).items()):
            u = parse_ts(cd.get("until"))
            if u and u > now_dt:
                flags.append(f"cooldown:{b}({fmt_remain(u, now_dt)})")
        state_str = ("阻塞：" + why) if blk else ("正常" + (f"（部分限制：{'、'.join(flags)}）" if flags else ""))
        lines.append(f"  {iid}（{r['driver']}，{r['usage_scope']}）：{state_str}")
    alerts = pending_alerts(doc, rows, now_dt)
    if alerts:
        lines.append("\n未解決警示：")
        for a in alerts:
            lines.append(f"  [{a['severity']}] {a['message']}")
    return "\n".join(lines)


# ---------- CLI ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description="帳號池狀態機、錯誤分類、額度視圖與接手順序")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("usage")
    p.add_argument("--refresh-agy", action="store_true", help="跑 agy -p /usage --output-format json 更新 Antigravity 額度")
    p.add_argument("--agy-instance", help="指定 --refresh-agy 對應的 Antigravity 實例 id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("failover")
    p.add_argument("--purpose", choices=["general", "cross_review_claude"], default="general")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("select-claude")
    p.add_argument("--strategy", choices=ACCOUNT_STRATEGIES)
    p.add_argument("--persist", action="store_true", help="記下這次挑選為新的黏著帳號")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("set-claude-quota", help="T3 快取與狀態列都沒有時，手動登記 Claude 實例的剩餘額度與重置日")
    p.add_argument("--instance", required=True)
    p.add_argument("--weekly-used", type=float, help="本週已用百分比 0 到 100")
    p.add_argument("--weekly-resets-at", help="每週重置時間（ISO8601 或 unix timestamp）")
    p.add_argument("--weekday", choices=list(WEEKDAYS), help="每週幾重置（沒給 --weekly-resets-at 時推下一次）")
    p.add_argument("--hour-utc", type=int, help="搭配 --weekday：幾點（UTC，0 到 23）")
    p.add_argument("--five-hour-used", type=float)
    p.add_argument("--five-hour-resets-at")
    p.add_argument("--clear", action="store_true", help="清除這個實例的手動登記")

    p = sub.add_parser("record-error")
    p.add_argument("--instance", required=True)
    p.add_argument("--kind", choices=ERROR_KINDS)
    p.add_argument("--text", help="錯誤原文：自動分類（不把疑似 token 存進狀態檔）")
    p.add_argument("--status-code", type=int)
    p.add_argument("--driver")
    p.add_argument("--model")
    p.add_argument("--bucket")
    p.add_argument("--resets-at")
    p.add_argument("--url")
    p.add_argument("--note", default="")

    p = sub.add_parser("record-ok")
    p.add_argument("--instance", required=True)
    p.add_argument("--driver")
    p.add_argument("--model")
    p.add_argument("--bucket")

    p = sub.add_parser("pause")
    p.add_argument("--instance", required=True)
    p.add_argument("--reason", default="")

    p = sub.add_parser("unpause")
    p.add_argument("--instance", required=True)

    p = sub.add_parser("clear")
    p.add_argument("--instance", required=True)
    p.add_argument("--dimension", choices=DIMENSIONS)
    p.add_argument("--force", action="store_true", help="允許清除 tos_banned")

    p = sub.add_parser("alerts")
    p.add_argument("--notify", choices=NOTIFY_MODES, help="依指定模式發送通知（預設讀 profile 的 notify）")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("classify")
    p.add_argument("--text", required=True)
    p.add_argument("--status-code", type=int)
    p.add_argument("--model")
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    if args.cmd == "classify":
        res = classify_error(args.text, args.status_code, args.model)
        print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else f"{res['kind']}（retry_same={res['retry_same']}）：{res['advice']}")
        return 0

    import accounts
    import dispatch
    data, state, _, folder = dispatch.context()
    pol = dispatch.policy(data)
    mine = dispatch.personal(folder)
    rows = accounts.registry(accounts.t3_instances(), mine, accounts.load_terms(data))

    if args.cmd == "status":
        doc = load_state(state)
        if args.json:
            print(json.dumps({"state": doc, "alerts": pending_alerts(doc, rows)}, ensure_ascii=False, indent=2))
        else:
            print(status_text(rows, doc))
        return 0

    if args.cmd == "usage":
        refreshed = None
        if args.refresh_agy:
            target = args.agy_instance or agy_cli_target(rows, mine)
            refreshed = refresh_agy_usage(state, target)
        view = quota_view_data(state, pol, mine, rows)
        if refreshed is not None:
            view["refreshed_agy"] = refreshed
        print(json.dumps(view, ensure_ascii=False, indent=2) if args.json else usage_view_text(view))
        return 0

    if args.cmd == "failover":
        doc = load_state(state)
        th = pol["usage_signal"]["claude_weekly_threshold_pct"]
        quotas = claude_quotas(state, rows, mine, th)
        plan = failover_plan(pol, mine, rows, doc, quotas, purpose=args.purpose)
        print(json.dumps(plan, ensure_ascii=False, indent=2) if args.json else failover_text(plan))
        return 0

    if args.cmd == "select-claude":
        doc = load_state(state)
        th = pol["usage_signal"]["claude_weekly_threshold_pct"]
        quotas = claude_quotas(state, rows, mine, th)
        res = select_claude_instance(rows, mine, quotas, doc, strategy=args.strategy, persist_state=state if args.persist else None)
        print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else f"挑選：{res['chosen'] or '無'}（{res['reason']}）")
        return 0

    if args.cmd == "set-claude-quota":
        if args.instance not in {r["id"] for r in rows if r.get("driver") == "claudeAgent"}:
            raise SystemExit(f"{args.instance} 不是已登記的 Claude 實例")
        try:
            _, msg = set_claude_quota(state, args.instance, weekly_used=args.weekly_used, weekly_resets_at=args.weekly_resets_at,
                                      weekday=args.weekday, hour_utc=args.hour_utc, five_hour_used=args.five_hour_used,
                                      five_hour_resets_at=args.five_hour_resets_at, clear=args.clear)
        except ValueError as e:
            raise SystemExit(str(e))
        print(msg)
        return 0

    if args.cmd == "record-error":
        kind = args.kind
        resets_at, url, reason, model = args.resets_at, args.url, args.note, args.model
        if not kind:
            if not args.text:
                raise SystemExit("要給 --kind 或 --text")
            c = classify_error(args.text, args.status_code, args.model)
            kind = c["kind"]
            resets_at = resets_at or c["resets_at"]
            url = url or c["url"]
            reason = reason or c["summary"]
            model = model or c["model"]
        driver = args.driver or next((r["driver"] for r in rows if r["id"] == args.instance), None)
        _, msg = record_error(state, args.instance, kind, driver=driver, model=model, bucket=args.bucket,
                              resets_at=resets_at, url=url, reason=reason)
        print(msg)
        return 0

    if args.cmd == "record-ok":
        driver = args.driver or next((r["driver"] for r in rows if r["id"] == args.instance), None)
        _, msg = record_ok(state, args.instance, driver=driver, model=args.model, bucket=args.bucket)
        print(msg)
        return 0

    if args.cmd == "pause":
        _, msg = set_paused(state, args.instance, True, args.reason)
        print(msg)
        return 0

    if args.cmd == "unpause":
        _, msg = set_paused(state, args.instance, False)
        print(msg)
        return 0

    if args.cmd == "clear":
        _, msg = clear_state(state, args.instance, dimension=args.dimension, force=args.force)
        print(msg)
        return 0

    if args.cmd == "alerts":
        doc = load_state(state)
        als = pending_alerts(doc, rows)
        mode = args.notify or (mine or {}).get("notify") or "hook"
        sent = send_notification(als, mode) if args.notify else None
        if args.json:
            print(json.dumps({"alerts": als, "notify": sent}, ensure_ascii=False, indent=2))
        else:
            if not als:
                print("沒有未解決的帳號警示。")
            for a in als:
                print(f"[{a['severity']}] {a['message']}")
            if sent:
                print(f"通知（{sent['mode']}）：{'已送出' if sent['sent'] else '未送出：' + str(sent['reason'])}")
        return 0

    ap.print_help()
    return 2


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def ok(label, cond):
        print(f"{'通過' if cond else '失敗'}：{label}")
        if not cond:
            failures.append(label)

    t0 = datetime(2026, 11, 23, 6, 0, 0, tzinfo=timezone.utc)

    # 1. 錯誤分類器與敏感資訊遮罩
    c_rate = classify_error("HTTP 429 Too Many Requests: rate limit exceeded, try again in 5 seconds", 429, now=t0)
    c_quota = classify_error("HTTP 429 RESOURCE_EXHAUSTED: weekly quota limit reached, resets at 2026-11-23T12:00:00Z", 429, now=t0)
    c_agy_q = classify_error("Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 33m32s.", now=t0)
    c_cap = classify_error("Our servers are experiencing high traffic right now. (UNAVAILABLE (code 503): No capacity available for model gemini-4-argon-high)", now=t0)
    c_401 = classify_error("401 invalid_grant Bearer secret-token-1234567890", 401, now=t0)
    c_val = classify_error("403 VALIDATION_REQUIRED please visit https://accounts.google.com/verify?id=abc", 403, now=t0)
    c_tos = classify_error("403 PERMISSION_DENIED TOS_VIOLATION appeal at https://support.google.com/appeal", 403, now=t0)
    c_gcp = classify_error("403 SERVICE_DISABLED for project foo", 403, now=t0)
    c_loc = classify_error("403 Location not supported in this region", 403, now=t0)
    c_mod = classify_error("403 model claude-opus-5-5 is not allowed for your tier", 403, model="claude-opus-5-5", now=t0)
    c_t15 = classify_error("Antigravity sent nothing for 15 minutes, so T3 Code stopped the turn", now=t0)
    ok("錯誤分類：速率型 429／503 容量不足（原帳號稍等）vs 額度型 429／複合重置時間（抓到 resets_at）",
       c_rate["kind"] == "rate_limit" and c_rate["retry_same"] is True
       and c_cap["kind"] == "rate_limit" and c_cap["retry_same"] is True
       and c_quota["kind"] == "quota_exhausted" and c_quota["retry_same"] is False
       and c_quota["resets_at"] == "2026-11-23T12:00:00+00:00"
       and c_agy_q["kind"] == "quota_exhausted" and c_agy_q["resets_at"] == "2026-11-23T06:33:32+00:00")
    ok("錯誤分類：401 遮罩 token、403 區分驗證鎖／TOS 封禁／地區／模型權限／15 分鐘逾時；GCP SERVICE_DISABLED 不誤判封禁",
       c_401["kind"] == "auth_expired" and "secret-token" not in c_401["summary"] and "[REDACTED]" in c_401["summary"]
       and c_val["kind"] == "validation_required" and c_val["url"] == "https://accounts.google.com/verify?id=abc"
       and c_tos["kind"] == "tos_banned" and c_tos["url"] == "https://support.google.com/appeal"
       and c_gcp["kind"] != "tos_banned"
       and c_loc["kind"] == "hard_forbidden"
       and c_mod["kind"] == "model_forbidden" and c_mod["model"] == "claude-opus-5-5"
       and c_t15["kind"] == "timeout_15min" and c_t15["retry_same"] is True)

    # 2. 正交狀態機＋200 不沖刷封禁＋失敗保留舊快照標 stale
    sample_agy = json.dumps({
        "conversation_id": "", "status": "SUCCESS", "response": "ok",
        "command": {"name": "usage", "data": {"groups": [
            {"name": "Gemini Models", "description": "Gemini 4 Neon, Hydrogen", "buckets": [
                {"id": "gemini-weekly", "window": "weekly", "remaining_fraction": 0.95, "reset_time": "2026-11-30T02:00:00Z"},
                {"id": "gemini-5h", "window": "5h", "remaining_fraction": 0.80, "reset_time": "2026-11-23T08:00:00Z"}]},
            {"name": "Claude and GPT models", "description": "Opus, Sonnet, GPT-OSS", "buckets": [
                {"id": "3p-weekly", "window": "weekly", "remaining_fraction": 1.0, "reset_time": "2026-11-30T05:00:00Z"}]},
            {"name": "Gemini 4 Argon", "description": "separate", "buckets": [
                {"id": "gemini-argon-wtu-weekly", "window": "weekly", "remaining_fraction": 0.99, "reset_time": "2026-11-30T02:00:00Z"}]},
        ]}},
    })
    with tempfile.TemporaryDirectory() as tmp:
        st = Path(tmp)
        # 額度型 429 只鎖該 bucket，同帳號其他 bucket 照常可用
        record_error(st, "ag_r", "quota_exhausted", driver="antigravity", model="gemini-4-neon",
                     resets_at="2026-11-23T08:00:00Z", now=t0)
        doc = load_state(st)
        ok("429 冷卻按桶隔離：Gemini 桶冷卻中，同帳號 Argon 與 3p 桶照常可用；重置時間過了自動解鎖",
           is_blocked(doc, "ag_r", driver="antigravity", model="gemini-4-hydrogen", now=t0)[0] is True
           and is_blocked(doc, "ag_r", driver="antigravity", model="gemini-4-argon", now=t0)[0] is False
           and is_blocked(doc, "ag_r", driver="antigravity", model="claude-opus-5-5", now=t0)[0] is False
           and is_blocked(doc, "ag_r", driver="antigravity", model="gemini-4-neon", now=t0 + timedelta(hours=3))[0] is False)
        # 無重置時間時指數退避
        record_error(st, "ag_b", "quota_exhausted", driver="antigravity", model="gemini-4-neon", now=t0)
        u1 = parse_ts(load_state(st)["accounts"]["ag_b"]["cooldowns"]["gemini"]["until"])
        record_error(st, "ag_b", "quota_exhausted", driver="antigravity", model="gemini-4-neon", now=t0)
        u2 = parse_ts(load_state(st)["accounts"]["ag_b"]["cooldowns"]["gemini"]["until"])
        ok("沒有 resets_at 時指數退避（30s → 60s）", (u1 - t0).total_seconds() == 30 and (u2 - t0).total_seconds() == 60)

        # 速率型 429 不封鎖
        record_error(st, "ag_rate", "rate_limit", driver="antigravity", now=t0)
        ok("速率型 429 不封鎖帳號", is_blocked(load_state(st), "ag_rate", driver="antigravity", now=t0)[0] is False)

        # 正交維度互不覆寫 + 200 額度查詢不沖刷 tos_banned + 失敗保留舊快照標 stale
        record_error(st, "ag_ban", "tos_banned", url="https://support.google.com/appeal", now=t0)
        set_paused(st, "ag_ban", True, "手動測試", now=t0)
        res_q = refresh_agy_usage(st, "ag_ban", runner=lambda: "jetski: info\n" + sample_agy, now=t0)
        doc_ban = load_state(st)
        ok("agy /usage 200 更新額度快照，絕不清除 tos_banned 與 paused",
           res_q["ok"] and doc_ban["accounts"]["ag_ban"]["quota"]["buckets"]["gemini"]["five_hour_remaining_pct"] == 80.0
           and doc_ban["accounts"]["ag_ban"]["tos_banned"] is not None
           and doc_ban["accounts"]["ag_ban"]["paused"] is True)
        res_fail = refresh_agy_usage(st, "ag_ban", runner=lambda: "network error", now=t0 + timedelta(minutes=5))
        q_after = load_state(st)["accounts"]["ag_ban"]["quota"]
        ok("agy /usage 查詢失敗時保留舊快照並標 stale: true，不當成 0% 或 100%",
           not res_fail["ok"] and q_after["stale"] is True and q_after["buckets"]["gemini"]["five_hour_remaining_pct"] == 80.0)
        record_ok(st, "ag_ban", driver="antigravity", model="gemini-4-neon", now=t0)
        clear_state(st, "ag_ban", dimension="tos_banned", force=False, now=t0)
        ok("record_ok 與沒帶 --force 的 clear 都不會清掉 tos_banned；加 --force 才清",
           load_state(st)["accounts"]["ag_ban"]["tos_banned"] is not None
           and clear_state(st, "ag_ban", dimension="tos_banned", force=True, now=t0)[0]["accounts"]["ag_ban"]["tos_banned"] is None)

        # 模型級 403 只停該模型
        record_error(st, "ag_m", "model_forbidden", driver="antigravity", model="claude-opus-5-5", now=t0)
        dm = load_state(st)
        ok("model_forbidden 只停該模型，同帳號其他模型照用；record_ok 後解開",
           is_blocked(dm, "ag_m", driver="antigravity", model="claude-opus-5-5", now=t0)[0] is True
           and is_blocked(dm, "ag_m", driver="antigravity", model="gemini-4-neon", now=t0)[0] is False
           and is_blocked(record_ok(st, "ag_m", driver="antigravity", model="claude-opus-5-5", now=t0)[0],
                          "ag_m", driver="antigravity", model="claude-opus-5-5", now=t0)[0] is False)

        # Hook 警示與 24 小時去重
        record_error(st, "ag_v", "validation_required", url="https://accounts.google.com/v", now=t0)
        a1 = due_alert(st, now=t0, env={})
        a2 = due_alert(st, now=t0 + timedelta(hours=1), env={})
        a3 = due_alert(st, now=t0 + timedelta(hours=25), env={})
        ok("due_alert：高優先異常出提醒（含驗證連結）、24 小時內去重、隔天再提、CI 靜音",
           a1 is not None and "ag_v" in a1 and "https://accounts.google.com/v" in a1
           and a2 is None and a3 is not None
           and due_alert(st, now=t0 + timedelta(hours=50), env={"CI": "true"}) is None)

        # 3. 多目錄 Claude 快照 + weekly-first + 防震盪 + failover 跨家審查例外
        import accounts
        import dispatch
        import profiles
        home = st / "home"
        for d in (".claude", ".claude-retis", ".claude-kai"):
            (home / d).mkdir(parents=True)
        t3_raw = {
            "claudeAgent": {"driver": "claudeAgent"},
            "claudeAgent_2": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-retis"}},
            "claudeAgent_claude_kai": {"driver": "claudeAgent", "config": {"homePath": "~/.claude-kai"}},
        }
        pol = dispatch.policy(profiles.DATA)
        mine = dispatch.personal(profiles.DATA / "profiles" / "ryan")
        t3_meta = {
            "claudeAgent": {"driver": "claudeAgent", "label": "Ryan", "enabled": True, "auth_mode": None},
            "claudeAgent_2": {"driver": "claudeAgent", "label": "retis", "enabled": True, "auth_mode": None},
            "claudeAgent_claude_kai": {"driver": "claudeAgent", "label": "Kai", "enabled": True, "auth_mode": None},
            "antigravity_ryan": {"driver": "antigravity", "label": "ryan", "enabled": True, "auth_mode": None},
            "antigravity_km0529": {"driver": "antigravity", "label": "km0529", "enabled": True, "auth_mode": None},
        }
        rows = accounts.registry(t3_meta, mine, accounts.load_terms(profiles.DATA))
        c_state = st / "cstate"
        ufile = claude_usage_path(c_state)
        ufile.parent.mkdir(parents=True)
        ufile.write_text(json.dumps({
            str((home / ".claude").resolve()): {
                "recorded_at": int(t0.timestamp()) - 100,
                "five_hour": {"used_percentage": 20, "resets_at": int((t0 + timedelta(hours=2)).timestamp())},
                "seven_day": {"used_percentage": 40, "resets_at": int((t0 + timedelta(days=3)).timestamp())},
            },
            str((home / ".claude-retis").resolve()): {
                "recorded_at": int(t0.timestamp()) - 100,
                "five_hour": {"used_percentage": 10, "resets_at": int((t0 + timedelta(hours=2)).timestamp())},
                "seven_day": {"used_percentage": 50, "resets_at": int((t0 + timedelta(days=1)).timestamp())},
            },
            str((home / ".claude-kai").resolve()): {
                "recorded_at": int(t0.timestamp()) - 100,
                "five_hour": {"used_percentage": 100, "resets_at": int((t0 + timedelta(hours=1)).timestamp())},
                "seven_day": {"used_percentage": 10, "resets_at": int((t0 + timedelta(hours=5)).timestamp())},
            },
        }), encoding="utf-8")
        qs = claude_quotas(c_state, rows, mine, 80, home=home, t3_raw=t3_raw, now=t0)
        sel1 = select_claude_instance(rows, mine, qs, load_state(c_state), strategy="weekly-first", now=t0, persist_state=c_state)
        ok("Claude 多目錄快照與 weekly-first：排除 5h 見底的 Kai、挑最快週重置的 retis",
           len(qs) == 3 and all(q["status"] == "ok" for q in qs) and sel1["chosen"] == "claudeAgent_2")
        # 5 分鐘內防震盪：即使切換策略為 least-used（Ryan 剩 60% 領先 retis 剩 50%），5 分鐘內不跳
        sel_cd = select_claude_instance(rows, mine, qs, load_state(c_state), strategy="least-used",
                                        now=t0 + timedelta(minutes=2))
        sel_after = select_claude_instance(rows, mine, qs, load_state(c_state), strategy="least-used",
                                           now=t0 + timedelta(minutes=6))
        ok("防震盪：5 分鐘冷卻內維持原帳號，過 5 分鐘且領先 > 5 個百分點才切換",
           sel_cd["chosen"] == "claudeAgent_2" and sel_after["chosen"] == "claudeAgent")

        # 3b. T3 快取補位與快重置優先（Expiring-Soon Burn First）
        (home / ".t3" / "caches").mkdir(parents=True)
        def t3c(iid, used, reset_dt, five=5):
            (home / ".t3" / "caches" / f"{iid}.json").write_text(json.dumps({
                "auth": {"email": "should-never-be-read@example.test", "type": "oauth"},
                "usageLimits": {"checkedAt": iso_utc(t0 - timedelta(minutes=3)), "windows": [
                    {"id": "five_hour", "usedPercent": five, "resetsAt": iso_utc(t0 + timedelta(hours=3))},
                    {"id": "seven_day", "usedPercent": used, "resetsAt": iso_utc(reset_dt)}]}}), encoding="utf-8")
        t3c("claudeAgent", 10, t0 + timedelta(days=5))
        t3c("claudeAgent_2", 20, t0 + timedelta(days=5, hours=2))
        t3c("claudeAgent_claude_kai", 70, t0 + timedelta(hours=24))
        e_state = st / "estate"
        qs_t3 = claude_quotas(e_state, rows, mine, 80, home=home, t3_raw=t3_raw, now=t0)
        snap_kai = t3_usage_snapshot("claudeAgent_claude_kai", home)
        ok("T3 快取補位：沒有狀態列快照時讀 ~/.t3/caches 的 usageLimits，來源標 t3_cache，絕不帶出 auth 欄位",
           all(q["status"] == "ok" and q["source"] == "t3_cache" for q in qs_t3)
           and "auth" not in snap_kai and "example.test" not in json.dumps(qs_t3)
           and t3_usage_snapshot("../evil", home) is None)
        sel_exp = select_claude_instance(rows, mine, qs_t3, load_state(e_state), strategy="weekly-first", now=t0)
        ok("快重置優先：Kai 距重置 24 小時（剩 30%）vs 其他剩 5 天（剩 80% 以上）時必選 Kai",
           sel_exp["chosen"] == "claudeAgent_claude_kai" and "48 小時" in sel_exp["reason"])
        # 黏著在 Ryan、剛切 1 分鐘（冷卻中）也要切到快過期的 Kai
        doc_e = load_state(e_state)
        doc_e["sticky"]["claudeAgent"] = {"instance": "claudeAgent", "switched_at": iso_utc(t0 - timedelta(minutes=1))}
        save_state(e_state, doc_e, t0)
        sel_exp2 = select_claude_instance(rows, mine, qs_t3, load_state(e_state), strategy="weekly-first", now=t0)
        ok("快重置優先壓過 5 分鐘防震盪與遲滯", sel_exp2["chosen"] == "claudeAgent_claude_kai")
        # Kai 已見底（週 100%）就不燒，回到一般 weekly-first
        t3c("claudeAgent_claude_kai", 100, t0 + timedelta(hours=24))
        qs_dep = claude_quotas(e_state, rows, mine, 80, home=home, t3_raw=t3_raw, now=t0)
        sel_dep = select_claude_instance(rows, mine, qs_dep, _empty_state(), strategy="weekly-first", now=t0)
        ok("快重置優先只對未耗盡的帳號：Kai 週 100% 時改挑其他", sel_dep["chosen"] == "claudeAgent")
        # 超過 48 小時不算快過期
        t3c("claudeAgent_claude_kai", 70, t0 + timedelta(hours=49))
        qs_49 = claude_quotas(e_state, rows, mine, 80, home=home, t3_raw=t3_raw, now=t0)
        ok("距重置 49 小時不算快過期", not any(c["expiring_soon"] for c in
           select_claude_instance(rows, mine, qs_49, _empty_state(), strategy="weekly-first", now=t0)["candidates"]))
        # 手動登記：只登記每週幾重置也能推下一次；狀態列快照比 T3 快取新時用狀態列
        m_state = st / "mstate"
        set_claude_quota(m_state, "claudeAgent_2", weekly_used=30, weekday="wed", hour_utc=21, now=t0)
        msnap = manual_claude_snapshot(load_state(m_state), "claudeAgent_2", t0)
        nxt = datetime.fromtimestamp(msnap["seven_day"]["resets_at"], timezone.utc)
        ok("手動登記：weekday＋hour 推出下一次重置（未來 7 天內、週三 21:00 UTC）",
           nxt > t0 and (nxt - t0) <= timedelta(days=7) and nxt.weekday() == 2 and nxt.hour == 21
           and msnap["seven_day"]["used_percentage"] == 30.0)
        try:
            set_claude_quota(m_state, "x", weekly_used=150)
            bad_rejected = False
        except ValueError:
            bad_rejected = True
        ok("手動登記：參數不合法時報錯", bad_rejected)
        newer = {"seven_day": {"used_percentage": 1, "resets_at": int((t0 + timedelta(days=2)).timestamp())},
                 "recorded_at": int(t0.timestamp()), "source": "statusline"}
        older = {"seven_day": {"used_percentage": 2, "resets_at": int((t0 + timedelta(days=2)).timestamp())},
                 "recorded_at": int(t0.timestamp()) - 600, "source": "t3_cache"}
        man = {"seven_day": {"used_percentage": 3}, "recorded_at": int(t0.timestamp()) + 60, "source": "manual"}
        ok("多來源取最新、手動登記墊底", _pick_snapshot([older, man, newer], t0.timestamp()) is newer
           and _pick_snapshot([None, man], t0.timestamp()) is man)

        # 接手順序：ryan 屏蔽 Argon 後跳過步驟 2 接手到同帳號 Opus；開啟 include_models 時接手到 Argon；跨家審查跳過第 3、4 步
        record_error(c_state, "antigravity_ryan", "quota_exhausted", driver="antigravity", model="gemini-4-neon",
                     resets_at=iso_utc(t0 + timedelta(hours=2)), now=t0)
        p_gen = failover_plan(pol, mine, rows, load_state(c_state), qs, purpose="general", now=t0)
        p_rev = failover_plan(pol, mine, rows, load_state(c_state), qs, purpose="cross_review_claude", now=t0)
        mine_with_argon = dict(mine, exclude_models=[m for m in (mine.get("exclude_models") or []) if m != "gemini-4-argon"],
                               include_models=["gemini-4-argon"])
        p_arg = failover_plan(pol, mine_with_argon, rows, load_state(c_state), qs, purpose="general", now=t0)
        ok("接手順序：Gemini 冷卻＋Argon 屏蔽跳到同帳號 Opus；啟用 Argon 時接手到 Argon；跨家審查跳過第 3、4 步",
           p_gen["steps"][0]["status"] == "skipped" and p_gen["steps"][1]["status"] == "skipped"
           and p_gen["active_step"]["stage"] == "antigravity_3p"
           and p_arg["active_step"]["stage"] == "antigravity_argon"
           and p_rev["steps"][2]["status"] == "skipped" and p_rev["steps"][3]["status"] == "skipped"
           and "跨家審查" in p_rev["steps"][2]["why"])

        # 通知模擬（desktop & webhook 不連網）
        sent_d = send_notification([{"message": "測試"}], "desktop", runner=lambda s: "OmniKit" in s)
        sent_w = send_notification([{"message": "測試"}], "webhook", env={"OMNIKIT_NOTIFY_WEBHOOK_URL": "https://example.test/hook"},
                                   poster=lambda u, b: u.startswith("https://") and b"OmniKit" in b)
        bad_w = send_notification([{"message": "測試"}], "webhook", env={"OMNIKIT_NOTIFY_WEBHOOK_URL": "http://insecure.example"})
        ok("通知通道：desktop 與 webhook 可運作，非 https 外部網址被擋下",
           sent_d["sent"] is True and sent_w["sent"] is True and bad_w["sent"] is False)

    print(f"\n{'account_pool.py selftest：全部通過' if not failures else f'account_pool.py selftest：{len(failures)} 項失敗'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
