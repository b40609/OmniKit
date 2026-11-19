# OmniKeep 官網首頁：替你做的決定

日期：2026-11-19。這次沒有人能回答問題，huashu-design 要求「先問使用者」或「讓使用者挑方向」的地方，都照簡報自己決定，列在下面。

## 怎麼看
在 `site/` 執行 `python -m http.server`，打開 http://127.0.0.1:8000/ 。不需要建置。

## 檔案
- `index.html`、`assets/css/style.css`、`assets/js/main.js`、`assets/img/mark.svg`：網站本身。
- `assets/img/screens/*.webp`：OmniKeep 實際執行的截圖（來源見 `CREDITS.md`）。
- `design/`、`polish/`、`polish-log.md`：設計過程的文件與打磨截圖，不是網站內容，上線時可以不部署。第一版的檔案備份在 `design/v1/`。

## 版本
- **第一版**：淺冷灰、以 Things 官網為參照，產品畫面用 HTML 畫的示意畫面。
- **第二版**（使用者回饋：「我偏好深色 iOS 官網風格，參考 apple.com.cn/iphone-18-pro」、「大部分螢幕都是 1080x1920」）：改成深色、Apple 產品頁的節奏；桌機以 1920×1080 驗收，手機 390 寬。
- **第二版＋真實截圖**（Ryan：不要示意畫面，也不要 agent 自己挑的示範內容，用他挑的 15 則收藏的實際 App 截圖）：頁面上所有示意畫面都換成 `C:\Users\user\.omnikit-wp1-demo\screens\` 的 11 張截圖，「示意畫面」的標註全部拿掉。

## 替你做的決定
1. **方向**：六個候選畫成縮圖（`design/v2/thumbs.png`），完整版選「參照 iPhone 18 Pro 頁」：黑與深灰交替、「先看重點」橫向卡片列、置中大標＋產品從下方升起；「怎麼運作」借 iOS 頁的膠囊分頁。理由在 `design/v2/direction-approved.md`。
2. **首屏改成置中大標＋收件匣截圖**：原本首屏的主角是一支畫出來的手機（Telegram 對話）。這批截圖裡沒有 Telegram 的畫面，所以首屏改成 Apple 頁另一種常見的排法：上面置中的產品名、主標、兩顆按鈕，下面是收件匣的實際畫面從底部升起。1920×1080 的第一屏看得到主標和前兩列收藏卡片（Claude 個人理財、Claude App 更新、mattpocock/skills、OmniKeep、CatOS…）。
3. **Telegram 只用文字講**：README 說主要入口是 Telegram，所以文案保留「在 Telegram 把連結丟給自己的機器人」；但沒有真實的 Telegram 截圖，就不再畫假的對話。「丟連結」那一步改用 App 的「新增」面板截圖（README 列出的另一個收錄管道），說明寫成「傳給 Telegram 的機器人，或在網頁按『新增』貼上」。**之後有真實的 Telegram 截圖，建議補回首屏或第一張卡。**
4. **截圖怎麼用**：
   - 首屏：`01-inbox-grid`（收件匣格狀）。
   - 先看重點四張卡：`11-add-link`（新增面板）、`04-detail-youtube`（影片讀成摘要）、`05-detail-youtube-analysis`（最重要的 3 件事、關聯）、`10-ask-answer`（提問附引用），各裁一塊；第五張「資料在你的電腦上」保留標誌＋`127.0.0.1` 的圖形（不是介面示意，沒有對應的截圖）。
   - 怎麼運作三個分頁：`11-add-link` → `04-detail-youtube` → `10-ask-answer` 整張放在視窗框裡切換。視窗標題列只寫「OmniKeep」，不寫網址：截圖是在隔離的示範版拍的，不是 README 預設的 `127.0.0.1:5000`。
   - 功能區「找得到」：原本可以打字玩的子字串搜尋示意（內容是編的備份句子）拿掉，換成 `08-search-suggest`（搜尋框下拉的「搜尋／提問」）與 `09-search-results`（搜尋「Claude Code」10 則結果）。
   - 沒用到的：`02-inbox-grid-more`、`03-filter-video`、`06-detail-github`、`07-detail-x-post`（版面放不下，或和已用的重複）。
5. **手機版裁切**：截圖都是 1920×1080 桌機畫面，手機上縮到整張會看不清楚。首屏改 3:4 裁、對準前兩欄卡片；「怎麼運作」視窗改 4:5 裁、對準面板或內文欄。
6. **頁尾聲明**：從「頁面上的介面與收藏內容為示意畫面」改成「頁面上的畫面是 OmniKeep 實際執行的截圖」。
7. **截圖裡的第三方縮圖**：收藏卡片的封面（YouTube 縮圖、GitHub 預覽圖、OpenRouter、claude.com 等）是 App 照原網站顯示的，照原樣保留，沒有另外修圖。示範版的「幾分鐘前」時間是拍攝前調過順序造成的（見截圖資料夾的 README），也照原樣。
8. **品牌與 logo 新做**（第一版定的，沒變）：深墨方塊＋白色書籤＋一道黃色標亮。App 自己（截圖左上）用的是藍底書籤圖示，和官網的標誌不同；**要不要統一，需要你決定**。
9. **文案與事實**：功能、安裝、限制都對回 `content/README.md`；兩行安裝指令照 README 原文。沒有任何編造的數字、評價、合作夥伴或媒體 logo。
10. **沒做的**：淺色模式、英文版、Tweaks 調整面板。

## 驗證（2026-11-19，實際跑過）
- `python -m http.server 18802` 背景啟動，Playwright 打開 http://127.0.0.1:18802/ ，1920×1080 與 390×844 都：console 沒有錯誤或警告、沒有失敗的請求、`scrollWidth` 等於視窗寬（1920／390，沒有橫向捲動）、13 張圖全部載入（naturalWidth > 0）；「怎麼運作」三個分頁都點過並截圖。檢查完伺服器已關閉。
- 打磨環這一版跑到第 4 輪（`polish-log.md`、`polish/index/round-1` 到 `round-4`）；首屏第 1 輪與最後一輪對照：`polish/v2-hero-round1-vs-final.png`。
- 逐屏截圖腳本不觸發捲動事件，所以截圖裡「怎麼運作」的視窗停在升起前、功能區兩張搜尋圖是空框；用 Playwright 真的捲過去量，視窗與說明相距 60px（手機 40px），兩張圖都正常顯示。
- `design_lint.py check`：紅燈 0。剩下的黃燈是「相對路徑圖片」（簡報要多檔靜態站）、「等寬小字」（指令與網址）、「標題字是 -apple-system」（刻意跟 Apple 頁一致，Mac 上是 SF／蘋方，其他平台退到 Geist／Noto Sans TC）。

## 環境備註
- huashu-design 的截圖腳本需要 Python 版 playwright：裝在 session 暫存資料夾的 venv 裡，瀏覽器也下載到那裡，沒有裝全域套件。
- 外觀帳本與經驗紀錄照 skill 預設要寫到 `~/.huashu-design/`；簡報不准改 `site/` 以外的檔案，所以寫在 `design/huashu-home/`。
