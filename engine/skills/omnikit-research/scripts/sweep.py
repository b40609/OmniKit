# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""飽和式調研的輔助：能用程式查的管道一次查完、記帳本、算什麼時候可以停、實測星數與授權。

用法（路徑相對於這個 skill 的資料夾）：
  uv run scripts/sweep.py channels "<關鍵字>" --ledger <帳本.json> [--topic <topic>]... [--limit 20]
      一組關鍵字查 GitHub topic、GitHub 關鍵字（依星數）、awesome 清單、skills.sh、npm、官方 MCP Registry、
      Hacker News，名字記進帳本；查不到的管道也記。
  uv run scripts/sweep.py add <帳本.json> --group "<關鍵字>" --channel web-zh|web-en|producthunt|related|... --names A B ...
      把網頁搜尋這類 agent 自己查的結果記進同一組。
  uv run scripts/sweep.py related <owner/repo> [--ledger <帳本.json> --group "<關鍵字>"] [--forks 10]
      主要專案星數最高的 fork，加上 README 裡連到的其他 GitHub repo（競品、awesome 清單的條目）。
  uv run scripts/sweep.py status <帳本.json>
      每組的新名字數、連續幾組沒有新名字、可不可以停、哪些管道沒查過或查不到。
  uv run scripts/sweep.py verify <owner/repo>...
      用 gh api 實測星數、授權、是否封存、最後 push，附查詢日期。
  uv run scripts/sweep.py --selftest

