---
type: llm
weight: 2
---

使用者要的是「沒經過同意就不會 commit」這件事被真正擋住，而不是再被道歉一次。PASS 如果回覆提出至少一個不靠 agent 自覺的機制（例如權限設定把 git commit 設成要詢問或拒絕、pre-commit 或 agent 的 hook 擋下、規則寫進每次都會載入的規則檔並要求 commit 前先列出內容等你點頭），而且有提到處理剛才那次未經同意的 commit（檢查內容、必要時撤回）。FAIL 如果只建議「講清楚一點」「再提醒它一次」。
