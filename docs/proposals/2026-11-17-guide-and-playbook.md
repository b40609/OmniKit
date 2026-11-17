# 方向修訂：從「工具顧問」改成「設定引導、當下提醒、問法庫」

日期：2026-11-17。狀態：提案，等使用者決定。接在 [2026-11-16-product-logic-review.md](2026-11-16-product-logic-review.md) 之後，依使用者對三個問題的回答修訂方案 A。

## 0. 要你決定的事

1. **方向**：OmniKit 收成三件事：設定引導（一次問答把官方功能設好）、當下提醒（該開新對話、該交接時講一聲）、問法庫（遇到某種情況該怎麼問）。建議、週報、換與換回、通知停用。我的建議：照這個做。
2. **起手清單的形式**：改成一頁三欄：人人都要的設定、實測過值得裝、實測過不用裝。只有實測過的才進後兩欄，所以一開始會很短。我的建議：照這個做，第 4 節說明為什麼「裝了一定比不裝好」的清單目前幾乎是空的。
3. **凍結期（到 2026-11-29）能不能做問法庫第 0 版**：凍結只准修錯、瘦身、試點修正。問法庫是新東西，但它正是試點指標 3（少了會不會非常失望）問出來的答案，而且只有一個 Markdown 檔。我的建議：算試點修正，先做給你自己用，實測過再給同事。

## 1. 你的三個回答改變了什麼

| 你的回答 | 改變的結論 |
|---|---|
| 同事各種組合都有：只用 Codex、只用 Claude、全都訂 | 跨 agent 要留。但要分清楚兩種跨法：**內容跨 agent**（規則檔、skill 都是 Markdown，三家都讀得懂）便宜；**讀紀錄跨 agent**（解析各家的對話紀錄算用量）貴而且一直壞。留前者，丟後者 |
| 少了會失望的是：壓縮與交接、分派、底線與全域規則的引導設定；新電腦的起手清單；使用技巧與問法 | 沒有一項是建議、週報、換與換回。昨天跟 Hydrogen 的分歧（它認為試用與換回、跨 agent 週報是該守的空白）就此定案：不守 |
| 先自己，再同事 | 每一樣先在你身上驗證有用才給同事；給同事的東西要接近零安裝 |

你的直覺跟這台的數字一致：官方 `/usage` 標出 87% 的用量發生在切換任務沒清 context 的對話，7 天內叫用最多的 OmniKit 功能是交接（12 次）。槓桿在使用習慣，不在工具清單。

## 2. 多模型分工：你現在的做法好不好

### 2.1 官方怎麼說（一手原文，2026-11-17 讀）

- 「And by default it's the same model (or a smaller one) on the same task. You get parallelism or a fresh pair of eyes out of it, but not a smarter answer.」
- 「Handing the same task to a subagent doesn't make the answer any better. A fresh reviewer does help, because it hasn't seen your reasoning」
- 子代理划算的四種情況：獨立的工作平行跑、把很長的輸出隔在主對話外面、要一個沒看過寫法的審查者、要給比主對話少的工具。
- 代價：每個子代理自己送請求，而且「a fresh subagent first has to gather context your conversation already had, so it can end up slower than doing the task where you are」。

跨廠商的分工，在這四種之外多兩個官方沒談的好處：**額度分流**（量大的苦工用便宜或額度多的那家）與**不同家族的審查**（盲點不同）。這兩個正是你的分派政策在做的事。

### 2.2 你自己的紀錄（`dispatch.py stats`，2026-11-14 到 11-17，17 筆）

| 級別與模型 | 筆數 | 一次通過 | 沒一次過的原因 |
|---|---|---|---|
| 中級，Sonnet medium | 6 | 6 | — |
| 中級，Hydrogen high | 5 | 2 | 1 筆結論不可靠（漏掉官方的 CUDA 變體）；1 筆被 agy 無頭權限擋；1 筆是主控把上限設太低 |
| 驗收，Hydrogen xhigh | 4 | 3 | 1 筆是呼叫端的長參數問題 |
| 高級與驗收，Opus high | 2 | 1 | 驗收抓到 22 項（這是驗收該做的事） |

