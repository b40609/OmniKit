# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""第 2 層排程提案（FR-26）：把第 1 層建議排實測的候選，依優先序排進每週的額度。

優先序 = 槽位權重 × 痛點 × 使用頻率 × 證據等級（docs/v2/research/eval.md 7.2）：
- 槽位權重：active 1、watch 0.3、frozen 不排。
- 痛點、使用頻率、每組的 token 量級：data/funnel/schedule.yaml（維護者可以改）。
- 證據等級：evidence.py 的等級，E0 1、E1 2、E2 3；可以查證的負面證據，優先序減半。
- 不排：凍結槽位、冷卻期、停滯或未知（第 0 層旗標）、同群不是代表的、卡片不是 pending 的。

每組實測 = 槽位現任 + 最多 2 個挑戰者（FR-25）。客觀實測的 token 估算 =
每次 token × 3 次 × (1 + 挑戰者數) × 2 個 agent；每週合計不超過 2,000 萬（含快取），盲選每週最多 2 次
（data/omnikit.yaml 的 eval.weekly_deep_limit）。單組就超過每週上限的，先拆成一個挑戰者一組；
還是超過就列在「排不進」，由維護者決定（例如只跑試點同事用的那個 agent）。

只是提案：結果寫 data/funnel/layer2-schedule.json（契約 contracts/layer2-schedule.schema.json），
維護者週報（digest.py）列出來；要不要照排、什麼時候跑，由維護者決定。

用法：uv run scripts/schedule.py [--today YYYY-MM-DD] [--start YYYY-MM-DD] [--weeks 6] [--no-usage] [--dry-run]
      uv run scripts/schedule.py --selftest
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import _omnikit
import batch0

FUNNEL = _omnikit.ROOT / "data" / "funnel"
CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
WEIGHT = {"active": 1.0, "watch": 0.3}
EVIDENCE_SCORE = {"E0": 1, "E1": 2, "E2": 3}
SKIP_FLAGS = {"cooling": "冷卻期", "stale": "停滯", "unknown": "未知"}
DEFAULTS = {"weekly_tokens": 20_000_000, "runs_per_arm": 3, "agents": 2, "max_challengers": 2,
            "tokens_per_run": {"short": 250_000, "medium": 1_000_000, "heavy": 3_900_000}}


def load_config(funnel):
    cfg = {**DEFAULTS, **(batch0.load_yaml(funnel / "schedule.yaml", {}) or {})}
    cfg["tokens_per_run"] = {**DEFAULTS["tokens_per_run"], **(cfg.get("tokens_per_run") or {})}
    cfg["slots"] = cfg.get("slots") or {}
    return cfg


def incumbents(slot_id, tools):
    """現任：試用中的優先（FR-25 比的是目前實際在用的），沒有就看預設。"""
    trial = [t["id"] for t in tools if slot_id in t["slots"] and t["status"] == "trial"]
    default = [t["id"] for t in tools if slot_id in t["slots"] and t["status"] == "default"]
    return trial or default


def pain(slot_id, tools, cfg):
    fixed = (cfg["slots"].get(slot_id) or {}).get("pain")
    if fixed:
        return int(fixed), "schedule.yaml"
    if any(slot_id in t["slots"] and t["status"] == "trial" for t in tools):
        return 2, "現任在試用"
    if not incumbents(slot_id, tools):
        return 3, "沒有現任"
    return 1, "現任夠用"


def usage_by_slot(tools, collect):
    """槽位裡的工具近 30 天的對話數；collect 丟例外就回 None（標「未知」，不當 0）。"""
    try:
        items = collect()["items"]
    except Exception:
        return None
    convs = {}
    for item in items:
        name = item["name"].split("@")[0].lower()
        convs[name] = convs.get(name, 0) + (item.get("conversations") or 0)
    out = {}
    for t in tools:
        names = {t["id"].lower(), t["name"].lower(), ((t.get("plugin") or {}).get("name") or "").lower()} - {""}
        hits = sum(convs.get(n, 0) for n in names)
        for slot in t["slots"]:
            out[slot] = out.get(slot, 0) + hits
    return out


def usage_score(slot_id, usage, cfg):
    fixed = (cfg["slots"].get(slot_id) or {}).get("usage")
    if fixed:
        return int(fixed), "schedule.yaml"
    if usage is None:
        return 2, "未知（讀不到使用紀錄）"
    n = usage.get(slot_id, 0)
    return (1 if n == 0 else 2 if n < 10 else 3), f"近 30 天 {n} 段對話"


