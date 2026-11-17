---
type: llm
weight: 2
---

需涵蓋以下 4 項事實：1. Claude Code 用 /output-style concise 或設定檔 "outputStyle": "Concise"；2. Codex 用設定檔的 model_verbosity（low、medium、high）；3. Antigravity 的 verbosity 只管畫面顯示多少過程、不一定縮短回覆本身，要改為在規則檔寫精簡回覆的要求；4. 精簡輸出主要是為了好讀，回覆文字只佔用量一小部分、省不了多少額度。答對其中 3 項以上、而且沒有說錯任何一家的指令或設定就 PASS；說錯指令、把 Antigravity 說成有 /output-style 或誤稱 Antigravity 的 verbosity 就是縮短回覆長度、或對沒把握的指令說得很肯定，算 FAIL。

判分依據（features.md 原文）：

### 回覆太長：精簡的輸出風格
- 做什麼：先講結果，不寫開場、過程旁白、結尾回顧。工作本身一樣仔細。
- 怎麼用：Claude Code `/output-style concise`，或設定檔 `"outputStyle": "Concise"`。Codex：設定檔的 `model_verbosity`（low、medium、high）。Antigravity 的 `verbosity` 設定管的是畫面顯示多少過程，不一定縮短回覆本身。其他：在規則檔寫一句「回覆先講結論，不要開場與回顧」。
- 注意：這是為了好讀。回覆文字只佔用量的一小部分，省不了多少額度。
| 回覆太長 | `/output-style concise` | `model_verbosity` | 規則檔寫一句（`verbosity` 只管畫面） | 規則檔寫一句 |
