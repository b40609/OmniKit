"""把執行結果配成兩兩比較，去掉組別與工具名稱，產生兩份評審訊息（順序 1：builtin 在 A；順序 2：反過來）。
對照表存 key.json，評審看不到。"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
from run import QUESTIONS, RUNS  # noqa: E402

SCRUB = re.compile(r"firecrawl[_\w]*|mcp__\w+", re.I)

INSTRUCTIONS = """你是評審，只讀、不改任何檔案、不執行會改動東西的指令。下面有 {n} 組比較，每組是同一個問題的兩個回答（A、B）。
每個回答都被要求：找一手來源（官方文件、官方 repo、法規、論文），每個結論附連結並寫出原文位置或一句原文；查不到的標「待驗證」。

請你實際打開回答裡的連結核對（可以用網頁工具），每個回答檢查四點：
1. 每個結論都附連結。
2. 連結是一手來源，不是轉述文章。
3. 回答引用的原文或位置，打開連結找得到。
4. 查不到的有標「待驗證」，沒有證據的沒寫成事實。

然後判斷哪個回答比較好（只看上面四點與結論是否正確，不看長短或文筆）。差不多就回 tie；無法判斷就回 unsure。

最後只輸出一個 JSON 區塊（```json 開頭），格式：
{{"pairs": [{{"pair": "P1", "winner": "A|B|tie|unsure", "reason": "一兩句", "A": {{"links": 數字, "primary": 數字, "verified": 數字, "unverified_claims_marked": true|false}}, "B": {{...}}}}]}}
links 是連結總數，primary 是一手來源的連結數，verified 是你打開後確認引用內容找得到的數目。

"""


def load(arm, q, n):
    d = json.loads((OUT / f"{arm}-{q}-{n}.json").read_text(encoding="utf-8"))
    return d


def main():
    pairs, key = [], {}
    i = 0
    for q, text in QUESTIONS.items():
        for n in range(1, RUNS + 1):
            i += 1
            pid = f"P{i}"
            pairs.append((pid, text, SCRUB.sub("（工具）", load("builtin", q, n)["answer"]),
                          SCRUB.sub("（工具）", load("firecrawl", q, n)["answer"])))
            key[pid] = {"q": q, "n": n}
    for order in (1, 2):
        parts = [INSTRUCTIONS.format(n=len(pairs))]
        for pid, text, b, f in pairs:
            a_ans, b_ans = (b, f) if order == 1 else (f, b)
            parts.append(f"=== {pid} ===\n問題：{text}\n\n--- 回答 A ---\n{a_ans}\n\n--- 回答 B ---\n{b_ans}\n")
        (HERE / f"judge-{order}.txt").write_text("\n".join(parts), encoding="utf-8")
    key["order"] = {"1": {"A": "builtin", "B": "firecrawl"}, "2": {"A": "firecrawl", "B": "builtin"}}
    (HERE / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    print("ok", len(pairs), [len((HERE / f"judge-{o}.txt").read_text(encoding="utf-8")) for o in (1, 2)])


if __name__ == "__main__":
    main()