樣本太少，不能下結論（政策自己訂的門檻是 20 筆）。看得出來的只有一點：Hydrogen 沒一次過的 4 筆裡，3 筆卡在管道或任務說明，1 筆是品質。跨廠商的成本主要是管道的摩擦，不是模型笨。

### 2.3 我的看法

**做法本身對，政策太細。** 你的做法涵蓋 11-16 調研歸納的 6 種模式裡的 3 種（主控加便宜工作者、不同家互審、直接驅動別家 CLI），沒有證據顯示換別的 harness 會更好。該改的是這幾點：

1. **「由 Claude 派」跟「直接在 T3 分工」不是二選一，看結果要不要回到同一個決定。** 前置苦工、調研、審查的結果要回到主控手上定案，由 Claude 派（agy_cli 或原生子代理）。彼此獨立、你想各自盯進度的工作包，直接在 T3 各開一條。官方對子代理與獨立 session 的分法也是這條線。
2. **不要為了品質而派。** 派的理由只有四個：省稀缺的額度、平行、隔離雜訊、獨立審查。範圍清楚的小修改留在主線做，寫任務說明加驗收常常比自己改還貴。
3. **規則的份量超過證據。** 現在是 11 種任務、4 個級別、前置與第二意見、4 條升級規則，背後只有 17 筆紀錄。每段對話固定載入的部分縮成四五行（上面第 1、2 點加「寫的跟審的不同家」），YAML 搬進 `omnikit-dispatch` skill，要派的時候才讀。現在這份每段對話約 2,559 tokens。
4. **給同事的版本要先問訂閱。** 共用層已經會跳過沒有實例的模型類別，缺的是「你訂了哪幾家」這一題與自動產生個人分派檔。只訂一家的人：只用原生子代理，分模型大小，不做跨家審查。訂兩家以上：加跨家審查。`omnikit-setup` 現在沒有問這題。
5. **略過權限的無頭模式只適合你自己。** agy 無頭要用 `--dangerously-skip-permissions`，只靠任務說明約束。給同事的預設應該只派唯讀的工作（調研、審查）到別家。

Codex 目前不在路由裡（2026-11-12 起是免費版）；之後重訂再加一個模型類別就好。

2026-11-30 照原訂計畫看統計：中級裡 Hydrogen 的筆數有沒有過半、一次通過率跟 Sonnet 差多少。

## 3. 引導設定：官方都有，為什麼還要一層

### 3.1 官方已經有的上手功能

| 功能 | 做什麼（官方指令表原文摘要） |
|---|---|
| `/powerup` | 互動小課程加動畫示範，教 Claude Code 的功能 |
| `/init`（設 `CLAUDE_CODE_NEW_INIT=1`） | 互動流程，除了 CLAUDE.md 還帶你設 skill、hook、個人記憶檔；找到 Codex 或 Gemini CLI 的設定會問要不要匯入 |
| `/team-onboarding` | 依你過去 30 天的使用產生上手指南，同事貼成第一則訊息就能設定 |
| `/insights` | HTML 報告：你怎麼用、哪裡出錯、可以試的功能 |
| setup-claude | 依角色裝 plugin、接工具、試一個 skill |
| 提示建議 | 每次回覆後建議你下一句可以問什麼 |

所以「教功能」與「依用量產生上手指南」官方都做了，而且會越做越多。OmniKit 不該再做課程或用量分析。

**`/team-onboarding` 在這台實跑的結果（2026-11-17，無頭模式，在 OmniKit 專案裡，不產生分享連結）：**

