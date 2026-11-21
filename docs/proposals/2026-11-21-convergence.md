# 對話收斂：現況統整、業界做法與建議

日期：2026-11-21。狀態：使用者 2026-11-21「暫定全照建議」；第 5 節照使用者的修正改寫成蒸餾的工作流，不用固定數字的規定。
起因：使用者說最近常開發到一半對話越來越發散，不知道離完工還有多遠、下一步是什麼；問業界頂尖工程師怎麼做、有沒有工具。另附一則 OmniKeep 摘要（AI 糾正改寫成自動檢查），問能不能拿來優化 OmniKit。

## 0. 要你決定的事

| # | 決定 | 我的建議 |
|---|---|---|
| 1 | 收斂做法要不要採用（第 5 節） | 已採用（暫定）。使用者修正：不要「最多開幾條」的死規定，要蒸餾頂尖工程師的工作流，第 5 節已改寫 |
| 2 | 「糾正改成檢查」（第 6 節）什麼時候做 | 12-01 解凍後試點 3 條；凍結期不加 hook |
| 3 | 主線要不要換新對話 | 換。舊主線 1,033 項、27 回合，新主線讀 NOW.md 接手；舊的接手後再 settle |
| 4 | 沒設定 `visibility` 的新使用者預設哪一種；規則版本要不要升 | 預設 `visible` 照 540f27c 不改；規則版本升到 2026-11-21-1（這週 AGENTS.md 改了兩條：visibility、Gemini 3.8 Flash 分派限制） |

只有你能做的：問法庫實測（`data/pilot/ask-test.md`）。紀錄表目前 0 筆，判定要 10 次以上；這是 11-17 定案的完工路徑第 1 步，4 天沒動。

## 1. 現在 OmniKit 的所有對話

範圍：T3 的 OmniKit 專案（46 條，active 4 條、settled 42 條）。Claude 桌面版的對話不在 T3 清單裡，這次沒列。

### Active

| 對話 | 狀態 | 剩下的事 | 這次怎麼處理 |
|---|---|---|---|
| OmniKit 主線（`mcp:launch:cc0092cd…`） | 11-20 15:40 停在【進行中】 | 第 5 項 R1：Gemini 4 Hydrogen 審查 T2 到 T5，等你回「續跑」 | 主線不 settle；建議換新主線（決定 3） |
| T3 MCP 斷線防護（`mcp:c230ce85…`） | 【完成待收尾】，2c892de | T3 更新設定（已在 NOW.md）；Codex 的新 hook 要在 `/hooks` 信任一次 | 待辦搬進 NOW.md，settle |
| Gemini 派送改回 T3 可見（`mcp:ad81de99…`） | 【完成待收尾】，238ec1e、540f27c | 預設 `visible` 確認、規則版本要不要升（決定 4）；NOW.md 還沒記這件事 | 補進 NOW.md，settle |
| 開發對話收斂與進度管理（這條） | 進行中 | 等你回第 0 節 | 回完就 settle |

### 11-17 方向定案後 settled 的 13 條

模型角色化調研、看板競品調研、Antigravity 原生讀規則實測、plugin 與 skill 同步到各帳號、設計 agent 調研、無頭瀏覽器調研、審查工具調研、prompt-audit 收尾，以及 5 條「套用 commit」的代跑對話。結論都在 repo，NOW.md 都有指向。

### 不是對話、但也掛著的

- `data/profiles/ryan/AGENTS.md` 有一段沒 commit 的「Gemini 3.8 Flash 子任務分派限制」，三條對話都說不是自己改的、沒動。`dispatch.md` 已經 commit 了同一條，這次一起 commit。
- `data/evals/` 底下沒 commit 的檔：`run_gemini.py`（R1 用，R1 做完一起 commit）、orchestrator-bench 的 log 與結果、`.done` 標記、`verify_tmp.jsonl`。沒刪，等 R1 收尾時一起整理。

