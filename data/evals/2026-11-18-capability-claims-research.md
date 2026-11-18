# agent 把做得到的事說成「做不到」：調研與 OmniKit 的對策

調研日期：2026-11-18
執行：主控 Claude Opus 5.5 查官方一手來源、本機實測與上游原始碼；兩條飽和式調研（`omnikit-research` 流程）派給 Gemini 4 Hydrogen（high，agy_cli 管道），主控驗收帳本 `status` 並抽查。
子題與帳本：R1「讓 agent 知道這台有哪些工具」、R2「agent 說做不到／把手動步驟丟給使用者」，各一本帳本，原檔在 `2026-11-18-capability-claims-research/`。

## 1. 結論

- **這類問題叫什麼**：研究上屬於可行性判斷（feasibility awareness）、代理棄權（agentic abstention）的反方向，也就是做得到卻判成做不到；也有人叫 learned incapacity。over-refusal 指的是安全誤拒，不是同一件事。論文顯示只往一個方向推（只叫它多做或多停）會傷到另一邊，有效的是「宣稱要附證據」與改 harness。
- **官方三家都有對應的建議**：Anthropic 說沒看過的 CLI 指給它看 `--help` 就夠、用工具查不要猜、沒查過不下斷言；OpenAI 說不要因為不確定就交回使用者、能自己找到答案就不找使用者；Google 說能用工具就不要先問使用者、沒查過不要假設不適用。
- **讓 agent 知道環境裡有什麼**：業界用 tool search、漸進式揭露、開局注入（Claude Code 的 SessionStart hook、Gemini CLI 的 `tools.discoveryCommand`）、掃 MCP 設定的工具（`fastmcp discover`）。沒有現成工具處理「Windows 多個 shell、多個 agent、本機 MCP 端點要不要登入」，所以 OmniKit 自己寫了一支清點腳本。
- **這次案例的根因要修正一處**：Git Bash 的 PATH 其實有 `~/.t3/bin`，找不到 `t3` 是因為只有 `t3.cmd`，Bash 不會自動補 `.cmd`。T3 的 MCP 確實能帶思考程度、能 settle（上游原始碼佐證，本機未實測）；Claude Code 已登記 T3 的 MCP，只差使用者核准一次登入。
- **規則漏洞**：原本的「說不確定之前先查」用內在感受當觸發條件，agent 很確定地說做不到時就不會觸發。新規則改用句子本身當觸發條件：要寫出「做不到、沒有工具、要你手動做、還不能」之前，先查完。
- **寫進 OmniKit 的**：安全底線新增〈說做不到之前〉（規則版本 2026-11-18-3）、新的 `omnikit-capabilities` skill 與 `capabilities.py`、分派規則的 T3 說法修正、ryan 規則補洞、問法庫第 73 條。最值得接著做的是用 Stop hook 強制，以及前後對照實測（第 7 節）。

## 2. 這次的案例與根因（2026-11-18 重查）

| # | 現象 | 根因 | 一手證據 |
|---|---|---|---|
| 1 | 好幾週，Claude Code 桌面版與 Codex 回答「這裡沒有 T3 工具，沒辦法派」 | 規則只寫了 T3 對話內的 MCP 工具（delegate_task），沒寫 CLI 這條路；agent 只看自己的工具清單就下結論 | commit `4e6a90a` 已補上 `t3_cli` 管道 |
| 2 | Git Bash 的 `command -v t3` 回 not found，agent 判成沒裝 | **修正原本的說法**：Git Bash 的 PATH 其實有 `~/.t3/bin`。真正的原因是那裡只有 `t3.cmd`，Bash 只會自動補 `.exe`，不會補 `.cmd`；npm 裝的 `codex` 另外放了沒有副檔名的 sh 腳本，所以 Bash 找得到 `codex`、找不到 `t3` | 2026-11-18 在 Git Bash 實測：`echo $PATH` 有 `/c/Users/user/.t3/bin`；`command -v t3` 找不到，`command -v t3.cmd` 找得到，`t3.cmd --version` 印 `t3 v0.1.10`；`~/AppData/Roaming/npm` 有 `codex`、`codex.cmd`、`codex.ps1` 三個 |
| 3 | 修正後又回報「v0.1.10 不能設思考程度、不能結案」，把接 T3 MCP 這條路寫在「沒實測」底下，標題卻是「還不能」 | 把「CLI 這個介面沒有」寫成「這件事做不到」；省事的做法放在限制後面 | 上游原始碼（main，2026-11-18 用 gh api 讀）：`t3_thread_launch` 的 `modelSelection` 有 `options`（`packages/contracts/src/modelSelection.ts`），可以帶思考程度；`t3_thread_organize` 有 `settle`（`apps/server/src/mcp/toolkits/thread/tools.ts`），外部 agent 可用（`scripts/scenarios/archive-lists-thread-archived-elsewhere.e2e.ts` 就是用外部 agent 的身分呼叫）。官方文件 `docs/user/outside-agents.md` 寫了 Claude Code 與 Codex 怎麼接。本機端點 `http://127.0.0.1:3773/mcp` 開著，GET 回 401 並附 OAuth 的 `resource_metadata`；Claude Code 的設定檔已登記 `t3`，`claude mcp list` 顯示 `Needs authentication`（只差 `claude mcp login t3`） |
| 4 | 使用者規則已有「說不確定之前先上網搜尋」「能自動完成的步驟就自己做」，還是一樣 | 規則用「不確定」這種內在感受當觸發條件；agent 說做不到時語氣很確定，所以沒觸發 | 規則原文（`data/profiles/ryan/AGENTS.md` 查證與完成第 1 條） |

