---
description: omnikit-ask 情境 arch-decision-record
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
---

我們剛剛終於決定認證改用 stateless JWT、不再存 session 到 Redis 了，討論了快一小時才拍板。但過幾個月或換人接手，大家一定又會問當初為什麼不放 Redis，這要怎麼留下來才不會之後又重吵一次？
