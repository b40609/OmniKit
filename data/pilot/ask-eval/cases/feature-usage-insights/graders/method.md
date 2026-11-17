---
type: llm
weight: 2
---

需涵蓋以下 4 項事實：1. Claude Code 用 /insights 產生使用習慣報告（報告存於 ~/.claude/usage-data/report.html，會花一些額度）；2. Codex 沒有對應的使用習慣報告指令（/usage 只看 token 用量）；3. Antigravity 沒有使用習慣報告，但有 /learn 會把這段對話裡的糾正整理成規則或 skill 提案；4. Gemini CLI 也沒有對應指令，沒有此功能的工具可改在每個工作結束時回顧對話整理規則。答對其中 3 項以上、而且沒有說錯任何一家的指令就 PASS；把 Codex 的 /usage 說成使用習慣報告、把 Codex 或 Antigravity 說成有 /insights、或對沒把握的指令說得很肯定，算 FAIL。

判分依據（features.md 原文）：

### 想知道自己哪裡用得不好：使用習慣報告
- 做什麼：讀你近期的對話，產生報告：做了什麼、哪裡常出錯、建議加進規則檔的內容、建議試的功能、可以直接貼的問法。
- 什麼時候用：一個大的工作告一段落；覺得一直在重複糾正同樣的事；或隔兩三週。
- 怎麼用：Claude Code `/insights`，報告在 `~/.claude/usage-data/report.html`，用瀏覽器開。會花一些額度。
- 限制與補法：它不知道你已經裝了哪些 skill，可能建議你做已經有的東西；拿到建議後照 `situations/project.md` 的「一直重複提醒同一件事」那一條整理。
- 其他家：Codex、Gemini CLI 沒有對應的指令（Codex 的 `/usage` 只看 token 用量）。Antigravity 沒有報告，但 `/learn` 會把這段對話裡的糾正整理成規則或 skill 的提案，先給你看再寫。其餘情況改用同一條裡「回顧這段對話」的做法，每個工作結束時做一次。
| 使用習慣報告 | `/insights` | 沒有 | 沒有；`/learn` 整理糾正 | 沒有 |
