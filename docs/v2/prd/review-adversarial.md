# PRD 對抗式審查（adversarial lens）

- 審查對象：`docs/v2/prd/prd.md`、`docs/v2/prd/addendum.md`（2026-11-05 草稿）
- 方法：BMAD bmad-review 的 adversarial lens（`references/lens-adversarial.md`）；欄位照 `SKILL.md` 的 Output：lens、location、trigger_condition、guard_snippet、potential_consequence；輸出格式照 `customize.toml` 預設的 both（markdown 加 JSON）。
- 佐證：讀過 `engine/scripts/`、`engine/skills/`、`engine/schema/`、`data/`、`.githooks/`、`.github/workflows/`、`docs/v2/research.md` 與 `docs/v2/research/`；另在這台用 Get-AuthenticodeSignature 查執行檔簽章。只審查，沒有修改任何其他檔案。
- 行號：`prd.md`、`addendum.md` 指 `docs/v2/prd/` 底下的檔案；所有行號以 2026-11-05 的工作目錄為準。
- 依 adversarial lens 的規定，發現不分嚴重度、不排序；下面依主題分組，編號只供引用。

## 判定

方向與研究扎實，但不建議照現稿進入架構與試點：核心主張「在你的情境實測」跟實際評估方式不符，現有同步機制（git pull 自動同步、試用 MCP 對所有人自動核准、hook 更新免重新信任）跟 PRD 的同意原則正面衝突，三個主要指標在 4 週試點內大多量不到。

## 用程式碼核對過的現況

PRD 描述正確的：

- `profiles.py:189-203`：Codex 規則整份換掉（`connect_codex`），PRD 與研究描述正確。
- `agents.py:380-388`：`same()` 只比 OmniKit 設的欄位，不同就覆寫，描述正確。
- FR-13 的 Codex plugin 使用統計已完成：commit e27c415（2026-11-05 00:24）。
- 訪談現有 6 題（`engine/skills/omnikit-setup/SKILL.md:35-47`），與 FR-4「沿用 6 題」一致。
- 名冊 116 張：預設 11、試用 1、待評估 104；非凍結槽位的待評估 57 張，與 SM-4 一致（本次重新統計）。
- `session_nudge.py` 已讀 Claude Code 與 Codex 的對話紀錄並輸出 `systemMessage`（`:12-14`）。

PRD 描述不正確、不完整，或沒提到的：

- 附錄 A.3 的 Antigravity 驗證位置 `~/.gemini/config/skills`，跟 agents.py 實際寫入的 `~/.agents/skills`（`agents.py:16、93-95`）不同（ADV-24）。
- 附錄 A.3「skills 與 MCP 沿用 agents.py」：agents.py 只裝 `engine/skills` 與全域 `data/mcp/servers.yaml`（`agents.py:322-324、359-367`），沒有安裝第三方工具卡的能力（ADV-23）。
- 工具卡 schema 的 `works_with` 與 `plugin` 只有 claude、codex（`tool.schema.json:26-30、35-63`）；72 張卡沒填 works_with（ADV-25）。
- marketplace 只收 default（`build.py:14、67-68`），全名冊只有 3 張卡有釘選來源（ADV-22）。
- git pull／commit 會自動同步規則、skills、MCP、權限與 hook（`.githooks/post-merge`、`sync-data.sh`、`install.ps1:23`），PRD 沒提（ADV-14）。
- 試用中的 chrome_devtools MCP 裝到三個 agent，Codex 自動核准、Claude 免問（`servers.yaml:19、23`、`claude-allow.txt:5`）（ADV-30）。
- 週報是 omnikit-eval 的手動指令，訪談第 5 題選「先不要」就沒有（`omnikit-setup/SKILL.md:46`）（ADV-13）。
- `usage.py:285-292` 沒有「未知」狀態，解析不到就判 unused（ADV-21）。
- 這台實際使用的 uv.exe 與 install.ps1 裝的 gitleaks.exe 都沒有數位簽章（Get-AuthenticodeSignature：NotSigned）（ADV-27）。
- 名冊沒有任何資料分析、Jupyter、pandas 相關卡片（ADV-03）。

## 發現（lens：adversarial，共 40 項）

### 一、核心主張與證據

#### ADV-01

- **lens**：adversarial
- **location**：prd.md §1 願景（:26）、UJ-2（:62）、FR-25（:438）；data/profiles/ryan/scenarios.yaml；data/evals/2026-11-04-browser-u1.md
- **trigger_condition**：通知文案寫「X 在你的情境實測勝過 Y」，但第 2 層實測只在維護者這台、用 ryan 的 CatOS／OmniKeep 情境、維護者的模型與帳號跑（U1 的測試對象就是 CatOS 前端副本）；同事的情境、模型與 harness 從來沒被測過。
- **guard_snippet**：通知與預覽的證據欄改成「在維護者情境（<情境 id>、<agent 與模型>、<日期>）勝出」，並列出跟這位同事的差異（agent、模型、專案類型）。若要保留「你的情境」的說法，新增需求：同事端可跑的縮小版驗證（例如在他勾選的專案上跑 1c 煙霧測試），通過才可使用這個措辭。
- **potential_consequence**：違反安全底線的「誠實回報」；同事照建議換了工具卻感受不到差異，SM-2 的換回率上升，「有證據才建議」這個核心定位失去可信度。

#### ADV-02

- **lens**：adversarial
- **location**：prd.md FR-5（:169）、§6.1（:558）、§7 階段 0（:579）、§10 第 4 題；docs/v2/brief/addendum.md:27、30、32、34；data/tools/bmad.yaml、rea.yaml、skill-creator.yaml
- **trigger_condition**：現有需要安裝的預設裡，bmad 的理由是「第一輪既定的預設；RIA 的評估結果出來之前不變」、rea 是「訪談：有感」、skill-creator 是「常用」，都是維護者個人偏好，沒有評估紀錄；FR-5 卻要求每項附「證據（評估紀錄的位置）」。訪談的「研究調查」「不確定時亂猜」對應到凍結的 product-research（預設 bmad），階段 0 只解凍 dev-workflow，§10 第 4 題也沒有時程。§6.1 又允許「明確標為沒有預設、用內建功能」，等於每個槽位都能用這個出口宣稱達標。
- **guard_snippet**：加一條規則：同事版只預先勾選證據等級 E3 以上的工具；沒有評估紀錄的預設在預覽標「維護者個人使用（未實測）」，不預先勾選。§6.1 的完成條件改成可數的門檻（例如訪談第 1、2 題的每個選項，至少一個對應槽位有 E3 以上的預設，否則在預覽如實寫「這一項只用內建功能」）。product-research 的處置（解凍，或從訪談對應中移除）列進階段 0。
- **potential_consequence**：試點同事看到的「證據」欄大多空白或指向不存在的紀錄；BMAD 這種約 30 個 skill 的框架被預先勾選給大多數寫程式的同事，跟 SM-3 的 token 目標直接衝突。

#### ADV-03

- **lens**：adversarial
- **location**：prd.md UJ-1（:49-60）、FR-3（:130-139）、FR-6（:174-183）、§10 第 3 題；addendum.md B（:94）；data/tools/（grep jupyter、pandas、notebook、ipynb、資料分析：0 筆）
- **trigger_condition**：主角阿哲做資料分析（`*.ipynb`、pandas），但名冊 116 張卡沒有任何資料分析、Jupyter 或 pandas 相關的卡片；FR-6 對新槽位只要求「至少一個情境」，附錄 B 又排除「pandas 就裝 pandas 的 skill」。UJ-1 第 1 步的本機模型判斷也沒有槽位可以接（§10 第 3 題未定）。
- **guard_snippet**：FR-6 加可測結果：新槽位進 MVP 之前，至少有 1 個通過第 1c 層的候選，否則明確標為「只用內建功能」並在預覽說明。把資料分析槽位的候選蒐集與實測列為階段 0 的交付項；或把 UJ-1 改成名冊現況做得到的人物。本機模型槽位定案前，硬體掃描結果不要出現在推薦理由裡。
- **potential_consequence**：試點第一天的「關鍵時刻」就落空：預覽只剩內建功能與規則，「4 個工具、每個都有實測證據」的承諾做不到，而第一印象往往決定試點成敗。

#### ADV-04

- **lens**：adversarial
- **location**：prd.md FR-25（:434）；addendum.md A.6（:76）；docs/v2/research/eval.md:425-428、:601
- **trigger_condition**：FR-25 的勝出條件只有「3 次配對至少贏 2 次」，漏掉研究同時要求的餘量規則（eval.md:601：「用『平均每次多 1 個檢查點』這類有餘量的規則，不用『總分高就贏』」）。用附錄 A.6 同一套模擬假設（4 個二元檢查點、兩邊通過率都是 70%）計算：單次挑戰者分數嚴格較高的機率約 35%（與 eval.md 的「跑 1 次 35%」一致），3 次至少贏 2 次約 28%；FR-25 允許最多 2 個挑戰者，至少一個被誤判勝出的機率上看約 48%（假設獨立；共用現任的執行結果時會略低）。「成本沒有明顯變差」也沒有數字。
- **guard_snippet**：FR-25 改寫為「3 次至少贏 2 次，而且平均每次多至少 1 個檢查點（或事先寫好的效果量門檻）」；多個挑戰者時逐一對現任比較並做多重比較校正；「成本沒有明顯變差」定成數字，例如每回合輸入 token 不超過現任的 110%；E4 通知附上這次判定規則的誤判率估計。
- **potential_consequence**：兩個一樣好的工具有相當機率被判成「更好」，錯誤的建議被主動推給所有同事；SM-2 與 SM-C3 由雜訊主導，第 3 層試用還會把誤判固化成預設。

### 二、成功指標與時程

#### ADV-05

- **lens**：adversarial
- **location**：prd.md §8 SM-2（:589）、§7 階段 2 與 3（:581-582）、FR-16（:306、:308）
- **trigger_condition**：SM-2 要量「接受、而且 30 天內沒換回」，但試點只有 4 週、檢討在試點後 1 週；建議最早也要等 E4 實測完成、通知送達才會被接受，30 天觀察窗一定超出檢討日。分母（E4 換工具通知的數量）在「每人每週最多 1 則」且 E4 取決於階段 0 產出的條件下，可能是 0 到個位數。
- **guard_snippet**：SM-2 改成試點期量得到的版本（例如「接受後 14 天內沒換回」，檢討時另列仍在觀察中的案例），或把檢討日訂在最後一則建議被接受後滿 30 天；事先寫明最少樣本數（例如少於 5 則時只報個案，不判定達標與否）。
- **potential_consequence**：檢討時 SM-2 算不出來，或只靠 1、2 個案例判定；v2.1 要不要打開主動建議的決策沒有依據。

#### ADV-06

- **lens**：adversarial
- **location**：prd.md §8 SM-3（:590）、FR-5（:167-168）；docs/v2/brief/brief.md:25；data/mcp/servers.yaml:7-25
- **trigger_condition**：SM-3 要求 token 比安裝前少 20%，前提是同事原本裝了很多；但目標使用者是「沒研究過 agent 工具」「乾脆什麼都不裝」的人（brief.md:25）。對他們來說，安裝 OmniKit 只會增加開頭負擔：底線與 profile 規則、omnikit-setup 與 omnikit-eval 的 skill 清單、內建功能改寫進規則（FR-5 :167），以及 servers.yaml 對每個人都裝的 chrome_devtools MCP 工具定義。27% 的依據是維護者這台 112 個 skill 的特例；「同樣的試點情境」要怎麼在安裝前後重播，也沒有定義。
- **guard_snippet**：SM-3 分群：原本負擔高的同事（例如對話開頭的 skill 清單超過 N 字元）量「下降幅度」；其他同事改量「OmniKit 增加的開頭負擔不超過 X tokens」。寫明量法：固定 1 到 2 個提示，安裝前後在同一專案各跑一次 `claude -p` 與 `codex exec`，記錄輸入 token。
- **potential_consequence**：多數試點同事的 SM-3 必然失敗，或被迫用不一致的量法湊數，指標失去意義。

#### ADV-07

- **lens**：adversarial
- **location**：prd.md §8 SM-1（:588）、FR-13（:270-271）；engine/scripts/usage.py:5-21；docs/v2/brief/brief.md:36
- **trigger_condition**：usage.py 只能從「讀了 SKILL.md」與 plugin skill 的呼叫判斷有沒有用到；MCP server、CLI、hook 型（例如 rtk 會攔所有 shell 指令）、rules 型工具與內建功能都沒有叫用紀錄，FR-13 也明說這類不判斷，但 SM-1 的分母是「OmniKit 裝的工具」。門檻也不一致：FR-13 是 14 天而且 10 個 session、SM-1 看 30 天、brief.md:36 與 usage.py 預設都是 30 天；第 14 天就被建議停用的工具，算不算進 SM-1 的分母沒有定義。每人只裝 0 到 5 個、共 3 到 5 人，1 個工具就能讓比例跳 20% 以上。
- **guard_snippet**：SM-1 的分母限定為有可觀察叫用訊號的工具，其他種類另列「無法量測」；MCP 改用 transcript 裡的 `mcp__<server>__` 呼叫補上量測；寫明被停用的工具怎麼計入；報告同時給分子、分母的原始數字；統一「沒在用」的門檻。
- **potential_consequence**：SM-1 不是被量不到的工具拉低，就是被「排除誰」左右，跟 SM-C1「不能靠少裝衝高」互相打架。