- 它只掃目前這個專案的對話。報告寫「4 sessions; 2 sessions with descriptors were available for classification, 36 sessions left out of the scan」。
- 「常用的 skill」只列出 `/doctor` 與 `/skill-doctor` 各 1 次，那是我昨天為了並排比較跑的；7 天內叫用 12 次的交接沒有出現。為什麼大部分對話沒被算進去，我沒有查到原因（待驗證：可能是桌面版開的對話或背景對話不算）。
- 產出的骨架是：工作類型比例、常用 skill 與指令、常用 MCP、設定清單（repo、MCP、skill）、**Team Tips（空白，等人填）**、**Get Started（空白，等人填）**，最後附一段給 Claude 的指示，讓它當新人的上手夥伴逐項帶。
- 結論：官方自動產生的是「裝了什麼、用了什麼」；「我們怎麼用、有哪些訣竅」那兩節留白給人寫。這正是第 3.2 節講的界線。它的交付形式值得借用：一份 Markdown，同事貼成第一則訊息，agent 就照著逐項帶，不用安裝任何東西。

### 3.2 官方做不到的（OmniKit 該做的）

官方最佳實務頁開頭就講了界線：「No default can know those things about your project」。官方能教功能，但不知道**你們的**約定：

- 你們的底線規則、語言、收尾的狀態標籤、交接檔放哪。
- 你訂了哪幾家、哪種工作派給誰。
- 只用 Codex 或 Antigravity 的同事（Claude Code 的課程幫不到他們）。
- 繁體中文。

### 3.3 送到使用者面前的三種方式（依「使用者需要懂多少」排序）

| 方式 | 使用者要懂什麼 | 現況 | 動作 |
|---|---|---|---|
| **預設值**：問答一次，之後自動生效 | 什麼都不用懂 | `omnikit-setup` 問語言、自主程度、習慣、情境 | 加：訂了哪幾家（產生個人分派檔）、這個專案「做完」要跑哪個檢查、要不要通知。最後帶著試一次 |
| **當下提醒**：事情發生時講一句 | 看得懂那一句 | `session_nudge.py`：自動壓縮第 1、3、9 次與第一次 push 時，建議開新對話或交接 | 留。這是三種裡最有效的形式，因為不用記 |
| **想問時查**：說「這種情況該怎麼做」 | 知道可以問 | 沒有 | 新增問法庫（第 5 節） |

同類工具的調研（第 9 節）印證這個排序，各種送法被批評的地方：

- **課程與測驗**（官方 `/powerup`、claude-howto、Claude-Code-Quest）：忙起來不會打開，幾週後就忘。
- **每次自動改寫提示詞的 hook**（claude-code-prompt-improver 這類）：簡單的指令也被攔下來追問，打斷節奏。
- **靠 skill 的描述讓 agent 自己觸發**：不可靠。Scott Spence 的測試（2025-11，Haiku 4.5，合成的 API 呼叫，每種 50 次）：只加一句提示的 hook 觸發率 20%，強制先評估的 hook 84%。這是舊模型的合成測試，數字不能直接套到現在，方向是「不要指望它自己想到」。
- **手動的 slash command**（mattpocock/skills 的 `/grill-me`）：意圖明確時效果好，缺點是新手不知道有這招。

所以問法庫不能只靠 agent 自己想到，要有明確的叫法（「我不知道怎麼問」「幫我問好一點」），並且寫進上手指南讓人知道有這招。

### 3.4 不要教過時的習慣

官方最佳實務頁有一張「What you can stop doing」，引導的內容要照它：

- context 快滿不再是主要問題（多數模型 1M、會自動壓縮）；**換任務時清掉**才是重點，因為每一回合都會重送整段對話。
- 不用為了保護 context 而派子代理。
- 規則裡不用寫 IMPORTANT 或全大寫，「piling on emphasis mostly makes Claude over-apply the rule」；不能有例外的規則改用 hook 或權限。
- `think hard`、`be thorough` 是普通文字，想得多深由 effort 決定。
- 修正兩次還不對：`/clear` 重寫一則把學到的寫進去的提示詞，不要修第三次。