只送關鍵字與 repo 名稱出去。GitHub 走本機 gh（要先 gh auth login）；其他都是不用金鑰的公開端點。
skills.sh 依 IP 限速：每次至少隔 3 秒，被擋就記「查不到」，不繞過。
"""
import argparse
import base64
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

STOP_AFTER = 3  # 連續幾組沒有新名字就停
# 每組關鍵字都要查的：這支自動查的七個，加上至少一種網頁搜尋（web-zh 或 web-en）
SCRIPT_CHANNELS = ("github-topic", "github-keyword", "awesome", "skills-sh", "npm", "mcp-registry", "hn")
WEB = ("web-zh", "web-en")
# 整次調研至少各查一次的
ONCE = {"web-zh": "中文網頁搜尋", "web-en": "英文網頁搜尋", "producthunt": "Product Hunt（網頁搜尋 site:producthunt.com）",
        "related": "主要專案的 fork 與 README 提到的競品（related）"}
HN = "https://hn.algolia.com/api/v1/search"
NPM = "https://registry.npmjs.org/-/v1/search"
REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"
SKILLS = "https://skills.sh/api/search"
SKILLS_GAP = 3
STOP_WORDS = {"mcp", "skill", "skills", "plugin", "plugins", "agent", "agents", "claude", "codex", "tool", "tools",
              "server", "servers", "ai", "for", "the", "and", "with", "llm", "cli", "a", "an", "to", "of"}
REPO = re.compile(r"github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)")
NOT_REPO_OWNERS = {"orgs", "topics", "sponsors", "features", "marketplace", "apps", "settings", "about", "login",
                   "collections", "search", "site", "pricing", "enterprise", "users", "user-attachments"}


# ---------- 名字與帳本 ----------

def repo_of(text):
    """從網址或文字抓出 owner/repo（小寫）；不是 repo 的（topics、orgs…）回 None。"""
    m = REPO.search(text or "")
    if not m or m.group(1).lower() in NOT_REPO_OWNERS:
        return None
    name = re.sub(r"\.git$", "", m.group(2)).rstrip(".")
    return f"{m.group(1)}/{name}".lower() if name else None


def key_of(name):
    """帳本裡比對用的名字：有 owner/repo 就用它，否則用小寫、去掉空白與標點的名稱。"""
    repo = repo_of(name) or (name.lower() if re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", name or "") else None)
    return repo or re.sub(r"[^0-9a-z一-鿿]+", "", (name or "").lower())


def short(key):
    return re.sub(r"[^0-9a-z]+", "", key.split("/")[-1])


def seen_before(key, keys, shorts):
    """repo 比全名；沒有 owner 的名字也比 repo 的短名，避免「archify」跟「tt-a1i/archify」算成兩個。"""
    if key in keys:
        return True
    return ("/" not in key and key in shorts) or ("/" in key and short(key) in keys)


def load(path):
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"created": dt.date.today().isoformat(), "groups": []}


def save(path, ledger):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


def record(ledger, group, channel, names, error=None):
    """一個管道的結果記進一組（同一組可以分好幾次記）。error 不是 None 就是「查不到」。"""
    g = next((x for x in ledger["groups"] if x["group"] == group), None)
    if g is None:
        g = {"group": group, "channels": {}}
        ledger["groups"].append(g)
    c = g["channels"].setdefault(channel, {"names": [], "errors": []})
    for n in names:
        if n and n not in c["names"]:
            c["names"].append(n)
    if error:
        c["errors"].append(error)
    return g


def status(ledger):
    """依帳本的組別順序算每組的新名字。可以停 = 連續 STOP_AFTER 組沒有新名字，而且 ONCE 的管道都查過。
    一組裡有該查的管道沒查過，那組不算「沒有新名字」（還沒查完），連續數歸零。"""
    keys, shorts, streak, rows = set(), set(), 0, []
    for g in ledger["groups"]:
        names = []
        for c in g["channels"].values():
            names += c["names"]
        new = []
        for n in names:
            k = key_of(n)
            if k and not seen_before(k, keys, shorts) and k not in [key_of(x) for x in new]:
                new.append(n)
        for n in names:
            k = key_of(n)
            if k and not seen_before(k, keys, shorts):
                keys.add(k)
                shorts.add(short(k))
        failed = sorted(ch for ch, c in g["channels"].items() if c["errors"] and not c["names"])
        missing = [ch for ch in SCRIPT_CHANNELS if ch not in g["channels"]]
        if not any(ch in g["channels"] for ch in WEB):
            missing.append("web-zh 或 web-en")
        complete = not missing
        streak = streak + 1 if (complete and not new) else 0
        rows.append({"group": g["group"], "names": len({key_of(n) for n in names if key_of(n)}), "new": new,
                     "missing": missing, "failed": failed, "complete": complete, "streak": streak,
                     "channels": list(g["channels"])})
    once_missing = [k for k in ONCE if not any(k in g["channels"] for g in ledger["groups"])]
    return {"groups": rows, "total": len(keys), "streak": streak, "once_missing": once_missing,
            "stop": streak >= STOP_AFTER and not once_missing}


# ---------- 連網 ----------

def http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "omnikit-research", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def gh_json(args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout or "gh 失敗").strip().splitlines()[-1][:200])
    return json.loads(out.stdout or "null")


def topics_of(keyword):
    """關鍵字 → GitHub topic：拿掉通用字後空白換 -；中文關鍵字沒有 topic。"""
    words = [w for w in re.findall(r"[a-z0-9]+", keyword.lower())]
    core = [w for w in words if w not in STOP_WORDS]
    out = []
    for ws in (words, core):
        if ws and len("-".join(ws)) >= 3:
            t = "-".join(ws)
            if t not in out:
                out.append(t)
    return out


def term_of(keyword):
    words = [w for w in re.findall(r"[a-z0-9]+", keyword.lower()) if w not in STOP_WORDS]
    return " ".join(words)


GH_FIELDS = "fullName,stargazersCount,description,license,updatedAt,isArchived"


def repo_rows(items):
    return [{"name": i["fullName"].lower(), "stars": i.get("stargazersCount"),
             "license": (i.get("license") or {}).get("key"), "archived": i.get("isArchived"),
             "desc": (i.get("description") or "")[:100]} for i in items or []]


def ch_github_topic(keyword, limit, gh, extra_topics=()):
    rows, notes = [], []
    for t in list(dict.fromkeys([*extra_topics, *topics_of(keyword)])):
        got = repo_rows(gh(["search", "repos", "--topic", t, "--sort", "stars", "--limit", str(limit), "--json", GH_FIELDS]))
        notes.append(f"topic:{t}={len(got)}")
        rows += [r for r in got if r["name"] not in {x["name"] for x in rows}]
    return rows, notes


def ch_github_keyword(keyword, limit, gh):
    return repo_rows(gh(["search", "repos", keyword, "--sort", "stars", "--limit", str(limit), "--json", GH_FIELDS])), []


def ch_awesome(keyword, limit, gh):
    term = term_of(keyword) or keyword
    rows = repo_rows(gh(["search", "repos", f"awesome {term}", "--sort", "stars", "--limit", str(min(limit, 5)),
                         "--json", GH_FIELDS]))
    return rows, ["awesome 清單本身不是候選；挑相關的用 related 抽條目"]


def ch_hn(keyword, limit, fetch):
    doc = fetch(f"{HN}?{urllib.parse.urlencode({'query': keyword, 'tags': 'story', 'hitsPerPage': limit})}")
    rows = []
    for h in doc.get("hits") or []:
        url = h.get("url") or ""
        rows.append({"name": repo_of(url) or (h.get("title") or "")[:80], "points": h.get("points"),
                     "url": url or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                     "lead": not repo_of(url)})
    return rows, ["lead=true 的是文章標題，不是工具名：點進去看，有工具名再用 add 記"]


def ch_npm(keyword, limit, fetch):
    doc = fetch(f"{NPM}?{urllib.parse.urlencode({'text': keyword, 'size': limit})}")
    rows = []
    for o in doc.get("objects") or []:
        p = o.get("package") or {}
        repo = repo_of(((p.get("links") or {}).get("repository")) or "")
        rows.append({"name": repo or p.get("name"), "npm": p.get("name"), "desc": (p.get("description") or "")[:100]})
    return rows, []


def ch_registry(keyword, limit, fetch):
    term = next((w for w in re.findall(r"[a-z0-9]+", keyword.lower()) if w not in STOP_WORDS and len(w) >= 3), None)
    if not term:
        return [], ["關鍵字沒有 3 個字元以上的英文字，Registry 不查"]
    doc = fetch(f"{REGISTRY}?{urllib.parse.urlencode({'search': term, 'version': 'latest', 'limit': min(limit, 100)})}")
    rows = []
    for item in doc.get("servers") or []:
        s = item.get("server") or {}
        repo = repo_of((s.get("repository") or {}).get("url") or "")
        rows.append({"name": repo or s.get("name"), "registry": s.get("name"), "desc": (s.get("description") or "")[:100]})
    return rows, [f"Registry 只比對名稱子字串，送出的字：{term}"]


_last_skills = [0.0]


def ch_skills(keyword, limit, fetch, sleep=time.sleep, clock=time.monotonic):
    term = term_of(keyword)
    if len(term) < 2:
        return [], ["拿掉通用字後沒有關鍵字，skills.sh 不查"]
    wait = SKILLS_GAP - (clock() - _last_skills[0])
    if wait > 0:
        sleep(wait)
    try:
        doc = fetch(f"{SKILLS}?{urllib.parse.urlencode({'q': term, 'limit': limit})}")
    finally:
        _last_skills[0] = clock()
    rows = []
    for s in doc.get("skills") or []:
        src, skill = str(s.get("source") or ""), str(s.get("skillId") or s.get("name") or "")
        if re.fullmatch(r"[A-Za-z0-9-]+/[\w.-]+", src):
            rows.append({"name": src.lower(), "skill": skill, "installs": s.get("installs")})
    return rows, []


def run_channels(keyword, limit, topics=(), gh=gh_json, fetch=http_json):
    jobs = {
        "github-topic": lambda: ch_github_topic(keyword, limit, gh, topics),
        "github-keyword": lambda: ch_github_keyword(keyword, limit, gh),
        "awesome": lambda: ch_awesome(keyword, limit, gh),
        "skills-sh": lambda: ch_skills(keyword, limit, fetch),
        "npm": lambda: ch_npm(keyword, limit, fetch),
        "mcp-registry": lambda: ch_registry(keyword, limit, fetch),
        "hn": lambda: ch_hn(keyword, limit, fetch),
    }
    out = {}
    for name, job in jobs.items():
        try:
            rows, notes = job()
            out[name] = {"rows": rows, "notes": notes, "error": None}
        except (RuntimeError, OSError, ValueError, urllib.error.URLError, subprocess.TimeoutExpired) as e:
            out[name] = {"rows": [], "notes": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}
    return out


def related(repo, forks, gh=gh_json):
    """主要專案星數最高的 fork，加上 README 連到的其他 GitHub repo。"""
    out = {"forks": [], "readme_links": [], "errors": []}
    try:
        items = gh(["api", f"repos/{repo}/forks?sort=stargazers&per_page={forks}"])
        out["forks"] = [{"name": i["full_name"].lower(), "stars": i.get("stargazers_count")} for i in items or []
                        if i.get("stargazers_count")]
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        out["errors"].append(f"forks: {e}")
    try:
        doc = gh(["api", f"repos/{repo}/readme"])
        text = base64.b64decode(doc.get("content") or "").decode("utf-8", "replace")
        me = repo.lower()
        links = []
        for m in REPO.finditer(text):
            r = repo_of(m.group(0))
            if r and r != me and r not in links:
                links.append(r)
        out["readme_links"] = links
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
        out["errors"].append(f"readme: {e}")
    return out


def verify(repos, gh=gh_json, today=None):
    today = (today or dt.date.today()).isoformat()
    rows = []
    for r in repos:
        r = repo_of(r) or r.lower()
        try:
            d = gh(["api", f"repos/{r}"])
            rows.append({"repo": d.get("full_name"), "stars": d.get("stargazers_count"),
                         "license": ((d.get("license") or {}).get("spdx_id")) or "無", "archived": d.get("archived"),
                         "pushed": (d.get("pushed_at") or "")[:10], "checked": today})
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as e:
            rows.append({"repo": r, "error": str(e)[:200], "checked": today})
    return rows


# ---------- 輸出 ----------

def fmt_row(r):
    bits = [r["name"]]
    for k, label in (("stars", "★"), ("installs", "裝"), ("points", "HN分")):
        if r.get(k) is not None:
            bits.append(f"{label}{r[k]}")
    if r.get("license"):
        bits.append(r["license"])
    if r.get("archived"):
        bits.append("已封存")
    if r.get("lead"):
        bits.append(f"(標題) {r.get('url', '')}")
    return " ".join(str(b) for b in bits)


def print_status(st):
    print(f"總共 {st['total']} 個不重複的名字；連續 {st['streak']} 組沒有新名字（要 {STOP_AFTER} 組）："
          + ("可以停" if st["stop"] else "還不能停"))
    if st["once_missing"]:
        print("整次調研還沒查過：" + "、".join(ONCE[k] for k in st["once_missing"]))
    for i, g in enumerate(st["groups"], 1):
        line = f"第 {i} 組「{g['group']}」：{g['names']} 個名字，新的 {len(g['new'])} 個"
        if g["missing"]:
            line += f"；沒查的管道：{', '.join(g['missing'])}（這組不算完成）"
        if g["failed"]:
            line += f"；查不到：{', '.join(g['failed'])}"
        print(line)
        if g["new"]:
            print("  新：" + ", ".join(g["new"][:30]) + (" …" if len(g["new"]) > 30 else ""))


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="飽和式調研的輔助")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("channels")
    c.add_argument("keyword")
    c.add_argument("--ledger", required=True)
    c.add_argument("--topic", action="append", default=[])
    c.add_argument("--limit", type=int, default=20)
    c.add_argument("--json", action="store_true")
    a = sub.add_parser("add")
    a.add_argument("ledger")
    a.add_argument("--group", required=True)
    a.add_argument("--channel", required=True)
    a.add_argument("--names", nargs="*", default=[])
    a.add_argument("--error", help="這個管道查不到的原因（連不上、要 token…）")
    r = sub.add_parser("related")
    r.add_argument("repo")
    r.add_argument("--ledger")
    r.add_argument("--group")
    r.add_argument("--forks", type=int, default=10)
    s = sub.add_parser("status")
    s.add_argument("ledger")
    s.add_argument("--json", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("repos", nargs="+")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.cmd == "channels":
        res = run_channels(args.keyword, args.limit, args.topic)
        ledger = load(args.ledger)
        for ch, out in res.items():
            record(ledger, args.keyword, ch, [x["name"] for x in out["rows"] if not x.get("lead") and ch != "awesome"],
                   out["error"])
        save(args.ledger, ledger)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            for ch, out in res.items():
                head = f"## {ch}：" + (f"查不到（{out['error']}）" if out["error"] else f"{len(out['rows'])} 筆")
                print(head + ("　" + "；".join(out["notes"]) if out["notes"] else ""))
                for x in out["rows"]:
                    print("- " + fmt_row(x))
            print()
            print_status(status(ledger))
        return 0
    if args.cmd == "add":
        ledger = load(args.ledger)
        record(ledger, args.group, args.channel, args.names, args.error)
        save(args.ledger, ledger)
        print_status(status(ledger))
        return 0
    if args.cmd == "related":
        res = related(args.repo, args.forks)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        if args.ledger and args.group:
            ledger = load(args.ledger)
            record(ledger, args.group, "related", [f["name"] for f in res["forks"]] + res["readme_links"],
                   "; ".join(res["errors"]) or None)
            save(args.ledger, ledger)
        return 0
    if args.cmd == "status":
        st = status(load(args.ledger))
        print(json.dumps(st, ensure_ascii=False, indent=1) if args.json else "", end="")
        if not args.json:
            print_status(st)
        return 0
    if args.cmd == "verify":
        for row in verify(args.repos):
            print(json.dumps(row, ensure_ascii=False))
        return 0
    ap.print_help()
    return 1


# ---------- 自我測試（不連網） ----------

def selftest():
    fails = []

    def check(name, ok):
        print(("ok   " if ok else "FAIL ") + name)
        if not ok:
            fails.append(name)

    check("repo_of 抓 owner/repo、去掉 .git", repo_of("https://github.com/tt-a1i/Archify.git") == "tt-a1i/archify")
    check("repo_of 不收 topics、orgs", repo_of("https://github.com/topics/architecture-diagram") is None)
    check("短名對上 repo 不算新", seen_before("archify", {"tt-a1i/archify"}, {"archify"}))
    check("repo 對上先前的短名不算新", seen_before("tt-a1i/archify", {"archify"}, {"archify"}))
    check("不同名字算新", not seen_before("codeflow", {"tt-a1i/archify"}, {"archify"}))
    check("topic 拿掉通用字", topics_of("architecture diagram agent skill") == ["architecture-diagram-agent-skill",
                                                                                "architecture-diagram"])
    check("中文關鍵字沒有 topic", topics_of("架構圖 工具") == [])

    led = {"groups": []}

    def group(name, names, skip=(), web="web-en"):
        for ch in (*SCRIPT_CHANNELS, web):
            if ch not in skip:
                record(led, name, ch, names if ch == web else [])

    group("g1", ["tt-a1i/archify", "codeflow"])
    group("g2", ["Archify"], web="web-zh")   # 短名重複
    group("g3", [])
    st = status(led)
    check("兩組沒有新名字：還不能停", not st["stop"] and st["streak"] == 2)
    group("g4", ["codeflow"], skip=("hn",))   # 少查一個管道：不算完成、連續數歸零
    st = status(led)
    check("少查管道的組不算、連續數歸零", st["streak"] == 0 and st["groups"][-1]["missing"] == ["hn"])
    record(led, "g4", "hn", [], "URLError: 連不上")
    st = status(led)
    check("查不到也算查過，列在 failed", st["groups"][-1]["failed"] == ["hn"] and st["streak"] == 3)
    check("總數不重複", st["total"] == 2)
    check("連續 3 組但 Product Hunt、related 沒查過：還不能停",
          not st["stop"] and st["once_missing"] == ["producthunt", "related"])
    record(led, "g4", "related", ["someone/codeflow"])   # 短名跟先前的 codeflow 一樣
    record(led, "g4", "producthunt", [], "要登入")
    check("整次調研的管道都查過才可以停", status(led)["stop"])
    record(led, "g4", "related", ["x/brand-new"])
    check("related 帶出新名字，連續數歸零", status(led)["streak"] == 0)
    led2 = {"groups": []}
    for ch in SCRIPT_CHANNELS:
        record(led2, "only-script", ch, [])
    check("一組沒做任何網頁搜尋不算完成", status(led2)["groups"][0]["missing"] == ["web-zh 或 web-en"])

    def fake_gh(args):
        if args[:2] == ["search", "repos"]:
            if "--topic" in args:
                return [{"fullName": "tt-a1i/archify", "stargazersCount": 96600, "license": {"key": "apache-2.0"}}]
            return [{"fullName": "Owner/Other", "stargazersCount": 5}]
        if args[0] == "api" and args[1].endswith("/forks?sort=stargazers&per_page=10"):
            return [{"full_name": "a/fork1", "stargazers_count": 3}, {"full_name": "b/fork0", "stargazers_count": 0}]
        if args[0] == "api" and args[1].endswith("/readme"):
            body = "見 https://github.com/Cocoon-AI/architecture-diagram-generator 與 github.com/topics/x 和 github.com/tt-a1i/archify"
            return {"content": base64.b64encode(body.encode()).decode()}
        if args[0] == "api":
            return {"full_name": "tt-a1i/archify", "stargazers_count": 96600, "license": {"spdx_id": "Apache-2.0"},
                    "archived": False, "pushed_at": "2026-11-15T00:00:00Z"}
        raise RuntimeError("unexpected")

    def fake_fetch(url):
        if url.startswith(HN):
            return {"hits": [{"title": "Show HN: Archify", "url": "https://github.com/tt-a1i/archify", "points": 900},
                             {"title": "Diagrams for codebases", "url": "https://blog.example.com/x", "points": 10}]}
        if url.startswith(NPM):
            return {"objects": [{"package": {"name": "repo-viz", "links": {"repository": "git+https://github.com/x/repo-viz.git"}}}]}
        if url.startswith(REGISTRY):
            raise urllib.error.URLError("連不上")
        if url.startswith(SKILLS):
            return {"skills": [{"source": "Konraddzbik/architecture-diagram-skill", "skillId": "arch", "installs": 12},
                               {"source": "https://evil.example", "skillId": "x"}]}
        raise ValueError(url)

    global SKILLS_GAP
    gap, SKILLS_GAP = SKILLS_GAP, 0
    try:
        res = run_channels("architecture diagram", 5, gh=fake_gh, fetch=fake_fetch)
    finally:
        SKILLS_GAP = gap
    check("七個程式管道都有結果或錯誤", set(res) == set(SCRIPT_CHANNELS))
    check("topic 搜尋找得到 Archify", res["github-topic"]["rows"][0]["name"] == "tt-a1i/archify")
    check("Registry 連不上記成錯誤", res["mcp-registry"]["error"] and not res["mcp-registry"]["rows"])
    check("HN：github 網址取 repo、其他標成線索",
          [r["name"] for r in res["hn"]["rows"]][0] == "tt-a1i/archify" and res["hn"]["rows"][1]["lead"])
    check("npm 用 repository 連結", res["npm"]["rows"][0]["name"] == "x/repo-viz")
    check("skills.sh 只收 owner/repo 來源", [r["name"] for r in res["skills-sh"]["rows"]]
          == ["konraddzbik/architecture-diagram-skill"])
    rel = related("tt-a1i/archify", 10, gh=fake_gh)
    check("related：0 星的 fork 不列、README 連結去掉自己與 topics",
          [f["name"] for f in rel["forks"]] == ["a/fork1"]
          and rel["readme_links"] == ["cocoon-ai/architecture-diagram-generator"])
    v = verify(["https://github.com/tt-a1i/archify"], gh=fake_gh, today=dt.date(2026, 11, 16))[0]
    check("verify 附日期與 SPDX 授權", v["license"] == "Apache-2.0" and v["checked"] == "2026-11-16" and v["stars"] == 96600)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "sub" / "ledger.json"
        ledger = load(path)
        record(ledger, "中文 關鍵字", "web-zh", ["工具甲"])
        save(path, ledger)
        check("帳本存取（中文）", load(path)["groups"][0]["channels"]["web-zh"]["names"] == ["工具甲"])

    print(f"\n{'全部通過' if not fails else f'{len(fails)} 項失敗'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