#### ADV-08

- **lens**：adversarial
- **location**：prd.md §7 推出計畫（:579-582）、§12（:658）、§10 第 1、7 題、SM-4（:594）、UJ-4（:74）；docs/v2/research.md:190-195
- **trigger_condition**：階段 0 要「跑評估漏斗」，但漏斗的批次工具（FR-22 到 FR-26：第 0 層批次、1b 證據卡、1c 隔離環境、第 2 層排程）就是階段 1 要開發的東西，兩者卻由同一位維護者「同時進行」。研究估計解凍兩個凍結槽位要再加 2 到 3 週（research.md:193-195），PRD 卻把解凍 dev-workflow 放進 6 到 8 週的階段 0。非凍結部分約 3,000 萬到 1.9 億 token、評分還要第三家模型，但 token 上限（第 1 題）、試點名單與開始日（第 7 題）都未定；SM-4 的「處理完」沒有定義。UJ-4 說維護者只要盲選與勾選，但 FR-22 的 url 比對、FR-24 的程式碼審查、FR-30 的提案審核與第 1 週隨訪都要人力。
- **guard_snippet**：§7 加關鍵路徑與進入試點的 go/no-go 閘門，例如「FR-7 到 FR-11 在 Windows 通過、訪談會用到的槽位至少 N 個有 E3 以上的預設、doctor 在 2 台非維護者電腦全部通過」才開始階段 2；SM-4 的「處理完」定成「每張卡都有第 0 層結果與第 1 層結論」；token 上限先給暫定值與用哪個方案；列出維護者每週的預估工時。
- **potential_consequence**：階段 0 與 1 互相等待，試點日期一再延後；或在內容空洞、工具鏈沒驗證的狀態下硬上，同事的第一次體驗就失敗。

#### ADV-09

- **lens**：adversarial
- **location**：prd.md §4.6 說明（:330）、FR-21（:378）、§6.1（:562）、§6.2（:569）、§7 階段 3（:582）
- **trigger_condition**：靜默期「只記錄、不顯示」，既沒有使用者回饋也沒有人工標註，「誤報率」無從計算（只算得出命中次數）；FR-19 的頻率關卡延到 v2.1，靜默期也不知道「本來會顯示哪一則」。§7 階段 3 要依此決定是否打開提示，卻沒有判定門檻。資料散在各同事電腦，彙整（FR-31）延後；Codex 的 hook 要同事手動信任才會跑，Antigravity 不跑。結果整個試點期間，使用者明確要求的 UJ-3 完全不會被驗證。
- **guard_snippet**：定義誤報的判定方式：靜默期每週在週報列出命中的情境摘要，讓同事勾「這時候建議有用／沒用」，或由維護者抽樣自己的紀錄標註；靜默期照樣跑 FR-19 的頻率關卡，記下「本來會顯示」的那一則；寫下打開提示的門檻（例如每條規則的精確率不低於 X、每人每週本來會顯示的不超過 Y 則）；MVP 加一個本機匯出指令，產生去識別的命中統計；記錄 hook 實際有在跑的比例。
- **potential_consequence**：檢討會只能憑感覺決定：主動建議要嘛永遠不開，要嘛帶著未知的誤報率直接開，兩者都達不到「比 Claude Code 做得更好」的要求。

### 三、通知與主動建議

#### ADV-10

- **lens**：adversarial
- **location**：prd.md FR-16（:308、:311）、FR-19（:354）、SM-C2（:599）；engine/scripts/session_nudge.py:5-11；docs/v2/research/recommend.md:686
- **trigger_condition**：三處上限互相不一致：FR-16 換工具通知每人每週 1 則、FR-19 工作中建議每週 3 則、SM-C2 卻說「通知次數每人每週最多 1 則」；FR-19 的「全部合計」包不包含 FR-16 與其例外沒有說。現有 session_nudge.py 已經會在每跨過 100k tokens、git push 之後印提醒，也佔同事的注意力，卻不在預算內。Claude Code 本身已會標「Not used recently」，研究要求 OmniKit 不重複提同一件事（recommend.md:686），PRD 沒寫進需求。
- **guard_snippet**：定一張跨類型的總預算表：換工具通知、工作中建議、開新對話提醒、停用建議各自的上限與合計上限，寫明安全事件例外是否計入；FR-13、FR-15 加「平台已經提示過的不重複提，只補另外兩個 agent 的狀況與替代品」。
- **potential_consequence**：實作時各自挑一個數字，同事一週可能看到 4 則以上 OmniKit 訊息，再加上平台自己的訊息，正好踩中風險表裡的「同事被通知打擾」。

#### ADV-11

- **lens**：adversarial
- **location**：prd.md FR-19（:357-358）、UJ-3（:66-67）、FR-20（:361-368）、§6.2（:569）；docs/v2/research/recommend.md:669-671
- **trigger_condition**：hook 印的 `systemMessage` 只給人看、模型看不到；使用者回「OmniKit 裝 X」或「不要再建議」時，agent 不知道他在回應哪一則，而處理這句話的 skill（FR-20）延到 v2.1。「沒回應」怎麼判定（下一則 prompt 沒提到？session 結束？）沒有定義。研究寫的是「連續 5 次沒回應或拒絕」與「同一工具沒回應 2 次後只留在週報」，PRD 改成「累計 5 次就全部靜音」，又漏掉後者；在每週最多 3 則的上限下，大約兩週就會永久靜音。
- **guard_snippet**：明定回應的擷取方式（例如 UserPromptSubmit hook 比對固定句型，或 MVP 就提供一個只處理「OmniKit 裝 X」「OmniKit 不要再建議 X」的小 skill）；「沒回應」定義為「顯示後同一個 session 內沒有出現對應句型」；靜音規則改回「連續 5 次」，補回「同一工具沒回應 2 次只留週報」；靜音時告訴使用者怎麼重新打開。
- **potential_consequence**：拒絕與沒回應的資料不可靠，FR-21 依錯的資料停用規則；或整個功能在試點兩週內就把自己靜音。

#### ADV-12

- **lens**：adversarial
- **location**：prd.md FR-18（:338）、FR-16（:306）、FR-27（:457）；docs/v2/research.md:125；data/tools/chrome-devtools-mcp.yaml
- **trigger_condition**：FR-16 規定只有 E4 才主動通知，研究也寫「只主動提實測勝出的工具」，但 FR-18 允許主動建議「預設或試用中」的工具。試用不等於 E4：現在唯一的試用 chrome-devtools-mcp 是 U1 打平（兩端都 4 分）後由維護者自己選的；預設裡也有 bmad 這種沒有實測的。
- **guard_snippet**：FR-18 的條件改成「證據等級 E4」（E3 只在使用者明確詢問時出現）；工具卡用欄位區分「實測勝出進試用」與「維護者自選試用」。
- **potential_consequence**：工作中跳出的建議其實沒有證據，跟產品主張衝突；FR-21 的接受率也混進不同品質的建議，自我檢討的結論失真。

#### ADV-13

- **lens**：adversarial
- **location**：prd.md FR-14（:281）、FR-15（:286）、FR-16（:305）、FR-18（:346）、FR-21（:376）、§3 週報（:97）、§4.2 說明（:143）；engine/skills/omnikit-setup/SKILL.md:46；engine/skills/omnikit-eval/scripts/digest.py:8-13
- **trigger_condition**：停用建議、上游新版、E2 與 E3、Antigravity 的建議、接受率都只出現在「週報」；但週報目前是 omnikit-eval skill 的手動指令（說「每週彙整」才產生），而訪談第 5 題選「先不要」就不裝 omnikit-eval，「也沒有每週彙整」。PRD 說訪談「沿用現有的 6 題」，等於讓最典型的同事（不想研究工具的人）自己關掉整個「只留有用的」迴路。週報什麼時候產生、出現在哪裡，以及 MVP 裡 E4 通知走什麼管道（session 開頭的顯示屬於延後的 FR-18、FR-19），都沒有寫。
- **guard_snippet**：新增 FR：使用者面的週報跟 omnikit-eval 脫鉤，每台都裝；定義觸發方式（例如 SessionStart hook 每 7 天提示一次「說『OmniKit 週報』」）與輸出位置；第 5 題只控制「評估新工具」，不影響週報；明寫 MVP 中 E4 通知的送達管道。
- **potential_consequence**：多數同事裝完之後再也看不到任何停用或替換建議，SM-1、SM-2 沒有資料，「OmniKit 持續幫他把關」不成立。

### 四、更新、同步與還原

#### ADV-14

- **lens**：adversarial
- **location**：prd.md §5 非目標（:546）、FR-7（:191）、FR-9（:227）、FR-10（:231）、FR-33（:531）；engine/scripts/install.ps1:23；.githooks/post-merge、.githooks/post-commit、.githooks/sync-data.sh:26-56
- **trigger_condition**：install.ps1 會把同事的 repo 設成 `core.hooksPath=.githooks`；之後每次 `git pull`（post-merge）只要動到 data/rules、data/profiles、data/mcp、data/harness 或相關腳本，就在背景自動改規則、重裝 skills、寫 MCP、補 Claude 的免問權限、改 hook，不經預覽也不問。PRD 完全沒提這個機制，也沒要求改掉。
- **guard_snippet**：同事版不設 .githooks（只有維護者需要）；pull 之後只提示「有 N 項變更，說『OmniKit 更新』預覽」，套用一律走 FR-7 的計畫與一次確認；FR-7 加可測結果「git pull 不會改動任何 agent 的設定」。
- **potential_consequence**：維護者一次 push 就能在所有同事的 agent 新增 MCP 與免問權限，直接違反「不在沒有使用者確認的情況下安裝」；遇到 FR-10 的衝突時，git hook 也沒辦法「停下來問」，只會在 pull 的輸出裡默默失敗。

#### ADV-15

- **lens**：adversarial
- **location**：prd.md §5（:547）、§9.4（:625）、FR-14（:281）、UJ-2（:62）
- **trigger_condition**：新的預設、E4 結果、退役決定都在維護者的 repo；同事端要知道，只能自己 `git pull`。PRD 同時規定「不自動更新」「除了使用者明確執行的步驟，不連網」，卻沒有任何 FR 定義 OmniKit 本身與名冊怎麼更新、多久一次、由誰觸發、更新前怎麼預覽。FR-14 的「上游有新版時，週報能列出」也要連網查上游。
- **guard_snippet**：新增 FR「更新 OmniKit」：使用者說「OmniKit 更新」才連網抓取，先列出名冊與腳本的差異（含新的 E4、退役、安全通報）再套用；週報顯示「名冊已經 N 天沒更新」；同事追維護者發佈的版本 tag，不直接追 main。
- **potential_consequence**：UJ-2 的「一個月後收到更好的選擇」不會發生（同事根本沒 pull）；或發生時伴隨 ADV-14 的靜默改動。

#### ADV-16

- **lens**：adversarial
- **location**：prd.md FR-16 例外（:311）、§9.1（:606-608）
- **trigger_condition**：「現任或試用中的工具出現安全事件…立即通知」需要一條把消息送到同事電腦的管道，但 OmniKit 不連網、不常駐、也沒有推送；偵測安全事件的第 0 層又是維護者端手動跑。整份 PRD 沒有「緊急停用」的機制。
- **guard_snippet**：定義安全事件流程：維護者在工具卡標 `revoked` 並附原因；同事下次更新（ADV-15）時第一個顯示，並預設勾選停用；另外在 README 寫不靠 OmniKit 也能做的手動停用步驟，由維護者直接通知試點同事；把「立即」改成做得到的時限描述。
- **potential_consequence**：一個被入侵的 MCP 或 hook 會在同事電腦上一直執行，直到他哪天剛好 pull；文件承諾「立即」卻做不到，出事時難以交代。

#### ADV-17

- **lens**：adversarial
- **location**：prd.md FR-7（:195-196）；addendum.md A.1（:12-13）；engine/scripts/usage.py:10-11
- **trigger_condition**：計畫的 revision 是「各檔的雜湊」，但 `~/.claude.json` 會被 Claude Code 自己持續寫入（usage.py 讀的 skillUsage 就存在裡面），Codex 也可能在信任專案等操作時改 `config.toml`。安裝流程本身就在 Claude Code 對話裡執行，預覽到安裝之間這些檔案幾乎一定會變。
- **guard_snippet**：revision 只算受管項目的雜湊（例如 `mcpServers.<名稱>` 正規化後的 JSON、受管區塊內容、特定 TOML 表格），不算整個檔案；`--check` 也只比受管項目，並分開「agent 自己改的欄位」與「使用者改了受管內容」。
- **potential_consequence**：安裝永遠停在「請重新預覽」，或實作者為了過關把這個檢查拿掉；`--check` 每週都報「設定被手動改過」，誤報讓使用者忽略真正的變更。

#### ADV-18

