# 問法庫：新題目與高品質來源的調研（Gemini 原文）

2026-11-17 由 Gemini 4 Hydrogen（High）經 `agy -p` 做的飽和式調研，原文照存。**只抽查了第 1 節的前 5 個來源**（都存在、數字對得上，見 [Gemini 評測紀錄](2026-11-17-ask-eval-gemini.md)），其餘網址、星數、數字都視為待驗證。

---

針對 [SKILL.md](../../engine/skills/omnikit-ask/SKILL.md) 與 [2026-11-17-ask-eval.md](../../docs/reviews/2026-11-17-ask-eval.md) 的飽和式調研結果。

---

## 1. 一段結論：最值得用的前 5 個來源與原因

現有 [SOURCES.md](../../engine/skills/omnikit-ask/SOURCES.md) 偏重官方文件與人類領域方法，缺少「真實開發者卡住紀錄」與「評測偏差校正」的一手依據。這次調研最值得優先採用的前 5 個來源如下：

1. **`How Coding Agents Fail Their Users`（arXiv:2605.29442）**：直接分析 20,574 筆真實開發者與 coding agent 對話工作階段，將「Developer-Agent Misalignment」量化分類（例如違反負面約束佔 38% 以上、虛假回報完成、擅自越權修改、診斷錯專案脈絡），是擴充「跟 agent 協作」題庫最直接的實證依據。
2. **`SALT-NLP/SWE-chat`（Hugging Face / arXiv:2604.20779）**：少數來自真實開源開發者「野放環境」的多輪 coding agent 完整軌跡資料集，含提示詞、工具呼叫、使用者推翻／糾正與 git 變更歸因，可拿來抽樣真實卡住對話改寫為評測題。
3. **`ClarifyCodeBench`（arXiv:2607.00711）與 `Ask or Assume?`（arXiv:2603.26233）**：專門測量 coding agent 在需求缺漏時會不會先反問澄清，並證實「會寫程式不等於會提問（Capability Decoupling）」，正好對應 `omnikit-ask` 最核心的價值（現有 11 題中拉開最大差距的項目），且提供了 Turn-discounted Key Question Rate 等可借鏡的多輪指標。
4. **`NVIDIA/SkillEvaluator`（arXiv:2608.20614）與 Anthropic `skill-creator`（`anthropics/skills`）**：業界少數專門針對 `SKILL.md` 的評測框架，提供 `should_trigger: true/false`、語意近失負向對照（near-misses）、語意重疊衝突檢查與三層（靜態／去重／沙盒）評測管線，直接解決目前 11 題缺少負向對照的問題。
5. **`Self-Preference Bias in Rubric-Based Evaluation`（arXiv:2604.06996）與 `Bias in the Loop`（arXiv:2604.16790）**：直接點出現有 `ask-eval` 的盲點——即使使用客觀檢核清單（rubric），同家族 LLM 評分者對自家模型失敗項仍高出 50% 以上的寬鬆誤判率，必須改採跨家族評審團（`RoPoLL`）與交換順序／去長度提示來校正。

---

## 2. 來源表

> 註：僅列出搜尋結果中實際出現的網址或識別碼；未於結果中直接確認的星數、授權或完整網址標示為「待驗證」。

### A. 真實對話、工作階段軌跡與 PR 紀錄資料集

| 名稱 | 網址 | 類型 | 能提供什麼 | 品質判斷 | 授權或取得方式 | 能轉成幾題評測 |
|---|---|---|---|---|---|---|
| `SALT-NLP/SWE-chat` | `https://huggingface.co/datasets/SALT-NLP/SWE-chat` / `https://github.com/SALT-NLP/SWE-chat` / `https://arxiv.org/abs/2604.20779` | Hugging Face 資料集 + 論文 | 真實開源開發者與 coding agent 多輪對話、工具呼叫、使用者糾正與提交紀錄 | 極高：非合成資料，有完整對話與 git 變更對照，涵蓋真實翻車點 | `odc-by`，HF `datasets` 直接下載 | 15–25 題（從使用者打斷／糾正回合抽樣） |
| `Suzhen/CodeChat` & `CodeChat-V2.0` | `https://huggingface.co/datasets/Suzhen/CodeChat` / `https://huggingface.co/datasets/Suzhen/CodeChat-V2.0` / `https://arxiv.org/abs/2509.10402` | Hugging Face 資料集 + 論文 | 從 WildChat 過濾出 82.8k（v1）至 587k+（v2）真實開發者多輪寫程式對話與修錯回合 | 高：涵蓋 20+ 語言與真實新手／老手模糊提問；缺點是偏一般聊天介面而非 CLI agent | 授權待驗證（源頭 WildChat 為 `ODC-By`），HF 直接載入 | 10–15 題（多輪 debug 與模糊需求） |
| `NAIST-SE/DevGPT` | `https://github.com/NAIST-SE/DevGPT` | GitHub / Zenodo 資料集（~56 stars、~17 forks） | 開發者在 GitHub PR/Issue/HN 分享的真實 ChatGPT 對話連結與對應程式碼變更 | 高：學界經典資料集（NAIST），對話與真實開發產物綁定；限制為早期對話為主，非 agent 工具鏈 | Zenodo 釋出為 `CC BY 4.0` | 5–10 題（補充設計討論與依賴選型） |
| `nuprl/AgentPack` | `https://huggingface.co/datasets/nuprl/AgentPack` | Hugging Face 資料集（arXiv:2509.21891） | 1.3M–1.8M 筆由人類與 Claude Code、Codex、Cursor 共同產出的 GitHub commit 與修改意圖 | 中高：規模極大且為真實產出；但只保留成功合入的 commit，較缺失敗過程 | 授權待驗證，HF 直接載入 | 3–5 題（對照成功規範寫法） |
| `all-hands/openhands-feedback` | `https://huggingface.co/datasets/all-hands/openhands-feedback` | Hugging Face 資料集（275 rows） | OpenHands 真實使用者的 thumbs-up/down 回饋與互動軌跡 | 中高：有明確好壞標記；但樣本數僅 275 筆 | `MIT`，HF 直接載入 | 3–5 題（使用者不滿意實例） |
| `nebius/SWE-agent-trajectories` & `thoughtworks/agentic-coding-trajectories` | Hugging Face `nebius/SWE-agent-trajectories`（80,036 rows）、`thoughtworks/agentic-coding-trajectories`（15,000 sessions） | Hugging Face 執行軌跡資料集 | Agent 解決 GitHub issue 的完整思考、讀檔、執行與重試迴圈紀錄 | 中：適合研究 agent 鬼打牆與 token 膨脹，但無人機對話提問階段 | `CC-BY-4.0`（nebius）／`derivative-multi-source`（thoughtworks） | 3–5 題（卡在同錯誤打轉、過度讀檔） |
| `trace-commons/agent-traces` | Hugging Face `trace-commons/agent-traces`（<1k rows） | Hugging Face 社群軌跡集 | 去識別化的 Claude Code／Codex 使用者互動與工具呼叫紀錄 | 中：真實 CLI 工具紀錄；樣本較小且上游程式碼授權需自行確認 | `CC-BY-4.0`，HF 直接載入 | 3–5 題（CLI 工具實戰卡點） |
| `ASSERT-KTH/reproducible-trajectories` | `https://github.com/ASSERT-KTH/reproducible-trajectories` | GitHub 工具庫與軌跡收集架構（搭配 arXiv:2509.14745） | 可重現的 Claude Code 等 agent 操作紀錄與 PR 採納／修改統計（54.9% 未改直接合入、45.1% 需人工微調） | 高：KTH 學界實證，揭示 PR 被人類微調的常見原因 | 授權／星數待驗證，GitHub 公開 | 3–5 題（PR 審查與人工接手修補） |