def cluster_reps(clusters):
    """{tool: [同群代表]}：只收有多個成員、而且自己不是代表的。"""
    out = {}
    for by_key in clusters.values():
        for g in by_key.values():
            for m in g["members"]:
                if len(g["members"]) > 1 and m not in g["representatives"]:
                    out[m] = g["representatives"]
    return out


def candidates(roster, layer0, layer1, clusters, evidence, cfg, usage):
    """回傳（候選, 排除）。一個工具屬於多個槽位時，只排優先序最高的那個槽位。"""
    tools = list(roster["tools"].values())
    focus = {s["id"]: s["focus"] for s in roster["slots"]}
    l0 = {t["id"]: t for t in layer0.get("tools", [])}
    reps = cluster_reps(clusters)
    out, excluded = [], []
    for doc in layer1:
        tid = doc["tool_id"]
        if doc["recommendation"] != "deep_eval":
            continue
        tool = roster["tools"].get(tid)
        if not tool:
            continue
        if tool["status"] != "pending":
            excluded.append({"tool": tid, "reason": f"卡片狀態是 {tool['status']}"})
            continue
        flags = [SKIP_FLAGS[f["flag"]] for f in (l0.get(tid) or {}).get("flags", []) if f["flag"] in SKIP_FLAGS]
        if flags:
            excluded.append({"tool": tid, "reason": f"第 0 層：{'、'.join(flags)}"})
            continue
        if tid in reps:
            excluded.append({"tool": tid, "reason": f"同群代表是 {'、'.join(reps[tid])}"})
            continue
        slots = [s for s in (doc["slots"] or tool["slots"]) if WEIGHT.get(focus.get(s))]
        if not slots:
            excluded.append({"tool": tid, "reason": "沒有 active 或 watch 槽位"})
            continue
        ev = evidence.get(tid) or {"level": "E0", "effect": "none"}
        best = None
        for slot in slots:
            p, why_p = pain(slot, tools, cfg)
            u, why_u = usage_score(slot, usage, cfg)
            e = EVIDENCE_SCORE[ev["level"]]
            score = WEIGHT[focus[slot]] * p * u * e * (0.5 if ev["effect"] == "exclude_or_deprioritize" else 1)
            cand = {"tool": tid, "slot": slot, "priority": round(score, 2),
                    "factors": {"weight": WEIGHT[focus[slot]], "pain": p, "usage": u, "evidence": ev["level"]},
                    "notes": [f"痛點：{why_p}", f"使用頻率：{why_u}"]
                    + (["有可以查證的負面證據，優先序減半"] if ev["effect"] == "exclude_or_deprioritize" else [])}
            if best is None or cand["priority"] > best["priority"]:
                best = cand
        others = [s for s in slots if s != best["slot"]]
        if others:
            best["notes"].append(f"也屬於 {'、'.join(others)}，只排優先序最高的槽位")
        out.append(best)
    out.sort(key=lambda c: (-c["priority"], c["tool"]))
    return out, excluded


def test_cost(slot_cfg, n_challengers, cfg):
    per_run = cfg["tokens_per_run"][slot_cfg.get("size", "medium")]
    return per_run * cfg["runs_per_arm"] * (1 + n_challengers) * cfg["agents"]


def build_tests(cands, roster, cfg):
    """每個槽位依優先序，每 max_challengers 個挑戰者組成一組實測；客觀題超過每週上限就拆成一個一組。"""
    tools = list(roster["tools"].values())
    by_slot = {}
    for c in cands:
        by_slot.setdefault(c["slot"], []).append(c)
    tests = []
    for slot, items in by_slot.items():
        slot_cfg = cfg["slots"].get(slot) or {}
        judge = slot_cfg.get("judge", "objective")
        size = cfg["max_challengers"]
        if judge == "objective" and test_cost(slot_cfg, size, cfg) > cfg["weekly_tokens"]:
            size = 1
        for i in range(0, len(items), size):
            group = items[i:i + size]
            tokens = test_cost(slot_cfg, len(group), cfg)
            tests.append({"slot": slot, "judge": judge, "size": slot_cfg.get("size", "medium"),
                          "incumbent": incumbents(slot, tools), "challengers": [c["tool"] for c in group],
                          "priority": max(c["priority"] for c in group), "tokens_est": tokens,
                          "over_cap": judge == "objective" and tokens > cfg["weekly_tokens"]})
    tests.sort(key=lambda t: (-t["priority"], t["tokens_est"], t["slot"]))
    return tests


