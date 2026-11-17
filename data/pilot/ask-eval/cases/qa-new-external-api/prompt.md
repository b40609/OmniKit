---
description: omnikit-ask 情境 qa-new-external-api
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
---

接下來要在訂單流程裡面串接一家以前沒用過的第三方物流查件 API 和 Webhook，我怕直接寫進現有邏輯之後，對方限流或回傳格式微調就整套跟著壞掉。這種外部串接該怎麼請你做？
