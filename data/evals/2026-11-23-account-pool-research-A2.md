# 業界與開源「同一人多 AI 訂閱帳號池」管理機制調研報告（A2）

- 調研日期：2026-11-23
- 研究者代號：A2（起手關鍵字：`"Antigravity 多帳號 切換"`、`"LLM quota failover"`、`"OAuth token pool proxy"`）
- 帳本位置：`C:\Users\user\AppData\Local\Temp\omnikit-research\account-pool-A2-ledger.json`
- 相關既有報告：`data/evals/2026-11-19-model-roles-research.md`、`data/evals/2026-11-22-multi-user-model-roles-research.md`、`data/evals/2026-11-22-gemini-pro-pool.md`

---

## 摘要

1. 業界開源工具對「同一人多 AI 訂閱帳號」形成四大流派：**本機隔離切換器**（`claude-swap`、`ccs`、`clauth`）、**本地／自架 OAuth 號池代理**（`OmniRoute`、`CLIProxyAPI`、`Sub2API`、`Antigravity-Manager`、`AIClient2API`、`codex-lb`、`9Router`）、**CLI 認證外掛**（`opencode-antigravity-auth`）、**唯讀配額監控面板**（`CodexBar`、`Quotio`、`ClaudeBar`、`vscode-antigravity-cockpit`、`AIUsage`）。
2. **新帳號接入**已標準化為環境目錄隔離（`CLAUDE_CONFIG_DIR`、`CODEX_HOME`、`GEMINI_CLI_HOME` 或 T3 的 `sha256(實例 id)`）搭配 OAuth 瀏覽器登入；**絕對不可自動代勞的步驟**包含互動登入／MFA、驗證解鎖（`validation_url`）、切號前禁止跑 `/logout`（會撤銷 refresh token）。
3. **Google Antigravity 額度與封鎖探測**有一手工程關鍵發現：控制面端點（`loadCodeAssist`、`fetchAvailableModels`、`retrieveUserQuotaSummary`）對被封帳號仍回 HTTP 200，唯有**資料面最小推理探針（`v1internal:generateContent`）**會回 `403 PERMISSION_DENIED + TOS_VIOLATION`；且查詢必須打 `daily-cloudcode-pa.googleapis.com` 而非 Prod host，並加上 `AGY_CLI_DISABLE_AUTO_UPDATE=true`。此外 Google 已於 2026-06-18 停服消費帳號之 Gemini CLI OAuth，個人方案全面轉向 Antigravity。
4. **帳號狀態機必須拆為正交維度**：手動停用、`invalid_grant`（需重登）、`VALIDATION_REQUIRED`（臨時驗證鎖＋網址）、`TOS_VIOLATION`（帳號封禁）、地區 Hard 403、以及模型級 403／保護線，彼此不可互相覆寫。
5. **選帳號策略的核心矛盾是「快取親和 vs 配額耗盡」**：coding agent 必須優先採 `sticky`（session affinity）＋ 5 分鐘冷卻與遲滯區間（hysteresis），避免輪詢摧毀 Prompt Cache；跨週期訂閱則興起 `expiry-first`／`weekly-first`（先花最快過期重置的週額度）與 `quota-weighted`（依 `剩餘額度 / 進行中併發數` 加權）。
6. **三大廠一手規約底線極為明確**：Google Antigravity 禁止消費方案自動輪換與第三方 agent 包裝；Anthropic 禁止非 API key 的自動化腳本與第三方應用中轉 Claude.ai OAuth（但**官方文件明文支援**個人用 `CLAUDE_CONFIG_DIR` 隔離多帳號）；OpenAI 禁止自動化規避限流與多人共用。對 OmniKit 而言，**訂閱帳號應只做「唯讀觀測＋人手切換建議＋目錄隔離同步」，自動輪換與跨家 failover 僅限 API Key／Vertex 通道**。

---

## 一、工具比較表（工具 × 六面向）

以下精選 20 個最具代表性之開源工具（含全部 5 個種子專案與各大流派標竿），GitHub 星數與授權均於 **2026-11-23** 透過 `sweep.py verify`（`gh api`）實測驗證；未直接讀到一手原始碼或官方文件佐證的項目均標註 `【待驗證】`。

