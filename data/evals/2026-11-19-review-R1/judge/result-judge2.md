# 評審 2 評語

## T1
標準答案主缺陷（先到先得）與次要（相對路徑 .env）四份都抓到。
- 甲：「When the allowlist is empty, any Telegram user ... becomes the permanent owner」；AUTH-003「dotenv.set_key('.env'...) writes relative to the process working directory」。抓到。其他：AUTH-002（寫入失敗仍宣告成功）成立、PIPE-001（單一 URL 丟掉伴隨文字）成立、PIPE-002（句尾標點被吞）成立。
- 乙：「陌生人搶綁（First-Come-First-Served Takeover）」；「使用 相對路徑 ".env"」。抓到。其他：第3項（短筆記遺失脈絡）成立、第4項（regex 吞標點，已實測）成立、第5項（配對成功後缺 return，修正 diff 的舊程式可證）成立。
- 丙：「Any first sender can claim the private bot owner role」+「persistence writes the relative path .env」。抓到，無其他意見。
- 丁：「Do not grant ownership to the first sender」+「this writes to a relative .env」。抓到，無其他意見。

## T2
- 甲：(a) 第4項「check_vertex() 建立 genai.Client(...) 時未指定 http_options timeout ... 對卡住的 socket 會無限期等待」抓到；(b) 沒提 Vertex 不能解析 YouTube，沒抓到。其他：1（AQ. 金鑰遮罩）成立、2（vertex 旗標殘留，丙丁也獨立指出）成立、3（reel.py 繞過 ChainProvider）不確定、5（check_vertex 忽略 json_mode）成立、6（環境變數劫持）成立、7（文件檔不存在）成立。
- 乙：兩項皆沒抓到。其他：舊預設模型 gemini-2.5-flash 成立、說明文件不存在成立。
- 丙：兩項皆沒抓到（只在推理過程提到 missing timeout，結論未列）。其他：vertex 旗標殘留成立。
- 丁：兩項皆沒抓到。其他：REV-001、REV-002、REV-003 皆成立。

## T3
- 甲：P2「a remote request temporarily falls back locally, incompatible vectors can receive arbitrary high similarity ... despite the code stating they must not be compared」抓到。其他：P1 public_http_client 擋 localhost，成立（乙有實測 validate_url）。
- 乙：第2項「查詢當下遠端暫時失敗退回 local-hash-v1 ... 跨模型混算相似度」抓到。其他：1、4 成立；3、5、6、7 不確定；8（rate limiter／同步阻塞 event loop）屬既有設計觀察，不成立。
- 丙：「On a transient embedding API failure, the query falls back to local-hash-v1 while existing items commonly remain indexed with the remote model」抓到。其他：public_http_client 成立。

## T4
- 甲：沒有指出中文整句被當成一個詞；第2項「只要有 1 筆資料符合 require_all=True，_search_items 就立即只回傳該 1 筆，不補充部分命中的候選」與修正的候選分階段同一段程式但原因不同，判部分。其他：1（自我命中）成立、4（連線洩漏）成立、5（非 ASCII 大小寫）成立、3（LIKE 重複展開的效能）不成立（效能風格建議）、6 不確定。

## T5
- 甲：第1項「canonical_url 在 bare == github.com 時把所有 2 段以上路徑截斷成 repo 根網址 ... 雷達 GitHub Releases 監控失效，只要庫內曾存過該 repo ... 新 release 都會被跳過」抓到。其他：2、3、4、5 成立；6（無 ORDER BY）不確定。
