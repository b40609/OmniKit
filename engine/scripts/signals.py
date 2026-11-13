# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""自我迭代第 1 階段：收集訊號、記錄影響判斷、量「有用」的比例（docs/proposals/2026-11-13-self-iteration.md）。

這一階段只記錄，不提示：週報還不會列出這一節。判斷準不準由評估漏斗驗證，不用使用者一筆一筆標：
名冊層的判斷變成待評估的卡或重評請求，第 0、1 層跑完，第 1 層建議深入評估的算命中。
靜默記錄滿 2 週、漏斗給出 10 個以上結果、命中率過半，才在第 3 階段打開（沿用 PRD §0.1 第 5 題的門檻，量法改成漏斗）。
使用者只在最後一步出現：第 2 層實測有結果、要不要換工具時。

來源設定在這台、repo 外：%LOCALAPPDATA%\\omnikit\\signals\\sources.yaml，沒有這個檔就沒有來源。例如：
  sources:
    - id: omnikeep
      type: omnikeep
      url: http://127.0.0.1:5000        只接受本機位址
      key_env: OMNIKEEP_API_KEY         金鑰放在這個環境變數，不寫進任何檔案
      keywords: [...]                   可省略，省略就用預設的關鍵字
目前只有 omnikeep 一種來源：唯讀呼叫它的 GET /api/items，由新到舊翻頁，讀到上次讀過的時間就停。
OmniKeep 沒在跑、金鑰沒設或不對，這個來源就標「略過」，不算失敗。

三步：
1. collect：讀各來源的新項目，用關鍵字篩出跟 agent 工具、提示詞、規則有關的，轉成訊號檔（engine/schema/signal.schema.json）。
   預覽不寫檔；加 --write 才存進 signals\\batches\\，並記下這次讀到哪裡。
2. judge：agent 讀還沒判斷的訊號，每筆分三類並寫理由，存成 JSON 交進來；腳本驗證後才記下來。
     none          不影響
     roster        名冊層：新增、替換或重評某張卡（要寫 target：工具卡 id 或槽位 id）
     architecture  架構或優先順序：之後要寫成提案
     名冊層的訊號是社群貼文時，agent 可以另外寫 repo_url（工具的 GitHub repo）。
3. promote：名冊層的判斷送進漏斗。目標是已有的卡就重評；目標是槽位、指到名冊沒有的 GitHub repo 就寫成
   待評估的卡（data/tools/，來源「自我迭代訊號」）；找不到 repo 的量不了，不算進命中率。預覽不寫檔。
4. 跑第 0、1 層（promote --write 會印出指令），status 照漏斗的結果算命中率。

訊號裡的文字是外部資料，只存、只給 agent 當資料讀，不執行、不當指令。不送任何東西到外面。

用法：
  uv run engine/scripts/signals.py init                             寫出預設的 sources.yaml（已經有就不動）
  uv run engine/scripts/signals.py sources                         來源設定與狀態（不印金鑰）
  uv run engine/scripts/signals.py collect [--write]                收集；預覽不寫檔
  uv run engine/scripts/signals.py pending [--days N]               還沒判斷的訊號（JSON，給 agent 讀）
  uv run engine/scripts/signals.py judge --file <JSON> [--write]    交判斷；預覽不寫檔
  uv run engine/scripts/signals.py promote [--write]                名冊層的判斷送進評估漏斗；預覽不寫檔
  uv run engine/scripts/signals.py status                           漏斗結果、命中率、能不能打開
  uv run engine/scripts/signals.py --selftest
