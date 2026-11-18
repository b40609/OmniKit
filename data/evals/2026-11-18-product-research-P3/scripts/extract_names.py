"""從 deep research 報告抽出候選名字：GitHub repo 連結、VS Code 擴充、其他網域、粗體與標題的名稱。

用法：python -I -X utf8 extract_names.py <報告.md>
只是幫主控整理，最後收哪些名字由主控逐一判斷。
"""
import collections
import re
import sys
from urllib.parse import urlparse

text = open(sys.argv[1], encoding="utf-8").read()
repos = collections.Counter()
for o, r in re.findall(r"github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)", text):
    if o.lower() in {"topics", "orgs", "features", "marketplace", "sponsors", "apps", "search"}:
        continue
    repos[f"{o}/{re.sub(r'(\.git|[.)\],]+)$', '', r)}"] += 1
vsx = collections.Counter(re.findall(r"marketplace\.visualstudio\.com/items\?itemName=([A-Za-z0-9_.-]+)", text))
domains = collections.Counter()
for u in re.findall(r"https?://[^\s)\]>\"']+", text):
    host = urlparse(u).netloc.lower().removeprefix("www.")
    if host and "github.com" not in host:
        domains[host] += 1
bold = collections.Counter(b.strip() for b in re.findall(r"\*\*([^*\n]{2,60})\*\*", text))
heads = collections.Counter(h.strip() for h in re.findall(r"^#{2,4}\s+(?:\d+(?:\.\d+)*\.?\s+)?(.+)$", text, re.M))
print("## GitHub repo"); [print(f"{n}\t{c}") for n, c in repos.most_common()]
print("## VS Code"); [print(f"{n}\t{c}") for n, c in vsx.most_common()]
print("## 網域"); [print(f"{n}\t{c}") for n, c in domains.most_common(60)]
print("## 粗體"); [print(f"{n}\t{c}") for n, c in bold.most_common(80)]
print("## 標題"); [print(f"{n}\t{c}") for n, c in heads.most_common(60)]
