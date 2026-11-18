# 調研 R2：AI coding agent 把做得到的事說成「做不到／請你手動做」：研究、官方指南與規則集

## 調研摘要與停止狀態

- **停止回合**：第 10 組（`coding agent laziness verify before claiming`）
- **停止條件判定**：**長尾未飽和**
  - 全部名字連續 0 新增組數：`1`（第 10 組為 0；目標 3 組，未達全體飽和）
  - ★1,000 以上的 GitHub repo 連續 0 新增組數：**`3`**（第 8、9、10 組皆無新進 ★1,000 以上 GitHub repo；已達停止門檻）
  - 備註：依「長尾未飽和」標準停止，代表 ★1,000 以下的小型專案，以及沒有 GitHub 星數的非 GitHub 產品／論文名單不保證完全窮舉。
- **不重複收錄數**：49 個（依 `sweep.py status` 計算）

### 判斷標準

本調研僅將符合以下任一條件之名稱計入帳本有效名單：
- **(a) 論文或 benchmark**：明確量測、診斷或處理「能力偽陰性／假性拒絕／明知可行卻宣稱做不到／可解卻判不可解／過早放棄」這類失敗的論文或 benchmark（僅處理安全性敏感詞誤拒、未涉及工具或任務可行性評估者不計入）。
- **(b) 官方指南**：Anthropic、OpenAI、Google、AWS 等模型或 agent 平台官方文件，內含專門處理 default to action、agentic eagerness、persistence、先探索／查證再下結論、不得僅依訓練資料斷言等段落者。
- **(c) 規則集／Prompt 集／Awesome 清單 repo**：GitHub 上的 `AGENTS.md`、`CLAUDE.md`、`.cursorrules`、system prompt 規則集或 awesome 清單 repo，內容**明確含有**「先探索再說做不到／不要把可自動化的步驟丟給使用者／用最新官方文件而非過時訓練資料」這類規則者（一般泛用 prompt 合集不計入）。

---

## 一、問題 1：研究與業界怎麼稱呼這類問題？

當 coding agent 把「其實有工具或 CLI 可做到的事」自信地說成「做不到／沒有工具／請你手動做」時，學術界與工程社群分別從不同切面命名這個現象（兩者往往比「單純拒絕」更細）：

1. **Learned Incapacity（習得性無能, LI）與 Functional Refusal（功能性拒絕, FR）**
   - 來源：`arXiv:2512.13762`（*State-Dependent Refusal and Learned Incapacity in RLHF-Aligned Language Models*）
   - 定義：類比心理學的 **learned helplessness（習得性無助）**。模型在非敏感領域表現正常（Normal Performance），但在特定政策或工具邊界情境下，即使具備潛在能力，仍重複產出功能性拒絕（FR），並伴隨角色敘事（Meta-Narrative）合理化不作為。
2. **Feasibility Awareness（可行性覺察）與 False Continue / False Infeasibility**
   - 來源：`arXiv:2605.28532`（*Do Agents Know What They Can't Do? Evaluating Feasibility Awareness in Tool-Using Agents*，工具鏈 `LeonChengg/FeasiGen` ★2，Apache/MIT：MIT，2026-11-18 gh api）
   - 定義：量測工具使用代理能否正確辨識「當前環境究竟缺不缺關鍵工具」。既有 benchmark 多半只測「做對多少」，忽略了「可行性誤判」（包含該停不停的 False Continue Rate 最高達 73.9%，以及對可行與不可行任務的錯判）。
