# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""第 0 層批次（FR-22）：一次對 data/tools/*.yaml 全部工具卡做身分與健康檢查。0 LLM token。

- 沒有 url 的卡：用 GitHub 搜尋補出候選 repo。名稱完全對得上而且只有一個的直接採用（標「自動比對」）；
  不明確的寫進 data/funnel/candidates.yaml，讓維護者勾選（chosen 填 owner/repo 或 none），
  再用 --apply 把網址寫回卡片。
- 只淘汰四種：已封存；確認惡意或有未解決的高風險（維護者記在 data/funnel/decisions.yaml）；
  授權不允許散布（只對要進 OmniKit marketplace、也就是有 plugin 來源的卡）；跟 agent 不相容（同樣記在 decisions.yaml）。
- 其他只標旗標：冷卻期（建立不到 14 天）、爆紅（近期星速是平均的 3 倍以上，而且建立不到 90 天）、
  停滯（180 天沒有 commit 而且 365 天沒有 release）、未知（查不到資料；未知不當作通過）。
- 每週記一次星數快照（data/funnel/stars/<日期>.json），近期星速用 7 到 35 天前的快照算；快照不夠時只記總數。
- 健康與採用度指標照 docs/v2/research/eval.md §4.3：H1 活躍、H2 發布、H3 issue 回應、H4 人員集中、
  H5 授權、H6 身分變動、A4 星數與速度；另記相容線索（plugin.json、skills/、AGENTS.md、CI 有沒有跑 Windows）。
  星數只用來標旗標，不加分。

結果寫到 data/funnel/layer0.json，並印出給維護者週報用的摘要。

用法：uv run scripts/batch0.py [--only id,id] [--no-resolve] [--no-issues] [--dry-run]
      uv run scripts/batch0.py --apply      把 candidates.yaml 裡選好的 repo 寫回卡片
      uv run scripts/batch0.py --selftest   離線自我測試
"""
import argparse
import json
import re
import shutil
import statistics
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

import _github
import _omnikit
import layer0

FUNNEL = _omnikit.ROOT / "data" / "funnel"
CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"

COOLING_DAYS = 14
VIRAL_RATIO = 3
VIRAL_MAX_AGE = 90
STALE_COMMIT_DAYS = 180
STALE_RELEASE_DAYS = 365
SNAPSHOT_EVERY = 6        # 距離上次快照不到幾天就不再記
VELOCITY_WINDOW = (7, 35)  # 近期星速用多少天前的快照
CHUNK = 12
ISSUE_WINDOW = (7, 60)     # H3 抽樣：7 到 60 天前開的 issue

# 允許再散布的授權（含 copyleft，散布時要附條款）；不在這裡的（沒有授權、NOASSERTION、NC 類）不能進 marketplace
REDISTRIBUTABLE = {
    "MIT", "MIT-0", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Unlicense", "CC0-1.0",
    "Zlib", "BSL-1.0", "MPL-2.0", "EPL-2.0", "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0", "AGPL-3.0",
    "CC-BY-4.0", "CC-BY-SA-4.0", "Artistic-2.0", "BlueOak-1.0.0", "PSF-2.0", "WTFPL",
}
DECISION_FAILS = {"malicious": "確認惡意", "high_risk": "有未解決的高風險問題", "incompatible": "跟 agent 不相容"}
MAINTAINERS = {"OWNER", "MEMBER", "COLLABORATOR"}

REPO_FIELDS = """
  nameWithOwner description isArchived isFork createdAt pushedAt stargazerCount forkCount
  licenseInfo { spdxId }
  defaultBranchRef { target { ... on Commit {
    recent: history(since: $since) { totalCount }
    last: history(first: 1) { nodes { committedDate } } } } }
  releases(first: 20, orderBy: {field: CREATED_AT, direction: DESC}) { nodes { tagName publishedAt isDraft } }
  claudePlugin: object(expression: "HEAD:.claude-plugin/plugin.json") { __typename }
  claudeMarket: object(expression: "HEAD:.claude-plugin/marketplace.json") { __typename }
  codexPlugin: object(expression: "HEAD:.codex-plugin/plugin.json") { __typename }
  agentsMd: object(expression: "HEAD:AGENTS.md") { __typename }
  skillMd: object(expression: "HEAD:SKILL.md") { __typename }
  skillsDir: object(expression: "HEAD:skills") { ... on Tree { entries { type } } }
  workflows: object(expression: "HEAD:.github/workflows") { ... on Tree { entries { object { ... on Blob { text } } } } }
"""
ISSUE_FIELDS = """
  nodes { ... on Issue { createdAt closedAt author { login }
    comments(first: 15) { nodes { createdAt authorAssociation author { login __typename } } } } }
