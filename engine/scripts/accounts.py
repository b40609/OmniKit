# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""帳號名冊、規約、模型淘汰過濾與探測計畫（帳號池第一階段，docs/proposals/2026-11-23-account-pool.md）。

四個來源，都只讀：
- T3 的 settings.json（providerInstances）：這台有哪些實例、哪個 driver、有沒有啟用。不讀 token，也不讀環境變數的值。
- 個人層 profile 的 dispatch.md：實例的用途（classes、usage_scope）、本人與否（owner）、知情同意（tos_ack）、
  模型排除（exclude_models、include_models）。
- 共用層 data/rules/provider-terms.md：每種「driver＋登入方式」能不能自動派工、自動挑帳號，附一手原文。
- T3 每天下載的模型單價表 usage-model-rates.json（LiteLLM 的價格資料）：successor_model、deprecation_date。

能力矩陣（探測結果）存在 ~/.omnikit/dispatch/capabilities.json，可刪重建，不進 git。

模型淘汰過濾（資料驅動，不寫死模型名）：
1. 單價表任何一筆同名模型寫了 successor_model 或 deprecation_date → 「已淘汰」。
2. 已淘汰的模型，只在同一個實例還有沒被淘汰的模型可用時才過濾；整個帳號只剩舊模型時照用，並標原因。
3. profile 的 exclude_models 一律排除；include_models 一律保留（覆寫 1、2）。

用法：
  uv run engine/scripts/accounts.py scan [--json]                      帳號名冊：每個實例的用途、規約、能不能自動派、原因
  uv run engine/scripts/accounts.py models [--catalog <檔>] [--json]   每個實例的模型與過濾結果
  uv run engine/scripts/accounts.py probe-plan --catalog <檔> [--instance <id>] [--json]
        探測計畫：catalog 是 T3 orchestrator_capabilities 的回應（存成檔）；列出每個實例要測哪些模型、開到哪一檔
  uv run engine/scripts/accounts.py probe-record --file <檔>           把探測結果寫進能力矩陣
  uv run engine/scripts/accounts.py check                              規約表欄位與查證日期
  uv run engine/scripts/accounts.py --selftest
