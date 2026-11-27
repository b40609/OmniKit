# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""範圍 C（外部競品與收錄交叉檢視）確定性前置漏斗腳本。

三種觸發模式共用同一套純唯讀前置引擎：
1. 每週定時（T3 排程）／手動觸發：
   uv run engine/scripts/competitor_watch.py scan --days 7
2. 丟特定專案即時觸發：
   uv run engine/scripts/competitor_watch.py target <github-url-or-owner/repo> [--project OmniKit]
3. 離線自測：
   uv run engine/scripts/competitor_watch.py --selftest

安全與反雜訊原則：
- 對 OmniKeep 資料庫採 SQLite URI `?mode=ro` 與 `PRAGMA query_only = ON`，絕不寫入。
- 預設只掃手動收錄（`origin='manual'`）並排除 agent 寫回的 `source_type='insight'`，防自我迎合迴圈。
- 僅備註含明確競品標記（`#競品`、`#watch`、`重造輪子`）走必查快車道（跳過分類過濾）；
  單純加星（+25）或一般備註（+10）只做加權、仍受雜訊過濾，避免生活／美食／投資文章擠掉工程名額。
- 每次檢視包依首個 GitHub repo 去重並嚴格截斷最多 N 項深挖標的（預設 3 項），附五選一強制處置與改判條件模板。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OMNIKEEP_DB_CANDIDATES = (
    Path.home() / "Desktop" / "OmniKeep" / "omnikeep.db",
    Path.home() / "OmniKeep" / "omnikeep.db",
)
DEFAULT_STATUS_DIR = Path.home() / ".omnikit" / "status"

# 左邊界排除子網域（docs.github.com / gist.github.com / api.github.com）；
# 右邊界以 lookahead 容許中文全形標點、半形逗號、反引號、方括號與句尾。
GITHUB_REPO_RE = re.compile(
    r"(?<![\w.-])(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?=[^A-Za-z0-9_.-]|$)",
    re.IGNORECASE,
)
BARE_REPO_RE = re.compile(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$")
NON_REPO_OWNERS = frozenset({
    "topics", "search", "orgs", "settings", "explore", "trending", "marketplace",
    "sponsors", "features", "pricing", "about", "login", "signup", "blog",
    "collections", "events", "issues", "pulls", "notifications", "new",
    "enterprise", "customer-stories", "readme", "security", "solutions",
    "user-attachments", "apps", "advisories", "users", "codespaces", "copilot",
    "site", "contact",
})

# 快車道僅認明確競品標記，避免 Telegram 順手備註（「下次去」「看一下」）繞過雜訊過濾。
FAST_TRACK_MARKERS = ("#競品", "#watch", "重造輪子")
NOISE_CATEGORY_KEYWORDS = (
    "投資", "財經", "股票", "股市", "理財", "生活", "美食", "旅遊", "娛樂",
    "影視", "新聞", "時事", "健康", "運動", "穿搭", "房地產", "政治", "八卦",
    "finance", "lifestyle", "travel", "food", "news",
)

# 內建核心專案領域關鍵詞（避開英文常見泛詞如 brand / line）
PROJECT_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "omnikit": (
        "skill", "skills", "mcp", "claude code", "codex", "antigravity",
        "openspec", "skill router", "harness", "skill-scanner", "mcp-scanner",
        "dispatch", "subagent", "plugin", "obsidian-skills", "skillspector",
    ),
    "omnikeep": (
        "second brain", "第二大腦", "obsidian", "vault", "mcpvault", "bookmark",
        "rss", "radar", "rag", "fts5", "sqlite-vec", "qmd", "rerank", "reranker",
        "embedding", "llm gateway", "freellmapi", "omniroute", "free llm",
        "telegram bot", "line bot", "read-later",
    ),
    "catos": ("catos", "quant", "trading", "backtest", "okx", "alpha"),
    "t3-deskcat": ("deskcat", "desktop pet", "tauri", "webview", "sprite"),
    "lineport": ("lineport", "line webhook", "line bot", "line messaging"),
}

# 英文單字與日常用語高度重疊的專案名，不把裸專案名本身當自動配對詞
GENERIC_PROJECT_NAMES = frozenset({"brand", "line", "docs", "test", "app", "web", "tools"})