## 2. 為什麼會發散：證據

1. **完工路徑其實有，只是沒放在每天看的地方。** 11-17 的 `docs/proposals/2026-11-17-summary.md` 第 7 節定了 4 步（問法庫實測 → 12-01 手動更新 → 11-29 後 plugin 取代自製接法 → 刪停用腳本）。NOW.md 有 11 項編號、5 條其他線、7 條已定案，但沒有這 4 步，所以從 NOW.md 看不出離完工多遠。
2. **定案後的工作大多不在那 4 步裡。** 11-17 13:32 之後 61 個 commit（feat 23、docs 30、fix 6、wip 2）。標題提到 T3、Antigravity、分派、帳號、轉接、MCP 的 32 個；評估、調研、WP1、R1、雷達的 25 個；問法庫評測 12 個（分類有重疊）。凍結期的規則是「只修錯、瘦身、試點修正」，但 23 個 feat 照樣進來。
3. **插單沒有上限。** T3 nightly 更新三天內引發 3 次急件（ACP 轉接程式、多帳號、MCP 斷線）。這些該修，但每次修完都順手延伸（例如 visibility 偏好、setup 訪談加一題），插單就變成新功能。
4. **等你的事散在各對話最後一則。** visibility 預設、規則版本、Codex hook 信任這三件，只寫在子對話的結尾，NOW.md 沒有。你不打開那條對話就不知道。
5. **NOW.md 會過期。** 「下一步」還寫著等第 3 項 WP1 盲選，其實 11-19 已經完成。
6. **主線太長。** 主線 11-19 到 11-20 兩天累積 1,033 項、27 回合，中間換過 Gemini 4 Neon 又換回 Claude。

一句話：缺的不是記錄（NOW.md、交接都有），是三個機制：**完工定義放在最上面、同時進行的數量有上限、新想法有地方放但不立刻做**。

## 3. 業界做法