### B. 學術實證研究（失敗模式分類、Context 檔案與安全邊界）

| 名稱 | 網址 | 類型 | 能提供什麼 | 品質判斷 | 授權或取得方式 | 能轉成幾題評測 |
|---|---|---|---|---|---|---|
| `How Coding Agents Fail Their Users` | `https://arxiv.org/abs/2605.29442` | arXiv 實證論文 | 分析 20,574 筆真實 session，建立「開發者-Agent 對齊失敗分類法」（違反約束 38%+、錯判意圖、假完成、擅自越權、錯診專案） | 極高：目前所見規模最大、最貼近使用者真實摩擦的失敗分類研究 | 公開論文（arXiv） | 8–12 題（負面禁令過猶不及、假完成等） |
| `Where Do AI Coding Agents Fail?` | `https://arxiv.org/abs/2601.15195` | MSR 2026 / arXiv 論文 | 分析 GitHub 上被拒的 agentic PR 分類（偏離設計、diff 過大難審、CI 失敗、重複無效 PR） | 高：從專案維護者角度看 agent 為什麼被打槍 | 公開論文（arXiv） | 4–6 題（diff 過大、不符專案規範） |
| `Evaluating AGENTS.md` | `https://arxiv.org/abs/2602.11988` | ETH Zurich / ICLR 2026 Workshop 論文 | 實測發現 LLM `/init` 自動產生的 `AGENTS.md` 反降成功率約 3% 且多花 20%+ 推理成本；人類精簡撰寫僅微幅提升約 4% | 極高：嚴謹對照實驗，直接修正「盲目叫 agent 生規則檔」的迷思 | 公開論文（arXiv） | 2–3 題（規則檔反效果、過長退化） |
| `Guardrails Beat Guidance` | `https://arxiv.org/abs/2604.11088` | arXiv 大規模實證（679 rule files / 5,000+ Claude Code runs） | 實測證實「負向護欄（不要動無關程式）」有效，空泛「正向指導（遵守風格）」常無效或有害 | 極高：與 `SKILL.md`「講原因與護欄」原則互補，有 5,000 次受控實驗支持 | 公開論文（arXiv） | 3–5 題（規則該寫什麼、不該寫什麼） |
| `Agent READMEs` & `Scanning the Harness` | `https://arxiv.org/abs/2511.12884` / `https://arxiv.org/abs/2609.07360` | arXiv 實證論文 | 前者統計 2,300+ `AGENTS.md`/`CLAUDE.md` 偏重測試/架構而漏寫安全（14.8%）與效能（14.5%）；後者掃描 3,171 repo 揭露設定檔與 skill 供應鏈安全缺陷 | 高：精確指出設定檔盲區與第三方 skill/hook 安全風險 | 公開論文（arXiv） | 3–4 題（規則漏寫非功能限制、安裝外部 skill/MCP 風險） |
| `Beyond Resolution Rates` | `https://arxiv.org/abs/2604.02547` | arXiv 實證論文 | 證實「先積極蒐集脈絡再改動 + 重視驗證」是成功的關鍵結構策略；最小改動卻失敗多源於架構推理不足 | 高：從軌跡控制任務難度後抽出的行為證據 | 公開論文（arXiv） | 2–3 題（先查後改策略） |

### C. 學術 Benchmark（模糊需求澄清、多輪協作、使用者模擬、安全與測試）

