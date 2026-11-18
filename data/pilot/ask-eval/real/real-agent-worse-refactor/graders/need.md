---
type: llm
weight: 2
---

使用者本來只想讓程式更清楚表示只會執行 git fetch origin，agent 越改越糟，最後他要求改回原本的寫法。PASS 如果回覆直接照做改回原本兩行，不再提出新的改寫；可以簡短說明 Go 的 variadic 參數不能在固定參數後接 slice 展開（所以 "fetch", "origin", refSpecs... 不合法）。FAIL 如果回覆又提出另一種新寫法。
