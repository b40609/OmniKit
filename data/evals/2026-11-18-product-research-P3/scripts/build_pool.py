"""盲評題庫：各組的名字混在一起、去重、拿掉來源、打亂順序；GitHub repo 附描述與星數。

用法：python -I -X utf8 build_pool.py <arms.json> <stars.json>... --out <pool.md> --key <key.json>
pool.md 給第二位評審（看不到哪一組找到的）；key.json 留在主控這邊，記每個編號對到哪個名字。
名字對齊跟 compare.py 一樣（全名或短名一樣算同一個）。
"""
import argparse
import json
import random
import re


def short(name):
    return re.sub(r"[^0-9a-z]+", "", name.strip().rstrip("/").split("/")[-1].lower())


def canon(name):
    n = name.strip().rstrip("/")
    return n.lower() if re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", n) else short(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arms")
    ap.add_argument("stars", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--seed", type=int, default=20261118)
    ap.add_argument("--links", help="名字對到報告給的連結（JSON）")
    a = ap.parse_args()
    arms = json.load(open(a.arms, encoding="utf-8"))
    stars = {}
    for s in a.stars:
        stars.update({k: v for k, v in json.load(open(s, encoding="utf-8")).items() if v})
    seen, items = {}, []
    for names in arms.values():
        for n in names:
            if "編造" in n:   # 連結核對已經判定不存在，不交給評審
                continue
            c, s = canon(n), short(n)
            hit = next((k for k, members in seen.items() if c in members or s in members), None)
            if hit:
                seen[hit].update({c, s})
                continue
            seen[c] = {c, s}
            items.append(n)
    random.Random(a.seed).shuffle(items)
    links = json.load(open(a.links, encoding="utf-8")) if a.links else {}
    key, lines = {}, []
    for i, n in enumerate(items, 1):
        key[str(i)] = n
        st = stars.get(n)
        if st:
            lines.append(f"| {i} | {n} | ★{st['stars']} | {st['description'].replace('|', '/')[:160]} |")
        else:
            hint = links.get(n, "")
            lines.append(f"| {i} | {n} | — | 不是 GitHub repo，沒有附描述，需要自己查{('；報告給的連結：' + hint) if hint else ''} |")
    head = ("| 編號 | 名字 | 星數 | GitHub 描述 |\n|---|---|---|---|\n")
    open(a.out, "w", encoding="utf-8").write(head + "\n".join(lines) + "\n")
    json.dump(key, open(a.key, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"題目 {len(items)} 個")


if __name__ == "__main__":
    main()
