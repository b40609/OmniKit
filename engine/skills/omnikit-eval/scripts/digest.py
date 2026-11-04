# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""每週彙整：試用快到期、這段期間新進的工具、本週的深度評估額度、建議這週評估的槽位。輸出 Markdown。

平常新工具只記進名冊，不逐筆通知；每週看一次這份彙整。

用法：uv run scripts/digest.py [--since YYYY-MM-DD] [--today YYYY-MM-DD]
"""
import argparse
import re
import sys
from datetime import date, timedelta

import _omnikit

FOCUS = {"active": "主動找", "watch": "有新工具才看", "frozen": "凍結"}


def main():
    parser = argparse.ArgumentParser(description="每週彙整")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--since", type=date.fromisoformat, help="預設是 7 天前")
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

    _omnikit.utf8_stdout()
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
