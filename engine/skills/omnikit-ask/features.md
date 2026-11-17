# 官方功能對照：什麼情況用哪個、三家各叫什麼

核對日期：2026-11-17。「待驗證」表示這次沒有在官方文件裡查到，不代表沒有。功能會變，用之前可以請 agent 查官方文件確認。

Gemini CLI 的官方文件寫著：免費與 Google One 使用者已在 2026-06-18 改用 Antigravity CLI。Antigravity 的指令這次沒查到文件，整欄待驗證；下表的 Gemini CLI 欄供參考。

## 最值得知道的幾個

### 換任務時，清掉對話
- 做什麼：開始一段空的新對話。舊的還在，可以找回來。
- 什麼時候用：下一件事跟目前的無關；或同一件事修正兩次還不對。
- 為什麼：每一次請求都會把整段對話重送一遍。聊過三件事，做第四件時三件的歷史都還在付費，也會干擾回答。清掉不花任何成本。
- 怎麼用：Claude Code `/clear`（可以加名字，例如 `/clear 登入改版`，之後用 `/resume` 找回）；桌面版直接開新對話。Gemini CLI `/clear`。Codex：開新的對話（指令名稱待驗證），舊的用 `codex resume` 找回。
- 還沒做完要換對話：先交接（見 `situations/agent.md`）。

### 同一件事做很久：壓縮，並設自動壓縮的門檻
- 做什麼：把前面的對話換成摘要。
- 什麼時候用：同一件事還沒做完，但對話已經很長。
- 怎麼用：Claude Code `/compact 保留〔要留的重點〕`；設門檻 `/autocompact 400k` 或在使用者設定檔寫 `"autoCompactWindow": 400000`（沒設的話，1M 的模型要到約 967k 才壓縮）。Codex：設定檔的 `model_auto_compact_token_limit`。Gemini CLI `/compress`（自動門檻待驗證）。
- 取捨：門檻越低越省，但壓縮次數越多，每次都會掉細節。

### 回覆太長：精簡的輸出風格
- 做什麼：先講結果，不寫開場、過程旁白、結尾回顧。工作本身一樣仔細。
- 怎麼用：Claude Code `/output-style concise`，或設定檔 `"outputStyle": "Concise"`。Codex：設定檔的 `model_verbosity`（low、medium、high）。其他：在規則檔寫一句「回覆先講結論，不要開場與回顧」。
- 注意：這是為了好讀。回覆文字只佔用量的一小部分，省不了多少額度。

### 想知道自己哪裡用得不好：使用習慣報告
- 做什麼：讀你近期的對話，產生報告：做了什麼、哪裡常出錯、建議加進規則檔的內容、建議試的功能、可以直接貼的問法。
- 什麼時候用：一個大的工作告一段落；覺得一直在重複糾正同樣的事；或隔兩三週。
- 怎麼用：Claude Code `/insights`，報告在 `~/.claude/usage-data/report.html`，用瀏覽器開。會花一些額度。
- 限制與補法：它不知道你已經裝了哪些 skill，可能建議你做已經有的東西；拿到建議後照 `situations/project.md` 的「一直重複提醒同一件事」那一條整理。Codex、Gemini CLI 沒有查到對應的指令：改用同一條裡「回顧這段對話」的做法，每個工作結束時做一次。

## 對照表

| 情況 | Claude Code | Codex | Gemini CLI |
|---|---|---|---|
| 換任務，清掉對話 | `/clear` | 開新對話（指令待驗證）；`codex resume` 找回 | `/clear` |
| 對話太長，壓縮 | `/compact`、`/autocompact` | `model_auto_compact_token_limit` | `/compress` |
| 先規劃再動手 | `/plan`，或 Shift+Tab 切換 | `/plan` | `/plan` |
| 改壞了退回 | `/rewind`，或連按兩次 Esc | 待驗證 | `/rewind`、`/restore` |
| 中途問個小問題，不想佔對話 | `/btw` | 待驗證 | 待驗證 |
| 回覆太長 | `/output-style concise` | `model_verbosity` | 規則檔寫一句 |
| 要它想深一點或快一點 | `/effort`；單次用 `ultrathink` | `model_reasoning_effort` | 待驗證 |
| 獨立審查 | 子代理；`/code-review`、`/security-review` | `/review`、`codex review` | `/agents` |
| 做完才能停的目標 | `/goal` | `/goal` | 待驗證 |
| 專案規則檔 | `CLAUDE.md`（也讀 `AGENTS.md`）；`/init` | `AGENTS.md`；`/init` | `GEMINI.md`；`/init`、`/memory` |
| 一定要執行的檢查 | hook、權限設定 | 設定檔的 hooks | `/hooks`、`/policies` |
| 使用習慣報告 | `/insights` | 沒查到 | 沒查到 |
| 用量花在哪 | `/usage`、`/context` | `/status` | `/stats` |
| 設定有沒有問題、哪些沒在用 | `/doctor`、`/skill-doctor` | 沒查到 | 沒查到 |
| 學有哪些功能 | `/powerup` | 沒查到 | `/docs` |
| 把用法包給同事 | `/team-onboarding` | 沒查到 | 沒查到 |

三家都能用的：規則檔、skill（都是 Markdown）、plan mode、worktree、這份問法庫裡「可以直接貼」的句子。只有 Claude Code 有的，多半是「量」的功能（使用習慣報告、用量歸因、設定體檢）。只用 Codex 或 Antigravity 的人，這幾樣用問法庫裡的做法手動做。