"""
import argparse
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pool  # noqa: E402  名冊比對（同一個 repo 有沒有卡）跟候選池同一套
import profiles  # noqa: E402
import validate  # noqa: E402
from fsretry import retry  # noqa: E402

ROOT = profiles.ROOT
SCHEMA = ROOT / "engine" / "schema" / "signal.schema.json"
FORMAT = 1
IMPACTS = ("none", "roster", "architecture")
PAGE = 100            # OmniKeep 的 limit 上限
MAX_PAGES = 20        # 第一次收集最多往回讀這麼多頁
FIRST_DAYS = 30       # 第一次收集只讀這麼多天內的
SILENT_DAYS = 14      # 靜默記錄至少這麼久
MIN_DECIDED = 10      # 漏斗至少給出這麼多個結果，命中率才算數
HIT_RATE = 0.5        # 命中率要超過這個
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
GITHUB_REPO = re.compile(r"^https://github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")
# 預設關鍵字：比對標題、摘要與標籤（不分大小寫）。只放通用的說法
KEYWORDS = (
    "claude code", "claude.md", "codex", "agents.md", "antigravity", "gemini cli", "coding agent", "agentic",
    "mcp", "skill", "plugin", "subagent", "hook", "prompt", "提示詞", "context engineering", "agent 工具",
    "ai 代理", "代理人", "llm eval", "新模型", "model release",
)
# 「代理」單獨一詞不收：2026-11-13 第一次實跑，538 筆裡有 216 筆只靠它留下，多半是網路代理、遙測代理這類不相關的


def state_dir(base=None):
    return Path(base) if base else profiles.STATE / "signals"


# ---------- 讀寫 ----------

def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    retry(tmp.write_text, json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    retry(os.replace, tmp, path)


def append_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    with retry(open, path, "a", encoding="utf-8") as f:
        f.write(text)


def read_jsonl(path):
    rows = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                rows.append(json.loads(line))
    except OSError:
        pass
    return rows


def now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_time(text):
    """ISO 時間轉成有時區的 datetime；沒寫時區的當 UTC。讀不懂回 None。"""
    if not isinstance(text, str) or not text:
        return None
    try:
        t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def iso(t):
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat()


# ---------- 來源設定 ----------

def load_sources(base):
    """回傳 (來源清單, 問題清單)。格式不對的來源不載入，原因列在問題裡。"""
    path = base / "sources.yaml"
    if not path.exists():
        return [], []
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except (OSError, yaml.YAMLError) as e:
        return [], [f"sources.yaml 讀不懂：{e}"]
    out, problems, seen = [], [], set()
    for i, s in enumerate(doc.get("sources") or []):
        where = f"第 {i + 1} 個來源"
        if not isinstance(s, dict):
            problems.append(f"{where}不是物件")
            continue
        sid = s.get("id")
        if not isinstance(sid, str) or not ID.match(sid) or sid in seen:
            problems.append(f"{where}的 id 不合格或重複：{sid!r}")
            continue
        if s.get("type") != "omnikeep":
            problems.append(f"{sid}：不認得的 type {s.get('type')!r}（目前只有 omnikeep）")
            continue
        url = s.get("url") or "http://127.0.0.1:5000"
        host = urllib.parse.urlparse(url).hostname
        if host not in LOCAL_HOSTS:
            problems.append(f"{sid}：url 只接受本機位址（{', '.join(sorted(LOCAL_HOSTS))}），拿到 {host!r}")
            continue
        key_env = s.get("key_env") or "OMNIKEEP_API_KEY"
        if not re.match(r"^[A-Z_][A-Z0-9_]*$", key_env):
            problems.append(f"{sid}：key_env 要是環境變數的名稱，拿到 {key_env!r}")
            continue
        kws = s.get("keywords")
        if kws is not None and (not isinstance(kws, list) or not all(isinstance(k, str) and k.strip() for k in kws)):
            problems.append(f"{sid}：keywords 要是文字清單")
            continue
        seen.add(sid)
        out.append({"id": sid, "type": "omnikeep", "url": url.rstrip("/"), "key_env": key_env,
                    "keywords": [k.strip().lower() for k in (kws or KEYWORDS)]})
    return out, problems


# ---------- OmniKeep ----------

def unquote(value):
    """從 .env 複製過來的值常帶著引號（KEY='...' 或 KEY="..."）：頭尾成對的引號與空白去掉。"""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1].strip()
    return value


def env_key(name, env=None):
    """讀金鑰的環境變數。Windows 剛用 SetEnvironmentVariable 設在使用者層的，已經開著的程式看不到，
    所以這個行程沒有時再讀使用者層（HKCU\\Environment）。只讀這一個名稱，值不印、不存。"""
    if env is not None:
        return unquote(env.get(name, ""))
    value = os.environ.get(name, "")
    if value or sys.platform != "win32":
        return unquote(value)
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return unquote(str(winreg.QueryValueEx(k, name)[0] or ""))
    except OSError:
        return ""


DEFAULT_SOURCES = """\
# 自我迭代的訊號來源：只在這台生效，在 repo 外。由 signals.py init 寫入，可以直接改；刪掉這個檔就沒有來源。
# 格式見 repo 的 engine/scripts/signals.py 開頭的說明。
sources:
  - id: omnikeep
    type: omnikeep
    url: http://127.0.0.1:5000
    # OmniKeep 的 API 金鑰放在這個環境變數（使用者層也可以），不要寫進這個檔
    key_env: OMNIKEEP_API_KEY
    # keywords: [claude code, codex, mcp, skill, 提示詞]   省略就用預設的關鍵字
