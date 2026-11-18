---
type: llm
weight: 2
---

錯誤表示 content 不是字串（例如某些 agent 的對話格式是陣列或物件，像 Gemini 的 session），使用者用的正是 Gemini 的 checkpoint。PASS 如果回覆指出 content 可能不是字串、要先看那筆資料的實際格式，處理不同格式（陣列取出文字等），並用使用者那個 checkpoint 實際重現驗證。FAIL 如果回覆只叫使用者清快取或重 build，或只加 optional chaining。
