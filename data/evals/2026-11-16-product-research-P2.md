# 產品研究槽位實測：P2，Exa（2026-11-16）

使用者點名的第 2 層評估。起因：11-14 OmniKeep 的 repo 圖示化調研只用網頁搜尋、找到 5 個就停，漏掉 GitHub topic `architecture-diagram` 星數第一的 Archify（tt-a1i/archify）；補查時把 Exa 列為「補同義詞沒想到」的候選（OmniKeep `backups/deep-layout-research-20261113/架構圖工具補充調研-20261116.md`）。同一天 OmniKit 加了 `omnikit-research`（飽和式調研），GitHub topic、目錄、HN 這些免費管道已經在裡面。

## 要回答的問題

1. 同一題，Exa 找得到 WebSearch 找不到的工具嗎？尤其是 Archify 這種「自稱跟使用者說法不一樣」的？
2. 加上 `omnikit-research` 的免費管道之後，Exa 還多出什麼？值不值得付金鑰、多一個 MCP？
3. 會改變的決定：Exa 的卡片（現在 `pending`）改 `trial` 放進名冊、記 `rejected`，或繼續等金鑰。

## 決策規則（實測前寫下）

- **情境**：ryan 的 P2「有產品想法時，先找出符合的現有專案，避免重造輪子」。題目用 11-14 漏找的真實問題：「找能把 GitHub repo 自動畫成架構圖的工具」。
- **候選**：Claude Code 內建的 WebSearch（基準）對上 Exa（exa-mcp-server 的網頁搜尋工具）。Tavily 只當報告裡的比較對象，不裝、不測。
- **關鍵字**：兩邊用同樣的 3 組，事先固定：
  - K1 `repo visualization tool`（一般說法，不含 agent、skill）
  - K2 `codebase diagram generator`（一般說法，不含 agent、skill）
  - K3 `agent skill architecture diagram from codebase`（含 agent、skill 的說法）
- **每組記錄**：
  1. 有沒有找到 Archify、排第幾。
  2. 結果分三類：工具（工具自己的 repo、官網、目錄頁，或專門介紹單一工具的頁）、清單（比較文章、awesome 清單，算線索不算雜訊）、雜訊（跟題目無關、一般教學文、廣告）。雜訊比例 = 雜訊 ÷ 結果數。
  3. 名字數：「工具」類的不重複名字。
  4. 新名字：不在另一邊結果、也不在 `omnikit-research` 免費管道帳本（同樣 3 組關鍵字跑 `sweep.py channels`）裡的名字。這一項回答問題 2。
- **次數**：搜尋引擎同一個查詢的結果大致固定，每組每邊跑 1 次；K1 在 WebSearch 跑 2 次，當同一設定的雜訊基準。差距不超過基準的不算贏。
- **放進名冊**（Exa 改 `trial`，兩週後看；當 `omnikit-research` 的選用管道），全部要成立：
  1. 3 組裡 Exa 找到 Archify 的組數比 WebSearch 多，或 Exa 的新名字（第 4 項）3 組合計 3 個以上。
  2. Exa 的雜訊比例不比 WebSearch 高 20 個百分點以上。
  3. 費用：每月約 200 次搜尋（每週 1 到 2 次調研 × 每次約 10 組關鍵字，加上偶爾抓內文）在免費額度內，或每月不到 US$5。
  4. 對話開頭：三個 agent 裡，會把工具定義全量載入的那幾個，每回合增加不到 2,000 token。
- **不放**（Exa 記 `rejected` 並寫理由）：條件 1 不成立，也就是 WebSearch 加上免費管道就夠。
- **等金鑰**：環境變數 `EXA_API_KEY` 沒設時，Exa 那半邊不跑，卡片維持 `pending`。其他部分（WebSearch 半邊、免費管道帳本、費用、接法、對話開頭成本）照做。

## 結果

原始資料在 `2026-11-16-product-research-P2/`：`out/websearch.json` 是 WebSearch 的連結與逐筆分類，`out/exa-*.json` 是 Exa 的原始回應（`-min` 是 objective 只填關鍵字的對照版），`ledger.json` 是 `omnikit-research` 的帳本，`compare.py` 依人工挑出的名單算三邊的比對（輸出在 `compare.json`），`exa_run.py` 是打 Exa 的腳本。

### 判定：放進名冊，Exa 改 `trial` 到 2026-11-30；匿名接，不用金鑰

| 條件 | 結果 | 成立 |
|---|---|---|
| 1. Archify 組數比 WebSearch 多，或新名字 3 個以上 | Archify：Exa 0／3 組，WebSearch 1／3（K3 第 5 名，agentconn.com 的目錄頁）。新名字：Exa 26 個不在 WebSearch 與免費管道裡 | 成立（靠新名字；Archify 這項 Exa 輸） |
| 2. 雜訊比例不比 WebSearch 高 20 個百分點以上 | Exa 1／30（3%）；WebSearch 12／58（21%） | 成立 |
| 3. 每月約 200 次搜尋在免費額度內或不到 US$5 | 匿名 0 元；註冊後每月 $10 額度，200 次約 $0.8 到 $1.4 | 成立 |
| 4. 全量載入的 agent 每回合增加不到 2,000 token | 定義 2,421 bytes，估計約 600 到 700 token | 成立 |