### 3.5 這是第四次替 OmniKit 保留位置，憑什麼這次不一樣

前三次保留的都是「偵測與衡量」（哪些沒在用、成本多少），那是 harness 天生做得比外掛好的事。這次保留的是「只有你知道的內容」：你們的規則、約定、問法、實測結論。官方的功能再多，也不會知道這些。判斷原則：**要量的交給官方，要寫的自己留。**

## 4. 起手清單：「裝了一定比不裝好」的有哪些

### 4.1 目前的證據指向「很少」

- 官方：「your first plain prompt in a fresh session already does the right thing, without any setup on your part」。
- OmniKit 自己的實測，內建幾乎都不輸：

| 用途 | 實測 | 結果 |
|---|---|---|
| 瀏覽器操作（Claude Code 互動使用） | `data/evals/2026-11-04-browser-u1.md` | 內建拿滿分，不用裝 |
| 找一手來源 | `data/evals/2026-11-13-web-sources-WR1.md` | 裝了 firecrawl，6 次只被叫用 1 次 |
| 程式碼理解 | `data/evals/2026-11-16-code-understanding-C1C2.md` | 內建兩題都不輸；graphify、Floorplan 裝著 0/6 被叫用 |
| 調研補漏 | `data/evals/2026-11-16-product-research-P2.md` | Exa 找到另外兩邊漏的，試用到 11-30 |
| 工具介面設計 | `data/evals/2026-11-14-frontend-design-F1c.md` | unslop 勝出，但判定有弱點（紀錄裡寫了），試用中 |

- 你舉的例子在這台的實況（官方 `/skill-doctor` 與 `/doctor`，2026-11-16）：caveman 7 天內叫用 7 次、最近一次是 9 天前；claude-mem 的 hook 被呼叫 38,630 次（自動的），但它帶的 skill 有二十幾個從沒叫用、每回合都佔 context。**兩個都在用，但都沒實測過「有它比沒它好」。** 用得多不等於有幫助。

- 外面的「必裝清單」（調研看了 6 份不同作者的）：**沒有任何一份附整體任務成功率的實測**，最多是單一工具的省 token 宣稱。出現在 3 份以上的，首先是三個**習慣**：規則檔、先規劃再動手（plan mode）、讓 agent 自己跑測試驗證（5 份以上）。第三方的有 obra/superpowers（4 份，★318,714）、frontend-design、mattpocock/skills 的 `/grill-me`（★325,990）、caveman（★120,774）、PreToolUse 與 PostToolUse hook。星數是 2026-11-17 gh api 實測；清單內容是 Hydrogen 整理的，我沒有逐份核對，待驗證。另有一派明講「什麼都不用裝」：短的規則檔加內建的 plan mode、`/clear`、`/compact`、`/context`，其他叫 agent 用本機的 CLI。
- 交集最大的是習慣，不是工具。這跟官方的說法、跟 OmniKit 自己的實測是同一個方向。

### 4.2 建議的形式：一頁三欄

| 欄 | 放什麼 | 現在有的 |
|---|---|---|
| **人人都要的設定**（不是工具） | 底線規則、語言、一個「做完要跑」的檢查指令、不能有例外的規則改成 hook 或權限、短的規則檔 | 底線與語言已有；檢查指令與 hook 還沒進引導 |
| **實測過值得裝** | 只收有實測紀錄的，寫明在哪種情況值得 | Exa（調研，試用中）、unslop（工具介面，試用中）、Codex 與非互動模式的瀏覽器工具 |
| **實測過不用裝** | 內建就夠的，省得同事白裝 | 瀏覽器（Claude Code 互動）、網頁來源、程式碼理解 |

另外一欄「在用但還沒測」：claude-mem、caveman、T3 Code、taste-skill。要進第二欄就各做一次實測（有它與沒它，用你的真實任務）。

