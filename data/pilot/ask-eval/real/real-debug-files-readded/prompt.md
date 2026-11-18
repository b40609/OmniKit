---
description: omnikit-ask 真實糾正題（real-debug-files-readded）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: debug
situation: debug.md「bug 修好了，下次又再發生」
kind: stuck
expect_fire: true
source: https://github.com/thedannywahl/pantoken refs/entire/checkpoints/1N/01M1C4M1DCHRCT0ATJKXW0W01N 1/prompt.txt 第 5 句（session 7a722705-6930-4d3a-924f-ab652ca6a0e0）
---

我根本沒在跑翻譯流程，可是這 255 個檔案一直被加回來，而且裡面的 TypeScript 文件區塊都是壞的。刪了又出現，要怎麼查？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
