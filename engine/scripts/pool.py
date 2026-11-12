# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""候選池：名冊沒有答案的槽位，從外面的目錄找候選。只找、只檢查、只記下來，不安裝。

三個來源：
- Anthropic 的官方 plugin 目錄（anthropics/claude-plugins-official 的 marketplace.json，一個檔）。
- OpenAI 的官方 plugin 目錄（openai/plugins）。這台有 Codex 就讀 Codex 自己同步下來的那份（~/.codex/.tmp/plugins），
  沒有才上網抓。openai/skills 的 README 寫明已經停止維護，所以不接。
- 官方 MCP Registry。三萬筆以上、沒有品質訊號、搜尋只比對名稱，所以不整包匯入：用槽位的關鍵字查，
  只留有 GitHub repo 的，再用 GitHub 現況篩。
另外，agent 自己上網找到的工具用 add 交進來，過同一套檢查後記在同一個檔，標「名冊外，剛查到」。

會連網：GitHub（raw 與 API）、registry.modelcontextprotocol.io。送出去的只有槽位的關鍵字（名冊裡公開的字），
不送專案名稱、不送這台的任何內容。抓回來的文字只當資料存，不執行。結果存在
%LOCALAPPDATA%\\omnikit\\pool\\，advise.py 只讀那裡的檔，自己不連網。

檢查沿用第 0 層的門檻：封存的不列；沒有授權、一年沒更新、建立不到 14 天、星數不到 50 只標出來；
查不到就寫「未知」，不當作通過。這裡沒有跑 batch0.py 的完整健康指標，也沒有做安全掃描。
每一筆都是名冊外、沒有實測過的，依據只有外部訊號（官方目錄收錄、分類、GitHub 現況）。

用法：
  uv run engine/scripts/pool.py find [--slot id,id] [--refresh] [--no-registry]   找候選，存檔並印出 JSON
  uv run engine/scripts/pool.py add --slot <id> --file <JSON 檔>                  記下 agent 上網找到的
  uv run engine/scripts/pool.py --selftest