| 名稱 | 網址 | 類型 | 能提供什麼 | 品質判斷 | 授權或取得方式 | 能轉成幾題評測 |
|---|---|---|---|---|---|---|
| `ClarifyCodeBench` | `https://arxiv.org/abs/2607.00711` | arXiv Benchmark | 專測寫程式前對模糊需求的提問能力，提供 TKQR、ORA 指標，揭示「會寫不等於會問」 | 極高：直接提供衡量「問法庫是否有效促進精準提問」的公式與資料 | 公開論文（arXiv） | 6–10 題（模糊需求澄清題） |
| `ClarEval` & `Ask or Assume?` | `https://arxiv.org/abs/2603.00187` / `https://arxiv.org/abs/2603.26233` / `https://github.com/nedwards99/ask-or-assume` | arXiv + GitHub（~11 stars） | 前者注入缺目標／缺前提／術語模糊測協作商數（ATC、KQC）；後者改編 SWE-bench Verified 成缺資訊版本測「該問還是該猜」 | 高：有可下載程式碼與明確模糊類型分類（CC BY-NC-SA 4.0） | arXiv 公開；GitHub `CC BY-NC-SA 4.0` | 6–8 題（何時先問、何時先做） |
| `Orchid`（Clarity Is Not Assumed） | `https://arxiv.org/abs/2604.21505` | arXiv Benchmark（1,304 題） | 將模糊需求細分為詞彙、句法、語意、籠統四類，實測模型在未澄清下品質急墜的現象 | 高：分類細緻，適合拿來做同情境四種模糊問法變體 | 公開論文（arXiv） | 4–6 題（多種模糊變體設計） |
| `SWE-Clar` | `https://github.com/upwork/SWE-Clar` | GitHub Benchmark（~44 stars） | 源自 100 個真實自由接案綠地專案（>= $4,000）的客戶不完整需求與多輪澄清測試 | 高：非常貼近非技術／半技術甲方「講不清要什麼」的真實情境 | `MIT`，GitHub 公開 | 5–8 題（從零開新專案與客戶對焦） |
| `UserSWE` & `SWE-Together` & `SWE-TaskFlow` | `https://arxiv.org/abs/2610.29822` / `https://arxiv.org/abs/2606.29957` / `https://arxiv.org/abs/2610.09633` | arXiv + HF（`yifannnwu/SWE-Together`） | 基於 20k+ 真實 session 與 JetBrains IDE 流程校準的動態使用者模擬器，分階段釋放資訊測多輪協作 | 極高：是把單輪評測升級成「多輪沙盒對話評測」的現成設計範本 | arXiv 公開；`SWE-Together` 為 `Apache-2.0` | 方法論核心（多輪模擬架構） + 4–6 題 |
| `FeatureLoop` & `EvoCode-Bench` | `https://arxiv.org/abs/2610.35488` / `https://arxiv.org/abs/2605.24110` | arXiv Benchmark | 測試持續工作區中歷經 5–15 輪「邊做邊改需求」與累積回歸測試時的穩定度 | 高：精準對應社群最痛的「多輪迭代後結構崩壞」 | 公開論文（arXiv） | 4–5 題（需求演進與防回歸） |
| `SyncMind`（SyncBench） | `https://arxiv.org/abs/2502.06994` | arXiv Benchmark | 測量協作中人類或環境狀態已變更、agent 認知過時（out-of-sync）時的恢復能力 | 高：補上「人類中途手改程式後 agent 狀況外」的空白 | 公開論文（arXiv） | 2–3 題（狀態不同步恢復） |
| `SWE-CC` & `SWE-Misbehavior` & `LSCBench` | `https://arxiv.org/abs/2610.06193` / `https://arxiv.org/abs/2610.18206` / LSCBench（URL 待驗證） | arXiv / GitHub Benchmark | 分別測：repo 政策合規（失敗率達 43%）、11 類越界破壞行為、未提安全時的功能實作漏洞率（73–91% 過功能但僅 <=25% 過安全） | 極高：揭露「功能對但違規／危險／刪錯檔」的隱形災難 | `SWE-CC`/`SWE-Misbehavior` arXiv 公開；LSCBench GitHub 網址待驗證 | 6–9 題（安全、政策合規、破壞性行為） |
| `TestPrism` | `arXiv:2610.12289`（完整 URL 待驗證） | arXiv Benchmark（300 任務 / 3,000 實作） | 用 Joint Success Function（JSF）揭露 agent 自寫測試的「單一參照幻覺」（從 59.7% 跌到 28.0%） | 高：直接可用於教使用者怎麼檢驗「agent 補的測試是不是假的」 | arXiv 公開 | 2–3 題（測試品質與假陽性排查） |

### D. 官方文件與開發指南

