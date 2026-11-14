# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""子任務分派：讀分派政策、寫委派紀錄、算 Sonnet 試行的比較、讀本週 Claude 用量。

政策分兩層，都是 Markdown 檔裡的一個 ```yaml 區塊（agent 載入規則時讀得懂，這支腳本也讀得到）：
- data/rules/dispatch.md：共用層，所有人都套用（任務類型 → 級別 → 模型類別 → 思考程度 → 升級）
- <profile>/dispatch.md：個人層，自己有哪些供應商實例、每個類別用哪個；沒有就只用原生子代理
profiles.py 把兩份接進 Claude Code、Codex 與 Antigravity 的規則；這支不改規則，只讀。

委派紀錄存在本機 %LOCALAPPDATA%\\omnikit\\dispatch\\log.jsonl（一次委派一行，不進 repo、不上傳）。
這份紀錄之後要拿來依數據調整分派規則；這支只負責記錄與計算，不會自己改規則。

本週 Claude 用量：Claude Code 狀態列的 JSON 輸入有 rate_limits.seven_day.used_percentage
（https://code.claude.com/docs/en/statusline）。`statusline` 子指令可以設成狀態列指令（或串在原本的前面），
把它存成 %LOCALAPPDATA%\\omnikit\\dispatch\\claude-usage.json；`usage` 讀這份快照。
T3 透過 Agent SDK 跑 Claude 時狀態列會不會執行，還沒實測（待驗證）。

用法：
  uv run engine/scripts/dispatch.py show [--agent claude|codex|antigravity] [--json]   套上這台 profile 之後的分派表
  uv run engine/scripts/dispatch.py check                                            檢查兩層政策
  uv run engine/scripts/dispatch.py log --task <類型> --class <類別> --thinking <程度> --verdict pass|fail|partial|skipped
        [--first-pass yes|no] [--retries N] [--escalations N] [--final-class <類別>] [--channel native|delegate_task|t3_thread_launch]
        [--instance <實例>] [--level <級別>] [--project <名稱>] [--control] [--note <文字>] [--dry-run]
  uv run engine/scripts/dispatch.py stats [--json]                                   一次通過率與 Sonnet 試行的判定
  uv run engine/scripts/dispatch.py usage [--json]                                   本週 Claude 用量（快照）
  uv run engine/scripts/dispatch.py statusline [--then "<原本的狀態列指令>"]          給 Claude Code 狀態列用
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
CHANNELS = ("native", "delegate_task", "t3_thread_launch")
AGENT_DRIVER = {"claude": "claudeAgent", "codex": "codex", "antigravity": "antigravity"}
FENCE = re.compile(r"```ya?ml\s*\n(.*?)\n```", re.S)
VERSION = re.compile(r"規則版本：\s*(\S+)")
STALE_HOURS = 12  # 快照超過這麼久，用量可能偏低（週用量只會往上加）


# ---------- 讀政策 ----------

def block(path):
    """Markdown 檔裡第一個 ```yaml 區塊；檔案不存在回 None。"""
    if not Path(path).is_file():
        return None
    m = FENCE.search(Path(path).read_bytes().decode("utf-8-sig").replace("\r\n", "\n"))
    if not m:
        raise ValueError(f"{path}：找不到 ```yaml 區塊")
    doc = yaml.safe_load(m.group(1))
    if not isinstance(doc, dict):
        raise ValueError(f"{path}：yaml 區塊不是對照表")
    return doc


def policy(data):
    return block(Path(data) / "rules" / "dispatch.md")


def personal(profile_dir):
    return block(Path(profile_dir) / "dispatch.md") if profile_dir else None


def rules_version(data):
    m = VERSION.search((Path(data) / "rules" / "baseline.md").read_text(encoding="utf-8"))
    return m.group(1) if m else "unknown"


def options(pol, level):
    lv = pol["levels"][level]
    return list(lv.get("route") or []) + list(lv.get("second_opinion") or [])


def check(pol, mine=None):
    """兩層政策的跨欄位檢查，回傳問題清單。"""
    errors = []
    classes = pol.get("model_classes") or {}
    levels = pol.get("levels") or {}
    for key in ("model_classes", "tasks", "levels", "escalation", "channels", "usage_signal", "trials", "log"):
        if key not in pol:
            errors.append(f"共用層少了 {key}")
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
    for i, e in enumerate(pol.get("escalation") or []):
        for k in ("from", "to"):
            v = e.get(k)
            v = v.get("class") if isinstance(v, dict) else v
            if v not in classes and v not in ("level", "higher") and v not in levels:
                errors.append(f"escalation 第 {i + 1} 條的 {k} 不認得：{v}")
    if mine is not None:
        for inst, spec in (mine.get("instances") or {}).items():
            spec = spec or {}
            for cls in spec.get("classes") or []:
                if cls not in classes:
                    errors.append(f"個人層 instances.{inst}：模型類別不存在：{cls}")
                elif spec.get("driver") and classes[cls].get("driver") != spec["driver"]:
                    errors.append(f"個人層 instances.{inst}：{cls} 要用 {classes[cls]['driver']} 的實例，這個是 {spec['driver']}")
    return errors


def instances_for(pol, mine, cls, agent="claude"):
    """這個模型類別可以用的實例，依序。目前的 agent 跟類別同一個供應商時，原生子代理（native）排第一。"""
    found = []
    if pol["model_classes"][cls].get("driver") == AGENT_DRIVER.get(agent) and cls.startswith(("claude-",)):
        found.append("native")
    for inst, spec in ((mine or {}).get("instances") or {}).items():
        if cls in ((spec or {}).get("classes") or []):
            found.append(inst)
    return found


def resolved(pol, mine, agent="claude"):
    """每一級的選項，加上可以用的實例；沒有實例的標 skip。"""
    out = {}
    for level, lv in pol["levels"].items():
        tasks = [t for t, v in pol["tasks"].items() if v["level"] == level]
        rows = []
        for kind, items in (("route", lv.get("route") or []), ("second_opinion", lv.get("second_opinion") or [])):
            for o in items:
                cls = pol["model_classes"][o["class"]]
                inst = instances_for(pol, mine, o["class"], agent)
                rows.append({"kind": kind, "class": o["class"], "model": cls["model"], "thinking": o["thinking"],
                             "thinking_name": "effort" if cls["driver"] == "claudeAgent" else "thinking_level",
                             "when": o.get("when"), "tasks": o.get("tasks"), "instances": inst, "skip": not inst,
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
    return {
        "ts": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "project": args.project or project, "task": args.task, "level": level,
        "channel": args.channel, "instance": args.instance or ("native" if args.channel == "native" else None),
        "class": args.cls, "model": classes[args.cls]["model"], "thinking": args.thinking,
        "first_pass": first, "retries": args.retries, "escalations": args.escalations,
        "final_class": args.final_class or args.cls, "verdict": args.verdict,
        "rules_version": version, "profile": profile, "control": bool(args.control), "note": args.note,
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
                verdict = f"基準不足：{tr['baseline']} 在這一級有 {len(b)} 筆，要 {tr.get('min_baseline', 1)} 筆（見 trials.{name}.pending）"
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


def config_dir():
    """這個 Claude Code 用的設定資料夾：不同帳號常用不同的 CLAUDE_CONFIG_DIR，快照依它分開。"""
    return os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")


def capture(state, payload, now=None):
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
    doc[config_dir()] = snap
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
    snap = doc.get(which or config_dir())
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


def show_text(table, profile, has_personal, usage=None):
    lines = [f"profile：{profile}；{'個人實例：有' if has_personal else '沒有個人分派設定，只用原生子代理'}"]
    if usage:
        lines.append(usage_text(usage))
    for level, lv in table.items():
        lines.append(f"\n{lv['name']}（{level}）：{'、'.join(lv['tasks']) or '—'}")
        for i, o in enumerate(lv["options"], 1):
            head = "第二意見" if o["kind"] == "second_opinion" else f"{i}."
            inst = "沒有實例，跳過" if o["skip"] else "實例：" + "、".join(o["instances"])
            extra = (f"；條件：{o['when']}" if o["when"] else "") + (f"；只接：{'、'.join(o['tasks'])}" if o["tasks"] else "")
            lines.append(f"  {head} {o['class']}（{o['model']}）{o['thinking_name']} {o['thinking']}；{inst}{extra}")
            if o["pending"]:
                lines.append(f"     {o['pending'].strip()}")
    return "\n".join(lines)


def stats_text(s):
    lines = [f"委派紀錄 {s['total']} 筆，有驗收的 {s['judged']} 筆"]
    for r in s["table"]:
        pct = "—" if r["first_pass_rate"] is None else f"{r['first_pass_rate'] * 100:.1f}%"
        lines.append(f"  {r['level']} / {r['class']}：{r['n']} 筆，一次通過 {pct}，升級 {r['escalated']} 筆")
    for name, per in s["trials"].items():
        for p in per:
            lines.append(f"試行 {name}{'（' + p['level'] + '）' if p.get('level') else ''}：{p['verdict']}")
    return "\n".join(lines)


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
    p.add_argument("--note")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("stats")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("usage")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("statusline")
    p.add_argument("--then", help="原本的狀態列指令：收到的 JSON 照樣轉給它，印它的輸出")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "statusline":  # 狀態列：任何錯誤都安靜，不能干擾畫面
        raw = sys.stdin.buffer.read()
        snap = None
        try:
            snap = capture(profiles.STATE, json.loads(raw.decode("utf-8") or "{}"))
        except Exception:  # noqa: BLE001
            pass
        if args.then:
            # Claude Code 在 Windows 上用 Git Bash 跑狀態列指令；原本的指令照同一個 shell 跑，寫法才對得上
            bash = shutil.which("bash") if os.name == "nt" else None
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
        table = resolved(pol, mine, args.agent)
        u = weekly_usage(state, pol["usage_signal"]["claude_weekly_threshold_pct"])
        print(json.dumps({"usage": u, "levels": table}, ensure_ascii=False, indent=2) if args.json
              else show_text(table, name, mine is not None, u))
        return 0
    if args.cmd == "log":
        rec = make_record(pol, args, rules_version(data), name, project_name())
        if not args.dry_run:
            append(log_path(state), rec)
        print(json.dumps(rec, ensure_ascii=False))
        print(("（預覽，沒有寫入）" if args.dry_run else f"已記到 {log_path(state)}"))
        return 0
    if args.cmd == "stats":
        rows, bad = read_log(log_path(state))
        s = stats(pol, rows)
        s["unreadable_lines"] = bad
        print(json.dumps(s, ensure_ascii=False, indent=2) if args.json else stats_text(s) + (f"\n讀不懂的行：{bad}" if bad else ""))
        return 0
    if args.cmd == "usage":
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
    ok("每一級、每個選項都寫明思考程度（不靠預設值）",
       all(o.get("thinking") in THINKING for lv in pol["levels"] for o in options(pol, lv)))

    bad = json.loads(json.dumps(pol))
    bad["levels"]["medium"]["route"][1]["thinking"] = "low"
    bad["levels"]["high"]["route"][0]["thinking"] = "xhigh"
    bad["levels"]["higher"]["route"][0].pop("thinking")
    bad["tasks"]["docs"]["level"] = "nope"
    errs = check(bad, {"instances": {"x": {"driver": "antigravity", "classes": ["claude-opus", "nope"]}}})
    ok("檢查抓得到：禁用的 low、超過上限、沒寫思考程度、不存在的級別、實例對錯供應商、不存在的類別",
       any("禁用" in e for e in errs) and any("最高 high" in e for e in errs) and any("不要靠預設值" in e for e in errs)
       and any("tasks.docs" in e for e in errs) and any("要用 claudeAgent 的實例" in e for e in errs)
       and any("類別不存在：nope" in e for e in errs))

    t = resolved(pol, ryan, "claude")
    med = t["medium"]["options"]
    ok("ryan：中級第一個 Gemini 選項是 Hydrogen（antigravity，thinking_level high），Flash 用 ava、kai",
       [o for o in med if o["class"] == "gemini-pro"][0]["instances"] == ["antigravity"]
       and [o for o in med if o["class"] == "gemini-flash"][0]["instances"] == ["antigravity_ava", "antigravity_kai"]
       and [o for o in med if o["class"] == "gemini-pro"][0]["thinking_name"] == "thinking_level")
    ok("Claude 類別在 Claude 底下原生子代理排第一", t["high"]["options"][-1]["instances"][0] == "native")
    bare = resolved(pol, None, "claude")
    ok("沒有個人層（同事只有 Claude）：Gemini 與 Antigravity 選項全部跳過，中級退回 Sonnet effort medium",
       all(o["skip"] for lv in bare.values() for o in lv["options"] if not o["class"].startswith("claude-"))
       and any(o["class"] == "claude-sonnet" and o["thinking"] == "medium" and not o["skip"] for o in bare["medium"]["options"]))

    ns = argparse.Namespace
    base = dict(task="docs", cls="claude-sonnet", thinking="medium", verdict="pass", first_pass=None, retries=0, escalations=0,
                final_class=None, channel="native", instance=None, level=None, project=None, control=False, note=None)
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    rec = make_record(pol, ns(**base), "2026-11-14-1", "ryan", "OmniKit", now)
    need = ["ts", "project", "task", "level", "instance", "model", "thinking", "first_pass", "retries", "escalations", "verdict", "rules_version"]
    ok("紀錄有必填欄位；級別從任務類型推；沒寫 first-pass 時，一次就過才算",
       all(k in rec for k in need) and rec["level"] == "medium" and rec["first_pass"] is True
       and rec["model"] == "claude-sonnet-5-5" and rec["instance"] == "native")
    esc = make_record(pol, ns(**{**base, "verdict": "pass", "escalations": 1, "final_class": "claude-opus"}), "v", "ryan", "p", now)
    ok("Sonnet 驗收不過、改 Opus 重跑：記成一行，class 是一開始派的 Sonnet，first_pass 是 false",
       esc["class"] == "claude-sonnet" and esc["final_class"] == "claude-opus" and esc["first_pass"] is False)
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

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