def place(tests, cfg, blind_limit, start, n_weeks):
    weeks = [{"start": (start + timedelta(weeks=i)).isoformat(), "tokens": 0, "blind": 0, "tests": []}
             for i in range(n_weeks)]
    unscheduled = []
    for t in tests:
        if t["over_cap"]:
            unscheduled.append({**t, "reason": "單組就超過每週 token 上限；請決定只跑一個 agent 或減少次數"})
            continue
        for w in weeks:
            if t["judge"] == "blind" and w["blind"] < blind_limit:
                w["blind"] += 1
                break
            if t["judge"] == "objective" and w["tokens"] + t["tokens_est"] <= cfg["weekly_tokens"]:
                w["tokens"] += t["tokens_est"]
                break
        else:
            unscheduled.append({**t, "reason": f"{n_weeks} 週內排不下"})
            continue
        w["tests"].append(t)
    return weeks, unscheduled


def next_monday(today):
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def plan(roster, funnel, today, start, n_weeks, collect=None):
    import evidence

    cfg = load_config(funnel)
    tools = list(roster["tools"].values())
    usage = usage_by_slot(tools, collect) if collect else None
    def read(name):
        path = funnel / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    layer0, clusters = read("layer0.json"), read("clusters.json")
    layer1 = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((funnel / "layer1").glob("*.json"))]
    ev = evidence.summary(funnel, today) if (funnel / "evidence").exists() else {}
    cands, excluded = candidates(roster, layer0, layer1, clusters, ev, cfg, usage)
    blind_limit = (roster["config"].get("eval") or {}).get("weekly_deep_limit", 2)
    weeks, unscheduled = place(build_tests(cands, roster, cfg), cfg, blind_limit, start, n_weeks)
    return {"generated": today.isoformat(), "start": start.isoformat(),
            "limits": {"weekly_tokens": cfg["weekly_tokens"], "weekly_blind": blind_limit,
                       "usage": "未知" if usage is None else "usage.py 近 30 天"},
            "weeks": weeks, "unscheduled": unscheduled, "candidates": cands, "excluded": excluded}


def fmt_tokens(n):
    return f"{n / 1_000_000:.1f}M"


def test_line(t):
    kind = "盲選" if t["judge"] == "blind" else f"客觀，約 {fmt_tokens(t['tokens_est'])} token"
    inc = "、".join(t["incumbent"]) or "內建功能"
    return f"{t['slot']}：{inc} 對 {'、'.join(t['challengers'])}（{kind}，優先序 {t['priority']:g}）"


def report(doc):
    lim = doc["limits"]
    lines = [f"# 第 2 層排程提案（{doc['generated']}；每週上限 {fmt_tokens(lim['weekly_tokens'])} token、盲選 {lim['weekly_blind']} 次；使用頻率：{lim['usage']}）"]
    for w in doc["weeks"]:
        if w["tests"]:
            lines.append(f"- {w['start']} 那週（客觀 {fmt_tokens(w['tokens'])}、盲選 {w['blind']} 次）：")
            lines += [f"  - {test_line(t)}" for t in w["tests"]]
    for t in doc["unscheduled"]:
        lines.append(f"- 排不進：{test_line(t)}：{t['reason']}")
    if doc["excluded"]:
        lines.append(f"- 不排 {len(doc['excluded'])} 張：" + "；".join(f"{e['tool']}（{e['reason']}）" for e in doc["excluded"]))
    return lines


def digest_lines(funnel, weeks=2):
    """給 digest.py：最近兩週的排程。沒有排程檔就回空清單。"""
    path = funnel / "layer2-schedule.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    lines = [f"## 第 2 層排程提案（{doc['generated']} 產生，data/funnel/layer2-schedule.json）"]
    shown = [w for w in doc["weeks"] if w["tests"]][:weeks]
    for w in shown:
        lines.append(f"- {w['start']} 那週：" + "；".join(test_line(t) for t in w["tests"]))
    if not shown:
        lines.append("- 沒有可以排的候選")
    if doc["unscheduled"]:
        lines.append(f"- 排不進 {len(doc['unscheduled'])} 組（看 schedule.py 的輸出）")
    return lines