- **lens**：adversarial
- **location**：prd.md FR-9（:226）、FR-17（:321）；addendum.md A.1（:17）
- **trigger_condition**：FR-9 說「一項失敗不會中斷整批」，附錄 A.1 說「有衝突就整批不寫」。安裝到一半才發現衝突（例如寫到第 3 個 MCP 才發現被改過）要怎麼辦沒有定義；部分成功時帳本與 lock 記什麼、要不要回復也沒寫。
- **guard_snippet**：明定兩階段：先完成全部衝突檢查，期間不寫任何東西，有衝突就整批不寫；通過後才執行，個別項目執行失敗不中斷，但帳本只記實際成功的項目，結尾列出可重跑的指令；寫入前先存還原紀錄（docs/v2/research/sync.md §8 第 7 點的 journal 做法）。
- **potential_consequence**：設定停在半套狀態，帳本跟實際不符；之後的換回（FR-17）與 doctor 都依錯的帳本判斷。

#### ADV-19

- **lens**：adversarial
- **location**：prd.md FR-10（:231）、FR-15（:290-292）、FR-17（:321）；engine/scripts/install.ps1:20；data/harness/claude-allow.txt
- **trigger_condition**：「換回之後設定與替換前一致（依帳本比對）」只涵蓋 OmniKit 寫的檔案：原生 `claude plugin install`、`codex plugin add` 產生的 plugin 快取與 agent 內部狀態不在帳本；Claude 的免問權限是「只增不刪」；記憶與交接槽位的工具（例如 claude-mem）累積的資料，換掉就沒了。FR-15 還要停用「跟帳號同步的 plugin」，那不是 OmniKit 的東西，跟 FR-10「只動自己管理的內容」衝突，帳本也沒有記錄這類經使用者同意的改動。
- **guard_snippet**：FR-17 的可測結果改成列舉範圍（規則、MCP、skills、權限、hooks、plugin 啟用狀態），並把權限規則納入帳本；有狀態的工具在預覽標「換掉會遺失 <資料>」，提供匯出；FR-10 加一條：對非 OmniKit 項目的改動記成「使用者同意的外部改動」，可以單獨還原。
- **potential_consequence**：同事以為一句話就能換回，實際上權限殘留、記憶資料遺失或帳號 plugin 狀態錯亂；信任只要破一次就回不來。

#### ADV-20

- **lens**：adversarial
- **location**：prd.md FR-9（:224）、FR-14（:281）、FR-16（:310）、FR-26（:449）、§5（:547）
- **trigger_condition**：FR-14「跨大版本更新要使用者同意」暗示小版本可以不問就更新，跟「版本一律釘選」「不自動更新」「不在沒有確認的情況下安裝」衝突；FR-16 又說「跨 minor 版本就降一級」，把小版本當成會讓證據失效的變化。名冊多數工具只能釘 git SHA，沒有 semver，「minor」無從判斷。證據滿 90 天就降級，代表每個預設每季都要重測，這個量沒有算進 FR-26 的額度。新版的能力揭露（hook、遙測）也沒有規定要重新檢查。
- **guard_snippet**：規定所有版本變更（含 patch）都要使用者同意，並重跑 1c 的能力揭露差異；只釘 SHA 的工具改用「上游變更範圍」（例如動到 hooks、manifest 或可執行檔）決定是否降級；FR-26 的額度保留回歸重測的份額。
- **potential_consequence**：實作者照 FR-14 做靜默的小版本更新，新版加了 hook 或遙測也沒人看到；或證據每 90 天全面過期，預設一夕之間全部降級，推薦清單清空。

#### ADV-21

- **lens**：adversarial
- **location**：prd.md FR-13（:270-273）、FR-15（:286）；engine/scripts/usage.py:285-292
- **trigger_condition**：usage.py 的 `judge()` 只要沒比對到任何 session 就判「unused」，不管解析器是不是其實什麼都沒讀到。Claude Code、Codex 或 Antigravity 改了對話紀錄的格式（例如 Skill 工具呼叫的 JSON 形狀），所有工具會一起變成「沒在用」。
- **guard_snippet**：FR-13 加可測結果：某個 agent 在統計期間有 N 個 session、卻解析出 0 次叫用時，那個 agent 的結果整批標「未知（解析失敗）」，不產生停用建議；selftest 加一筆「格式改了」的 fixture。
- **potential_consequence**：某次 agent 自動更新之後，週報建議同事停用全部工具；同事照做，或從此不信任週報。

### 五、安裝與相容

#### ADV-22

- **lens**：adversarial
- **location**：prd.md FR-5（:163-164）、FR-9（:224）、UJ-2（:63）；engine/scripts/build.py:14、67-68；data/tools/find-skills.yaml、rtk.yaml；docs/v2/research.md:37
- **trigger_condition**：marketplace 只收狀態是 default、而且卡片有 plugin 來源的工具；整個名冊只有 3 張卡（frontend-design、rea、skill-creator）有釘選來源。FR-5 讓試用與「社群推薦（未實測）」的待評估工具出現在預覽、可以從「逐項調整」勾選，UJ-2 要把 E4 的挑戰者裝進試用，但這些工具都沒有釘選來源，FR-9「版本一律釘選並比對雜湊」做不到。三個沒有預設的 active 槽位會列出 rtk（用 hook 攔所有 shell 指令）、find-skills（卡片沒有 url、沒有 kind；研究指出 skills CLI 的 find 會把查詢字串連同遙測送出去）這類沒過第 0 層的工具。
- **guard_snippet**：只有通過第 0 層、卡片有釘選來源的工具才能出現在可勾選清單；待評估工具在預覽只列名稱與「未審查」，不能從預覽安裝；marketplace 改成收 default 與 trial，build 時檢查 trial 一定有釘選來源。
- **potential_consequence**：同事以為「社群推薦」經過 OmniKit 把關，結果裝了沒審查的 hook 或會外送查詢的工具，違反 §9.1、§9.2，FR-9 的釘選承諾也破功。

#### ADV-23

- **lens**：adversarial
- **location**：prd.md FR-5（:168）、FR-9（:220）；addendum.md A.3（:37-43）；engine/scripts/agents.py:146-147、322-324、359-367；data/tools/bmad.yaml；docs/v2/prd/.memlog.md:3
- **trigger_condition**：附錄 A.3 說「skills 與 MCP 沿用 agents.py」，但 agents.py 只會裝 OmniKit 自己的 `engine/skills`，MCP 只讀全域的 data/mcp/servers.yaml（每台都一樣）；它沒有依工具卡抓上游、依個人工具包挑選的能力。名冊種類分布是 collection 16、app 13、service 9、mcp 8、cli 7、library 2、rules 1、沒填 25，plugin 只有 9。預設 bmad 是 collection、沒有 plugin 來源，BMAD 又是裝在專案目錄的框架（memlog:3「BMAD 沒裝進這個 repo」），跟 OmniKit 只做全域的方式不合。service 類（exa、tavily、firecrawl、composio 等）還要帳號與金鑰，並把資料送到第三方。
- **guard_snippet**：FR-9 依 kind 列出支援的安裝方式，以及不支援時怎麼呈現（例如 app、service、library 只給手動安裝說明，不預先勾選）；工具包的 MCP 改由 lock 產生、每人不同，不再用全域 servers.yaml；service 類一律不預先勾選，預覽另標「資料會送到 <服務>」並要求單獨同意；附錄 A.3 如實寫出要新增的能力（抓上游、釘選、雜湊、移除）。
- **potential_consequence**：開發時才發現一半以上的候選沒有安裝路徑，FR-5 的「最多 5 個」實際上只剩 1、2 個能裝；或臨時讓 LLM 照 README 安裝，違反「不讓 LLM 直接寫設定檔」。

#### ADV-24

- **lens**：adversarial
- **location**：addendum.md A.3（:41）、A.4（:53）；prd.md FR-11（:247）、FR-15、FR-32（:518-522）；engine/scripts/agents.py:16、93-95、298-304；docs/v2/research/sync.md:437、562
- **trigger_condition**：agents.py 把 Antigravity 的 skills 放在跟 Codex 共用的 `~/.agents/skills`，附錄 A.3 卻寫用「檢查 `~/.gemini/config/skills`」驗證，兩個位置不同；agy（Antigravity CLI）讀不讀 `~/.agents/skills`，研究也還沒實測。附錄 A.4 的 Antigravity 停用方式「移除 OmniKit 放的複製品」，會讓 Codex 同時失去那個 skill，因為是同一個資料夾。
- **guard_snippet**：FR-32 補上 Antigravity skills 位置的偵測與實測結論（IDE 與 agy 分開）；驗證檢查的位置必須等於實際寫入的位置，而且要能證明 Antigravity 真的讀到（做不到就標「未知」）；要能單獨停用 Antigravity，就改放 Antigravity 專屬的位置；共用資料夾的項目在預覽標明「會同時影響 Codex」。
- **potential_consequence**：Antigravity 的驗證要嘛永遠失敗，要嘛只證明檔案存在卻沒被讀到；同事在 Antigravity 停用一個工具，Codex 也跟著少一個。

#### ADV-25

- **lens**：adversarial
- **location**：prd.md §1（:26）、FR-5（:166）、FR-18（:338、:346）、§6.2（:569）、§10 第 7 題；engine/schema/tool.schema.json:26-30、35-63
- **trigger_condition**：核心主張是「三個 agent 一致」，但工具卡 schema 的 `works_with` 只允許 claude、codex，plugin 來源也只有 claude、codex；116 張卡有 72 張沒填 works_with。FR-5、FR-18 的「相容這台／目前的 agent」對 Antigravity 沒有資料可判斷。FR-18 說 Antigravity 第一階段「只在週報與使用者明確詢問時建議」，但明確詢問（FR-20）整個延到 v2.1，週報又可能不存在（ADV-13）。
- **guard_snippet**：FR-28 把 `works_with` 與安裝方式擴成三個 agent，沒填就當「未知」並在預覽標示；§6 加一張「各 agent 在 MVP 支援哪些功能」的矩陣；試點名單裡若有只用 Antigravity 的同事，事先說明限制，或把 FR-20 的「只查名冊」部分提前進 MVP。
- **potential_consequence**：只用 Antigravity 的同事在 MVP 幾乎拿不到任何推薦與通知，卻被算進 SM-1 到 SM-3 的分母；「三個 agent 一致」在第一次試點就被證偽。

#### ADV-26

- **lens**：adversarial
- **location**：prd.md FR-1（:111-116）、FR-2（:120-128）、§9.4（:625）；addendum.md A.5（:60）；engine/scripts/install.ps1:7、11、23；engine/scripts/codex_hooks.py:12
- **trigger_condition**：環境掃描在安裝之後才跑，但安裝本身就需要：git、從 GitHub release 下載 uv、gh、gitleaks、npm 全域安裝 MCP 套件、uv 依腳本標頭從 PyPI 解析相依套件（agents.py、digest.py 都要 pyyaml 與 jsonschema）、PowerShell 執行原則允許跑 .ps1。依 codex_hooks.py:12 的註解，Codex 在 Windows 用 `pwsh` 跑 hook，而 Windows 11 預設只有 PowerShell 5.1。FR-2 對 proxy 只「看名稱」，沒處理 proxy 與憑證設定；hook 每回合用 `uv run --script`，uv 快取被清掉時會在 hook 裡連網，跟 §9.4「不連網」衝突。
- **guard_snippet**：FR-1 加「安裝前檢查」：用 PowerShell 5.1 內建功能先查執行原則、git、Node、pwsh，以及到 github.com、registry.npmjs.org、pypi.org 的連線，任何一項不過就停下並給具體處理方式；hook 腳本保持沒有外部相依，並用 `--offline` 或預先建好的環境執行；§9.4 逐項列出哪些步驟會連網。
- **potential_consequence**：同事卡在 install 第一步、看到一串英文錯誤；或裝好了但 Codex 的 hook 從來沒跑過，靜默記錄缺一半資料也沒人發現。

#### ADV-27

- **lens**：adversarial
- **location**：prd.md §11 防毒列（:646）、FR-5（:166）、FR-18（:345）、§9.4（:626）；engine/scripts/agents.py:10-11；這台實測 Get-AuthenticodeSignature：PATH 上的 %LOCALAPPDATA%\hermes\bin\uv.exe 與 install.ps1 裝的 %LOCALAPPDATA%\Programs\gitleaks\gitleaks.exe 都是 NotSigned；docs/v2/research/sync.md:566
- **trigger_condition**：對策寫「不用沒簽章的背景程式」，但 OmniKit 每回合的 Stop hook 都在背景啟動沒簽章的 uv.exe，安裝也放了沒簽章的 gitleaks（同事不 commit 根本用不到）。Trend Micro 的允許通知要剛好盯著畫面才按得到（agents.py:10-11），hook 在背景被擋時照 FR-18「安靜結束」，沒有人會知道。「已知阻擋」以防毒產品名稱為鍵，但同一套產品在不同政策下行為可能不同。
- **guard_snippet**：把「uv 在 Trend Micro 下能不能穩定放行」列為試點前的實測項目（研究也說只能在同事電腦上觀察）；同事版不裝 gitleaks 與 gh；hook 失敗寫進本機錯誤計數，doctor 與週報顯示「hook 最近 7 天失敗 N 次」；`blocked_on` 記錄觀察到的機器、日期與現象，不只記產品名。
- **potential_consequence**：試點中 hook、掃描或 MCP 被擋卻無聲無息，靜默記錄與使用統計都缺資料，檢討時把「被擋」誤判成「沒用」。

#### ADV-28