| 名稱 | 網址 | 類型 | 能提供什麼 | 品質判斷 | 授權或取得方式 | 能轉成幾題評測 |
|---|---|---|---|---|---|---|
| Anthropic `Demystifying evals for AI agents` | `https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents` | 官方工程指南 | Agent eval 拆解（task/trial/transcript/grader）、`pass@k` vs `pass^k` 穩定度指標與實戰建議 | 極高：一線官方實務總結 | 公開網頁 | 評測設計核心參考 |
| `anthropics/skills`（`skill-creator`） | `https://github.com/anthropics/skills` | 官方開源套件（~196k stars、~22.6k+ forks） | 官方技能結構、觸發率評估規範（`should_trigger: true/false`）、近失負向測試與 description 自動優化迴圈 | 極高：與 Claude Code plugin 機制完全同源 | `Apache-2.0`（範例技能）／專屬條款（文件技能） | 評測設計核心參考（觸發率測試） |
| OpenAI Codex Guides & Best Practices | `https://developers.openai.com/codex` / `https://learn.chatgpt.com/docs/guides/best-practices` | 官方文件 | Codex 四要素提示架構（Goal / Context / Constraints / Done When）、`/plan`、`/goal`、`AGENTS.md` 階層合併規則與推理程度選擇 | 極高：官方一手規格，可對齊 `features.md` Codex 欄 | 公開網頁 | 2–4 題（Codex `/goal` 與推理調整） |
| Google Antigravity & Gemini CLI Docs | `https://antigravity.google` / `https://github.com/google-gemini/gemini-cli` | 官方文件與開源 repo（gemini-cli ~108k stars、~14.9k forks、Apache-2.0） | Antigravity 探索-規劃-執行流程、One URL = One Project Folder 隔離規則、`GEMINI.md` `@import` 模組化設定 | 極高：官方一手文件 | 公開網頁／`Apache-2.0` | 2–3 題（Gemini CLI/Antigravity 情境） |

### E. 社群回報、業界調查與開源實踐（GitHub / Reddit / HN / 中文社群）

| 名稱 | 網址 | 類型 | 能提供什麼 | 品質判斷 | 授權或取得方式 | 能轉成幾題評測 |
|---|---|---|---|---|---|---|
| 主流 Coding Agent GitHub Issues（Codex / Gemini CLI / Cline / Aider / Claude Code） | `openai/codex`（~136k stars）、`google-gemini/gemini-cli`（~108k stars）、`cline/cline`（~64k stars）、`Aider-AI/aider`（~50.2k stars） | 開源 Issue Tracker | 真實卡住現場：compaction 無限重讀（Claude Code #11487/#6061、Codex #27588/#8481）、thinking loop（#24585、Cline #13111）、API 重試風暴 | 極高：最即時的真實用戶卡死案例；需過濾純程式 bug 與「使用者問法可解」的狀況 | 公開 Issue（多為 Apache-2.0 repo） | 6–10 題（中斷與急救情境） |
| Reddit（`r/ClaudeCode`, `r/ClaudeAI`, `r/codex`, `r/vibecoding`）與 Hacker News | `reddit.com` / `news.ycombinator.com` | 技術社群討論 | Compaction 失憶救回（`SessionStart` hook 讀 `DECISIONS.md`）、MCP 工具定義塞爆 context、hooks `exit 0` 靜默失敗、subagent 燒光 5 小時額度、Vibe coding doom loop | 中高：極貼近體感痛點；偏零散經驗談，建議交叉多帖再採信 | 公開網頁 | 8–12 題（實戰摩擦與操作急救） |
| 中文開發社群（iT 邦幫忙、V2EX、掘金） | `ithome.com.tw` / `v2ex.com` / `juejin.cn` | 繁簡中文技術社群 | 「症狀修補（亂加 null check）」、「虛假掌控感」、Vibe coding 遺留大量空殼與明文密碼、用檔案當臨時 RAM（`planning-with-files`） | 中高：反應華語開發者常見語境與提問盲點 | 公開網頁 | 4–6 題（中文常見誤區） |
| METR 2025 RCT & Stack Overflow Survey & GitClear | METR / Stack Overflow / GitClear（具體頁 URL 待驗證） | 業界實證調查與隨機對照實驗 | METR：資深開發者在大型 repo 用 AI 反慢 19% 但自覺快 20%（感知落差）；SO：84% 採用率但信任跌至 29–33%，66% 痛「Almost right」、45% 嫌 debug 更久；GitClear：複製程式碼與 churn 翻倍 | 極高：打破「看起來很順就是比較快」的盲區 | 公開研究報告 | 3–5 題（何時該停手自己寫、避免複製造輪子） |
| `multica-ai/andrej-karpathy-skills` / `PatrickJS/awesome-cursorrules` | GitHub（andrej-karpathy-skills ~233k stars、MIT；awesome-cursorrules ~41.2k stars、CC0-1.0） | 社群高星規範合集 | 歸納 LLM 寫程式高頻毛病（動手前不問、過度複雜、順便改別處、不給驗證步驟）對應的簡潔護欄 | 中：極具代表性社群共識，但未附系統性實驗對照（與 `Guardrails Beat Guidance` 搭配看更佳） | `MIT` / `CC0-1.0` | 參考語句與規則模板 |

### F. Skill / Prompt 評測工具與 LLM-as-a-Judge 校準方法論

