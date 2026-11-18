---
base: debug-env-diff
max_turns: 6
---
## 開場
這段上傳檔案的功能在我這台 Windows 筆電上跑完全正常，測試也都有過，但一推上 GitHub Actions 的 CI 就一直失敗（CI 的輸出我存在 ci.log）。我現在也不知道問題出在哪，該怎麼辦？

## 處境
你負責一個讓客戶上傳 CSV 匯入訂單的小功能。你在自己的 Windows 筆電跑測試全過，CI（Ubuntu）卻一直紅。你不太懂程式。

## 想要的結果
- CI 跟你自己的電腦都要過。
- 客戶從 Windows 或 Mac 上傳的 CSV 都要能正確匯入（欄位跟內容都對）。

## 細節
- CI 是 GitHub Actions，跑在 ubuntu-latest。
- 客戶有人用 Windows、有人用 Mac。
- 你沒改過 CI 設定，也不想為了讓 CI 綠而跳過測試。
