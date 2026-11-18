"""P3 對比：各組的名字對齊、套兩位評審的判定、算指標。

用法：python -I -X utf8 compare.py <arms.json> <judge1.json> <judge2.json> <輸出.json>

arms.json：{"A": [名字...], "B1": [...], ...}。名字可以是 owner/repo 或產品名。
名字對齊照 sweep.py 的規則：owner/repo 比全名；短名（repo 名或產品名，小寫、只留英數）一樣也算同一個。
judge1.json：default + not_relevant + uncertain（見檔案說明）。judge2.json：{"verdicts": {名字: relevant|not_relevant|uncertain}}。
相關（下限）= 兩位都判相關；相關（上限）= 至少一位判相關或不確定、而且不是兩位都判不相關。
雜訊 = 兩位都判不相關的名字 ÷ 該組列出的名字。
"""
import json
import re
import sys

ARCHIFY = "archify"


def short(name: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", name.strip().rstrip("/").split("/")[-1].lower())


def canon(name: str) -> str:
    n = name.strip().rstrip("/")
    m = re.search(r"github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)", n)
    if m:
        return f"{m.group(1)}/{m.group(2)}".lower()
    return n.lower() if re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", n) else short(n)


def verdict1(name, j1):
    if name in j1["not_relevant"]:
        return "not_relevant"
    if name in j1["uncertain"]:
        return "uncertain"
    return j1["default"]


def main(arms_path, j1_path, j2_path, out_path):
    arms = json.load(open(arms_path, encoding="utf-8"))
    j1 = json.load(open(j1_path, encoding="utf-8"))
    j2 = json.load(open(j2_path, encoding="utf-8"))["verdicts"]

    # 每個名字一個 id：全名或短名對上就是同一個
    ids, display = {}, {}

    def ident(name):
        c, s = canon(name), short(name)
        for key, members in ids.items():
            if c in members or s in members:
                members.update({c, s})
                return key
        ids[c] = {c, s}
        display[c] = name
        return c

    arm_ids = {arm: [] for arm in arms}
    for arm, names in arms.items():
        for n in names:
            i = ident(n)
            if i not in arm_ids[arm]:
                arm_ids[arm].append(i)

    def v1(i):
        return verdict1(display[i], j1)

    def v2(i):
        return j2.get(display[i], "uncertain")

    def label(i):
        a, b = v1(i), v2(i)
        if a == b == "relevant":
            return "relevant"
        if a == b == "not_relevant":
            return "not_relevant"
        if "relevant" in (a, b) or "uncertain" in (a, b):
            return "disputed_or_uncertain"
        return "not_relevant"

    a_rel = {i for i in arm_ids.get("A", []) if label(i) == "relevant"}
    result = {"arms": {}, "disagreements": []}
    for arm, lst in arm_ids.items():
        labels = [label(i) for i in lst]
        lower = [i for i in lst if label(i) == "relevant"]
        upper = [i for i in lst if label(i) != "not_relevant"]
        noise = [i for i in lst if label(i) == "not_relevant"]
        result["arms"][arm] = {
            "listed": len(lst),
            "relevant_lower": len(lower),
            "relevant_upper": len(upper),
            "noise": len(noise),
            "noise_ratio": round(len(noise) / len(lst), 3) if lst else None,
            "archify": any(ARCHIFY in ids[i] for i in lst),
            "new_vs_A": sorted(display[i] for i in lower if i not in arm_ids.get("A", [])) if arm != "A" else [],
            "covers_A_relevant": round(len(set(lower) & a_rel) / len(a_rel), 3) if a_rel and arm != "A" else None,
            "names": [{"name": display[i], "label": label(i), "judge1": v1(i), "judge2": v2(i)} for i in lst],
        }
        _ = labels
    for i in display:
        if v1(i) != v2(i):
            result["disagreements"].append({"name": display[i], "judge1": v1(i), "judge2": v2(i)})
    json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for arm, r in result["arms"].items():
        print(f"{arm}: 列出 {r['listed']}、相關 {r['relevant_lower']} 到 {r['relevant_upper']}、雜訊 {r['noise']}"
              f"（{r['noise_ratio']}）、Archify {'有' if r['archify'] else '沒有'}"
              + (f"、A 沒有的相關名字 {len(r['new_vs_A'])}、涵蓋 A 的相關名字 {r['covers_A_relevant']}" if arm != "A" else ""))
    print(f"兩位評審意見不同：{len(result['disagreements'])} 個")


if __name__ == "__main__":
    main(*sys.argv[1:5])
