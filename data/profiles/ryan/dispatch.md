# 個人分派設定：ryan

分派規則（任務類型、級別、模型類別、思考程度、升級）照共用層 `data/rules/dispatch.md`；這份只寫 ryan 有哪些供應商實例，以及每個模型類別用哪個實例。`instances` 的 key 是 T3 的供應商實例 id：在 T3 裡是 `delegate_task` 的 `target.providerInstanceId`，不在 T3 裡（Claude Code、Codex、Antigravity）就是 `t3 thread start --provider` 的值（例如 `t3 thread start . "<任務>" --provider antigravity_kai --model gemini-3.8-flash --json --wait`，在 PowerShell 跑；Git Bash 要打 `t3.cmd`；見政策的 `t3_cli` 管道；這個例子的 Flash 沒帶思考程度，依 2026-11-18 定案 Gemini 一律 high 以上，CLI 要帶程度就寫進代號，例如 `gemini-3.8-flash-high`，但 Flash 帶程度的代號未實測，要確定程度改用 `t3_thread_launch` 加 `thinking_level: high`）；`classes` 裡同一個類別列了好幾個實例時，由上往下用。

```yaml
# 2026-11-21 ryan 定案：派出去的子任務要開在 T3 看得到的對話（要能確認 prompt 符不符合預期、看過程），
# 無頭派送（agy_cli）只在 ryan 同意或 T3 沒在跑時用。這是 ryan 的個人偏好，共用層的說明在 dispatch-policy.md 的 visibility。
visibility: visible

# 2026-11-23 ryan 暫定：每個模型開到它能開的最高思考程度（Neon、Hydrogen、Orchestrator 用 xhigh；Argon、3.8 Flash 最高 high）。
# 理由：ryan 帳號多、Gemini 的 token 不用省。這只是 ryan 的偏好；其他使用者要能自己選或照分析建議（docs/proposals/2026-11-23-account-pool.md 第七節）。
# dispatch.py 還沒讀這個欄位（待帳號池機制實作）；派工時由主控照這條寫明程度。
thinking_preference: max_available

# 2026-11-23 ryan 定案（D2）：額度用完先照接手順序（antigravity_ryan Gemini → 同帳號 Argon 桶 → 同帳號 Claude & GPT 桶的 Opus／Sonnet →
# Claude 三個實例依額度挑 → 停下來列各帳號剩多少、幾點重置、建議換哪個）。派給 Gemini 是為了跨家審查 Claude 的產出時，跳過換成 Claude 的兩步。
# 細節 docs/proposals/2026-11-23-account-pool.md 第四節。dispatch.py 還沒讀這兩個欄位（第一、二階段實作）。
on_exhausted: prompt_manual_switch

# 2026-11-23 ryan 定案（D7）：3.8 Flash 有後繼 Hydrogen、GPT-OSS 120B 沒有角色使用，退出分工；OmniKit 的模型淘汰過濾預設開，這裡是額外排除。
exclude_models: [gemini-3.8-flash, gpt-oss-120b]
# Argon 不在現行政策的角色裡，單價表（Copilot）又寫了後繼 gemini-4-carbon，自動過濾會把它濾掉；
# 提案第七節定的是「進試用，用煙霧題組決定擺哪」，所以先留著。試用結束不用就拿掉這行。
include_models: [gemini-4-argon]

instances:
  # 2026-11-23 ryan 確認（D3）：3 個 Claude 帳號都在 ryan 本人名下；開新子對話時依額度在工作包邊界自動挑，同一條對話不中途換（tos_ack 2026-11-23）。
  claudeAgent:            {driver: claudeAgent, account: Ryan,  owner: self, tos_ack: "2026-11-23 D3：本人名下，工作包邊界依額度挑", classes: [claude-opus, claude-sonnet]}
  claudeAgent_2:          {driver: claudeAgent, account: retis, owner: self, tos_ack: "2026-11-23 D3：本人名下，工作包邊界依額度挑", classes: [claude-opus, claude-sonnet]}
  claudeAgent_claude_kai: {driver: claudeAgent, account: Kai,   owner: self, tos_ack: "2026-11-23 D3：本人名下，工作包邊界依額度挑", classes: [claude-opus, claude-sonnet]}
  antigravity_ryan:
    driver: antigravity
    account: ryan
    classes: [gemini-pro, antigravity-opus]
    owner: self
    tos_ack: "2026-11-22 2B：知道 Google FAQ 寫消費方案不支援別家 agent 驅動 agy，選擇照舊；固定這一個、不輪換、一次一條"
    note: Gemini 4 Hydrogen 的 thinking_level 最高 xhigh；這裡的 Claude 最高只到 high
  # 以下 5 個是 2026-11-22 新買的 Gemini Pro（1A：只給 ryan 自己開的對話用，classes 留空，agent 不自動派、不輪換；分工重新討論中，定案前照舊）。
  # 2026-11-23 ryan 全部刪掉重登，實例 id 改成下面這些（舊的 antigravity_1 到 5 作廢，資料夾已刪）。
  # 2026-11-23 實測：6 個 Antigravity 實例 × Neon、Argon、Hydrogen、Orchestrator (Neon／Argon)、3.8 Flash 全部能用，都讀得到 OmniKit 規則。
  antigravity_kanny163: {driver: antigravity, account: kanny163, classes: []}
  antigravity_km0529:   {driver: antigravity, account: km0529,   classes: []}
  antigravity_stk608:   {driver: antigravity, account: stk608,   classes: []}
  antigravity_stk824:   {driver: antigravity, account: stk824,   classes: []}
  antigravity_itri:     {driver: antigravity, account: itri,     classes: []}
  # antigravity_ava、antigravity_kai（印度 Jio 方案，只剩 3.8 Flash）：11-22 退出派工並從 T3 移除；資料夾 2026-11-23 已刪。

# 2026-11-22 ryan 定案（帳號池 1A＋2B，細節 data/evals/2026-11-22-gemini-pro-pool.md）：
# - ryan 新買 5 個 Gemini Pro（正式付費、能用 Neon），只給 ryan 自己開的對話用，一次一個帳號，額度用完 ryan 在 T3 手動換；
#   不列進上面的 classes，agent 不自動派、不自動輪換（Google 官方 FAQ：個人方案不支援自動輪換帳號）。接進 T3 後在這裡登記實例 id，classes 留空。
# - Claude 自動派給 Gemini 維持 antigravity_ryan（2B）：Google 官方 FAQ 寫別家 coding agent 驅動 agy 在個人方案不支援、可能停權，ryan 知情後選擇照舊；
#   固定這一個帳號、不輪換、一次一條（staff 2026-10-07 建議低並行）。
#   2026-11-23 ryan 再確認（D1）：不改走 Vertex（之前用過抵免額，流程繁雜、設定困難），維持 2B；用完照上面 on_exhausted 的接手順序。
# 原生子代理（Agent 工具）用的是目前這段對話的帳號，不用列。
# 要用 delegate_task 派給 Claude 時，先用目前這段對話的實例（inherited）；那個帳號額度用完，再照上面 instances 的順序（claudeAgent、claudeAgent_2、claudeAgent_claude_kai）換下一個。使用者沒有偏好（2026-11-18 定案）。
# 2026-11-19 定案：派出去的 Claude Opus 子任務（claude-opus、antigravity-opus，不論哪個管道）effort 預設 medium，只有 ryan 明確指定才用 high 以上（細則在 data/profiles/ryan/AGENTS.md）；主線本身維持使用者指定的設定。Gemini 仍一律 high 以上。
# 2026-11-19 更正（Codex），2026-11-21 再更正：ryan 取消了 Codex 訂閱的續訂，訂閱在 2026-11-21 的上上週到期（約 11-02 到 11-08 那週，哪天 ryan 也不確定）。到期後官方 Codex 仍跑得動：11-19 R1 跑完 8 次才撞 usage limit（寫 12-11 重置），推測是免費方案的額度（待驗證）。不要寫成「沒有額度」，也不要假設有付費方案的額度；長期要用的審查流程不要依賴官方 Codex，改走本機 codex-chatgpt-web 橋接（127.0.0.1:17841）或改派其他模型唯讀審查。
# 2026-11-19 定案（15 分鐘逾時）：T3 server 把 Antigravity 的 promptInactivityTimeout 寫死成 "15 minutes"（Claude 與 Codex 無此限制且無法改設定）。長時間跑的主線優先用 Claude 實例；Antigravity 主線出現逾時橫幅時，先檢查工作是否已完成，未完成再送「繼續」。
# 2026-11-20 更新（agy 多帳號已修好）：T3 0.1.11-nightly.20261120.4979 合入上游 PR 39485（原 issue #37587），三個 Antigravity 實例各自登入（實測 Ryan 23 個模型、kai 6 個、ava 6 個）。Ryan 的實例 id 改為 antigravity_ryan（原 antigravity），kai、ava 沿用原 id。
```

# 2026-11-19 定案（Gemini 3.8 Flash 分派限制）：只要目前對話是由 Gemini 3.8 Flash（如 antigravity_ava、antigravity_kai）所運行，所分配/派發出去的子對話或子任務，一律只能派給 kai 或 ava 的 Gemini 3.8 Flash（providerInstanceId: antigravity_kai 或 antigravity_ava），思考程度固定 high。嚴禁從 Gemini 3.8 Flash 主線跨派給 Claude 或其他模型。
