---
description: omnikit-ask 情境 agent-stops-halfway
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
---

叫 agent 幫我把五個表單頁一起搬到新的驗證寫法，結果它改了兩個就停下來問我接下來怎麼辦，有時還直接在程式碼裡寫個「// 其餘邏輯同上」省略交差。要怎麼讓它好好把事情做完？