### 每組的數字

名字數是「工具」類的不重複名字；新名字是不在另外兩邊（三組合起來）的名字。免費管道是 `sweep.py channels` 的七個管道，原始結果雜訊很多，名字是人工挑出相關的，不算雜訊比例。

| 組 | 來源 | 結果數 | 名字數 | 雜訊 | Archify | 新名字 |
|---|---|---|---|---|---|---|
| K1 repo visualization tool | WebSearch | 22 | 8 | 11（50%），多是只畫 git 歷史的工具與論文 | 沒有 | 8 |
| | Exa | 10 | 9 | 1（10%），gat Graph 畫 git 歷史 | 沒有 | 8 |
| | 免費管道 | — | 3 | — | 沒有 | — |
| K2 codebase diagram generator | WebSearch | 26 | 18 | 0（另有 1 篇文章算清單） | 沒有 | 14 |
| | Exa | 10 | 10 | 0 | 沒有 | 9 |
| | 免費管道 | — | 18 | — | 沒有 | — |
| K3 agent skill architecture diagram from codebase | WebSearch | 10 | 9 | 1（10%） | 第 5 名 | 7 |
| | Exa | 10（兩種 objective 合起來 11 個名字） | 11 | 0 | 沒有 | 9 |
| | 免費管道 | — | 13 | — | 第 1 名（topic `architecture-diagram`） | — |

三組合起來：免費管道 33 個名字（其中 24 個另外兩邊沒有）、WebSearch 35 個（29 個）、Exa 29 個（26 個），聯集 88 個。Exa 跟 WebSearch 沒有交集；Exa 跟免費管道重疊 3 個（gitdiagram、draw-c4-skill、drawio-skill）；WebSearch 跟免費管道重疊 6 個（Eraser、meduza、claude-code-guide、CodeBoarding、Archify、dp-archive）。

### 看到什麼

- **三個來源各撈到不同的一塊。** GitHub topic 撈到高星的開源 repo：Archify ★96,828（Apache-2.0）、gitdiagram ★18,943、drawio-skill ★10,781、dependency-cruiser ★7,427（都是 MIT，2026-11-16 `gh api`）。WebSearch 撈到 skill 目錄頁（skills.cat、mcpmarket、smithery、tessl）與介紹文章。Exa 撈到產品官網、VS Code 擴充與小型 GitHub skill。
- **Exa 補到另外兩邊漏的。** WebSearch 三組都沒有 gitdiagram，Exa 在 K1、K2 分別排第 3、第 5。OmniKeep 補充調研說「形態最接近 OmniKeep」的 konraddzbik/architecture-diagram-skill（★162，MIT），只有 Exa 找到。
- **Exa 找不到 Archify。** 所以 Exa 是多加一個管道，不能取代 GitHub topic；11-14 漏掉 Archify 的修法還是 `omnikit-research` 的 topic 搜尋。
- **雜訊少。** Exa 的 30 筆裡 29 筆是工具頁；WebSearch K1 一半是只畫 git 歷史的工具、論文與別的工具的文件。
- **離飽和還很遠。** 3 組之後聯集 88 個，每組還有一大半是新名字。這次只回答「Exa 有沒有多撈到」，不是這個題目的完整調研。
- **結果穩定。** WebSearch 的 K1 跑兩次，22 筆連結與順序完全相同；Exa 同一組換 objective，K1 完全相同、K2 只差順序、K3 差 1 筆。差距不是同一設定每次跑出來的隨機差異。

### 費用

| | Exa | Tavily（只當比較，沒測） |
|---|---|---|
| 免費 | hosted MCP 匿名可用，有限速（多少沒公布，待驗證）；註冊後每月 $10 額度（約 2,500 次 lite 搜尋），每月 1 號重置 | 每月 1,000 credits |
| 搜尋 | lite、instant 每千次 $4；auto、fast 每千次 $7；含 10 筆，多 1 筆每千筆加 $1 | basic 1 credit、advanced 2 credits；超過免費額度 $0.008／credit |
| 抓內文 | Contents 每千頁 $1 | 沒查 |
| 每月約 200 次搜尋 | 約 $0.8 到 $1.4，在免費額度內；匿名則 0 元 | 200 到 400 credits，在免費額度內 |
| MCP 的搜尋算哪個型別 | 待驗證 | — |
| GitHub（2026-11-16 `gh api`） | exa-labs/exa-mcp-server ★5,235，MIT，最後 push 2026-11-05 | tavily-ai/tavily-mcp ★2,493，MIT，最後 push 2026-11-13 |

