---
type: llm
weight: 2
---

使用者要的是：這次改用 trailer 當連結，並把「commit hash 不穩定、用 trailer 連結」寫成持久規則。PASS 如果回覆同意寫進規則檔，並給出簡短、附理由的規則文字（例如 commit hash 會因 rebase／amend 改變，關聯 commit 一律用 Entire-Checkpoint trailer），同時修正目前的方案不用 commit hash。FAIL 如果回覆只修這一次、沒有規則文字，或規則沒寫理由。