原本規則裡另一個錯：`dispatch-policy.md` 的 t3_cli 把「v0.1.10 不能設思考程度、不能結案」寫在前面，接 MCP 這條路放在最後的【待驗證】裡。這次改成先寫接 MCP 的做法（標「可以這樣做，未實測」），CLI 的限制放後面。

## 3. 官方一手指南（2026-11-18 讀原文）

以下是轉述，附來源；原文在網址。

### Anthropic
- **Claude Code 最佳實踐**（https://code.claude.com/docs/en/best-practices ，〈Tell Claude what it can't see〉）：外部系統有 CLI 時通常是最省事的接法；遇到沒看過的 CLI，指給它看 `--help` 就夠了。沒有 CLI 的才用 MCP。規則檔只寫 agent 自己找不到、或每次都要重新挖的資訊。
- 同一頁：規則檔裡的某一行一直被忽略時，加 IMPORTANT 通常沒用；要嘛檔案太長、那行被淹沒，要嘛它是不能有例外的規則，該改成 hook。「不要偷懶、一直做到完」這類句子對現在的模型比較可能造成做過頭，給它一個可以跑的檢查才有用。
- **Prompting best practices**（https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices）：`<default_to_action>` 範例要模型預設直接動手，缺的細節用工具去查，不要用猜的；`<investigate_before_answering>` 範例要模型沒查過就不要對程式碼下任何斷言。同一頁也提醒：新模型對系統提示更敏感，用 CRITICAL、MUST 這類強烈字眼容易觸發過度，用平常的語氣寫就好。

### OpenAI
- **GPT-5 prompting guide**（https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide ，〈Controlling agentic eagerness〉）：`<persistence>` 範例要 agent 遇到不確定時不要停下來交回給使用者，自己研究或推出最合理的做法繼續，事後再說明假設；並建議明確定義什麼情況才可以交回給使用者。
- 同一份指南收錄 Cursor 的系統提示調整：能自己找到答案的，就不要找使用者幫忙；幾乎不要問使用者要不要照計畫進行。
- 同一份指南的 Tau-bench 範例：對使用者要求的資訊不確定時，用工具讀檔，不要猜。

### Google
- **Gemini 提示策略**（https://aistudio.google.com/docs/prompting-strategies ，agentic 的系統指令範例）：能用手上的資訊呼叫工具的，就不要先問使用者；沒查過不要假設某件事不適用；不要放棄，直到推理都用盡；錯誤時換策略或參數，不要重複同一個失敗的呼叫；提到規則或政策時引用原文來佐證。
- 同一頁提醒：模型有知識截止日，要照提供的現在日期去查最新資訊。

### T3 Code（這次案例的工具）
- `docs/user/outside-agents.md`（pingdotgg/t3code main，2026-11-18 用 gh api 讀）：T3 以外的 agent（自己終端機裡的 Claude Code、Codex）可以透過環境的 MCP 端點讀專案與對話、開對話、傳訊息；Claude Code 用 `claude mcp add --transport http t3 <位址>/mcp` 再 `claude mcp login t3`，Codex 用 `codex mcp add t3 --url ...` 再 `codex mcp login t3`；外部 agent 不能用 `delegate_task`，要用 `t3_thread_launch`。

## 4. 業界與研究怎麼稱呼、怎麼解決（R2）

