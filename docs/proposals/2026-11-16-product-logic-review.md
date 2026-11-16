# 產品邏輯檢討：OmniKit 還該不該存在、該長什麼樣

日期：2026-11-16。狀態：討論稿，等使用者決定方向。

起因：體檢找到 70 項「說的比證據多」的地方（`docs/reviews/2026-11-16-claims-audit.md`）之後，使用者問了更底層的問題：

- 下一步是先修完所有問題，還是先把沒涵蓋到的審完？
- 為什麼一定是刪除、換、換回？為什麼是週報，不是日報或月報？判斷邏輯與方法合不合理？
- Anthropic 的工程師會怎麼設計 OmniKit？模型迭代這麼快，OmniKit 還有存在的必要嗎？
- 另外：使用者上週退訂了 Codex，之後看不到新的 Codex 使用資訊。

## 0. 要你決定的事

| # | 決定 | 我的建議 |
|---|---|---|
| 1 | 方向：A 收成「團隊設定包」、B 維持現在的範圍修到好、C 停掉（第 7 節） | A |
| 2 | 剩下的 A 級 15 項要不要修 | 不修。換與換回整塊拿掉；自製安裝改用原生的 plugin 安裝（先做原型確認做得到），問題跟著程式一起消失（第 2 節） |
| 3 | Codex 端 | 降成「不再維護」：不出 Codex 的建議，規則同步留著。你已退訂，資料只會越來越舊（第 3.3 節） |
| 4 | 凍結期剩下的 13 天（到 2026-11-29）做什麼 | 不加功能，也不修那 15 項；只做刪減與原生 plugin 的原型（第 7 節）。並排實測今天已先跑一次（第 3.5 節） |

想先跟你對三件事，答案會改變上面的建議（第 8 節）。

## 1. 結論

1. **OmniKit 的主幹「診斷加建議」，在 Claude Code 端官方都有了，而且這件事專案早就知道。** 11-05、11-11、11-15 三次查到官方功能，三次的結論都是「OmniKit 做互補的那一塊」，然後繼續蓋。今天把官方功能排在一起看（十一項，第 3.1 節），再對上這台的實際使用紀錄，互補的那幾塊站不住：Codex 端你已經不用，換與換回沒發生過，要對照的名冊大部分沒評過。
2. **體檢的 70 項不是 70 個獨立的 bug，是同一個結構問題的症狀**：OmniKit 從對話紀錄反推 harness 本來就知道的事（哪個 skill 被叫用、哪段是背景執行、哪個 plugin 停用中）。格式每變一次就錯一次，這次的 Codex 壓縮檔、背景對話、子代理都是這一類。這種錯修不完。
3. **程式量跟實際使用成反比。** 官方的 `/skill-doctor` 在這台的紀錄：7 天內 `omnikit-handoff` 叫用 12 次，它是一份 20 行的 SKILL.md、沒有腳本；`omnikit-weekly`（建議與週報）背後約 7,600 行腳本，叫用 1 次，就是今天的試點（第 3.2 節）。
4. **「裝、換、拿掉」是套件管理的想法，前提今年已經變了。** 沒在用的工具現在幾乎不花成本（MCP 工具預設延後載入、skill 清單有預算上限），拿掉的好處變小，刪錯的風險沒變。做過的實測結論又多是「內建就夠」，所以「換」從沒發生過（第 4 節）。
5. **週報沒有依據。** 這台的工具變動是一陣一陣的（一週 9 個，下一週 3 個），不是每週固定；官方與同類工具都是「想到才跑」或「事件觸發」（第 4.2 節）。
6. **還站得住的是另一塊**：團隊的底線規則、子任務分派、交接、飽和式調研，以及用自己情境做出來的實測結論。這些是你每天真的在用的，模型變強也不會取代「你們團隊的規矩」。
7. **所以我的答案是：OmniKit 當「工具組合顧問」沒有存在的必要；當「你和同事的團隊設定包」有，但只需要現在五分之一左右的程式。**

## 2. 先修問題，還是先把沒涵蓋的審完

都不是。這兩個選項都假設現在的範圍會留下來，而體檢的結果正好在質疑這個假設：

- 還沒修的 A 級 15 項，4 項在換與換回（從沒真的用過），11 項在自製的安裝與移除（Claude Code 與 Codex 都有原生的 plugin 安裝與移除指令，11-11 在這台用 `--help` 確認過；Antigravity 沒查）。修它們等於替不該存在的程式補洞。
- 沒涵蓋的四塊（訪談設定、實測腳本、交接、開新對話提醒）裡，交接與提醒是會留下來的，值得審；但要等範圍定了再審，不然又審到要刪的東西。
- 急迫性也不成立：安裝與移除的 A 級只有在同事電腦上移除時才會出事，而目前沒有任何同事裝過。