"""
import argparse
import json
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / "skills" / "omnikit-eval" / "scripts"))
import _github  # noqa: E402
import edition as editions  # noqa: E402
import profiles  # noqa: E402
import validate  # noqa: E402

ANTHROPIC_REPO = "anthropics/claude-plugins-official"
ANTHROPIC_MARKET = "claude-plugins-official"
ANTHROPIC_URL = f"https://raw.githubusercontent.com/{ANTHROPIC_REPO}/main/.claude-plugin/marketplace.json"
OPENAI_MARKET = "openai-curated"
OPENAI_RAW = "https://raw.githubusercontent.com/openai/plugins/main"
OPENAI_LISTS = (".agents/plugins/marketplace.json", ".agents/plugins/api_marketplace.json")
REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"
OFFICIAL_META = "io.modelcontextprotocol.registry/official"

FRESH_DAYS = 7       # 目錄、Registry 的查詢結果、GitHub 現況，這麼多天內不重抓
KEEP_WEB_DAYS = 30   # agent 上網找到的，留這麼多天
PER_SOURCE = 3       # 每個槽位、每個來源最多列幾個
SHORTLIST = 12       # Registry 每個槽位先留幾個去查 GitHub 現況
REGISTRY_PAGES = 2   # Registry 每個關鍵字最多翻幾頁（一頁 100 筆）
ANON_LIMIT = 30      # 沒登入 GitHub 時最多查幾個 repo（每小時只有 60 次）
STALE_DAYS, FEW_STARS, COOLING_DAYS = 365, 50, 14
CLIP = 300
STOP = {"mcp", "skill", "skills", "plugin", "plugins", "agent", "agents", "claude", "codex", "tool", "tools", "server",
        "servers", "ai", "for", "the", "and", "with", "code", "llm", "cli"}
FLAGS = {"no-license": "沒有標授權", "stale": "超過一年沒更新", "cooling": f"建立不到 {COOLING_DAYS} 天",
         "few-stars": f"星數不到 {FEW_STARS}", "unknown": "GitHub 現況查不到"}
SOURCES = {"anthropic": "Anthropic 官方 plugin 目錄", "openai": "OpenAI 官方 plugin 目錄",
           "registry": "官方 MCP Registry", "web": "agent 上網找到的"}
CAVEAT = "名冊外，沒有實測過；依據只有外部訊號"


# ---------- 小工具 ----------

def http(url, timeout=30, tries=2):
    """抓得到回文字，抓不到（試兩次）回 None。"""
    req = urllib.request.Request(url, headers={"User-Agent": "omnikit-pool", "Accept": "application/json, text/plain"})
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                return None
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        if n + 1 < tries:
            time.sleep(2)
    return None


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def dump(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


def fresh(stamp, today, days=FRESH_DAYS):
    try:
        return (today - date.fromisoformat(str(stamp)[:10])).days < days
    except ValueError:
        return False


def clip(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= CLIP else text[:CLIP] + "…"


def repo_of(*texts):
    """從網址找出 GitHub 的 owner/name（小寫）；不是 GitHub 上的 repo 就回 None。"""
    for text in texts:
        m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+)", str(text or ""))
        if m:
            name = m.group(2).removesuffix(".git")
            if name:
                return f"{m.group(1)}/{name}".lower()
    return None


def norm(text):
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def tokens(text):
    out = []
    for t in re.findall(r"[a-z0-9]+", str(text or "").lower()):
        if t not in STOP:
            out.append(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t)
    return out


# ---------- 匯入兩家官方目錄 ----------

def parse_anthropic(doc):
    out = []
    for p in doc.get("plugins") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        source = p.get("source")
        out.append({
            "id": f"anthropic:{p['name']}", "source": "anthropic", "name": p.get("displayName") or p["name"],
            "description": clip(p.get("description")), "category": p.get("category"), "kind": "plugin",
            "url": p.get("homepage") or (source.get("url") if isinstance(source, dict) else None),
            "repo": repo_of(source.get("url") if isinstance(source, dict) else None, p.get("homepage")),
            "agents": ["claude"],
            "install": {"claude": {"marketplace": ANTHROPIC_MARKET, "add": f"claude plugin marketplace add {ANTHROPIC_REPO}",
                                   "command": f"claude plugin install {p['name']}@{ANTHROPIC_MARKET}"}}})
    return out


def parse_openai(names, manifest):
    """names：marketplace 檔列的 plugin（名稱 → 那一筆）；manifest(name) 回傳該 plugin 的 plugin.json（dict）或 None。"""
    out = []
    for name, listed in names.items():
        doc = manifest(name)
        if not isinstance(doc, dict):
            continue  # 讀不到說明就不收：沒有說明沒辦法比對
        if ((listed.get("policy") or {}).get("installation") or "AVAILABLE") != "AVAILABLE":
            continue
        face = doc.get("interface") or {}
        out.append({
            "id": f"openai:{name}", "source": "openai", "name": face.get("displayName") or name,
            "description": clip(". ".join(filter(None, [doc.get("description"), face.get("longDescription")]))),
            "category": listed.get("category") or face.get("category"), "kind": "plugin",
            "url": doc.get("homepage") or face.get("websiteURL") or f"https://github.com/openai/plugins/tree/main/plugins/{name}",
            "repo": None,  # plugin 本體都在 openai/plugins 裡，沒有各自的 repo 可以查
            "agents": ["codex"], "keywords": [k for k in doc.get("keywords") or [] if isinstance(k, str)],
            "install": {"codex": {"marketplace": OPENAI_MARKET, "command": f"codex plugin add {name}@{OPENAI_MARKET}"}}})
    return out


def openai_names(read):
    names = {}
    for rel in OPENAI_LISTS:
        try:
            doc = json.loads(read(rel) or "")
        except ValueError:
            continue
        for p in doc.get("plugins") or []:
            if isinstance(p, dict) and p.get("name"):
                names.setdefault(p["name"], p)
    return names


def import_openai(home, fetch):
    """有 Codex 就讀它同步下來的那份；沒有才上網抓。回傳（條目, 從哪讀的）。"""
    local = home / ".codex" / ".tmp" / "plugins"

    def read_local(rel):
        try:
            return (local / rel).read_text(encoding="utf-8")
        except OSError:
            return None

    def as_json(text):
        try:
            return json.loads(text or "")
        except ValueError:
            return None

    names = openai_names(read_local)
    if names:
        return parse_openai(names, lambda n: as_json(read_local(f"plugins/{n}/.codex-plugin/plugin.json"))), "這台的 Codex"
    names = openai_names(lambda rel: fetch(f"{OPENAI_RAW}/{rel}"))
    if not names:
        return [], None
    with ThreadPoolExecutor(8) as pool:
        docs = dict(zip(names, pool.map(lambda n: as_json(fetch(f"{OPENAI_RAW}/plugins/{n}/.codex-plugin/plugin.json")), names)))
    return parse_openai(names, docs.get), "openai/plugins"


def refresh(home, state, fetch=http, today=None, force=False):
    """兩家官方目錄 → state/pool/catalog.json。7 天內抓過就不重抓；這次抓不到就留著舊的。"""
    today = today or date.today()
    path = state / "pool" / "catalog.json"
    old = load(path, {})
    if not force and fresh(old.get("fetched"), today) and old.get("entries"):
        return old
    sources, entries = {}, []
    try:
        got = parse_anthropic(json.loads(fetch(ANTHROPIC_URL) or ""))
    except ValueError:
        got = []
    theirs, where = import_openai(home, fetch)
    for key, items, origin in (("anthropic", got, ANTHROPIC_REPO), ("openai", theirs, where)):
        if items:
            sources[key] = {"count": len(items), "from": origin, "fetched": today.isoformat()}
        else:  # 這次抓不到：沿用上次的，並照實寫
            items = [e for e in old.get("entries") or [] if e.get("source") == key]
            kept = (old.get("sources") or {}).get(key) or {}
            sources[key] = {"count": len(items), "from": kept.get("from"), "fetched": kept.get("fetched"),
                            "error": "這次抓不到" + ("，用上次的" if items else "")}
        entries += items
    doc = {"fetched": today.isoformat(), "sources": sources, "entries": entries}
    dump(path, doc)
    return doc


# ---------- 比對 ----------

def score(entry, keywords):
    """槽位的關鍵字一組一組比：一組裡的字要在名稱或說明的同一句裡都出現才算；名稱裡有再加分。
    一組關鍵字去掉通用字（mcp、agent 這類）之後只剩一個字的，那個字要在名稱或條目自己的關鍵字裡才算，
    不然「local llm」會比中每一個說明裡有 local 的條目。回傳（分數, 命中的關鍵字）。"""
    name = set(tokens(entry.get("name")) + tokens(entry["id"].split(":", 1)[-1]))
    extra = set(tokens(entry.get("category")))
    for k in entry.get("keywords") or []:
        extra |= set(tokens(k))
    units = [name | extra] + [name | extra | set(tokens(part)) for part in re.split(r"[.;!?。；！？\n]+", entry.get("description") or "")]
    total, matched = 0, []
    for kw in keywords:
        parts = tokens(kw)
        narrowed = len(parts) == 1 and len(re.findall(r"[a-z0-9]+", kw.lower())) > 1
        if parts and any(all(p in unit for p in parts) for unit in (units[:1] if narrowed else units)):
            total += 2 * len(parts) + (2 if any(p in name for p in parts) else 0)
            matched.append(kw)
    return total, matched


def top(entries, keywords, limit):
    scored = [(s, e, m) for e in entries for s, m in [score(e, keywords)] if s]
    scored.sort(key=lambda x: (-x[0], x[1]["name"].lower()))
    return [{**e, "score": s, "matched": m} for s, e, m in scored[:limit]]


def open_slots(roster, edition="colleague"):
    """哪些槽位要找：這個 agent 還沒有答案（或答案是不知道、也沒記內建功能），名冊也沒有預設或試用的卡。"""
    hidden = {m["id"] for m in roster["modules"] if m.get("maintainer_only") and edition != "maintainer"}
    enabled = roster.get("enabled")
    out = []
    for s in roster["slots"]:
        if s["module"] in hidden or (enabled is not None and s["module"] not in enabled) or not s.get("search"):
            continue
        agents = []
        for agent in ("claude", "codex"):
            a = (s.get("answers") or {}).get(agent) or {}
            if a.get("verdict", "unknown") != "unknown" or a.get("reason"):
                continue
            ready = [c for c in roster["tools"].values() if s["id"] in c.get("slots", [])
                     and c.get("status") in ("default", "trial") and (not c.get("works_with") or agent in c["works_with"])]
            if not ready:
                agents.append(agent)
        if agents:
            out.append({"slot": s["id"], "slot_name": s["name"], "module": s["module"], "keywords": list(s["search"]),
                        "agents": agents})
    return out


def roster_index(roster):
    """名冊裡已經有的：repo 或名稱 → 卡片。用來排除，別裝的附上名冊記的理由。"""
    by_repo, by_name = {}, {}
    for card in roster["tools"].values():
        repo = repo_of(card.get("url"))
        if repo:
            by_repo[repo] = card
        for key in (card["id"], card.get("name")):
            if norm(key):
                by_name[norm(key)] = card
    return by_repo, by_name


def in_roster(entry, index):
    by_repo, by_name = index
    card = by_repo.get(entry.get("repo")) or by_name.get(norm(entry.get("name"))) or by_name.get(norm(entry["id"].split(":", 1)[-1]))
    if not card:
        return None
    if card.get("status") in ("rejected", "retired"):
        return {"code": "roster-no", "tool": card["id"],
                "text": f"名冊記的是{'拒絕' if card['status'] == 'rejected' else '退役'}：{card.get('reason') or '沒有寫理由'}"}
    return {"code": "in-roster", "tool": card["id"], "text": "名冊已經有這張卡，照名冊的評估走"}


# ---------- GitHub 現況 ----------

REPO_QUERY = "isArchived stargazerCount pushedAt createdAt licenseInfo { spdxId }"


def fetch_health(client, repos):
    """repo（owner/name）→ 現況；查不到的寫 unknown 與原因。"""
    out, repos = {}, sorted(set(repos))
    if getattr(client, "has_graphql", False):
        for i in range(0, len(repos), 40):
            chunk = repos[i:i + 40]
            body = " ".join(f'r{n}: repository(owner: {json.dumps(r.split("/")[0])}, name: {json.dumps(r.split("/")[1])}) '
                            f"{{ {REPO_QUERY} }}" for n, r in enumerate(chunk))
            try:
                data = client.graphql(f"query {{ {body} }}")
            except _github.GitHubError as e:
                out.update({r: {"unknown": str(e)[:120]} for r in chunk})
                continue
            for n, r in enumerate(chunk):
                node = (data or {}).get(f"r{n}")
                out[r] = {"unknown": "GitHub 上找不到這個 repo"} if not node else {
                    "archived": node["isArchived"], "stars": node["stargazerCount"], "pushed": (node.get("pushedAt") or "")[:10],
                    "created": (node.get("createdAt") or "")[:10], "license": (node.get("licenseInfo") or {}).get("spdxId")}
        return out
    for n, r in enumerate(repos):
        if n >= ANON_LIMIT:
            out[r] = {"unknown": "沒有登入 GitHub，額度不夠查（gh auth login 之後再跑一次）"}
            continue
        try:
            node = client.rest(f"repos/{r}")
        except _github.GitHubError as e:
            out[r] = {"unknown": str(e)[:120]}
            continue
        out[r] = {"unknown": "GitHub 上找不到這個 repo"} if not node else {
            "archived": node.get("archived", False), "stars": node.get("stargazers_count", 0),
            "pushed": (node.get("pushed_at") or "")[:10], "created": (node.get("created_at") or "")[:10],
            "license": (node.get("license") or {}).get("spdx_id")}
    return out


def flags(health, today):
    if not health or health.get("unknown"):
        return ["unknown"]
    out = []
    if health.get("license") in (None, "NOASSERTION"):
        out.append("no-license")

    def age(stamp):
        try:
            return (today - date.fromisoformat(stamp)).days
        except (TypeError, ValueError):
            return None
    pushed, created = age(health.get("pushed")), age(health.get("created"))
    if pushed is not None and pushed > STALE_DAYS:
        out.append("stale")
    if created is not None and created < COOLING_DAYS:
        out.append("cooling")
    if (health.get("stars") or 0) < FEW_STARS:
        out.append("few-stars")
    return out


class Health:
    """GitHub 現況的本機快取（state/pool/health.json）。"""

    def __init__(self, state, client, today):
        self.path, self.client, self.today = state / "pool" / "health.json", client, today
        self.data = load(self.path, {})

    def get(self, repos):
        need = [r for r in set(repos) if r and not fresh((self.data.get(r) or {}).get("checked"), self.today)]
        if need:
            for r, h in fetch_health(self.client, need).items():
                if h.get("unknown") and "額度" in h["unknown"]:
                    self.data.pop(r, None)  # 額度不夠的不存，下次再查
                    self.data[r] = {**h, "checked": ""}
                else:
                    self.data[r] = {**h, "checked": self.today.isoformat()}
            dump(self.path, self.data)
        return {r: self.data.get(r) for r in repos if r}


def judge(entries, health, today):
    """附上 GitHub 現況與旗標；封存的拿掉。回傳（留下的, 拿掉的）。沒有 repo 的官方目錄條目照樣留，標「沒有 repo 可查」。"""
    kept, dropped = [], []
    for e in entries:
        h = health.get(e.get("repo")) if e.get("repo") else None
        if h and h.get("archived"):
            dropped.append({"id": e["id"], "name": e["name"], "code": "archived", "text": "GitHub 上已經封存"})
            continue
        e = {**e, "flags": flags(h, today) if e.get("repo") else []}
        if h and not h.get("unknown"):
            e["github"] = {k: h.get(k) for k in ("stars", "pushed", "created", "license")}
        elif not e.get("repo"):
            e["github"] = None
        kept.append(e)
    return kept, dropped


# ---------- 官方 MCP Registry ----------

def registry_term(keyword):
    """Registry 的搜尋只比對名稱的子字串，所以一組關鍵字只送第一個有意義的字，其他的在本機比。
    不到 3 個字元的字 Registry 會回 422（實測），跳過。"""
    parts = [t for t in re.findall(r"[a-z0-9]+", keyword.lower()) if t not in STOP and len(t) >= 3]
    return parts[0] if parts else None


def short_name(name):
    return re.sub(r"[^a-z0-9-]+", "-", name.split("/")[-1].lower()).strip("-") or "server"


def registry_install(server):
    """照 Registry 登記的資料組出安裝指令；要金鑰或要填變數的不組。回傳（指令, 說明）。"""
    name = short_name(server.get("name", ""))
    for remote in server.get("remotes") or []:
        if remote.get("type") == "streamable-http" and "{" not in (remote.get("url") or "") and not remote.get("headers"):
            url = remote["url"]
            return ({"claude": {"command": f"claude mcp add --transport http {name} {url}"},
                     "codex": {"command": f"codex mcp add {name} --url {url}"}}, None)
    for pkg in server.get("packages") or []:
        if (pkg.get("transport") or {}).get("type") != "stdio" or not pkg.get("identifier"):
            continue
        if any(v.get("isRequired") for v in pkg.get("environmentVariables") or []):
            return {}, "要先設定金鑰或環境變數，照來源的說明安裝"
        runner = {"npm": "npx -y", "pypi": "uvx"}.get(pkg.get("registryType"))
        if runner:
            run = f"{runner} {pkg['identifier']}"
            return ({"claude": {"command": f"claude mcp add {name} -- {run}"},
                     "codex": {"command": f"codex mcp add {name} -- {run}"}}, None)
    return {}, "Registry 登記的安裝方式要另外設定，照來源的說明安裝"


def parse_registry(doc):
    out = []
    for item in (doc or {}).get("servers") or []:
        server = item.get("server") or {}
        meta = (item.get("_meta") or {}).get(OFFICIAL_META) or {}
        repo = repo_of((server.get("repository") or {}).get("url"))
        if not server.get("name") or meta.get("status") != "active" or not repo:
            continue  # 沒有 GitHub repo 的沒有任何訊號可以檢查，不列
        install, note = registry_install(server)
        entry = {"id": f"registry:{server['name']}", "source": "registry", "name": server.get("title") or server["name"],
                 "description": clip(server.get("description")), "category": None, "kind": "mcp",
                 "url": f"https://github.com/{repo}", "repo": repo, "agents": ["claude", "codex"], "install": install}
        if note:
            entry["install_note"] = note
        out.append(entry)
    return out


def search_registry(state, keyword, fetch, today):
    """用一個字查 Registry（只查最新版），結果存 7 天。回傳條目；查不到或連不上回 None。"""
    term = registry_term(keyword)
    if not term:
        return []
    path = state / "pool" / "registry" / f"{term}.json"
    cached = load(path, {})
    if fresh(cached.get("fetched"), today):
        return cached.get("entries") or []
    entries, cursor = [], None
    for _ in range(REGISTRY_PAGES):
        query = {"search": term, "version": "latest", "limit": 100, **({"cursor": cursor} if cursor else {})}
        try:
            doc = json.loads(fetch(f"{REGISTRY}?{urllib.parse.urlencode(query)}") or "")
        except ValueError:
            return None if not entries else entries
        entries += parse_registry(doc)
        cursor = (doc.get("metadata") or {}).get("nextCursor")
        if not cursor:
            break
    dump(path, {"fetched": today.isoformat(), "term": term, "entries": entries})
    return entries


# ---------- 找候選 ----------

def find(roster, catalog, state, client, fetch=http, today=None, only=None, registry=True, edition="colleague"):
    """對要找的槽位，從兩家官方目錄與 Registry 找候選，過檢查，存到 state/pool/slots.json。"""
    today = today or date.today()
    index, health = roster_index(roster), Health(state, client, today)
    path = state / "pool" / "slots.json"
    saved = load(path, {}).get("slots") or {}
    slots = open_slots(roster, edition)
    if only:
        known = {s["id"]: s for s in roster["slots"]}
        slots = [{"slot": i, "slot_name": known[i]["name"], "module": known[i]["module"],
                  "keywords": list(known[i].get("search") or []), "agents": ["claude", "codex"]} for i in only if i in known]
    result, unreachable = {}, []
    for slot in slots:
        excluded, picked = [], []

        def admit(entries):
            ok = []
            for e in entries:
                why = in_roster(e, index)
                if why:
                    excluded.append({"id": e["id"], "name": e["name"], **why})
                else:
                    ok.append(e)
            return ok

        for source in ("anthropic", "openai"):
            listed = [e for e in catalog.get("entries") or [] if e["source"] == source
                      and set(e["agents"]) & set(slot["agents"])]
            shortlist = admit(top(listed, slot["keywords"], PER_SOURCE * 2))
            kept, dropped = judge(shortlist, health.get([e["repo"] for e in shortlist]), today)
            picked += kept[:PER_SOURCE]
            excluded += dropped
        if registry:
            found, failed = {}, False
            for kw in slot["keywords"]:
                got = search_registry(state, kw, fetch, today)
                if got is None:
                    failed = True
                for e in got or []:
                    found.setdefault(e["id"], e)
            if failed:
                unreachable.append(slot["slot_name"])
            shortlist = admit(top(list(found.values()), slot["keywords"], SHORTLIST))
            kept, dropped = judge(shortlist, health.get([e["repo"] for e in shortlist]), today)
            # Registry 不審核、沒有品質訊號：查不到 GitHub 現況的不列；星數不到門檻的排後面，
            # 其餘先看比對分數、再看星數（星數只用來排順序，不代表品質）
            kept = [e for e in kept if "unknown" not in e["flags"]]
            kept.sort(key=lambda e: ("few-stars" in e["flags"], -e["score"], -(e["github"]["stars"] or 0)))
            picked += kept[:PER_SOURCE]
            excluded += dropped
        web = [e for e in (saved.get(slot["slot"]) or {}).get("candidates") or []
               if e.get("source") == "web" and fresh(e.get("found"), today, KEEP_WEB_DAYS)]
        result[slot["slot"]] = {**{k: slot[k] for k in ("slot_name", "module", "keywords", "agents")},
                                "searched": today.isoformat(), "registry": registry,
                                "candidates": picked + web, "excluded": excluded}
    for slot_id, old in saved.items():
        if slot_id in result:
            continue
        if only:  # 只找指定的槽位：其他槽位上次的結果原樣留著
            result[slot_id] = old
            continue
        # 全部重找之後不在清單裡的槽位（已經有答案了）：只留之前上網找到的
        web = [e for e in old.get("candidates") or [] if e.get("source") == "web" and fresh(e.get("found"), today, KEEP_WEB_DAYS)]
        if web:
            result[slot_id] = {**old, "candidates": web}
    notes = [f"官方 MCP Registry 連不上，這 {len(unreachable)} 個槽位這次沒有那邊的候選：{'、'.join(unreachable)}"] if unreachable else []
    doc = {"generated": today.isoformat(), "sources": catalog.get("sources") or {}, "github": getattr(client, "mode", None),
           "notes": notes, "slots": result}
    dump(path, doc)
    return doc


def add_found(roster, state, client, slot_id, items, today=None):
    """agent 上網找到的：過同一套檢查，通過的記進這個槽位。回傳（記下的, 沒收的與原因）。"""
    today = today or date.today()
    slot = next((s for s in roster["slots"] if s["id"] == slot_id), None)
    if not slot:
        return [], [{"name": slot_id, "text": "名冊沒有這個槽位"}]
    index, health = roster_index(roster), Health(state, client, today)
    accepted, refused, entries = [], [], []
    for item in items if isinstance(items, list) else []:
        item = item if isinstance(item, dict) else {}
        name, url = " ".join(str(item.get("name") or "").split()), str(item.get("url") or "").strip()
        if not name or not re.match(r"https://[\w.-]+/", url):
            refused.append({"name": name or "（沒有名稱）", "text": "要有名稱與 https 開頭的來源網址"})
            continue
        agents = [a for a in item.get("agents") or [] if a in ("claude", "codex")]
        if not agents:
            refused.append({"name": name, "text": "要寫明支援哪個 agent（claude、codex）"})
            continue
        repo = repo_of(url)
        entry = {"id": f"web:{repo or norm(url)}", "source": "web", "name": name, "description": clip(item.get("description")),
                 "category": None, "kind": item.get("kind") if item.get("kind") in ("skill", "plugin", "mcp", "cli") else "other",
                 "url": url, "repo": repo, "agents": agents, "install": {}, "found": today.isoformat(),
                 "install_note": "照來源的說明安裝"}
        why = in_roster(entry, index)
        if why:
            refused.append({"name": name, "text": why["text"]})
            continue
        entries.append(entry)
    kept, dropped = judge(entries, health.get([e["repo"] for e in entries]), today)
    refused += [{"name": d["name"], "text": d["text"]} for d in dropped]
    accepted = kept
    if accepted:
        path = state / "pool" / "slots.json"
        doc = load(path, {"generated": today.isoformat(), "slots": {}})
        entry = doc.setdefault("slots", {}).setdefault(slot_id, {
            "slot_name": slot["name"], "module": slot["module"], "keywords": list(slot.get("search") or []),
            "agents": ["claude", "codex"], "searched": None, "candidates": [], "excluded": []})
        ids = {e["id"] for e in accepted}
        entry["candidates"] = [e for e in entry["candidates"] if e["id"] not in ids] + accepted
        dump(path, doc)
    return accepted, refused


def summary(doc):
    """給 agent 看的精簡版：每個槽位的候選只留判斷要用的欄位。"""
    slots = {}
    for slot_id, s in doc["slots"].items():
        slots[slot_id] = {"slot_name": s["slot_name"], "keywords": s["keywords"], "agents": s["agents"], "searched": s.get("searched"),
                          "candidates": [{"id": e["id"], "name": e["name"], "source": SOURCES[e["source"]], "agents": e["agents"],
                                          "description": e["description"], "url": e["url"], "github": e.get("github"),
                                          "flags": [FLAGS[f] for f in e.get("flags") or []]} for e in s["candidates"]],
                          "excluded": s["excluded"]}
    return {"generated": doc["generated"], "sources": doc.get("sources"), "github": doc.get("github"),
            "notes": doc.get("notes") or [], "caveat": CAVEAT, "slots": slots,
            "empty": sorted(i for i, s in slots.items() if not s["candidates"])}


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check(name, ok):
        print(f"{'通過' if ok else '失敗'}：{name}")
        if not ok:
            failures.append(name)

    today = date(2026, 11, 11)
    market = {"plugins": [
        {"name": "web-pilot", "description": "Browser automation for testing web apps", "category": "testing",
         "source": {"source": "url", "url": "https://github.com/Acme/Web-Pilot.git"}, "homepage": "https://acme.dev"},
        {"name": "old-pilot", "description": "Browser automation, the old one", "category": "testing",
         "source": {"source": "git-subdir", "url": "https://github.com/acme/old-pilot", "path": "p"}},
        {"name": "inhouse", "displayName": "In House", "description": "Browser automation by the directory owner",
         "source": "./plugins/inhouse", "homepage": "https://github.com/anthropics/claude-plugins-public/tree/main/plugins/inhouse"},
        {"name": "pilot-notes", "description": "Take notes about automation. Opens in a browser", "source": "./x"},
        {"name": "bad-tool", "description": "Browser automation that the roster rejected", "source": {"source": "url", "url": "https://github.com/x/bad"}},
        {"name": "sheet", "description": "Spreadsheet formulas", "source": "./y"}, {"description": "沒有名稱"}]}
    got = {e["id"]: e for e in parse_anthropic(market)}
    check("Anthropic 目錄：三種來源寫法都解析出 repo，沒有名稱的略過",
          len(got) == 6 and got["anthropic:web-pilot"]["repo"] == "acme/web-pilot"
          and got["anthropic:old-pilot"]["repo"] == "acme/old-pilot"
          and got["anthropic:inhouse"]["repo"] == "anthropics/claude-plugins-public" and got["anthropic:sheet"]["repo"] is None)
    check("Anthropic 目錄：只給 Claude Code，安裝指令指到官方 marketplace",
          got["anthropic:inhouse"]["agents"] == ["claude"] and got["anthropic:inhouse"]["name"] == "In House"
          and got["anthropic:inhouse"]["install"]["claude"]["command"] == "claude plugin install inhouse@claude-plugins-official"
          and got["anthropic:inhouse"]["install"]["claude"]["add"] == "claude plugin marketplace add anthropics/claude-plugins-official")

    lists = {OPENAI_LISTS[0]: json.dumps({"plugins": [
        {"name": "surf", "category": "Coding", "policy": {"installation": "AVAILABLE"}},
        {"name": "hidden", "policy": {"installation": "NOT_AVAILABLE"}}, {"name": "nodoc"}]}),
        OPENAI_LISTS[1]: json.dumps({"plugins": [{"name": "surf"}, {"name": "extra"}]})}
    manifests = {"surf": {"description": "Drive a browser", "interface": {"displayName": "Surf", "longDescription": "browser automation"},
                          "keywords": ["playwright"]},
                 "hidden": {"description": "x"}, "extra": {"description": "Extra things", "homepage": "https://extra.dev"}}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        home = tmp / "home"
        local = home / ".codex" / ".tmp" / "plugins"
        for rel, text in lists.items():
            (local / rel).parent.mkdir(parents=True, exist_ok=True)
            (local / rel).write_text(text, encoding="utf-8")
        for name, doc in manifests.items():
            (local / "plugins" / name / ".codex-plugin").mkdir(parents=True)
            (local / "plugins" / name / ".codex-plugin" / "plugin.json").write_text(json.dumps(doc), encoding="utf-8")
        asked = []

        def web(url):
            asked.append(url)
            if url == ANTHROPIC_URL:
                return json.dumps(market)
            if url.startswith(OPENAI_RAW):
                rel = url[len(OPENAI_RAW) + 1:]
                if rel in lists:
                    return lists[rel]
                name = rel.split("/")[1]
                return json.dumps(manifests[name]) if name in manifests else None
            if url.startswith(REGISTRY):
                return json.dumps(registry_pages.get(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["search"][0], {"servers": []}))
            return None

        registry_pages = {}
        state = tmp / "state"
        cat = refresh(home, state, web, today)
        ids = [e["id"] for e in cat["entries"]]
        check("OpenAI 目錄：這台有 Codex 就讀本機那份，不上網抓",
              cat["sources"]["openai"] == {"count": 2, "from": "這台的 Codex", "fetched": "2026-11-11"}
              and not [u for u in asked if u.startswith(OPENAI_RAW)])
        check("OpenAI 目錄：兩個清單合併、不能裝的與讀不到說明的不收，只給 Codex",
              ids[-2:] == ["openai:surf", "openai:extra"] and cat["entries"][-2]["agents"] == ["codex"]
              and cat["entries"][-2]["install"]["codex"]["command"] == "codex plugin add surf@openai-curated"
              and cat["entries"][-2]["category"] == "Coding" and cat["entries"][-1]["url"] == "https://extra.dev")
        asked.clear()
        check("7 天內抓過就不重抓", refresh(home, state, web, today + timedelta(days=6)) == cat and not asked)
        again = refresh(home, state, lambda url: None, today + timedelta(days=7))
        check("過期重抓、這次抓不到：留著上次的，並照實寫",
              again["sources"]["anthropic"]["count"] == 6 and "用上次的" in again["sources"]["anthropic"]["error"]
              and again["sources"]["anthropic"]["fetched"] == "2026-11-11" and "error" not in again["sources"]["openai"])
        nocodex = refresh(tmp / "nobody", tmp / "state2", web, today)
        check("OpenAI 目錄：這台沒有 Codex 才上網抓",
              nocodex["sources"]["openai"]["from"] == "openai/plugins" and nocodex["sources"]["openai"]["count"] == 2
              and f"{OPENAI_RAW}/plugins/surf/.codex-plugin/plugin.json" in asked)

        # 比對
        kws = ["browser automation", "playwright mcp"]
        check("比對：一組關鍵字裡的字都要出現才算，名稱裡有再加分；mcp 這類通用字不算",
              score(got["anthropic:web-pilot"], kws) == (4, ["browser automation"])
              and score(got["anthropic:sheet"], kws) == (0, [])
              and score({"id": "x:playwright-kit", "name": "Playwright Kit", "description": "Automation"}, kws) == (4, ["playwright mcp"])
              and score({"id": "x:b", "name": "B", "description": "Uses playwright under the hood"}, kws) == (0, [])
              and score({"id": "x:b", "name": "B", "description": "Uses playwright under the hood"}, ["playwright"]) == (2, ["playwright"])
              and score({"id": "x:b", "name": "B", "description": "x", "keywords": ["Playwright"]}, kws) == (2, ["playwright mcp"])
              and score({"id": "x:browser-bot", "name": "Browser Bot", "description": "automation"}, kws)[0] == 6
              and score({"id": "x:a", "name": "A", "description": "a browser"}, kws) == (0, [])
              and score(got["anthropic:pilot-notes"], kws) == (0, [])
              and score(cat["entries"][-2], kws) == (6, ["browser automation", "playwright mcp"]))

        def card(cid, status, slots, **extra):
            return {"id": cid, "name": cid, "status": status, "slots": slots, "kind": "plugin", **extra}

        def slot(sid, module="m", answers=None, search=("browser automation", "playwright mcp")):
            return {"id": sid, "name": f"{sid} 槽位", "module": module, "search": list(search), "answers": answers or {}}

        roster = {"modules": [{"id": "m"}, {"id": "secret", "maintainer_only": True}, {"id": "off"}], "enabled": ["m", "secret"],
                  "slots": [slot("open"), slot("native", answers={"claude": {"verdict": "native", "reason": "內建就夠"},
                                                                 "codex": {"verdict": "tool", "tool": "t"}}),
                            slot("builtin", answers={"claude": {"verdict": "unknown", "reason": "內建有這個功能"}}),
                            slot("covered"), slot("half"), slot("hidden", module="secret"), slot("disabled", module="off"),
                            slot("nokey", search=())],
                  "tools": {"t": card("t", "default", ["covered"]), "c": card("c", "trial", ["half"], works_with=["claude"]),
                            "p": card("p", "pending", ["open"]),
                            "bad": card("bad", "rejected", [], url="https://github.com/X/Bad", reason="會把金鑰寫進 log"),
                            "In House": card("In House", "pending", [])}}
        opened = {s["slot"]: s["agents"] for s in open_slots(roster)}
        check("要找的槽位：沒有答案、名冊也沒有預設或試用的卡才找；記了內建功能的不找；分 agent",
              opened == {"open": ["claude", "codex"], "builtin": ["codex"], "half": ["codex"]})
        check("要找的槽位：同事版不看只給維護者的模組，維護者版才看",
              "hidden" in {s["slot"] for s in open_slots(roster, "maintainer")})

        # GitHub 現況
        def node(archived=False, stars=900, pushed="2026-10-01", created="2025-01-01", spdx="MIT"):
            return {"isArchived": archived, "stargazerCount": stars, "pushedAt": pushed + "T00:00:00Z",
                    "createdAt": created + "T00:00:00Z", "licenseInfo": {"spdxId": spdx} if spdx else None}

        repos = {"acme/web-pilot": node(), "acme/old-pilot": node(archived=True), "anthropics/claude-plugins-public": node(stars=5000),
                 "s/big": node(stars=4000), "s/small": node(stars=60), "s/gone": None, "s/dead": node(archived=True),
                 "s/keyed": node(stars=70), "s/tiny": node(stars=3), "w/new": node(stars=10, created="2026-11-05", spdx=None, pushed="2025-01-01")}

        def graphql(query, _vars):
            pairs = re.findall(r'(r\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', query)
            return {alias: repos.get(f"{o}/{n}") for alias, o, n in pairs}

        client = _github.Fake(graphql=graphql)
        seen = fetch_health(client, ["acme/web-pilot", "s/gone", "w/new"])
        check("GitHub 現況：一次查多個；找不到的寫未知",
              seen["acme/web-pilot"] == {"archived": False, "stars": 900, "pushed": "2026-10-01", "created": "2025-01-01", "license": "MIT"}
              and "找不到" in seen["s/gone"]["unknown"] and len(client.calls) == 1)
        check("旗標：沒有授權、超過一年沒更新、建立不到 14 天、星數不到 50；查不到是未知，不當作通過",
              flags(seen["w/new"], today) == ["no-license", "stale", "cooling", "few-stars"] and flags(seen["acme/web-pilot"], today) == []
              and flags(seen["s/gone"], today) == ["unknown"] and flags(None, today) == ["unknown"]
              and flags({"stars": 50, "license": "MIT", "pushed": "2025-11-11", "created": "2026-10-28"}, today) == []
              and flags({"stars": 49, "license": "NOASSERTION", "pushed": "2025-11-10", "created": "2026-10-29"}, today)
              == ["no-license", "stale", "cooling", "few-stars"])
        anon = _github.Fake(rest={f"repos/r/{n}": {"archived": False, "stargazers_count": n, "pushed_at": "2026-01-01T00:00:00Z",
                                                   "created_at": "2024-01-01T00:00:00Z", "license": {"spdx_id": "MIT"}}
                                  for n in range(40)}, mode="anonymous")
        limited = fetch_health(anon, [f"r/{n}" for n in range(40)])
        check("沒登入 GitHub：一筆一筆查，超過上限的寫未知",
              sum("unknown" not in h for h in limited.values()) == ANON_LIMIT and len(anon.calls) == ANON_LIMIT
              and "額度" in limited["r/9"]["unknown"] and limited["r/0"]["license"] == "MIT")

        # Registry
        def server(name, repo=None, status="active", desc="Browser automation server", **extra):
            return {"server": {"name": name, "description": desc, **({"repository": {"url": f"https://github.com/{repo}"}} if repo else {}),
                               **extra}, "_meta": {OFFICIAL_META: {"status": status}}}

        registry_pages["browser"] = {"servers": [
            server("io.x/browser-big", "s/big", remotes=[{"type": "streamable-http", "url": "https://big.dev/mcp"}]),
            server("io.x/browser-tiny-playwright", "s/tiny", desc="Browser automation with playwright"),
            server("io.x/browser-small", "s/small", packages=[{"registryType": "npm", "identifier": "@s/small", "transport": {"type": "stdio"}}]),
            server("io.x/browser-norepo"), server("io.x/browser-deleted", "s/big", status="deleted"),
            server("io.x/browser-gone", "s/gone"), server("io.x/browser-dead", "s/dead"),
            server("io.x/browser-keyed", "s/keyed", packages=[{"registryType": "pypi", "identifier": "keyed", "transport": {"type": "stdio"},
                                                               "environmentVariables": [{"name": "KEY", "isRequired": True}]}]),
            server("io.x/browser-other", "s/big", desc="Reads bookmarks")]}
        parsed = {e["id"]: e for e in parse_registry(registry_pages["browser"])}
        check("Registry：只收狀態正常、有 GitHub repo 的",
              sorted(parsed) == ["registry:io.x/browser-" + n for n in ("big", "dead", "gone", "keyed", "other", "small", "tiny-playwright")])
        check("Registry：照登記的資料組安裝指令；要金鑰的不組，改寫說明",
              parsed["registry:io.x/browser-big"]["install"]["claude"]["command"] == "claude mcp add --transport http browser-big https://big.dev/mcp"
              and parsed["registry:io.x/browser-big"]["install"]["codex"]["command"] == "codex mcp add browser-big --url https://big.dev/mcp"
              and parsed["registry:io.x/browser-small"]["install"]["codex"]["command"] == "codex mcp add browser-small -- npx -y @s/small"
              and parsed["registry:io.x/browser-keyed"]["install"] == {} and "金鑰" in parsed["registry:io.x/browser-keyed"]["install_note"]
              and registry_install({"name": "a/b", "remotes": [{"type": "streamable-http", "url": "https://{region}.x/mcp"}]})[0] == {}
              and registry_install({"name": "a/b", "remotes": [{"type": "streamable-http", "url": "https://x/mcp", "headers": [{"name": "Authorization"}]}]})[0] == {}
              and registry_install({"name": "a/b", "packages": [{"registryType": "pypi", "identifier": "pk", "transport": {"type": "stdio"}}]})[0]["claude"]["command"]
              == "claude mcp add b -- uvx pk")
        check("Registry：一組關鍵字只送第一個有意義的字", registry_term("browser automation") == "browser"
              and registry_term("playwright mcp") == "playwright" and registry_term("mcp server") is None
              and registry_term("on-device inference") == "device" and registry_term("ml") is None)

        # 找候選
        asked.clear()
        doc = find(roster, cat, state, client, web, today)
        cands = {sid: [e["id"] for e in s["candidates"]] for sid, s in doc["slots"].items()}
        check("找候選：只找要找的槽位", sorted(doc["slots"]) == ["builtin", "half", "open"])
        check("找候選：兩家官方目錄各自比對，封存的與名冊記了別裝的不列，Registry 先看比對分數、再看星數",
              cands["open"] == ["anthropic:web-pilot", "openai:surf", "registry:io.x/browser-big", "registry:io.x/browser-keyed",
                                "registry:io.x/browser-small"])
        check("找候選：只列支援那個 agent 的來源", cands["half"] == cands["builtin"] == cands["open"][1:])
        out = {x["id"]: x for x in doc["slots"]["open"]["excluded"]}
        check("沒列的都寫原因：名冊拒絕的附名冊記的理由、名冊已有卡的、封存的",
              "會把金鑰寫進 log" in out["anthropic:bad-tool"]["text"] and out["anthropic:bad-tool"]["code"] == "roster-no"
              and out["anthropic:inhouse"]["code"] == "in-roster" and out["anthropic:old-pilot"]["code"] == "archived"
              and out["registry:io.x/browser-dead"]["code"] == "archived")
        check("Registry：GitHub 現況查不到的不列；星數不到門檻的就算比對分數比較高也排後面，名額滿了就不列",
              "registry:io.x/browser-gone" not in cands["open"] and "registry:io.x/browser-tiny-playwright" not in cands["open"]
              and score(parsed["registry:io.x/browser-tiny-playwright"], kws)[0] > score(parsed["registry:io.x/browser-big"], kws)[0])
        first = doc["slots"]["open"]["candidates"]
        check("每個候選附 GitHub 現況與旗標；OpenAI 目錄的沒有各自的 repo，照實寫沒得查",
              first[0]["github"] == {"stars": 900, "pushed": "2026-10-01", "created": "2025-01-01", "license": "MIT"}
              and first[0]["flags"] == [] and first[1]["github"] is None and first[1]["flags"] == [])
        sent = [urllib.parse.parse_qs(urllib.parse.urlparse(u).query) for u in asked if u.startswith(REGISTRY)]
        check("送出去的只有槽位關鍵字裡的一個字，而且只查最新版",
              sorted(q["search"][0] for q in sent) == ["browser", "playwright"] and all(q["version"] == ["latest"] for q in sent)
              and all(set(q) == {"search", "version", "limit"} for q in sent))
        asked.clear()
        calls = len(client.calls)
        find(roster, cat, state, client, web, today + timedelta(days=3))
        check("7 天內再找：Registry 與 GitHub 都用存下來的，不再連網", not asked and len(client.calls) == calls)
        off = find(roster, cat, tmp / "state3", client, web, today, registry=False)
        check("--no-registry：不查 Registry", all(not e["id"].startswith("registry:") for e in off["slots"]["open"]["candidates"]))
        down = find(roster, cat, tmp / "state4", client, lambda url: None, today)
        check("Registry 連不上：照實寫，官方目錄的候選照樣給",
              "連不上" in down["notes"][0] and len(down["notes"]) == 1 and [e["id"] for e in down["slots"]["open"]["candidates"]] == cands["open"][:2])
        forced = find(roster, cat, tmp / "state5", client, web, today, only=["native", "nope"])
        check("--slot：指定的槽位不管有沒有答案都找", sorted(forced["slots"]) == ["native"] and forced["slots"]["native"]["candidates"])
        before = find(roster, cat, tmp / "state6", client, web, today)["slots"]["open"]
        one = find(roster, cat, tmp / "state6", client, web, today + timedelta(days=1), only=["native"])["slots"]
        check("--slot：其他槽位上次的結果原樣留著", one["open"] == before and one["native"]["searched"] == (today + timedelta(days=1)).isoformat())

        # agent 上網找到的
        ok, no = add_found(roster, state, client, "open", [
            {"name": "New Thing", "url": "https://github.com/w/new", "description": "x" * 400, "kind": "skill", "agents": ["claude", "nope"]},
            {"name": "Site Tool", "url": "https://tool.example/docs", "agents": ["codex"]},
            {"name": "No Url", "agents": ["claude"]}, {"name": "Http", "url": "http://x.dev/", "agents": ["claude"]},
            {"name": "No Agent", "url": "https://github.com/w/na"}, {"name": "Bad", "url": "https://github.com/x/bad", "agents": ["claude"]},
            {"name": "Dead", "url": "https://github.com/s/dead", "agents": ["claude"]}, "不是物件"], today)
        check("上網找到的：要有名稱、https 網址與支援的 agent；名冊記了別裝的、封存的不收，原因都寫出來",
              [e["id"] for e in ok] == ["web:w/new", "web:httpstoolexampledocs"] and len(no) == 6
              and any("會把金鑰寫進 log" in r["text"] for r in no) and any("封存" in r["text"] for r in no))
        check("上網找到的：過同一套檢查，旗標照標；說明截短；不是 GitHub 的照實寫沒得查",
              ok[0]["flags"] == ["no-license", "stale", "cooling", "few-stars"] and ok[0]["agents"] == ["claude"]
              and len(ok[0]["description"]) == CLIP + 1 and ok[1]["github"] is None and ok[1]["kind"] == "other")
        stored = load(state / "pool" / "slots.json", {})["slots"]["open"]["candidates"]
        check("上網找到的：記在同一個槽位，原本的候選還在", [e["id"] for e in stored] == cands["open"] + ["web:w/new", "web:httpstoolexampledocs"])
        add_found(roster, state, client, "open", [{"name": "New Thing 2", "url": "https://github.com/w/new", "agents": ["claude"]}], today)
        stored = load(state / "pool" / "slots.json", {})["slots"]["open"]["candidates"]
        check("上網找到的：同一個來源再交一次，換成新的、不重複", [e["name"] for e in stored if e["id"] == "web:w/new"] == ["New Thing 2"])
        later = find(roster, cat, state, client, web, today + timedelta(days=KEEP_WEB_DAYS - 1))["slots"]["open"]["candidates"]
        gone = find(roster, cat, state, client, web, today + timedelta(days=KEEP_WEB_DAYS))["slots"]["open"]["candidates"]
        check(f"上網找到的：重找時留著，{KEEP_WEB_DAYS} 天後才拿掉",
              "web:w/new" in [e["id"] for e in later] and "web:w/new" not in [e["id"] for e in gone])
        check("上網找到的：名冊沒有的槽位不收", add_found(roster, state, client, "nope", [], today)[1][0]["text"] == "名冊沒有這個槽位")
        add_found(roster, state, client, "native", [{"name": "Kept", "url": "https://github.com/s/big", "agents": ["claude"]}], today)
        kept = find(roster, cat, state, client, web, today)["slots"]
        check("這次沒找的槽位：之前上網找到的留著", [e["id"] for e in kept["native"]["candidates"]] == ["web:s/big"])
        brief = summary(doc)
        check("印出來的精簡版：來源與旗標寫成字，列出沒有候選的槽位",
              brief["slots"]["open"]["candidates"][0]["source"] == "Anthropic 官方 plugin 目錄" and brief["caveat"] == CAVEAT
              and brief["empty"] == [] and summary({**doc, "slots": {"e": {**doc["slots"]["open"], "candidates": []}}})["empty"] == ["e"])

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="OmniKit 候選池：名冊沒有答案的槽位，從官方目錄與 MCP Registry 找候選")
    parser.add_argument("command", nargs="?", choices=["find", "add"])
    parser.add_argument("--slot", help="find：只找這幾個槽位（逗號分隔），不管有沒有答案；add：要記到哪個槽位")
    parser.add_argument("--file", type=Path, help="add：agent 上網找到的（JSON 陣列，每筆有 name、url、description、kind、agents）")
    parser.add_argument("--refresh", action="store_true", help="find：不管上次什麼時候抓的，重抓兩家官方目錄")
    parser.add_argument("--no-registry", action="store_true", help="find：不查官方 MCP Registry")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.command:
        parser.error("要給 find 或 add")
    # 這台的私有模組也找：它的槽位一開始都沒有答案，關鍵字是唯一的線索
    errors, roster = validate.check(profiles.DATA, state=profiles.STATE, private=True)
    if errors:
        print("名冊驗證沒過，先修好：\n" + "\n".join(f"- {e}" for e in errors))
        return 1
    client = _github.Client()
    if args.command == "add":
        if not args.slot or not args.file:
            parser.error("add 要給 --slot 與 --file")
        try:
            items = json.loads(args.file.read_bytes().decode("utf-8-sig"))
        except (OSError, ValueError) as e:
            print(f"讀不到 {args.file}：{e}")
            return 1
        accepted, refused = add_found(roster, profiles.STATE, client, args.slot, items)
        print(json.dumps({"accepted": [{"id": e["id"], "name": e["name"], "github": e.get("github"),
                                        "flags": [FLAGS[f] for f in e["flags"]]} for e in accepted],
                          "refused": refused, "caveat": CAVEAT}, ensure_ascii=False, indent=2))
        return 0 if accepted or not refused else 1
    catalog = refresh(Path.home(), profiles.STATE, force=args.refresh)
    only = [s.strip() for s in args.slot.split(",") if s.strip()] if args.slot else None
    doc = find(roster, catalog, profiles.STATE, client, only=only, registry=not args.no_registry,
               edition=editions.resolve(profiles.STATE, profiles.DATA.parent)[0])
    print(json.dumps(summary(doc), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