3. **Agentic Abstention（代理棄權）與 Agentic Self-Awareness（ASA）**
   - 來源：`arXiv:2606.28733`（*Agentic Abstention: Do Agents Know When to Stop Instead of Act?*）、`arXiv:2607.10059`（*AgentAbstain*）、`arXiv:2610.19226`（*Agentic Self-Awareness: Aligning Knowing, Acting, and Holding*）
   - 定義：將單輪問答的「棄權（Abstention）」擴展到多輪工具互動。特別是 `arXiv:2610.19226` 在 Terminal-Bench 2.1 與 retail tau-2-bench 建立**成對的可行任務與受阻任務（paired feasible and blocked tasks）**，量測「認知（know）、行動（act）、被質疑時的堅持度（hold）」三者之間的一致性——結果發現模型即使辨識出障礙（84.4%），嚴格的自我覺察對齊（strict SA）基線僅 40.6%，且單純提高棄權傾向會傷害可行任務的成功率。
4. **Solvability Boundary（可解性邊界）與 Knowing-Acting Gap**
   - 來源：`arXiv:2512.01661`（*Learning the Boundary of Solvability*）、`arXiv:2406.20015`（*ToolBeHonest*）、`arXiv:2606.20661`（*KAPRO: Knowing-Acting Quadrant Probe*）
   - 定義：區分「客觀不可解（objective unsolvability）」與「主觀能力限制（subjective capability limits）」。`arXiv:2606.20661` 指出「知道能不能用內部知識／外部工具（Knowing）」與「實際呼叫或放棄工具（Acting）」常出現錯位。
5. **注意術語分流：`over-refusal` 多指「安全誤拒」而非「能力低報」**
   - 本調研第 3 組實測驗證：文獻中的 **over-refusal / false refusal / exaggerated refusal**（例如 OR-Bench、XSTest、`arXiv:2505.18325`、`arXiv:2510.08158`）幾乎全數指涉「安全對齊把無害詞彙（如 kill a process）誤判為有害內容而拒絕回答」，並非 coding agent 誤判本機工具／CLI 能力不足。搜尋與設計規則時必須區分這兩者，避免只套用安全去拒絕方案。
6. **業界與工程實務用語**
   - **Permission Anxiety / Passivity（過度請示與被動）**：Anthropic 以 `Default to action` 反制模型只提建議或反覆徵詢。
   - **Agentic Eagerness 過低（積極度不足）／Handing back to user prematurely**：OpenAI GPT-5 Prompting Guide 針對模型一遇不確定就停手、把問題丟回給使用者的行為。
   - **Agent Laziness / Deferring Manual Steps / Premature Refusal**：工程社群用來指涉 agent 跳過探索、偷懶只做一半或叫使用者手動查 log、開 dashboard、跑指令。
   - **Knowledge Cutoff Hallucination**：因模型僅憑過時訓練資料斷言「某 CLI／功能不存在」，未透過 `--help` 或官方文件驗證。

---

## 二、問題 2：有哪些做法被驗證有效？（附論文編號與出處）

### 1. 已被論文／實驗驗證有效的架構與訓練做法
| 做法 | 核心機制 | 實測效果（一手論文數據） | 出處 |
| :--- | :--- | :--- | :--- |
| **CONVOLVE（軌跡蒸餾停損／判斷規則）** | 不改模型權重，從歷史互動軌跡蒸餾出可重用的環境探索與停止規則寫入 context | 在 WebShop 測試集將 Llama-3.3-70B 的及時棄權召回率從 26.7 提升至 57.4 | `arXiv:2606.28733` |
| **HERA（Harness-Environment 共同演化）** | 自動配對「可行／受阻」環境變體，依失敗紀錄迭代調適 agent harness | 在保留測試集將棄權準確率從 61.7% 升至 83.3%，且**同時將可行任務完成率從 68.3% 升至 76.7%**；並可遷移至其他 19 個模型（平均 +15.3 個百分點） | `arXiv:2610.06563` |
| **聯合目標 Harness 搜尋（Joint-Objective Harness Search）** | 不只懲罰做錯，而是對「可行任務成功率」與「受阻任務自我覺察」做雙目標搜尋 | 在 Terminal-Bench 搜尋集將嚴格自我覺察從 45.3% 升至 93.8%；論文並警告「若只針對棄權單目標篩選，會壓低可行任務成功率」 | `arXiv:2610.19226` |
| **UnsolvableRL（可解與不可解配對強化學習）** | 在對齊訓練中納入可解與不可解反例（Reverse Construction），避免單邊嚴苛約束造成能力崩塌 | 在 Qwen3-4B-Instruct 達到 >85% 不可解偵測率，並將可解題目準確率從 43.4% 升至 69.4% | `arXiv:2512.01661` |
| **Evidence-Conditioned Execution Layer（ECLoop）** | 在 agent 與 repo 之間插入執行層閘道，強制要求「先觀測到指定證據，才允許做出對應狀態宣稱或修改」 | 防止未讀夠證據就過早定案（premature commitment），將文字要求轉為執行層狀態檢查 | `arXiv:2607.28815` |
| **多代理架構與能力分離** | 以多代理交叉查核或由明確工具追蹤分離探索與判斷 | `FeasiGen` 觀察到多代理架構可顯著降低不可行條件下的錯誤執行 | `arXiv:2605.28532` |

