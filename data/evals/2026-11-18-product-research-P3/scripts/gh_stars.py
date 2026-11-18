"""用 gh api graphql 批次查 repo 的星數、授權、封存、最後 push、描述。

用法：python -I gh_stars.py <輸入.tsv（第一欄 name）> <輸出.json>
只查 owner/repo 形式的名字；每批 40 個。gh 要已登入（不讀 token，交給 gh 自己處理）。
"""
import json
import subprocess
import sys

GH = r"C:\Program Files\GitHub CLI\gh.exe"


def batch_query(repos):
    parts = []
    for i, full in enumerate(repos):
        owner, name = full.split("/", 1)
        parts.append(
            f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) '
            '{ nameWithOwner stargazerCount isArchived pushedAt description licenseInfo { spdxId } }'
        )
    query = "query {" + " ".join(parts) + "}"
    out = subprocess.run([GH, "api", "graphql", "-f", f"query={query}"], capture_output=True, text=True, encoding="utf-8")
    data = json.loads(out.stdout or "{}")
    return data.get("data") or {}


def main(tsv, out_path):
    names = []
    with open(tsv, encoding="utf-8") as f:
        next(f)
        for line in f:
            n = line.split("\t")[0].strip()
            if n.count("/") == 1 and not n.startswith("http"):
                names.append(n)
    result = {}
    for start in range(0, len(names), 40):
        chunk = names[start:start + 40]
        data = batch_query(chunk)
        for i, full in enumerate(chunk):
            r = data.get(f"r{i}")
            if r:
                result[full] = {
                    "full": r["nameWithOwner"], "stars": r["stargazerCount"], "archived": r["isArchived"],
                    "pushed": (r["pushedAt"] or "")[:10], "license": (r.get("licenseInfo") or {}).get("spdxId"),
                    "description": (r.get("description") or "")[:200],
                }
            else:
                result[full] = None
    json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    found = [v for v in result.values() if v]
    print(f"queried={len(names)} found={len(found)} missing={len(names) - len(found)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
