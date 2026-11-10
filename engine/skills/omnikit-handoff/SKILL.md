---
name: omnikit-handoff
description: 把做到一半的工作交給新對話，或照交接檔接手。使用者說「交接」「handoff」「接手」「讀 <交接檔路徑> 接著做」時使用；OmniKit 的開新對話提醒出現、而工作還沒做完時，先問使用者要不要交接。Hands unfinished work over to a new conversation, or takes over from a handoff file.
---

# 交接與接手

交接檔存在使用者的狀態 repo（私人 repo），位置寫在個人規則的「工作階段」。個人規則沒寫狀態 repo 時，問使用者要放哪裡，不要自己建 repo。

- 交接檔路徑：`<GitHub repo 名稱>\handoffs\<YYYY-MM-DD-HHmm>-<主題>.md`，repo 名稱取自專案的 `git remote`。
- 格式照狀態 repo 的 `_template\HANDOFF.md`。
- 不寫金鑰、token、密碼。

## 交接

1. 工作的修改先 commit 並 push 到工作分支（未完成用 `wip:` 前綴）；不能 push 的，在交接檔寫明「只在這台」。
2. 先 `git pull` 狀態 repo，照範本寫交接檔，commit 並 push。
3. Claude 桌面版：直接開新對話接手，簡報裡寫交接檔路徑。其他介面：給使用者一句可以貼進新對話的起始 prompt：「讀 <交接檔路徑> 接著做」。

## 接手

1. 先 `git pull` 狀態 repo 與專案 repo。
2. 讀交接檔。沒給路徑就到 `<repo 名稱>\handoffs\` 拿檔名排序最後的一份。
3. 比對交接檔的規則版本與自己載入的是否一致；不一致先講。
4. 「接手紀錄」已經有別的對話時，先問使用者再接。
5. 確認分支與「下三步」，回報看到的狀態再開工。
6. 開工後第一次 commit 時，在交接檔的「接手紀錄」加一行（時間、裝置、介面、對話 id），狀態 repo 一併 commit 並 push。
