# 業界與開源怎麼管理「同一人的多個 AI 訂閱帳號」給 coding agent 用（調研 A1）

查證日期 2026-11-23。唯讀調研，未安裝、未登入任何服務。帳本：`C:\Users\user\AppData\Local\Temp\omnikit-research\account-pool-A1-ledger.json`。
停法：**12 組跑完仍未飽和，依規定停下來回報現況**（見第六節），不是照飽和或長尾停。

## 摘要

1. 業界做法分三層：帳號隔離（每帳號一個設定資料夾）、狀態與選帳號（額度、冷卻、策略）、對外代理（把訂閱登入包成 API 端點）。第三層（CLIProxyAPI、9Router、ccflare、TeamClaude、cligate 等）最熱門，也最靠近各家條款的紅線。
2. 帳號隔離，Anthropic 官方文件明文支援：`CLAUDE_CONFIG_DIR`，「每個目錄有自己的設定、對話紀錄、claude.ai 登入」（用途寫的是工作與個人帳號）。Codex 的 `CODEX_HOME` 做法同理，但這次只找到第三方教學，沒找到 OpenAI 官方明文（待驗證）。
3. 選帳號策略各工具用語不同，但骨架一致：sticky（session 親和）+ 額度門檻預先換 + 429 才換。Hermes Agent 的官方文件把策略命名為 `fill_first`、`round_robin`、`least_used`、`random`，並把 429、402、401 分別處理，是最清楚的一份。
4. 「要分清楚額度用完的 429」與「每分鐘速率 429」：TeamClaude 只在額度桶用完時換帳號，速率限制則原帳號慢下來，理由是換帳號會丟掉熱快取、只是把突發流量搬到下一個帳號（README 原文）。
5. 額度來源：Claude 靠回應標頭 `anthropic-ratelimit-unified-*`（TeamClaude README）或 OAuth 用量端點（claude-swap、CodexBar）；Codex 靠 `account/rateLimits/read`（codex-switch，第三方說法，待驗證）；Google 靠 `retrieveUserQuotaSummary`（T3 已在用）。
6. **規約是這題的決定性因素。** Anthropic、OpenAI、Google 三家一手文字都禁止分享帳號憑證，Anthropic 與 Google 另有明文限制自動化與第三方包裝；Google 對「自動輪換」明寫不支援。Anthropic 與 OpenAI 對「同一人多個付費訂閱」沒有找到明文允許或禁止（待驗證）。
7. 沒有任何工具在做「自動探測每個帳號能用哪些模型與思考程度」。這是缺口，OmniKit 已有 T3 `orchestrator_capabilities` 加 30/30 實測，可以自己做。
8. 帳號與政策寫成資料的成熟做法：OpenClaw 把「設定（auth.order，只有 metadata）」與「秘密與執行期狀態（SQLite）」分開；TeamClaude 把「手改設定」與「觀察到的額度狀態（可刪）」分兩個檔。OmniKit 該照這個分法。
9. 建議必做 6 項、選配 4 項、不建議 3 項，見第四節。

## 一、工具比較表

星數與授權為 2026-11-23 `sweep.py verify`（gh api）實測。「README」表示只有該專案自己的說法，沒有獨立驗證。

