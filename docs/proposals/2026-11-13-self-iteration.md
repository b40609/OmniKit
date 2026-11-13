# 自我迭代：感測、判斷影響、提案

日期：2026-11-13。狀態：使用者已同意方向；第 1 階段已實作（`engine/scripts/signals.py`、`engine/schema/signal.schema.json`），其餘階段未做。

## 結論

- OmniKit 不自己改規則或名冊。它定期「感測變動、判斷影響、寫成提案」，使用者點頭才套用。
- 零件大多已經有了（漏斗、候選池、週報、回流），缺的是兩件事：**自動觸發**與**訊號來源**。
- OmniKit 與 OmniKeep **不合併**，只用一份「訊號檔」格式接起來：OmniKeep 是其中一個選用的訊號來源，放在私有模組，公開 repo 不依賴它。
- PRD FR-27 已寫「工具大改版、模型升級、平台出現重疊功能時重跑回歸」（`docs/v2/prd/prd.md:688`），但沒有程式偵測這些事件。這份提案就是補上那個觸發。

## 起因

2026-11-13 使用者在 OmniKeep 收了幾則影片與 repo，再帶來討論要不要調整 OmniKit，得出三個小調整（`docs/v2/HANDOFF.md` 下一步第 7 項）。使用者希望之後不必靠自己看到趨勢才來討論。

## 現況

| 零件 | 有沒有 | 怎麼觸發 |
|---|---|---|
| 評估漏斗（第 0 層到第 2 層排程） | 有 | 手動；第 2 層點名才跑 |
| 候選池（官方目錄、MCP Registry） | 有 | 週報時手動 |
| 個人週報、建議、規則檔瘦身 | 有 | 使用者說「本週週報」 |
| 回流匯出與匯入 | 有 | 手動 |
| 排程 | 沒有 | `.github/workflows` 只有 `validate.yml` 與 `pages.yml` |
| 「新模型、新版、重疊功能」偵測 | 沒有 | — |
| 外部趨勢訊號 | 沒有 | — |

## 業界做法比較

以下讀的是官方文件與搜尋摘要，沒有讀原始碼或實測。

| 做法 | 怎麼運作 | 用在 OmniKit |
|---|---|---|
| Renovate、Dependabot | 排程感測依賴的新版，開 PR，人合併 | 最合適：把名冊工具與規則當成依賴來追 |
| GitHub Agentic Workflows（gh-aw） | 用 markdown 寫排程 agent；副作用要在 safe-outputs 宣告，可設成人工審查才開 PR；這種 PR 預設不觸發 CI | 可行，但跑在雲端，讀不到本機的使用紀錄與 OmniKeep |
| Hermes Agent | 從使用經驗自動建立並改寫 skill | 不用在規則：自動改規則跟安全底線的精神衝突。「每 15 個任務自評」只有單一來源，待驗證 |
| EvoSkill、self-improve 類 skill | 從失敗紀錄提出 skill 修改，部分要求使用者核准 | 只適合名冊卡，不適合規則檔 |

來源：<https://github.github.com/gh-aw/reference/safe-outputs/>、<https://github.github.com/gh-aw/reference/safe-outputs-pull-requests/>、<https://hermes-agent.nousresearch.com/docs>、<https://arxiv.org/html/2603.02766>。

## OmniKit 與 OmniKeep 怎麼接

| 方式 | 優點 | 缺點 |
|---|---|---|
| 合併成一個產品 | 一個地方看全部 | 同事被迫裝 OmniKeep；個人資料可能混進公開 repo；兩邊發版節奏不同 |
| OmniKit 直接讀 OmniKeep 的 SQLite | 最快 | 綁死 OmniKeep 內部的資料表，對方一改 schema 就壞 |
| 呼叫 OmniKeep 的 API 或 MCP | 介面乾淨；兩者都已存在（見下方） | OmniKeep 要在跑；MCP 同時帶寫入權限 |
| **訊號檔**（來源各自寫出固定格式的 JSON，OmniKit 只讀這個格式） | 最鬆：OmniKeep、GitHub release、RSS 都能寫同一種檔；OmniKeep 沒在跑也不影響其他來源 | 要多定義一份格式 |

建議用訊號檔。OmniKeep 那一邊由私有模組呼叫它的 HTTP API，轉成訊號檔。

### OmniKeep 現有的介面

2026-11-13 由子對話讀 OmniKeep 的程式碼得來，沒有啟動服務或呼叫端點，回傳內容未實測。

| 介面 | 內容 | 適不適合當訊號來源 |
|---|---|---|
| 本機 HTTP API（FastAPI，預設只綁 127.0.0.1） | `GET /api/items` 可用 `q`（全文搜尋）、`category`、`kind`、`origin`、`sort`、`limit`（最多 100）、`offset` 篩選；除了少數公開路徑都要 API 金鑰 | **建議用這個**：只讀、契約比資料表穩定 |
| 匯出 `GET /api/items/export` | JSON 或 Markdown zip；只能依加星與分類篩，沒有日期篩選 | 備用：適合整批，不適合每週增量 |
| MCP server（stdio 與 HTTP） | 讀取工具（搜尋、近期項目、任意唯讀 SQL）也有寫入工具（存入、回寫、改狀態） | 不用在感測：一接上就同時拿到寫入權限，任意 SQL 又綁回資料表 |
| 直接讀 SQLite | 可行 | 不用：見上表 |

