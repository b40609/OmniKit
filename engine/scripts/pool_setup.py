# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""帳號池初次設定掃描、多使用者建議器與 dispatch.md 產生器（帳號池第三階段）。

依據 docs/proposals/2026-11-23-account-pool.md 第八節：
- 每個使用者的帳號與習慣不同：Ryan 的偏好只套 Ryan 的 profile，不強加給別人。
- 自動掃描 T3 實例、各 CLAUDE_CONFIG_DIR、CODEX_HOME、環境變數裡有沒有 API 金鑰／雲端專案（只看有沒有，絕不讀值）。
- 針對每一項設定（thinking_preference、on_exhausted、account_strategy、visibility、notify、模型過濾）給出建議值與原因；
  使用者的選擇永遠優先。
- 嚴格遵守規約表（data/rules/provider-terms.md）：新帳號預設 manual_only，owner 不是 self 不自動派，
  規約為 avoid／needs_ack 要有使用者明示的 tos_ack 才能設為 auto_dispatch，forbidden 一律不放行。
- 產生的 dispatch.md 寫進 repo 外的 ~/.omnikit/profiles/<名稱>/dispatch.md（FR-38），寫完過 dispatch.check 驗證。

用法：
  uv run engine/scripts/pool_setup.py recommend [--json]                         掃描這台並印出每一項設定的建議與原因
  uv run engine/scripts/pool_setup.py render --answers <JSON 檔> [--write] [--force]
                                                                                 依訪談答案預覽或寫入 profile 的 dispatch.md
  uv run engine/scripts/pool_setup.py --selftest
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import account_pool  # noqa: E402
import accounts  # noqa: E402
import dispatch  # noqa: E402
import homes  # noqa: E402
import profiles  # noqa: E402

# 只檢查環境變數是否存在且非空，絕不讀取、不印出、不儲存變數的值
API_ENV_VARS = {
    "anthropic_api_key": ("ANTHROPIC_API_KEY",),
    "gemini_api_key": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai_api_key": ("OPENAI_API_KEY", "CODEX_API_KEY"),
    "vertex": ("GOOGLE_CLOUD_PROJECT", "VERTEX_PROJECT"),
    "bedrock": ("CLAUDE_CODE_USE_BEDROCK", "AWS_BEDROCK_REGION"),
}


def detect_api_env(environ=None):
    """回傳 {種類: bool}，只回有沒有設，絕不讀值。"""
    env = os.environ if environ is None else environ
    return {k: any(bool(str(env.get(v) or "").strip()) for v in names) for k, names in API_ENV_VARS.items()}