| 工具（★、授權） | 類型 | 1 接入與隔離 | 2 健康與額度 | 3 選帳號與接手 | 4 規約態度 | 5 可觀測 | 6 設定資料 |
|---|---|---|---|---|---|---|---|
| realiti4/claude-swap（★4,908、MIT） | Claude 帳號切換器 | `cswap add` 登入後存入 slot；`cswap run N` 以 session 模式同時跑多帳號 | `cswap list` 顯示每帳號 5h、7d 用量與重置；死 token 帳號隔離（quarantine）並報告 | `best`、`next-available`、`weekly-first`、`consume-first`、`priority-consume-first`；門檻預設 90%，每帳號可覆寫；冷卻預設 5 分鐘加遲滯，防來回跳 | README 警告：不要先 `/logout`，會讓被離開帳號的 refresh token 失效；未談條款 | TUI 儀表板 | `cswap config set autoswitch.threshold`；`cswap priority`、`cswap threshold` |
| KarpelesLab/teamclaude（★527、MIT） | Claude／Codex 多帳號代理 | 設定檔 `~/.config/teamclaude.json`（可手改），狀態檔 `teamclaude.state.json`（可刪，額度重新學） | 讀 `anthropic-ratelimit-unified-*` 標頭得 5h／7d；每模型週額度分開算；區分「額度 429」與「速率 429」 | 門檻 98% 換、偏好週額度最早重置者；全部用完可 `holdSeconds` 等重置；選配 `allowExtraUsage` 用付費額外用量 | README 未談條款（待驗證） | TUI 額度條與重置倒數；選配 MCP 讓 agent 讀額度 | JSON 設定，proxy API key 首次自動產生 |
| tombii/better-ccflare（★283、MIT）、snipeship/ccflare（★1,054、MIT，最後 push 2026-04-19） | Claude OAuth 多帳號代理 | `--add-account … --mode claude-oauth --priority 0` | OAuth token 健康監控、到期前 30 分鐘自動刷新；偵測重置後自動回高優先帳號 | 預設 `LB_STRATEGY=session`（5 小時視窗對齊，為了 prompt cache）；O(1) 優先序選取；每帳號月用量上限 | README 未談條款（待驗證） | Web 儀表板、請求層級分析 | 環境變數加 SQLite |
| router-for-me/CLIProxyAPI（★59,258、MIT） | 把 CLI 登入包成 API 端點 | 各 CLI OAuth 登入 | 本體只列「多帳號 round-robin」；額度由周邊工具（Quotio、各種 tray、status line）經 Management API 讀 | round-robin | README 未談；周邊生態有「account-risk guide」（待驗證） | 周邊工具極多（見 README 清單） | YAML 設定（待驗證） |
| decolua/9router（★32,752、MIT） | 路由與額度追蹤 | Web 儀表板登入 | 「Real-Time Quota Tracking」；額度或錯誤即切換 | per-provider round-robin 或優先序；三層降級：訂閱、便宜、免費 | README 未談（先前報告：未見 ToS 排除表） | 儀表板 | 儀表板設定 |
| cheaper-inference/OmniRoute（★89,646、MIT） | 閘道 | 數百供應商 | 偵測 429 自動 cascade | 付費帳號、API key、低價、免費；**`FREE_TIER_TOS` 規約表（`ok／caution／ambiguous／avoid／unknown`）把 agy 等標 avoid 並預設不自動路由**（先前報告 `2026-11-22-multi-user-model-roles-research.md` 已讀原始碼，本次未重驗） | 唯一把規約做成資料的 | 儀表板 | 規約欄位獨立於模型目錄 |
| NousResearch/hermes-agent（★265,461、MIT）credential pools | agent 內建帳號池（官方文件） | `hermes auth` 互動精靈，新增、移除、重設冷卻 | 429：同 key 重試一次，第二次換，冷卻 1 小時；402 立刻換，冷卻 1 小時；401 先刷新 token，失敗才換，冷卻 5 分鐘；「該模型不支援 ChatGPT 帳號」只對該 key 的該模型停用 | `round_robin`、`least_used`、`fill_first`（依 priority）、`random`；全部耗盡才走 `fallback_model`（不同供應商） | 文件未談條款 | `hermes auth` 顯示池狀態 | 池與策略寫在設定檔 |
| openclaw/openclaw（★395,066、MIT）auth profiles | agent 內建（官方文件） | profile id 形如 `openai:<email>`；`openclaw models auth order set` | 速率限制只在供應商明講時才冷卻；其餘冷卻 30 秒、1 分鐘、5 分鐘（上限）；計費或永久授權錯誤整個 profile 停用 | 兩段式：先同供應商換 profile，再換模型 fallback；順序：覆寫、設定、OAuth 先於 API key、最久沒用者先；**session 釘選（cache 友善）**，使用者釘選的 profile 失敗時不換 profile 而換模型 | 官方文件未談；2026-02 Google 曾切斷 OpenClaw 經 Antigravity OAuth（VentureBeat、The Register，先前報告） | 狀態指令；佇列等待時顯示「Waiting for rate limit」並對恢復請求加 100 到 250 ms 抖動 | `auth.profiles`／`auth.order` 只放 metadata，秘密在 per-agent SQLite |
| BerriAI/litellm（★63,724、NOASSERTION） | 通用 LLM 路由 | 以 `model_list` 多個 deployment | `allowed_fails` 加 `cooldown_time` | `simple-shuffle`（預設、可加權）、`least-busy`、`usage-based`（tpm／rpm）、`latency-based`、`order`（優先層）、fallbacks | API key 型，無訂閱條款議題 | 虛擬 key、預算、支出追蹤 | YAML |
| kaitranntt/ccs（★2,907、MIT） | 設定與帳號切換 | 多個 Claude 訂閱的隔離帳號環境 | CCS Bar 顯示訂閱額度與當日花費 | 原生提供 round-robin 與 fill-first（README） | README 未談 | 選單列、儀表板 | 設定檔 |
| farion1231/cc-switch（★156,432、MIT） | 設定管理（不是路由） | 管理 Claude Code、Codex、Gemini CLI 設定 | 無 | 無（第三方比較文：不做帳號池，待驗證） | — | — | — |
| musistudio/claude-code-router（★38,323、MIT） | 依任務分流到不同模型 | 本地 proxy | 規則式 fallback | 依 background、think、longContext 分流 | API key 型 | 無 | JSON |
| Soju06/codex-lb（★3,454、MIT） | Codex 帳號池 | ChatGPT 帳號登入 | 池狀態、額度餘量、重置額度；周邊有 macOS、Linux、Home Assistant 監看 | 負載平衡（細節待讀） | README 未談 | 周邊最多（SwiftBar、tray、桌面通知） | — |
| christiandoxa/prodex（★61、Apache-2.0）、xhyqaq/codex-auto（★60、MIT） | Codex 包裝 | 每 profile 獨立 `CODEX_HOME`（prodex，docs.rs 說法） | prodex 內建額度檢查；codex-auto 靠終端輸出的失敗字串偵測，輪替只看本地順序、無權重或健康檢查（第三方分析，待驗證） | 自動輪替 | — | — | — |
| steipete/CodexBar（★23,287、MIT）、tddworks/ClaudeBar（★1,590、Apache-2.0）、aqua5230/usage（★356、AGPL-3.0）、f-is-h/Usage4Claude（★422、MIT） | 額度顯示（選單列） | 讀各 CLI 登入或本機檔案 | 5h、7d、重置時間 | 無（純顯示） | 純讀取，風險最低 | 選單列 | — |
| jlcodes99/cockpit-tools（★20,293、授權無）、lbjlaq/Antigravity-Manager（★33,691、NOASSERTION）、Draculabo/AntigravityManager（★2,565、NOASSERTION） | 多帳號管理桌面程式（含 Antigravity） | 帳號管理、一鍵切換 | 額度視圖 | cockpit-tools 稱 round-robin | **Antigravity 自動輪換正是 Google FAQ 說不支援的用法**；這些工具的條款態度未讀（待驗證） | 桌面介面 | — |
| maximhq/bifrost（★9,954、Apache-2.0）、Portkey-AI/gateway（★13,431、MIT）、agentgateway/agentgateway（★6,361、Apache-2.0） | API 金鑰型 LLM 閘道 | 虛擬 key | 加權、failover；bifrost 的 adaptive 為付費（搜尋摘要，待驗證） | 加權分流 | API key 型，官方支援路線 | 預算與用量 | YAML／JSON |

