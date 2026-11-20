# 個人分派設定：ryan

分派規則（任務類型、級別、模型類別、思考程度、升級）照共用層 `data/rules/dispatch.md`；這份只寫 ryan 有哪些供應商實例，以及每個模型類別用哪個實例。`instances` 的 key 是 T3 的供應商實例 id：在 T3 裡是 `delegate_task` 的 `target.providerInstanceId`，不在 T3 裡（Claude Code、Codex、Antigravity）就是 `t3 thread start --provider` 的值（例如 `t3 thread start . "<任務>" --provider antigravity_kai --model gemini-3.8-flash --json --wait`，在 PowerShell 跑；Git Bash 要打 `t3.cmd`；見政策的 `t3_cli` 管道；這個例子的 Flash 沒帶思考程度，依 2026-11-18 定案 Gemini 一律 high 以上，CLI 要帶程度就寫進代號，例如 `gemini-3.8-flash-high`，但 Flash 帶程度的代號未實測，要確定程度改用 `t3_thread_launch` 加 `thinking_level: high`）；`classes` 裡同一個類別列了好幾個實例時，由上往下用。

```yaml
instances:
  claudeAgent:            {driver: claudeAgent, account: Ryan,  classes: [claude-opus, claude-sonnet]}
  claudeAgent_2:          {driver: claudeAgent, account: retis, classes: [claude-opus, claude-sonnet]}
  claudeAgent_claude_kai: {driver: claudeAgent, account: Kai,   classes: [claude-opus, claude-sonnet]}
  antigravity:
    driver: antigravity
    account: ryan
    classes: [gemini-pro, antigravity-opus]
    note: Gemini 4 Hydrogen 的 thinking_level 最高 xhigh；這裡的 Claude 最高只到 high
  antigravity_ava:
    driver: antigravity
    account: ava
    classes: [gemini-flash]
    note: 印度 Jio 方案的 Gemini Pro，只有 Opus 4.6 與 Gemini 3.8 Flash（沒有 Opus 5.5，也沒有 Gemini 4 系列）
    needs_user: antigravity 的 Gemini 額度用完時，請 ryan 開啟 ava、kai 帳號再用
  antigravity_kai:
    driver: antigravity
    account: kai
    classes: [gemini-flash]
    note: 同 antigravity_ava（印度 Jio 方案的 Gemini Pro，只有 Opus 4.6 與 Gemini 3.8 Flash）
    needs_user: 同 antigravity_ava

# 原生子代理（Agent 工具）用的是目前這段對話的帳號，不用列。
# 要用 delegate_task 派給 Claude 時，先用目前這段對話的實例（inherited）；那個帳號額度用完，再照上面 instances 的順序（claudeAgent、claudeAgent_2、claudeAgent_claude_kai）換下一個。使用者沒有偏好（2026-11-18 定案）。
# 2026-11-19 定案：派出去的 Claude Opus 子任務（claude-opus、antigravity-opus，不論哪個管道）effort 預設 medium，只有 ryan 明確指定才用 high 以上（細則在 data/profiles/ryan/AGENTS.md）；主線本身維持使用者指定的設定。Gemini 仍一律 high 以上。
# 2026-11-19 更正（Codex）：ryan 已取消 Codex 訂閱，沒有官方 Codex 額度，以後不要假設有官方 Codex 或等官方額度恢復；需要跑 Codex 類審查工具時，改走本機 codex-chatgpt-web 橋接（127.0.0.1:17841）或改派其他模型唯讀審查。
# 2026-11-19 定案（15 分鐘逾時）：T3 server 把 Antigravity 的 promptInactivityTimeout 寫死成 "15 minutes"（Claude 與 Codex 無此限制且無法改設定）。長時間跑的主線優先用 Claude 實例；Antigravity 主線出現逾時橫幅時，先檢查工作是否已完成，未完成再送「繼續」。
# 2026-11-20 暫時限制（agy 多帳號）：T3 0.1.11 nightly 搭 agy 1.5.13 時，Google 登入存在 Windows 認證管理員，全機只有一個項目（gemini:antigravity），三個 Antigravity 實例都會變成最後登入的帳號（上游 https://github.com/pingdotgg/t3code/issues/39507）。ryan 決定只留 antigravity_kai，antigravity、antigravity_ava 停用：
#   - Antigravity 目前只能同時用一個帳號（kai）。
#   - gemini-pro 類別（Hydrogen、Neon）暫時沒有可用實例：改用 antigravity_kai 的 Gemini 3.8 Flash（thinking high），或改派 Claude。antigravity-opus 同樣沒有實例。
#   - 等 issue 39507 修好再恢復三帳號，恢復前不要派給 antigravity、antigravity_ava。
```

# 2026-11-19 定案（Gemini 3.8 Flash 分派限制）：只要目前對話是由 Gemini 3.8 Flash（如 antigravity_ava、antigravity_kai）所運行，所分配/派發出去的子對話或子任務，一律只能派給 kai 或 ava 的 Gemini 3.8 Flash（providerInstanceId: antigravity_kai 或 antigravity_ava），思考程度固定 high。嚴禁從 Gemini 3.8 Flash 主線跨派給 Claude 或其他模型。