"""


# ---------- 讀寫 ----------

def load_yaml(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def dump_yaml(path, doc, header):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000)
    path.write_text(header + text, encoding="utf-8", newline="\n")


def dump_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


CANDIDATES_HEADER = """# 第 0 層：沒有 url 的工具卡的候選 repo（batch0.py 產生，維護者勾選）。
# match：clear 已自動採用（auto；同名唯一而且是星數最多的，或符合括號裡的擁有者）；
#        likely 有建議（suggested）但要維護者確認；ambiguous 不明確；none_found 搜尋不到。
# 請在 chosen 填 owner/repo（從 options 挑，或自己找的），不是 GitHub 上的專案就填 none；
# 建議都對的話跑 batch0.py --accept-suggested。改完跑 batch0.py --apply 把網址寫回卡片。
"""
DECISIONS_HEADER = """# 第 0 層：腳本判斷不了、由維護者確認後才淘汰的工具（batch0.py 讀取）。
# fail 只能是 malicious（確認惡意）、high_risk（有未解決的高風險問題）、incompatible（跟 agent 不相容）。
# 每筆都要附 evidence（證據連結或卡片位置）與 date；問題解決了就刪掉那一筆。
# 例：
#   some-tool: {fail: incompatible, evidence: "只支援 macOS（README 的 Requirements）", date: 2026-11-05}
"""


def snapshots(funnel):
    out = []
    for path in sorted((funnel / "stars").glob("*.json")):
        try:
            out.append((date.fromisoformat(path.stem), json.loads(path.read_text(encoding="utf-8"))["repos"]))
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
    return out


# ---------- 對應 repo ----------

def card_repo(tool):
    """卡片 url，其次 plugin 來源；回傳 owner/repo（保留原本大小寫）。"""
    urls = [tool.get("url")]
    for source in (tool.get("plugin") or {}).values():
        if isinstance(source, dict):
            urls += [source.get("url"), source.get("repo") and f"https://github.com/{source['repo']}"]
    for url in urls:
        m = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", url or "", re.I)
        if m:
            name = m.group(2)[:-4] if m.group(2).endswith(".git") else m.group(2)
            return f"{m.group(1)}/{name}"
    return None


def plugin_sources(tool):
    """marketplace 實際散布的來源：[("github", owner/repo) 或 ("npm", 套件@版本)]。"""
    out = set()
    for source in (tool.get("plugin") or {}).values():
        if not isinstance(source, dict):
            continue
        if source.get("source") == "npm":
            out.add(("npm", f"{source['package']}@{source['version']}"))
        else:
            repo = card_repo({"url": source.get("url") or (source.get("repo") and f"https://github.com/{source['repo']}")})
            if repo:
                out.add(("github", repo))
    return sorted(out)


def redistributable(spdx):
    """SPDX 運算式：OR 有一個允許就好，AND 要全部允許。"""
    if not spdx:
        return False
    ids = [t for t in re.findall(r"[A-Za-z0-9.+-]+", spdx) if t not in ("OR", "AND", "WITH")]
    check = all if " AND " in spdx else any
    return bool(ids) and check(i in REDISTRIBUTABLE for i in ids)


def npm_license(spec):
    """npm registry 上這個版本的授權；查不到回 None。"""
    name, _, version = spec.rpartition("@")
    try:
        with urllib.request.urlopen(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}/{version}", timeout=20) as resp:
            lic = json.load(resp).get("license")
    except (OSError, ValueError):
        return None
    return lic.get("type") if isinstance(lic, dict) else lic


def norm(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def search_terms(tool):
    """搜尋字串與括號裡的擁有者提示，例如「competitors-analysis（daymade）」。"""
    hint = re.search(r"[（(]([A-Za-z0-9_.-]+)[）)]", tool["name"])
    base = re.sub(r"[（(].*?[）)]", "", tool["name"]).strip()
    query = base if base.isascii() and norm(base) else tool["id"]
    return query, hint.group(1) if hint else None


MIN_AUTO_STARS = 50  # 自動採用或建議的最低星數，擋掉同名的冷門 repo
DOMINANT = 10        # 建議：名稱包含目標的候選裡，第一名的星數至少是第二名的幾倍


def classify(tool, options, hint):
    """回傳（match, 自動採用的 repo, 建議的 repo）。
    clear：括號擁有者提示對得上的同名 repo；或同名只有一個、而且它就是星數最多的（至少 50 星）。
    likely：名稱包含目標、星數遠高於其他同名候選的，只當建議，維護者用 --accept-suggested 接受。
    2026-11-05 實跑：同名唯一但冷門的（gsd、tavily）常常是錯的，所以要求它同時是星數最多的。"""
    if not options:
        return "none_found", None, None
    targets = {norm(tool["id"]), norm(search_terms(tool)[0])} - {""}
    name_of = lambda o: norm(o["repo"].split("/")[1])  # noqa: E731
    exact = [o for o in options if name_of(o) in targets]
    if hint:
        hinted = [o for o in exact if norm(o["repo"].split("/")[0]) == norm(hint)]
        if len(hinted) == 1:
            return "clear", hinted[0]["repo"], None
    top = max(options, key=lambda o: o["stars"])
    if len(exact) == 1 and exact[0] is top and top["stars"] >= MIN_AUTO_STARS:
        return "clear", top["repo"], None
    related = sorted((o for o in options if any(t in name_of(o) for t in targets)), key=lambda o: -o["stars"])
    if (related and related[0] is top and top["stars"] >= MIN_AUTO_STARS
            and (len(related) == 1 or top["stars"] >= DOMINANT * max(1, related[1]["stars"]))):
        return "likely", None, top["repo"]
    return "ambiguous", None, None


def resolve_missing(client, tools, candidates, today):
    """沒有 url 的卡（內建功能除外）補候選；維護者已經勾過的不再搜尋，自動採用的每次重新比對。"""
    for tool in tools:
        if tool.get("kind") == "native" or card_repo(tool):
            continue
        entry = candidates.get(tool["id"]) or {}
        if entry.get("chosen") and entry.get("chosen") != entry.get("auto"):
            continue  # 維護者決定過了（自動採用的 auto 每次重新比對）
        query, hint = search_terms(tool)
        try:
            options = client.search_repos(f"{query} in:name" + (f" user:{hint}" if hint else ""))
            if not options and hint:
                options = client.search_repos(f"{query} in:name")
        except _github.GitHubError as e:
            candidates[tool["id"]] = {**entry, "query": query, "match": "error", "error": str(e)[:200],
                                      "chosen": entry.get("chosen") if entry.get("chosen") != entry.get("auto") else None,
                                      "checked": today.isoformat()}
            continue
        match, repo, suggested = classify(tool, options, hint)
        candidates[tool["id"]] = {
            "name": tool["name"], "query": query, "match": match,
            "chosen": repo, **({"auto": repo} if repo else {}), **({"suggested": suggested} if suggested else {}),
            "checked": today.isoformat(), "options": options,
        }
    return candidates


def accept_suggested(funnel):
    """維護者一次接受所有「建議」：chosen 填成 suggested。回傳接受的卡片 id。"""
    path = funnel / "candidates.yaml"
    candidates = (load_yaml(path, {}) or {}).get("tools") or {}
    done = []
    for tid, entry in sorted(candidates.items()):
        if entry.get("match") == "likely" and entry.get("suggested") and not entry.get("chosen"):
            entry["chosen"] = entry["suggested"]
            done.append(tid)
    if done:
        dump_yaml(path, {"tools": candidates}, CANDIDATES_HEADER)
    return done


def repo_for(tool, candidates):
    """回傳（repo 或 None, 來源）。來源：card、candidate-auto、candidate、not-on-github、none。"""
    repo = card_repo(tool)
    if repo:
        return repo, "card"
    entry = candidates.get(tool["id"]) or {}
    chosen = entry.get("chosen")
    if chosen == "none":
        return None, "not-on-github"
    if chosen and layer0.parse_repo(chosen):
        return layer0.parse_repo(chosen), "candidate-auto" if chosen == entry.get("auto") else "candidate"
    return None, "none"


# ---------- 查 GitHub ----------

def day(ts):
    return ts[:10] if ts else None


def parse_repo_node(node):
    if not node:
        return None
    target = ((node.get("defaultBranchRef") or {}).get("target") or {})
    last = ((target.get("last") or {}).get("nodes") or [{}])
    releases = [r for r in (node.get("releases") or {}).get("nodes", []) if not r.get("isDraft") and r.get("publishedAt")]
    workflows = (node.get("workflows") or {}).get("entries")
    texts = [((e.get("object") or {}).get("text") or "") for e in workflows or []]
    return {
        "repo": node["nameWithOwner"], "description": (node.get("description") or "")[:300],
        "archived": node["isArchived"], "fork": node["isFork"],
        "created": day(node["createdAt"]), "pushed": day(node["pushedAt"]),
        "stars": node["stargazerCount"], "forks": node["forkCount"],
        "license": (node.get("licenseInfo") or {}).get("spdxId"),
        "commits_90d": (target.get("recent") or {}).get("totalCount"),
        "last_commit": day(last[0].get("committedDate")) if last else None,
        "releases": [{"tag": r["tagName"], "date": day(r["publishedAt"])} for r in releases],
        "compat": {
            "claude_plugin": bool(node.get("claudePlugin")), "claude_marketplace": bool(node.get("claudeMarket")),
            "codex_plugin": bool(node.get("codexPlugin")), "agents_md": bool(node.get("agentsMd")),
            "skill_md": bool(node.get("skillMd")),
            "skills": sum(1 for e in ((node.get("skillsDir") or {}).get("entries") or []) if e.get("type") == "tree"),
            "windows_ci": None if workflows is None else any("windows" in t.lower() for t in texts),
        },
    }


def fetch_meta(client, repos, today):
    """回傳 {owner/repo 小寫: meta 或 None}；整批查詢失敗的，值是 GitHubError。"""
    out = {}
    if not client.has_graphql:
        for repo in repos:
            out[repo.lower()] = fetch_meta_rest(client, repo)
        return out
    since = (datetime.combine(today, datetime.min.time(), timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(0, len(repos), CHUNK):
        chunk = repos[i:i + CHUNK]
        parts = [f"r{j}: repository(owner: {json.dumps(r.split('/')[0])}, name: {json.dumps(r.split('/')[1])}) {{{REPO_FIELDS}}}"
                 for j, r in enumerate(chunk)]
        query = "query($since: GitTimestamp!) {\n" + "\n".join(parts) + "\n}"
        try:
            data = client.graphql(query, {"since": since})
        except _github.GitHubError as e:
            out.update({r.lower(): e for r in chunk})
            continue
        for j, repo in enumerate(chunk):
            out[repo.lower()] = parse_repo_node(data.get(f"r{j}"))
    return out


def fetch_meta_rest(client, repo):
    """未登入時的簡化版：沒有 commit 數與相容線索，停滯用最後 push 近似。"""
    try:
        info = client.rest(f"repos/{repo}")
        if info is None:
            return None
        release = client.rest(f"repos/{repo}/releases/latest")
    except _github.GitHubError as e:
        return e
    return {
        "repo": info["full_name"], "description": (info.get("description") or "")[:300],
        "archived": info["archived"], "fork": info["fork"],
        "created": day(info["created_at"]), "pushed": day(info["pushed_at"]),
        "stars": info["stargazers_count"], "forks": info["forks_count"],
        "license": (info.get("license") or {}).get("spdx_id"),
        "commits_90d": None, "last_commit": None,
        "releases": [{"tag": release["tag_name"], "date": day(release["published_at"])}] if release else [],
        "compat": None,
    }


def contributor_absence(client, repo):
    """CHAOSS Contributor Absence Factor：最少幾個人貢獻一半的 commit（只看前 100 名）。"""
    try:
        people = client.rest(f"repos/{repo}/contributors?per_page=100")
    except _github.GitHubError:
        return None
    counts = sorted((p.get("contributions", 0) for p in people or [] if isinstance(p, dict)), reverse=True)
    if not counts:
        return None
    total, running = sum(counts), 0
    for k, c in enumerate(counts, 1):
        running += c
        if running * 2 >= total:
            return {"factor": k, "contributors_sampled": len(counts)}
    return None


def is_bot(author):
    return not author or author.get("__typename") == "Bot" or (author.get("login") or "").endswith("[bot]")


def issue_health(nodes):
    """H3：抽樣 issue 的真人回覆比例、維護者回覆比例、第一次回覆的小時數中位數、7 天內關閉比例。"""
    issues = [n for n in nodes if n and n.get("createdAt")]
    if not issues:
        return None
    human = maint = closed7 = 0
    waits = []
    for issue in issues:
        opener = (issue.get("author") or {}).get("login")
        opened = datetime.fromisoformat(issue["createdAt"].replace("Z", "+00:00"))
        replies = [c for c in (issue.get("comments") or {}).get("nodes", [])
                   if not is_bot(c.get("author")) and c["author"].get("login") != opener]
        if replies:
            human += 1
            first = min(datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00")) for c in replies)
            waits.append((first - opened).total_seconds() / 3600)
        if any(c.get("authorAssociation") in MAINTAINERS for c in replies):
            maint += 1
        if issue.get("closedAt"):
            closed = datetime.fromisoformat(issue["closedAt"].replace("Z", "+00:00"))
            closed7 += (closed - opened) <= timedelta(days=7)
    n = len(issues)
    return {"sampled": n, "human_reply": round(human / n, 2), "maintainer_reply": round(maint / n, 2),
            "first_reply_hours_median": round(statistics.median(waits), 1) if waits else None,
            "closed_within_7d": round(closed7 / n, 2)}


def fetch_issues(client, repos, today):
    out = {}
    if not client.has_graphql:
        return out
    start, end = today - timedelta(days=ISSUE_WINDOW[1]), today - timedelta(days=ISSUE_WINDOW[0])
    for i in range(0, len(repos), CHUNK):
        chunk = repos[i:i + CHUNK]
        parts = [f"s{j}: search(query: {json.dumps(f'repo:{r} is:issue created:{start}..{end}')}, type: ISSUE, first: 20) {{{ISSUE_FIELDS}}}"
                 for j, r in enumerate(chunk)]
        try:
            data = client.graphql("query {\n" + "\n".join(parts) + "\n}")
        except _github.GitHubError:
            continue
        for j, repo in enumerate(chunk):
            out[repo.lower()] = issue_health((data.get(f"s{j}") or {}).get("nodes") or [])
    return out


# ---------- 判斷 ----------

def days_between(earlier, today):
    return (today - date.fromisoformat(earlier)).days if earlier else None


def velocity(repo, stars, created, today, snaps):
    """近期星速：用 7 到 35 天前最近的一份快照；沒有就回 None（只記總數）。"""
    age = max(1, days_between(created, today))
    base = None
    for when, repos in snaps:
        gap = (today - when).days
        if VELOCITY_WINDOW[0] <= gap <= VELOCITY_WINDOW[1] and repo in repos:
            base = (when, repos[repo])
    a4 = {"stars": stars, "age_days": age, "stars_per_day": round(stars / age, 1)}
    if base:
        gap = (today - base[0]).days
        recent = (stars - base[1]["stars"]) / gap
        a4.update({"window_days": gap, "recent_per_day": round(recent, 1),
                   "ratio": round(recent / (stars / age), 2) if stars else None})
    return a4


def previous_license(repo, snaps):
    for _, repos in reversed(snaps):
        if repo in repos:
            return repos[repo].get("license"), True
    return None, False


def assess(tool, repo, source, meta, extra, decision, snaps, today, duplicates, market=()):
    out = {"id": tool["id"], "name": tool["name"], "status": tool["status"], "slots": tool["slots"],
           "repo": repo, "resolution": source, "flags": [], "fails": [], "notes": []}
    if decision:
        why = DECISION_FAILS.get(decision.get("fail"))
        if why:
            out["fails"].append({"rule": decision["fail"], "detail": f"{why}（維護者確認 {decision.get('date', '')}）：{decision.get('evidence', '')}"})
    if tool.get("kind") == "native":
        out["verdict"] = "fail" if out["fails"] else "skip"
        out["notes"].append("內建功能，不查 repo")
        return out
    if source == "candidate-auto":
        out["notes"].append(f"自動比對到 {repo}（同名唯一而且星數最多，或符合括號裡的擁有者）；不對的話在 candidates.yaml 改 chosen")
    if repo is None:
        detail = "維護者確認不在 GitHub" if source == "not-on-github" else "沒有 url，也還沒選好候選 repo"
        out["flags"].append({"flag": "unknown", "detail": detail})
        out["verdict"] = "fail" if out["fails"] else "unknown"
        return out
    if isinstance(meta, Exception) or meta is None:
        detail = f"GitHub 查詢失敗：{meta}" if meta else f"GitHub 上找不到 {repo}"
        out["flags"].append({"flag": "unknown", "detail": detail})
        out["verdict"] = "fail" if out["fails"] else "unknown"
        return out

    key = meta["repo"].lower()
    if meta["archived"]:
        out["fails"].append({"rule": "archived", "detail": "repo 已封存，不再維護"})
    license_ = meta["license"]
    for m in market:
        if not m["known"]:
            out["flags"].append({"flag": "unknown", "detail": f"查不到 plugin 來源 {m['source']} 的授權"})
        elif not redistributable(m["license"]):
            out["fails"].append({"rule": "license", "detail": f"要進 OmniKit marketplace，但 plugin 來源 {m['source']} 的授權是 {m['license'] or '沒有'}，不允許再散布"})
    if license_ in (None, "NOASSERTION"):
        out["notes"].append("卡片的 repo 偵測不到授權（marketplace 看的是 plugin 來源）" if market
                            else "偵測不到明確授權；要進 marketplace 時會淘汰")

    age = days_between(meta["created"], today)
    if age is not None and age < COOLING_DAYS:
        until = date.fromisoformat(meta["created"]) + timedelta(days=COOLING_DAYS)
        out["flags"].append({"flag": "cooling", "detail": f"建立 {age} 天，冷卻到 {until}：可以做第 1 層，不排實測"})

    a4 = velocity(key, meta["stars"], meta["created"], today, snaps)
    if a4.get("ratio") is not None and a4["ratio"] >= VIRAL_RATIO and age < VIRAL_MAX_AGE:
        out["flags"].append({"flag": "viral", "detail": f"近 {a4['window_days']} 天每天 {a4['recent_per_day']} 星，是平均的 {a4['ratio']} 倍；延後一輪再看"})
    elif "ratio" not in a4:
        out["notes"].append("星數快照不足，還不能判斷爆紅")

    last_commit = meta["last_commit"] or meta["pushed"]
    commit_days = days_between(last_commit, today)
    release_days = days_between(meta["releases"][0]["date"], today) if meta["releases"] else None
    if commit_days is not None and commit_days > STALE_COMMIT_DAYS and (release_days is None or release_days > STALE_RELEASE_DAYS):
        out["flags"].append({"flag": "stale", "detail": f"{commit_days} 天沒有 commit，" + (f"{release_days} 天沒有 release" if release_days is not None else "沒有 release")})

    prev, seen = previous_license(key, snaps)
    h6 = {}
    if repo.lower() != key:
        h6["renamed_from"] = repo
        out["notes"].append(f"repo 改名或轉移：{repo} → {meta['repo']}，要重審")
    if seen and prev != license_:
        h6["license_changed_from"] = prev
        out["notes"].append(f"授權變更：{prev or '沒有'} → {license_ or '沒有'}，要重審")
    if duplicates.get(key):
        out["notes"].append(f"跟 {'、'.join(duplicates[key])} 指向同一個 repo")

    releases_180 = sum(1 for r in meta["releases"] if days_between(r["date"], today) <= 180)
    out.update({
        "repo": meta["repo"],
        "github": {k: meta[k] for k in ("description", "created", "pushed", "stars", "forks", "license", "archived", "fork")},
        "health": {
            "H1": {"last_commit_days": commit_days, "commits_90d": meta["commits_90d"],
                   **({"approximate": "未登入，用最後 push 近似"} if meta["last_commit"] is None else {})},
            "H2": {"releases_180d": releases_180, "last_release": meta["releases"][0] if meta["releases"] else None},
            "H3": extra.get("issues"),
            "H4": extra.get("absence"),
            "H5": {"license": license_},
            "H6": h6,
        },
        "adoption": {"A4": a4},
        "compat": meta["compat"],
    })
    if meta["compat"] is None:
        out["notes"].append("未登入：沒有相容線索與 commit 數")
    out["verdict"] = "fail" if out["fails"] else ("flagged" if out["flags"] else "pass")
    return out


def run(client, roster, today, funnel, resolve=True, issues=True, snapshot=True, only=None, write=True, npm=npm_license):
    tools = [t for t in roster["tools"].values() if not only or t["id"] in only]
    candidates = (load_yaml(funnel / "candidates.yaml", {}) or {}).get("tools") or {}
    decisions = (load_yaml(funnel / "decisions.yaml", {}) or {}).get("tools") or {}
    snaps = snapshots(funnel)

    if resolve:
        candidates = resolve_missing(client, tools, candidates, today)
    targets = {t["id"]: repo_for(t, candidates) for t in tools}
    sources = {t["id"]: plugin_sources(t) for t in tools}
    repos = sorted({r for r, _ in targets.values() if r}
                   | {spec for specs in sources.values() for kind, spec in specs if kind == "github"}, key=str.lower)
    owners = {}
    for tid, (r, _) in targets.items():
        if r:
            owners.setdefault(r.lower(), []).append(tid)

    metas = fetch_meta(client, repos, today)
    live = [m["repo"] for m in metas.values() if isinstance(m, dict)]
    absence = {r.lower(): contributor_absence(client, r) for r in live}
    issue_map = fetch_issues(client, live, today) if issues else {}

    npm_cache = {}

    def market(tid):
        out = []
        for kind, spec in sources[tid]:
            if kind == "github":
                m = metas.get(spec.lower())
                out.append({"source": spec, "license": m["license"] if isinstance(m, dict) else None, "known": isinstance(m, dict)})
            else:
                if spec not in npm_cache:
                    npm_cache[spec] = npm(spec)
                out.append({"source": f"npm:{spec}", "license": npm_cache[spec], "known": npm_cache[spec] is not None})
        return out

    results = []
    for tool in tools:
        repo, source = targets[tool["id"]]
        meta = metas.get(repo.lower()) if repo else None
        key = meta["repo"].lower() if isinstance(meta, dict) else None
        others = [i for i in owners.get(repo.lower(), []) if i != tool["id"]] if repo else []
        extra = {"absence": absence.get(key), "issues": issue_map.get(key)}
        results.append(assess(tool, repo, source, meta, extra, decisions.get(tool["id"]), snaps, today,
                              {key: others} if key else {}, market(tool["id"])))

    counts = {v: sum(1 for r in results if r["verdict"] == v) for v in ("pass", "flagged", "fail", "unknown", "skip")}
    pick = sorted(tid for tid, e in candidates.items() if not e.get("chosen") and e.get("match") != "clear")
    doc = {"layer": "0-batch", "generated": today.isoformat(), "github": client.mode,
           "summary": {**counts, "total": len(results), "candidates_to_pick": pick}, "tools": results,
           "suggested": {tid: candidates[tid]["suggested"] for tid in pick if candidates[tid].get("suggested")}}

    if write:
        if resolve:
            dump_yaml(funnel / "candidates.yaml", {"tools": dict(sorted(candidates.items()))}, CANDIDATES_HEADER)
        if not (funnel / "decisions.yaml").exists():
            dump_yaml(funnel / "decisions.yaml", {"tools": {}}, DECISIONS_HEADER)
        recent = [w for w, _ in snaps if (today - w).days < SNAPSHOT_EVERY]
        if snapshot and not recent and live and not only:
            repos_now = {m["repo"].lower(): {"stars": m["stars"], "license": m["license"]} for m in metas.values() if isinstance(m, dict)}
            dump_json(funnel / "stars" / f"{today}.json", {"date": today.isoformat(), "repos": dict(sorted(repos_now.items()))})
            doc["snapshot"] = f"data/funnel/stars/{today}.json"
        if not only:
            dump_json(funnel / "layer0.json", doc)
    return doc


def apply_candidates(funnel, tools_dir):
    """把 candidates.yaml 選好的 repo 寫進卡片的 url（插在 status 那一行後面）。回傳寫入的卡片 id。"""
    candidates = (load_yaml(funnel / "candidates.yaml", {}) or {}).get("tools") or {}
    done = []
    for tid, entry in sorted(candidates.items()):
        repo = layer0.parse_repo(entry.get("chosen") or "") if entry.get("chosen") != "none" else None
        path = tools_dir / f"{tid}.yaml"
        if not repo or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?m)^url:", text):
            continue
        new, n = re.subn(r"(?m)^(status: .*\n)", rf"\1url: https://github.com/{repo}\n", text, count=1)
        if n:
            path.write_text(new, encoding="utf-8", newline="\n")
            done.append(tid)
    return done


def report(doc):
    s = doc["summary"]
    lines = [f"# 第 0 層批次（{doc['generated']}，GitHub：{doc['github']}）", "",
             f"- 共 {s['total']} 張：通過 {s['pass']}、只標旗標 {s['flagged']}、淘汰 {s['fail']}、未知 {s['unknown']}、不適用 {s['skip']}"]
    if doc.get("snapshot"):
        lines.append(f"- 這週的星數快照：{doc['snapshot']}")
    fails = [t for t in doc["tools"] if t["fails"]]
    lines += ["", "## 淘汰", ""] + ([f"- {t['id']}：{'；'.join(f['detail'] for f in t['fails'])}" for t in fails] or ["- 沒有"])
    lines += ["", "## 旗標", ""]
    names = {"cooling": "冷卻期", "viral": "爆紅", "stale": "停滯", "unknown": "未知"}
    for flag, label in names.items():
        hits = [f"{t['id']}（{f['detail']}）" for t in doc["tools"] for f in t["flags"] if f["flag"] == flag]
        if hits:
            lines.append(f"- {label} {len(hits)} 張：" + "、".join(hits[:12]) + ("…" if len(hits) > 12 else ""))
    notes = [f"- {t['id']}：{n}" for t in doc["tools"] for n in t["notes"] if "要重審" in n or "自動比對" in n]
    if notes:
        lines += ["", "## 要看一下的", ""] + notes
    if s["candidates_to_pick"]:
        lines += ["", "## 請勾選候選 repo（data/funnel/candidates.yaml）", ""]
        lines += [f"- [ ] {tid}" + (f"（建議 {doc['suggested'][tid]}）" if tid in doc.get("suggested", {}) else "")
                  for tid in s["candidates_to_pick"]]
        if doc.get("suggested"):
            lines.append("- 建議都對的話：batch0.py --accept-suggested，再 --apply 寫回卡片")
    return lines


# ---------- 自我測試 ----------

def fake_repo(name, created, stars, archived=False, license_="MIT", last_commit="2026-11-01", releases=(), compat=True):
    return {
        "nameWithOwner": name, "isArchived": archived, "isFork": False, "createdAt": f"{created}T00:00:00Z",
        "pushedAt": f"{last_commit}T00:00:00Z", "stargazerCount": stars, "forkCount": 1,
        "licenseInfo": {"spdxId": license_} if license_ else None,
        "defaultBranchRef": {"target": {"recent": {"totalCount": 5}, "last": {"nodes": [{"committedDate": f"{last_commit}T00:00:00Z"}]}}},
        "releases": {"nodes": [{"tagName": t, "publishedAt": f"{d}T00:00:00Z", "isDraft": False} for t, d in releases]},
        "claudePlugin": {"__typename": "Blob"} if compat else None, "claudeMarket": None, "codexPlugin": None,
        "agentsMd": None, "skillMd": None, "skillsDir": {"entries": [{"type": "tree"}, {"type": "blob"}]},
        "workflows": {"entries": [{"object": {"text": "runs-on: windows-latest"}}]} if compat else None,
    }


def selftest():
    import jsonschema

    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    today = date(2026, 11, 5)
    repos = {
        "o/archived": fake_repo("o/archived", "2024-01-01", 500, archived=True),
        "o/fresh": fake_repo("o/fresh", "2026-11-01", 900),
        "o/viral": fake_repo("o/viral", "2026-09-06", 6000),
        "o/stale": fake_repo("o/stale", "2023-01-01", 300, last_commit="2025-01-01", releases=[("v1", "2025-06-01")], compat=False),
        "o/nolicense": fake_repo("o/nolicense", "2025-01-01", 50, license_=None),
        "o/healthy": fake_repo("o/healthy", "2025-01-01", 4000, releases=[("v2", "2026-10-01")]),
        "New/renamed": fake_repo("New/renamed", "2025-01-01", 10),
        "daymade/competitors-analysis": fake_repo("daymade/competitors-analysis", "2025-06-01", 40),
    }

    def graphql(query, variables):
        if query.lstrip().startswith("query($since"):
            names = re.findall(r'(r\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', query)
            return {alias: repos.get(f"{o}/{n}") or (repos["New/renamed"] if f"{o}/{n}" == "Old/renamed" else None)
                    for alias, o, n in names}
        names = re.findall(r'(s\d+): search\(query: "repo:([^ ]+) ', query)
        issue = {"createdAt": "2026-10-01T00:00:00Z", "closedAt": "2026-10-03T00:00:00Z", "author": {"login": "u"},
                 "comments": {"nodes": [
                     {"createdAt": "2026-10-01T05:00:00Z", "authorAssociation": "NONE", "author": {"login": "dependabot[bot]", "__typename": "Bot"}},
                     {"createdAt": "2026-10-01T10:00:00Z", "authorAssociation": "OWNER", "author": {"login": "m", "__typename": "User"}}]}}
        lonely = {"createdAt": "2026-10-02T00:00:00Z", "closedAt": None, "author": {"login": "v"},
                  "comments": {"nodes": [{"createdAt": "2026-10-02T01:00:00Z", "authorAssociation": "NONE", "author": {"login": "v", "__typename": "User"}}]}}
        return {alias: {"nodes": [issue, lonely]} for alias, _ in names}

    rest = {f"repos/{r}/contributors?per_page=100": [{"contributions": c} for c in (60, 30, 10)] for r in repos}
    search = {
        "competitors-analysis in:name user:daymade": [{"repo": "daymade/competitors-analysis", "description": "", "stars": 40, "pushed": "", "archived": False}],
        "DeepGit in:name": [{"repo": "a/deepgit", "description": "", "stars": 5, "pushed": "", "archived": False},
                            {"repo": "b/deepgit", "description": "", "stars": 9, "pushed": "", "archived": False}],
        "Ghost in:name": [],
        "Ctx in:name": [{"repo": "up/ctx", "description": "", "stars": 6000, "pushed": "", "archived": False},
                        {"repo": "x/ctx", "description": "", "stars": 12, "pushed": "", "archived": False},
                        {"repo": "y/ctx-tool", "description": "", "stars": 40, "pushed": "", "archived": False}],
        "Gsd in:name": [{"repo": "n/gsd", "description": "", "stars": 244, "pushed": "", "archived": False},
                        {"repo": "b/get-shit-done", "description": "", "stars": 64160, "pushed": "", "archived": False}],
    }
    client = _github.Fake(rest=rest, graphql=graphql, search=search)

    def card(tid, url=None, **kw):
        return {"id": tid, "name": kw.pop("name", tid), "slots": kw.pop("slots", ["browser"]), "status": "pending",
                **({"url": f"https://github.com/{url}"} if url else {}), **kw}

    tools = [card("archived", "o/archived"), card("fresh", "o/fresh"), card("viral", "o/viral"),
             card("stale", "o/stale"), card("nolicense", "o/nolicense"),
             card("market", "o/nolicense", plugin={"claude": {"source": "github", "repo": "o/nolicense", "sha": "0" * 40}}),
             card("healthy", "o/healthy"), card("twin", "o/healthy"), card("renamed", "Old/renamed"),
             card("bad", "o/healthy"), card("missing", "o/gone"),
             card("native-x", kind="native"), card("competitors-analysis", name="competitors-analysis（daymade）"),
             card("deepgit", name="DeepGit"), card("ghost", name="Ghost"), card("svc", name="Svc"),
             card("ctx", name="Ctx"), card("gsd", name="Gsd"),
             card("official", "o/nolicense", plugin={"claude": {"source": "git-subdir", "url": "https://github.com/o/healthy.git", "path": "p", "sha": "0" * 40}}),
             card("npm-ok", "o/healthy", plugin={"claude": {"source": "npm", "package": "ok-pkg", "version": "1.0.0"}}),
             card("npm-bad", "o/healthy", plugin={"claude": {"source": "npm", "package": "bad-pkg", "version": "1.0.0"}}),
             card("npm-gone", "o/healthy", plugin={"claude": {"source": "npm", "package": "gone-pkg", "version": "1.0.0"}})]
    roster = {"tools": {t["id"]: t for t in tools}}
    fake_npm = {"ok-pkg@1.0.0": "(MIT OR GPL-3.0)", "bad-pkg@1.0.0": "SEE LICENSE IN LICENSE"}.get

    tmp = Path(tempfile.mkdtemp(prefix="okb0-"))
    try:
        funnel = tmp / "funnel"
        dump_json(funnel / "stars" / "2026-10-29.json", {"date": "2026-10-29", "repos": {
            "o/viral": {"stars": 3600, "license": "MIT"}, "o/healthy": {"stars": 3990, "license": "Apache-2.0"}}})
        dump_yaml(funnel / "decisions.yaml", {"tools": {"bad": {"fail": "malicious", "evidence": "x", "date": "2026-11-05"}}}, DECISIONS_HEADER)
        dump_yaml(funnel / "candidates.yaml", {"tools": {"svc": {"match": "ambiguous", "chosen": "none"}}}, CANDIDATES_HEADER)

        doc = run(client, roster, today, funnel, npm=fake_npm)
        by = {t["id"]: t for t in doc["tools"]}
        rules = lambda tid: {f["rule"] for f in by[tid]["fails"]}  # noqa: E731
        flags = lambda tid: {f["flag"] for f in by[tid]["flags"]}  # noqa: E731

        check("封存：淘汰", by["archived"]["verdict"] == "fail" and rules("archived") == {"archived"})
        check("冷卻期：建立 4 天只標旗標", by["fresh"]["verdict"] == "flagged" and flags("fresh") == {"cooling"})
        check("爆紅：快照算出近期星速 ≥ 3 倍，而且建立不到 90 天",
              "viral" in flags("viral") and by["viral"]["adoption"]["A4"]["ratio"] >= 3)
        check("停滯：180 天沒 commit、365 天沒 release", flags("stale") == {"stale"} and by["stale"]["verdict"] == "flagged")
        check("沒授權但不進 marketplace：只註記，不淘汰", by["nolicense"]["verdict"] == "pass" and any("授權" in n for n in by["nolicense"]["notes"]))
        check("沒授權又要進 marketplace：淘汰", rules("market") == {"license"})
        check("marketplace 看 plugin 來源的授權，不看卡片 url", by["official"]["verdict"] == "pass")
        check("npm 來源：SPDX 運算式有一個允許就通過", by["npm-ok"]["verdict"] == "pass")
        check("npm 來源：不允許散布就淘汰", rules("npm-bad") == {"license"})
        check("npm 來源查不到授權：標未知", "unknown" in flags("npm-gone") and by["npm-gone"]["verdict"] == "flagged")
        check("健康的 repo：通過", by["healthy"]["verdict"] == "pass")
        check("同一個 repo 的兩張卡互相註記", any("twin" in n for n in by["healthy"]["notes"]))
        check("改名或轉移：註記要重審", by["renamed"]["health"]["H6"].get("renamed_from") == "Old/renamed")
        check("維護者確認惡意：淘汰", rules("bad") == {"malicious"})
        check("GitHub 上找不到：未知，不當作通過", by["missing"]["verdict"] == "unknown" and flags("missing") == {"unknown"})
        check("內建功能：不查 repo", by["native-x"]["verdict"] == "skip")
        check("括號裡的擁有者提示：自動比對", by["competitors-analysis"]["resolution"] == "candidate-auto"
              and by["competitors-analysis"]["repo"] == "daymade/competitors-analysis")
        check("兩個同名候選：不明確，列給維護者勾", "deepgit" in doc["summary"]["candidates_to_pick"] and by["deepgit"]["verdict"] == "unknown")
        check("搜尋不到：列給維護者勾", "ghost" in doc["summary"]["candidates_to_pick"])
        check("同名有好幾個、但一個星數遠高於其他：只當建議，不自動採用", by["ctx"]["verdict"] == "unknown"
              and doc["suggested"].get("ctx") == "up/ctx")
        check("同名唯一但冷門、有更紅的不同名 repo：不自動採用", by["gsd"]["repo"] is None and "gsd" not in doc["suggested"])
        check("維護者填 none：不再搜尋、標未知", by["svc"]["resolution"] == "not-on-github"
              and not any(c == ("search", "Svc in:name") for c in client.calls))
        check("H4：最少 1 人貢獻一半的 commit", by["healthy"]["health"]["H4"] == {"factor": 1, "contributors_sampled": 3})
        h3 = by["healthy"]["health"]["H3"]
        check("H3：排除 bot 與發文者自己，算真人與維護者回覆", h3["human_reply"] == 0.5 and h3["maintainer_reply"] == 0.5
              and h3["first_reply_hours_median"] == 10.0 and h3["closed_within_7d"] == 0.5)
        check("相容線索：plugin.json、skills/、CI 跑 Windows", by["healthy"]["compat"]["claude_plugin"]
              and by["healthy"]["compat"]["skills"] == 1 and by["healthy"]["compat"]["windows_ci"] is True)
        check("授權變更：跟上次快照比", any("授權變更" in n for n in by["healthy"]["notes"]))
        check("這週記了星數快照", (funnel / "stars" / "2026-11-05.json").exists() and doc.get("snapshot"))

        schema = json.loads((CONTRACTS / "layer0-batch.schema.json").read_text(encoding="utf-8"))
        try:
            jsonschema.validate(doc, schema)
            check("輸出符合 contracts/layer0-batch.schema.json", True)
        except jsonschema.ValidationError as e:
            check(f"輸出符合 contracts/layer0-batch.schema.json（{e.message[:80]}）", False)

        doc2 = run(client, roster, today + timedelta(days=2), funnel, npm=fake_npm)
        check("6 天內不重複記快照", not doc2.get("snapshot") and len(list((funnel / "stars").glob("*.json"))) == 2)
        saved = load_yaml(funnel / "candidates.yaml", {})["tools"]
        check("維護者填的 chosen 會保留", saved["svc"]["chosen"] == "none")

        check("自動採用的會記 auto，每次重新比對", saved["competitors-analysis"].get("auto") == "daymade/competitors-analysis")
        saved["competitors-analysis"]["chosen"] = "other/ca"
        dump_yaml(funnel / "candidates.yaml", {"tools": saved}, CANDIDATES_HEADER)
        doc5 = run(client, roster, today + timedelta(days=2), funnel, npm=fake_npm, write=False)
        ca = next(t for t in doc5["tools"] if t["id"] == "competitors-analysis")
        check("維護者改掉自動採用的：保留維護者的", ca["resolution"] == "candidate" and ca["repo"] == "other/ca")
        check("--accept-suggested：建議填進 chosen", accept_suggested(funnel) == ["ctx"]
              and load_yaml(funnel / "candidates.yaml", {})["tools"]["ctx"]["chosen"] == "up/ctx")
        saved = load_yaml(funnel / "candidates.yaml", {})["tools"]
        saved["deepgit"]["chosen"] = "b/deepgit"
        dump_yaml(funnel / "candidates.yaml", {"tools": saved}, CANDIDATES_HEADER)
        tools_dir = tmp / "tools"
        tools_dir.mkdir()
        (tools_dir / "deepgit.yaml").write_text("id: deepgit\nname: DeepGit\nslots: []\nstatus: pending\nadded: '2026-11-04'\n", encoding="utf-8")
        (tools_dir / "ghost.yaml").write_text("id: ghost\nname: Ghost\nslots: []\nstatus: pending\nadded: '2026-11-04'\n", encoding="utf-8")
        done = apply_candidates(funnel, tools_dir)
        written = yaml.safe_load((tools_dir / "deepgit.yaml").read_text(encoding="utf-8"))
        check("--apply：選好的寫回卡片，沒選的不動", "deepgit" in done and "ghost" not in done
              and written["url"] == "https://github.com/b/deepgit" and list(written)[4] == "url")
        check("--apply：已經有 url 的不重寫", apply_candidates(funnel, tools_dir) == [])

        anon = _github.Fake(rest={"repos/o/healthy": {"full_name": "o/healthy", "archived": False, "fork": False,
                                                      "created_at": "2025-01-01T00:00:00Z", "pushed_at": "2026-11-01T00:00:00Z",
                                                      "stargazers_count": 10, "forks_count": 0, "license": None},
                                  "repos/o/healthy/releases/latest": None}, mode="anonymous")
        doc3 = run(anon, {"tools": {"healthy": card("healthy", "o/healthy")}}, today, funnel, resolve=False, write=False)
        h = doc3["tools"][0]
        check("未登入：只用 REST，commit 用最後 push 近似", h["verdict"] == "pass" and h["health"]["H1"].get("approximate")
              and not any(c[0] == "graphql" for c in anon.calls))

        broken = _github.Fake(graphql=lambda q, v: (_ for _ in ()).throw(_github.GitHubError("rate limited")))
        doc4 = run(broken, {"tools": {"healthy": card("healthy", "o/healthy")}}, today, funnel, resolve=False, write=False)
        check("查詢失敗：標未知，不當作通過", doc4["tools"][0]["verdict"] == "unknown")
        check("摘要列出淘汰與勾選", "## 淘汰" in "\n".join(report(doc)) and "- [ ] deepgit" in "\n".join(report(doc)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'✓' if ok else '✗'} {name}")
    print(f"batch0 自我測試：{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description="第 0 層批次")
    parser.add_argument("--only", help="只跑這些卡片 id（逗號分隔）；不寫快照與 layer0.json")
    parser.add_argument("--no-resolve", action="store_true", help="不替沒有 url 的卡搜尋候選")
    parser.add_argument("--no-issues", action="store_true", help="不抽樣 issue（H3）")
    parser.add_argument("--dry-run", action="store_true", help="只印結果，不寫檔")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--apply", action="store_true", help="把 candidates.yaml 選好的 repo 寫回卡片")
    parser.add_argument("--accept-suggested", action="store_true", help="接受 candidates.yaml 裡所有的建議")
    parser.add_argument("--selftest", action="store_true", help="離線自我測試")
    args = parser.parse_args()
    _omnikit.utf8_stdout()
    if args.selftest:
        return selftest()
    if args.accept_suggested:
        done = accept_suggested(FUNNEL)
        print(f"接受 {len(done)} 個建議：{'、'.join(done) or '沒有'}；確認後跑 --apply 寫回卡片")
        return 0
    if args.apply:
        done = apply_candidates(FUNNEL, _omnikit.ROOT / "data" / "tools")
        print(f"寫回 {len(done)} 張卡片的 url：{'、'.join(done) or '沒有'}；接著跑 uv run engine/scripts/validate.py")
        return 0
    client = _github.Client()
    if client.mode == "anonymous":
        print("注意：沒有 gh 登入也沒有 GITHUB_TOKEN，改用未登入的 API（每小時 60 次，沒有 commit 數與相容線索）", file=sys.stderr)
    only = set(args.only.split(",")) if args.only else None
    doc = run(client, _omnikit.roster(), args.today, FUNNEL, resolve=not args.no_resolve,
              issues=not args.no_issues, only=only, write=not args.dry_run)
    print("\n".join(report(doc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
