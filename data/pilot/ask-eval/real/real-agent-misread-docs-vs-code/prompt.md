---
description: omnikit-ask 真實糾正題（real-agent-misread-docs-vs-code）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: docs
situation: docs.md「文件跟程式對不起來」
kind: correction
expect_fire: false
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 02/2555aeb816/1/prompt.txt 第 20 句（session 76a22c7e-19de-4161-86ec-e2249d072ec4）
---

你沒聽懂：開了雙寫的時候，摘要要同時寫進 v1 跟 v2 兩個儲存。現在 v2 還沒寫摘要，但它應該要寫。要改的是程式，不是去改註解說「只寫 v1」。

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
