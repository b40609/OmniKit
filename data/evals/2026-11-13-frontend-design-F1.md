# 前端設計槽位實測：F1 第二次（2026-11-13）

起因是自我迭代的訊號：OmniKeep 收錄的 Taste Skill（`omnikeep:f20d9b5a7ee8`）與 unslop（`omnikeep:3c5fcdbfe765`），第 1 層都建議深入評估。第一次 F1 的紀錄見 `2026-11-04-frontend-design-F1.md`。

## 要回答的問題

在不改變 CatOS 既定視覺方向的前提下，taste-skill 或 unslop 打磨儀表板，會不會比現任的 frontend-design 做得更好，值得進兩週試用？

## 決策規則（實測前寫下）

沿用第一次 F1 的規則，只改組數：

1. **硬性條件**（任一不過，該組出局）：功能、導航項目、面板都還在；沒有新增 console 錯誤；`npm run typecheck` 通過；程式碼只改 `src/`（skill 需要的設計說明文件可以放 `docs/`）；仍是黑金、緊湊的方向。
2. **主要依據：使用者盲選。** 原版與三組各開一個 port，隨機標成 X、Y、Z，對照表選完才公開。使用者實際操作後選最好的一組，或回答「都沒比原版好」。
3. **次要依據：Gemini 評審。** 只看方向文件、截圖與 diff，不知道各組是哪個工具；使用者選完才公開，不推翻使用者的選擇。
4. **判定：**
   - 選了 taste-skill 或 unslop 的那組，且硬性條件都過：Update，進兩週試用，frontend-design 維持預設到試用結束。
   - 選了 frontend-design：Keep，另外兩個記為拒絕並附這次的結果。
   - 「都沒比原版好」：Keep，三個都沒解決 F1，挑戰者維持待評估。
5. **平手：** 照第一次 F1 補的規則，截下喜歡的部分投票，至少 2 票而且是另一組的兩倍以上才算選了那組，否則 Keep。

## 設定

- **測試對象：** CatOS 目前 main（`C:\dev\CatOS`，`d719103f`）的前端 `frontend/cat-os-vite`，每組一份副本，原本的工作目錄不動。
  - 第一次 F1 的基準 commit `9fef976` 已經不在 CatOS repo 裡（歷史改寫過），F1 的 patch 也套不上 11/4 的前端，所以用目前的版本。
  - 假後端沿用第一次 F1 的 `mock-server.mjs`（第二輪的資料：4 個 SMA 實例、152 筆事件、權益曲線、風控快照）。2026-11-13 確認目前的前端接上去畫面有資料、沒有 console 錯誤。
- **方向文件：** 沿用第一次 F1 的 `design-direction.md`，放進每份副本的 `docs/`。
- **各組只差 skill**，放在副本的 `.agents/skills/<名稱>/`，提示要求先讀它的 SKILL.md：
  - frontend-design：anthropics/skills `2c5958e` 的 `skills/frontend-design`（現任）。
  - taste-skill：Leonxlnx/taste-skill `f6b7657` 的 `skills/taste-skill`（它的說明以公司官網、形象頁為主）。
  - unslop：heydamir/unslop `97daa3e` 的 `skills/unslop`。
- **執行：** T3 子對話，`retis` 的 Claude 帳號（provider `claudeAgent_2`），模型 Claude Opus 5.5。三組用同一個提示，依序跑，每組前後讀一次 `retis` 的 `/usage`。
  - 原本想用 agy 的 Claude；校準發現它一週大約只有 500 萬 token，前端一組就要幾百萬，所以改用 `retis`。
  - 只跑 1 次：這是品味題，最後由使用者決定，9 個版本讓使用者看負擔太大。
- **評審：** Gemini 4 Hydrogen（T3 子對話），跟執行的 Claude 不同家族。

## 結果

原始資料在 `2026-11-13-frontend-design-F1/`：三組的 diff（`*.patch`）與執行紀錄（`*.json`）、四張 1440×900 截圖（`screenshots/`）、封存的對照表與評審（`mapping.sealed`、`judge.sealed`）、評審提示（`judge-prompt.md`）、執行腳本（`run.py`）。

### 硬性條件：三組都通過