順序應該是：先定範圍（這份文件），刪掉不留的，再只審、只修留下來的。

## 3. 今天查到的事實

### 3.1 Claude Code 已經內建的（2026-11-16 讀官方文件，這台是 2.1.325）

| OmniKit 的功能 | 官方對應 | 官方怎麼做 |
|---|---|---|
| 沒在用的 skill | `/skill-doctor` | 每個 skill 列出清單成本、7 天 token、叫用次數、上次使用；`-p` 模式印成文字 |
| 沒在用的 plugin | `/plugin` 的 Not used recently | 門檻是「至少 14 天而且 10 段對話」都沒用；主題、LSP 這類沒有叫用紀錄的另外處理 |
| 沒在用的 MCP、整體體檢 | `/doctor` | 沒用到的 skill、MCP、plugin 對照 context 成本，加上慢的 hook、設定檔錯誤；先回報，使用者確認後才改 |
| 規則檔瘦身 | `/doctor` 的 CLAUDE.md 檢查、`/doctor prompt-audit`、`/usage` 的建議 | 找重複的、可以從程式碼推導的、過時或互相衝突的指示，涵蓋 CLAUDE.md、AGENTS.md、rules、skills；提議把常駐的內容搬進用到才載入的 skill |
| 成本 | `/usage`、`/context`、`claude plugin details` | 用量歸因到 skill、子代理、plugin、各 MCP server；只對佔 10% 以上的行為給建議，按 `f` 讓 Claude 套用 |
| 建議裝什麼 | plugin relevance、對話中建議 | 在本機比對工作目錄、讀過的檔、跑過的指令；同一個 plugin 每 3 段對話最多提一次，提過 2 次就停；絕不自動安裝 |
| 實測工具有沒有用 | `claude plugin eval`、skill-creator | 有 plugin 與沒 plugin 兩組，每組預設 3 次，隔離的非互動對話，評審投票 |
| 使用習慣報告 | `/insights` | HTML 報告：做了什麼、哪裡卡住、可以試的功能 |
| 跨 agent 的規則 | 原生讀 `AGENTS.md`（2.1.277 起）、`/init` 的 `/import` | 沒有 CLAUDE.md 就直接讀 AGENTS.md；發現 Codex 或 Gemini CLI 的設定會問要不要帶過來 |
| 工具太多吃 context | 預設行為 | MCP 工具定義預設延後載入；skill 清單的預算是 context 視窗的 1%，超過時先丟掉最少用的 skill 的說明 |
| 給同事上手 | `/team-onboarding` | 依你過去 30 天的使用，產生同事可以直接貼上的上手指南 |

這張表裡大部分的功能，專案先前就查到過（`/skill-doctor`、`/doctor`、`prompt-audit`、Not used recently、`claude plugin eval` 都出現在先前的文件與程式註解裡）。這次第一次查到的是 `/usage` 的歸因與一鍵套用、`/insights`、`/team-onboarding`、原生讀 AGENTS.md，以及 14 天加 10 段對話這個門檻。

問題不在沒查到，而在每次查到之後都替 OmniKit 留了一塊「互補」的位置，然後繼續蓋。把那幾塊拿出來對今天的狀況：

| 哪一次 | 當時留給 OmniKit 的 | 今天的狀況 |
|---|---|---|
| 11-11（`docs/proposals/2026-11-11-diagnose-advice.md` 第 9、10 行） | 「用內建的就好」這一類；Codex 端的「沒在用」；把官方的事實拿來跟名冊對照 | 「用內建的就好」每次實測都成立，但它是結論，不是需要引擎的功能；Codex 你已經退訂；名冊 126 張卡有 117 張還是待評估 |
| 11-15（`docs/proposals/2026-11-15-maturity.md` 第 9 行） | 跨 agent、試用與換回的證據、名冊的判斷與實測、團隊規則與交接 | 跨 agent 對主要使用者不成立；換與換回 0 次；實測與團隊規則成立，而且是真的在用的 |

所以四塊裡站得住的是後兩塊，也就是第 6 節說的「不會被吃掉」的那一類。

### 3.2 這台的實際數字