| 工具（Repo / Verify 星數與授權，2026-11-23 gh api） | 定位 | 1. 新帳號接入與探測 | 2. 健康與額度（含 403/401/429） | 3. 選帳號與接手策略 | 4. 規約態度與降風險做法 | 5. 可觀測性與告警 | 6. 多使用者 Schema 與設定流程 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **OmniRoute**<br>`cheaper-inference/OmniRoute`<br>★89,647, MIT | 多供應商訂閱＋免費＋API 聚合閘道 | Web UI 連 394 家供應商、OAuth／API key／免費池；live catalog 發現模型與共享池去重 | 16 因子即時健康分（<0.2 隔離 5 分鐘）；50% 以上異常進 incident mode；追蹤配額與 429 冷卻 | 22 種策略：`priority`、`fill-first`、`round-robin`、`least-used`、`quota-weighted`、`expiry-first`、`cache-optimized`；`auto/subscription`（fail-closed）vs `auto/thrifty`（超額轉低價 API、重置切回） | `FREE_TIER_TOS` 標註 `ok/caution/ambiguous/avoid`；`tos: avoid` 預設排除出 `auto`，`FREE_TIERS.md` 明確標出 `agy` 代理風險 | Web Dashboard（`/dashboard/free-tiers`、配額遙測）、回應標頭顯示命中的供應商與模型、Discord/Telegram 社群支持【原生推播告警待驗證】 | SQLite／本地設定＋Web 精靈；區分無金鑰／訂閱／API 層級與地區資格閘門（`eligibilityGate`） |
| **CLIProxyAPI (CPA)**<br>`router-for-me/CLIProxyAPI`<br>★59,260, MIT | Go 本機 CLI OAuth 轉標準 API 代理 | 支援 Antigravity、Codex、Claude Code、Gemini CLI、Grok OAuth 登入與多 auth JSON 檔；含 `fetch_antigravity_models` 探測工具 | 區分 403/408/429/5xx 重試輪次（`request-retry`）；可設 `save-cooldown-status: true` 持久化為 `.cds` 檔；`ResetQuota` 管理 API | `round-robin`、`weighted-round-robin`、`fill-first`；支援跨 client 的 `session-affinity`（Header／LCP 前綴雜湊）、子代理繼承親和（`session-affinity-subagents`）、`rebind-on: any/quota/never`、憑證級 concurrency 控管 | 透過內建 uTLS 模擬瀏覽器/CLI 指紋、每帳號獨立 `proxy-url`；未強制阻擋違反 ToS 的消費訂閱代理 | 獨立 Management API，衍生完整生態看板：`Cli-Proxy-API-Management-Center`（★4,830）、`CPA-Manager-Plus`（★4,100）、`cpa-usage-keeper`（★1,324） | 完整 `config.example.yaml`（1,481 行）宣告路由、重試、冷卻、併發、權重與各憑證覆寫 |
| **New-API**<br>`QuantumNous/new-api`<br>★52,357, AGPL-3.0 | 企業／團隊多模型中轉閘道 | 渠道（Channel）管理介面加入多組 API key／中轉帳號；啟動精靈建管理員與模型定價 | 渠道測試、錯誤自動禁用與餘額／額度追蹤 | 渠道優先級、加權輪詢與失敗切換 | README 明文要求使用者合法取得上游憑證並自負上游 ToS 合規責任 | 內建用量與成本儀表板、快取計費、請求日誌與外掛市集 | SQLite/MySQL/PG＋Web Setup Wizard＋使用者／群組／權限多租戶模型 |
| **Sub2API**<br>`Wei-Shaw/sub2api`<br>★46,465, LGPL-3.0 | 一站式訂閱號池分發閘道 | Web 精靈接入 Claude、OpenAI/Codex、Gemini、Antigravity、Grok OAuth 與 API key；支援 Composite Groups 模型解析 | 追蹤平台額度、429/529/401/403 錯誤冷卻、排程測活（`scheduled_test_handler`）；可整合獨立代理 IP | 智慧調度＋Sticky Session（提醒 Nginx 須開 `underscores_in_headers on` 保 `session_id`）＋每使用者／每帳號 Concurrency 上限 | README 頂部紅字警語「可能違反 Anthropic 等上游 ToS，作者不負封號責任」；社群搭配住宅代理防關聯 | Admin Dashboard、精準 Token 計費、延伸手機端管理 App `sub2api-mobile`（iOS/Android）【原生手機告警待驗證】 | Go + PostgreSQL + Redis + Vue3；一鍵部署腳本自動生成密鑰與 Web Setup Wizard |
| **Antigravity-Manager**<br>`lbjlaq/Antigravity-Manager`<br>★33,691, NOASSERTION | Antigravity 專用多帳號桌面管理＋本地代理 | Tauri v2 + React；OAuth 2.0 自動/手動授權、匯入現有 Token；讀取 `fetchAvailableModels` 取得模型目錄與 `tieredModelIds` | **業界最細 6 維狀態機**：查 `daily-cloudcode-pa` 的 `retrieveUserQuotaSummary`＋`fetchAvailableModels`；**資料面最小推理探針**測 `403 TOS_VIOLATION`；獨立追蹤 `validation_blocked`＋`validation_url`、`invalid_grant` 持久化 `disabled`、`forbidden_models` 模型級隔離、獨立 `QUOTA_ENDPOINT_HEALTH` 防輪詢污染推理端點 | 依帳號層級（Ultra > Pro > Free）與額度冗餘推薦「Best Account」一鍵切換；代理層支援 429/401 毫秒切換、背景任務靜默降級 Flash | 支援帳號手動停用與代理層停用分離（`manual_proxy_disabled`）；僅採探針判封並擷取 `ban_appeal_url`，但本身提供反代輪換仍屬 Google FAQ 禁止區 | 全域配額儀表板（List/Grid 視圖）、403/Disabled 徽章與原因提示、本機 SQLite 代理監控日誌 | 單帳號獨立 JSON 檔（`accounts/<id>.json`）＋ `~/.antigravity_tools/gui_config.json`，支援無頭 Docker 模式 |
| **9Router**<br>`decolua/9router`<br>★32,752, MIT | 本機訂閱→平價→免費三層降級路由器 | `localhost:20128` Dashboard 連接訂閱 OAuth、平價與免費供應商；自動刷新 OAuth Token | 即時 Token 計數、重置倒數、追蹤每組 key 配額並於 429／耗盡自動切下一層 | 帳號間 Round-Robin；三層自動接手（Tier 1 訂閱額度 → Tier 2 平價 API → Tier 3 免費池） | 未見如 OmniRoute 的結構化 ToS 風險排除表，將消費訂閱與免費/API 混於同條備援鏈（高風險） | 本地 Web Dashboard 即時配額進度與重置倒數 | 單機 Web 面板設定＋Combo 鏈配置 |
| **CodexBar**<br>`steipete/CodexBar`<br>★23,287, MIT | 跨平台選單列唯讀配額監控（115 供應商） | 複用既有 CLI／瀏覽器／OAuth 登入，不存密碼；Codex 支援多個隔離 `CODEX_HOME` 與自訂 `codexProfileHomePaths`；Antigravity 支援 4 種來源 | **唯讀探測集大成**：Antigravity 依序讀本機 `language_server` → `agy` CLI（`agy -p /usage --output-format json` 帶 `AGY_CLI_DISABLE_AUTO_UPDATE=true` 與假 `BROWSER` 防彈窗）→ IDE → OAuth `retrieveUserQuotaSummary`；Claude 讀 `api/oauth/usage`（回退 CLI PTY／Web）；Codex 讀 OAuth/RPC/Web；可偵測 2026-06-18 個人 Gemini CLI 停服訊號 | **不做代理不自動輪換**；Codex 提供顯式 `codex-accounts promote` 原子切換（含檔案鎖、防外部覆寫衝突、重啟 daemon） | **合規性最高**：純唯讀觀測＋人工顯式切換；預設關閉跨應用讀取外部 OAuth，嚴守 Keychain 提示政策與去個資隱私模式 | macOS 選單列／Linux 桌面通知、剩餘額度燃盡圖（burndown）、閾值與預報警告、`codexbar serve` 本機唯讀 JSON API | `~/.config/codexbar/config.json` 統一多帳號 `tokenAccounts`、`codexProfileHomePaths`、個別 `claudeConfigDirectory` |
| **Cockpit Tools**<br>`jlcodes99/cockpit-tools`<br>★20,293, 無授權 | 多 AI IDE 帳號管理與本機 Rust 閘道 | 支援 Antigravity、Codex、GitHub Copilot、Windsurf、Cursor、Gemini CLI、Grok（OIDC device flow）；支援 OAuth、Refresh Token、剪貼板與本地匯入 | 統一面板檢視各帳號配額與重置窗口；支援按官方 Quota Group 顯示 | 內建 Rust API 服務引擎，支援 Responses HTTP/SSE/WS、自動續接跨帳號上下文（保留 reasoning/compaction/`call_id`）與帳號池切換 | 同時提供「純切換／觀測」與「本機號池反代」，後者具 ToS 風險 | 統合儀表板、帳號總覽與分組額度卡片 | 桌面 GUI 配置帳號池、代理與各 IDE 同步設定 |
| **Claude Relay Service**<br>`Wei-Shaw/claude-relay-service`<br>★12,827, MIT | Claude/OpenAI/Gemini 訂閱中轉服務 | 管理後台完成 OAuth 授權並支援帳號級參數覆寫；提供各 CLI 設定指南（`~/.claude/config.json`、`~/.codex/config.toml`） | 403 驗證失敗記錄、Proxy Host Online 狀態監控與自動切換【冷卻細則待驗證】 | 多帳號拼車中轉與負載均衡 | 同 Sub2API 生態，屬上游明文禁止之消費訂閱共享／中轉模式 | Web 管理後台顯示節點在線與使用統計 | Web 後台＋客戶端手動指向中轉端點 |
| **opencode-antigravity-auth**<br>`NoeFabris/opencode-antigravity-auth`<br>★11,087, MIT | OpenCode 專用 Antigravity OAuth 外掛 | `opencode auth login` 互動新增多組 Google 帳號；透過 `fetchAvailableModels` 動態發現模型（快取 1 小時）並映射 thinking variants | 獨立腳本 `scripts/check-quota.mjs` 打 `loadCodeAssist` + `fetchAvailableModels` 查各家族最低剩餘與最早重置；`invalid_grant` 自動移除；短限流（<= 5 秒）同號重試＋指數退避；主動於過期前 30 分鐘刷新 token | 3 種策略：`sticky`（保 Anthropic prompt cache）、`round-robin`、`hybrid`（健康分 initial 70 / -10 限流 / -20 失敗 / 每小時 +2 恢復 + token bucket + LRU）；**`pid_offset_enabled`** 避免平行子代理撞同號；雙池（Antigravity 全滅自動降級 Gemini CLI） | 明確標示檔案含 refresh token 如密碼；屬 Google FAQ 明文禁止之第三方 coding agent 接入 Antigravity OAuth（已有大量 403 封號案例） | `/antigravity` 面板顯示快取最低配額與倒數、Toast 通知（可設 `toast_scope: root_only` 與 `quiet_mode`）、Debug 檔案日誌 | 提供標準 JSON Schema（`assets/antigravity.schema.json`）與帳號檔 `~/.config/opencode/antigravity-accounts.json`（區分 `activeIndexByFamily`） |
| **AIClient2API**<br>`justlovemaki/AIClient2API`<br>★8,996, GPL-3.0 | 多協定客戶端轉標準 API 號池 | Web UI 一鍵開瀏覽器 OAuth（固定 callback ports：Antigravity 8086、Codex 1455、Grok 56121）或上傳憑證檔；支援 Quick Associate 綁定 | 週期性背景健康檢查、異步刷新佇列與緩衝去重、全域併發控制、節點預熱 | 號池管理（`provider_pools.json`）、智慧路由與自動 failover、按節點覆寫輔助模型 | 明文主打「突破官方限流」＋內建 Go uTLS Sidecar 繞過 Cloudflare 403；屬高風險違規代理 | Web UI 控制台：Dashboard、Provider Pools 健康統計、即時日誌流 | `configs/config.json`＋獨立 `provider_pools.json`（支援 `--provider-pools-file`）；首次啟動自動產生隨機登入密碼 |
| **GPT-Load**<br>`tbphp/gpt-load`<br>★7,246, MIT | Go 高併發多金鑰／訂閱代理 | Web UI 建立渠道並匯入多組 API key 或完成 OAuth（支援 Codex/Claude/Antigravity callback port，經由 CLIProxyAPI 適配） | 多憑證排程、自動重試、冷卻、黑名單隔離與憑證探測（`credential probes`）與模型發現 | 可設權重、Session Affinity 與故障隔離 | 支援純官方 API Key 池（合規）及選配訂閱 OAuth 渠道（具 ToS 風險） | Web 管理面板與請求狀態監控【原生手機推播待驗證】 | `.env` 環境變數（精細分離 `HOST`、`BIND_ADDRESS`、`OAUTH_CALLBACK_BIND_ADDRESS`）＋ Web UI |
| **Gemini Balance**<br>`snailyp/gemini-balance`<br>★5,772, NOASSERTION | Gemini 多 API Key 負載均衡代理 | 批量匯入多組 Gemini API key，轉為 OpenAI/Gemini 相容端點 | 錯誤監控與失活金鑰排除【最新 Antigravity 支援停滯，最後 push 2025-09-30】 | 多 API Key 輪詢與故障切換 | 主打官方 Gemini API Key（若為同人多免費 key 仍有濫用風控風險） | 內建 Web 管理頁與 Telegram 社群 | 環境變數＋資料庫設定 |
| **Quotio**<br>`nguyenphutrong/quotio`<br>★4,920, MIT | macOS 選單列全能代理＋額度指揮中心 | 整合管理 CLIProxyAPI 生命週期、OAuth／API key／CLI 帳號登入與自動組態各 coding agent | 即時追蹤各帳號 5 小時與每週重置窗口 | 透過底層 CLIProxyAPI 執行多帳號負載均衡與自動 failover | 同 CLIProxyAPI：消費訂閱代理具 ToS 風險；僅用於監控與 API key 則安全 | macOS 原生 SwiftUI 選單列、視覺化儀表板與桌面通知 | 圖形介面自動配置本地代理與 agent 設定檔 |
| **claude-swap (`cswap`)**<br>`realiti4/claude-swap`<br>★4,909, MIT | Claude Code 多帳號本機切換與自動監控 | 登入新帳號後執行 `cswap add` 備份（**警告不可先 `/logout`**）；支援 `add-token` 匯入 `setup-token` 或 Console API key；可目錄綁定 `cswap map` | 輪詢 `api/oauth/usage`（自適應頻率避免觸發限流）；`setup-token` 可選開 `usage.headerProbe`（1-token Haiku 讀限流 header）；死 token 自動隔離（quarantine）；切號時持有 Claude Code 鎖檔防競態 | 4 種策略：`best`（剩餘最多）、`weekly-first`（最快週重置）、`consume-first`、`priority-consume-first`（tier 0–1000）；5 分鐘冷卻＋**hysteresis margin** 防震盪；預設不自動輪換到 API key 帳號；支援 `cswap run` 獨立 `CLAUDE_CONFIG_DIR` 並行＋Windows directory junction 共享對話歷史 | **無代理、不改二進位、純操作本機官方 CLI 憑證與目錄**；手動切換與 `CLAUDE_CONFIG_DIR` 隔離落於官方支援區；唯高頻全自動切換規避限流仍屬灰色地帶 | TUI Live Dashboard（`cswap watch`）、macOS 選單列、結構化 JSON / JSONL 事件流（`cswap auto --json`）、**跨機 `import-usage --hold` 避免多機重複輪詢撞限流** | 驗證型 `cswap config set`＋`settings.json`＋`autoswitch_state.json`；分平台安全存放（macOS Keychain / Win & Linux 檔案），支援 `export/import` 剝離本機 MCP 憑證 |
| **vscode-antigravity-cockpit**<br>`jlcodes99/vscode-antigravity-cockpit`<br>★4,857, MIT | VS Code Antigravity 配額監控擴充 | 讀取 Antigravity 本機進程／授權資料，嚴格驗證本機 email 一致才合併模型清單（`local_quota.ts:45-54`） | 動態跟隨官方 Model Quota 分組（週配額＋5h 窗口），自動收合相同配額與重置時間的 High/Medium/Low 變體（`collapseLocalQuotaVariants`） | 純唯讀監控與快速檢視，不代理不自動切換 | **高合規性**：僅讀取本機已登入之官方環境狀態 | Webview 儀表板、QuickPick、狀態列進度、**閾值桌面通知（`agCockpit.notificationEnabled`）**、隱私模式 | VS Code Settings（`agCockpit.*`） |
| **EchoBird**<br>`edison7009/EchoBird`<br>★3,580, MIT | 全合一 AI 桌面工具＋帳號管理＋路由器 | 一鍵安裝 Claude Code／Codex CLI／DeepSeek 等；瀏覽器授權新增多帳號，自動改寫各 CLI 設定檔（如 `~/.grok/config.toml`） | 單一面板查看 Claude 5h/7d 剩餘額度與重置時間、一鍵刷新 | App Manager 啟動時手動選帳號；Smart Router 依使用者拖拉的**顯式優先序（Explicit Priority）**做自動 failover（免費／付費／私有模型） | 啟動時人工挑帳號屬低風險；Smart Router 主要用於 API／模型清單備援 | 桌面端用量儀表板（My AI Career）與配額一覽 | 圖形化拖拉卡片排優先序，免手編 TOML/JSON |
| **codex-lb**<br>`Soju06/codex-lb`<br>★3,454, MIT | OpenAI Codex / ChatGPT 多帳號負載均衡器 | Web 面板（`localhost:2455`，callback `1455`）新增多組 ChatGPT OAuth 帳號；自動從上游同步可用模型清單 | 追蹤每帳號 Token、成本、28 天趨勢與 5h/週配額；失敗與限流自動排除 | 多帳號池負載均衡、每張自發 API key 可設 Token／成本／時間窗／模型限額；支援 Codex Responses API 與 WebSockets | 屬第三方本地 OAuth 聚合代理，個人小量使用處灰色區，多人共用或自動繞限流違 OpenAI ToS | Web 儀表板（密碼＋可選 TOTP 保護）；衍生豐富社群監控：`codex-lb-statusbar`、SwiftBar、Ubuntu Tray、**Home Assistant 感測器（`codex-lb-rates`）** | `CODEX_LB_*` 環境變數／`.env.local`＋SQLite/PostgreSQL；首次遠端登入採一次性 bootstrap token |
| **CCS (Claude Codex Switch)**<br>`kaitranntt/ccs`<br>★2,907, MIT | 多供應商 Profile 與執行環境管理器 | 統一管理多個獨立 Claude 訂閱目錄（`~/.ccs/instances/*`）、API/本機 profile（GLM、Ollama、OpenRouter）與內嵌 CLIProxy OAuth | Live Auth Monitor 顯示認證健康與就緒度 | 命令列顯式切換（`ccs`、`ccs codex`、`ccs glm`）；內嵌代理提供 `round-robin` vs `fill-first` 切換及 `profile:model` 選擇器 | 同時提供合規的本機 `CLAUDE_CONFIG_DIR` 隔離＋API profile，以及選配的 CLIProxy OAuth 代理（後者具 ToS 風險） | Web 儀表板（`:3000`）、Analytics、macOS 選單列 `CCS Bar` | `ccs config` 與 `ccs api create --preset` 預設樣板 |
| **ClaudeBar**<br>`tddworks/ClaudeBar`<br>★1,590, Apache-2.0 | macOS 多帳號配額監控與手機推播 | 支援「瀏覽器開新隔離資料夾登入（`claude auth login`/`codex login`）」或「匯入既有 `CLAUDE_CONFIG_DIR`/`CODEX_HOME`」；**三步入庫校驗**（找到金鑰→核對 email 防重複→首刷額度） | 追蹤 20+ 供應商配額＋**消耗速度預測（Forecast）**；支援單帳號 Pause（暫停刷新與告警但保留數據） | 純唯讀監控不代理；同一供應商多帳號採「最健康帳號優先呈現」（一號見底不誤報整家 DEPLETED） | **高合規性**：嚴格呼叫官方 CLI 登入、禁止複製 `auth.json`/`.credentials.json` 避免刷新競態、Keychain 隔離保存 API key | macOS 選單列、MacBook Notch、Touch Bar、四色速度感知告警、**透過 Notify! 推播 iPhone 鎖定畫面 Live Activity 與桌面小工具** | 圖形精靈＋自訂帳號別名、排序、釘選與跨裝置配對碼 |
| **Subpool**<br>`gesta-run/subpool`<br>★117, Apache-2.0 | 企業自架訂閱與 API 治理控制面 | 管理員接入授權訂閱（Codex、Copilot、Antigravity 須自填 OAuth Client）與 API 帳號至 Pool，再發員工專屬 key；不儲存 prompt/程式碼 | 429 指數退避上限 30 分鐘（尊重較長 `Retry-After`）；併發查詢共享單次讀取；OpenAI Costs API 估算贈金餘額（30 分鐘刷一次、2 小時寬限期）；查詢失敗保留快照不中斷推理 | 支援 `SUBPOOL_CODEX_QUOTA_ROUTING`：保留既有 `previous_response_id` 與 WebSocket 綁定絕不重播遷移；新請求依「訂閱 > 促銷贈金（快到期優先）> 預付點數」三層排序；同級需領先 **> 5 個百分點**才切換防抖；可設整數權重（如 4:1）；每上游帳號併發上限 16 active turns | 明文要求僅使用獲授權管理之帳號，並提示檢查上游 ToS；預設關閉自動配額路由（opt-in） | Web Console、Prometheus `/metrics`（含 `subpool_codex_routing_requests_total`、`subpool_responses_ws_connection_rejections_total`）、**每日定時 Email 團隊報表（Resend，具 DB lease 防重發與冪等鍵）** | Go + PostgreSQL + React；環境變數＋Console 熱更新請求上限；員工報表名稱映射與路由邏輯解耦 |
| **gcli2api**<br>原 `su-kaka/gcli2api`（2026-11-23 已 404）；鏡像 `yixuanwangluo/gcli2api-fix-master` ★166, CNC-1.0 | Gemini CLI OAuth 轉 OpenAI/Gemini 代理 | 本機 `127.0.0.1:7861/auth` 完成 OAuth 產生 JSON 憑證檔（支援 ZIP 批量上傳或 `GCLI_CREDS_*` Base64 環境變數） | 即時健康檢查、429/403/500 錯誤碼追蹤、自動封禁故障憑證、按日統計呼叫次數（UTC+7 重置） | 依呼叫次數輪換多組 Google OAuth 憑證、可配置 429 自動重試間隔與次數 | 反商業授權（CNC-1.0）；2026-06-18 Google 停服消費端 Gemini CLI OAuth 後對個人帳號大幅失效，且屬高風險違規代理 | Web 控制台、WebSocket 即時日誌流、手機版介面 | TOML 設定檔＋環境變數鎖定優先權 |

