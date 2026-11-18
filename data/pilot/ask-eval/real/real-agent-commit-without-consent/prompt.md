---
description: omnikit-ask 真實糾正題（real-agent-commit-without-consent）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: agent
situation: agent.md「規則寫了，它還是照樣違反」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main ef/6cefb310e0/0/prompt.txt 第 30 句（session 581df83f-fb6e-425e-a135-362f6ea16c5a）
---

我已經講過好幾次：沒有我同意不要 commit。它剛剛又自己 commit 了。我要怎麼讓它真的停下來？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
