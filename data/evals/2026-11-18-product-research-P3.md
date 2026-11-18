# 產品研究槽位實測：P3，omnikit-research 對開源 deep research（2026-11-17 到 11-18）

使用者點名的第 2 層評估。起因：評估 14 個外部連結時，使用者問「網路上很多開源高分搜索工具，omnikit-research 有優勢嗎？」。名冊裡 GPT Researcher、Open Deep Research 等 10 張 deep research 卡片都是 `pending`，從來沒有跟 omnikit-research 比過。

## 要回答的問題

1. 同一題，開源 deep research 工具找到的名字，跟 omnikit-research 比是多是少？找得到 Archify 嗎？
2. 有沒有值得當成 omnikit-research 選用管道的？
3. 會改變的決定：GPT Researcher、Open Deep Research 的卡片（`pending`）、新候選的卡片；omnikit-research 本身要不要改。

## 決策規則（實測前寫下，2026-11-17 22:45）

- **題目**：沿用 P2 的「找能把 GitHub repo 自動畫成架構圖的工具」。P2 的資料（88 個名字的聯集、Archify）當參考，不給任何一組看。
- **判斷標準**（跟 P2 一樣）：能把 repo 或程式碼自動畫成架構、結構或依賴圖的工具才算相關；只畫 git 歷史的、要人手畫的圖表工具或函式庫、只產生文字的、教學文、論文算雜訊。
- **組別**：A omnikit-research（Hydrogen high 照 skill 跑到「可以停」）、B GPT Researcher（deep research 模式，預設設定）、C Open Deep Research（預設設定）、D（看 R1 調研補一個）。B、C、D 各 2 次，給同一段英文指令（見 `2026-11-18-product-research-P3/scripts/run_gptr.py` 的 `QUERY`）。
- **量什麼**：有沒有找到 Archify；相關名字數；A 沒有的相關名字、A 有它沒有的；雜訊比例；時間與費用。
- **怎麼判相關**：所有組的名字混在一起、拿掉來源、打亂順序，兩位評審各自判；意見不同的由主控定案並列出。
- **判定**：
  1. 當成 omnikit-research 的選用管道（`trial` 兩週），全部要成立：2 次裡至少 1 次找到 Archify，或平均多出 5 個以上 A 沒有的相關名字；雜訊比例不比 A 高 20 個百分點以上；每次平均費用不到 US$1；Windows 不用 Docker 就能跑。
  2. 可以取代 omnikit-research（只提案）：2 次都找到 Archify、平均找到 A 相關名字的 80% 以上、時間不比 A 長。
  3. 都不成立：卡片記 `rejected`（產品研究槽位），理由寫數字。
  4. B、C 的相關名字數都不少於 A 的話，寫明「這一題 omnikit-research 在找齊名單上沒有優勢」。

## 開跑前與過程中的變更（照時間）

每一項都在當下記進計畫檔，才往下做。

1. **C 組換人（11-17 22:58）**：Open Deep Research 第 0 層不通過，repo 已封存（最後 push 2026-08-10，README 沒有寫接替的專案）。照硬性門檻，結果再好也進不了名冊，所以不跑。改從 R1 調研挑一個當 C 組（第 4 項）。
2. **B 組改用 Gemini（11-17 23:15）**：預設要 OpenAI，但那把金鑰的帳戶沒有額度（429「You have no credits remaining」，沒有任何請求成功、沒花到錢）。使用者選改用 Gemini 免費金鑰，三個角色都設 `gemini-4-hydrogen`（跟 A 組同一個模型），embedding 用 `gemini-embedding-001`，搜尋照預設用 Tavily。
3. **兩個相容性問題（11-17 23:20）**：
   - GPT Researcher 0.17.0 在繁中 Windows 上一印 emoji 就因為 cp950 編碼當掉，要開 Python 的 UTF-8 模式（`-X utf8`）。
   - 用 Gemini 4 時，langchain-google-genai 4.5.0 回傳的 content 是分段的 list，GPT Researcher 只對 `minimax_anthropic` 改用 `.text`，所以在 `deep_research.py` 的 `response.strip()` 當掉。執行腳本加了一處修正，讓 `google_genai` 也走它既有的 `.text` 路徑，研究流程沒動。