FIVE_DISPOSITIONS = (
    ("adopt_or_integrate", "直接導入或改接現有方案（免重造輪子）"),
    ("steal_pattern", "只借鏡關鍵模式或規格到既有專案"),
    ("replace_or_retire", "取代或退役我方已落後／過重的自建方案"),
    ("watch_with_trigger", "暫不動作，但明訂可檢驗的觸發／改判條件"),
    ("dismiss_with_evidence", "明確排除，記下反例與現任差距免日後重踩"),
)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def normalize_repo(text: str) -> str | None:
    """從 GitHub URL 或 owner/repo 字串萃取正規化的 owner/repo。"""
    s = (text or "").strip()
    if not s:
        return None
    m = GITHUB_REPO_RE.search(s)
    if m:
        owner, repo = m.group(1), m.group(2)
    else:
        m2 = BARE_REPO_RE.match(s)
        if not m2:
            return None
        owner, repo = m2.group(1), m2.group(2)
    if owner.lower() in NON_REPO_OWNERS:
        return None
    repo = repo.rstrip(".,;:!?")
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo or repo.startswith("."):
        return None
    return f"{owner}/{repo}"


def extract_github_repos(*texts: str) -> list[str]:
    """從多段文字／網址中萃取不重複的 GitHub owner/repo 清單（保留首次出現順序）。"""
    seen: dict[str, str] = {}
    for text in texts:
        if not text:
            continue
        for m in GITHUB_REPO_RE.finditer(text):
            owner, repo = m.group(1), m.group(2).rstrip(".,;:!?")
            if owner.lower() in NON_REPO_OWNERS:
                continue
            if repo.endswith(".git"):
                repo = repo[:-4]
            if not owner or not repo or repo.startswith("."):
                continue
            key = f"{owner}/{repo}".lower()
            seen.setdefault(key, f"{owner}/{repo}")
    return list(seen.values())


