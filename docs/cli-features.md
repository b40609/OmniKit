# 官方功能對照：什麼情況用哪個、各家叫什麼

核對日期：2026-11-17（補齊 Claude Code、Codex、Antigravity 指令與更新紀錄；2026-11-25 自退役的 `omnikit-ask` 移出獨立留存）。「待驗證」表示當時沒有在官方文件或原始碼裡查到，不代表沒有。功能會隨版本演進，用之前可請 agent 查最新官方文件確認。2026-11-18 補了對照表最後 6 列與「規則檔與 skill 越來越重」一節（Claude Code 欄已於 2.1.326 實跑核對 `/doctor prompt-audit`；其他欄標待驗證，由官方功能雷達後續補齊）。

核對基準版本：Claude Code 2.1.326、Codex 0.168.0（原始碼 tag rust-v0.168.0）、Antigravity CLI 1.5.9、Gemini CLI 0.68.0。

Gemini CLI 的免費與 Google One 使用者已在 2026-06-18 改用 Antigravity CLI，所以表上以 Antigravity 為主，Gemini CLI 欄供還在用的人參考。Antigravity 的官方文件有純文字版，可以直接抓：`https://antigravity.google/docs/<頁面>.md`（索引在 `https://antigravity.google/llms.txt`）。下表的 Antigravity 指令以 CLI 為準，App 多半同名；IDE 沒有完整的指令表。

## 最值得知道的幾個

### 換任務時，清掉對話
- 做什麼：開始一段空的新對話。舊的還在，可以找回來。
- 什麼時候用：下一件事跟目前的無關；或同一件事修正兩次還不對。
- 為什麼：每一次請求都會把整段對話重送一遍。聊過三件事，做第四件時三件的歷史都還在付費，也會干擾回答。清掉不花任何成本。
- 怎麼用：Claude Code `/clear`（可以加名字，例如 `/clear 登入改版`，之後用 `/resume` 找回）；桌面版直接開新對話。Codex `/new`（不清畫面）或 `/clear`，舊的用 `codex resume` 找回。Antigravity `/clear`（別名 `/new`），`/resume` 找回。
- 還沒做完要換對話：先交接（見 `omnikit-handoff`）。

### 同一件事做很久：壓縮，並設自動壓縮的門檻
- 做什麼：把前面的對話換成摘要。
- 什麼時候用：同一件事還沒做完，但對話已經很長。
- 怎麼用：Claude Code `/compact 保留〔要留的重點〕`；設門檻 `/autocompact 400k` 或在使用者設定檔寫 `"autoCompactWindow": 400000`（沒設的話，1M 的模型要到約 967k 才壓縮）。Codex：設定檔的 `model_auto_compact_token_limit`。Antigravity：會自動壓縮，手動用 `/compact`（門檻查不到；`/compact` 在 changelog 有、CLI 指令表沒列，用之前先試）。Gemini CLI `/compress`，門檻是設定檔的 `model.compressionThreshold`（0 到 1 的比例，預設 0.5）。
- 取捨：門檻越低越省，但壓縮次數越多，每次都會掉細節。

### 需求還沒想清楚：先規劃或讓它反過來訪談你
- 做什麼：鎖住寫檔權限先讀程式碼庫，由 agent 針對缺漏的決策一題一題反問（附推薦答案），對齊規格與計畫後再動手。
- 怎麼用：三家都有 `/plan`（Claude Code 與 Antigravity 也可按 `Shift+Tab` 切換）；Antigravity 另外內建 `/grill-me` 互動訪談指令，Claude Code 內建 `AskUserQuestion` 選擇題工具。

### 中途問個小問題，不想塞進主對話
- 做什麼：在旁邊開一個暫時的分支回答，主對話不會多出這段。
- 什麼時候用：做到一半想問「這個參數是什麼意思」這類跟主線無關的小事。
- 怎麼用：Claude Code、Codex、Antigravity 都是 `/btw 〔問題〕`（Codex 也叫 `/side`）。

### 回覆太長：精簡的輸出風格
- 做什麼：先講結果，不寫開場、過程旁白、結尾回顧。工作本身一樣仔細。
- 怎麼用：Claude Code `/output-style concise`，或設定檔 `"outputStyle": "Concise"`。Codex：設定檔的 `model_verbosity`（low、medium、high）。Antigravity 的 `verbosity` 設定管的是畫面顯示多少過程，不一定縮短回覆本身。其他：在規則檔寫一句「回覆先講結論，不要開場與回顧」。
- 注意：這是為了好讀。回覆文字只佔用量的一小部分，省不了多少額度。

### 想知道自己哪裡用得不好：使用習慣報告
- 做什麼：讀你近期的對話，產生報告：做了什麼、哪裡常出錯、建議加進規則檔的內容、建議試的功能。
- 什麼時候用：一個大的工作告一段落；覺得一直在重複糾正同樣的事；或隔兩三週。
- 怎麼用：Claude Code `/insights`，報告在 `~/.claude/usage-data/report.html`，用瀏覽器開。會花一些額度。
- 限制與補法：它不知道你已經裝了哪些 skill，可能建議你做已經有的東西；拿到建議後只挑重複發生兩次以上的錯誤寫進規則檔或確定性 hook。
- 其他家：Codex、Gemini CLI 沒有對應的指令（Codex 的 `/usage` 只看 token 用量）。Antigravity 沒有報告，但 `/learn` 會把這段對話裡的糾正整理成規則或 skill 的提案，先給你看再寫。

