# 多使用者訂閱組合之模型角色分配、降級與規約感知調研報告

- 調研日期：2026-11-22
- 產出位置：`data/evals/2026-11-22-multi-user-model-roles-research.md`
- 關聯基準：`data/evals/2026-11-19-model-roles-research.md`（方案 B 與 Ryan 拍板定案）、`data/evals/2026-11-22-gemini-pro-pool.md`、`data/rules/dispatch-policy.md`、`engine/skills/omnikit-research/SKILL.md`

---

## 摘要與核心結論

1. **從單人廠牌別名走向多使用者能力角色**：目前業界成熟工具已普遍將角色抽象與底層廠牌脫鉤（如 `oh-my-openagent` 的 Agent/Category 鏈、`Continue` 的 `roles` + `capabilities`、`OpenRouter` 的 `auto` / `auto-code`、`Kilo Code` 的 `kilo-auto/frontier` 與 `efficient`）。OmniKit 現有 `dispatch-policy.md` 與 2026-11-19 Plan B 仍保留 `gemini-strong`、`claude-strong` 等廠牌前綴角色名，應改為純職責導向角色，才容得下只有 Claude、只有 ChatGPT/Codex、只有 Copilot/Cursor 或純 API 金鑰的各類使用者。
2. **「規約限制（ToS）」必須與「技術可行（API 可通）」分開建模**：本次飽和式調研最關鍵的實證來自 `cheaper-inference/OmniRoute`（★89,350）——它在模型目錄旁獨立維護 `FREE_TIER_TOS` 資料表，將禁止第三方代理或自動輪換的供應商（如 `agy` / `antigravity`、`kiro`、`amazon-q`）顯式標為 `avoid` 並預設排除於自動路由之外，將條款模糊者（如 Copilot endpoint）標為 `ambiguous`。這可直接解決 `2026-11-22-gemini-pro-pool.md` 發現的 Antigravity 消費方案規約衝突。
3. **單一廠牌與缺家降級是實際多用戶剛需**：`oh-my-openagent` 在設計上區分「必須有指定模型才能開的軌道（`requiresAnyModel` gate）」與「單一供應商專屬降級表（`isOpenAiOnlyAvailability`）」，以及「沒買高階訂閱時自動降階思考量（非 `isMaxPlan` 時 `unspecified-high` 降為 `unspecified-low`）」。OmniKit 缺乏某家廠商時，「寫審跨廠牌」無法強制成立，需有明確的降級狀態機（跨廠牌自動 → 跨廠牌手動提示 → 同廠牌獨立新 Context 審查），而非直接報錯或靜默失靈。
4. **雙階段故障處理與失敗案例的借鏡**：`OpenClaw`（★394,968）明確拆開「先同供應商輪帳號（僅限認證/配額/方案類錯誤），再跨模型備援（未知/下架模型則直接跳過輪帳號）」且讓互動對話插隊優先於背景審查；`Kilo Code` 對自訂模型池做隨選基準驗證（`Benchmarking` / `Ready` / `Failed`）；相對地，`Cursor Auto` 因完全隱藏實際底層模型而遭透明性批評，`Goose` 曾主打的 `Lead/Worker`（`GOOSE_LEAD_FAILURE_THRESHOLD`）則已於官方文件正式標註 Outdated 並移除。

---

## 一、業界與開源工具六面向比較表

以下涵蓋題目指定的 13 項起點工具，並納入本次飽和式調研發掘的高星數／高相關代表專案（`OmniRoute`、`OpenClaw`、`9Router`、`ClawRouter`、`Manifest`、`CLIProxyAPI`、`Amp`、`Magpie`）。GitHub 星數與授權皆於 **2026-11-22** 以 `gh api`（`sweep.py verify`）實測；無一手原始碼或官方文件佐證的項目一律標註 `【待驗證】`。

### (A) Coding Agent 與多代理編排層

