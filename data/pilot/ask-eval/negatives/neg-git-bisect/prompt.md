---
description: omnikit-ask 負例 neg-git-bisect
kind: negative
expect_fire: false
---

用 git bisect 找出哪個 commit 讓 `npm test` 開始失敗，已知 `v1.2.0` 是好的、`HEAD` 是壞的，給我指令。
