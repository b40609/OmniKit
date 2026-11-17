---
name: ok-eval
description: 評估工具（omnikit-eval 的捷徑）：評估新的 skill、MCP、plugin 值不值得用。只在使用者明確輸入 /ok-eval 或 $ok-eval 時使用。Shortcut for omnikit-eval; use only when the user types /ok-eval.
argument-hint: "[GitHub 連結或工具名稱]"
disable-model-invocation: true
---

# /ok-eval：評估工具

使用者打的是 `/ok-eval`（Claude Code、Antigravity）或 `$ok-eval`（Codex），後面的字是參數：$ARGUMENTS

照 `omnikit-eval` 做，參數一併交給它。Claude Code 用 Skill 工具叫用 `omnikit-eval`；其他 agent 讀同一層資料夾裡的 `../omnikit-eval/SKILL.md`，照裡面的步驟做。

這個 skill 只是讓 `/ok` 打出來時列得到整組 OmniKit 的捷徑，內容以 `omnikit-eval` 為準，不要在這裡另外寫步驟。