4. **A 組停在額度用完的那一刻、C 組改用 local-deep-research（11-17 23:45）**：Antigravity（ryan）的額度在 A、R1 兩條調研跑到第 12、13 組時用完（3 天 11 小時後重置）。兩邊每組都還有一大半是新名字，完全沒有收斂，所以 A 組照帳本當下的內容算，標「未飽和」，不改派 Claude 續跑。C 組改用 LearningCircuit/local-deep-research 2.0.1（★9,597、MIT、第 0 層通過、名冊沒有）：R1 帳本裡近期有更新、pip 就能在 Windows 裝、能用 Gemini、研究時自己挑搜尋引擎的一個。R1 沒飽和，所以它只是「符合條件的一個」，不保證是最好的對手。
5. **B、C 改用本機模型（11-18 02:25）**：Gemini 免費版的 `gemini-4-hydrogen` **一天只能 20 次請求**（429 RESOURCE_EXHAUSTED，`generate_content_free_tier_requests, limit: 20`）。B 第 1 次跑了 31 分鐘、0 個來源；B 第 2 次與 C 兩次一開始就被拒。這 4 次不算結果（`out/failed/`）。改用這台的 Ollama `qwen3:8b`（RTX 2000 Ada，16 GB；local-deep-research 的預設本來就是 Ollama）：兩邊 context 都設 20,480（LDR 的本機預設），思考模式照 LDR 預設開著，一次只跑一個。**B、C 用的是 8B 小模型、A 組是 Gemini 4 Hydrogen，所以 B、C 的結果只能當下限。**

## 結果

原始資料在 `2026-11-18-product-research-P3/`（見最後一節）。

### 總表

「相關」是兩位評審的區間：下限是兩位都判相關，上限是至少一位判相關或不確定、而且不是兩位都判不相關。雜訊是兩位都判不相關（含連結核對判定編造的）÷ 列出的名字。名字照短名對齊，所以 A 的 221 個合併成 217 個。

| 組 | 列出 | 相關 | 雜訊 | 其中編造 | Archify | A 沒有的相關名字（下限） | 涵蓋 A 的相關名字 | 時間 |
|---|---|---|---|---|---|---|---|---|
| A omnikit-research | 217 | 162 到 213 | 4（2%） | 0 | 有 | — | — | 約 53 分鐘（未飽和） |
| B1 GPT Researcher | 6 | 1 到 2 | 4（67%） | 0 | 沒有 | 0 | 0.6% | 19.5 分鐘 |
| B2 GPT Researcher | 9 | 2 到 5 | 4（44%） | 3 | 沒有 | 0 | 1.2% | 22.5 分鐘 |
| C1 local-deep-research | 75 | 10 到 22 | 53（71%） | 18 | 有（連結錯） | 2 | 4.9% | 43.6 分鐘 |
| C2 local-deep-research | 42 | 12 到 17 | 25（60%） | 19 | 有 | 0 | 7.4% | 29.0 分鐘 |

B、C 用的是本機 qwen3:8b，A 用 Gemini 4 Hydrogen，見「要打折看的地方」。

### A：omnikit-research（未飽和）

- 12 組完整的關鍵字（第 13 組做到一半就碰到額度用完），221 個不重複的名字（短名一樣算同一個）。其中 185 個是 GitHub repo，36 個是產品或網站。
- 每組都有 9 到 34 個新名字，從頭到尾沒有收斂。
- 找到 Archify：第 1 組（中文網頁搜尋）。
- **★1,000 以上的名字第 7 組之後就沒有新的了**：

| 組 | 新名字 | 其中 ★100 以上 | ★1,000 以上 |
|---|---|---|---|
| 1 | 14 | 4 | 4 |
| 2 | 34 | 12 | 7 |
| 3 | 31 | 16 | 8 |
| 4 | 14 | 10 | 7 |
| 5 | 23 | 9 | 1 |
| 6 | 23 | 4 | 1 |
| 7 | 21 | 10 | 3 |
| 8 | 9 | 0 | 0 |
| 9 | 12 | 3 | 0 |
| 10 | 12 | 4 | 0 |
| 11 | 17 | 5 | 0 |
| 12 | 11 | 1 | 0 |

- 跟 P2 比：P2 三組關鍵字的 88 個名字，A 只找到 29 個（33%）。P2 有、A 沒有的 59 個裡，★1,000 以上、而且真的相關的只有 1 個（jfeliu007/goplantuml，★2,082，從 Go 程式碼產生 PlantUML 類別圖）；另外 3 個 ★1,000 以上的（Claude Code 使用指南、GenAI 開發框架、agent 建構平台）照判斷標準不算相關，是 P2 單一評審放寬了。長尾很大，兩次獨立調研的小 repo 重疊很少。
- 時間：第 1 到 4 組 13 分鐘（22:36 到 22:49），第 5 到 12 組約 40 分鐘（23:21 起）；中間斷線一次。花的是 Antigravity 的訂閱額度，跟 R1 一起把一週的額度用完。

### B：GPT Researcher 0.17.0（本機 qwen3:8b）

