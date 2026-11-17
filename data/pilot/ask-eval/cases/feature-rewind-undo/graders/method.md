---
type: llm
weight: 2
---

需涵蓋以下 4 項事實：1. Claude Code 用 /rewind 或連按兩次 Esc 退回；2. Codex 在輸入框空的時候連按兩次 Esc 改上一則訊息，或用 /fork 分叉，檔案修改則用 git 退回；3. Antigravity 用 /rewind（別名 /undo）；4. Gemini CLI 用 /rewind 或 /restore。答對其中 3 項以上、而且沒有說錯任何一家的指令就 PASS；把 Codex 說成有 /rewind 或 /undo 指令、說錯任一家指令名稱、或對沒把握的指令說得很肯定，算 FAIL。

判分依據（features.md 原文）：

| 改壞了退回 | `/rewind`，或連按兩次 Esc | 輸入框空的時候連按兩次 Esc，改上一則訊息；`/fork` 分叉。檔案用 git 退 | `/rewind`（`/undo`） | `/rewind`、`/restore` |