完整報告：`2026-11-18-capability-claims-research/R2-report.md`。停在第 10 組，照 ★1,000 停法停，屬於**長尾未飽和**（49 個名字，最後連續沒有新名字只有 1 組）。這一題的名字多半是論文與官方指南，沒有星數，★ 停法對它比較寬鬆，所以論文清單不保證找齊。主控核對：10 篇論文的 arXiv 編號與標題都存在（arXiv API，2026-11-18），報告引用的數字都出現在各篇摘要裡；5 個規則集 repo 的星數與授權一致；netdata 的規則原文與台灣教學文章都讀過。

**怎麼稱呼。** 研究上把「其實做得到卻判成做不到」放在可行性判斷（feasibility awareness）與代理棄權（agentic abstention）這一類，是「該停沒停」的反方向（false infeasibility）：
- Learned Incapacity：RLHF 對齊過的模型在特定情境反覆用「功能性拒絕」不做事，並自己編理由（arXiv:2512.13762）。
- Feasibility Awareness：工具型 agent 能不能判斷環境裡到底有沒有需要的工具；既有 benchmark 只算做對多少，沒算可行性誤判（arXiv:2605.28532）。
- Agentic Abstention、AgentAbstain、Agentic Self-Awareness：在多輪工具環境量「知道、行動、被質疑時堅持」三者是否一致；用成對的可行與受阻任務測（arXiv:2606.28733、2607.10059、2610.19226）。
- Knowing-Acting Gap：知道能不能做，跟實際有沒有去做，常常對不上（arXiv:2606.20661）。另有 Solvability Boundary（arXiv:2512.01661）、ToolBeHonest（arXiv:2406.20015）。
- 注意：over-refusal、false refusal、exaggerated refusal（OR-Bench、XSTest 等）指的是**安全誤拒**（把無害的請求當成有害），不是低報自己的能力，不能直接套用。
- 工程社群的說法：agent laziness、premature refusal、把手動步驟丟給使用者、knowledge cutoff 造成的「這功能不存在」。

**被驗證有效的做法（論文數字，主控只核對摘要）。**
- 單向調整會傷另一邊：arXiv:2610.19226 發現模型辨識出障礙的比例有 84.4%，但三者都一致的只有 40.6%；只篩「更會停」會壓低可行任務的成功率。所以規則不能寫成「不准說做不到」，要寫成「說做不到也要附證據」。
- 改 harness 不改模型就有效：HERA 自動配對可行與受阻的環境變體，棄權準確率 61.7% 到 83.3%，可行任務完成率也從 68.3% 升到 76.7%（arXiv:2610.06563）；CONVOLVE 從過去的軌跡蒸餾出規則放進 context，及時棄權的召回率 26.7 到 57.4（arXiv:2606.28733）。
- 證據閘門：ECLoop 在 agent 與 repo 之間加一層，沒觀測到指定證據就不准做對應的宣稱或修改，用來防過早定案（arXiv:2607.28815）。這對應到 OmniKit 下一步的 Stop hook。
- 訓練面：UnsolvableRL 用可解與不可解成對的資料，不可解偵測 85% 以上，可解題準確率 43.4% 到 69.4%（arXiv:2512.01661）。OmniKit 用不到訓練，只參考它「成對看兩個方向」的原則。

**規則集怎麼寫（GitHub，星數 2026-11-18 gh api）。**
- obra/superpowers ★319,549（MIT）的 `verification-before-completion`：說「完成」之前要有新跑的驗證輸出。它管的是正面宣稱；這次補的是對稱的反面：說「做不到」之前也要有查證。
- netdata/netdata ★81,463（GPL-3.0）的 `AGENTS.md`：問使用者或要他做決定之前先把功課做完；有疑慮先查（Default on doubt）。
- PatrickJS/awesome-cursorrules ★41,167（CC0-1.0）的反諂媚規則：用函式庫前先確認它真的存在、沒有證據不背書、不確定就明說。
- dep/agent-rules ★11（MIT）：不要向使用者討協助，直接看 log 與錯誤自己解決。
- 中文社群：小高工具間第 3 課〈能叫它做的，就別自己動手〉給的三條規則（先自己試、只叫使用者做卡住的那一步；改完自己讀回來；付款、送出、刪除停在按鈕前），與這次的 baseline 幾乎一樣。就享知的文章觀察到：一句寫進記憶的「做不到」，會讓之後的任務連查都不查就停（第三方觀察，沒有一手實驗）；這點寫進了 baseline。

## 5. 讓 agent 知道環境裡有什麼的做法與工具（R1）

