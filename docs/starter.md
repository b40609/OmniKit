# 起手清單：新電腦要設什麼、裝什麼、不用裝什麼

更新：2026-11-17。規則：**實測過的才進「值得裝」與「不用裝」**；沒測過的放最後一欄，不下結論。所以這份很短，短是故意的。

官方對 Claude Code 的說法是「your first plain prompt in a fresh session already does the right thing, without any setup on your part」。外面的「必裝清單」調研看了 6 份，沒有一份附整體成效的實測；交集最大的是三個習慣（短的規則檔、先規劃再動手、讓 agent 自己跑測試驗證），不是工具。

## 1. 人人都要的設定（不是工具）

| 設定 | 為什麼 | 怎麼設 |
|---|---|---|
| 安全底線與語言 | 刪除、對外發送、付款前先問；回覆用你要的語言 | 裝 OmniKit 後說「幫我設定 OmniKit」 |
| 每個專案的規則檔寫「做完要跑的檢查」 | agent 有辦法自己驗證，才不會說做完其實沒有 | 專案的 `CLAUDE.md` 或 `AGENTS.md` 寫上測試、型別檢查、lint 的指令 |
| 規則檔保持短 | 每一行每次都佔注意力；只寫它從程式碼看不出來的事 | Claude Code 可以用 `/doctor` 檢查 |
| 不能有例外的規則改成 hook 或權限設定 | 只用講的不保證 | Claude Code 的 hook 與權限規則；Codex 設定檔的 hooks |
| 精簡的輸出風格 | 回覆先講結果，比較好讀（省不了多少額度） | Claude Code：`"outputStyle": "Concise"`；Codex：`model_verbosity = "low"` |
| 自動壓縮的門檻 | 同一件事做很久時，用量不會越滾越大 | Claude Code：`"autoCompactWindow": 400000`（一台電腦 7 天紀錄的模擬：最多省約兩成）；Codex：`model_auto_compact_token_limit`，數值沒有資料 |
| 換任務就清掉對話 | 每次請求都重送整段對話；這是最大的省法，而且不花成本 | 習慣，不是設定：`/clear` 或開新對話 |

## 2. 實測過，值得裝

| 工具 | 什麼情況值得 | 實測 | 狀態 |
|---|---|---|---|
| Exa（搜尋） | 做調研、要找齊同類工具時。它找到網頁搜尋與 GitHub 都漏掉的 | `data/evals/2026-11-16-product-research-P2.md` | 試用到 2026-11-30 |
| unslop（前端設計 skill） | 做工具介面（不是行銷頁）時 | `data/evals/2026-11-14-frontend-design-F1c.md`；判定有弱點，紀錄裡寫了 | 試用中 |
| 瀏覽器工具（Codex、或 Claude Code 的非互動模式） | Codex 內建的瀏覽器在非互動模式不能用 | `data/evals/2026-11-04-browser-u1.md` | — |

## 3. 實測過，不用裝（內建就夠）

| 用途 | 結果 | 實測 |
|---|---|---|
| 瀏覽器操作（Claude Code 互動使用） | 內建拿滿分 | `data/evals/2026-11-04-browser-u1.md` |
| 找一手來源、抓網頁 | 裝了 firecrawl，6 次只被叫用 1 次 | `data/evals/2026-11-13-web-sources-WR1.md` |
| 程式碼理解（找呼叫者、影響範圍） | 內建兩題都不輸；graphify、Floorplan 裝著 6 次都沒被叫用 | `data/evals/2026-11-16-code-understanding-C1C2.md` |
| 精簡回覆（caveman 的回覆風格） | 內建的 Concise 做同一件事。caveman 自己的數字：比一句「Answer concisely.」只再短 3%；回覆文字只佔用量的一小部分 | 用的是 caveman 公開的數字與一台電腦的用量組成，不是 OmniKit 的對照實測 |

實測的範圍都很小（一兩個情境、中型的專案）。你的情況差很多時，結論可能不同。

## 4. 有人在用，還沒測

不下結論。要進第 2 或第 3 欄，各做一次有它與沒它的實測。

| 工具 | 現況 |
|---|---|
| claude-mem（跨對話記憶） | 維護者在用，hook 自動執行；它帶的二十幾個 skill 從沒被叫用、每回合都佔 context。有沒有幫助沒測過 |
| T3 Code（多家模型的桌面應用） | 維護者在用，試用中；只測過它會正確載入規則與 skill |
| taste-skill（行銷頁的設計） | 試用到 2026-11-28 |
| caveman 的「先壓縮 log 與測試輸出再給 agent 讀」 | 省的是輸入，作者自測整段對話少 33.2% |
| superpowers、mattpocock/skills 的 grill-me | 外面的清單最常推薦的兩個；跟 OmniKit 的問法庫是同一類東西 |
| 型別語言的 code intelligence plugin | 官方推薦：用「跳到定義」取代搜尋加讀檔 |

官方的另一個建議：能用 CLI 的就不要裝 MCP（`gh`、`aws`、`gcloud` 這類），agent 可以直接跑指令。

## 5. 已經被官方功能取代的

裝著這些的話，可以停用（先停用，不要刪；有問題再打開）。

| 原本用的 | 現在用官方的 |
|---|---|
| OmniKit 的週報與建議 | `/doctor`、`/skill-doctor`、`/usage`、`/insights` |
| 精簡回覆的 skill | Concise 輸出風格 |
| 為舊模型寫的提示詞補丁（要它一步一步想、叫它不要偷懶、全大寫強調） | 不需要；想得多深用 `/effort` |

各家的指令對照與「什麼情況用哪個」在 `engine/skills/omnikit-ask/features.md`。
