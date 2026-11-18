---
description: omnikit-ask 真實糾正題（real-quality-review-slow）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: quality
situation: quality.md「系統變慢，不知道慢在哪」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/0G/01KWY3M0FWWCV0SVB84CPG040G 0/prompt.txt 第 11 句（session 93833a17-c2c6-4cb0-85b2-663c867b105f）
---

跑一次審查指令，Codex 要 7 分鐘、Claude 跑到 13 分鐘還沒完，比直接在 agent 對話裡叫它審還慢，這樣就沒意義了。是不是使用者選的每個 skill 都一個一個跑？怎麼查它慢在哪？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
