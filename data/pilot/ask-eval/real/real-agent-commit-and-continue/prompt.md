---
description: omnikit-ask 真實糾正題（real-agent-commit-and-continue）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: agent
situation: agent.md「它一直停下來等我按確認，或權限開太大亂改」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 69/61155c2f6e/0/prompt.txt 第 3 句（session ses_29b5bcf47ffeomWfkY2fNw7Gw2）
---

我只說「commit 然後繼續」，它 commit 完就自己往下做了一大串，中間又 commit 了好幾次，完全沒問我。我要它每一步都先給我看，該怎麼跟它講？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
