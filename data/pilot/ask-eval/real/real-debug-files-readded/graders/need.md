---
type: llm
weight: 2
---

使用者後來推測是某個準備流程（ready 指令裡的 linter 或 formatter）造成，最後決定先手動修一次、再把所有文件裡壞掉的寫法修掉。PASS 如果回覆建議找出是哪個流程在重新產生或改寫這些檔案（例如看 git log／git blame、逐步執行建置或格式化流程、檢查 hook 與 formatter 設定），修正來源，並把壞掉的檔案一次修好。FAIL 如果回覆只建議再刪一次或加進 .gitignore。
