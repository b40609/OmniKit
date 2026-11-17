---
name: ok-dispatch
description: 分派（omnikit-dispatch 的捷徑）：派子任務給別的模型或帳號，記委派紀錄。只在使用者明確輸入 /ok-dispatch 或 $ok-dispatch 時使用。Shortcut for omnikit-dispatch; use only when the user types /ok-dispatch.
argument-hint: "[要派的任務]"
disable-model-invocation: true
---

# /ok-dispatch：分派

使用者打的是 `/ok-dispatch`（Claude Code、Antigravity）或 `$ok-dispatch`（Codex），後面的字是參數：$ARGUMENTS

照 `omnikit-dispatch` 做，參數一併交給它。Claude Code 用 Skill 工具叫用 `omnikit-dispatch`；其他 agent 讀同一層資料夾裡的 `../omnikit-dispatch/SKILL.md`，照裡面的步驟做。

這個 skill 只是讓 `/ok` 打出來時列得到整組 OmniKit 的捷徑，內容以 `omnikit-dispatch` 為準，不要在這裡另外寫步驟。
