---
type: llm
weight: 2
---

使用者要的是針對全域 excludes 修（讓 go-git 也讀 core.excludesFile 或 XDG 預設路徑），而且他接著擔心測試跑的時候會不會改到自己本機的 git 設定。PASS 如果回覆針對全域 ignore 提出修法，並提到測試要隔離使用者的 git 設定（例如把 HOME、XDG_CONFIG_HOME 或 GIT_CONFIG_GLOBAL 指到暫存目錄）。FAIL 如果回覆還在改專案層的 .gitignore 處理。
