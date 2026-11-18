---
description: omnikit-ask 真實糾正題（real-agent-not-convinced-needed）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: agent
situation: agent.md「只要簡單功能，它蓋了一整套架構」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 7d/aa370e8203/0/prompt.txt 第 40 句（session 019e21b7-de04-7873-ab36-adadcc3930ec）
---

它在測試裡加了一些輔助程式，我問了幾次還是不覺得需要。我不想讓 codebase 多一堆東西，只想要一個答案：到底需不需要？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