> **補充值得關注之同類工具（皆已 `verify` 實測，2026-11-23）**：
> - **`automazeio/vibeproxy`**（★3,414, MIT）：macOS 選單列封裝 CLIProxyAPI，最新亮點是整合 **Vercel AI Gateway** 作為官方核准的合規替代路徑。
> - **`badrisnarayanan/antigravity-claude-proxy`**（★4,087, MIT）：Antigravity 轉 Anthropic `/v1/messages` 本地代理，README 頂部直接掛上紅字 **ToS Violation Ban 警告**。
> - **`ding113/claude-code-hub`**（★3,401, MIT）：面向 Claude Code 與 Codex 的現代化自架代理、Session 儀表板與智慧負載均衡。
> - **`uwuclxdy/clauth`**（★344, MIT）：同時整合 Claude Code（`CLAUDE_CONFIG_DIR`）與 Codex（`CODEX_HOME`）本機隔離並行、即時 5h/7d 監控、跨帳號 MCP fallback 與無痕 headless 啟動。
> - **`sylearn/AIUsage`**（★748, Apache-2.0）：跨 12+ 供應商多帳號儀表板＋Keychain 憑證保險庫＋強調 **Truthful Status**（區分「已組態」與「經真實請求驗證」）。
> - **`slkiser/opencode-quota`**（★1,165, MIT）：專為 OpenCode 設計的「零上下文視窗污染」多供應商配額監控外掛（支援 Antigravity、Copilot、OpenAI、Cursor 等）。
> - **`Mirrowel/LLM-API-Key-Proxy`**（★566, NOASSERTION）：Python/FastAPI 金鑰與 OAuth 輪換代理，主打容量階段鎖定（capacity-phase locking）保護快取局部性與遞增冷卻。

---

## 二、六面向各自的業界做法

### 面向 1：新帳號接入（發現、登入、隔離、模型與思考等級探測、人手邊界）

1. **帳號發現（Discovery）**：
   - **被動掃描＋特徵檔驗證**：如 OmniKit 現有 `engine/scripts/homes.py`、`CodexBar`、`ClaudeBar` 的做法：依序檢查「環境變數（`CLAUDE_CONFIG_DIR`、`CODEX_HOME`、`GEMINI_CLI_HOME`）→ 啟動器設定檔（如 T3 `~/.t3/userdata/settings.json` 的 `providerInstances`）→ 慣例資料夾掃描（如 `~/.claude-*`、`~/.ccs/instances/*`、`~/.codex-*`）」，並透過特徵檔（`.claude.json`、`auth.json`）過濾非帳號目錄。
   - **顯式三步入庫校驗（標竿：`ClaudeBar`）**：加入帳號時不盲收，必須驗證：(1) 目錄內有有效憑證；(2) 解析帳號 email／組織／workspace ID，**拒絕與既有槽位重複的登入**；(3) 執行首次查詢或煙霧測試（離線時可選 Add anyway 並標 `Re-auth`）。
2. **環境隔離（Isolation）與「共享層 vs 私有層」切分**：
   - **官方原生環境變數隔離**：Claude Code 用 `CLAUDE_CONFIG_DIR`（`code.claude.com/docs/en/authentication` 官方文件明文支援；macOS Keychain 項目已以目錄雜湊做鍵值隔離）；Codex CLI 用 `CODEX_HOME`（`auth.json` 或 `cli_auth_credentials_store = "keyring"`）；Gemini CLI 用 `GEMINI_CLI_HOME`；T3 Code 則把 Antigravity 實例隔離在 `~/.t3/userdata/providers/antigravity/<sha256(實例 id)>`。
   - **共享工作層、隔離憑證層（標竿：`claude-swap`、`ccs`、`aisw`）**：開源實務發現「完全隔離整個家目錄」會導致規則（`CLAUDE.md`）、skills、MCP 與對話紀錄重複維護或斷裂。最佳解是只隔離 OAuth 憑證與 rate-limit 狀態，而透過符號連結／Windows directory junction（免管理員權限）共享 `projects` 對話歷史與規則，並將與帳號無關的 MCP OAuth 狀態獨立保留、不在切換槽位時覆寫（`claude-swap` README L159-162, L251-252）。
   - **兩大真實踩坑警訊**：
     - **切勿在新增／切換前執行 `/logout`**（`claude-swap` README L58）：新版 Claude Code 的 `/logout` 會直接向伺服器撤銷 `refresh_token`，令剛備份的舊帳號憑證立刻作廢。
     - **切勿複製 `auth.json` 或 `.credentials.json` 製造分身**（`ClaudeBar` `multi-account/README.md`）：多個獨立執行個體共用同一顆 `refresh_token` 會發生 OAuth token rotation 競態，一邊刷新就令另一邊 `invalid_grant`；同時寫入憑證必須持有官方 CLI 的鎖檔（`claude-swap` L254；`CodexBar` 非阻塞進程鎖）。
3. **模型與思考程度自動探測（能力矩陣與煙霧測試）**：
   - **動態目錄查詢**：Antigravity 生態透過 `v1internal:fetchAvailableModels` 拿即時模型鍵值、`deprecatedModelIds` 與 `tieredModelIds`（`Antigravity-Manager:quota.rs:50-81`、`opencode-antigravity-auth:models-v2.ts`）；OpenAI/Codex 與一般 API 閘道透過 `/v1/models`＋`models.dev` 快照組裝支援的 `thinking_level` / `effort` 範圍。在 T3 Code 環境則以 `orchestrator_capabilities` 為單一即時真實來源。
   - **兩階段真實性驗證（Truthful Status）**：`AIUsage` 明確區分「已組態（Prepared）」與「經真實請求證實（Proven）」；`Antigravity-Manager` 證明**單靠控制面目錄回傳 200 無法證實帳號可用**，必須搭配最小開銷的資料面煙霧探針（如 1-token 請求或極小 `generateContent`），才算驗證完成。
4. **哪些步驟「一定只能由人做」**：
   - 瀏覽器 OAuth 互動登入、Google／Anthropic／OpenAI 帳號密碼與 2FA／Passkey 授權（遠端／無頭機器則需人工於本機完成登入後貼回 callback URL 或匯入憑證）。
   - `403 VALIDATION_REQUIRED` 的真人帳戶驗證（點擊 `validation_url` 解鎖）與 `TOS_VIOLATION` 申訴（`ban_appeal_url`）。
   - macOS Keychain 首次讀取授權與 T3 MCP 配對核准（`claude mcp login t3`）。
   - 決定各帳號的用途屬性（僅人工對話 vs 允許自動派工、是否啟用付費備援）。

---

### 面向 2：健康與額度（狀態機、冷卻重試與 Google Antigravity／Gemini CLI 端點詳解）

#### (A) Google Antigravity／Gemini CLI 額度查詢全景（一手原始碼實證）

本次直接查閱 `Antigravity-Manager`（`quota.rs`）、`opencode-antigravity-auth`（`check-quota.mjs`）、`CodexBar`（`docs/antigravity.md`、`docs/gemini.md`）與 `vscode-antigravity-cockpit`（`local_quota.ts`）一手原始碼，彙整出四大查詢路徑與關鍵陷阱：