- **lens**：adversarial
- **location**：prd.md FR-18（:334、:345）、FR-19、§2.1（:36）；addendum.md A.5（:63-65）；engine/scripts/codex_hooks.py:85-86
- **trigger_condition**：每個回合結束都要啟動 uv 與 Python、讀新增的 transcript、比對訊號、寫狀態檔；Codex hook 的 timeout 是 10 秒，防毒掃描還會再拉長。PRD 說「不會拖慢 agent」，卻沒有延遲預算。Claude Code 與 Codex 同時開著時，兩邊的 hook 會同時寫同一份頻率與靜音狀態（三個 agent 共用），沒有鎖定或原子寫入的要求；防毒短暫鎖檔也會讓寫入失敗。
- **guard_snippet**：加非功能需求：hook 的 p95 延遲上限（例如 1 秒），超過就跳過這次比對；狀態檔用檔案鎖，加「寫暫存檔再取代」（規則檔要保留硬連結的限制不適用於狀態檔）；selftest 加「兩個 hook 同時寫」的案例。
- **potential_consequence**：每回合多等幾秒，同事覺得 OmniKit 拖慢 agent；狀態檔互相覆蓋，靜音設定或頻率計數遺失，同一則建議重複出現。

#### ADV-29

- **lens**：adversarial
- **location**：prd.md §11 平台改版列（:644）；addendum.md A.3（:40）、A.4（:51）、A.5、A.6（:74）
- **trigger_condition**：幾個關鍵行為只在某一天、維護者這台試過，或只來自別人的文件：Codex 帳號同步 plugin 的 `[[skills.config]]` 停用（2026-11-04 實測一次）、`codex plugin add --json`（引用 ECC 的文件）、`claude plugin eval`（未實測）、Codex 工具核准紀錄的位置（研究推論）。Claude Code 會自動更新，同事的版本不會跟維護者一致。風險表的對策只有「位置偵測、doctor、記錄實測日期」，沒有版本閘門。
- **guard_snippet**：新增需求：每個會寫入的功能記錄「已驗證的 agent 版本範圍」；偵測到範圍外的版本時，該功能降級為只預覽、不寫入，並在 doctor 標示；維護者每次升級 agent 先跑 selftest 與 doctor，再更新範圍。
- **potential_consequence**：某次 Claude Code 或 Codex 更新後，停用、驗證或 hook 輸出悄悄失效或寫錯位置，同事看到的是「OmniKit 壞了」。

### 六、隱私與安全

#### ADV-30

- **lens**：adversarial
- **location**：prd.md FR-5（:163）、FR-33（:531）、§9.1（:607）；data/mcp/servers.yaml:7-25；data/harness/claude-allow.txt:4-5；data/tools/chrome-devtools-mcp.yaml:6、13
- **trigger_condition**：試用中的 chrome-devtools-mcp 寫在全域的 servers.yaml，targets 是三個 agent，install.ps1 會裝到每一位同事；Codex 設 `default_tools_approval_mode: approve`，Claude 的權限清單加 `mcp__chrome_devtools` 免問，依據是「使用者同意免問（2026-11-04）」，也就是維護者本人的同意。試用到 2026-11-18 到期，沒有到期自動處理的機制。
- **guard_snippet**：同事版不套用維護者的 servers.yaml 與 claude-allow.txt；MCP 與免問權限改由個人工具包的計畫產生，試用工具預設不勾選，免問要在預覽單獨同意；試用到期後在下一次預覽列為「到期，建議移除」。
- **potential_consequence**：每位同事在不知情的情況下多了一個自動核准、能開任意網頁並執行 JavaScript 的瀏覽器工具（遇到網頁裡的提示注入時沒有人工把關），每回合還多載入它的工具定義；同時違反 FR-5、FR-33 與 SM-3。

#### ADV-31

- **lens**：adversarial
- **location**：addendum.md A.5（:60）；prd.md §9.1（:607）；.githooks/sync-data.sh:42-56
- **trigger_condition**：附錄刻意讓 Codex hook 的指令字串固定，「邏輯放在腳本裡，更新腳本不用重新信任」，等於繞過 Codex 用來偵測 hook 變更的信任機制；Claude Code 的 hook 本來就沒有信任步驟。再加上 ADV-14 的 pull 自動同步，repo 上任何對 hook 腳本的修改（包括維護者帳號被盜、誤合併的 PR）都會在所有同事電腦的每個回合直接執行。
- **guard_snippet**：由 OmniKit 自己做信任：hook 啟動時比對腳本雜湊與使用者上次同意的雜湊，不符就只印「OmniKit hook 已更新，說『OmniKit 更新』檢視差異」，不執行新邏輯；或把腳本雜湊放進指令字串，讓 Codex 的重新信任自然觸發。
- **potential_consequence**：一次惡意或錯誤的提交，就成為對全體試點同事的程式碼執行管道，而且 Codex 不會再提醒任何人。

#### ADV-32

