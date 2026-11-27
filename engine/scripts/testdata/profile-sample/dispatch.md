# 個人分派設定：sample

自我測試用的假個人層：3 個 Claude 實例、1 個自動派工的 Antigravity 實例、6 個手動帳號。實例名與帳號名都是假的。

```yaml
visibility: visible
thinking_preference: max_available
on_exhausted: prompt_manual_switch
exclude_models: [gemini-3.8-flash, gpt-oss-120b, gemini-4-argon, claude-haiku-5-5]

instances:
  # claude-fable 只宣告在 claudeAgent；claudeAgent_claude_b 有存取到期日（測燒額度與到期判斷）
  claudeAgent:          {driver: claudeAgent, account: Owner, owner: self, tos_ack: "測試：本人名下", classes: [claude-opus, claude-sonnet, claude-fable]}
  claudeAgent_2:        {driver: claudeAgent, account: Alt,   owner: self, tos_ack: "測試：本人名下", classes: [claude-opus, claude-sonnet]}
  claudeAgent_claude_b: {driver: claudeAgent, account: Burn,  owner: self, tos_ack: "測試：本人名下", classes: [claude-opus, claude-sonnet], access_ends: "2026-11-28T00:00:00+08:00"}
  antigravity_main:
    driver: antigravity
    account: main
    classes: [gemini-pro, gemini-fast, gemini-carbon, gemini-orchestrator, antigravity-opus]
    owner: self
    tos_ack: "測試：知道規約表的限制，固定這一個、不輪換、一次一條"
  # 以下 6 個是手動帳號（classes 留空，agent 不自動派、不自動輪換）
  antigravity_m1: {driver: antigravity, account: m1, classes: []}
  antigravity_m2: {driver: antigravity, account: m2, classes: []}
  antigravity_m3: {driver: antigravity, account: m3, classes: []}
  antigravity_m4: {driver: antigravity, account: m4, classes: []}
  antigravity_m5: {driver: antigravity, account: m5, classes: []}
  antigravity_m6: {driver: antigravity, account: m6, classes: []}
```