def resolve_db_path(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    env_db = os.environ.get("OMNIKEEP_DB", "").strip()
    if env_db:
        p = Path(env_db).expanduser()
        if p.is_file():
            return p
    for cand in DEFAULT_OMNIKEEP_DB_CANDIDATES:
        if cand.is_file():
            return cand
    return None


def load_roster_tools(data_dir: Path) -> dict[str, dict[str, Any]]:
    """讀取 OmniKit data/tools/*.yaml 建立索引（依 id 與正規化 repo 雙向查表）。"""
    tools_dir = data_dir / "tools"
    by_id: dict[str, dict[str, Any]] = {}
    by_repo: dict[str, dict[str, Any]] = {}
    if not tools_dir.is_dir():
        return {"by_id": by_id, "by_repo": by_repo}
    for path in sorted(tools_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        tid = str(doc.get("id") or path.stem)
        entry = {
            "id": tid,
            "name": str(doc.get("name") or tid),
            "status": str(doc.get("status") or ""),
            "slots": list(doc.get("slots") or []),
            "url": str(doc.get("url") or ""),
            "reason": str(doc.get("reason") or ""),
            "decided_at": str(doc.get("decided_at") or ""),
        }
        by_id[tid.lower()] = entry
        for repo in extract_github_repos(entry["url"]):
            by_repo[repo.lower()] = entry
    return {"by_id": by_id, "by_repo": by_repo}


def load_project_profiles(status_dir: Path) -> list[dict[str, Any]]:
    """從 ~/.omnikit/status/*/NOW.md 擷取活躍專案定位卡。"""
    profiles: list[dict[str, Any]] = []
    if not status_dir.is_dir():
        return profiles
    for child in sorted(status_dir.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        now_file = child / "NOW.md"
        if not now_file.is_file():
            continue
        try:
            text = now_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        heading = lines[0].lstrip("# ").strip() if lines else child.name
        path_line = next((ln for ln in lines[:12] if "專案路徑" in ln), "")
        conclusions = [ln for ln in lines if ln.startswith(("1.", "2.", "3.", "- [ ]"))][:4]
        hints = list(PROJECT_DOMAIN_HINTS.get(child.name.lower(), ()))
        keywords = {h.lower() for h in hints}
        if child.name.lower() not in GENERIC_PROJECT_NAMES:
            keywords.add(child.name.lower())
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", heading):
            low_tok = token.lower()
            if low_tok not in GENERIC_PROJECT_NAMES:
                keywords.add(low_tok)
        profiles.append({
            "name": child.name,
            "heading": heading,
            "now_path": str(now_file),
            "project_path": path_line,
            "highlights": conclusions,
            "keywords": sorted(keywords),
        })
    return profiles


def match_projects(text_blob: str, projects: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    """依文字內容比對最相關的活躍專案與命中關鍵詞。"""
    low = (text_blob or "").lower()
    matches: list[tuple[str, list[str]]] = []
    for proj in projects:
        hits = []
        for kw in proj["keywords"]:
            if not kw:
                continue
            if re.fullmatch(r"[a-z0-9_-]+", kw):
                if re.search(rf"(?<![a-z0-9_]){re.escape(kw)}(?![a-z0-9_])", low):
                    hits.append(kw)
            elif kw in low:
                hits.append(kw)
        if hits:
            matches.append((proj["name"], hits[:6]))
    matches.sort(key=lambda pair: (-len(pair[1]), pair[0].lower()))
    return matches


def _open_readonly_db(db_path: Path) -> sqlite3.Connection:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def fetch_recent_items(db_path: Path, days: int, include_radar: bool = False) -> list[dict[str, Any]]:
    """唯讀查詢 OmniKeep 近 N 天手動收錄（排除 radar 與 agent 寫回的 insight）。"""
    day_window = f"-{max(1, int(days))} days"
    conn = _open_readonly_db(db_path)
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(items)").fetchall()}
        wanted = [
            "id", "url", "source_type", "category_name", "title_l1", "summary_l1",
            "tech_tags", "is_starred", "is_read", "origin", "user_note", "agent_status",
            "created_at", "deep_analysis",
        ]
        select_cols = [c for c in wanted if c in cols]
        if "id" not in select_cols or "created_at" not in select_cols:
            raise ValueError("omnikeep.db 的 items 資料表缺少必要欄位（id / created_at）")

        # 使用 julianday 同時精準處理 'YYYY-MM-DD HH:MM:SS' 與 ISO 'YYYY-MM-DDTHH:MM:SS+00:00'
        where = ["julianday(created_at) >= julianday('now', ?)"]
        params: list[Any] = [day_window]
        if not include_radar and "origin" in cols:
            where.append("(origin = 'manual' OR origin IS NULL OR origin = '')")
        # 排除 agent 透過 writeback_insight 寫回的報告，避免自我迎合迴圈
        if "source_type" in cols:
            where.append("(source_type IS NULL OR source_type != 'insight')")

        sql = f"SELECT {', '.join(select_cols)} FROM items WHERE {' AND '.join(where)} ORDER BY julianday(created_at) DESC LIMIT 300"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        citations_by_parent: dict[str, list[dict[str, str]]] = {}
        if "item_citations" in tables and rows:
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in ids)
            cit_rows = conn.execute(
                f"SELECT source_parent_id, target_name, target_canonical_url, mention_context "
                f"FROM item_citations WHERE source_parent_id IN ({placeholders})",
                ids,
            ).fetchall()
            for cr in cit_rows:
                citations_by_parent.setdefault(cr["source_parent_id"], []).append({
                    "name": cr["target_name"] or "",
                    "url": cr["target_canonical_url"] or "",
                    "context": cr["mention_context"] or "",
                })

        for r in rows:
            tags_raw = r.get("tech_tags")
            if isinstance(tags_raw, str):
                try:
                    parsed = json.loads(tags_raw)
                    r["tech_tags"] = [str(t) for t in parsed] if isinstance(parsed, list) else []
                except Exception:
                    r["tech_tags"] = []
            elif isinstance(tags_raw, list):
                r["tech_tags"] = [str(t) for t in tags_raw]
            else:
                r["tech_tags"] = []
            r["citations"] = citations_by_parent.get(r["id"], [])
        return rows
    finally:
        conn.close()


def _is_fast_track(item: dict[str, Any]) -> tuple[bool, list[str]]:
    """僅備註含明確競品標記（#競品 / #watch / 重造輪子）才進必查快車道。
    一般備註與單純加星只於評分加權，不跳過分類雜訊過濾。
    """
    reasons: list[str] = []
    note = (item.get("user_note") or "").strip()
    if note:
        low_note = note.lower()
        for mk in FAST_TRACK_MARKERS:
            if mk.lower() in low_note:
                reasons.append(f"備註含 {mk}")
                break
    return bool(reasons), reasons


def _is_noise_item(item: dict[str, Any], repos: list[str], project_hits: list[tuple[str, list[str]]]) -> str:
    if repos or project_hits:
        return ""
    cat = (item.get("category_name") or "").lower()
    title = (item.get("title_l1") or "").lower()
    for kw in NOISE_CATEGORY_KEYWORDS:
        if kw in cat or kw in title:
            return f"非工程／生活雜訊（命中 {kw}）"
    return ""


def verify_github_repo(repo: str, runner=None) -> dict[str, Any]:
    """透過本機 gh CLI 取得一手 GitHub repo 指標（星數、授權、最後 push、最新 release）。"""
    checked_on = date.today().isoformat()
    exec_fn = runner or subprocess.run

    def _gh_json(endpoint: str) -> tuple[dict[str, Any] | None, str]:
        try:
            proc = exec_fn(
                ["gh", "api", endpoint],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=20,
            )
        except FileNotFoundError:
            return None, "找不到 gh CLI"
        except Exception as exc:
            return None, str(exc)
        if proc.returncode != 0:
            lines = (proc.stderr or proc.stdout or "").strip().splitlines()
            err = lines[0] if lines else f"exit {proc.returncode}"
            return None, err
        try:
            return json.loads(proc.stdout), ""
        except Exception as exc:
            return None, f"JSON 解析失敗: {exc}"

    info, err = _gh_json(f"repos/{repo}")
    if err or not isinstance(info, dict):
        return {"repo": repo, "verified_on": checked_on, "ok": False, "error": err or "empty"}

    rel, _ = _gh_json(f"repos/{repo}/releases/latest")
    latest_tag = (rel.get("tag_name") or "") if isinstance(rel, dict) else ""
    lic = info.get("license") or {}
    return {
        "repo": info.get("full_name") or repo,
        "verified_on": checked_on,
        "ok": True,
        "stars": info.get("stargazers_count"),
        "license": lic.get("spdx_id") or "NONE",
        "archived": bool(info.get("archived")),
        "pushed_at": (info.get("pushed_at") or "")[:10],
        "latest_release": latest_tag,
        "description": (info.get("description") or "").strip(),
        "html_url": info.get("html_url") or f"https://github.com/{repo}",
    }


def build_scan_packet(
    items: list[dict[str, Any]],
    roster: dict[str, dict[str, Any]],
    projects: list[dict[str, Any]],
    *,
    days: int = 7,
    max_deep: int = 3,
    verify_gh: bool = True,
    gh_verifier=None,
) -> dict[str, Any]:
    """執行兩段降噪漏斗的第 1 段確定性篩選，產出結構化檢視包。"""
    candidates: list[dict[str, Any]] = []
    filtered_out: list[dict[str, Any]] = []

    for item in items:
        cit_urls = " ".join(c.get("url", "") for c in item.get("citations") or [])
        cit_names = " ".join(f"{c.get('name', '')} {c.get('context', '')}" for c in item.get("citations") or [])
        repos = extract_github_repos(
            item.get("url") or "",
            cit_urls,
            item.get("title_l1") or "",
            item.get("summary_l1") or "",
            (item.get("deep_analysis") or "")[:4000],
        )
        blob = " ".join([
            item.get("title_l1") or "",
            item.get("summary_l1") or "",
            item.get("category_name") or "",
            " ".join(item.get("tech_tags") or []),
            item.get("user_note") or "",
            cit_names,
            " ".join(repos),
        ])
        proj_hits = match_projects(blob, projects)
        fast_track, ft_reasons = _is_fast_track(item)

        if not fast_track:
            noise_reason = _is_noise_item(item, repos, proj_hits)
            if noise_reason:
                filtered_out.append({
                    "id": item.get("id"),
                    "title": item.get("title_l1") or "(無標題)",
                    "category": item.get("category_name") or "",
                    "reason": noise_reason,
                })
                continue

        roster_hits = []
        for r in repos:
            hit = roster["by_repo"].get(r.lower())
            if hit:
                roster_hits.append({"repo": r, **hit})

        score = 0
        score_reasons: list[str] = []
        if fast_track:
            score += 60
            score_reasons.append(f"快車道(+60: {', '.join(ft_reasons)})")
        elif (item.get("user_note") or "").strip():
            score += 10
            score_reasons.append("含一般備註(+10)")
        if item.get("is_starred"):
            score += 25
            score_reasons.append("已加星(+25)")
        if repos:
            score += 20
            score_reasons.append(f"含 GitHub repo(+20: {len(repos)} 個)")
        if proj_hits:
            total_kw = sum(len(kws) for _, kws in proj_hits)
            pts = 4 if total_kw == 1 else min(32, total_kw * 8)
            score += pts
            score_reasons.append(
                f"命中活躍專案(+{pts}: {', '.join(p for p, _ in proj_hits[:3])})"
            )
        if any(h["status"] == "rejected" for h in roster_hits) and not fast_track:
            score -= 15
            score_reasons.append("曾於名冊拒絕(-15)")

        # 既不在快車道、沒有 GitHub repo 也沒有命中任何活躍專案 → 降噪過濾
        if not fast_track and not repos and not proj_hits:
            filtered_out.append({
                "id": item.get("id"),
                "title": item.get("title_l1") or "(無標題)",
                "category": item.get("category_name") or "",
                "reason": "未命中活躍專案關鍵詞且無 GitHub repo（非快車道）",
            })
            continue

        candidates.append({
            "id": item.get("id"),
            "created_at": str(item.get("created_at") or "")[:19],
            "title": item.get("title_l1") or "(無標題)",
            "category": item.get("category_name") or "",
            "url": item.get("url") or "",
            "summary": item.get("summary_l1") or "",
            "user_note": item.get("user_note") or "",
            "is_starred": bool(item.get("is_starred")),
            "fast_track": fast_track,
            "fast_track_reasons": ft_reasons,
            "repos": repos,
            "matched_projects": [{"project": p, "keywords": kws} for p, kws in proj_hits],
            "roster_matches": roster_hits,
            "score": score,
            "score_reasons": score_reasons,
        })

    # 嚴格依分數由高到低，同分時快車道優先、再按時間新到舊
    candidates.sort(key=lambda c: (c["score"], int(c["fast_track"]), c["created_at"]), reverse=True)

    # 挑選深挖名單時以首個正規化 GitHub repo 去重，避免同一個 repo 的貼文與專案卡佔走兩個名額
    deep_limit = max(1, min(max_deep, 5))
    deep_candidates: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    seen_primary_repos: set[str] = set()
    for cand in candidates:
        primary_repo = cand["repos"][0].lower() if cand["repos"] else ""
        if len(deep_candidates) < deep_limit and (not primary_repo or primary_repo not in seen_primary_repos):
            deep_candidates.append(cand)
            if primary_repo:
                seen_primary_repos.add(primary_repo)
        else:
            overflow.append(cand)

    gh_facts: dict[str, dict[str, Any]] = {}
    if verify_gh:
        verifier = gh_verifier or verify_github_repo
        to_check: list[str] = []
        for cand in deep_candidates:
            for r in cand["repos"]:
                if r.lower() not in {x.lower() for x in to_check}:
                    to_check.append(r)
                if len(to_check) >= 10:
                    break
            if len(to_check) >= 10:
                break
        for repo in to_check:
            gh_facts[repo] = verifier(repo)

    return {
        "mode": "scan",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "days": days,
        "max_deep": deep_limit,
        "counts": {
            "scanned_items": len(items),
            "deep_candidates": len(deep_candidates),
            "overflow_candidates": len(overflow),
            "filtered_out": len(filtered_out),
            "active_projects": len(projects),
        },
        "active_projects": [
            {"name": p["name"], "heading": p["heading"], "now_path": p["now_path"]}
            for p in projects
        ],
        "deep_candidates": deep_candidates,
        "overflow_candidates": overflow,
        "filtered_out": filtered_out,
        "gh_verified": gh_facts,
        "dispositions": [{"id": k, "desc": v} for k, v in FIVE_DISPOSITIONS],
    }


def build_target_packet(
    raw_target: str,
    roster: dict[str, dict[str, Any]],
    projects: list[dict[str, Any]],
    *,
    project_filter: str = "",
    note: str = "",
    verify_gh: bool = True,
    gh_verifier=None,
) -> dict[str, Any]:
    """建構單一目標即時觸發（target 模式）檢視包。"""
    repo = normalize_repo(raw_target)
    gh_info = None
    if repo and verify_gh:
        verifier = gh_verifier or verify_github_repo
        gh_info = verifier(repo)

    roster_hit = roster["by_repo"].get(repo.lower()) if repo else None
    if not roster_hit:
        slug = (repo.split("/")[-1] if repo else raw_target).lower()
        cand_hit = roster["by_id"].get(slug)
        # 只有名冊條目本身未填 url 時才用 slug 兜底比對，避免不同 owner 同名誤判
        if cand_hit and not cand_hit.get("url"):
            roster_hit = cand_hit

    blob_parts = [raw_target, repo or "", note]
    if isinstance(gh_info, dict) and gh_info.get("ok"):
        blob_parts.append(gh_info.get("description") or "")
    matched = match_projects(" ".join(blob_parts), projects)
    if project_filter:
        chosen = [p for p in projects if p["name"].lower() == project_filter.lower()]
        if chosen and all(m[0].lower() != project_filter.lower() for m in matched):
            matched.insert(0, (chosen[0]["name"], ["使用者指定"]))

    return {
        "mode": "target",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "raw_target": raw_target,
        "normalized_repo": repo,
        "user_note": note,
        "project_filter": project_filter,
        "gh_verified": gh_info,
        "roster_match": roster_hit,
        "matched_projects": [{"project": p, "keywords": kws} for p, kws in matched],
        "active_projects": [
            {"name": p["name"], "heading": p["heading"], "now_path": p["now_path"], "highlights": p["highlights"]}
            for p in projects
            if not project_filter or p["name"].lower() == project_filter.lower()
        ],
        "dispositions": [{"id": k, "desc": v} for k, v in FIVE_DISPOSITIONS],
    }


def render_markdown(packet: dict[str, Any]) -> str:
    """把檢視包轉為高密度繁體中文 Markdown（嚴禁 LaTeX 語法）。"""
    lines: list[str] = []
    if packet["mode"] == "scan":
        c = packet["counts"]
        lines.append(f"# 範圍 C 競品與收錄交叉檢視包（近 {packet['days']} 天）")
        lines.append(f"- 產生時間：{packet['generated_at']}")
        lines.append(
            f"- 漏斗統計：掃描 {c['scanned_items']} 筆手動收錄 → 精選深挖 **{c['deep_candidates']}** 項"
            f"（上限 {packet['max_deep']}）、觀察備選 {c['overflow_candidates']} 項、降噪濾除 {c['filtered_out']} 項"
        )
        lines.append(
            "- 活躍專案定位："
            + ("、".join(p["name"] for p in packet["active_projects"]) or "（未偵測到 NOW.md）")
        )
        lines.append("")
        lines.append(f"## 建議深挖標的（最多 {packet['max_deep']} 項）")
        if not packet["deep_candidates"]:
            lines.append("- 本期無符合條件的外部競品或工具候選，無需硬產報告。")
        for idx, cand in enumerate(packet["deep_candidates"], 1):
            badge = " [快車道]" if cand["fast_track"] else ""
            lines.append(f"### {idx}. [{cand['id']}] {cand['title']}{badge}（分數 {cand['score']}）")
            lines.append(f"- 分類 / 時間：{cand['category']} | {cand['created_at']}")
            lines.append(f"- 連結：{cand['url']}")
            if cand["user_note"]:
                lines.append(f"- 使用者備註：{cand['user_note']}")
            if cand["matched_projects"]:
                p_str = "；".join(
                    f"{m['project']}（{', '.join(m['keywords'])}）" for m in cand["matched_projects"][:3]
                )
                lines.append(f"- 關聯我方專案：{p_str}")
            if cand["repos"]:
                repo_bits = []
                for r in cand["repos"]:
                    gh = packet["gh_verified"].get(r)
                    if gh and gh.get("ok"):
                        rel = f" / {gh['latest_release']}" if gh.get("latest_release") else ""
                        arch = " [已封存]" if gh.get("archived") else ""
                        repo_bits.append(
                            f"`{gh['repo']}` (★{gh['stars']}, {gh['license']}, push {gh['pushed_at']}{rel}{arch}, {gh['verified_on']} gh api)"
                        )
                    elif gh and not gh.get("ok"):
                        repo_bits.append(f"`{r}` (gh api 查詢失敗：{gh.get('error')})")
                    else:
                        repo_bits.append(f"`{r}`")
                lines.append("- 涉及 GitHub Repo：" + "；".join(repo_bits))
            if cand["roster_matches"]:
                rm = "；".join(
                    f"{h['id']} ({h['status']}: {h['reason'][:60]})" for h in cand["roster_matches"]
                )
                lines.append(f"- 名冊查重命中：{rm}")
            lines.append(f"- 篩選依據：{'；'.join(cand['score_reasons'])}")
            lines.append(f"- 白話摘要：{cand['summary'][:200]}")
            lines.append("")

        if packet["overflow_candidates"]:
            lines.append("## 其餘候選（本期不深挖，防過度消耗）")
            for ov in packet["overflow_candidates"][:10]:
                lines.append(f"- [{ov['id']}] {ov['title']}（分數 {ov['score']}，repos: {', '.join(ov['repos']) or '無'}）")
            lines.append("")

        if packet["filtered_out"]:
            lines.append(f"## 降噪濾除摘要（共 {len(packet['filtered_out'])} 筆）")
            for fo in packet["filtered_out"][:8]:
                lines.append(f"- [{fo['id']}] {fo['title']} — {fo['reason']}")
            if len(packet["filtered_out"]) > 8:
                lines.append(f"- ...其餘 {len(packet['filtered_out']) - 8} 筆略")
            lines.append("")
    else:
        lines.append(f"# 範圍 C 即時單一專案對決包：{packet['normalized_repo'] or packet['raw_target']}")
        lines.append(f"- 產生時間：{packet['generated_at']}")
        if packet["user_note"]:
            lines.append(f"- 使用者提問：{packet['user_note']}")
        gh = packet.get("gh_verified")
        if isinstance(gh, dict):
            if gh.get("ok"):
                rel = f"｜最新 Release：{gh['latest_release']}" if gh.get("latest_release") else ""
                lines.append(
                    f"- 一手 GitHub 實測（{gh['verified_on']} gh api）：★{gh['stars']}｜授權 {gh['license']}｜最後 push {gh['pushed_at']}{rel}｜封存={gh['archived']}"
                )
                if gh.get("description"):
                    lines.append(f"- 官方簡介：{gh['description']}")
            else:
                lines.append(f"- GitHub 實測失敗：{gh.get('error')}")
        if packet.get("roster_match"):
            rm = packet["roster_match"]
            lines.append(
                f"- OmniKit 名冊查重：`{rm['id']}`（狀態 `{rm['status']}`，槽位 {rm['slots']}，原因：{rm['reason']}）"
            )
        if packet["matched_projects"]:
            p_str = "；".join(
                f"{m['project']}（{', '.join(m['keywords'])}）" for m in packet["matched_projects"]
            )
            lines.append(f"- 關聯我方專案：{p_str}")
        lines.append("")

    lines.append("## 強制深度檢視與五選一處置協定（禁建 pending 墳場）")
    lines.append("對上方每一個深挖標的，執行 Agent 必須完成下列四點才算結案：")
    lines.append("1. **一手原始碼驗證**：克隆或檢視實際程式碼／`SKILL.md`／tool schema，禁止只轉述貼文或 README 行銷文。")
    lines.append("2. **防迎合反例**：至少列 1 條具體缺陷、平台限制（含 Windows 實況）或社群反例。")
    lines.append("3. **改判條件**：明確寫出「什麼可檢驗的未來事實會推翻本結論」。")
    lines.append("4. **五選一結案處置（必擇一，禁止留 pending）**：")
    for code, desc in FIVE_DISPOSITIONS:
        lines.append(f"   - `{code}`：{desc}")
    return "\n".join(lines) + "\n"


def run_selftest() -> int:
    """完全離線的自我驗證，確保過濾、快車道、repo 萃取、insight 排除、去重與 target 模式皆正確。"""
    with tempfile.TemporaryDirectory(prefix="omnikit-scope-c-selftest-") as td:
        tmp = Path(td)
        db_path = tmp / "omnikeep.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE items (
                id TEXT PRIMARY KEY, url TEXT, source_type TEXT, category_name TEXT,
                title_l1 TEXT, summary_l1 TEXT, tech_tags TEXT, is_starred INTEGER,
                is_read INTEGER, origin TEXT, user_note TEXT, agent_status TEXT,
                created_at TEXT, deep_analysis TEXT
            );
            CREATE TABLE item_citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source_parent_id TEXT,
                target_name TEXT, target_canonical_url TEXT, mention_context TEXT
            );
        """)
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [
            ("i1", "https://threads.net/post/1", "web", "AI工具", "OpenSpec Skill Router",
             "自然語言自動路由 Skills", '["Claude","Skills"]', 1, 0, "manual", "#競品 OmniKit", "none", now_iso, ""),
            ("i2", "https://github.com/bitbonsai/mcpvault", "web", "知識管理", "MCPVault Obsidian",
             "Obsidian Vault MCP 讀寫工具", '["Obsidian","MCP"]', 0, 0, "manual", "", "none", now_iso, ""),
            ("i3", "https://example.com/food", "web", "美食", "台北拉麵清單",
             "週末吃拉麵推薦", '["生活"]', 0, 0, "manual", "下次去", "none", now_iso, ""),
            ("i4", "https://github.com/acme/radar-item", "web", "AI工具", "雷達自動抓的",
             "不該被手動模式撈出", '["Agent"]', 0, 0, "radar", "", "none", now_iso, ""),
            ("i5", "https://github.com/acme/old-rejected", "web", "AI工具", "曾被拒絕的代理",
             "以前拒絕過的 mcp skill 套件", '["MCP"]', 0, 0, "manual", "", "none", now_iso, ""),
            ("i6", "https://github.com/tobi/qmd", "web", "搜尋", "QMD Hybrid Reranker",
             "Markdown 本地語意檢索與 Reranker", '["RAG","QMD"]', 1, 0, "manual", "", "none", now_iso, ""),
            ("i7", "omnikeep://insight/ins_1", "insight", "Insight", "Agent 自己回寫的結論",
             "不該再進漏斗形成自我迎合", '["AgentInsight"]', 1, 0, "manual", "", "none", now_iso, ""),
        ]
        conn.executemany("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.execute(
            "INSERT INTO item_citations (source_parent_id, target_name, target_canonical_url, mention_context) VALUES (?,?,?,?)",
            ("i1", "OpenSpec", "https://github.com/Fission-AI/OpenSpec", "Skill Router"),
        )
        conn.commit()
        conn.close()

        data_dir = tmp / "data"
        (data_dir / "tools").mkdir(parents=True)
        (data_dir / "tools" / "old-rejected.yaml").write_text(
            "id: old-rejected\nname: Old Rejected\nstatus: rejected\nslots: [mcp]\n"
            "url: https://github.com/acme/old-rejected\nreason: Windows 閃退\n",
            encoding="utf-8",
        )
        status_dir = tmp / "status"
        (status_dir / "OmniKit").mkdir(parents=True)
        (status_dir / "OmniKit" / "NOW.md").write_text("# OmniKit — 目前狀態\n- 專案路徑：/tmp/OmniKit\n", encoding="utf-8")
        (status_dir / "OmniKeep").mkdir(parents=True)
        (status_dir / "OmniKeep" / "NOW.md").write_text("# OmniKeep：現在\n- 專案路徑：/tmp/OmniKeep\n", encoding="utf-8")

        items = fetch_recent_items(db_path, days=7, include_radar=False)
        assert {i["id"] for i in items} == {"i1", "i2", "i3", "i5", "i6"}, "radar 與 insight 不應出現在預設手動掃描"

        roster = load_roster_tools(data_dir)
        projects = load_project_profiles(status_dir)
        fake_gh = lambda r: {"repo": r, "verified_on": "2026-11-27", "ok": True, "stars": 1234, "license": "MIT", "archived": False, "pushed_at": "2026-11-26", "latest_release": "v1.0.0", "description": "demo"}
        pkt = build_scan_packet(items, roster, projects, days=7, max_deep=3, verify_gh=True, gh_verifier=fake_gh)

        assert pkt["counts"]["deep_candidates"] == 3, "應嚴格截斷最多 3 項"
        assert [f["id"] for f in pkt["filtered_out"]] == ["i3"], "美食加一般備註仍應被濾除"
        assert pkt["deep_candidates"][0]["id"] == "i1", "明確 #競品 快車道應排第一"
        assert "Fission-AI/OpenSpec" in pkt["deep_candidates"][0]["repos"]

        t_pkt = build_target_packet(
            "https://github.com/acme/old-rejected",
            roster,
            projects,
            project_filter="OmniKit",
            note="確認這工具是否改好了",
            verify_gh=True,
            gh_verifier=fake_gh,
        )
        assert t_pkt["normalized_repo"] == "acme/old-rejected"
        assert t_pkt["roster_match"]["status"] == "rejected"
        assert "Windows 閃退" in render_markdown(t_pkt)

    print("SELFTEST PASS: competitor_watch.py（降噪漏斗、快車道、insight 排除、repo 萃取、Top 3 去重、target 模式）全部通過。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OmniKit 範圍 C：外部競品與收錄交叉檢視漏斗")
    parser.add_argument("--selftest", action="store_true", help="執行離線自我測試（不碰真實資料庫與網路）")
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="掃描 OmniKeep 近期手動收錄並產出 Top N 檢視包")
    p_scan.add_argument("--days", type=int, default=7, help="回看天數（預設 7）")
    p_scan.add_argument("--max-deep", type=int, default=3, help="最多深挖幾項（預設 3，上限 5）")
    p_scan.add_argument("--db", default="", help="omnikeep.db 路徑（預設自動偵測）")
    p_scan.add_argument("--data", type=Path, default=ROOT / "data", help="OmniKit data/ 路徑")
    p_scan.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR, help="狀態板 ~/.omnikit/status 路徑")
    p_scan.add_argument("--include-radar", action="store_true", help="也納入自動雷達項目（預設僅掃手動收錄）")
    p_scan.add_argument("--no-gh", action="store_true", help="不呼叫 gh api 查一手星數")
    p_scan.add_argument("--format", choices=["markdown", "json"], default="markdown")

    p_target = sub.add_parser("target", help="針對單一 GitHub URL 或 owner/repo 產出即時對決包")
    p_target.add_argument("target", help="GitHub URL 或 owner/repo")
    p_target.add_argument("--project", default="", help="指定要比對的我方專案名稱（如 OmniKit、OmniKeep）")
    p_target.add_argument("--note", default="", help="使用者提問或比較重點")
    p_target.add_argument("--data", type=Path, default=ROOT / "data", help="OmniKit data/ 路徑")
    p_target.add_argument("--status-dir", type=Path, default=DEFAULT_STATUS_DIR, help="狀態板 ~/.omnikit/status 路徑")
    p_target.add_argument("--no-gh", action="store_true", help="不呼叫 gh api")
    p_target.add_argument("--format", choices=["markdown", "json"], default="markdown")

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.selftest:
        return run_selftest()
    if not args.command:
        parser.print_help()
        return 2

    roster = load_roster_tools(args.data)
    projects = load_project_profiles(args.status_dir)

    if args.command == "scan":
        db_path = resolve_db_path(args.db)
        if db_path is None:
            print("錯誤：找不到 omnikeep.db，請以 --db 或環境變數 OMNIKEEP_DB 指定路徑。", file=sys.stderr)
            return 1
        try:
            items = fetch_recent_items(db_path, days=args.days, include_radar=args.include_radar)
        except sqlite3.OperationalError as exc:
            print(f"錯誤：無法唯讀開啟資料庫 {db_path}（{exc}）；若為 WAL 模式且服務已停止，請確認有目錄讀取權限或先啟動服務。", file=sys.stderr)
            return 1
        packet = build_scan_packet(
            items,
            roster,
            projects,
            days=args.days,
            max_deep=args.max_deep,
            verify_gh=not args.no_gh,
        )
    elif args.command == "target":
        packet = build_target_packet(
            args.target,
            roster,
            projects,
            project_filter=args.project,
            note=args.note,
            verify_gh=not args.no_gh,
        )
    else:
        parser.print_help()
        return 2

    if args.format == "json":
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(packet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
