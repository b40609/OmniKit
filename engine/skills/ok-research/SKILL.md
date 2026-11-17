---
name: ok-research
description: 調研（omnikit-research 的捷徑）：查業界做法、找同類工具、比較方案。只在使用者明確輸入 /ok-research 或 $ok-research 時使用。Shortcut for omnikit-research; use only when the user types /ok-research.
argument-hint: "[要查的題目]"
disable-model-invocation: true
---

# /ok-research：調研

使用者打的是 `/ok-research`（Claude Code、Antigravity）或 `$ok-research`（Codex），後面的字是參數：$ARGUMENTS

照 `omnikit-research` 做，參數一併交給它。Claude Code 用 Skill 工具叫用 `omnikit-research`；其他 agent 讀同一層資料夾裡的 `../omnikit-research/SKILL.md`，照裡面的步驟做。

這個 skill 只是讓 `/ok` 打出來時列得到整組 OmniKit 的捷徑，內容以 `omnikit-research` 為準，不要在這裡另外寫步驟。
