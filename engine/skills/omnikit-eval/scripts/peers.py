# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""列出一個槽位的情境、現任（預設與試用）、曾拒絕與退役的工具。輸出 JSON。

第 1 層用它提醒以前拒絕過的理由；第 2 層用它自動配對比較對象。

用法：uv run scripts/peers.py <槽位 id>
"""
import sys

import _omnikit


def main():
    if len(sys.argv) != 2:
        sys.exit("用法：uv run scripts/peers.py <槽位 id>")
    slot_id = sys.argv[1]
    roster = _omnikit.roster()
    slot = next((s for s in roster["slots"] if s["id"] == slot_id), None)
    if slot is None:
        sys.exit(f"找不到槽位「{slot_id}」，可用的有：{'、'.join(s['id'] for s in roster['slots'])}")

    tools = [t for t in roster["tools"].values() if slot_id in t["slots"]]
    pick = lambda *statuses: [_omnikit.card_summary(t) for t in tools if t["status"] in statuses]  # noqa: E731
    _omnikit.emit({
        "layer": "peers",
        "omnikit_root": str(_omnikit.ROOT),
        # slot 的情境已經套上這個 profile；None 表示用的是 slots.yaml 的範本
        "profile": roster["profile"],
        "slot": slot,
        "incumbents": pick("default", "trial"),
        "rejected": pick("rejected"),
        "retired": pick("retired"),
        "pending": [{"id": t["id"], "name": t["name"]} for t in tools if t["status"] == "pending"],
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