完整報告：`2026-11-18-capability-claims-research/R1-report.md`。停在第 8 組，照「★1,000 以上的 repo 連續 3 組沒有新的」停，屬於**長尾未飽和**：65 個名字、每組都還有新的小 repo，★1,000 以下與沒有星數的產品不保證找齊。主控抽查 5 個 repo 的星數與授權（`sweep.py verify`，2026-11-18）都一致；更正一處：fastmcp 掃描本機 MCP 設定的指令是 `fastmcp discover`（`docs/cli/client.mdx`），報告原文寫成 `fastmcp list`。

業界的說法與做法，大致分成兩類問題：

1. **工具太多塞爆 context**：tool search／延遲載入（Anthropic 的 Tool Search Tool、Claude Code 的 tool search、OpenAI 的 `tool_search` 與 `defer_loading`）、漸進式揭露（skill 只先載入名稱與說明；CLI 用 `--help` 按需看）、把 MCP 轉成 CLI（knowsuchagency/mcp2cli ★2,440、philschmid/mcp-cli ★1,285）、本機 MCP 閘道（IBM/mcp-context-forge ★4,847、mcpjungle ★1,628 等）。
2. **agent 不知道環境裡有什麼**：開局清點並注入（Claude Code 的 `SessionStart` command hook，stdout 會進 context）、Gemini CLI 的 `tools.discoveryCommand`（啟動時跑一支指令，把本機工具註冊進來；`docs/reference/tools.md`，2026-11-18 用 gh 搜原始碼確認）、掃描本機 MCP 設定的工具（PrefectHQ/fastmcp 的 `fastmcp discover` ★28,640、lirantal/ls-mcp ★84）、偵測裝了哪些 agent CLI（expo/agent-cli-detector ★5）、掃 PATH 與套件管理器（cli-ai-org/cli ★1）。

這次的問題屬於第 2 類，而且多一層 Windows 多 shell 的坑。查到的工具都只做一部分：fastmcp 與 ls-mcp 只看 MCP 設定，agent-cli-detector 只看有沒有裝 agent，沒有一個會比對「PowerShell 找得到、Git Bash 找不到」或探測本機 MCP 端點要不要登入。所以 OmniKit 自己寫一支小的清點腳本（第 6 節），不裝第三方工具。

跨 shell 的坑（R1 第六節，主控用這台實測補強）：
- PowerShell 照 PATHEXT 補副檔名，還認 `.ps1`；cmd 照 PATHEXT；Git Bash 只補 `.exe`，所以只有 `.cmd` 的指令（`t3.cmd`）要打完整檔名；WSL 呼叫 Windows 程式要帶 `.exe`。
- 寫在 PowerShell `$PROFILE` 裡的 PATH，Git Bash、cmd、以 `-NoProfile` 啟動的 PowerShell 都看不到（Gemini CLI 在 Windows 用 `powershell.exe -NoProfile`，`docs/tools/shell.md`）。
- 裝好之後才加進 PATH 的指令，已經開著的程式（含 agent 的 app）拿不到，要看登錄檔的 PATH 或用完整路徑。

## 6. 寫進 OmniKit 的對策