| 名稱 | 網址 | 類型 | 能提供什麼 | 品質判斷 | 授權或取得方式 | 能轉成幾題評測 |
|---|---|---|---|---|---|---|
| `NVIDIA/SkillEvaluator` | `https://github.com/NVIDIA/SkillEvaluator` / `https://arxiv.org/abs/2608.20614` | GitHub 框架（~3.1k stars、~434 forks）+ 論文 | 專為 Agent Skill 設計的三層評測：靜態與安全檢查、Skill 間語意重疊偵測、沙盒執行與路由命中評測 | 極高：是目前最系統化的 Skill 持續評測架構 | `Apache-2.0` | 評測基礎設施 |
| `SkillsBench` & `adewale/skill-eval-harness` | `https://github.com/benchflow-ai/skillsbench`（arXiv:2602.12670）／GitHub `adewale/skill-eval-harness`（~54–79 stars） | Benchmark 與開源評測器 | 跨模型、跨 harness（Claude Code / Codex / OpenCode）的 `with-skill` vs `without-skill` 因果增益矩陣與觸發率統計 | 高：正好可補 `ask-eval`「只測 Claude Code 單模型」的缺口 | `MIT`（skill-eval-harness）／SkillsBench 授權待驗證 | 評測基礎設施 |
| `Self-Preference Bias in Rubric-Based Evaluation` & `Bias in the Loop` | `https://arxiv.org/abs/2604.06996` / `https://arxiv.org/abs/2604.16790` | arXiv 評測方法論文 | 證明同家族裁判在二元 rubric 下對自家模型失敗項誤判率高 >50%；提供長度、順序偏誤與審計報告標準 | 極高：直接修正 `ask-eval` 評分者設計 | 公開論文（arXiv） | 評測校準規範 |
| `RoPoLL` / `PoLL` & `JudgeBench` | `https://arxiv.org/abs/2606.30931` / `https://github.com/ScalerLab/JudgeBench` | 論文與裁判校準基準 | 用多模型異質評審團（Jury）+ 穩健估計量（如幾何中位數）取代單一裁判，降低同源與迎合偏誤 | 高：低成本取代單一昂貴同源裁判 | arXiv / GitHub 公開 | 評測校準規範 |
| `promptfoo/promptfoo` & `UKGovernmentBEIS/inspect_ai` | GitHub `promptfoo/promptfoo`（~27.3k stars、MIT）／`UKGovernmentBEIS/inspect_ai`（~3.3k stars、MIT） | 開源評測引擎 | Promptfoo 擅長 YAML 宣告式紅隊／回歸矩陣；Inspect AI（UK AISI）原生支援多輪 agent 沙盒、工具狀態追蹤與自訂評分器 | 極高：業界與安全機構標準基礎設施 | `MIT` | 評測執行引擎 |

---

## 3. 新題目清單（目前 72 個情境沒涵蓋的常見卡住情境）

已逐一核對 [SKILL.md](../../engine/skills/omnikit-ask/SKILL.md) 現有 72 個情境，以下 16 題均屬於**現有索引尚未明確點破**、但在實證論文與社群高頻出現的卡住處境（按現有類別歸類）：

### 跟 agent 協作（`situations/agent.md`）
1. **Compaction 壓縮後記憶斷片、反覆重讀同一批檔案**：對話自動壓縮完，agent 忘掉剛講好的設計決定，甚至陷入「讀檔 → 壓縮 → 再重讀」的無限迴圈。（出處：GitHub Claude Code #11487/#6061、Codex #27588/#8481、Reddit `r/ClaudeCode`）
2. **裝了太多 MCP 伺服器，還沒開口做事腦容量就滿了**：接了一堆資料庫／GitHub／Jira MCP，tool schema 佔滿上下文讓表現變笨，或擔心外部 MCP 工具描述藏惡意指令。（出處：Reddit `r/ClaudeCode`、MCP tool poisoning 安全報告、`Scanning the Harness` arXiv:2609.07360）
3. **Hook 或自動檢查腳本其實沒過，agent 卻像沒看到繼續往下改**：自訂的 `PreToolUse` / `PostToolUse` 或檢查腳本出錯卻回傳 `exit 0` 或 `stderr` 被吞，形成假護欄。（出處：Reddit / DEV Community hooks 踩坑紀錄）
4. **用 `/init` 自動生出來的 `CLAUDE.md`／`AGENTS.md` 反而拖慢效能、越用越貴**：專案根目錄塞了自動生成或過時的架構指南，導致 agent 盲目探索無關目錄或沿用舊寫法。（出處：ETH Zurich `Evaluating AGENTS.md` arXiv:2602.11988、Reddit `CLAUDE.md` 過時反模式）
5. **派了多隻 Subagent 分工，結果總控自己跳下去做或把額度瞬間燒光**：多代理系統出現 Orchestrator Drift，沒切好邊界或沒限 `maxTurns`，一轉眼撞到 5 小時速率上限。（出處：Reddit `r/ClaudeCode` subagent 踩坑）
6. **Agent 卡在「自己跟自己開會」的思考迴圈遲遲不動手**：一直重複輸出「其實問題在於…等等不對…讓我再檢查一次」卻不呼叫工具也不改檔。（出處：GitHub Claude Code #24585、Cline #13111/#5722）
7. **下了「不要做 X」的負面禁令，agent 卻過度解讀把正常功能一起砍掉**：例如寫「不要發任何外部訊息」，結果它把內部錯誤監控或測試通知管線也一併關掉。（出處：`How Coding Agents Fail Their Users` arXiv:2605.29442）
8. **自己中途手改了程式或切了分支，agent 卻拿著過時印象繼續亂蓋**：人機編輯不同步（out-of-sync），agent 沒重讀現場就依記憶打補丁覆蓋掉人類剛寫好的邏輯。（出處：`SyncMind` arXiv:2502.06994）
9. **誤動到不該碰的系統環境、`.env` 或正式資料庫**：沒隔離環境就讓 agent 跑指令，結果它偷改設定檔、降級依賴、或對真實資料庫下破壞性查詢。（出處：`SWE-Misbehavior` arXiv:2610.18206、Reddit DB/env 踩坑）
10. **換了新版模型或別家工具後，原本好用的提示或規則突然失效或變很拗**：舊習慣的「逐步思考」「嚴格遵守」在新模型上引發過度推理，或模型切換後表現大幅漂移。（出處：Hacker News 模型漂移討論、Anthropic 新模型提示建議）

