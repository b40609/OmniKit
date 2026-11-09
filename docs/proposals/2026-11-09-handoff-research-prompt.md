# 給 Gemini 的深度研究 prompt：自動交接與跨 session 狀態

用法：整段複製給 Gemini（要能下載 repo、讀原始碼的模式）。研究結果請存成 `docs/v2/research/handoff.md`，之後由 Claude 讀取討論。

---

## 任務

請實際下載以下兩個 GitHub 專案的完整原始碼，做原始碼層級的深度研究，回答我列出的問題。目的是決定：我要自己開發一套「自動交接與工作狀態」功能，支援 Claude Code、Codex、Antigravity 三個 coding agent；這兩個專案哪些設計可以借用、哪些不要學。

1. `https://github.com/alexknowshtml/claude-auto-handoff`（Claude Code 的 mod，到達上下文門檻時寫交接摘要、清空對話、用新段落接手，取代自動壓縮）
2. `https://github.com/parcadei/Continuous-Claude-v3`（Claude Code 的大型延續性框架：continuity ledger、handoff、PostgreSQL、hooks、背景 daemon）

## 我的背景（研究時要用這些條件判斷）

- 作業系統：Windows 11（主要），PowerShell 5.1 與 7 都要能用；公司電腦有 Trend Micro，可能擋未簽章的程式。
- 介面：Claude Code 桌面版（主力跑 Claude）、T3 Code（跑 Codex、Antigravity；它的 Claude 走 Claude Agent SDK，settingSources 帶 user、project、local）、偶爾用 CLI。
- 我已經有一個自己的工具（OmniKit），會把規則同步到 `~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md`、`~/.gemini/GEMINI.md`，也已經在 Claude Code 與 Codex 註冊一個 Stop hook：上下文跨過 100k、200k tokens 或成功 git push 時，提醒「該開新對話了」，但只是提醒，不會交接。
- 我常在多台電腦開發同一個 GitHub 專案，交接與狀態要能跨裝置；其中三個專案的 repo 是公開的，交接內容不能進公開 repo。
- 我最痛的兩件事（同等重要）：
  - P1：同時開很多對話，不主動問就不知道哪個在等我、哪個做完、哪個卡住。
  - P3：上下文快滿時不知道怎麼順暢轉到新對話，新對話要重講脈絡。

## 研究規則

- 每個專案先 `git clone`，記下 commit SHA；所有結論附證據，格式 `檔案路徑:行號 @ SHA前7碼`。
- **不要執行任何會寫入 `~/.claude/`、`~/.codex/`、`~/.gemini/` 的安裝程式或精靈**（Continuous-Claude-v3 的 wizard 會改全域設定）。只讀原始碼；要跑測試的話，用隔離的臨時目錄並把 HOME／USERPROFILE 指到那裡。
- 區分三種說法：**已驗證**（讀到程式碼或實際跑過）、**推論**（從程式碼推得）、**未知**。README 寫的但程式碼沒看到的，標「僅文件宣稱」。
- 官方文件優先：Claude Code（code.claude.com/docs）、Codex（developers.openai.com/codex）、Antigravity（antigravity.google/docs）。
- 全文用繁體中文（台灣用語）；程式碼、指令、路徑、錯誤訊息維持原文。不要用 LaTeX 數學語法，數字與單位用純文字。

## 問題

### A. claude-auto-handoff 的運作原理

1. 它用了 Claude Code 的哪些介面（mod／function hook／plugin API）？逐一列出，並說明每個介面在流程中做什麼。這些介面是正式功能還是實驗性的？最低需要哪個 Claude Code 版本？
2. 門檻怎麼量：上下文大小從哪裡讀？「還沒量到的工具輸出用估算」是怎麼估的？
3. 超過門檻後「拒絕新的工具呼叫」是怎麼做到的？會不會讓正在做的事做一半？
4. 交接摘要：由誰寫（Haiku？）、prompt 全文、輸出欄位；哪些欄位由程式從對話紀錄取出、哪些由模型生成；「模型加的數字標成未驗證」怎麼實作？
5. 清空與接手：怎麼執行 `/clear`、怎麼把第一句訊息送進新段落？新段落是同一個 session id 還是新的？
6. 在 Claude Code 桌面版、Claude Agent SDK（例如 T3 Code）裡能不能跑？哪些部分只能在 CLI 跑？
7. Windows 上哪些部分會壞（POSIX shell、jq、Tailscale 檢視頁），怎麼替代？
8. 失敗模式：Haiku 失敗、使用者正在輸入、子 agent 執行中、兩個門檻接連觸發時，各會怎樣？

