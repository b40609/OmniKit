# 來源與核對狀態

這份給維護者看，agent 平常不用讀。

## 怎麼來的

2026-11-17 派 Gemini 4 Hydrogen 做飽和式調研（`omnikit-research` 的流程，帳本記的是情境不是工具）：16 組關鍵字，72 個情境、10 類，連續 3 組沒有新情境才停。條目的做法與問法由主控依官方對新模型的提示詞建議重寫（給資訊不給口號、講原因不加強調、審查者要沒看過過程）。

限制：

- **還沒有對照實測。** 沒有任何一條做過「有它與沒它」的比較。調研報告裡 72 條有 57 條的證據欄是「待驗證」；標「有實證」的 15 條我也沒有逐一核對。
- 情境的歸併是 Hydrogen 自己做的，所以「沒有新情境」的飽和強度有限。
- 中文社群只查了 2 組關鍵字。
- 調研報告有 16 個來源只給了網站首頁，無法核對，這裡沒有引用。

## 叫用測試（2026-11-17，這台，Claude Code 無頭模式，Haiku 5.5，各 1 次）

| 說法 | 有沒有叫用 | 結果 |
|---|---|---|
| 「我不知道怎麼問：畫面太多太雜，想把一些功能與按鍵入口合併」 | 有 | 讀了 `ux.md`，給出可以貼的問法，並提醒補上「哪個畫面」與「最常做的事」 |
| 「這個 bug 之前修好了，過兩天又冒出來，我該怎麼跟你講比較好」 | 第一次沒有；說明文字加上「該怎麼跟你講」後有 | 讀了 `debug.md`，給出四步的問法 |
| 「清掉對話的 /clear 是做什麼的？同事只有 Codex 怎麼辦」 | 沒有 | 模型用自己的知識回答，沒讀 `features.md` |

- 沒有允許讀檔時（無頭模式的預設），它讀不到 `situations/` 下的檔案，只用索引回答。互動模式第一次會問能不能讀。
- 上表跑在 Haiku 5.5 不是故意的：從桌面版對話裡啟動的無頭 Claude 會繼承環境變數而落到 Haiku。

同樣三題用使用者的預設模型（Fable 5.2，拿掉繼承的環境變數，各 1 次）重跑：**三題都有叫用**。問 `/clear` 那題讀了 `features.md`，還自己上網查證 Codex 的指令。

- 每題只跑一次，樣本很小。小模型上問官方功能的問題不會自動叫用，要明確打 `/omnikit-ask`。

## 我核對過的（2026-11-17）

官方文件，讀過原文：

- https://code.claude.com/docs/en/best-practices.md （給它看不到的資訊、給它檢查的方法、訪談到能寫規格、修正兩次就清掉重寫、子代理的成本、沒看過推理的審查者、規則檔放什麼、可以停止做的事）
- https://code.claude.com/docs/en/commands.md 、 https://code.claude.com/docs/en/costs.md 、 https://code.claude.com/docs/en/model-config.md 、 https://code.claude.com/docs/en/output-styles.md （`features.md` 的 Claude Code 欄）
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices.md （講清楚、給原因）
- https://learn.chatgpt.com/docs/config-file/config-reference （Codex 的 `model_auto_compact_token_limit`、`model_verbosity`、`model_reasoning_effort`）
- https://learn.chatgpt.com/docs/developer-commands?surface=cli （Codex 的 `/plan`、`/review`、`/init`、`/status`、`/goal`、`codex resume`、`codex fork`；這一頁沒有完整的斜線指令表）
- https://geminicli.com/docs/reference/commands/ （Gemini CLI 的指令）

### 2026-11-17 第二輪（補 Codex、Antigravity，加 11-10 之後的更新紀錄）

子代理（Sonnet 5.5）查，主控抽查 6 條一手證據都對得上。完整報告留在本機的對話筆記，沒有進 repo。