## 二、六面向的業界做法

### 1. 新帳號接入

- **隔離單位**：每帳號一個設定資料夾。Anthropic 官方 `https://code.claude.com/docs/en/authentication`（2026-11-23）寫：「To stay signed in to multiple accounts at once, such as work and personal accounts, give each account its own configuration directory ... set the `CLAUDE_CONFIG_DIR` environment variable ... Each directory has its own settings, session history, and claude.ai login or API key.」Codex 的 `CODEX_HOME` 隔離只有第三方教學與工具（prodex、codex-profiles、clausona），OpenAI 官方沒找到對應文字（待驗證）。Gemini CLI 的 `GEMINI_HOME` 本次沒查到一手說明（待驗證）。
- **登入**：所有工具都是「呼叫官方登入流程，工具只存結果」。`cswap add`、`better-ccflare --add-account`、`hermes auth`、`openclaw models auth`，都需要人在瀏覽器完成 OAuth。**一定要人做：登入、同意畫面、Google 的 403 要求驗證（`VALIDATION_REQUIRED`，這台 2026-11-22 到 23 已實測遇到，antigravity_2 重登仍未解）、付款與方案升級。**
- **憑證搬移的風險**：claude-swap 的 README 警告目前版本的 Claude Code 可能在 `/logout` 時作廢 refresh token；這種「複製憑證到別處」的做法比「每帳號獨立資料夾」脆弱。獨立資料夾（官方做法）不會有這個問題。
- **自動探測帳號能用哪些模型與思考程度**：十二組都沒找到這種工具。接近的只有 Hermes 的「該 key 的該模型被拒就只停用那一格」（被動偵測）與 TeamClaude 的每模型週額度。OmniKit 已有 T3 `orchestrator_capabilities` 與 2026-11-23 的 30/30 煙霧測試，這部分要自己做，沒有現成可借。

### 2. 健康與額度

- **錯誤分類（Hermes 官方文件，最完整）**：429 先同 key 重試一次，第二次才換並冷卻 1 小時；方案用量上限（ChatGPT／Codex「usage limit reached」）立刻換、不重試，因為重試沒用；402 立刻換、冷卻 1 小時；401 先刷新 token，失敗才換、冷卻 5 分鐘；模型不支援某帳號只停用該帳號的該模型。
- **OpenClaw 官方文件**：速率限制冷卻只用供應商明講的時間（不自己發明），其他錯誤 30 秒、1 分鐘、5 分鐘封頂；計費與永久授權錯誤是整個 profile 停用；冷卻或停用的 profile 排到最後、依最早到期排序。
- **額度來源**：Claude 有兩條路：回應標頭 `anthropic-ratelimit-unified-*`（TeamClaude README；只在有流量時更新）與 OAuth 用量端點（claude-swap、CodexBar；可主動輪詢）。Codex：`account/rateLimits/read`（codex-switch 第三方說明，待驗證）。Google：`v1internal:retrieveUserQuotaSummary`、`fetchAvailableModels`（T3 已在用）。
- **被鎖（403 要求驗證）**：沒有工具處理。所有工具遇到都只當一般錯誤。結論：這類狀態要獨立成 `needs_human`，不重試、不輪換、通知人。
- **死 token**：claude-swap 隔離並報告，不再嘗試；better-ccflare 到期前 30 分鐘預先刷新。
- **冷卻與重試的共同點**：指數式或階梯式（OpenClaw 30 秒、1 分、5 分），上限 5 分鐘到 1 小時；遲滯與最小冷卻防來回跳（claude-swap 預設 5 分鐘）；恢復時加抖動（OpenClaw 100 到 250 ms）。

