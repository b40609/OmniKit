# 圖片與素材來源

## 產品畫面（media/）

`media/` 裡的每一張圖都是 OmniKeep 的真實畫面，沒有任何一張是模擬圖或示意圖。

- **來源**：隔離的 OmniKeep 1.5.0 示範版，跑在 127.0.0.1:5055。
  - 用的是示範版自己的 demo.db 與設定。
  - 收藏是 Ryan 指定的 15 則連結，全部由 App 實際讀完、寫好摘要。
- **原圖**：`C:\Users\user\.omnikit-wp1-demo\screens\` 的 1920×1080 截圖，OLED 深色主題，2026-11-19 拍攝。每張原圖的說明在同資料夾的 README.md。
- **處理方式**：只做裁切與縮放，用 PIL 轉成 WebP，沒有修改畫面內容。

| 檔案 | 裁自 |
|---|---|
| inbox.webp、inbox-960.webp | 01-inbox-grid.png |
| step-add*.webp | 11-add-link.png |
| step-read*.webp、detail*.webp | 04-detail-youtube.png |
| step-find*.webp | 08-search-suggest.png |
| videos*.webp | 03-filter-video.png |
| xpost*.webp | 07-detail-x-post.png |
| search-results*.webp | 09-search-results.png |
| ask*.webp | 10-ask-answer.png |

畫面裡出現的封面圖、標題與網站名稱，屬於各自的原作者，例如 YouTube 影片、GitHub 專案與 X 貼文的作者。它們會出現在這裡，只是因為那是 App 收藏後的原樣。

- `share.jpg`：分享預覽圖，由本頁英雄區在 1440 寬的截圖縮裁而成。

## 標誌

- `ok-icon.svg` 是 OmniKeep 的應用程式圖示。
  - 從 OmniKeep repo 的 `static/dist/favicon.svg` 原樣複製，repo 採 MIT 授權。
  - 圖示內的圖形是 Lucide 的 brain-circuit，Lucide 採 ISC 授權。

## 第三方服務圖示（assets/icons/）

這些圖示由 taste-skill 隨附，詳細紀錄在 `assets/icons/icons-credits.json`。

| 圖示 | 來源 | 授權 |
|---|---|---|
| telegram、apple、claude-code、sqlite、google-drive、dropbox、aws-s3、github | gilbarbara/logos（Gil Barbara） | CC0-1.0 |
| line | simple-icons 16.30.0（Simple Icons Collaborators） | CC0-1.0 |

圖示的授權是 CC0，但各標誌仍是其所有者的商標。頁尾已註明「第三方名稱與標誌為各自所有者的商標」。

## 字型

字型都經由 Google Fonts 載入，三者皆採 SIL Open Font License 1.1。

- Geist、Geist Mono：Vercel。
- Noto Sans TC：Google，只載入本頁用到的字。

## 程式與樣式

- `assets/` 的 system.css、motion、layout、moments（liquid-type、marquee-row）來自專案內的 `.agents/skills/taste-skill`。
- `page.js` 是複製按鈕的程式，沿用 v1。