"""


def init(base):
    path = base / "sources.yaml"
    if path.exists():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    retry(path.write_text, DEFAULT_SOURCES, encoding="utf-8")
    return path


def http_get(url, key, timeout=20):
    """回 (狀態, 內容, 標頭)。連不上回 (None, 原因, {})。金鑰只放在標頭，不出現在網址或訊息裡。"""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                               "User-Agent": "omnikit-signals"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, "", {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return None, getattr(e, "reason", e).__str__(), {}


def tags_of(value):
    """tech_tags 可能是清單，也可能是存成文字的 JSON 陣列。"""
    if isinstance(value, str):
        with contextlib.suppress(ValueError):
            value = json.loads(value)
    if not isinstance(value, list):
        return []
    return [str(t)[:60] for t in value if isinstance(t, (str, int, float)) and str(t).strip()][:30]


def first(item, *keys):
    for k in keys:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def to_signal(source, item):
    """OmniKeep 的一則轉成訊號；缺必要欄位回 None。"""
    if not isinstance(item, dict):
        return None
    raw_id = str(item.get("id") or "").strip()
    url = first(item, "url", "canonical_url", "source_url")
    title = first(item, "title_l1", "title", "name")
    when = parse_time(first(item, "created_at", "saved_at", "added_at"))
    if not re.match(r"^[A-Za-z0-9._-]{1,80}$", raw_id) or not re.match(r"^https?://", url) or not title or not when:
        return None
    sig = {"id": f"{source['id']}:{raw_id}", "source": source["id"], "url": url[:2000], "title": title[:300],
           "date": iso(when)}
    summary = first(item, "summary_l1", "summary", "description")
    if summary:
        sig["summary"] = summary[:1000]
    tags = tags_of(item.get("tech_tags"))
    if tags:
        sig["tags"] = tags
    return sig


def matches(sig, keywords):
    text = " ".join([sig["title"], sig.get("summary", ""), " ".join(sig.get("tags", []))]).lower()
    return [k for k in keywords if k in text]


def collect_omnikeep(source, since, get=http_get, env=None):
    """回 (來源結果, 訊號清單, 最新的時間)。since 是上次讀到的時間；沒有就往回讀 FIRST_DAYS 天。"""
    key = env_key(source["key_env"], env)
    if not key:
        return {"id": source["id"], "status": "skipped", "reason": f"環境變數 {source['key_env']} 沒有設定"}, [], None
    stop = since or now() - timedelta(days=FIRST_DAYS)
    read, kept, newest = 0, [], None
    for page in range(MAX_PAGES):
        query = urllib.parse.urlencode({"sort": "newest", "limit": PAGE, "offset": page * PAGE})
        status, body, _ = get(f"{source['url']}/api/items?{query}", key)
        if status is None:
            return {"id": source["id"], "status": "skipped", "reason": f"連不上 OmniKeep（{body}）"}, [], None
        if status in (401, 403):
            return {"id": source["id"], "status": "skipped", "reason": f"OmniKeep 拒絕金鑰（HTTP {status}）"}, [], None
        if status != 200:
            return {"id": source["id"], "status": "skipped", "reason": f"OmniKeep 回 HTTP {status}"}, [], None
        try:
            doc = json.loads(body)
        except ValueError:
            return {"id": source["id"], "status": "skipped", "reason": "OmniKeep 回的不是 JSON"}, [], None
        items = doc if isinstance(doc, list) else (doc.get("items") if isinstance(doc, dict) else None)
        if not isinstance(items, list):
            return {"id": source["id"], "status": "skipped", "reason": "OmniKeep 回的格式不認得"}, [], None
        done = not items or len(items) < PAGE
        for item in items:
            sig = to_signal(source, item)
            if not sig:
                continue
            when = parse_time(sig["date"])
            if when <= stop:
                done = True
                continue
            read += 1
            newest = max(newest, when) if newest else when
            hit = matches(sig, source["keywords"])
            if hit:
                kept.append({**sig, "matched": hit})
        if done:
            break
    return {"id": source["id"], "status": "ok", "read": read, "kept": len(kept)}, kept, newest


def collect(base, write=False, get=http_get, env=None):
    sources, problems = load_sources(base)
    cursor = load_json(base / "cursor.json", {})
    seen = {s["id"] for b in batches(base) for s in b.get("signals", [])}
    results, signals, moved = [], [], {}
    for src in sources:
        res, kept, newest = collect_omnikeep(src, parse_time(cursor.get(src["id"])), get=get, env=env)
        results.append(res)
        signals += [s for s in kept if s["id"] not in seen]
        if newest:
            moved[src["id"]] = iso(newest)
    doc = {"format": FORMAT, "collected_at": iso(now()), "sources": results, "signals": signals}
    errors = check_batch(doc)
    if errors:
        raise SystemExit("訊號檔不合格式（腳本的錯，沒有寫檔）：\n" + "\n".join(errors))
    path = None
    if write:
        if signals:
            # 檔名用收集時間；同一秒收了兩次就加編號，不覆蓋前一個檔
            stem = doc["collected_at"][:19].replace(":", "")
            path = base / "batches" / f"{stem}.json"
            n = 1
            while path.exists():
                n += 1
                path = base / "batches" / f"{stem}-{n}.json"
            write_json(path, doc)
        if moved:
            write_json(base / "cursor.json", {**cursor, **moved})
    return doc, problems, path


def check_batch(doc):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    v = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'/'.join(map(str, e.path)) or '(根)'}：{e.message}" for e in v.iter_errors(doc)]


def batches(base):
    out = []
    for p in sorted((base / "batches").glob("*.json")):
        doc = load_json(p, None)
        if isinstance(doc, dict) and not check_batch(doc):
            out.append(doc)
    return out


# ---------- 判斷與標記 ----------

def all_signals(base):
    found = {}
    for b in batches(base):
        for s in b["signals"]:
            found.setdefault(s["id"], s)
    return found


def judged(base):
    """每個訊號最新的一筆判斷。"""
    out = {}
    for r in read_jsonl(base / "judgments.jsonl"):
        if isinstance(r, dict) and isinstance(r.get("signal"), str):
            out[r["signal"]] = r
    return out


def pending(base, days=None, today=None):
    """還沒判斷的訊號。來源的關鍵字改過的話照現在的關鍵字重新篩：不再命中的不列，matched 換成現在命中的。
    days：只列這麼多天內收錄的。"""
    done = judged(base)
    kws = {s["id"]: s["keywords"] for s in load_sources(base)[0]}
    since = (today or now()) - timedelta(days=days) if days else None
    out = []
    for sid, s in all_signals(base).items():
        if sid in done or (since and parse_time(s["date"]) < since):
            continue
        if s["source"] in kws:
            hit = matches(s, kws[s["source"]])
            if not hit:
                continue
            s = {**s, "matched": hit}
        out.append(s)
    return out


def check_judgments(base, doc):
    """回 (可以記下的判斷, 被擋下的原因)。"""
    sigs = all_signals(base)
    items = doc.get("judgments") if isinstance(doc, dict) else doc
    if not isinstance(items, list):
        return [], ["要交一個清單，或 {\"judgments\": [...]}"]
    ok, bad, seen = [], [], set()
    for i, j in enumerate(items):
        where = f"第 {i + 1} 筆"
        if not isinstance(j, dict):
            bad.append(f"{where}不是物件")
            continue
        sid = j.get("signal")
        if sid not in sigs:
            bad.append(f"{where}：沒有這個訊號 {sid!r}")
            continue
        if sid in seen:
            bad.append(f"{where}：{sid} 重複")
            continue
        if j.get("impact") not in IMPACTS:
            bad.append(f"{where}（{sid}）：impact 要是 {'、'.join(IMPACTS)}")
            continue
        reason = j.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 4:
            bad.append(f"{where}（{sid}）：要寫理由")
            continue
        target = j.get("target")
        if j["impact"] == "roster" and (not isinstance(target, str) or not ID.match(target)):
            bad.append(f"{where}（{sid}）：名冊層要寫 target（工具卡或槽位的 id）")
            continue
        repo_url = j.get("repo_url")
        if repo_url is not None and not (isinstance(repo_url, str) and GITHUB_REPO.match(repo_url)):
            bad.append(f"{where}（{sid}）：repo_url 要是 https://github.com/<擁有者>/<repo>")
            continue
        seen.add(sid)
        row = {"signal": sid, "impact": j["impact"], "reason": reason.strip()[:1000], "at": iso(now())}
        if j["impact"] == "roster":
            row["target"] = target
            if repo_url:
                row["repo_url"] = repo_url.rstrip("/")
        ok.append(row)
    return ok, bad


def repo_from(*urls):
    """第一個是 GitHub repo 網址的，回 (owner/repo 小寫, 網址)；都不是回 (None, None)。"""
    for u in urls:
        m = GITHUB_REPO.match(u or "")
        if m and m.group(1).lower() not in ("orgs", "topics", "search", "features", "marketplace"):
            return f"{m.group(1)}/{m.group(2)}".lower(), f"https://github.com/{m.group(1)}/{m.group(2)}"
    return None, None


def promotions(base):
    out = {}
    for r in read_jsonl(base / "promotions.jsonl"):
        if isinstance(r, dict) and isinstance(r.get("signal"), str):
            out[r["signal"]] = r
    return out


def plan_promotions(base, roster, today):
    """名冊層的判斷 → 送進評估漏斗的動作（還沒寫檔）：
       reeval  目標是名冊已有的卡，或訊號的 repo 已經有卡：重跑那張卡的第 0、1 層
       card    目標是槽位、訊號指到名冊沒有的 GitHub repo：寫成待評估的卡，照常走第 0、1 層
       skip    找不到 GitHub repo（社群貼文、做法類）或名冊已經拒絕：漏斗量不了，不算進命中率"""
    sigs, done = all_signals(base), promotions(base)
    tools, slots = roster["tools"], {sl["id"] for sl in roster["slots"]}
    index = pool.roster_index(roster)
    taken, actions = set(tools), []
    for sid, j in judged(base).items():
        if j["impact"] != "roster" or sid in done or sid not in sigs:
            continue
        sig, target = sigs[sid], j["target"]
        row = {"signal": sid, "target": target}
        repo, url = repo_from(j.get("repo_url"), sig["url"])
        # 有些 id 同時是槽位與工具卡（例如 frontend-design）：有 repo 就當槽位的新候選，沒有才當重評那張卡
        if target in tools and not (target in slots and repo):
            if target in slots:
                actions.append({**row, "action": "skip", "why": f"{target} 同時是槽位與工具卡，訊號沒有 GitHub repo，分不出要重評哪個"})
            else:
                actions.append({**row, "action": "reeval", "tool": target, "why": "目標是名冊已有的卡"})
            continue
        if target not in slots:
            actions.append({**row, "action": "skip", "why": f"名冊沒有 {target} 這張卡或這個槽位"})
            continue
        if not repo:
            actions.append({**row, "action": "skip", "why": "找不到 GitHub repo，漏斗量不了"})
            continue
        hit = pool.in_roster({"repo": repo, "name": "", "id": f"web:{repo}"}, index)
        if hit:
            if hit["code"] == "roster-no":
                actions.append({**row, "action": "skip", "why": f"名冊已經拒絕或退役（{hit['tool']}）"})
            else:
                actions.append({**row, "action": "reeval", "tool": hit["tool"], "why": "這個 repo 名冊已經有卡"})
            continue
        name = repo.split("/")[-1]
        cid = base_id = re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "signal"
        if cid in taken:
            cid = re.sub(r"[^a-z0-9]+", "-", repo).strip("-")
        n = 2
        while cid in taken:
            cid, n = f"{base_id}-{n}", n + 1
        taken.add(cid)
        card = {"id": cid, "name": f"{name}（{repo.split('/')[0]}）", "slots": [target], "status": "pending", "url": url,
                "sources": ["自我迭代訊號"],
                "notes": f"自我迭代從 {sig['source']} 的收錄找到（{today.isoformat()}，訊號 {sid}）：{j['reason']}。名冊外，還沒評估。",
                "added": today.isoformat()}
        actions.append({**row, "action": "card", "tool": cid, "card": card, "why": "名冊沒有，寫成待評估的卡"})
    return actions


def promote(base, data, write=False, today=None, state=None):
    """回 (動作清單, 問題)。write 才寫卡與 promotions.jsonl；寫完照名冊驗證。"""
    today = today or datetime.now().date()
    errors, roster = validate.check(data, state=state)
    if errors:
        return [], ["名冊驗證沒過，先修好：" + "；".join(errors[:3])]
    actions = plan_promotions(base, roster, today)
    if not write:
        return actions, []
    problems, rows = [], []
    check_tool = validate.validator("tool.schema.json")
    for a in actions:
        if a["action"] == "card":
            path = Path(data) / "tools" / f"{a['tool']}.yaml"
            bad = validate.schema_errors(check_tool, a["card"], path)
            if bad or path.exists():
                problems.append(f"沒寫 {path.name}：{bad[0] if bad else '檔案已經存在'}")
                continue
            retry(path.write_bytes, yaml.safe_dump(a["card"], allow_unicode=True, sort_keys=False, width=10000).encode("utf-8"))
        row = {k: a[k] for k in ("signal", "target", "action", "why")}
        if a.get("tool"):
            row["tool"] = a["tool"]
        rows.append({**row, "at": iso(now())})
    errors, _ = validate.check(data, state=state)
    if errors:
        problems.append("寫卡之後名冊驗證沒過：" + "；".join(errors[:3]))
    append_jsonl(base / "promotions.jsonl", rows)
    return actions, problems


def outcome(funnel, tool_id, since):
    """漏斗對一張卡的結果，第 1 層只看 since 那天之後跑的：
       hit      第 1 層建議深入評估（deep_eval）
       miss     第 0 層淘汰，或第 1 層建議拒絕、先放著
       waiting  還沒跑到"""
    funnel = Path(funnel)
    tools = load_json(funnel / "layer0.json", {}).get("tools") or {}
    l0 = tools.get(tool_id) if isinstance(tools, dict) else next((t for t in tools if t.get("id") == tool_id), None)
    if isinstance(l0, dict) and l0.get("fails"):
        return "miss", "第 0 層淘汰：" + "、".join(map(str, l0["fails"]))
    l1 = load_json(funnel / "layer1" / f"{tool_id}.json", None)
    if isinstance(l1, dict):
        ran = parse_time(str((l1.get("meta") or {}).get("generated") or (l1.get("meta") or {}).get("date") or ""))
        if not since or not ran or ran.date() >= since.date():
            rec = l1.get("recommendation")
            if rec == "deep_eval":
                return "hit", "第 1 層建議深入評估"
            return "miss", "第 1 層建議" + ("拒絕" if rec == "reject" else "先放著")
    return "waiting", "第 1 層還沒跑"


def status(base, funnel=None, today=None):
    """命中率由評估漏斗的結果算，不用使用者標記。只有送進漏斗的名冊層判斷量得到；
    「不影響」與「架構」量不到，只列個數。"""
    today = today or now()
    funnel = Path(funnel) if funnel else ROOT / "data" / "funnel"
    js, proms = judged(base), promotions(base)
    first_at = min((parse_time(j.get("at")) for j in js.values() if parse_time(j.get("at"))), default=None)
    days = (today - first_at).days if first_at else 0
    by = {k: sum(1 for j in js.values() if j["impact"] == k) for k in IMPACTS}
    results = {"hit": [], "miss": [], "waiting": [], "skip": []}
    for sid, r in proms.items():
        if r.get("action") == "skip" or not r.get("tool"):
            results["skip"].append({"signal": sid, "why": r.get("why", "")})
            continue
        res, why = outcome(funnel, r["tool"], parse_time(r.get("at")))
        results[res].append({"signal": sid, "tool": r["tool"], "why": why})
    decided = len(results["hit"]) + len(results["miss"])
    rate = len(results["hit"]) / decided if decided else None
    unpromoted = sum(1 for sid, j in js.items() if j["impact"] == "roster" and sid not in proms)
    ready = days >= SILENT_DAYS and decided >= MIN_DECIDED and rate is not None and rate > HIT_RATE
    missing = []
    if days < SILENT_DAYS:
        missing.append(f"記錄滿 {SILENT_DAYS} 天（目前 {days} 天）")
    if decided < MIN_DECIDED:
        missing.append(f"漏斗至少給出 {MIN_DECIDED} 個結果（目前 {decided} 個）")
    if rate is not None and rate <= HIT_RATE:
        missing.append(f"命中率超過 {HIT_RATE:.0%}（目前 {rate:.0%}）")
    return {"signals": len(all_signals(base)), "pending": len(pending(base)), "judged": by, "unpromoted": unpromoted,
            "results": results, "decided": decided, "rate": rate, "days": days, "ready": ready, "missing": missing}


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check(name, ok):
        print(f"{'通過' if ok else '失敗'}：{name}")
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "signals"
        base.mkdir()

        # 沒有設定檔：沒有來源，也不算錯
        doc, problems, path = collect(base, write=True, get=lambda *a: (_ for _ in ()).throw(AssertionError))
        check("沒有 sources.yaml：沒有來源、不連線、不寫檔", doc["sources"] == [] and not problems and path is None)

        made = init(base)
        srcs, problems = load_sources(base)
        check("init：寫出預設設定，載入得到 omnikeep、只連本機、用預設關鍵字",
              made and [s["id"] for s in srcs] == ["omnikeep"] and not problems
              and srcs[0]["url"] == "http://127.0.0.1:5000" and srcs[0]["keywords"] == list(KEYWORDS))
        made.write_text(made.read_text(encoding="utf-8") + "# 使用者改過\n", encoding="utf-8")
        check("init：已經有設定就不覆蓋", init(base) is None and "使用者改過" in made.read_text(encoding="utf-8"))
        check("金鑰：有給 env 就只看 env，不讀這台的環境變數", env_key("OMNIKIT_SELFTEST_NOPE", {}) == ""
              and env_key("X", {"X": "v"}) == "v")
        check("金鑰：從 .env 複製來的頭尾引號與空白去掉，不成對的不動",
              env_key("X", {"X": " 'abc' "}) == "abc" and env_key("X", {"X": '"abc"'}) == "abc"
              and env_key("X", {"X": "'abc"}) == "'abc")

        (base / "sources.yaml").write_text(yaml.safe_dump({"sources": [
            {"id": "omnikeep", "type": "omnikeep"},
            {"id": "far", "type": "omnikeep", "url": "http://10.0.0.5:5000"},
            {"id": "rss-x", "type": "rss"},
            {"id": "omnikeep", "type": "omnikeep"},
            {"id": "bad-env", "type": "omnikeep", "key_env": "my key"},
        ]}), encoding="utf-8")
        srcs, problems = load_sources(base)
        check("設定檔：只接受本機位址、認得的 type、合法的環境變數名稱，重複的 id 不載入",
              [s["id"] for s in srcs] == ["omnikeep"] and len(problems) == 4
              and any("10.0.0.5" in p for p in problems) and any("rss" in p for p in problems))

        t0 = now()
        items = [
            {"id": "a1", "title_l1": "Claude Code 新版的 hook", "url": "https://github.com/anthropics/claude-code",
             "summary_l1": "新增 hook 事件", "tech_tags": '["claude-code"]', "created_at": iso(t0 - timedelta(hours=1))},
            {"id": "a2", "title_l1": "台股盤後整理", "url": "https://example.com/tw", "summary_l1": "加權指數",
             "created_at": iso(t0 - timedelta(hours=2))},
            {"id": "a3", "title_l1": "MCP server 清單", "url": "https://example.com/mcp", "tech_tags": ["MCP"],
             "created_at": (t0 - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")},
            {"id": "bad id!", "title_l1": "Codex 新功能", "url": "https://example.com/x", "created_at": iso(t0)},
            {"id": "a4", "title_l1": "無網址的提示詞技巧", "url": "", "created_at": iso(t0)},
            {"id": "old", "title_l1": "很舊的 Codex 文章", "url": "https://example.com/old",
             "created_at": iso(t0 - timedelta(days=40))},
        ]
        asked = []

        def fake(url, key, timeout=20):
            asked.append((url, key))
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            off = int(q["offset"][0])
            return 200, json.dumps(items[off:off + PAGE]), {}

        doc, _, _ = collect(base, write=False, get=fake, env={})
        check("金鑰沒設：標略過、不連線", doc["sources"][0]["status"] == "skipped" and "OMNIKEEP_API_KEY" in
              doc["sources"][0]["reason"] and not asked)

        env = {"OMNIKEEP_API_KEY": "k" * 40}
        doc, _, path = collect(base, write=False, get=fake, env=env)
        ids = [s["id"] for s in doc["signals"]]
        check("篩選：關鍵字命中才留下；壞 id、沒網址、超過 30 天的不收", ids == ["omnikeep:a1", "omnikeep:a3"]
              and doc["sources"][0] == {"id": "omnikeep", "status": "ok", "read": 3, "kept": 2})
        check("轉換：文字 JSON 的標籤拆開、沒時區的當 UTC、記下命中的關鍵字",
              doc["signals"][0]["tags"] == ["claude-code"] and doc["signals"][1]["date"].endswith("+00:00")
              and "mcp" in doc["signals"][1]["matched"])
        check("金鑰只在標頭：網址裡沒有，也是唯讀的 GET /api/items",
              all("k" * 40 not in u and "/api/items?" in u for u, _ in asked))
        check("預覽不寫檔", path is None and not (base / "batches").exists() and not (base / "cursor.json").exists())

        doc, _, path = collect(base, write=True, get=fake, env=env)
        check("--write：存訊號檔、記下讀到哪裡", path and path.exists() and not check_batch(load_json(path, {}))
              and load_json(base / "cursor.json", {}).get("omnikeep") == iso(t0 - timedelta(hours=1)))

        asked.clear()
        doc, _, _ = collect(base, write=True, get=fake, env=env)
        check("再收一次：讀到上次的位置就停，沒有重複的訊號", doc["signals"] == [] and doc["sources"][0]["read"] == 0)

        def page_fake(url, key, timeout=20):
            off = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["offset"][0])
            if off >= PAGE * 3:
                return 200, json.dumps({"items": []}), {}
            return 200, json.dumps({"items": [{"id": f"p{off + i}", "title_l1": f"Codex 筆記 {off + i}",
                                               "url": "https://example.com/p", "created_at": iso(t0 + timedelta(minutes=10 + off + i))}
                                              for i in range(PAGE)]}), {}
        doc, _, _ = collect(base, write=False, get=page_fake, env=env)
        check("翻頁：回物件也認得，滿一頁就繼續讀，讀到上次的位置停",
              doc["sources"][0]["read"] == PAGE * 3 and len(doc["signals"]) == PAGE * 3)

        for code, word in ((401, "拒絕"), (500, "HTTP 500")):
            doc, _, _ = collect(base, get=lambda *a, c=code: (c, "", {}), env=env)
            check(f"HTTP {code}：標略過、說明原因", doc["sources"][0]["status"] == "skipped" and word in doc["sources"][0]["reason"])
        doc, _, _ = collect(base, get=lambda *a: (None, "connection refused", {}), env=env)
        check("連不上：標略過、不當成失敗", doc["sources"][0]["status"] == "skipped" and "連不上" in doc["sources"][0]["reason"])
        doc, _, _ = collect(base, get=lambda *a: (200, "<html>", {}), env=env)
        check("回的不是 JSON：標略過", "JSON" in doc["sources"][0]["reason"])

        check("待判斷：剛收的兩筆", [s["id"] for s in pending(base)] == ["omnikeep:a1", "omnikeep:a3"])
        ok, bad = check_judgments(base, {"judgments": [
            {"signal": "omnikeep:a1", "impact": "roster", "target": "claude-code-hooks", "reason": "官方新增 hook 事件，要重評"},
            {"signal": "omnikeep:a3", "impact": "roster", "reason": "清單類，沒寫目標"},
            {"signal": "omnikeep:zz", "impact": "none", "reason": "不存在的訊號"},
            {"signal": "omnikeep:a1", "impact": "none", "reason": "重複交"},
            {"signal": "omnikeep:a3", "impact": "maybe", "reason": "類別不對"},
            {"signal": "omnikeep:a3", "impact": "none", "reason": ""},
        ]})
        check("判斷：名冊層要寫目標；沒有的訊號、重複、類別不對、沒理由都擋下", len(ok) == 1 and len(bad) == 5)
        append_jsonl(base / "judgments.jsonl", ok)
        check("記下判斷後，待判斷少一筆", [s["id"] for s in pending(base)] == ["omnikeep:a3"])
        cfg = base / "sources.yaml"
        saved = cfg.read_text(encoding="utf-8")
        cfg.write_text(yaml.safe_dump({"sources": [{"id": "omnikeep", "type": "omnikeep", "keywords": ["claude code"]}]}),
                       encoding="utf-8")
        check("關鍵字改了：待判斷照現在的關鍵字重新篩", pending(base) == [])
        cfg.write_text(saved, encoding="utf-8")
        check("days：只列這麼多天內的", pending(base, days=1) and not pending(base, days=1, today=now() + timedelta(days=3)))

        funnel = Path(tmp) / "funnel"
        st = status(base, funnel=funnel)
        check("剛開始：不能打開，列出還差什麼；名冊層還沒送進漏斗", not st["ready"] and len(st["missing"]) == 2
              and st["judged"]["roster"] == 1 and st["unpromoted"] == 1)

        # 送進漏斗：用複製的真名冊
        import shutil
        data = Path(tmp) / "data"
        shutil.copytree(profiles.DATA, data)
        nostate = Path(tmp) / "nostate"
        roster = validate.check(data, state=nostate)[1]
        slot = roster["slots"][0]["id"]
        card_id = next(iter(roster["tools"]))
        card_url = roster["tools"][card_id].get("url") or ""
        t1 = now() - timedelta(hours=1)
        extra = [
            {"id": "omnikeep:n1", "source": "omnikeep", "url": "https://github.com/Acme/Brand-New-Skill", "title": "n1", "date": iso(t1)},
            {"id": "omnikeep:n2", "source": "omnikeep", "url": "https://www.threads.net/@x/post/1", "title": "n2", "date": iso(t1)},
            {"id": "omnikeep:n3", "source": "omnikeep", "url": "https://www.threads.net/@x/post/2", "title": "n3", "date": iso(t1)},
            {"id": "omnikeep:n4", "source": "omnikeep", "url": "https://example.com/n4", "title": "n4", "date": iso(t1)},
            {"id": "omnikeep:n5", "source": "omnikeep", "url": card_url or "https://example.com/n5", "title": "n5", "date": iso(t1)},
        ]
        write_json(base / "batches" / "extra.json", {"format": 1, "collected_at": iso(t1), "sources": [], "signals": extra})
        ok, bad = check_judgments(base, [
            {"signal": "omnikeep:n1", "impact": "roster", "target": slot, "reason": "名冊沒有的新工具"},
            {"signal": "omnikeep:n2", "impact": "roster", "target": slot, "reason": "社群貼文，有補 repo",
             "repo_url": "https://github.com/acme/other-tool"},
            {"signal": "omnikeep:n3", "impact": "roster", "target": slot, "reason": "社群貼文，沒補 repo"},
            {"signal": "omnikeep:n4", "impact": "roster", "target": "no-such-slot", "reason": "目標不存在"},
            {"signal": "omnikeep:n5", "impact": "roster", "target": card_id, "reason": "已有的卡要重評"},
            {"signal": "omnikeep:a3", "impact": "roster", "target": slot, "reason": "repo 網址不對", "repo_url": "https://gitlab.com/x/y"},
        ])
        check("判斷：repo_url 只收 GitHub repo 網址", len(ok) == 5 and len(bad) == 1 and "repo_url" in bad[0])
        append_jsonl(base / "judgments.jsonl", ok)

        actions, problems = promote(base, data, write=False, state=nostate)
        by = {a["signal"]: a for a in actions}
        check("promote 預覽：新 repo 寫卡、補了 repo 的社群貼文寫卡、沒 repo 量不了、目標不存在量不了、已有的卡重評",
              by["omnikeep:n1"]["action"] == "card" and by["omnikeep:n1"]["tool"] == "brand-new-skill"
              and by["omnikeep:n2"]["action"] == "card" and by["omnikeep:n2"]["card"]["url"] == "https://github.com/acme/other-tool"
              and by["omnikeep:n3"]["action"] == "skip" and by["omnikeep:n4"]["action"] == "skip"
              and by["omnikeep:n5"]["action"] == "reeval" and by["omnikeep:n5"]["tool"] == card_id and not problems)
        check("promote 預覽：不寫卡、不記錄", not (data / "tools" / "brand-new-skill.yaml").exists()
              and not (base / "promotions.jsonl").exists())
        actions, problems = promote(base, data, write=True, state=nostate)
        made = yaml.safe_load((data / "tools" / "brand-new-skill.yaml").read_text(encoding="utf-8"))
        check("promote --write：寫成待評估的卡、來源是自我迭代訊號、名冊驗證照過",
              made["status"] == "pending" and made["slots"] == [slot] and made["sources"] == ["自我迭代訊號"]
              and not problems and not validate.check(data, state=nostate)[0])
        check("promote 再跑一次：送過的不再送", promote(base, data, write=False, state=nostate)[0] == [])

        both = sorted(set(roster["tools"]) & {sl["id"] for sl in roster["slots"]})
        if both:
            twin = both[0]
            t2 = [{"id": "omnikeep:w1", "source": "omnikeep", "url": "https://github.com/acme/twin-new", "title": "w1", "date": iso(t1)},
                  {"id": "omnikeep:w2", "source": "omnikeep", "url": "https://www.threads.net/@x/post/9", "title": "w2", "date": iso(t1)}]
            write_json(base / "batches" / "twin.json", {"format": 1, "collected_at": iso(t1), "sources": [], "signals": t2})
            append_jsonl(base / "judgments.jsonl", check_judgments(base, [
                {"signal": "omnikeep:w1", "impact": "roster", "target": twin, "reason": "槽位的新候選"},
                {"signal": "omnikeep:w2", "impact": "roster", "target": twin, "reason": "沒有 repo 的貼文"}])[0])
            by = {a["signal"]: a for a in promote(base, data, write=False, state=nostate)[0]}
            check(f"目標同時是槽位與卡（{twin}）：有 repo 當槽位的新候選，沒有 repo 量不了，不會誤當重評",
                  by["omnikeep:w1"]["action"] == "card" and by["omnikeep:w2"]["action"] == "skip")
            promote(base, data, write=True, state=nostate)

        # 漏斗結果：第 0 層淘汰、第 1 層 deep_eval／reject、沒跑過、舊的第 1 層結果不算
        (funnel / "layer1").mkdir(parents=True)
        write_json(funnel / "layer0.json", {"tools": [{"id": "other-tool", "fails": ["H6"]}]})
        write_json(funnel / "layer1" / "brand-new-skill.json", {"recommendation": "deep_eval", "meta": {"date": iso(now())[:10]}})
        write_json(funnel / "layer1" / f"{card_id}.json", {"recommendation": "deep_eval", "meta": {"date": "2026-01-01"}})
        st = status(base, funnel=funnel)
        r = {k: [x.get("tool") for x in v] for k, v in st["results"].items()}
        check("status：第 1 層 deep_eval 算命中、第 0 層淘汰算沒中、送進漏斗前跑的舊結果不算",
              r["hit"] == ["brand-new-skill"] and r["miss"] == ["other-tool"] and card_id in r["waiting"]
              and len(r["skip"]) >= 3 and st["rate"] == 0.5 and st["decided"] == 2)
        write_json(funnel / "layer1" / f"{card_id}.json", {"recommendation": "reject", "meta": {"date": iso(now())[:10]}})
        check("status：重評後第 1 層建議拒絕算沒中", status(base, funnel=funnel)["results"]["miss"][-1]["tool"] == card_id)

        # 門檻：滿 14 天、10 個結果、命中率過半
        start_at = now() - timedelta(days=15)
        rows = [{"signal": f"omnikeep:g{i}", "target": slot, "action": "card", "tool": f"g{i}", "why": "測試", "at": iso(start_at)}
                for i in range(12)]
        append_jsonl(base / "promotions.jsonl", rows)
        append_jsonl(base / "judgments.jsonl", [{"signal": f"omnikeep:g{i}", "impact": "roster", "target": slot,
                                                 "reason": "測試用理由", "at": iso(start_at)} for i in range(12)])
        for i in range(12):
            write_json(funnel / "layer1" / f"g{i}.json", {"recommendation": "deep_eval" if i < 9 else "keep_pending",
                                                          "meta": {"date": iso(now())[:10]}})
        st = status(base, funnel=funnel)
        check("門檻：滿 14 天、15 個結果、命中 10 個（67%）可以打開", st["ready"] and st["decided"] == 15 and st["days"] >= 14)
        for i in range(9):
            write_json(funnel / "layer1" / f"g{i}.json", {"recommendation": "reject", "meta": {"date": iso(now())[:10]}})
        st = status(base, funnel=funnel)
        check("門檻：命中率沒過半就不能打開，說明差什麼", not st["ready"] and any("命中率" in m for m in st["missing"]))

        # 壞掉的訊號檔不讀
        (base / "batches" / "broken.json").write_text('{"format": 1, "signals": "x"}', encoding="utf-8")
        check("格式不對的訊號檔略過，不影響其他的", "omnikeep:a1" in all_signals(base))

        # 命令列
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["sources"], base=base)
        check("sources：不印金鑰", "k" * 40 not in out.getvalue())

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 0 if not failures else 1


# ---------- 命令列 ----------

def main(argv=None, base=None, data=None):
    parser = argparse.ArgumentParser(description="OmniKit 自我迭代第 1 階段：收集訊號、記錄影響判斷、量有用的比例")
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("init")
    sub.add_parser("sources")
    p = sub.add_parser("collect")
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("pending")
    p.add_argument("--days", type=int, help="只列這麼多天內收錄的")
    p = sub.add_parser("judge")
    p.add_argument("--file", required=True)
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("promote")
    p.add_argument("--write", action="store_true")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    base = state_dir(base)

    if args.cmd == "init":
        made = init(base)
        print(f"已寫入 {made}" if made else f"{base / 'sources.yaml'} 已經存在，沒有覆蓋")
        return 0
    if args.cmd == "sources":
        sources, problems = load_sources(base)
        if not sources and not problems:
            print(f"沒有來源：{base / 'sources.yaml'} 不存在。格式見 signals.py 開頭的說明。")
        for s in sources:
            has = "已設定" if env_key(s["key_env"]) else "沒有設定"
            print(f"- {s['id']}（{s['type']}）：{s['url']}；金鑰環境變數 {s['key_env']} {has}；關鍵字 {len(s['keywords'])} 個")
        for p in problems:
            print(f"沒載入：{p}")
        return 0
    if args.cmd == "collect":
        doc, problems, path = collect(base, write=args.write)
        for p in problems:
            print(f"沒載入：{p}", file=sys.stderr)
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        print(f"\n已寫入 {path}" if path else "\n（預覽，沒有寫檔；加 --write 才寫）", file=sys.stderr)
        return 0
    if args.cmd == "pending":
        print(json.dumps(pending(base, days=args.days), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "judge":
        try:
            doc = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            print(f"讀不了 {args.file}：{e}", file=sys.stderr)
            return 1
        ok, bad = check_judgments(base, doc)
        for row in ok:
            print(f"- {row['signal']}：{row['impact']}" + (f" → {row['target']}" if row.get("target") else "") + f"。{row['reason']}")
        for b in bad:
            print(f"擋下：{b}")
        if args.write and ok:
            append_jsonl(base / "judgments.jsonl", ok)
            print(f"\n記下 {len(ok)} 筆。")
        elif ok:
            print("\n（預覽，沒有寫檔；加 --write 才記下）")
        return 0 if not bad else 1
    if args.cmd == "promote":
        actions, problems = promote(base, data or profiles.DATA, write=args.write)
        names = {"reeval": "重評", "card": "寫成待評估的卡", "skip": "量不了"}
        for a in actions:
            print(f"- {a['signal']} → {names[a['action']]}" + (f" {a['tool']}" if a.get("tool") else "") + f"：{a['why']}")
        for p in problems:
            print(f"問題：{p}")
        tools = sorted({a["tool"] for a in actions if a.get("tool")})
        if args.write and tools:
            print("\n接著跑漏斗（第 0 層看 GitHub 現況，第 1 層用便宜模型讀 README）：")
            print(f"  uv run engine/skills/omnikit-eval/scripts/batch0.py --only {','.join(tools)}")
            print(f"  uv run engine/skills/omnikit-eval/scripts/layer1.py run --force --only {','.join(tools)}")
        elif actions and not args.write:
            print("\n（預覽，沒有寫檔；加 --write 才寫卡並記下）")
        return 0 if not problems else 1
    if args.cmd == "status":
        st = status(base)
        rate = "還沒有" if st["rate"] is None else f"{st['rate']:.0%}"
        r = st["results"]
        print(f"訊號 {st['signals']} 筆，待判斷 {st['pending']} 筆；判斷：不影響 {st['judged']['none']}、"
              f"名冊層 {st['judged']['roster']}（還沒送進漏斗 {st['unpromoted']}）、架構 {st['judged']['architecture']}")
        print(f"漏斗結果：命中 {len(r['hit'])}、沒中 {len(r['miss'])}、還沒跑到 {len(r['waiting'])}、量不了 {len(r['skip'])}；"
              f"命中率 {rate}；記錄 {st['days']} 天")
        for key, word in (("hit", "命中"), ("miss", "沒中"), ("waiting", "等漏斗")):
            for x in r[key]:
                print(f"  {word}：{x['tool']}（{x['signal']}）{x['why']}")
        print("可以在週報打開這一節。" if st["ready"] else "還不能打開：" + "；".join(st["missing"]))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
