---
description: omnikit-ask 情境 agent-hallucinated-api
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
---

昨天叫 agent 接一個我們有裝的圖表套件，結果它自己編了一個根本不存在的參數跟函式名稱，寫完才在噴型別錯誤，害我除錯半天。要怎麼避免它每次遇到外部套件就用猜的？