### 除錯 / 測試、安全、效能、上線（`situations/debug.md` 與 `situations/quality.md`）
11. **修 bug 時只做了「表面空值防呆」或把測試改鬆，問題其實被藏起來**：遇到錯誤就在報錯行加 `if x is None: return` 或修改預期值讓測試綠燈，但上游資料源頭依然是壞的。（出處：中文社群「症狀修補」討論、`How Coding Agents Fail Their Users` arXiv:2605.29442）
12. **功能寫得出來也會動，但沒提安全就被塞了隱形漏洞**：需求只講業務流程沒講安全，結果生出含硬編碼密鑰、不安全反序列化或缺少權限驗證的程式碼。（出處：`LSCBench`、Vibe coding 資安案例）
13. **剛叫 agent 補完測試，怎麼確定這批測試「真的能抓錯」而不是量身敷衍**：新生成的測試對現行實作會過，但不確定它能不能擋住錯誤實作（單一參照幻覺）。（出處：`TestPrism` arXiv:2610.12289、HN「overfitting to the test」；註：現有 `quality.md` 只有「測試很多但感覺抓不到真錯」，這題專指「驗收剛由 agent 生出來的新測試」）
14. **改對了邏輯也過了測試，卻因為不合專案隱含的貢獻規範被退件**：違反 repository 的 git 流程、命名或模組邊界政策，因為政策文件沒直接指給 agent 看。（出處：`SWE-CC` arXiv:2610.06193、`Where Do AI Coding Agents Fail?` arXiv:2601.15195）

### 需求與範圍 / 架構與專案管理（`situations/requirements.md` 與 `situations/project.md`）
15. **不確定這個小缺漏該讓 agent「直接猜著先做」，還是「先停下來反問我」**：怕每次都問太煩、又怕直接做錯白燒半小時。（出處：`ClarifyCodeBench` arXiv:2607.00711、`Ask or Assume?` arXiv:2603.26233）
16. **Agent 每次都重寫新函式「造輪子」，不重用專案現有元件／工具**：程式庫裡明明已經有共用模組，agent 卻因上下文沒看到而到處複製類似邏輯，讓後續維護加倍痛苦。（出處：GitClear Code Churn & Duplication 報告）
17. **已經進入「90% 看似寫完、剩最後 10% 怎麼逼都修不好」的泥沼，不知該繼續提示還是接手自己寫**：一直出現「幾乎對但差一點」的微妙邏輯錯，重試越久比手寫更慢。（出處：Stack Overflow Survey 66%「Almost right」、METR RCT 慢 19%、HN「Slot Machine」討論）

---

## 4. 評測設計的建議

對照現有 [2026-11-17-ask-eval.md](../../docs/reviews/2026-11-17-ask-eval.md)（11 題、空資料夾、單一 Claude 執行 + Sonnet 評分、題目與問法庫同源、未測負向對照），業界與 2026 年最新研究指出以下 6 項最關鍵的補強做法：

1. **補齊「近失負向對照（Near-Miss Negative Controls）」獨立量測觸發精準度**：
   - 照 Anthropic `skill-creator` 與 `NVIDIA/SkillEvaluator` 的做法，建立 `should_trigger: false` 測試集，且題目必須是**外觀很像但其實資訊已給齊、不該觸發問法庫反問使用者**的近失題（例如：「請依 `src/auth.ts` 第 42 行修正 refresh token 過期未拋錯的問題，並跑 `pytest tests/test_auth.py` 貼出結果」）。
   - 同時檢查 `omnikit-ask` 的 `description` 與 repo 內其他 skill 的語意重疊度（`SkillEvaluator` Tier 2），避免搶觸發。
2. **去除「觸發關鍵字依賴」與增加多樣口語變體（Paraphrase Suite）**：
   - 現有 11 題中有 5 題直接寫出「我不知道怎麼問」等提示語，實際卡住時使用者多半只會貼錯誤、抱怨或講得不清不楚。每個情境應至少設計 3 種說法：明確求助型、情緒抱怨／籠統描述型（參考 `Orchid` 四類模糊）、只貼片段錯誤或截圖型。
3. **消除「評分同源偏誤」與「Self-Preference Bias」**：
   - `arXiv:2604.06996` 證實即使用客觀 rubric，用同家族模型評自家輸出仍有 >50% 寬鬆偏誤；且目前評分項「有沒有給可以直接貼的句子」偏袒問法庫格式。
   - 建議：
     - **跨模型家族評審團（`RoPoLL` / `PoLL`）**：改用 Claude + GPT + Gemini 三家異質裁判投票或幾何中位數聚合計分。
     - **隨機交換 A/B 成對比較 + 反冗長指令**：同時把「有 skill」與「無 skill」回覆盲測並交換先後順序，只在正反順序一致時算勝，並在評分 prompt 明寫不因字數較長加分。
     - **抽樣人類盲評校準**：抽 20% 題目由人盲評「哪個回答真的減少下輪返工」，計算與 LLM 裁判的一致率（Cohen's kappa），修正裁判 rubric 直到對齊後再凍結評分腳本。
4. **從「空資料夾純說理」升級到「微縮壞專案沙盒 + 模擬使用者多輪對話」**：
   - 現有 11 題在空資料夾執行，只能考「嘴上建議」。參考 `Inspect AI`、`UserSWE`、`SWE-Together`、`FeatureLoop`：建 5–8 個極小壞掉的沙盒資料夾（例如：按鈕壞掉但有真實 log 的網頁、沒測試的舊函式、`CLAUDE.md` 過時的專案、含假測試的模組）。
   - 加入一個扮演使用者的 LLM（僅握有隱藏細節，照 `ClarifyCodeBench` / `UserSWE` 資訊池設計：只有在 agent 問對關鍵問題時才吐出真實條件），最終用**確定性測試（程式跑得過、diff 範圍最小、總往返輪數與 Key Question Coverage）**計分，而不是只用 LLM 看文字順不順眼。
