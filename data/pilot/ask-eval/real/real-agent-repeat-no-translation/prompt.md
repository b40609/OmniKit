---
description: omnikit-ask 真實糾正題（real-agent-repeat-no-translation）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: agent
situation: agent.md「每次新對話都要重講一樣的規矩」
kind: stuck
expect_fire: true
source: https://github.com/thedannywahl/pantoken refs/entire/checkpoints/21/01M35KESTEWKNZ3CP271BJMK21 3/prompt.txt 第 2 句（session 7f8c7993-0df3-4e3b-b263-c064d53dae50）
---

我已經在好幾個對話裡講過「翻譯不要做，我自己另外處理」，可是每開一個新任務，它還是又跑去做翻譯。要怎麼讓它記住？

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