- **lens**：adversarial
- **location**：prd.md FR-1（:115）、FR-29（:487-491）、FR-30（:495-500）、§6.1（:563）、§9.2（:613）；.githooks/pre-commit:1-2（「這個 repo 是公開的」）；data/evals/2026-11-04-frontend-design-F1/（x.patch、y.patch、votes/*.png）
- **trigger_condition**：回流與提案走 GitHub issue 或 PR，而 repo 是公開的：內容會公開，而且綁著 GitHub 帳號，談不上匿名；3 到 5 人的試點，工具組合本身就能認出是誰。FR-30 的「實測結果」照現有格式會含 patch、截圖與情境文字，同事工作專案的內容可能因此公開。FR-1 允許沒有 GitHub 帳號，MVP 卻只有 GitHub issue 範本，這些同事沒有任何回流管道。
- **guard_snippet**：MVP 的回流改成「本機匯出檔，交給維護者的非公開管道（例如共用資料夾）」，GitHub 只當選配；匯出前自動檢查不含路徑、專案名稱、程式碼片段與圖片，預覽給同事確認；FR-29 拿掉「匿名」，改成如實說明「去識別，但小樣本仍可能被認出」；FR-30 的實測結果只收結論與數字。
- **potential_consequence**：同事的工具使用狀況與工作內容出現在公開網路上；回流機制一出事就會被叫停，維護者的資料來源（UJ-4）也跟著斷掉。

#### ADV-33

- **lens**：adversarial
- **location**：prd.md FR-4（:153）、FR-30（:495）；.gitignore；engine/skills/omnikit-setup/SKILL.md:104；engine/scripts/scan.py:72-92、180
- **trigger_condition**：同事的 profile、answers.json、scenarios.yaml（含主要專案名稱與工作背景）都寫在 clone 下來的公開 repo 的 `data/profiles/<名稱>/`，.gitignore 沒有排除；profile 名稱還是從 git user.name 或登入帳號推出來的。同事照 FR-30 開 PR 時，一個 `git add -A` 就會把它們送上公開 repo；上游哪天新增同名的 profile，同事的 `git pull` 會因為未追蹤的檔案而失敗。
- **guard_snippet**：個人資料改存 %LOCALAPPDATA%\omnikit\profiles\（repo 只放範本），或至少把 default 與範例以外的 `data/profiles/*` 列進 .gitignore；FR-30 的提案用產生器輸出單一檔案，不讓同事直接在這個 repo 開 PR。
- **potential_consequence**：個人背景與專案名稱外洩；更新時 pull 失敗，同事卡在舊版又不知道原因。

#### ADV-34

- **lens**：adversarial
- **location**：prd.md FR-3（:136）、FR-18（:334-344）、§9.2（:612）；docs/v2/research.md:105-111
- **trigger_condition**：FR-3 承諾「沒勾選的專案不會被讀取」，但 FR-18 的訊號要從所有 session 的對話紀錄抽取（讀了哪些檔、跑了哪些指令、使用者說了「不是叫你改這個」），等於讀取所有專案的工作內容，包括沒勾選的；FR-18 沒有任何同意或關閉的要求，而 MVP 的靜默記錄會對每位同事預設開啟。
- **guard_snippet**：FR-18 加：第一次啟用前取得同意，可以限定只看 FR-3 勾選的專案；提供一個「關閉工作中比對」的開關；狀態檔與紀錄只存規則 id 與次數，不存路徑、檔名或原文片段，並寫成可測結果。
- **potential_consequence**：同事發現 OmniKit 在背景讀自己全部的對話紀錄，會覺得被監看，跟「掃描結果只留在本機、只拿來預選」的說法不一致，可能因此退出試點。

#### ADV-35

- **lens**：adversarial
- **location**：prd.md FR-24（:420-425）、FR-25（:439）；addendum.md A.6（:74）；docs/v2/research/eval.md:142、642
- **trigger_condition**：「隔離環境」「乾淨的環境」在原生 Windows 沒有沙箱可用；研究說要給 shell 權限的套件得在 WSL2 跑，但這台有沒有 WSL2、效能如何都沒驗證。乾淨的 HOME 代表沒有登入狀態：要嘛複製憑證檔（跟底線「不碰金鑰」衝突），要嘛根本跑不起來。FR-24 也沒規定程式碼審查要在安裝執行之前，待評估的 hook 與 MCP 會先在維護者的公司電腦上跑起來。
- **guard_snippet**：FR-24 改成：有 hook、MCP 或可執行程式的工具先做靜態審查，通過才安裝；隔離方式明定（WSL2、Windows Sandbox 或拋棄式 VM 擇一），列為階段 0 的第一個驗證項；登入改用各 agent 支援的環境變數或專用測試帳號，不複製使用者的憑證檔。
- **potential_consequence**：評估漏斗的第 1c、2 層要嘛做不出來（時程崩盤），要嘛在沒有隔離的狀態下執行沒審查的第三方程式。

#### ADV-36

- **lens**：adversarial
- **location**：prd.md FR-12（:253-258）、UJ-1（:58）、FR-8（:208）
- **trigger_condition**：第一次成功要「在他的真實專案上實際跑一次」，但沒有限制只能用唯讀的工具、沒有要求在分支或 worktree 上跑，也沒有事先說會花多少 token；FR-8 自己就把「會不會改原始碼」列為要揭露的能力。
- **guard_snippet**：FR-12 加：只挑能力揭露為「不改原始碼」的工具，或在暫存 worktree 執行，結束時只顯示結果與 diff；執行前顯示預估的 token 與時間，取得同意。
- **potential_consequence**：同事第一次用就被改了工作專案的程式碼，或用掉一大段額度，第一印象從驚喜變成驚嚇。

#### ADV-37

- **lens**：adversarial
- **location**：prd.md FR-33（:526-531）、§9.1（:606）；docs/v2/research.md:40
- **trigger_condition**：profile 是自然語言的 AGENTS.md，「放寬底線」（例如寫「push 不用問我」）沒辦法用名冊驗證這類腳本可靠判斷；研究建議先從權限、MCP、hooks 這些結構化欄位做。「權限、MCP 與 hooks 預設拒絕」也沒說清楚對象：是只限 OmniKit 要寫入的項目，還是連同事原本自己裝的 MCP 與 hook 都要拒絕（後者跟 FR-10「只動自己管理的內容」衝突）。
- **guard_snippet**：FR-33 拆成兩條可測結果：結構化欄位（權限、MCP、hooks）用 deny 優先的程式檢查；自然語言部分改成「profile 不能刪除或改寫底線檔的條目，新增的內容在預覽標示並由使用者確認」。「預設拒絕」限定為「OmniKit 要寫入的第三方項目」。
- **potential_consequence**：要嘛寫出誤判一堆的關鍵字檢查，讓同事的 profile 套不上；要嘛宣稱有程式檢查卻擋不住真正的放寬；若解讀成連既有 MCP 都拒絕，還會誤動同事原本的設定。

### 七、可測性與其他

#### ADV-38

- **lens**：adversarial
- **location**：prd.md FR-4（:147-153）、UJ-1（:49-59）、FR-2（:120）、FR-3（:132）、FR-11（:248）、FR-12；engine/skills/omnikit-setup/SKILL.md:52；docs/v2/research/eval.md:100
- **trigger_condition**：「最多 6 題加 1 次確認」跟流程實際的互動次數不符：環境掃描同意、專案勾選、6 題、照建議或逐項調整、profile 名稱確認（現行 SKILL.md:52）、預覽確認、煙霧測試同意、第一次成功、Codex 信任 hook、開新 session。「二十分鐘內」在研究裡沒有任何依據，第 2 層的重題一次就要約 16 分鐘（eval.md:100）。
- **guard_snippet**：FR-4 改成列出完整的互動清單與上限（例如必答 8 次以內）；新增量測「從 clone 到第一次成功的時間」，在試點第 1 週隨訪時實測，再決定 UJ-1 要承諾幾分鐘。
- **potential_consequence**：驗收時 FR-4 無法判斷有沒有通過；同事照 UJ-1 期待 20 分鐘，實際花 40 分鐘以上，覺得被騙。

#### ADV-39

- **lens**：adversarial
- **location**：prd.md FR-34（:535-540）、§9.4（:623）
- **trigger_condition**：GitHub 的 windows-latest 是英文系統語系，要換成 cp950 得改系統地區設定並重開機，CI job 裡做不到（`chcp 950` 只改主控台字碼頁）；runner 上的是 Defender，不是 Trend Micro，「被防毒短暫鎖住會重試」與「被防毒擋下」都測不到。
- **guard_snippet**：FR-34 拆成：CI 做得到的（PowerShell 5.1 與 7、含空白與長路徑、模擬檔案鎖的單元測試、`PYTHONIOENCODING` 與主控台字碼頁）；以及試點前在至少 1 台同事規格的公司電腦上跑的「驗收清單」（cp950 系統語系、Trend Micro、非系統管理員帳號）。
- **potential_consequence**：CI 全綠讓人以為 Windows 相容性已經驗證，問題到同事電腦上才爆出來。

#### ADV-40

- **lens**：adversarial
- **location**：prd.md FR-22（:403）、FR-26（:447）；addendum.md A.6（:72）；docs/v2/research/eval.md:221、639
- **trigger_condition**：「爆紅」要算「近期星數成長速度是平均的 3 倍以上」，但 stargazers 清單已不開放，只能用事件 API 最近 300 個事件裡的 WatchEvent；研究自己說很活躍的 repo，這個窗口可能只有幾小時、雜訊大。這個旗標卻會影響排程（延後一輪）。
- **guard_snippet**：爆紅旗標只當「提示人工看」，不影響排程；或改成第 0 層每週記一次 stargazers_count 快照，自己算成長率，資料不足時標「未知」。
- **potential_consequence**：熱門工具因為幾小時的事件窗口被誤標爆紅，實測一再延後；或反過來漏掉真正的灌星。

## 原始 JSON

```json
[
  {
    "id": "ADV-01",
    "lens": "adversarial",
    "location": "prd.md §1 願景（:26）、UJ-2（:62）、FR-25（:438）；data/profiles/ryan/scenarios.yaml；data/evals/2026-11-04-browser-u1.md",
    "trigger_condition": "通知文案寫「X 在你的情境實測勝過 Y」，但第 2 層實測只在維護者這台、用 ryan 的 CatOS／OmniKeep 情境、維護者的模型與帳號跑（U1 的測試對象就是 CatOS 前端副本）；同事的情境、模型與 harness 從來沒被測過。",
    "guard_snippet": "通知與預覽的證據欄改成「在維護者情境（<情境 id>、<agent 與模型>、<日期>）勝出」，並列出跟這位同事的差異（agent、模型、專案類型）。若要保留「你的情境」的說法，新增需求：同事端可跑的縮小版驗證（例如在他勾選的專案上跑 1c 煙霧測試），通過才可使用這個措辭。",
    "potential_consequence": "違反安全底線的「誠實回報」；同事照建議換了工具卻感受不到差異，SM-2 的換回率上升，「有證據才建議」這個核心定位失去可信度。"
  },
  {
    "id": "ADV-02",
    "lens": "adversarial",
    "location": "prd.md FR-5（:169）、§6.1（:558）、§7 階段 0（:579）、§10 第 4 題；docs/v2/brief/addendum.md:27、30、32、34；data/tools/bmad.yaml、rea.yaml、skill-creator.yaml",
    "trigger_condition": "現有需要安裝的預設裡，bmad 的理由是「第一輪既定的預設；RIA 的評估結果出來之前不變」、rea 是「訪談：有感」、skill-creator 是「常用」，都是維護者個人偏好，沒有評估紀錄；FR-5 卻要求每項附「證據（評估紀錄的位置）」。訪談的「研究調查」「不確定時亂猜」對應到凍結的 product-research（預設 bmad），階段 0 只解凍 dev-workflow，§10 第 4 題也沒有時程。§6.1 又允許「明確標為沒有預設、用內建功能」，等於每個槽位都能用這個出口宣稱達標。",
    "guard_snippet": "加一條規則：同事版只預先勾選證據等級 E3 以上的工具；沒有評估紀錄的預設在預覽標「維護者個人使用（未實測）」，不預先勾選。§6.1 的完成條件改成可數的門檻（例如訪談第 1、2 題的每個選項，至少一個對應槽位有 E3 以上的預設，否則在預覽如實寫「這一項只用內建功能」）。product-research 的處置（解凍，或從訪談對應中移除）列進階段 0。",
    "potential_consequence": "試點同事看到的「證據」欄大多空白或指向不存在的紀錄；BMAD 這種約 30 個 skill 的框架被預先勾選給大多數寫程式的同事，跟 SM-3 的 token 目標直接衝突。"
  },
  {
    "id": "ADV-03",
    "lens": "adversarial",
    "location": "prd.md UJ-1（:49-60）、FR-3（:130-139）、FR-6（:174-183）、§10 第 3 題；addendum.md B（:94）；data/tools/（grep jupyter、pandas、notebook、ipynb、資料分析：0 筆）",
    "trigger_condition": "主角阿哲做資料分析（`*.ipynb`、pandas），但名冊 116 張卡沒有任何資料分析、Jupyter 或 pandas 相關的卡片；FR-6 對新槽位只要求「至少一個情境」，附錄 B 又排除「pandas 就裝 pandas 的 skill」。UJ-1 第 1 步的本機模型判斷也沒有槽位可以接（§10 第 3 題未定）。",
    "guard_snippet": "FR-6 加可測結果：新槽位進 MVP 之前，至少有 1 個通過第 1c 層的候選，否則明確標為「只用內建功能」並在預覽說明。把資料分析槽位的候選蒐集與實測列為階段 0 的交付項；或把 UJ-1 改成名冊現況做得到的人物。本機模型槽位定案前，硬體掃描結果不要出現在推薦理由裡。",
    "potential_consequence": "試點第一天的「關鍵時刻」就落空：預覽只剩內建功能與規則，「4 個工具、每個都有實測證據」的承諾做不到，而第一印象往往決定試點成敗。"
  },
  {
    "id": "ADV-04",
    "lens": "adversarial",
    "location": "prd.md FR-25（:434）；addendum.md A.6（:76）；docs/v2/research/eval.md:425-428、:601",
    "trigger_condition": "FR-25 的勝出條件只有「3 次配對至少贏 2 次」，漏掉研究同時要求的餘量規則（eval.md:601：「用『平均每次多 1 個檢查點』這類有餘量的規則，不用『總分高就贏』」）。用附錄 A.6 同一套模擬假設（4 個二元檢查點、兩邊通過率都是 70%）計算：單次挑戰者分數嚴格較高的機率約 35%（與 eval.md 的「跑 1 次 35%」一致），3 次至少贏 2 次約 28%；FR-25 允許最多 2 個挑戰者，至少一個被誤判勝出的機率上看約 48%（假設獨立；共用現任的執行結果時會略低）。「成本沒有明顯變差」也沒有數字。",
    "guard_snippet": "FR-25 改寫為「3 次至少贏 2 次，而且平均每次多至少 1 個檢查點（或事先寫好的效果量門檻）」；多個挑戰者時逐一對現任比較並做多重比較校正；「成本沒有明顯變差」定成數字，例如每回合輸入 token 不超過現任的 110%；E4 通知附上這次判定規則的誤判率估計。",
    "potential_consequence": "兩個一樣好的工具有相當機率被判成「更好」，錯誤的建議被主動推給所有同事；SM-2 與 SM-C3 由雜訊主導，第 3 層試用還會把誤判固化成預設。"
  },
  {
    "id": "ADV-05",
    "lens": "adversarial",
    "location": "prd.md §8 SM-2（:589）、§7 階段 2 與 3（:581-582）、FR-16（:306、:308）",
    "trigger_condition": "SM-2 要量「接受、而且 30 天內沒換回」，但試點只有 4 週、檢討在試點後 1 週；建議最早也要等 E4 實測完成、通知送達才會被接受，30 天觀察窗一定超出檢討日。分母（E4 換工具通知的數量）在「每人每週最多 1 則」且 E4 取決於階段 0 產出的條件下，可能是 0 到個位數。",
    "guard_snippet": "SM-2 改成試點期量得到的版本（例如「接受後 14 天內沒換回」，檢討時另列仍在觀察中的案例），或把檢討日訂在最後一則建議被接受後滿 30 天；事先寫明最少樣本數（例如少於 5 則時只報個案，不判定達標與否）。",
    "potential_consequence": "檢討時 SM-2 算不出來，或只靠 1、2 個案例判定；v2.1 要不要打開主動建議的決策沒有依據。"
  },
  {
    "id": "ADV-06",
    "lens": "adversarial",
    "location": "prd.md §8 SM-3（:590）、FR-5（:167-168）；docs/v2/brief/brief.md:25；data/mcp/servers.yaml:7-25",
    "trigger_condition": "SM-3 要求 token 比安裝前少 20%，前提是同事原本裝了很多；但目標使用者是「沒研究過 agent 工具」「乾脆什麼都不裝」的人（brief.md:25）。對他們來說，安裝 OmniKit 只會增加開頭負擔：底線與 profile 規則、omnikit-setup 與 omnikit-eval 的 skill 清單、內建功能改寫進規則（FR-5 :167），以及 servers.yaml 對每個人都裝的 chrome_devtools MCP 工具定義。27% 的依據是維護者這台 112 個 skill 的特例；「同樣的試點情境」要怎麼在安裝前後重播，也沒有定義。",
    "guard_snippet": "SM-3 分群：原本負擔高的同事（例如對話開頭的 skill 清單超過 N 字元）量「下降幅度」；其他同事改量「OmniKit 增加的開頭負擔不超過 X tokens」。寫明量法：固定 1 到 2 個提示，安裝前後在同一專案各跑一次 `claude -p` 與 `codex exec`，記錄輸入 token。",
    "potential_consequence": "多數試點同事的 SM-3 必然失敗，或被迫用不一致的量法湊數，指標失去意義。"
  },
  {
    "id": "ADV-07",
    "lens": "adversarial",
    "location": "prd.md §8 SM-1（:588）、FR-13（:270-271）；engine/scripts/usage.py:5-21；docs/v2/brief/brief.md:36",
    "trigger_condition": "usage.py 只能從「讀了 SKILL.md」與 plugin skill 的呼叫判斷有沒有用到；MCP server、CLI、hook 型（例如 rtk 會攔所有 shell 指令）、rules 型工具與內建功能都沒有叫用紀錄，FR-13 也明說這類不判斷，但 SM-1 的分母是「OmniKit 裝的工具」。門檻也不一致：FR-13 是 14 天而且 10 個 session、SM-1 看 30 天、brief.md:36 與 usage.py 預設都是 30 天；第 14 天就被建議停用的工具，算不算進 SM-1 的分母沒有定義。每人只裝 0 到 5 個、共 3 到 5 人，1 個工具就能讓比例跳 20% 以上。",
    "guard_snippet": "SM-1 的分母限定為有可觀察叫用訊號的工具，其他種類另列「無法量測」；MCP 改用 transcript 裡的 `mcp__<server>__` 呼叫補上量測；寫明被停用的工具怎麼計入；報告同時給分子、分母的原始數字；統一「沒在用」的門檻。",
    "potential_consequence": "SM-1 不是被量不到的工具拉低，就是被「排除誰」左右，跟 SM-C1「不能靠少裝衝高」互相打架。"
  },
  {
    "id": "ADV-08",
    "lens": "adversarial",
    "location": "prd.md §7 推出計畫（:579-582）、§12（:658）、§10 第 1、7 題、SM-4（:594）、UJ-4（:74）；docs/v2/research.md:190-195",
    "trigger_condition": "階段 0 要「跑評估漏斗」，但漏斗的批次工具（FR-22 到 FR-26：第 0 層批次、1b 證據卡、1c 隔離環境、第 2 層排程）就是階段 1 要開發的東西，兩者卻由同一位維護者「同時進行」。研究估計解凍兩個凍結槽位要再加 2 到 3 週（research.md:193-195），PRD 卻把解凍 dev-workflow 放進 6 到 8 週的階段 0。非凍結部分約 3,000 萬到 1.9 億 token、評分還要第三家模型，但 token 上限（第 1 題）、試點名單與開始日（第 7 題）都未定；SM-4 的「處理完」沒有定義。UJ-4 說維護者只要盲選與勾選，但 FR-22 的 url 比對、FR-24 的程式碼審查、FR-30 的提案審核與第 1 週隨訪都要人力。",
    "guard_snippet": "§7 加關鍵路徑與進入試點的 go/no-go 閘門，例如「FR-7 到 FR-11 在 Windows 通過、訪談會用到的槽位至少 N 個有 E3 以上的預設、doctor 在 2 台非維護者電腦全部通過」才開始階段 2；SM-4 的「處理完」定成「每張卡都有第 0 層結果與第 1 層結論」；token 上限先給暫定值與用哪個方案；列出維護者每週的預估工時。",
    "potential_consequence": "階段 0 與 1 互相等待，試點日期一再延後；或在內容空洞、工具鏈沒驗證的狀態下硬上，同事的第一次體驗就失敗。"
  },
  {
    "id": "ADV-09",
    "lens": "adversarial",
    "location": "prd.md §4.6 說明（:330）、FR-21（:378）、§6.1（:562）、§6.2（:569）、§7 階段 3（:582）",
    "trigger_condition": "靜默期「只記錄、不顯示」，既沒有使用者回饋也沒有人工標註，「誤報率」無從計算（只算得出命中次數）；FR-19 的頻率關卡延到 v2.1，靜默期也不知道「本來會顯示哪一則」。§7 階段 3 要依此決定是否打開提示，卻沒有判定門檻。資料散在各同事電腦，彙整（FR-31）延後；Codex 的 hook 要同事手動信任才會跑，Antigravity 不跑。結果整個試點期間，使用者明確要求的 UJ-3 完全不會被驗證。",
    "guard_snippet": "定義誤報的判定方式：靜默期每週在週報列出命中的情境摘要，讓同事勾「這時候建議有用／沒用」，或由維護者抽樣自己的紀錄標註；靜默期照樣跑 FR-19 的頻率關卡，記下「本來會顯示」的那一則；寫下打開提示的門檻（例如每條規則的精確率不低於 X、每人每週本來會顯示的不超過 Y 則）；MVP 加一個本機匯出指令，產生去識別的命中統計；記錄 hook 實際有在跑的比例。",
    "potential_consequence": "檢討會只能憑感覺決定：主動建議要嘛永遠不開，要嘛帶著未知的誤報率直接開，兩者都達不到「比 Claude Code 做得更好」的要求。"
  },
  {
    "id": "ADV-10",
    "lens": "adversarial",
    "location": "prd.md FR-16（:308、:311）、FR-19（:354）、SM-C2（:599）；engine/scripts/session_nudge.py:5-11；docs/v2/research/recommend.md:686",
    "trigger_condition": "三處上限互相不一致：FR-16 換工具通知每人每週 1 則、FR-19 工作中建議每週 3 則、SM-C2 卻說「通知次數每人每週最多 1 則」；FR-19 的「全部合計」包不包含 FR-16 與其例外沒有說。現有 session_nudge.py 已經會在每跨過 100k tokens、git push 之後印提醒，也佔同事的注意力，卻不在預算內。Claude Code 本身已會標「Not used recently」，研究要求 OmniKit 不重複提同一件事（recommend.md:686），PRD 沒寫進需求。",
    "guard_snippet": "定一張跨類型的總預算表：換工具通知、工作中建議、開新對話提醒、停用建議各自的上限與合計上限，寫明安全事件例外是否計入；FR-13、FR-15 加「平台已經提示過的不重複提，只補另外兩個 agent 的狀況與替代品」。",
    "potential_consequence": "實作時各自挑一個數字，同事一週可能看到 4 則以上 OmniKit 訊息，再加上平台自己的訊息，正好踩中風險表裡的「同事被通知打擾」。"
  },
  {
    "id": "ADV-11",
    "lens": "adversarial",
    "location": "prd.md FR-19（:357-358）、UJ-3（:66-67）、FR-20（:361-368）、§6.2（:569）；docs/v2/research/recommend.md:669-671",
    "trigger_condition": "hook 印的 `systemMessage` 只給人看、模型看不到；使用者回「OmniKit 裝 X」或「不要再建議」時，agent 不知道他在回應哪一則，而處理這句話的 skill（FR-20）延到 v2.1。「沒回應」怎麼判定（下一則 prompt 沒提到？session 結束？）沒有定義。研究寫的是「連續 5 次沒回應或拒絕」與「同一工具沒回應 2 次後只留在週報」，PRD 改成「累計 5 次就全部靜音」，又漏掉後者；在每週最多 3 則的上限下，大約兩週就會永久靜音。",
    "guard_snippet": "明定回應的擷取方式（例如 UserPromptSubmit hook 比對固定句型，或 MVP 就提供一個只處理「OmniKit 裝 X」「OmniKit 不要再建議 X」的小 skill）；「沒回應」定義為「顯示後同一個 session 內沒有出現對應句型」；靜音規則改回「連續 5 次」，補回「同一工具沒回應 2 次只留週報」；靜音時告訴使用者怎麼重新打開。",
    "potential_consequence": "拒絕與沒回應的資料不可靠，FR-21 依錯的資料停用規則；或整個功能在試點兩週內就把自己靜音。"
  },
  {
    "id": "ADV-12",
    "lens": "adversarial",
    "location": "prd.md FR-18（:338）、FR-16（:306）、FR-27（:457）；docs/v2/research.md:125；data/tools/chrome-devtools-mcp.yaml",
    "trigger_condition": "FR-16 規定只有 E4 才主動通知，研究也寫「只主動提實測勝出的工具」，但 FR-18 允許主動建議「預設或試用中」的工具。試用不等於 E4：現在唯一的試用 chrome-devtools-mcp 是 U1 打平（兩端都 4 分）後由維護者自己選的；預設裡也有 bmad 這種沒有實測的。",
    "guard_snippet": "FR-18 的條件改成「證據等級 E4」（E3 只在使用者明確詢問時出現）；工具卡用欄位區分「實測勝出進試用」與「維護者自選試用」。",
    "potential_consequence": "工作中跳出的建議其實沒有證據，跟產品主張衝突；FR-21 的接受率也混進不同品質的建議，自我檢討的結論失真。"
  },
  {
    "id": "ADV-13",
    "lens": "adversarial",
    "location": "prd.md FR-14（:281）、FR-15（:286）、FR-16（:305）、FR-18（:346）、FR-21（:376）、§3 週報（:97）、§4.2 說明（:143）；engine/skills/omnikit-setup/SKILL.md:46；engine/skills/omnikit-eval/scripts/digest.py:8-13",
    "trigger_condition": "停用建議、上游新版、E2 與 E3、Antigravity 的建議、接受率都只出現在「週報」；但週報目前是 omnikit-eval skill 的手動指令（說「每週彙整」才產生），而訪談第 5 題選「先不要」就不裝 omnikit-eval，「也沒有每週彙整」。PRD 說訪談「沿用現有的 6 題」，等於讓最典型的同事（不想研究工具的人）自己關掉整個「只留有用的」迴路。週報什麼時候產生、出現在哪裡，以及 MVP 裡 E4 通知走什麼管道（session 開頭的顯示屬於延後的 FR-18、FR-19），都沒有寫。",
    "guard_snippet": "新增 FR：使用者面的週報跟 omnikit-eval 脫鉤，每台都裝；定義觸發方式（例如 SessionStart hook 每 7 天提示一次「說『OmniKit 週報』」）與輸出位置；第 5 題只控制「評估新工具」，不影響週報；明寫 MVP 中 E4 通知的送達管道。",
    "potential_consequence": "多數同事裝完之後再也看不到任何停用或替換建議，SM-1、SM-2 沒有資料，「OmniKit 持續幫他把關」不成立。"
  },
  {
    "id": "ADV-14",
    "lens": "adversarial",
    "location": "prd.md §5 非目標（:546）、FR-7（:191）、FR-9（:227）、FR-10（:231）、FR-33（:531）；engine/scripts/install.ps1:23；.githooks/post-merge、.githooks/post-commit、.githooks/sync-data.sh:26-56",
    "trigger_condition": "install.ps1 會把同事的 repo 設成 `core.hooksPath=.githooks`；之後每次 `git pull`（post-merge）只要動到 data/rules、data/profiles、data/mcp、data/harness 或相關腳本，就在背景自動改規則、重裝 skills、寫 MCP、補 Claude 的免問權限、改 hook，不經預覽也不問。PRD 完全沒提這個機制，也沒要求改掉。",
    "guard_snippet": "同事版不設 .githooks（只有維護者需要）；pull 之後只提示「有 N 項變更，說『OmniKit 更新』預覽」，套用一律走 FR-7 的計畫與一次確認；FR-7 加可測結果「git pull 不會改動任何 agent 的設定」。",
    "potential_consequence": "維護者一次 push 就能在所有同事的 agent 新增 MCP 與免問權限，直接違反「不在沒有使用者確認的情況下安裝」；遇到 FR-10 的衝突時，git hook 也沒辦法「停下來問」，只會在 pull 的輸出裡默默失敗。"
  },
  {
    "id": "ADV-15",
    "lens": "adversarial",
    "location": "prd.md §5（:547）、§9.4（:625）、FR-14（:281）、UJ-2（:62）",
    "trigger_condition": "新的預設、E4 結果、退役決定都在維護者的 repo；同事端要知道，只能自己 `git pull`。PRD 同時規定「不自動更新」「除了使用者明確執行的步驟，不連網」，卻沒有任何 FR 定義 OmniKit 本身與名冊怎麼更新、多久一次、由誰觸發、更新前怎麼預覽。FR-14 的「上游有新版時，週報能列出」也要連網查上游。",
    "guard_snippet": "新增 FR「更新 OmniKit」：使用者說「OmniKit 更新」才連網抓取，先列出名冊與腳本的差異（含新的 E4、退役、安全通報）再套用；週報顯示「名冊已經 N 天沒更新」；同事追維護者發佈的版本 tag，不直接追 main。",
    "potential_consequence": "UJ-2 的「一個月後收到更好的選擇」不會發生（同事根本沒 pull）；或發生時伴隨 ADV-14 的靜默改動。"
  },
  {
    "id": "ADV-16",
    "lens": "adversarial",
    "location": "prd.md FR-16 例外（:311）、§9.1（:606-608）",
    "trigger_condition": "「現任或試用中的工具出現安全事件…立即通知」需要一條把消息送到同事電腦的管道，但 OmniKit 不連網、不常駐、也沒有推送；偵測安全事件的第 0 層又是維護者端手動跑。整份 PRD 沒有「緊急停用」的機制。",
    "guard_snippet": "定義安全事件流程：維護者在工具卡標 `revoked` 並附原因；同事下次更新（ADV-15）時第一個顯示，並預設勾選停用；另外在 README 寫不靠 OmniKit 也能做的手動停用步驟，由維護者直接通知試點同事；把「立即」改成做得到的時限描述。",
    "potential_consequence": "一個被入侵的 MCP 或 hook 會在同事電腦上一直執行，直到他哪天剛好 pull；文件承諾「立即」卻做不到，出事時難以交代。"
  },
  {
    "id": "ADV-17",
    "lens": "adversarial",
    "location": "prd.md FR-7（:195-196）；addendum.md A.1（:12-13）；engine/scripts/usage.py:10-11",
    "trigger_condition": "計畫的 revision 是「各檔的雜湊」，但 `~/.claude.json` 會被 Claude Code 自己持續寫入（usage.py 讀的 skillUsage 就存在裡面），Codex 也可能在信任專案等操作時改 `config.toml`。安裝流程本身就在 Claude Code 對話裡執行，預覽到安裝之間這些檔案幾乎一定會變。",
    "guard_snippet": "revision 只算受管項目的雜湊（例如 `mcpServers.<名稱>` 正規化後的 JSON、受管區塊內容、特定 TOML 表格），不算整個檔案；`--check` 也只比受管項目，並分開「agent 自己改的欄位」與「使用者改了受管內容」。",
    "potential_consequence": "安裝永遠停在「請重新預覽」，或實作者為了過關把這個檢查拿掉；`--check` 每週都報「設定被手動改過」，誤報讓使用者忽略真正的變更。"
  },
  {
    "id": "ADV-18",
    "lens": "adversarial",
    "location": "prd.md FR-9（:226）、FR-17（:321）；addendum.md A.1（:17）",
    "trigger_condition": "FR-9 說「一項失敗不會中斷整批」，附錄 A.1 說「有衝突就整批不寫」。安裝到一半才發現衝突（例如寫到第 3 個 MCP 才發現被改過）要怎麼辦沒有定義；部分成功時帳本與 lock 記什麼、要不要回復也沒寫。",
    "guard_snippet": "明定兩階段：先完成全部衝突檢查，期間不寫任何東西，有衝突就整批不寫；通過後才執行，個別項目執行失敗不中斷，但帳本只記實際成功的項目，結尾列出可重跑的指令；寫入前先存還原紀錄（docs/v2/research/sync.md §8 第 7 點的 journal 做法）。",
    "potential_consequence": "設定停在半套狀態，帳本跟實際不符；之後的換回（FR-17）與 doctor 都依錯的帳本判斷。"
  },
  {
    "id": "ADV-19",
    "lens": "adversarial",
    "location": "prd.md FR-10（:231）、FR-15（:290-292）、FR-17（:321）；engine/scripts/install.ps1:20；data/harness/claude-allow.txt",
    "trigger_condition": "「換回之後設定與替換前一致（依帳本比對）」只涵蓋 OmniKit 寫的檔案：原生 `claude plugin install`、`codex plugin add` 產生的 plugin 快取與 agent 內部狀態不在帳本；Claude 的免問權限是「只增不刪」；記憶與交接槽位的工具（例如 claude-mem）累積的資料，換掉就沒了。FR-15 還要停用「跟帳號同步的 plugin」，那不是 OmniKit 的東西，跟 FR-10「只動自己管理的內容」衝突，帳本也沒有記錄這類經使用者同意的改動。",
    "guard_snippet": "FR-17 的可測結果改成列舉範圍（規則、MCP、skills、權限、hooks、plugin 啟用狀態），並把權限規則納入帳本；有狀態的工具在預覽標「換掉會遺失 <資料>」，提供匯出；FR-10 加一條：對非 OmniKit 項目的改動記成「使用者同意的外部改動」，可以單獨還原。",
    "potential_consequence": "同事以為一句話就能換回，實際上權限殘留、記憶資料遺失或帳號 plugin 狀態錯亂；信任只要破一次就回不來。"
  },
  {
    "id": "ADV-20",
    "lens": "adversarial",
    "location": "prd.md FR-9（:224）、FR-14（:281）、FR-16（:310）、FR-26（:449）、§5（:547）",
    "trigger_condition": "FR-14「跨大版本更新要使用者同意」暗示小版本可以不問就更新，跟「版本一律釘選」「不自動更新」「不在沒有確認的情況下安裝」衝突；FR-16 又說「跨 minor 版本就降一級」，把小版本當成會讓證據失效的變化。名冊多數工具只能釘 git SHA，沒有 semver，「minor」無從判斷。證據滿 90 天就降級，代表每個預設每季都要重測，這個量沒有算進 FR-26 的額度。新版的能力揭露（hook、遙測）也沒有規定要重新檢查。",
    "guard_snippet": "規定所有版本變更（含 patch）都要使用者同意，並重跑 1c 的能力揭露差異；只釘 SHA 的工具改用「上游變更範圍」（例如動到 hooks、manifest 或可執行檔）決定是否降級；FR-26 的額度保留回歸重測的份額。",
    "potential_consequence": "實作者照 FR-14 做靜默的小版本更新，新版加了 hook 或遙測也沒人看到；或證據每 90 天全面過期，預設一夕之間全部降級，推薦清單清空。"
  },
  {
    "id": "ADV-21",
    "lens": "adversarial",
    "location": "prd.md FR-13（:270-273）、FR-15（:286）；engine/scripts/usage.py:285-292",
    "trigger_condition": "usage.py 的 `judge()` 只要沒比對到任何 session 就判「unused」，不管解析器是不是其實什麼都沒讀到。Claude Code、Codex 或 Antigravity 改了對話紀錄的格式（例如 Skill 工具呼叫的 JSON 形狀），所有工具會一起變成「沒在用」。",
    "guard_snippet": "FR-13 加可測結果：某個 agent 在統計期間有 N 個 session、卻解析出 0 次叫用時，那個 agent 的結果整批標「未知（解析失敗）」，不產生停用建議；selftest 加一筆「格式改了」的 fixture。",
    "potential_consequence": "某次 agent 自動更新之後，週報建議同事停用全部工具；同事照做，或從此不信任週報。"
  },
  {
    "id": "ADV-22",
    "lens": "adversarial",
    "location": "prd.md FR-5（:163-164）、FR-9（:224）、UJ-2（:63）；engine/scripts/build.py:14、67-68；data/tools/find-skills.yaml、rtk.yaml；docs/v2/research.md:37",
    "trigger_condition": "marketplace 只收狀態是 default、而且卡片有 plugin 來源的工具；整個名冊只有 3 張卡（frontend-design、rea、skill-creator）有釘選來源。FR-5 讓試用與「社群推薦（未實測）」的待評估工具出現在預覽、可以從「逐項調整」勾選，UJ-2 要把 E4 的挑戰者裝進試用，但這些工具都沒有釘選來源，FR-9「版本一律釘選並比對雜湊」做不到。三個沒有預設的 active 槽位會列出 rtk（用 hook 攔所有 shell 指令）、find-skills（卡片沒有 url、沒有 kind；研究指出 skills CLI 的 find 會把查詢字串連同遙測送出去）這類沒過第 0 層的工具。",
    "guard_snippet": "只有通過第 0 層、卡片有釘選來源的工具才能出現在可勾選清單；待評估工具在預覽只列名稱與「未審查」，不能從預覽安裝；marketplace 改成收 default 與 trial，build 時檢查 trial 一定有釘選來源。",
    "potential_consequence": "同事以為「社群推薦」經過 OmniKit 把關，結果裝了沒審查的 hook 或會外送查詢的工具，違反 §9.1、§9.2，FR-9 的釘選承諾也破功。"
  },
  {
    "id": "ADV-23",
    "lens": "adversarial",
    "location": "prd.md FR-5（:168）、FR-9（:220）；addendum.md A.3（:37-43）；engine/scripts/agents.py:146-147、322-324、359-367；data/tools/bmad.yaml；docs/v2/prd/.memlog.md:3",
    "trigger_condition": "附錄 A.3 說「skills 與 MCP 沿用 agents.py」，但 agents.py 只會裝 OmniKit 自己的 `engine/skills`，MCP 只讀全域的 data/mcp/servers.yaml（每台都一樣）；它沒有依工具卡抓上游、依個人工具包挑選的能力。名冊種類分布是 collection 16、app 13、service 9、mcp 8、cli 7、library 2、rules 1、沒填 25，plugin 只有 9。預設 bmad 是 collection、沒有 plugin 來源，BMAD 又是裝在專案目錄的框架（memlog:3「BMAD 沒裝進這個 repo」），跟 OmniKit 只做全域的方式不合。service 類（exa、tavily、firecrawl、composio 等）還要帳號與金鑰，並把資料送到第三方。",
    "guard_snippet": "FR-9 依 kind 列出支援的安裝方式，以及不支援時怎麼呈現（例如 app、service、library 只給手動安裝說明，不預先勾選）；工具包的 MCP 改由 lock 產生、每人不同，不再用全域 servers.yaml；service 類一律不預先勾選，預覽另標「資料會送到 <服務>」並要求單獨同意；附錄 A.3 如實寫出要新增的能力（抓上游、釘選、雜湊、移除）。",
    "potential_consequence": "開發時才發現一半以上的候選沒有安裝路徑，FR-5 的「最多 5 個」實際上只剩 1、2 個能裝；或臨時讓 LLM 照 README 安裝，違反「不讓 LLM 直接寫設定檔」。"
  },
  {
    "id": "ADV-24",
    "lens": "adversarial",
    "location": "addendum.md A.3（:41）、A.4（:53）；prd.md FR-11（:247）、FR-15、FR-32（:518-522）；engine/scripts/agents.py:16、93-95、298-304；docs/v2/research/sync.md:437、562",
    "trigger_condition": "agents.py 把 Antigravity 的 skills 放在跟 Codex 共用的 `~/.agents/skills`，附錄 A.3 卻寫用「檢查 `~/.gemini/config/skills`」驗證，兩個位置不同；agy（Antigravity CLI）讀不讀 `~/.agents/skills`，研究也還沒實測。附錄 A.4 的 Antigravity 停用方式「移除 OmniKit 放的複製品」，會讓 Codex 同時失去那個 skill，因為是同一個資料夾。",
    "guard_snippet": "FR-32 補上 Antigravity skills 位置的偵測與實測結論（IDE 與 agy 分開）；驗證檢查的位置必須等於實際寫入的位置，而且要能證明 Antigravity 真的讀到（做不到就標「未知」）；要能單獨停用 Antigravity，就改放 Antigravity 專屬的位置；共用資料夾的項目在預覽標明「會同時影響 Codex」。",
    "potential_consequence": "Antigravity 的驗證要嘛永遠失敗，要嘛只證明檔案存在卻沒被讀到；同事在 Antigravity 停用一個工具，Codex 也跟著少一個。"
  },
  {
    "id": "ADV-25",
    "lens": "adversarial",
    "location": "prd.md §1（:26）、FR-5（:166）、FR-18（:338、:346）、§6.2（:569）、§10 第 7 題；engine/schema/tool.schema.json:26-30、35-63",
    "trigger_condition": "核心主張是「三個 agent 一致」，但工具卡 schema 的 `works_with` 只允許 claude、codex，plugin 來源也只有 claude、codex；116 張卡有 72 張沒填 works_with。FR-5、FR-18 的「相容這台／目前的 agent」對 Antigravity 沒有資料可判斷。FR-18 說 Antigravity 第一階段「只在週報與使用者明確詢問時建議」，但明確詢問（FR-20）整個延到 v2.1，週報又可能不存在（ADV-13）。",
    "guard_snippet": "FR-28 把 `works_with` 與安裝方式擴成三個 agent，沒填就當「未知」並在預覽標示；§6 加一張「各 agent 在 MVP 支援哪些功能」的矩陣；試點名單裡若有只用 Antigravity 的同事，事先說明限制，或把 FR-20 的「只查名冊」部分提前進 MVP。",
    "potential_consequence": "只用 Antigravity 的同事在 MVP 幾乎拿不到任何推薦與通知，卻被算進 SM-1 到 SM-3 的分母；「三個 agent 一致」在第一次試點就被證偽。"
  },
  {
    "id": "ADV-26",
    "lens": "adversarial",
    "location": "prd.md FR-1（:111-116）、FR-2（:120-128）、§9.4（:625）；addendum.md A.5（:60）；engine/scripts/install.ps1:7、11、23；engine/scripts/codex_hooks.py:12",
    "trigger_condition": "環境掃描在安裝之後才跑，但安裝本身就需要：git、從 GitHub release 下載 uv、gh、gitleaks、npm 全域安裝 MCP 套件、uv 依腳本標頭從 PyPI 解析相依套件（agents.py、digest.py 都要 pyyaml 與 jsonschema）、PowerShell 執行原則允許跑 .ps1。依 codex_hooks.py:12 的註解，Codex 在 Windows 用 `pwsh` 跑 hook，而 Windows 11 預設只有 PowerShell 5.1。FR-2 對 proxy 只「看名稱」，沒處理 proxy 與憑證設定；hook 每回合用 `uv run --script`，uv 快取被清掉時會在 hook 裡連網，跟 §9.4「不連網」衝突。",
    "guard_snippet": "FR-1 加「安裝前檢查」：用 PowerShell 5.1 內建功能先查執行原則、git、Node、pwsh，以及到 github.com、registry.npmjs.org、pypi.org 的連線，任何一項不過就停下並給具體處理方式；hook 腳本保持沒有外部相依，並用 `--offline` 或預先建好的環境執行；§9.4 逐項列出哪些步驟會連網。",
    "potential_consequence": "同事卡在 install 第一步、看到一串英文錯誤；或裝好了但 Codex 的 hook 從來沒跑過，靜默記錄缺一半資料也沒人發現。"
  },
  {
    "id": "ADV-27",
    "lens": "adversarial",
    "location": "prd.md §11 防毒列（:646）、FR-5（:166）、FR-18（:345）、§9.4（:626）；engine/scripts/agents.py:10-11；這台實測 Get-AuthenticodeSignature：PATH 上的 %LOCALAPPDATA%\\hermes\\bin\\uv.exe 與 install.ps1 裝的 %LOCALAPPDATA%\\Programs\\gitleaks\\gitleaks.exe 都是 NotSigned；docs/v2/research/sync.md:566",
    "trigger_condition": "對策寫「不用沒簽章的背景程式」，但 OmniKit 每回合的 Stop hook 都在背景啟動沒簽章的 uv.exe，安裝也放了沒簽章的 gitleaks（同事不 commit 根本用不到）。Trend Micro 的允許通知要剛好盯著畫面才按得到（agents.py:10-11），hook 在背景被擋時照 FR-18「安靜結束」，沒有人會知道。「已知阻擋」以防毒產品名稱為鍵，但同一套產品在不同政策下行為可能不同。",
    "guard_snippet": "把「uv 在 Trend Micro 下能不能穩定放行」列為試點前的實測項目（研究也說只能在同事電腦上觀察）；同事版不裝 gitleaks 與 gh；hook 失敗寫進本機錯誤計數，doctor 與週報顯示「hook 最近 7 天失敗 N 次」；`blocked_on` 記錄觀察到的機器、日期與現象，不只記產品名。",
    "potential_consequence": "試點中 hook、掃描或 MCP 被擋卻無聲無息，靜默記錄與使用統計都缺資料，檢討時把「被擋」誤判成「沒用」。"
  },
  {
    "id": "ADV-28",
    "lens": "adversarial",
    "location": "prd.md FR-18（:334、:345）、FR-19、§2.1（:36）；addendum.md A.5（:63-65）；engine/scripts/codex_hooks.py:85-86",
    "trigger_condition": "每個回合結束都要啟動 uv 與 Python、讀新增的 transcript、比對訊號、寫狀態檔；Codex hook 的 timeout 是 10 秒，防毒掃描還會再拉長。PRD 說「不會拖慢 agent」，卻沒有延遲預算。Claude Code 與 Codex 同時開著時，兩邊的 hook 會同時寫同一份頻率與靜音狀態（三個 agent 共用），沒有鎖定或原子寫入的要求；防毒短暫鎖檔也會讓寫入失敗。",
    "guard_snippet": "加非功能需求：hook 的 p95 延遲上限（例如 1 秒），超過就跳過這次比對；狀態檔用檔案鎖，加「寫暫存檔再取代」（規則檔要保留硬連結的限制不適用於狀態檔）；selftest 加「兩個 hook 同時寫」的案例。",
    "potential_consequence": "每回合多等幾秒，同事覺得 OmniKit 拖慢 agent；狀態檔互相覆蓋，靜音設定或頻率計數遺失，同一則建議重複出現。"
  },
  {
    "id": "ADV-29",
    "lens": "adversarial",
    "location": "prd.md §11 平台改版列（:644）；addendum.md A.3（:40）、A.4（:51）、A.5、A.6（:74）",
    "trigger_condition": "幾個關鍵行為只在某一天、維護者這台試過，或只來自別人的文件：Codex 帳號同步 plugin 的 `[[skills.config]]` 停用（2026-11-04 實測一次）、`codex plugin add --json`（引用 ECC 的文件）、`claude plugin eval`（未實測）、Codex 工具核准紀錄的位置（研究推論）。Claude Code 會自動更新，同事的版本不會跟維護者一致。風險表的對策只有「位置偵測、doctor、記錄實測日期」，沒有版本閘門。",
    "guard_snippet": "新增需求：每個會寫入的功能記錄「已驗證的 agent 版本範圍」；偵測到範圍外的版本時，該功能降級為只預覽、不寫入，並在 doctor 標示；維護者每次升級 agent 先跑 selftest 與 doctor，再更新範圍。",
    "potential_consequence": "某次 Claude Code 或 Codex 更新後，停用、驗證或 hook 輸出悄悄失效或寫錯位置，同事看到的是「OmniKit 壞了」。"
  },
  {
    "id": "ADV-30",
    "lens": "adversarial",
    "location": "prd.md FR-5（:163）、FR-33（:531）、§9.1（:607）；data/mcp/servers.yaml:7-25；data/harness/claude-allow.txt:4-5；data/tools/chrome-devtools-mcp.yaml:6、13",
    "trigger_condition": "試用中的 chrome-devtools-mcp 寫在全域的 servers.yaml，targets 是三個 agent，install.ps1 會裝到每一位同事；Codex 設 `default_tools_approval_mode: approve`，Claude 的權限清單加 `mcp__chrome_devtools` 免問，依據是「使用者同意免問（2026-11-04）」，也就是維護者本人的同意。試用到 2026-11-18 到期，沒有到期自動處理的機制。",
    "guard_snippet": "同事版不套用維護者的 servers.yaml 與 claude-allow.txt；MCP 與免問權限改由個人工具包的計畫產生，試用工具預設不勾選，免問要在預覽單獨同意；試用到期後在下一次預覽列為「到期，建議移除」。",
    "potential_consequence": "每位同事在不知情的情況下多了一個自動核准、能開任意網頁並執行 JavaScript 的瀏覽器工具（遇到網頁裡的提示注入時沒有人工把關），每回合還多載入它的工具定義；同時違反 FR-5、FR-33 與 SM-3。"
  },
  {
    "id": "ADV-31",
    "lens": "adversarial",
    "location": "addendum.md A.5（:60）；prd.md §9.1（:607）；.githooks/sync-data.sh:42-56",
    "trigger_condition": "附錄刻意讓 Codex hook 的指令字串固定，「邏輯放在腳本裡，更新腳本不用重新信任」，等於繞過 Codex 用來偵測 hook 變更的信任機制；Claude Code 的 hook 本來就沒有信任步驟。再加上 ADV-14 的 pull 自動同步，repo 上任何對 hook 腳本的修改（包括維護者帳號被盜、誤合併的 PR）都會在所有同事電腦的每個回合直接執行。",
    "guard_snippet": "由 OmniKit 自己做信任：hook 啟動時比對腳本雜湊與使用者上次同意的雜湊，不符就只印「OmniKit hook 已更新，說『OmniKit 更新』檢視差異」，不執行新邏輯；或把腳本雜湊放進指令字串，讓 Codex 的重新信任自然觸發。",
    "potential_consequence": "一次惡意或錯誤的提交，就成為對全體試點同事的程式碼執行管道，而且 Codex 不會再提醒任何人。"
  },
  {
    "id": "ADV-32",
    "lens": "adversarial",
    "location": "prd.md FR-1（:115）、FR-29（:487-491）、FR-30（:495-500）、§6.1（:563）、§9.2（:613）；.githooks/pre-commit:1-2（「這個 repo 是公開的」）；data/evals/2026-11-04-frontend-design-F1/（x.patch、y.patch、votes/*.png）",
    "trigger_condition": "回流與提案走 GitHub issue 或 PR，而 repo 是公開的：內容會公開，而且綁著 GitHub 帳號，談不上匿名；3 到 5 人的試點，工具組合本身就能認出是誰。FR-30 的「實測結果」照現有格式會含 patch、截圖與情境文字，同事工作專案的內容可能因此公開。FR-1 允許沒有 GitHub 帳號，MVP 卻只有 GitHub issue 範本，這些同事沒有任何回流管道。",
    "guard_snippet": "MVP 的回流改成「本機匯出檔，交給維護者的非公開管道（例如共用資料夾）」，GitHub 只當選配；匯出前自動檢查不含路徑、專案名稱、程式碼片段與圖片，預覽給同事確認；FR-29 拿掉「匿名」，改成如實說明「去識別，但小樣本仍可能被認出」；FR-30 的實測結果只收結論與數字。",
    "potential_consequence": "同事的工具使用狀況與工作內容出現在公開網路上；回流機制一出事就會被叫停，維護者的資料來源（UJ-4）也跟著斷掉。"
  },
  {
    "id": "ADV-33",
    "lens": "adversarial",
    "location": "prd.md FR-4（:153）、FR-30（:495）；.gitignore；engine/skills/omnikit-setup/SKILL.md:104；engine/scripts/scan.py:72-92、180",
    "trigger_condition": "同事的 profile、answers.json、scenarios.yaml（含主要專案名稱與工作背景）都寫在 clone 下來的公開 repo 的 `data/profiles/<名稱>/`，.gitignore 沒有排除；profile 名稱還是從 git user.name 或登入帳號推出來的。同事照 FR-30 開 PR 時，一個 `git add -A` 就會把它們送上公開 repo；上游哪天新增同名的 profile，同事的 `git pull` 會因為未追蹤的檔案而失敗。",
    "guard_snippet": "個人資料改存 %LOCALAPPDATA%\\omnikit\\profiles\\（repo 只放範本），或至少把 default 與範例以外的 `data/profiles/*` 列進 .gitignore；FR-30 的提案用產生器輸出單一檔案，不讓同事直接在這個 repo 開 PR。",
    "potential_consequence": "個人背景與專案名稱外洩；更新時 pull 失敗，同事卡在舊版又不知道原因。"
  },
  {
    "id": "ADV-34",
    "lens": "adversarial",
    "location": "prd.md FR-3（:136）、FR-18（:334-344）、§9.2（:612）；docs/v2/research.md:105-111",
    "trigger_condition": "FR-3 承諾「沒勾選的專案不會被讀取」，但 FR-18 的訊號要從所有 session 的對話紀錄抽取（讀了哪些檔、跑了哪些指令、使用者說了「不是叫你改這個」），等於讀取所有專案的工作內容，包括沒勾選的；FR-18 沒有任何同意或關閉的要求，而 MVP 的靜默記錄會對每位同事預設開啟。",
    "guard_snippet": "FR-18 加：第一次啟用前取得同意，可以限定只看 FR-3 勾選的專案；提供一個「關閉工作中比對」的開關；狀態檔與紀錄只存規則 id 與次數，不存路徑、檔名或原文片段，並寫成可測結果。",
    "potential_consequence": "同事發現 OmniKit 在背景讀自己全部的對話紀錄，會覺得被監看，跟「掃描結果只留在本機、只拿來預選」的說法不一致，可能因此退出試點。"
  },
  {
    "id": "ADV-35",
    "lens": "adversarial",
    "location": "prd.md FR-24（:420-425）、FR-25（:439）；addendum.md A.6（:74）；docs/v2/research/eval.md:142、642",
    "trigger_condition": "「隔離環境」「乾淨的環境」在原生 Windows 沒有沙箱可用；研究說要給 shell 權限的套件得在 WSL2 跑，但這台有沒有 WSL2、效能如何都沒驗證。乾淨的 HOME 代表沒有登入狀態：要嘛複製憑證檔（跟底線「不碰金鑰」衝突），要嘛根本跑不起來。FR-24 也沒規定程式碼審查要在安裝執行之前，待評估的 hook 與 MCP 會先在維護者的公司電腦上跑起來。",
    "guard_snippet": "FR-24 改成：有 hook、MCP 或可執行程式的工具先做靜態審查，通過才安裝；隔離方式明定（WSL2、Windows Sandbox 或拋棄式 VM 擇一），列為階段 0 的第一個驗證項；登入改用各 agent 支援的環境變數或專用測試帳號，不複製使用者的憑證檔。",
    "potential_consequence": "評估漏斗的第 1c、2 層要嘛做不出來（時程崩盤），要嘛在沒有隔離的狀態下執行沒審查的第三方程式。"
  },
  {
    "id": "ADV-36",
    "lens": "adversarial",
    "location": "prd.md FR-12（:253-258）、UJ-1（:58）、FR-8（:208）",
    "trigger_condition": "第一次成功要「在他的真實專案上實際跑一次」，但沒有限制只能用唯讀的工具、沒有要求在分支或 worktree 上跑，也沒有事先說會花多少 token；FR-8 自己就把「會不會改原始碼」列為要揭露的能力。",
    "guard_snippet": "FR-12 加：只挑能力揭露為「不改原始碼」的工具，或在暫存 worktree 執行，結束時只顯示結果與 diff；執行前顯示預估的 token 與時間，取得同意。",
    "potential_consequence": "同事第一次用就被改了工作專案的程式碼，或用掉一大段額度，第一印象從驚喜變成驚嚇。"
  },
  {
    "id": "ADV-37",
    "lens": "adversarial",
    "location": "prd.md FR-33（:526-531）、§9.1（:606）；docs/v2/research.md:40",
    "trigger_condition": "profile 是自然語言的 AGENTS.md，「放寬底線」（例如寫「push 不用問我」）沒辦法用名冊驗證這類腳本可靠判斷；研究建議先從權限、MCP、hooks 這些結構化欄位做。「權限、MCP 與 hooks 預設拒絕」也沒說清楚對象：是只限 OmniKit 要寫入的項目，還是連同事原本自己裝的 MCP 與 hook 都要拒絕（後者跟 FR-10「只動自己管理的內容」衝突）。",
    "guard_snippet": "FR-33 拆成兩條可測結果：結構化欄位（權限、MCP、hooks）用 deny 優先的程式檢查；自然語言部分改成「profile 不能刪除或改寫底線檔的條目，新增的內容在預覽標示並由使用者確認」。「預設拒絕」限定為「OmniKit 要寫入的第三方項目」。",
    "potential_consequence": "要嘛寫出誤判一堆的關鍵字檢查，讓同事的 profile 套不上；要嘛宣稱有程式檢查卻擋不住真正的放寬；若解讀成連既有 MCP 都拒絕，還會誤動同事原本的設定。"
  },
  {
    "id": "ADV-38",
    "lens": "adversarial",
    "location": "prd.md FR-4（:147-153）、UJ-1（:49-59）、FR-2（:120）、FR-3（:132）、FR-11（:248）、FR-12；engine/skills/omnikit-setup/SKILL.md:52；docs/v2/research/eval.md:100",
    "trigger_condition": "「最多 6 題加 1 次確認」跟流程實際的互動次數不符：環境掃描同意、專案勾選、6 題、照建議或逐項調整、profile 名稱確認（現行 SKILL.md:52）、預覽確認、煙霧測試同意、第一次成功、Codex 信任 hook、開新 session。「二十分鐘內」在研究裡沒有任何依據，第 2 層的重題一次就要約 16 分鐘（eval.md:100）。",
    "guard_snippet": "FR-4 改成列出完整的互動清單與上限（例如必答 8 次以內）；新增量測「從 clone 到第一次成功的時間」，在試點第 1 週隨訪時實測，再決定 UJ-1 要承諾幾分鐘。",
    "potential_consequence": "驗收時 FR-4 無法判斷有沒有通過；同事照 UJ-1 期待 20 分鐘，實際花 40 分鐘以上，覺得被騙。"
  },
  {
    "id": "ADV-39",
    "lens": "adversarial",
    "location": "prd.md FR-34（:535-540）、§9.4（:623）",
    "trigger_condition": "GitHub 的 windows-latest 是英文系統語系，要換成 cp950 得改系統地區設定並重開機，CI job 裡做不到（`chcp 950` 只改主控台字碼頁）；runner 上的是 Defender，不是 Trend Micro，「被防毒短暫鎖住會重試」與「被防毒擋下」都測不到。",
    "guard_snippet": "FR-34 拆成：CI 做得到的（PowerShell 5.1 與 7、含空白與長路徑、模擬檔案鎖的單元測試、`PYTHONIOENCODING` 與主控台字碼頁）；以及試點前在至少 1 台同事規格的公司電腦上跑的「驗收清單」（cp950 系統語系、Trend Micro、非系統管理員帳號）。",
    "potential_consequence": "CI 全綠讓人以為 Windows 相容性已經驗證，問題到同事電腦上才爆出來。"
  },
  {
    "id": "ADV-40",
    "lens": "adversarial",
    "location": "prd.md FR-22（:403）、FR-26（:447）；addendum.md A.6（:72）；docs/v2/research/eval.md:221、639",
    "trigger_condition": "「爆紅」要算「近期星數成長速度是平均的 3 倍以上」，但 stargazers 清單已不開放，只能用事件 API 最近 300 個事件裡的 WatchEvent；研究自己說很活躍的 repo，這個窗口可能只有幾小時、雜訊大。這個旗標卻會影響排程（延後一輪）。",
    "guard_snippet": "爆紅旗標只當「提示人工看」，不影響排程；或改成第 0 層每週記一次 stargazers_count 快照，自己算成長率，資料不足時標「未知」。",
    "potential_consequence": "熱門工具因為幾小時的事件窗口被誤標爆紅，實測一再延後；或反過來漏掉真正的灌星。"
  }
]
```