### 2. 對「確定性說做不到」的關鍵工程洞見（結合論文與工程實證）
1. **為什麼「不確定就上網查」在「自信說做不到」時會失效？**
   - 依 `arXiv:2606.20661`（KAPRO）與 `arXiv:2610.19226`（ASA）：模型的「陳述性自信／自我信念」與「真實環境可行性」常脫鉤。當模型因過時訓練資料或未探索環境而產生**高確定性的否定信念**時，「若不確定再查」的條件分支根本不會觸發。
   - **解法**：把**所有否定主張（「沒有這個工具」「這個功能不支援」「只能手動做」）都視為「待驗證主張」**，套用與「宣稱完成」對稱的 **Evidence-Before-Claim Gate**（先在工作環境跑 `which`／`Get-Command`／`<cli> --help` 或查官方文件，拿到失敗輸出才能說沒有）。這與 `obra/superpowers`（★319,549，MIT，2026-11-18 gh api）的 `verification-before-completion` 鐵律邏輯互補——`obra/superpowers` 規範正面宣稱（「已通過／已完成」前必須有新跑過的指令輸出），否定宣稱（「做不到／不存在」）同樣必須附上實測探索證據。
2. **純自然語言規則（Prose）的遵從衰減**
   - `anthropics/claude-code` Issue #27032 與多篇工程紀錄指出，長篇 `CLAUDE.md` 在長對話後期容易被忽略（「Prose cannot enforce prose」）。
   - 解法是**縮短並具體化規則**（Anthropic 官方建議），並對不可妥協的邊界改用 **PreToolUse / Stop Hooks** 或外掛執行層（如 `ECLoop`）攔截未附驗證證據的回覆。
3. **「最省事路徑優先」的輸出約束**
   - 當模型真的在環境卡關、要提出替代方案或交還使用者時，若缺乏結構化輸出格式，容易把可行方案藏在次要段落或直接請使用者手動點介面。結合 Anthropic `<default_to_action>` 與 Google Gemini「Tool-failure fallback」設計，應強制：先用 CLI／工具探索完成能做的部分，最後一步需要人類時才停止，且不得把可自動執行的步驟列成手動清單。

---

## 三、問題 3：Anthropic、OpenAI、Google（含 AWS）官方指南相關段落

以下皆直接查證官方原始頁面，僅摘錄不超過 15 個英文字的原文短句：

1. **Anthropic — Claude Prompting Best Practices**
   - URL：`https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices`
   - `<default_to_action>` 段落：建議明確指示模型直接動手而非只給建議，缺細節時用工具探索而非猜測：
     - `"By default, implement changes rather than only suggesting them."`
     - `"using tools to discover any missing details instead of guessing."`
   - `<investigate_before_answering>` 段落：強制讀過、查過再回答，禁止憑空斷言：
     - `"Never speculate about code you have not opened."`
     - `"Never make any claims about code before investigating"`
