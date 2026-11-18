---
description: omnikit-ask 真實糾正題（real-agent-test-fix-changes-code）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: none
situation: 沒有對應情境
kind: correction
expect_fire: false
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 15/f85f570b97/1/prompt.txt 第 9 句（session ses_2b5c4f966ffeIY6gYo1V8UkxV2）
---

你為了讓測試通過，把被測的程式改了太多，還讓測試沒辦法平行跑。這不是好的修法，請撤回，找一個不用動到被測程式這麼多的方法。

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