| 項目 | 數字 | 怎麼來的 |
|---|---|---|
| 程式量 | `engine/scripts` 13,664 行、各 skill 的腳本 5,372 行、PowerShell 1,622 行 | 2026-11-16 數行數 |
| 開發期間 | 13 天、120 個 commit | `git log` |
| 名冊 | 126 張卡，實測紀錄 11 份 | `data/tools`、`data/evals` |
| 「給我建議」跑過幾次 | 2 天（11-11、11-16），都是開發或試點時跑的 | 本機 `advice` 資料夾 |
| 建議被採納 | 1 項（拿掉 graphify，而且是你質疑、實測之後才成立） | `data/pilot/ryan.md` |
| 換與換回 | 4 筆試用紀錄，都是 0 段任務 | 本機 `swaps.json` |
| 通知 | 今天的佇列兩個 agent 都是空的；沒有任何一則通知被採納的紀錄 | 本機 `notify/queue.json` |
| 這台的工具變動 | 4 週裝了 18 個：1、9、5、3 | plugin 安裝日期與 skill 資料夾建立時間 |
| Claude Code 的 skill 清單 | 56 個，每回合約 7,330 tokens；從沒叫用的 47 個約 5,870 tokens | `claude -p "/skill-doctor"` |

`/skill-doctor` 記到的 7 天叫用次數：

| skill | 叫用 | 背後的程式 |
|---|---|---|
| `omnikit-handoff` | 12 次 | SKILL.md 20 行，沒有腳本 |
| `omnikit-dispatch` | 3 次 | `dispatch.py` 668 行 |
| `omnikit-research` | 2 次 | `sweep.py` 554 行 |
| `omnikit-eval` | 1 次 | 14 支腳本 4,646 行 |
| `omnikit-weekly` | 1 次（今天的試點） | 建議、使用統計、成本、候選池、規則、通知、換、影子、回流、週報，約 7,600 行 |

### 3.3 Codex 退訂帶出來的一個邏輯漏洞

這台 Codex 的對話數：第 44 週 124 段、第 45 週 27 段、第 46 週 13 段，最後一段是 11-13。OmniKit 沒有「整個 agent 已經沒在用」這個判斷（在 `advise.py`、`usage.py`、`cost.py` 找不到）。照現在的邏輯，30 天後 Codex 上每一個工具都會變成「30 天沒用到」，建議全部拿掉。正確的說法只有一句：「你已經不用 Codex 了，這邊不看。」

這也說明「跨 agent」這根柱子對主要使用者已經不成立；同事那邊成不成立要問（第 8 節）。

### 3.4 官方的報告也會說錯

`/skill-doctor` 在這台說「35 個 plugin skill 從沒叫用，來自 claude-mem、taste-skill、productivity，到 `/plugin` 停用這些 plugin」。其中 claude-mem 每段對話都在用，只是走 hook 與 MCP，不走 skill；taste-skill 是你刻意留著試用到 11-28 的。

兩個觀察：

- 官方的做法是只報它量得到的（「從沒叫用」），判斷留給使用者。OmniKit 想替使用者下判斷，所以錯的地方多。
- OmniKit 今天修過這一條（只靠 MCP 的 plugin，呼叫到工具就算用到）。這類「官方報告的但書」頂多是一頁說明，不需要一套引擎；而且官方的 `/doctor` 自己就認得出 claude-mem 在用（第 3.5 節）。

### 3.5 並排：官方 `/doctor` 對 OmniKit 的建議（這台，2026-11-16）

`claude -p "/doctor …" --permission-mode plan`，唯讀模式跑一次，約 4 分鐘。它沒有改設定，但在使用者資料夾的 `plans` 與系統暫存資料夾寫了計畫檔與輔助腳本。

| | 官方 `/doctor`（一個指令） | OmniKit 今天的建議（Claude Code 端） |
|---|---|---|
| 沒在用 | 建議移除 archify、omnikeep-setup、web-unblock、productivity；認得出 claude-mem 是靠 hook 在用（累計 38,630 次）；讀了你的 profile，taste-skill 留到 11-28 再判定 | 拿掉 0 項 |
| 證據多強 | 開頭就寫：最近 50 段對話只跨 1.3 天，其中 36 段是背景對話，「未使用」的判定證據偏弱 | 不會講 |
| 規則檔 | 標出常駐約 5.0k tokens、最大的是 `dispatch.md`，並寫明「這是你自己的規則，不提議刪減，只標出來」 | 列 22 段候選 |
| MCP | chrome_devtools 的 451 次呼叫全在另一個專案，建議只在這個專案停用 | 不分專案 |
| 用量 | 87% 的用量發生在切換任務沒清 context 的對話、77% 是長對話、42% 是子代理、13% 是 chrome_devtools | 沒有 |
| 其他 | 安裝健康、hook 耗時、自動更新被關掉、權限規則裡有解譯器前綴、建議把 auto 模式設成預設 | 沒有 |
| 對方沒有的 | | 「瀏覽器用內建的就好」，來自自己的實測 |
| 說錯的 | 把 claude.ai 同步來的 skill 說成 skillshare 同步的，並建議移除（官方文件寫刪掉會再同步回來） | 體檢的 70 項 |

