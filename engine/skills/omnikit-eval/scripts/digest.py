# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""每週彙整：試用快到期、這段期間新進的工具、本週的深度評估額度、建議這週評估的槽位，
以及這台電腦 30 天沒用到的 skill 與 plugin（engine/scripts/usage.py 讀本機紀錄）。輸出 Markdown。

平常新工具只記進名冊，不逐筆通知；每週看一次這份彙整。

用法：uv run scripts/digest.py [--since YYYY-MM-DD] [--today YYYY-MM-DD] [--usage-days 30] [--no-usage]
"""
import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import _omnikit
import usage  # noqa: E402  _omnikit 已把 engine/scripts 加進 sys.path

FOCUS = {"active": "主動找", "watch": "有新工具才看", "frozen": "凍結"}


def usage_section(tools, days):
    """這台裝了、但 days 天沒用到的 skill 與 plugin；名冊上還是預設或試用中的，另外點出來。"""
    try:
        result = usage.collect(Path.home(), days=days)
    except Exception as e:  # 讀不到使用紀錄，不影響彙整的其他段落
        return [f"- 讀不到使用紀錄：{e}"]
    lines = usage.report(result, limit=15)
    unused = {i["name"].split("@")[0] for i in result["items"] if i["status"] == "unused"}
    for t in tools:
        names = {t["id"], (t.get("plugin") or {}).get("name")} - {None}
        if t["status"] in ("default", "trial") and names & unused:
            lines.append(f"- 名冊：{t['name']}（{t['status']}）{days} 天沒用到；考慮 Retire，或試用到期時不續用")
    return lines


def funnel_section(root, today):
    """維護者週報的評估漏斗：第 0 層淘汰與要勾選的候選、第 1 層建議排實測的、值得實測的外部證據。
    還沒跑過 batch0.py 就略過整段。"""
    import json

    import batch0
    import evidence

    funnel = root / "data" / "funnel"
    path = funnel / "layer0.json"
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    s = doc["summary"]
    lines = ["", "## 評估漏斗", "",
             f"- 第 0 層（{doc['generated']}）：{s['total']} 張，通過 {s['pass']}、只標旗標 {s['flagged']}、淘汰 {s['fail']}、未知 {s['unknown']}"]
    for t in doc["tools"]:
        if t["fails"]:
            lines.append(f"  - 淘汰 {t['id']}：{'；'.join(f['detail'] for f in t['fails'])}")
    pick = s.get("candidates_to_pick") or []
    if pick:
        suggested = doc.get("suggested") or {}
        lines.append(f"- 請勾選候選 repo（{len(pick)} 張，data/funnel/candidates.yaml；建議都對就跑 batch0.py --accept-suggested）：")
        lines += [f"  - [ ] {tid}" + (f"（建議 {suggested[tid]}）" if tid in suggested else "") for tid in pick]
    deep = []
    for p in sorted((funnel / "layer1").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d["recommendation"] == "deep_eval":
            deep.append(f"{d['tool_id']}（{'、'.join(d['slots']) or '未分配'}）")
    if deep:
        lines.append(f"- 第 1 層建議排實測：{'、'.join(deep)}")
    lines += ["- " + line.lstrip("# ") if line.startswith("##") else "  " + line
              for line in evidence.summary_lines(evidence.summary(funnel, today))]
    import schedule

    lines += ["- " + line.lstrip("# ") if line.startswith("##") else "  " + line
              for line in schedule.digest_lines(funnel)]
    return lines


def main():
    parser = argparse.ArgumentParser(description="每週彙整")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--since", type=date.fromisoformat, help="預設是 7 天前")
    parser.add_argument("--usage-days", type=int, default=30, help="多少天沒用到算「沒在用」，預設 30")
    parser.add_argument("--no-usage", action="store_true", help="不讀本機的使用紀錄")
    args = parser.parse_args()
    today = args.today
    since = args.since or today - timedelta(days=7)

    roster = _omnikit.roster()
    tools = list(roster["tools"].values())
    slots = sorted(roster["slots"], key=lambda s: list(FOCUS).index(s["focus"]))
    lines = [f"# OmniKit 每週彙整（{since} ～ {today}）", ""]

    lines += ["## 試用快到期", ""]
    trials = sorted((t for t in tools if t["status"] == "trial"), key=lambda t: t["trial_until"])
    for t in trials:
        left = (date.fromisoformat(t["trial_until"]) - today).days
        when = f"剩 {left} 天" if left > 0 else ("今天到期" if left == 0 else f"已過期 {-left} 天")
        lines.append(f"- {t['name']}（{'、'.join(t['slots'])}）：試用到 {t['trial_until']}，{when}；到期要決定 Keep 或 Update")
    if not trials:
        lines.append("- 沒有試用中的工具")

    lines += ["", "## 這段期間新進的工具", ""]
    new = [t for t in tools if date.fromisoformat(t["added"]) >= since]
    for slot in slots:
        items = [t for t in new if slot["id"] in t["slots"]]
        if items:
            names = "、".join(f"{t['name']}（{t['status']}）" for t in items)
            lines.append(f"- {slot['name']}［{FOCUS[slot['focus']]}］：{names}")
    unassigned = [t for t in new if not t["slots"]]
    if unassigned:
        lines.append(f"- 未分配：{'、'.join(t['name'] for t in unassigned)}")
    if not new:
        lines.append("- 沒有新工具")

    monday = today - timedelta(days=today.weekday())
    used = [p.name for p in (_omnikit.ROOT / "data" / "evals").glob("*.md")
            if (m := re.match(r"(\d{4}-\d{2}-\d{2})", p.name)) and monday <= date.fromisoformat(m.group(1)) <= today]
    limit = (roster["config"].get("eval") or {}).get("weekly_deep_limit", 0)
    lines += ["", "## 本週的深度評估", "", f"- 已用 {len(used)}／上限 {limit}" + (f"：{'、'.join(used)}" if used else "")]

    # 只有主動找的槽位用得到每週的深度評估額度；依待評估數量排，讓使用者勾選
    lines += ["", "## 建議這週評估的槽位（請勾選）", ""]
    active = [(s, sum(1 for t in tools if s["id"] in t["slots"] and t["status"] == "pending"))
              for s in slots if s["focus"] == "active"]
    for slot, pending in sorted(active, key=lambda x: -x[1]):
        if pending:
            lines.append(f"- [ ] {slot['name']}（{slot['id']}）：{pending} 個待評估")

    lines += funnel_section(_omnikit.ROOT, today)

    if not args.no_usage:
        lines += ["", f"## {args.usage_days} 天沒用到的 skill 與 plugin", ""]
        lines += usage_section(tools, args.usage_days)

    _omnikit.utf8_stdout()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
