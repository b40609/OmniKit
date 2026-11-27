# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""第 0 層（免費）：GitHub 現況、名冊比對、硬性門檻，選擇性做 skill 與可執行碼安全掃描。輸出 JSON。

用法：uv run scripts/layer0.py <GitHub 網址或 owner/repo> [--scan]
  --scan  淺層下載 repo，檢查可執行碼／MCP 設定並用 cisco-ai-defense/skill-scanner 的靜態模式掃描每個 skill（不上傳、不需帳號）
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import _github
import _omnikit

SCANNER = "cisco-ai-skill-scanner==2.3.2"
STALE_DAYS = 365
FEW_STARS = 50
SEVERITY = ["SAFE", "INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
STATIC_SCAN_DISCLAIMER = "靜態掃描召回率約 8%（廠商自測），中文自然語言指令無法偵測；通過不代表安全"
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
# 靜態英文規則難以判讀的非拉丁自然語言腳本（中日韓、注音、全形英數、西里爾、阿拉伯）
NON_LATIN_REVIEW_RE = re.compile(
    r"[\u3100-\u312f\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff\uff01-\uff5e]"
)
MAX_CJK_SCAN_BYTES = 512 * 1024

# 套件／建置清單檔：出現即代表目標 repo 含可執行程式或建置腳本，不能只靠靜態 SKILL.md 掃描判通過
EXECUTABLE_MANIFESTS = {
    "package.json",
    "cargo.toml",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "gemfile",
    "makefile",
    "cmakelists.txt",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "composer.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "justfile",
    "flake.nix",
}

SHELL_SCRIPT_EXTS = {
    ".sh", ".bash", ".zsh", ".fish",
    ".ps1", ".psm1", ".psd1",
    ".bat", ".cmd", ".vbs",
}

EXECUTABLE_CODE_EXTS = {
    ".py", ".pyw",
    ".js", ".mjs", ".cjs", ".ts", ".mts", ".cts",
    ".rs", ".go", ".rb", ".pl", ".php",
    ".c", ".cc", ".cpp", ".cs", ".java", ".kt", ".swift",
    ".exe", ".msi", ".dll", ".so", ".dylib", ".wasm",
}

MCP_CONFIG_NAMES = {
    ".mcp.json",
    "mcp.json",
    "mcp_config.json",
    "mcp-config.json",
    "mcp_servers.json",
    "mcp-servers.json",
    "hooks.json",
}

STATIC_DOC_EXTS = {".md", ".markdown", ".txt", ".rst", ".adoc", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf"}
# Skill 資料夾內排除已知二進位／媒體資產副檔名，其餘（含無副檔名、.mdx、.xml、.html、.csv 等）全部納入語意審查檢查
BINARY_ASSET_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff", ".tif", ".avif",
    ".mp3", ".mp4", ".wav", ".ogg", ".flac", ".mov", ".avi", ".mkv", ".webm",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".exe", ".msi", ".dll", ".so", ".dylib", ".wasm", ".pyc", ".pyo", ".class", ".o", ".a",
    ".sqlite", ".db", ".parquet", ".bin", ".dat",
}
ROOT_REPO_DOC_EXACT = {
    "license", "license.md", "license.txt", "copying", "copying.md", "copying.txt",
    "changelog.md", "changelog.txt", "changes.md",
    "contributing.md", "contributing.txt",
    "code_of_conduct.md", "code_of_conduct.txt",
    "security.md", "security.txt",
}
ROOT_README_RE = re.compile(r"^readme(?:[._-][a-z]{2,5}(?:[_-][a-z]{2,4})?)?\.(?:md|markdown|txt|rst)$", re.IGNORECASE)
MAX_INDICATORS_REPORTED = 30


def parse_repo(text):
    """接受 https://github.com/owner/repo/...、github.com/owner/repo、git@github.com:owner/repo.git、owner/repo。"""
    text = (text or "").strip()
    m = (re.match(r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)", text, re.I)
         or re.match(r"^git@github\.com:([^/\s]+)/([^/\s]+)$", text, re.I)
         or re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", text))
    if not m:
        return None
    name = m.group(2)[:-4] if m.group(2).endswith(".git") else m.group(2)
    return f"{m.group(1)}/{name}"


def github(path):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "omnikit-eval"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 403:
            sys.exit("GitHub API 回 403，可能是未登入的每小時 60 次額度用完了，稍後再試")
        raise


def repo_key(url):
    m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", url or "", re.I)
    if not m:
        return None
    name = m.group(2)[:-4] if m.group(2).endswith(".git") else m.group(2)
    return f"{m.group(1)}/{name}".lower()


def _tool_repo_keys(tool):
    urls = [tool.get("url")]
    if tool.get("repo"):
        urls.append(f"https://github.com/{tool['repo']}")
    for source in (tool.get("plugin") or {}).values():
        if isinstance(source, dict):
            urls += [source.get("url"), source.get("repo") and f"https://github.com/{source['repo']}"]
    return {k for u in urls if u and (k := repo_key(u))}


def roster_matches(repo, roster):
    """卡片的 url、plugin 來源指向同一個 repo，或卡片 id 等於 repo 名稱，就算已收錄。"""
    if not repo or "/" not in repo:
        return []
    key, name = repo.lower(), repo.split("/")[1].lower()
    hits = []
    for tool in roster["tools"].values():
        if key in _tool_repo_keys(tool) or tool["id"] == name:
            hits.append(_omnikit.card_summary(tool))
    return hits


def words(text):
    text = (text or "").lower()
    latin = {w for w in re.findall(r"[a-z0-9]+", text) if len(w) >= 3}
    cjk = "".join(re.findall(r"[一-鿿]", text))
    return latin | {cjk[i:i + 2] for i in range(len(cjk) - 1)}


def load_rejected_history(history_path=None):
    """讀取 data/funnel/rejected-history.jsonl 中的拒絕歷史（不存在回空陣列）。"""
    if history_path is False:
        return []
    path = Path(history_path) if history_path is not None else (_omnikit.ROOT / "data" / "funnel" / "rejected-history.jsonl")
    if not path.is_file():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(doc, dict):
                rows.append(doc)
    except OSError:
        return []
    return rows


def similar_rejected(repo, description, roster, history_path=None):
    """跟曾經拒絕的工具同 repo 或用字相近的，列出當時的理由。

    同時比對名冊內 status=rejected 的卡片與 rejected-history.jsonl：
    - 同 repo（url / plugin / history.repo 精確命中）直接給 similarity=1.0。
    - 同類工具依 id、name、url、reason、notes 計算文字相似度，並避免長 notes 稀釋交集。
    """
    target_key = repo.lower() if repo and "/" in repo else None
    mine = words(f"{repo or ''} {description or ''}")

    # 合併名冊 rejected 卡片與拒絕歷史檔（同 tool_id 合併補強，保留卡片完整欄位）
    candidates = {}
    for tool in roster["tools"].values():
        if tool.get("status") != "rejected":
            continue
        candidates[tool["id"]] = {
            "summary": _omnikit.card_summary(tool),
            "repo_keys": _tool_repo_keys(tool),
            "text": f"{tool['id']} {tool.get('name', '')} {tool.get('url', '')} {tool.get('reason', '')} {tool.get('notes', '')}",
        }

    for row in load_rejected_history(history_path):
        tid = row.get("tool_id") or row.get("id")
        if not tid:
            continue
        row_keys = set()
        if row.get("repo"):
            parsed = parse_repo(row["repo"])
            if parsed:
                row_keys.add(parsed.lower())
        if row.get("url"):
            rk = repo_key(row["url"])
            if rk:
                row_keys.add(rk)
        extra_text = " ".join(str(row.get(k) or "") for k in ("tool_id", "name", "repo", "url", "reason", "decision_note", "notes"))
        if tid in candidates:
            candidates[tid]["repo_keys"] |= row_keys
            candidates[tid]["text"] += " " + extra_text
            if not candidates[tid]["summary"].get("reason") and (row.get("reason") or row.get("decision_note")):
                candidates[tid]["summary"]["reason"] = row.get("reason") or row.get("decision_note")
        else:
            summary = {
                "id": tid,
                "name": row.get("name") or tid,
                "status": "rejected",
                "slots": row.get("slots") or [],
            }
            if row.get("url"):
                summary["url"] = row["url"]
            if row.get("reason") or row.get("decision_note"):
                summary["reason"] = row.get("reason") or row.get("decision_note")
            if row.get("decided_at"):
                summary["decided_at"] = str(row["decided_at"])[:10]
            if row.get("notes"):
                summary["notes"] = row["notes"]
            candidates[tid] = {"summary": summary, "repo_keys": row_keys, "text": extra_text}

    found = []
    for tid, item in candidates.items():
        if target_key and target_key in item["repo_keys"]:
            found.append({**item["summary"], "similarity": 1.0})
            continue
        theirs = words(item["text"])
        if not mine or not theirs:
            continue
        common = len(mine & theirs)
        jaccard = common / max(1, len(mine | theirs))
        overlap = common / max(1, min(len(mine), len(theirs)))
        # 至少 2 個以上共通 token 才採用覆蓋係數，避免長 notes 稀釋但也不讓單一泛用字誤中
        score = max(jaccard, overlap * 0.6) if common >= 2 else jaccard
        if score >= 0.15:
            found.append({**item["summary"], "similarity": round(min(score, 0.99), 2)})
    return sorted(found, key=lambda t: (-t["similarity"], t["id"]))[:3]


def thresholds(meta, now):
    out = []
    if meta["archived"]:
        out.append({"rule": "archived", "level": "fail", "detail": "repo 已封存，不再維護"})
    days = (now - datetime.fromisoformat(meta["pushed_at"].replace("Z", "+00:00"))).days
    if days > STALE_DAYS:
        out.append({"rule": "stale", "level": "warn", "detail": f"{days} 天沒有更新"})
    if meta["license"] in (None, "NOASSERTION"):
        out.append({"rule": "license", "level": "warn", "detail": "沒有明確的授權條款"})
    if meta["stars"] < FEW_STARS:
        out.append({"rule": "adoption", "level": "warn", "detail": f"只有 {meta['stars']} 顆星，用的人很少"})
    return out


def tree_digest(folder):
    """整個 skill 資料夾的雜湊：同一份 skill 為不同 agent 複製很多份時只掃一次。"""
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(path.relative_to(folder).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _has_shebang(path):
    try:
        with path.open("rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        return False


def _plugin_has_mcp_or_hooks(path):
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    if not isinstance(doc, dict):
        return False
    return bool(doc.get("mcpServers") or doc.get("mcp_servers") or doc.get("hooks"))


def _inspect_text_for_review(path):
    """檢查檔案是否含靜態層看不懂的非拉丁自然語言，或因過大／非 UTF-8 無法靜態判讀（fail-closed）。

    回傳 (needs_review: bool, reason: str)，其中 reason 為 ""、"non_latin"、"oversized"、"non_utf8" 或 "unreadable"。
    """
    try:
        size = path.stat().st_size
    except OSError:
        return True, "unreadable"
    if size > MAX_CJK_SCAN_BYTES:
        return True, "oversized"
    try:
        raw = path.read_bytes()
    except OSError:
        return True, "unreadable"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return True, "non_utf8"
    if NON_LATIN_REVIEW_RE.search(text):
        return True, "non_latin"
    return False, ""


def _file_contains_cjk(path):
    """向後相容介面：含中日韓／非拉丁腳本，或過大／非 UTF-8 無法判讀時皆回 True（fail-closed）。"""
    needs_review, _ = _inspect_text_for_review(path)
    return needs_review


def _is_root_repo_doc(name_lower, root_skill_text_lower=""):
    """僅排除根目錄的標準說明文件（如 README.md、README_zh.md、LICENSE），且被 SKILL.md 提及者不排除。"""
    if root_skill_text_lower and name_lower in root_skill_text_lower:
        return False
    return name_lower in ROOT_REPO_DOC_EXACT or bool(ROOT_README_RE.match(name_lower))


def inspect_repo_tree(folder):
    """靜態盤點 repo 檔案樹：找出所有 SKILL.md、需語意審查檔案（中日韓／非拉丁／過大／非 UTF-8）以及可執行碼／MCP 設定。"""
    folder = Path(folder)
    skill_files = []
    indicators = []
    cjk_files = []
    unreadable_files = []
    cjk_seen = set()
    aux_text_candidates = []
    root_skill_text_lower = ""

    def _record_review(path, posix):
        if posix in cjk_seen:
            return
        needs_review, reason = _inspect_text_for_review(path)
        if needs_review:
            cjk_seen.add(posix)
            cjk_files.append(posix)
            if reason in ("oversized", "non_utf8", "unreadable"):
                unreadable_files.append(posix)

    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(folder)
        if ".git" in rel.parts:
            continue
        posix = rel.as_posix()
        name_lower = path.name.lower()
        suffix_lower = path.suffix.lower()

        if path.name == "SKILL.md":
            skill_files.append(posix)
            if len(rel.parts) == 1:
                try:
                    if path.stat().st_size <= MAX_CJK_SCAN_BYTES:
                        root_skill_text_lower = path.read_text(encoding="utf-8", errors="ignore").lower()
                except OSError:
                    pass
            _record_review(path, posix)
            continue

        if suffix_lower not in BINARY_ASSET_EXTS:
            aux_text_candidates.append((path, rel, posix, name_lower))

        if name_lower in EXECUTABLE_MANIFESTS:
            indicators.append({"path": posix, "kind": "package_manifest"})
            continue

        if name_lower in MCP_CONFIG_NAMES or (
            "mcp" in name_lower and suffix_lower in {".json", ".yaml", ".yml", ".toml"}
        ):
            indicators.append({"path": posix, "kind": "mcp_config"})
            continue

        if name_lower == "plugin.json" and _plugin_has_mcp_or_hooks(path):
            indicators.append({"path": posix, "kind": "mcp_config"})
            continue

        if suffix_lower in SHELL_SCRIPT_EXTS:
            indicators.append({"path": posix, "kind": "shell_script"})
            _record_review(path, posix)
            continue

        if suffix_lower in EXECUTABLE_CODE_EXTS:
            indicators.append({"path": posix, "kind": "executable_code"})
            if suffix_lower not in BINARY_ASSET_EXTS:
                _record_review(path, posix)
            continue

        if suffix_lower not in STATIC_DOC_EXTS and _has_shebang(path):
            indicators.append({"path": posix, "kind": "shell_script"})
            _record_review(path, posix)

    # Skill 資料夾樹底下的所有非二進位輔助檔（含無副檔名、.md/.mdx/.html/.xml/.csv/.yaml 等）
    # 皆須納入檢查，防止非英文自然語言提示詞注入或非 UTF-8／超大檔繞過第 1 層語意審查
    skill_dirs = [Path(s).parent for s in skill_files]
    for path, rel, posix, name_lower in aux_text_candidates:
        if posix in cjk_seen:
            continue
        for sdir in skill_dirs:
            if sdir == Path("."):
                if len(rel.parts) == 1 and _is_root_repo_doc(name_lower, root_skill_text_lower):
                    continue
                _record_review(path, posix)
                break
            if rel.is_relative_to(sdir):
                _record_review(path, posix)
                break

    cjk_files.sort()
    unreadable_files.sort()

    return {
        "skill_files": skill_files,
        "skill_count": len(skill_files),
        "has_executable_code": bool(indicators),
        "executable_indicators_total": len(indicators),
        "executable_indicators": indicators[:MAX_INDICATORS_REPORTED],
        "has_cjk": bool(cjk_files),
        "cjk_files": cjk_files[:MAX_INDICATORS_REPORTED],
        "unreadable_files": unreadable_files[:MAX_INDICATORS_REPORTED],
    }


def classify_security(scanned):
    """依掃描與檔案樹盤點結果產出結構化 security_badge 與理由清單。

    - "risk_flagged"：檢出 HIGH / CRITICAL 規則或明確高危旗標。
    - "executable_needs_review"：未掃描、掃描報錯、掃出 0 個 SKILL.md、含可執行碼／腳本／MCP 設定，
      或檢出非拉丁自然語言／超大檔／非 UTF-8 檔須進第 1 層語意審查。
    - "skill_scan_pass"：僅確認存在靜態英文／UTF-8 SKILL.md，無可執行碼、高風險規則或語意審查需求。
    """
    if not scanned or not scanned.get("ran"):
        err = (scanned or {}).get("error")
        msg = f"安全掃描未完成（{err}），需人工檢視" if err else "未執行安全掃描，需人工檢視"
        return "executable_needs_review", [msg, STATIC_SCAN_DISCLAIMER]

    skills = scanned.get("skills") or []
    findings = scanned.get("findings") or []
    risk_flags = scanned.get("risk_flags") or []
    reasons = []

    has_cjk = bool(scanned.get("has_cjk"))
    cjk_files = scanned.get("cjk_files") or []
    unreadable_files = scanned.get("unreadable_files") or []
    requires_llm_review = scanned.get("requires_layer1_llm_review")

    high_skills = [s["path"] for s in skills if s.get("max_severity") in ("HIGH", "CRITICAL")]
    high_findings = [f for f in findings if f.get("severity") in ("HIGH", "CRITICAL")]
    if high_skills or high_findings or risk_flags:
        if high_skills:
            reasons.append(f"skill 掃描檢出高風險規則（HIGH/CRITICAL）：{', '.join(high_skills[:5])}")
        if high_findings and not high_skills:
            reasons.append(f"掃描檢出 {len(high_findings)} 條高風險規則（HIGH/CRITICAL）")
        for flag in risk_flags:
            reasons.append(str(flag))
        if has_cjk and cjk_files:
            sample_cjk = ", ".join(cjk_files[:5])
            reasons.append(f"另偵測到需第 1 層語意審查檔案（{sample_cjk}），不可略過人工／LLM 判讀")
        reasons.append(STATIC_SCAN_DISCLAIMER)
        return "risk_flagged", reasons

    error_skills = [s["path"] for s in skills if s.get("error")]
    if scanned.get("error") or error_skills:
        if scanned.get("error"):
            reasons.append(f"安全掃描器錯誤：{scanned['error']}")
        if error_skills:
            reasons.append(f"部分 skill 掃描失敗，不可視為通過：{', '.join(error_skills[:5])}")
        reasons.append(STATIC_SCAN_DISCLAIMER)
        return "executable_needs_review", reasons

    skill_count = scanned.get("skill_count")
    if skill_count is None:
        skill_count = len(skills)
    has_exec = bool(scanned.get("has_executable_code"))
    indicators = scanned.get("executable_indicators") or []

    if skill_count == 0:
        reasons.append("目標 repo 掃出 0 個靜態 SKILL.md，靜態 skill 掃描無法涵蓋，需人工檢視")
    if has_exec:
        sample = ", ".join(i["path"] for i in indicators[:5])
        total = scanned.get("executable_indicators_total", len(indicators))
        suffix = f" 等共 {total} 項" if total > 5 else ""
        reasons.append(f"目標 repo 含可執行碼／設定（{sample}{suffix}），不可只靠靜態 skill 掃描判通過，需人工檢視")
    if has_cjk or requires_llm_review is True or requires_llm_review is None and "requires_layer1_llm_review" in scanned:
        sample_cjk = ", ".join(cjk_files[:5]) if cjk_files else "未列檔案"
        if unreadable_files:
            sample_unreadable = ", ".join(unreadable_files[:5])
            reasons.append(
                f"偵測到檔案過大或非 UTF-8 無法靜態判讀（{sample_unreadable}），必須進第 1 層 LLM／人工語意審查"
            )
        if not unreadable_files or len(cjk_files) > len(unreadable_files):
            reasons.append(
                f"偵測到中日韓／非拉丁自然語言（{sample_cjk}）：靜態層看不懂中文，必須進第 1 層 LLM 語意審查"
            )
    if reasons:
        reasons.append(STATIC_SCAN_DISCLAIMER)
        return "executable_needs_review", reasons

    return "skill_scan_pass", [
        f"已確認 {skill_count} 份靜態 SKILL.md 通過掃描，且未檢出可執行碼、安裝腳本、MCP 設定或需語意審查的非拉丁檔案",
        STATIC_SCAN_DISCLAIMER,
    ]


def run_scanner(folder):
    uv = os.environ.get("UV") or shutil.which("uv") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/uv/uv.exe")
    result = subprocess.run(
        [uv, "tool", "run", "--from", SCANNER, "skill-scanner", "scan", str(folder), "--format", "json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    try:
        doc = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": (result.stderr or result.stdout)[-300:]}
    findings = doc.get("findings") or (doc.get("results") or [{}])[0].get("findings", [])
    worst = max((f.get("severity", "INFO") for f in findings), key=SEVERITY.index, default="SAFE")
    return {
        "max_severity": worst,
        "findings": [
            {"severity": f.get("severity"), "rule": f.get("rule_id") or f.get("id"), "title": f.get("title"),
             "where": Path(str(f.get("file_path") or f.get("location") or "")).as_posix(),
             "line": f.get("line_number"), "snippet": (f.get("snippet") or "")[:200]}
            for f in findings if f.get("severity") in ("MEDIUM", "HIGH", "CRITICAL")
        ],
    }


def summarize(skills):
    """同一份 skill 常為不同 agent 各放一份，內容略有差異；依規則合併，人工只要看一次。"""
    merged = {}
    for skill in skills:
        for f in skill.pop("findings", []):
            key = (f["severity"], f["rule"], f["where"])
            entry = merged.setdefault(key, {**f, "skills": set(), "hits": 0})
            entry["skills"].add(skill["path"])
            entry["hits"] += 1
    found = [{**f, "skills": len(f["skills"])} for f in merged.values()]
    return sorted(found, key=lambda f: (-SEVERITY.index(f["severity"]), f["rule"]))


def remove_readonly(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def scan_local(folder, sha="", scanner_fn=None):
    """對本機目錄執行檔案樹盤點與靜態 SKILL.md 掃描，並計算 security_badge。純唯讀，不修改目標目錄。"""
    folder = Path(folder)
    scanner = scanner_fn or run_scanner
    tree = inspect_repo_tree(folder)
    seen, skills, skipped = set(), [], 0
    for rel_skill in tree["skill_files"]:
        skill_dir = (folder / rel_skill).parent
        digest = tree_digest(skill_dir)
        if digest in seen:
            skipped += 1
            continue
        seen.add(digest)
        rel_dir = skill_dir.relative_to(folder).as_posix()
        skills.append({"path": rel_dir, **scanner(skill_dir)})
    findings = summarize(skills)
    result = {
        "ran": True,
        "sha": sha,
        "skills": skills,
        "duplicates_skipped": skipped,
        "findings": findings,
        "skill_count": tree["skill_count"],
        "has_executable_code": tree["has_executable_code"],
        "executable_indicators_total": tree["executable_indicators_total"],
        "executable_indicators": tree["executable_indicators"],
        "has_cjk": tree["has_cjk"],
        "cjk_files": tree["cjk_files"],
        "unreadable_files": tree["unreadable_files"],
        "requires_layer1_llm_review": tree["has_cjk"],
        "disclaimer": STATIC_SCAN_DISCLAIMER,
    }
    badge, reasons = classify_security(result)
    result["security_badge"] = badge
    result["security_reasons"] = reasons
    return result


def scan(repo, scanner_fn=None):
    tmp = Path(tempfile.mkdtemp(prefix="okl0-"))
    try:
        subprocess.run(
            ["git", "-c", "core.longpaths=true", "clone", "--depth", "1", "--quiet", f"https://github.com/{repo}.git", str(tmp / "r")],
            check=True, capture_output=True,
        )
        sha = subprocess.run(["git", "-C", str(tmp / "r"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        return scan_local(tmp / "r", sha=sha, scanner_fn=scanner_fn)
    finally:
        # git 的 pack 檔是唯讀的，Windows 上要先拿掉唯讀才刪得掉
        if sys.version_info >= (3, 12):
            shutil.rmtree(tmp, onexc=remove_readonly)
        else:
            shutil.rmtree(tmp, onerror=remove_readonly)


def evaluate_target(
    target,
    roster,
    do_scan=False,
    client=None,
    scanner_fn=None,
    scan_fn=None,
    now=None,
    history_path=None,
):
    """以純函式方式執行第 0 層評估（不呼叫 sys.exit），供 layer0 CLI 與 eval_single 共用。"""
    repo = parse_repo(target)
    if not repo:
        raise ValueError(f"看不懂「{target}」：目前第 0 層只支援 GitHub repo")
    gh_client = client or _github.Client()
    info = gh_client.rest(f"repos/{repo}")
    if info is None:
        raise LookupError(f"GitHub 上找不到 {repo}")
    repo = info["full_name"]
    try:
        release = gh_client.rest(f"repos/{repo}/releases/latest")
    except _github.GitHubError:
        release = None
    meta = {
        "description": info.get("description") or "",
        "stars": info["stargazers_count"],
        "forks": info["forks_count"],
        "license": (info.get("license") or {}).get("spdx_id"),
        "archived": info["archived"],
        "created_at": info["created_at"][:10],
        "pushed_at": info["pushed_at"],
        "default_branch": info["default_branch"],
        "latest_release": {"tag": release["tag_name"], "date": release["published_at"][:10]} if release else None,
    }

    now = now or datetime.now(timezone.utc)
    checks = thresholds(meta, now)
    scanned = None
    if do_scan:
        try:
            scanned = scan_fn(repo) if scan_fn else scan(repo, scanner_fn=scanner_fn)
        except Exception as e:
            scanned = {
                "ran": False,
                "error": str(e)[:300],
                "skills": [],
                "duplicates_skipped": 0,
                "findings": [],
                "skill_count": 0,
                "has_executable_code": False,
                "executable_indicators_total": 0,
                "executable_indicators": [],
                "has_cjk": None,
                "cjk_files": [],
                "unreadable_files": [],
                "requires_layer1_llm_review": True,
                "disclaimer": STATIC_SCAN_DISCLAIMER,
            }
            badge, reasons = classify_security(scanned)
            scanned["security_badge"] = badge
            scanned["security_reasons"] = reasons

    security_badge, security_reasons = (
        (scanned["security_badge"], scanned.get("security_reasons") or [])
        if scanned and scanned.get("security_badge")
        else classify_security(scanned)
    )
    if scanned is not None:
        scanned.setdefault("security_badge", security_badge)
        scanned.setdefault("security_reasons", security_reasons)
        scanned.setdefault("disclaimer", STATIC_SCAN_DISCLAIMER)

    # 未掃描、掃描失敗或無法判讀皆視為需要第 1 層語意審查（fail-closed）
    if scanned is None or not scanned.get("ran"):
        requires_layer1_llm_review = True
    else:
        raw_req = scanned.get("requires_layer1_llm_review")
        requires_layer1_llm_review = True if raw_req is None else bool(raw_req)

    # 若執行掃描後為 risk_flagged 或 executable_needs_review，不可輸出 verdict="pass"
    scan_blocks_pass = scanned is not None and security_badge in ("risk_flagged", "executable_needs_review")
    verdict = "fail" if any(c["level"] == "fail" for c in checks) else (
        "warn" if scan_blocks_pass or any(c["level"] == "warn" for c in checks) else "pass"
    )
    matches = roster_matches(repo, roster)
    sim_rejected = similar_rejected(repo, meta["description"], roster, history_path=history_path)

    cjk_files = (scanned or {}).get("cjk_files") or []
    if matches:
        next_step = "已收錄：回報現況與上次的理由，問要不要重新評估"
    elif verdict == "fail":
        next_step = "不往下評，回報 fail 的理由"
    elif requires_layer1_llm_review and cjk_files:
        next_step = f"進第 1 層：讀 README 並逐一語意審查 scan.cjk_files 原文（{', '.join(cjk_files[:5])}，只當資料）、決定槽位、寫卡片"
    elif requires_layer1_llm_review:
        next_step = "進第 1 層：讀 README 並補做語意安全審查（第 0 層未完成靜態排除）、決定槽位、寫卡片"
    else:
        next_step = "進第 1 層：讀 README、決定槽位、寫卡片"

    return {
        "layer": 0,
        "input": target,
        "repo": repo,
        "url": f"https://github.com/{repo}",
        "checked_at": now.strftime("%Y-%m-%d"),
        "omnikit_root": str(_omnikit.ROOT),
        "github": meta,
        "roster": {"matches": matches, "similar_rejected": sim_rejected},
        "thresholds": checks,
        "scan": scanned,
        "security_badge": security_badge,
        "requires_layer1_llm_review": requires_layer1_llm_review,
        "scan_disclaimer": STATIC_SCAN_DISCLAIMER,
        "verdict": verdict,
        "next": next_step,
    }


def main():
    parser = argparse.ArgumentParser(description="第 0 層評估")
    parser.add_argument("target", help="GitHub 網址或 owner/repo")
    parser.add_argument("--scan", action="store_true", help="下載並掃描 repo 裡的 skill 與可執行碼")
    args = parser.parse_args()

    try:
        doc = evaluate_target(args.target, _omnikit.roster(), do_scan=args.scan)
    except (ValueError, LookupError, _github.GitHubError) as e:
        sys.exit(str(e))
    _omnikit.emit(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
