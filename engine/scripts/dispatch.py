# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""子任務分派：讀分派政策、寫委派紀錄、算 Sonnet 試行的比較、讀本週 Claude 用量。

政策分兩層，都是 Markdown 檔裡的一個 ```yaml 區塊（agent 載入規則時讀得懂，這支腳本也讀得到）：
- data/rules/dispatch-policy.md：共用層的完整政策（任務類型 → 級別 → 模型類別 → 思考程度 → 升級）；
  常駐載入的 data/rules/dispatch.md 只有幾行原則，沒有 yaml
- <profile>/dispatch.md：個人層，自己有哪些供應商實例、每個類別用哪個；沒有就只用原生子代理
profiles.py 把兩份接進 Claude Code、Codex 與 Antigravity 的規則；這支不改規則，只讀。

委派紀錄存在本機 ~/.omnikit/dispatch/log.jsonl（一次委派一行，不進 repo、不上傳）。
這份紀錄之後要拿來依數據調整分派規則；這支只負責記錄與計算，不會自己改規則。

本週 Claude 用量：Claude Code 狀態列的 JSON 輸入有 rate_limits.seven_day.used_percentage
（https://code.claude.com/docs/en/statusline）。`statusline` 子指令可以設成狀態列指令（或串在原本的前面），
把它存成 ~/.omnikit/dispatch/claude-usage.json；`usage` 讀這份快照。
T3 透過 Agent SDK 跑 Claude 時狀態列會不會執行，還沒實測（待驗證）。

用法：
  uv run engine/scripts/dispatch.py show [--agent claude|codex|antigravity] [--json]   套上這台 profile 之後的分派表
  uv run engine/scripts/dispatch.py check                                            檢查兩層政策
  uv run engine/scripts/dispatch.py log --task <類型> --class <類別> --thinking <程度> --verdict pass|fail|partial|skipped
        [--first-pass yes|no] [--retries N] [--retries-infra N] [--retries-quality N] [--escalations N] [--final-class <類別>]
        [--origin field|eval|probe] [--role author|reviewer|prework|judge] [--infra <基礎設施問題>]
        [--scope complete|capped_by_caller|truncated_by_model | --scope-capped] [--unverified]
        [--subject-pass yes|no|na] [--model-ok yes|no|na] [--defect <缺陷類別>]
        [--duration-sec <秒>] [--work <群組ID>] [--eval-ref-json <JSON>]
        [--channel native|agy_cli|t3_cli|delegate_task|t3_thread_launch]
        [--instance <實例>] [--level <級別>] [--project <名稱>] [--control] [--note <文字>] [--dry-run]
  uv run engine/scripts/dispatch.py stats [--mode both|raw|clean] [--json]           去噪模型良率（Wilson 95% CI）、原始通過率與試行判定
  uv run engine/scripts/dispatch.py backfill-audit [--limit 30] [--json]             唯讀回溯投影對帳與原 log 零寫改雜湊驗證
  uv run engine/scripts/dispatch.py usage [--json]                                   本週 Claude 用量（快照）
  uv run engine/scripts/dispatch.py statusline [--then "<原本的狀態列指令>"]          給 Claude Code 狀態列用
  uv run engine/scripts/dispatch.py agy --class <類別> --thinking <程度> (--brief <文字> | --brief-file <檔>) [--cwd <資料夾>]
        [--timeout 秒] [--log-file <檔>]                                              用 agy 無頭派（visibility: headless；T3 看不到）
  uv run engine/scripts/dispatch.py --selftest
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402  同一個資料夾：這台選的 profile 與它的資料夾

THINKING = ["low", "medium", "high", "xhigh", "max"]
VERDICTS = ("pass", "fail", "partial", "skipped")
SCHEMA_VERSION = 2
ORIGINS = ("field", "eval", "probe")
ROLES = ("author", "reviewer", "prework", "judge")
INFRA_ISSUES = (
    "quota",
    "rate_limit",
    "model_unavailable",
    "auth",
    "harness_timeout",
    "harness_permission",
    "harness_tooling",
    "cancelled",
)
SCOPES = ("complete", "capped_by_caller", "truncated_by_model")
DEFECT_KINDS = (
    "wrong_fact",
    "false_claim",
    "missed_requirement",
    "overreach",
    "unfinished",
    "low_quality",
    "other",
)
STATS_MODES = ("both", "raw", "clean")
ERROR_TO_INFRA = {
    "quota_exhausted": "quota",
    "rate_limit": "rate_limit",
    "model_forbidden": "model_unavailable",
    "auth_expired": "auth",
    "validation_required": "auth",
    "tos_banned": "auth",
    "hard_forbidden": "auth",
    "timeout_15min": "harness_timeout",
    "other": "harness_tooling",
}
QUOTA_INFRA = frozenset({"quota", "rate_limit", "model_unavailable", "auth"})
HARNESS_INFRA = frozenset({"harness_timeout", "harness_permission", "harness_tooling", "cancelled"})
LEGACY_CLASS_MODELS = {
    "claude-fable": "claude-fable-5-2",
    "claude-opus": "claude-opus-5-5",
    "claude-sonnet": "claude-sonnet-5-5",
    "gemini-carbon": "gemini-4-carbon",
    "gemini-pro": "gemini-4-neon",
    "gemini-fast": "gemini-4-hydrogen",
    "gemini-orchestrator": "gemini-pro-orchestrator-neon",
    "antigravity-opus": "claude-opus-5-5",
    "gemini-flash": "gemini-3.8-flash",
    "gemini-argon": "gemini-4-argon",
}
LOG_FIELDS = (
    "ts", "project", "task", "level", "channel", "instance", "class", "model", "thinking",
    "first_pass", "retries", "escalations", "final_class", "verdict", "error_kind",
    "rules_version", "profile", "control", "note",
    "schema_version", "origin", "role", "infra_issue", "scope", "unverified",
    "subject_pass", "model_ok", "defect_kind", "retries_infra", "retries_quality",
    "judged_model", "judged_thinking", "duration_sec", "work_id", "eval_ref", "inferred",
)
# 管道名稱要和共用層 channels 的 key 一致（check 會比對）。t3_cli：不在 T3 裡，用本機 t3 thread CLI 開 T3 對話。
CHANNELS = ("native", "agy_cli", "t3_cli", "delegate_task", "t3_thread_launch")
# 派給 Antigravity 時看不看得到過程：個人層 dispatch.md 的 visibility，沒寫用共用層 visibility.default（2026-11-21）。
VISIBILITY = ("visible", "headless")
AGY_MAX_BRIEF = 30000  # Windows 命令列上限約 32k 字元，任務說明走參數，留一點餘裕
AGENT_DRIVER = {"claude": "claudeAgent", "codex": "codex", "antigravity": "antigravity"}
FENCE = re.compile(r"```ya?ml\s*\n(.*?)\n```", re.S)
VERSION = re.compile(r"規則版本：\s*(\S+)")
STALE_HOURS = 12  # 快照超過這麼久，用量可能偏低（週用量只會往上加）
# 自我測試用的假個人層（2026-11-27）：個人 profile 不進公開 repo，自測與 tests/ 改讀這份，實例名與帳號名都是假的
SAMPLE_PROFILE = Path(__file__).resolve().parent / "testdata" / "profile-sample"


# ---------- 讀政策 ----------

class NoDupLoader(yaml.SafeLoader):
    """同一層重複的鍵直接報錯：PyYAML 預設只留後面那個，前面的規則會悄悄消失（2026-11-16 delegate_task 寫了兩個 note）。"""


def _no_dup(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    dup = sorted({str(k) for k in keys if keys.count(k) > 1})
    if dup:
        raise ValueError(f"yaml 有重複的鍵（第 {node.start_mark.line + 1} 行那一層）：{'、'.join(dup)}")
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


NoDupLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup)


def block(path):
    """Markdown 檔裡第一個 ```yaml 區塊；檔案不存在回 None。"""
    if not Path(path).is_file():
        return None
    m = FENCE.search(Path(path).read_bytes().decode("utf-8-sig").replace("\r\n", "\n"))
    if not m:
        raise ValueError(f"{path}：找不到 ```yaml 區塊")
    doc = yaml.load(m.group(1), NoDupLoader)  # noqa: S506  SafeLoader 的子類別
    if not isinstance(doc, dict):
        raise ValueError(f"{path}：yaml 區塊不是對照表")
    return doc


def policy_path(data):
    """完整政策在 dispatch-policy.md（不載入每段對話）；舊版放在 dispatch.md 的 yaml 區塊，還讀得到。"""
    rules = Path(data) / "rules"
    return rules / "dispatch-policy.md" if (rules / "dispatch-policy.md").is_file() else rules / "dispatch.md"


def policy(data):
    path = policy_path(data)
    if path.name == "dispatch.md" and path.is_file() and not FENCE.search(path.read_bytes().decode("utf-8-sig")):
        return None  # 只有原則、沒有政策：當成沒有共用層
    return block(path)


def personal(profile_dir):
    return block(Path(profile_dir) / "dispatch.md") if profile_dir else None


def rules_version(data):
    m = VERSION.search((Path(data) / "rules" / "baseline.md").read_text(encoding="utf-8"))
    return m.group(1) if m else "unknown"


def options(pol, level):
    lv = pol["levels"][level]
    return list(lv.get("prework") or []) + list(lv.get("route") or []) + list(lv.get("second_opinion") or [])


def check(pol, mine=None):
    """兩層政策的跨欄位檢查，回傳問題清單。"""
    errors = []
    classes = pol.get("model_classes") or {}
    levels = pol.get("levels") or {}
    for key in ("model_classes", "tasks", "levels", "escalation", "channels", "visibility", "antigravity_turns", "usage_signal", "trials", "log"):
        if key not in pol:
            errors.append(f"共用層少了 {key}")
    if "log" in pol:
        log_cfg = pol.get("log")
        fields = (log_cfg or {}).get("fields") if isinstance(log_cfg, dict) else None
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            errors.append("log.fields 要是欄位名稱清單")
        else:
            expected_fields = set(LOG_FIELDS)
            valid_task = next(
                (tk for tk, tv in (pol.get("tasks") or {}).items()
                 if isinstance(tv, dict) and tv.get("level") in levels),
                None,
            )
            valid_cls = next(
                (ck for ck, cv in classes.items()
                 if isinstance(cv, dict) and cv.get("model") and cv.get("default_thinking") in THINKING
                 and THINKING.index(cv["default_thinking"]) <= THINKING.index(cv.get("max_thinking", "max")
                 if cv.get("max_thinking") in THINKING else "max")),
                None,
            )
            if valid_task and valid_cls:
                try:
                    sample_rec = make_record(
                        pol,
                        argparse.Namespace(
                            task=valid_task, cls=valid_cls,
                            thinking=classes[valid_cls]["default_thinking"],
                            verdict="pass", first_pass=None, retries=0, escalations=0,
                            final_class=None, channel="native", instance=None,
                            level=None, project="p", control=False, note=None,
                        ),
                        "v", "default", "p", datetime(2026, 11, 29, tzinfo=timezone.utc),
                    )
                    expected_fields = set(sample_rec.keys())
                except SystemExit:
                    pass
            f_set = set(fields)
            if len(fields) != len(f_set):
                errors.append(f"log.fields 有重複欄位：{sorted(f for f in f_set if fields.count(f) > 1)}")
            if f_set != expected_fields:
                errors.append(
                    f"log.fields 和 make_record 實際欄位對不上：政策多了 {sorted(f_set - expected_fields)}，"
                    f"少了 {sorted(expected_fields - f_set)}"
                )
    turns = pol.get("antigravity_turns") or {}
    if "antigravity_turns" in pol:
        if len(turns.get("brief") or []) != 4:
            errors.append("antigravity_turns.brief 要列四件事（交付檔、完成標記、10 行內的回覆、伺服器背景啟動）")
        for k in ("verify", "failed_15min"):
            if not turns.get(k):
                errors.append(f"antigravity_turns 少了 {k}")
    vis = pol.get("visibility") or {}
    modes = vis.get("modes") or {}
    if "visibility" in pol:
        if set(modes) != set(VISIBILITY):
            errors.append(f"visibility.modes 要剛好是 {list(VISIBILITY)}：{sorted(modes)}")
        if vis.get("default") not in VISIBILITY:
            errors.append(f"visibility.default 要是 {list(VISIBILITY)} 之一：{vis.get('default')}")
        for m, spec in modes.items():
            chs = [(c or {}).get("channel") for c in ((spec or {}).get("channels") or [])]
            if not chs or any(c not in CHANNELS for c in chs):
                errors.append(f"visibility.modes.{m}.channels 要列存在的管道：{chs}")
            if not (spec or {}).get("fallback"):
                errors.append(f"visibility.modes.{m} 少了 fallback（這個偏好的管道用不了時怎麼退）")
        if "agy_cli" in [(c or {}).get("channel") for c in ((modes.get("visible") or {}).get("channels") or [])]:
            errors.append("visibility.modes.visible.channels 不能有 agy_cli（T3 看不到）")
    chans = set(pol.get("channels") or {})
    if "channels" in pol and chans != set(CHANNELS):
        errors.append(f"channels 和 dispatch.py 的 CHANNELS 對不上：政策多了 {sorted(chans - set(CHANNELS))}，"
                      f"少了 {sorted(set(CHANNELS) - chans)}")
    sob = pol.get("second_opinion_burn")
    if sob is not None:
        if not isinstance(sob, dict):
            errors.append("second_opinion_burn 要是對照表")
        else:
            if not isinstance(sob.get("within_hours"), (int, float)) or not 0 < sob["within_hours"] <= 168:
                errors.append(f"second_opinion_burn.within_hours 要是 1 到 168 的小時數：{sob.get('within_hours')}")
            if not isinstance(sob.get("min_weekly_remaining_pct"), (int, float)) or not 0 <= sob["min_weekly_remaining_pct"] <= 100:
                errors.append(f"second_opinion_burn.min_weekly_remaining_pct 要是 0 到 100：{sob.get('min_weekly_remaining_pct')}")
            for a, rv in (sob.get("same_vendor") or {}).items():
                rc = (rv or {}).get("class")
                if a not in classes or rc not in classes:
                    errors.append(f"second_opinion_burn.same_vendor.{a}：模型類別不存在（{a} → {rc}）")
                    continue
                if rc == a or classes[rc].get("model") == classes[a].get("model"):
                    errors.append(f"second_opinion_burn.same_vendor.{a}：審查者跟作者同一個模型，同一個模型不能審自己")
                if classes[rc].get("driver") != classes[a].get("driver"):
                    errors.append(f"second_opinion_burn.same_vendor.{a}：改判要同一家，{rc} 是別家")
                if (rv or {}).get("thinking") not in THINKING:
                    errors.append(f"second_opinion_burn.same_vendor.{a}：thinking 要是 {THINKING} 之一")
    for lv_name, lv in levels.items():
        for o in (lv or {}).get("route") or []:
            if o.get("usage_gate") not in (None, "below_threshold"):
                errors.append(f"levels.{lv_name}.route：usage_gate 只能是 below_threshold：{o.get('usage_gate')}")
    for name, c in classes.items():
        for k in ("model", "driver", "default_thinking", "max_thinking"):
            if k not in c:
                errors.append(f"model_classes.{name} 少了 {k}")
        for k in ("default_thinking", "max_thinking"):
            if k in c and c[k] not in THINKING:
                errors.append(f"model_classes.{name}.{k} 不是 {THINKING} 之一：{c[k]}")
        if "opt_in" in c and not isinstance(c["opt_in"], bool):
            errors.append(f"model_classes.{name}.opt_in 要是 true 或 false：{c['opt_in']}")
    for task, t in (pol.get("tasks") or {}).items():
        if t.get("level") not in levels:
            errors.append(f"tasks.{task} 的級別不存在：{t.get('level')}")
    for level in levels:
        if not levels[level].get("route"):
            errors.append(f"levels.{level} 沒有 route")
        for i, o in enumerate(options(pol, level)):
            where = f"levels.{level} 第 {i + 1} 個選項"
            c = classes.get(o.get("class"))
            if c is None:
                errors.append(f"{where}：模型類別不存在：{o.get('class')}")
                continue
            th = o.get("thinking")
            if th not in THINKING:
                errors.append(f"{where}：thinking 要寫明（{THINKING} 之一），不要靠預設值：{th}")
            elif THINKING.index(th) > THINKING.index(c.get("max_thinking", "max")):
                errors.append(f"{where}：{o['class']} 的 thinking 最高 {c['max_thinking']}，寫了 {th}")
            elif th in (c.get("forbid_thinking") or []):
                errors.append(f"{where}：{o['class']} 禁用 thinking {th}")
            for task in o.get("tasks") or []:
                if task not in (pol.get("tasks") or {}):
                    errors.append(f"{where}：tasks 裡的任務類型不存在：{task}")
            if o.get("trial") and o["trial"] not in (pol.get("trials") or {}):
                errors.append(f"{where}：試行不存在：{o['trial']}")
            fb = o.get("fallback_for")
            if fb is not None and (fb not in classes or fb == o.get("class")):
                errors.append(f"{where}：fallback_for 要寫另一個存在的模型類別：{fb}")
    for name, tr in (pol.get("trials") or {}).items():
        for k in ("class", "baseline", "min_samples", "max_gap_pp"):
            if k not in tr:
                errors.append(f"trials.{name} 少了 {k}")
        for k in ("class", "baseline"):
            if tr.get(k) and tr[k] not in classes:
                errors.append(f"trials.{name}.{k} 的模型類別不存在：{tr[k]}")
    esc_edges = {}
    for i, e in enumerate(pol.get("escalation") or []):
        for k in ("from", "to"):
            raw = e.get(k)
            v = raw.get("class") if isinstance(raw, dict) else raw
            allowed_special = ("level", "higher", "stop") if k == "to" else ("level", "higher")
            if v not in classes and v not in allowed_special and v not in levels:
                errors.append(f"escalation 第 {i + 1} 條的 {k} 不認得：{v}")
            if isinstance(raw, dict) and "levels" in raw:
                for lv_name in raw.get("levels") or []:
                    if lv_name not in levels:
                        errors.append(f"escalation 第 {i + 1} 條的 {k}.levels 不認得：{lv_name}")
        if not e.get("once"):
            f_raw, t_raw = e.get("from"), e.get("to")
            fc = f_raw.get("class") if isinstance(f_raw, dict) else f_raw
            tc = t_raw.get("class") if isinstance(t_raw, dict) else t_raw
            f_th = f_raw.get("thinking") if isinstance(f_raw, dict) else None
            t_th = (t_raw.get("thinking") if isinstance(t_raw, dict) else None) or e.get("thinking")
            if fc in classes and tc in classes:
                src_ths = [f_th] if f_th in THINKING else [th for th in THINKING if th not in (classes[fc].get("forbid_thinking") or []) and THINKING.index(th) <= THINKING.index(classes[fc].get("max_thinking", "max"))]
                for sth in src_ths:
                    dth = sth if t_th == "same" else (t_th if t_th in THINKING else classes[tc].get("default_thinking", "medium"))
                    if (fc, sth) != (tc, dth):
                        esc_edges.setdefault((fc, sth), set()).add((tc, dth))
            elif fc in levels and tc in levels:
                for r_opt in (levels[fc].get("route") or []):
                    for t_opt in (levels[tc].get("route") or []):
                        if r_opt.get("class") in classes and t_opt.get("class") in classes:
                            u = (r_opt["class"], r_opt.get("thinking"))
                            v_node = (t_opt["class"], t_opt.get("thinking"))
                            if u != v_node:
                                esc_edges.setdefault(u, set()).add(v_node)
    visiting, visited = set(), set()

    def _has_cycle(node):
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for nxt in esc_edges.get(node, ()):
            if _has_cycle(nxt):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    if any(_has_cycle(n) for n in list(esc_edges)):
        errors.append("escalation 升級鏈出現無 once 限制的循環")
    if mine is not None:
        for inst, spec in (mine.get("instances") or {}).items():
            spec = spec or {}
            for cls in spec.get("classes") or []:
                if cls not in classes:
                    errors.append(f"個人層 instances.{inst}：模型類別不存在：{cls}")
                elif spec.get("driver") and classes[cls].get("driver") != spec["driver"]:
                    errors.append(f"個人層 instances.{inst}：{cls} 要用 {classes[cls]['driver']} 的實例，這個是 {spec['driver']}")
        opt = mine.get("opt_in_classes")
        if opt is not None:
            if not isinstance(opt, list):
                errors.append("個人層 opt_in_classes 要是模型類別清單，例如 [claude-fable]")
            else:
                for cls in opt:
                    if cls not in classes:
                        errors.append(f"個人層 opt_in_classes：模型類別不存在：{cls}")
                    elif not classes[cls].get("opt_in"):
                        errors.append(f"個人層 opt_in_classes：{cls} 不是選配類別，不用宣告")
        if "visibility" in mine and mine.get("visibility") not in VISIBILITY:
            errors.append(f"個人層 visibility 要是 {list(VISIBILITY)} 之一：{mine.get('visibility')}")
        overrides = mine.get("effort_overrides")
        if overrides is not None:
            if not isinstance(overrides, dict):
                errors.append("個人層 effort_overrides 要是對照表（{模型類別或級別: 思考程度}）")
            else:
                for k, th in overrides.items():
                    if k not in classes and k not in levels:
                        errors.append(f"個人層 effort_overrides 的鍵不是模型類別也不是級別：{k}")
                    elif th not in THINKING:
                        errors.append(f"個人層 effort_overrides.{k} 要是 {THINKING} 之一：{th}")
                    elif k in classes:
                        if THINKING.index(th) > THINKING.index(classes[k].get("max_thinking", "max")):
                            errors.append(f"個人層 effort_overrides.{k} 超過上限 {classes[k].get('max_thinking')}：{th}")
                        elif th in (classes[k].get("forbid_thinking") or []):
                            errors.append(f"個人層 effort_overrides.{k} 禁用 {th}")
        import account_pool
        for key, allowed in (("thinking_preference", account_pool.THINKING_PREFS),
                             ("on_exhausted", account_pool.ON_EXHAUSTED_MODES),
                             ("account_strategy", account_pool.ACCOUNT_STRATEGIES),
                             ("notify", account_pool.NOTIFY_MODES)):
            if key in mine and mine.get(key) not in allowed:
                errors.append(f"個人層 {key} 要是 {list(allowed)} 之一：{mine.get(key)}")
    return errors


def visibility(pol, mine=None):
    """這個使用者派給 Antigravity 時的偏好與對應管道：個人層的 visibility，沒寫用共用層的預設。"""
    vis = pol.get("visibility") or {}
    mode = (mine or {}).get("visibility") or vis.get("default") or "visible"
    spec = (vis.get("modes") or {}).get(mode) or {}
    return {"mode": mode, "source": "profile" if (mine or {}).get("visibility") else "default",
            "desc": spec.get("desc", ""), "channels": list(spec.get("channels") or []),
            "fallback": re.sub(r"(?<=[，。；：、（）])\s+", "", " ".join(str(spec.get("fallback", "")).split()))}


def opted_in(pol, mine, cls):
    """選配類別（opt_in: true，例如多數訂閱方案沒有的 Fable）：個人層 opt_in_classes 有列、
    或有實例的 classes 宣告它，才算這個人有；一般類別一律算有。"""
    if not pol["model_classes"][cls].get("opt_in"):
        return True
    mine = mine or {}
    if cls in (mine.get("opt_in_classes") or []):
        return True
    return any(cls in ((spec or {}).get("classes") or []) for spec in (mine.get("instances") or {}).values())


def instances_for(pol, mine, cls, agent="claude"):
    """這個模型類別可以用的實例，依序。目前的 agent 跟類別同一個供應商時，原生子代理（native）排第一；
    選配類別沒宣告的不算原生子代理（避免派給方案裡沒有的模型）。"""
    found = []
    if (pol["model_classes"][cls].get("driver") == AGENT_DRIVER.get(agent) and cls.startswith(("claude-",))
            and opted_in(pol, mine, cls)):
        found.append("native")
    for inst, spec in ((mine or {}).get("instances") or {}).items():
        if cls in ((spec or {}).get("classes") or []):
            found.append(inst)
    return found


def effective_thinking(pol, cls_name, base_thinking, level, kind, mine=None):
    """套用個人層 effort_overrides 與 thinking_preference（max_available / balanced / economy / custom）後的思考程度與原因。"""
    cls = pol["model_classes"][cls_name]
    forbid = set(cls.get("forbid_thinking") or [])
    top = cls.get("max_thinking", base_thinking)
    overrides = (mine or {}).get("effort_overrides")
    if isinstance(overrides, dict):
        for key in (f"{level}.{cls_name}", level, cls_name):
            ov = overrides.get(key)
            if ov in THINKING and ov not in forbid and THINKING.index(ov) <= THINKING.index(top):
                return (ov, f"effort_overrides: {key}") if ov != base_thinking else (ov, "")
    pref = (mine or {}).get("thinking_preference")
    if not pref or pref in ("balanced", "custom"):
        return base_thinking, ""
    if pref == "max_available":
        # 限定對 Antigravity 的 Gemini 模型拉到該模型能開的最高檔（Neon/Hydrogen xhigh；Carbon high）；
        # Claude 類別維持政策分級，絕不強制把 Opus / Fable 子任務拉到 max
        if cls.get("driver") == "antigravity" and str(cls.get("model", "")).startswith("gemini-") and top in THINKING and top not in forbid:
            if THINKING.index(top) > THINKING.index(base_thinking):
                return top, "thinking_preference: max_available"
        return base_thinking, ""
    if pref == "economy":
        # 只有定案（high/higher/verify/architecture 的 route）與第二意見維持高檔；其餘降一檔且絕不碰 forbid_thinking
        if level == "medium" or kind == "prework":
            idx = THINKING.index(base_thinking)
            while idx > 0 and THINKING[idx - 1] in forbid:
                idx -= 1
            if idx > 0 and THINKING[idx - 1] not in forbid:
                return THINKING[idx - 1], "thinking_preference: economy"
    return base_thinking, ""


def verified_pairs(state):
    """實測成功過的 (實例, 模型)：委派紀錄裡 verdict pass、沒有錯誤、沒有升級換類別的那幾行，加上能力矩陣 ok 的模型。
    選配類別（例如 Fable）宣告在某個實例、卻沒有這裡的紀錄時，show 標「未實測」並排到已實測的後面。"""
    import accounts
    rows, _ = read_log(log_path(state))
    out = set()
    for r in rows:
        if (r.get("verdict") == "pass" and not r.get("error_kind") and r.get("instance") and r.get("model")
                and r.get("final_class") in (None, r.get("class")) and r.get("model_ok") is not False):
            out.add((r["instance"], r["model"]))
    for iid, rec in (accounts.load_matrix(state) or {}).items():
        for m, v in ((rec or {}).get("models") or {}).items():
            if isinstance(v, dict) and v.get("ok"):
                out.add((iid, m))
    return out


def resolved(pol, mine, agent="claude", judge=None, model_note=None, claude_order=None, verified=None, usage=None):
    """每一級的選項，加上可以用的實例；沒有實例的標 skip。
    judge（accounts.annotate 給的）：(實例, 模型) → (能不能自動派, 原因)；不能派的實例移到 blocked 並附原因。
    model_note：模型被淘汰過濾時回原因（整個選項跳過）。
    claude_order：依額度策略排好的 Claude 實例優先順序（工作包邊界挑）。
    verified：verified_pairs 的結果；給了就把選配類別沒實測過的實例標 unverified、排到後面。
    usage：實例 → instance_usage 的結果；route 選項寫 usage_gate: below_threshold 的，已達門檻的實例移到 blocked。"""
    # 第二家：只算真的能派的實例（有 classes、不是只給手動）；登記了但只給手動的帳號不算有第二家
    configured_drivers = {(spec or {}).get("driver") for spec in ((mine or {}).get("instances") or {}).values()
                          if (spec or {}).get("driver") and (spec or {}).get("classes") and (spec or {}).get("usage_scope") != "manual_only"}
    if AGENT_DRIVER.get(agent):
        configured_drivers.add(AGENT_DRIVER[agent])

    def usable(cls_name):
        """這個類別在 judge 與模型淘汰過濾之後還剩的實例（判斷 fallback_for 的主選項是不是真的能用）。"""
        model = pol["model_classes"][cls_name]["model"]
        if model_note and model_note(model):
            return []
        got = instances_for(pol, mine, cls_name, agent)
        return [i for i in got if judge(i, model)[0]] if judge else got

    out = {}
    for level, lv in pol["levels"].items():
        tasks = [t for t, v in pol["tasks"].items() if v["level"] == level]
        rows = []
        for kind, items in (("prework", lv.get("prework") or []), ("route", lv.get("route") or []),
                            ("second_opinion", lv.get("second_opinion") or [])):
            for o in items:
                cls = pol["model_classes"][o["class"]]
                single_vendor_skip = kind == "second_opinion" and not (configured_drivers - {cls["driver"]})
                # fallback_for：主選項的類別這個人有、而且過了 judge 與淘汰過濾還能派（例如有 Fable），這個備援就不用
                superseded = o.get("fallback_for") if o.get("fallback_for") and usable(o["fallback_for"]) else None
                opt_in_missing = not opted_in(pol, mine, o["class"])
                inst, blocked = ([] if single_vendor_skip or superseded else instances_for(pol, mine, o["class"], agent)), []
                if claude_order and cls["driver"] == "claudeAgent" and inst:
                    rank = {iid: idx for idx, iid in enumerate(claude_order)}
                    head = [i for i in inst if i == "native"]
                    rest = [i for i in inst if i != "native"]
                    rest.sort(key=lambda i: (rank.get(i, 999), inst.index(i)))
                    inst = head + rest
                if judge and inst:
                    verdicts = [(i, *judge(i, cls["model"])) for i in inst]
                    inst = [i for i, ok, _ in verdicts if ok]
                    blocked = [{"instance": i, "why": why} for i, ok, why in verdicts if not ok]
                if o.get("usage_gate") == "below_threshold" and usage and inst:
                    over = [i for i in inst if (usage.get(i) or {}).get("over")]
                    blocked += [{"instance": i, "why": f"本週用量 {usage[i]['pct']:.0f}% 已達門檻 {usage[i]['threshold']}%（usage_signal）"}
                                for i in over]
                    inst = [i for i in inst if i not in over]
                unverified = []
                if verified is not None and cls.get("opt_in") and inst:
                    unverified = [i for i in inst if i != "native" and (i, cls["model"]) not in verified]
                    inst = [i for i in inst if i not in unverified] + unverified
                filtered = model_note(cls["model"]) if model_note else ""
                th, th_why = effective_thinking(pol, o["class"], o["thinking"], level, kind, mine)
                rows.append({"kind": kind, "class": o["class"], "model": cls["model"], "thinking": th,
                             "policy_thinking": o["thinking"], "thinking_name": "effort" if cls["driver"] == "claudeAgent" else "thought_level",
                             "thinking_why": th_why, "when": o.get("when"), "tasks": o.get("tasks"),
                             "instances": [] if filtered else inst, "blocked": blocked, "filtered": filtered,
                             "single_vendor_skip": single_vendor_skip, "superseded": superseded,
                             "opt_in_missing": opt_in_missing, "fallback_for": o.get("fallback_for"), "unverified": unverified,
                             "skip": bool(filtered) or single_vendor_skip or bool(superseded) or not inst,
                             "trial": o.get("trial"), "pending": o.get("pending"), "note": o.get("note"), "role": o.get("role")})
        out[level] = {"name": lv.get("name", level), "tasks": tasks, "options": rows}
    return out


VENDOR_NAMES = {"claudeAgent": "Claude", "antigravity": "Gemini（Antigravity）", "codex": "Codex"}


def burn_decision(pol, mine, cands, agent="claude", judge=None, model_note=None, verified=None):
    """第二意見看額度到期（政策 second_opinion_burn）：作者那一家有快到期的帳號、另一家沒有時，
    審那一家產出的第二意見改用同一家、不同模型、不同帳號。cands 是 account_pool.burn_candidates 的結果。
    回傳 {triggered, author_driver, reason, expiring, swaps: [{author_class, class, model, thinking, instances, unverified}]}。"""
    cfg = pol.get("second_opinion_burn") or {}
    if not cfg:
        return {"triggered": False, "reason": "政策沒有 second_opinion_burn", "swaps": []}
    hrs, pct = cfg.get("within_hours", 48), cfg.get("min_weekly_remaining_pct", 20)
    configured = {(spec or {}).get("driver") for spec in ((mine or {}).get("instances") or {}).values()
                  if (spec or {}).get("driver") and (spec or {}).get("classes") and (spec or {}).get("usage_scope") != "manual_only"}
    if AGENT_DRIVER.get(agent):
        configured.add(AGENT_DRIVER[agent])
    expiring = {d: lst for d, lst in (cands or {}).items() if lst and d in configured}
    base = {"triggered": False, "author_driver": None, "expiring": expiring, "swaps": []}
    if not expiring:
        return {**base, "reason": f"沒有可自動派的帳號距週重置 < {hrs} 小時且週剩 >= {pct}%，第二意見照原本的跨家審查"}
    if len(expiring) > 1:
        names = "、".join(VENDOR_NAMES.get(d, d) for d in expiring)
        return {**base, "reason": f"{names} 都有快到期的額度，維持原本的跨家審查"}
    drv, lst = next(iter(expiring.items()))
    others = configured - {drv}
    if not others:
        return {**base, "author_driver": drv, "reason": "只有一家模型，本來就沒有跨家第二意見"}
    burn_ids = [c["instance"] for c in lst]
    swaps = []
    for author_cls, rv in (cfg.get("same_vendor") or {}).items():
        a = pol["model_classes"].get(author_cls) or {}
        rc = (rv or {}).get("class")
        rcls = pol["model_classes"].get(rc) or {}
        if a.get("driver") != drv or rcls.get("driver") != drv or rc == author_cls:
            continue
        model = rcls["model"]
        if model_note and model_note(model):
            continue
        inst = instances_for(pol, mine, rc, agent)
        if judge:
            inst = [i for i in inst if judge(i, model)[0]]
        orig = list(inst)
        inst.sort(key=lambda i: (0, burn_ids.index(i)) if i in burn_ids else (1, orig.index(i)))
        unverified = ([i for i in inst if i != "native" and (i, model) not in verified]
                      if verified is not None and rcls.get("opt_in") else [])
        if unverified:
            inst = [i for i in inst if i not in unverified] + unverified
        if inst:
            swaps.append({"author_class": author_cls, "class": rc, "model": model, "thinking": rv.get("thinking"),
                          "thinking_name": "effort" if drv == "claudeAgent" else "thought_level",
                          "instances": inst, "unverified": unverified})
    vendor = VENDOR_NAMES.get(drv, drv)
    other_names = "、".join(VENDOR_NAMES.get(d, d) for d in sorted(others))
    why = "、".join(f"{c['instance']}（{c['why']}）" for c in lst)
    reason = (f"{vendor} 有帳號額度快作廢（距週重置 < {hrs} 小時且週剩 >= {pct}%，或使用者指定要燒）：{why}；"
              f"{other_names} 沒有快到期的額度")
    if not swaps:
        return {**base, "author_driver": drv,
                "reason": reason + "；但同一家找不到能派的不同模型審查者，維持原本的跨家審查"}
    return {**base, "triggered": True, "author_driver": drv, "swaps": swaps,
            "reason": reason + f" → 審 {vendor} 產出的第二意見改用同一家、不同模型、不同帳號（快到期的帳號排前面）"}


def burn_lines(burn):
    """show 的「第二意見改判」段落。"""
    if not burn:
        return []
    lines = ["\n第二意見改判（額度到期，政策 second_opinion_burn）：",
             f"  {'改判' if burn['triggered'] else '不改判'}：{burn['reason']}"]
    for sw in burn.get("swaps") or []:
        unv = f"（未實測：{'、'.join(sw['unverified'])}）" if sw.get("unverified") else ""
        lines.append(f"  作者 {sw['author_class']} → 審查 {sw['class']}（{sw['model']}）{sw['thinking_name']} {sw['thinking']}；"
                     f"實例：{'、'.join(sw['instances'])}{unv}")
    if burn["triggered"]:
        lines.append("  審查者不能用作者那個帳號、也不能跟作者同一個模型；只剩作者那個帳號時維持原本的跨家第二意見。")
    return lines


# ---------- 委派紀錄 ----------

NOISE_PROJECT_RE = re.compile(
    r"(?i)(?:^\d{4}-\d{2}-\d{2}(?:[-_]|$)|[-_][0-9a-f]{7,}$|^[0-9a-f]{7,}$|^omnikit-)"
)


def looks_like_noise_project(name):
    """project 名稱看起來像日期、hash、worktree 或 skill 子目錄名時回傳 True（KIT-X-06）。"""
    return bool(name and NOISE_PROJECT_RE.search(str(name).strip()))


def log_path(state):
    return Path(state) / "dispatch" / "log.jsonl"


def annotations_path(state):
    return Path(state) / "dispatch" / "annotations.jsonl"


def record_fingerprint(row):
    """紀錄指紋鍵：ts|class|instance|task，供 annotations.jsonl 非破壞性覆寫對齊。"""
    if not isinstance(row, dict):
        return ""
    return f"{row.get('ts') or ''}|{row.get('class') or ''}|{row.get('instance') or ''}|{row.get('task') or ''}"


def read_annotations(state):
    """讀取可選覆寫檔 ~/.omnikit/dispatch/annotations.jsonl（或直接傳入 .jsonl 路徑），回傳 {指紋鍵: 覆寫欄位 dict}。"""
    if state is None:
        return {}
    p = Path(state)
    if p.suffix.lower() != ".jsonl":
        p = annotations_path(p)
    if not p.is_file():
        return {}
    meta_keys = {"key", "fingerprint", "by", "author", "updated_at", "reason", "comment"}
    id_keys = {"ts", "class", "instance", "task"}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        explicit_key = obj.get("key") or obj.get("fingerprint")
        key = str(explicit_key) if explicit_key else record_fingerprint(obj)
        if not key or key == "|||":
            continue
        if isinstance(obj.get("override"), dict):
            ov = dict(obj["override"])
        elif isinstance(obj.get("fields"), dict):
            ov = dict(obj["fields"])
        else:
            skip = meta_keys | (set() if explicit_key else id_keys)
            ov = {k: v for k, v in obj.items() if k not in skip}
        if ov:
            out.setdefault(key, {}).update(ov)
    return out


def project_name(cwd=None):
    """專案名稱：優先用 git common-dir 取主 repo 資料夾名（worktree 也能回到主專案名）；
    次用 --show-toplevel；不在 repo 裡就用目前資料夾名。只記名稱，不記完整路徑。"""
    cwd = Path(cwd or os.getcwd())
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), "-c", "core.quotepath=false", "rev-parse", "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            raw = Path(r.stdout.strip())
            common = raw.resolve() if raw.is_absolute() else (cwd / raw).resolve()
            if common.name == ".git":
                return common.parent.name
            if common.name.endswith(".git") and len(common.name) > 4:
                return common.name[:-4]
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), "-c", "core.quotepath=false", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).name
    except (OSError, subprocess.TimeoutExpired):
        pass
    return cwd.name


def _clamp_thinking_for_class(cls_spec, thinking):
    if not isinstance(cls_spec, dict) or thinking not in THINKING:
        return thinking
    top = cls_spec.get("max_thinking", "max")
    forbid = set(cls_spec.get("forbid_thinking") or [])
    if top in THINKING and THINKING.index(thinking) > THINKING.index(top):
        return cls_spec.get("default_thinking") or top
    if thinking in forbid:
        return cls_spec.get("default_thinking") or thinking
    return thinking


def make_record(pol, args, version, profile, project, now=None):
    """命令列參數 → 一筆 Schema v2 紀錄；不合政策或違反源頭防呆的直接失敗（SystemExit），不寫半筆。"""
    tasks, classes = pol["tasks"], pol["model_classes"]
    if args.task not in tasks:
        raise SystemExit(f"任務類型不存在：{args.task}，可選：{'、'.join(tasks)}")
    level = getattr(args, "level", None) or tasks[args.task]["level"]
    if level not in pol["levels"]:
        raise SystemExit(f"級別不存在：{level}")
    for k in ("cls", "final_class"):
        v = getattr(args, k, None)
        if v and v not in classes:
            raise SystemExit(f"模型類別不存在：{v}，可選：{'、'.join(classes)}")
    if args.thinking not in THINKING:
        raise SystemExit(f"思考程度要是 {THINKING} 之一：{args.thinking}")
    top = classes[args.cls].get("max_thinking", "max")
    if THINKING.index(args.thinking) > THINKING.index(top):
        raise SystemExit(f"{args.cls} 的思考程度最高 {top}，寫了 {args.thinking}")
    if args.verdict not in VERDICTS:
        raise SystemExit(f"驗收結論要是 {VERDICTS} 之一：{args.verdict}")
    if getattr(args, "escalations", 0) and not getattr(args, "final_class", None):
        raise SystemExit("有升級（--escalations）就要寫最後用哪個類別（--final-class）")

    inferred = []

    origin = getattr(args, "origin", None)
    if origin is None:
        origin = "field"
    elif origin not in ORIGINS:
        raise SystemExit(f"來源（--origin）要是 {ORIGINS} 之一：{origin}")

    role = getattr(args, "role", None)
    if role is None:
        role = "reviewer" if args.task == "verify" else "author"
        inferred.append("role")
    elif role not in ROLES:
        raise SystemExit(f"角色（--role）要是 {ROLES} 之一：{role}")

    error_kind = getattr(args, "error", None)
    error_text = getattr(args, "error_text", None)
    note = getattr(args, "note", None)
    if error_kind or error_text:
        import account_pool
        if error_kind and error_kind not in account_pool.ERROR_KINDS:
            raise SystemExit(f"錯誤種類不存在：{error_kind}，可選：{'、'.join(account_pool.ERROR_KINDS)}")
        if not error_kind and error_text:
            c = account_pool.classify_error(error_text, model=classes[args.cls]["model"], now=now)
            error_kind = c["kind"]
            if not note:
                note = c["summary"]

    infra_arg = getattr(args, "infra", None)
    if infra_arg is not None:
        if infra_arg not in INFRA_ISSUES:
            raise SystemExit(f"基礎設施問題（--infra）要是 {INFRA_ISSUES} 之一：{infra_arg}")
        infra_issue = infra_arg
    elif error_kind:
        infra_issue = ERROR_TO_INFRA.get(error_kind)
        if infra_issue is not None:
            inferred.append("infra_issue")
    else:
        infra_issue = None

    scope_arg = getattr(args, "scope", None)
    scope_capped = bool(getattr(args, "scope_capped", False))
    if scope_capped:
        if scope_arg is not None and scope_arg != "capped_by_caller":
            raise SystemExit(f"--scope-capped 與 --scope {scope_arg} 衝突")
        scope = "capped_by_caller"
    elif scope_arg is not None:
        if scope_arg not in SCOPES:
            raise SystemExit(f"範圍（--scope）要是 {SCOPES} 之一：{scope_arg}")
        scope = scope_arg
    else:
        scope = "complete"

    unverified = bool(getattr(args, "unverified", False))

    defect_kind = getattr(args, "defect", None)
    if defect_kind is not None and defect_kind not in DEFECT_KINDS:
        raise SystemExit(f"缺陷類別（--defect）要是 {DEFECT_KINDS} 之一：{defect_kind}")

    subj_arg = getattr(args, "subject_pass", None)
    if subj_arg not in (None, "yes", "no", "na"):
        raise SystemExit(f"--subject-pass 要是 yes|no|na 之一：{subj_arg}")
    if subj_arg in ("yes", "no") and role not in ("reviewer", "judge"):
        raise SystemExit("--subject-pass 僅適用於 reviewer 或 judge 角色")

    model_ok_arg = getattr(args, "model_ok", None)
    if model_ok_arg not in (None, "yes", "no", "na"):
        raise SystemExit(f"--model-ok 要是 yes|no|na 之一：{model_ok_arg}")

    # 源頭寫入防呆
    if model_ok_arg == "no" and not defect_kind:
        raise SystemExit("顯式指定 --model-ok no 時必填 --defect（缺陷類別）")
    if model_ok_arg in ("yes", "na") and defect_kind:
        raise SystemExit(f"顯式指定 --model-ok {model_ok_arg} 時不可同時指定 --defect")
    if role == "reviewer" and args.verdict == "fail" and subj_arg is None and infra_issue is None:
        raise SystemExit("審查者抓到真問題請記 --verdict pass --subject-pass no，環境故障請帶 --infra 或 --error")

    r_inf_arg = getattr(args, "retries_infra", None)
    r_qual_arg = getattr(args, "retries_quality", None)
    r_legacy = getattr(args, "retries", 0) or 0
    if r_legacy < 0 or (r_inf_arg is not None and r_inf_arg < 0) or (r_qual_arg is not None and r_qual_arg < 0):
        raise SystemExit("重跑次數不可為負數")
    if r_inf_arg is not None or r_qual_arg is not None:
        retries_infra = int(r_inf_arg or 0)
        retries_quality = int(r_qual_arg or 0)
        split_sum = retries_infra + retries_quality
        retries = int(r_legacy) if r_legacy > split_sum else split_sum
    else:
        retries = int(r_legacy)
        if retries > 0:
            if infra_issue is not None and defect_kind is None:
                retries_infra, retries_quality = retries, 0
                inferred.append("retries_infra")
            else:
                retries_infra, retries_quality = 0, retries
                inferred.append("retries_quality")
        else:
            retries_infra, retries_quality = 0, 0

    escalations = int(getattr(args, "escalations", 0) or 0)
    first_arg = getattr(args, "first_pass", None)
    first = {"yes": True, "no": False, None: None}[first_arg]
    if first is None:  # 沒寫就從結論推：一次就過、沒有重跑與升級才算
        first = args.verdict == "pass" and not retries and not escalations

    final_cls = getattr(args, "final_class", None) or args.cls
    model = classes[args.cls]["model"]
    if getattr(args, "final_class", None) and args.final_class != args.cls:
        judged_model = classes[args.final_class]["model"]
        judged_thinking = _clamp_thinking_for_class(classes[args.final_class], args.thinking)
        inferred.extend(["judged_model", "judged_thinking"])
    else:
        judged_model = model
        judged_thinking = args.thinking

    if subj_arg is not None:
        subject_pass = {"yes": True, "no": False, "na": None}[subj_arg]
    elif role in ("reviewer", "judge"):
        if args.verdict == "pass" and first and not unverified and infra_issue is None:
            subject_pass = True
            inferred.append("subject_pass")
        else:
            subject_pass = None
    else:
        subject_pass = None

    if model_ok_arg is not None:
        model_ok = {"yes": True, "no": False, "na": None}[model_ok_arg]
    else:
        inferred.append("model_ok")
        if args.verdict == "skipped" or unverified:
            model_ok = None
        elif defect_kind is not None:
            model_ok = False
        elif infra_issue is not None and not first:
            model_ok = None
        elif role in ("reviewer", "judge") and subject_pass is False:
            model_ok = True
        elif scope == "capped_by_caller" and args.verdict == "partial":
            model_ok = True
        else:
            model_ok = bool(first)

    dur_raw = getattr(args, "duration_sec", None)
    if dur_raw is not None:
        duration_sec = float(dur_raw)
        if duration_sec < 0 or math.isnan(duration_sec) or math.isinf(duration_sec):
            raise SystemExit(f"--duration-sec 必須是非負實數：{dur_raw}")
    else:
        duration_sec = None

    work_id = getattr(args, "work", None) or None
    eval_raw = getattr(args, "eval_ref_json", None)
    if eval_raw is not None:
        if isinstance(eval_raw, dict):
            eval_ref = eval_raw
        else:
            try:
                eval_ref = json.loads(eval_raw)
            except ValueError as e:
                raise SystemExit(f"--eval-ref-json JSON 解析失敗：{e}") from e
            if not isinstance(eval_ref, dict):
                raise SystemExit("--eval-ref-json 必須是 JSON 物件（dict）")
    else:
        eval_ref = None

    channel = getattr(args, "channel", "native") or "native"
    instance = getattr(args, "instance", None) or ("native" if channel == "native" else None)

    return {
        "ts": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "project": getattr(args, "project", None) or project,
        "task": args.task,
        "level": level,
        "channel": channel,
        "instance": instance,
        "class": args.cls,
        "model": model,
        "thinking": args.thinking,
        "first_pass": first,
        "retries": retries,
        "escalations": escalations,
        "final_class": final_cls,
        "verdict": args.verdict,
        "error_kind": error_kind,
        "rules_version": version,
        "profile": profile,
        "control": bool(getattr(args, "control", False)),
        "note": note,
        "schema_version": SCHEMA_VERSION,
        "origin": origin,
        "role": role,
        "infra_issue": infra_issue,
        "scope": scope,
        "unverified": unverified,
        "subject_pass": subject_pass,
        "model_ok": model_ok,
        "defect_kind": defect_kind,
        "retries_infra": retries_infra,
        "retries_quality": retries_quality,
        "judged_model": judged_model,
        "judged_thinking": judged_thinking,
        "duration_sec": duration_sec,
        "work_id": work_id,
        "eval_ref": eval_ref,
        "inferred": inferred,
    }


def append(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_log(path):
    rows, bad = [], 0
    if Path(path).is_file():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    return rows, bad


# ---------- 非破壞性讀取期投影（v1 回溯瀑布流 ＋ 複合缺陷覆寫保護） ----------

_ZERO_FALSE_POSITIVE_RE = re.compile(r"(?:0\s*誤報|零誤報|無誤報|0\s*缺漏|0\s*佔位符錯|0\s*missing)")
DEFECT_EVIDENCE_RE = re.compile(
    r"漏掉官方|結論不可靠|數字對不上|經核對不成立|誤報|寫錯|未對官方頁|"
    r"把文件當成已實作|引文有對不上|宣稱沒改檔|夾帶自行添加|抽測抓到.*失敗|"
    r"查無原文|報告本身\s*\d+\s*處(?:小)?錯"
)
_INFRA_NOTE_PATTERNS = (
    ("cancelled", re.compile(r"提前取消|使用者取消|手動取消")),
    ("model_unavailable", re.compile(r"無此模型|未開通.*credits|無\s*Fable|model_forbidden", re.I)),
    ("rate_limit", re.compile(r"\b429\b|rate[-_ ]?limit", re.I)),
    ("quota", re.compile(
        r"額度|配額|限額|quota|5h\s*(?:上限|限額|中斷|桶)|"
        r"撞\s*(?:02:00|2am|上限|Ryan|Kai|個人|Gemini|週)|週上限|冷卻至|"
        r"前半\s*(?:Kai|Ryan).*收尾\s*(?:antigravity|claude)",
        re.I,
    )),
    ("harness_timeout", re.compile(r"15\s*分鐘無輸出|sent nothing for 15 minutes", re.I)),
    ("harness_permission", re.compile(r"無頭權限擋|權限核准|守工作目錄邊界|觸發審批")),
    ("harness_tooling", re.compile(r"靜默結束|Git Bash\s*路徑|provider\s*錯誤|斷線|ECONNREFUSED|被中斷.*換手", re.I)),
)
_SCOPE_CAP_RE = re.compile(
    r"(?:跑滿|查滿|到|第)?\s*\d+\s*組(?:上限|未飽和|未收斂|完整|到頂)|\d+-group\s+cap|照\s*★\s*停法停|長尾未飽和",
    re.I,
)
_UNVERIFIED_RE = re.compile(r"內容待主控查證|待主控查證")
_VERIFY_CATCH_RE = re.compile(
    r"抓到|抓出|初審|首輪\s*FAIL|第一輪\s*FAIL|初驗\s*(?:FAIL|PASS)|修後窄範圍重驗|[DB]\d+\s*[-–]\s*[DB]?\d+"
)
_NOTE_THINKING_RE = re.compile(r"(?:Opus(?:\s*5\.5)?|Fable(?:\s*5\.2)?|Carbon|Neon|Hydrogen)\s+(low|medium|high|xhigh|max)\b", re.I)


def _infer_defect_kind(clean_note):
    if "宣稱沒改檔" in clean_note:
        return "false_claim"
    if "夾帶自行添加" in clean_note:
        return "overreach"
    if "漏掉官方" in clean_note or "漏看後續決定" in clean_note:
        return "missed_requirement"
    if re.search(r"抽測抓到.*失敗", clean_note):
        return "unfinished"
    if DEFECT_EVIDENCE_RE.search(clean_note):
        return "wrong_fact"
    return "other"


def _derive_attribution(proj):
    """依投影後的正交欄位決定一致的 failure_attribution。"""
    verdict = proj.get("verdict")
    infra = proj.get("infra_issue")
    scope = proj.get("scope")
    model_ok = proj.get("model_ok")
    if model_ok is False:
        if infra is not None or scope == "capped_by_caller" or "compound_defect" in (proj.get("inferred") or []):
            return "compound_defect"
        return "model_defect"
    if verdict == "skipped":
        if infra in QUOTA_INFRA:
            return "infra_quota"
        if infra in HARNESS_INFRA:
            return "infra_harness"
        return "skipped"
    if proj.get("unverified"):
        return "unverified"
    if proj.get("role") in ("reviewer", "judge") and proj.get("subject_pass") is False and model_ok is True:
        return "verify_subject_fail"
    if infra is not None and model_ok is None:
        return "infra_quota" if infra in QUOTA_INFRA else "infra_harness"
    if scope == "capped_by_caller" and model_ok is True and (verdict == "partial" or not proj.get("first_pass", True)):
        return "scope_cap_partial"
    return None


def _resolve_judged_pair(row, pol=None):
    cls = row.get("class")
    final_cls = row.get("final_class") or cls
    raw_model = row.get("model")
    raw_th = row.get("thinking")
    classes = (pol or {}).get("model_classes") or {}
    if not final_cls or final_cls == cls:
        jm = raw_model or (classes.get(cls) or {}).get("model") or LEGACY_CLASS_MODELS.get(cls) or cls
        return jm, raw_th, False
    t_spec = classes.get(final_cls) or {}
    jm = t_spec.get("model") or LEGACY_CLASS_MODELS.get(final_cls) or raw_model or final_cls
    note = str(row.get("note") or "")
    m_th = _NOTE_THINKING_RE.search(note)
    if m_th:
        jt = m_th.group(1).lower()
    else:
        jt = _clamp_thinking_for_class(t_spec, raw_th) if t_spec else raw_th
    return jm, jt, True


def project_record(row, annotations=None, pol=None):
    """非破壞性讀取期投影：不修改傳入的 row、不改寫 log.jsonl。
    v1 紀錄（無 schema_version）透過確定性瀑布流與複合缺陷覆寫保護（Defect-Override Guard）投影為 v2 結構；
    若有 annotations（dict: key -> override）命中紀錄指紋鍵則最後覆寫。"""
    out = dict(row)
    fp_key = record_fingerprint(out)

    if out.get("schema_version") and int(out["schema_version"]) >= 2:
        inferred = list(out.get("inferred") or [])
        out.setdefault("origin", "field")
        out.setdefault("role", "reviewer" if out.get("task") == "verify" else "author")
        out.setdefault("infra_issue", ERROR_TO_INFRA.get(out.get("error_kind")) if out.get("error_kind") else None)
        out.setdefault("scope", "complete")
        out.setdefault("unverified", False)
        out.setdefault("subject_pass", None)
        out.setdefault("defect_kind", None)
        out.setdefault("retries_infra", 0)
        out.setdefault("retries_quality", 0)
        jm, jt, _ = _resolve_judged_pair(out, pol)
        out.setdefault("judged_model", jm)
        out.setdefault("judged_thinking", jt)
        out.setdefault("duration_sec", None)
        out.setdefault("work_id", None)
        out.setdefault("eval_ref", None)
        out["inferred"] = inferred
        if "failure_attribution" not in out:
            out["failure_attribution"] = _derive_attribution(out)
    else:
        inferred = ["v1_backfill"]
        verdict = out.get("verdict")
        task = out.get("task")
        retries = int(out.get("retries") or 0)
        escalations = int(out.get("escalations") or 0)
        if isinstance(out.get("first_pass"), bool):
            first_pass = out["first_pass"]
        else:
            first_pass = verdict == "pass" and not retries and not escalations
            out["first_pass"] = first_pass

        origin = "field"
        role = "reviewer" if task == "verify" else "author"
        inferred.extend(["origin", "role"])

        note = str(out.get("note") or "")
        clean_note = _ZERO_FALSE_POSITIVE_RE.sub("", note)

        error_kind = out.get("error_kind")
        infra_issue = ERROR_TO_INFRA.get(error_kind) if error_kind else None
        if infra_issue is None and note:
            for kind, pat in _INFRA_NOTE_PATTERNS:
                if pat.search(note):
                    infra_issue = kind
                    break
        if infra_issue is not None:
            inferred.append("infra_issue")

        scope = "capped_by_caller" if (note and _SCOPE_CAP_RE.search(note)) else "complete"
        if scope != "complete":
            inferred.append("scope")

        unverified = bool(note and _UNVERIFIED_RE.search(note) and verdict in ("partial", "skipped"))
        if unverified:
            inferred.append("unverified")

        is_verify_catch = bool(
            role in ("reviewer", "judge")
            and (verdict in ("fail", "partial") or retries > 0)
            and infra_issue is None
            and note
            and _VERIFY_CATCH_RE.search(note)
        )
        has_defect_evidence = bool(clean_note and DEFECT_EVIDENCE_RE.search(clean_note) and not is_verify_catch)

        subject_pass = None
        defect_kind = None
        retries_infra = 0
        retries_quality = 0

        # 確定性優先序瀑布流 ＋ 複合缺陷覆寫保護（Defect-Override Guard）
        if first_pass and verdict == "pass":
            model_ok = True
            if role in ("reviewer", "judge"):
                subject_pass = True
                inferred.append("subject_pass")
            failure_attribution = None
        elif first_pass and verdict == "partial":
            if has_defect_evidence:
                model_ok = False
                defect_kind = _infer_defect_kind(clean_note)
                retries_quality = retries
                if infra_issue is not None or scope == "capped_by_caller":
                    failure_attribution = "compound_defect"
                    inferred.append("compound_defect")
                else:
                    failure_attribution = "model_defect"
                inferred.append("defect_kind")
            else:
                model_ok = True
                failure_attribution = "scope_cap_partial" if scope == "capped_by_caller" else None
        elif verdict == "skipped":
            if has_defect_evidence:
                model_ok = False
                defect_kind = _infer_defect_kind(clean_note)
                if infra_issue is not None or scope == "capped_by_caller":
                    failure_attribution = "compound_defect"
                    inferred.append("compound_defect")
                else:
                    failure_attribution = "model_defect"
                inferred.append("defect_kind")
            else:
                model_ok = None
                retries_infra = retries if infra_issue is not None else 0
                if infra_issue in QUOTA_INFRA:
                    failure_attribution = "infra_quota"
                elif infra_issue in HARNESS_INFRA:
                    failure_attribution = "infra_harness"
                else:
                    failure_attribution = "skipped"
        elif has_defect_evidence:
            # Defect-Override Guard：即使同筆撞額度、逾時或 12/15 組上限，真實模型缺陷絕不洗白！
            model_ok = False
            defect_kind = _infer_defect_kind(clean_note)
            if infra_issue is not None:
                retries_infra = retries
            else:
                retries_quality = retries
            if infra_issue is not None or scope == "capped_by_caller":
                failure_attribution = "compound_defect"
                inferred.append("compound_defect")
            else:
                failure_attribution = "model_defect"
            inferred.append("defect_kind")
        elif unverified:
            model_ok = None
            failure_attribution = "unverified"
        elif is_verify_catch:
            subject_pass = False
            model_ok = True
            retries_quality = 0
            failure_attribution = "verify_subject_fail"
            inferred.append("subject_pass")
        elif infra_issue is not None:
            model_ok = None
            retries_infra = retries
            failure_attribution = "infra_quota" if infra_issue in QUOTA_INFRA else "infra_harness"
        elif scope == "capped_by_caller":
            model_ok = True
            retries_quality = 0
            failure_attribution = "scope_cap_partial"
        else:
            model_ok = False
            defect_kind = "other"
            retries_quality = retries
            failure_attribution = "model_defect"
            inferred.extend(["defect_kind", "fallback_non_first_pass"])

        inferred.append("model_ok")
        jm, jt, changed_jm = _resolve_judged_pair(out, pol)
        if changed_jm:
            inferred.extend(["judged_model", "judged_thinking"])

        out.update({
            "schema_version": SCHEMA_VERSION,
            "raw_schema_version": 1,
            "origin": origin,
            "role": role,
            "infra_issue": infra_issue,
            "scope": scope,
            "unverified": unverified,
            "subject_pass": subject_pass,
            "model_ok": model_ok,
            "defect_kind": defect_kind,
            "retries_infra": retries_infra,
            "retries_quality": retries_quality,
            "judged_model": jm,
            "judged_thinking": jt,
            "duration_sec": out.get("duration_sec"),
            "work_id": out.get("work_id"),
            "eval_ref": out.get("eval_ref"),
            "failure_attribution": failure_attribution,
            "inferred": inferred,
        })

    if annotations and fp_key in annotations:
        ov = annotations[fp_key]
        if isinstance(ov, dict) and ov:
            out.update(ov)
            inf = list(out.get("inferred") or [])
            if "annotation" not in inf:
                inf.append("annotation")
            out["inferred"] = inf
            if "failure_attribution" not in ov:
                out["failure_attribution"] = _derive_attribution(out)

    return out


# ---------- 統計、Wilson 信賴區間與回溯對帳 ----------

def wilson_ci(k, n, z=1.96):
    """純標準庫計算 Wilson score 信賴區間，回傳 [lo, hi]（0..1 浮點數）。"""
    if n <= 0:
        return [0.0, 0.0]
    k = max(0, min(int(k), int(n)))
    n = float(n)
    p = k / n
    z2 = float(z) * float(z)
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (float(z) / denom) * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))
    return [round(max(0.0, min(1.0, center - half)), 4), round(max(0.0, min(1.0, center + half)), 4)]


def rate(rows):
    return (sum(1 for r in rows if r.get("first_pass")) / len(rows)) if rows else None


def stats(pol, rows, annotations=None):
    """雙視圖統計：保留舊版依 (level, class) 的原始 table 相容舊呼叫端，
    並新增依 (level, judged_model, judged_thinking) 的去噪 clean_table、infra_summary、verify_summary、attribution_counts；
    trials 改以去噪 model_ok（origin=='field' 且 model_ok is not None）判定，並附 raw_trial_rate 與 wilson_ci。"""
    judged = [r for r in rows if r.get("verdict") != "skipped"]
    groups = {}
    for r in judged:
        groups.setdefault((r.get("level"), r.get("class")), []).append(r)
    table = [{"level": lv, "class": c, "n": len(g), "first_pass_rate": rate(g),
              "escalated": sum(1 for r in g if r.get("escalations"))} for (lv, c), g in sorted(groups.items(), key=str)]

    projected = [project_record(r, annotations=annotations, pol=pol) for r in rows]

    # 1. 去噪模型良率表：依 (level, judged_model, judged_thinking) 分組，只計 origin == "field" 且 model_ok is not None
    clean_field = [p for p in projected if p.get("origin") == "field" and p.get("model_ok") is not None]
    c_groups = {}
    for p in clean_field:
        key = (p.get("level"), p.get("judged_model") or p.get("model"), p.get("judged_thinking") or p.get("thinking"))
        c_groups.setdefault(key, []).append(p)
    clean_table = []
    for (lv, jm, jt), g in sorted(c_groups.items(), key=lambda kv: tuple(str(x or "") for x in kv[0])):
        n = len(g)
        ok_n = sum(1 for p in g if p.get("model_ok") is True)
        ci = wilson_ci(ok_n, n)
        durs = [float(p["duration_sec"]) for p in g if isinstance(p.get("duration_sec"), (int, float))]
        clean_table.append({
            "level": lv,
            "model": jm,
            "judged_model": jm,
            "thinking": jt,
            "judged_thinking": jt,
            "n": n,
            "ok": ok_n,
            "model_ok_rate": ok_n / n if n else None,
            "wilson_ci": ci,
            "low_sample": n < 20,
            "ceiling_warn": bool(n >= 20 and ci[0] > 0.85),
            "median_duration_sec": round(statistics.median(durs), 1) if durs else None,
        })

    # 2. 基礎設施損耗彙總：依 (instance, channel) 分組
    i_groups = {}
    for p in projected:
        ikey = (p.get("instance") or "unknown", p.get("channel") or "unknown")
        i_groups.setdefault(ikey, []).append(p)
    infra_summary = []
    for (inst, ch), g in sorted(i_groups.items(), key=str):
        ic = sum(1 for p in g if p.get("infra_issue") is not None)
        by_issue = {}
        for p in g:
            iss = p.get("infra_issue")
            if iss:
                by_issue[iss] = by_issue.get(iss, 0) + 1
        infra_summary.append({
            "instance": inst,
            "channel": ch,
            "total": len(g),
            "infra_count": ic,
            "infra_rate": round(ic / len(g), 4) if g else 0.0,
            "issues": by_issue,
        })

    # 3. 審查抓蟲率統計
    rev_rows = [p for p in projected if p.get("origin") == "field" and p.get("role") == "reviewer"]
    rev_eval = [p for p in rev_rows if p.get("subject_pass") is not None]
    rev_caught = sum(1 for p in rev_eval if p.get("subject_pass") is False)
    verify_summary = {
        "reviewer_total": len(rev_rows),
        "evaluated_n": len(rev_eval),
        "caught_n": rev_caught,
        "catch_rate": round(rev_caught / len(rev_eval), 4) if rev_eval else None,
        "wilson_ci": wilson_ci(rev_caught, len(rev_eval)) if rev_eval else [0.0, 0.0],
        "reviewer_model_ok_n": sum(1 for p in rev_rows if p.get("model_ok") is True),
    }

    # 4. 歸因類別計數
    attribution_counts = {}
    for p in projected:
        attr = p.get("failure_attribution") or "clean_pass"
        attribution_counts[attr] = attribution_counts.get(attr, 0) + 1

    # 5. 試行判定：改以去噪 model_ok 為基準，附 raw_trial_rate 與 wilson_ci
    trials = {}
    for name, tr in (pol.get("trials") or {}).items():
        clean_mine = [p for p in clean_field if p.get("class") == tr["class"]]
        raw_mine = [r for r in judged if r.get("class") == tr["class"]]
        levels = sorted({p.get("level") for p in (clean_mine or raw_mine)}, key=str)
        per = []
        for lv in levels:
            a = [p for p in clean_mine if p.get("level") == lv]
            b = [p for p in clean_field if p.get("class") == tr["baseline"] and p.get("level") == lv]
            raw_a = [r for r in raw_mine if r.get("level") == lv]
            raw_b = [r for r in judged if r.get("class") == tr["baseline"] and r.get("level") == lv]
            ok_a = sum(1 for p in a if p.get("model_ok") is True)
            ok_b = sum(1 for p in b if p.get("model_ok") is True)
            ra = (ok_a / len(a)) if a else None
            rb = (ok_b / len(b)) if b else None
            ci_a = wilson_ci(ok_a, len(a))
            ci_b = wilson_ci(ok_b, len(b))
            gap = None if ra is None or rb is None else round((rb - ra) * 100, 1)
            if len(a) < tr["min_samples"]:
                verdict = f"樣本不足：{tr['class']} 有 {len(a)} 筆，要 {tr['min_samples']} 筆"
            elif len(b) < tr.get("min_baseline", 1):
                verdict = f"基準不足：{tr['baseline']} 在這一級有 {len(b)} 筆，要 {tr.get('min_baseline', 1)} 筆（見 trials.{name}.note）"
            elif gap >= tr["max_gap_pp"]:
                verdict = f"退回：{tr['class']} 比 {tr['baseline']} 低 {gap} 個百分點（門檻 {tr['max_gap_pp']}）"
            else:
                verdict = f"繼續試行：差距 {gap} 個百分點，低於門檻 {tr['max_gap_pp']}"
            per.append({
                "level": lv,
                "trial_n": len(a),
                "trial_rate": ra,
                "raw_trial_n": len(raw_a),
                "raw_trial_rate": rate(raw_a),
                "wilson_ci": ci_a,
                "baseline_n": len(b),
                "baseline_rate": rb,
                "raw_baseline_rate": rate(raw_b),
                "baseline_wilson_ci": ci_b,
                "gap_pp": gap,
                "verdict": verdict,
                "revert": verdict.startswith("退回"),
            })
        trials[name] = per or [{
            "verdict": f"樣本不足：{tr['class']} 還沒有紀錄",
            "revert": False,
            "raw_trial_rate": None,
            "wilson_ci": [0.0, 0.0],
        }]

    return {
        "total": len(rows),
        "judged": len(judged),
        "clean_judged": len(clean_field),
        "table": table,
        "clean_table": clean_table,
        "infra_summary": infra_summary,
        "verify_summary": verify_summary,
        "attribution_counts": attribution_counts,
        "trials": trials,
    }


def backfill_audit(path, annotations=None, pol=None, limit=30):
    """唯讀對帳：計算原 log.jsonl SHA-256 並執行讀取期投影，彙總歸因分布與前 limit 筆真模型缺陷／複合缺陷。"""
    p = Path(path)
    before_sha = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    rows, bad = read_log(p)
    attribution_counts = {}
    defects = []
    v1_count, v2_count, annotated_count = 0, 0, 0
    for idx, r in enumerate(rows, 1):
        if r.get("schema_version") and int(r["schema_version"]) >= 2:
            v2_count += 1
        else:
            v1_count += 1
        proj = project_record(r, annotations=annotations, pol=pol)
        if "annotation" in (proj.get("inferred") or []):
            annotated_count += 1
        attr = proj.get("failure_attribution") or "clean_pass"
        attribution_counts[attr] = attribution_counts.get(attr, 0) + 1
        if proj.get("model_ok") is False or attr in ("model_defect", "compound_defect"):
            defects.append({
                "index": idx,
                "ts": proj.get("ts"),
                "task": proj.get("task"),
                "level": proj.get("level"),
                "class": proj.get("class"),
                "judged_model": proj.get("judged_model"),
                "judged_thinking": proj.get("judged_thinking"),
                "verdict": proj.get("verdict"),
                "failure_attribution": attr,
                "defect_kind": proj.get("defect_kind"),
                "infra_issue": proj.get("infra_issue"),
                "scope": proj.get("scope"),
                "note": proj.get("note"),
            })
    after_sha = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    return {
        "log_path": str(p),
        "log_sha256": before_sha,
        "after_sha256": after_sha,
        "zero_mutation": before_sha == after_sha,
        "total": len(rows),
        "unreadable_lines": bad,
        "v1_count": v1_count,
        "v2_count": v2_count,
        "annotated_count": annotated_count,
        "attribution_counts": attribution_counts,
        "defect_total": len(defects),
        "defects": defects[: max(0, int(limit))],
    }


# ---------- 本週 Claude 用量 ----------

def usage_path(state):
    return Path(state) / "dispatch" / "claude-usage.json"


def config_dir(override=None):
    """這個 Claude Code 用的設定資料夾：不同帳號常用不同的 CLAUDE_CONFIG_DIR，快照依它分開。"""
    raw = override or os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    p = Path(raw).expanduser()
    try:
        return str(p.resolve())
    except OSError:
        return str(p.absolute())


def _find_snap(doc, target):
    if target in doc:
        return doc[target]
    norm_t = os.path.normcase(str(Path(target)))
    best = None
    for k, v in doc.items():
        if isinstance(v, dict) and os.path.normcase(str(Path(k))) == norm_t:
            if best is None or (v.get("recorded_at") or 0) > (best.get("recorded_at") or 0):
                best = v
    return best


def capture(state, payload, now=None, target_dir=None):
    """狀態列的 JSON 輸入 → 存下 rate_limits 的快照（依設定資料夾分開）。沒有 rate_limits 就不動。"""
    limits = payload.get("rate_limits") if isinstance(payload, dict) else None
    if not isinstance(limits, dict) or not limits:
        return None
    path = usage_path(state)
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        doc = {}
    snap = {k: limits[k] for k in ("five_hour", "seven_day") if isinstance(limits.get(k), dict)}
    if not snap:
        return None
    snap["recorded_at"] = int(now or time.time())
    snap["model"] = ((payload.get("model") or {}).get("id") if isinstance(payload.get("model"), dict) else None)
    key = config_dir(target_dir)
    norm_k = os.path.normcase(key)
    for old in [k for k in doc if k != key and os.path.normcase(str(Path(k))) == norm_k]:
        doc.pop(old, None)
    doc[key] = snap
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return snap


def instance_usage(q, threshold):
    """account_pool.claude_quotas 的一列 → weekly_usage 同形狀的結果（給「這次要派的實例」判門檻）。"""
    if not q or q.get("weekly_used_pct") is None or q.get("over_threshold") is None:
        return {"status": "unknown", "pct": None, "over": None, "threshold": threshold, "instance": (q or {}).get("instance"),
                "source": (q or {}).get("source"), "why": (q or {}).get("why") or "沒有這個實例的額度快照"}
    pct = float(q["weekly_used_pct"])
    return {"status": q.get("status") or "ok", "pct": pct, "over": pct >= threshold, "threshold": threshold,
            "instance": q.get("instance"), "source": q.get("source"), "resets_at": q.get("weekly_resets_at"),
            "age_hours": q.get("age_hours"), "why": q.get("why")}


def weekly_usage(state, threshold, now=None, which=None, instance=None, quotas=None):
    """本週 Claude 用量：{status: ok|stale|unknown, pct, over, resets_at, age_hours, why}。
    unknown 時 over 是 None：不知道就不要假設已達門檻。
    給 instance 時對那個實例判定，來源跟 weekly-first 相同（account_pool.claude_quotas：狀態列快照、T3 快取、手動登記取最新）；
    quotas 沒給就現算。沒給 instance 才是舊行為：只看這個行程的 CLAUDE_CONFIG_DIR 的狀態列快照。"""
    if instance is not None:
        if quotas is None:
            import account_pool
            import accounts
            data, _, _, folder = context()
            mine = personal(folder)
            rows = accounts.registry(accounts.t3_instances(), mine, accounts.load_terms(data))
            quotas = account_pool.claude_quotas(state, rows, mine, threshold)
        return instance_usage(next((q for q in quotas if q.get("instance") == instance), None), threshold)
    now = now or time.time()
    path = usage_path(state)
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        doc = {}
    snap = _find_snap(doc, config_dir(which))
    week = (snap or {}).get("seven_day") or {}
    if not snap or "used_percentage" not in week:
        return {"status": "unknown", "pct": None, "over": None, "threshold": threshold,
                "why": "沒有快照：Claude Code 的狀態列沒有接 dispatch.py statusline，或這個帳號不是訂閱制（rate_limits 只有 Pro、Max、Ultra）"}
    if week.get("resets_at") and week["resets_at"] <= now:
        return {"status": "unknown", "pct": None, "over": None, "threshold": threshold, "why": "快照的這一週已經重置，還沒有新的快照"}
    age = round((now - snap.get("recorded_at", now)) / 3600, 1)
    pct = float(week["used_percentage"])
    return {"status": "stale" if age > STALE_HOURS else "ok", "pct": pct, "over": pct >= threshold, "threshold": threshold,
            "resets_at": week.get("resets_at"), "age_hours": age,
            "why": f"快照是 {age} 小時前的，實際用量可能更高" if age > STALE_HOURS else None}


# ---------- 輸出 ----------

def quota_summary_text(quotas, threshold, native=None):
    """show 第 2 行：每個 Claude 實例本週用量對門檻（跟 weekly-first 同一個來源），加上這段對話自己（native）的狀態列快照。"""
    parts = []
    for q in quotas or []:
        u = instance_usage(q, threshold)
        if u["over"] is None:
            parts.append(f"{q['instance']} 未知")
        else:
            parts.append(f"{q['instance']} {u['pct']:.0f}%（{'已達' if u['over'] else '未達'}"
                         + ("，舊資料" if u["status"] == "stale" else "") + "）")
    if native and native.get("over") is not None:
        parts.append(f"native {native['pct']:.0f}%（{'已達' if native['over'] else '未達'}）")
    if not parts:
        return usage_text(native) if native else f"本週 Claude 用量：沒有任何實例的快照。不要假設已達 {threshold}%。"
    return f"本週 Claude 用量（門檻 {threshold}%，對這次要派的實例判定；未知不假設已達）：" + "、".join(parts)


def usage_text(u):
    if u["status"] == "unknown":
        return f"本週 Claude 用量：未知（{u['why']}）。不要假設已達 {u['threshold']}%。"
    return (f"本週 Claude 用量：{u['pct']:.0f}%（門檻 {u['threshold']}%，{'已達' if u['over'] else '未達'}）"
            + (f"；{u['why']}" if u["why"] else ""))


def channel_lines(pol):
    """管道一覽：每個管道印 use 的第一句。完整寫法（t3_cli 的指令、限制）在 dispatch-policy.md 的 channels。"""
    lines = ["\n管道（完整用法看 data/rules/dispatch-policy.md 的 channels）："]
    for name, ch in (pol.get("channels") or {}).items():
        use = " ".join(str((ch or {}).get("use", "")).split())
        lines.append(f"  {name}：{use.split('。')[0]}")
    return lines


def antigravity_lines(pol, mine=None):
    """派給 Antigravity 時用哪個管道（照使用者偏好 visibility）、任務說明要寫的四件事與驗收方式。"""
    t = pol.get("antigravity_turns") or {}
    if not t:
        return []
    lines = []
    if pol.get("visibility"):
        v = visibility(pol, mine)
        src = "profile 的 dispatch.md" if v["source"] == "profile" else "沒有設定，用政策的預設"
        lines.append(f"\n派給 Antigravity 的管道：偏好 {v['mode']}（{src}）：{v['desc']}；由上往下第一個成立的：")
        lines += [f"  {i}. {c.get('channel')}：{c.get('when', '')}" for i, c in enumerate(v["channels"], 1)]
        lines.append(f"  退路：{v['fallback']}")
    lines.append("\n派給 Antigravity（所有管道）：任務說明固定寫這四件事（證據與待驗證看 antigravity_turns）：")
    lines += [f"  {i}. {b}" for i, b in enumerate(t.get("brief") or [], 1)]
    verify = re.sub(r"(?<=[，。；：、（）])\s+", "", " ".join(str(t.get("verify", "")).split()))  # YAML 換行變成的空白
    lines.append("  驗收：" + verify.split("。")[0])
    lines.append("  以 sent nothing for 15 minutes 失敗時：先看交付檔與完成標記，不要直接重派")
    return lines


def show_text(table, profile, has_personal, usage=None, pol=None, mine=None, accounts=None, pool_lines=None, burn=None):
    prefs = []
    if mine:
        if mine.get("thinking_preference"):
            prefs.append(f"thinking_preference: {mine['thinking_preference']}")
        if mine.get("on_exhausted"):
            prefs.append(f"on_exhausted: {mine['on_exhausted']}")
    pref_str = f"；{'，'.join(prefs)}" if prefs else ""
    lines = [f"profile：{profile}；{'個人實例：有' if has_personal else '沒有個人分派設定，只用原生子代理'}{pref_str}"]
    if usage:
        lines.append(usage if isinstance(usage, str) else usage_text(usage))
    lines += burn_lines(burn)
    burn_drv = (burn or {}).get("author_driver") if (burn or {}).get("triggered") else None
    for level, lv in table.items():
        lines.append(f"\n{lv['name']}（{level}）：{'、'.join(lv['tasks']) or '—'}")
        route = [o for o in lv["options"] if o["kind"] == "route"]
        for o in lv["options"]:
            head = {"prework": "前置", "second_opinion": "第二意見"}.get(o["kind"]) or f"{route.index(o) + 1}."
            inst = (f"已過濾，跳過（{o['filtered']}）" if o.get("filtered") else
                    "單一供應商無跨家對象，跳過" if o.get("single_vendor_skip") else
                    f"已有 {o['superseded']}，不用這個備援" if o.get("superseded") else
                    f"選配，沒宣告，跳過（方案有 {o['model']} 的在 profile 的 dispatch.md 加 opt_in_classes: [{o['class']}]）"
                    if o.get("opt_in_missing") and o["skip"] and not o.get("blocked") else
                    ("沒有可自動派的實例，跳過" if o.get("blocked") else "沒有實例，跳過") if o["skip"] else
                    "實例：" + "、".join(o["instances"])
                    + (f"（未實測：{'、'.join(o['unverified'])}，派前小量探測；撞 model_forbidden 記 log --error 後自動退下一個）"
                       if o.get("unverified") else ""))
            if (burn_drv and o["kind"] == "second_opinion" and not o["skip"]
                    and (pol or {}).get("model_classes", {}).get(o["class"], {}).get("driver") != burn_drv):
                inst += f"；額度到期改判：審 {VENDOR_NAMES.get(burn_drv, burn_drv)} 產出時改用上方「第二意見改判」"
            extra = (f"；條件：{o['when']}" if o["when"] else "") + (f"；只接：{'、'.join(o['tasks'])}" if o["tasks"] else "")
            detail = o.get("role") or o.get("note") or ""
            role = f"；{detail}" if detail else ""
            th_note = f"（{o['thinking_why']}）" if o.get("thinking_why") else ""
            lines.append(f"  {head} {o['class']}（{o['model']}）{o['thinking_name']} {o['thinking']}{th_note}；{inst}{extra}{role}")
            for b in o.get("blocked") or []:
                lines.append(f"     不派 {b['instance']}：{b['why']}")
            if o["pending"]:
                lines.append(f"     {o['pending'].strip()}")
    if accounts:
        lines += accounts
    if pool_lines:
        lines += pool_lines
    if pol:
        lines += channel_lines(pol) + antigravity_lines(pol, mine)
    return "\n".join(lines)


def account_lines(rows, filtered, hints=()):
    """名冊摘要：哪些帳號只給手動、哪些有問題，以及被過濾的模型（帳號池第一階段）。"""
    lines = ["\n帳號（accounts.py scan 看完整原因）："]
    auto = [r["id"] for r in rows if r["auto"][0]]
    manual = [r["id"] for r in rows if r["usage_scope"] == "manual_only" and r["in_t3"]]
    lines.append(f"  可自動派：{'、'.join(auto) or '無'}")
    if manual:
        lines.append(f"  只給手動（manual_only）：{'、'.join(manual)}")
    for r in rows:
        if not r["auto"][0] and r["usage_scope"] != "manual_only":
            lines.append(f"  不派 {r['id']}：{r['auto'][1]}")
    if filtered:
        lines.append(f"  已過濾的模型：{'、'.join(filtered)}")
    for h in hints:
        lines.append(f"  提醒（不過濾）：{h}")
    return lines


def stats_text(s, mode="both"):
    lines = [f"委派紀錄 {s['total']} 筆，有驗收的 {s['judged']} 筆（去噪實地可評 {s.get('clean_judged', 0)} 筆）"]
    if mode in ("both", "raw"):
        if mode == "both":
            lines.append("\n原始一次通過率（依級別 / 初始類別，含基礎設施雜訊）：")
        for r in s["table"]:
            pct = "—" if r["first_pass_rate"] is None else f"{r['first_pass_rate'] * 100:.1f}%"
            lines.append(f"  {r['level']} / {r['class']}：{r['n']} 筆，一次通過 {pct}，升級 {r['escalated']} 筆")
    if mode in ("both", "clean"):
        lines.append("\n去噪模型良率（origin=field，依 level / model / thinking 分組，附 Wilson 95% CI）：")
        for r in s.get("clean_table") or []:
            lo, hi = r["wilson_ci"]
            pct = "—" if r["model_ok_rate"] is None else f"{r['model_ok_rate'] * 100:.1f}%"
            tags = []
            if r.get("low_sample"):
                tags.append("n<20 樣本偏少，請看區間")
            if r.get("ceiling_warn"):
                tags.append("觸頂警示 CI下限>85%")
            dur = f"，中位耗時 {r['median_duration_sec']:.1f}s" if r.get("median_duration_sec") is not None else ""
            tag_s = f"［{'；'.join(tags)}］" if tags else ""
            lines.append(
                f"  {r['level']} / {r['model']} ({r['thinking']})：{r['ok']}/{r['n']} 通過（{pct}，"
                f"95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%]{dur}）{tag_s}"
            )
        infra_rows = [x for x in (s.get("infra_summary") or []) if x.get("infra_count")]
        lines.append("\n基礎設施損耗率（依 instance / channel）：")
        if not infra_rows:
            lines.append("  無基礎設施損耗紀錄")
        for x in infra_rows:
            detail = "、".join(f"{k}:{v}" for k, v in sorted((x.get("issues") or {}).items()))
            lines.append(
                f"  {x['instance']} / {x['channel']}：{x['infra_count']}/{x['total']}"
                f"（{x['infra_rate'] * 100:.1f}%；{detail}）"
            )
        vs = s.get("verify_summary") or {}
        if vs.get("reviewer_total"):
            cpct = "—" if vs.get("catch_rate") is None else f"{vs['catch_rate'] * 100:.1f}%"
            vlo, vhi = vs.get("wilson_ci") or [0.0, 0.0]
            lines.append(
                f"\n審查抓蟲率（reviewer）：共 {vs['reviewer_total']} 筆，已評被審物 {vs['evaluated_n']} 筆，"
                f"抓出真問題 {vs['caught_n']} 筆（{cpct}，95% CI [{vlo * 100:.1f}%, {vhi * 100:.1f}%]）"
            )
    for name, per in s["trials"].items():
        for p in per:
            extra = ""
            if p.get("trial_rate") is not None and p.get("wilson_ci"):
                lo, hi = p["wilson_ci"]
                raw_s = f"，原始 {p['raw_trial_rate'] * 100:.1f}%" if p.get("raw_trial_rate") is not None else ""
                extra = f"（去噪 {p['trial_rate'] * 100:.1f}%，95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%]{raw_s}）"
            lines.append(f"試行 {name}{'（' + p['level'] + '）' if p.get('level') else ''}：{p['verdict']}{extra}")
    return "\n".join(lines)


def backfill_audit_text(rep):
    lines = [
        f"唯讀回溯對帳：{rep['log_path']}",
        f"  log_sha256：{rep['log_sha256'] or '（檔案不存在）'}（零寫改驗證：{'通過' if rep['zero_mutation'] else '失敗'}）",
        f"  總筆數：{rep['total']}（v1 舊紀錄 {rep['v1_count']} 筆、v2 新紀錄 {rep['v2_count']} 筆、覆寫命中 {rep['annotated_count']} 筆、壞行 {rep['unreadable_lines']}）",
        "\n歸因分布：",
    ]
    for k, v in sorted((rep.get("attribution_counts") or {}).items(), key=lambda kv: (-kv[1], kv[0])):
        pct = (v / rep["total"] * 100) if rep["total"] else 0.0
        lines.append(f"  {k}：{v} 筆（{pct:.1f}%）")
    lines.append(f"\n真模型缺陷／複合缺陷清單（共 {rep['defect_total']} 筆，顯示前 {len(rep['defects'])} 筆）：")
    for d in rep.get("defects") or []:
        lines.append(
            f"  #{d['index']} [{d['failure_attribution']}/{d['defect_kind']}] {d['level']} / {d['judged_model']} ({d['judged_thinking']}) "
            f"task={d['task']} verdict={d['verdict']}：{(d.get('note') or '')[:120]}"
        )
    return "\n".join(lines)


# ---------- agy 管道：從任何 agent 無頭派給 Antigravity 的模型 ----------
# 2026-11-16 用 agy 1.5.9 實測：
# - 思考程度要寫在模型代號後面（gemini-4-hydrogen-xhigh），或用 --effort；只寫 gemini-4-hydrogen 會落到 medium。
#   log 會印 resolved to "gemini-4-hydrogen-xhigh"，思考 token 三次是 high 約 900 到 1150、xhigh 約 1850 到 3330。
# - 權限：無頭模式沒辦法核准，agy 的安全監控把不認得的指令送審時就自動拒絕，時好時壞（一次 3 分鐘的調研中途被拒）；
#   --mode accept-edits 一律拒絕終端機指令；--settings 的允許規則讓指令落進沙盒，uv 跑不起來。
#   --dangerously-skip-permissions 連測 3 次都穩定，所以用它，並在任務說明前面加硬性限制（AGY_GUARD），結果一律由主控驗收。
# - agy 終端機的 PATH 只有系統路徑（沒有使用者路徑），uv、gh 這類要給絕對路徑。
AGY_GUARD = ("【硬性限制，優先於下面的任務說明】不 git commit、不 git push、不刪檔或清空資料夾、不改 git 設定、"
             "不寄信或發訊息、不安裝軟體、不改系統或安全設定；只改任務說明允許的檔案。做不到就停下來回報。\n\n")
# 收尾規定（dispatch-policy.md 的 antigravity_turns.brief）：2026-11-18 Antigravity 實例在 T3 寫完回報後回合一直不結束，
# 15 分鐘後被判失敗；同一次也因為在前景跑伺服器撞到工具逾時。完成標記固定寫在交付檔旁邊，主控才查得到。
AGY_FINISH = ("【收尾規定，優先於下面的任務說明】1. 交付物先寫成檔案：任務說明有指定位置就寫在那裡，沒指定就寫進 {result}。"
              "2. 全部做完後，最後一個動作是建立完成標記檔 {done}（內容寫交付檔的路徑），寫完才送出最後回覆。"
              "3. 最後回覆不超過 10 行，附上交付檔路徑。"
              "4. 伺服器、watcher 這類不會自己結束的程式一律背景啟動，不要在前景跑。"
              "這兩個檔一律允許寫。\n\n")


def agy_prefix(result_file):
    """固定加在任務說明前面的硬性限制與收尾規定。"""
    return AGY_GUARD + AGY_FINISH.format(result=result_file, done=f"{result_file}.done")


def agy_result_path(folder=None):
    """沒指定 --result-file 時的交付檔：暫存資料夾的 omnikit-agy 底下，每次一個新檔名。"""
    folder = Path(folder or tempfile.gettempdir()) / "omnikit-agy"
    return folder / f"result-{int(time.time() * 1000)}-{os.getpid()}.md"


def agy_marks(result_file):
    """跑完之後交付檔與完成標記在不在；沒有標記不直接判失敗，提醒主控先看檔再判斷。"""
    result = Path(result_file)
    done = Path(f"{result}.done")
    out = {"result_file": str(result), "result_exists": result.exists(), "done_marker": done.exists()}
    if not out["done_marker"]:
        out["warnings"] = [f"沒有完成標記檔 {done}：先看交付檔與它改的檔，再判斷做完了沒有"]
    return out

def agy_model(pol, cls, thinking):
    """模型類別加思考程度 → agy 的模型代號；不合政策就停。"""
    c = (pol.get("model_classes") or {}).get(cls)
    if c is None:
        raise SystemExit(f"模型類別不存在：{cls}")
    if c.get("driver") != "antigravity":
        raise SystemExit(f"{cls} 不是 Antigravity 的類別，不能走 agy（{c.get('driver')}）")
    if thinking not in THINKING:
        raise SystemExit(f"思考程度要寫明（{THINKING} 之一）：{thinking}")
    if THINKING.index(thinking) > THINKING.index(c.get("max_thinking", "max")):
        raise SystemExit(f"{cls} 的思考程度最高 {c['max_thinking']}，寫了 {thinking}")
    if thinking in (c.get("forbid_thinking") or []):
        raise SystemExit(f"{cls} 禁用思考程度 {thinking}")
    return f"{c['model']}-{thinking}"


def agy_path_note():
    """agy 終端機看不到使用者 PATH：把這台常用工具的絕對路徑附在任務說明後面。"""
    found = {n: shutil.which(n) for n in ("uv", "gh", "git", "node")}
    found = {n: p for n, p in found.items() if p}
    if not found:
        return ""
    return ("\n\n（執行環境備註：你的終端機 PATH 只有系統路徑，這些指令請用絕對路徑："
            + "；".join(f"{n} = {p}" for n, p in found.items()) + "）")


AGY_INLINE_MAX = 4000  # 超過就寫成檔案，參數只放指標


def agy_command(exe, brief, model, timeout_s, result_file, log_file=None, spill_dir=None):
    """長說明寫成檔案、參數只放「讀這個檔照做」：2026-11-16 評審時，約 1.7 萬字的說明放在參數裡，
    有兩份每次都讓呼叫端在 1 秒內靜默結束（結束碼 0、沒有任何輸出），改成檔案指標就正常。
    硬性限制與收尾規定（agy_prefix）一律留在參數裡、放在最前面。"""
    if len(brief) > AGY_INLINE_MAX:
        folder = Path(spill_dir or tempfile.gettempdir()) / "omnikit-agy"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"brief-{int(time.time() * 1000)}-{os.getpid()}.md"
        path.write_text(brief, encoding="utf-8")
        brief = f"完整的任務說明在這個檔案：{path}\n先讀它，完全照裡面的指示做；最後的回覆格式也照它寫的。"
    if len(brief) > AGY_MAX_BRIEF:
        raise SystemExit(f"任務說明 {len(brief)} 字元，超過 {AGY_MAX_BRIEF}")
    cmd = [exe, "-p", agy_prefix(result_file) + brief, "--model", model, "--output-format", "json", "--print-timeout", f"{timeout_s}s",
           "--dangerously-skip-permissions"]
    return cmd + (["--log-file", str(log_file)] if log_file else [])


def agy_result(raw):
    """agy --output-format json 的輸出（前後可能夾著 jetski: 說明）→ 摘要；ok 要成功、沒有被拒的動作、有回覆。"""
    i = raw.find('{"conversation_id"')
    if i < 0:
        return {"ok": False, "error": "看不到 agy 的 JSON 結果", "raw": raw[-2000:]}
    try:
        j, _ = json.JSONDecoder().raw_decode(raw[i:])
    except ValueError as e:
        return {"ok": False, "error": f"agy 的 JSON 讀不懂：{e}", "raw": raw[-2000:]}
    denied = j.get("denied_actions") or []
    resp = (j.get("response") or "").strip()
    problems = ([] if j.get("status") == "SUCCESS" else [f"status 是 {j.get('status')}"]) \
        + ([f"被拒的動作：{', '.join(d.get('display_name') or d.get('action', '?') for d in denied)}"] if denied else []) \
        + ([] if resp else ["沒有回覆"])
    u = j.get("usage") or {}
    return {"ok": not problems, "problems": problems, "conversation_id": j.get("conversation_id"),
            "duration_seconds": j.get("duration_seconds"), "thinking_tokens": u.get("thinking_tokens"),
            "total_tokens": u.get("total_tokens"), "response": resp}


def run_agy(pol, args):
    exe = shutil.which("agy")
    if not exe:
        raise SystemExit("找不到 agy（Antigravity CLI）；這台沒裝就走 delegate_task 或原生子代理")
    model = agy_model(pol, args.cls, args.thinking)
    brief = Path(args.brief_file).read_text(encoding="utf-8-sig") if args.brief_file else args.brief
    if not brief:
        raise SystemExit("要給 --brief 或 --brief-file")
    result = Path(args.result_file).resolve() if args.result_file else agy_result_path()
    result.parent.mkdir(parents=True, exist_ok=True)
    cmd = agy_command(exe, brief + agy_path_note(), model, args.timeout, result, args.log_file)
    t0 = time.monotonic()
    r = subprocess.run(cmd, cwd=args.cwd, capture_output=True, timeout=args.timeout + 120)
    out = agy_result((r.stdout + r.stderr).decode("utf-8", "replace"))
    out.update({"model": model, "elapsed_seconds": round(time.monotonic() - t0), "exit_code": r.returncode})
    out.update(agy_marks(result))
    out["headless_note"] = "這次走無頭模式，T3 看不到；偏好是 visible 的使用者，回報要寫明原因（T3 沒在跑、使用者同意）"
    return out


# ---------- 主程式 ----------

def context():
    """這台的 data、state、選的 profile 與它的資料夾。
    在 git worktree 內開發時，被 .gitignore 忽略的個人 profile（data/profiles/<name>）只存在主 repo；
    若當前 data/ 找不到，依序查 state/config.json 登記的主 repo，仍無則退回 default，避免 worktree 內 stats/backfill-audit 失敗。"""
    data, state = profiles.DATA, profiles.STATE
    chosen_name = profiles.chosen(state)
    if chosen_name and profiles.folder(data, state, chosen_name) is None:
        cfg_file = Path(state) / "config.json"
        if cfg_file.is_file():
            try:
                cfg_repo = Path(json.loads(cfg_file.read_text(encoding="utf-8-sig")).get("repo") or "")
                cand = cfg_repo / "data" / "profiles" / chosen_name
                if (cand / "AGENTS.md").is_file():
                    return data, state, chosen_name, cand
            except (OSError, ValueError, TypeError):
                pass
        return data, state, profiles.DEFAULT, profiles.folder(data, state, profiles.DEFAULT)
    name, _ = profiles.resolve(data, state)
    return data, state, name, profiles.folder(data, state, name)


def main(argv=None):
    ap = argparse.ArgumentParser(description="子任務分派：政策、委派紀錄、試行比較、本週 Claude 用量")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("show")
    p.add_argument("--agent", choices=list(AGENT_DRIVER), default="claude")
    p.add_argument("--json", action="store_true")
    p.add_argument("--burn", action="append", default=[], metavar="實例",
                   help="使用者明說要燒的實例（可重複）：當成快到期，第二意見照 second_opinion_burn 改判")
    sub.add_parser("check")
    p = sub.add_parser("log")
    p.add_argument("--task", required=True)
    p.add_argument("--class", dest="cls", required=True)
    p.add_argument("--thinking", required=True)
    p.add_argument("--verdict", required=True)
    p.add_argument("--first-pass", choices=["yes", "no"])
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--retries-infra", type=int, default=None, help="基礎設施重跑次數")
    p.add_argument("--retries-quality", type=int, default=None, help="模型品質重跑次數")
    p.add_argument("--escalations", type=int, default=0)
    p.add_argument("--final-class")
    p.add_argument("--origin", choices=ORIGINS, default=None, help="紀錄來源：field（預設）| eval | probe")
    p.add_argument("--role", choices=ROLES, default=None, help="角色：author | reviewer | prework | judge")
    p.add_argument("--infra", choices=INFRA_ISSUES, default=None, help="基礎設施問題分類")
    p.add_argument("--scope", choices=SCOPES, default=None, help="執行範圍：complete | capped_by_caller | truncated_by_model")
    p.add_argument("--scope-capped", action="store_true", help="快捷旗標：等同 --scope capped_by_caller（如 12 組上限封頂）")
    p.add_argument("--unverified", action="store_true", help="交付完成但尚未完成實質驗收（model_ok=None）")
    p.add_argument("--subject-pass", choices=["yes", "no", "na"], default=None, help="被審物是否通過（僅 reviewer/judge 有效）")
    p.add_argument("--model-ok", choices=["yes", "no", "na"], default=None, help="模型本身表現是否合格（no 必填 --defect）")
    p.add_argument("--defect", choices=DEFECT_KINDS, default=None, help="模型缺陷分類")
    p.add_argument("--duration-sec", type=float, default=None, help="本次委派耗時（秒）")
    p.add_argument("--work", default=None, help="同一工作包／對照實驗叢集 ID")
    p.add_argument("--eval-ref-json", default=None, help="關聯盲評／評測 JSON 物件字串")
    p.add_argument("--channel", choices=CHANNELS, default="native")
    p.add_argument("--instance")
    p.add_argument("--level")
    p.add_argument("--project")
    p.add_argument("--control", action="store_true")
    p.add_argument("--error", help="錯誤種類（rate_limit、quota_exhausted、auth_expired、validation_required、tos_banned、hard_forbidden、model_forbidden、timeout_15min、other）")
    p.add_argument("--error-text", help="錯誤原文：自動分類並遮罩疑似 token")
    p.add_argument("--resets-at", help="額度重置時間（ISO8601 或 unix timestamp），寫進 pool-state.json")
    p.add_argument("--error-url", help="本人驗證或申訴連結（https://），寫進 pool-state.json")
    p.add_argument("--note")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("stats")
    p.add_argument("--mode", choices=STATS_MODES, default="both", help="顯示視圖：both（預設）| raw | clean")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("backfill-audit", help="唯讀對帳 log.jsonl 投影結果與原檔 SHA-256 零寫改驗證")
    p.add_argument("--limit", type=int, default=30, help="列出模型缺陷清單筆數上限（預設 30）")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("usage")
    p.add_argument("--all", action="store_true", help="列出全部 Claude 設定目錄與 Antigravity 帳號的額度視圖")
    p.add_argument("--refresh-agy", action="store_true", help="呼叫 agy -p /usage 更新本機 agy 帳號額度（搭配 --all 或單獨用）")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("statusline")
    p.add_argument("--dir", help="這個 Claude Code 的設定目錄（沒給就看 CLAUDE_CONFIG_DIR 或 ~/.claude）")
    p.add_argument("--then", help="原本的狀態列指令：收到的 JSON 照樣轉給它，印它的輸出")
    p = sub.add_parser("agy", help="用 agy 無頭派給 Antigravity 的模型（visibility: headless 的管道；T3 看不到過程）")
    p.add_argument("--class", dest="cls", required=True)
    p.add_argument("--thinking", required=True)
    p.add_argument("--brief")
    p.add_argument("--brief-file")
    p.add_argument("--cwd", help="agy 的工作資料夾（預設目前資料夾）")
    p.add_argument("--timeout", type=int, default=1800, help="秒")
    p.add_argument("--result-file", help="任務說明沒指定交付位置時寫在這裡，完成標記是它加 .done（預設在暫存資料夾）")
    p.add_argument("--log-file")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "statusline":  # 狀態列：任何錯誤都安靜，不能干擾畫面
        raw = sys.stdin.buffer.read()
        snap = None
        try:
            snap = capture(profiles.STATE, json.loads(raw.decode("utf-8") or "{}"), target_dir=args.dir)
        except Exception:  # noqa: BLE001
            pass
        if args.then:
            # Claude Code 在 Windows 上用 Git Bash 跑狀態列指令；優先找 Git Bash，避開未裝發行版的 System32\bash.exe（WSL stub）
            git_bash = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
            bash = (str(git_bash) if git_bash.is_file() else shutil.which("bash")) if os.name == "nt" else None
            r = subprocess.run([bash, "-c", args.then] if bash else args.then, shell=not bash, input=raw, capture_output=True)
            sys.stdout.buffer.write(r.stdout)
        elif snap and "seven_day" in snap:
            print(f"Claude 本週 {float(snap['seven_day'].get('used_percentage', 0)):.0f}%")
        return 0
    data, state, name, folder = context()
    pol = policy(data)
    mine = personal(folder)
    if args.cmd == "check":
        errors = check(pol, mine)
        print("\n".join(errors) if errors else f"分派政策沒有問題（profile：{name}）")
        return 1 if errors else 0
    if args.cmd == "show":
        import account_pool
        import accounts  # 帳號名冊與模型過濾；accounts 也 import 這支，所以在這裡才載入
        pdoc = account_pool.load_state(state)
        rows, judge, model_note = accounts.annotate(pol, mine, data, state, pool_doc=pdoc)
        filtered, hints = accounts.filtered_summary(pol, mine, state, accounts.rates_index())
        th = pol["usage_signal"]["claude_weekly_threshold_pct"]
        c_quotas = account_pool.claude_quotas(state, rows, mine, th)
        c_sel = account_pool.select_claude_instance(rows, mine, c_quotas, pdoc)
        plan = account_pool.failover_plan(pol, mine, rows, pdoc, c_quotas)
        alerts = account_pool.pending_alerts(pdoc, rows)
        u = weekly_usage(state, th)  # 這段對話自己（native）的狀態列快照
        per_inst = {q["instance"]: instance_usage(q, th) for q in c_quotas}
        if u.get("over") is not None:
            per_inst["native"] = u
        verified = verified_pairs(state)
        table = resolved(pol, mine, args.agent, judge, model_note, claude_order=c_sel.get("ordered"),
                         verified=verified, usage=per_inst)
        sob = pol.get("second_opinion_burn") or {}
        cands = account_pool.burn_candidates(rows, mine, c_quotas, pdoc, within_hours=sob.get("within_hours"),
                                             min_remaining_pct=sob.get("min_weekly_remaining_pct", 20), forced=args.burn)
        burn = burn_decision(pol, mine, cands, args.agent, judge, model_note, verified)
        plines = []
        if c_sel.get("chosen"):
            plines.append(f"  Claude 實例推薦（工作包邊界挑，同一條不中途換）：{c_sel['chosen']}（{c_sel['reason']}）")
        plines.append("")
        plines += account_pool.failover_text(plan).splitlines()
        if alerts:
            plines.append("\n帳號警示：")
            plines += [f"  [{a['severity']}] {a['message']}" for a in alerts]
        print(json.dumps({"usage": u, "usage_by_instance": per_inst, "second_opinion_burn": burn,
                          "claude_quotas": c_quotas, "claude_selection": c_sel,
                          "levels": table, "channels": pol.get("channels"), "accounts": rows,
                          "filtered_models": filtered, "model_hints": hints, "failover": plan,
                          "alerts": alerts, "visibility": visibility(pol, mine),
                          "thinking_preference": (mine or {}).get("thinking_preference"),
                          "on_exhausted": (mine or {}).get("on_exhausted")}, ensure_ascii=False, indent=2)
              if args.json else show_text(table, name, mine is not None, quota_summary_text(c_quotas, th, u), pol, mine,
                                          account_lines(rows, filtered, hints), plines, burn))
        return 0
    if args.cmd == "log":
        rec = make_record(pol, args, rules_version(data), name, project_name())
        pool_msg = None
        if not args.dry_run:
            append(log_path(state), rec)
            if rec.get("instance") and rec["instance"] != "native":
                import account_pool
                drv = pol["model_classes"][rec["class"]]["driver"]
                if rec.get("error_kind"):
                    c_info = account_pool.classify_error(args.error_text, model=rec["model"]) if args.error_text else {}
                    _, pool_msg = account_pool.record_error(
                        state, rec["instance"], rec["error_kind"], driver=drv, model=rec["model"],
                        resets_at=args.resets_at or c_info.get("resets_at"),
                        url=args.error_url or c_info.get("url"),
                        reason=rec.get("note") or c_info.get("summary") or "",
                    )
                elif rec.get("verdict") == "pass":
                    _, pool_msg = account_pool.record_ok(state, rec["instance"], driver=drv, model=rec["model"])
        print(json.dumps(rec, ensure_ascii=False))
        print(("（預覽，沒有寫入）" if args.dry_run else f"已記到 {log_path(state)}"))
        if looks_like_noise_project(rec.get("project")):
            print(
                f"提醒：project 名稱「{rec['project']}」看起來像日期、hash 或 skill 子目錄，請確認是否應帶 --project <專案名>",
                file=sys.stderr,
            )
        if pool_msg:
            print(f"帳號池狀態：{pool_msg}")
        return 0
    if args.cmd == "stats":
        rows, bad = read_log(log_path(state))
        anns = read_annotations(state)
        s = stats(pol, rows, annotations=anns)
        s["unreadable_lines"] = bad
        print(json.dumps(s, ensure_ascii=False, indent=2) if args.json else stats_text(s, mode=args.mode) + (f"\n讀不懂的行：{bad}" if bad else ""))
        return 0
    if args.cmd == "backfill-audit":
        anns = read_annotations(state)
        rep = backfill_audit(log_path(state), annotations=anns, pol=pol, limit=args.limit)
        print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else backfill_audit_text(rep))
        return 0
    if args.cmd == "agy":
        out = run_agy(pol, args)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["ok"] else 1
    if args.cmd == "usage":
        if args.all or args.refresh_agy:
            import account_pool
            import accounts
            rows = accounts.registry(accounts.t3_instances(), mine, accounts.load_terms(data))
            refreshed = None
            if args.refresh_agy:
                refreshed = account_pool.refresh_agy_usage(state, account_pool.agy_cli_target(rows, mine))
            view = account_pool.quota_view_data(state, pol, mine, rows)
            if refreshed is not None:
                view["refreshed_agy"] = refreshed
            print(json.dumps(view, ensure_ascii=False, indent=2) if args.json else account_pool.usage_view_text(view))
            return 0
        u = weekly_usage(state, pol["usage_signal"]["claude_weekly_threshold_pct"])
        print(json.dumps(u, ensure_ascii=False) if args.json else usage_text(u))
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

    def fails(fn):
        try:
            fn()
        except SystemExit:
            return True
        return False

    pol = policy(profiles.DATA)
    sample = personal(SAMPLE_PROFILE)
    ok("repo 裡的共用層與假的樣本個人層（testdata/profile-sample）通過檢查", check(pol, sample) == [])
    with tempfile.TemporaryDirectory() as tmp:
        dup = Path(tmp) / "d.md"
        dup.write_text("```yaml\na:\n  note: 1\n  note: 2\n```\n", encoding="utf-8")
        try:
            block(dup)
            caught = False
        except ValueError as e:
            caught = "note" in str(e)
    ok("政策 yaml 同一層重複的鍵會報錯，不會悄悄只留後面那個", caught)
    t3 = (pol.get("channels") or {}).get("t3_cli") or {}
    ok("共用層有 t3_cli 管道：寫明在 PowerShell 呼叫 t3 thread start、--provider 用實例 key、沒有 settle 子指令",
       "t3 thread start" in t3.get("how", "") and "PowerShell" in t3.get("how", "") and "--provider" in t3.get("how", "")
       and "settle" in t3.get("settle", "") and set(pol["channels"]) == set(CHANNELS))
    mcp = (pol.get("channels") or {}).get("t3_thread_launch") or {}
    ok("t3_thread_launch 管道寫明 T3 外怎麼接 MCP、思考程度用 modelSelection.options、settle 後回讀 settled",
       "claude mcp login t3" in mcp.get("how", "") and "modelSelection.options" in mcp.get("thinking", "")
       and "settled" in mcp.get("settle", ""))
    shown = show_text(resolved(pol, sample, "claude"), "sample", True, None, pol, sample)
    ok("show 的輸出列出每個管道，包含 t3_cli", all(f"  {c}：" in shown for c in CHANNELS))
    vr = visibility(pol, sample)
    ok("sample 的 visibility 是 visible（profile 設定）：show 依序印 delegate_task、t3_thread_launch、t3_cli 與退路",
       vr["mode"] == "visible" and vr["source"] == "profile"
       and [c["channel"] for c in vr["channels"]] == ["delegate_task", "t3_thread_launch", "t3_cli"]
       and "偏好 visible（profile 的 dispatch.md）" in shown and "1. delegate_task：" in shown and "退路：" in shown)
    vh = visibility(pol, {"instances": {}, "visibility": "headless"})
    hs = show_text(resolved(pol, sample, "claude"), "x", True, None, pol, {"visibility": "headless"})
    ok("visibility: headless 的使用者：管道是 agy_cli，show 印偏好 headless",
       [c["channel"] for c in vh["channels"]] == ["agy_cli"] and "偏好 headless" in hs and "1. agy_cli：" in hs)
    vd = visibility(pol, {"instances": {}})
    ok("沒寫 visibility：用政策的預設，source 是 default", vd["mode"] == pol["visibility"]["default"] and vd["source"] == "default")
    ok("個人層 visibility 寫錯會報錯", any("個人層 visibility" in e for e in check(pol, {"visibility": "both"})))
    bad_vis = json.loads(json.dumps(pol))
    bad_vis["visibility"]["modes"]["visible"]["channels"].insert(0, {"channel": "agy_cli"})
    bad_vis["visibility"]["default"] = "maybe"
    errs_vis = check(bad_vis)
    ok("政策的 visible 放進 agy_cli、預設值寫錯都會報錯",
       any("visible.channels 不能有 agy_cli" in e for e in errs_vis) and any("visibility.default" in e for e in errs_vis))
    drift = json.loads(json.dumps(pol))
    drift["channels"].pop("t3_cli")
    drift["channels"]["t3_typo"] = {"use": "x"}
    ok("政策的管道和 CHANNELS 對不上會報錯（log --channel 才不會收不存在的管道）",
       any("t3_cli" in e and "t3_typo" in e for e in check(drift)))
    ok("每一級、每個選項都寫明思考程度（不靠預設值）",
       all(o.get("thinking") in THINKING for lv in pol["levels"] for o in options(pol, lv)))

    bad = json.loads(json.dumps(pol))
    bad["levels"]["medium"]["route"][0]["thinking"] = "low"
    for opt in bad["levels"]["high"]["route"]:
        if opt["class"] in ("gemini-carbon", "antigravity-opus"):
            opt["thinking"] = "xhigh"
            break
    bad["levels"]["higher"]["route"][0].pop("thinking")
    bad["tasks"]["docs"]["level"] = "nope"
    bad["escalation"].append({"from": {"class": "claude-fable", "thinking": "high"}, "to": {"class": "claude-opus", "thinking": "xhigh"}, "why": "測試無 once 循環"})
    errs = check(bad, {"instances": {"x": {"driver": "antigravity", "classes": ["claude-opus", "nope"]}}})
    ok("檢查抓得到：禁用的 low、超過上限、沒寫思考程度、不存在的級別、實例對錯供應商、不存在的類別、升級循環",
       any("禁用" in e for e in errs) and any("最高 high" in e for e in errs) and any("不要靠預設值" in e for e in errs)
       and any("tasks.docs" in e for e in errs) and any("要用 claudeAgent 的實例" in e for e in errs)
       and any("類別不存在：nope" in e for e in errs) and any("循環" in e for e in errs))

    t = resolved(pol, sample, "claude")
    med = t["medium"]["options"]
    # 2026-11-25 定案：讀檔／雜務（docs、readonly）用 Hydrogen xhigh 或 Opus medium；多檔／UI 用 Neon xhigh 或 Opus high；Sonnet 留作試行退路
    ok("sample：中級 docs/readonly 首選 Hydrogen xhigh，多檔／UI 首選 Neon xhigh，選項名稱為 thought_level；Claude 維持政策 effort 不被 max_available 拉到 max",
       med[0]["class"] == "gemini-fast" and med[0]["model"] == "gemini-4-hydrogen"
       and med[0]["thinking"] == "xhigh" and med[0]["instances"] == ["antigravity_main"]
       and med[0]["thinking_name"] == "thought_level" and med[0]["tasks"] == ["docs", "readonly"]
       and med[1]["class"] == "gemini-pro" and med[1]["model"] == "gemini-4-neon"
       and med[1]["thinking"] == "xhigh" and med[1]["thinking_name"] == "thought_level"
       and any(o["class"] == "claude-opus" and o["thinking"] == "medium" and o["tasks"] == ["docs", "readonly"] for o in med)
       and any(o["class"] == "claude-opus" and o["thinking"] == "high" and o["tasks"] == ["ui-small", "code-small"] for o in med)
       and med[-1]["class"] == "claude-sonnet")
    ov_t = resolved(pol, {**sample, "effort_overrides": {"claude-opus": "medium"}}, "claude")
    ok("個人層 effort_overrides 可覆寫特定類別／級別的思考程度，不合法覆寫會被 check 擋下",
       [o for o in ov_t["verify"]["options"] if o["class"] == "claude-opus"][0]["thinking"] == "medium"
       and [o for o in ov_t["verify"]["options"] if o["class"] == "claude-opus"][0]["thinking_why"] == "effort_overrides: claude-opus"
       and any("effort_overrides" in e for e in check(pol, {"effort_overrides": {"gemini-pro": "low"}})))
    econ = resolved(pol, {**sample, "thinking_preference": "economy"}, "claude")
    ok("thinking_preference: economy 降一般任務一檔（Neon/Hydrogen xhigh→high、Sonnet medium→low），但絕不把 Gemini 降到禁用的 medium／low",
       [o for o in econ["medium"]["options"] if o["class"] == "gemini-pro"][0]["thinking"] == "high"
       and [o for o in econ["medium"]["options"] if o["class"] == "gemini-fast"][0]["thinking"] == "high"
       and [o for o in econ["medium"]["options"] if o["class"] == "claude-sonnet"][0]["thinking"] == "low")
    ok("個人層 thinking_preference、on_exhausted、account_strategy、notify 寫錯會報錯",
       len(check(pol, {"thinking_preference": "ultra", "on_exhausted": "spin", "account_strategy": "rng", "notify": "sms"})) == 4)
    ord_t = resolved(pol, sample, "claude", claude_order=["claudeAgent_2", "claudeAgent_claude_b", "claudeAgent"])
    ok("claude_order 依額度策略排實例順序，native 仍排第一",
       [o for o in ord_t["high"]["options"] if o["class"] == "claude-opus"][0]["instances"]
       == ["native", "claudeAgent_2", "claudeAgent_claude_b", "claudeAgent"])
    tj = resolved(pol, sample, "claude", lambda i, m: (i != "claudeAgent_2", "測試：停用"),
                  lambda m: "測試：過濾" if m == "gemini-4-hydrogen" else "")
    son = [o for o in tj["medium"]["options"] if o["class"] == "claude-sonnet"][0]
    fl = [o for o in tj["medium"]["options"] if o["class"] == "gemini-fast"][0]
    ok("judge 不能派的實例移到 blocked 附原因；被過濾的模型整個選項跳過",
       "claudeAgent_2" not in son["instances"] and son["blocked"] == [{"instance": "claudeAgent_2", "why": "測試：停用"}]
       and fl["skip"] and fl["filtered"] == "測試：過濾"
       and "已過濾，跳過（測試：過濾）" in show_text(tj, "sample", True) and "不派 claudeAgent_2：測試：停用" in show_text(tj, "sample", True))
    ok("Claude 類別在 Claude 底下原生子代理排第一",
       [o for o in t["high"]["options"] if o["class"] == "claude-fable"][0]["instances"][0] == "native"
       and [o for o in t["high"]["options"] if o["class"] == "claude-opus"][0]["instances"][0] == "native")
    high_routes = [o["class"] for o in t["high"]["options"] if o["kind"] == "route"]
    ok("sample：high 含 synthesis／major-change 且首選 Fable 5.2 high 與 Carbon high；verify／higher 維持 Opus xhigh；雙向對等跨家審查齊備",
       "synthesis" in t["high"]["tasks"] and "major-change" in t["high"]["tasks"]
       and high_routes[:2] == ["claude-fable", "gemini-carbon"]
       and all(t[lv]["options"][0]["kind"] == "prework" and t[lv]["options"][0]["class"] == "gemini-pro" for lv in ("high", "higher"))
       and all(
           any(o["kind"] == "second_opinion" and o["class"] == "gemini-carbon" and o["thinking"] == "high" for o in t[lv]["options"])
           and any(o["kind"] == "second_opinion" and o["class"] == "claude-fable" and o["thinking"] == "high" for o in t[lv]["options"])
           for lv in ("high", "higher", "verify", "architecture")
       )
       and [o for o in t["higher"]["options"] if o["kind"] == "route"][0]["class"] == "claude-opus"
       and [o for o in t["higher"]["options"] if o["kind"] == "route"][0]["thinking"] == "xhigh"
       and t["verify"]["options"][0]["class"] == "claude-opus" and t["verify"]["options"][0]["thinking"] == "xhigh"
       and t["architecture"]["options"][0]["class"] == "claude-fable" and t["architecture"]["options"][0]["thinking"] == "high")
    bare = resolved(pol, None, "claude")
    ok("沒有個人層（同事只有 Claude）：Gemini 與 Antigravity 選項、以及所有跨家第二意見全部跳過（不自己審自己），Claude 原生主路由可用",
       all(o["skip"] for lv in bare.values() for o in lv["options"] if not o["class"].startswith("claude-"))
       and all(o["skip"] for lv in bare.values() for o in lv["options"] if o["kind"] == "second_opinion")
       and any(o["class"] == "claude-sonnet" and o["thinking"] == "medium" and not o["skip"] for o in bare["medium"]["options"])
       and "有 Fable 才升 Fable 5.2 high" in show_text(t, "sample", True))

    def pick(table, lv, cls, kind="route", nth=0):
        return [o for o in table[lv]["options"] if o["class"] == cls and o["kind"] == kind][nth]
    bare_show = show_text(bare, "default", False)
    ok("Fable 是選配：沒宣告的同事 high 與 architecture 的 Fable 跳過並提示 opt_in_classes，改走 Opus（high 用 Opus high、architecture 用 Opus xhigh 備援）",
       pick(bare, "high", "claude-fable")["skip"] and pick(bare, "high", "claude-fable")["opt_in_missing"]
       and pick(bare, "high", "claude-opus")["instances"] == ["native"] and pick(bare, "high", "claude-opus")["thinking"] == "high"
       and pick(bare, "architecture", "claude-fable")["skip"]
       and pick(bare, "architecture", "claude-opus")["instances"] == ["native"]
       and pick(bare, "architecture", "claude-opus")["thinking"] == "xhigh"
       and all(any(not o["skip"] and o["kind"] == "route" for o in lv["options"]) for lv in bare.values())
       and "選配，沒宣告，跳過" in bare_show and "opt_in_classes: [claude-fable]" in bare_show)
    ok("sample 的實例宣告了 claude-fable：Fable 照用，標 fallback_for 的 Opus 備援自動跳過",
       pick(t, "architecture", "claude-fable")["instances"][0] == "native"
       and pick(t, "architecture", "claude-opus")["superseded"] == "claude-fable"
       and pick(t, "architecture", "claude-opus")["skip"]
       and "已有 claude-fable，不用這個備援" in show_text(t, "sample", True))
    opt = resolved(pol, {"opt_in_classes": ["claude-fable"]}, "claude")
    ok("只寫 opt_in_classes: [claude-fable]（沒有任何 T3 實例）也能啟用 Fable 的原生子代理",
       pick(opt, "high", "claude-fable")["instances"] == ["native"] and pick(opt, "architecture", "claude-opus")["skip"])
    gem = {"instances": {"ag": {"driver": "antigravity", "classes": ["gemini-carbon", "gemini-pro"]}}}
    gt = resolved(pol, gem, "claude")
    ok("有 Gemini 沒 Fable：審 Gemini 產出的第二意見由 Opus xhigh 備援接手，Fable 那行跳過",
       pick(gt, "verify", "claude-fable", "second_opinion")["skip"]
       and pick(gt, "verify", "claude-opus", "second_opinion")["instances"] == ["native"]
       and pick(gt, "verify", "claude-opus", "second_opinion")["thinking"] == "xhigh"
       and pick(gt, "verify", "gemini-carbon", "second_opinion")["instances"] == ["ag"])
    gone = resolved(pol, sample, "claude", None, lambda m: "測試：淘汰" if m == pol["model_classes"]["claude-fable"]["model"] else "")
    ok("宣告了 Fable 但它被淘汰過濾：Opus 備援不跳過，architecture 仍派得出去",
       pick(gone, "architecture", "claude-fable")["skip"]
       and not pick(gone, "architecture", "claude-opus")["skip"] and pick(gone, "architecture", "claude-opus")["superseded"] is None)
    gem_only = {"instances": {"ag": {"driver": "antigravity", "classes": ["gemini-carbon"]},
                              "cl": {"driver": "claudeAgent", "classes": ["claude-opus", "claude-fable"]}}}
    blk = resolved(pol, gem_only, "antigravity", lambda i, m: (not (i == "cl" and m == pol["model_classes"]["claude-fable"]["model"]), "測試：擋 Fable"))
    ok("Fable 的實例都被 judge 擋下：Opus 備援接手（不因為登記過 Fable 就整個跳過）",
       pick(blk, "architecture", "claude-opus")["superseded"] is None and pick(blk, "architecture", "claude-opus")["instances"] == ["cl"])
    manual = {"instances": {"ag": {"driver": "antigravity", "usage_scope": "manual_only", "classes": ["gemini-carbon"]},
                            "ag2": {"driver": "antigravity"}}}
    ok("只給手動或沒寫 classes 的實例不算第二家：Claude 的第二意見照樣跳過，不會只剩派不出去的那行",
       all(o["skip"] and o["single_vendor_skip"] for o in resolved(pol, manual, "claude")["verify"]["options"]
           if o["kind"] == "second_opinion" and o["class"].startswith("claude")))
    bad_fb = json.loads(json.dumps(pol))
    bad_fb["levels"]["architecture"]["route"][1]["fallback_for"] = "nope"
    bad_fb["model_classes"]["claude-fable"]["opt_in"] = "yes"
    errs_fb = check(bad_fb, {"opt_in_classes": ["claude-opus", "ghost"]})
    ok("檢查抓得到：fallback_for 指到不存在的類別、opt_in 不是布林、opt_in_classes 寫了非選配或不存在的類別",
       any("fallback_for" in e for e in errs_fb) and any("opt_in 要是" in e for e in errs_fb)
       and any("不是選配類別" in e for e in errs_fb) and any("類別不存在：ghost" in e for e in errs_fb))

    ok("agy：類別加思考程度寫進模型代號（Neon xhigh、Hydrogen xhigh、Carbon high、Antigravity 的 Opus high）",
       agy_model(pol, "gemini-pro", "xhigh") == "gemini-4-neon-xhigh"
       and agy_model(pol, "gemini-fast", "xhigh") == "gemini-4-hydrogen-xhigh"
       and agy_model(pol, "gemini-carbon", "high") == "gemini-4-carbon-high"
       and agy_model(pol, "antigravity-opus", "high") == "claude-opus-5-5-high")
    ok("agy：不合政策的不派（Claude Code 的類別、禁用的 low、超過 Carbon 上限 xhigh、沒寫思考程度）",
       fails(lambda: agy_model(pol, "claude-opus", "high")) and fails(lambda: agy_model(pol, "gemini-pro", "low"))
       and fails(lambda: agy_model(pol, "gemini-carbon", "xhigh")) and fails(lambda: agy_model(pol, "gemini-pro", None)))
    cmd = agy_command("agy", "任務", "gemini-4-hydrogen-high", 600, "r.md", "x.log")
    ok("agy：指令帶模型代號、JSON 輸出、逾時、log 與略過權限；任務說明前面加硬性限制與收尾規定；不帶 --mode（accept-edits 會擋掉終端機指令）",
       cmd[:2] == ["agy", "-p"] and cmd[2] == agy_prefix("r.md") + "任務" and cmd[2].startswith(AGY_GUARD)
       and "gemini-4-hydrogen-high" in cmd and "json" in cmd
       and "600s" in cmd and "--dangerously-skip-permissions" in cmd and "--mode" not in cmd and cmd[-1] == "x.log")
    finish = agy_prefix("C:/t/result-1.md")
    ok("agy：收尾規定四件事都在（交付檔路徑、最後寫完成標記 .done、回覆 10 行內、伺服器背景啟動），而且跟政策的 brief 一樣是四條",
       "C:/t/result-1.md" in finish and "C:/t/result-1.md.done" in finish and "最後一個動作" in finish
       and "10 行" in finish and "背景啟動" in finish and "前景" in finish
       and len(pol["antigravity_turns"]["brief"]) == 4 and all(f"{i}. " in finish for i in range(1, 5)))
    with tempfile.TemporaryDirectory() as tmp:
        long_cmd = agy_command("agy", "長說明" * 3000, "m", 1, "r.md", spill_dir=tmp)
        spilled = list((Path(tmp) / "omnikit-agy").glob("brief-*.md"))
        ok("agy：長說明寫成檔案，參數只放指標、硬性限制與收尾規定（長參數曾讓呼叫端靜默結束）",
           len(long_cmd[2]) < AGY_INLINE_MAX + len(agy_prefix("r.md")) and long_cmd[2].startswith(agy_prefix("r.md"))
           and len(spilled) == 1 and spilled[0].read_text(encoding="utf-8") == "長說明" * 3000
           and str(spilled[0]) in long_cmd[2])
        res = agy_result_path(tmp)
        res.parent.mkdir(parents=True, exist_ok=True)
        before = agy_marks(res)
        res.write_text("報告", encoding="utf-8")
        Path(f"{res}.done").write_text(str(res), encoding="utf-8")
        after = agy_marks(res)
        ok("agy：預設交付檔在暫存的 omnikit-agy；跑完回報交付檔與完成標記在不在，沒標記只提醒、不改 ok",
           res.parent == Path(tmp) / "omnikit-agy" and res.name.startswith("result-")
           and not before["done_marker"] and not before["result_exists"] and before["warnings"]
           and after["done_marker"] and after["result_exists"] and "warnings" not in after and "ok" not in after)
    turns = pol.get("antigravity_turns") or {}
    ok("政策的 antigravity_turns：驗收寫明 t3_thread_wait 短逾時、t3_thread_interrupt、settle，t3_cli 沒有中斷子指令；"
       "15 分鐘失敗先看交付檔；三項待驗證",
       all(k in turns.get("verify", "") for k in ("t3_thread_wait", "60 秒", "t3_thread_interrupt", "settle", "t3 thread show"))
       and "完成標記" in turns.get("failed_15min", "") and "重派" in turns.get("failed_15min", "")
       and sum("待驗證" in p for p in turns.get("pending") or []) == 3)
    shown_turns = show_text(resolved(pol, sample, "claude"), "sample", True, None, pol)
    ok("show 的輸出印出派給 Antigravity 的四件事與驗收方式",
       all(b in shown_turns for b in turns.get("brief") or ["?"]) and "t3_thread_interrupt" in shown_turns)
    no_turns = json.loads(json.dumps(pol))
    no_turns.pop("antigravity_turns")
    three = json.loads(json.dumps(pol))
    three["antigravity_turns"]["brief"] = three["antigravity_turns"]["brief"][:3]
    ok("檢查抓得到：少了 antigravity_turns、brief 不是四件事",
       any("antigravity_turns" in e for e in check(no_turns)) and any("四件事" in e for e in check(three)))
    good = agy_result('{"conversation_id":"c1","status":"SUCCESS","response":"完成\\n","duration_seconds":14.2,'
                      '"usage":{"thinking_tokens":358,"total_tokens":23514}}')
    denied = agy_result('{"conversation_id":"c2","status":"SUCCESS","response":"","denied_actions":[{"action":"command",'
                        '"display_name":"Bash"}]}jetski: no output produced')
    ok("agy：成功、有回覆才算 ok；終端機指令被拒或沒回覆不算；讀不到 JSON 照實說",
       good["ok"] and good["thinking_tokens"] == 358 and good["response"] == "完成"
       and not denied["ok"] and any("Bash" in p for p in denied["problems"]) and any("沒有回覆" in p for p in denied["problems"])
       and not agy_result("jetski: crashed")["ok"])

    ns = argparse.Namespace
    base = dict(task="docs", cls="claude-sonnet", thinking="medium", verdict="pass", first_pass=None, retries=0, escalations=0,
                final_class=None, channel="native", instance=None, level=None, project=None, control=False, note=None)
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    rec = make_record(pol, ns(**base), "2026-11-14-1", "sample", "OmniKit", now)
    need = ["ts", "project", "task", "level", "instance", "model", "thinking", "first_pass", "retries", "escalations", "verdict", "rules_version"]
    ok("紀錄有必填欄位；級別從任務類型推；沒寫 first-pass 時，一次就過才算",
       all(k in rec for k in need) and rec["level"] == "medium" and rec["first_pass"] is True
       and rec["model"] == "claude-sonnet-5-5" and rec["instance"] == "native")
    t3rec = make_record(pol, ns(**{**base, "cls": "gemini-fast", "thinking": "xhigh", "channel": "t3_cli",
                                   "instance": "antigravity_main"}), "v", "sample", "p", now)
    p_log = argparse.ArgumentParser(exit_on_error=False)
    p_log.add_argument("--channel", choices=CHANNELS)
    ok("log 收 t3_cli 管道，實例照寫（antigravity_main）",
       t3rec["channel"] == "t3_cli" and t3rec["instance"] == "antigravity_main"
       and p_log.parse_args(["--channel", "t3_cli"]).channel == "t3_cli")
    esc = make_record(pol, ns(**{**base, "verdict": "pass", "escalations": 1, "final_class": "claude-opus"}), "v", "sample", "p", now)
    ok("Sonnet 驗收不過、改 Opus 重跑：記成一行，class 是一開始派的 Sonnet，first_pass 是 false",
       esc["class"] == "claude-sonnet" and esc["final_class"] == "claude-opus" and esc["first_pass"] is False)
    erec = make_record(pol, ns(**{**base, "verdict": "fail", "error": None,
                                  "error_text": "HTTP 429 weekly quota exhausted Bearer tok-secret-999999"}), "v", "sample", "p", now)
    ok("log --error-text 自動分類錯誤並寫進 error_kind，note 遮罩 token",
       erec["error_kind"] == "quota_exhausted" and "tok-secret" not in (erec["note"] or "") and "[REDACTED]" in (erec["note"] or ""))
    ok("不合政策的不寫：任務類型、類別、思考程度（含超過類別上限）、結論寫錯，或有升級卻沒寫最後的類別",
       fails(lambda: make_record(pol, ns(**{**base, "task": "x"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "cls": "x"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "thinking": "huge"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "cls": "antigravity-opus", "thinking": "xhigh"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "verdict": "ok"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "escalations": 1}), "v", "r", "p")))
    ok("Schema v2：欄位與政策 log.fields 完全一致；源頭防呆擋下無 --defect 的 --model-ok no 與無歸因的 reviewer fail",
       tuple(rec.keys()) == LOG_FIELDS and rec["schema_version"] == 2 and rec["model_ok"] is True
       and esc["judged_model"] == "claude-opus-5-5" and esc["model_ok"] is False
       and erec["infra_issue"] == "quota" and erec["model_ok"] is None
       and fails(lambda: make_record(pol, ns(**{**base, "model_ok": "no"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "task": "verify", "cls": "claude-opus", "thinking": "xhigh", "verdict": "fail"}), "v", "r", "p"))
       and make_record(pol, ns(**{**base, "task": "verify", "cls": "claude-opus", "thinking": "xhigh", "verdict": "pass", "subject_pass": "no"}), "v", "r", "p")["model_ok"] is True)
    ci_9 = wilson_ci(9, 9)
    compound_v1 = project_record({
        "ts": "2026-11-15T00:00:00+00:00", "task": "readonly", "level": "medium", "class": "gemini-pro",
        "model": "gemini-4-hydrogen", "thinking": "high", "verdict": "partial", "first_pass": False, "retries": 1,
        "escalations": 0, "final_class": "gemini-pro", "error_kind": None,
        "note": "兩輪都因 15 分鐘無輸出被 T3 停掉；事後發現漏掉官方 cuda-gpu 變體，結論不可靠",
    }, pol=pol)
    ok("Schema v2 回溯與 Wilson CI：9/9 下限約 0.701，複合缺陷覆寫保護（逾時＋漏掉官方）強制標 model_ok=False 與 compound_defect",
       0.700 <= ci_9[0] <= 0.702 and ci_9[1] == 1.0
       and compound_v1["model_ok"] is False and compound_v1["failure_attribution"] == "compound_defect"
       and compound_v1["judged_model"] == "gemini-4-hydrogen")
    bad_fields = json.loads(json.dumps(pol))
    bad_fields["log"]["fields"] = ["ts", "final_model"]
    ok("政策檢查抓得到 log.fields 與 make_record 欄位漂移（如舊版誤寫 final_model）",
       any("log.fields" in e and "final_model" in e for e in check(bad_fields)))

    def rows(cls, n, passed, level="medium"):
        return [{"level": level, "class": cls, "first_pass": i < passed, "verdict": "pass" if i < passed else "fail",
                 "escalations": 0 if i < passed else 1} for i in range(n)]

    tr = dict(pol["trials"]["sonnet-trial"])
    p2 = {**pol, "trials": {"sonnet-trial": {**tr, "min_baseline": 5}}}
    s = stats(p2, rows("claude-sonnet", 19, 10) + rows("claude-opus", 10, 9))
    ok("試行：Sonnet 不到 20 筆時不判定", s["trials"]["sonnet-trial"][0]["verdict"].startswith("樣本不足"))
    s = stats(p2, rows("claude-sonnet", 20, 14) + rows("claude-opus", 10, 9))
    ok("試行：20 筆、70% 對 90%（低 20 個百分點）→ 退回 Opus",
       s["trials"]["sonnet-trial"][0]["revert"] and s["trials"]["sonnet-trial"][0]["gap_pp"] == 20.0)
    s = stats(p2, rows("claude-sonnet", 20, 17) + rows("claude-opus", 10, 9))
    ok("試行：85% 對 90%（低 5 個百分點）→ 繼續試行", not s["trials"]["sonnet-trial"][0]["revert"]
       and s["trials"]["sonnet-trial"][0]["verdict"].startswith("繼續"))
    s = stats(p2, rows("claude-sonnet", 20, 17) + rows("claude-opus", 3, 3) + rows("claude-opus", 10, 10, level="high"))
    ok("試行：只比同一級；Opus 在中級不夠基準數量時照實說基準不足",
       s["trials"]["sonnet-trial"][0]["verdict"].startswith("基準不足"))
    s = stats(p2, rows("claude-sonnet", 20, 20) + [{"level": "medium", "class": "claude-sonnet", "verdict": "skipped"}])
    ok("沒驗收的（skipped）不算進通過率", s["judged"] == 20 and s["table"][0]["first_pass_rate"] == 1.0)

    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp)
        path = log_path(state)
        append(path, rec)
        append(path, esc)
        path.open("a", encoding="utf-8").write("壞掉的一行\n")
        got, broken = read_log(path)
        ok("紀錄是一行一筆的 JSONL，讀不懂的行跳過並計數", len(got) == 2 and broken == 1 and got[1]["final_class"] == "claude-opus")

        th = pol["usage_signal"]["claude_weekly_threshold_pct"]
        ok("沒有快照：用量未知，over 是 None（不假設已達 80%）", weekly_usage(state, th)["over"] is None)
        t0 = 1_800_000_000
        os.environ["CLAUDE_CONFIG_DIR"] = str(state / "acct-a")
        capture(state, {"model": {"id": "claude-opus-5-5"}, "rate_limits": {
            "seven_day": {"used_percentage": 83.5, "resets_at": t0 + 86400}, "five_hour": {"used_percentage": 10, "resets_at": t0 + 3600}}}, now=t0)
        u = weekly_usage(state, th, now=t0 + 60)
        ok("狀態列快照：83.5% → 已達 80%", u["status"] == "ok" and u["over"] is True and u["pct"] == 83.5)
        ok("快照依帳號的設定資料夾分開：別的帳號查不到", weekly_usage(state, th, now=t0 + 60, which=str(state / "acct-b"))["status"] == "unknown")
        ok("快照超過 12 小時標 stale；這一週重置之後變未知",
           weekly_usage(state, th, now=t0 + 13 * 3600)["status"] == "stale"
           and weekly_usage(state, th, now=t0 + 86400 + 1)["status"] == "unknown")
        ok("沒有 rate_limits（API key 計費、還沒第一個回應）不覆蓋舊快照",
           capture(state, {"model": {}}) is None and weekly_usage(state, th, now=t0 + 60)["pct"] == 83.5)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)

        doc = Path(tmp) / "x.md"
        doc.write_text("# 說明\n\n```yaml\na: 1\n```\n", encoding="utf-8")
        ok("Markdown 裡的 yaml 區塊讀得到；檔案不存在回 None", block(doc) == {"a": 1} and block(Path(tmp) / "nope.md") is None)
        rules = Path(tmp) / "split" / "rules"
        rules.mkdir(parents=True)
        (rules / "dispatch.md").write_text("# 只有原則\n\n- 不為了品質而派\n", encoding="utf-8")
        ok("常駐的 dispatch.md 只有原則、沒有 yaml：當成沒有共用層，不報錯", policy(rules.parent) is None)
        (rules / "dispatch-policy.md").write_text("# 完整政策\n\n```yaml\nb: 2\n```\n", encoding="utf-8")
        ok("完整政策讀 dispatch-policy.md", policy(rules.parent) == {"b": 2} and policy_path(rules.parent).name == "dispatch-policy.md")
        (rules / "dispatch-policy.md").unlink()
        (rules / "dispatch.md").write_text("```yaml\nc: 3\n```\n", encoding="utf-8")
        ok("舊版把 yaml 放在 dispatch.md 的還讀得到", policy(rules.parent) == {"c": 3})

        # KIT-X-06：worktree 裡用 --git-common-dir 仍回到主 repo 名；日期／hash／skill 目錄名觸發提醒
        # 名稱壓短（P／w）並加 core.longpaths=true，避免 Windows CI 超長暫存路徑下 git worktree 撞內部 $GIT_DIR 上限
        main_repo = Path(tmp) / "P"
        wt_dir = Path(tmp) / "w"
        main_repo.mkdir()
        git_env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
        subprocess.run(["git", "-C", str(main_repo), "-c", "core.longpaths=true", "init", "-q"], check=True, env=git_env)
        subprocess.run(["git", "-C", str(main_repo), "config", "core.longpaths", "true"], check=True, env=git_env)
        (main_repo / "a.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(main_repo), "-c", "core.longpaths=true", "add", "a.txt"], check=True, env=git_env)
        subprocess.run(["git", "-C", str(main_repo), "-c", "core.longpaths=true", "commit", "-q", "-m", "init"], check=True, env=git_env)
        subprocess.run(["git", "-C", str(main_repo), "-c", "core.longpaths=true", "worktree", "add", "-q", "-b", "wt", str(wt_dir)], check=True, env=git_env)
        ok("project_name 在 git worktree 內取回主 repo 名，不被 worktree 目錄名污染",
           project_name(main_repo) == "P" and project_name(wt_dir) == "P")
        ok("looks_like_noise_project 偵測日期、hash 與 skill 子目錄名，正常專案名不誤判",
           looks_like_noise_project("2026-11-23-lineport-145f3fe3")
           and looks_like_noise_project("2026-11-24-claude-mem-f7ebcde3")
           and looks_like_noise_project("omnikit-dispatch")
           and not looks_like_noise_project("OmniKit")
           and not looks_like_noise_project("LinePort"))

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
