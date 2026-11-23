# 業界頂尖多模型分工工作流調研（2026 年現況）

- 調研日期：2026-11-23（唯讀；未安裝、未登入、未改 repo 其他檔案）
- 帳本：`C:\Users\user\AppData\Local\Temp\omnikit-research\multimodel-workflow-ledger.json`
- 前置報告：`2026-11-19-model-roles-research.md`、`2026-11-22-multi-user-model-roles-research.md`、`2026-11-22-gemini-pro-pool.md`

## 跟舊報告比新增了什麼

舊報告談的是「模型目錄、閘道、角色別名、ToS 資料化、降級矩陣」（結構面）。這份補的是舊報告沒有的「效果面證據」：

1. **跨家審查有實驗數字**：兩篇 2026 年 arXiv 預印本，結論不是「跨家一定更好」，而是「看審查者能力與方向」。舊報告只有 `reviewer_cross` 的設計建議，沒有證據。
2. **思考程度有實測資料**：官方文件逐級建議，加上第三方實測（Forcebench 等），含 Gemini 4 Argon 與 Claude 5.5 的 token 倍數。舊報告只引用了定價。
3. **新模型上線評估的做法**：golden set 回歸、shadow、canary、小題組 onboarding（ICL-Router、ZeroRouter），以及可用的開源評測工具（promptfoo、Inspect、PinchBench）。舊報告只有「試用期狀態機」概念。
4. **council、best-of-N**：查了，結論是沒有程式碼品質的對照證據，只有可驗證輸出時 best-of-N 才有數據。
5. **Anthropic 自己的 orchestrator 與 subagent 說法**：含官方明講「多數寫碼任務不適合拆」。
6. 新工具名單（舊兩份都沒有）：claudex-loop、cross-review、fabro、PinchBench、oh-my-codex、UncommonRoute、NadirClaw、claude-model-router-hook、opencode-model-router 等（見最後的帳本摘要）。

## 摘要（10 行內）

1. 跨家審查的價值取決於「審查者不比作者弱」。弱模型（Flash 級）跨家審查不比同模型新 session 好；Codex 審 Claude 的草稿在一項實驗裡反而降低通過率（91.4% 到 82.8%）。
2. 最穩的組合是「同模型新 context 審一次 + 強的跨家審一次」：覆蓋的預埋錯誤 56.7%，兩次同模型審是 42.7%。
3. 強作者自審在一項實驗裡完全沒增益，卻多 72% 成本與 58% 延遲。審查要有目的，不是預設動作。
4. Anthropic 官方：orchestrator 加 subagents 在研究類任務贏單 agent 90.2%，但用 15 倍 token，而且「多數寫碼任務可平行的部分比研究少」。
5. council（Karpathy llm-council 類）與 best-of-N：沒有找到程式碼品質的對照實驗；best-of-N 的瓶頸是挑選者（verifier），要有測試或強 verifier 才划算。
6. 思考程度：官方建議起手 high（Opus 5.5 預設 medium），xhigh、max 只在「你量到增益」時開；max 在 Forcebench 的 32k 輸出上限下反而掉 13 到 35 個百分點（大量答案沒寫完）。
7. 新模型或新帳號：業界做法是小題組加確定性驗證器的煙霧測試，過關再 shadow，再 canary；LLM 評審不能當唯一閘門。
8. 動態路由的實用形式是「角色對模型的資料表加回退鏈」（oh-my-openagent、Kilo、OpenRouter auto），不是訓練式 router；訓練式的新模型 onboarding 成本高。
9. 開源多使用者：角色以「主控是誰」相對定義（claudex-loop 的 host 互換）、每格附原因（oh-my-openagent 的 doctor 輸出）。
10. 本報告停在第 12 組，**未達停止條件**（見飽和紀錄），請決定要不要拆題再查。

## 一、頂尖團隊怎麼分工（面向 1）

### 1.1 跨模型家族審查：實驗證據

