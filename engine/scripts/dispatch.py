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
        [--first-pass yes|no] [--retries N] [--escalations N] [--final-class <類別>] [--channel native|agy_cli|t3_cli|delegate_task|t3_thread_launch]
        [--instance <實例>] [--level <級別>] [--project <名稱>] [--control] [--note <文字>] [--dry-run]
  uv run engine/scripts/dispatch.py stats [--json]                                   一次通過率與 Sonnet 試行的判定
  uv run engine/scripts/dispatch.py usage [--json]                                   本週 Claude 用量（快照）
  uv run engine/scripts/dispatch.py statusline [--then "<原本的狀態列指令>"]          給 Claude Code 狀態列用
  uv run engine/scripts/dispatch.py agy --class <類別> --thinking <程度> (--brief <文字> | --brief-file <檔>) [--cwd <資料夾>]
        [--timeout 秒] [--log-file <檔>]                                              用 agy 無頭派（visibility: headless；T3 看不到）
  uv run engine/scripts/dispatch.py --selftest
"""
import argparse
import json
import os
import re
import shutil
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
# 管道名稱要和共用層 channels 的 key 一致（check 會比對）。t3_cli：不在 T3 裡，用本機 t3 thread CLI 開 T3 對話。
CHANNELS = ("native", "agy_cli", "t3_cli", "delegate_task", "t3_thread_launch")
# 派給 Antigravity 時看不看得到過程：個人層 dispatch.md 的 visibility，沒寫用共用層 visibility.default（2026-11-21）。
VISIBILITY = ("visible", "headless")
AGY_MAX_BRIEF = 30000  # Windows 命令列上限約 32k 字元，任務說明走參數，留一點餘裕
AGENT_DRIVER = {"claude": "claudeAgent", "codex": "codex", "antigravity": "antigravity"}
FENCE = re.compile(r"```ya?ml\s*\n(.*?)\n```", re.S)
VERSION = re.compile(r"規則版本：\s*(\S+)")
STALE_HOURS = 12  # 快照超過這麼久，用量可能偏低（週用量只會往上加）


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
    for name, c in classes.items():
        for k in ("model", "driver", "default_thinking", "max_thinking"):
            if k not in c:
                errors.append(f"model_classes.{name} 少了 {k}")
        for k in ("default_thinking", "max_thinking"):
            if k in c and c[k] not in THINKING:
                errors.append(f"model_classes.{name}.{k} 不是 {THINKING} 之一：{c[k]}")
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


def instances_for(pol, mine, cls, agent="claude"):
    """這個模型類別可以用的實例，依序。目前的 agent 跟類別同一個供應商時，原生子代理（native）排第一。"""
    found = []
    if pol["model_classes"][cls].get("driver") == AGENT_DRIVER.get(agent) and cls.startswith(("claude-",)):
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


def resolved(pol, mine, agent="claude", judge=None, model_note=None, claude_order=None):
    """每一級的選項，加上可以用的實例；沒有實例的標 skip。
    judge（accounts.annotate 給的）：(實例, 模型) → (能不能自動派, 原因)；不能派的實例移到 blocked 並附原因。
    model_note：模型被淘汰過濾時回原因（整個選項跳過）。
    claude_order：依額度策略排好的 Claude 實例優先順序（工作包邊界挑）。"""
    configured_drivers = {(spec or {}).get("driver") for spec in ((mine or {}).get("instances") or {}).values() if (spec or {}).get("driver")}
    if AGENT_DRIVER.get(agent):
        configured_drivers.add(AGENT_DRIVER[agent])
    out = {}
    for level, lv in pol["levels"].items():
        tasks = [t for t, v in pol["tasks"].items() if v["level"] == level]
        rows = []
        for kind, items in (("prework", lv.get("prework") or []), ("route", lv.get("route") or []),
                            ("second_opinion", lv.get("second_opinion") or [])):
            for o in items:
                cls = pol["model_classes"][o["class"]]
                single_vendor_skip = kind == "second_opinion" and not (configured_drivers - {cls["driver"]})
                inst, blocked = ([] if single_vendor_skip else instances_for(pol, mine, o["class"], agent)), []
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
                filtered = model_note(cls["model"]) if model_note else ""
                th, th_why = effective_thinking(pol, o["class"], o["thinking"], level, kind, mine)
                rows.append({"kind": kind, "class": o["class"], "model": cls["model"], "thinking": th,
                             "policy_thinking": o["thinking"], "thinking_name": "effort" if cls["driver"] == "claudeAgent" else "thought_level",
                             "thinking_why": th_why, "when": o.get("when"), "tasks": o.get("tasks"),
                             "instances": [] if filtered else inst, "blocked": blocked, "filtered": filtered,
                             "single_vendor_skip": single_vendor_skip,
                             "skip": bool(filtered) or single_vendor_skip or not inst,
                             "trial": o.get("trial"), "pending": o.get("pending"), "note": o.get("note"), "role": o.get("role")})
        out[level] = {"name": lv.get("name", level), "tasks": tasks, "options": rows}
    return out


# ---------- 委派紀錄 ----------

def log_path(state):
    return Path(state) / "dispatch" / "log.jsonl"


def project_name(cwd=None):
    """專案名稱：所在 git repo 的資料夾名；不在 repo 裡就用目前資料夾名。只記名稱，不記完整路徑。"""
    cwd = Path(cwd or os.getcwd())
    try:
        r = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).name
    except (OSError, subprocess.TimeoutExpired):
        pass
    return cwd.name


def make_record(pol, args, version, profile, project, now=None):
    """命令列參數 → 一筆紀錄；不合政策的直接失敗（SystemExit），不寫半筆。"""
    tasks, classes = pol["tasks"], pol["model_classes"]
    if args.task not in tasks:
        raise SystemExit(f"任務類型不存在：{args.task}，可選：{'、'.join(tasks)}")
    level = args.level or tasks[args.task]["level"]
    if level not in pol["levels"]:
        raise SystemExit(f"級別不存在：{level}")
    for k in ("cls", "final_class"):
        v = getattr(args, k)
        if v and v not in classes:
            raise SystemExit(f"模型類別不存在：{v}，可選：{'、'.join(classes)}")
    if args.thinking not in THINKING:
        raise SystemExit(f"思考程度要是 {THINKING} 之一：{args.thinking}")
    top = classes[args.cls].get("max_thinking", "max")
    if THINKING.index(args.thinking) > THINKING.index(top):
        raise SystemExit(f"{args.cls} 的思考程度最高 {top}，寫了 {args.thinking}")
    if args.verdict not in VERDICTS:
        raise SystemExit(f"驗收結論要是 {VERDICTS} 之一：{args.verdict}")
    first = {"yes": True, "no": False, None: None}[args.first_pass]
    if first is None:  # 沒寫就從結論推：一次就過、沒有重跑與升級才算
        first = args.verdict == "pass" and not args.retries and not args.escalations
    if args.escalations and not args.final_class:
        raise SystemExit("有升級（--escalations）就要寫最後用哪個類別（--final-class）")
    error_kind = getattr(args, "error", None)
    error_text = getattr(args, "error_text", None)
    note = args.note
    if error_kind or error_text:
        import account_pool
        if error_kind and error_kind not in account_pool.ERROR_KINDS:
            raise SystemExit(f"錯誤種類不存在：{error_kind}，可選：{'、'.join(account_pool.ERROR_KINDS)}")
        if not error_kind and error_text:
            c = account_pool.classify_error(error_text, model=classes[args.cls]["model"], now=now)
            error_kind = c["kind"]
            if not note:
                note = c["summary"]
    return {
        "ts": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "project": args.project or project, "task": args.task, "level": level,
        "channel": args.channel, "instance": args.instance or ("native" if args.channel == "native" else None),
        "class": args.cls, "model": classes[args.cls]["model"], "thinking": args.thinking,
        "first_pass": first, "retries": args.retries, "escalations": args.escalations,
        "final_class": args.final_class or args.cls, "verdict": args.verdict,
        "error_kind": error_kind,
        "rules_version": version, "profile": profile, "control": bool(args.control), "note": note,
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


# ---------- 統計與試行判定 ----------

def rate(rows):
    return (sum(1 for r in rows if r.get("first_pass")) / len(rows)) if rows else None


def stats(pol, rows):
    """一次通過率（依級別與一開始派的類別分組；沒驗收的 skipped 不算），以及每個試行的判定。"""
    judged = [r for r in rows if r.get("verdict") != "skipped"]
    groups = {}
    for r in judged:
        groups.setdefault((r.get("level"), r.get("class")), []).append(r)
    table = [{"level": lv, "class": c, "n": len(g), "first_pass_rate": rate(g),
              "escalated": sum(1 for r in g if r.get("escalations"))} for (lv, c), g in sorted(groups.items(), key=str)]
    trials = {}
    for name, tr in (pol.get("trials") or {}).items():
        mine = [r for r in judged if r.get("class") == tr["class"]]
        levels = sorted({r.get("level") for r in mine}, key=str)
        per = []
        for lv in levels:
            a = [r for r in mine if r.get("level") == lv]
            b = [r for r in judged if r.get("class") == tr["baseline"] and r.get("level") == lv]
            ra, rb = rate(a), rate(b)
            gap = None if ra is None or rb is None else round((rb - ra) * 100, 1)
            if len(a) < tr["min_samples"]:
                verdict = f"樣本不足：{tr['class']} 有 {len(a)} 筆，要 {tr['min_samples']} 筆"
            elif len(b) < tr.get("min_baseline", 1):
                verdict = f"基準不足：{tr['baseline']} 在這一級有 {len(b)} 筆，要 {tr.get('min_baseline', 1)} 筆（見 trials.{name}.note）"
            elif gap >= tr["max_gap_pp"]:
                verdict = f"退回：{tr['class']} 比 {tr['baseline']} 低 {gap} 個百分點（門檻 {tr['max_gap_pp']}）"
            else:
                verdict = f"繼續試行：差距 {gap} 個百分點，低於門檻 {tr['max_gap_pp']}"
            per.append({"level": lv, "trial_n": len(a), "trial_rate": ra, "baseline_n": len(b), "baseline_rate": rb,
                        "gap_pp": gap, "verdict": verdict, "revert": verdict.startswith("退回")})
        trials[name] = per or [{"verdict": f"樣本不足：{tr['class']} 還沒有紀錄", "revert": False}]
    return {"total": len(rows), "judged": len(judged), "table": table, "trials": trials}


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


def weekly_usage(state, threshold, now=None, which=None):
    """本週 Claude 用量：{status: ok|stale|unknown, pct, over, resets_at, age_hours, why}。
    unknown 時 over 是 None：不知道就不要假設已達門檻。"""
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


def show_text(table, profile, has_personal, usage=None, pol=None, mine=None, accounts=None, pool_lines=None):
    prefs = []
    if mine:
        if mine.get("thinking_preference"):
            prefs.append(f"thinking_preference: {mine['thinking_preference']}")
        if mine.get("on_exhausted"):
            prefs.append(f"on_exhausted: {mine['on_exhausted']}")
    pref_str = f"；{'，'.join(prefs)}" if prefs else ""
    lines = [f"profile：{profile}；{'個人實例：有' if has_personal else '沒有個人分派設定，只用原生子代理'}{pref_str}"]
    if usage:
        lines.append(usage_text(usage))
    for level, lv in table.items():
        lines.append(f"\n{lv['name']}（{level}）：{'、'.join(lv['tasks']) or '—'}")
        route = [o for o in lv["options"] if o["kind"] == "route"]
        for o in lv["options"]:
            head = {"prework": "前置", "second_opinion": "第二意見"}.get(o["kind"]) or f"{route.index(o) + 1}."
            inst = (f"已過濾，跳過（{o['filtered']}）" if o.get("filtered") else
                    "單一供應商無跨家對象，跳過" if o.get("single_vendor_skip") else
                    ("沒有可自動派的實例，跳過" if o.get("blocked") else "沒有實例，跳過") if o["skip"] else
                    "實例：" + "、".join(o["instances"]))
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


def stats_text(s):
    lines = [f"委派紀錄 {s['total']} 筆，有驗收的 {s['judged']} 筆"]
    for r in s["table"]:
        pct = "—" if r["first_pass_rate"] is None else f"{r['first_pass_rate'] * 100:.1f}%"
        lines.append(f"  {r['level']} / {r['class']}：{r['n']} 筆，一次通過 {pct}，升級 {r['escalated']} 筆")
    for name, per in s["trials"].items():
        for p in per:
            lines.append(f"試行 {name}{'（' + p['level'] + '）' if p.get('level') else ''}：{p['verdict']}")
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
    """這台的 data、state、選的 profile 與它的資料夾。"""
    data, state = profiles.DATA, profiles.STATE
    name, _ = profiles.resolve(data, state)
    return data, state, name, profiles.folder(data, state, name)


def main(argv=None):
    ap = argparse.ArgumentParser(description="子任務分派：政策、委派紀錄、試行比較、本週 Claude 用量")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("show")
    p.add_argument("--agent", choices=list(AGENT_DRIVER), default="claude")
    p.add_argument("--json", action="store_true")
    sub.add_parser("check")
    p = sub.add_parser("log")
    p.add_argument("--task", required=True)
    p.add_argument("--class", dest="cls", required=True)
    p.add_argument("--thinking", required=True)
    p.add_argument("--verdict", required=True)
    p.add_argument("--first-pass", choices=["yes", "no"])
    p.add_argument("--retries", type=int, default=0)
    p.add_argument("--escalations", type=int, default=0)
    p.add_argument("--final-class")
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
        table = resolved(pol, mine, args.agent, judge, model_note, claude_order=c_sel.get("ordered"))
        u = weekly_usage(state, th)
        plines = []
        if c_sel.get("chosen"):
            plines.append(f"  Claude 實例推薦（工作包邊界挑，同一條不中途換）：{c_sel['chosen']}（{c_sel['reason']}）")
        plines.append("")
        plines += account_pool.failover_text(plan).splitlines()
        if alerts:
            plines.append("\n帳號警示：")
            plines += [f"  [{a['severity']}] {a['message']}" for a in alerts]
        print(json.dumps({"usage": u, "claude_quotas": c_quotas, "claude_selection": c_sel,
                          "levels": table, "channels": pol.get("channels"), "accounts": rows,
                          "filtered_models": filtered, "model_hints": hints, "failover": plan,
                          "alerts": alerts, "visibility": visibility(pol, mine),
                          "thinking_preference": (mine or {}).get("thinking_preference"),
                          "on_exhausted": (mine or {}).get("on_exhausted")}, ensure_ascii=False, indent=2)
              if args.json else show_text(table, name, mine is not None, u, pol, mine, account_lines(rows, filtered, hints), plines))
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
        if pool_msg:
            print(f"帳號池狀態：{pool_msg}")
        return 0
    if args.cmd == "stats":
        rows, bad = read_log(log_path(state))
        s = stats(pol, rows)
        s["unreadable_lines"] = bad
        print(json.dumps(s, ensure_ascii=False, indent=2) if args.json else stats_text(s) + (f"\n讀不懂的行：{bad}" if bad else ""))
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
    ryan = personal(profiles.DATA / "profiles" / "ryan")
    ok("repo 裡的共用層與 ryan 的個人層通過檢查", check(pol, ryan) == [])
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
    shown = show_text(resolved(pol, ryan, "claude"), "ryan", True, None, pol, ryan)
    ok("show 的輸出列出每個管道，包含 t3_cli", all(f"  {c}：" in shown for c in CHANNELS))
    vr = visibility(pol, ryan)
    ok("ryan 的 visibility 是 visible（profile 設定）：show 依序印 delegate_task、t3_thread_launch、t3_cli 與退路",
       vr["mode"] == "visible" and vr["source"] == "profile"
       and [c["channel"] for c in vr["channels"]] == ["delegate_task", "t3_thread_launch", "t3_cli"]
       and "偏好 visible（profile 的 dispatch.md）" in shown and "1. delegate_task：" in shown and "退路：" in shown)
    vh = visibility(pol, {"instances": {}, "visibility": "headless"})
    hs = show_text(resolved(pol, ryan, "claude"), "x", True, None, pol, {"visibility": "headless"})
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

    t = resolved(pol, ryan, "claude")
    med = t["medium"]["options"]
    # 2026-11-25 定案：讀檔／雜務（docs、readonly）用 Hydrogen xhigh 或 Opus medium；多檔／UI 用 Neon xhigh 或 Opus high；Sonnet 留作試行退路
    ok("ryan：中級 docs/readonly 首選 Hydrogen xhigh，多檔／UI 首選 Neon xhigh，選項名稱為 thought_level；Claude 維持政策 effort 不被 max_available 拉到 max",
       med[0]["class"] == "gemini-fast" and med[0]["model"] == "gemini-4-hydrogen"
       and med[0]["thinking"] == "xhigh" and med[0]["instances"] == ["antigravity_ryan"]
       and med[0]["thinking_name"] == "thought_level" and med[0]["tasks"] == ["docs", "readonly"]
       and med[1]["class"] == "gemini-pro" and med[1]["model"] == "gemini-4-neon"
       and med[1]["thinking"] == "xhigh" and med[1]["thinking_name"] == "thought_level"
       and any(o["class"] == "claude-opus" and o["thinking"] == "medium" and o["tasks"] == ["docs", "readonly"] for o in med)
       and any(o["class"] == "claude-opus" and o["thinking"] == "high" and o["tasks"] == ["ui-small", "code-small"] for o in med)
       and med[-1]["class"] == "claude-sonnet")
    ov_t = resolved(pol, {**ryan, "effort_overrides": {"claude-opus": "medium"}}, "claude")
    ok("個人層 effort_overrides 可覆寫特定類別／級別的思考程度，不合法覆寫會被 check 擋下",
       [o for o in ov_t["verify"]["options"] if o["class"] == "claude-opus"][0]["thinking"] == "medium"
       and [o for o in ov_t["verify"]["options"] if o["class"] == "claude-opus"][0]["thinking_why"] == "effort_overrides: claude-opus"
       and any("effort_overrides" in e for e in check(pol, {"effort_overrides": {"gemini-pro": "low"}})))
    econ = resolved(pol, {**ryan, "thinking_preference": "economy"}, "claude")
    ok("thinking_preference: economy 降一般任務一檔（Neon/Hydrogen xhigh→high、Sonnet medium→low），但絕不把 Gemini 降到禁用的 medium／low",
       [o for o in econ["medium"]["options"] if o["class"] == "gemini-pro"][0]["thinking"] == "high"
       and [o for o in econ["medium"]["options"] if o["class"] == "gemini-fast"][0]["thinking"] == "high"
       and [o for o in econ["medium"]["options"] if o["class"] == "claude-sonnet"][0]["thinking"] == "low")
    ok("個人層 thinking_preference、on_exhausted、account_strategy、notify 寫錯會報錯",
       len(check(pol, {"thinking_preference": "ultra", "on_exhausted": "spin", "account_strategy": "rng", "notify": "sms"})) == 4)
    ord_t = resolved(pol, ryan, "claude", claude_order=["claudeAgent_2", "claudeAgent_claude_kai", "claudeAgent"])
    ok("claude_order 依額度策略排實例順序，native 仍排第一",
       [o for o in ord_t["high"]["options"] if o["class"] == "claude-opus"][0]["instances"]
       == ["native", "claudeAgent_2", "claudeAgent_claude_kai", "claudeAgent"])
    tj = resolved(pol, ryan, "claude", lambda i, m: (i != "claudeAgent_2", "測試：停用"),
                  lambda m: "測試：過濾" if m == "gemini-4-hydrogen" else "")
    son = [o for o in tj["medium"]["options"] if o["class"] == "claude-sonnet"][0]
    fl = [o for o in tj["medium"]["options"] if o["class"] == "gemini-fast"][0]
    ok("judge 不能派的實例移到 blocked 附原因；被過濾的模型整個選項跳過",
       "claudeAgent_2" not in son["instances"] and son["blocked"] == [{"instance": "claudeAgent_2", "why": "測試：停用"}]
       and fl["skip"] and fl["filtered"] == "測試：過濾"
       and "已過濾，跳過（測試：過濾）" in show_text(tj, "ryan", True) and "不派 claudeAgent_2：測試：停用" in show_text(tj, "ryan", True))
    ok("Claude 類別在 Claude 底下原生子代理排第一",
       [o for o in t["high"]["options"] if o["class"] == "claude-fable"][0]["instances"][0] == "native"
       and [o for o in t["high"]["options"] if o["class"] == "claude-opus"][0]["instances"][0] == "native")
    high_routes = [o["class"] for o in t["high"]["options"] if o["kind"] == "route"]
    ok("ryan：high 含 synthesis／major-change 且首選 Fable 5.2 high 與 Carbon high；verify／higher 維持 Opus xhigh；雙向對等跨家審查齊備",
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
       and "審 Gemini Carbon／Neon 重要產出時升 Fable 5.2 high" in show_text(t, "ryan", True))

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
    shown_turns = show_text(resolved(pol, ryan, "claude"), "ryan", True, None, pol)
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
    rec = make_record(pol, ns(**base), "2026-11-14-1", "ryan", "OmniKit", now)
    need = ["ts", "project", "task", "level", "instance", "model", "thinking", "first_pass", "retries", "escalations", "verdict", "rules_version"]
    ok("紀錄有必填欄位；級別從任務類型推；沒寫 first-pass 時，一次就過才算",
       all(k in rec for k in need) and rec["level"] == "medium" and rec["first_pass"] is True
       and rec["model"] == "claude-sonnet-5-5" and rec["instance"] == "native")
    t3rec = make_record(pol, ns(**{**base, "cls": "gemini-fast", "thinking": "xhigh", "channel": "t3_cli",
                                   "instance": "antigravity_ryan"}), "v", "ryan", "p", now)
    p_log = argparse.ArgumentParser(exit_on_error=False)
    p_log.add_argument("--channel", choices=CHANNELS)
    ok("log 收 t3_cli 管道，實例照寫（antigravity_ryan）",
       t3rec["channel"] == "t3_cli" and t3rec["instance"] == "antigravity_ryan"
       and p_log.parse_args(["--channel", "t3_cli"]).channel == "t3_cli")
    esc = make_record(pol, ns(**{**base, "verdict": "pass", "escalations": 1, "final_class": "claude-opus"}), "v", "ryan", "p", now)
    ok("Sonnet 驗收不過、改 Opus 重跑：記成一行，class 是一開始派的 Sonnet，first_pass 是 false",
       esc["class"] == "claude-sonnet" and esc["final_class"] == "claude-opus" and esc["first_pass"] is False)
    erec = make_record(pol, ns(**{**base, "verdict": "fail", "error": None,
                                  "error_text": "HTTP 429 weekly quota exhausted Bearer tok-secret-999999"}), "v", "ryan", "p", now)
    ok("log --error-text 自動分類錯誤並寫進 error_kind，note 遮罩 token",
       erec["error_kind"] == "quota_exhausted" and "tok-secret" not in (erec["note"] or "") and "[REDACTED]" in (erec["note"] or ""))
    ok("不合政策的不寫：任務類型、類別、思考程度（含超過類別上限）、結論寫錯，或有升級卻沒寫最後的類別",
       fails(lambda: make_record(pol, ns(**{**base, "task": "x"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "cls": "x"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "thinking": "huge"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "cls": "antigravity-opus", "thinking": "xhigh"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "verdict": "ok"}), "v", "r", "p"))
       and fails(lambda: make_record(pol, ns(**{**base, "escalations": 1}), "v", "r", "p")))

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

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