### 3. 選帳號策略

| 策略 | 誰有 | 說明 |
|---|---|---|
| sticky／session 親和 | ccflare（session，5h）、OpenClaw（auth 釘選）、magpie（`stays=session`）、TeamClaude（session spreading、pinning） | 為了 prompt cache：每次換帳號會丟掉部分快取（magpie 與 TeamClaude 文件都這樣寫） |
| fill-first／priority | Hermes `fill_first`、better-ccflare priority、CCS fill-first、claude-swap `priority-consume-first` | 先用高優先帳號直到門檻 |
| round-robin | CLIProxyAPI、9Router、Hermes、CCS、cockpit-tools | 簡單，但丟快取；magpie 文件明說輪流會損失部分提示詞快取 |
| least-used | Hermes、LiteLLM `usage-based` | 看用量 |
| 依額度加權、週額度最早重置優先 | claude-swap `weekly-first`／`consume-first`、TeamClaude、magpie「額度優先」 | 週額度到重置前沒用掉就作廢，所以先用快重置的 |
| 門檻預先換 | claude-swap 90%、TeamClaude 98% | 在撞牆前換，client 看不到 429 |
| 每帳號並行上限 | LiteLLM（tpm／rpm）、better-ccflare（月上限）、Bifrost（per-key rate limit，搜尋摘要） | 訂閱帳號型工具少見；Google 論壇 staff 建議低並行（先前報告） |

**額度用完的接手順序（共識）**：同家另一個帳號 → 另一家模型（Hermes `fallback_model`、OpenClaw model fallbacks）→ 付費 API（TeamClaude `allowExtraUsage`、9Router 三層降級）。全部用完時 TeamClaude 可選擇「掛住等重置」而不是回 429（`holdSeconds`）。

### 4. 規約與停權

**一手來源（查證 2026-11-23，自己抓頁面讀原文）：**

| 來源 | 原文重點 |
|---|---|
| Anthropic Claude Code 法務頁 `https://code.claude.com/docs/en/legal-and-compliance` | 「OAuth authentication is intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications.」「Advertised usage limits for Pro, Max, and Ultra plans assume ordinary, individual usage of Claude Code and the Agent SDK.」「Developers building products or services ... should use API key authentication through Claude Console or a supported cloud provider. Anthropic does not permit third-party developers to offer Claude.ai login ... or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users. Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens.」「Nor does it prevent an end user from signing in to the unmodified Claude Code binary with their own Claude subscription」「Anthropic reserves the right to take measures to enforce these restrictions and may do so without prior notice.」 |
| Anthropic Consumer Terms `https://www.anthropic.com/legal/consumer-terms` | 「You may not share your Account login information, Anthropic API key, or Account credentials with anyone else. You also may not make your Account available to anyone else.」禁止「Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it, to access the Services through automated or non-human means, whether through a bot, script, or otherwise.」 |
| Anthropic Claude Code 認證頁 | 多帳號用 `CLAUDE_CONFIG_DIR`（見上） |
| OpenAI Terms of Use `https://openai.com/policies/row-terms-of-use/` | 「You may not share your account credentials or make your account available to anyone else」；禁止「circumvent any rate limits or restrictions」；禁止「Automatically or programmatically extract data or Output」 |
| OpenAI Codex 說明 `https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan` | 「OpenAI Support does not reset ChatGPT or Codex usage limits ... wait until it resets or use another available option shown in your account.」；另寫模型變更「does not affect the OpenAI API or using Codex with your own API key」 |
| Google Antigravity FAQ `https://antigravity.google/docs/faq`（2026-11-23 重讀確認） | 「Antigravity CLI headless mode (agy -p) is intended for direct scripting and CI workflows. Wrapping agy inside third-party coding agents or applications, or automating account rotation, is not supported under consumer plans.」另一題：用第三方軟體（Claude Code、OpenClaw、OpenCode）存取 Antigravity 登入「is a violation of our Terms of Service」，可能停權；建議用「Gemini Enterprise or Google AI Studio API key」 |
| Google Antigravity 條款第 6 段、論壇 staff 回覆 | 已由 `2026-11-22-gemini-pro-pool.md` 整理，本次未重查 |

**判讀（我的整理，不是官方結論）：**