| | 第 1 次 | 第 2 次 |
|---|---|---|
| 時間 | 19.5 分鐘 | 22.5 分鐘 |
| 來源數 | 150 | 140 |
| 報告長度 | 9,949 字元 | 10,502 字元 |
| 列出的工具 | 6 個 | 9 個 |
| Archify | 沒有 | 沒有 |
| 它自己估的費用 | US$1.10 | US$1.19 |

- 第 1 次的子題偏到「AI 導入的成本與 ROI」，150 個來源幾乎都跟題目無關；報告自己寫「Their inclusion is based on general knowledge, as the sources do not directly reference them」，列的 6 個工具（GitHub Copilot、Code Outline、CodeScene、Sourcegraph、Dependency Cruiser、Graphviz）是模型憑記憶寫的。
- 第 2 次比較切題，但 9 個裡有 **3 個是編的**（連結核對見 `linkcheck-B2.txt`）：`github.com/github/codegraph` 404、`codedepend.com` 連不上、`codemap.io` 被轉址到賭博網站；另外 Code2Flow 的連結（`github.com/Code2Flow/Code2Flow`）404（真的在 scottrogowski/code2flow）、CodeScene 的 `codescene.net` 連不上（官網是 .com）。
- 「它自己估的費用」是照它內建的價目表算的，本機模型實際花費是 0。

### C：local-deep-research 2.0.1（本機 qwen3:8b）

- 兩次報告各 71,844、63,045 字元，比 B 長很多；工具名單是從報告的表格與標題逐一收的（`C/` 裡的報告原文）。
- **編造很多**：C1 給的 20 個 GitHub 連結有 10 個不存在、12 個 VS Code 擴充 ID 有 8 個不存在，還有 `yourusername/...` 這種範本佔位字串與 `example.com`；C2 提到的 29 個 repo 有 20 個不存在（`repo-graph/repo-graph`、`gitstruct/gitstruct` 這類），5 個擴充 ID 有 4 個不存在。核對紀錄在 `linkcheck*.json`。
- **兩次都找到 Archify**：C2 連結正確（`tt-a1i/archify`）；C1 名字與描述對，但連結寫成 `github.com/archify`（一個不相干的組織），來源是一支 YouTube 影片。
- A 沒有、兩位評審都判相關的：C1 的 amitfounderspace/CodeXray（★1）與 codetoflow.com。C2 另外提到 Cocoon-AI/architecture-diagram-generator（★7,612），第一位評審判相關、第二位判不相關（「從自然語言提示詞生成，不是分析程式碼」），算爭議，不算進下限。
- 其餘大多是圖碼工具（Mermaid、PlantUML、D2、draw.io）、執行期監控產品（New Relic、Datadog 這類）、資安工具與論文。
- 在 Windows 上 pip 就裝得起來，第一次執行會自己下載期刊品質的資料；預設的 SearXNG 要自己架伺服器，這次改用 Tavily。

### 盲評

- 第一位評審：主控（Claude Opus 5.5），看得到來源。第二位：Gemini 3.8 Flash（antigravity_kai，照分派政策第二意見該用 Gemini Pro xhigh，但那個帳號額度用完），只拿到 `pool.md`：281 個名字、拿掉來源、打亂順序，GitHub repo 附描述。編造的 40 個由連結核對判定，沒有交給評審。
- 第二位評審：相關 217、不相關 63、不確定 1。
- 意見不同 67 個：主控不確定、對方相關 48 個（大多是沒有描述的產品，對方上網查了）；主控不確定、對方不相關 13 個；主控不相關、對方相關 5 個（openflowkit、gitprobe、cscout、apispec、erd-editor）；主控相關、對方不相關 1 個（Cocoon-AI）。所以表上用區間，不硬判。

## 判定

| 規則 | B GPT Researcher | C local-deep-research |
|---|---|---|
| 1. 選用管道：Archify 或多出 5 個以上 | 不成立（0/2 次 Archify，平均多出 0 個） | Archify 成立（2/2 次） |
| 1. 雜訊不比 A 高 20 個百分點以上 | 不成立（56% 對 2%） | 不成立（66% 對 2%） |
| 1. 每次費用不到 US$1 | 成立（本機 0 元） | 成立（本機 0 元） |
| 1. Windows 不用 Docker | 成立（但要 `-X utf8`，用 Gemini 4 還要改一處） | 成立（搜尋要改成 Tavily） |
| 2. 可以取代 | 不成立 | 不成立（涵蓋 A 的相關名字不到 8%） |

