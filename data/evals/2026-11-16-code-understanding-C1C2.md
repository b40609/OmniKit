# 第 2 層：程式碼理解（C1、C2）：內建 對 graphify 對 Floorplan

日期：2026-11-16。槽位：`code-understanding`（程式碼理解與搜尋）。點名的人：ryan（試點第 1 天，「拿掉 graphify」的建議被指出沒有證據）。

## 決策規則（動手前寫好）

**問題**：在 ryan 的兩個真實情境，裝了 graphify 或 Floorplan 的 Claude Code，答得比只用內建工具（Read、Grep、Glob、Bash）好嗎？

**會改變的決定**：
- graphify 勝出 → 卡片改 `trial`，這台留著；槽位答案記「graphify 對 C1 或 C2 有幫助」。
- graphify 沒勝出、而且有被用到 → 卡片 `rejected`（這兩個情境），之後「拿掉」的建議才有實測依據。
- graphify 沒被用到（一半以下的執行有查圖）→ 判「沒用到」，卡片維持 `pending`，不能據此叫人拿掉。
- Floorplan 同上。內建工具若兩題都不輸，槽位在 Claude 的答案改成 `native`（實測過）。

**情境**（`peers.py code-understanding`，ryan 的 profile）：
- C1：在 OmniKeep 找某個函式的所有呼叫者，以及改動的影響範圍。題目：`app/providers/__init__.py` 的 `get_provider`。
- C2：深讀第三方 repo，寫附行號的研究筆記。題目：pal-mcp-server 的 `clink` 從收到請求到回傳結果的完整流程。

repo 都從 GitHub clone 到暫存資料夾（OmniKeep `bd8b0c4`、pal-mcp-server `7afc7c1`），不動使用者本機的工作目錄。

**組別**（每組都在自己的 repo 副本裡跑，不載入使用者的規則、hook、plugin）：
- 內建：只有 Read、Grep、Glob、Bash。
- graphify：同上，加上 repo 內的 graphify skill 與事先建好的 `graphify-out/`（`graphify update`，只用 AST、不花 token）。
- Floorplan：同上，加上 repo 內的 Floorplan skill 與事先建好的 `floorplan/` 地圖（由 Hydrogen 照 Floorplan 的 SKILL.md 建）。

**執行**：Claude Sonnet 5.5（effort medium）`claude -p`，每組每題 3 次，共 18 次。執行模型用 Claude，因為要測的是 Claude Code 的 skill。

**評分**：
- C1（客觀，腳本算）：標準答案用 AST 與 `git grep` 先算好，不給執行者看。直接呼叫點 9 個（非測試），經 3 個包裝函式間接影響的檔案 6 個。分數 = 找到的直接呼叫點（行號差 2 行內算對）+ 找到的間接檔案；另記錯報數。
- C2（評審）：Gemini 4 Hydrogen xhigh（不同家族）兩兩比較，去掉組別、A、B 兩種順序各評一次，兩次一致才算一勝；內建對內建的組混在裡面當雜訊基準。另外用腳本檢查每個 `檔案:行號` 引用是否存在。
- 有沒有用到：從執行紀錄看有沒有呼叫 `graphify` 或 `floorplan` 的指令、讀 `graphify-out/`、`floorplan/`。

**判定**（全部成立才算挑戰者勝出）：
1. 一半以上的執行有用到它。
2. C1：平均分數高於內建，而且錯報不比內建多；或 C2：淨勝率（勝減負除以組數）大於雜訊率。
3. 引用存在率不低於內建。

花費另外記（token、秒數），不列入勝負，但寫進結論。

## 結果

### 有沒有被用到（自然使用：skill 在、圖或地圖也建好，題目不提工具）

| 組 | C1 | C2 |
|---|---|---|
| graphify | 0/3 | 0/3 |
| Floorplan | 0/3 | 0/3 |

開頭的 skill 清單有列出它們，模型自己選了 Grep、Read。照規則判「沒用到」。

### 補充組（事後加的，不在原本的決策規則裡）：題目明講「先用 graphify／Floorplan 查」

| 組 | 用到 | C1 分數 | C1 平均花費 | C2 引用存在率 | C2 平均花費 |
|---|---|---|---|---|---|
| 內建 | — | 15、15、15 | 0.091 美元 | 0.97、1.0、1.0 | 0.283 美元 |
| graphify 明講 | 3/3、3/3 | 15、15、15 | 0.182 美元 | 1.0、1.0、0.90 | 0.345 美元 |
| Floorplan 明講 | 3/3、3/3 | 15、12、15 | 0.083 美元 | 0.97、1.0、1.0 | 0.249 美元 |