- **同一人多個付費訂閱本身**：Anthropic 與 OpenAI 的一手文字都沒有「禁止同一人擁有多個訂閱」或「允許」（待驗證，只查了上表頁面，未查客服 FAQ 與使用政策 PDF）。Anthropic 官方文件有給「工作與個人」多帳號的設定方式。
- **共用或轉手帳號**：三家都禁止分享憑證。這排除「團隊共用池」，不影響「一個人自己的幾個帳號」。
- **自動輪換、代理訂閱登入**：Anthropic 明文限制的是「第三方開發者」代理他人使用訂閱憑證與蒐集憑證；自己用未修改的 Claude Code 登入自己的訂閱是明文允許的。**CLIProxyAPI、ccflare、TeamClaude 這類「本機代理，所有請求經訂閱憑證轉發」是否算違規，一手文字沒有直接回答（待驗證）**；maxpool 的 README 自己說依 Anthropic Consumer Terms 與 2026 年 2 月一條關於訂閱 OAuth token 的規則，可合理解讀為涵蓋代理（第三方說法，待驗證）。Consumer Terms 的「automated or non-human means」例外只有 API key，腳本驅動訂閱帳號有風險。
- **Google**：自動輪換與第三方包裝都有明文「不支援」。這是三家裡最明確的。
- **實際停權案例（非官方，待驗證）**：2026-02 Google 切斷 OpenClaw 經 Antigravity OAuth 的存取（VentureBeat、The Register，先前報告查過）；Google 論壇有 403「Service disabled for violation of Terms of Service」申訴（先前報告）。Anthropic、OpenAI 的停權案例本次沒有找到可靠來源，不寫。
- **工具怎麼降低風險**：OmniRoute 把受限來源標 `avoid` 並預設不自動路由；oh-my-subscriptions 自述不製造額度、不繞過供應商限制、不池化陌生人帳號、不轉售（搜尋摘要，待驗證）；CodexBar 類只讀額度、不碰請求；claude-swap 只換憑證而非代理請求。沒有工具能保證不停權。
- **官方明確支援的路**：API 金鑰（Anthropic Console、AI Studio、OpenAI API）；雲端供應商（Bedrock、Vertex、Foundry）；Team 與 Enterprise 方案；升級更高方案（Google 論壇建議升 Ultra，非官方）；Antigravity 的 `agy -p` 在自己的腳本與 CI 中是支援的，但被第三方 agent 包起來就不是。

### 5. 可觀測性

- **用量顯示**：選單列與桌面程式很多：CodexBar（★23,287）、ClaudeBar（★1,590）、aqua5230/usage、Usage4Claude、Quotio（CLIProxyAPI 周邊）。多半 macOS 限定。claude-swap 的 `cswap list` 與 TUI 跨 Windows、macOS、Linux。
- **紀錄**：ccflare 系有請求層級分析（延遲、token、成本）；LiteLLM 有支出追蹤與預算；OpenClaw 狀態指令顯示冷卻。
- **告警與手機通知**：codex-lb 周邊有 Linux 桌面通知（omarchy 外掛）與 Home Assistant 整合（可接手機推播，待驗證）；Claude Code status line 版 CLIProxyAPI 額度外掛。**手機通知沒有找到成熟的專用做法**；OmniKit 若要做，用現有 `PushNotification` 就夠（這是工具能力，不是調研結論）。
- **agent 讀得到的介面**：TeamClaude 的選配 MCP 讓 agent 自己讀額度與切帳號；CLIProxyAPI 的 Management API。**OmniKit 目前缺這一塊**（T3 有探測、沒有對外介面）。

### 6. 給不同使用者用：設定資料長什麼樣

看過的 schema 共同點（OpenClaw、Hermes、TeamClaude、claude-swap、magpie、LiteLLM）：

- 帳號身分與秘密分開：設定檔只放 id、供應商、方案、順序、策略；秘密在鑰匙圈或獨立 store（OpenClaw：config 是 metadata only）。
- 設定與狀態分檔：手改的設定、機器學到的狀態（額度、冷卻、最後使用）各一個檔，狀態可刪可重建（TeamClaude 明說）。
- 策略是欄位而不是程式碼：`strategy: fill_first | round_robin | least_used | session`（Hermes、CCS、magpie 的 `routing=` 與 `stays=`）。
- 每帳號覆寫：門檻、優先序、啟用旗標（claude-swap 的 `threshold N pct`、`priority N tier`）。
- 規約欄位：只有 OmniRoute 有（`FREE_TIER_TOS`）。
- 初次設定流程的共通形狀：`add`（人在瀏覽器登入）→ 工具列出該帳號可用項目 → 設順序與門檻 → `list`／儀表板確認。沒有任何工具問「你的訂閱組合是什麼」；都是使用者自己一個一個加。

## 三、飽和調研紀錄（必附五項）

### 3.1 查了哪些管道與關鍵字（`status` 輸出）

管道：GitHub topic、GitHub 關鍵字、awesome、skills.sh、npm、官方 MCP Registry、Hacker News、Exa（匿名）、網頁搜尋（中英文）、Product Hunt（網頁搜尋）、`sweep.py related`（CLIProxyAPI、better-ccflare、openclaw）。

