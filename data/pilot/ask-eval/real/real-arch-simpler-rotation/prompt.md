---
description: omnikit-ask 真實糾正題（real-arch-simpler-rotation）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: none
situation: 沒有對應情境
kind: stuck
expect_fire: true
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 14/886a520190/0/prompt.txt 第 25 句（session f012439c-5bfb-42a7-bd2e-6399c77c9f36）
---

設計文件寫了兩個處理並發輪替的選項：在 ref 上做樂觀鎖，或讓第二個寫入者發現 current 已經輪替過、改寫到新的 current。我想再確認：真的沒有更簡單的方法嗎？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