2. **Anthropic — Claude Code Best Practices & CLAUDE.md 文件**
   - URL 1：`https://code.claude.com/docs/en/best-practices`
   - URL 2：`https://code.claude.com/docs/en/claude-md`
   - 針對「本機就有 CLI 卻不會用／不接工具」的情境，明確指出 CLI 是最簡單入口，且不熟的 CLI 只要看 `--help`：
     - `"If that system has a CLI, that's usually the easiest way in."`
     - `"For a CLI it hasn't seen before, pointing it at --help is enough."`
   - 針對規則遵從度與 Hook 強制力：
     - `"The more specific and concise your instructions, the more consistently Claude follows"`
     - `"Longer files consume more context and reduce adherence."`
     - 建議必須強制執行的規定改用 Hook（`"use a PreToolUse hook instead"`）。
3. **OpenAI — GPT-5 Prompting Guide**
   - URL：`https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide`
   - `"Controlling agentic eagerness"` / `"Prompting for more eagerness"` 段落（`<persistence>` 範例）：明確處理模型一遇不確定就停手、向使用者反問或交回控制權的問題：
     - `"Never stop or hand back to the user when you encounter uncertainty"`
     - `"research or deduce the most reasonable approach and continue"`
     - `"Only terminate your turn when you are sure that the problem is solved."`
     - `"Do not ask the human to confirm or clarify assumptions"`
4. **OpenAI — Codex `AGENTS.md` 官方指南**
   - URL：`https://developers.openai.com/codex/agent-configuration/agents-md`
   - 說明 `AGENTS.md` 的載入層級（`~/.codex/AGENTS.md` 到專案目錄合併，上限預設 32 KiB）與驗證方式（`codex --ask-for-approval never`）。**本頁僅說明設定探索與覆寫機制，未見專門處理「勿假性拒絕／不得把步驟丟給使用者」的獨立段落**（若有更細之系統提示指南未公開於此頁，標註為「待驗證」）。
5. **Google — AI Studio / Google Cloud / DeepMind Gemini Prompting 指南**
   - Google AI Studio Prompting Strategies（`https://aistudio.google.com/docs/prompting-strategies`）`## Agentic workflows` 段落：
     - `"Persistence and Recovery: The degree to which the model attempts to self-correct errors."`
   - Google Cloud Engineer Agentic Prompts（`https://docs.cloud.google.com/gemini/docs/discover/engineer-agentic-prompts`）：示範以 XML `<rules>` 與 `<tool_usage>` 強制先查診斷輸出再下結論：
     - `"Verify target cluster and namespace names from diagnostic output before proposing changes."`
   - Google DeepMind 工程師 Phil Schmid 的 Gemini 3 Prompt Practices（`https://www.philschmid.de/gemini-3-prompt-practices`）`The Persistence Directive` 段落：
     - `"If a tool fails, analyze the error and try a different approach."`
     - `"Do NOT yield control back to the user until you have verified"`
6. **補充發現：AWS Well-Architected Agentic AI Lens（`AGENTREL05-BP03`）**
   - URL：`https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentrel05-bp03.html`
   - 專門規範不得僅靠模型訓練資料（knowledge cutoff）推論，必須以權威工具即時檢索：
     - `"Training data has a cutoff"`
     - `"agent reasoning only from model knowledge can hallucinate"`

---

## 四、問題 4：GitHub 上的規則集、Prompt 集與 Awesome 清單（含實測星數與授權）

以下專案皆已用 `gh` API 實測星數、授權並讀過實際規則檔原文（查詢日期：**2026-11-18**）：

