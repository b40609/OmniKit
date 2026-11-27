---
name: omnikit-verify
description: 防假完工真機驗收：在宣告完成前抓出假綠燈（.skip、吞錯）、斷頭引用，並用無 Mock 真實執行與真瀏覽器（桌機＋手機寬度、0 console/network 錯誤）走完使用者旅程。使用者說「驗收」「真機測試」「防假完工」「檢查有沒有壞」或打 /ok 驗收 時使用。Verifies real end-to-end user journeys and blocks fake-green premature completion.
---

# 防假完工真機驗收（omnikit-verify）

為什麼要有這步：AI 寫完程式最常犯的錯是「只跑離線假資料單測全綠就說做好了，使用者一打開畫面或一跑安裝就壞」。本技能把業界頂尖團隊（Anthropic、Stripe、gstack）的防假完工流程變成任何專案都能直接執行的 4 步實證檢查。

下面的腳本路徑在 `~/.omnikit/current/engine/scripts`（開發環境可用 repo 的 `engine/scripts`）；`uv` 不在 PATH 時用 `%LOCALAPPDATA%\Programs\uv\uv.exe`。

## 驗收四步（依序執行，不能跳步）

### 1. 機械掃雷（抓假綠燈作弊與斷頭引用）
對目前專案執行確定性稽核腳本：
```powershell
uv run ~/.omnikit/current/engine/scripts/wiring_audit.py --project "<目前專案絕對路徑>"
```
- 發現偷加 `.skip`／`xit`／`@pytest.mark.skip`、CI `|| true`、斷頭腳本或未解衝突標記時，**當場修好程式碼與測試**，嚴禁刪除測試混過去。

### 2. 真實無 Mock 啟動（Walking Skeleton）
- **後端／API／CLI／安裝腳本**：在真實環境（或乾淨暫存目錄，不用 `-WhatIf` 乾跑代替）實際啟動服務或執行完整指令，確認結束碼為 0、健康檢查回應正常、無未捕獲例外。
- **刪舊功能時**：搜尋全專案文件、設定檔與 UI 是否還殘留舊名稱、舊參數或舊連結。

### 3. 前端與畫面真瀏覽器巡檢（有網頁／UI 時必跑）
使用已掛載的瀏覽器工具（如 `chrome_devtools` MCP 或 Playwright）實際打開剛啟動的本機網址，逐一確認：
1. **零隱藏報錯**：Console `error` 數量 = 0、Network 回應 `>= 400` 數量 = 0。
2. **真的點過一次核心流程**：以「第一次打開的新用戶」視角完成主要操作（不只看首頁 HTML 字串存在）。
3. **手機寬度不破版**：切到行動端寬度（如 `390x844` iPhone 15），確認橫向溢位 = 0、捲動正常、輸入框字級 `>= 16px`。

### 4. 獨立挑刺與附上完工回執
- 若環境支援子代理且屬於大改動，派一個**沒看過剛才寫碼過程的唯讀子代理**，只拿 `README.md` 與啟動好的畫面走一遍前 3 分鐘流程挑錯。
- 最後回覆附上真實執行的**完工回執**（`done_check.py` 會做機械核驗）：

```markdown
## 完工回執
| 需求項 | 驗證層級 | 驗證指令或觀察 | 結果 | 證據位置 |
|---|---|---|---|---|
| 機械防假綠燈掃描 | 靜態 | wiring_audit.py --project . | 0 異常 | 本回合工具輸出 |
| 核心流程真實執行 | 實跑觀察 | 實際啟動並操作完整路徑 | 通過（附關鍵結果） | 本回合工具輸出或截圖路徑 |
沒驗的範圍：…（沒有就寫「無」）
```
