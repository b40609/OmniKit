# 個人分派設定：ryan

分派規則（任務類型、級別、模型類別、思考程度、升級）照共用層 `data/rules/dispatch.md`；這份只寫 ryan 有哪些供應商實例，以及每個模型類別用哪個實例。`instances` 的 key 是 T3 的供應商實例 id：在 T3 裡是 `delegate_task` 的 `target.providerInstanceId`，不在 T3 裡（Claude Code、Codex、Antigravity）就是 `t3 thread start --provider` 的值（例如 `t3 thread start . "<任務>" --provider antigravity_kai --model gemini-3.8-flash --json --wait`，在 PowerShell 跑；Git Bash 要打 `t3.cmd`；見政策的 `t3_cli` 管道）；`classes` 裡同一個類別列了好幾個實例時，由上往下用。

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
    needs_user: antigravity 的 Gemini 額度用完時，請 ryan 開啟 ava、kai 帳號再用
  antigravity_kai:
    driver: antigravity
    account: kai
    classes: [gemini-flash]
    needs_user: 同 antigravity_ava

# 原生子代理（Agent 工具）用的是目前這段對話的帳號，不用列。
# 要用 delegate_task 派給 Claude 時，先用目前這段對話的實例（inherited）；那個帳號額度用完，再照上面 instances 的順序（claudeAgent、claudeAgent_2、claudeAgent_claude_kai）換下一個。使用者沒有偏好（2026-11-18 定案）。
```
