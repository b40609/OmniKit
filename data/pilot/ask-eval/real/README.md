# 真實糾正題（`--set real`）

2026-11-18 加入。題目來自公開的真實 coding agent 對話紀錄，使用者在裡面卡住或糾正 agent；評分標準照原始對話裡「使用者後來真正要的是什麼、agent 原本錯在哪」寫，**不從問法庫的情境檔產出**。

```bash
uv run data/pilot/ask-eval/agy_eval.py --set real --account ava --model gemini-3.8-flash-high -j 3 --runs 1 --out <資料夾>
```

預設跑 `global,without`（只裝全域對照都沒有）。整份當外部驗證：不分訓練題與保留題，**不要照這組的結果改問法庫**；要改的話先換一批題目。

## 來源

- **SWE-chat**（Baumann 等，arXiv 2604.20779，COLM 2026）：[Hugging Face `SALT-NLP/SWE-chat`](https://huggingface.co/datasets/SALT-NLP/SWE-chat)，授權標 ODC-BY，但下載要登入並同意分享 Hugging Face 資訊（gated），這台沒有登入。
- 這組直接用它的上游來源：公開 GitHub repo 裡由 [Entire.io](https://entire.io) CLI 存的 checkpoint（`refs/entire/checkpoints/*` 或 `entire/checkpoints/v1` 分支，每段對話有 `prompt.txt`、`metadata.json`、`transcript.jsonl`）。SWE-chat 也是從這裡收的。
- 用到的 repo：`entireio/cli`（MIT）、`thedannywahl/pantoken`（MIT）、`getnao/nao`（沒有標授權）。
- **repo 裡只存改寫後的繁體中文題目與出處，不存原文。** 每題 `prompt.md` 的 `source` 寫 repo、checkpoint ref、檔案路徑、第幾句使用者訊息與 session id，可以自己 `git fetch` 回去看。

## 出題方式

1. 抓 10 個有 Entire checkpoint 的公開 repo（GitHub 搜尋 `.entire/settings.json`，依 checkpoint 數排序），只讀 `prompt.txt` 與 `metadata.json`：約 2,700 段對話、14,249 句使用者訊息（`entireio/cli` 一個就佔 1,658 段、11,227 句）。
2. 用關鍵字篩出像糾正或卡住的句子（still、again、you said、forgot、revert、why did you、too much…），再人工從約 300 句裡挑，看每句的前兩句與後兩句判斷使用者真正要什麼。
3. 改寫成單輪繁體中文題目。專案名、內部名詞大多保留，但移除個人路徑、帳號與連結（CI 連結換成 example）。每題最後固定加一句「這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關」。第一輪沒有這句：沒有前文的糾正句（「你剛剛改的…」）讓 agent 在硬碟上找專案，翻到 `data/pilot/ask-eval`（連這組的評分標準都讀到），還有幾題跑到 600 秒逾時。那輪結果作廢。`agy_eval.py` 另外會把工具參數裡出現 `ask-eval` 的回合標成 `peeked`，不算分。
4. `kind`：
   - `stuck`（18 題）：使用者描述處境、問怎麼辦。`expect_fire: true`。
   - `correction`（23 題）：使用者直接糾正 agent、講了要它做什麼。照問法庫的說明，這類應該直接做，`expect_fire: false`。
5. `situation`：對應的問法庫情境（`situations/<檔>「標題」`）；沒有對應的 10 題標「沒有對應情境」，留給之後擴充情境用。
6. 評分項每題兩個：
   - `need`（權重 2）：回覆有沒有朝使用者後來真正要的方向走（多半取自那句之後的使用者訊息）。
   - `pitfall`（權重 1）：有沒有避開 agent 原本犯的錯。

## 要打折看的地方

- 題目是單輪、空資料夾：原始對話有完整 repo 與前文，這裡只能看回覆的做法與方向，看不到真的改程式。
- 挑題與評分標準都是同一個人（Claude Opus）寫的，沒有第二個人審。
- 來源偏向少數活躍 repo（`entireio/cli` 佔多數），使用者多是早期採用者、英文、Claude Code 為主。
