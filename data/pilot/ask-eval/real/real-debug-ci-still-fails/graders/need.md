---
type: llm
weight: 2
---

使用者要的是 CI 上的失敗被修好（之後還要更新 PR 說明、處理 PR 留言）。PASS 如果回覆建議先讀 CI 的實際失敗 log（例如用 gh run view --log-failed），比對 CI 跟本機的環境差異（作業系統、相依版本、環境變數、是否裝了 gemini CLI 等），在本機重現後再修，並以 CI 重跑通過為完成條件。四項至少做到三項就 PASS。
