---
type: llm
weight: 2
---

需涵蓋以下 4 項事實：1. Claude Code 用 /btw 在旁邊開暫時分支回答，不會寫進主對話；2. Codex 用 /btw 或 /side 問旁支問題；3. Antigravity 用 /btw 問旁支問題；4. Gemini CLI 沒有這個功能。答對其中 3 項以上、而且沒有說錯任何一家的指令就 PASS；說錯指令、把 Gemini CLI 說成有 /btw 或 /side、或對沒把握的指令說得很肯定，算 FAIL。

判分依據（features.md 原文）：

### 中途問個小問題，不想塞進主對話
- 做什麼：在旁邊開一個暫時的分支回答，主對話不會多出這段。
- 什麼時候用：做到一半想問「這個參數是什麼意思」這類跟主線無關的小事。
- 怎麼用：Claude Code、Codex、Antigravity 都是 `/btw 〔問題〕`（Codex 也叫 `/side`）。
| 中途問個小問題，不想佔對話 | `/btw` | `/btw`（`/side`） | `/btw` | 沒有 |