| 做法 | 解決哪個問題 | 重點 | 來源 |
|---|---|---|---|
| Shape Up 的 appetite 與 scope hammering | 一直加範圍 | 先定願意花多少時間，時間到就砍範圍，不延長時間 | [Basecamp《Shape Up》](https://basecamp.com/shapeup/3.4-chapter-12) |
| Shape Up 的 hill chart | 不知道離完工多遠 | 不報百分比，只分「上坡：還在想怎麼做」「下坡：只剩執行」；風險高的先推過山頂 | [同上](https://basecamp.com/shapeup/3.4-chapter-12) |
| Kanban 的 WIP 上限 | 同時開太多條 | 同時進行的數量設上限，滿了就先收完一個再開新的（stop starting, start finishing） | Kanban 通用做法 |
| 完成條件（Definition of Done） | 說做完其實沒有 | 每一項都有能驗證的完成條件；Claude Code 官方最佳實務也要求先給驗證標準 | [Claude Code best practices](https://code.claude.com/docs/en/best-practices) |
| Anthropic 長時間 agent 的 feature list 加 progress 檔 | agent 提早宣告完成、跨對話接不起來 | 第一回合把所有功能寫成清單、全部先標未通過；之後每回合只做一項、通過才改狀態、寫進 progress 檔 | [Anthropic Engineering](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) |
| Ralph 迴圈 | 同上 | `prd.json` 每個 story 有 `passes` 欄位，迴圈做到全部通過為止；跨回合只靠 git、progress.txt、prd.json | [snarktank/ralph](https://github.com/snarktank/ralph) |
| 規格驅動（Spec Kit、OpenSpec） | 需求在對話裡漂移 | 每個變更一個資料夾（提案、規格、tasks 勾選），做完封存 | [github/spec-kit](https://github.com/github/spec-kit)、[Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) |
| GTD 的收件匣與每週回顧 | 新想法打斷手上的事 | 想到就記一行、不立刻做；每週固定一次看完、決定做不做 | GTD 通用做法 |

這幾種做法的共同點：**完工是一張清單，每一項是「通過／沒通過」，不是靠印象估百分比**。OmniKit 的 NOW.md 跟 Anthropic 的 progress 檔是同一種東西，缺的是那張「全部先標未通過」的清單。

## 4. 工具：調研結果

查了 10 組關鍵字，75 個相關名字，沒有飽和（第 7 節）。分成四類：

| 類別 | 代表（★ 為 2026-11-21 gh api 實測） | 跟 OmniKit 合不合 |
|---|---|---|
| 規格驅動框架 | github/spec-kit ★150,856 MIT；Fission-AI/OpenSpec ★75,366 MIT；bmad-code-org/BMAD-METHOD ★55,583；obra/superpowers ★322,987 MIT；awslabs/aidlc-workflows ★6,189 MIT-0 | 偏「單一功能從需求到程式」，OmniKit 的發散是在「很多條線之間」，不是單一功能內，幫助有限 |
| 給 agent 用的任務板 | gastownhall/beads ★28,881 MIT；eyaltoledano/claude-task-master ★28,503；MrLesk/Backlog.md ★7,456 MIT；automazeio/ccpm ★8,459 MIT | 最對題。beads 的 `bd ready` 會列出沒有被擋住的下一步，正好回答「下一步是什麼」。都要另裝，凍結期不裝 |
| 計畫寫成檔案 | OthmanAdi/planning-with-files ★28,163 MIT | 跟 NOW.md 同一招，OmniKit 已經有 |
| 自動迴圈 | snarktank/ralph ★22,312 MIT 等 Ralph 變體 | 要能自動驗證的任務才合用；OmniKit 很多項目要你拍板，不適合整條自動跑 |

結論：**現在不建議裝新工具。** 一是凍結到 11-29；二是 OmniKit 已經有狀態板與交接，缺的是第 2 節講的三個機制，裝工具補不了。如果之後要工具，beads 最值得評，12-01 跟收件匣一起用 `omnikit-eval` 評（已記進 `data/inbox.md`）。

## 5. 頂尖工程師的共通工作流

第一版寫的是「同時最多 1 條主線加 2 條子對話」這種數字規定，使用者指出那不是頂尖工程師的做法。改看 6 個人實際怎麼做：Mitchell Hashimoto（Ghostty、HashiCorp）、Kent Beck（TDD 提出者）、Boris Cherny（Claude Code 作者）、Harper Reed、Simon Willison、Peter Steinberger。他們沒有人用固定數字限制對話數；共同的限制是：**每條在跑的對話，都對到清單上一個還沒勾的項目**。蒸餾成 7 步的循環：

1. **規劃和執行分開。** 想法還模糊時，先開一條只做規劃的對話，產物是一份清單，不寫程式。
   - Mitchell：「split the work into separate planning vs. execution sessions」（原文）。
   - Harper Reed：先讓 LLM 一次問一題、把需求問成 spec.md，再拆成 prompt_plan.md 與 todo.md 勾選清單（二手整理）。
   - Boris：先用 plan mode 把計畫對好再動手（二手整理）。
2. **清單每一項都能驗證。** 用測試、截圖、實際輸出讓 agent 自己判斷過了沒；離完工多遠，就是還沒勾的項目數。
   - Mitchell：「give an agent a way to verify its work」，它多半會自己修好錯（原文）。
   - Beck：plan.md 裡放一個個測試，「find the next unmarked test」（原文，附錄的 system prompt）。
   - Anthropic：第一回合先把所有功能列成清單、全部標未通過，通過一項才改一項。
   - Willison：測試已經「no longer even remotely optional」。
   - Boris：每個改動都讓 Claude 開瀏覽器自己測到能動（二手整理）。
3. **一條執行對話只做一項；下一步永遠是清單上第一個沒勾的。**
   - Mitchell：「Don't try to 'draw the owl' in one mega session」（原文）。
   - Beck：說「go」就做下一個沒標記的測試（原文）。
4. **看到偏離訊號就停。** Beck 列了三個訊號（原文）：在繞圈；做了沒要求的功能，就算是合理的下一步；作弊，例如關掉或刪掉測試。第二個就是 OmniKit 這週的主因（第 2 節第 3 點）：插單修完順手延伸。停下來的做法是把延伸的想法記進收件匣，這條對話照原本的完成條件收掉。
5. **並行看你審得過來多少，不是固定數字。**
   - Boris 同時跑 5 條、Steinberger 3 到 8 條，每條都是彼此獨立、目標明確的工作（二手整理）。
   - Mitchell 反過來，刻意不跑多條（「I don't want to run agents for the sake of running agents」）、關掉 agent 的桌面通知，在自己的空檔才去看（原文）。
   - 兩種都成立，前提都是每條都是清單上的一項。
6. **研究、評估、分類排到一天的尾巴。** Mitchell 每天最後 30 分鐘派背景 agent 做調研、探索模糊的想法、分類 issue，隔天先看結果，只挑 agent 一定做得好的去執行（原文）。OmniKit 的工具評估與調研屬於這一類，現在卻是白天插進主線。
7. **每次糾正都變成 harness。** Mitchell：「anytime you find an agent makes a mistake, you take the time to engineer a solution」（原文）。他 AGENTS.md 的每一行都來自一次 agent 犯錯，能寫成工具的就寫成工具。poteto 的倒金字塔講的是同一件事（第 6 節）。

套到 OmniKit：

- **第 1、2 點**：NOW.md 頂端的「完工路徑」就是這份清單，每步都寫了完成條件與進度（已做）。`omnikit-handoff` 的 NOW.md 格式加了這一節，其他專案也照用。
- **第 3 點**：每條對話開頭寫一句「這條做清單上的哪一項、做到什麼算完成」。清單上沒有的事，先在規劃對話裡加進清單，再開執行對話。
- **第 4 點**：清單外的想法記 `data/inbox.md`；急件修完就停，在 NOW.md 的「插單紀錄」記一行。
- **第 6 點**：工具評估與調研改成傍晚派、隔天看，不在白天的主線裡開。
- **第 7 點**：12-01 試點第 6 節的 3 個檢查。之後可以加一個 Stop 檢查，收尾時對照完成條件，問這回合有沒有做清單外的事，把第 4 點也變成檢查。

來源：[Mitchell〈My AI Adoption Journey〉](https://mitchellh.com/writing/my-ai-adoption-journey)、[Kent Beck〈Augmented Coding: Beyond the Vibes〉](https://newsletter.kentbeck.com/p/augmented-coding-beyond-the-vibes)、[Harper Reed〈My LLM codegen workflow atm〉](https://harper.blog/2025/02/16/my-llm-codegen-workflow-atm/)、[Simon Willison〈Vibe engineering〉](https://simonwillison.net/2025/Oct/7/vibe-engineering/)、[InfoQ：Claude Code 作者的工作流](https://www.infoq.com/news/2026/01/claude-code-creator-workflow)、[Simon Willison 轉述 Steinberger](https://simonwillison.net/2025/Oct/14/agentic-engineering/)、[Anthropic：long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)。Mitchell 與 Beck 是 2026-11-21 讀原文；Boris、Harper、Steinberger 只看到二手整理，細節標待驗證。

## 6. 題外話：糾正改成檢查，套到 OmniKit

那則摘要的核心是講者 poteto 的倒金字塔：越下層擋錯越貴，依序是程式設計、自動檢查、驗證、文字規則、人工審查。OmniKit 現在大多停在文字規則（`baseline.md`、`AGENTS.md`）與你的人工糾正。

OmniKit 其實已經有兩個「糾正改成檢查」的例子：說做不到查證的 Stop hook（`engine/scripts/claim_check.py`）、分派政策檢查（`dispatch.py check`）。可以照同樣做法再改幾條：

| 你糾正過的（出處） | 改成什麼 | 層級 |
|---|---|---|
| Gemini 思考程度一律 high 以上，寫了三處（AGENTS.md、dispatch.md、NOW.md） | PreToolUse hook：`t3 thread start` 或 `t3_thread_launch` 派 Gemini 時，模型代號沒帶 `-high`、`-xhigh` 或 `thinking_level` 低於 high 就擋下 | 自動檢查 |
| 派出去的 Opus 子任務 effort 預設 medium | 同一支 hook 一起檢查 | 自動檢查 |
| 嚴禁 LaTeX 數學語法 | Stop hook 掃回覆裡的 `$...$`、`\frac`、`\times`，有就退回一次 | 自動檢查 |
| 收尾第一句要有狀態標籤 | T3 子對話結束時檢查最後一則回覆的第一句 | 驗證 |
| NOW.md 過期（第 2 節第 5 點） | `now_check`：「下一步」提到的項目已標完成就報錯；子對話結尾有【等你決定】但 NOW.md 沒有就報錯 | 自動檢查 |
| 分派一律用 `run.py show` 的建議，不靠預設值 | 更下層：派送只透過一支 `run.py launch`，模型與程度由它帶，手打的指令根本寫不出錯的代號 | 程式設計 |

試點建議挑前三條：規則最明確、最常被糾正、誤報風險低。改完把對應的文字規則縮成一行「由 hook 檢查」，規則檔跟著瘦身，也符合凍結期的方向。凍結期不加 hook，12-01 解凍後做。

摘要本身有一處錯：「用 Lean 證明捲動清單不閃不抖」的 Lean 是定理證明器 leanprover/lean4（★10,095），不是摘要連到的 QuantConnect/Lean（★22,637，量化交易引擎）。這是 OmniKeep 對開源專案名稱比對的 bug，要在 OmniKeep 專案另開對話修。摘要裡的 pstack 我在網頁搜尋與 GitHub 都找不到，演講原文也沒找到，數字（10,926 個 PR、0.47%）都是講者自報，標待驗證。

## 7. 調研紀錄

- **管道**：GitHub topic、GitHub 關鍵字、awesome 清單、skills.sh、npm、官方 MCP Registry、Hacker News、Exa，每組都查（`sweep.py channels`）；英文與中文網頁搜尋；Product Hunt 用網頁搜尋帶到（Backlog.md）；related 抽了 github/spec-kit 的 fork（只有小 fork，沒有新的大專案）。
- **10 組關鍵字**：spec-driven development；issue tracker for coding agents；AI 寫程式 對話發散 進度追蹤（只查了中文網頁，這組不算完成）；task management for ai agents；markdown backlog in git repo（不含 AI 字眼的一般說法）；long-running agent harness；ralph loop prd progress；规格驱动开发；agentic sdlc workflow；session handoff progress tracking claude code。擴展的詞來自結果：harness、Ralph、AI-DLC、progress file。
- **停在第 10 組，沒飽和**：`status --min-stars 1000` 印「還不能停」，第 10 組還有新的 ★1,000 以上名字（sodiumsun/agenttrail、OthmanAdi/planning-with-files）。原因是題目混了四類（規格驅動、任務板、計畫檔、自動迴圈），每換一組就進到新的子領域。這次的目的是找做法、不是選工具，所以先停；★1,000 以下與沒有星數的產品不保證找齊。真的要選工具時，拆成「給 agent 用的任務板」單一子題再跑一次。
- **查不到的**：poteto 的演講原文、pstack（網頁搜尋與 GitHub 都沒有）；Claude Code 官方最佳實務頁只看到摘要片段。
- **待驗證**：各工具的功能說明都來自 README 與第三方文章，沒有實測；摘要裡的 PR 數、撤銷比例、token 比例是講者自報。