### 1. 符合判斷標準 (c) 的代表專案
| Repo | 實測星數與授權（2026-11-18 gh api） | 規則所在檔案 | 相關規則大意 |
| :--- | :--- | :--- | :--- |
| `x1xhlol/system-prompts-and-models-of-ai-tools` | ★144,739（GPL-3.0） | `Anthropic/Claude Code 2.0.txt` 等系統提示集合 | 收錄主流 AI 工具系統提示；其中 Claude Code 提示明確規範遇不確定時先調查再回答（`"Whenever there is uncertainty, it's best to investigate to find the truth first"`），並強制操作前先讀取檔案與目錄。 |
| `netdata/netdata` | ★81,463（GPL-3.0） | `AGENTS.md` | 內含 `Working With The User` 與 `Default on doubt`：`Do your homework before asking questions`、只把無法縮減的產品／設計／風險決策交給使用者，遇到懷疑時先調查而非直接分類或退縮。 |
| `PatrickJS/awesome-cursorrules` | ★41,167（CC0-1.0） | `rules/anti-sycophancy-code-discipline-cursorrules-prompt-file.mdc` | 明確要求 **Verify Library Existence**（生成呼叫前先檢查專案依賴檔確認真實存在）、**Refuse to Validate Without Evidence**、以及 **Acknowledge Uncertainty Explicitly**（不知道就明說需驗證，不得編造）。 |
| `dep/agent-rules` | ★11（MIT） | `AGENTS.md` | 明確寫出 **Autonomous Bug Fixing**（不要向使用者討手把手協助，直接看 log、錯誤、失敗測試並解決，對使用者零切換成本）與 **No Laziness**（找根因，不做臨時敷衍修補）。 |
| `jason-m-d/crosby` | ★0（無授權） | `CLAUDE.md` | 實戰型專案規則範例：直接點名禁止把可查的動作推給使用者（`"Don't ask the user to do this."`、`"Don't ask the user to go to the Supabase dashboard."`），要求先檢查 server／讀 log 再猜測。 |

### 2. 常見但「不完全符合」標準 (c) 的高星鄰近專案（說明區分）
- **`multica-ai/andrej-karpathy-skills`**（原 `forrestchang/andrej-karpathy-skills`，★234,078，無授權，2026-11-18 gh api）：`CLAUDE.md` 聚焦「先想清楚再寫、極簡、外科手術式修改、目標驅動驗證迴圈」，未明確包含「禁止叫使用者手動做／不可依訓練資料說做不到」。
- **`obra/superpowers`**（★319,549，MIT，2026-11-18 gh api）：`skills/verification-before-completion/SKILL.md` 的鐵律非常強大，但針對的是「**正面完成宣稱**必須先跑最新驗證」，未處理「**負面不可行宣稱**（做不到）」；不過其 Gate Function 結構可直接借鏡。
- **`AIPMAndy/AndySoul`**（★112，MIT，2026-11-18 gh api）：偏向認知公理、馬斯克五步法與 Karpathy 四原則。
- **`steipete/agent-rules`**（★5,668，MIT，已封存，2026-11-18 gh api）：作者已註明停更。
- **`hesreallyhim/awesome-claude-code`**（★58,260，NOASSERTION，2026-11-18 gh api）：為 Claude Code 資源索引清單，收錄了前述如 HumanLayer、官方規則與部分反敷衍 skill。
- **`upstash/context7`**（★65,036，MIT，2026-11-18 gh api）：屬「提供最新官方文件的 MCP 工具」本身，而非規則集 repo；實務上常配合 `CLAUDE.md` 規則（「查最新文件而非依訓練資料」）一起使用。

---

## 五、問題 5：中文社群怎麼講這個問題？

綜合本調研在 **iT 邦幫忙、就享知、小高工具間、方格子（Vocus）、數位時代、知乎、掘金** 的搜尋與實測讀取，繁簡中文社群對這類問題的討論集中在四個角度：