```
總共 176 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
已經 12 組還沒停（上限 12 組）：先回報現況
第 1 組「multi account rotation」：28 個名字（新 28）
第 2 組「claude code multiple accounts」：42 個名字（新 41）
第 3 組「subscription account pool」：24 個名字（新 22）
第 4 組「quota aware router usage limit failover」：20 個名字（新 18）
第 5 組「better-ccflare」：0 個名字（新 0）  ← 誤開的單詞查詢，只是我想看一個種子名字的 related，不是真正的擴展組，不當作「沒有新名字」的證據
第 6 組「claude code proxy load balancer oauth accounts」：20 個名字（新 16）
第 7 組「claude codex usage quota menubar dashboard」：18 個名字（新 18）
第 8 組「openclaw auth profiles failover cooldown」：3 個名字（新 3）
第 9 組「llm gateway api key rotation cooldown least used」：9 個名字（新 8）
第 10 組「codex multiple accounts codex home profile switch」：9 個名字（新 8）
第 11 組「antigravity multi account manager quota」：13 個名字（新 11）
第 12 組「号池 多账号 额度 轮询」：4 個名字（新 4）
```

擴展用詞來源：起手 3 組是題目指定；第 4 組來自第 1 到 3 組結果的「rate limit」「quota」；第 6 組來自 CLIProxyAPI、ccflare 的自稱「proxy、load balancer」；第 7 組來自結果中的「menu bar、dashboard」；第 8 組來自 Hermes、OpenClaw 的「auth profiles、cooldown」；第 9 組補「LLM gateway」；第 10 組補 Codex 側；第 11 組補 Antigravity；第 12 組補中文「號池」。

判斷「相關」的標準：能管理、切換、輪替、監看「同一人多個 AI 訂閱帳號或 API key」並服務 coding agent 的工具才算；純 API 閘道只收有帳號池、冷卻或 failover 功能的；通用雲端 Load Balancer、爬蟲帳號工具不算。

### 3.2 第幾組停、哪 3 組沒有新名字

**第 12 組停，照「12 組還沒停就回報」的規定停，結論是「未飽和」。** 每一組都還有新名字，連續沒有新名字的組數是 0；★1,000 以上的新名字（第 12 組仍有 Hermes 的 ★265,461 與 lbjlaq/Antigravity-Manager 的 ★33,691，第 11 組出現）也沒有連續 3 組沒新的。第 10 組單獨看沒有新的 ★1,000 以上名字，但前後組都有，不構成連續。**沒有哪 3 組沒有新名字可列。**

要不要再查：我的判斷是題目混了三種東西（訂閱帳號代理、帳號切換器、額度顯示），每換詞就跳進新子領域（第 7、11 組尤其）。建議拆成三個子題各一本帳本，或接受目前的結論，因為六個面向的做法已經有多個互相印證的來源（Hermes、OpenClaw、TeamClaude、claude-swap），再查大概只會增加小 repo。要不要拆開再跑，等使用者決定。

### 3.3 查不到的管道與原因

- Exa：第 3 組匿名限速（`ai.exa/rateLimited`），第 4、5 組之後恢復，第 3 組記為查不到。
- GitHub API：第 10 組第一次查詢時 403 rate limit，過一段時間重查補上。
- HN：第 4、7 組 0 筆；skills.sh：多數組 0 筆或只有無關結果；awesome：多數組 0 筆，第 9 組找到 howardpen9/awesome-ai-api-proxy（★114）。
- Product Hunt：只做一次（`site:producthunt.com`），找到 Claudy、Moxie、cux、One-Click Claude Code Account Switching（Alfred workflow），細節未讀。
- MCP Registry：Registry 只比對名稱子字串，查詢字多半無意義，有用的只有 `io.github.Evozim/api-quota-balancer-mcp`（未讀）。
- 沒查：Gemini CLI 的 `GEMINI_HOME` 一手說明；OpenAI 與 Anthropic 客服 FAQ 對「多個訂閱」的說明；OpenClaw、Hermes 以外 agent（OpenCode、Goose、Aider）的內建帳號池；new-api、one-api（搜尋沒回結果，未查 GitHub）；Kong、Helicone 類企業閘道。

### 3.4 `verify` 實測星數與授權（2026-11-23 gh api）

