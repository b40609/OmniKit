---
description: omnikit-ask 真實糾正題（real-agent-shortest-path）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: agent
situation: agent.md「話還沒講完，它就開始大改」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 51/a265047d72/0/prompt.txt 第 4 句（session 2026-01-24-53ea19c1-6d29-4ebf-952b-ddbb27af25bb）
---

我發現它總是走最短路徑：看到問題就直接寫程式，沒先看專案裡已經有什麼，結果一直寫出功能重複的程式。有什麼辦法？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