### B. Continuous-Claude-v3 的運作原理

1. 畫出元件圖：hooks（列出每個 hook 事件與腳本）、skills、agents、PostgreSQL 四個表、背景 daemon，各自負責什麼。
2. continuity ledger 與 handoff 的差別：檔案位置、格式（YAML 或 Markdown，以程式碼為準）、欄位、誰寫、何時寫、何時讀。
3. 跨 session 的狀態怎麼追：sessions 表的 heartbeat、file_claims 檔案鎖、stale session 判定；哪些功能**必須**有 PostgreSQL，哪些只靠檔案就能運作？
4. PreCompact 自動交接與 SessionStart 載入的實作細節（附程式碼位置）。
5. 拿掉 PostgreSQL、Docker、daemon 之後，「最小可用核心」是哪幾個檔案？估計行數。
6. 它有沒有解決 P1（不用問就知道每個對話的狀態）？如果有，怎麼呈現給使用者？
7. 對 Windows、Codex、Antigravity 的支援狀況。

### C. 移植到 Codex 與 Antigravity 的可行性

1. Codex：列出目前 hook 事件（我查到有 SessionStart、UserPromptSubmit、PreToolUse、PostToolUse、PermissionRequest、PreCompact、PostCompact、Stop、SubagentStart、SubagentStop，請以官方文件確認）；hook 能不能阻擋、注入上下文、結束或清空對話；hooks 在 Windows 上目前能不能用（有文章說暫時停用）；`experimental_compact_prompt_file`／`compact_prompt` 能不能讓自動壓縮直接產出交接格式；`model_auto_compact_token_limit` 的實際上限與預設值。
2. Antigravity（IDE 與 CLI）：hooks 的設定檔位置（`~/.gemini/config/hooks.json`、`.agents/hooks.json` 等，以官方為準）、事件清單、payload 欄位、能不能阻擋或注入；它有沒有自動壓縮、能不能自訂壓縮內容、能不能程式化開新對話。
3. 對每個 agent 給出可行的「自動交接」做法，分兩級：
   - 最低限度：到門檻時寫交接檔到磁碟，新對話開始時自動讀入。
   - 完整版：到門檻時自動清空或開新對話並接手（像 claude-auto-handoff）。
   標明每一級是否可行、靠哪個介面、有什麼限制。

### D. 跨裝置與跨 agent 的狀態存放

1. 兩個專案的交接檔與狀態存在哪裡？能不能跨裝置？
2. 比較這幾種存放方式在「多台電腦、公開 repo、三個 agent 都要讀」條件下的優缺點：私人 GitHub repo 當狀態中心、專案 repo 內 commit、專案 repo 的專用分支、雲端同步資料夾、Claude Code 原生 Tasks（`~/.claude/tasks`、`CLAUDE_CODE_TASK_LIST_ID`）、beads（git 帳本）。
3. 多台電腦同時寫同一份狀態時，怎麼避免衝突？

## 交付格式

1. **一頁結論**：兩個專案各值得借用的 3 個設計、不要學的 3 個設計；我該自己做的最小版本長什麼樣。
2. **A、B、C、D 各節的回答**，每個結論附證據與「已驗證／推論／未知」標記。
3. **移植可行性表**：列 = Claude Code 桌面版、Claude Agent SDK（T3）、Codex、Antigravity；欄 = 門檻偵測、寫交接檔、新對話自動讀入、自動清空接手、Windows 可用；格子填「可行／有限制／不可行／未知」加一句理由。
4. **建議的交接檔格式**（欄位清單與範例），要能同時給三個 agent 用。
5. **風險清單**：實驗性 API、版本相依、Windows、安全（會不會讀到金鑰、會不會把對話內容送到第三方服務）。
6. **參考來源**：所有用到的網址與 repo SHA。
