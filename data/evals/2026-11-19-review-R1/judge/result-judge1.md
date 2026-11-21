# 評審 1 評語

## T1
- 甲：抓到。"Do not grant ownership to the first sender ... any Telegram account that messages this publicly discoverable bot is immediately made an owner"；另指相對路徑 .env（即次要問題）。無其他意見。
- 乙：抓到。AUTH-001 "any Telegram user ... becomes the permanent owner"。其他：AUTH-002 寫入失敗仍報成功（成立）、PIPE-001 單網址文字被丟棄（成立）、PIPE-002 結尾標點（成立）。AUTH-003 是標準答案的次要問題，不計。
- 丙：抓到。"無驗證的先搶先贏自動配對"。其他：#3 單網址短文字路由（成立）、#4 regex 吞標點（成立）、#5 缺 return（成立）。#2 為相對路徑次要問題，不計。
- 丁：抓到。"Any first sender can claim the private bot owner role"；第二點為相對路徑，不計其他意見。

## T2
- 甲：(a)沒抓到、(b)沒抓到。只有 vertex 旗標殘留一條（成立）。
- 乙：(a)沒抓到、(b)沒抓到。舊預設模型、vertex 旗標殘留、缺文件各一條（皆成立）。
- 丙：(a)抓到："check_vertex 未設定 HTTP Timeout ... 對卡住的 socket 會無限期等待"。(b)沒抓到，沒提 Vertex 不能解析 YouTube。其他：#1 金鑰遮罩、#2 旗標殘留、#3 reel 備援鏈、#5 json_mode、#7 缺文件成立；#6 環境變數劫持不確定。
- 丁：(a)沒抓到、(b)沒抓到。舊預設模型、缺文件（成立）。

## T3
- 甲：抓到。#2 "偵測到模型不匹配後僅記錄一次警告，仍跨模型混算相似度"。其他：#1 public_http_client、#4 免金鑰 Ollama、#6 OMNIKEEP_TESTING 成立；#3、#5、#7 不確定；#8 效能/限流屬既有問題，不成立。
- 乙：抓到。"query falls back to local-hash-v1 while existing items commonly remain indexed with the remote model ... can promote unrelated items"。其他：localhost 被擋（成立）。
- 丙：抓到。"a remote request temporarily falls back locally, incompatible vectors can receive arbitrary high similarity"。其他：P1 localhost 被擋（成立）。

## T4
- 甲：部分。#2 "ask_brain 以自然語言問句呼叫 ... 單篇全中即截斷"，指到同一段多詞全命中搜尋，但不是中文整句沒法切詞。其他：#1 自我命中（成立）、#3 重複 LIKE 效能（成立）、#4 連線洩漏（成立）、#5 Unicode 大小寫（成立）、#6 不確定。

## T5
- 甲：抓到。#1 "GitHub Release／Issue／PR 遭壓平為 Repo 根網址 ... 新 release 會被跳過"。其他：#2、#3、#4、#5 成立；#6 不確定。
