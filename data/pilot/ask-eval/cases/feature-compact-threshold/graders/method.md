---
type: llm
weight: 2
---

需涵蓋以下 4 項事實：1. Claude Code 用 /compact 手動壓縮（可指定保留重點），用 /autocompact 或使用者設定檔的 autoCompactWindow 設定自動壓縮門檻（1M 模型未設時約 967k 才壓縮）；2. Codex 在設定檔透過 model_auto_compact_token_limit 設定門檻；3. Antigravity 會自動壓縮，手動 /compact 屬於待驗證狀態（在 changelog 有但 CLI 指令表未列），且門檻查不到；4. Gemini CLI 用 /compress 手動壓縮，門檻是設定檔的 model.compressionThreshold（0 到 1 的比例，預設 0.5）。答對其中 3 項以上、而且沒有說錯任何一家的指令或設定鍵名就 PASS；說錯指令、把 Antigravity 查不到門檻或待驗證的 /compact 講成確定支援、或對沒把握的指令說得很肯定，算 FAIL。

判分依據（features.md 原文）：

### 同一件事做很久：壓縮，並設自動壓縮的門檻
- 做什麼：把前面的對話換成摘要。
- 什麼時候用：同一件事還沒做完，但對話已經很長。
- 怎麼用：Claude Code `/compact 保留〔要留的重點〕`；設門檻 `/autocompact 400k` 或在使用者設定檔寫 `"autoCompactWindow": 400000`（沒設的話，1M 的模型要到約 967k 才壓縮）。Codex：設定檔的 `model_auto_compact_token_limit`。Antigravity：會自動壓縮，手動用 `/compact`（門檻查不到；`/compact` 在 changelog 有、CLI 指令表沒列，用之前先試）。Gemini CLI `/compress`，門檻是設定檔的 `model.compressionThreshold`（0 到 1 的比例，預設 0.5）。
- 取捨：門檻越低越省，但壓縮次數越多，每次都會掉細節。
