"""R1 匿名雙評審的資料包：每題一份，含標準答案（後來的修正 diff）與各組審查意見（隨機代號）。

用法：python make_packets.py <根> <輸出資料夾>
- <根>/out/<題>-<組>.json：run.py 與 Gemini 審查的結果（stdout 欄是審查全文）
- <根>/omnikeep：OmniKeep 的 clone，用來取標準答案的 diff
輸出：<輸出>/<題>-judge{1,2}.md（兩位評審的順序與代號都不同）與 <輸出>/key.json（代號對應組別，評完才打開）
"""
import json
import random
import subprocess
import sys
from pathlib import Path

GOLD = {
    "T1": ["9fee1e3"],
    "T2": ["dd5084d", "62adaa9"],
    "T3": ["9385e71"],
    "T4": ["343e0bc"],
    "T5": ["e7ab107"],
}
GOLD_NOTE = {
    "T1": "白名單空著時第一個對 Bot 發訊息的人就成為擁有者（先到先得，陌生人可能搶先）；修正改成網頁一次性配對連結。同一個修正也提到綁定結果用相對路徑寫 .env，從別的目錄啟動會寫錯地方（次要）",
    "T2": "兩個問題各算半題：(a) Gemini 與 Vertex 呼叫沒有逾時，連線卡住會永遠等；(b) Vertex 不能解析 YouTube，卻被排進影片用途",
    "T3": "向量模型沒回應時查詢退回雜湊向量，和索引（多數是真正模型建的）不同模型，只拿少數同為雜湊的幾筆比，回不相關的收藏；應只用關鍵字，備援向量不該寫進索引",
    "T4": "中文整句問句被當成一個詞（沒有空白可切），多詞全命中規則下找不到收藏",
    "T5": "雷達去重沿用「GitHub 任何頁面都算同一個 repo」的比對，把 repo 的新 release 頁當成已收錄；應改用頁面層級的比對",
}
ARMS = ["incumbent", "codex-plugin-cc", "claudex-loop", "gemini-hydrogen-xhigh"]
LABELS = "甲乙丙丁"
MAX_DIFF = 40000

RUBRIC = """你是程式碼審查結果的評審。下面是一個 commit 的後來修正（標準答案），以及幾份匿名的審查意見。
你不知道哪份是哪個工具寫的，也不要猜。

請對每一份審查意見回答：
1. 標準答案：抓到／部分／沒抓到。
   - 抓到：指出同一個缺陷，講得出原因或症狀。
   - 部分：指到同一段程式，但講的是別的原因。
   - 沒抓到：其他情況。
   T2 有 (a)(b) 兩個問題，分別判。
   引用該份意見裡對應的原句當證據。
2. 其他意見：逐條分成「成立」「不成立」「不確定」，各算條數。不成立指的是對這個 commit 的程式碼來說是錯的判斷，或根本不會發生；只是風格建議也算不成立。
3. 最後輸出一行 JSON（只有一行，放在最後）：
   {"題": "<題>", "評": [{"代號": "甲", "標準答案": "抓到|部分|沒抓到", "標準答案b": "（只有 T2 才填）", "成立": n, "不成立": n, "不確定": n}, ...]}

不要讀檔、不要執行指令，只根據下面的內容判斷。
"""


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def main():
    root, dest = Path(sys.argv[1]), Path(sys.argv[2])
    dest.mkdir(parents=True, exist_ok=True)
    key = {}
    rng = random.Random(20261121)
    for case, fixes in GOLD.items():
        reviews = {}
        for arm in ARMS:
            f = root / "out" / f"{case}-{arm}.json"
            if f.exists():
                d = json.loads(f.read_text(encoding="utf-8"))
                if d.get("rc") == 0 and d.get("stdout", "").strip():
                    reviews[arm] = d["stdout"].strip()
        gold = "\n\n".join(git(root / "omnikeep", "show", "--stat", "--patch", c)[:MAX_DIFF] for c in fixes)
        for judge in (1, 2):
            arms = list(reviews)
            rng.shuffle(arms)
            labels = dict(zip(arms, LABELS))
            key[f"{case}-judge{judge}"] = {lab: arm for arm, lab in labels.items()}
            parts = [RUBRIC, f"## 題目 {case}\n\n標準答案摘要：{GOLD_NOTE[case]}\n\n### 標準答案的修正 diff\n\n```diff\n{gold}\n```"]
            for arm in arms:
                parts.append(f"### 審查意見 {labels[arm]}\n\n{reviews[arm]}")
            (dest / f"{case}-judge{judge}.md").write_text("\n\n".join(parts), encoding="utf-8")
        print(case, "組數", len(reviews), "標準答案", len(gold), "字")
    (dest / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
