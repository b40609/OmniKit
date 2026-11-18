---
description: omnikit-ask 真實糾正題（real-debug-flaky-windows）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: debug
situation: debug.md「有時候壞、有時候好」
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 8b/5b4eca788e/1/prompt.txt 第 30 句（session ad0d3d4c-b801-4b04-8f13-d1bfb9f3edef）
---

我不記得了：這個 Windows 的 e2e 測試為什麼會不穩？為什麼不是每次都壞？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
