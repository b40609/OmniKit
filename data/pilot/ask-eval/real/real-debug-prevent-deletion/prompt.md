---
description: omnikit-ask 真實糾正題（real-debug-prevent-deletion）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: debug
situation: debug.md「同一類的坑一直踩，想徹底複盤」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 23/72de7ea2ff/0/prompt.txt 第 5 句（session 2026-01-12-deeac353-0765-4439-9056-293619a99172）
---

這個分支在修 agent 誤刪檔案的問題，我叫它再檢查了兩次。我想知道：CLAUDE.md 裡面的規則夠不夠防止這種事再發生？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