外面清單交集裡、這台還沒有的候選：superpowers 與 `/grill-me`。這兩個跟問法庫是同一類東西，放在第 5 節一起測。

官方自己推薦、可以排進實測的候選：型別語言的 code intelligence plugin（官方說能少讀很多檔）；能用 CLI 的就不要裝 MCP（`gh`、`aws` 這類）。

這份清單短是它的價值：它能回答「新電腦要裝什麼」，也能回答「哪些不用裝」。126 張卡的名冊收成只留實測過與試用中的。

## 5. 問法庫：縮小新手與高手的差距

### 5.1 你貼的十條，對照官方建議

| # | 貼文的說法 | 對照 | 該做成什麼 |
|---|---|---|---|
| 1 | 從第一性原理找最本質的原因再修 | 口號本身是普通文字。官方的例子是給三樣模型看不到的東西：症狀、位置、「修好」長什麼樣，並要求先寫一個會失敗的測試 | 問法「修 bug」：填這三格 |
| 2 | 先問不清楚的地方，再出 3 版方案 | 官方同款：「Interview me until you could write the spec, then write it to SPEC.md」，寫完開新對話照規格做 | 問法「我還沒想清楚」 |
| 3 | 不要預設我的問題定義是對的 | 官方：Claude「tends to read a request conservatively」，範圍與目的只有你知道 | 問法「先確認我問對問題」 |
| 4 | 推演二階、三階影響 | 抽象推演容易空泛；有用的是要具體清單（誰會讀到舊格式、哪些測試會受影響） | 併進「大改動之前」 |
| 5 | 跨領域找類似方案 | 對調研有用；`omnikit-research` 已經規定要用不含 AI 字眼的一般說法查 | 併進調研 |
| 6 | 先假設方案是錯的，站在最強反對者的角度 | 官方：同一段對話自己反駁幫助有限，沒看過推理的審查者才有用 | 問法「找人挑毛病」：開獨立審查，有訂第二家就換一家審 |
| 7 | 分析 git 歷史，找出可以移除的歷史包袱 | 這是值得做的任務，不是問法 | 配方「大掃除」 |
| 8 | 評估新工程師接手的認知成本 | 同上 | 配方「大掃除」 |
| 9 | 找最慢的 PR | 同上，要有 PR 資料 | 配方，個人專案用不太到 |
| 10 | 複盤 bug 與返工，找共同根因，沉澱成規則或 skill | 官方 `/insights` 做前半；11-16 的體檢就是照這個做的 | 配方「複盤」 |

十條裡，真正的「問法」只有 3 條（2、3、6），1 條是口號，2 條是思考動作，4 條是「值得叫 agent 做的任務」。所以新手缺的不只是措辭，更多是**不知道可以叫它做這些事**，以及官方列的四種失敗原因：少給它看不到的資訊、沒給它檢查的方法、該硬性擋的只用講的、花太多。

### 5.2 外面的證據：這類東西很多，證明有效的很少

調研找到 96 個相關工具（提示詞改寫、思考框架 skill、使用習慣教練、起手包、團隊上手套件），沒有飽和。跟問法庫直接相關的發現：

