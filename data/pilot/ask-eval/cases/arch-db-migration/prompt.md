---
description: omnikit-ask 情境 arch-db-migration
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
---

線上 `users` 表的 `full_name` 欄位要拆成 `first_name` 跟 `last_name`，而且不能停機、也不能讓舊資料不見。現在一堆 API 跟背景排程都有讀寫這張表，這要怎麼改才不會出事？