三個觀察：

- 官方的一個 skill 涵蓋了 OmniKit 建議的全部範圍，還多出用量、hook、權限、安裝健康。OmniKit 只多一項：自己實測過的結論。
- 用量最大的槓桿是使用習慣（切換任務不清 context、長對話、子代理），不是工具清單。47 個沒叫用的 skill 合計才約 5,870 tokens。OmniKit 一直在最佳化小的那一邊。
- 官方也會說錯，但它會自己講證據弱，而且每一項都等使用者確認。

### 3.6 同類工具

飽和式調研派給 Gemini 4 Hydrogen（high），寫這份文件時還在跑，結果回來、驗收之後補在這裡。

到 2026-11-16 23:50 的帳本：12 組關鍵字、122 個它判定相關的名字，還沒飽和（每一組都還有新名字）。我還沒驗收，下面只是帳本裡看得到的分布：

- 找沒在用的 skill 或 MCP、清理 context：第 1 組就有 29 個（skill-graveyard、mcp-prune、claude-slim、cc-audit 這類）。
- CLAUDE.md、AGENTS.md 的 lint 與 doctor：26 個（agnix、AgentLint、claudelint、claude-md-doctor 這類）。
- skill 的實測框架：16 個。
- profile 切換與還原：7 個。

光看數量就有一個結論：「替 coding agent 找沒在用的東西、審規則檔」這件事，外面有一百個以上的人在做，官方也做了。這一塊不缺工具。

第 4 節關於節奏與門檻的判斷，目前只有官方文件與這台的資料當依據；同類工具怎麼做，要等這份調研。

## 4. 底層邏輯逐項檢討

### 4.1 為什麼是「裝、換、拿掉、用內建的就好」

這四個動詞來自「工具組合是一份要管理的庫存」的想法，跟套件管理員一樣。它成立要靠三個前提：

| 前提 | 現況 |
|---|---|
| 沒在用的工具有可觀的成本，所以值得拿掉 | 變小了。MCP 工具定義預設延後載入；skill 清單有預算，超過時 harness 自己先丟最少用的說明。這台 47 個從沒叫用的 skill 合計約 5,870 tokens，以 20 萬 token 的視窗算約 2.9%，而且走 prompt cache |
| 每個槽位有「更好的選擇」，而且找得到 | 要靠實測，而做過的第 2 層實測結論幾乎都是「內建不輸」（瀏覽器、程式碼理解）或「挑戰者根本沒被叫用」（網頁來源 6 次只叫用 1 次、graphify 12 次都沒被叫用）。這本身就是發現：模型越強，多數槽位的答案越接近「用內建的」 |
| 換回需要專門的機制 | 原生就有停用與啟用（plugin enable/disable、`skillOverrides`、`.trash`）。換回等於「停用新的、啟用舊的」兩個原生指令。OmniKit 另外做了狀態機，A 級問題有 4 個出在這裡 |

所以四個動詞的現況是：

- **拿掉**：好處小、風險大（刪錯是 A 級）。應該降成「停用」，而且直接用官方的報告。
- **換**：為一個發生次數是 0 的事件做了約 1,100 行（`swap.py`、`shadow.py`）。
- **裝**：從 100 個以上的候選裡請 agent 挑。Anthropic 自己的原則是工具越少越好（第 5.1 節），平台也已經在對的時機建議。
- **用內建的就好**：這是四個裡面唯一每次實測都被證實的。它其實不是一個「動作」，而是一個結論：大部分時候什麼都不用裝。

更根本的問題是單位選錯了。使用者真正遇到的不是「我的 126 張卡該怎麼調」，而是「這類工作上次做得不好，有沒有什麼能幫上忙」。前者以清單為單位，由工具推給人；後者以任務為單位，由人遇到摩擦才問。官方的 `/insights` 走的是後者（哪裡卡住、可以試什麼）。

### 4.2 為什麼是週報