| | X | Y | Z |
|---|---|---|---|
| 型別檢查、建置 | 通過 | 通過 | 通過 |
| console 錯誤（1440×900） | 沒有 | 沒有 | 沒有 |
| 只改 `src/`、`docs/` | 是（9 個檔，+483／−533） | 是（9 個檔，+266／−209） | 是（18 個檔，+427／−542） |
| 面板、導航都在 | 是 | 是 | 是 |

### 盲選（2026-11-13）

使用者實際操作四個版本後，選了**原版與 Y**。

使用者同時指出這次實驗有爭議：**原版是使用者自己調出來的半成品**，自然會給比較高的評價。這是所有權偏誤：拿任何工具的結果去比使用者親手做的東西，比較基準本身就不公平。所以這次的結果分兩部分看：

- **工具之間（X、Y、Z）：不受這個偏誤影響。** 三組都從同一份原版出發，使用者在三組裡選了 Y。
- **工具對原版：不採用。** 使用者選原版有一部分是因為那是自己的設計，判斷不了工具是不是真的比原版好。

### 對照（選完後解開）

`mapping.sealed` 解碼後的 SHA-256 是 `c231604f97a04a79293c54096228ec2d966ea1887240141dc65730ceedfdfb3f`，跟封存時一致。

- **X = frontend-design（現任）**
- **Y = taste-skill**
- **Z = unslop**

### Gemini 評審（選完後解開，只當參考）

`judge.sealed` 的 SHA-256 開頭 `c2919713`，跟封存時一致。Gemini 4 Hydrogen 只看方向文件、截圖與 diff，不知道各組是哪個工具：

- 兩兩比較：X 與 Y 平手，X 勝 Z，Y 勝 Z。排序 X＝Y＞Z；它認為不是三個都沒有比原版好。
- X（frontend-design）：最貼近方向文件（異常置頂、移除 run ID、金色總權益），但策略實例表格右側的「詳情」與第 4 列被裁切。
- Y（taste-skill）：策略實例 4 列與操作按鈕完整可見、事件可見列數最多，但沒做異常置頂、槓桿卡的徽章被截斷、「模擬」二字斷行。
- Z（unslop）：去掉光暈與多餘動畫，但策略實例的操作按鈕整欄被推出畫面、KPI 副標被截斷，方向文件的幾項要求沒落實。
- 跟使用者的選擇大致一致：Y 在前、Z 最後；差別在 Gemini 認為 X 跟 Y 一樣好。

### 判定：暫緩，等第二輪

照事先寫的規則，使用者選了 taste-skill 那組，應該是 Update。但使用者選的同時也選了原版，而工具對原版的比較已經判定不採用，所以這一輪只能說「taste-skill 在三組裡勝出」。考量到：

1. 使用者的偏誤是自己指出的，這個基準的問題不只影響原版，也可能影響什麼樣的改動看起來順眼（越接近自己原本的做法越容易被選）。
2. Gemini 評審認為 X、Y 平手，沒有明確支持 taste-skill 勝過現任。
3. taste-skill 與 unslop 自己的定位都是處理 AI 生成的介面，CatOS 這份原版不是那種介面，可能低估了它們。

所以 taste-skill 先不進試用，三張卡都維持現狀，用一份**完全由 AI 生成的前端**再測一輪，兩輪結果一致才判定。

### 額度消耗（retis 的 Claude，Opus 5.5）

依執行順序：frontend-design、taste-skill、unslop。

| 組 | 秒數 | 5 小時額度 | 週額度 |
|---|---|---|---|
| frontend-design | 612 | 0% → 9% | 27% → 28% |
| taste-skill | 630 | 10% → 19% | 29% → 30% |
| unslop | 664 | 19% → 29% | 30% → 32% |

T3 沒有回報 token 數，所以只有百分比。Opus 5.5 跑一組前端打磨，約扣 `retis` 5 小時額度的 10%、週額度的 1 到 2%。

### 過程中的疏失

- 第一次 F1 的基準 commit 已經不在 CatOS repo（歷史改寫過），只能改用目前的前端；兩次 F1 的結果不能直接比較。
- agy 與 T3 的 Claude 都會載入各自帳號的全域設定（`retis` 只有帳號同步的文件類 skill，沒有前端相關的），三組條件一樣，但不是完全乾淨的環境。
