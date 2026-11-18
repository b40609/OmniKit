---
description: omnikit-ask 真實糾正題（real-ui-styles-not-applied）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: none
situation: 沒有對應情境
kind: stuck
expect_fire: true
source: https://github.com/thedannywahl/pantoken refs/entire/checkpoints/MW/01M296998W9Y2T7AQZ6MPV3YMW 2/prompt.txt 第 3 句（session b31e715f-4790-4905-b871-127f77bea8ba）
---

它改的樣式完全沒套上去：那排按鈕不管什麼狀態都沒有邊框跟背景。我重開 dev server 也一樣，連在瀏覽器手動加 !important 的 inline style 都沒反應。是不是少了什麼建置步驟？要怎麼叫它查？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
