---
description: omnikit-ask 真實糾正題（real-agent-lint-still-fails）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: agent
situation: agent.md「它說做完了，其實沒有」
kind: correction
expect_fire: false
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 02/2555aeb816/1/prompt.txt 第 63 句（session 76a22c7e-19de-4161-86ec-e2249d072ec4）
---

不對，linter 還是失敗。你上一輪說修好了。

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