def recent_quota_hits(state, days=7, now=None):
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    cutoff = now_dt - timedelta(days=days)
    rows, _ = dispatch.read_log(dispatch.log_path(state))
    hits = 0
    for r in rows:
        if r.get("error_kind") != "quota_exhausted":
            continue
        try:
            dt = datetime.fromisoformat(str(r.get("ts") or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                hits += 1
        except ValueError:
            continue
    return hits


def discover_pool(home=None, state=None, data=None, environ=None, which=shutil.which, now=None):
    """自動掃描這台的 T3 實例、獨立設定目錄（無 T3 也支援）與 API 金鑰有無。"""
    home = Path(home) if home else homes.HOME
    state = Path(state) if state else profiles.STATE
    data = Path(data) if data else profiles.DATA
    env = os.environ if environ is None else environ

    t3 = accounts.t3_instances(home / ".t3" / "userdata")
    found_homes = homes.discover(home, env)
    claude_dirs = ([home / ".claude"] if (home / ".claude").is_dir() else []) + homes.extra("claude-code", home, env, found_homes)
    codex_dirs = ([home / ".codex"] if (home / ".codex").is_dir() else []) + homes.extra("codex", home, env, found_homes)
    api_env = detect_api_env(env)
    terms = accounts.load_terms(data)

    # 整理候選實例（先收 T3 裡啟用的，沒有 T3 就從獨立設定目錄推）
    instances = []
    if t3:
        for iid, spec in t3.items():
            drv = spec.get("driver")
            if drv not in ("antigravity", "claudeAgent", "codex") or not spec.get("enabled", True):
                continue
            auth, term = accounts.terms_row(terms, drv, spec.get("auth_mode"))
            instances.append({
                "id": iid, "driver": drv, "label": spec.get("label") or iid, "source": "t3",
                "auth_mode": auth, "config_dir": spec.get("home_path"),
                "verdict": term.get("verdict"), "auto_dispatch": term.get("auto_dispatch"),
                "auto_select": term.get("auto_select"), "default_scope": "manual_only",
            })
    else:
        for idx, cdir in enumerate(claude_dirs):
            iid = "claudeAgent" if idx == 0 else f"claude_{cdir.name.lstrip('.')}"
            auth = "api-key" if api_env["anthropic_api_key"] else "subscription"
            _, term = accounts.terms_row(terms, "claudeAgent", auth)
            instances.append({
                "id": iid, "driver": "claudeAgent", "label": cdir.name, "source": "config_dir",
                "auth_mode": auth, "config_dir": str(cdir),
                "verdict": term.get("verdict"), "auto_dispatch": term.get("auto_dispatch"),
                "auto_select": term.get("auto_select"), "default_scope": "manual_only",
            })
        for idx, cdir in enumerate(codex_dirs):
            iid = "codex" if idx == 0 else f"codex_{cdir.name.lstrip('.')}"
            auth = "api-key" if api_env["openai_api_key"] else "subscription"
            _, term = accounts.terms_row(terms, "codex", auth)
            instances.append({
                "id": iid, "driver": "codex", "label": cdir.name, "source": "config_dir",
                "auth_mode": auth, "config_dir": str(cdir),
                "verdict": term.get("verdict"), "auto_dispatch": term.get("auto_dispatch"),
                "auto_select": term.get("auto_select"), "default_scope": "manual_only",
            })

    return {
        "has_t3": t3 is not None,
        "has_agy": bool(which("agy")),
        "claude_dirs": [str(p) for p in claude_dirs],
        "codex_dirs": [str(p) for p in codex_dirs],
        "api_env_present": api_env,
        "instances": instances,
        "recent_quota_hits_7d": recent_quota_hits(state, 7, now),
    }


def recommend(discovered):
    """依偵測結果對提案第八節的每一項設定給出建議與原因；使用者永遠可以改選。"""
    insts = discovered.get("instances") or []
    by_drv = {}
    for i in insts:
        by_drv.setdefault(i["driver"], []).append(i)
    max_same_family = max((len(v) for v in by_drv.values()), default=0)
    hits = int(discovered.get("recent_quota_hits_7d") or 0)
    api = discovered.get("api_env_present") or {}
    has_paid_api = any(api.values())

    # 1. thinking_preference
    if max_same_family >= 2 and hits < 2:
        th_val, th_why = "max_available", f"同供應商有 {max_same_family} 個帳號且近 7 天撞額度 {hits} 次，可開到模型最高檔"
    elif max_same_family <= 1 and hits >= 3:
        th_val, th_why = "economy", f"單一帳號且近 7 天撞額度 {hits} 次，建議只把高檔留給定案與審查"
    else:
        th_val, th_why = "balanced", f"定案、審查、前置苦工用高檔，其餘照政策平衡（同家最多 {max_same_family} 個帳號、近 7 天撞額度 {hits} 次）"

    # 2. on_exhausted
    if has_paid_api:
        keys = [k for k, v in api.items() if v]
        ex_val = "fallback_paid_api"
        ex_why = f"偵測到付費 API／雲端環境變數（{'、'.join(keys)}），訂閱用完可切備援；怕意外帳單請改選 fail_closed"
    else:
        ex_val = "prompt_manual_switch"
        ex_why = "未偵測到 API 金鑰備援，額度用完時列出各帳號剩餘與重置時間由你決定"

    # 3. account_strategy
    claude_cnt = len(by_drv.get("claudeAgent") or [])
    if claude_cnt >= 2:
        st_val = "weekly-first"
        st_why = f"偵測到 {claude_cnt} 個 Claude 帳號，工作包邊界優先消耗最快重置且還有剩的週額度（搭配 5 分鐘冷卻與 5pp 防震盪）"
    else:
        st_val = "sticky"
        st_why = "單一帳號固定黏著，最大化 Prompt Cache 命中"

    # 4. visibility
    if discovered.get("has_t3"):
        vis_val, vis_why = "visible", "這台有裝 T3 Code，開成 T3 看得到的對話，方便檢查 prompt 與過程"
    elif discovered.get("has_agy"):
        vis_val, vis_why = "headless", "這台沒裝 T3 Code 但有 agy，改走無頭模式"
    else:
        vis_val, vis_why = "visible", "預設為 visible（裝上 T3 後自動看得到過程）"

    # 5. notify
    nt_val = "hook"
    nt_why = "預設在主線對話第一回合顯示異常提醒（validation_required、auth_expired、tos_banned 永遠提醒）；想加系統通知可選 desktop 或 webhook"

    # 6. model_filter
    mf_val = True
    mf_why = "預設開啟自動淘汰過濾（有後繼或同桶被壓過的舊模型自動跳過；只剩舊模型的帳號照用，可用 include_models 撈回）"

    return {
        "thinking_preference": {"recommended": th_val, "choices": list(account_pool.THINKING_PREFS), "why": th_why},
        "on_exhausted": {"recommended": ex_val, "choices": list(account_pool.ON_EXHAUSTED_MODES), "why": ex_why},
        "account_strategy": {"recommended": st_val, "choices": list(account_pool.ACCOUNT_STRATEGIES), "why": st_why},
        "visibility": {"recommended": vis_val, "choices": list(dispatch.VISIBILITY), "why": vis_why},
        "notify": {"recommended": nt_val, "choices": list(account_pool.NOTIFY_MODES), "why": nt_why},
        "model_filter": {"recommended": mf_val, "choices": [True, False], "why": mf_why},
    }


DEFAULT_CLASSES_BY_DRIVER = {
    "claudeAgent": ["claude-opus", "claude-sonnet"],
    "antigravity": ["gemini-pro", "gemini-fast", "antigravity-opus"],
    "codex": [],
}


def validate_pool_answers(answers, data):
    """檢查訪談產生的帳號池答案，嚴格套規約表與 dispatch.check。回傳錯誤列表。"""
    errors = []
    if not isinstance(answers, dict):
        return ["答案檔最外層要是 JSON 物件"]
    name = answers.get("profile")
    if not name or not profiles.NAME.match(str(name)) or name == "default":
        errors.append(f"profile 名稱不合法或不能為 default：{name}")
    for key, allowed in (
        ("thinking_preference", account_pool.THINKING_PREFS),
        ("on_exhausted", account_pool.ON_EXHAUSTED_MODES),
        ("account_strategy", account_pool.ACCOUNT_STRATEGIES),
        ("visibility", dispatch.VISIBILITY),
        ("notify", account_pool.NOTIFY_MODES),
    ):
        if key in answers and answers[key] not in allowed:
            errors.append(f"{key} 要是 {list(allowed)} 之一：{answers[key]}")
    terms = accounts.load_terms(data)
    pol = dispatch.policy(data)
    valid_classes = set((pol.get("model_classes") or {}).keys())
    for iid, spec in (answers.get("instances") or {}).items():
        if not isinstance(spec, dict):
            errors.append(f"instances.{iid} 要是物件")
            continue
        drv = spec.get("driver")
        if drv not in ("antigravity", "claudeAgent", "codex"):
            errors.append(f"instances.{iid}.driver 不支援：{drv}")
            continue
        scope = spec.get("usage_scope", "manual_only")
        if scope not in accounts.SCOPES:
            errors.append(f"instances.{iid}.usage_scope 要是 {list(accounts.SCOPES)} 之一：{scope}")
            continue
        owner = spec.get("owner", "self")
        if scope != "manual_only" and owner != "self":
            errors.append(f"instances.{iid}：owner 不是 self（{owner}），三家條款都禁止多人共用，不能設為 {scope}")
        _, term = accounts.terms_row(terms, drv, spec.get("auth_mode"))
        if scope != "manual_only":
            perm = term.get("auto_dispatch", "needs_ack")
            if perm == "forbidden":
                errors.append(f"instances.{iid}：規約禁止自動派工（{drv} {spec.get('auth_mode')}）")
            elif perm == "needs_ack" and not str(spec.get("tos_ack") or "").strip():
                errors.append(f"instances.{iid}：規約要求知情同意（verdict {term.get('verdict')}），改為 {scope} 必須填 tos_ack")
        for cls in spec.get("classes") or []:
            if cls not in valid_classes:
                errors.append(f"instances.{iid}：模型類別不存在：{cls}")
            elif pol["model_classes"][cls].get("driver") != drv:
                errors.append(f"instances.{iid}：{cls} 要用 {pol['model_classes'][cls]['driver']}，但實例是 {drv}")
    return errors


def render_dispatch_md(answers, data, today=None):
    """把已驗證的訪談答案轉成個人 profile 的 dispatch.md（每格附設定原因）。"""
    today = today or date.today().isoformat()
    doc = {
        "visibility": answers.get("visibility", "visible"),
        "thinking_preference": answers.get("thinking_preference", "balanced"),
        "on_exhausted": answers.get("on_exhausted", "prompt_manual_switch"),
        "account_strategy": answers.get("account_strategy", "sticky"),
        "notify": answers.get("notify", "hook"),
    }
    if answers.get("exclude_models"):
        doc["exclude_models"] = list(answers["exclude_models"])
    if answers.get("include_models"):
        doc["include_models"] = list(answers["include_models"])
    insts = {}
    for iid, spec in (answers.get("instances") or {}).items():
        scope = spec.get("usage_scope", "manual_only")
        classes = list(spec.get("classes") or ([] if scope == "manual_only" else DEFAULT_CLASSES_BY_DRIVER.get(spec["driver"], [])))
        entry = {
            "driver": spec["driver"],
            "account": spec.get("account") or iid,
            "owner": spec.get("owner", "self"),
            "usage_scope": scope,
            "classes": classes,
        }
        if spec.get("auth_mode"):
            entry["auth_mode"] = spec["auth_mode"]
        if spec.get("config_dir"):
            entry["config_dir"] = spec["config_dir"]
        if spec.get("tos_ack"):
            entry["tos_ack"] = spec["tos_ack"]
        insts[iid] = entry
    doc["instances"] = insts

    pol = dispatch.policy(data)
    errs = dispatch.check(pol, doc)
    if errs:
        raise ValueError("產生的 dispatch.md 未通過政策檢查：\n" + "\n".join(f"- {e}" for e in errs))

    dumped = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000).rstrip()
    header = (
        f"# 個人分派設定：{answers['profile']}\n\n"
        f"這份由 omnikit-setup 帳號池訪談產生（{today}），存在 repo 外的個人 profile 資料夾，可以直接改；"
        "完整分派政策在 `data/rules/dispatch-policy.md`，規約表在 `data/rules/provider-terms.md`。\n\n"
        "```yaml\n"
        f"{dumped}\n"
        "```\n"
    )
    return header


def write_dispatch_md(state, profile_name, content, force=False):
    folder = Path(state) / "profiles" / profile_name
    target = folder / "dispatch.md"
    if target.exists() and not force:
        raise SystemExit(f"{target} 已經存在；要覆蓋請加 --force（舊檔會先備份成 dispatch.md.bak）")
    folder.mkdir(parents=True, exist_ok=True)
    backup = None
    if target.exists():
        backup = folder / "dispatch.md.bak"
        if backup.exists():
            backup = folder / f"dispatch.md.bak-{datetime.now():%Y%m%d%H%M%S}"
        target.replace(backup)
    target.write_text(content, encoding="utf-8", newline="\n")
    return target, backup


def recommend_text(discovered, recs):
    lines = ["帳號池偵測與設定建議（你的選擇永遠優先）："]
    lines.append(f"  環境：T3 Code {'有' if discovered['has_t3'] else '無'}、agy {'有' if discovered['has_agy'] else '無'}、"
                 f"Claude 目錄 {len(discovered['claude_dirs'])} 個、Codex 目錄 {len(discovered['codex_dirs'])} 個、"
                 f"近 7 天撞額度 {discovered['recent_quota_hits_7d']} 次")
    present_api = [k for k, v in discovered["api_env_present"].items() if v]
    lines.append(f"  偵測到 API／雲端環境變數（只看有無，不讀值）：{'、'.join(present_api) or '無'}")
    lines.append(f"  實例（{len(discovered['instances'])} 個，新帳號預設 manual_only）：")
    for i in discovered["instances"]:
        lines.append(f"    - {i['id']}（{i['driver']}，{i['auth_mode']}，規約 {i['verdict']}，auto_dispatch={i['auto_dispatch']}）")
    lines.append("\n建議設定（每格附原因）：")
    for k, v in recs.items():
        lines.append(f"  - {k}：建議 `{v['recommended']}`（可選：{'、'.join(map(str, v['choices']))}）— {v['why']}")
    return "\n".join(lines)


# ---------- CLI ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description="帳號池初次設定偵測、建議器與 dispatch.md 產生器")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("recommend")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("render")
    p.add_argument("--answers", required=True, help="訪談答案 JSON 檔")
    p.add_argument("--write", action="store_true", help="寫入 ~/.omnikit/profiles/<名稱>/dispatch.md")
    p.add_argument("--force", action="store_true")

    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    data, state = profiles.DATA, profiles.STATE
    if args.cmd == "recommend":
        disc = discover_pool(state=state, data=data)
        recs = recommend(disc)
        if args.json:
            print(json.dumps({"discovered": disc, "recommendations": recs}, ensure_ascii=False, indent=2))
        else:
            print(recommend_text(disc, recs))
        return 0

    if args.cmd == "render":
        raw = json.loads(Path(args.answers).read_text(encoding="utf-8-sig"))
        errs = validate_pool_answers(raw, data)
        if errs:
            print("帳號池答案有問題：")
            print("\n".join(f"- {e}" for e in errs))
            return 1
        md = render_dispatch_md(raw, data)
        if not args.write:
            print(f"預覽（不會寫進 repo，寫入位置：{state / 'profiles' / raw['profile'] / 'dispatch.md'}）：\n")
            print(md)
            return 0
        target, bak = write_dispatch_md(state, raw["profile"], md, force=args.force)
        print(f"已寫入 {target}" + (f"（舊檔備份：{bak.name}）" if bak else ""))
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

    # 1. 不讀金鑰值、正確區分三類使用者的建議器
    env_with_key = {"ANTHROPIC_API_KEY": "sk-ant-never-print-this-secret"}
    det = detect_api_env(env_with_key)
    ok("環境變數偵測：只回布林值，不外洩金鑰內容",
       det["anthropic_api_key"] is True and det["gemini_api_key"] is False
       and "never-print" not in json.dumps(det))

    r_multi = recommend({"has_t3": True, "has_agy": True, "claude_dirs": ["a", "b"], "codex_dirs": [],
                         "api_env_present": {"anthropic_api_key": False}, "recent_quota_hits_7d": 0,
                         "instances": [{"id": "c1", "driver": "claudeAgent"}, {"id": "c2", "driver": "claudeAgent"}]})
    r_single_hit = recommend({"has_t3": False, "has_agy": True, "claude_dirs": ["a"], "codex_dirs": [],
                              "api_env_present": {"gemini_api_key": True}, "recent_quota_hits_7d": 4,
                              "instances": [{"id": "c1", "driver": "claudeAgent"}]})
    ok("建議器：同家多帳號少撞額度建議 max_available＋weekly-first＋prompt_manual_switch＋visible",
       r_multi["thinking_preference"]["recommended"] == "max_available"
       and r_multi["account_strategy"]["recommended"] == "weekly-first"
       and r_multi["on_exhausted"]["recommended"] == "prompt_manual_switch"
       and r_multi["visibility"]["recommended"] == "visible")
    ok("建議器：單帳號常撞額度且有 API 金鑰建議 economy＋sticky＋fallback_paid_api＋headless",
       r_single_hit["thinking_preference"]["recommended"] == "economy"
       and r_single_hit["account_strategy"]["recommended"] == "sticky"
       and r_single_hit["on_exhausted"]["recommended"] == "fallback_paid_api"
       and r_single_hit["visibility"]["recommended"] == "headless")

    # 2. 無 T3 環境也能從 CLAUDE_CONFIG_DIR / CODEX_HOME 發現多帳號
    with tempfile.TemporaryDirectory() as tmp:
        h, st = Path(tmp) / "home", Path(tmp) / "state"
        (h / ".claude").mkdir(parents=True)
        (h / ".claude-work").mkdir(parents=True)
        (h / ".claude-work" / ".claude.json").write_text("{}", encoding="utf-8")
        (h / ".codex").mkdir(parents=True)
        disc = discover_pool(home=h, state=st, data=profiles.DATA, environ={}, which=lambda x: None)
        ok("無 T3 環境：自動從設定目錄偵測多個 Claude 目錄與 Codex 目錄，預設 manual_only",
           not disc["has_t3"] and len(disc["claude_dirs"]) == 2
           and all(i["default_scope"] == "manual_only" for i in disc["instances"]))

        # 3. 規約驗證：缺 tos_ack 與非本人都被擋，合法答案產出可通過 dispatch.check 的 dispatch.md
        bad_ack = {"profile": "alice", "instances": {"ag1": {"driver": "antigravity", "usage_scope": "auto_dispatch", "owner": "self"}}}
        bad_owner = {"profile": "alice", "instances": {"c1": {"driver": "claudeAgent", "usage_scope": "auto_dispatch", "owner": "friend", "tos_ack": "x"}}}
        ok("規約檢查：訂閱設 auto_dispatch 沒 tos_ack 會擋；owner 不是 self 會擋",
           any("tos_ack" in e for e in validate_pool_answers(bad_ack, profiles.DATA))
           and any("owner" in e for e in validate_pool_answers(bad_owner, profiles.DATA)))

        good = {
            "profile": "alice", "visibility": "visible", "thinking_preference": "balanced",
            "on_exhausted": "prompt_manual_switch", "account_strategy": "weekly-first", "notify": "hook",
            "instances": {
                "claudeAgent": {"driver": "claudeAgent", "account": "Alice", "owner": "self",
                                "usage_scope": "auto_dispatch", "tos_ack": "2026-11-23 同意"},
                "antigravity_spare": {"driver": "antigravity", "account": "Spare", "owner": "self",
                                      "usage_scope": "manual_only"},
            },
        }
        ok("合法答案通過驗證並產出合法 dispatch.md（寫在 repo 外，重寫自動備份）",
           validate_pool_answers(good, profiles.DATA) == [])
        md = render_dispatch_md(good, profiles.DATA, today="2026-11-23")
        t1, b1 = write_dispatch_md(st, "alice", md)
        t2, b2 = write_dispatch_md(st, "alice", md + "\n", force=True)
        parsed = dispatch.block(t2)
        ok("寫入與備份正常，產出的 dispatch.md 可被 dispatch.block 與 dispatch.check 解析通過",
           b1 is None and b2 is not None and b2.name == "dispatch.md.bak"
           and parsed["thinking_preference"] == "balanced"
           and parsed["instances"]["antigravity_spare"]["classes"] == []
           and dispatch.check(dispatch.policy(profiles.DATA), parsed) == [])

    print(f"\n{'pool_setup.py selftest：全部通過' if not failures else f'pool_setup.py selftest：{len(failures)} 項失敗'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