| repo | ★ | 授權 | 最後 push |
|---|---|---|---|
| openclaw/openclaw | 395,066 | MIT | 2026-11-23 |
| NousResearch/hermes-agent | 265,461 | MIT | 2026-11-23 |
| farion1231/cc-switch | 156,432 | MIT | 2026-11-23 |
| cheaper-inference/OmniRoute | 89,646 | MIT | 2026-11-23 |
| BerriAI/litellm | 63,724 | NOASSERTION | 2026-11-23 |
| router-for-me/CLIProxyAPI | 59,258 | MIT | 2026-11-23 |
| musistudio/claude-code-router | 38,323 | MIT | 2026-11-21 |
| lbjlaq/Antigravity-Manager | 33,691 | NOASSERTION | 2026-11-22 |
| decolua/9router | 32,752 | MIT | 2026-11-23 |
| steipete/CodexBar | 23,287 | MIT | 2026-11-21 |
| jlcodes99/cockpit-tools | 20,293 | 無 | 2026-11-22 |
| Portkey-AI/gateway | 13,431 | MIT | 2026-11-20 |
| maximhq/bifrost | 9,954 | Apache-2.0 | 2026-11-22 |
| tbphp/gpt-load | 7,246 | MIT | 2026-11-22 |
| agentgateway/agentgateway | 6,361 | Apache-2.0 | 2026-11-22 |
| snailyp/gemini-balance | 5,772 | NOASSERTION | 2025-09-30 |
| realiti4/claude-swap | 4,908 | MIT | 2026-11-21 |
| badrisnarayanan/antigravity-claude-proxy | 4,087 | MIT | 2026-11-16 |
| Soju06/codex-lb | 3,454 | MIT | 2026-11-22 |
| kaitranntt/ccs | 2,907 | MIT | 2026-11-16 |
| Draculabo/AntigravityManager | 2,565 | NOASSERTION | 2026-11-21 |
| tddworks/ClaudeBar | 1,590 | Apache-2.0 | 2026-11-20 |
| snipeship/ccflare | 1,054 | MIT | 2026-04-19 |
| KarpelesLab/teamclaude | 527 | MIT | 2026-11-21 |
| tombii/better-ccflare | 283 | MIT | 2026-11-20 |
| aqua5230/usage | 356 | AGPL-3.0 | 2026-11-22 |
| f-is-h/Usage4Claude | 422 | MIT | 2026-09-29 |
| codeking-ai/cligate | 135 | AGPL-3.0 | 2026-10-15 |
| inulute/cux | 90 | GPL-3.0 | 2026-09-23 |
| christiandoxa/prodex | 61 | Apache-2.0 | 2026-11-22 |
| xhyqaq/codex-auto | 60 | MIT | 2026-05-02 |
| uwuclxdy/clauth | 344 | MIT | 2026-11-23 |
| Mirrowel/LLM-API-Key-Proxy | 566 | NOASSERTION | 2026-11-02 |
| 2solarmax/maxpool | 6 | MIT | 2026-11-22 |
| sanketvp/qlb | 0 | MIT | 2026-11-23 |

注意：cockpit-tools、AntigravityManager、Antigravity-Manager 的授權不是標準開源授權（「無」或 NOASSERTION），OmniKit 不宜內嵌或改寫它們的程式碼，只能當做法參考。

### 3.5 沒有一手證據、標「待驗證」的說法

- 工具比較表中所有「README」欄的功能，都只是專案自己的說法，沒有實測（本次沒有安裝任何東西）。
- Anthropic、OpenAI 對「同一人多個付費訂閱」的態度：沒找到明文。
- CLIProxyAPI 類本機代理對個人自用是否違反 Anthropic 條款：官方文字沒有直接回答。
- maxpool README 提到的「2026 年 2 月一條關於訂閱 OAuth token 的規則」：未找到原文。
- Codex `account/rateLimits/read` 端點、codex-auto 的偵測方式：第三方文章說法。
- Bifrost adaptive balancing 為付費、oh-my-subscriptions 的自述：搜尋摘要。
- Home Assistant 能推手機通知：推論，未驗證。
- OmniRoute `FREE_TIER_TOS` 內容：引自先前報告（2026-11-22 已讀原始碼），本次未重驗。

## 四、對 OmniKit 的機制建議

### 必做

1. **帳號清冊做成資料檔，秘密與設定分開。** 一個 `accounts` 檔，每筆：`id`（沿用 T3 的 provider instance id）、`provider`、`plan`、`config_dir`（Claude 的 `CLAUDE_CONFIG_DIR`、T3 Antigravity 的 sha256 資料夾）、`classes`（可擔任的角色）、`enabled`、`auto_dispatch: allowed | manual_only | never`、`tos_note`（附一手來源網址與查證日期）。依據：OpenClaw（config 只放 metadata、秘密在別處）、Hermes（策略是欄位）、OmniRoute（規約獨立欄位）、Anthropic 官方 `CLAUDE_CONFIG_DIR` 多帳號做法。
2. **狀態另存一個可刪檔。** 每帳號 `health`：`ok | cooldown | needs_login | needs_verification | disabled`，加 `until` 時間、`last_used`、最近一次探測到的額度與重置時間。依據：TeamClaude 的 `teamclaude.state.json`（可刪重學）、OpenClaw 的 `usageStats`。
3. **錯誤分類成固定表，照 Hermes 與 OpenClaw 的做法。** 429 額度用完（換帳號或換家，冷卻到重置時間）、429 速率（原帳號慢下來，不換）、401（先刷新一次，失敗標 `needs_login`）、402 或計費（停用至人處理）、**403 要求驗證（標 `needs_verification`，不重試、不輪換、通知人）**。依據：Hermes 官方錯誤表、TeamClaude 的兩種 429、OpenClaw 的「計費與永久授權錯誤整個 profile 停用」。
4. **session 親和：同一個工作包從頭到尾用同一個帳號。** 換帳號只發生在工作包之間。依據：OpenClaw 的 session 釘選、ccflare 的 `LB_STRATEGY=session`、TeamClaude 與 magpie 文件都說明換帳號會丟 prompt cache。OmniKit 的 T3 子對話本來就是一條對話一個實例，天然符合。
5. **能力煙霧測試做成資料。** 帳號 × 模型 × 思考程度的矩陣，附測試日期與結果，帳號新增或重新登入時自動跑一次。依據：沒有現成工具，這是缺口；最接近的是 Hermes「只停用該 key 的該模型」。T3 `orchestrator_capabilities` 加今天的 30/30 煙霧測試就是原型。
6. **規約欄位強制，預設保守。** 新帳號 `auto_dispatch` 預設 `manual_only`，要改成 `allowed` 必須填 `tos_note` 與查證日期。Google Antigravity 消費方案固定 `never`（FAQ 明文：自動輪換與第三方包裝不支援）。依據：OmniRoute 的 `avoid` 預設排除；本檔第二節第 4 項的一手原文。