沒有依據。週報是照「每週彙整」這個慣例定的，PRD 沒有引用任何使用資料。

- 這台的工具變動是一陣一陣的：4 週分別是 1、9、5、3 個（最後一週才過一天）。安靜的那週，週報沒東西可講，變成雜訊；變動多的那週，一週才看一次又太慢。
- 日報更糟：絕大多數日子沒有任何變化。月報對不上任何事件。
- 官方沒有任何定期報告：`/doctor`、`/skill-doctor`、`/usage` 都是想到才跑，`/usage` 可以切 24 小時或 7 天；主動建議是事件觸發，而且限制頻率。

合理的觸發不是日曆，是事件：

| 事件 | 該做什麼 |
|---|---|
| 裝了新工具之後過了若干段對話 | 「你裝了 X，之後 10 段對話都沒用到，要不要停用」 |
| 模型或 harness 升級 | 重跑自己的實測；檢查哪些規則與工具是替舊模型補的 |
| 同一類工作反覆不順 | 這時才找工具，而且先試內建 |
| 使用者想到 | 跑官方的 `/doctor` |

真正決定「這個輔助還需不需要」的時鐘是模型的發布週期（幾個月一次），不是星期。

### 4.3 判斷方法逐條

| 規則 | 在哪 | 問題 | 比較好的做法 |
|---|---|---|---|
| 30 天沒用到就列進拿掉 | `advise.py:1143` | 只看天數，不看這段期間有沒有出現「該用到它」的工作。「沒用到」有三種：不需要、需要但沒觸發（說明寫不好）、觸發了但沒幫助。三種的處理完全不同，使用紀錄分不出來 | 只報事實（上次使用、叫用次數），不下「拿掉」的結論；要分三種只能靠觸發測試或實測 |
| 跟內建重疊、裝 7 天沒用到就列 | `advise.py:67` | 7 這個數字沒有來源 | 同上 |
| 開頭成本 1,000 tokens 以上、14 天與 10 段對話都沒用到 | `cost.py:52-54` | 門檻跟官方 `/plugin` 的一樣（14 天、10 段），等於重做一次，而且 OmniKit 的對話數是從紀錄反推的 | 直接用官方的 |
| 試用 14 天 | `swap.py` 的 `TRIAL_DAYS` | 14 天裡有幾段相關的工作沒有保證；這台 4 筆試用都是 0 段 | 以「相關任務的次數」為單位，不是天數；或直接做一次性的實測 |
| 通知之後 30 天內同一槽位不再通知 | `notify.py:55` | 假設使用者想被主動通知工具的事，沒有證據 | 不通知 |
| agent 從候選裡挑「裝」 | `omnikit-weekly` 的 SKILL.md | 候選 100 個以上，品質取決於 agent；為了防它亂挑，SKILL.md 一直加規則（體檢修掉的「猜使用者最近在做什麼」就是一例） | 不做 |
| 規則檔哪些可以拿掉 | `rules.py:17-27` | 腳本只標得出五種表面訊號（訪談產生的、重複、口號、語氣重、很長）。最關鍵的那一步「這條是不是模型現在預設就會做」腳本判斷不了，留給 agent 寫理由，也就是沒有證據。體檢後還得把紅線、確認、權限類全部設成受保護，免得被列進去。腳本自己的說明也寫了官方 `/doctor` 在做同一件事，它補的是每段對話的成本、Codex 端、底線受保護 | 交給 `/doctor` 與 `prompt-audit`，成本看 `/usage`；紅線改用 hook 強制，不靠文字 |
| 第 2 層實測（雜訊基準、不同家族的評審、盲選） | `omnikit-eval` | 這是 OmniKit 最嚴謹、也最有自己東西的一塊：雜訊基準抓到過「評審判 4 勝 1 負的工具其實只被叫用 1 次」 | 留。執行的框架可以逐步換成 `claude plugin eval`，題目與結論是自己的 |

這些數字（30、7、14、10、1,000）都來自 PRD 的條文編號，沒有一個是從資料定出來的。

### 4.4 通知與回流

- **通知**（`notify.py`、`signals.py`，約 1,370 行）：前提是「有更好的工具時，使用者想被打斷」。目前的證據是反的：做過的實測多半是內建不輸，體檢還發現只要 `data/evals/` 有檔案就會被升成「實測勝出」（WK-04，審查者回報，我沒有逐條驗證）。
- **回流**（`feedback.py`，522 行）：把去識別的統計匯出給維護者。試點是 1 到 3 個人，直接問比較快也比較準；體檢還發現它宣稱「不含專案名稱」卻可能帶出內部網址（WK-21，同樣是審查者回報）。

