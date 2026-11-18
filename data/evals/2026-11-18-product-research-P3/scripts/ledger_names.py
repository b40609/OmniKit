"""從 omnikit-research 帳本取出名字：第幾組第一次出現、哪個管道。

用法：python -I ledger_names.py <帳本.json> <輸出.tsv>
名字比對照 sweep.py 的規則：短名（owner/repo 取 repo）小寫一樣就算同一個。
"""
import json
import sys


def short(name: str) -> str:
    return name.strip().rstrip("/").split("/")[-1].lower()


def main(ledger_path: str, out_path: str) -> None:
    ledger = json.load(open(ledger_path, encoding="utf-8"))
    seen = {}
    rows = []
    per_group = []
    for gi, group in enumerate(ledger["groups"], start=1):
        new = 0
        for channel, info in group["channels"].items():
            for name in info.get("names", []):
                key = short(name)
                if key in seen:
                    continue
                seen[key] = name
                new += 1
                rows.append((name, key, gi, channel))
        per_group.append((gi, new))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("name\tshort\tgroup\tchannel\n")
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")
    print(f"names={len(rows)} groups={len(per_group)}")
    print("new per group:", per_group)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