### 規則檔與 skill 越來越重
- 做什麼：找出規則檔與 skill 裡過時、互相打架、或 agent 看程式碼就知道的指示；把不常用的 skill 從每回合的 context 拿掉。
- 什麼時候用：規則檔改過很多次；換了新模型；回覆變慢、額度掉得快；覺得 agent 一直過度套用某條規則。
- 怎麼用：Claude Code `/doctor prompt-audit`（`/checkup` 是同一個指令），它先列清單、你確認才改，改完自己看一次 diff。自己寫的 skill，說明欄只想在點名時用的，front matter 寫 `disable-model-invocation: true`；別人的 skill 不想改它的檔，就在設定檔用 `skillOverrides` 做同一件事，不用移除整個 plugin。
- 其他家：Codex 停用單一 skill 是設定檔的 `[[skills.config]]`（讀過官方文件，沒實測）；Antigravity 支援 `skills.json` 的 `exclude` 欄位；Gemini CLI 待驗證。
- 依據：官方 `code.claude.com/docs/en/features-overview` 的「Context cost by feature」；Anthropic 為新模型把 Claude Code 的系統提示砍掉八成以上，評測沒有退步（Thariq Shihipar，2026-07-24）。

### 不知道某個指令是做什麼的
- Claude Code `/help 〔指令名〕`（2.1.326 起）；想看有哪些功能用 `/powerup`。
- Antigravity `/antigravity-guide 〔問題〕`，它照官方文件回答；`/changelog` 看更新紀錄。
- Codex 沒有對應指令，直接問它「Codex 怎麼做 X」（內建的 `openai-docs` skill 會回答 Codex 的問題）。

## 對照表

| 情況 | Claude Code | Codex | Antigravity | Gemini CLI |
|---|---|---|---|---|
| 換任務，清掉對話 | `/clear` | `/new`、`/clear`；`codex resume` 找回 | `/clear`（`/new`）；`/resume` 找回 | `/clear` |
| 對話太長，壓縮 | `/compact`、`/autocompact` | `model_auto_compact_token_limit` | 自動；`/compact`（待驗證） | `/compress`；`model.compressionThreshold` |
| 先規劃／訪談對焦再動手 | `/plan`（或 Shift+Tab）；`AskUserQuestion` | `/plan` | `/plan`（或 Shift+Tab）；`/grill-me` | `/plan` |
| 改壞了退回 | `/rewind`，或連按兩次 Esc | 輸入框空的時候連按兩次 Esc，改上一則訊息；`/fork` 分叉。檔案用 git 退 | `/rewind`（`/undo`） | `/rewind`、`/restore` |
| 中途問個小問題，不想佔對話 | `/btw` | `/btw`（`/side`） | `/btw` | 沒有 |
| 回覆太長 | `/output-style concise` | `model_verbosity` | 規則檔寫一句（`verbosity` 只管畫面） | 規則檔寫一句 |
| 要它想深一點或快一點 | `/effort`；單次用 `ultrathink` | `model_reasoning_effort` | `/effort`、`--effort` | 設定檔的 `thinkingLevel` 或 `thinkingBudget` |
| 獨立審查 | 子代理；`/code-review`、`/security-review` | `/review`、`codex review` | 自訂子代理 `/agents`；`/diff` | `/agents` |
| 做完才能停的目標 | `/goal` | `/goal` | `/goal` | 沒有指令；`AfterAgent` hook 可以擋 |
| 專案規則檔 | `CLAUDE.md`（也讀 `AGENTS.md`）；`/init` | `AGENTS.md`；`/init` | `AGENTS.md` 或 `GEMINI.md`、`.agents/rules/` | `GEMINI.md`；`/init`、`/memory` |
| 一定要執行的檢查 | hook、權限設定 | 設定檔的 hooks（第一次要在 `/hooks` 信任） | hooks（`/hooks`） | `/hooks`、`/policies` |
| 使用習慣報告 | `/insights` | 沒有 | 沒有；`/learn` 整理糾正 | 沒有 |
| 用量花在哪 | `/usage`、`/context` | `/status`、`/usage` | `/usage`、`/context` | `/stats` |
| 設定有沒有問題、哪些沒在用 | `/doctor`、`/skill-doctor` | `codex doctor`（只查環境與設定壞了沒） | 沒有 | 沒有 |
| 學有哪些功能 | `/help 〔指令〕`、`/powerup` | 沒有；直接問它 | `/antigravity-guide`、`/changelog` | `/docs` |
| 把用法包給同事 | `/team-onboarding`；或做成 plugin | 做成 plugin（`codex plugin marketplace add`）；`/import` 從 Claude Code 帶設定過來 | 做成 plugin | `/extensions`（能包哪些待驗證） |
| 規則檔有沒有過時或互相打架 | `/doctor prompt-audit`（`/checkup`） | 待驗證 | 待驗證 | 待驗證 |
| 不常用的 skill 別每回合佔 context | `disable-model-invocation: true`；別人的 skill 用 `skillOverrides` | `[[skills.config]]`（待驗證） | `skills.json` 的 `exclude` | 待驗證 |
| 讓它自己記住學到的事 | auto memory（自動記憶，不用自己寫） | 待驗證 | `/learn` 先提案再寫 | `/memory`（手動加） |
| 一次跑很多子代理、交叉驗證 | dynamic workflow（在提示裡要求跑一個 workflow） | 待驗證 | `run_workflow` | 待驗證 |
| 一段對話的結論送到另一段 | cross-session messaging（請它把結論送過去） | 待驗證 | 待驗證 | 待驗證 |
| 型別語言找定義、找引用 | 裝那個語言的 code intelligence plugin | 待驗證 | 待驗證 | 待驗證 |

三家都能用的：規則檔、skill（都是 Markdown）、plan mode（`/plan`）、`/btw`、`/goal`、plugin、worktree。只有 Claude Code 有的，多半是「量」的功能（使用習慣報告、用量歸因、設定體檢）。