- **思考框架 skill 唯一公開的實測結果是「沒過」。** tjboudreaux/cc-thinking-skills（★1,750）測了自己的 28 個思考框架 skill。README 原文：「no automatic-retain verdict」；最好的一個是「+4.0 percentage points」，低於它自己訂的 +5 門檻；「The evidence supports structured procedures, not a guaranteed accuracy gain.」（我核對過 README）
- **官方不建議在提示詞裡寫思考口號。** Anthropic 的原文我讀過（第 3.4 節）。OpenAI 與 Google 也這樣建議的說法是 Hydrogen 整理的，我沒有核對原文，待驗證。
- **新手與高手的差距，一手研究指向「有沒有參與」而不是措辭。** Anthropic 的隨機對照實驗（2026-01-29，52 位多數資淺的工程師，學一個沒用過的函式庫）：用 AI 的那組測驗「scored 17% lower」，差最多的是除錯題。低分（40% 以下）的用法是整個丟給 AI；高分（65% 以上）的用法是「used AI both for code generation and conceptual queries」。這個實驗量的是學會多少，不是產出品質，但它說明該教的是「問它為什麼、叫它解釋、自己驗證」。
- **這類工具被內建取代的例子不少。** CCPlugins（★2,774，已封存）的 README：「Several slash commands have become redundant as Claude Code CLI now handles them natively.」（我核對過）。steipete/agent-rules、wshobson/commands 也封存了（Hydrogen 用 gh api 查的，我沒有核對）。

對問法庫的含意：

1. **不要做成一大包思考框架。** 外面最接近的實測沒過門檻。只留用得到機制的幾條（訪談、獨立審查、先重現、清掉重寫）。
2. **有現成的先比現成的。** 「訪談到能寫規格」外面最多人用的是 `/grill-me`，官方文件裡也有一句話的版本。第 0 版要比三組：直接問、官方那一句、`/grill-me`，不是先自己寫一份。
3. **沒過實測就不給同事。** 我有把握的只有「該教習慣」；「包成問法庫有沒有用」沒有證據，要靠第 5.4 節的實測。

### 5.3 第 0 版：一個 skill，依情況查

一個 `SKILL.md`，每個情況 5 到 10 行，用機制（訪談、plan mode、獨立審查、開新對話）而不是口號：

1. 我還沒想清楚要什麼 → 訪談到能寫規格，寫完開新對話。
2. 修 bug → 症狀、位置、修好的定義，先重現。
3. 先確認我問對問題 → 先講你理解的目的，指出我有沒有把症狀當原因。
4. 要比較方案 → 先查業界做法，列三案與建議，寫出什麼情況會改變建議。
5. 改完找人挑毛病 → 獨立審查。
6. 大改動之前 → plan mode 加具體的影響清單。
7. 修了兩次還不對 → 清掉重寫。
8. 做到一半要換對話 → 交接。
9. 大掃除 → 歷史包袱與接手成本。
10. 複盤 → `/insights` 加共同根因，變成規則、hook 或 skill。
11. 不知道該用哪個功能 → 一張對照表：清掉、壓縮、交接、子代理、新對話、plan mode 各在什麼時候用。

skill 是 Markdown，Claude Code、Codex、Antigravity 都能用，符合「內容跨 agent」。

### 5.4 先實測再給同事

照 `omnikit-eval` 第 2 層的做法：從你過去的對話挑 6 到 10 個真實的模糊問題，同一題跑「直接問」與「照問法問」，各 3 次，不同家族的模型盲評，贏的比例要大於雜訊基準才算有用。沒過的配方刪掉。這也是實測機制留下來的理由。

## 6. OmniKit 變成什麼

| 部分 | 現況 | 動作 |
|---|---|---|
| 規則（底線、語言、個人層） | 有 | 留；分派的 YAML 搬進 skill |
| 設定引導（`omnikit-setup`） | 有，166 行 | 加訂閱、檢查指令、通知三題；指到官方的 `/init`、`/powerup`。給同事的版本借官方 `/team-onboarding` 的形式：一份貼上就能跑的 Markdown，agent 照著逐項帶，三家 agent 都能用 |
| 當下提醒（`session_nudge.py`） | 有 | 留；拿掉附帶的工具通知 |
| 交接、分派、調研 | 有 | 留；分派規則縮短 |
| 問法庫 | 沒有 | 新增，一個 skill |
| 起手清單 | 126 張卡 | 收成一頁三欄 |
| 實測（第 2 層） | 有 | 留，用來驗問法庫與清單 |
| 建議、週報、換與換回、通知、成本、回流 | 約 7,600 行 | 停用，確認沒人用再刪 |
| 自製安裝與移除 | 約 3,000 行 | 先做原生 plugin 的原型；只用 Codex 的同事要另外確認 Codex 的 plugin 能不能裝同一包 |