| 對策 | 依據 | 放在哪 |
|---|---|---|
| 把「做不到、沒有工具、沒辦法、要你手動做、還不能」本身當成觸發條件，跟「不確定」一樣先查 | 案例 4：用內在感受當觸發會漏；Anthropic「沒查過不下斷言」、Google「沒查過不要假設不適用」 | `data/rules/baseline.md`〈說做不到之前〉第 1 條（所有人） |
| 說做不到之前的檢查清單：能力清點、`--help`、最新官方文件或原始碼、其他接法 | Anthropic「沒看過的 CLI 指給它看 --help」「用工具查，不要猜」；OpenAI Cursor 範例「能自己找到答案就不找使用者」；案例 1、2、3 | baseline 第 2 條；做法在新的 `omnikit-capabilities` skill |
| 回答先給最省事、能直接做的路；能做但沒實測寫「可以這樣做（未實測）」，不寫「還不能」 | 案例 3 | baseline 第 3 條 |
| 記憶、交接檔、舊回報裡的「做不到」只當線索，重查才沿用；寫進去要附查證日期 | 就享知的觀察（R2）：一句寫進記憶的做不到會讓之後連查都不查；這台多個 agent 共用記憶與交接檔 | baseline 第 4 條 |
| 要使用者親手做的只限非他不可的步驟，一次講清楚 | OpenAI「明確定義何時交回使用者」；netdata 的 AGENTS.md「先做完功課再問」；使用者 profile 原有的「能自動完成的步驟就自己做」 | baseline 第 5 條 |
| 說做不到也要附證據，不寫成「不准說做不到」 | arXiv:2610.19226：只往一個方向推會傷另一邊；obra/superpowers 的完成前驗證是同一種閘門的正面版 | baseline 第 1、2、5 條的寫法 |
| 能力清點腳本：列出各種 shell 找法下的 CLI（標出 Bash 找不到的 .cmd）、各 agent 登記的 MCP、本機 MCP 端點的狀態與怎麼接 | 案例 1、2、3；Anthropic「只寫 agent 找不到的資訊」：讓它自己查得到，比寫死在規則裡好 | `engine/scripts/capabilities.py`、`engine/skills/omnikit-capabilities/` |
| 修正分派規則裡錯的根因說法（「Git Bash 的 PATH 沒有 t3」），把 T3 MCP 這條可行的路放到 t3_cli 的思考程度與結案說明最前面 | 案例 2、3 | `data/rules/dispatch.md`、`dispatch-policy.md`、`omnikit-dispatch` skill |
| ryan 的「說不確定之前先上網搜尋」補上「說做不到也算不確定」，並寫明這台裝了哪幾個 agent | 案例 4 | `data/profiles/ryan/AGENTS.md` |

寫法照官方對新模型的建議：講原因、不加 IMPORTANT 或全大寫；觸發條件寫成看得見的句子（要寫出「做不到」之前），不寫「要更努力」這類口號。

## 7. 沒做、列為下一步

1. **用 hook 強制（Claude Code 與 Codex 的 Stop hook）**：官方說不能有例外的規則要改成 hook。可以做一支 Stop hook：最後的回覆出現「做不到、沒有工具、請你手動」這類句子，卻沒有附查證（清點、`--help`、文件網址）時，擋回去要 agent 先查。要先量誤判率（例如真的做不到、或只是在轉述別人說做不到），所以另開一條做。（2026-11-18 已做：`engine/scripts/claim_check.py`，誤判率見 [2026-11-18-claim-check-hook.md](2026-11-18-claim-check-hook.md)）
2. **前後對照實測**：用這次的 T3 案例當題目（例如「把這個任務派給 T3 的 antigravity_kai，用 gemini-3.8-flash」），在 Claude Code、Codex、Antigravity 各跑幾次，比較新規則上線前後還會不會說做不到；照 `omnikit-ask` 的叫用測試做法。
3. **登入 T3 的 MCP 並實測**：Claude Code 已登記 t3，只差使用者跑一次 `claude mcp login t3`；Codex 要先 `codex mcp add t3 --url http://127.0.0.1:3773/mcp` 再登入。登入之後實測 `t3_thread_launch` 帶思考程度與 `t3_thread_organize` settle，把分派政策裡的「未實測」改掉。
4. **開局注入**：Claude Code 的 `SessionStart` command hook 與 Gemini CLI 的 `tools.discoveryCommand` 都能在開局把清點結果放進 context。這次沒做：每次開局都要多付幾百字的成本，先看規則加 skill 夠不夠（第 2 項的結果）。
5. **問法庫的說明文字**：`omnikit-ask` 新增了第 73 個情境，但 skill 的說明文字（決定會不會被叫用）沒改，叫用測試也沒做。

## 8. 待驗證

- 這台 T3（v0.1.10）的 `t3_thread_launch` 能用 `modelSelection.options` 帶思考程度：只有上游 main 的原始碼佐證，沒實測。
- 外部 agent 呼叫 `t3_thread_organize` settle：上游原始碼與 e2e 情境佐證，這台沒實測（要先登入 T3 的 MCP）。
- Codex 的 `codex mcp add` 與 `codex mcp login` 接 T3：只照官方文件，沒實測。
- 新規則能不能讓 agent 不再誤說做不到：沒做前後對照（第 7 節第 2 項）。
- 論文的數字：主控核對了各篇摘要裡有這些數字，沒讀全文、沒重現。
- 第三方工具的效果數字（mcptoon 省 99% 的 schema token、mcp2cli 省 96% 到 99% 等）：作者自述。
- AWS Well-Architected Agentic AI Lens 的 AGENTREL05-BP03、Google Cloud 的 engineer-agentic-prompts 頁、Phil Schmid 的 Gemini 3 文章（個人部落格，不是 Google 官方文件）：R2 讀的原文，主控沒重讀。
- 就享知「一句做不到會污染之後的任務」：第三方文章的觀察，沒有一手實驗。