### 4.5 共同的根因

1. **重建 harness 已經知道的事。** 使用次數、背景對話、停用狀態，harness 都有第一手紀錄；OmniKit 從對話紀錄反推，三個 agent 三種格式，每一版都可能變。
2. **以清單為單位，不是以任務為單位。** 所以需要名冊、槽位、候選池、門檻，而這些東西都需要實測來填，實測又做不完（126 張卡，11 份紀錄）。
3. **用規則補規則。** 腳本給候選、agent 照 SKILL.md 的規則挑；每次挑錯就再加一條規則。這正是 Anthropic 說模型變強之後該拆掉的那種鷹架（第 5.1 節）。
4. **替使用者下結論，而不是給事實。** 「建議拿掉」比「12 天沒用到」多了一層沒有證據的判斷，70 項裡大部分是這一層。

## 5. Anthropic 的工程師會怎麼做

先講限制：Anthropic 內部怎麼做我看不到。能引用的只有兩種一手資料：他們公開的工程文章，以及他們實際做出來的產品。

### 5.1 公開講的原則（原文引用，2026-11-16 讀取）

| 原則 | 原文 | 出處 |
|---|---|---|
| 每個元件都是一個假設，模型升級就要重新檢查 | "every component in a harness encodes an assumption about what the model can't do on its own"；"it is generally good practice to re-examine a harness, stripping away pieces that are no longer load-bearing" | Harness design for long-running application development（2026-03-24） |
| 先用最簡單的做法 | "find the simplest solution possible, and only increase complexity when needed" | 同上 |
| 工具不是越多越好 | "More tools don't always lead to better outcomes."；"One of the most common failure modes we see is bloated tool sets that cover too much functionality" | Writing effective tools for agents（2025-09-11）；Effective context engineering for AI agents（2025-09-29） |
| context 只放訊號最強的 | "find the smallest set of high-signal tokens that maximize the likelihood of your desired outcome" | Effective context engineering |
| 模型越強，規定越少 | "smarter models require less prescriptive engineering" | 同上 |
| 實測從真實的失敗開始，不用多 | "20-50 simple tasks drawn from real failures is a great start."；"Because model outputs vary between runs, we run multiple trials" | Demystifying evals for AI agents（2026-01-09） |
| 一定要守的規則用 hook，不靠文字 | 官方文件：CLAUDE.md 是 context，不是強制設定；"To block an action regardless of what Claude decides, use a PreToolUse hook instead." | code.claude.com/docs/en/memory |

另外有二手報導說 Claude Code 團隊替新模型刪掉了八成以上的系統提示、產品是照「六個月後的模型」設計的。這兩點我只找到二手摘要，沒有找到完整逐字稿【待驗證】。

### 5.2 實際做出來的形狀

從第 3.1 節的產品倒推，他們的做法有幾個共同點：

- **`/doctor` 是一個 skill，不是一套引擎。** 官方指令表把它標成 Skill：一份提示，加上 harness 自己有的資料，讓模型去看、去說、確認後去改。`/fewer-permission-prompts` 也一樣，是「請模型掃你的對話紀錄」的 skill。
- **資料在源頭記。** 使用次數是 harness 記的（`skill_activated` 事件、Last used），不是事後解析。
- **只報量得到的，門檻兼看天數與次數**（14 天而且 10 段對話）。
- **使用者想到才跑；主動建議有嚴格的頻率上限，而且永遠要使用者確認。**
- **能逆轉的動作優先**：停用而不是刪除，刪掉的 skill 進 `.trash` 留 30 天。
- **實測有對照組與重複次數**（有 plugin 對沒 plugin，各 3 次）。

### 5.3 套到 OmniKit：每個元件在假設什麼

