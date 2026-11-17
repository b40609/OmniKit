---
type: llm
weight: 2
---

需涵蓋以下 4 項事實：1. Claude Code 用 /help 〔指令名〕 查指令，用 /powerup 看有哪些功能；2. Antigravity 用 /antigravity-guide 〔問題〕 照官方文件回答，用 /changelog 看更新紀錄；3. Codex 沒有對應的查詢指令，直接問它即可（內建的 openai-docs skill 會回答）；4. Gemini CLI 用 /docs。答對其中 3 項以上、而且沒有說錯任何一家的指令就 PASS；把 Codex 說成有 /help 或 /docs 這類對應指令、說錯 /powerup 或 /antigravity-guide 等指令名、或對沒把握的指令說得很肯定，算 FAIL。

判分依據（features.md 原文）：

### 不知道某個指令是做什麼的
- Claude Code `/help 〔指令名〕`（2.1.326 起）；想看有哪些功能用 `/powerup`。
- Antigravity `/antigravity-guide 〔問題〕`，它照官方文件回答；`/changelog` 看更新紀錄。
- Codex 沒有對應指令，直接問它「Codex 怎麼做 X」（內建的 `openai-docs` skill 會回答 Codex 的問題）。
| 學有哪些功能 | `/help 〔指令〕`、`/powerup` | 沒有；直接問它 | `/antigravity-guide`、`/changelog` | `/docs` |