5. **做「跨 Harness」與「無全域規則」的消融對照矩陣**：
   - 參考 `SkillsBench` 與 `adewale/skill-eval-harness`：把實驗設計成多格矩陣——測驗 **Claude Code / Codex CLI / Gemini CLI（或 Antigravity）**，並比較「有個人全域規則（OmniKit `CLAUDE.md`）」與「純淨預設環境」兩組。這能拆清增益究竟是來自問法庫本身還是全域規則，同時檢驗 `features.md` 在 Codex／Antigravity 的指令正確性。
6. **引入穩定度指標 `pass^k` 與安全退化門檻**：
   - 照 Anthropic *Demystifying evals* 建議，除平均分外另外看 `pass^k`（同一題連跑 3 次全部穩定通過的比例），以及負向回歸門檻（裝了問法庫後，原本就會做的「簡單明確修改題」不能變慢、不能多出無關建議或違反 `LSCBench` 安全底線）。

---

## 5. 查了什麼

本次採**飽和式調研**，依結果中出現的新詞動態展開，總計執行 **11 輪網路檢索**，覆蓋全部指定管道，並在**連續 3 組不同角度擴展關鍵字均未出現新來源名稱**時停止。

### 使用的關鍵字組與輪次紀錄
* **第 1 輪（廣泛鋪網，12 組並行，跨全部管道）**：
  - `"coding agent" trajectory dataset huggingface OR github`
  - `"DevGPT" OR "WildChat" OR "LMSYS" developer coding conversation dataset`
  - `underspecified code generation clarification questions benchmark arxiv`
  - `multi-turn interactive coding agent benchmark "user simulator" arxiv`
  - `"Stack Overflow" Developer Survey AI coding frustrations trust 2024 OR 2025 OR 2026`
  - `METR AI coding productivity RCT developer study`
  - `site:reddit.com "Claude Code" OR "Cursor" OR "Codex" stuck OR frustrating OR "keeps breaking" OR "loop"`
  - `site:news.ycombinator.com "Claude Code" OR "coding agent" frustrating OR "rabbit hole" OR "breaks"`
  - `"Claude Code" OR "Cursor" 踩坑 OR 越改越爛 OR 卡住 OR 問法`
  - `Anthropic skill eval trigger rate "negative" OR "should_trigger" OR "skill-creator"`
  - `LLM-as-a-judge bias calibration self-enhancement verbosity rubric eval`
  - `site:github.com "claude-code" OR "codex" OR "aider" OR "cline" "best practices" OR "awesome" coding agent prompts`
* **第 2 輪（從第 1 輪新詞擴展 + 業界調查 + Vibe coding + 中文技術論壇，10 組）**：
  - `"ClarifyCodeBench" OR "ClarEval" OR "UserSWE" OR "SWE-TaskFlow" OR "EvoCode-Bench" arxiv URL`
  - `"DevGPT" github OR zenodo license size AND "thoughtworks/agentic-coding-trajectories" huggingface`
  - `"MINT" OR "Tau-bench" OR "ColBench" OR "SyncMind" multi-turn user interaction coding agent benchmark arxiv`
  - `"GitClear" AI code churn OR "DORA" report AI coding productivity OR "JetBrains" Developer Ecosystem AI 2025 OR 2026`
  - `Anthropic "Demystifying evals" OR "skill-creator" github "should_trigger" OR OpenAI "Codex" prompting guide`
  - `"PoLL" "Panel of LLM Evaluators" OR "JudgeBench" OR "promptfoo" LLM judge calibration arxiv OR github`
  - `site:github.com "anthropics/claude-code" OR "openai/codex" OR "cline/cline" issues "stuck" OR "loop" OR "context" OR "breaks"`
  - `"vibe coding" frustrations OR "keeps breaking" OR "stuck" debugging security deployment reddit OR "hacker news"`
  - `(site:v2ex.com OR site:juejin.cn OR site:zhihu.com OR site:ithome.com.tw) ("Claude Code" OR "Cursor" OR "vibe coding") 踩坑 OR 卡住 OR 幻覺 OR 上下文`
  - `site:huggingface.co datasets "WildChat" OR "CodeFeedback" OR "OpenHands" OR "SWE-agent-trajectories" license rows`
* **第 3 輪（學術失敗分類法、Semantic Scholar、OpenAI/Google 官方文件、GitHub Topics/Stars、MCP/Hooks/Subagent 痛點，10 組）**：
  - `"taxonomy" OR "empirical study" developer challenges OR failures "coding agent" OR "ChatGPT" OR "Copilot" "Semantic Scholar" OR ICSE OR FSE OR MSR OR arxiv`
  - `site:developers.openai.com OR site:platform.openai.com OR site:cookbook.openai.com "Codex" prompting OR "best practices" OR "AGENTS.md"`
  - `site:geminicli.com OR site:ai.google.dev OR site:antigravity.google "best practices" OR "GEMINI.md" OR "prompt" coding agent`
  - `"Demystifying evals for AI agents" anthropic.com URL AND "anthropics/skills" github stars skill-creator`
  - `"NAIST-SE/DevGPT" OR "DevGPT" github zenodo stars license AND "all-hands/openhands-feedback" huggingface`
  - `site:github.com ("anthropics/claude-code" OR "openai/codex" OR "google-gemini/gemini-cli" OR "cline/cline" OR "Aider-AI/aider") stars forks license`
  - `"promptfoo" OR "inspect_ai" OR "OpenAI Evals" agent evaluation calibration LLM judge github stars`
  - `"Ask or Assume" "SWE-bench" arxiv URL AND "Orchid" "Clarity Is Not Assumed" arxiv URL AND "SWE-RPG" arxiv URL`
  - `"SWE-bench" failure analysis OR "why coding agents fail" OR "developer-agent interaction" empirical study arxiv 2025 OR 2026`
  - `site:reddit.com "Claude Code" OR "Codex" OR "Gemini CLI" ("MCP" OR "permissions" OR "worktree" OR "compaction" OR "CLAUDE.md" OR "AGENTS.md") frustrating OR mistake OR tip`
