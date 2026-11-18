"""核對報告裡推薦工具的連結：GitHub repo 用 gh api graphql 查存不存在，VS Code 擴充查官方 marketplace。

用法：python -I -X utf8 linkcheck.py <工具.tsv（name、link）>... --out <結果.json>
其他網址只記下來，不逐一打開（網域連不連得上不等於工具存在）。
"""
import argparse
import json
import re
import subprocess
import urllib.request

GH = r"C:\Program Files\GitHub CLI\gh.exe"
VSX = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"


def gh_exists(repos):
    out = {}
    repos = sorted(set(repos))
    for start in range(0, len(repos), 40):
        chunk = repos[start:start + 40]
        q = " ".join(f'r{i}: repository(owner: {json.dumps(r.split("/")[0])}, name: {json.dumps(r.split("/")[1])}) '
                     '{ nameWithOwner stargazerCount isArchived }' for i, r in enumerate(chunk))
        res = subprocess.run([GH, "api", "graphql", "-f", "query=query {" + q + "}"], capture_output=True, text=True,
                             encoding="utf-8")
        data = (json.loads(res.stdout or "{}").get("data") or {})
        for i, r in enumerate(chunk):
            v = data.get(f"r{i}")
            out[r] = {"exists": bool(v), "stars": v["stargazerCount"] if v else None, "full": v["nameWithOwner"] if v else None}
    return out


def vsx_exists(ids):
    out = {}
    for ext in sorted(set(ids)):
        body = json.dumps({"filters": [{"criteria": [{"filterType": 7, "value": ext}]}], "flags": 0}).encode()
        req = urllib.request.Request(VSX, data=body, headers={"Content-Type": "application/json",
                                                              "Accept": "application/json;api-version=7.2-preview.1",
                                                              "User-Agent": "omnikit-p3-linkcheck"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            exts = d["results"][0]["extensions"]
            out[ext] = {"exists": bool(exts), "display": exts[0]["displayName"] if exts else None}
        except Exception as e:  # noqa: BLE001
            out[ext] = {"exists": None, "error": str(e)[:120]}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for t in a.tsv:
        with open(t, encoding="utf-8") as f:
            next(f)
            for line in f:
                name, _, link = line.rstrip("\n").partition("\t")
                rows.append((t, name, link))
    repos, exts = [], []
    for _, _, link in rows:
        m = re.search(r"github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)", link)
        if m and m.group(1).lower() not in {"features", "marketplace", "topics", "orgs"}:
            repos.append(f"{m.group(1)}/{m.group(2)}")
        m = re.search(r"itemName=([A-Za-z0-9_.-]+)", link)
        if m:
            exts.append(m.group(1))
    gh = gh_exists(repos)
    vs = vsx_exists(exts)
    result = []
    for t, name, link in rows:
        check = {"kind": "other", "ok": None}
        m = re.search(r"github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)", link)
        if m and f"{m.group(1)}/{m.group(2)}" in gh:
            g = gh[f"{m.group(1)}/{m.group(2)}"]
            check = {"kind": "github", "ok": g["exists"], "stars": g["stars"], "full": g["full"]}
        m2 = re.search(r"itemName=([A-Za-z0-9_.-]+)", link)
        if m2:
            v = vs[m2.group(1)]
            check = {"kind": "vscode", "ok": v["exists"], "display": v.get("display")}
        result.append({"file": t.replace("\\", "/").split("/")[-1], "name": name, "link": link, **check})
    json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for f in sorted({r["file"] for r in result}):
        rs = [r for r in result if r["file"] == f]
        gh_rs = [r for r in rs if r["kind"] == "github"]
        vs_rs = [r for r in rs if r["kind"] == "vscode"]
        print(f"{f}: 工具 {len(rs)}；GitHub 連結 {len(gh_rs)}，不存在 {sum(1 for r in gh_rs if r['ok'] is False)}；"
              f"VS Code 擴充 {len(vs_rs)}，不存在 {sum(1 for r in vs_rs if r['ok'] is False)}；其他網址 {len(rs) - len(gh_rs) - len(vs_rs)}")


if __name__ == "__main__":
    main()