"""
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch  # noqa: E402  同一個資料夾：讀 Markdown 裡的 yaml 區塊、政策、profile

THINKING = dispatch.THINKING
PERMS = ("allowed", "needs_ack", "forbidden")
VERDICTS = ("ok", "caution", "avoid", "unknown")
SCOPES = ("auto_dispatch", "fallback_only", "manual_only")
TERMS_STALE_DAYS = 90
LEVEL_SUFFIX = re.compile(r"-(low|medium|high|xhigh)$")


# ---------- 來源 ----------

def t3_home():
    base = os.environ.get("T3CODE_HOME")
    return (Path(base) / "userdata") if base else Path.home() / ".t3" / "userdata"


def t3_instances(home=None):
    """T3 settings.json 的 providerInstances。讀不到回 None（這台沒有 T3）。"""
    path = Path(home or t3_home()) / "settings.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get("providerInstances") or {}
    except (OSError, ValueError):
        return None
    out = {}
    for iid, spec in raw.items():
        spec = spec or {}
        cfg = spec.get("config") or {}
        auth = cfg.get("authMethod") or (cfg.get("auth") or {}).get("authMethod")
        env_keys = set((cfg.get("env") or {}).keys()) | set((spec.get("env") or {}).keys())  # 只看有沒有這個名字，不讀值
        if not auth and spec.get("driver") == "claudeAgent" and {"ANTHROPIC_API_KEY"} & env_keys:
            auth = "api-key"
        if not auth and spec.get("driver") == "codex" and {"OPENAI_API_KEY", "CODEX_API_KEY"} & env_keys:
            auth = "api-key"
        out[iid] = {"driver": spec.get("driver"), "label": spec.get("displayName") or iid,
                    "enabled": spec.get("enabled", True), "auth_mode": auth,
                    "home_path": cfg.get("homePath") if isinstance(cfg.get("homePath"), str) else None}
    return out


def terms_path(data):
    return Path(data) / "rules" / "provider-terms.md"


def load_terms(data):
    p = terms_path(data)
    return dispatch.block(p) if p.is_file() else {"terms": {}, "default_auth": {}}


def rates_index(home=None):
    """單價表 → {模型名: [(來源鍵, successor, deprecation_date)]}；只留有 successor 或下架日的。"""
    path = Path(home or t3_home()) / "usage-model-rates.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8")).get("document") or {}
    except (OSError, ValueError):
        return None
    idx = {}
    for key, v in doc.items():
        if not isinstance(v, dict) or not (v.get("successor_model") or v.get("deprecation_date")):
            continue
        name = key.rsplit("/", 1)[-1].lower()
        succ = (v.get("successor_model") or "").rsplit("/", 1)[-1] or None
        idx.setdefault(name, []).append((key, succ, v.get("deprecation_date")))
    return idx


def matrix_path(state):
    return Path(state) / "dispatch" / "capabilities.json"


def load_matrix(state):
    try:
        return json.loads(matrix_path(state).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------- 名冊與規約 ----------

def terms_row(terms, driver, auth):
    auth = auth or (terms.get("default_auth") or {}).get(driver)
    row = ((terms.get("terms") or {}).get(driver) or {}).get(auth)
    if not row:
        return auth, {"verdict": "unknown", "auto_dispatch": "needs_ack", "auto_select": "needs_ack",
                      "quote": "規約表沒有這種登入方式，當成要知情同意"}
    return auth, row


def access_end(row):
    """profile 實例的 access_ends（訂閱或方案到期的時刻）→ 有時區的 datetime；沒寫或寫錯回 None。
    沒寫時區的照這台的本地時區解讀。"""
    v = (row or {}).get("access_ends")
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, date):
        dt = datetime(v.year, v.month, v.day)
    elif isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.strip())
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.astimezone()


def registry(t3, mine, terms):
    """T3 實例＋profile 登記 → 名冊。兩邊對不上的也列出來，附問題。"""
    reg = ((mine or {}).get("instances") or {})
    ids = list(t3 or {}) + [i for i in reg if i not in (t3 or {})]
    rows = []
    for iid in ids:
        live = (t3 or {}).get(iid)
        spec = reg.get(iid) or {}
        driver = (live or {}).get("driver") or spec.get("driver")
        if driver not in ("antigravity", "claudeAgent", "codex"):
            continue  # T3 其他 driver（cursor、grok 等）OmniKit 目前不派
        auth, term = terms_row(terms, driver, spec.get("auth_mode") or (live or {}).get("auth_mode"))
        scope = spec.get("usage_scope") or ("auto_dispatch" if spec.get("classes") else "manual_only")
        r = {"id": iid, "driver": driver, "label": (live or {}).get("label") or spec.get("account") or iid,
             "account": spec.get("account"), "enabled": (live or {}).get("enabled", True) if live else None,
             "in_t3": (live is not None) if t3 is not None else None, "registered": iid in reg, "auth_mode": auth, "owner": spec.get("owner"),
             "usage_scope": scope, "classes": list(spec.get("classes") or []), "tos_ack": spec.get("tos_ack"),
             "access_ends": spec.get("access_ends"), "terms": term, "problems": []}
        if spec.get("access_ends") is not None and access_end(spec) is None:
            r["problems"].append(f"access_ends 要是 ISO 8601 時刻（例如 2026-11-28T00:00:00+08:00）：{spec.get('access_ends')}")
        if t3 is not None and live is None:
            r["problems"].append("T3 裡沒有這個實例（登記了但沒接上，或改名了）")
        if live is not None and iid not in reg:
            r["problems"].append("profile 沒登記：預設只給手動（manual_only）")
        if live is not None and not live.get("enabled", True):
            r["problems"].append("T3 裡停用")
        if scope not in SCOPES:
            r["problems"].append(f"usage_scope 要是 {list(SCOPES)} 之一：{scope}")
        r["auto"] = can_auto(r, "auto_dispatch")
        rows.append(r)
    return rows


def can_auto(row, what="auto_dispatch", now=None):
    """這個實例能不能讓 agent 自動用：回 (True/False, 原因)。what：auto_dispatch 或 auto_select。
    profile 寫了 access_ends、而且已經過了，就不再自動派也不再推薦。"""
    if row["usage_scope"] == "manual_only":
        return False, "只給手動（manual_only）"
    end = access_end(row)
    if end is not None and end <= (now or datetime.now(timezone.utc)):
        return False, f"訂閱已到期（access_ends {end.isoformat()}）"
    if row["in_t3"] is False and row["driver"] != "claudeAgent":
        return False, "T3 裡沒有這個實例"
    if row["enabled"] is False:
        return False, "T3 裡停用"
    if row["registered"] and row["owner"] not in (None, "self"):
        return False, f"帳號不是本人的（owner: {row['owner']}）；三家條款都禁止把帳號給別人用"
    perm = row["terms"].get(what, "needs_ack")
    if perm == "forbidden":
        return False, f"規約不允許（{row['driver']} {row['auth_mode']}：{what} forbidden）"
    if perm == "needs_ack" and not row["tos_ack"]:
        return False, f"規約要知情同意，profile 沒填 tos_ack（{row['driver']} {row['auth_mode']}，verdict {row['terms'].get('verdict')}）"
    note = f"；已知情同意（{row['tos_ack']}）" if perm == "needs_ack" else ""
    return True, f"{row['usage_scope']}，規約 {row['terms'].get('verdict')}{note}"


def by_id(rows):
    return {r["id"]: r for r in rows}


# ---------- 模型淘汰過濾 ----------

def norm(model):
    return LEVEL_SUFFIX.sub("", (model or "").lower())


FIRST_PARTY = ("", "gemini", "vertex_ai", "anthropic", "openai")  # 原廠自己的條目；其他是轉售平台（Azure、Copilot 等）
# 同帳號、同額度桶內明確的「同家族上下位」能力關係（規則 2）：
# 2026-11-23 agy -p /usage 一手證實：Antigravity 帳號的「Claude and GPT models」桶共用 Opus 5.5 與 Sonnet 5.5，
# 且共用政策裡 antigravity 沒有任何角色使用 Sonnet；同帳號同桶已有 Opus 時，Sonnet 被壓過而過濾。
# Claude Code 原生實例（claudeAgent）有 claude-sonnet 角色（中級／Sonnet 試行），不受此條過濾。
SAME_BUCKET_SUPERIOR = {
    "antigravity": {
        "claude-sonnet-5-5": ("claude-opus-5-5", "Claude and GPT models"),
    },
}


def _is_first_party_host(host, model):
    m = norm(model)
    if not host:
        return True
    if m.startswith("claude-"):
        return host == "anthropic"
    if m.startswith("gemini-"):
        return host in ("gemini", "vertex_ai")
    if m.startswith(("gpt-", "o1", "o3", "o4")):
        return host == "openai"
    return host in FIRST_PARTY


def lineage(model, rates, today=None):
    """單價表裡這個模型的後繼與下架日：(立即生效後繼集合, 全部後繼集合, 原廠已過的下架日或 None, 說明字串)。
    轉售／雲端託管平台常替現役主力模型排一年後的 endpoint 輪替日，甚至出現互指（例如 azure_ai 寫 Opus 5.5 於 2027-09 後繼 Fable 5.2，
    vertex_ai 又寫 Fable 5.2 於 2027-11 後繼 Opus 5.5）：凡是掛著未來下架日（> today）的條目，對「仍在分工裡服役的模型」只當提醒、不過濾；
    對「已不在分工裡的模型」仍可依全部後繼過濾。原廠條目的下架日已過才算真的下架。"""
    today_d = today or date.today()
    active_succ, all_succ, past, notes = set(), set(), None, []
    m = norm(model)
    for key, s, dep in (rates or {}).get(m, []):
        host = key.rsplit("/", 1)[0] if "/" in key else ""
        dep_future = False
        if dep:
            try:
                dep_d = date.fromisoformat(str(dep)[:10])
                if dep_d > today_d:
                    dep_future = True
                elif _is_first_party_host(host, m):
                    past = str(dep)[:10]
            except ValueError:
                pass
        if s and norm(s) != m:
            ns = norm(s)
            all_succ.add(ns)
            # 排除互為後繼（A -> B 且 B -> A）以及尚未到期的遠期輪替排程，避免誤殺現役分工模型
            reverse_targets = {norm(rs) for _, rs, _ in (rates or {}).get(ns, []) if rs}
            if m not in reverse_targets and not dep_future:
                active_succ.add(ns)
            notes.append(f"{key} 寫後繼 {s}" + (f"（排程 {str(dep)[:10]}）" if dep_future else ""))
    return active_succ, all_succ, past, "；".join(notes[:2])


def model_status(model, available, mine, rates, role_models=None, driver=None):
    """一個實例上的一個模型：('keep'|'filtered', 原因)。
    available：同一個實例能用的模型（不知道給 None，當成都有）；role_models：分派政策用到的模型（不知道給 None）。
    過濾條件（資料驅動）：profile 排除；原廠下架日已過；同帳號同額度桶已有更強的同家族模型且這個供應商沒有角色使用；
    無遠期排程的單向後繼已是你分工裡的模型且帳號就有；沒有任何角色使用而且已有後繼（帳號沒別的模型可用時照用）。其他有後繼的只回提醒、不過濾。"""
    inc = {norm(m) for m in (mine or {}).get("include_models") or []}
    exc = {norm(m) for m in (mine or {}).get("exclude_models") or []}
    m = norm(model)
    active_succ, all_succ, past, notes = lineage(model, rates)
    if m in inc:
        return "keep", "profile include_models 保留"
    if m in exc:
        return "filtered", "profile exclude_models 排除" + (f"；{notes}" if notes else "")
    if past:
        return "filtered", f"原廠下架日 {past} 已過"
    roles = {norm(x) for x in role_models} if role_models is not None else None
    have = {norm(a) for a in available} if available is not None else None
    # 規則 2：同帳號同額度桶內被更強模型完全壓過，而且這個供應商沒有角色使用它
    sup = (SAME_BUCKET_SUPERIOR.get(driver) or {}).get(m)
    if sup and (roles is None or m not in roles):
        better, bucket_name = sup
        if have is None or better in have:
            return "filtered", f"同帳號同額度桶（{bucket_name}）已有更強的 {better}，且這個供應商沒有角色使用"
    if not all_succ:
        return "keep", ""
    if roles is not None:
        took = sorted(s for s in active_succ & roles if have is None or s in have)
        if took:
            return "filtered", f"被 {'、'.join(took)} 取代（已是你分工裡的模型{'，這個帳號就有' if have is not None else ''}）；{notes}"
        if m not in roles:
            alive = None if have is None else [a for a in have if a != m and a not in exc and not lineage(a, rates)[1]]
            if alive is None or alive:
                return "filtered", f"沒有角色使用，而且已有後繼；{notes}"
            return "keep", f"已有後繼，但這個帳號沒有別的模型可用，照用；{notes}"
    return "keep", f"提醒：{notes}（要不要換由你決定）"


def role_models(pol, driver=None):
    return {c["model"] for c in ((pol or {}).get("model_classes") or {}).values()
            if driver is None or c.get("driver") == driver}


def instance_models(state, catalog=None):
    """每個實例能用的模型：先看這次給的 catalog（orchestrator_capabilities），再看能力矩陣。"""
    out = {}
    for p in (catalog or {}).get("providers") or []:
        if p.get("models"):
            out[p["providerInstanceId"]] = [m["id"] for m in p["models"]]
    for iid, rec in load_matrix(state).items():
        out.setdefault(iid, list((rec.get("models") or {}).keys()))
    return out


# ---------- 探測 ----------

def top_level(options):
    """模型選項裡思考程度的最高檔（T3 的 thought_level 或 effort）。"""
    for o in options or []:
        if o.get("id") in ("thought_level", "effort", "reasoning_effort"):
            vals = [v for v in o.get("values") or [] if v in THINKING]
            if vals:
                return o["id"], max(vals, key=THINKING.index)
    return None, None


def probe_plan(catalog, rows, mine, rates, only=None, roles=None, pol=None):
    """每個實例要測的模型與程度；被過濾的模型跳過並寫原因。只排 T3 裡啟用的 Antigravity 與 Claude 實例。"""
    known = by_id(rows)
    plan = []
    for p in (catalog or {}).get("providers") or []:
        iid = p.get("providerInstanceId")
        if only and iid not in only:
            continue
        drv = p.get("driverKind")
        if drv not in ("antigravity", "claudeAgent") or not p.get("canRunChildTask"):
            continue
        drv_roles = role_models(pol, drv) if pol is not None else roles
        models = p.get("models") or []
        avail = [m["id"] for m in models]
        steps, skipped = [], []
        for m in models:
            st, why = model_status(m["id"], avail, mine, rates, drv_roles, driver=drv)
            if st == "filtered":
                skipped.append({"model": m["id"], "why": why})
                continue
            opt, lv = top_level(m.get("options"))
            steps.append({"model": m["id"], "option": opt, "level": lv, "label": m.get("label")})
        plan.append({"instance": iid, "label": p.get("displayName"), "registered": iid in known and known[iid]["registered"],
                     "steps": steps, "skipped": skipped,
                     "note": "catalog 沒列模型：用 orchestrator_capabilities 的 search 帶這個實例 id 再抓一次" if not models else ""})
    return plan


PROBE_PROMPT = ("探測：只回一行「OK <模型> <你目前讀到的 OmniKit 規則版本>」，不要做別的事。")


def probe_steps_text(plan):
    lines = ["探測步驟（T3 MCP；一個實例一條對話，同一條對話輪流換模型）：",
             "  1. t3_thread_launch 開對話（providerInstanceId＝實例、第一個模型、程度照下表），送：" + PROBE_PROMPT,
             "  2. 其餘模型：t3_thread_configure 換模型與程度 → t3_thread_send（mode queue）同一句 → t3_thread_wait",
             "  3. 記每個模型：能不能用、回覆的規則版本、耗時；寫成 JSON 交給 probe-record",
             "  4. t3_thread_organize 帶 action settle 結案，回讀確認 settled: true"]
    for p in plan:
        lines.append(f"\n{p['instance']}（{p['label']}）{'' if p['registered'] else '【profile 沒登記】'}")
        if p["note"]:
            lines.append(f"  {p['note']}")
        for s in p["steps"]:
            lines.append(f"  - {s['model']}：{s['option'] or '沒有程度選項'} {s['level'] or ''}".rstrip())
        for s in p["skipped"]:
            lines.append(f"  - 跳過 {s['model']}：{s['why']}")
    return "\n".join(lines)


def record(state, results, now=None):
    """results：[{instance, model, ok, level?, rules_version?, seconds?, note?}]。同實例同模型以新的為準。"""
    m = load_matrix(state)
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    for r in results:
        if not r.get("instance") or not r.get("model") or "ok" not in r:
            raise ValueError(f"每一筆要有 instance、model、ok：{r}")
        inst = m.setdefault(r["instance"], {"models": {}})
        inst["checked_at"] = ts
        inst["models"][r["model"]] = {k: r[k] for k in ("ok", "level", "rules_version", "seconds", "note") if k in r} | {"checked_at": ts}
    path = matrix_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return m


# ---------- 給 dispatch.py show 用 ----------

def annotate(pol, mine, data, state, t3=None, rates=None, pool_doc=None):
    """回傳 (名冊, 判斷函式, 模型過濾函式)。判斷函式 (實例, 模型) → (能不能自動派, 原因)。"""
    import account_pool
    rows = registry(t3_instances() if t3 is None else t3, mine, load_terms(data))
    reg = by_id(rows)
    rates = rates_index() if rates is None else rates
    avail = instance_models(state)
    roles_all = role_models(pol)
    pdoc = account_pool.load_state(state) if pool_doc is None else pool_doc

    def judge(iid, model):
        if iid == "native":
            return True, "目前這段對話的帳號"
        r = reg.get(iid)
        if r is None:
            return False, "名冊裡沒有"
        ok, why = can_auto(r, "auto_dispatch")
        if not ok:
            return False, why
        blk, bwhy, _ = account_pool.is_blocked(pdoc, iid, driver=r["driver"], model=model)
        if blk:
            return False, bwhy
        st, mwhy = model_status(model, avail.get(iid), mine, rates, role_models(pol, r["driver"]), driver=r["driver"])
        if st == "filtered":
            return False, mwhy
        return True, why

    def model_note(model):
        st, why = model_status(model, None, mine, rates, roles_all)
        return why if st == "filtered" else ""

    return rows, judge, model_note


def filtered_summary(pol, mine, state, rates):
    """政策用到的模型與能力矩陣裡的模型：(被過濾的, 只提醒的)，各附原因（show 的帳號段）。"""
    seen = {c["model"] for c in (pol.get("model_classes") or {}).values()}
    for ms in instance_models(state).values():
        seen.update(ms)
    seen.update((mine or {}).get("exclude_models") or [])
    out, hints = [], []
    for m in sorted(seen):
        st, why = model_status(m, None, mine, rates, role_models(pol))
        if st == "filtered":
            out.append(f"{m}（{why}）")
        elif why.startswith("提醒"):
            hints.append(f"{m}：{why[3:]}")
    # 補上供應商限定的同桶壓過（例如 Antigravity 裡的 Sonnet 5.5 被同桶 Opus 5.5 壓過）
    for drv, rules in SAME_BUCKET_SUPERIOR.items():
        drv_roles = role_models(pol, drv)
        for m in sorted(rules):
            st, why = model_status(m, None, mine, rates, drv_roles, driver=drv)
            if st == "filtered":
                out.append(f"{drv}/{m}（{why}）")
    return out, hints


# ---------- 文字 ----------

def scan_text(rows):
    lines = []
    for r in rows:
        ok, why = r["auto"]
        sel = can_auto(r, "auto_select")
        lines.append(f"{r['id']}（{r['driver']}，{r['label']}，{r['auth_mode']}）：自動派工 {'可' if ok else '不可'}：{why}")
        if r["driver"] in ("claudeAgent", "codex") and ok:
            lines.append(f"    依額度自動挑帳號：{'可' if sel[0] else '不可'}：{sel[1]}")
        for p in r["problems"]:
            lines.append(f"    問題：{p}")
    return "\n".join(lines)


def check_terms(terms, today=None):
    errs = []
    checked = terms.get("checked")
    try:
        age = ((today or date.today()) - date.fromisoformat(str(checked))).days
        if age > TERMS_STALE_DAYS:
            errs.append(f"規約表 {age} 天沒重查（上次 {checked}），條款可能改了")
    except ValueError:
        errs.append(f"規約表的 checked 不是日期：{checked}")
    for drv, modes in (terms.get("terms") or {}).items():
        for auth, row in (modes or {}).items():
            where = f"terms.{drv}.{auth}"
            if row.get("verdict") not in VERDICTS:
                errs.append(f"{where}.verdict 要是 {list(VERDICTS)} 之一")
            for k in ("auto_dispatch", "auto_select"):
                if row.get(k) not in PERMS:
                    errs.append(f"{where}.{k} 要是 {list(PERMS)} 之一：{row.get(k)}")
            if not row.get("source"):
                errs.append(f"{where} 少了 source（一手原文網址）")
    return errs


# ---------- 入口 ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description="帳號名冊、規約、模型淘汰過濾與探測計畫")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("scan")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("models")
    p.add_argument("--catalog")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("probe-plan")
    p.add_argument("--catalog", required=True)
    p.add_argument("--instance", action="append")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("probe-record")
    p.add_argument("--file", required=True)
    sub.add_parser("check")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    data, state, name, folder = dispatch.context()
    mine = dispatch.personal(folder)
    terms = load_terms(data)
    if args.cmd == "check":
        errs = check_terms(terms)
        print("\n".join(errs) if errs else f"規約表沒有問題（查證日 {terms.get('checked')}）")
        return 1 if errs else 0
    if args.cmd == "probe-record":
        results = json.loads(Path(args.file).read_text(encoding="utf-8"))
        m = record(state, results)
        print(f"已寫進 {matrix_path(state)}：{len(results)} 筆，{len(m)} 個實例")
        return 0
    t3 = t3_instances()
    rows = registry(t3, mine, terms)
    rates = rates_index()
    pol = dispatch.policy(data)
    roles = role_models(pol)
    if args.cmd == "scan":
        if t3 is None:
            print("（這台讀不到 T3 的 settings.json，只列 profile 登記的實例）")
        print(json.dumps(rows, ensure_ascii=False, indent=2) if args.json else scan_text(rows))
        return 0
    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8")) if getattr(args, "catalog", None) else None
    if args.cmd == "models":
        known = by_id(rows)
        out = {}
        for iid, ms in instance_models(state, catalog).items():
            drv = (known.get(iid) or {}).get("driver")
            drv_roles = role_models(pol, drv) if drv else roles
            out[iid] = {m: dict(zip(("status", "why"), model_status(m, ms, mine, rates, drv_roles, driver=drv))) for m in ms}
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            if not out:
                print("沒有能力矩陣也沒給 catalog：先跑探測，或用 --catalog 帶 orchestrator_capabilities 的回應")
            for iid, ms in out.items():
                bad = [f"{m}（{v['why']}）" for m, v in ms.items() if v["status"] == "filtered"]
                print(f"{iid}：可用 {sum(v['status'] == 'keep' for v in ms.values())} 個；已過濾：{'、'.join(bad) or '無'}")
            if rates is None:
                print("（讀不到 T3 的模型單價表，只套 profile 的 exclude_models）")
        return 0
    if args.cmd == "probe-plan":
        plan = probe_plan(catalog, rows, mine, rates, set(args.instance or []) or None, roles, pol=pol)
        print(json.dumps(plan, ensure_ascii=False, indent=2) if args.json else probe_steps_text(plan))
        return 0
    ap.print_help()
    return 2


# ---------- 自我測試 ----------

def selftest():
    terms = {"checked": "2026-11-23", "default_auth": {"antigravity": "oauth-personal", "claudeAgent": "subscription"},
             "terms": {"antigravity": {"oauth-personal": {"verdict": "avoid", "auto_dispatch": "needs_ack", "auto_select": "forbidden", "source": "x"},
                                       "gemini-api-key": {"verdict": "ok", "auto_dispatch": "allowed", "auto_select": "allowed", "source": "x"}},
                       "claudeAgent": {"subscription": {"verdict": "caution", "auto_dispatch": "needs_ack", "auto_select": "needs_ack", "source": "x"}}}}
    t3 = {"ag_main": {"driver": "antigravity", "label": "Main", "enabled": True, "auth_mode": None},
          "ag_spare": {"driver": "antigravity", "label": "Spare", "enabled": True, "auth_mode": None},
          "ag_key": {"driver": "antigravity", "label": "Key", "enabled": True, "auth_mode": "gemini-api-key"},
          "cl_a": {"driver": "claudeAgent", "label": "A", "enabled": True, "auth_mode": None},
          "cl_off": {"driver": "claudeAgent", "label": "Off", "enabled": False, "auth_mode": None},
          "grok": {"driver": "grok", "label": "Grok", "enabled": False, "auth_mode": None}}
    mine = {"instances": {"ag_main": {"driver": "antigravity", "classes": ["gemini-pro"], "tos_ack": "2026-11-22 2B"},
                          "ag_spare": {"driver": "antigravity", "classes": []},
                          "ag_key": {"driver": "antigravity", "classes": ["gemini-pro"]},
                          "cl_a": {"driver": "claudeAgent", "classes": ["claude-opus"], "owner": "self", "tos_ack": "2026-11-23"},
                          "cl_off": {"driver": "claudeAgent", "classes": ["claude-opus"], "owner": "self", "tos_ack": "2026-11-23"},
                          "cl_friend": {"driver": "claudeAgent", "classes": ["claude-opus"], "owner": "friend", "tos_ack": "x"},
                          "ag_gone": {"driver": "antigravity", "classes": ["gemini-pro"], "tos_ack": "x"}},
            "exclude_models": ["gpt-oss-120b"]}
    rows = by_id(registry(t3, mine, terms))
    assert "grok" not in rows
    assert rows["ag_main"]["auto"][0] and "知情同意" in rows["ag_main"]["auto"][1]
    assert not rows["ag_spare"]["auto"][0] and "manual_only" in rows["ag_spare"]["auto"][1]
    assert rows["ag_key"]["auto"][0] and rows["ag_key"]["auth_mode"] == "gemini-api-key"
    assert can_auto(rows["ag_key"], "auto_select")[0]
    assert not can_auto(rows["ag_main"], "auto_select")[0]  # 訂閱不自動輪換
    assert rows["cl_a"]["auto"][0] and can_auto(rows["cl_a"], "auto_select")[0]
    assert not rows["cl_off"]["auto"][0] and "停用" in rows["cl_off"]["auto"][1]
    assert not rows["cl_friend"]["auto"][0] and "本人" in rows["cl_friend"]["auto"][1]
    assert not rows["ag_gone"]["auto"][0] and rows["ag_gone"]["problems"]
    mine2 = {"instances": {"ag_main": {"driver": "antigravity", "classes": ["gemini-pro"]}}}
    r2 = by_id(registry(t3, mine2, terms))
    assert not r2["ag_main"]["auto"][0] and "tos_ack" in r2["ag_main"]["auto"][1]
    r3 = by_id(registry(None, mine, terms))  # 這台沒有 T3（CI、只用 Claude Code 的人）：照 profile 判斷
    assert r3["ag_main"]["auto"][0] and r3["ag_main"]["in_t3"] is None and not r3["ag_main"]["problems"]
    assert "profile 沒登記" in " ".join(r2["ag_spare"]["problems"])
    # 單價表的過濾
    rates = {"gemini-3.8-flash": [("github_copilot/gemini-3.8-flash", "gemini-4-hydrogen", None)],
             "gpt-oss-120b": [("azure_ai/gpt-oss-120b", "gpt-6.1-terra", "2027-09-15")],
             "gemini-4-hydrogen": [("x/gemini-4-hydrogen", "gemini-4-hydrogen", None)],
             "claude-opus-5-5": [("azure_ai/claude-opus-5-5", "claude-fable-5-2", "2027-09-18")],
             "old-model": [("gemini/old-model", None, "2026-01-01")]}
    roles = {"gemini-4-hydrogen", "gemini-3.8-flash", "claude-opus-5-5"}
    full = ["gemini-4-hydrogen", "gemini-3.8-flash", "gpt-oss-120b-medium", "gemini-4-neon"]
    st, why = model_status("gemini-3.8-flash", full, {}, rates, roles)
    assert st == "filtered" and "gemini-4-hydrogen 取代" in why  # 後繼已在分工裡、帳號就有
    assert model_status("gemini-3.8-flash", ["gemini-3.8-flash", "gpt-oss-120b"], {}, rates, roles)[0] == "keep"  # 帳號沒有後繼
    assert model_status("gemini-4-hydrogen", full, {}, rates, roles)[0] == "keep"  # 後繼是自己不算
    st, why = model_status("gpt-oss-120b-medium", full, {}, rates, roles)
    assert st == "filtered" and "沒有角色使用" in why  # 去掉程度字尾再比
    st, why = model_status("gpt-oss-120b", ["gpt-oss-120b", "gemini-3.8-flash"], {}, rates, roles)
    assert st == "keep" and "沒有別的模型" in why  # 只剩舊模型的帳號照用
    st, why = model_status("claude-opus-5-5", None, {}, rates, roles)
    assert st == "keep" and why.startswith("提醒")  # 轉售平台的後繼只提醒，主力模型不濾
    # 轉售／雲端平台同時把 Opus 與 Fable 互標遠期後繼、且兩者都在分工裡時：兩邊都保留（只提醒），絕不互相消滅
    cyc_rates = {**rates, "claude-fable-5-2": [("vertex_ai/claude-fable-5-2", "claude-opus-5-5", "2027-11-09")]}
    cyc_roles = {"claude-opus-5-5", "claude-fable-5-2"}
    assert model_status("claude-opus-5-5", ["claude-opus-5-5", "claude-fable-5-2"], {}, cyc_rates, cyc_roles)[0] == "keep"
    assert model_status("claude-fable-5-2", ["claude-opus-5-5", "claude-fable-5-2"], {}, cyc_rates, cyc_roles)[0] == "keep"
    assert model_status("old-model", None, {}, rates, roles)[0] == "filtered"  # 原廠下架日已過
    assert model_status("gemini-4-neon", full, {}, rates, roles) == ("keep", "")  # 沒後繼、沒角色：只是不在政策裡
    assert model_status("gemini-3.8-flash", full, {"include_models": ["gemini-3.8-flash"]}, rates, roles)[0] == "keep"
    assert model_status("gemini-4-hydrogen", full, {"exclude_models": ["gemini-4-hydrogen"]}, rates, roles)[0] == "filtered"
    assert model_status("gemini-3.8-flash", None, {}, rates, roles)[0] == "filtered"
    assert model_status("gemini-3.8-flash", full, {}, rates, None)[0] == "keep"  # 不知道角色：只提醒
    assert model_status("anything", full, {}, None, roles)[0] == "keep"
    # 規則 2：Antigravity 帳號裡 Sonnet 與 Opus 同桶且 Antigravity 沒有角色使用 Sonnet → 過濾；無 Opus 或原生 Claude 實例則保留
    st_ag_son, why_ag_son = model_status("claude-sonnet-5-5", ["claude-opus-5-5", "claude-sonnet-5-5"], {}, rates,
                                         {"gemini-4-hydrogen", "claude-opus-5-5"}, driver="antigravity")
    assert st_ag_son == "filtered" and "claude-opus-5-5" in why_ag_son
    assert model_status("claude-sonnet-5-5", ["claude-sonnet-5-5"], {}, rates,
                        {"gemini-4-hydrogen", "claude-opus-5-5"}, driver="antigravity")[0] == "keep"
    assert model_status("claude-sonnet-5-5", ["claude-opus-5-5", "claude-sonnet-5-5"], {}, rates,
                        {"claude-opus-5-5", "claude-sonnet-5-5"}, driver="claudeAgent")[0] == "keep"
    assert model_status("claude-sonnet-5-5", ["claude-opus-5-5", "claude-sonnet-5-5"],
                        {"include_models": ["claude-sonnet-5-5"]}, rates,
                        {"gemini-4-hydrogen", "claude-opus-5-5"}, driver="antigravity")[0] == "keep"
    # 探測計畫
    catalog = {"providers": [
        {"providerInstanceId": "ag_main", "driverKind": "antigravity", "displayName": "Main", "canRunChildTask": True,
         "models": [{"id": "gemini-4-hydrogen", "options": [{"id": "thought_level", "values": ["low", "medium", "high", "xhigh"]}]},
                    {"id": "gemini-3.8-flash", "options": [{"id": "thought_level", "values": ["low", "high"]}]},
                    {"id": "gemini-pro-orchestrator-neon", "options": []}]},
        {"providerInstanceId": "ag_spare", "driverKind": "antigravity", "displayName": "Spare", "canRunChildTask": True, "models": []},
        {"providerInstanceId": "grok", "driverKind": "grok", "canRunChildTask": False, "models": []}]}
    plan = probe_plan(catalog, list(rows.values()), mine, rates, roles=roles)
    assert [p["instance"] for p in plan] == ["ag_main", "ag_spare"]
    st = {s["model"]: s for s in plan[0]["steps"]}
    assert st["gemini-4-hydrogen"]["level"] == "xhigh" and "gemini-3.8-flash" not in st
    assert st["gemini-pro-orchestrator-neon"]["level"] is None
    assert plan[0]["skipped"][0]["model"] == "gemini-3.8-flash" and plan[1]["note"]
    assert "跳過 gemini-3.8-flash" in probe_steps_text(plan)
    # 能力矩陣
    with tempfile.TemporaryDirectory() as tmp:
        record(tmp, [{"instance": "ag_main", "model": "gemini-4-neon", "ok": True, "level": "xhigh"}])
        m = record(tmp, [{"instance": "ag_main", "model": "gemini-4-argon", "ok": False, "note": "403"}])
        assert set(m["ag_main"]["models"]) == {"gemini-4-neon", "gemini-4-argon"}
        assert instance_models(tmp)["ag_main"] == ["gemini-4-neon", "gemini-4-argon"]
        try:
            record(tmp, [{"instance": "x"}])
            raise AssertionError("缺欄位要報錯")
        except ValueError:
            pass
    # 規約表檢查
    assert check_terms(terms, date(2026, 12, 1)) == []
    assert any("沒重查" in e for e in check_terms(terms, date(2027, 6, 1)))
    bad = {"checked": "x", "terms": {"a": {"b": {"verdict": "nope", "auto_dispatch": "yes", "auto_select": "allowed"}}}}
    assert len(check_terms(bad)) == 4
    print("accounts.py selftest：全部通過")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