1. **「AI 負責出主意，人負責當工具人／跑腿」**
   - 方格子文章《AI Agent 能不能讓你少當一點工具人》（`https://vocus.cc/article/6aef0259fd89780001f611cd`）直指許多使用者雖然用了 Agent，卻仍變成「一直按下一步、幫忙複製貼上、開分頁查資料、照 AI 清單手動改檔名」的跑腿角色，主張應透過工具串接讓 AI 做到「確認前」才交回人類。
2. **「一句『做不到』形成工作記憶污染，讓後續任務連查都不查就停住」**
   - 就享知文章《AI 一句「做不到」，為什麼會讓下一次工作也停住？》（`https://www.digiknow.com.tw/knowledge/0f1b8e91b7f14`）實例分析：當 AI 在一次互動中誤判「後台不能操作」或寫入錯誤的記憶結論後，會導致後續任務甚至**連查都不查就直接停手**。
3. **直接針對 `CLAUDE.md` 的反推託寫法（台灣實務教學）**
   - 小高工具間第 3 課《能叫它做的，就別自己動手》（`https://tools.arminkao.com/learn/lesson-03.html`）專門針對 AI 動不動說「請你去做」提供可直接貼入 `CLAUDE.md` 的三條白話規則：「叫我動手之前先自己試；只有卡在我才能做的那一步才叫我，只叫那一步」「要改的東西，叫它自己改，改完讀回來」「付款、送出、刪除，準備好停在按鈕前，等我按」。
4. **「偷懶／鬼打牆／看起來做完」與規則載入失敗**
   - iT 邦幫忙（如《自主決策的分界線：什麼時候該讓 AI 自己決定》`https://ithelp.ithome.com.tw/articles/10422654`）、數位時代與技術部落格多將現象歸納為：
     - 自主光譜未切分清楚（AI 不知何時該自己查、何時才請示）；
     - 規則寫進 `CLAUDE.md`／`AGENTS.md` 太冗長，導致子代理（subagent）零上下文啟動時漏讀規則、模型「偷懶」跳過驗證步驟，最後還是得人工手動重構或擦屁股。

---

## 六、調研管道與帳本輸出紀錄（必附項目）

### 1. 查過的管道與無法查詢的管道說明
- **每組皆查**：`github-topic`、`github-keyword`、`awesome`、`skills-sh`、`npm`、`mcp-registry`、`hn`（Hacker News Algolia）、`exa`（匿名 Exa MCP），以及至少一種網頁搜尋（`web-en` 或 `web-zh`）。
- **整次補查**：`web-zh`（第 4 組中文搜尋）、`web-en`（第 1–3、5–10 組英文搜尋）、`producthunt`（第 7 組執行 `site:producthunt.com` 搜尋）、`related`（第 7 組對 `PatrickJS/awesome-cursorrules` 與 `x1xhlol/system-prompts-and-models-of-ai-tools` 執行 `sweep.py related` 抽 fork 與 README 連結）。
- **查不到／未查的管道與原因**：
  - 全程所有 API 管道皆成功連線，無 HTTP 403/429 限速或金鑰缺漏錯誤。
  - 唯第 4 組使用中文關鍵字 `AI agent 說做不到 叫我手動` 時，依 `sweep.py` 規則：`skills-sh` 因「拿掉通用字後沒有關鍵字」略過不查，`mcp-registry` 因「關鍵字沒有 3 個字元以上的英文字」略過不查，屬腳本設計的語言限制而非連線失敗。

### 2. 最後一次 `sweep.py status --min-stars 1000` 完整輸出