| 元件 | 行數 | 它假設模型或 harness 做不到什麼 | 現在還成立嗎 | 處置 |
|---|---|---|---|---|
| 使用統計與成本（`usage.py`、`cost.py`） | 1,541 | harness 不會告訴你哪些沒在用、花多少 | Claude Code 不成立 | 刪，改讀官方報告 |
| 建議與候選池（`advise.py`、`pool.py`、`proof.py`） | 2,401 | agent 與平台不會在對的時機建議工具 | 不成立，而且跟「工具越少越好」相反 | 刪 |
| 規則瘦身（`rules.py`） | 398 | 沒有東西幫你審規則檔 | 不成立 | 刪 |
| 換、影子比對（`swap.py`、`shadow.py`） | 1,096 | 換工具要狀態機與 14 天試用 | 換從沒發生過；原生就能停用與啟用 | 刪 |
| 通知（`notify.py`、`signals.py`） | 1,369 | 使用者想被主動通知更好的工具 | 沒有證據 | 刪 |
| 回流（`feedback.py`） | 522 | 維護者要靠匯出才知道同事怎麼用 | 3 個人以內直接問 | 刪 |
| 週報（`weekly.py`、`report.py`） | 314 | 每週看一次有用 | 沒有證據 | 刪 |
| 自製安裝與移除（`agents.py`、`install.ps1`、`uninstall.ps1`） | 約 2,980 | 沒有原生的安裝與移除 | 不成立：plugin marketplace、`claude plugin install` 與 `uninstall` | 換成原生 plugin，先做原型驗證；A 級 11 項跟著消失 |
| 底線規則與個人規則 | 資料 | 模型不知道你們團隊的底線與慣例 | 成立，模型變強也不會知道 | 留；紅線改用 hook 強制 |
| 子任務分派（`dispatch.py`、skill） | 711 | harness 不會照你的帳號、額度、不同家族互審來分派 | 成立 | 留；分派的 YAML 從常駐規則搬進 skill |
| 交接（skill） | 20 | 對話之間的工作狀態會掉 | 部分成立（官方有 auto memory、session recap）；但它是你用最多的 | 留 |
| 飽和式調研（skill、`sweep.py`） | 554 | agent 查幾個就停 | 成立（11-14、11-16 各一次實例） | 留 |
| 實測（`omnikit-eval`） | 4,646 | 沒有東西能用你的情境比工具 | 框架部分不成立；題目與結論成立 | 留題目、結論與盲選；框架逐步換成原生的 |
| 名冊（126 張卡、看板） | 資料 | 需要一份自己的工具目錄 | 117 張還是待評估；有實測結論的只有幾個槽位 | 縮成一份「實測過的結論」 |

可以直接刪的約 7,600 行，可望換成原生的約 3,000 行，合計約佔現在 20,600 行的一半；實測框架（4,646 行）之後再逐步換。

順帶一個 OmniKit 自己違反自己原則的地方：規則檔每段對話約 5,020 tokens，其中 `data/rules/dispatch.md` 約 2,559（`data/pilot/ryan.md` 第 12 行）。分派的 YAML 與背景數據只有在派子任務時才用得到，卻每段對話都載入。官方的建議正是把這種內容搬進 skill，用到才載入；`omnikit-dispatch` 這個 skill 已經存在，搬過去就好。

## 6. 模型迭代這麼快，OmniKit 還有必要嗎

照「會不會被吃掉」分三類：

| 類別 | 內容 | 為什麼 |
|---|---|---|
| 很快被吃掉（已經發生） | 建議裝什麼、沒在用的偵測、context 成本、規則檔體檢、換與換回、跨 agent 的設定同步 | 這些是 harness 最清楚的事，平台廠商一定會自己做。Claude Code 已經做完；AGENTS.md 成為共通格式之後，連同步都不用做 |
| 慢慢被吃掉 | 交接、開新對話提醒、實測的執行框架 | 官方有 auto memory、session recap、`claude plugin eval`，但還沒有完全蓋住你的用法 |
| 不會被吃掉 | 你們團隊的底線與慣例；你的帳號與額度怎麼分派、誰審誰；你用自己的工作情境得到的實測結論；Windows 加公司防毒的環境、繁體中文的上手 | 這些是關於「你們」的知識，不是關於模型的。模型再強也要有人告訴它 |

第一類佔了現在大部分的程式，第三類大多是資料與幾份短的 skill，不是引擎。

還有一個角度：照 PRD 的試點指標「少了它會不會非常失望」，用這台的叫用紀錄先替你自己答一次。少了交接、分派、底線規則，你明天就會有感覺；少了週報與建議，從紀錄看不出會有人發現。

## 7. 三個方案