## 7. 順序

1. 問法庫第 0 版加實測（先給你自己用）。
2. `omnikit-setup` 加訂閱題，產生個人分派檔；分派規則縮短。
3. 起手清單一頁。
4. 停用建議與週報的觸發詞（腳本先留著）。
5. 原生 plugin 原型：這台裝一次、移除一次。

## 8. 限制與還沒驗證的

- 委派紀錄只有 17 筆，第 2.2 節不能當成模型優劣的結論。
- 「要量的交給官方，要寫的自己留」是我的判斷原則，沒有實測。
- 問法庫有沒有用還沒測；第 5.4 節的實測沒過，這個方向就要重想。
- claude-mem 與 caveman 有沒有幫助沒有實測。

## 9. 調研紀錄

- 派 Hydrogen high（agy_cli）做飽和式調研，22 分鐘，約 53 萬 tokens。帳本 143 個名字，報告收 96 個相關工具。
- **沒有飽和**：跑滿我設的 15 組上限，最後一組仍有 3 個新名字。驗收記為部分通過。
- 每組查的管道：GitHub topic、GitHub 關鍵字、awesome 清單、skills.sh、npm、MCP Registry、Hacker News、Exa、網頁搜尋（13 組英文、2 組中文）；Product Hunt 1 次；related 1 次。
- 15 組關鍵字：claude code prompt improver hook、clarifying questions skill、thinking frameworks prompts、claude code workflow coach、claude code starter kit、developer onboarding playbook、gemini cli codex skills starter、session handoff context management skill、first principles checklist、Claude Code 提示词 框架 思维、claude code daily tips statusline、claude code interactive tutorial quiz、prompt enhancer skill coding、adversarial review red team skill、coding agent prompt library。
- 我抽查了 5 個引用。4 個對得上：cc-thinking-skills 的 README、CCPlugins 的 README 與封存狀態、Anthropic 的實驗、mattpocock/skills 裡有 grill-me。**1 個對不上**：Hydrogen 寫「skill 自動觸發率約 37% 到 55%」，原文的數字是 20%（只加提示）、84%（強制評估）、80%（LLM 評估）；本文用原文的數字。其餘引用沒有逐一核對。
- 官方 `/team-onboarding` 跑了三次才有結果：第一次 Git Bash 把指令當成路徑；第二次在空資料夾跑，只掃到 1 段對話；第三次在 OmniKit 專案裡跑，產出的檔案已移出 repo。

## 來源

- https://www.anthropic.com/research/AI-assistance-coding-skills （隨機對照實驗，2026-01-29）
- https://github.com/tjboudreaux/cc-thinking-skills （思考框架 skill 的實測，README）
- https://github.com/brennercruvinel/CCPlugins （因內建而封存，README）
- https://github.com/mattpocock/skills （`/grill-me`）
- https://scottspence.com/posts/how-to-make-claude-code-skills-activate-reliably （skill 觸發率，2025-11，合成測試）
- https://code.claude.com/docs/en/best-practices.md （開頭的界線、Write a specific prompt、Brainstorm with Claude first、Know what subagents cost、Keep cost and context down、Steer the session、What you can stop doing）
- https://code.claude.com/docs/en/commands.md （`/powerup`、`/init`、`/team-onboarding`、`/insights`）
- https://code.claude.com/docs/en/costs.md （`/insights`、清 context、型別語言的 code intelligence plugin、優先用 CLI）
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices.md （Be clear and direct、Add context、Subagent orchestration）
- 本機：`dispatch.py stats` 與委派紀錄（2026-11-17）、`data/evals/` 的實測紀錄、2026-11-16 的 `/skill-doctor` 與 `/doctor` 輸出