### 選配

1. **額度唯讀探測與顯示（風險最低）。** 用 T3 已在呼叫的 Google 端點與 Claude 的 OAuth 用量端點，只讀、只顯示、只用來給人看與給派工政策「選哪個帳號開新對話」的參考，不自動重送請求。依據：CodexBar、ClaudeBar、`cswap list` 都只做顯示。注意：Anthropic 用量端點非官方文件化（待驗證），欄位可能變。
2. **在「開新工作包」這個粒度，依額度與優先序選實例。** 策略建議 `weekly-first`（先用週額度最快重置者）加門檻，換帳號只在工作包邊界。依據：claude-swap、TeamClaude 都主張「週額度到重置前沒用掉就作廢」。**風險**：這是自動選擇訂閱帳號；Anthropic 一手文字沒有直接禁止，也沒有直接允許（待驗證）；做法是「選哪個未修改的 Claude Code 實例來跑」，不是代理憑證，離官方明文禁止的「路由他人請求或蒐集憑證」較遠，但仍建議先只對 Claude 三個自己名下帳號開，並在 `tos_note` 記錄這個判斷。
3. **額度用完的接手順序寫成資料：** 同家另一帳號（僅 `auto_dispatch: allowed` 者）→ 別家模型 → API 金鑰或 Vertex。依據：Hermes 的 `fallback_model`、OpenClaw 兩段式、TeamClaude 的 `allowExtraUsage`。「改走付費 API」是官方明確支援的路（Google FAQ 建議 API key；Anthropic 法務頁建議 API key）。
4. **提供 agent 讀得到的狀態介面**（本機 JSON 檔或 MCP），內容只有 health、until、剩餘比例，不含秘密。依據：TeamClaude 選配 MCP、CLIProxyAPI Management API。另加 `needs_verification` 與 `needs_login` 時用 `PushNotification` 通知人。

### 不建議（規約風險）

1. **Antigravity 帳號的自動輪換、帳號池、把 `agy` 包進別的 agent 自動派工**：Google FAQ 一手原文明寫不支援，條款寫可能停權（本檔 2.4）。cockpit-tools、Antigravity-Manager、opencode-antigravity-auth 這類工具正是這種用法，只當做法參考，不採用。OmniKit 現有 `antigravity_ryan` 自動派工的風險已在 `2026-11-22-gemini-pro-pool.md` 記錄，這份調研沒有改變那個結論。
2. **把 CLIProxyAPI、ccflare、TeamClaude、9Router、cligate 這類「本機代理 + 訂閱登入」當 OmniKit 的核心機制**：Anthropic 法務頁明文禁止第三方「route requests through ... plan credentials on behalf of their users」與蒐集、中介憑證；個人自用的灰色地帶沒有一手答案。OmniKit 要開源給多人，一旦內建這條路，等於替每個使用者做了未經確認的規約決定。可借鏡它們的策略與錯誤分類，不內建代理。
3. **多人共用或轉手帳號、折扣池帳號**：三家一手條款都禁止分享憑證；Google staff 也說問題常出在「discounted or shared pool」帳號。

## 五、對照 OmniKit 目前狀態的缺口

- 有：T3 的實例隔離（3 個 Claude 各自 `CLAUDE_CONFIG_DIR`、6 個 Antigravity 各自資料夾）、T3 內部的額度探測、30/30 模型煙霧測試、`dispatch.md` 的 `classes` 清單。
- 缺：帳號清冊的規約欄位與查證日期、`health` 狀態檔與錯誤分類表、能力矩陣的落檔格式、agent 能讀的狀態介面、`needs_verification` 的通知。
- 現況 `dispatch.md` 把「帳號」「類別」「政策」混在一份 YAML 的註解裡；上面第 1、2 項是把它資料化。
