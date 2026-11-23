# OmniKit 規約表：各供應商帳號能不能讓 agent 自動派工、自動挑帳號

這份是共用層，所有使用者都套用；個人層（profile 的 `dispatch.md`）只能用 `tos_ack` 記下「知情後仍要這樣用」，不能把 `forbidden` 改成可以。`engine/scripts/accounts.py` 讀下面的 YAML，`run.py show` 照它在每個實例旁邊寫原因。

每一筆是「供應商 driver ＋ 登入方式」。欄位：

- `verdict`：`ok`（官方明寫支援這種用法）、`caution`（條款文字有疑慮或沒明寫）、`avoid`（官方明寫不支援，可能停權）、`unknown`（沒查到一手原文）。
- `auto_dispatch`：agent 自動把子任務派到這種帳號。`allowed`、`needs_ack`（要使用者在 profile 填 `tos_ack` 才會派）、`forbidden`（不派，`tos_ack` 也不行）。
- `auto_select`：同一家有好幾個帳號時，在工作包之間依額度自動挑帳號。值同上。
- `source`、`quote`：一手原文與網址；`checked`：查證日期。條款會改，超過 90 天沒重查時 `accounts.py check` 會提醒。

三家都禁止把帳號給別人用：`owner` 不是本人（`self`）的帳號一律不自動派。

```yaml
checked: 2026-11-23
terms:
  antigravity:
    oauth-personal:
      verdict: avoid
      auto_dispatch: needs_ack
      auto_select: forbidden
      source: https://antigravity.google/docs/faq
      quote: "Antigravity CLI headless mode (agy -p) is intended for direct scripting and CI workflows. Wrapping agy inside third-party coding agents or applications, or automating account rotation, is not supported under consumer plans."
      note: 同一頁另一題寫用第三方軟體存取 Antigravity 登入違反服務條款、可能停權，建議改用 Gemini Enterprise 或 Google AI Studio API 金鑰。
    oauth-business:
      verdict: ok
      auto_dispatch: allowed
      auto_select: needs_ack
      source: https://antigravity.google/docs/faq
      quote: FAQ 建議自動化改用 Gemini Enterprise 或 Google AI Studio API 金鑰。
      note: 多個 Enterprise 帳號自動輪用沒查到明文（待驗證），所以 auto_select 要 tos_ack。
    gemini-api-key:
      verdict: ok
      auto_dispatch: allowed
      auto_select: allowed
      source: https://antigravity.google/docs/faq
      quote: FAQ 建議自動化改用 Gemini Enterprise 或 Google AI Studio API 金鑰。
    agent-platform:
      verdict: ok
      auto_dispatch: allowed
      auto_select: allowed
      source: https://antigravity.google/docs/faq
      quote: Vertex AI（T3 的 Agent Platform 登入）走雲端專案計費，屬 API 路線。
      note: FAQ 原文點名的是 Enterprise 與 AI Studio API 金鑰；Vertex 歸 API 路線是 OmniKit 的判讀（待驗證）。
  claudeAgent:
    subscription:
      verdict: caution
      auto_dispatch: needs_ack
      auto_select: needs_ack
      source: https://www.anthropic.com/legal/consumer-terms
      quote: "Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it, to access the Services through automated or non-human means, whether through a bot, script, or otherwise."
      note: Claude Code 文件（https://code.claude.com/docs/en/authentication）寫同一人多帳號「give each account its own configuration directory」；法務頁寫訂閱額度假設「ordinary, individual usage」。
    api-key:
      verdict: ok
      auto_dispatch: allowed
      auto_select: allowed
      source: https://code.claude.com/docs/en/legal-and-compliance
      quote: "Developers building products or services ... should use API key authentication through Claude Console or a supported cloud provider."
  codex:
    subscription:
      verdict: caution
      auto_dispatch: needs_ack
      auto_select: needs_ack
      source: https://openai.com/policies/row-terms-of-use/
      quote: 禁止「circumvent any rate limits or restrictions」與「Automatically or programmatically extract data or Output」。
      note: 多個 CODEX_HOME 隔離只有第三方教學，OpenAI 官方沒找到對應文字（待驗證）。
    api-key:
      verdict: ok
      auto_dispatch: allowed
      auto_select: allowed
      source: https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
      quote: 模型變更說明寫「does not affect the OpenAI API or using Codex with your own API key」。
# 沒列到的 driver 或登入方式：verdict unknown，auto_dispatch 與 auto_select 都當 needs_ack。
default_auth:
  antigravity: oauth-personal
  claudeAgent: subscription
  codex: subscription
```