- **規則 1、2 都不成立。** 照規則 3，B、C 應記 `rejected`；但 B、C 跑的是 8B 本機模型，跟寫規則時設想的預設模型差很多，雜訊（尤其是編造）有一大部分是模型造成的。所以這次**不判 rejected**：GPT Researcher 維持 `pending`、local-deep-research 新增一張 `pending` 卡，數字寫在卡片上，等用前沿模型重跑再判。這一點偏離了事先寫的規則，寫在這裡。
- **規則 4**：B、C 的相關名字數（最多 22 個）遠少於 A（至少 162 個）。在這個題目、這些條件下，**omnikit-research 找齊名單的能力明顯比較好**；這個結論對前沿模型版的 B、C 還沒驗證。
- Open Deep Research：repo 封存，卡片記 `rejected`。

## 看到什麼

- **多管道對單一搜尋的差距很大。** B、C 都只透過網頁搜尋（Tavily）找，A 的 221 個名字裡，GitHub topic 一個管道就貢獻 65 個、GitHub 關鍵字 41 個。deep research 工具擅長把幾十頁整理成報告，不擅長把一類工具列齊。
- **小模型的 deep research 會編造。** C 的兩次加起來有 37 個編造的工具或連結，B2 也有 3 個。報告寫得很像樣（表格、引用編號），不逐一核對看不出來。要拿這類工具找工具，連結核對是必要的一步。
- **omnikit-research 自己的問題：長尾題目停不下來。** 12 組了每組還有一大半是新名字，兩條平行的調研就把一週的 Antigravity 額度用完。★1,000 以上的名字第 7 組之後就沒有新的，所以已經在 `61f2f0b` 加了 `status --min-stars` 的停法與 12 組上限。這個停法也會漏：P2 有、A 沒有的 goplantuml（★2,082）就沒找到。
- **兩次獨立調研的長尾重疊很少**（A 只找到 P2 的 33%），所以「找齊」在長尾上本來就做不到，有分量的名字找齊才是實際的目標。
- **Windows 上要先排掉的坑**：GPT Researcher 的 cp950 崩潰、Gemini 4 的 list content；兩個工具都假設有付費的 OpenAI 金鑰，免費路線（Gemini 免費版一天 20 次）跑不起 deep research。

## 用掉的資源

- Antigravity（ryan）：A 與 R1 兩條調研把這一週的額度用完（3 天 11 小時後重置）。
- Gemini API 免費版：`gemini-4-hydrogen` 當天的 20 次。
- OpenAI：0（帳戶沒有額度，請求都被拒）。
- Tavily：免費額度內（每月 1,000 credits），用量沒有逐次記。
- 本機 GPU：B 兩次約 42 分鐘、C 兩次約 73 分鐘。
- 第二位評審：Gemini 3.8 Flash（antigravity_kai）一次。

## 要打折看的地方

- 只有一個題目。
- B、C 用 8B 本機模型，A 用 Gemini 4 Hydrogen；B、C 的結果只能當下限，不能說「GPT Researcher 本身比較差」。
- A 沒有飽和（額度用完）；B、C 是全自動，A 是 agent 照流程跑。
- B、C 用英文指令，A 中英文都查。
- 第一位評審（主控）看得到每個名字是哪一組找到的；只有第二位評審是盲評。

## 下一步（建議）

1. **要不要用前沿模型重跑 B、C**（要付費，使用者決定）：OpenAI 儲值或 Gemini 開 Tier 1，各跑 2 次，GPT Researcher 自己估每次約 US$1 多（待驗證）。重跑才能決定兩張卡要 `trial` 還是 `rejected`。
2. omnikit-research 用新的 `--min-stars` 停法實際跑一個新題目，看會不會太早停。
3. Exa 試用到 11-30：A 的 221 個名字裡 Exa 貢獻 39 個（第一次找到的管道），試用結束時照 P2 的規則看。

## 原始資料

`2026-11-18-product-research-P3/`：

- `plan.md`：實測前寫的決策規則與照時間記的變更（就是上面兩節的原稿）。
- `A/`：`R2-ledger.json`（omnikit-research 的帳本）、`A-names.tsv`（名字、第幾組、哪個管道第一次找到）、`A-stars.json`（gh api 星數，2026-11-17）、`P2-missed-stars.json`。
- `B/`、`C/`：每次的報告（`.md`）與執行資訊（`.json`）；`linkcheck-B2.txt`。
- `failed/`：沒跑成的那幾次的說明（log 太大沒放，摘要寫在上面的變更）。
- `judge1.json`、`judge2.json`、`pool.md`、`compare.json`：兩位評審的判定與比對結果。
- `scripts/`：`run_gptr.py`、`run_ldr.py`、`ledger_names.py`、`gh_stars.py`、`build_pool.py`、`compare.py`。
