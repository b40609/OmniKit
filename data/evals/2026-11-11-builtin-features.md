# 內建功能盤點（原本的 10 張內建卡）

日期：2026-11-11。這份是搬家紀錄，不是實測。

名冊原本用 10 張「內建卡」（`data/tools/native-*.yaml`）記 Claude Code 與 Codex 的內建功能，當成各槽位的比較基準。
2026-11-11 起，內建功能改記在槽位的答案裡（模組檔的 `answers`，Claude Code 與 Codex 分開），這 10 張卡刪除。
卡片上的說明比答案裡的一句話詳細，原文留在這裡；之後盤點到新的內建功能，改槽位的答案，這份不再更新。

- 除了瀏覽器，其他都還沒實測內建的夠不夠；卡片當時的理由都是「還沒有第三方預設，先用原生功能當比較基準」。
- 瀏覽器的實測在 [2026-11-04-browser-u1.md](2026-11-04-browser-u1.md)。
- 評估漏斗在這之前產生的結果檔（`data/funnel/`）還是用舊的卡片 id，例如 `native-search`；對照下表就知道是哪個槽位。

| 舊的卡片 id | 槽位 | 當時的狀態 | 支援 | 加入日期 |
|---|---|---|---|---|
| `native-browser` | 瀏覽器操作與驗證（`browser`） | 預設（比較基準） | Claude Code、Codex | 2026-11-04 |
| `native-concise` | 輸出精簡（`concise-output`） | 預設（比較基準） | Claude Code、Codex | 2026-11-04 |
| `native-data` | 探索分析與 notebook（`data-analysis`） | 預設（比較基準） | Claude Code、Codex | 2026-11-05 |
| `native-docs` | Word 文件與報告（`docs-output`） | 預設（比較基準） | Claude Code、Codex | 2026-11-04 |
| `native-memory` | 記憶與交接（`memory`） | 預設（比較基準） | Claude Code、Codex | 2026-11-04 |
| `native-permissions` | 權限與通知（`permissions`） | 預設（比較基準） | Claude Code、Codex | 2026-11-04 |
| `native-review` | 審查與驗收（`review`） | 預設（比較基準） | Claude Code、Codex | 2026-11-04 |
| `native-search` | 程式碼理解與搜尋（`code-understanding`） | 預設（比較基準） | Claude Code、Codex | 2026-11-04 |
| `native-sessions` | 工作階段管理（`session-management`） | 預設（比較基準） | Claude Code | 2026-11-09 |
| `native-workflow` | 規劃與開發流程（`dev-workflow`） | 待評估 | Claude Code、Codex | 2026-11-04 |

## 原生瀏覽器（`native-browser`）

槽位：瀏覽器操作與驗證。

Claude Code 桌面版內建 Browser 面板：自己開 dev server、截圖、看 DOM、點擊與填表，改完檔案預設會自動驗證；用乾淨的設定檔，沒有你的登入。要用已登入的網站時改用 Claude in Chrome（CLI 加 --chrome）。Codex app 內建 browser plugin（in-app browser，給 localhost 用，前端大改後會自己打開）與 chrome plugin（用你的 Chrome 登入狀態，瀏覽資料可能依 OpenAI 帳號的資料設定用於訓練）；這台筆電與另一台桌機的 plugin 快取都有。U1 實測（2026-11-04）：Claude 桌面版 Browser 面板拿 4 分；Codex 內建瀏覽器在 codex exec 回報 browser access host is unavailable，只能在 app 裡互動使用（app 內沒測）。

## 原生精簡輸出（`native-concise`）

槽位：輸出精簡。

Claude Code 的 Concise 輸出風格；Codex 的 model_verbosity。

## 原生資料分析（`native-data`）

槽位：探索分析與 notebook。

Claude Code 內建 NotebookEdit，可以逐個 cell 改 .ipynb，再用 shell 跑 python 或 jupyter nbconvert 重跑；Codex 沒有 notebook 專用工具，靠 shell 跑 python 與改檔。兩邊都看不到正在跑的 kernel 狀態。

## 原生文件產出（`native-docs`）

槽位：Word 文件與報告。

Claude 的 docx、pptx、xlsx、pdf skills；Codex 的 documents、presentations、spreadsheets、pdf plugin。

## 原生記憶（`native-memory`）

槽位：記憶與交接。

Claude 的 auto memory（預設開）；Codex 的 memories（預設關）；兩邊不互通。

## 原生權限與通知（`native-permissions`）

槽位：權限與通知。

Claude Code 的權限 allowlist、auto mode 與通知；Codex 的 sandbox、核准政策與 notify。

## 原生審查（`native-review`）

槽位：審查與驗收。

Claude Code 的 /code-review、/security-review；Codex 的 /review。

## 原生搜尋（`native-search`）

槽位：程式碼理解與搜尋。

agent 內建的 grep、glob 搜尋。

## 原生工作階段管理（`native-sessions`）

槽位：工作階段管理。

Claude 桌面版：側邊欄群組、封存（可從 Archived 分頁還原）、「PR 合併或關閉後自動封存」、完成時的系統通知、Remote Control（手機看與回覆）、side chat（/btw）、Context 卡片顯示上下文百分比。Claude 能列出、改名、封存其他桌面版 session，也能開子 session 並交接；看不到 CLI、VS Code、雲端開的 session。CLI：/rename、/clear <名稱>、claude --resume <名稱>，以及 Agent View（claude agents，研究預覽，只列背景 session）。風險：桌面版封存時 worktree 未 commit 的修改可能遺失，worktree 在封存約 30 天後刪除；Agent View 刪除 session 會連 worktree 的未 commit 修改一起刪，claude rm 才會保留。2026-11-09 盤點：桌面版 22 個 session，封存 13 個，封存前用 git 確認 worktree 乾淨、分支已併入；封存父 session 時，已完成的子 session 會被連帶封存（實際發生一次，已還原）。Codex 端的原生功能還沒盤點。

## 原生開發流程（`native-workflow`）

槽位：規劃與開發流程。

比較基準：不裝方法論，只用 Claude Code 與 Codex 內建的 plan mode、/goal 等。