| 查詢路徑 | 端點／命令 | 採用工具 | 回傳資料與限制（一手證據） |
| :--- | :--- | :--- | :--- |
| **1. 官方 `agy` 非互動 CLI 報告** | `agy -p /usage --output-format json`（必帶環境變數 `AGY_CLI_DISABLE_AUTO_UPDATE=true`，注意小寫 `true`，`1` 無效） | `CodexBar`（`agy 1.1.11+`） | 官方於 `agy 1.1.11` 新增；無須打未公開端點、不送模型 prompt；但輸出**不含帳號與方案身分**，且登入失效時會嘗試 `open`/`xdg-open` 彈瀏覽器，工具需在暫存目錄覆寫 `PATH` 與 `BROWSER` 攔截並帶 `CODEXBAR_PROBE_OWNER` 回收殘留 MCP 子行程（`CodexBar:docs/antigravity.md:32-76`）。 |
| **2. 本機 `language_server` / `agy` 內嵌 HTTPS** | `RetrieveUserQuotaSummary` → 回退 `GetUserStatus` → `GetCommandModelConfigs` | `CodexBar`、`vscode-antigravity-cockpit`、`AntigravityQuota`、`AntigravityQuotaWatcher` | 僅在 Antigravity 桌面版或 `agy` 運行時可用；**`agy 1.2.2+` 起拒絕無 CSRF token 之本機請求並回 `401 missing CSRF token`**，且不對外暴露該 token（`CodexBar:docs/antigravity.md:44-47`）。 |
| **3. Cloud Code 內部 OAuth RPC（Antigravity）** | **優先**：`POST https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary`<br>**備援**：`daily-cloudcode-pa.sandbox.googleapis.com`；輔以 `v1internal:loadCodeAssist`（取 `projectId` 與 `paidTier`/`currentTier`/`ineligibleTiers`）與 `v1internal:fetchAvailableModels` | T3 Code、`Antigravity-Manager`、`opencode-antigravity-auth`、`CodexBar`、`CLIProxyAPI`、`Sub2API`、`AIClient2API`、`OpenTokenUsage` | 回傳官方兩大配額群組（`Gemini Models` 與 `Claude and GPT models`）的 **5 小時與每週 `remainingFraction` + `resetTime`**。<br>**關鍵陷阱 1（Host 不一致）**：不可回退至 Prod（`cloudcode-pa.googleapis.com`），`Antigravity-Manager:quota.rs:30-33` 實測 Prod 與 Daily 回傳的 Gemini 配額會跳變（耗盡帳號報 100%、可用報 0%）。<br>**關鍵陷阱 2（假 100%）**：`fetchAvailableModels` 回傳全 100% 僅代表模型列表可見、不代表實際配額（`CodexBar:docs/antigravity.md:126-127, 154-156`）。<br>**關鍵陷阱 3（控制面 200 無法測封禁）**：被 TOS 封禁的帳號打 `loadCodeAssist` / `fetchAvailableModels` / `retrieveUserQuotaSummary` / `countTokens` **仍然回 200**，只有真正打資料面 `v1internal:generateContent` 才回 `403 PERMISSION_DENIED + TOS_VIOLATION`（`Antigravity-Manager:quota.rs:160-169`）。 |
| **4. Gemini CLI 舊端點（消費端已停服）** | `POST https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota`（帶 `ideType: GEMINI_CLI`）；以及網頁版 `gemini.google.com/usage` GraphQL（`GXU_FIVE_HOURLY`/`GXU_WEEKLY`） | `CodexBar`、`gcli2api`（舊） | **重大變動**：Google 已於 **2026-06-18** 停服個人、AI Pro、Ultra 帳號之 Gemini CLI OAuth（僅保留 Standard/Enterprise 與 Workspace/教育版）。消費帳號呼叫 `loadCodeAssist` 會收到 HTTP 200 但 `ineligibleTiers[].reasonCode == "UNSUPPORTED_CLIENT"`，續打 `retrieveUserQuota` 則回 `403 SUBSCRIPTION_REQUIRED`（`CodexBar:docs/gemini.md:120-132`）。 |

#### (B) Claude Code 與 Codex 的額度查詢方式（一手對照）
- **Claude Code**：
  1. **官方狀態列 JSON**（最合規零額外請求）：`statusline` 輸入包含 `rate_limits.five_hour` 與 `rate_limits.seven_day.used_percentage`（限 Pro/Max/Ultra，首輪回應後出現；OmniKit 已採用）。
  2. **OAuth Usage API**：`GET https://api.anthropic.com/api/oauth/usage?cedar_ember=1`（Header 帶 `anthropic-beta: oauth-2025-04-20`，需 `user:profile` scope），回傳 `five_hour`、`seven_day`、`seven_day_sonnet`、`seven_day_opus`、`limits[].weekly_scoped`、`extra_usage`（`CodexBar:docs/claude.md:238-261`）。注意 `claude setup-token` 僅含 `user:inference` scope 打不到該端點，`claude-swap` 因此提供預設關閉的 `usage.headerProbe`（送 1-output-token Haiku 請求從回應標頭讀 5h/7d 利用率）。
- **OpenAI Codex**：透過 `auth.json` OAuth API、Codex CLI RPC 或 Web Dashboard 讀取 5 小時／每週與模型專屬限額（如 `additional_rate_limits[]`）；本機憑證鮮度採過期前 5 分鐘或 `last_refresh` 逾 8 天判別，不可依檔案 mtime（`CodexBar:docs/codex.md:107-110, 155-158`）。

#### (C) 異常分類、六維正交狀態機與冷卻重試
業界成熟工具不再用單一布林 `healthy: true/false`，而是依錯誤語意做精細分流：

| 錯誤碼／徵兆 | 正交狀態分類（標竿：`Antigravity-Manager`、`CLIProxyAPI`、`claude-swap`、`Subpool`） | 正確處置方式 |
| :--- | :--- | :--- |
| **`401` / OAuth `invalid_grant`** | `auth_revoked`（持久化 `disabled: true` + `disabled_reason`） | 立即移出可用池、**禁止背景重複刷新**以免製造風暴；提示使用者重登或更新 token（token 變更時自動清除 disabled 狀態）。 |
| **`403` + `VALIDATION_REQUIRED` / `validation_url`** | `validation_blocked`（帶 `validation_blocked_until` 與驗證連結） | 暫時隔離並將 `validation_url` 推給使用者點擊驗證，**不誤判為永久封禁**。 |
| **`403` + `TOS_VIOLATION` / `account_banned` / `service has been disabled in this account`** | `banned`（需資料面確認；擷取 `ban_appeal_url`） | 永久停用並保留證據，**絕不可被控制面 HTTP 200 沖刷解鎖**；亦不可將 GCP 專案級 `SERVICE_DISABLED` 誤判為帳號封禁。 |
| **`403` + `Location not supported`** | `hard_forbidden`（地區或網路出口不支援） | 標示網路／區域問題，維持鎖定不被 200 沖刷。 |
| **`403` + 特定模型無權限（如試用 Pro 無 Claude 5.5）** | `forbidden_models`（模型級排除） | 只排除該帳號的該模型，同帳號其他模型照常可用。 |
| **`429` 速率限制／配額耗盡** | `cooldown`（按 `(帳號, 模型家族)` 獨立追蹤，可持久化成 `.cds` 或 JSON 防重啟失憶） | 區分「短暫限流（<= 5 秒，原帳號小等重試）」與「窗口耗盡（依 `Retry-After` 或 `resetTime` 進冷卻，無標頭則指數退避如 30 秒起跳至 30 分鐘上限）」。配額查詢失敗時**保留上次已知快照並標示 stale**，不中斷推理也不歸零為 0%（`Subpool`、`CodexBar`、`claude-swap` 共同準則）。 |
| **輪詢探針與推理端點解耦** | 獨立 Health Tracker（`QUOTA_ENDPOINT_HEALTH`） | 絕不讓背景額度輪詢超時把主推理端點標壞（`Antigravity-Manager:quota.rs:9-17`）。 |

---

### 面向 3：選帳號策略、並行控制、Session 親和與接手方式

1. **主流選帳號演算法比較**：
   - **`sticky`（黏著優先，Coding Agent 預設首選）**：固定同一帳號直到觸發冷卻或高水位門檻，最大化 Anthropic／OpenAI／Gemini **Prompt Cache 命中率**並減少 TTFT；`opencode-antigravity-auth`、`CLIProxyAPI`、`Sub2API`、`Subpool` 皆將其列為多輪對話關鍵。
   - **`round-robin` / `weighted-round-robin`**：逐請求輪詢或依權重（如 `Subpool` 4:1、`CLIProxyAPI` 整數權重與 credit 補償）分攤，吞吐最高但**嚴重破壞 Prompt Cache**，僅適合無狀態單輪批次任務。
   - **`fill-first` / `priority`**：依帳號優先級（如 `Ultra > Pro > Free` 或 `claude-swap` tier 0–1000）先耗盡高優先或即將到期帳號再往下一層溢流。
   - **`least-used` / `headroom`**：挑選目前進行中負載最低或剩餘額度百分比最高者（`claude-swap` 的 `best`）。
   - **`expiry-first` / `weekly-first` / `consume-first`（訂閱制專屬創新）**：`OmniRoute` 與 `claude-swap` 均實作此策略——因為訂閱制「沒花完的每週額度到重置時間就歸零作廢」，因此優先消耗**最早重置且仍有剩餘額度**的帳號。
   - **`quota-weighted` / `hybrid` 綜合評分**：`OmniRoute` 以 `剩餘額度 / 進行中併發負載` 比例加權並保持既有對話黏著；`opencode-antigravity-auth` 結合「健康分（0–100）＋ Token Bucket（上限 50、每分鐘回 6）＋ LRU」。
   - **防震盪機制（必備）**：`claude-swap` 用「5 分鐘切換冷卻＋遲滯區間（hysteresis margin）」；`Subpool` 規定同優先級帳號必須剩餘額度領先 **> 5 個百分點**才觸發預設綁定切換，防止帳號在閾值線附近來回翻滾。
2. **每帳號並行上限（Concurrency Cap）與多行程防撞**：
   - `Sub2API` 設每使用者與每帳號雙層併發上限；`Subpool` 預設每上游帳號上限 16 active turns、每金鑰 32 條 WS 連線（超限回 HTTP 503 `subpool_capacity_exceeded`）；`CLIProxyAPI` 具 `credentials.concurrency` 契約與心跳回收（`reclaim-grace: 5s`）。
   - 多子代理平行啟動防撞：`opencode-antigravity-auth` 提供 `pid_offset_enabled: true` 依行程 PID 錯開初始帳號；針對 Google Antigravity 消費方案，Google staff 建議維持低並行（一次一條，見 11-22 查證）。
3. **Session 親和（Session Affinity）實作細節**：
   - **識別鍵優先鏈（標竿：`CLIProxyAPI:config.example.yaml:201-208`）**：顯式 Session Header（`X-Session-ID`、`session_id`、Claude/Codex/OpenCode header）→ `prompt_cache_key` → Responses `previous_response_id` → Merkle LCP 歷史前綴雜湊（需 >= 2 輪共享尾段，否則 compaction 後會重綁）→ 首則訊息雜湊。
   - **反向代理暗坑**：Nginx 預設丟棄含底線的 Header（如 `session_id`），須加 `underscores_in_headers on`（`Sub2API` README L235-239）。
   - **子代理親和繼承與重綁控制**：`CLIProxyAPI` 支援 `session-affinity-subagents: true`（同模型子代理繼承父對話憑證共享 KV Cache，設 `false` 則打散追求並行）與 `session-affinity-rebind-on: any | quota | never`（設 `quota` 時，遇 5xx/408 僅單次借道備援、不解除原綁定，遇 429/401/403 才永久重綁）。`Subpool` 則採取更嚴格的不變量：**絕不跨帳號重播既有 `previous_response_id` 鏈或已建立的 WebSocket**，僅對新對話／unbound turn 做配額路由。
4. **額度用完時的四種接手模式**：
   - **模式 A：Fail-Closed（絕不意外花錢）**：如 `OmniRoute` 的 `auto/subscription`，只消耗已付費訂閱額度，耗盡即停止並回報精確 `resetsAt`，絕不自動切進按量付費 API。
   - **模式 B：同家換帳號（具規約前提）**：合規 API Key 池可直接切換下一個金鑰；消費訂閱帳號則應先停止自動輪換，改為輸出「剩餘額度表＋重置時間＋建議手動切換目標」由人切換（或透過 `claude-swap`／`CLAUDE_CONFIG_DIR` 搭配 `--resume` 接續）。
   - **模式 C：訂閱優先→按量 API／贈金兜底→重置自動切回**：如 `OmniRoute` 的 `auto/thrifty` 與 `Subpool` 三層排序（訂閱 > 快到期促銷贈金 > 預付點數），當訂閱窗口重置後自動切回訂閱池。
   - **模式 D：跨廠牌／同廠牌降級**：參考 11-22 調研與 `OpenClaw` 雙階段 Failover（認證／配額錯先同家處理，模型未知／下架直接跨模型備援；且高風險任務設能力閘門，不可降級至弱模型如 3.8 Flash）。

---

### 面向 4：規約與停權（三大廠一手條款原文、執法案例、降風險與官方支援做法）

> 以下條款原文均於 **2026-11-23** 直接抓取官方頁面核對；非官方論壇與媒體轉述均明確標註來源或 `【待驗證】`。

