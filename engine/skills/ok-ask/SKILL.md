---
name: ok-ask
description: 問法庫（omnikit-ask 的捷徑）：卡住、不知道怎麼開口時找好的問法。只在使用者明確輸入 /ok-ask 或 $ok-ask 時使用。Shortcut for omnikit-ask; use only when the user types /ok-ask.
argument-hint: "[你的狀況]"
disable-model-invocation: true
---

# /ok-ask：問法庫

使用者打的是 `/ok-ask`（Claude Code、Antigravity）或 `$ok-ask`（Codex），後面的字是參數：$ARGUMENTS

照 `omnikit-ask` 做，參數一併交給它。Claude Code 用 Skill 工具叫用 `omnikit-ask`；其他 agent 讀同一層資料夾裡的 `../omnikit-ask/SKILL.md`，照裡面的步驟做。

後面沒有字：照 `../ok/SKILL.md` 的「問法庫選單」列出類別，讓使用者回編號。

這個 skill 只是讓 `/ok` 打出來時列得到整組 OmniKit 的捷徑，內容以 `omnikit-ask` 為準，不要在這裡另外寫步驟。