C1 的 12 分不是找錯：每一份回答的正文都有 `providers/__init__.py` 第 105、122、126 行那 3 個包裝函式，只是最後的清單沒列進 DIRECT。自然使用的 graphify、Floorplan 兩組 6 次都是這樣（12 分），內建 3 次都列進去（15 分）；兩組工具其實跟內建一樣，差在 repo 裡多了 skill 與產物，原因沒查清楚，不當成工具的勝負。

### C2 盲評（Hydrogen xhigh，兩種順序一致才算一勝）

| 比較 | 勝 | 負 | 平 | 淨勝率 |
|---|---|---|---|---|
| 內建 對 內建（雜訊基準） | — | — | 1 | 分出勝負 2/3，雜訊率 0.67 |
| graphify 明講 對 內建 | 2 | 1 | 0 | 0.33 |
| Floorplan 明講 對 內建 | 1 | 1 | 1 | 0 |

評審抽查的引用錯誤（錯的處數／抽查處數）：graphify 明講 28/84、對應的內建 16/84；Floorplan 明講 16/78、對應的內建 22/78。差異主要來自少數幾份把 `clink/constants.py`、`clink/models.py` 的行號寫到超出檔案長度，各組都有。

### 判定

- graphify：**沒用到**（自然使用 0/6）。明講要用時 C1 一樣找齊但花費 2 倍，C2 淨勝 0.33 低於雜訊 0.67，不算勝出。卡片維持 `pending`（照事先寫的規則，沒用到不判拒絕），notes 記這次結果。
- Floorplan：**沒用到**（0/6）。明講要用時跟內建打平。它的強項是給人看的架構地圖，不是 agent 自己查程式碼，這次沒測那個用途。卡片維持 `pending`。
- 內建：兩題都不輸 → 槽位 `code-understanding` 在 Claude 的答案改成 `native`，附這份紀錄。之後「給我建議」裡，裝著卻一週以上沒用到的 graphify 會以「內建功能實測過夠用」列進拿掉，這次有證據了。

### 沒驗證到的部分與過程中的疏失

- 只測了 2 個情境、2 個中型 repo（各約 250 個 Python 檔）。大型 monorepo、跨語言、跨 repo 的呼叫關係沒測；graphify 的知識圖在那種規模可能比較有用。
- 執行模型只用 Sonnet 5.5 medium；Opus 或別的 agent（Codex）沒測。
- 雜訊基準只有 3 組，雜訊率 0.67 本身就不穩；挑戰者也只有 3 組。結論是「看不出比內建好」，不是「比內建差」。
- 補充組是看到「沒用到」之後才加的，不在事先寫的規則裡，只當參考。
- 抹除組別字樣後，挑戰者的回答留下 1 到 3 個「（工具）」字樣，評審可能看得出哪一份用了工具（不知道是哪個工具）。
- 計分腳本前兩版有錯（資料夾名稱含工具名被算成用到；短路徑 `registry.py:58` 被當成沒有這個檔；Floorplan 在 `floorplan/` 裡跑 `node query.mjs` 沒被認出），都修正後才定案。
- 評審 18 份裡有 2 份，在說明放進 agy 命令列參數時讓呼叫端靜默結束（結束碼 0、沒有輸出）；改成檔案指標後補完，其中 1 份的理由文字因背景工作的編碼毀損，只留數字與勝負。`dispatch.py agy` 已改成長說明一律寫成檔案。
- Floorplan 的地圖由 Hydrogen 照 SKILL.md 建（OmniKeep 7.6 分鐘、pal-mcp-server 5.4 分鐘），不是 Claude 建的；地圖品質沒有另外評。

- 執行沒有隔離 Claude Code 的設定資料夾：明講組叫用 graphify 的那幾次，更新了這台 `~/.claude.json` 的 skill 使用時間，OmniKit 的使用統計因此把 graphify 看成 2026-11-16 用過，30 天內不會列進「拿掉」。下次實測要用獨立的 `CLAUDE_CONFIG_DIR`（`smoke.py login` 那套）。

### 花費

Claude 執行 31 次（含 1 次不計分的試跑），合計 6.21 美元的等值用量（`claude -p` 回報的 total_cost_usd 加總）。Hydrogen：建地圖 2 次、評審 20 次（含 2 次重跑）。