- https://github.com/openai/codex/blob/rust-v0.168.0/codex-rs/tui/src/slash_command.rs （Codex 的 `/new`、`/clear`、`/btw`／`/side`、`/fork`、`/import`、`/recap`、`/usage`；沒有 rewind、undo、help）
- https://learn.chatgpt.com/docs/developer-commands?surface=cli （Codex：輸入框空的時候連按兩次 Esc 改上一則訊息）
- 本機 `codex --help`、`codex doctor --help`（`codex doctor` 診斷安裝、設定、登入）；https://github.com/openai/codex/releases 的 0.168.0、0.169.0
- https://antigravity.google/docs/cli/reference.md 、`docs/slash-commands.md`、`docs/commands/{btw,goal,learn,antigravity-guide}.md`、`docs/cli/commands/{effort,usage,context,changelog}.md`、`docs/rules.md`、`docs/build-plugins.md`、`docs/changelog.md`（Antigravity 欄）
- https://github.com/google-gemini/gemini-cli 的 `docs/reference/commands.md`、`docs/reference/configuration.md`（`model.compressionThreshold`、`thinkingLevel`／`thinkingBudget`）、`docs/hooks/reference.md`（`AfterAgent`）
- https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md 的 2.1.322 到 2.1.326（`/help <command>`、`/doctor` 邊跑邊回報；沒有指令改名或移除）
- 還是查不到：Antigravity 自動壓縮的門檻、`/compact` 在 CLI 指令表沒列（changelog 1.3.5 有）；Gemini CLI 的 extensions 能包哪些東西；Antigravity IDE 專屬的 rewind、btw、compact。

社群與研究，確認存在：

- mattpocock/skills：`grill-me`、`retro`、`triage`、`pr`、`improve-codebase-architecture`、`handoff`（路徑存在；`retro` 的原文讀過）
- addyosmani/agent-skills：`interview-me`、`doubt-driven-development`、`frontend-ui-engineering`、`code-simplification`、`source-driven-development`、`planning-and-task-breakdown`、`browser-testing-with-devtools`、`documentation-and-adrs`、`deprecation-and-migration`、`observability-and-instrumentation`（路徑存在，內容沒有逐一讀）
- obra/superpowers：`systematic-debugging`、`verification-before-completion`、`brainstorming`、`using-git-worktrees`（路徑存在，內容沒有逐一讀）
- https://www.nngroup.com/articles/signal-noise-ratio/ （訊噪比）
- https://aclanthology.org/2026.emnlp-main.738/ （Handoff Debt 論文）
- https://www.anthropic.com/research/AI-assistance-coding-skills （用 AI 學新函式庫的實驗）
- https://hbr.org/2007/09/performing-a-project-premortem （事前驗屍；網址是調研給的，這次沒有重新打開）

### 2026-11-18 補充（`features.md` 新增的 6 列與「規則檔與 skill 越來越重」一節）

官方，讀過原文：

- https://code.claude.com/docs/en/features-overview （「Build your setup over time」觸發表、「Context cost by feature」、`disable-model-invocation` 與 `skillOverrides`、dynamic workflow、cross-session messaging、code intelligence；起手清單第 6 節也用這頁）
- https://claude.dev/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models （Thariq Shihipar，2026-07-24：為新模型把 Claude Code 系統提示砍掉八成以上、評測沒有退步；給判斷不給規則、不給範例、漸進揭露；CLAUDE.md 寫地雷、不寫看專案就知道的事）
- https://www.claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop （Diane Sarkis，2026-10-22：單一 agent 加 skill 常比整組子代理好；只在 context 塞到測得出變差、要平行、選不到工具或指示互相打架時拆；收回時一次收一個、有它沒它各比一次）
- `/doctor prompt-audit`：2026-11-17 在這台 Claude Code 2.1.326 無頭跑過一次（plan 模式，唯讀），會先列清單、確認才改

沒讀到原文的：Lydia Hallie〈Rethinking Claude Code Best Practices〉（AI Engineer，2026-11-12），字幕被 YouTube 限速擋住；〈Using Claude Code: Spending your effort〉只看過影片的轉述。

## 調研裡我改掉的

- 「官方建議規則檔控制在 60 到 80 行」：官方文件沒有這個數字（費用頁寫的是 200 行以內）。條目裡只寫「保持短」。
- 問法裡的「嚴禁」「禁止稱讚」「扮演嚴格的某某」：照官方建議改成講原因、指定沒看過過程的審查者。

## 人類專業的做法（跨領域）

條目的「依據」提到的方法都是各領域的通用做法，這次沒有逐一附來源：Nielsen 十項可用性原則與啟發式評估、漸進式揭露、認知走查、卡片分類、WCAG、設計評審、內容設計、五個為什麼與無指責複盤、事前驗屍、特徵測試（Feathers）、絞殺者模式與平行變更（Fowler）、深模組（Ousterhout）、ADR、Chesterton 的柵欄、JTBD、MoSCoW、Shape Up、YAGNI、垂直切片、突變測試、探索性資料分析、金字塔原理、TRIZ。
