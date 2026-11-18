"""把第二位評審照編號給的判定對回名字；編造的條目照連結核對結果判 not_relevant（沒交給評審）。

用法：python -I -X utf8 judge2_by_name.py <judge2-raw.json> <pool-key.json> <arms.json> <輸出 judge2.json>
"""
import json
import sys

raw = json.load(open(sys.argv[1], encoding="utf-8"))
key = json.load(open(sys.argv[2], encoding="utf-8"))
arms = json.load(open(sys.argv[3], encoding="utf-8"))
out = {"judge": raw.get("judge"), "verdicts": {}, "reasons": {}}
for num, name in key.items():
    v = raw["verdicts"].get(num) or {}
    out["verdicts"][name] = v.get("verdict", "uncertain")
    out["reasons"][name] = v.get("reason", "")
for names in arms.values():
    for n in names:
        if "編造" in n:
            out["verdicts"][n] = "not_relevant"
            out["reasons"][n] = "連結核對判定不存在，沒有交給評審"
json.dump(out, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
missing = [k for k in key if k not in raw["verdicts"]]
print(f"對回 {len(key)} 個名字，評審漏判 {len(missing)} 個")