## 附錄：飽和調研的 `status` 輸出與管道狀況

兩條都照 `sweep.py status --min-stars 1000` 印「可以停」才停，屬於長尾未飽和：★1,000 以上的 GitHub repo 連續 3 組沒有新的，但全部名字還沒有連續 3 組沒有新的。★1,000 以下與沒有星數的名字（論文、產品）不保證找齊。兩條都查了 8 個腳本管道（GitHub topic、GitHub 關鍵字、awesome、skills.sh、npm、官方 MCP Registry、Hacker News、Exa），每組加網頁搜尋，整次有中文（web-zh）、Product Hunt 與 related。沒有連不上、限速或缺金鑰；中文那一組 skills.sh 與 MCP Registry 因為沒有英文關鍵字而照腳本規則跳過。

### R1（停在第 8 組，第 6、7、8 組沒有 ★1,000 以上的新名字）

```text
總共 65 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 3 組沒有新的（要 3 組）：可以停，報告寫「長尾未飽和」並附上面兩種連續數
第 1 組「agent tool discovery」：15 個名字，新的 15 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ibm/mcp-context-forge, agentic-community/mcp-gateway-registry, xfey/mcp-zero, neuronto/agentic-resource-discovery, usefulsoftwareco/executor, mcpjungle/mcpjungle, btsouth/toolport, tuckerschreiber/need, EnactProtocol/encat-spec-and-tools, openai-tool-search, anthropic-tool-search-tool, claude-code-tool-search, DunkelCloud/ToolMesh, TheLunarCompany/lunar, obot-platform/obot
  ★1000 以上的新名字：ibm/mcp-context-forge, agentic-community/mcp-gateway-registry, usefulsoftwareco/executor, mcpjungle/mcpjungle, obot-platform/obot
第 2 組「mcp server discovery local」：13 個名字，新的 12 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：cli-use, activeing123/mcptoon, lirantal/ls-mcp, cubicecho/mcp-discovery, kuldeep-poonia/mcpscan, PrefectHQ/fastmcp, mcp-shark/lazy-tool, abdullah1854/MCPGateway, voicetreelab/lazy-mcp, keybrdist/opencode-lazy-loader, knowsuchagency/mcp2cli, philschmid/mcp-cli
  ★1000 以上的新名字：PrefectHQ/fastmcp, knowsuchagency/mcp2cli, philschmid/mcp-cli
第 3 組「command line tools inventory」：5 個名字，新的 5 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：cli-ai-org/cli, Yaemikoreal/CliLoci, clihub-ai/clihub, syshin0116/clidex, thellimist/clihub
第 4 組「agent 工具 自動 探索 本機 指令」：4 個名字，新的 2 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：linxule/opencli, claude-code-sessionstart-hook
第 5 組「dynamic tool loading」：12 個名字，新的 12 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt
  新：ChandraMohanBusam/mcp-dynamic-tool-loader, asadani/tool-attention, asyrjasalo/dynamic-mcp, mizchi/mcp-reloader, spring-ai-community/spring-ai-tool-search-tool, yulimfish/opencode-tool-search, openrouter-tool-search, kimi-dynamic-tool-loading, morphllm-dynamic-tool-loading, Scalekit, Klavis-AI/klavis, AgentKey
  ★1000 以上的新名字：Klavis-AI/klavis
第 6 組「sessionstart hook environment tools」：4 個名字，新的 1 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related
  新：Alpha-Oi/cc-skill-router
第 7 組「progressive disclosure cli mcp」：9 個名字，新的 9 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：everclear077/dsh-progressive-tools, labmimors/dsh-mcp-lens, runkids/agents-context-router, brunogama/mcp-cli-wrappers, codyaverett/mcp-cli, brunogama/claude-mcp-wrapper, Consiliency/pmcp, nvidia-nemoclaw-progressive-tool-disclosure, anthropic-agent-skills
第 8 組「capability discovery agent cli」：9 個名字，新的 9 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：cordsjon/a2a-cli-registry, 444136347/dsh-capability-discovery, adaptive-interfaces/adaptive-tool-discovery, Rosh1106/WhatTheAgent, expo/agent-cli-detector, SenteLabsAI/extensible-mcp, Magic-Man-us/claude-code-capabilities, gushuaialan1/od-cli-scanner, alpibrusl/acli
```

### R2（停在第 10 組，第 8、9、10 組沒有 ★1,000 以上的新名字）

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