價格來源：exa.ai/pricing、docs.tavily.com/documentation/api-credits，2026-11-16 用 WebFetch 讀取，表裡的數字是頁面原文的引述。

### 接法

- **Exa hosted MCP**：`https://mcp.exa.ai/mcp`。README 寫匿名可用、有限速；要更高額度與 Exa Agent 用 OAuth 或金鑰（`?exaApiKey=`、`Authorization: Bearer`、`x-api-key` 標頭）。2026-11-16 匿名實測：initialize、tools/list、6 次 `web_search_exa` 都成功，伺服器是 exa-search-server 3.5.1。
- **預設工具 2 個**：`web_search_exa`（`query` 與 `objective` 必填，`numResults` 預設 10）、`web_fetch_exa`（`urls`，每頁預設 3,000 字元）。網址加 `?tools=` 可以換成 `web_search_advanced_exa` 等。
- **Claude Code**：`claude mcp add --transport http exa https://mcp.exa.ai/mcp`。要帶金鑰時在 headers 寫 `x-api-key: ${EXA_API_KEY}`；官方文件寫 url 與 headers 支援 `${VAR}` 展開（Claude Code 自己的憑證變數除外）。
- **Codex**：README 寫 `codex mcp add exa --url https://mcp.exa.ai/mcp`；帶金鑰的寫法待驗證。
- **OmniKit 的同步**：`data/mcp/servers.yaml` 的 schema 只收 `command`（stdio），遠端 URL 型要改 schema 與 `agents.py`；功能凍結到 2026-11-29。
- **另一條路**：`omnikit-research` 的 `sweep.py` 加一個 exa 管道，像這次的 `exa_run.py` 直接對 hosted MCP 講協定，不裝進任何 agent。

### 對話開頭的大小

- tools/list 實測：2 個工具，定義合計 2,421 bytes（`web_search_exa` 1,555 字元、`web_fetch_exa` 861 字元）；server instructions 458 字元。以每 token 3.5 到 4 字元估，約 600 到 700 token（估計，沒有用 tokenizer 量）。
- **Claude Code**：官方文件（code.claude.com/docs/en/mcp，Scale with MCP tool search）寫 tool search 預設開，session 開頭只載入工具名稱與 server instructions。開頭只多 2 個工具名與 458 字元的 instructions，估計約 120 token。
- **Codex、Antigravity**：會不會延遲載入待驗證；最壞情況全量載入，約 700 token，低於門檻 2,000。
- **走 `sweep.py` 管道**：0，只在調研時呼叫。

### 過程中的發現與疏失

- `objective` 是必填，事先寫的決策規則沒有預料到；每組都跑了兩種（任務描述、只填關鍵字），結果幾乎一樣。
- 原本以為要金鑰才能測；README 寫匿名可用，就直接用匿名跑，沒用到金鑰，也沒改任何 agent 的設定。
- `omnikit-research` 的 `sweep.py` 第一版在這次實測暴露 3 個問題，同一天修好：npm、skills.sh 的雜訊被算成新名字（改成只算判斷過、用 `add` 記的名字）；多字關鍵字被 `gh` 當成整句精確比對，`codebase diagram generator` 回 0 筆（改成拆字）；topic 只試整串（加試相鄰兩個字，`architecture-diagram` 這樣才撈到 Archify）。
- 「相關工具」是我（Claude）一個人判斷的，沒有第二位評審。標準：能把 repo 或程式碼自動畫成架構、結構或依賴圖的工具；只畫 git 歷史的算雜訊。名單在 `compare.py`。
- 名字照 `sweep.py` 的規則比：短名一樣就算同一個，所以 arrufat/meduza 與 tensorush/meduza 算一個；pypi 的 diagramgen 與 openclaw 的 diagram-gen 也被併成一個。
- Exa 每次預設 10 筆，WebSearch 回 10 到 26 筆，名字數不是在相同筆數下比的。
- 沒測 `web_fetch_exa`、`web_search_advanced_exa`。

### 沒驗證到的

- 匿名限速多少。
- MCP 的 `web_search_exa` 計費算哪個搜尋型別。
- Codex、Antigravity 怎麼載入 MCP 工具定義。
- 裝成 MCP 之後模型會不會主動叫用 Exa。這次是直接打協定；WR1 的 firecrawl 就是裝了卻幾乎沒被叫用。

## 下一步

- Exa 改 `trial` 到 2026-11-30。試用的接法：使用者 2026-11-16 選 `sweep.py` 加 exa 管道（開頭成本 0、每次調研一定會查到、不用金鑰），不裝成 MCP。
- 試用結束看兩件事：調研時 Exa 帶來的新名字占多少、有沒有撞到匿名限速。撞到才請 ryan 註冊金鑰放進 `EXA_API_KEY`。
- Tavily 維持 `pending`，不測。
