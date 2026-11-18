"""從報告的 markdown 表格抽出「推薦的工具」：第一欄的名稱（去掉粗體）與同一列第一個連結。

用法：python -I -X utf8 table_tools.py <報告.md> <輸出.tsv>
表頭、分隔列、第一欄是欄位名稱（Tool、Feature…）的列略過。
"""
import re
import sys

SKIP = {"tool", "tool/method", "feature", "name", "aspect", "category", "---", "tool name", "framework"}
rows, seen = [], set()
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if not line.startswith("|") or re.fullmatch(r"[|\s:-]+", line):
        continue
    cells = [c.strip() for c in line.strip("|").split("|")]
    if not cells:
        continue
    name = re.sub(r"\*\*|\[|\]\([^)]*\)", "", cells[0]).strip()
    if not name or name.lower() in SKIP or len(name) > 70:
        continue
    link = next(iter(re.findall(r"\((https?://[^)\s]+)\)", line) or re.findall(r"https?://[^\s|)]+", line)), "")
    key = name.lower()
    if key in seen:
        continue
    seen.add(key)
    rows.append((name, link))
with open(sys.argv[2], "w", encoding="utf-8") as f:
    f.write("name\tlink\n")
    for n, l in rows:
        f.write(f"{n}\t{l}\n")
print(f"{len(rows)} 個工具")
