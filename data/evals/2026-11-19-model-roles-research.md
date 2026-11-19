# 模型角色映射、目錄變動偵測與工作流模型選型調研報告

- 調研日期：2026-11-19
- 產出位置：`data/evals/2026-11-19-model-roles-research.md`
- 相關檔案：`data/rules/dispatch-policy.md`、`data/profiles/ryan/dispatch.md`、`engine/scripts/dispatch.py`、`engine/scripts/homes.py`、`engine/scripts/home_watch.py`、`engine/scripts/build.py`、`floorplan/serve.mjs`、`data/tools/t3-code.yaml`

---

## 一、業界與開源做法比較表

以下依「閘道器與路由器」、「Coding Agent 與多代理框架」、「SDK 與語意路由」、「模型目錄、淘汰偵測與 UI 選型」四類整理代表性專案。GitHub 星數皆於 **2026-11-19** 透過 `gh api`（`sweep.py verify`）實測驗證；未經一手文件或原始碼直接確認的第三方說法已標註 `【待驗證】`。

| 做法分類 | 代表工具（網址、星數／官方） | 角色／別名怎麼定義 | 怎麼對應到實際模型 | 新模型／變動偵測與提醒 | 前端工作流選型 | 對 OmniKit 的啟發 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **統一閘道與別名路由** | **LiteLLM**（[github.com/BerriAI/litellm](https://github.com/BerriAI/litellm) ★63,526, MIT; [docs.litellm.ai](https://docs.litellm.ai/docs/model_latest_aliases)） | `model_list` 定義 `model_name` 群組；`model_group_alias` 將虛擬別名指到目標群組；內建 `provider/model-latest` 與 `*` wildcard 通配 | Router 依策略（latency/usage/cost）將別名解析至部署實例；支援 `fallbacks`（一般、context window、content policy）與 `default_fallbacks` | 啟動或每 6 小時自 GitHub 拉取 `model_prices_and_context_window.json`（含 `source_revision` / `etag`）；另有 `/model/deprecations` API 與 30 天／1 天前淘汰 Email 提醒 | Admin UI 提供 Models & Endpoints 卡片、Price Data Reload 狀態與 Migration 告警頁 | 別名群組（`model_group_alias`）＋「依條件自動對應而非硬編成本表」值得借鏡；其 `fallbacks` 分類可對應 OmniKit 額度耗盡／能力不足升級路徑 |
| **多供應商路由與變體後綴** | **OpenRouter**（[openrouter.ai/docs/features/model-routing](https://openrouter.ai/docs/features/model-routing), 官方） | 虛擬路由模型 slug：`openrouter/auto`、`openrouter/auto-code`、`openrouter/auto-beta`；模型後綴變體（如 `:nitro`、`:floor`、`:free`【待驗證：僅見題目與摘要提及，未逐頁抓取變體全文】） | 請求級 `plugins` 指定 `allowed_models`（支援 glob pattern）、`excluded_models`、`cost_tier`；決策模型先評 11 項特徵再結合即時價格／快取／基準分挑選模型與推理深度，並以 `session_id` 維持跨輪黏著 | 提供公開 `/api/v1/models` 目錄與 Latest Model Resolution；回傳 body 附實際選中的 `model` 與 `X-OpenRouter-Metadata` 決策原因 | Web Chatroom 與 Account Defaults 可設定預設路由池與成本分級 | 「角色允許池（allow/exclude）＋成本分級（cost tier）＋會話黏著」可直接用於 OmniKit 任務級路由，避免每次都切模型破壞快取 |
| **商業閘道虛擬模型** | **Portkey AI Gateway**（[github.com/Portkey-AI/gateway](https://github.com/Portkey-AI/gateway) ★13,415, MIT; [portkey.ai/docs](https://portkey.ai/docs/product/ai-gateway/universal-api)） | 以 `@provider-slug/model` 與集中式 `Configs`（JSON 定義 `strategy` / `targets`）抽象角色與流量分配 | `x-portkey-config` 依條件路由（Conditional Routing）、權重負載平衡、自動重試與熔斷切換至真實 provider deployment | Model Catalog 集中管理各供應商支援模型與 Virtual Keys 遷移指南；Nitro Mode 測試中 | Portkey Studio UI 可視化編輯 Config JSON、A/B 金絲雀分流與條件規則 | 將「路由邏輯（Config）」與「模型清單（Catalog）」拆開存放，比 OmniKit 目前把模型寫死在規則 Markdown 更容易熱更新 |
| **高效能閘道與本地路由** | **Bifrost**（[github.com/maximhq/bifrost](https://github.com/maximhq/bifrost) ★9,762, Apache-2.0）、**AgentGateway**（[github.com/agentgateway/agentgateway](https://github.com/agentgateway/agentgateway) ★6,299, Apache-2.0）、**OmniRoute**（[github.com/cheaper-inference/OmniRoute](https://github.com/cheaper-inference/OmniRoute) ★88,768, MIT） | 以 Go/Rust 實作虛擬 model key 與多帳號輪替；OmniRoute 主打訂閱／免費帳號聚合路由與多階 fallback | 攔截 OpenAI／Anthropic 相容請求，依配額冷卻、429 狀態與優先序自動切到備援帳號或模型 | 依賴上游 `/v1/models` 同步或手動更新 catalog；OmniRoute 提供 Web dashboard 檢視配額健康度【待驗證】 | 提供本地 Web 控制台切換帳號優先序與檢視用量 | OmniKit 的 `antigravity` / `claudeAgent` 多帳號輪替已有類似需求，但若直接架 HTTP proxy 須注意 T3 Code 本機驅動（ACP／CLI）並非全部走統一 OpenAI endpoint |
| **雲端邊緣 AI 閘道** | **Cloudflare AI Gateway** / **Vercel AI Gateway**（官方架構【待驗證細部欄位】） | 透過 Gateway Route／統一 `provider/model` 字串集中管理上游金鑰與 fallback 鏈 | 按規則將邏輯端點轉發至多個 provider，並支援快取與 rate-limit fallback | 依賴平台側模型清單同步更新 | Cloud Dashboard 提供路由規則編輯與成本遙測 | 適合雲端服務型團隊；OmniKit 屬於本機多 agent 編排工具（Claude/Codex/Antigravity/T3），較不適合把所有流量綁死在雲端代理 |
| **Coding Agent：內建別名＋雙模切換** | **Claude Code**（[github.com/anthropics/claude-code](https://github.com/anthropics/claude-code) ★156,227, 專有授權; [code.claude.com/docs/en/model-config](https://code.claude.com/docs/en/model-config)） | 內建簡短別名 `default`、`best`、`sonnet`、`opus`、`haiku`、`fable`、`opusplan`、`sonnet[1m]`；subagent `.md` frontmatter 另有 `model` 與 `effort` 欄位 | 依執行環境自動解析：`ANTHROPIC_DEFAULT_*_MODEL` 環境變數覆寫底層實際模型（支援 Bedrock ARN、Foundry、Vertex 版本對應）；`opusplan` 自動於 Plan 模式用 Opus、執行切 Sonnet | 透過 Claude Code 版本更新與環境變數 pin 定控制；支援 `availableModels` 與組織層級 allowlist 限制 | `/model` 互動選單（支援 `Tab` 或選項調整 effort），也可在自訂選項加入模型 | 「環境變數／provider 覆寫別名底層模型」＋「Plan／Act 自動分流（`opusplan`）」是最簡潔的零代理（zero-proxy）抽象 |
| **Coding Agent：主／弱／編輯三槽位** | **Aider**（[github.com/Aider-AI/aider](https://github.com/Aider-AI/aider) ★50,176, Apache-2.0; [aider.chat/docs/config/model-aliases.html](https://aider.chat/docs/config/model-aliases.html)） | 區分 `main model`（對話寫碼）、`editor model`（套用編輯）、`weak model`（摘要與 commit 訊息）；另有 `--alias name:model` 與內建別名表（`opus`、`sonnet`、`flash` 等） | 啟動或 `/model <alias>` 時展開 alias 為 LiteLLM 格式全名，並自動查表推斷預設的 `weak`／`editor` 搭檔 | 內建 model metadata 警告未知模型或未支援的 reasoning 參數（`Model warnings`），不自動背景推播新模型 | 僅 CLI `/model` 指令切換 | 把「角色職責（主寫／編輯／輔助）」拆開綁定模型，比只用單一模型省費且符合 OmniKit `prework`/`implement`/`review` 分工 |
| **IDE Agent：多職責 Role 標籤** | **Continue**（[github.com/continuedev/continue](https://github.com/continuedev/continue) ★36,515, Apache-2.0; [docs.continue.dev/reference](https://docs.continue.dev/reference)） | `config.yaml` 的每個模型宣告 `roles` 陣列：`chat`、`edit`、`apply`、`autocomplete`、`embed`、`rerank`、`summarize`（預設 `[chat, edit, apply, summarize]`） | 當某個職責未專屬指定模型時，自動回退至有宣告該 role（或預設 `chat`）的模型；支援 `capabilities`（`tool_use`、`image_input`） | 依賴 Hub／設定檔版本同步與啟動檢查，無內建遠端淘汰追蹤 | IDE 側邊欄針對各 role 提供獨立下拉選單，僅列出支援該 role 的候選模型 | **極具參考價值**：先替每個實際模型標註能力／角色標籤，再讓各工作流角色自動篩選合適候選，前端下拉也只顯示相容模型 |
| **Coding Agent：動態 Catalog 驅動** | **OpenCode**（[github.com/anomalyco/opencode](https://github.com/anomalyco/opencode) ★227,906, MIT; [opencode.ai/docs/models](https://opencode.ai/docs/models/)） | `opencode.json` 設定全域預設 `model` 與 `small_model`【待驗證 `small_model` 鍵名】，每個 agent（build/plan/自訂）與 command 可覆寫專屬 `model` 與 `variant` | 結合本地已連線供應商憑證＋[Models.dev](https://models.dev) 即時目錄過濾「目前專案可用」模型；若預設模型不可用則回退到最新可用支援模型 | 直接消費 `models.dev` API／資料更新，新模型上線可立即出現在 `/models` 清單與定價能力表中 | TUI `/models` 互動搜尋選取，僅限當前 session 生效不改寫設定檔 | 把「專案可用性（憑證已啟用）」與「公開規格庫（Models.dev）」分離比對，正適合 OmniKit 結合 T3 `orchestrator_capabilities` |
| **IDE Agent：雙模／多模式配置** | **Cline**（[github.com/cline/cline](https://github.com/cline/cline) ★71,762, Apache-2.0; [docs.cline.bot](https://docs.cline.bot/features/plan-and-act)）、**Roo Code**（[github.com/RooCodeInc/Roo-Code](https://github.com/RooCodeInc/Roo-Code) ★24,236, Apache-2.0, **已封存 Archived 2026-05-15**） | Cline 採 `Plan`／`Act` 雙模式各選不同模型；Roo Code（已封存）擴展為 `Code` / `Architect` / `Ask` / `Debug` 等自訂 Mode 各綁一組 `API Configuration Profile` | 使用者預先建立數組命名 Profile（含 provider + model + 參數），再於模式切換列綁定對應 Profile | 依賴內建各 provider `/models` API 刷新清單（如 OpenRouter／Anthropic 列表），無自動淘汰警報 | IDE 擴充功能頂部／設定頁直接切換不同 Mode 使用的模型 Profile | 「命名 Profile ＋ 工作模式綁定」非常適合 OmniKit 的「進階用戶工作流選型 UI」概念 |
| **Coding Agent：Profile 與雙模型交接** | **Codex CLI**（[github.com/openai/codex](https://github.com/openai/codex) ★135,832, Apache-2.0; [developers.openai.com/codex/config-basic](https://developers.openai.com/codex/config-basic)）、**Goose**（[github.com/aaif-goose/goose](https://github.com/aaif-goose/goose) ★56,779, Apache-2.0）、**Crush**（[github.com/charmbracelet/crush](https://github.com/charmbracelet/crush) ★29,133） | Codex 在 `config.toml` 用 `[profiles.<name>]` 封裝 `model` 與 `model_reasoning_effort`；Goose 用 `GOOSE_LEAD_MODEL` + `GOOSE_MODEL`（Worker）+ `GOOSE_FAST_MODEL`；Crush 拆為 `models.large` 與 `models.small` | Codex 依 `--profile` 載入；Goose 依輪數（`GOOSE_LEAD_TURNS`）與失敗閾值（`GOOSE_LEAD_FAILURE_THRESHOLD`）在 Lead 與 Worker 間動態升級交接；Crush 依任務型態（主程式 vs 標題／摘要）分派，若 `small` 缺省則退回 `large` | Codex／Crush 透過 CLI 升級或 provider 列表檢查；Goose 無內建遠端淘汰巡檢 | Crush 在 TUI 提供 `Ctrl+L`＋`Tab` 在 `large`/`small` 切換；Goose Desktop 底部提供 Lead/Worker 設定面板 | Goose 的 `failure_threshold` 自動升級邏輯，與 OmniKit `dispatch-policy.md` 的 `escalation` 規則高度契合 |
| **Coding Agent：擴充目錄同步** | **oh-my-pi**（[github.com/can1357/oh-my-pi](https://github.com/can1357/oh-my-pi) ★39,454, MIT）、**OpenHands**（[github.com/OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) ★93,810, MIT） | `oh-my-pi` 支援多帳號與模型 profile 切換（生態另見 `omp-model-profiles`、`pi-model-discovery` 外掛）；OpenHands 採 In-conversation LLM Profiles | 啟動／對話前向各 provider 或設定檔讀取可用模型清單，再依 profile 或會話選擇綁定 | 社群已發展出 `pi-model-discovery`／`pi-models-discovery` 專門處理 provider model polling 與同步 | OpenHands 對話視窗內建 Profile 選擇器；`omp-settings-web` 提供 Web 設定頁 | 說明「靜態設定＋外掛式 Model Discovery 輪詢器」是編碼代理的常見演進路徑 |
| **多代理與工作流框架** | **CrewAI**（[github.com/crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) ★61,091, MIT）、**Pydantic AI**（[github.com/pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) ★21,283, MIT）、**Mastra**（[github.com/mastra-ai/mastra](https://github.com/mastra-ai/mastra) ★29,630） | CrewAI 為每個 `Agent` 指定 `llm` 與 `function_calling_llm`；Pydantic AI 支援 `FallbackModel` 與依賴注入動態換模型；Mastra 為每個 Agent／Workflow step 宣告模型 | 執行期透過統一模型字串（`provider:model`）或可動態解析的函式決定當前節點所用模型 | Mastra 內建整合最新供應商清單與 Studio 測試【待驗證自動提醒】；CrewAI／Pydantic AI 依賴上游 SDK | Mastra Studio 提供視覺化 Workflow 節點選取模型與測試 | 對「每個工作流階段（如 `prework`、`route`、`second_opinion`）獨立覆寫模型」提供了清晰的資料模型參考 |
| **開發框架 Registry** | **Vercel AI SDK**（[github.com/vercel/ai](https://github.com/vercel/ai) ★28,079; [ai-sdk.dev](https://ai-sdk.dev/docs/reference/ai-sdk-core/provider-registry)）、**LangChain**（[github.com/langchain-ai/langchain](https://github.com/langchain-ai/langchain) ★149,875, MIT） | Vercel AI SDK 提供 `createProviderRegistry`（`providerId:modelId` 統一命名空間）與 `customProvider`（定義別名映射與預設參數）；LangChain 提供 `init_chat_model(configurable_fields="any")` | 應用程式只呼叫邏輯 ID（例如 `my-custom:reasoning`），執行時透過 `customProvider` 轉譯為真實模型與預設 `thinking`／`temperature` | 無內建遠端模型目錄輪詢，需由應用端搭配外部目錄 | 無內建 UI（常搭配 AI Elements／shadcn 模型選擇器元件） | `customProvider` 把「預設 thinking/effort 參數」綁進別名定義，能直接解決 OmniKit 必須強制 Gemini `high` 以上、Opus `medium` 的規範 |
| **品質／成本預測型路由** | **RouteLLM**（[github.com/lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM) ★5,719, Apache-2.0, 2024-08 後較少更新）、**Martian / NotDiamond**（商業服務【待驗證公開架構細節】） | 只分「強模型（strong）」與「弱模型（weak）」兩個抽象端點 | 用分類器／矩陣分解／路由器評估 prompt 難度與勝率閾值，動態決定送給 strong 或 weak | 需定期重新訓練或校準 router 權重，新模型上線無法即刻生效 | 商業平台提供 Dashboard 調整品質／成本滑桿 | **不建議作為 OmniKit 主力**：規則可預測性、可追蹤性與人工稽核在 OmniKit 更重要；任務分級比 prompt 語意分類更穩定 |
| **開放目錄、淘汰追蹤與依賴機器人** | **Models.dev**（[github.com/anomalyco/models.dev](https://github.com/anomalyco/models.dev) ★7,687, MIT; [models.dev](https://models.dev/)）、**deprecations.info**（[deprecations.info](https://deprecations.info/)）、**Renovate**（[github.com/renovatebot/renovate](https://github.com/renovatebot/renovate) ★23,181, AGPL-3.0）、**dsh-model-sync**（[github.com/GooDAnDReaDY/dsh-model-sync](https://github.com/GooDAnDReaDY/dsh-model-sync) ★7）、**chowkidar**（[github.com/bhav09/chowkidar](https://github.com/bhav09/chowkidar) ★9）、**sunset**（[github.com/AppliedBenchmark/sunset](https://github.com/AppliedBenchmark/sunset) ★2）、**model-deprecation-tracker**（[github.com/quora/model-deprecation-tracker](https://github.com/quora/model-deprecation-tracker) ★4）、**foundry-model-catalog-watcher**（[github.com/dhangerkapil/foundry-model-catalog-watcher](https://github.com/dhangerkapil/foundry-model-catalog-watcher) ★0） | Models.dev 以開源 TOML/JSON 維護各實驗室與供應商模型規格（上下文、定價、推理、工具呼叫支援）；`deprecations.info` 提供標準化 JSON Feed (`_deprecation.model_id`, `shutdown_date`) 與 RSS | 定期比對本地設定檔／清單與遠端目錄的 diff（新增、價格變動、即將下架），Renovate 式地自動產出升級建議或 Issue／PR | **最核心參考模式**：1) 實時可用清單由本機 runtime（T3）查詢；2) 規格／定價／淘汰日期由外部公開 Feed（Models.dev + deprecations.info + 官方文件）交叉比對；3) Renovate 風格只提建議 PR／通知，不靜默換掉生產模型 | 可在網頁／CLI 標記 `New`、`Deprecated (YYYY-MM-DD)` 與建議替代型號 | OmniKit **不該只比對 T3 列表增減**，若能加上「新模型規格初判」＋「Renovate 式確認建議」，就能精準給出「Gemini 4 Neon 建議納入試行或替換哪一級」 |
| **本地選型小工具** | **llama-swap**（[github.com/mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap) ★6,273, MIT）、**Nekko Agent**（[github.com/nekko-labs/nekko-agent](https://github.com/nekko-labs/nekko-agent) ★12, MIT） | `llama-swap` 支援 Profiles 與 Selectors 在多組模型設定間熱切換；Nekko Agent 提供前端模型／工作流節點選取 | 依使用者選定的 profile 或節點覆寫，於送出執行前注入目標模型與參數 | 無遠端新模型自動發現 | 輕量本地 Web UI 直接挑選模型與參數 | 展示本機小工具（不需複雜雲端後端）也能做到好用的視覺化工作流選型 |

---

## 二、三個可行架構方案（輕 → 重，保持中立）

### 現況與實測基礎（2026-11-19）

在設計方案前，先確認 OmniKit 目前的實作邊界與本機工具能力：

1. **現有政策與程式耦合點**：
   - `data/rules/dispatch-policy.md:20-25` 的 `model_classes` 硬編寫死 `gemini-pro: gemini-4-hydrogen`、`gemini-flash: gemini-3.8-flash`、`claude-opus: claude-opus-5-5`、`claude-sonnet: claude-sonnet-5-5`、`antigravity-opus: claude-opus-5-5`。
   - `data/rules/dispatch-policy.md:63-116` 的 `levels` 與 `escalation` 直接引用上述類別代號。
   - `data/profiles/ryan/dispatch.md:6-27` 將 `claudeAgent*`、`antigravity*` 實例綁到上述類別；注意 `dispatch-policy.md:194` 還留有過時註解稱 `antigravity_ava`／`antigravity_kai` 無模型可用。
   - `engine/scripts/dispatch.py:54-57, 122-223, 244-276, 494-507` 把 `THINKING`、`CHANNELS` 與 `resolved()`／`check()` 寫在腳本與雙份規則解析中，且會驗證 `agy_model()`。
   - `engine/scripts/homes.py:86-120` 讀取 `~/.t3/userdata/settings.json` 的 `providerInstances` 取得實例 ID 與帳號，但該設定檔**不含可用模型清單**；`data/tools/t3-code.yaml:1-19` 也明確警告 `~/.t3/userdata/statev2.sqlite` 含登入憑證，OmniKit **不可直接讀取**。
   - 定期與網站基底：`engine/scripts/home_watch.py:1-120` 已有 Claude/Codex `SessionStart` 6 小時重試機制；`engine/scripts/weekly.py:25` 提到尚無定期排程 hook；`engine/scripts/build.py` 建置靜態 `_site/`（含 `engine/site/app.js`）；`floorplan/serve.mjs` 已有純 Node 本機 HTTP server（`127.0.0.1:4378`）範例。

2. **T3 Code CLI vs MCP 與 Antigravity CLI 實測結果**：
   - **`t3` CLI（`t3 v0.1.10`）實測無法列出模型與供應商清單**：
     - 實測指令與摘要：
       - `t3 --help`：僅列出 `help, serve, app, pair, auth, environment, browser, project, thread, up, status, service, update, install, uninstall, theme, trace, doctor, policy, triage, connect`。
       - `t3 thread --help`：僅有 `list, start, send, show`。
       - `t3 status --json`：僅回傳本地 daemon 執行狀態／port 等資訊，不含 `providers` 或 `models`。
       - `t3 policy show`：僅印出安全審批政策，不含模型清單。
       - 同步檢查 `t3 doctor --help`、`t3 environment --help`、`t3 project --help`、`t3 app --help`，均無任何列出供應商可用模型或選項的子指令。
   - **`orchestrator_capabilities` MCP 工具實測可完整取得即時清單**：
     - 2026-11-19 實測回傳每個 `providerInstanceId` 的 `driverKind`、`canRunChildTask`、`constraints` 與 `models[]`（含 `id`、`label`、`options[]` 合法範圍與預設值）：
       - `antigravity`：`gemini-4-hydrogen`（`thinking_level` low–xhigh, default high）、`gemini-4-argon`（low–high, default high）、`gemini-4-neon`（low–xhigh, default high）、`claude-opus-5-5`（low–high, default medium）、`claude-sonnet-5-5`（low–high, default high）。
       - `antigravity_ava`、`antigravity_kai`：`gemini-3.8-flash`（low–high, default high）— 證實政策舊註解已過時。
       - `claudeAgent`、`claudeAgent_2`、`claudeAgent_claude_kai`：`claude-opus-5-5`（`effort` low–ultrathink, default medium）、`claude-sonnet-5-5`（default high）、`claude-fable-5-2`（default medium），另含 `ultracode` 與 `fastMode` 布林選項。
       - 未啟用實例（`codex`, `cursor`, `grok`, `opencode`, `fx`, `kiro`, `muse`, `pi`）回傳 `constraints: ["Provider instance is disabled."]`。
   - **Antigravity CLI（`agy models`）**：根據官方文件（`https://antigravity.google/docs/models`），`agy models` 可於終端機查詢 Antigravity 可用模型代碼，適合作為脫離 T3 MCP 時的次要補充來源。

---

### 方案 A（輕量級）：角色別名規則層 ＋ SessionStart 快照比對 ＋ 靜態設定匯出

以最小改動把 `model_classes` 升級為「角色（Role）優先清單」，不引入常駐背景服務，完全沿用 OmniKit 現有檔案與 `SessionStart` 機制。

1. **要改哪些檔案與欄位設計**：
   - `data/rules/dispatch-policy.md`：
     - 將 `model_classes` 改為 `model_roles`（例如 `gemini-strong`、`gemini-fast`、`claude-strong`、`claude-balanced`、`claude-fast`、`antigravity-opus`）。每個 role 不再寫死單一字串，而是宣告「候選排序清單（`candidates`）＋排除標籤／最低思考等級（`min_thinking`）」，例如 `gemini-strong` 依序偏好 `[gemini-4-carbon, gemini-4-neon, gemini-4-hydrogen]`（或依試行設定調整順位），由執行期對照 T3 現有模型清單取第一個可用者。
     - `levels`、`tasks`、`escalation` 全面改引用 `model_roles`。
   - `data/profiles/<name>/dispatch.md`：
     - `instances` 的 `classes` 同步對應 role 名稱；新增選用區段 `workflow_overrides`（例如 `eval: {role: gemini-strong}` 或鎖定特定 `model`），供進階用戶覆寫。
   - `engine/scripts/dispatch.py` 與 `engine/skills/omnikit-dispatch/scripts/run.py`：
     - 新增 `resolve_role(role, instance_id, catalog_path)` 與 `--sync-catalog` 子指令；讀不到快取目錄時，退回各 role 的靜態 fallback 首選並標註「未經即時清單驗證」。
2. **怎麼從 T3 讀現有模型清單**：
   - 主路徑：在任何有接 `t3-code` MCP 的對話（含主線開工時）執行 `orchestrator_capabilities`，將結果正規化存至 `~/.omnikit/dispatch/t3-capabilities-snapshot.json`（只存 `providerInstanceId`、`models`、`options`，絕不碰 `statev2.sqlite`）。
   - 輔助路徑：針對非 T3 環境的純終端機情境，透過 `dispatch.py` 呼叫 `agy models`（或透過 `T3_ACP_MCP_NODE acp-mcp-call orchestrator_capabilities '{}'`，見 T3 Code ACP fallback 機制）更新快照；若 T3 CLI 未來補上 `t3 provider list` 等指令再無縫切換。
3. **定期比對與新舊模型提醒**：
   - 不另開常駐排程，直接掛進 `engine/scripts/home_watch.py`（Claude/Codex `SessionStart` hook，已有 6 小時防抖）。
   - 每次比對新舊快照的 `models[].id` 集合差集：
     - 出現新模型（例如 `gemini-4-neon`）：用名稱前綴／版本規則（`family` + `tier` 關鍵字與支援的 `thinking_level` 範圍）產生建議對應文案，寫入 `~/.omnikit/dispatch/catalog-diff.json` 並於開工摘要顯示「發現新模型 X，建議加入 role Y 候選」。
     - 舊模型消失：若該模型仍被任何 role 優先或 `workflow_overrides` 鎖定，立刻顯示警告與替代建議。
4. **前端進階工作流模型選型整合**：
   - 擴充 `engine/scripts/build.py` 與 `engine/site/app.js`，在現有靜態儀表板新增「工作流模型配置（進階）」分頁：讀取建置時嵌入的 `tasks` / `levels` 與最新 `t3-capabilities-snapshot.json`，提供下拉選單挑選各工作流對應的 role 或具體模型，一鍵複製 `workflow_overrides` YAML 貼回 `data/profiles/<name>/dispatch.md`（或匯出 JSON 下載檔）。
5. **風險與取捨**：
   - 優點：改動最小、零常駐 daemon、無跨目錄權限問題、完全純文字與 Git 可追蹤。
   - 風險：`SessionStart` Hook 僅於開新對話觸發（T3 原生 MCP 不會主動在背景推播，除非手動觸發或等下一次開工）；靜態網頁無法直接寫回本機檔案，進階用戶需複製貼上一次。

---

### 方案 B（中量級）：獨立 Model Catalog 鎖定檔 ＋ 能力矩陣解析 ＋ `schedule_task` 定期巡檢 ＋ 本機設定 UI

效法 **Continue (`roles` + `capabilities`)**、**OpenCode (`models.dev` + 可用性過濾)** 與 **Renovate 式建議鎖定檔** 的架構，同時復用 `floorplan/serve.mjs` 的本機 Server 模式提供真正可存檔的前端選型 UI。

1. **要改哪些檔案與欄位設計**：
   - 新增規格層 `~/.omnikit/dispatch/catalog.json`（由系統自動更新，**不進 Git 版控避免污染工作區**）與建議鎖定檔 `data/rules/model-catalog-lock.yaml`（可選進 Git，記錄每個模型推斷的能力標籤：`provider_family`、`tier`、`supports_thinking`、`cost_tier`、`deprecation_status`）。
   - `data/rules/dispatch-policy.md`：
     - `model_roles` 改用「宣告式需求（`requirements`）＋偏好多樣性」，例如：
       - `gemini-strong`: `{family: gemini, min_tier: pro-or-mid, require_options: [thinking_level: high+], prefer_newest: true}`
       - `claude-balanced`: `{family: claude, tier: sonnet, effort: high}`
     - `tasks` 明確定義每個工作流階段（如 `research`、`implement`、`second_opinion`、`quick_edit`）的預設 role。
   - `data/profiles/<name>/dispatch.md`（或獨立 `~/.omnikit/dispatch/workflow-overrides.yaml`）：記錄使用者在前端對個別工作流鎖定的 `{instance, model, thinking_level}`。
   - `engine/scripts/dispatch.py`：拆出 `catalog.py` 模組負責「實例可用模型 × 規格能力 × 使用者覆寫」三層解析與 diff 計算。
2. **怎麼從 T3 讀現有模型清單**：
   - 優先透過 `orchestrator_capabilities`（或無 MCP 時用 `T3_ACP_MCP_NODE` CLI bridge `acp-mcp-call orchestrator_capabilities '{}'`）拉取即時資料；同時整合 `agy models` 作為 Antigravity 帳號在未開啟 T3 MCP 時的交叉驗證來源。
   - 注意邊界：嚴格遵守 `data/tools/t3-code.yaml:13-19`，不解析 `statev2.sqlite`；若上述兩管道皆無法呼叫，回退讀取最近一次有效的 `~/.omnikit/dispatch/catalog.json` 並標註資料時間戳。
3. **定期比對與新舊模型提醒**：
   - 採用 **雙引擎巡檢**：
     1. 利用 T3 Code 內建 `schedule_task` MCP 建立週期性唯讀巡檢任務（例如每週一次或每日一次），呼叫 `orchestrator_capabilities`，並連網抓取 **Models.dev**（`https://models.dev/api.json`【待驗證正確 JSON 端點路徑】／模型頁面）與 **deprecations.info**（`https://deprecations.info/v1/feed.json`）交叉比對定價、推理支援與已知下架日期。
     2. 產生結構化 Diff 報告（含「新增模型建議歸入哪個 role」、「已消失模型影響哪些工作流」、「即將淘汰倒數提醒」），寫入 `~/.omnikit/status` 狀態板（或 `NOW.md` 待確認區），等待使用者拍板確認後才寫入覆寫／政策（Renovate 原則：不靜默自動切換）。
   - 在未使用 T3 排程時，保留 `home_watch.py` 作為開工時（>24 小時未檢）補檢備援。
4. **前端進階工作流模型選型整合**：
   - 參照 `floorplan/serve.mjs` 模式建立極輕量本機設定頁（`127.0.0.1:<port>`，或直接整合為 `floorplan`／OmniKit Dashboard 的一個本地 API 分頁，搭配 `/omnikit-dispatch ui` 啟動）：
     - 左側顯示所有工作流（`prework`、`implement`、`review`、`second_opinion`、`research` 等）；
     - 右側下拉選單只列出透過 T3 實時查到「目前有帳號且啟用」的模型，並標示 `New`、`Deprecated` 徽章與支援的 `thinking_level` / `effort` 滑桿（自動阻擋違反個人規則的選項，例如禁止 Gemini 設定 `low`/`medium`）；
     - 儲存時直接寫入 `~/.omnikit/dispatch/workflow-overrides.yaml`，立即生效於下一次 `run.py show` / `dispatch.py`。
5. **風險與取捨**：
   - 優點：兼顧動態發現、智慧建議、Renovate 式人類把關，且前端選型真正可點擊保存，不用手寫 YAML。
   - 風險：需要維護 `catalog.py` 解析邏輯與本機 HTTP 設定介面；若跨多台電腦工作，放在 `~/.omnikit/` 的覆寫檔需決定是否同步至 `omnikit-status` 私有 repo。

---

### 方案 C（重量級）：本機虛擬模型轉接層（Mini-Gateway / Wrapper）＋ 自動健康度／額度感知路由 ＋ 工作流矩陣控制台

參考 **LiteLLM (`model_group_alias` + health/cooldown)**、**Bifrost / OmniRoute** 與 **Goose (`Lead/Worker` failure threshold)**，在派工層之下建立一層虛擬模型轉接與額度感知路由引擎。

1. **要改哪些檔案與欄位設計**：
   - `data/rules/dispatch-policy.md` 徹底退居「高階意圖合約」：只定義 role（`strong_reasoning`、`fast_execution`、`second_opinion_cross_vendor`）與「禁止單一廠商同時寫與審」等不變量。
   - 新增獨立子系統 `engine/dispatch_router/`（或獨立本機服務）：維護虛擬模型別名表、配額冷卻狀態機（cooldown registry）、各工作流 DAG 節點對應表，以及健康歷史紀錄（`runs` + `429/403` 失敗率）。
   - `engine/scripts/dispatch.py`、`omnikit-dispatch/run.py`、`t3` 派工封裝改為對接該路由層回傳的最終 `{providerInstanceId, model, options}`，甚至為支援 OpenAI/Anthropic `BASE_URL` 的外部工具（如 OpenCode、Aider、Codex）提供本機代理端點。
2. **怎麼從 T3 讀現有模型清單**：
   - 路由 Daemon 啟動時透過 `T3_ACP_MCP_NODE acp-mcp-call orchestrator_capabilities '{}'`（或等 T3 未來提供穩定本機 RPC/CLI）建立實例能力圖譜，並週期性探測各帳號可用性與模型支援清單。
   - 同樣不可直接讀 `statev2.sqlite`；對於 Antigravity CLI 則結合 `agy models` 與歷史執行回應做雙重驗證。
3. **定期比對與新舊模型提醒**：
   - 背景 Daemon（或每小時／每日排程）結合三路來源：T3 實測清單 × `models.dev` 規格價格表 × `deprecations.info` 淘汰 Feed。
   - 除了發出新／舊模型變更告警外，還能在測試集／試行期（對應 `dispatch-policy.md:242-250` 的 `trials` 機制）自動進行 shadow logging 或 A/B 抽樣比對，統計新模型（例如 `gemini-4-neon`）的通過率與耗時，數據達標再建議晉升預設候選。
4. **前端進階工作流模型選型整合**：
   - 建置完整互動式本地 Web 控制台（例如 React／靜態 SPA ＋ 本機後端 API），呈現「工作流 × 任務級別 × 模型／帳號矩陣」，支援：
     - 拖拉或編排主要模型與 1–3 層 fallback 鏈；
     - 即時顯示各帳號實例冷卻狀態、本週各家使用量（整合 `run.py stats`）、與外部模型淘汰警告；
     - 測試單一角色解析預覽（輸入 `task + level` 即時模擬會派到哪個帳號、模型與思考等級）。
5. **風險與取捨**：
   - 優點：自動化程度最高，能把配額切換、跨廠商審查互斥、試行 A/B 測試、前端矩陣選型一次整合。
   - 風險與成本：**維護複雜度極高**。T3 Code 的各 driver（`claudeAgent`、`antigravity-acp`）各自有專屬認證與參數格式，並非全部能靠 HTTP proxy 統一攔截；一旦多一層本機 Daemon，可能增加 T3 派工失敗的排查難度，也與 OmniKit 目前「輕量規則＋腳本驅動」的哲學有較大張力。

### 三方案核心比較摘要（供主線決策參考，不代拍板）

| 比較面向 | 方案 A（輕量級） | 方案 B（中量級） | 方案 C（重量級） |
| :--- | :--- | :--- | :--- |
| **核心機制** | 角色優先清單 ＋ SessionStart 差集 | 獨立 Catalog ＋ 能力矩陣 ＋ 本機設定 UI | 本機虛擬路由引擎 ＋ 配額狀態機 ＋ 矩陣控制台 |
| **改動範圍** | 政策／profile／`dispatch.py`／靜態頁 | 新增 `catalog.py`、T3 排程、本地 UI server | 新增完整路由器子系統與互動後端 |
| **選型 UI 體驗** | 靜態頁產生 YAML（需手動貼回） | 本機網頁下拉／滑桿選擇並一鍵存檔 | 完整矩陣編排＋Fallback 鏈＋預覽模擬器 |
| **外部來源整合** | 僅 T3 快照（選配 `agy models`） | T3 快照 ＋ `models.dev` ＋ `deprecations.info` | 上述全部 ＋ 試行 A/B 統計與健康度追蹤 |
| **主要風險** | 無背景主動通知；需手動貼回設定 | 需維護本機 server 生命週期與兩地同步 | 過渡設計風險高；與 T3 原生驅動耦合不易除錯 |

---

## 三、調研紀錄（飽和式檢索與驗證證據）

### 1. 納排準則
- **納入對象**：具備「模型邏輯別名／角色映射、能力／成本路由、新模型自動發現、模型淘汰／目錄變更偵測告警、或多工作流模型選型 UI」任一實質機制的開源專案、商業閘道器／路由服務、開發框架 SDK 或資料標準。
- **排除對象**：單純的傳統機器學習模型註冊庫（如 MLflow/DVC/物理動力學建模如 PySINDy）、企業資料目錄（如 Apache Gravitino）、僅提供單一模型聊天介面的套殼 UI，以及無具體工具實體的文章列表。

### 2. 關鍵字組與詞彙擴展軌跡（共 12 組）

依據 `engine/skills/omnikit-research/SKILL.md` 執行 `sweep.py` 飽和式檢索，詞彙從各輪結果中抽取擴展（例如由 `model_group_alias`／`fallback` 擴展到 `registry`、`coding agent profile`、`deprecation watcher`、`virtual catalog sync`、`model picker ui`、`capability matrix`、`provider discovery polling`）：

| 組別 | 關鍵字組 | 本組新增數（總／★1000+） | 已覆蓋管道 |
| :---: | :--- | :---: | :--- |
| 1 | `model alias fallback routing` | 36（★1000+：18） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, web-zh |
| 2 | `llm model router registry` | 48（★1000+：18） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 3 | `coding agent model profile` | 62（★1000+：11） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related |
| 4 | `model catalog deprecation watcher` | 18（★1000+：1） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh |
| 5 | `virtual model catalog sync` | 18（★1000+：2） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 6 | `model picker ui workflow` | 25（★1000+：1） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 7 | `llm model alias configuration` | 10（★1000+：3） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, web-zh |
| 8 | `ai model deprecation alert` | 22（★1000+：0） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 9 | `agent role model assignment` | 11（★1000+：5） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 10 | `model capability fallback matrix` | 24（★1000+：0） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 11 | `llm model switcher profile` | 34（★1000+：0） | github-topic, github-keyword, npm, exa, web-en, awesome, skills-sh, mcp-registry, hn |
| 12 | `provider model discovery polling` | 21（★1000+：0） | github-topic, npm, exa, web-en, github-keyword, awesome, skills-sh, mcp-registry, hn |

### 3. 停止條件與 `sweep.py status` 實測結果

執行 `uv run engine/skills/omnikit-research/scripts/sweep.py status "%TEMP%\model-roles-ledger.json" --min-stars 1000` 完整統計輸出如下：

```text
總共 329 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 3 組沒有新的（要 3 組）：可以停，報告寫「長尾未飽和」並附上面兩種連續數
```

- **停止理由**：已達 **長尾未飽和** 停止條件（全體候選連續 0 組沒有新名字、但 `★1000` 以上 GitHub repo 於第 10、11、12 組已**連續 3 組沒有新名字**），同時亦剛好觸及第 12 組上限。代表業界主流千星級架構（閘道器、Coding Agent、工作流框架與標準目錄）皆已完整涵蓋，其餘新增多為個人微調外掛或小型 CLI 腳本。

### 4. 查不到的管道與工具限制
- **Product Hunt**：`sweep.py` 直接抓 Product Hunt API 需要開發者 token，除第 3 組搭配網頁檢索確認相關詞彙外，其餘組別主要以 Exa / Web 搜尋補齊商業產品（如 OpenRouter、Martian、NotDiamond、MindStudio）。
- **MCP Registry / skills.sh**：兩者偏向子字串搜尋，包含較多名稱含 `model`／`provider` 但實為領域資料模型（如醫療／不動產）之雜訊，已依納排準則人工過濾。
- **T3 Code CLI (`t3 v0.1.10`)**：經實測 `t3 --help`、`t3 status --json`、`t3 policy show`、`t3 thread --help`、`t3 environment --help`，本機 CLI 確無輸出各實例可用模型清單的指令，需仰賴 MCP `orchestrator_capabilities`（或 `T3_ACP_MCP_NODE` bridge）。

### 5. GitHub `sweep.py verify` 實測紀錄（查證日期：2026-11-19 `gh api`）

以下僅節錄比較表引用之代表性倉庫實測結果（完整 37 筆均保存於任務紀錄）：

| Repo | Stars | License | Archived | Last Pushed |
| :--- | :---: | :--- | :---: | :--- |
| `anomalyco/opencode` | 227,906 | MIT | false | 2026-11-19 |
| `anthropics/claude-code` | 156,227 | 無（專有授權） | false | 2026-11-19 |
| `langchain-ai/langchain` | 149,875 | MIT | false | 2026-11-19 |
| `openai/codex` | 135,832 | Apache-2.0 | false | 2026-11-19 |
| `OpenHands/OpenHands` | 93,810 | MIT | false | 2026-11-19 |
| `cheaper-inference/OmniRoute` | 88,768 | MIT | false | 2026-11-19 |
| `cline/cline` | 71,762 | Apache-2.0 | false | 2026-11-19 |
| `BerriAI/litellm` | 63,526 | NOASSERTION（倉庫 LICENSE 為 MIT） | false | 2026-11-19 |
| `crewAIInc/crewAI` | 61,091 | MIT | false | 2026-11-19 |
| `aaif-goose/goose` | 56,779 | Apache-2.0 | false | 2026-11-19 |
| `Aider-AI/aider` | 50,176 | Apache-2.0 | false | 2026-05-22 |
| `can1357/oh-my-pi` | 39,454 | MIT | false | 2026-11-19 |
| `continuedev/continue` | 36,515 | Apache-2.0 | false | 2026-11-18 |
| `mastra-ai/mastra` | 29,630 | NOASSERTION | false | 2026-11-19 |
| `charmbracelet/crush` | 29,133 | NOASSERTION | false | 2026-11-19 |
| `vercel/ai` | 28,079 | NOASSERTION | false | 2026-11-19 |
| `RooCodeInc/Roo-Code` | 24,236 | Apache-2.0 | **true** | 2026-05-15 |
| `renovatebot/renovate` | 23,181 | AGPL-3.0 | false | 2026-11-19 |
| `pydantic/pydantic-ai` | 21,283 | MIT | false | 2026-11-19 |
| `langchain-ai/langchainjs` | 18,353 | MIT | false | 2026-11-18 |
| `Portkey-AI/gateway` | 13,415 | MIT | false | 2026-05-25 |
| `simonw/llm` | 12,781 | Apache-2.0 | false | 2026-11-17 |
| `maximhq/bifrost` | 9,762 | Apache-2.0 | false | 2026-11-19 |
| `anomalyco/models.dev` | 7,687 | MIT | false | 2026-11-19 |
| `katanemo/plano` | 7,119 | Apache-2.0 | false | 2026-10-24 |
| `agentgateway/agentgateway` | 6,299 | Apache-2.0 | false | 2026-11-19 |
| `mostlygeek/llama-swap` | 6,273 | MIT | false | 2026-11-19 |
| `lm-sys/RouteLLM` | 5,719 | Apache-2.0 | false | 2024-08-10 |
| `UKGovernmentBEIS/inspect_ai` | 3,287 | MIT | false | 2026-11-19 |
| `theopenco/llmgateway` | 1,750 | NOASSERTION | false | 2026-11-19 |
| `Portkey-AI/models` | 146 | MIT | false | 2026-11-18 |
| `nekko-labs/nekko-agent` | 12 | MIT | false | 2026-11-19 |
| `bhav09/chowkidar` | 9 | 無 | false | 2026-06-29 |
| `GooDAnDReaDY/dsh-model-sync` | 7 | MIT | false | 2026-11-14 |
| `quora/model-deprecation-tracker` | 4 | 無 | false | 2026-11-18 |
| `AppliedBenchmark/sunset` | 2 | Apache-2.0 | false | 2026-11-18 |
| `dhangerkapil/foundry-model-catalog-watcher` | 0 | MIT | false | 2026-10-05 |

---

## 四、Gemini 4 Neon 與 Gemini 4 Argon【待驗證】一手查證結果

以下均於 **2026-11-19** 查核 Google 官方文件與 Antigravity 官方頁面。

### (a) Gemini 4 Neon（`gemini-4-neon`）官方定位、定價與額度消耗

1. **官方定位**（來源：[Gemini 4 Neon in Google Antigravity Blog](https://antigravity.google/blog/gemini-4-neon-in-google-antigravity), 2026-11-18）：
   - 官方原文：*"Neon hits the sweet spot between Gemini 4 Carbon for your deepest long-horizon projects and Gemini 4 Hydrogen for rapid everyday execution."*
   - 支援四段思考等級：`Low`、`Medium`、`High`（預設）、`Extra High`。
   - 同步推出 **Orchestrator (Neon)**：單一會話內自動由 `Neon` 負責規劃／審查／除錯恢復，將日常檔案編輯、套件更新與測試交給 `Hydrogen` 執行。

2. **Gemini API 官方定價比較**（來源：[Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing), Standard Paid Tier，每百萬 tokens）：

| 模型 ID | Free Tier | Input 價格 | Output 價格（含 thinking） | Context Caching（僅隱式） | 相對 Hydrogen 倍數 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `gemini-4-hydrogen` | 有（有限額度） | USD 1.50 | USD 7.50 | USD 0.075 | 1.0 倍（基準） |
| `gemini-4-neon` | **無** | **USD 3.00** | **USD 15.00** | **USD 0.15** | **正好 2.0 倍** |
| `gemini-4-argon` | 無 | USD 2.00（至 2026-11-30）<br>USD 4.00（2026-12-01 起） | USD 10.00（至 2026-11-30）<br>USD 20.00（2026-12-01 起） | USD 0.10（至 2026-11-30）<br>USD 0.20（2026-12-01 起） | 1.33 倍 → 2.67 倍 |
| `gemini-4-carbon` | 無 | USD 2.00（至 2026-11-30）<br>USD 4.00（2026-12-01 起） | USD 10.00（至 2026-11-30）<br>USD 20.00（2026-12-01 起） | USD 0.10（至 2026-11-30）<br>USD 0.20（2026-12-01 起） | 1.33 倍 → 2.67 倍 |

3. **Antigravity 方案資格與額度消耗**（來源：[Antigravity Pricing](https://antigravity.google/pricing)、[Antigravity Plans](https://antigravity.google/docs/plans/)）：
   - **方案資格**：Neon 提供給付費 **Google AI Pro**（註記 `[2]`：含符合資格裝置試用）、**Google AI Ultra** 與 **Gemini Enterprise**，**不含 Individual Free 方案**（與實測 `antigravity_ava`／`antigravity_kai` 看不到 Neon 一致；另注意 Hydrogen 與 Claude 5.5 標註 `[3]` 僅限非試用之付費 Pro）。
   - **Antigravity 實際額度消耗比例 → 【待驗證】（無官方公開數字）**：
     - Antigravity Plans 與 Pricing 頁面僅說明 *"Rate limits and AI credit pools vary by plan and task complexity"*（Pro/Ultra 採每 5 小時刷新＋每週上限），**並未公布 Neon 相對於 Hydrogen 扣除多少倍的訂閱池額度**。
     - 唯一一手效能與成本數據來自 Neon 官方部落格：在預設 `High` thinking 等級下，Neon 每任務成本比 Carbon 低 32%（*"shows a 32% lower cost per task than Carbon"*）；另外官方建議搭配 `Orchestrator (Neon)` 混合 Hydrogen 執行以延長配額。民間社群有回報單開 Neon 比 Hydrogen 消耗配額更快，但因無官方倍率與實測記錄，維持標註 **`【待驗證】`**。

### (b) Gemini 4 Argon（`gemini-4-argon`）是否已被宣布淘汰／何時下架

- **一手查證結論：尚未宣布淘汰，也無排定下架日期**（來源：[Gemini API Deprecations](https://ai.google.dev/gemini-api/docs/deprecations), 2026-11-19 查證）。
- **官方原文表格紀錄**（`#gemini-4-models` 區段）：
  - **Model**：`gemini-4-argon`
  - **Release date**：`October 13, 2026`
  - **Shutdown date**：**`No shutdown date announced`**
  - **Recommended replacement**：（空白，未指定替代模型）
- **多源交叉驗證現況**：
  1. [Gemini API Models](https://ai.google.dev/gemini-api/docs/models) 與 [Antigravity Models](https://antigravity.google/docs/models) 仍正常列出 `gemini-4-argon`。
  2. [Antigravity Pricing](https://antigravity.google/pricing) 仍將 `Gemini 4 Argon` 與 `Orchestrator (Argon)` 列於 Pro、Ultra 與 Business 方案模型清單中（對照該頁註記 `[4]` 僅對舊版協力廠商／部分模型標註於 2026-11-18 移除）。
  3. 2026-11-19 實測 T3 `orchestrator_capabilities` 顯示 `antigravity` 實例依然同時提供 `gemini-4-argon` 與 `gemini-4-neon`。
- 若有任何說法指稱「Neon 已在消費端 app 或特定介面取代 Argon 顯示位置」，目前查無 Gemini API 或 Antigravity 官方淘汰公告佐證，標註 **`【待驗證】`**。

---

## 五、併案：Antigravity Orchestrator 模式候選角色比較與小實測（2026-11-19）

Ryan 2026-11-19 指示將 Antigravity 的 **Orchestrator 模式**（`gemini-pro-orchestrator-neon`：Neon 規劃與審查、平行派 Hydrogen 子代理實作）併入本調研，評估其作為分派政策中一個候選角色（例如 `gemini-orchestrator`：「大任務的規劃＋平行實作」）的定位，並實測比較與單跑 `gemini-4-neon-high` 的差異。完整實測腳本與原始數據見 `data/evals/2026-11-19-orchestrator-bench/REPORT.md` 與 `summary.json`。

### 1. 本機能力與參數實測（一手確認）

- `agy models`（2026-11-19 本機 Ryan 帳號）實際列出 `gemini-pro-orchestrator-neon`（`Orchestrator (Neon)`）與 `gemini-pro-orchestrator-g1-pro`（`Orchestrator (Argon)`），以及 `gemini-4-neon-high` 等；但 T3 的 `antigravity` 實例目前尚未在 `orchestrator_capabilities` 中列出 Orchestrator，因此現階段只能透過 `agy_cli` 管道呼叫。
- 對 `gemini-pro-orchestrator-neon` 傳入 `--effort high` 實測失敗（exit code 1）：
  `invalid model selection (--model "gemini-pro-orchestrator-neon" --effort "high"): --effort is not supported for model "gemini-pro-orchestrator-neon"`。
- `antigravity_ava`、`antigravity_kai`（印度 Jio 方案）無 Gemini 4 系列，預期無法使用 Orchestrator（尚未以兩帳號實測，標 **`【待驗證】`**）。

### 2. 同題對照小實測（`gemini-pro-orchestrator-neon` vs `gemini-4-neon-high`，n = 1）

兩組於各自乾淨沙盒依同一份 `SPEC.md` 與真實 T3／`agy` 樣本，實作純 Python 標準函式庫套件 `model_router`（3 個獨立模組 `catalog.py`、`resolver.py`、`cli.py` ＋ `__init__.py` ＋ `unittest`），再以兩組不可見的 14 項獨立客觀驗收腳本（`verify_bench.py`）評分：

| 指標 | Orchestrator (Neon) | Gemini 4 Neon (High) | 差異（Orchestrator 對 Neon High） |
| :--- | :---: | :---: | :--- |
| 獨立驗收通過數 | 14 / 14 | 14 / 14 | 持平（自寫測試 18 對 19；總行數 949 對 952） |
| 牆鐘耗時 / CLI 耗時 | 213.46s / 208.81s | 247.89s / 244.10s | 快 13.9% / 14.5% |
| 淨 agent LLM 呼叫數（扣監控） | 6 次 | 7 次 | 少 1 次 |
| `input_tokens` | 99,276 | 169,591 | 少 41.5%（-70,315） |
| `output_tokens` | 22,077 | 18,859 | 多 17.1%（+3,218） |
| `thinking_tokens` | 7,982 | 7,947 | 幾乎一致（+0.4%） |
| `cache_read_tokens` | 143,934 | 107,474 | 多 33.9%（+36,460） |
| `total_tokens` | 121,353 | 188,450 | 少 35.6%（-67,097） |

- **機制觀察與誠實限制**：
  1. 檢視 `log_orchestrator_neon.txt`，Orchestrator 啟動後先進入 Plan Mode 規劃再呼叫 `exit_plan_mode` 批次寫檔，**本題規模（5 檔約 950 行）只建立 1 個 conversation，並未觸發平行 Hydrogen 子代理**；省下 35.6% `total_tokens` 來自少 1 輪呼叫與較高快取命中。
  2. 雖然不可指定 `--effort`，其 `thinking_tokens`（7,982）與 `gemini-4-neon-high`（7,947）幾乎一致，觀察推論內部預設已屬 high 級別思考量。
  3. **仍標【待驗證】**：真正跨多目錄大任務觸發平行 Hydrogen 子代理時，子代理 token 是否計入 CLI `usage` 回傳、總體是否省 token，以及 Antigravity 週額度實際扣除比例（相較單跑 Neon High 或 Hydrogen）。

### 3. 候選角色定位比較：Antigravity Orchestrator vs OmniKit 自派子任務

| 比較面向 | Antigravity Orchestrator（候選角色 `gemini-orchestrator`） | OmniKit 自派子任務（主控＋子代理） |
| :--- | :--- | :--- |
| **跨廠商寫審分離** | 不支援（全在 Google Gemini 體系內：Neon＋Hydrogen） | 支援（Claude 定案＋Gemini 唯讀審查，或反之） |
| **派工粒度與規則約束** | 黑盒自行決定是否拆子代理、不可設 `--effort`、無法對子步驟套用不同規則 | 可逐個子任務指定模型、thinking 程度、worktree 隔離與交付驗收條件 |
| **T3 整合與可觀測性** | T3 清單尚未納入，僅能走 `agy_cli` 單次交付 | 完整整合 `delegate_task`、`t3_thread_launch`、T3 側邊欄與自動 settle |
| **多檔原型開發效率** | 內建 Plan Mode＋自動平行實作，免主控手寫多份 brief；小實測快 13.9%、total_tokens 少 35.6% | 主控需拆包、撰寫 brief 與逐一驗收整合，編排開銷較高 |
| **額度與帳號調度** | 綁定單一付費 Pro/Ultra 帳號（Ryan）；ava／kai 預期不可用【待驗證】 | 可跨帳號與跨供應商輪替調度（Ryan／retis／Kai／ava／kai） |
| **三方案納入方式** | 方案 A／B／C 皆可將 `gemini-orchestrator` 設為**選配角色**（僅經 `agy_cli` 解析 `agy models` 啟用），專責非高風險、無須跨家寫審分離的「大範圍多檔原型／測試／文件實作」；完成後仍由主線主控驗收 | 維持為 OmniKit 核心編排架構，承擔高風險任務（帳務／風控／下單／設計決策）、跨廠商第二意見審查與需 worktree 隔離的並行工作包 |

