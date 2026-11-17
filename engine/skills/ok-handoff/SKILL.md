---
name: ok-handoff
description: 交接（omnikit-handoff 的捷徑）：把做到一半的工作交給新對話，或照交接檔接手。只在使用者明確輸入 /ok-handoff 或 $ok-handoff 時使用。Shortcut for omnikit-handoff; use only when the user types /ok-handoff.
argument-hint: "[交接檔路徑]"
disable-model-invocation: true
---

# /ok-handoff：交接

使用者打的是 `/ok-handoff`（Claude Code、Antigravity）或 `$ok-handoff`（Codex），後面的字是參數：$ARGUMENTS

照 `omnikit-handoff` 做，參數一併交給它。Claude Code 用 Skill 工具叫用 `omnikit-handoff`；其他 agent 讀同一層資料夾裡的 `../omnikit-handoff/SKILL.md`，照裡面的步驟做。

這個 skill 只是讓 `/ok` 打出來時列得到整組 OmniKit 的捷徑，內容以 `omnikit-handoff` 為準，不要在這裡另外寫步驟。
