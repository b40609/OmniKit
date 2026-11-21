# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""第 0 層（免費）：GitHub 現況、名冊比對、硬性門檻，選擇性做 skill 安全掃描。輸出 JSON。

用法：uv run scripts/layer0.py <GitHub 網址或 owner/repo> [--scan]
  --scan  淺層下載 repo，用 cisco-ai-defense/skill-scanner 的靜態模式掃描每個 skill（不上傳、不需帳號）
自我測試：uv run engine/skills/omnikit-eval/scripts/layer0.py --selftest
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

import _omnikit

SCANNER = "cisco-ai-skill-scanner==2.3.1"
STALE_DAYS = 365
FEW_STARS = 50
SEVERITY = ["SAFE", "INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


def parse_repo(text):
    """接受 https://github.com/owner/repo/...、github.com/owner/repo、git@github.com:owner/repo.git、owner/repo。"""
    text = text.strip()
    if re.match(r"^(?:https?://)?(?:www\.)?github\.com", text, re.I):
        m = re.match(r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)", text, re.I)
        if not m:
            return None
    else:
        m = (re.match(r"^git@github\.com:([^/\s]+)/([^/\s]+)$", text, re.I)
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


def roster_matches(repo, roster):
    """卡片的 url、plugin 來源指向同一個 repo，或卡片 id 等於 repo 名稱，就算已收錄。"""
    key, name = repo.lower(), repo.split("/")[1].lower()
    hits = []
    for tool in roster["tools"].values():
        urls = [tool.get("url")]
        for source in (tool.get("plugin") or {}).values():
            if isinstance(source, dict):
                urls += [source.get("url"), source.get("repo") and f"https://github.com/{source['repo']}"]
        if key in {repo_key(u) for u in urls if u} or tool["id"] == name:
            hits.append(_omnikit.card_summary(tool))
    return hits


def words(text):
    text = (text or "").lower()
    latin = {w for w in re.findall(r"[a-z0-9]+", text) if len(w) >= 3}
    cjk = "".join(re.findall(r"[一-鿿]", text))
    return latin | {cjk[i:i + 2] for i in range(len(cjk) - 1)}


def similar_rejected(repo, description, roster):
    """跟曾經拒絕的工具用字相近的，列出當時的理由（粗略比對；第 1 層會再看同槽位的拒絕紀錄）。"""
    mine = words(f"{repo} {description}")
    found = []
    for tool in roster["tools"].values():
        if tool["status"] != "rejected":
            continue
        theirs = words(f"{tool['id']} {tool['name']} {tool.get('notes', '')}")
        score = len(mine & theirs) / max(1, len(mine | theirs))
        if score >= 0.15:
            found.append({**_omnikit.card_summary(tool), "similarity": round(score, 2)})
    return sorted(found, key=lambda t: -t["similarity"])[:3]


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


def scan(repo):
    tmp = Path(tempfile.mkdtemp(prefix="okl0-"))
    try:
        subprocess.run(
            ["git", "-c", "core.longpaths=true", "clone", "--depth", "1", "--quiet", f"https://github.com/{repo}.git", str(tmp / "r")],
            check=True, capture_output=True,
        )
        sha = subprocess.run(["git", "-C", str(tmp / "r"), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        seen, skills, skipped = set(), [], 0
        for skill_md in sorted((tmp / "r").rglob("SKILL.md")):
            digest = tree_digest(skill_md.parent)
            if digest in seen:
                skipped += 1
                continue
            seen.add(digest)
            skills.append({"path": skill_md.parent.relative_to(tmp / "r").as_posix(), **run_scanner(skill_md.parent)})
        findings = summarize(skills)
        return {"ran": True, "sha": sha, "skills": skills, "duplicates_skipped": skipped, "findings": findings}
    finally:
        # git 的 pack 檔是唯讀的，Windows 上要先拿掉唯讀才刪得掉
        if sys.version_info >= (3, 12):
            shutil.rmtree(tmp, onexc=remove_readonly)
        else:
            shutil.rmtree(tmp, onerror=remove_readonly)


def main():
    parser = argparse.ArgumentParser(description="第 0 層評估")
    parser.add_argument("target", help="GitHub 網址或 owner/repo")
    parser.add_argument("--scan", action="store_true", help="下載並掃描 repo 裡的 skill")
    args = parser.parse_args()

    repo = parse_repo(args.target)
    if not repo:
        sys.exit(f"看不懂「{args.target}」：目前第 0 層只支援 GitHub repo")
    info = github(f"repos/{repo}")
    if info is None:
        sys.exit(f"GitHub 上找不到 {repo}")
    repo = info["full_name"]
    release = github(f"repos/{repo}/releases/latest")
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

    now = datetime.now(timezone.utc)
    roster = _omnikit.roster()
    checks = thresholds(meta, now)
    scanned = scan(repo) if args.scan else None
    risky = scanned and any(s.get("max_severity") in ("HIGH", "CRITICAL") or s.get("error") for s in scanned["skills"])
    verdict = "fail" if any(c["level"] == "fail" for c in checks) else (
        "warn" if risky or any(c["level"] == "warn" for c in checks) else "pass")
    matches = roster_matches(repo, roster)

    _omnikit.emit({
        "layer": 0,
        "input": args.target,
        "repo": repo,
        "url": f"https://github.com/{repo}",
        "checked_at": now.strftime("%Y-%m-%d"),
        "omnikit_root": str(_omnikit.ROOT),
        "github": meta,
        "roster": {"matches": matches, "similar_rejected": similar_rejected(repo, meta["description"], roster)},
        "thresholds": checks,
        "scan": scanned,
        "verdict": verdict,
        "next": "已收錄：回報現況與上次的理由，問要不要重新評估" if matches else (
            "不往下評，回報 fail 的理由" if verdict == "fail" else "進第 1 層：讀 README、決定槽位、寫卡片"),
    })
    return 0


def selftest():
    # parse_repo
    assert parse_repo("https://github.com/a/b") == "a/b"
    assert parse_repo("https://github.com/a/b/tree/main") == "a/b"
    assert parse_repo("github.com/a/b.git") == "a/b"
    assert parse_repo("git@github.com:a/b.git") == "a/b"
    assert parse_repo(" a/b ") == "a/b"
    assert parse_repo("github.com/owner") is None
    assert parse_repo("www.github.com/owner") is None
    assert parse_repo("https://gitlab.com/a/b") is None
    assert parse_repo("a/b/c") is None

    # repo_key
    assert repo_key("https://github.com/A/B.git") == "a/b"
    assert repo_key("https://gitlab.com/a/b") is None

    # thresholds
    now = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    base_meta = {
        "archived": False,
        "pushed_at": "2024-01-02T00:00:00Z",  # 365 天前
        "license": "MIT",
        "stars": 50,
    }

    # archived: 為 True 出現 fail
    t_archived = thresholds({**base_meta, "archived": True}, now)
    assert any(c["rule"] == "archived" and c["level"] == "fail" for c in t_archived)

    # pushed_at: 距今剛好 365 天不出現 stale、366 天出現
    t_stale_365 = thresholds({**base_meta, "pushed_at": "2024-01-02T00:00:00Z"}, now)
    assert not any(c["rule"] == "stale" for c in t_stale_365)
    t_stale_366 = thresholds({**base_meta, "pushed_at": "2024-01-01T00:00:00Z"}, now)
    assert any(c["rule"] == "stale" and c["level"] == "warn" for c in t_stale_366)

    # license: 為 None 與 "NOASSERTION" 都出現 license
    t_lic_none = thresholds({**base_meta, "license": None}, now)
    assert any(c["rule"] == "license" and c["level"] == "warn" for c in t_lic_none)
    t_lic_noassert = thresholds({**base_meta, "license": "NOASSERTION"}, now)
    assert any(c["rule"] == "license" and c["level"] == "warn" for c in t_lic_noassert)

    # stars: 49 出現 adoption、50 不出現
    t_stars_49 = thresholds({**base_meta, "stars": 49}, now)
    assert any(c["rule"] == "adoption" and c["level"] == "warn" for c in t_stars_49)
    t_stars_50 = thresholds({**base_meta, "stars": 50}, now)
    assert not any(c["rule"] == "adoption" for c in t_stars_50)

    # summarize: 同一組 (severity, rule, where) 出現在兩個 skill，要合併成一筆，skills 為 2、hits 為 2；排序時嚴重度高的在前
    skills_input = [
        {
            "path": "skills/skill_a",
            "findings": [
                {"severity": "MEDIUM", "rule": "rule_med", "where": "file.py"},
                {"severity": "HIGH", "rule": "rule_high", "where": "file.py"},
            ],
        },
        {
            "path": "skills/skill_b",
            "findings": [
                {"severity": "HIGH", "rule": "rule_high", "where": "file.py"},
            ],
        },
    ]
    summary = summarize(skills_input)
    assert len(summary) == 2
    assert summary[0]["severity"] == "HIGH" and summary[0]["rule"] == "rule_high"
    assert summary[0]["skills"] == 2 and summary[0]["hits"] == 2
    assert summary[1]["severity"] == "MEDIUM" and summary[1]["rule"] == "rule_med"
    assert summary[1]["skills"] == 1 and summary[1]["hits"] == 1

    # roster_matches、similar_rejected: 手寫小名冊 dict，不讀 data/
    mock_roster = {
        "tools": {
            "tool_1": {
                "id": "my_tool",
                "name": "My Tool",
                "status": "active",
                "url": "https://github.com/foo/bar",
                "plugin": {},
            },
            "tool_2": {
                "id": "other_tool",
                "name": "Other Tool",
                "status": "rejected",
                "url": "https://github.com/baz/qux",
                "notes": "similar tool for prompt evaluation",
                "plugin": {},
            },
        }
    }

    # roster_matches: 一個命中、一個不命中
    assert len(roster_matches("foo/bar", mock_roster)) == 1
    assert len(roster_matches("nomatch/nomatch", mock_roster)) == 0

    # similar_rejected: 一個命中、一個不命中
    # mine: "test/repo prompt evaluation assistant" -> test, repo, prompt, evaluation, assistant (5 個)
    # theirs: "other_tool", "Other Tool", "similar tool for prompt evaluation" -> other, tool, similar, for, prompt, evaluation (6 個)
    # overlap: "prompt", "evaluation" (2 個)
    # union: 9 個。2 / 9 = 0.222 (落在 0.15 到 0.9 之間)
    rej_hit = similar_rejected("test/repo", "prompt evaluation assistant", mock_roster)
    assert len(rej_hit) == 1
    rej_miss = similar_rejected("unrelated/repo", "completely different keywords here", mock_roster)
    assert len(rej_miss) == 0

    print("layer0 selftest OK")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
