---
description: omnikit-ask 真實糾正題（real-arch-rename-recap）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: arch
situation: architecture.md「一堆不敢刪的舊檔案與過渡層」
kind: correction
expect_fire: false
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 05/c429733f7f/0/prompt.txt 第 24 句（session b35707d3-641d-4b8a-83b2-52ef9ab92ecf）
---

看一下 #999，我們不能讓程式碼變得令人混淆。功能已經改名叫 recap 了，還在用的 activity/ 檔案也要跟著改名。

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
