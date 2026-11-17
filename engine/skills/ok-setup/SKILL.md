---
name: ok-setup
description: 設定（omnikit-setup 的捷徑）：建立或修改我的 OmniKit 設定（profile）。只在使用者明確輸入 /ok-setup 或 $ok-setup 時使用。Shortcut for omnikit-setup; use only when the user types /ok-setup.
disable-model-invocation: true
---

# /ok-setup：設定

使用者打的是 `/ok-setup`（Claude Code、Antigravity）或 `$ok-setup`（Codex），後面的字是參數：$ARGUMENTS

照 `omnikit-setup` 做，參數一併交給它。Claude Code 用 Skill 工具叫用 `omnikit-setup`；其他 agent 讀同一層資料夾裡的 `../omnikit-setup/SKILL.md`，照裡面的步驟做。

這個 skill 只是讓 `/ok` 打出來時列得到整組 OmniKit 的捷徑，內容以 `omnikit-setup` 為準，不要在這裡另外寫步驟。