| | A. 收成團隊設定包 | B. 維持範圍，修到好 | C. 停 |
|---|---|---|---|
| 做什麼 | 留規則、分派、交接、調研、實測的題目與結論；刪掉建議、週報、換、通知、回流、使用統計；安裝改用原生 plugin | 修完 A 級 15 項、B 級 37 項，審完沒涵蓋的四塊 | 封存 repo，規則檔自己留著用 |
| 好處 | 留下的每一樣都有人在用；A 級問題大多隨程式消失；之後模型升級要重查的東西很少 | 不用推翻已經做的 | 零維護 |
| 代價 | 承認約一半的程式白做；原生 plugin 能不能放下現在的規則同步，要先做原型 | 每一版 Claude Code 都可能再弄壞解析；修完之後跟官方 `/doctor` 做的是同一件事 | 同事沒有現成的設定包；分派與交接要另外找地方放 |
| 風險 | Codex、Antigravity 端的原生安裝我還沒查證 | 最高：繼續花時間在會被吃掉的那一類 | 丟掉真的在用的那一塊 |

建議 A。它不是放棄 OmniKit，是把名字還給真的在用的東西。

如果選 A，凍結期內只做這些（都算瘦身，不是加功能）：

1. 並排實測已經先做了一次（第 3.5 節）：OmniKit 說了、官方沒說、而且是對的，只有「實測過的結論」這一項。你看過輸出、同意這個判讀，就照下一步走。
2. `omnikit-weekly` 改成一頁：教 agent 跑官方的報告，加上第 3.4 節那種但書與實測過的結論。背後的腳本先停用（不刪），確認沒人找再刪。
3. 做一個原型：把規則、skills、hook 包成原生 plugin，在這台裝與移除各一次，看規則同步哪些做得到、哪些做不到。
4. Codex 端：不再出建議。
5. `dispatch.md` 的 YAML 搬進 `omnikit-dispatch` skill。

同事試點改成驗證另一件事：裝了這個設定包之後，交接與底線規則有沒有幫到他們。

## 8. 想先跟你對的三件事

1. **同事實際用哪個 agent？** 如果都是 Claude，「跨 agent」可以整根拿掉，安裝也只要做 Claude 的原生 plugin。如果有人主要用 Codex 或別的，要另外查那邊的原生機制。
2. **你自己「少了會非常失望」的是哪幾樣？** 我從叫用紀錄猜是交接、分派、底線規則。如果你覺得建議或週報其實有幫到你，只是紀錄看不出來，結論要改。
3. **OmniKit 是做給誰的？** 自己好用、同事好用，還是想做成給外面的人用的產品？前兩個指向 A。第三個的話，「工具顧問」這個產品的對手是平台自己，我不建議；但「一套跨模型分派加交接的工作方法」是另一個題目，可以另外談。

## 9. 這份分析的限制

- 官方功能是讀文件，加上在這台各跑一次 `/skill-doctor` 與 `/doctor` 得到的；`/insights`、`claude plugin eval`、plugin relevance 我沒有實際跑過。並排只比了一次、一台。
- Codex 端：11-11 查過，官方的 `codex doctor` 只做健康檢查，沒有「沒在用」的偵測；這次沒有重查。Antigravity 沒查過。
- 「原生 plugin 能取代自製安裝」是推論，還沒做原型。OmniKit 當初自己寫安裝，有一部分原因是公司防毒擋第三方同步工具，這個限制對原生 plugin 成不成立要實測。
- 叫用次數只有 7 天、只有這一台、只有你一個人。
- Anthropic 的「做法」是從公開文章與產品倒推的，不是內部資訊。

## 來源

官方文件（2026-11-16 讀取）：

- https://code.claude.com/docs/en/plugins/install.md （Not used recently、Context cost）
- https://code.claude.com/docs/en/plugins/measure.md （14 天與 10 段對話的門檻、`/doctor`、`/usage`、`/skill-doctor`）
- https://code.claude.com/docs/en/skills.md （`/doctor` 涵蓋範圍、`/skill-doctor`、skill 清單預算）
- https://code.claude.com/docs/en/costs.md （`/usage` 的歸因與建議、`/insights`、MCP 工具預設延後載入）
- https://code.claude.com/docs/en/plugin-evals.md （對照組、每組 3 次、隔離）
- https://code.claude.com/docs/en/plugins/relevance.md （建議的訊號與頻率上限）
- https://code.claude.com/docs/en/memory.md （CLAUDE.md 目標 200 行以內、原生讀 AGENTS.md、prompt-audit）
- https://code.claude.com/docs/en/commands.md （`/doctor` 是 skill、`/team-onboarding`、`/init` 的匯入）

Anthropic 工程文章：

- https://www.anthropic.com/engineering/harness-design-long-running-apps
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

二手報導【待驗證】：

- https://www.barath.ai/learnings/boris-cherny-yc-startup-school-2026
- https://with-agents.dev/summaries/coding-with-agents/boris-cherny-we-cut-80-of-claude-codes-prompt/