# ---------- 自我測試 ----------

def selftest():
    import tempfile

    import jsonschema

    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    today = date(2026, 11, 5)
    slots = [{"id": "browser", "name": "B", "focus": "active"}, {"id": "frontend", "name": "F", "focus": "active"},
             {"id": "rules", "name": "R", "focus": "active"}, {"id": "docs", "name": "D", "focus": "watch"},
             {"id": "research", "name": "P", "focus": "frozen"}, {"id": "memory", "name": "M", "focus": "active"}]
    tools = {t["id"]: {"name": t["id"], "slots": [], "status": "pending", **t} for t in [
        {"id": "native-browser", "slots": ["browser"], "status": "default"},
        {"id": "devtools", "slots": ["browser"], "status": "trial"},
        {"id": "fd", "slots": ["frontend"], "status": "default"},
        {"id": "b1", "slots": ["browser"]}, {"id": "b2", "slots": ["browser"]}, {"id": "b3", "slots": ["browser"]},
        {"id": "f1", "slots": ["frontend"]}, {"id": "f2", "slots": ["frontend"]}, {"id": "f3", "slots": ["frontend"]},
        {"id": "r1", "slots": ["rules"]}, {"id": "d1", "slots": ["docs"]}, {"id": "p1", "slots": ["research"]},
        {"id": "cool", "slots": ["rules"]}, {"id": "twin", "slots": ["rules"]}, {"id": "done", "slots": ["rules"], "status": "rejected"},
        {"id": "m1", "slots": ["memory"]}, {"id": "m2", "slots": ["memory"]}, {"id": "multi", "slots": ["docs", "rules"]}]}
    roster = {"slots": slots, "tools": tools, "config": {"eval": {"weekly_deep_limit": 2}}}
    deep = ["b1", "b2", "b3", "f1", "f2", "f3", "r1", "d1", "p1", "cool", "twin", "done", "m1", "m2", "multi"]
    layer1 = [{"tool_id": t, "recommendation": "deep_eval", "slots": []} for t in deep] + \
             [{"tool_id": "x", "recommendation": "reject", "slots": ["rules"]}]
    layer0 = {"tools": [{"id": "cool", "flags": [{"flag": "cooling", "detail": "x"}]}]}
    clusters = {"rules": {"g": {"members": ["r1", "twin"], "representatives": ["r1"]}}}
    evidence = {"b1": {"level": "E2", "effect": "raise"}, "b2": {"level": "E1", "effect": "exclude_or_deprioritize"}}
    cfg = {**DEFAULTS, "slots": {"frontend": {"judge": "blind", "size": "heavy", "pain": 3},
                                 "browser": {"judge": "objective", "size": "short"},
                                 "memory": {"judge": "objective", "size": "heavy"},
                                 "docs": {"judge": "objective", "size": "medium"}}}
    usage = usage_by_slot(list(tools.values()), lambda: {"items": [
        {"name": "devtools@m", "conversations": 12}, {"name": "fd", "conversations": 3}]})
    check("使用紀錄依槽位加總", usage == {"browser": 12, "frontend": 3, "rules": 0, "docs": 0, "research": 0, "memory": 0})
    check("讀不到使用紀錄回 None", usage_by_slot(list(tools.values()), lambda: 1 / 0) is None)
    check("讀不到使用紀錄算 2 並標未知", usage_score("x", None, cfg) == (2, "未知（讀不到使用紀錄）"))
    cands, excluded = candidates(roster, layer0, layer1, clusters, evidence, cfg, usage)
    by = {c["tool"]: c for c in cands}
    why = {e["tool"]: e["reason"] for e in excluded}
    check("凍結槽位不排", "p1" not in by and "沒有 active" in why.get("p1", ""))
    check("冷卻期不排", "cool" not in by and "冷卻期" in why.get("cool", ""))
    check("同群不是代表的不排", "twin" not in by and "r1" in why.get("twin", ""))
    check("不是 pending 的不排", "done" not in by and "rejected" in why.get("done", ""))
    check("痛點：現任在試用 2、沒有現任 3、手動 3", by["b3"]["factors"]["pain"] == 2 and by["r1"]["factors"]["pain"] == 3
          and by["f1"]["factors"]["pain"] == 3)
    check("使用頻率：12 段算 3、3 段算 2、0 段算 1", by["b3"]["factors"]["usage"] == 3 and by["f1"]["factors"]["usage"] == 2
          and by["r1"]["factors"]["usage"] == 1)
    check("證據 E2 乘 3", by["b1"]["priority"] == 1 * 2 * 3 * 3)
    check("負面證據優先序減半", by["b2"]["priority"] == 1 * 2 * 3 * 2 * 0.5)
    check("watch 槽位權重 0.3", by["d1"]["priority"] == round(0.3 * 3 * 1 * 1, 2))
    check("多槽位只排優先序最高的", by["multi"]["slot"] == "rules" and any("docs" in n for n in by["multi"]["notes"]))
    tests = build_tests(cands, roster, cfg)
    browser = [t for t in tests if t["slot"] == "browser"]
    check("一組最多 2 個挑戰者，依優先序", [t["challengers"] for t in browser] == [["b1", "b2"], ["b3"]])
    check("試用中的當現任", browser[0]["incumbent"] == ["devtools"])
    check("token 估算 = 每次 × 3 次 × (1 + 挑戰者) × 2", browser[0]["tokens_est"] == 250_000 * 3 * 3 * 2)
    memory = [t for t in tests if t["slot"] == "memory"]
    check("重題超過上限就拆成一個一組，還是超過就標出來",
          [t["challengers"] for t in memory] == [["m1"], ["m2"]] and all(t["over_cap"] for t in memory))
    weeks, unscheduled = place(tests, cfg, 2, date(2026, 11, 9), 2)
    check("盲選每週最多 2 次", all(w["blind"] <= 2 for w in weeks)
          and sum(1 for w in weeks for t in w["tests"] if t["judge"] == "blind") == 2)
    check("客觀題每週不超過 token 上限", all(w["tokens"] <= cfg["weekly_tokens"] for w in weeks))
    check("超過上限的列在排不進", {tuple(t["challengers"]) for t in unscheduled if "單組" in t["reason"]} == {("m1",), ("m2",)})
    check("下週一", next_monday(today) == date(2026, 11, 9) and next_monday(date(2026, 11, 9)) == date(2026, 11, 16))
    with tempfile.TemporaryDirectory() as tmp:
        funnel = Path(tmp)
        doc = {"generated": "2026-11-05", "start": "2026-11-09",
               "limits": {"weekly_tokens": cfg["weekly_tokens"], "weekly_blind": 2, "usage": "未知"},
               "weeks": weeks, "unscheduled": unscheduled, "candidates": cands, "excluded": excluded}
        schema = json.loads((CONTRACTS / "layer2-schedule.schema.json").read_text(encoding="utf-8"))
        try:
            jsonschema.validate(doc, schema)
            check("輸出符合 contracts/layer2-schedule.schema.json", True)
        except jsonschema.ValidationError as e:
            check(f"輸出符合 contracts/layer2-schedule.schema.json（{e.message[:80]}）", False)
        check("沒有排程檔時 digest 不列", digest_lines(funnel) == [])
        batch0.dump_json(funnel / "layer2-schedule.json", doc)
        lines = digest_lines(funnel)
        check("digest 列出最近兩週", lines[0].startswith("## 第 2 層排程提案") and sum(1 for x in lines if "那週" in x) == 2)
        check("報表列出排不進與不排", any("排不進" in x for x in report(doc)) and any("不排" in x for x in report(doc)))
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    failed = [n for n, ok in checks if not ok]
    print(f"{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description="第 2 層排程提案")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--start", type=date.fromisoformat, help="第一週的週一，預設是下週一")
    parser.add_argument("--weeks", type=int, default=6, help="排幾週，預設 6（試點期）")
    parser.add_argument("--no-usage", action="store_true", help="不讀本機的使用紀錄")
    parser.add_argument("--dry-run", action="store_true", help="只印結果，不寫檔")
    args = parser.parse_args()
    _omnikit.utf8_stdout()
    if args.selftest:
        return selftest()
    import usage as usage_mod  # _omnikit 已把 engine/scripts 加進 sys.path

    collect = None if args.no_usage else (lambda: usage_mod.collect(Path.home(), days=30))
    doc = plan(_omnikit.roster(), FUNNEL, args.today, args.start or next_monday(args.today), args.weeks, collect)
    if not args.dry_run:
        batch0.dump_json(FUNNEL / "layer2-schedule.json", doc)
    print("\n".join(report(doc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