* **第 4 輪（補齊失敗研究 arXiv URL、GitHub topics、Semantic Scholar 延伸、HF 剩餘資料集、OpenAI eval 指南，8 組）**：
  - `"How Coding Agents Fail Their Users" OR "Where Do AI Coding Agents Fail" OR "SWE-Misbehavior" OR "SWE-CC" OR "Beyond Resolution Rates" arxiv URL`
  - `"developers.openai.com/codex" OR "cookbook.openai.com" "codex" prompting guide URL AND "geminicli.com/docs" best practices OR "GEMINI.md" URL`
  - `site:github.com topic "coding-agent" OR "claude-code" OR "llm-evaluation" OR "agent-skills" stars forks`
  - `site:semanticscholar.org developer "coding assistant" OR "ChatGPT" OR "coding agent" "challenges" OR "frustrations" OR "misalignment" OR "prompt"`
  - `site:huggingface.co datasets "SWE-smith" OR "OpenHands" OR "WildFeedback" OR "CommitPack" OR "ShareGPT" coding trajectory license rows`
  - `"OpenAI" "evaluation best practices" OR "eval-driven" OR "working with evals" platform.openai.com OR cookbook.openai.com`
  - `"CodeAgent" OR "InterCode" OR "AppWorld" OR "Terminal-Bench" OR "SWE-Lancer" multi-turn coding agent benchmark arxiv URL`
  - `"Claude Code" OR "Codex" "MCP" OR "hooks" OR "subagent" OR "database" OR "environment" common pitfalls developer experience reddit OR blog`
* **第 5 輪（追新詞 + 查星數與授權，7 組）**：出現 `nuprl/AgentPack`、`ASSERT-KTH/reproducible-trajectories`、`SkillsBench`、`SkillRouter`、`TestPrism`、`andrej-karpathy-skills`、ETH Zurich `Evaluating AGENTS.md` 研究。
* **第 6 輪（查第 5 輪新詞 + 首輪 3 組飽和測試，6 組）**：其中 2 組再冒出 `SALT-NLP/SWE-chat`、`SWE-Together`、`Guardrails Beat Guidance`、`Agent READMEs`、`Beyond the Prompt`、`Scanning the Harness`，故飽和計數歸零。
* **第 7 輪（查第 6 輪 URL + 擴展資料集／社群清單／HN 討論，5 組）**：再冒出 `Suzhen/CodeChat-V2.0`、`trace-commons/agent-traces`、`LSCBench`。
* **第 8 輪（第 2 次 3 組飽和測試 + 查 Antigravity 文件，4 組）**：`LSCBench` 延伸組提及新名稱 `SWE-Clar`，故計數再歸零。
* **第 9 輪（確認 `SWE-Clar` + 檢索 ACM/IEEE/Semantic Scholar + GitHub skill evals + 互動資料集，4 組）**：冒出 `adewale/skill-eval-harness`。
* **第 10 輪（查 `skill-eval-harness`/`SWE-Clar` 星數 + 最後擴展人機互動與裁判偏誤，3 組）**：冒出 `FeatureLoop`、`CentaurEval`、`Self-Preference Bias in Rubric-Based Evaluation`、`Bias in the Loop`。
* **第 11 輪（查第 10 輪 arXiv URL + 3 組獨立飽和收斂驗證，4 組）**：
  - `"FeatureLoop" OR "CentaurEval" OR "SWE-Clar" benchmark human-agent collaboration arxiv` → **無新名字**
  - `"Self-Preference Bias in Rubric-Based Evaluation" OR "Bias in the Loop: Auditing LLM-as-a-Judge" coding evaluation calibration` → **無新名字**
  - `"AgentPack" OR "SWE-chat" OR "DevGPT" developer prompt dataset github OR huggingface` → **無新名字**
  - 在第 11 輪達成**連續 3 組關鍵字皆無新來源名稱**，確認飽和停止。

### 哪裡查不到（研究限制）
- **商業工具內部真實付費互動日誌**：Anthropic（Claude Code）、OpenAI（Codex）、Cursor、Google（Antigravity）皆未公開真實付費使用者的原始卡住對話紀錄，社群公開多只能透過 `SALT-NLP/SWE-chat`、`DevGPT`、`AgentPack` 與 GitHub Issues 間接觀察。
- **「問法建議 skill 是否真的減少人類來回修正輪數」的業界基準**：目前沒有專門測「提示建議庫」省下多少人類輪數的現成公開評測集，最接近的替代機制是 `UserSWE`、`SWE-Together` 與 `ClarifyCodeBench` 的多輪模擬指標。
- **部分零散來源的即時數據**：如 `SALT-NLP/SWE-chat` 與 `ASSERT-KTH/reproducible-trajectories` 在 GitHub 的精確 star/fork 數、`Suzhen/CodeChat` 的單獨授權標示，以及 Antigravity 專屬的第三方評測基準報告，在本次搜尋結果中未見明確一手數字，均已如實標示為「待驗證」。
