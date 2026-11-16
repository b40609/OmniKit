"""照決策規則算 C2：兩種順序一致才算一勝；雜訊率 = 內建對內建分出勝負的比例。"""
import json
from pathlib import Path

S = Path(__file__).resolve().parent
key = json.loads((S / "judge" / "key.json").read_text(encoding="utf-8"))
res = {}
for pid, (x, y) in key.items():
    v = {}
    for order in ("xy", "yx"):
        p = S / "judge" / f"{pid}-{order}.json"
        if p.exists():
            v[order] = json.loads(p.read_text(encoding="utf-8"))["verdict"]
    if len(v) < 2:
        res[pid] = {"x": x, "y": y, "result": "missing"}
        continue
    xy, yx = v["xy"]["winner"], v["yx"]["winner"]
    wx = (xy == "A") + (yx == "B")
    wy = (xy == "B") + (yx == "A")
    result = "x" if (xy == "A" and yx == "B") else "y" if (xy == "B" and yx == "A") else "tie"
    wrong_x = v["xy"]["a_wrong"] + v["yx"]["b_wrong"]
    wrong_y = v["xy"]["b_wrong"] + v["yx"]["a_wrong"]
    checked_x = v["xy"]["a_checked"] + v["yx"]["b_checked"]
    checked_y = v["xy"]["b_checked"] + v["yx"]["a_checked"]
    res[pid] = {"x": x, "y": y, "xy": xy, "yx": yx, "result": result, "wrong_x": f"{wrong_x}/{checked_x}",
                "wrong_y": f"{wrong_y}/{checked_y}", "reasons": [v["xy"]["reason"], v["yx"]["reason"]]}
for pid, r in res.items():
    print(pid, json.dumps(r, ensure_ascii=False))


def net(prefix):
    rows = [r for r in res.values() if r["x"].startswith(prefix) and r["result"] != "missing"]
    w = sum(r["result"] == "x" for r in rows); l = sum(r["result"] == "y" for r in rows)
    return w, l, len(rows), (w - l) / len(rows) if rows else None


noise = [r for r in res.values() if r["x"].startswith("native") and r["result"] != "missing"]
nrate = sum(r["result"] != "tie" for r in noise) / len(noise) if noise else None
print("noise_rate", nrate, [r["result"] for r in noise])
for g in ("graphify-forced", "floorplan-forced"):
    print(g, "wins/losses/n/net =", net(g))
