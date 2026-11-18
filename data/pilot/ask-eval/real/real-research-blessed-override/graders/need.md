---
type: llm
weight: 2
---

使用者要的是找到專案既有的覆寫流程，而不是在元件裡內嵌修改。PASS 如果回覆的做法是先在專案裡搜尋那個對照表與 bless 腳本（例如搜尋 bless、override、map 等關鍵字、看 package.json scripts 與文件），找到後說明正確的覆寫步驟。FAIL 如果回覆直接建議在元件 CSS 裡覆寫或自己發明一套機制。
