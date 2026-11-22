# 個人分派設定：ryan

分派規則（任務類型、級別、模型類別、思考程度、升級）照共用層 `data/rules/dispatch.md`；這份只寫 ryan 有哪些供應商實例，以及每個模型類別用哪個實例。`instances` 的 key 是 T3 的供應商實例 id：在 T3 裡是 `delegate_task` 的 `target.providerInstanceId`，不在 T3 裡（Claude Code、Codex、Antigravity）就是 `t3 thread start --provider` 的值（例如 `t3 thread start . "<任務>" --provider antigravity_kai --model gemini-3.8-flash --json --wait`，在 PowerShell 跑；Git Bash 要打 `t3.cmd`；見政策的 `t3_cli` 管道；這個例子的 Flash 沒帶思考程度，依 2026-11-18 定案 Gemini 一律 high 以上，CLI 要帶程度就寫進代號，例如 `gemini-3.8-flash-high`，但 Flash 帶程度的代號未實測，要確定程度改用 `t3_thread_launch` 加 `thinking_level: high`）；`classes` 裡同一個類別列了好幾個實例時，由上往下用。

```yaml
# 2026-11-21 ryan 定案：派出去的子任務要開在 T3 看得到的對話（要能確認 prompt 符不符合預期、看過程），
# 無頭派送（agy_cli）只在 ryan 同意或 T3 沒在跑時用。這是 ryan 的個人偏好，共用層的說明在 dispatch-policy.md 的 visibility。
visibility: visible

instances:
  claudeAgent:            {driver: claudeAgent, account: Ryan,  classes: [claude-opus, claude-sonnet]}
  claudeAgent_2:          {driver: claudeAgent, account: retis, classes: [claude-opus, claude-sonnet]}
  claudeAgent_claude_kai: {driver: claudeAgent, account: Kai,   classes: [claude-opus, claude-sonnet]}
  antigravity_ryan:
    driver: antigravity
    account: ryan
    classes: [gemini-pro, antigravity-opus]
    note: Gemini 4 Hydrogen 的 thinking_level 最高 xhigh；這裡的 Claude 最高只到 high
  # 以下 5 個是 2026-11-22 新買的 Gemini Pro（1A：只給 ryan 自己開的對話用，classes 留空，agent 不自動派、不輪換）。
  # 2026-11-22 orchestrator_capabilities 實測：1 到 4 都列出 Neon、Argon、Hydrogen、Orchestrator (Neon／Argon)、3.8 Flash、Claude Opus／Sonnet 5.5；5 還沒登入（模型清單是空的）。
  antigravity_1: {driver: antigravity, account: 新 Pro 1, classes: []}
  antigravity_2: {driver: antigravity, account: 新 Pro 2, classes: []}
  antigravity_3: {driver: antigravity, account: 新 Pro 3, classes: []}
  antigravity_4: {driver: antigravity, account: 新 Pro 4, classes: []}
  antigravity_5: {driver: antigravity, account: 新 Pro 5, classes: [], note: 2026-11-22 ryan 忘記密碼、還沒登入}
  # antigravity_ava、antigravity_kai（印度 Jio 方案，只剩 3.8 Flash）：11-22 退出派工，同日 orchestrator_capabilities 已查不到這兩個實例，從清單拿掉。

# 2026-11-22 ryan 定案（帳號池 1A＋2B，細節 data/evals/2026-11-22-gemini-pro-pool.md）：
# - ryan 新買 5 個 Gemini Pro（正式付費、能用 Neon），只給 ryan 自己開的對話用，一次一個帳號，額度用完 ryan 在 T3 手動換；
#   不列進上面的 classes，agent 不自動派、不自動輪換（Google 官方 FAQ：個人方案不支援自動輪換帳號）。接進 T3 後在這裡登記實例 id，classes 留空。
# - Claude 自動派給 Gemini 維持 antigravity_ryan（2B）：Google 官方 FAQ 寫別家 coding agent 驅動 agy 在個人方案不支援、可能停權，ryan 知情後選擇照舊；
#   固定這一個帳號、不輪換、一次一條（staff 2026-10-07 建議低並行）。
# 原生子代理（Agent 工具）用的是目前這段對話的帳號，不用列。
# 要用 delegate_task 派給 Claude 時，先用目前這段對話的實例（inherited）；那個帳號額度用完，再照上面 instances 的順序（claudeAgent、claudeAgent_2、claudeAgent_claude_kai）換下一個。使用者沒有偏好（2026-11-18 定案）。
# 2026-11-19 定案：派出去的 Claude Opus 子任務（claude-opus、antigravity-opus，不論哪個管道）effort 預設 medium，只有 ryan 明確指定才用 high 以上（細則在 data/profiles/ryan/AGENTS.md）；主線本身維持使用者指定的設定。Gemini 仍一律 high 以上。
# 2026-11-19 更正（Codex），2026-11-21 再更正：ryan 取消了 Codex 訂閱的續訂，訂閱在 2026-11-21 的上上週到期（約 11-02 到 11-08 那週，哪天 ryan 也不確定）。到期後官方 Codex 仍跑得動：11-19 R1 跑完 8 次才撞 usage limit（寫 12-11 重置），推測是免費方案的額度（待驗證）。不要寫成「沒有額度」，也不要假設有付費方案的額度；長期要用的審查流程不要依賴官方 Codex，改走本機 codex-chatgpt-web 橋接（127.0.0.1:17841）或改派其他模型唯讀審查。
# 2026-11-19 定案（15 分鐘逾時）：T3 server 把 Antigravity 的 promptInactivityTimeout 寫死成 "15 minutes"（Claude 與 Codex 無此限制且無法改設定）。長時間跑的主線優先用 Claude 實例；Antigravity 主線出現逾時橫幅時，先檢查工作是否已完成，未完成再送「繼續」。
# 2026-11-20 更新（agy 多帳號已修好）：T3 0.1.11-nightly.20261120.4979 合入上游 PR 39485（原 issue #37587），三個 Antigravity 實例各自登入（實測 Ryan 23 個模型、kai 6 個、ava 6 個）。Ryan 的實例 id 改為 antigravity_ryan（原 antigravity），kai、ava 沿用原 id。
```

# 2026-11-19 定案（Gemini 3.8 Flash 分派限制）：只要目前對話是由 Gemini 3.8 Flash（如 antigravity_ava、antigravity_kai）所運行，所分配/派發出去的子對話或子任務，一律只能派給 kai 或 ava 的 Gemini 3.8 Flash（providerInstanceId: antigravity_kai 或 antigravity_ava），思考程度固定 high。嚴禁從 Gemini 3.8 Flash 主線跨派給 Claude 或其他模型。
