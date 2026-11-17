---
description: omnikit-ask 情境 agent-context-bloat
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
---

我待會要請 agent 把整個權限模組十幾個檔案跟昨天幾千行的 error log 全部翻一遍，找出哪裡有漏檢查，但很怕一讀就把這條對話的上下文塞爆，後面沒辦法好好改程式。該怎麼處理比較好？