```text
總共 49 個不重複的名字；連續 1 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 3 組沒有新的（要 3 組）：可以停，報告寫「長尾未飽和」並附上面兩種連續數
第 1 組「llm agent learned helplessness」：1 個名字，新的 1 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：arXiv:2512.13762
第 2 組「agents.md rules autonomy」：1 個名字，新的 1 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：dep/agent-rules
第 3 組「over-refusal capability」：0 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 4 組「AI agent 說做不到 叫我手動」：0 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
第 5 組「default to action agentic eagerness」：7 個名字，新的 7 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：arXiv:2610.24194, arXiv:2604.08588, anthropic-claude-prompting-best-practices, openai-gpt5-prompting-guide, google-aistudio-prompting-strategies, google-cloud-engineer-agentic-prompts, claude-code-best-practices
第 6 組「unsolvable task detection llm agent」：8 個名字，新的 8 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：arXiv:2606.28733, arXiv:2605.28532, arXiv:2512.01661, arXiv:2406.20015, arXiv:2510.20270, arXiv:2607.10059, arXiv:2506.09038, arXiv:2607.28815
第 7 組「claude.md cursorrules agent rules」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related, producthunt
  新：PatrickJS/awesome-cursorrules, netdata/netdata, x1xhlol/system-prompts-and-models-of-ai-tools, jason-m-d/crosby, balqaasem/awesome-windsurfrules, jhonma82/awesome-clinerules, project-translation/awesome-cursorrules, luongnv89/agents-dot-md, iagomsouza/awesome-cursorrules, obstr/awesome-cursorrules, ghuntley/awesome-cursorrules, jfontestad/ai-awesome-cursorrules, surefirestudios/awesome-cursorrules, stacklok/prompt-library, claire-gong-18/awesome-cursorrules, shareai-lab/share-best-prompt, wesleymaik/system-prompts-and-models-of-ai-tools, hussainasghar/system-prompts-and-models-of-ai-tools, deonna/system-prompts-and-models-of-ai-tools, iamunbounded/ai-tools, yours-flow/leaked-prompts, tasmay-tibrewal/system-prompts-and-models-of-ai-tools, anxkhn/system-prompts-and-models-of-ai-tools, kiliczsh/system-prompts-and-models-of-ai-tools, harshyadav152/prompts-g-es-by-x1xhlol
  ★1000 以上的新名字：PatrickJS/awesome-cursorrules, netdata/netdata, x1xhlol/system-prompts-and-models-of-ai-tools
第 8 組「latest documentation training data cutoff agent rules」：1 個名字，新的 1 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：aws-agentic-ai-lens-agentrel05
第 9 組「feasibility awareness agentic abstention」：6 個名字，新的 6 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：arXiv:2610.06563, arXiv:2610.19226, facebookresearch/AbstentionBench, LeonChengg/FeasiGen, knowledge-verse-ai/LLM-Self_Knowledge_Eval, arXiv:2606.20661
第 10 組「coding agent laziness verify before claiming」：0 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
```

### 3. 本次調研挑過的關鍵字擴展脈絡
1. 起手：`llm agent learned helplessness` → 擴展出 `learned incapacity`、`functional refusal`、`unsolvable`
2. 起手：`agents.md rules autonomy` → 擴展出 `claude.md`、`cursorrules`、`no laziness`
3. 起手一般說法：`over-refusal capability` → 驗證 `over-refusal` 偏安全誤拒，轉向 `unsolvable task detection`
4. 中文起手：`AI agent 說做不到 叫我手動` → 補充台灣／簡中社群關鍵詞
5. 擴展：`default to action agentic eagerness` → 由官方指南用語切入
6. 擴展：`unsolvable task detection llm agent` → 撈出 `Feasibility Awareness`、`Agentic Abstention`、`Solvability Boundary`
7. 擴展：`claude.md cursorrules agent rules` → 撈出高星規則集、system prompt 庫與 `related`、`producthunt`
8. 擴展：`latest documentation training data cutoff agent rules` → 切入訓練資料截止日期與即時查證規範
9. 擴展：`feasibility awareness agentic abstention` → 補齊 HERA、Agentic Self-Awareness、KAPRO、AbstentionBench
10. 擴展：`coding agent laziness verify before claiming` → 驗證 `verification-before-completion` 屬正面驗證、確認 ★1,000 以上清單收斂