#### (A) 三大廠一手規約與官方支援做法對照

| 供應商 | 一手來源（查證日期：2026-11-23） | 對「同一人多訂閱帳號」 | 對「自動輪換」與「第三方工具／代理驅動訂閱」 | 官方明確支援的做法 |
| :--- | :--- | :--- | :--- | :--- |
| **Google Antigravity** | 1. [Additional Terms of Service](https://antigravity.google/terms)（第 6 段）<br>2. [Antigravity FAQ](https://antigravity.google/docs/faq)<br>3. [Gemini Code Assist Individuals Deprecation](https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals)（經 CodexBar 引述） | 官方條款與 FAQ **未明文禁止**同一人擁有多個個人付費帳號並手動切換；論壇 Google staff 曾稱個人付費帳號手動切換不違規（見 11-22 報告引述 `discuss.ai.google.dev/t/174378`）。同機多帳號**同時並發**無官方明文，非 staff 回覆稱與號池無法區分有停權風險【待驗證】。 | **明確禁止**。<br>• Additional ToS 原文：*"Using third party software, tools, or services to access the Service (e.g. using OpenClaw with Antigravity OAuth) is a breach of this Agreement. Such actions may be grounds for suspension or termination of your Antigravity and/or Gemini CLI accounts."*<br>• FAQ 原文：*"Wrapping `agy` inside third-party coding agents or applications, or automating account rotation, is not supported under consumer plans."* 另一題點名 Claude Code、OpenClaw、OpenCode 為違反 ToS，可能導致停權或終止帳號。 | • 在官方 Antigravity IDE／CLI、或 ACP 用戶端（如 T3 Code）由**人自行互動操作**單一帳號。<br>• 帳號內建平行（Subagents、`/swarm`、Orchestrator）。<br>• 本機直接腳本或 CI 執行 `agy -p`。<br>• 第三方 coding agent 或自動化存取 Gemini：**官方 FAQ 明文建議改用 Gemini Enterprise 或 Google AI Studio API key**（或 Vertex AI）。 |
| **Anthropic (Claude / Claude Code)** | 1. [Consumer Terms of Service](https://www.anthropic.com/legal/consumer-terms)（Effective Oct 8, 2025）<br>2. [Claude Code Legal & Compliance](https://code.claude.com/docs/en/legal-and-compliance)<br>3. [Claude Code Authentication](https://code.claude.com/docs/en/authentication) | **官方明文支援同一人以多目錄登入多帳號**。<br>• Authentication 原文（"Log in with multiple accounts"）：*"To stay signed in to multiple accounts at once, such as work and personal accounts, give each account its own configuration directory. When you start `claude`, set the `CLAUDE_CONFIG_DIR` environment variable..."*<br>• Consumer Terms 僅明文禁止將帳號給**他人**用：*"You may not share your Account login information, Anthropic API key, or Account credentials with anyone else. You also may not make your Account available to anyone else."*<br>• **勘誤備註**：多篇二手部落格稱 Consumer Terms 含「禁止建立多帳號規避限額」字句，經 2026-11-23 檢索 `consumer-terms` 原文未出現 `multiple` 或 `circumvent` 字眼，該具體條文引述屬【待驗證】；實務風險係來自下欄之「非 API key 自動化」條款。 | **明確禁止第三方中轉與非 API key 自動化**。<br>• Consumer Terms 原文：*"Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it, to access the Services through automated or non-human means, whether through a bot, script, or otherwise."*<br>• Claude Code Legal 原文：*"OAuth authentication is intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications... Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users. Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens."* | • 以 `CLAUDE_CONFIG_DIR` 隔離多個個人／工作官方 Claude Code 目錄並由官方未修改之 `claude` 執行。<br>• 使用官方 `claude.ai` OAuth 登入原生 Claude Code。<br>• 第三方工具、自建代理或 Agent SDK 整合：**使用 Claude Console API Key、Amazon Bedrock、Google Vertex AI 或 Microsoft Foundry**。<br>• 官方另提供 Extra Usage 按量加購（2026-04 政策調整相關報導見下）。 |
| **OpenAI (ChatGPT / Codex)** | 1. [Terms of Use](https://openai.com/policies/row-terms-of-use/)<br>2. Codex CLI 文件（`auth.json`、`CODEX_HOME`） | Terms of Use 禁止**分享帳號給他人**：*"You may not share your account credentials or make your account available to anyone else..."*；未見禁止同一人於工作與個人用途持有個別帳號（且網頁／行動端提供官方帳號切換）。 | **明確禁止自動化擷取與規避限流**。<br>• Terms of Use 原文：*"Automatically or programmatically extract data or Output."* 及 *"Interfere with or disrupt our Services, including circumvent any rate limits or restrictions or bypass any protective measures or safety mitigations we put on our Services."* | • 以獨立 `CODEX_HOME` 隔離個人／工作設定環境，由官方 Codex CLI／IDE 執行。<br>• 自動化程式、背景排程與高併發代理：使用 **OpenAI API Key**（依 Tier 按量計費）或 Team/Enterprise 方案。 |

#### (B) 實際執法與停權案例（區分媒體／一手證據與社群回報）
- **Google Antigravity 執法（已有多源確認）**：2026-02 起 Google 切斷 OpenClaw 等工具經 Antigravity OAuth 之存取（VentureBeat、The Register 報導，見 11-22 報告引用）；`badrisnarayanan/antigravity-claude-proxy`（README L11-22）、`lbjlaq/Antigravity-Manager`（`quota.rs:160-169`、`account.rs:127-145`）均於一手原始碼與首頁明文證實上游已大規模對代理連線帳號發放資料面 `403 PERMISSION_DENIED + TOS_VIOLATION`（停用該帳號之 Antigravity／Gemini CLI 服務，非刪除整個 Google 帳號）。Google AI 開發者論壇亦有多起付費 Pro/Ultra 用戶申訴案，並提及個人帳號僅有**一次性申訴復權機會**【論壇說法，待驗證是否寫入正式條款】。
- **Anthropic 執法演進（媒體與社群紀錄【部分細節待驗證官方公告原頁】）**：2026-01-09 技術封鎖偽造 Claude Code 標頭之第三方工具（回傳 `"This credential is only authorized for use with Claude Code"`）；2026-02-19 更新合規文件明確禁止第三方工具使用消費訂閱 OAuth（如 `code.claude.com/docs/en/legal-and-compliance` 一手原文所示）；2026-04-04 社群報導 Anthropic 團隊調整規則，第三方工具接入訂閱憑證不再消耗月費池而須走 Extra Usage 或 API key【部落格轉述，待驗證官方公告原頁】。
- **OpenAI 執法**：主要鎖定多人共用號池、轉售與自動化繞過限流；單機自用 `codex-lb` 之封號比率缺乏一手統計【待驗證】。

#### (C) 工具界常見的「降風險」分界：合規降風險 vs 高風險對抗
- **合規降風險做法（OmniKit 可採納）**：
  1. **嚴格區分 `auth_mode`（訂閱 vs API Key）並設 ToS 閘門**：如 `OmniRoute` 的 `FREE_TIER_TOS`、`Subpool` 預設關閉自動輪換、`claude-swap` 預設不輪換到 API key 帳號、`vibeproxy` 導入官方核准的 **Vercel AI Gateway** 路徑。
  2. **不碰憑證中轉、只做唯讀觀測＋本機官方目錄隔離**：如 `CodexBar`、`ClaudeBar`、`vscode-antigravity-cockpit`（絕不偽造官方 client、不幫其他工具代理消費 OAuth）。
  3. **降低異常行為特徵**：單帳號低併發（Antigravity 一次一條）、自適應降低額度輪詢頻率（`claude-swap` 活躍快刷、閒置慢刷＋跨機共享快照）、遇 401/403 立即停止重試。
- **高風險對抗做法（OmniKit 絕不可採納）**：
  - Go uTLS 模擬瀏覽器指紋繞過 Cloudflare（`AIClient2API`、`CLIProxyAPI`）、綁定住宅代理 IP 掩飾多帳號同源（`Sub2API`、`CLIProxyAPI` 贊助與實務生態）、偽造官方 IDE `User-Agent` 供第三方 agent 偷渡消費訂閱 OAuth。這些屬於與平台風控正面對抗，一旦特徵更新會導致整批帳號連坐停權。

---

### 面向 5：可觀測性（儀表板、紀錄、告警、手機通知）

1. **多層次呈現載體**：
   - **桌面選單列／系統匣（最高頻接觸點）**：`CodexBar`（macOS/Linux）、`ClaudeBar`（macOS＋Notch＋Touch Bar）、`Quotio`、`CCS Bar`、`AIUsage`、`ai-usage-menubar`、`claude-swap` menubar。核心顯示元件為「5 小時＋每週剩餘進度環／條」、「重置倒數（`Resets in Xh Ym`）」、「當前速度預報（Forecast：照目前速率會不會在重置前耗盡）」與「已存重置次數（banked resets）」。
   - **本機 Web 儀表板與 TUI**：`OmniRoute`、`Antigravity-Manager`、`CLIProxyAPI` 生態（`CPA-Manager-Plus`、`cpa-usage-keeper`）、`Sub2API`、`codex-lb`、`claude-swap` (`cswap watch` TUI)。
   - **編輯器內建與零上下文污染狀態列**：`vscode-antigravity-cockpit`（VS Code 狀態列＋Webview）、`slkiser/opencode-quota`（不污染對話 context window）、Claude Code 原生 `/statusline`。
2. **結構化紀錄與遙測輸出**：
   - **JSONL 事件流＋版本契約**：`claude-swap` 輸出帶 `schemaVersion: 1` 的 JSONL（`poll`、`switch`、`account-quarantined`、`all-exhausted`、`error`）；OmniKit 既有 `~/.omnikit/dispatch/log.jsonl` 完全契合此模式。
   - **Prometheus Metrics 與智慧家庭整合**：`Subpool` 暴露 `/metrics`（區分 `unbound` / `continuation` / `connection` 路由邊界與容量拒收原因）；`codex-lb` 社群甚至提供 Home Assistant 整合（`codex-lb-rates`）監控 5h/weekly/monthly 感測器。
   - **跨機器輪詢去重（工程亮點）**：`claude-swap` 透過 `cswap list --json | ssh laptop cswap import-usage - --hold 600` 讓單機輪詢並分發讀數，避免多台電腦同時打 Anthropic usage API 撞上每帳號的查詢頻率上限。
3. **告警與手機通知機制**：
   - **多段閾值與滯後復歸**：常見 50% / 75% / 90%（或 Healthy / Warning / Critical / Depleted 四級）告警，並於配額重置回升後自動 re-arm（`CodexBar:docs/claude.md:269-278`）。
   - **手機端即時推播實務**：
     - **iOS 鎖定畫面 Live Activity / Widget**：`ClaudeBar` 透過第三方推播載體 **Notify!**（免自建 iOS App，最密每分鐘更新一次）將最緊配額與最多 6 個視窗送到 iPhone 鎖定畫面與桌面小工具；`iebb/when-reset` 採原生 SwiftUI + Cloudflare Workers 靜默刷新。
     - **Telegram / Discord Webhook / Email**：`davedavedavenm/ai-usage-dashboard`、`CodeNotch` 與 Claude Code 原生 `Notification`/`Stop` Hooks 推送至 Telegram Bot／Discord Webhook；`Subpool` 內建透過 Resend 寄送**每日定時團隊配額與重置報表**（具 DB lease 防重發與冪等鍵）；`Sub2API` 有原生行動管理 App `sub2api-mobile`。

---

### 面向 6：給不同使用者用（設定檔 Schema 與初次設定流程）

1. **業界設定 Schema 的五大共識**：
   - **「帳密憑證（機密、不進 Git）」與「策略／角色設定（可進 Git、跨機共享）」嚴格分離**：`opencode-antigravity-auth` 拆為 `antigravity-accounts.json`（含 refresh token，僅存本機）與 `antigravity.json`（策略設定，帶 `$schema` 校驗）；`claude-swap` 的 `export` 預設剝離本機裝置與 MCP 憑證；`Subpool` 將憑證加密存於 DB，報表人員映射放環境變數。
   - **宣告式帳號描述必備欄位**：
     - `id`（穩定不透明鍵，如實例 ID）、`label`（自訂別名，如「個人」「工作」）、`provider` / `driver`、`auth_mode`（`subscription` | `api_key` | `vertex` | `aggregator`）、`plan_tier`（`ultra` | `max_20x` | `max_5x` | `pro` | `free` | `payg`）、`usage_policy`（`manual_only` | `auto_eligible` | `fallback_only`）、`priority` / `weight`、`max_concurrency`、`config_dir` / `home_path`、`enabled` / `paused`、`tos_ack`（若使用者知情自負風險啟用非建議路徑之顯式記錄）。
   - **強型別校驗＋未知欄位提醒**：`opencode-antigravity-auth` 發布官方 JSON Schema 供編輯器自動補全；`claude-swap` 提供 `cswap config set` 範圍驗證並警告設定檔中拼錯或未讀取的鍵值。
   - **漸進式揭露（Progressive Disclosure）**：`opencode-antigravity-auth` 的最小設定僅需 3 行（只指 `$schema`），依帳號數量給預設範本（1 帳號用 `sticky`、2–3 帳號用 `hybrid`、多帳號平行才開 `pid_offset_enabled`），進階健康分與冷卻參數全部收進可選進階區。
2. **初次設定（Onboarding）最佳流程**：
   - **自動掃描 → 人工確認分類 → 煙霧測試 → 產出個人設定檔**：
     1. **探測現有環境**：自動掃描本機已裝 CLI、T3 `providerInstances`、各 `CLAUDE_CONFIG_DIR` / `CODEX_HOME` 與環境變數 API Key（不碰密碼庫與 `statev2.sqlite`）。
     2. **簡短訪談（3–5 題）**：確認每個帳號的方案等級（Pro/Max/Ultra/API）、用途邊界（僅人開對話手動切換 vs 允許自動派工）、額度用完偏好（Fail-Closed 停下來等人切 vs 自動溢流至付費 API/抵免額）、思考程度偏好（如 `max_available` vs 省額度預設）與通知管道（無／桌面／Telegram／Discord）。
     3. **能力實測與去重**：對啟用實例跑一次唯讀目錄查詢（如 T3 `orchestrator_capabilities`）＋選配最小煙霧測試，驗證模型與思考等級上限，自動產生 `~/.omnikit/dispatch/account-pool.json`（本機狀態）與 `data/profiles/<user>/dispatch.md`（策略設定）。

---

## 三、對 OmniKit 的機制建議（分「必做」「選配」，含規約風險界線）

結合 OmniKit 現況（以 T3 Code 統一操作多實例、`engine/scripts/homes.py` 已能發現多目錄、11-19 Plan B 與 11-22 多使用者角色化將於 12-01 實作、Ryan 已定案 Gemini Pro 帳號池 1A＋2B），以下將建議切分為 **必做**、**選配** 與 **規約紅線**。

### A. 必做（建議併入 12-01 帳號池與 Plan B 實作）

1. **建立「帳號能力 × 規約屬性」三層分離 Schema（依託 `data/profiles/<user>/dispatch.md` ＋ `~/.omnikit/dispatch/`）**
   - **做法**：在 `data/profiles/<user>/dispatch.md` 的 `instances` 補齊標準欄位：`auth_mode`（`subscription` | `api_key` | `vertex`）、`plan_tier`、`usage_scope`（`manual_only` | `auto_dispatch` | `fallback_api`）、`max_concurrency`（預設消費訂閱 `1`）、`thinking_preference`、`paused`；同時新增全域 `data/rules/provider-terms-policy.yaml` 定義各 `(driver, auth_mode)` 的 `tos_verdict`（`ok` | `caution` | `avoid`）、`allow_auto_rotation`、`allow_third_party_dispatch`。本機即時健康與額度快照存於 `~/.omnikit/dispatch/pool-state.json`（不進 Git，絕不存任何 OAuth token 或讀 T3 `statev2.sqlite`）。
   - **依據**：`OmniRoute` 的 `FREE_TIER_TOS`、`opencode-antigravity-auth` 帳號與策略雙檔分離、`claude-swap` 設定範圍驗證、以及 11-22 多使用者調研之結構化 ToS 建議。
2. **實作 6 維正交健康狀態機與持久化冷卻檔（`~/.omnikit/dispatch/cooldowns.json`）**
   - **做法**：於 `dispatch.py` 區分 `manual_paused`、`auth_expired`（401/`invalid_grant`）、`validation_required`（403 驗證連結）、`tos_banned`（403 `TOS_VIOLATION`）、`model_forbidden`（模型級 403）、`quota_cooldown`（429 帶 `resets_at`）。規則：(a) 系統鎖解除不可覆寫 `manual_paused`；(b) 查不到最新額度時保留上次快照標 `stale`，絕不當作 0% 或 100%；(c) 每次 `run.py log` 紀錄 `error_type` 並寫入冷卻時間。
   - **依據**：`Antigravity-Manager:src-tauri/src/models/account.rs`（6 維正交狀態與防 200 沖刷設計）、`CLIProxyAPI`（`.cds` 持久化冷卻）、`Subpool`（查詢失敗保留快照不阻斷）。
3. **新帳號接入檢核與「最小資料面煙霧測試」指令（擴充 `homes.py` ＋ `dispatch.py doctor`）**
   - **做法**：擴充 `homes.py` 發現新帳號後，提供一條 `dispatch.py probe`（唯讀目錄同步透過 T3 `orchestrator_capabilities` ＋ 選配最小 1 輪煙霧測試）確認「模型清單、支援思考程度（含 `xhigh`）、是否讀到 OmniKit 規則、資料面是否未遭 403 `TOS_VIOLATION`」；在 `omnikit-setup` 增加 4 題帳號池訪談（方案、手動/自動邊界、額度耗盡是否允許切 API、思考等級偏好），明確列出「瀏覽器登入、T3 加實例、`validation_url` 驗證、不可先跑 `/logout`」等必由人手完成事項。
   - **依據**：`Antigravity-Manager:quota.rs:160-169`（控制面 200 測不出封禁）、`ClaudeBar` 三步入庫校驗、`AIUsage` Truthful Status、`claude-swap` `/logout` 警訊。
4. **唯讀額度統合視圖與「手動換號建議」引擎（不碰自動輪換）**
   - **做法**：整併各帳號可合法取得的額度訊號：Claude 沿用官方 `statusline` 快照（擴充支援多 `CLAUDE_CONFIG_DIR` 分帳號紀錄）；Antigravity 優先等 T3 暴露配額介面，或於使用者手動執行巡檢時呼叫 `agy -p /usage --output-format json`（必帶 `AGY_CLI_DISABLE_AUTO_UPDATE=true` 與無頭防彈窗保護，且限查詢單一已登入帳號，不做 OAuth 代理）。在 `run.py show` 與本機儀表板顯示所有帳號剩餘比例、重置倒數與**「建議下一條對話手動切到哪個帳號」**（依 `expiry-first` 最快週重置優先或 `headroom` 剩餘最多排序，但**只建議、不自動切換消費訂閱帳號**）。
   - **依據**：`CodexBar:docs/antigravity.md:32-67`、`claude-swap` `weekly-first` 演算法、Ryan 11-22 定案 1A（消費訂閱人工切換）。
5. **明確的「額度用完接手政策」開關（Fail-Closed vs Thrifty API Fallback）**
   - **做法**：為每位使用者在 profile 提供明確選項 `on_exhausted: fail_closed | prompt_manual_switch | fallback_paid_api`：預設 `prompt_manual_switch`（停下來顯示剩餘額度表與重置時間，由人決定換哪個訂閱帳號或同意切 API）；已設定 Gemini API Key / Vertex 抵免額者可選 `fallback_paid_api`（訂閱滿載時自動轉合法 API 通道，待訂閱重置自動切回）；重視零意外帳單者可選 `fail_closed`。
   - **依據**：`OmniRoute` 的 `auto/subscription`（fail-closed）與 `auto/thrifty` 雙模式、`Subpool` 三層排序（訂閱 > 快到期贈金 > 預付點數）。
6. **主線與子任務「同帳號黏著＋低併發」與跨帳號共享上下文**
   - **做法**：對同一工作階段維持帳號黏著（保護 Prompt Cache）；同一消費帳號同時僅派 1 條自動化任務（`max_concurrency: 1`），不並發轟炸。換帳號接續工作時，沿用 OmniKit 既有 `NOW.md` ＋交接檔，加上 `homes.py` 確保所有隔離目錄（`~/.claude-*`、`~/.codex-*`）皆同步最新規則與 skills。
   - **依據**：`CLIProxyAPI` Session Affinity、`opencode-antigravity-auth` `sticky` 策略、Google Antigravity staff 低並行建議、`claude-swap` 共享規則／隔離憑證架構。

### B. 選配（依使用者規模與痛點逐步加裝）

1. **合法付費 API Key／Vertex 池自動輪換與加權路由**：針對「只用官方 API Key／多組專案抵免額」的進階使用者，開放 `allow_auto_rotation: true`，支援 `sticky`、`fill-first`、`quota-weighted`（`剩餘額度 / 進行中併發數`）與 `> 5%` 防抖切換門檻（依據：`Subpool`、`OmniRoute`、`CLIProxyAPI`）。
2. **選單列／系統匣與手機告警整合**：在 `dispatch.py` 輸出標準化 JSON（帶 `schemaVersion: 1`）與閾值事件（達 75% / 90%、進入冷卻、窗口重置完成），讓使用者透過 Webhook 選配接上 **Telegram Bot / Discord / Notify!（iPhone Live Activity）** 或整合既有工具如 `CodexBar` / `ClaudeBar`（依據：`ClaudeBar` Notify!、`ai-usage-dashboard`、`claude-swap` JSONL 事件流）。
3. **多機共用帳號之唯讀額度同步（防查詢限流）**：透過 `b40609/omnikit-status` 私有 repo 或 SSH 傳遞帶時間戳與 `--hold` TTL 的額度快照，避免公司電腦與家裡電腦重複打同一帳號的額度查詢（依據：`claude-swap` `import-usage --hold`）。
4. **進階消耗速度預報（Pacing / Burn-rate Forecast）**：依最近數小時耗用斜率推算「依目前節奏會在重置前幾小時耗盡」，於長任務開工前主動提醒改派或降思考等級（依據：`ClaudeBar` Forecast、`CodexBar` Burndown）。

### C. 規約不允許的做法與明確風險（OmniKit 必須標紅線並預設關閉）

| 做法 | 涉及平台 | 風險等級與一手依據 | OmniKit 處置建議 |
| :--- | :--- | :--- | :--- |
| **把多組消費訂閱帳號放進自動輪換代理（如 `CLIProxyAPI`、`Sub2API`、`Antigravity-Manager` 反代、`opencode-antigravity-auth`、`AIClient2API`、`9Router`）** | Google Antigravity、Anthropic Claude Pro/Max/Ultra、OpenAI ChatGPT/Codex | **極高（已大規模實質執法）**。Google Additional ToS 第 6 段與 FAQ 明文禁止第三方工具存取與消費方案自動輪換（實測發放 `403 TOS_VIOLATION` 停權）；Anthropic Legal 明文禁止第三方應用收集／中轉消費 OAuth token；OpenAI ToS 禁止自動化規避限流。 | **絕不內建、絕不預設啟用**；若使用者自行在外部使用並知情自負風險（如 Ryan 2B 維持單一 `antigravity_ryan`），必須顯式標記 `tos_ack: user_accepted_risk`、鎖定 `max_concurrency: 1` 禁止輪換，並在 `run.py show` 持續提示合規替代路（Gemini API Key / Vertex）。 |
| **用非 API Key 消費訂閱跑無人值守高頻自動化／CI／多帳號同時並發** | Google Antigravity、Anthropic、OpenAI | **高**。Anthropic Consumer Terms 明文禁止非 API Key 之自動化 bot/script 存取；OpenAI ToS 禁止自動化擷取；Google Antigravity 消費方案多號同機並發在社群回報與號池行為無法區分【待驗證】。 | 自動化背景排程（如 `schedule_task` 定期巡檢、跨廠牌自動審查 R1）一律優先導向 **API Key／Vertex 通道**；消費訂閱僅供人開對話與經核准之單線互動輔助。 |
| **多人共用／拼車／轉售消費訂閱帳號池** | Google、Anthropic、OpenAI 全數禁止 | **極高（明確違約）**。Anthropic Consumer Terms 與 OpenAI Terms of Use 皆一字明文禁止將帳號憑證提供給他人使用。 | OmniKit 設計上嚴格定位為**單人本機工具**，禁止任何多人共享消費訂閱池功能。 |
| **使用 uTLS 指紋偽造、住宅 IP 輪換或爬蟲繞過風控** | 所有供應商 | **極高**。刻意規避平台防護措施直接違反 OpenAI ToS（*"bypass any protective measures"*）與各家反濫用條款，易導致連坐永久封鎖。 | **明文禁止進入 OmniKit 程式碼與規則**。 |

---

## 四、飽和調研紀錄（五項必附）

### 1. 納排準則與詞彙擴展軌跡

- **納入對象**：支援管理多組 AI/LLM 訂閱帳號、OAuth token 池、多憑證／多 API key 輪換、配額與健康度監控冷卻（含 `retrieveUserQuota` 等探測端點）、帳號環境隔離切換（如 `CLAUDE_CONFIG_DIR`／`CODEX_HOME`）、或給 coding agent 使用的多帳號代理／外掛／告警面板。
- **排除對象**：僅單一帳號聊天客戶端、與 LLM／coding agent 無關的通用 OAuth 函式庫／傳統負載均衡器（Nginx、Traefik、HAProxy）／瀏覽器反指紋／遊戲帳號切換器、以及無工具本體的純心得文或商業中轉站廣告清單。
- **詞彙擴展軌跡**（共 12 組，起手 3 組含中文與不含 AI/agent 的通用詞，後續皆從前輪結果抽詞擴展）：
  - 起手 1–3 組：`"Antigravity 多帳號 切換"`（中文）、`"LLM quota failover"`、`"OAuth token pool proxy"`（不含 AI/agent）＋ 對 `lbjlaq/Antigravity-Manager`、`router-for-me/CLIProxyAPI`、`cheaper-inference/OmniRoute` 執行 `sweep.py related`；
  - 擴展 4–5 組：從 `CLAUDE_CONFIG_DIR`、`ccswitch`、`codex-lb` 抽出 `"claude code multi account switcher"`、`"codex multi account load balancer"`；
  - 擴展 6 組：從 `LLM-API-Key-Proxy`、`gpt-load`、`gemini-balance` 抽出不含 AI/agent 的 `"api key pool cooldown rotation"`；
  - 擴展 7–8 組：從 `CodexBar`、`Quotio`、`ClaudeBar`、`Sub2API`、`New-API` 抽出 `"subscription quota monitor menu bar"` 與中文組 `"AI 訂閱 號池 中轉"`；
  - 擴展 9–12 組：針對隔離目錄、Google 額度內部端點、會話親和冷卻、告警推播擴展 `"multi account credential isolation profile"`、`"retrieveUserQuota fetchAvailableModels quota"`、`"sticky session rate limit cooldown proxy"`、`"ai subscription quota alert notification"`。

### 2. 查了哪些管道與每組關鍵字（`sweep.py status --min-stars 1000` 完整輸出）

執行 `uv run C:\Users\user\.claude\skills\omnikit-research\scripts\sweep.py status C:\Users\user\AppData\Local\Temp\omnikit-research\account-pool-A2-ledger.json --min-stars 1000` 之原始輸出如下：

```text
總共 326 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 2 組沒有新的（要 3 組）：還不能停
已經 12 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續
第 1 組「Antigravity 多帳號 切換」：18 個名字，新的 18 個；查不到：github-keyword；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：router-for-me/cliproxyapi, lbjlaq/antigravity-manager, jlcodes99/cockpit-tools, justlovemaki/aiclient2api, yuaotian/antigravity-proxy, chrisflicker/tsa-claude-usage, fikrilal/agy-auth, anglee0323/agy-switch, praveensenpai/agym, antigravity-cli-multi-accounts, at2008/antigravity-cockpit, monchilin/antigravity-agent, AgentsRoom, erennyuksell/ag-multi-account-switchboard, wangejay/c-switcher, NoeFabris/opencode-antigravity-auth, Wei-Shaw/sub2api, yixuanwangluo/gcli2api-fix-master
  ★1000 以上的新名字：router-for-me/cliproxyapi, lbjlaq/antigravity-manager, jlcodes99/cockpit-tools, justlovemaki/aiclient2api, yuaotian/antigravity-proxy, NoeFabris/opencode-antigravity-auth, Wei-Shaw/sub2api
第 2 組「LLM quota failover」：42 個名字，新的 42 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt
  新：hudiohizari/antigravity-switcher, gzy940086/cc-keyring-companion, azrinaldi/gemini-stealth-bridge, seaavey/srouter, kame696/kame-api-rotation-for-agent-zero, llmrix/llmrix-router, arnav8452/freeloader, colombefioren/cokey, 3langel0/balanceria, bojieli/agentswap, cocoonstack/gateway, lightconsen/kiwano, kame696/kame-api-rotation-for-hermes, vinaygiri/freeway, jonsonwu0823-coding/quotaforge, s-berdia/opencode_router, edison7009/EchoBird, ajoly21/llm-failover-proxy, sarrius/pi-multi-account, 2solarmax/maxpool, kbastwad19/claude-pool, kunchenguid/quota-axi, m1khal3v/dsh-llm-key-rotation, cs-qyzhang/dsh-llm-quota, io.github.Evozim/api-quota-balancer-mcp, io.github.backstagebarcelona66-maker/quotatick, limitcool/quota-mcp, UnifyRoute, GoatCode, BerriAI/litellm …
  ★1000 以上的新名字：edison7009/EchoBird, BerriAI/litellm, cheaper-inference/OmniRoute
第 3 組「OAuth token pool proxy」：56 個名字，新的 54 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related
  新：ai.getvda/oauth-multi-llm-orchestrator, ai.getvda/encrypted-oauth-llm-agent, ClawPool, danielkillenberger/perpetua, jamila-khan/codex-proxy, north-web-dev/poolctl, hamdisoudani/nous-pool, victorminemu/cc-router, steventong/codex-openai-proxy, Ken-Chy129/llm-proxy, ProxyPoolHub, pysugar/oauth-llm-nexus, llm8, badrisnarayanan/antigravity-claude-proxy, zhongruichen/aistudio-gemini-proxy, su-kaka/gcli2api, thuongtin/antigravity-manager, benjaminaaron196/cliproxyapi, ben-vargas/ai-cli-proxy-api, ve-ria/cliproxyapiplus, router-for-me/cli-proxy-api-management-center, willxup/cpa-usage-keeper, seakee/cpa-manager-plus, wiziscool/oh-my-cpa, automazeio/vibeproxy, kaitranntt/ccs, nguyenphutrong/quotio, finesssee/proxypilot, ferretgeek/cpa-x, kitephp/cliproxyapi_tray …
  ★1000 以上的新名字：badrisnarayanan/antigravity-claude-proxy, router-for-me/cli-proxy-api-management-center, willxup/cpa-usage-keeper, seakee/cpa-manager-plus, automazeio/vibeproxy, kaitranntt/ccs, nguyenphutrong/quotio, qixing-jk/all-api-hub, decolua/9router, chriscompton/omniroute, miuuyy/codex-chatgpt-web, alishahryar1/free-claude-code, chenyme/grok2api, jlcodes99/vscode-antigravity-cockpit, steipete/codexbar
第 4 組「claude code multi account switcher」：55 個名字，新的 52 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：tonf1917/claude-desktop-multiple-windows-different-api, shx2005/codex-account-switcher, xdtrees/dsh-xdpool, karpeleslab/teamclaude, razzant/claudexor, jackson-cmd/claude-multi-desktop, edison-land/paragravity, uwuclxdy/clauth, ducksss/codex-profiles, liuzhao1225/codex-account-switcher, aaditya-v-more/claude-graft, kzcfg/ailsa-subswitch, vallierdev/codex-switcher, snlperstripes/claude-account-switcher, hamzarehmandeveloper/claude-account, errhythm/ccswap, changexbc/workbuddy-switch, leuconoe/claudecodemultiaccounts, blackhole1/aswap, rchaz/claude-nonstop, vyshnavsdeepak/ccswitch, ictechgy/multi-account-tool, andrewtjin/claude-control, abiroot/clyde, tusharkanjariya/claude-code-multi-account, bkankim/cct, newbdez33/ccsw, gordonpow/switchpilot, osrcmap/multiacclaude, ukogan/claude-account-switcher …
  ★1000 以上的新名字：changexbc/workbuddy-switch, realiti4/claude-swap
第 5 組「codex multi account load balancer」：30 個名字，新的 23 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：tbphp/gpt-load, snailyp/gemini-balance, soju06/codex-lb, nhatbien/copilot-helper, braitoli/team-ai-quota, ibnabeeali/codex-multiplexer, anowell/subbier, ff-rohman/codex_proxy_server, samuellhuber/ai-sub-usage-tracker, shirazelec/se-aiproxy, vybestack/llxprt-code, owjs3901/opencode-auth-load-balancer, ai.getvda/traced-multi-llm-proxy, gngeorgiev/openai-codex-lb, lilong7676/codex-pool, supabitapp/codex-balancer, dollannn/codex-lb-rs, CodexUse, aafqaq/codex-lb-enhanced, moonsunkim/codexmulti, christiandoxa/prodex, Cloud370/codex-account-switcher, Lampese/codex-switcher
  ★1000 以上的新名字：tbphp/gpt-load, snailyp/gemini-balance, soju06/codex-lb
第 6 組「api key pool cooldown rotation」：38 個名字，新的 37 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：mirrowel/llm-api-key-proxy, snake-aabb-wtf/deepseek-web2api-free, weiruchenai1/api-key-tester, aipmandy/freetoken, aigne-io/aigne-hub, demonbane18/relmio, yzbrh/keyrealm, dabao-yi/model-flux, dwgx/cursorapi, leeguooooo/cloudflare-llm-gateway, yizutt/dsh-modelscope-pool, mree9527/new-api-pool, bilibiliuid1480494301/relay-hub, tianya-dao/dsh-opencode-go-pool, jackzigen/keypool-guard, phiiggfdg/open-cli-codex, yeahx/dsh-opencode-pool, piyush-tyagi-13/llm-keypool, xiaozhe7772222/dsh-api-key-pool, ax1zz/nvidia-hub, ssdiwu/pi-key-pool, marktantongco/glm-official-pool, phucpm89/llmkeypool, goodandready/dsh-subscriptions, opencode-v2-gemini-rotator, vitorvilaca3011/saros-proxy, dushaobindoudou/dsh-freeroute, lnilluv/pi-opencode-go-rotation, halfemptydrum/key-carousel, @lacspace/keypool …
第 7 組「subscription quota monitor menu bar」：48 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：slkiser/opencode-quota, n2ns/antigravity-panel, aqua5230/usage, licoy/quosparr, lumidarin/agy-capsule, nanvon/cc-bar, levi-qiao/herdr-agent-usage, yuhuan-dev/antigravity-usage-monitor, wycocoyu/agy-context-dashboard, defy-an94/codex94, duoasa/quotaview, wassim-azi/agy-powerline, jiayang-buaa/codex-desktop-usage-monitor-windows, juk1-gh/codexscope, majiayu000/quotabar, enzoo404/gravitybox, yagcioglutoprak/aiquotabar, chattymin/poketokenbar, vincent-liuc/quotabar, jorben/quotax, jamesbrink/burnrate, supia7/quota-bar, davewell3010/ai-quota-monitor-macos, a-nomad-studio/zenmux-monitor, yturkkan/suyoi, letrahoo/sub-bar, aromaw/planwatch, how1215/codex-monitor, hviper/codex-quota, sergioperezcheco/codexquota …
  ★1000 以上的新名字：slkiser/opencode-quota, tddworks/ClaudeBar
第 8 組「AI 訂閱 號池 中轉」：8 個名字，新的 5 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Wei-Shaw/claude-relay-service, poxiao33/toSub2, QuantumNous/new-api, basketikun/chatgpt2api, ding113/claude-code-hub
  ★1000 以上的新名字：Wei-Shaw/claude-relay-service, QuantumNous/new-api, basketikun/chatgpt2api, ding113/claude-code-hub
第 9 組「multi account credential isolation profile」：13 個名字，新的 8 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：gusitllc/credential-isolation-autonomous-ai-coders, tdnhathuy/agy-mult-profiles, ildourol/multigravity-cli, codex-profile-manager, tonamson/switch-acc-ai, aisw, ccm, Gemini-CLI-Auth-Manager
第 10 組「retrieveUserQuota fetchAvailableModels quota」：23 個名字，新的 15 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：guyinwonder168/opencode-glm-quota, openclaw/openclaw, zer020/pi-fireworks-quota, ravshansbox/pi-quota, yangwudong/pi-quota, easerlee/codex-quota-chip, tuzelko/opencode-quota, xinghe-1018/dsh-token-plan-quota, vibe_coding_tracker, PowerUserZ/OpenTokenUsage, diegosouzapw/omniroute, can1357/oh-my-pi, usage-monitor-cli, deviffyy/openquota, nclamvn/bom-cham
  ★1000 以上的新名字：openclaw/openclaw, diegosouzapw/omniroute, can1357/oh-my-pi
第 11 組「sticky session rate limit cooldown proxy」：15 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：kenyony/openai-forward, leeguooooo/claude-code-usage-bar, cheapestinference/claude-auto-retry, shanggqm/codexu, jens-duttke/usage-monitor-for-claude, jackdrogon/opencode-context-cache, azumag/opencode-rate-limit-fallback, subscription_proxy_pool, nexon33/openrouter-proxy-server, azrtydxb/Fastllm-proxy
第 12 組「ai subscription quota alert notification」：21 個名字，新的 17 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：lnwu/opencode-statusline-plugins, ktrouter, AIQuotaMonitor, davedavedavenm/ai-usage-dashboard, MstyNexus, Magpie, onllm-dev/onwatch, ykertytsky/pi-usage-alerts, rock3r/headroom, QuotaMate, usageowl/usageowl, CodeNotch, iebb/when-reset, edilsonvilarinho/usage-monitor, mohitkale/ai-tools-usage-tracker, nikolmedo/AIOversight, Karylcode/token-usage-deck
```

### 3. 停止組數、連續數與停法說明
- **停止點**：於 **第 12 組** 依 `brief-common.md` 規則「**達 12 組上限停止回報現況**」停下，不超過預算繼續搜尋。
- **兩種連續數**：
  - 全體不重複名字（共 326 個）：連續 **0 組**沒有新名字（因小工具與個人 CLI/選單列腳本呈長尾分布）。
  - ★1,000 以上 GitHub repo：連續 **2 組**沒有新名字（**第 11 組**與**第 12 組**皆 0 個新 ★1,000+，第 6 組與第 9 組亦為 0 個；第 10 組因反查 `retrieveUserQuota` 帶出既有綜合代理 `openclaw/openclaw`、`can1357/oh-my-pi`，以及實為 `cheaper-inference/OmniRoute` 舊 owner 跳轉的 `diegosouzapw/omniroute`，導致連續數歸零，距「長尾未飽和」的連續 3 組只差 1 組）。
- **覆蓋聲明**：本報告已完整涵蓋 39+ 個主流千星級帳號池閘道、隔離切換器、配額選單列與告警工具；★1,000 以下小型外掛與無 GitHub 星數的商業服務不保證找齊，待與另一位研究者（A1）的結果合併補強。

### 4. 查不到的管道與限制
- **第 1 組初始限速與中文檢索限制**：首次執行第 1 組時因並行觸發 GitHub Search API 每分鐘 30 次限速（HTTP 403）與 Exa 免費層限速，等待重置後重跑第 1 組已補齊 `github-topic`（20 筆）、`awesome`（5 筆）與 `exa`（10 筆）；惟中文詞組於 `github-keyword` 仍為 0 筆（帳本保留首次 403 錯誤紀錄故 `status` 標示 `查不到：github-keyword`），已由 `web-zh` 與 `exa` 完整覆蓋。
- **中文組（第 8 組）跨管道限制**：`"AI 訂閱 號池 中轉"` 移去通用字後無 3 字元以上英文詞，`skills.sh`、`mcp-registry`、`github-topic` 依腳本規則回 0 筆，改以 `web-zh` 與 `exa` 補齊中文開源生態。
- **Product Hunt API**：需開發者 token，依規範於第 2 組改以網頁搜尋 `site:producthunt.com` 補齊（收錄 `Multi-Claude`、`Moxie`、`Claudy`）。
- **已移除／404 原倉**：種子專案 `su-kaka/gcli2api` 經 2026-11-23 `gh api` 實測回傳 **HTTP 404 Not Found**，已改以社群鏡像 `yixuanwangluo/gcli2api-fix-master` 核對功能與授權。
- **Gemini CLI 配額文件頁**：`https://geminicli.com/docs/quota-and-pricing/` 直接 HTTP 抓取僅得 128 字元 SPA 殼層，改以 `CodexBar:docs/gemini.md` 一手原始碼與 `antigravity.google` 官方原文交叉佐證。

### 5. `sweep.py verify` 實測星數與授權（查證日期：2026-11-23 `gh api`）

| Repo | Stars | License | Archived | Last Pushed |
| :--- | :---: | :--- | :---: | :--- |
| `openclaw/openclaw` | 395,067 | MIT | false | 2026-11-23 |
| `cheaper-inference/OmniRoute` | 89,647 | MIT | false | 2026-11-23 |
| `BerriAI/litellm` | 63,724 | NOASSERTION | false | 2026-11-23 |
| `router-for-me/CLIProxyAPI` | 59,260 | MIT | false | 2026-11-23 |
| `QuantumNous/new-api` | 52,357 | AGPL-3.0 | false | 2026-11-22 |
| `Wei-Shaw/sub2api` | 46,465 | LGPL-3.0 | false | 2026-11-23 |
| `can1357/oh-my-pi` | 39,679 | MIT | false | 2026-11-23 |
| `lbjlaq/Antigravity-Manager` | 33,691 | NOASSERTION | false | 2026-11-22 |
| `decolua/9router` | 32,752 | MIT | false | 2026-11-23 |
| `steipete/CodexBar` | 23,287 | MIT | false | 2026-11-21 |
| `jlcodes99/cockpit-tools` | 20,293 | 無 | false | 2026-11-22 |
| `Wei-Shaw/claude-relay-service` | 12,827 | MIT | false | 2026-11-22 |
| `NoeFabris/opencode-antigravity-auth` | 11,087 | MIT | false | 2026-11-13 |
| `justlovemaki/AIClient2API` | 8,996 | GPL-3.0 | false | 2026-11-18 |
| `tbphp/gpt-load` | 7,246 | MIT | false | 2026-11-22 |
| `basketikun/chatgpt2api` | 6,980 | MIT | false | 2026-11-22 |
| `snailyp/gemini-balance` | 5,772 | NOASSERTION | false | 2025-09-30 |
| `yuaotian/antigravity-proxy` | 5,337 | NOASSERTION | false | 2026-11-21 |
| `qixing-jk/all-api-hub` | 5,079 | AGPL-3.0 | false | 2026-11-22 |
| `nguyenphutrong/quotio` | 4,920 | MIT | false | 2026-11-18 |
| `realiti4/claude-swap` | 4,909 | MIT | false | 2026-11-21 |
| `jlcodes99/vscode-antigravity-cockpit` | 4,857 | MIT | false | 2026-11-12 |
| `router-for-me/Cli-Proxy-API-Management-Center` | 4,830 | MIT | false | 2026-11-22 |
| `seakee/CPA-Manager-Plus` | 4,100 | MIT | false | 2026-11-22 |
| `badrisnarayanan/antigravity-claude-proxy` | 4,087 | MIT | false | 2026-11-16 |
| `edison7009/EchoBird` | 3,580 | MIT | false | 2026-11-23 |
| `Soju06/codex-lb` | 3,454 | MIT | false | 2026-11-22 |
| `automazeio/vibeproxy` | 3,414 | MIT | false | 2026-11-23 |
| `ding113/claude-code-hub` | 3,401 | MIT | false | 2026-11-18 |
| `kaitranntt/ccs` | 2,907 | MIT | false | 2026-11-16 |
| `changexbc/workbuddy-switch` | 1,950 | MIT | false | 2026-10-12 |
| `tddworks/ClaudeBar` | 1,590 | Apache-2.0 | false | 2026-11-20 |
| `Willxup/cpa-usage-keeper` | 1,324 | MIT | false | 2026-11-23 |
| `slkiser/opencode-quota` | 1,165 | MIT | false | 2026-11-19 |
| `shx2005/codex-account-switcher` | 977 | MIT | false | 2026-10-20 |
| `onllm-dev/onWatch` | 773 | GPL-3.0 | false | 2026-11-16 |
| `sylearn/AIUsage` | 748 | Apache-2.0 | false | 2026-11-14 |
| `wangdabaoqq/LinJun` | 625 | MIT | false | 2026-08-19 |
| `ndycode/codex-multi-auth` | 569 | MIT | false | 2026-11-18 |
| `Mirrowel/LLM-API-Key-Proxy` | 566 | NOASSERTION | false | 2026-11-02 |
| `KarpelesLab/teamclaude` | 527 | MIT | false | 2026-11-21 |
| `razzant/claudexor` | 526 | MIT | false | 2026-11-23 |
| `uwuclxdy/clauth` | 344 | MIT | false | 2026-11-23 |
| `Finesssee/ProxyPilot` | 262 | MIT | false | 2026-06-24 |
| `yixuanwangluo/gcli2api-fix-master` | 166 | NOASSERTION | false | 2025-11-28 |
| `gesta-run/subpool` | 117 | Apache-2.0 | false | 2026-11-21 |
| `buddingnewinsights/proxypal` | 89 | MIT | false | 2026-07-21 |
| `burakgon/ai-usage-menubar` | 58 | MIT | false | 2026-11-07 |
| `iebb/when-reset` | 5 | 無 | false | 2026-09-24 |
| `usageowl/usageowl` | 1 | MIT | false | 2026-08-08 |
| `davedavedavenm/ai-usage-dashboard` | 0 | MIT | false | 2026-11-22 |
| `su-kaka/gcli2api` | — | HTTP 404 Not Found | — | — |

### 6. 無一手證據而標註「待驗證」之清單
- Google Antigravity 論壇傳稱「個人帳號 TOS 封禁僅有一次性申訴機會」及「同機多付費帳號同時並發會觸發自動封禁」：均出自社群論壇非正式條款，標【待驗證】。
- 二手部落格稱 Anthropic Consumer Terms 內含「禁止建立多帳號以規避限額」條文：2026-11-23 核對 `anthropic.com/legal/consumer-terms` 原文未見該字眼，標【待驗證】（一手條款係禁止非 API key 自動化與帳號共用）。
- 媒體轉述 Anthropic 2026-04-04 改以 Extra Usage 計費取代全面封鎖第三方 harness：未抓到官方部落格原頁，標【待驗證】。
- OpenAI 個人單機使用 `codex-lb` 之實際封號率：無公開一手統計，標【待驗證】。
- `OmniRoute`、`Sub2API`、`GPT-Load` 之原生手機推播告警與 `Claude Relay Service` 詳細冷卻參數：未逐一深讀後端實作檔，標【待驗證】。
