---
description: omnikit-ask 真實糾正題（real-debug-global-gitignore）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: debug
situation: debug.md「我的電腦正常，CI 或正式環境壞掉」
kind: correction
expect_fire: false
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 48/b4b05476e5/0/prompt.txt 第 8 句（session 1c38adc0-5071-4382-9e53-de8c30e2265f）
---

等一下，問題其實是我的全域 git ignore（~/.config/git/ignore）忽略了 .claude/settings.local.json，而 go-git 沒有讀全域設定。專案的 .gitignore 早就處理好了。

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