| 工具（來源／星數） | 1. 怎麼知道使用者有哪些訂閱或模型 | 2. 角色怎麼定義與缺某家時如何降級 | 3. 模型能力資料來源與保持最新 | 4. 方案/規約限制資料化、稀缺加權、帳號輪換 | 5. 依使用結果回饋調整（成功率/429/試用期） | 6. 怎麼向使用者說明選型原因 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **oh-my-openagent**（原 `oh-my-opencode`，[code-yeongyu/oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent)，★71,042，NOASSERTION，2026-11-22 gh api） | 安裝時 CLI 問或帶參數（`--claude=no\|yes\|max20`、`--openai`、`--gemini`、`--copilot`、`--opencode-zen`、`--zai-coding-plan` 等）；執行期讀連線供應商、`availableModels` 與 `request-auth.ts` 憑證探測 | 以無廠牌 **Agent 角色**（`sisyphus`、`hephaestus`、`oracle`、`librarian`、`explore`）與 **Task Category**（`ultrabrain`、`deep-*`、`quick`、`unspecified-high/low` 等）配有序 `fallbackChain`。強依賴特定家族者設 `requiresAnyModel` gate 沒可用模型就隱藏該軌道；非 `isMaxPlan` 時 `unspecified-high` 降為 `unspecified-low`；純 OpenAI 連線觸發 `isOpenAiOnlyAvailability` 專屬覆寫；全無退回 `opencode/gpt-5-nano` | 四層解析：連線供應商即時 metadata -> 內建 `models.dev` 快照（GitHub Actions 排程 `refresh-model-capabilities.yml` 發 PR 更新） -> 相容別名表 `model-capability-aliases.ts` -> 啟發式推斷，搭配 guardrail 測試 | `fallback-lane-policy.ts` 將 `openrouter`、`opencode`、`vercel` 排除出預設鏈；`builtin-profiles.ts` 標明特定模型限訂閱與直連 API；有靜態供應商順位但無動態額度稀缺加權；`credentialRotationPolicy` 預設允許同家多憑證輪換（可於 `models.json` 關掉） | `provider-exhaustion-fallback-policy.ts` 分類 `quota_exceeded` 觸發會話內 `retry.fallbackChains`；**無**依長期任務成功率自動重排角色順位（靠開發者實測與 PR 調整） | 啟動由 `notice.ts` 印出選定模型、跳過的 rungs 與認證失敗原因；`omo doctor --models` 逐項顯示各角色與 category 解析鏈與覆寫診斷 |
| **oh-my-opencode-slim**（[alvinunreal/oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim)，★10,309，MIT，2026-11-22 gh api） | 沿用 OpenCode 已連線供應商與設定檔預設（preset），亦支援經 ACP 接入 Claude Code 作為子代理 | 以專業子代理團隊定義角色（Orchestrator、Oracle、Explorer、Fixer 等）；明確提示模型陣容變動快，範例 preset 僅供靈感、需依自己擁有的模型自建與微調 | 依賴 OpenCode 底层目錄（`models.dev`），無獨立自動化能力維持管線 | 預設推薦結合外部免費/聚合閘道（README 直接推薦搭配 OmniRoute 處理配額與 fallback）；本身不做 ToS 資料庫、稀缺加權或多帳號輪換 | 無內建回饋自調；依賴底層閘道或手動改設定 | 透過設定檔與編排日誌檢視指派的子代理與模型 |
| **OpenCode**（[anomalyco/opencode](https://github.com/anomalyco/opencode)，★228,375，MIT）＋ **Models.dev**（[anomalyco/models.dev](https://github.com/anomalyco/models.dev)，★7,707，MIT，2026-11-22 gh api） | `/connect` 存憑證於 `~/.local/share/opencode/auth.json`，並讀 `opencode.json` provider 設定，執行期過濾出已連線可用的模型 | 內建 `build`/`plan` 等 agent 與自訂 command 可個別覆寫 `model`/`small_model`/`variant`；不強制寫審分離，也不主動依訂閱組合自動重算角色分工 | 直接消費 **Models.dev**（`packages/core/script/models-snapshot.ts` 建置快照＋線上同步），收錄 100+ 供應商模型定價、推理、工具呼叫與上下文規格 | 無方案 ToS 風險資料、無額度稀缺加權；刻意保持單會話模型穩定，原生不做自動多帳號輪換或 429 跨家備援（交給外掛如 `opencode-model-fallback`） | 無原生依 429／成功率自動調權重 | TUI `/models` 列出已連線供應商與規格；無主動角色分工推薦說明 |
| **Continue**（[continuedev/continue](https://github.com/continuedev/continue)，★36,535，Apache-2.0，2026-11-22 gh api） | 讀取使用者 `config.yaml` 宣告的 `models`（BYOK 或 Hub 託管），對每個模型做能力自動偵測 | **Role × Capability** 宣告：`roles`（`chat`、`autocomplete`、`edit`、`apply`、`embed`、`rerank`、`summarize`）＋ `capabilities`（`tool_use`、`image_input`）。某職責未專屬指定時回退至宣告該 role 的可用模型；無單廠牌審查替代規則 | 來自 `core/llm/toolSupport.ts` 啟發規則與 `@continuedev/llm-info` 套件；使用者可在 YAML 額外新增能力（僅能追加、無法覆寫內建判斷） | 無方案 ToS 資料、無額度稀缺加權、無同廠牌多帳號輪換 | 無線上使用回饋自動調參 | IDE 側邊欄按 Role 下拉只顯示符合該 role 的模型；不具 `tool_use` 者不允許進 Agent 模式 |
| **Aider**（[Aider-AI/aider](https://github.com/Aider-AI/aider)，★50,211，Apache-2.0，2026-11-22 gh api） | 依 CLI 參數 `--model`、環境變數 API keys 與設定檔決定主模型，再從本地對照表推斷輔助模型 | 固定三功能槽位：`main model`（規劃/對話）、`editor model`（`--architect` 模式下套用編輯 diff）、`weak model`（commit 訊息/摘要）。`model-settings.yml` 替各主模型預配預設 `weak_model_name`；缺或單一模型時退回 `self` | 依賴 **LiteLLM `model_prices_and_context_window.json`** 快照（定價/上下文）＋ 本機維護的 `aider/resources/model-settings.yml`（實測 `edit_format`、`use_repo_map` 等） | 無訂閱 ToS 規則、無額度稀缺加權、無多帳號輪換 | 無線上回饋學習；啟動時依 `model-settings.yml` 對未知或不相容設定印出 `Model warnings` | 啟動摘要與 `/model` 清楚印出 `Main model`、`Weak model`、`Editor model` 與 `edit_format` |
| **Claude Code**（[anthropics/claude-code](https://github.com/anthropics/claude-code)，★156,543，專有授權，2026-11-22 gh api） | 登入單一工作階段憑證（Claude 訂閱 OAuth / Console API / Bedrock / Vertex / Foundry），可設組織 `availableModels` allowlist 與環境變數映射 | 原生單一廠牌（Anthropic）：語意別名 `default`、`best`、`opus`、`sonnet`、`haiku`、`fable`、`opusplan`（Plan 用 Opus、執行自動切 Sonnet），及 `.claude/agents/*.md` frontmatter `model` 與 `effort` 欄位；不支援跨家模型 | 內建官方模型目錄隨 CLI 版本更新，或透過 `ANTHROPIC_DEFAULT_*_MODEL` 對應雲端供應商 ID | 訂閱受 Anthropic 帳號與速率邊界限制；不支援非官方多帳號自動輪換（且歷史上曾封鎖第三方 OAuth 代理使用訂閱【待驗證具體條款條文】）；無跨供應商稀缺權重 | 含本地 retry 與 context compaction；無跨家成功率回饋路由 | `/model` 互動選單與 `/statusline`（JSON 含 `.model.display_name`、context 使用率、訂閱 `rate_limits.seven_day` 百分比）即時顯示 |
| **Cline**（[cline/cline](https://github.com/cline/cline)，★71,805，Apache-2.0，2026-11-22 gh api） | 支援 Cline 帳號、ClinePass、ChatGPT OAuth（`openai-codex`）與數十種 BYOK/本機 provider（CLI onboarding 區分 `oauth` / `local_cli` / `api_key`），並拉取各家即時模型清單 | **雙模式配置（Plan / Act）**：可分別替唯讀規劃（Plan）與寫檔執行（Act）挑選不同模型；無自動跨家推薦演算法或單廠牌降級矩陣 | 依賴各 provider API `/models` 回傳與內建能力/價格資訊 | 無跨家 ToS 風險表；無額度稀缺加權；無同供應商多帳號自動輪換 | 無自動依成功率回饋重選模型 | 模式切換列與設定頁清楚顯示 Plan 與 Act 各自綁定的模型與費率 |
| **Roo Code**（[RooCodeInc/Roo-Code](https://github.com/RooCodeInc/Roo-Code)，★24,236，Apache-2.0，**已於 2026-05-15 封存**，2026-11-22 gh api） | 採用 BYOK 與命名 `API Configuration Profile`，由各 provider API 刷新可用模型 | **多模式 Profile 綁定**：`Code`、`Architect`、`Ask`、`Debug` 與自訂 Mode 各自綁定一組 Configuration Profile；手動指定，無自動降級引擎 | 依賴各 provider API metadata | 無 ToS 規則資料、無額度稀缺加權、無多帳號自動輪換 | 無回饋學習機制 | 介面頂部與設定頁直接顯示目前 Mode 對應的 Profile 名稱 |
| **Kilo Code**（[Kilo-Org/kilocode](https://github.com/Kilo-Org/kilocode)，★28,071，MIT，2026-11-22 gh api） | 支援 Kilo Gateway/Pass、外部訂閱（ChatGPT OAuth 等）、BYOK 與本機模型；支援自訂 **Efficient model pool**（1 到 10 個 `(model, variant)` 對）或繼承組織/平台池 | Modes（Code/Architect/Debug）可配具體模型，或選虛擬自動路由層：`kilo-auto/frontier`（規劃 vs 實作自動分模型）、`kilo-auto/efficient`（依會話難度動態選最省達標模型，無解退回固定基準模型）、`kilo-auto/free` | 依賴 **Kilo 持續執行的基準測試**；自訂池新增 `(model, variant)` 會觸發 **隨選基準測試（on-demand benchmark）**，標為 `Benchmarking` / `Ready` / `Failed` / `Unavailable`（每 24 小時上限 10 組） | `auto-model.md` 明文警示 `Auto Free`（含 NVIDIA 試用端點）可能記錄並用於改進服務、勿傳機密；無通用外部消費訂閱 ToS 表與多帳號自動輪換 | `kilo-auto/efficient` 依上下文難度與基準測試分數動態路由，並刻意在同一相關會話內保持黏著（避免過度切換破壞效益） | 展開的 model picker 顯示實際選用的底層模型與費用；自訂池頁面顯示各候選條目的驗證狀態徽章 |
| **Goose**（[aaif-goose/goose](https://github.com/aaif-goose/goose)，★56,849，Apache-2.0，2026-11-22 gh api） | 初始化精靈與環境變數設定 provider 與模型 | **實證更正**：昔日文件廣為引用的 **`Lead / Worker` 模式**（`GOOSE_LEAD_TURNS`、`GOOSE_LEAD_FAILURE_THRESHOLD`）與取代它的 Planning Mode **皆已於官方文件標註 Outdated 並移除**；現行改為 `/model` 手動切換＋各自指定 provider/model 的獨立 Subagents | 依賴設定的供應商與手動配置，無內建外部能力資料庫同步 | 無方案 ToS 資料、無稀缺加權、無同廠牌多帳號輪換 | 舊 Lead/Worker 曾以工具失敗／語法錯誤次數觸發升級；現行版本已無自動失敗回饋切換 | CLI 與 Desktop 介面顯示目前主模型與子代理設定模型 |
| **OpenClaw**（[openclaw/openclaw](https://github.com/openclaw/openclaw)，★394,968，MIT，2026-11-22 gh api） | 讀設定檔與 `auth-profiles` 憑證清單 | 主模型＋`agents.defaults.model.fallbacks` 陣列，並區分互動式對話與背景子代理（如審查、生成標題）的請求優先權 | 依賴供應商回傳與設定檔定義（是否串接 `models.dev`【待驗證】） | 依錯誤語意做雙階段處理：認證／配額／方案限制先做同家 **Auth-profile rotation**，未知或已下架模型則跳過輪換直接進入 **Model fallback**；依 org/endpoint 維護 `Retry-After` 與 TPM 準入閘門，互動對話優先通過 | 具持久化 auth-profile cooldown 與 memory gate；超過 `maxRetryDelayMs` 時快速失敗；無依任務品質自動調排序 | 明確顯示限流模型、相對與絕對重置時間、以及建議調整的設定鍵（`agents.defaults.model.fallbacks`）；計費累計含中途失敗棄用的候選成本 |

### (B) 閘道器、路由器與商業平台自動選型

| 工具（來源／星數） | 1. 怎麼知道使用者有哪些訂閱或模型 | 2. 角色怎麼定義與缺某家時如何降級 | 3. 模型能力資料來源與保持最新 | 4. 方案/規約限制資料化、稀缺加權、帳號輪換 | 5. 依使用結果回饋調整（成功率/429/試用期） | 6. 怎麼向使用者說明選型原因 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **LiteLLM**（[BerriAI/litellm](https://github.com/BerriAI/litellm)，★63,659，NOASSERTION，2026-11-22 gh api） | 管理員在 `config.yaml` `model_list` 手動宣告每個 deployment 與金鑰，不自動掃描外部個人訂閱 | 透過 `model_name` 群組與 `model_group_alias` 抽象模型名；備援區分 `fallbacks`、`context_window_fallbacks`、`content_policy_fallbacks` 與 `default_fallbacks`；不理解代理分工角色 | 啟動或每 6 小時自 GitHub 拉取 `model_prices_and_context_window.json`（含 `etag` 驗證），提供 `/model/deprecations` API 與下架前預警 | 支援同群組多個 deployment/key 負載平衡與 budget/RPM/TPM 限額，但無消費訂閱 ToS 風險欄位或代理合法性標記 | **具錯誤冷卻回饋**：`allowed_fails` 達標將 deployment 放進 `cooldown_time`；支援 `lowest-latency` / `least-busy` / `usage-based` 策略 | 回應標頭與 Admin UI Spend Logs 顯示實際命中的 deployment、fallback 路徑與費用 |
| **OmniRoute**（[cheaper-inference/OmniRoute](https://github.com/cheaper-inference/OmniRoute)，★89,350，MIT，2026-11-22 gh api） | 整合 394 家供應商、OAuth 訂閱登入（Cursor/Claude/Copilot 等）、API keys 與免費池，於本地端點與 `/v1/me/status` 匯總 | 支援 22 種 Combo 路由策略（`priority`、`round-robin` 等）與語意自動端點 `auto`、`auto/coding`、`auto/fast`、`auto/cheap`、`auto/smart`、`auto/offline`；全滅時支援緊急免費池備援 | 自建人工每兩週稽核的 **`freeModelCatalog.ts`**（含共享池去重、`trainsOnPrompts` 隱私標註、`hardStopGuaranteed` 硬上限、地區實名閘門 `eligibilityGate`）與任務適配評分 | **標竿做法**：`FREE_TIER_TOS` 以 `ok\|caution\|ambiguous\|avoid\|unknown` 結構化標註規約（如把 `agy`/`antigravity`、`kiro`、`amazon-q` 標 `avoid` 預設排除）；16 因子評分納 `Quota`（15%–37%）與 `Tier`（Ultra>Pro>Free）做稀缺加權；同家多帳號各自獨立計分與輪換 | **16 因子動態評分＋Bandit 探索**：依即時健康度（20%）、延遲（12%）、穩定度（5%）自動調分，低於 0.2 隔離 5 分鐘，超過 50% 異常進 incident mode 停用探索；`auto/smart` 保留 10% 探索比例試用新路線 | 回應標頭回傳實際供應商與模型；Dashboard 明確公開真實去重可用額度、隱私訓練警示與 `tos: avoid` 標記理由 |
| **9Router**（[decolua/9router](https://github.com/decolua/9router)，★32,701，MIT，2026-11-22 gh api） | 透過本機 Web Dashboard（`localhost:20128`）連接訂閱 OAuth、平價 API 與免費供應商 | **三層自動降級架構**：Tier 1 訂閱額度 -> Tier 2 平價模型（GLM/MiniMax） -> Tier 3 免費模型（Kiro/OpenCode Free/Vertex 抵免額）；未實作跨廠牌寫審職責表 | 內建 40+ 供應商與 100+ 模型對應表，隨版本維護 | 有訂閱到期前優先榨乾額度與多帳號 Round-Robin 輪換，**未見**針對消費訂閱 ToS 風險的顯式排除表（把受限來源與 API 混在同一備援鏈，具規約風險） | 追蹤每組 key 配額並於耗盡／錯誤時切換至下一層，內建 RTK 壓縮工具節省 20% 到 40% token | Dashboard 顯示連線供應商與配額消耗狀態 |
| **ClawRouter**（[BlockRunAI/ClawRouter](https://github.com/BlockRunAI/ClawRouter)，★6,667，MIT，2026-11-22 gh api） | 主打無須人工申請帳號或訂閱：以本地 x402/USDC 錢包或單一預付 API key 存取 91 個 chat 模型與 8 個免費開源模型 | 單一本地 `<1ms` 路由器，依 **15 維度請求評分** ＋ 約束優先排序（`router-core`）指派「能完成任務的最便宜模型」，未定義多代理分工角色 | 平台側維護 91+ 模型規格與自由／付費定價目錄 | 不涉及多外部消費帳號或訂閱 ToS；採事前預算檢查（budget preflight）與費用控管 | 依模型定價與約束評分計算省費比率（README 宣稱比固定 Opus 省 84%【廠商自述，待驗證】），主要為靜態多維評分規則【待驗證線上學習】 | 本地路由日誌與成本對照呈現 |
| **RouteLLM**（[lm-sys/RouteLLM](https://github.com/lm-sys/RouteLLM)，★5,722，Apache-2.0，2024-08 後較少更新，2026-11-22 gh api） | 開發者啟動時手動傳入 `strong_model` 與 `weak_model` 名稱及對應金鑰 | 固定兩極角色（`strong` vs `weak`），靠矩陣分解（`mf`）等分類器依每則 prompt 預測勝率與閾值二選一；缺家需手動重配，無寫審或工作流語意 | 依賴離線 Chatbot Arena 偏好資料訓練的路由器權重＋ `calibrate_threshold`；新模型上線無法即刻納入 | 無方案 ToS、無額度稀缺加權、無多帳號輪換 | 僅離線評測校準閾值，無線上執行回饋自調 | 回傳標準 OpenAI `model` 欄位標示選中的是強或弱模型，無理由解釋 |
| **Not Diamond**（商業 SaaS / SDK） | 開發者在請求或平台傳入候選 `llm_providers` 清單（支援 60+ 模型與自帶金鑰） | 無固定工作流角色，改以學習式 **Meta-Model** 針對每個 prompt 在品質/成本/延遲權衡下選模型；支援以自家評測資料訓練 Custom Router | 官方持續依 GPQA、MMLU、HumanEval、Arena Hard 等基準與線上評估訓練路由器 | 支援成本／延遲權衡設定與 client-side 隱私路由；不處理外部消費端訂閱合規限制或個人帳號輪換 | **支援線上 Feedback API**：可回傳使用者實際滿意度或評估分數，持續自適應微調路由映射 | SDK 回傳選中模型與路由 session ID，平台面板顯示節省比率與評估指標 |
| **OpenRouter Auto**（`openrouter/auto`、`openrouter/auto-code`，商業平台） | 依 OpenRouter 帳號可用供應商，套用請求級 `allowed_models`（glob）、`excluded_models`、`ZDR`（零資料保留）與預算上限 | 提供 `openrouter/auto`（通用）與 `openrouter/auto-code`（Coding Agent 專用），同時挑選底層模型與 reasoning effort；備援支援請求內 `models` 陣列自動順延 | 整合 `/api/v1/models` 即時目錄、價格與延遲遙測，路由引擎部分與 **Not Diamond** 合作；`auto-code` 重點考量測試與錯誤迴圈而非只看單題分數 | 支援嚴格企業合規過濾（ZDR、供應商黑白名單、預算鎖），但不處理第三方個人訂閱 OAuth 或帳號池輪換 | 偵測代理錯誤迴圈與基礎設施失敗，並採取 **Prompt Cache 優先原則**（跨輪優先調整 reasoning effort，持續失敗才換模型） | **透明度典範**：請求帶 `X-OpenRouter-Metadata: enabled` 即於回應附候選模型、預估成本、reasoning effort 與決策理由；Web Chatroom 亦有視覺化面板 |
| **Cursor**（`Auto` / Cursor Router，商業 IDE） | 綁定 Cursor 訂閱額度池（內含原生/合作模型與有額度上限的 "Other Models"）或團隊 Admin allowlist（支援有限度的 BYOK） | 單一 `Auto` 入口＋三檔目標偏向（**Cost** / **Balance** / **Intelligence**），由 **ML 分類器 ＋ 複雜度預測器（Compass）** 依任務與最近 tool calls 動態派工；企業擋掉模型時自動跳轉至允許替代（但停用基礎備援如 Grok 會觸發 `Fallback Model Disabled` 阻擋） | 官方內部基準與線上遙測驅動，模型池隨平台更新 | 嚴格套用方案額度隔離（Other Models 耗盡時自動切回內含池）與企業合規黑白名單、安全護欄轉路由；無使用者個人多帳號輪換 | 官方依整體延遲與品質遙測調校內部 ML 模型，無單一用戶個人化試用期回饋機制 | **透明度最低（反面教材）**：官方論壇與文件均確認，一般對話使用 `Auto` 時**介面不顯示實際選用的底層模型名稱** |
| **GitHub Copilot**（`Auto model selection`，商業平台） | 綁定 Copilot 訂閱席次（Free/Pro/Business/Enterprise）與組織 Admin 核准的可用模型清單 | 提供 `Auto` 模式搭配三段偏好（**Efficiency** / **Balance** / **Intelligence**），考量對話/補全/Cloud Agent 情境與 Prompt Cache 邊界；無跨廠牌寫審角色分離 | 官方內部即時健康監控與複雜度分類器維護模型池 | **經濟誘因導向稀缺保護**：付費方案選 `Auto` 享 **10% 請求乘數折扣**；高級請求（premium requests）配額耗盡時自動平滑降級至 0x／低乘數模型 | 依即時API 延遲、429 限流與容量狀態自動避開擁塞或故障模型 | 文件公開三檔策略與計價折扣規則，組織政策可控；逐則對話是否明確顯示當次底層模型【待驗證】 |

> **補充高相關開源工具觀察**（飽和掃描確認，不重覆列長表）：
> - **`router-for-me/CLIProxyAPI`**（★59,170，MIT）與 **`Magpie`**（`usemagpie.ai`）：皆把原生訂閱登入（Claude Code、Codex、Copilot、Antigravity、Gemini CLI）包裝為本地標準 API 端點；Magpie 並提供 `smart`/`order`/`rotate`/`pace` 分組策略。但對消費者訂閱來說，此類「第三方代理包裝／自動輪換」正是 Anthropic、Google Antigravity 等條款明確禁止或曾執法封鎖的高風險區。
> - **`musistudio/claude-code-router`**（★38,289，MIT）：針對 Claude Code 做本地 HTTP proxy（`127.0.0.1:3456`），將不同階段（背景摘要、思考、長上下文）轉發到不同模型與 API key，適合 API key 用戶做成本分流。
> - **`mnfst/llm-gateway`（Manifest）**（★7,651，MIT）與 **`Amp`**（`ampcode.com`）：Manifest 整合訂閱、API 與自癒 fallback；Amp 以 `Rush` / `Smart` / `Deep` 能力旋鈕取代模型名稱，讓使用者只選任務難度不選型號。

---

## 二、對 OmniKit Plan B 的具體建議（要加與要改）

對照 `data/evals/2026-11-19-model-roles-research.md` 的 Plan B 定案與 `data/evals/2026-11-22-gemini-pro-pool.md` 的規約查證，Plan B 原本是從「Ryan 個人同時有 Claude ＋ Antigravity Pro，且角色以 `gemini-strong` / `claude-strong` 廠牌前綴命名」出發。要讓 OmniKit 適用各種訂閱與 API 組合的使用者，建議在 12-01 實作前對 Plan B 做以下 **6 項關鍵修正與擴充**：

### 1. 【要改】角色全面改為「無廠牌職責角色」，廢除 `gemini-strong` / `claude-strong` 命名
- **現況問題**：`2026-11-19-model-roles-research.md` 方案 B 仍沿用 `gemini-strong`、`claude-balanced` 等廠牌前綴；若使用者只有 ChatGPT/Codex、只有 Claude Max、或只用 OpenRouter/DeepSeek API，這些 role 名稱直接語意失效。
- **修改建議**：參照 `oh-my-openagent` 的 Category/Agent 分層與 `Continue` 的 `roles + capabilities`，把 `data/rules/dispatch-policy.md` 的 `model_roles` 改為純能力／職責導向，建議 6 個核心角色：
  1. `architect_lead`（定案／高風險設計／帳務風控下單）：要求頂尖推理能力、高穩定度；有 Claude Opus / GPT 旗艦 / Gemini 頂規者依偏好優先。
  2. `implementer_main`（中大型實作與重構）：要求穩定工具呼叫與寫碼準確率。
  3. `prework_scout`（唯讀前置苦工、大量讀檔、調研）：要求大上下文、便宜或訂閱配額充裕、高思考等級（若用 Gemini 必 >= `high`），**不改檔、不定案**。
  4. `fast_utility`（規格明確的文件、小修改、摘要）：追求速度與低成本；但修改程式碼仍設 `min_tier` 下限（不派給 3.8 Flash 等弱寫碼模型）。
  5. `reviewer_cross`（獨立審查／第二意見）：宣告式約束 `prefer_different_vendor_from: author`（優先選與實作模型不同廠牌，且思考等級為高／最高，如 Gemini `xhigh` 或 GPT `xhigh`）。
  6. `orchestrator_bulk`（選配，對應 `gemini-orchestrator`）：無須跨廠牌分離的大範圍原型／測試／文件工作包；僅當環境存在支援原生子代理的 orchestrator 模型時啟用。

### 2. 【要加】把「方案與規約限制（ToS / Compliance）」做成結構化資料
- **借鏡對象**：`OmniRoute` 的 `FREE_TIER_TOS`（`ok | caution | ambiguous | avoid | unknown`）。
- **新增設計**：在 `data/rules/model-catalog-lock.yaml` 或獨立 `data/rules/provider-terms-policy.yaml` 中，為每個 `(driver, auth_mode)` 組合建立結構化約束，**不靠註解或人工記憶**。建議欄位：
  - `tos_verdict`: `ok` | `caution` | `ambiguous` | `avoid`
  - `allow_third_party_dispatch`: `true` | `false`（例如 `antigravity + subscription` 設為 `false` 或需顯式 opt-in 並警告；`antigravity + api_key` / `vertex` 設為 `true`）
  - `allow_auto_account_rotation`: `true` | `false`（消費方案 `claudeAgent` / `antigravity_pro` 設為 `false`；多組獨立付費 API key 可設為 `true`）
  - `allow_headless`: `true` | `false`（及對應風險註記）
  - `hard_constraints`: 例如 `forbid_thinking: [low, medium]`（Gemini）、`prompt_inactivity_timeout_sec: 900`（T3 Antigravity 寫死 15 分鐘）、`max_concurrent_runs: 1`（Antigravity 官方 staff 建議低並行）。
- **效果**：`catalog.py` 在產生個人可用清單時，自動把違反該使用者 `auth_mode` 規約的自動派工路徑過濾或標為「僅限人工開啟（`manual_only`）」，避免代理預設幫使用者踩停權紅線。

### 3. 【要加】三層合併的「個人清單偵測與訂閱組合解析器（Capability Resolver）」
- **現況補足**：Plan B 原文只寫 `catalog.py` 讀 T3 `orchestrator_capabilities`（＋ `agy models`）與 `models.dev` / `deprecations.info`；對多使用者而言，還缺「使用者自己買了什麼方案、這台電腦怎麼認証」的正規化層。
- **建議流程**：`catalog.py` 合併三層來源產出 `~/.omnikit/dispatch/resolved-profile.json`（不進共用 Git repo）：
  1. **Runtime 能力實測層**：呼叫 T3 `orchestrator_capabilities`（無 MCP 時走 `T3_ACP_MCP_NODE` bridge 或 `agy models`），取得實際啟用的實例、模型與參數上限（避免直接讀 `statev2.sqlite` 憑證庫）。
  2. **個人帳號屬性層**（`data/profiles/<name>/dispatch.md` 或 `omnikit-setup` 訪談收集）：記錄每個實例的 `auth_mode`（`subscription` / `api_key` / `vertex` / `aggregator`）、方案等級（如 `claude_max` / `pro` / `free`）、是否 `manual_only`、以及使用者自訂 `workflow_overrides`。
  3. **外部規格與規約層**：`models.dev`（上下文、定價、tool_use、reasoning）＋ `deprecations.info`（淘汰倒數）＋ `provider-terms-policy.yaml`（規約邊界）。
- **解析順序**：仿 `oh-my-openagent` 的 `resolveModelForDelegateTask`：使用者顯式 Pin (`workflow_overrides`) > 合規的 Role 候選排序鏈 > 降級規則。

### 4. 【要加】跨組合「降級矩陣與審查分離降級規則」
針對不同訂閱組合的使用者，不能在缺某一家時卡死或靜默降低品質，應將降級邏輯寫死進解析規則：

| 使用者可用組合情境 | 主力實作 / 定案 | 前置苦工 / 探索 | 審查（`reviewer_cross`）降級策略 | 閘門與提醒 |
| :--- | :--- | :--- | :--- | :--- |
| **雙廠牌完整合規**（如 Claude Max ＋ Gemini API/Vertex，或 Claude ＋ Codex API） | Claude Opus / Sonnet | Gemini Hydrogen / Neon | **Level 0（跨廠牌自動審查）**：由異廠牌高思考模型執行唯讀審查 | 理想預設 |
| **雙廠牌但次家僅消費訂閱**（如 Claude Max ＋ Gemini Pro 1A 模式） | Claude Opus / Sonnet（或人手開 Gemini Neon 對話） | Claude Haiku/Sonnet（避免自動化驅動消費端 agy） | **Level 1（人工跨廠牌切換）**：輸出審查 prompt 與交接指令，請使用者在 Gemini Pro 對話手動貼上審查，或建議開通 Vertex/API key 解鎖自動化 | 保護訂閱帳號不被停權 |
| **只有單一廠牌多模型**（僅 Claude Max，或僅 ChatGPT/Codex，或僅 Gemini Pro） | 主力最強模型（如 Opus / GPT-6.2 / Neon） | 同家次快模型（如 Sonnet / Haiku / GPT-mini / Hydrogen） | **Level 2（同廠牌獨立 Context 審查）**：強制另開全新唯讀對話／子代理審查（不帶作者思考過程），並優先選同家不同系列或較高思考等級（如 `xhigh`） | 標註 `degraded_same_vendor_review: true` 提醒同家族盲點風險 |
| **單一自動平台或僅免費/弱模型池**（僅 Copilot Auto、Cursor Auto、或 3.8 Flash） | 該平台預設主力 | 同平台低階檔 | **Level 3（能力閘門保護）**：仿 OmO `requiresAnyModel` gate，碰到高風險任務（`accounting`/`risk`/`orders`）不硬派弱模型（如 3.8 Flash），改顯示【等你決定】請人工覆核或接 API key | 嚴禁以低能力模型假裝完成高風險審查 |

### 5. 【要加】額度稀缺加權（Scarcity Weight）與雙階段 Failover 邊界
- **額度稀缺加權**：延續現有 `dispatch-policy.md` 的 `usage_signal`（目前只有 `claude_weekly_threshold_pct: 80` 一條硬門檻），建議擴充為每位實例的 `scarcity_score`：
  - 訂閱型帳號依當週／5 小時已用百分比（如 `< 50%` 充裕、`>= 80%` 稀缺）調整在非關鍵角色（`prework_scout`、`fast_utility`）的優先權，讓稀缺額度自動保留給 `architect_lead`。
  - 參考 `GitHub Copilot`（`Auto` 省 10% 配額並在耗盡後平順降級）與 `9Router` 的思路，但**反轉順序確保品質**：高風險不亂降級，只把可轉移的苦工／文件工作轉去額度充裕或按量計費低廉的合法通道。
- **雙階段 Failover（借鏡 `OpenClaw` 與 `OmniRoute`）**：
  - 遇到 HTTP 429 / 配額錯誤：先查該實例是否允許 `allow_auto_account_rotation: true`。**允許（僅限 API key / 企業合規池）** 才自動切換備援金鑰並寫入本地冷卻檔案（記下 `Retry-After` 與重置時間）；**不允許（消費訂閱如 Ryan 的 6 個 Pro 帳號）** 則**不自動輪換**，直接切換到下一條合規的跨模型備援（例如訂閱切 API），或暫停並印出明確 resets 時間與建議切換的帳號名稱。
  - 遇到模型未知／已下架錯誤：直接跳過同家帳號輪換，推進至下一候選模型（並標註該模型疑似下架以待週巡檢確認）。

### 6. 【要加】輕量回饋閉環、試用期狀態機與「選型可解釋性」
- **不走方案 C 重型 Daemon，直接在 Plan B 檔案層加回饋與試用期**：
  - **錯誤與冷卻統計**：在既有 `~/.omnikit/dispatch/log.jsonl` 新增可選欄位 `error_type`（`429_quota` / `429_tpm` / `timeout_15m` / `model_error`），由 `dispatch.py` 寫入 `~/.omnikit/dispatch/cooldowns.json` 做短時冷卻（例：連 2 次 429 冷卻 15 分鐘），重啟對話即自動讀取。
  - **新模型試用期（仿 `Kilo Code` 隨選基準 ＋ 現有 `trials`）**：從 `models.dev` / `orchestrator_capabilities` 偵測到的新模型（如 `gemini-4-neon`）預設狀態為 `trialing`（不直接覆蓋預設主力），需在 `log.jsonl` 累積達標樣本（如 `n >= 20` 且一次通過率未落後基準超過 10 個百分點，沿用 `trials.sonnet-trial` 口徑），才於每週差異報告（`NOW.md` 與看板）建議晉升為 `ready`。
- **選型可解釋性（借鏡 `oh-my-openagent` 與 `OpenRouter`）**：
  - 讓 `run.py show`（CLI）與 Plan B 本機設定 UI（`floorplan` 擴充）在列出每個角色的指派結果時，固定附帶一行「**決策原因摘要（Why）**」：
    - 命中原因：例如「`reviewer_cross` 選 `gemini-api/gemini-4-hydrogen-xhigh`（符合高推理需求，且與實作模型 `claude` 不同廠牌）」；
    - 跳過原因：例如「略過 `antigravity_ryan`（`tos_verdict: avoid` 第三方自動派工）、略過 `claudeAgent`（本週額度 84% >= 80% 稀缺閾值）」；
    - 降級提示：若落入單一廠牌 Level 2，明確顯示提示「目前無第二廠牌合規自動化通道，已降級為同廠牌獨立對話審查；加入任一異廠牌 API Key 可升級為跨廠牌審查」。

---

## 三、飽和式調研紀錄（管道、關鍵字組、停止條件與 GitHub 實測）

### 1. 納排準則
- **納入對象**：具備「依使用者擁有的訂閱、API 憑證、方案限制或模型可用清單動態／宣告式分配模型角色、路由規則、模式切換、或自動降級與帳務/配額保護」之 Coding Agent、IDE 擴充、多代理編排層、LLM Gateway／Router 工具或開放目錄標準。
- **排除對象**：傳統 ML 模型（Tabular/Vision/AutoML 如 TPOT、AutoDL）工具、傳統微服務熔斷／API 閘道（未含 LLM 路由語意者如 Istio、Kong 本體）、未公開具體工具實作的論文清單（僅取其提及之開源工具本體），以及純單一模型介面。

### 2. 關鍵字組、詞彙擴展與覆蓋管道（共 11 組）
依 `engine/skills/omnikit-research/SKILL.md` 使用 `sweep.py` 建立獨立帳本（置於暫存目錄），由起手詞彙擴展至 `fallback`、`credential`、`account pool`、`quota`、`model tier`、`virtual model`、`capability matrix`、`harness`、`cooldown`、`multi-agent policy`、`failover`，涵蓋不含 `agent/skill/AI/MCP` 的一般字眼（如第 3 組 `provider credential model selection`、`llm gateway model fallback cooldown`）。

| 組別 | 關鍵字組 | 新增數（總數／★1,000+） | 已覆蓋管道 |
| :---: | :--- | :---: | :--- |
| 1 | `coding agent model routing subscription` | 39（★1000+：13） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, web-zh, producthunt |
| 2 | `llm model role fallback router` | 23（★1000+：7） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 3 | `provider credential model selection` | 36（★1000+：5） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related |
| 4 | `multi-provider account pool quota routing` | 19（★1000+：8） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 5 | `model tier assignment coding assistant` | 17（★1000+：3） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related |
| 6 | `virtual model alias cost tier routing` | 9（★1000+：1） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 7 | `llm model capability matrix benchmark routing` | 9（★1000+：1） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 8 | `agent harness model fallback strategy` | 5（★1000+：3） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 9 | `llm gateway model fallback cooldown` | 6（★1000+：0） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 10 | `multi-agent model selection policy` | 3（★1000+：0） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |
| 11 | `subscription quota model failover` | 5（★1000+：0） | github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en |

### 3. 停止條件與 `sweep.py status` 實測結果
執行 `uv run engine/skills/omnikit-research/scripts/sweep.py status "$env:TEMP\multi-user-model-roles-ledger.json" --min-stars 1000` 完整統計輸出如下：

```text
總共 170 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 3 組沒有新的（要 3 組）：可以停，報告寫「長尾未飽和」並附上面兩種連續數
```

- **停止類型**：**長尾未飽和**（於第 **11 組**停止；連續數：全體候選連續 0 組無新名字，但 `★1,000 以上` GitHub repo 於第 **9、10、11 組**連續 3 組無新名字，達停止條件）。
- **覆蓋聲明**：`★1,000` 以下之小型路由外掛（如個人為 Pi、OpenCode、Claude Code 寫的 hook／plugin 腳本）與無開源星數之新創商業服務不保證找齊。

### 4. 查不到的管道與資料限制
- **Product Hunt API**：`sweep.py` 未整合須要開發者 token 的 Product Hunt API，已依規範於第 1 組透過 `site:producthunt.com` 網頁檢索補齊。
- **MCP Registry 與 skills.sh**：兩者皆採子字串比對且雜訊偏高（例如搜 `model` 或 `provider` 會大量命中醫療／不動產資料模型），已依納排準則人工過濾不納入非相關條目。
- **`awesome` 清單**：多數關鍵字僅觸及通用清單（如 `awesome-claude-code`）或 0 筆，對比主要專案（`anomalyco/opencode`、`BerriAI/litellm`、`code-yeongyu/oh-my-openagent`）改用 `sweep.py related` 抽取出高星數 fork 與 README 關聯專案。
- **閉源商業路由內部細節**：`Cursor Auto`、`GitHub Copilot Auto`、`Not Diamond`、`OpenRouter Auto`、`Amp` 之訓練特徵權重、內部評估集與實際後端切換閾值屬閉源商業邏輯，僅能引用官方公開文件與部落格，未有公開一手數據之欄位均標註 `【待驗證】`。

### 5. GitHub `sweep.py verify` 實測紀錄（查證日期：2026-11-22 `gh api`）

| Repo | Stars | License | Archived | Last Pushed |
| :--- | :---: | :--- | :---: | :--- |
| `openclaw/openclaw` | 394,968 | MIT | false | 2026-11-21 |
| `anomalyco/opencode` | 228,375 | MIT | false | 2026-11-21 |
| `anthropics/claude-code` | 156,543 | 無 | false | 2026-11-21 |
| `OpenHands/OpenHands` | 93,955 | MIT | false | 2026-11-21 |
| `cheaper-inference/OmniRoute` | 89,350 | MIT | false | 2026-11-21 |
| `cline/cline` | 71,805 | Apache-2.0 | false | 2026-11-21 |
| `code-yeongyu/oh-my-openagent` | 71,042 | NOASSERTION | false | 2026-11-21 |
| `BerriAI/litellm` | 63,659 | NOASSERTION | false | 2026-11-21 |
| `router-for-me/CLIProxyAPI` | 59,170 | MIT | false | 2026-11-21 |
| `aaif-goose/goose` | 56,849 | Apache-2.0 | false | 2026-11-20 |
| `QuantumNous/new-api` | 52,313 | AGPL-3.0 | false | 2026-11-20 |
| `Aider-AI/aider` | 50,211 | Apache-2.0 | false | 2026-05-22 |
| `can1357/oh-my-pi` | 39,580 | MIT | false | 2026-11-21 |
| `musistudio/claude-code-router` | 38,289 | MIT | false | 2026-11-21 |
| `continuedev/continue` | 36,535 | Apache-2.0 | false | 2026-11-20 |
| `decolua/9router` | 32,701 | MIT | false | 2026-11-16 |
| `Kilo-Org/kilocode` | 28,071 | MIT | false | 2026-11-21 |
| `RooCodeInc/Roo-Code` | 24,236 | Apache-2.0 | **true** | 2026-05-15 |
| `Portkey-AI/gateway` | 13,425 | MIT | false | 2026-11-20 |
| `tensorzero/tensorzero` | 11,700 | Apache-2.0 | **true** | 2026-06-11 |
| `github/copilot-cli` | 11,445 | NOASSERTION | false | 2026-11-21 |
| `alvinunreal/oh-my-opencode-slim` | 10,309 | MIT | false | 2026-11-21 |
| `maximhq/bifrost` | 9,908 | Apache-2.0 | false | 2026-11-21 |
| `anomalyco/models.dev` | 7,707 | MIT | false | 2026-11-21 |
| `mnfst/llm-gateway` | 7,651 | MIT | false | 2026-11-17 |
| `katanemo/plano` | 7,118 | Apache-2.0 | false | 2026-10-24 |
| `BlockRunAI/ClawRouter` | 6,667 | MIT | false | 2026-11-21 |
| `vllm-project/semantic-router` | 6,515 | Apache-2.0 | false | 2026-11-21 |
| `lm-sys/RouteLLM` | 5,722 | Apache-2.0 | false | 2024-08-10 |
| `weave-os/router` | 5,625 | Apache-2.0 | false | 2026-11-21 |
| `lemony-ai/cascadeflow` | 3,922 | MIT | false | 2026-09-25 |
| `vybestack/llxprt-code` | 704 | Apache-2.0 | false | 2026-11-21 |
| `code-yeongyu/senpi` | 523 | MIT | false | 2026-11-21 |
