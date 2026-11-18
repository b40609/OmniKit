---
description: omnikit-ask 真實糾正題（real-agent-path-loop）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: agent
situation: agent.md「它卡在同一個錯誤裡打轉」
kind: correction
expect_fire: false
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 8b/5b4eca788e/1/prompt.txt 第 14 句（session ad0d3d4c-b801-4b04-8f13-d1bfb9f3edef）
---

又來了，它又在把路徑轉成 unix 格式？你到底在改什麼，完全說不通。把 /c/... 轉成 C:/... 有那麼難嗎？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
