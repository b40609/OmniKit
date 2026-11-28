---
name: omnikit-mobile-web
description: 改前端（CSS、Vue、React、HTML）、手機版網頁、獨立 PWA 或包成桌面 App 的 WebApp（Tauri、Electron、WebView2）時必讀的工程底線與交付前 WebKit 行動端巡檢規範。非前端工作不觸發。Mobile Safari/WebKit and WebApp engineering baseline.
---

# 行動端與 WebApp 工程底線

只在改前端（CSS、Vue、React、HTML）、手機版、PWA 或包成桌面 App 的 WebApp 時適用；其他工作略過這份。來源：OmniKeep 在 iOS Safari／WebKit 反覆踩到的雷（2026-11-24 調研）。專案規則另有規定時照專案。

## 版面與觸控底線

- **高度**：不用 `100vh`，改 `100dvh` 或外層殼 `fixed inset-0`。不用 `background-attachment: fixed`。
- **渲染與捲動效能**：捲動卡片不掛 `content-visibility: auto`；觸控裝置（`@media (hover: none)`）不在大量圖卡上掛 CSS `filter` 動畫。
- **全頁垂直捲動區**：帶 `overscroll-behavior: contain; touch-action: pan-y; -webkit-overflow-scrolling: touch`。
- **觸控手勢**：`@touchstart` 一律 `.passive`（JS 用 `{ passive: true }`）；水平滑動手勢要 `dx >= 12px` 且 `|dx| > |dy| * 1.5` 才攔截。
- **防止 iOS 自動放大**：手機（`< 768px`）的輸入框字級在 `@layer` 之外強制 `>= 16px`，避免 `.text-sm` 之類蓋掉後 iOS 自動放大。
- **iOS 獨立 PWA 狀態列**：不用 `black-translucent`；頂部統一吃 `--safe-top`，在 `@supports (-webkit-touch-callout: none)` 加 `@media (display-mode: standalone)` 裡補純色緩衝，避開 iOS 26／27 的系統漸層模糊帶。

## 互動彈出層選型與三坑（2026-11-28 補強）

- **依打擾程度選對元件**：
  - `Tooltip`：補充說明（手機無 hover，關鍵資訊不可只藏在裡面）。
  - `Toast`：2 秒自動消失，只報操作結果、不放按鈕、文案簡短。
  - `Alert`：頂部橫幅提醒但不攔截操作；避免同時掛超過兩條。
  - `Popconfirm`：貼在觸發按鈕旁的輕量確認，適合高頻後台操作。
  - `Drawer`：側滑面板，適合需對照底層清單的檢視或長表單編輯。
  - `Modal`：全頁攔截，只用於不可逆刪除、付款、未存檔離開等高風險動作。
- **三個必避的 UX 坑**：
  1. 填寫表單的彈窗／抽屜禁止點暗幕背景直接關閉（防誤觸掉資料）。
  2. 能「撤銷（Undo）」的動作不跳二次確認弹窗。
  3. 確認按鈕寫具體動作（如「刪除專案」「繼續編輯」），禁止只寫「是／否」。

## 風格對齊與 5 值量化驗收（Refero 參考法）

- 做 UI 前優先鎖定專案的 `DESIGN.md` 或明確設計規格，不用「像某品牌」等模糊口號。
- 交付驗收時對照 **5 個具體數值**（主色色碼、字體與字級、間距基準、圓角半徑、陰影或 1px 外框），不符即改；外部網站風格規則檔僅作參數參考，嚴禁複製品牌圖片、標誌或受版權保護資產。

## 交付前驗證與確定性工具

- **行動端實機／WebKit 巡檢**：交付前跑真的 Playwright `webkit` 行動端巡檢（例如 `playwright-cli --browser=webkit --device="iPhone 15"`），確認三項指標：
  1. 橫向溢位 = 0
  2. 捲動往前不鎖死
  3. 輸入框字級 `>= 16px`
  沒跑就照安全底線〈誠實回報〉寫明沒跑。
- **確定性檢查優先**：能寫成規則的用確定性工具擋（stylelint 禁用值、ast-grep 規則、axe-core 開 `wcag22aa` 並補 44×44px 觸控目標檢查），不要只靠文字提醒；工具卡在 `data/tools/`，槽位 `static-guardrails`、`mobile-web-verify`。
