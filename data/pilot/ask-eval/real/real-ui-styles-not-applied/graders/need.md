---
type: llm
weight: 2
---

使用者要的是找出樣式為什麼沒生效（連 inline !important 都無效，代表很可能改到的不是畫面上那個元素，或元素被別的東西蓋住、在 shadow DOM 或 iframe 裡）。PASS 如果回覆建議用瀏覽器的開發者工具或截圖檢查實際渲染的元素與 computed style，確認選取器有沒有對到、樣式檔有沒有載入，而不是繼續改 CSS。FAIL 如果回覆只建議清快取、重 build 或加更多 !important。
