---
description: omnikit-ask 真實糾正題（real-agent-forgot-tests）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: project
situation: project.md「一直重複提醒同一件事，想讓它下次自己會」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 02/2555aeb816/1/prompt.txt 第 18 句（session 76a22c7e-19de-4161-86ec-e2249d072ec4）
---

它又忘了加測試。我已經講過不只一次：改程式一定要補測試。要怎麼讓它以後不會再忘？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