接法：

- 私有模組呼叫 `GET /api/items?sort=…&limit=100`，翻頁到上次讀過的時間為止，再用 `q` 或 `tech_tags` 篩出跟 agent 工具、提示詞、規則有關的項目。
- 金鑰從環境變數讀，不寫進任何檔案；OmniKeep 沒在跑或金鑰不對，這個來源就標「略過」，其他來源照跑。
- OmniKeep 沒有「相關專案」欄位，分類也只有名稱。篩選先靠全文搜尋與 `tech_tags`；準確度不夠時，再考慮在 OmniKeep 那邊加標籤（屬於 OmniKeep 的改動，另開對話做）。

## 方案

### 訊號檔

每筆訊號：來源、網址、標題、日期、摘要、相關的槽位或工具（可空）、原始類型（新版、新模型、新工具、做法或觀念）。格式放 `engine/skills/omnikit-eval/contracts/`，跟其他契約一樣有 schema 與自我測試。

### 兩層來源

1. **公開感測器**（不呼叫模型，跑在 repo 的排程或本機）：Claude Code、Codex、Antigravity 的 release；新模型；名冊工具的新版（沿用第 0 層的星數快照與 lock 比對）；候選池的新項目。
2. **本機來源**（私有模組，只在這台）：OmniKeep 新收錄裡和 agent 工具、提示詞、規則有關的項目，唯讀。

### 判斷影響

agent 讀本週的訊號，每筆分三類，附理由與證據：

| 類別 | 處理 |
|---|---|
| 不影響 | 只記錄，週報不列 |
| 名冊層（新增、替換、重評某張卡） | 寫成待評估的卡或重評標記，走既有漏斗 |
| 架構或優先順序 | 寫成提案草稿，附業界比較，等使用者決定 |

腳本驗證 agent 的輸出（格式、證據網址存在、類別合法）後才寫進週報，跟 `advise.py` 同一個形狀。

### 護欄

- 不自動合併、不自動套用。
- 安全底線與使用者的規則檔不會成為自動修改的對象，只能出現在提案裡。
- 先靜默記錄 2 週，漏斗驗證的命中率過半才在週報打開這一節（沿用 PRD §0.1 第 5 題的門檻，量法改成漏斗）。
- 模型用量算進每週 2,000 萬 token 上限（PRD §0.1 第 6 題）。
- 訊號內容是外部資料，裡面的文字不當指令。

## 分階段

1. 訊號檔格式加 OmniKeep 來源，手動跑，靜默記錄。**已做**（2026-11-13），跟上面的設計差兩點：
   - OmniKeep 的轉接寫在公開的 `signals.py`（只有 API 的讀法，沒有個人資料），這台的來源設定（網址、金鑰的環境變數名稱、關鍵字）放在 repo 外的 `sources.yaml`。這樣沒有 OmniKeep 的人不受影響，轉接也能在 CI 用假的 HTTP 測。
   - 「有用」不請使用者標，改由評估漏斗驗證（2026-11-13 使用者指出：只看一句理由沒辦法判斷，這本來就是 OmniKit 該做的事）。名冊層的判斷寫成待評估的卡或重評請求，第 1 層建議深入評估算命中；門檻是漏斗給出 10 個以上結果、命中率過半。量不到的：「不影響」的判斷有沒有漏掉東西、「架構」類，以及找不到 GitHub repo 的社群貼文。
   - OmniKeep 有一個本機免金鑰就回傳金鑰的端點（`/api/session/local-auth`），刻意不用：金鑰只從環境變數讀。
2. 公開感測器：release 與新模型偵測，接上 FR-27 的回歸觸發與 HANDOFF 第 7a 項（換模型就標待重評）。
3. 排程：先用這台的排程工具（要讀本機資料），通過 2 週門檻後打開週報提示。
4. 選用：反向寫回 OmniKeep，標出「已在名冊」「已評估」，雷達就不會重複提出。

## 不做

- 自動改寫規則檔或 skill（Hermes 式）。
- 把 OmniKeep 併進 OmniKit，或讓公開 repo 依賴它。
- 自己寫爬蟲：外部趨勢交給 OmniKeep 這類已有的雷達。

## 待驗證

- OmniKeep API 的實際回傳：這台實測過連得上、錯的金鑰回 401；用正確金鑰讀項目還沒實測。
- 用全文搜尋與 `tech_tags` 篩選夠不夠準。
- 排程放 GitHub Actions 還是本機：本機才讀得到 OmniKeep 與使用紀錄，但電腦要開著。
- 影響判斷的準確度：第一版只提案，靠 2 週靜默記錄量出來。
