---
description: omnikit-ask 真實糾正題（real-agent-unrelated-change）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: none
situation: 沒有對應情境
kind: correction
expect_fire: false
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 01/5674a6934c/0/prompt.txt 第 8 句（session 53820994-09c3-4a2b-8aff-8ebfda43134b）
---

我叫你修測試失敗，你為什麼順手改了 addTrailerForAgentCommit？那個改動看起來跟測試失敗沒有關係。

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