| 研究 | 設定 | 結果（逐字數字） | 限制 |
|---|---|---|---|
| arXiv 2610.01471（Tae-Eun Song，單一作者預印本，2026-10-01，v2 10-06）[abs](https://arxiv.org/abs/2610.01471) | 30 份文件（10 程式模組）、150 個預埋錯誤、900 個 session；作者 Claude Opus 4.6，審查者 GPT-5.4、Gemini 2.5 Pro、Gemini 2.5 Flash | F1：GPT-5.4 跨家 32.3，Opus 新 session 同模型 28.6（不顯著）；Gemini 2.5 Pro 26.8，Flash 24.0；同 session 自審 27.1；一次同模型加一次跨家覆蓋 56.7%，兩次同模型 42.7%（Holm 調整 p=.006）；找到的錯誤重疊 Jaccard 41.2% | 作者自承：單一作者、預埋錯誤未獨立標註、文件為韓文、審查者能力與廠牌混在一起無法分離、未同儕審查 |
| arXiv 2607.21656（UC Davis 等，Agentic SE @ KDD'26 workshop，2026-07-22）[abs](https://arxiv.org/abs/2607.21656) | 116 題 LiveCodeBench（2025 年後的中難題）；claude-opus-4-7（Claude Code）與 gpt-5.5（Codex CLI），皆 high；審查者只能靜態讀、不能跑程式 | Codex 草稿 71.6%：Claude 審 89.7%、Codex 自審 84.5%；Claude 草稿 91.4%：Claude 自審 91.4%、Codex 審 82.8%（p_BH=.046）；Claude 單跑在成本與準確率的 Pareto 前緣；自審 AA 比單跑多 72% 成本與 58% 延遲 | 只測一組模型；兩種跨家方向的直接對比不顯著（p_BH=.1444），論文自己說不能宣稱方向可分；單檔 Python，不是 repo 規模 |

怎麼讀（我的解讀，非論文原文）：兩篇都沒有證明「跨家本身有魔力」。共同點是審查者的能力不能低於作者，而且審查要能補上作者看不到的東西。弱的跨家審查者沒用，強作者自審沒增益。對 OmniKit 現行「重要結果換一家唯讀審查」的規則：有支持（互補性、覆蓋變多），但要加「審查者等級下限」，Flash 這種不要拿來審 Opus 寫的程式。

實務面的一致做法（第三方，**待驗證**，只當線索）：iThome 鐵人賽文章主張分工依據是「誰能驗證自己的產出」而不是模型強弱；開源 ecc-universal `multi-workflow` 指令讓 Codex、Gemini 平行審查再由 Claude 綜合；synapse 反過來讓 Claude、Gemini 起草、Codex 審查。各方案角色配置不一致，沒有業界標準。

### 1.2 orchestrator 加 subagents

- Anthropic 工程部落格（2025-06-13）：lead 為 Opus 4、subagents 為 Sonnet 4 的多代理在內部研究評測贏單 agent Opus 4 達 90.2%；多代理約用聊天 15 倍 token；「需要所有 agent 共用同一份 context、或 agent 之間依賴很多的領域不適合」；「多數寫碼任務真正可平行的部分比研究少」。評測方法：約 20 個查詢起手、單次 LLM 評審輸出 0.0 到 1.0 分、人工測試補位。[來源](https://www.anthropic.com/engineering/multi-agent-research-system)（2026-11-23 讀）
- Claude Code 官方文件：subagent 預設與主對話同模型；可用 frontmatter 的 `model` 與 `effort` 覆寫；優先序為單次呼叫參數、定義檔、`CLAUDE_CODE_SUBAGENT_MODEL`、主對話；文件原話建議「Control costs by routing tasks to faster, lower-cost models like Haiku」；`opusplan` 在 plan 模式用 opus、執行切 sonnet。[sub-agents](https://code.claude.com/docs/en/sub-agents)、[model-config](https://code.claude.com/docs/en/model-config)（2026-11-23；model-config 的 opusplan 細節為摘要，標待驗證）
- 開源實作：claudex-loop（★3,553）是 Claude Code skill，host 與 reviewer 互換：host 是 Claude 時 Codex 審計畫、Claude 實作、新 Codex session 驗收；host 是 Codex 則角色對調；審查結論 `APPROVED`／`REVISE`／`BLOCKED`，回合數上限預設 5 並明確不把失敗轉成通過。[README](https://github.com/chaseai-yt/claudex-loop)（2026-11-23 讀）

### 1.3 council 與 best-of-N

- **council**：Karpathy 的 llm-council（★26,877，最後 push 2025-11-22）流程是多模型回答、匿名互評、主席模型彙整；搜尋摘要稱作者自稱是 vibe code 專案、不維護、沒有發佈基準（**待驗證**，二手摘要，未讀 README 原文）。未找到程式碼品質的對照實驗；某部落格的「標準差降 50%、人工偏好 70%」查無一手來源，不採用。
- **best-of-N**：近期論文的共同結論是瓶頸在挑選者。arXiv 2607.05391 稱異質三候選加 verifier 在 SWE-bench Verified 達 78.2%，高於最強單一成員 Claude Opus 4.5 的 76.8%；arXiv 2601.04171 用 rubric 型 verifier（皆為搜尋摘要，**待驗證**，未讀全文）。結論：有測試或強 verifier 的可驗證輸出才值得做 best-of-N。
- Zenflow（商業，Product Hunt 發佈文自稱可同時跑最多四個模型並排比較與跨模型驗證；官方文件頁抓取 403，**待驗證**）、fabro（★1,882）屬於把這些模式產品化的工作流工具。

## 二、新模型或新帳號上線的自動評估（面向 2）

業界模式（多為廠商或個人部落格，數字是示意預設，不是標準）：
- **golden set 回歸 → shadow → canary → 全量**：candidate 在真實流量並行跑但使用者只看舊模型的輸出（成本約加倍），再用 1% 到 5% 到 20% 逐步放量，觀察 24 到 72 小時；要自動回滾；警告不要只用 LLM 評審當閘門（拿評審測評審）；低流量系統做不了有意義的 canary。來源：[tianpan.co](https://tianpan.co/blog/2026-04-20-canary-deploys-llm-model-upgrades)、[Arize 詞彙表](https://arize.com/glossary/canary-evaluation-ai-systems/)、[Langfuse golden dataset](https://langfuse.com/resources/engineering/golden-dataset-evaluation)（皆**待驗證**，二手）。
- **新模型小題組 onboarding**：ICL-Router（arXiv 2510.09719，程式碼 lalalamdbf/ICL-Router ★10）與 ZeroRouter（arXiv 2601.06220）都主張新模型只需在一小批 anchor 題上跑分就能估出能力、不必重訓 router（搜尋摘要，**待驗證**）。
- **隨選基準驗證**：舊報告已記 Kilo Code 對自訂模型池新增 `(model, variant)` 時觸發隨選基準，狀態 `Benchmarking`／`Ready`／`Failed`（舊報告來源，本次未重查）。
- **依回饋排序**：Factory Agent Arena 用人類投票的成對比較算 Bradley-Terry Elo（Droid 1330、Codex 1301、Devin 1263、Claude Code 1242，文件標更新於 2025-12）[docs](https://docs.factory.ai/benchmarks/agent-arena)；搜尋摘要提到 2026-02 論文稱 Elo 對評測設定很敏感（**待驗證**）。Elo 要大量成對比較，單一使用者的樣本數不夠，通過率加樣本數門檻較實際。
- 外部排行榜（Arena 的 coding agent、Tokscale 等）當篩選線索可以，不當派工依據（第三方，**待驗證**）。

可拿來做這件事的開源工具（`verify` 2026-11-23）：

| 工具 | 星數與授權 | 適合做什麼（官方頁原文為準） |
|---|---|---|
| promptfoo | ★27,553 MIT | 本機 CLI，對多個 provider 跑同一批測試、矩陣檢視；GitHub Action 在 PR 比較前後（是否能擋 merge 頁面未寫）[docs](https://www.promptfoo.dev/docs/intro/) |
| Inspect（UKGovernmentBEIS/inspect_ai） | ★3,310 MIT | Task = dataset + solver + scorer；有 `model_graded_qa()`、docker sandbox、`react()` agent；一次 `inspect eval` 指一個 `--model`（頁面沒寫一個指令跑多模型）[docs](https://inspect.aisi.org.uk/) |
| PinchBench（pinchbench/skill） | ★1,384 MIT | 53 個真實任務，自動或 LLM 評審；`--model` 要 provider 前綴，預設走 OpenRouter；輸出 results JSON 與逐任務 transcripts，預設會上傳 pinchbench.com（要 `--no-upload`）[README](https://github.com/pinchbench/skill) |
| langfuse | ★37,734（授權 NOASSERTION） | 觀測與 golden dataset 管理（待驗證，未讀官方文件） |
| EleutherAI lm-evaluation-harness | ★14,522 MIT | 學術基準；一般說法「model evaluation harness」撈到的主力，對派工選型太重，不建議 |

## 三、思考程度政策（面向 3）

**一手（官方文件，2026-11-23 讀）**：[effort 文件](https://platform.claude.com/docs/en/build-with-claude/effort)
- low：「Simpler tasks … such as subagents」；medium：Opus 5.5 與 Haiku 5.5 的預設；high：其他模型預設，「Complex reasoning, difficult coding problems」；xhigh：「Long-running agentic and coding tasks (over 30 minutes) with token budgets in the millions」；max：「no constraints on token spending」。
- 逐模型：Fable 5.2 先 `high`，xhigh 用於「where you've measured a gain」，max 只拿來量天花板，「runs slower and costs more than at xhigh, often for only a small gain」；Sonnet 5.5 寫碼先 medium、難的 high，xhigh 或 max「only where your evals show a quality gain」；Haiku 5.5 的 low 在長 agent prompt 會「skip a search, stop early, or skip a check」。
- 文件**沒有**任何實測數字；effort 是行為訊號不是 token 預算；high 以上要設大 `max_tokens`。
- subagent 的 `effort` 可寫在 frontmatter，優先序見 sub-agents 文件。

**第三方實測（標示來源與偏誤）**：
- Forcebench（Azul Labs，賣私有評測，非模型廠；Salesforce 任務 272 題，輸出上限 32,768 含思考，超過算失敗；結果日 2026-10-25）[effort](https://forcebench.ai/studies/effort/)、[max](https://forcebench.ai/studies/max-effort/)：Opus 5.5 low 到 high 89% 到 90%（無明確差），token 約 2 倍；Sonnet 5.5 77% 到 82%；**Gemini 4 Argon 89% 到 89%，token 598 到 5.3k（約 9 倍）、延遲 10 秒到 37 秒**；Sonnet 5.5 與 Haiku 5.5 的 high 到 max 分別掉 35 與 22 個百分點，約一半答案在上限前沒寫完。頁面自己說這是「Forcebench 預算下的 max」，不是廠商建議的 max；任務不是一般寫碼。
- Crewshal（商業產品廠，8 題、176 次呼叫、天花板效應）[文章](https://crewshal.com/blog/does-reasoning-effort-buy-quality-claude-codex)：各檔皆 16/16 通過，token 約 1.5 到 1.8 倍；作者自己說「無法證明 effort 在更難的題目上沒用」。偏誤：廠商自家研究。
- arXiv 2608.03169（Georgia Tech、CU Boulder，v2 2026-09-29）：GPT-5.6 兩檔跑 14 個例行辦公任務、840 次，low 與 max 都沒有違規，low 少用約 44% token、少 20% 時間 [abs](https://arxiv.org/abs/2608.03169)。一個模型家族、任務簡單。
- arXiv 2611.11910（CMU 等，2026-11-09）：有截止時間時，思考模式的答案常超時；單 GPU 同時請求從 8 增到 56，45 秒內完成的思考答案比例從 79.2% 掉到 1.4%（摘要為逐字，內文為摘要版）[abs](https://arxiv.org/abs/2611.11910)。對「長時間無輸出就逾時」的環境有直接參考性。

**對 OmniKit 的讀法**：沒有任何一手資料支持「全部開最高」。高檔位的代價（token 倍數、延遲、逾時風險）有實測，增益在多數任務上不明顯，且只有在「你自己的任務量到增益」時才值得。T3 對 Antigravity 寫死 15 分鐘無輸出逾時（舊報告與 profile 記載），xhigh 長思考與這個限制相衝，這是 OmniKit 自己的環境事實，不是業界數據。

## 四、分工由資料推出來（面向 4）

做法光譜（舊報告已詳列閘道類，這裡只補新增或重要者）：
- **角色加類別加有序回退鏈**：oh-my-openagent（★71,065，授權 NOASSERTION，最後 push 2026-11-23）的 Agent 角色與 Task Category，各配 `fallbackChain`，執行期用連線供應商的模型清單解析（舊報告已讀過原始碼層級資料）。其 related 的 fork 與連結：opensoft/oh-my-opencode（★1,369）、yeachan-heo/oh-my-codex（★33,836）、badlogic/pi-mono。
- **虛擬模型加難度或成本偏好**：OpenRouter auto 與 auto-code、Kilo `kilo-auto/frontier` 與 `efficient`、Cursor 與 Copilot 的 Auto（舊報告）。
- **規則式小 router**（本次新發現，星數小，**待驗證**）：UncommonRoute（★703 MIT）、NadirClaw（★666）、claude-model-router-hook（★114）、opencode-model-router（npm）。大多是依 prompt 難度分到便宜或強模型。
- **訓練式 router 的新模型問題**：RouteLLM（★5,726，最後 push 2024-08-10）固定 strong、weak 兩端點，新模型要重訓；近兩年論文（ICL-Router、ZeroRouter、InferenceDynamics、COMPASS、HyDRA）都在解決「新模型不必重訓」，但屬研究，OmniKit 的任務級別分類比 prompt 語意分類更可稽核（舊報告同結論）。
- **自適應思考預算**：DART、AdaCtrl、ODAR 等論文是訓練時方法，非現成工具；Claude 官方做法是 effort 檔位加使用者量測。

資料推導的最小配方（建議用，見下）：模型目錄（T3 即時清單加 models.dev 規格）× 本機煙霧測試分數 × 額度與成本 × 使用者偏好與規約旗標 → 每個角色的有序候選，附原因。

## 五、開源給多使用者時的自動適配（面向 5）

舊報告（11-22）已覆蓋偵測、降級矩陣、ToS 資料化。本次新增兩點：
- **角色相對於主控定義**：claudex-loop 的 host 互換做法，等於「審查者永遠是另一家」，用一個規則涵蓋 Claude 主控與 Codex 主控兩種使用者。
- **每格附原因與狀態徽章**：oh-my-openagent 的診斷指令（舊報告：`omo doctor --models`）、Kilo 的 `Ready`／`Failed` 徽章（舊報告）。新模型尚未通過煙霧測試的格子標 `trialing`。
- Product Hunt 上的 router 類產品（RouKey 以角色分派模型、FastRouter 依任務叢集選模型、ClawPane、Adaptive、ModelPilot）都是廠商自述，**待驗證**，只當功能清單參考。

## 六、對 OmniKit 的建議

### 必做

1. **`reviewer_cross` 加「能力下限」規則**：審查者的級別不得低於作者；Flash 級、Haiku 級不審 Opus 或 Neon 級寫的程式。依據：2610.01471 輕量跨家審查不優於同模型新 session；2607.21656 弱方審強方降低通過率（91.4% 到 82.8%）。
2. **審查有目的才開，且用「同模型新 context 加強跨家」的組合**：一般任務同模型新 session 審一次；高風險（帳務、風控、下單，與現有紅線一致）再加一個等級夠的跨家審查。依據：2610.01471 兩者合併覆蓋 56.7% 對 42.7%；2607.21656 強作者自審 +0.0 個百分點卻 +72% 成本。這跟 profile 現行「寫的與審的不同家」不衝突，只是補上何時開與何者可擔任。
3. **新模型或新帳號必過煙霧測試才能從 `trialing` 到 `ready`**：固定 5 到 10 題、確定性驗證器（跑測試或比對輸出，不靠 LLM 評審），對每個「實例 × 模型 × 思考程度」跑一次，記通過、耗時、token 到現有 `log.jsonl`；再沿用現有 `trials` 門檻（n >= 20）累積真實使用回饋。依據：golden set／canary 做法（二手，待驗證）、Kilo 隨選基準與 ICL-Router 的小題組概念。第一版自己寫腳本即可，不必先引入 promptfoo 或 Inspect。
4. **思考程度預設表照官方起手，高檔位要有本機量測才開**：subagent 預設 low 或 medium，主線與難題 high，xhigh 限「長任務且量到增益」，max 不預設。要點：同一任務在檔位間比通過率、耗時、token，結果寫進 `data/evals`。依據：官方 effort 文件（無數字）、Forcebench（Argon 9 倍 token 無增益、max 掉分）。**已定案的 Gemini 一律 high 以上不重審**；這裡只建議把 Gemini 各檔位也納入第 3 點的煙霧測試，累積自己的數據，需要時由 Ryan 決定。
5. **每格附原因**：`run.py show` 對每個角色指派印一行「命中原因／跳過原因／降級提示」，並標出該格是否通過煙霧測試。依據：oh-my-openagent doctor 與 OpenRouter metadata 的透明度；Cursor Auto 不透明被批評（舊報告）。
6. **角色相對於主控定義**（reviewer 永遠是「另一家且不弱於作者」，而非寫死 Gemini）。依據：claudex-loop 的 host 互換；多使用者適配（舊報告 11-22）。

### 選配

7. **影子審查（shadow）**：新模型上線時，讓它對同一份 diff 與正式審查者並行唯讀審查，不影響結果，只記「找到的問題與正式審查者的重疊（Jaccard）與獨有發現」。依據：2610.01471 的 Jaccard 41.2% 指出跨家主要價值是互補，shadow 剛好量這個；成本是多跑一次審查，所以只對新模型做、有上限。
8. **orchestrator 加 subagents 只用在可平行的研究或審查工作包**，寫碼不拆。依據：Anthropic 官方說多數寫碼任務可平行部分少、15 倍 token。
9. **best-of-N 只對有測試的任務**（跑 N 個候選，用測試挑）；council 不做預設。依據：best-of-N 瓶頸在挑選者（論文，待驗證）；council 無對照證據。
10. **不做**：訓練式 router、Elo 排行（樣本數不夠）、直接用外部排行榜決定派工、把 lm-evaluation-harness 這類學術基準接進來。依據：舊報告對 RouteLLM 的判斷、Factory Elo 靠人類投票、第三方榜單待驗證。
11. **工具選配**：若第 3 點要做成可重跑的流程，promptfoo（MIT、★27,553）或 Inspect（MIT、★3,310）可評估；兩者的「一次跑多模型」能力官方頁沒寫清楚，真要採用先實測（走 `omnikit-eval`）。

## 七、飽和調研紀錄

### 1. 判斷標準
納入：有「多模型分工、跨家審查、council／best-of-N、新模型評估或煙霧測試、思考程度實測、動態路由」任一實質機制或數據的工具、論文或官方文件。排除：純學術 ML 基準（只在第 3 組當線索）、與 LLM 無關的同名套件（npm、MCP registry 雜訊大，已人工過濾）、第 10 組幾乎全是雜訊。

### 2. 管道與關鍵字組（共 12 組；`status` 輸出）

起手三組：「multi-model coding workflow」「cross-model code review」「model evaluation harness」（第三組是不含 agent、AI 字眼的一般說法）。擴展詞來源：第 2 組結果的 arXiv 標題與 `council`、`best-of-N`（第 4、5 組）；第 3 組結果的 `regression`、`golden set`（第 7 組）；結果中的 `reasoning effort`（第 6 組）、`routing`、`capability`（第 8 組）、`elo`、`leaderboard`（第 9 組）；`roles`、`plan implement review`（第 11 組）；`adaptive thinking budget`（第 12 組）。

```text
總共 148 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 2 組沒有新的（要 3 組）：還不能停
已經 12 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續
```

各組新增（總名字數；★1000 以上新名字）：1) 37（pinchbench/skill、vercel/ai、fabro-sh/fabro、opensoft/oh-my-opencode、badlogic/pi-mono、yeachan-heo/oh-my-codex）；2) 20（pr-agent、open-code-review、auto-claude-code-research-in-sleep、claudex-loop）；3) 11（lm-evaluation-harness、bigcode-evaluation-harness、autoevals）；4) 11（pro-workflow、karpathy/llm-council）；5) 8（0）；6) 10（0）；7) 7（0）；8) 19（quantumnous/new-api）；9) 9（kilo-org/kilocode）；10) 1（0）；11) 9（0）；12) 8（0）。

### 3. 停法
**未達任何停止條件，第 12 組上限停下回報。** 全體候選每組都有新名字（連續 0 組無新）；★1,000 以上的新名字連續 2 組沒有新的（第 11、12 組；第 10 組的 web 管道沒查完，所以不算完成組），差 1 組。★1,000 以下與沒有星數的產品不保證找齊。題目五個面向混在一起（審查、評測、effort、路由、多使用者），依 skill 建議其實該拆成子題各自一本帳本。

### 4. 查不到的管道與原因
- GitHub 搜尋 API 限速：第 3 組第一次被 403，等 60 秒後重跑成功。
- Exa 匿名限速：第 10 組 Exa 查不到（已記）。
- awesome：第 7 組限速查不到；其餘組多只撈到無關通用清單。
- skills.sh、npm、MCP registry：子字串比對，雜訊大（npm 的 deepseek-harness 灌水，MCP registry 大量無關名稱），已人工過濾。
- Product Hunt：只有網頁搜尋，找到的多是廠商自述，沒有獨立評論。
- Zencoder 官方文件頁：抓取 403，內容未驗證。
- 沒有第二位獨立研究者交叉（skill 的 ★ 停法會漏，這次單人跑）。

### 5. `verify` 實測（2026-11-23，gh api）
| Repo | 星數 | 授權 | 封存 | 最後 push |
|---|---|---|---|---|
| earendil-works/pi | 123,382 | MIT | 否 | 2026-11-23 |
| cheaper-inference/OmniRoute | 89,647 | MIT | 否 | 2026-11-23 |
| code-yeongyu/oh-my-openagent | 71,065 | NOASSERTION | 否 | 2026-11-23 |
| alibaba/open-code-review | 55,447 | Apache-2.0 | 否 | 2026-11-22 |
| langfuse/langfuse | 37,734 | NOASSERTION | 否 | 2026-11-22 |
| Yeachan-Heo/oh-my-codex | 33,836 | MIT | 否 | 2026-11-22 |
| promptfoo/promptfoo | 27,553 | MIT | 否 | 2026-11-23 |
| karpathy/llm-council | 26,877 | 無 | 否 | 2025-11-22 |
| wanshuiyin/Auto-claude-code-research-in-sleep | 19,609 | MIT | 否 | 2026-11-19 |
| The-PR-Agent/pr-agent | 16,573 | MIT | 否 | 2026-11-22 |
| EleutherAI/lm-evaluation-harness | 14,522 | MIT | 否 | 2026-11-04 |
| anomalyco/models.dev | 7,727 | MIT | 否 | 2026-11-23 |
| lm-sys/RouteLLM | 5,726 | Apache-2.0 | 否 | 2024-08-10 |
| chaseai-yt/claudex-loop | 3,553 | NOASSERTION | 否 | 2026-10-14 |
| UKGovernmentBEIS/inspect_ai | 3,310 | MIT | 否 | 2026-11-22 |
| fabro-sh/fabro | 1,882 | MIT | 否 | 2026-11-21 |
| pinchbench/skill | 1,384 | MIT | 否 | 2026-07-02 |
| braintrustdata/autoevals | 1,087 | MIT | 否 | 2026-11-19 |
| gmickel/flow-next | 731 | MIT | 否 | 2026-11-22 |
| CommonstackAI/UncommonRoute | 703 | MIT | 否 | 2026-06-26 |
| NadirRouter/NadirClaw | 666 | NOASSERTION | 否 | 2026-11-20 |
| lploc94/cross-review | 168 | MIT | 否 | 2026-11-11 |
| lalalamdbf/ICL-Router | 10 | 無 | 否 | 2025-10-14 |

### 6. 待驗證清單（沒有一手證據）
- 所有 `Zenflow`、Product Hunt 產品的功能與效能說法（廠商自述；Zenflow 官方頁 403）。
- council 的效果數字（無一手來源）；Karpathy repo 的維護狀態說法（二手摘要，未讀 README）。
- best-of-N 的 78.2% 等數字（搜尋摘要，未讀論文全文）。
- ICL-Router、ZeroRouter、Elo 敏感度論文的細節（搜尋摘要）。
- shadow、canary 的門檻數字（部落格的示意預設）。
- model-config 頁 `opusplan` 與 `effortLevel` 細節（摘要版）。
- Forcebench 與 Crewshal 的數字是第三方；Crewshal 是廠商自家研究。兩篇 arXiv 為預印本（2607.21656 為 workshop 接受，未見正式同儕審查結論）。
- Gemini 在 Antigravity 訂閱池上各檔位的額度消耗倍率：本次仍無官方數字（延續舊報告）。
