---
description: omnikit-ask 真實糾正題（real-debug-ci-still-fails）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: debug
situation: debug.md「我的電腦正常，CI 或正式環境壞掉」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 01/5674a6934c/0/prompt.txt 第 4 句（session 53820994-09c3-4a2b-8aff-8ebfda43134b）
---

PR 開了，可是 CI 上 gemini-cli 的測試還是失敗，它之前說本機都過了。這種情況要怎麼叫它查？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
