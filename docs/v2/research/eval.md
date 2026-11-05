# OmniKit v2：品質優先的工具評估規模化研究

日期：2026-11-05
研究對象：b40609/OmniKit @ 4a4fc38（只讀，沒有改任何檔案）
範圍：skills、MCP、plugins 的大量評估；104 張待評估卡片

標記方式：

- 〔已驗證〕：在原始來源親眼看到，或本研究實際量到。研究時有兩條平行的子研究（目錄與 registry、網路心得與基準），由它們讀到的來源也標〔已驗證〕。
- 〔已複查〕：關鍵數字由我再回原始來源核對過一次。
- 〔推論〕：依證據推得，但沒有直接驗證。
- 〔計算〕：本研究自己的計算或模擬，假設寫在旁邊。
- 〔未證實〕：找不到可靠出處，只當線索。

程式碼引用格式是「repo 路徑:行 @ 短 SHA」。OmniKit 的檔案都是 @ 4a4fc38。

---

## 0. 需要你決定的事

| # | 決定 | 建議 |
|---|---|---|
| 1 | 要不要採用第 7 節的漏斗 | 採用。前面幾層只負責「排除」與「排序」；要不要換工具，仍然只看第 2 層實測 |
| 2 | 每週額度怎麼算 | 把 `eval.weekly_deep_limit: 2` 拆成兩種：要你盲選的，每週最多 2 次；不需要你參與的客觀實測，改用每週 token 上限（數字由你定）。不拆也能跑，只是時程會從約 4 到 5 週拉長到 6 到 8 週 |
| 3 | 凍結槽位的 47 張怎麼處理 | 現在只跑免費的第 0 層：補身分、查封存、查安全。等 RIA 有結果再進漏斗 |
| 4 | 什麼時候主動通知你 | 只在第 2 層依事先寫好的規則勝出，或你盲選選中時，才主動通知。外部證據最多出現在週報（第 10 節） |

## 1. 重點結論

1. **星數、fork、安裝數在這個生態幾乎沒有鑑別力。**
   - 名冊有 50 個不重複的 GitHub repo：星數中位數 31,000，41 個超過 1 萬。現行第 0 層「少於 50 星就警告」只擋到 1 個。〔已驗證，本研究實測〕
   - 這些指標只能放在「同分時」排序的最後幾位，而且要先排除灌星與爆紅的干擾。
2. **沒有任何目錄或 registry 判斷「對這個使用者好不好」。**
   - 它們只看身分、安全與熱門度。
   - Tessl 會量「有裝和沒裝」的差異，但題目是通用的，不是你的情境。
   - 最接近「用你的情境比」的是工具，例如 `claude plugin eval`，以及 Tessl 從 commit 出題的功能；目錄本身做不到。〔已驗證〕
3. **2026 年的研究一致顯示：skill 平均效果小，而且不穩定。**
   - SWE-Skills-Bench：98 個軟體工程 skill 裡，92 個沒有顯著效果。
   - 網頁開發 skill 平均讓通過率下降 1.3% 到 4.2%，token 增加 72% 到 394%，而且效果跨模型轉移很弱。〔已複查〕
   - 所以預設要假設「沒效果」，挑戰者得證明自己比現任或原生功能好。
4. **網路心得可以縮小範圍，但只能用來排除和排序。**
   - 一則可查證的負面證據就能把工具排後面，例如不支援 Windows、非互動模式不能用。
   - 正面心得最多只能讓工具早一點進第 2 層。
5. **省成本靠「不測不可能贏的」，不是少測。** 具體做法有五個：
   - 先擋掉不相容、重複、原生已經有、不在範圍內的工具。
   - 同一個槽位一次比多個挑戰者，共用同一套素材。
   - 客觀題自動跑，不用你盯。
   - 你的盲選只留給牽涉品味的題目。
   - 實測素材轉成回歸套件，之後重複使用。
6. **時程估算〔推論〕**：非凍結的 57 張約 6 到 8 週可以處理完，active 的 34 張需要 7 到 10 次第 2 層；凍結的 47 張等 RIA 之後再加 2 到 3 週。非凍結部分約 30M 到 190M token，其中大多是快取輸入。相較之下，現行做法是每週 2 次、一次評一個工具，約需 52 週。

---

## 2. OmniKit 現在怎麼評估

### 2.1 三層與相關設定

- **第 0 層（免費）**：〔已驗證〕
  - 查 GitHub 現況（星數、最後 push、授權、封存、最新 release）、比對名冊，可選擇加做 skill 掃描（`cisco-ai-skill-scanner==2.3.1` 靜態模式）。
  - 門檻：封存直接 fail；超過 365 天沒更新、沒有授權、少於 50 星只 warn。（engine/skills/omnikit-eval/scripts/layer0.py:30-33、107-118）
  - GitHub API 用未登入的 urllib 呼叫，額度用完腳本就結束（layer0.py:48-61）。
- **第 1 層（便宜）**：讀 README（只當資料）、對照槽位情境、用 peers.py 找同槽位的現任與曾拒絕的工具，再寫卡片（engine/skills/omnikit-eval/SKILL.md:32-41）。〔已驗證〕
  - 平常不逐筆通知你，等每週彙整一起看（SKILL.md:41）。
  - schema 描述寫明，第二輪改由 OmniKeep 在背景產生第 1 層結果，再放進每週彙整（engine/skills/omnikit-eval/contracts/layer1.schema.json:4）。
- **第 2 層（你點名才跑）**：〔已驗證〕
  - 先寫決策規則、用真實情境、候選最多 3 個（contracts/layer2-request.schema.json:12-15）。
  - 執行與評分用不同家族的模型；牽涉品味的題目由你盲選（SKILL.md:43-60）。
  - 每週上限是 `eval.weekly_deep_limit: 2`（data/omnikit.yaml:12-14），digest 依 data/evals 的檔名日期計數（scripts/digest.py:79-83）。
- **每週彙整**：建議評估的槽位依「待評估張數」排序（digest.py:86-91）。〔已驗證〕
- **使用紀錄**：usage.py 讀三個 agent 的本機紀錄，只算實際讀取或呼叫；30 天沒用到就列為可移除（engine/scripts/usage.py:9-15）。〔已驗證〕
- **槽位 focus**：〔已驗證〕
  - active：主動找更好的。
  - watch：有新工具才做免費初篩。
  - frozen：不評估（data/slots.yaml:4-5）。
- **設計原則**：用真實情境比、不看星數（README.md:28）；評估分層、有額度（README.md:31）。〔已驗證〕

### 2.2 名冊現況〔已驗證，本研究統計 data/tools/*.yaml〕

- 116 張卡片：待評估（pending）104、預設（default）11、試用（trial）1。
- 104 張待評估，依卡片所屬槽位中最高的 focus 分：

  | focus | 張數 | 說明 |
  |---|---|---|
  | active | 34 | browser 9、code-understanding 8、frontend-design 4，其餘每個槽位 2 到 3 張 |
  | watch | 8 | |
  | frozen | 47 | product-research 33、dev-workflow 16，兩者有重疊 |
  | 未分配 | 15 | 多數是大型 skill 合集 |

- 49 張沒有 url，大多是 RIA 的候選；52 張是 GitHub，3 張是其他網址。第 0 層只吃 GitHub，所以這 49 張現在連第 0 層都跑不了。
- notes 欄位中位數只有 16 個字，88 張少於 120 字。也就是說，大多數卡片還沒做第 1 層。
- 卡片來源（一張可以有多個來源）：RIA 77 次（分布在 60 張卡）、使用者提出 18、訪談 15、桌機盤點 13、Codex 使用紀錄 6。

### 2.3 兩次第 2 層留下的成本基準與教訓〔已驗證〕

- **U1（瀏覽器）**
  - 成本：Codex 每次執行輸入 117,651 到 245,892 token，其中 68% 到 87% 是快取；輸出 457 到 1,099 token；每次 39 到 83 秒（data/evals/2026-11-04-browser-u1.md:52-58）。
  - 勝負由環境決定，而不是能力：非互動模式、沙箱、核准政策（:60-64）。
  - 每組只跑一次，token 有雜訊（:77）。兩個工具同分時，用「token 差 20%」當門檻，結果剛好 21% 越線（:72）。
- **F1（前端）**
  - 成本：每次輸入 3,068,285 到 3,899,100 token，約 96% 是快取；輸出 27,901 到 30,962；每次 949 到 985 秒（data/evals/2026-11-04-frontend-design-F1.md:63-65）。
  - 過程：第一輪畫面大多是空狀態，看不出差別；第二輪截圖被舊的瀏覽器設定影響。最後投票原版 2 票、frontend-design 1 票、impeccable 0 票，判定平手（:126-141、:152）。
  - 成本大頭是準備資料與你的注意力，不只是 token。
- **卡片上記錄的干擾**
  - 兩個工具同時裝，分不出效果：data/tools/caveman.yaml:15。
  - 不強制使用時，agent 0/6 次主動呼叫：data/tools/serena.yaml:14。
  - skill 掃描大量誤判：impeccable 多數標 HIGH、floorplan 有 7 個 CRITICAL，人工看過都是誤判（data/tools/impeccable.yaml:15、data/tools/floorplan.yaml:13）。

### 2.4 瓶頸在哪

1. 第 2 層的計數單位是「一份評估紀錄」，跟這次評幾個工具、要不要你參與都無關。
2. 第 0 層的門檻幾乎篩不掉工具（見 4.2）；第 1 層又沒做完，所以待評估的工具全擠在第 2 層門口。
3. 建議槽位用「待評估張數」排序。凍結中的 product-research 有 33 張，但根本不能評。
4. 第 0 層用未登入的 API，每小時只有 60 次；104 張每張要查好幾次，一定會撞到上限（layer0.py:48-61）。〔推論〕

---

## 3. 題目 1：同類目錄與 registry 怎麼判斷品質

| 目錄 | 用什麼訊號 | 自動化程度 | 能否判斷你的情境 | 弱點 | OmniKit 可以借的 |
|---|---|---|---|---|---|
| skills.sh（Vercel） | 安裝數，來自 CLI 匿名遙測，分 All Time、Trending 24h、Hot；另有 Gen、Socket、Snyk 三家稽核 | 全自動，沒有收錄門檻；稽核只提示、不擋安裝 | 不能 | 見表下說明 | 三家稽核當「需要人工看」的觸發器；安裝數依 repo 去重後當弱參考 |
| Tessl registry | Quality：決定性檢查，加上評描述與內文的兩個 LLM judge。Impact：task eval，比有裝和沒裝。Security：Snyk | 發布時自動；考題由 skill 自動生成，預設 3 題，每題有裝、沒裝各跑 | registry 上的分數不能；但 `tessl scenario generate --commits/--prs` 可以從你 repo 的歷史出題 | 官方說 review 不代表產出會變好；US 區預設模型是 `deepseek-v4.1-flash`，不是你用的模型；兩組分數區間大幅重疊時，不能說有差異 | Quality 當「寫得好不好」的便宜訊號；Impact 只在平手時排序；借用「從 commit 出題」的做法 |
| aitmpl（claude-code-templates） | 下載數，每次安裝送一次；安裝成功、失敗、部分 | 同 repo 的 PR 自動合併；skill 用 SkillSpector 掃描，分數變差才擋 | 不能 | 只審格式與安全，不看有沒有用 | 記錄「安裝結果」；「變差才擋」的增量門檻 |
| Smithery | verified、使用次數、score | 不明，官方文件回 404 | 不能 | 2026-08-05 被 Arcade 收購；分數定義不公開 | 不接 |
| 官方 MCP Registry | namespace 驗證（GitHub、DNS、HTTP）、套件所有權、狀態欄位 | 管理刻意寬鬆，只移除違法、惡意、垃圾、完全不能用的；明說不移除低品質或重複的 | 刻意不判斷，交給下游 subregistry | 還在 preview | 第 0 層查三件事：有沒有登錄、namespace 是否等於 repo owner、是否已刪除 |
| Anthropic 官方 plugin marketplace | 有沒有收錄、固定的 SHA；每個 plugin 的每個 SHA 都跑一次政策掃描 | 每晚把上游新 SHA 更新進來並先跑 validate，再由 Claude 依政策 prompt 審；新提交走開發者入口，部分項目由人審 | 不能。官方明說驗證與掃描只檢查 plugin 怎麼建，不檢查對安裝的人有沒有幫助，並建議作者用 `claude plugin eval` 比較有裝和沒裝〔已複查〕 | 完全不審品質 | 政策 prompt 的三個旗標（範圍過寬的 hook、未揭露的遙測、描述跟行為不符）可以直接當靜態審查清單；「每個 SHA 只判一次」的快取 |
| awesome-claude-code | 人工挑選，加上機械門檻：滿 14 天且持續開發，或至少 100 星；一個人同時只能推薦一筆 | 表單驗證自動、品質由人判斷；API 查詢失敗時一律放行 | 不能 | 只反映一個人的品味；查不到就放行 | 14 天冷卻期；定期重查。反例：查不到要標成「未知」，不能放行 |
| `claude plugin eval` | 每個 case 是一句真實提示，加上幾個 grader；預設每個 case 每組跑 3 次，有裝、沒裝兩組，報出差值 Δ；llm grader 三票兩勝 | 全自動；`--max-cost-usd` 設花費上限，超過時 exit 2 | 可以。目標可以是已安裝的 `name@marketplace`，或一個目錄；情境題由你自己寫 | 見表下說明 | 第 2 層的 Claude 端可以直接用它 |
| Codex 官方精選 plugin（openai/plugins） | 有沒有被收錄；共 65 個條目，沒有任何分數 | 審核流程不公開；skills 會自動掃描 | 不能 | 不透明 | 準則要求 plugin 提供產品內建沒有的功能：可以直接變成 OmniKit 的退役規則〔已複查〕 |

skills.sh 的弱點：

- 遙測是沒有驗證的 GET 請求（vercel-labs/skills src/telemetry.ts:3、132-162 @ 9197d91）。〔已複查〕
- Vercel 一方面說目前品質最好的訊號是安裝數，一方面也承認安裝數不代表不同的人，也不代表獨立的選擇。
- 安裝高度集中：375 個 skill（占 0.04%）拿走 62% 的安裝，近一半的 skill 只被裝過一次（Vercel，2026-09-25）。〔已複查〕
- 三家稽核的結論可以互相矛盾。例如 find-skills 同時拿到 Gen「Safe」、Socket「0 alerts」、Snyk「Med Risk」。

`claude plugin eval` 的弱點：

- 只支援 Claude Code。
- 隔離環境不載入你的 CLAUDE.md、其他 plugin、記憶，所以量到的是「單獨裝這一個」的效果，不是跟你現有組合一起用的效果。
- 原生 Windows 沒有沙箱後端，要給 shell 權限的套件得在 WSL2 跑。
- 通過不代表安全。
- 預設每次 10 回合、300 秒。

反面教材，出自子研究、我沒有複查：

- ClawHub：VirusTotal 分析 3,016 個 skill，有數百個帶惡意特徵。也有研究者發布帶後門的 skill 並灌高下載數，幾小時內就有開發者執行（[Socket](https://socket.dev/blog/openclaw-skill-marketplace-emerges-as-active-malware-vector)）。〔已驗證〕
- Snyk ToxicSkills：3,984 個 skill 有 13.4% 帶 CRITICAL 問題，確認 76 個惡意（[Snyk](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub)）。〔已驗證〕

**跨家結論**

- **目錄層的訊號只有三類：** 身分、安全與揭露、熱門度。品質層只有 Tessl 一家，而且用的是通用題。
- **同類競品的解法：**
  - registry 負責身分。
  - 官方 marketplace 負責安全與政策。
  - 大型目錄負責熱門度。
  - Tessl 和 `claude plugin eval` 負責「有裝和沒裝」的差異。

  沒有一家做到「挑戰者對現任、用你的情境比、依實際使用汰除」。這正是 OmniKit 的空位，跟 docs/proposals/2026-11-05-positioning.md:57 的觀察一致；那份是另一個 session 的討論稿，尚未 commit。
- **可以直接接進第 0 層的訊號：**
  - MCP Registry 的身分資料。
  - 是否收錄在官方 marketplace：收錄等於通過了 Anthropic 的政策掃描。
  - skills.sh 三家稽核：只當觸發器。
  - Tessl 分數：只在平手時排序，並記下版本與日期。
  - awesome 清單收錄：弱的策展訊號。
- **不能當排序主因的：**
  - skills.sh 安裝數、npm 下載數、Smithery score。
  - 單一掃描器的嚴重度：OmniKit 自己的紀錄裡，被標高嚴重度的全部是誤判。

證據：

- 官方 marketplace：
  - anthropics/claude-plugins-official @ fa4eb54：README.md:3-5、.github/policy/prompt.md:1-5 與 88-128、.github/workflows/bump-plugin-shas.yml:1-25
  - [pre-submission checklist](https://claude.com/docs/plugins/pre-submission-checklist.md)
- awesome-claude-code：hesreallyhim/awesome-claude-code @ 29e6b50：CONTRIBUTING.md:15-23、.github/workflows/validate-new-issue.yml:27-28 與 56-72
- MCP Registry：modelcontextprotocol/registry @ 5c3de5c：docs/modelcontextprotocol-io/moderation-policy.mdx:10、20-24、38-45
- Tessl：[評估](https://docs.tessl.io/improving-your-skills/evaluating-skills.md)、[review](https://docs.tessl.io/improving-your-skills/reviewing-skills.md)
- `claude plugin eval`：[文件](https://code.claude.com/docs/en/plugin-evals.md)
- skills.sh 與 Vercel：[Vercel 報告](https://vercel.com/blog/state-of-agent-skills)、[issue #488](https://github.com/vercel-labs/skills/issues/488)
- Codex 精選：[Codex 準則](https://developers.openai.com/plugins/plugin-guidelines)；openai/plugins @ b767f8f：.agents/plugins/marketplace.json
- aitmpl：davila7/claude-code-templates @ cc3f535：cli-tool/src/tracking-service.js:1-9 與 283-298、.github/workflows/skill-security-scan.yml:5-8 與 50-51
- Smithery：[Smithery 併入 Arcade](https://arcade.dev/blog/smithery-joins-arcade)

---

## 4. 題目 2：GitHub 訊號有多可靠

### 4.1 研究證據

- **灌星（StarScout）**：He、Yang、Burckhardt、Kapravelos、Vasilescu、Kästner，ICSE 2026（[arXiv 2412.13459 v2](https://arxiv.org/abs/2412.13459)）。〔已複查〕
  - 規模：2019 到 2024 年約有 600 萬顆疑似假星。保守後處理後剩 18,617 個 repo、30.1 萬個帳號、381 萬顆。
  - 2024 年 7 月，至少 50 星的熱門 repo 裡有 16.66%（3,499 個）出現假星活動。
  - 偵測方法有兩種：
    - 低活動帳號：只按過一次星，同一天最多再有一個事件。
    - 同步群聚：50 個帳號在 30 天內一起替 10 個 repo 按星。
  - 效果：假星只在短期（約兩個月內）有拉抬效果，長期反而是負擔。作者建議星數不要單獨拿來做高風險決策，可以改成依帳號活躍度加權。
- **下載數**：npm 官方說明，下載數是 tarball 回應的單純計數，CI、鏡像、機器人都算進去，絕對不等於使用者數（[npm blog](https://blog.npmjs.org/post/92574016600/numeric-precision-matters-how-npm-download-counts-work.html)）。〔已驗證〕
  - 用 `npx` 啟動的 MCP server，每次沒命中快取的啟動都可能多計一次。〔推論〕
- **安裝數**：skills.sh 的遙測是沒有驗證的 GET，可以偽造（程式已複查；可偽造屬推論）。ClawHub 已有灌下載數讓後門 skill 被執行的實例（見第 3 節）。
- **星數與實際效益**：子研究在搜尋範圍內沒有找到把星數或安裝數跟實測效益連起來的研究。沒找到不代表不存在。
- **GitHub 平台變動**：
  - GitHub 2026-06-30 公告，列出 stargazers 與 watchers 的 API 只開放給 admin 與 collaborator，理由是這些清單被拿去蒐集使用者資料、發垃圾訊息（[changelog](https://github.blog/changelog/2026-06-30-upcoming-access-restrictions-to-public-api-endpoints-and-ui-views/)）。〔已複查〕
  - 2026-11-05 實測：查第三方 repo 的 stargazers 回 404，但 repo 的公開事件 API 仍然有 WatchEvent（floorplan 最近 100 個事件裡有 84 個）。〔已驗證〕
  - 結論：StarScout 那種逐一檢查帳號的做法，現在不適合自己做，也不應該做。只用事件的時間戳算星數速度，不碰個別帳號。

### 4.2 名冊實測〔已驗證，本研究，2026-11-05，50 個不重複的 GitHub repo〕

- **星數**：
  - 中位數 31,000；41 個超過 1 萬，15 個超過 10 萬。
  - 平均每天增加的星數，中位數 137 顆；29 個 repo 每天 100 顆以上。
- **年齡**：
  - 30 個 repo 建立不到一年；8 個不到 120 天。
  - 例子：craft-anything 4 天就有 10,786 星，floorplan 8 天 2,801 星。
- **活動**：
  - 44 個在 7 天內有 push，只有 2 個超過 90 天沒動；40 個在 180 天內發過 release。
  - 也就是說，「最後更新」這個指標同樣篩不掉工具。
- **人員集中**：38 個 repo 的一半 commit 來自同一個人（CHAOSS 的 Contributor Absence Factor 等於 1）。單人專案是常態，只能當風險註記，不能當門檻。
- **爆紅**：近期星速超過平均 2 倍的有 7 個：
  - agent-desktop 41 倍、impeccable 7.5 倍、playwright-cli 5.8 倍、claude-mem 3.6 倍、SeleniumBase 3.3 倍、spec-kit 2.9 倍、mattpocock/skills 2.1 倍。
  - 近期星速用事件 API 最近 300 個事件裡的 WatchEvent 計算。很活躍的 repo，這個窗口可能只有幾小時，數字雜訊大。
- **相關性**：〔計算，相關不代表因果〕
  - 星數跟「issue 有真人回覆的比例」負相關：Spearman −0.28，n=46。越紅的 repo 越回不完 issue。
  - 星數跟 90 天 commit 數正相關：0.42，n=50。
- **現行第 0 層的結果**：0 個 fail、6 個 warn。其中 5 個是 GitHub 偵測不到授權，1 個是少於 50 星。
- **查詢成本**：
  - 50 個 repo 的基本指標共 28 秒。每個 repo 1 次 GraphQL（cost 1），加 1 次 REST。
  - 加上 issue 抽樣與事件查詢，再 93 秒。
  - 登入後的額度是每小時 5,000 次，搜尋每分鐘 30 次。
- **npm 上個月下載數**（2026-10-05 到 11-03，來源 api.npmjs.org）：

  | 套件 | 下載數 |
  |---|---|
  | @playwright/mcp | 27,086,757 |
  | chrome-devtools-mcp | 7,847,694 |
  | agent-browser | 7,321,690 |
  | @playwright/cli | 4,787,907 |
  | impeccable | 938,419 |
  | claude-mem | 94,255 |

- **OpenSSF Scorecard**：查了 8 個名冊 repo，API 都沒有資料（chrome-devtools-mcp 回 404，其餘回空內容），推測是不在每週掃描名單裡。deps.dev 有基本資料，但沒有 Scorecard。要用 Scorecard 得自己跑 CLI。〔已驗證：查詢結果；原因與 CLI 做法屬推論〕

完整表格見附錄 A；腳本與原始資料見附錄 B。

### 4.3 提議：可以用腳本算的「健康與採用度」指標

| 代號 | 指標 | 定義 | 資料來源 | 用法 |
|---|---|---|---|---|
| H1 | 活躍 | 最後 push 是幾天前、預設分支 90 天內的 commit 數 | GraphQL | 180 天沒有 commit 而且 365 天沒有 release，標「停滯」 |
| H2 | 發布 | 180 天內的 release 數、最後一次 release 是幾天前 | GraphQL releases | 排序 |
| H3 | 回應 | 抽 7 到 60 天前開的 issue 20 則：真人回覆比例（排除發文者與 bot）、維護者回覆比例、回覆時間中位數、7 天內關閉的比例。對應 CHAOSS 的 Time to First Response，要排除 bot | GraphQL search | 排序；真人回覆比例低於 0.3 時註記 |
| H4 | 人員集中 | 最少幾個人貢獻一半的 commit（CHAOSS 的 Contributor Absence Factor，舊稱 Bus Factor） | REST contributors | 只註記 |
| H5 | 授權 | SPDX 代號 | GraphQL | 要放進 OmniKit marketplace 再散布時，才當門檻 |
| H6 | 身分變動 | 封存、改名或轉移（full_name 跟卡片不同）、授權變更 | REST | 封存直接 fail；轉移或授權變更要重審 |
| H7 | 安全 | 現有的 skill 掃描、官方 marketplace 收錄、skills.sh 三家稽核、MCP Registry 狀態 | 既有掃描加外部資料 | HIGH 或 CRITICAL 觸發人工複核，不直接當判決 |
| A1 | 下載 | npm 或 PyPI 上個月的下載數，取對數並設上限 | api.npmjs.org、pypistats | 弱排序 |
| A2 | 被依賴 | deps.dev 或 ecosyste.ms 的 dependents 數，只對程式庫有意義 | API | 弱排序 |
| A3 | 策展 | 是否收錄在官方 marketplace、Codex 精選、awesome 清單 | clone 或 API | 弱排序 |
| A4 | 星數與速度 | 星數、平均每天星數、事件 API 算出的近期星速、近期與平均的比值 | GraphQL 加 events | 只用來標「爆紅」與「冷卻期」，不用來加分 |

另外四個旗標：

- **冷卻期**：建立不到 14 天（借 awesome-claude-code 的門檻）。可以做第 1 層，但不排第 2 層，除非你點名。
- **爆紅**：近期星速是平均的 3 倍以上，而且建立不到 90 天。延後一個週期再看。
- **停滯**：見 H1。
- **未知**：API 失敗或查不到。標成「未知」，不當作通過。

**怎麼用：**

1. **只用硬證據篩掉工具**：H6 的封存、H7 經確認的安全問題、相容性不符。其他指標都只能「延後」或「註記」，不能直接淘汰。
2. **只當排序的一個乘數**：健康與採用度只是第 2 層佇列優先序的其中一項（見 7.2）。採用度要取對數並設上限；爆紅會降低優先序，不會提高。
3. **只在打平時分勝負**：第 2 層打平時才用這些指標，順序是：
   - 相容性
   - 成本（token、時間）
   - 風險與權限
   - 健康
   - 採用度
   - 都分不出來，就維持現任

### 4.4 回答：同功能分不出好壞時，能不能用星數、fork 排序

可以，但要放在最後，而且有兩個前提：先去掉灌星與爆紅的干擾，並且先比完成本與風險。

研究和名冊實測都顯示，星數在這個生態沒有鑑別力（4.1、4.2）。fork 對 skill 類工具意義更小：名冊 repo 的 fork 數與星數比，中位數只有 0.093。〔計算〕

U1「同分就比 token」的方向是對的。但單次執行的 token 雜訊可能超過 20%（U1:77），所以同分時的比較，要用至少 3 次執行的中位數。

---

## 5. 題目 3：網路上的測試心得與影片

### 5.1 收集方式〔已驗證，子研究；Reddit 一項例外〕

| 來源 | 怎麼取得 | 限制與風險 | 建議 |
|---|---|---|---|
| GitHub issues 與 discussions | `gh api search/issues`，搭配 windows、codex、sandbox、non-interactive 等關鍵字；登入後每小時 5,000 次，搜尋每分鐘 30 次 | 多半是負面回報，這正是需要的；條款清楚（[使用政策](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)） | 第一優先 |
| Hacker News | Algolia API，不需要金鑰；實測查「chrome devtools mcp」有 55 筆 | 討論多、實測少 | 次要 |
| dev.to | Forem API，不需要金鑰；回應有 `ai_disclosure_label` 欄位 | 抽樣的文章都沒有揭露 | 次要 |
| YouTube | Data API 的 `videos.list` 每次 1 unit，每天預設 10,000 units；有 `paidProductPlacementDetails.hasPaidProductPlacement` 欄位，但由創作者自己勾選。官方的字幕下載需要影片的編輯權限；YouTube 條款禁止未經許可的自動化存取 | 批次抓字幕有條款風險 | 只用官方 API 拿影片資訊；需要看內容時，用 Gemini API 直接讀公開影片網址（官方管道） |
| SponsorBlock | 群眾標記的業配段落，可以標「整支都是業配」 | 資料授權是 CC BY-NC-SA 4.0；冷門影片多半沒有資料 | 只存推導出來的旗標，並註明出處 |
| Reddit | 據說 2025-11 起官方 API 改成審核制〔未證實〕 | 不明 | 不當主要管道 |
| X | 讀一則 0.005 美元 | 貴、雜訊多 | 不用 |
| 廠商自己寫的比較文 | 搜尋 | 有利益衝突。browser-use 的比較文把自家兩個產品排在前兩名，但文中四個工具的成功率其實差不多（data/tools/browser-use.yaml:10） | 只當線索 |

### 5.2 可信度怎麼判斷

- **兩種現成框架可以借：**
  - Admiralty code：把「來源可不可靠」和「這則資訊可不可信」分開評。
  - GRADE：依偏誤、不一致、間接性、不精確、發表偏誤逐項降級。
  - 對 OmniKit 最致命的是間接性：別人用的模型、harness、作業系統、專案都跟你不同。
- **業配揭露率很低**：Mathur 等人（CSCW 2018，[arXiv 1809.00620](https://arxiv.org/abs/1809.00620)）看了 50 萬支 YouTube 影片，聯盟行銷內容只有約 10% 有任何揭露。所以沒揭露不代表沒有業配。〔已驗證〕
- **評分規則**（子研究設計的，尚未驗證）〔推論〕：
  - 起點看方法：

    | 方法 | 起始等級 |
    |---|---|
    | 有對照組，而且至少跑 3 次 | 高 |
    | 只跑一次，但有數字 | 中 |
    | 個人心得 | 低 |
    | 行銷文 | 極低 |

  - 降一級的情況：作者不獨立；任務、模型、作業系統、agent 跟你的不同（每一項各降一級）；已過期。
  - 升一級的情況：結論違反作者自身利益；兩個獨立來源說法一致。
- **正反證據的用法不對稱：**
  - 負面、而且可以客觀查證的事（不支援 Windows、非互動模式不能用、已封存、出過安全事件），一則中等以上的證據就能拿來排除或降低優先序。
  - 正面的品質說法，最多只能把工具送進第 2 層，不能讓它跳過第 2 層。

### 5.3 證據卡（建議格式，可以用腳本填）

```yaml
id: ev-20261105-001
tool: chrome-devtools-mcp
tool_version_tested: 1.12.0      # 原文沒寫就填 unknown
slot: browser
scenarios: [U1]
source: {type: issue, url: ..., ts: "t=312s", author: ..., published: 2026-10-20, retrieved: 2026-11-05}
independence: independent        # vendor | competitor | sponsored | affiliate | unknown
disclosure: {yt_paid_flag: false, sponsorblock_full: null, affiliate_links: 0}
setup: {agent: codex-cli, model: ..., os: windows, mode: exec}
method: anecdote                 # controlled-ab | benchmark | single-run | marketing
comparator: none                 # baseline | incumbent:<id>
runs: 1
kind: elimination                # capability | quality | cost
direction: "-"
claim: 自己改寫的一句話
quote: 原文最多 15 字
reliability: B                   # Admiralty A 到 F
credibility: 2                   # Admiralty 1 到 6
certainty: low                   # GRADE 四級
expires: 2027-02-05              # 工具跨 minor 版本或滿 90 天就過期
```

### 5.4 2026 年 skill 與 MCP 效用研究

| 研究 | 規模 | 主要數字 | 對 OmniKit 的意涵 |
|---|---|---|---|
| [SkillsBench](https://arxiv.org/abs/2602.12670) v4（2026-06-14）〔已複查〕 | 87 題、8 個領域、18 組模型與 harness 的組合 | 見表下說明 | 只有精選、精簡的 skill 有用；Merge 判定或自己寫的 skill 一定要實測；Claude 端要記錄有沒有被叫用 |
| [SWE-Skills-Bench](https://arxiv.org/abs/2603.15401) v2（2026-10-27）〔已複查〕 | 98 個公開的軟體工程 skill，3,920 組配對 | 92 個沒有顯著效果；平均通過率 76.6% 到 76.9%；有幫助的最多 +17.7，有害的最多 −17.0，有害的多半是寫死的範本蓋掉了任務指示 | 先驗應該是「沒效果」；有害的情況是真的會發生 |
| [Signal or Noise](https://arxiv.org/abs/2608.23067)（2026-08-24）〔已複查〕 | 31 個網頁開發 skill、50 個專案共 1,000 題、4 個模型 | Pass@2 下降 1.3% 到 4.2%；token 增加 72% 到 394%；只有 17% 到 36% 的「skill 對專案」組合有增益；排名跨模型轉移很弱；建議用等長的無關內容當對照，並逐模型審核 | 便宜模型的結果不能代表你實際用的模型 |
| [How Well Do Agentic Skills Work in the Wild](https://arxiv.org/abs/2604.04323)（2026-04-06）〔已複查〕 | 約 3.4 萬個 skill 的 skill 池 | 越接近真實（讓 agent 自己找 skill），效益越接近沒裝；加上檢索與改寫，Opus 4.6 在 Terminal-Bench 2.0 從 57.7% 升到 65.5% | 裝一大堆讓 agent 自己挑，效益會消失 |
| [ACES](https://arxiv.org/abs/2608.20614)（2026-08-20）〔已複查〕 | 145 個 skill；947 組配對 | 靜態結構分數跟 LLM 評審分數的 Spearman 相關只有 0.14；72.8% 的配對有正效益，效益多半出現在流程指標 | 靜態審查不能取代實跑 |
| [Vercel：AGENTS.md vs skills](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)（2026-01-27）〔已複查〕 | Next.js 16 的 API 題目，題數未公開，是廠商自己跑的 | 沒裝 53%；裝了 skill 還是 53%，因為 56% 的案例沒叫用；明確指示要用時 79%；把 8KB 的文件索引放進 AGENTS.md 是 100%；結果對措辭很敏感 | 第一件要量的是「有沒有被叫用」 |
| 安全研究〔已驗證〕 | [2601.10338](https://arxiv.org/abs/2601.10338)：31,132 個 skill；[MalSkillBench](https://arxiv.org/abs/2606.07131) | 26.1% 至少有一個漏洞；最強的偵測器抓程式碼注入的召回率有 98.4%，碰到 prompt injection 就失效 | 掃描器只能當觸發器 |
| MCP 與工具數量〔已驗證〕 | [LiveMCPBench](https://arxiv.org/abs/2508.01780)、[Anthropic advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)、[MCPMark](https://arxiv.org/abs/2509.24002) | 工具池 527 個時，將近一半的失敗是選錯工具；58 個工具的定義就吃掉約 55K token，改用 tool search 後 Opus 4 從 49% 升到 74%；gpt-5-medium 單次通過 52.56%，連續 4 次都通過只剩 33.86% | 工具少裝；穩定度要用 `pass^k`（k 次全過）量 |

SkillsBench 的主要數字：

- 加上人工整理的 skill，平均通過率從 33.9% 升到 50.5%（+16.6 pp）。
- 模型自己生成的 skill，反而比沒裝還差 8.1 到 11.5 pp。
- 依 skill 數量：給 1 個 +18.0 pp；給 4 個以上只剩 +10.1 pp。
- 依寫法：寫成完整文件型的只有 +0.7 pp。
- 87 題裡有 13 題變差。
- 軟體工程領域只有 +11.6 pp。
- 實際有沒有叫用 skill：Codex 搭 GPT-5.5 是 99.2%，Claude Code 搭 Opus 4.7 只有 68.2%（附錄 K）。

### 5.5 結論：能不能先看網路心得來縮小測試範圍

可以，但只拿來「排除」和「排序」：

1. **先撈 GitHub issues 找環境問題。** U1 的勝負就是環境決定的。一則可以查證的負面證據，就能把工具排到後面或排除。
2. **正面心得不能讓工具跳過第 2 層。** 上述三篇研究都顯示，skill 的效果綁在模型、harness 和專案上，別人的正面結果很難套到你的環境。正面心得最多只能讓工具早一點進第 2 層。
3. **影片只用官方管道。** 影片資訊用 Data API，內容用 Gemini 官方管道，不要批次抓字幕。
4. **證據卡要有到期日。** 引用原文要短。

---

## 6. 題目 4：降低實測成本的方法與偏誤

| 方法 | 做法 | 省什麼 | 偏誤與風險 | 對策 |
|---|---|---|---|---|
| 只讓挑戰者跟現任比 | 每次第 2 層一定包含現任；沒有現任的槽位，用原生功能或「沒裝」當基準 | 不用全部互相比 | 現狀偏誤：打平就留現任，可能錯過「一樣好但更便宜」的；現任本身也可能過時 | 打平時再比成本；現任每季跑一次回歸套件；原生功能也算一個挑戰者 |
| 同一個情境一次測多個工具 | 共用同一套素材（假後端、埋點、資料）與決策規則；contract 上限是 3 個 | 準備素材是大頭（F1 準備了兩輪資料），一次攤提 | 工具互相干擾（同時裝就分不出效果：caveman.yaml:15）；前一組留下的狀態，例如 Claude 看到前一次試驗的 git 歷史（[Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)），或 F1 殘留的瀏覽器設定 | 每組用獨立的 HOME、worktree、無痕設定檔；一次只裝一個工具 |
| 盲評 | 密封對照表（F1 的 mapping.sealed 加 SHA-256 核對） | 不省錢，省偏誤 | 風格指紋（例如金色的選取狀態）讓人猜得出是誰；LLM 偏好自己產生的內容 | 用不同家族的模型評分；評審只看結果、不看工具名 |
| 便宜模型執行、強模型評分 | Haiku 或 mini 級模型執行，強模型評分 | 執行的 token 便宜很多 | 效果跨模型轉移很弱（Signal or Noise）；SkillsBench 也指出小模型加上 skill 可以追上沒裝 skill 的大模型，代表效益大小會隨模型改變。所以便宜模型上的勝負，不能代表你實際用的模型 | 只用在煙霧測試：裝得起來、會被叫用、不會壞。品質決定一律用你實際的模型與 harness |
| 強模型當評審 | 用 LLM 打分或兩兩比較 | 省你的時間 | 見表下說明 | 兩種順序都評，結果一致才算；分項各自評；給「無法判斷」的選項；用你的盲選結果校準；差距小就算平手 |
| 兩兩比較或錦標賽 | Bradley-Terry 或 Elo 排名；先打資格賽再打決賽 | 比全部排序少很多次 | 可能不遞移；樣本少時排名不穩；公開排行榜可以靠選擇性揭露操弄，例如 Meta 在 Llama-4 發表前測了 27 個私有變體（[Leaderboard Illusion](https://arxiv.org/abs/2504.20879)） | 只在同槽位、同一套素材內使用；資格賽用客觀檢查點，決賽才找你 |
| 依槽位重要性分配額度 | 優先序 = 痛點 × 使用頻率 × 最佳候選的證據等級（見 7.2） | 額度用在會改變決定的地方 | 低優先的槽位被餓死；痛點的評估主觀 | 每季對 watch 槽位做一次免費掃描；痛點寫在槽位卡上，可以追溯 |
| 日常使用紀錄當持續評估 | usage.py 的叫用次數；Claude Code v2.1.252 起的 `/skill-doctor`，會列出每個 skill 佔多少 context、多常被用（[文件](https://code.claude.com/docs/en/skills.md)） | 免費 | 「有用」不等於「被叫用」：Vercel 的評測有 56% 沒被叫用，可能是觸發失敗而不是沒價值；「被叫用」也不等於「有幫助」；描述寫得太廣會被多叫；每個月做的工作本來就不同 | 只拿來判斷「沒在用」，以及「試用期間有沒有被叫用」，不拿來判斷品質 |
| 平台內建了，就淘汰外掛 | 追蹤 Claude Code 與 Codex 的 changelog；出現重疊功能時，用該槽位的回歸套件測原生功能 | 一次換掉整類外掛 | changelog 寫的跟實際能力有落差，例如 Codex 內建瀏覽器在 exec 模式不能用（U1:62） | 一定要在素材上實際驗證；Codex 準則本來就要求 plugin 提供內建沒有的功能 |
| 實測素材轉成回歸套件 | 通過的能力評估轉成回歸測試（Anthropic 的建議）；工具大改版或模型升級時重跑 | 之後每次的成本接近煙霧測試 | 套件飽和：全過之後就沒有訊號 | 定期加入新的真實失敗案例 |

LLM 評審已知的偏誤：

- 位置偏誤：只換排列順序，Vicuna-13B 就能在 80 題裡贏 ChatGPT 66 題（[2305.17926](https://arxiv.org/abs/2305.17926)）。
- 冗長偏誤與自我偏好（[MT-Bench](https://arxiv.org/abs/2306.05685)）。越能認出自己產生的內容，就越偏好它（[2404.13076](https://arxiv.org/abs/2404.13076)）。
- 碰到困難的配對，GPT-4o 等級的評審只比亂猜好一點（[JudgeBench](https://arxiv.org/abs/2410.12784)）。
- GPT-4 評審跟人的一致率超過 80%，跟人與人之間的一致率相當（MT-Bench）。

以上都已複查。

**統計上的提醒**

- **Miller（[2411.00640](https://arxiv.org/abs/2411.00640)）的建議**〔已複查〕：
  - 報出標準誤。
  - 題目彼此相關時，用叢集標準誤。
  - 重抽樣降低變異。
  - 比較兩個模型時，用題目層級的配對差。他指出這等於「免費」降低變異。
  - 用檢定力分析確認這組題目測得出差異。
- **少量重跑的誤判率**〔計算，本研究模擬，假設檢查點互相獨立，所以偏樂觀〕：情境是 4 個二元檢查點。

  兩個工具一樣好（通過率都是 70%）時，誤判挑戰者勝出的機率：

  | 判定規則 | 跑 1 次 | 跑 3 次 | 跑 5 次 |
  |---|---|---|---|
  | 總分高就算贏 | 35% | 41% | 43% |
  | 平均每次多 1 個檢查點才算贏 | — | 13% | 6% |

  代價是：挑戰者真的好 25 個百分點（60% 對 85%）時，嚴格規則只抓得到 58% 到 60%。

- **結論**：小樣本下寧可錯過，也不要亂換。打平就維持現任，用嚴格門檻才發通知。錯過的好工具，下一輪有新證據時還會再回來。

---

## 7. 建議的評估漏斗

### 7.1 各層

| 層 | 做什麼 | 誰做 | 成本 | 輸出 | 進下一層的門檻 |
|---|---|---|---|---|---|
| **0：身分、門檻與健康** | 見表下說明 | 腳本；改用 `gh` 或 `GITHUB_TOKEN` 環境變數，避開未登入每小時 60 次的上限 | 0 LLM token；50 個 repo 的指標約 2 分鐘（實測）；掃描另外依 repo 大小計 | 第 0 層 JSON，加上 health、adoption、flags 三組欄位 | 只有四種情況會 fail：已封存；確認惡意，或有未解決的 HIGH／CRITICAL；授權不允許再散布（要進 OmniKit marketplace 時）；跟槽位要求的 agent 不相容。其他一律只 warn |
| **1：情境對應、去重、原生比對** | 把 README、SKILL.md、manifest 當資料讀；決定槽位與情境；列出可以查證的主張（例如「支援 `codex exec`」「原生 Windows」）；對照「平台內建功能表」看是否已被原生涵蓋；同槽位、同做法的分成一群，每群挑 1 到 2 個代表；用 layer1.schema 寫卡片 | 便宜模型，背景執行（OmniKeep） | README 中位數 18,915 bytes，約 5k token（實測）；加上指示與 peers 輸出，每張約 10k 到 25k token〔推論〕 | 卡片與第 1 層 JSON（建議加上 claims 與 cluster 欄位） | 符合以下全部才進候選佇列：對得上 active 槽位的真實情境；提供現任沒有的能力，或現任在該情境有已知缺口；沒被原生涵蓋；不是同群裡較弱的重複。不符合的，大多記「先收著」，只有不在範圍內或確定重複的才記「拒絕」 |
| **1b：外部證據** | GitHub issues、HN、dev.to、YouTube 的影片資訊、基準論文（例如名冊工具有沒有出現在 SWE-Skills-Bench 的 98 個 skill 裡）、registry 分數（Tessl、官方 marketplace）；整理成證據卡並分級 | 腳本抓資料，便宜模型整理 | 每個工具約 20k 到 50k token〔推論〕 | 證據卡（5.3） | 負面而且可以查證的證據：排除或降低優先序。正面證據：只提高排序 |
| **1c：煙霧測試與靜態審查** | 在隔離環境（新的 HOME、worktree、無痕設定檔）安裝，跑一次縮小版的情境，確認：裝得起來、會被叫用、Codex 非互動模式與 Claude 都能跑；量 context 成本（SKILL.md 大小、MCP 工具定義的 token）；有 hook、MCP 或可執行程式的，再照 Anthropic 政策 prompt 的三個旗標審程式碼 | 腳本加便宜模型；靜態審查用強模型 | 煙霧測試每個 agent 一次約 0.12M 到 0.25M 輸入 token（參考 U1）〔推論〕；靜態審查 30k 到 80k token〔推論〕 | 煙霧測試結果、context 成本、政策旗標 | 裝得起來；兩邊都能用（槽位要求時）；會被叫用，或可以用規則明確叫用；沒有政策等級的問題；不在冷卻期 |
| **2：情境實測** | 見表下說明 | 強模型執行，用你實際的模型與 harness；評分用不同家族的模型；品味題由你盲選 | 客觀短題（U1 型）每次 0.12M 到 0.25M 輸入 token；重題（F1 型）每次 3.07M 到 3.90M、約 16 分鐘 | 第 2 層結果 JSON（建議加上 runs、invoked、effect 與不確定性） | 見第 10 節的 E4 條件 |
| **3：試用與持續評估** | 兩週試用（現行做法）；用 usage.py 看試用期間有沒有被叫用、有沒有出錯、有沒有被你手動繞過；第 2 層的素材轉成回歸套件，在工具大改版、模型升級、平台 changelog 出現重疊功能時重跑；30 天沒用到就建議退役（現行做法） | 腳本；你只在週報確認 | 回歸套件每次約 1M token 以內〔推論〕 | 試用結論、退役建議 | 試用期間有被叫用、沒有退步，才轉成預設 |

第 0 層的工作內容：

- 補齊身分：沒有 url 的 49 張，用 `gh search repos` 加名稱比對找出候選；比對不明確的列進週報，讓你勾選。
- 依 repo 去重。
- 查封存、授權、身分變動。
- 查相容線索：有沒有 `.claude-plugin/plugin.json`、`skills/*/SKILL.md`、AGENTS.md，以及 CI 有沒有跑 Windows。
- 安全：現有的掃描，加上官方 marketplace 收錄、skills.sh 三家稽核、MCP Registry 身分。
- 算出 4.3 節的健康與採用度指標和旗標。

第 2 層的做法：照現行的第 2 層，另外加上這幾項：

- 每個槽位一次測「現任加上最多 2 個挑戰者」，共用同一套素材。
- 客觀檢查點每組至少跑 3 次，做配對分析；勝出門檻事先寫好。
- 記錄每次有沒有被叫用。
- 純提示型的 skill，加一組長度相同的對照。
- Claude 端可以用 `claude plugin eval`：給 shell 權限的套件要在 WSL2 跑；用 `--max-cost-usd` 設上限。
- Codex 端用 `codex exec`。

### 7.2 第 2 層的排程優先序（取代 digest.py:86-91 的「待評估張數」）

優先序 = 槽位權重 × 痛點 × 使用頻率 × 候選的證據等級。

各因子的給分：

- **槽位權重**：active 1、watch 0.3、frozen 0。
- **痛點**：
  - 3 分：槽位沒有現任（output-compression、tool-discovery、behavior-rules），或現任已知沒解決問題（frontend-design 的卡片 reason 寫明沒解決核心痛點：data/tools/frontend-design.yaml:12）。
  - 2 分：現任還在試用。
  - 1 分：現任夠用。
- **使用頻率**：依 usage.py 近 30 天相關工具的對話數，分成 1 到 3 分。
- **證據等級**：第 1b 層的最高等級，對應 1 到 3 分。
- **排除**：凍結槽位、冷卻期內的、健康是「停滯」或「未知」的。

### 7.3 active 槽位怎麼跑〔推論：第 1 層還沒實際跑，下表是依卡片內容推估〕

| 槽位 | 第 1 層之後可能留下的 | 第 2 層的形式 | 次數 |
|---|---|---|---|
| browser（9 張） | agent-browser、playwright-mcp、browser-mcp、browser-harness。browser-use 和 SeleniumBase 是程式庫、Browserbase 是雲端服務、Skyvern 是應用程式，不屬於 U1 要的工具（browser-use.yaml:10 已經這樣註記） | 先在 U1 素材上用 Codex exec 跑客觀資格賽，全自動；前 1 到 2 名再對上試用中的 chrome-devtools-mcp | 1 到 2 |
| code-understanding（8 張） | C1（找呼叫者）：codegraph、claude-lsp；C2（深讀第三方 repo）：deepwiki-mcp、deepwiki-open。serena 已經有 RIA 的實測結論（serena.yaml:14）；context7 是查文件，換槽位或先收著 | C1 客觀（跟 grep 結果比對）；C2 較重 | 1 到 2 |
| frontend-design（4 張） | ai-design-skills、craft-anything（建立 4 天，冷卻到約 2026-11-15，對應 F3）、claude-design | F2 或 F3，你盲選 | 1 |
| memory（3 張） | claude-mem（hook 範圍要先做靜態審查）、planning-with-files、ce-handoff | M1 或 M2，重題 | 1 |
| review（3 張） | pullboard（建立 28 天）、claudex-loop（偵測不到授權）、codex-security（只有 Codex、沒有 url） | R1 | 0 到 1 |
| output-compression（2 張） | rtk、token-economizer | T1 客觀：token 有沒有減少，失敗資訊有沒有保留 | 1 |
| tool-discovery（3 張） | aihot、find-skills、mcp-registry | N1：涵蓋率跟一份參考清單比 | 1 |
| behavior-rules（2 張） | ponytail、karpathy-guidelines | B1 客觀：diff 有沒有超出範圍，再加評審 | 1 |
| 合計 | | | 7 到 10 次 |

---

## 8. 估算：104 張跑完要多久、多少 token

### 8.1 依據

**實測值**：

- U1 每次執行的輸入 token 是 117,651 到 245,892，F1 是 3,068,285 到 3,899,100，兩者大多是快取。
- README 中位數 18,915 bytes。
- 50 個 repo 的 API 指標約 2 分鐘。

**假設**〔推論〕：

- 第 1 層的通過率：45% 到 65%。
- 第 1c 層的通過率：55% 到 75%。
- 客觀題每組跑 3 次；重題每組跑 1 到 2 次，再加上你的盲選。
- 前兩週跑完後，用實際的通過率回頭校正這些假設。

### 8.2 分階段

| 階段 | 對象 | 數量 | 每單位 | 小計 | 時間 |
|---|---|---|---|---|---|
| A1 補身分 | 沒有 url 的卡片 | 49 張 | 3k 到 8k token（便宜模型） | 0.15M 到 0.4M | 第 1 週 |
| A2 第 0 層 | 所有能對到 repo 的 | 約 100 張 | 0 token | 0 | 第 1 週，幾分鐘 |
| A3 第 1 層 | active 34、watch 8、未分配 15 | 57 張 | 10k 到 25k（便宜模型） | 0.6M 到 1.4M | 第 1 週 |
| B1 第 1b 層 | 第 1 層留下的 | 25 到 35 張 | 20k 到 50k（便宜模型） | 0.5M 到 1.8M | 第 2 週 |
| B2 煙霧測試 | 第 1b 層留下的 | 15 到 22 張，各 2 個 agent | 0.12M 到 0.25M（便宜模型，多數是快取） | 3.6M 到 11M | 第 2 週 |
| B3 靜態審查 | 有 hook、MCP 或程式碼的 | 8 到 12 張 | 30k 到 80k（強模型） | 0.24M 到 0.96M | 第 2 週 |
| C1 第 2 層客觀題 | browser、C1、T1、N1、B1、R1 | 5 到 7 次 | 3 組 × 3 次 × 1 到 2 個 agent × 0.15M 到 0.5M | 6.8M 到 63M | 第 3 到 7 週 |
| C2 第 2 層重題 | frontend-design、memory、C2 | 2 到 4 次 | 3 組 × 1 到 2 次 × 3M 到 4M | 18M 到 96M | 第 3 到 7 週 |
| C3 評審 | 每次第 2 層 | 7 到 10 次 | 0.1M 到 0.5M（強模型） | 0.7M 到 5M | 同上 |

### 8.3 合計

| 部分 | 張數 | 第 2 層次數 | 時間 | token |
|---|---|---|---|---|
| active | 34 | 7 到 10 | 6 到 8 週（每週 2 次）；客觀題若不計入你的額度，約 4 到 5 週 | 約 30M 到 180M |
| watch | 8 | 0 到 2（concise-output 要你盲選） | 第 1 到 2 週，只做到第 1 層 | 約 0.1M 到 10M |
| 未分配 | 15 | 0（多數是 skill 合集，當零件庫） | 第 1 週 | 約 0.2M 到 0.5M |
| 非凍結合計 | 57 | 7 到 12 | **6 到 8 週** | **約 30M 到 190M** |
| frozen | 47 | RIA 之後 3 到 5 次重題 | 解凍後再 2 到 3 週 | 每次 10M 以上（V1 是完整開發流程），合計約 30M 到 150M，也可能更多 |

- 快取比例：U1 是 68% 到 87%，F1 約 96%。大部分 token 落在重題，所以整體會是九成以上快取。實際費用要依你用的方案計算，本報告不換算金額。
- 跟現行做法比：每週 2 次、一次一個工具，104 張約 52 週（positioning.md:23）；就算每次放 2 個挑戰者，也還要約 26 週。〔計算〕
- 你的時間：盲選只出現在 frontend-design、concise-output、凍結的 V1 等少數場次，合計約 2 到 5 次；其他只需要在週報勾選確認。〔推論〕

---

## 9. 要避開的坑

1. **把熱門度當品質。**
   - 星數會被灌（StarScout），npm 下載數是不過濾的計數，skills.sh 的遙測可以偽造。
   - 名冊 50 個 repo 裡有 49 個超過 50 星，現行的星數門檻形同虛設。
2. **被爆紅新專案帶著走。**
   - craft-anything 4 天 10,786 星、floorplan 8 天 2,801 星，都還沒有任何可以觀察的維護紀錄。
   - 設冷卻期（借 awesome-claude-code 的 14 天）。爆紅會降低優先序，不會提高。
3. **把掃描器的嚴重度當判決。**
   - OmniKit 自己標過的 HIGH 和 CRITICAL，人工看過全是誤判。
   - 三家稽核會互相矛盾，而且碰到 prompt injection 幾乎都抓不到（MalSkillBench）。
   - 掃描結果只當「要人工看」的觸發器。
4. **拿通用評測代替你的情境。** Tessl 的 Impact、作者自己寫的 eval、Vercel 這類廠商評測，用的模型、harness、題目都跟你不同；而且研究顯示效果跨模型轉移很弱。
5. **自己生成或 Merge 出來的 skill 不測就用。** SkillsBench 顯示，自己生成的 skill 比沒裝還差 8.1 到 11.5 pp。
6. **把「沒被叫用」當「沒用」，或把「被叫用」當「有用」。**
   - Claude Code 搭 Opus 4.7 的叫用率只有 68.2%（SkillsBench 附錄 K）。
   - Vercel 的評測有 56% 沒被叫用。
   - 第 2 層要分開記：觸發失敗，還是叫用了但沒幫助。
7. **只跑一次就下結論。**
   - U1 自己記了 token 有雜訊（U1:77）。
   - 模擬顯示，兩個工具一樣好時，「總分高就贏」的規則有 35% 到 43% 會誤判挑戰者勝出。
8. **試驗之間互相污染。** Anthropic 記錄過 Claude 讀到前一次試驗的 git 歷史；F1 第二輪的截圖被舊的瀏覽器設定影響。每組都要用乾淨的環境。
9. **素材不像真實使用。** F1 第一輪畫面大多是空狀態，你無法判斷。這一點現行 SKILL.md:48 已經寫進去，要沿用到所有槽位。
10. **LLM 評審的偏誤。**
    - 位置、冗長、自我偏好；碰到困難的配對接近亂猜。
    - 兩種順序都要評；用不同家族的模型；差距小就算平手；品味題以你的盲選為準。
11. **相信公開排行榜的小差距。** Arena 類排行榜可以靠選擇性揭露操弄（Leaderboard Illusion）。
12. **裝太多。**
    - 工具越多越容易選錯（LiveMCPBench、RAG-MCP），光是工具定義就吃掉 context。
    - OmniKit 自己的量測：Codex 的 skill 從 112 個減到 32 個之後，同一個問題的 token 從 27,038 降到 19,695（positioning.md:64-67，另一個 session 的討論稿）。
13. **同時改兩件事。** caveman 和 i-have-adhd 同時裝，就分不出效果（caveman.yaml:15）。試用期一次只換一個工具。
14. **條款與版權。**
    - YouTube 禁止未經許可的自動化存取，Reddit 的 API 也有限制。
    - 證據卡只存改寫後的內容與帶時間點的連結，引用原文要短。
15. **README 裡的 prompt injection。** 例如 agent-browser 的 README 要 agent 去改 AGENTS.md（agent-browser.yaml:13）。一律當資料看，不照著做。
16. **API 查詢失敗就放行。** awesome-claude-code 就是這樣做的。OmniKit 應該把查不到的標成「未知」。
17. **對使用統計 Goodhart。** 描述寫得太廣的 skill 會被多叫；叫用次數不能拿來當品質分數。
18. **證據過期。** 工具改版、模型升級之後，舊的實測和心得要降級。卡片要記版本，並跟著工具大改版重測。
19. **建立在會變動的平台 API 上。** stargazers 清單 2026-06-30 起就不再對外開放。指標要有替代來源，也要容許欄位缺漏。
20. **忘了先問原生功能能不能做。** U1 裡原生 Claude 拿到滿分（U1:44）；positioning.md:22 也指出，11 個預設裡有 7 個是內建功能。每個槽位都要把原生功能當一個挑戰者。

---

## 10. 「有更好的選擇時通知你」的證據門檻

### 10.1 證據等級與通知方式

| 等級 | 條件 | 通知方式 |
|---|---|---|
| E0：熱門度 | 星數、安裝數、trending、下載數 | 不通知；只影響佇列順序，而且有上限 |
| E1：主張 | README、廠商比較文、單一心得或影片 | 不通知；寫進卡片的 notes |
| E2：外部可信證據 | 至少 2 個獨立來源，90 天內、版本相符、測的是同類任務；或有對照組的第三方評測（Tessl 的有裝和沒裝、基準論文） | 週報的「值得實測」區，每週最多 3 則 |
| E3：OmniKit 初測 | 通過第 1c 層煙霧測試，並在資格賽（客觀檢查點、至少 3 次、配對）贏過現任 | 週報的「建議排第 2 層」區，不另外通知 |
| E4：OmniKit 實測勝出 | 第 2 層照事先寫好的規則勝出（條件見下），或你盲選選中 | 主動通知一次：建議 Update，進兩週試用 |

### 10.2 E4 要同時符合的條件

1. **硬性條件全過。** 槽位要求 Claude Code 與 Codex 都能用時，兩邊都要過。
2. **主要指標的差距達到事先寫好的門檻。** 至少 3 次配對執行裡要贏 2 次以上；用「平均每次多 1 個檢查點」這類有餘量的規則，不用「總分高就贏」。品味題以你的盲選為準，評審分數只當說明。
3. **成本沒有明顯變差。** token 或時間的增加，不超過事先寫好的上限。
4. **工具本身沒有風險旗標。** 健康不是「停滯」或「未知」；不在冷卻期；沒有未解決的 HIGH 或 CRITICAL。
5. **打平就維持現任（Keep），不通知。**

### 10.3 防止亂通知

- 主動通知每週最多 1 則（安全警報除外），其他的都進週報。
- 同一個槽位做完判定後，30 天內不再通知同一類工具，除非出現新證據：工具大改版、新的獨立來源，或平台有變。
- 同一群相似的工具，只通知代表。
- 證據滿 90 天或工具跨 minor 版本就降一級。
- 每則通知都附上：比較對象、評估紀錄的連結、差距與執行次數、沒驗證到的部分、試用到期日。

### 10.4 例外

**立即通知，不受每週額度限制。** 現任或試用中的工具有下列任一情況：

- 出現安全事件。
- 被封存或轉移所有權。
- 授權變更。
- 新版本加了範圍過寬的 hook，或未揭露的遙測（Anthropic 政策 prompt 的旗標）。

**只進週報。** 以下兩種退役提醒：

- 30 天沒用到。
- 原生功能已經涵蓋，而且回歸套件通過。

**通知範例：**

> 前端設計（F2）：X 依 2026-11-20 的決策規則勝出（3 次配對贏 3 次；你盲選選 X）。建議 Update：X 試用到 12-04，frontend-design 維持預設到試用結束。沒驗證到：Codex 互動模式。紀錄：data/evals/2026-11-20-frontend-design-F2.md

---

## 11. 還不確定的地方

- **7.3 和 8.x 的通過率是假設。** 第 1 層還沒在 104 張上實際跑過。建議前兩週跑完後，用實際值重新估算。
- **token 的基準只來自兩次評估的 7 次 Codex 執行。** Claude 端與評審的 token 沒有記在評估紀錄裡。
- **維護者回覆比例可能被低估。** 用的是 GitHub 的 authorAssociation；組織成員沒公開身分時，可能顯示成 CONTRIBUTOR。〔推論〕
- **近期星速只靠事件 API 最近 300 個事件。** 很活躍的 repo，窗口可能只有幾小時；而且 GitHub 已經限縮過一次相關 API，之後可能再改。
- **skills.sh 的稽核端點不是公開 API**（子研究從 CLI 原始碼找到），可能隨時改變。
- **Tessl 的兩個限制：** 從 commit 出題會把 repo 歷史上傳到第三方；US 區預設用 `deepseek-v4.1-flash`。要不要用，由你決定。
- **`claude plugin eval` 在這台的可行性沒有實測。** 原生 Windows 沒有沙箱，給 shell 權限的套件要在 WSL2 跑；這台有沒有 WSL2、效能如何，都還沒驗證。
- **Reddit API 的現況、Smithery 的評分方式〔未證實〕。**
- **基準研究的母體跟名冊不同。** 研究的是軟體工程、網頁開發、Terminal-Bench；推廣到記憶、瀏覽器、壓縮這類工具，屬於推論。
- **漏斗內的門檻沒有回測過。** 健康分級、冷卻期 14 天、爆紅 3 倍、E4 的差距門檻，都是建議值。

---

## 附錄 A：active 槽位工具的 GitHub 指標（2026-11-05）

計算方式：

- 星數與速度：「平均星／天」是星數除以建立天數；「近期／平均」是事件 API 最近 300 個事件裡的 WatchEvent 速度，除以平均星速。
- 180 天 release：只抓最近 30 筆，所以 30 代表 30 以上。
- 半數貢獻人數：最少幾個人貢獻一半的 commit。
- issue 回覆比：抽 2026-09-06 到 2026-10-29 開的 issue，最多 20 則，排除維護者自己開的；「—」代表窗口內沒有 issue。
- 授權：「無」或 NOASSERTION 代表 GitHub 偵測不到授權。

| 槽位 | 卡片 | 狀態 | 星數 | 建立天數 | 平均星／天 | 近期／平均 | 90 天 commit | 180 天 release | 半數貢獻人數 | issue 人類回覆比 | 維護者回覆比 | 授權 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| behavior-rules | ponytail | pending | 184,354 | 145 | 1271.4 | 0.76 | 163 | 30 | 1 | 0.0 | 0.0 | MIT |
| browser | agent-browser | pending | 45,507 | 297 | 153.2 | 0.96 | 168 | 30 | 1 | 0.3 | 0.1 | Apache-2.0 |
| browser | browser-harness | pending | 18,867 | 201 | 93.9 | 0.33 | 302 | 14 | 2 | 0.32 | 0.0 | MIT |
| browser | browser-mcp | pending | 7,287 | 586 | 12.4 | 0.68 | 22 | 0 | 1 | 1.0 | 0.0 | Apache-2.0 |
| browser | browser-use | pending | 120,022 | 734 | 163.5 | 0.63 | 408 | 18 | 2 | 0.3 | 0.0 | MIT |
| browser | chrome-devtools-mcp | trial | 54,787 | 419 | 130.8 | 0.52 | 492 | 17 | 2 | 0.61 | 0.39 | Apache-2.0 |
| browser | playwright-cli | pending | 14,952 | 2,328 | 6.4 | 5.77 | 23 | 11 | 2 | 0.47 | 0.35 | Apache-2.0 |
| browser | playwright-mcp | pending | 39,173 | 592 | 66.2 | 1.26 | 39 | 10 | 2 | 0.55 | 0.35 | Apache-2.0 |
| browser | seleniumbase | pending | 13,225 | 4,627 | 2.9 | 3.31 | 312 | 30 | 1 | 1.0 | 1.0 | MIT |
| browser | skyvern | pending | 23,340 | 980 | 23.8 | 0.29 | 920 | 22 | 3 | 0.15 | 0.0 | AGPL-3.0 |
| code-understanding | codegraph | pending | 76,546 | 289 | 264.9 | 0.68 | 999 | 30 | 1 | 0.35 | 0.2 | MIT |
| code-understanding | floorplan | pending | 2,801 | 8 | 350.1 | 0.85 | 120 | 22 | 1 | 1.0 | 1.0 | MIT |
| code-understanding | graphify | pending | 142,291 | 215 | 661.8 | 1.13 | 1,481 | 30 | 1 | 0.55 | 0.45 | Apache-2.0 |
| code-understanding | serena | pending | 31,091 | 590 | 52.7 | 0.94 | 376 | 10 | 1 | 0.2 | 0.05 | NOASSERTION |
| frontend-design | ai-design-skills | pending | 14,118 | 98 | 144.1 | 1.44 | 13 | 0 | 1 | 1.0 | 0.0 | MIT |
| frontend-design | craft-anything | pending | 10,786 | 4 | 2696.5 | 1.5 | 355 | 3 | 4 | — | — | Apache-2.0 |
| frontend-design | frontend-design | default | 187,350 | 408 | 459.2 | 0.83 | 15 | 0 | 2 | 0.35 | 0.0 | 無 |
| frontend-design | impeccable | pending | 102,473 | 353 | 290.3 | 7.5 | 1,204 | 30 | 1 | 0.57 | 0.57 | Apache-2.0 |
| memory | ce-handoff | pending | 25,924 | 390 | 66.5 | 0.56 | 434 | 30 | 1 | 0.16 | 0.16 | MIT |
| memory | claude-mem | pending | 112,612 | 429 | 262.5 | 3.58 | 1,516 | 30 | 1 | 0.8 | 0.75 | Apache-2.0 |
| memory | planning-with-files | pending | 27,881 | 305 | 91.4 | 0.28 | 258 | 30 | 1 | 1.0 | 1.0 | MIT |
| output-compression | rtk | pending | 85,555 | 286 | 299.1 | 0.44 | 1,167 | 30 | 2 | 0.39 | 0.33 | Apache-2.0 |
| output-compression | token-economizer | pending | 4,759 | 22 | 216.3 | 0.6 | 110 | 1 | 1 | 1.0 | 0.5 | Apache-2.0 |
| review | claudex-loop | pending | 3,346 | 152 | 22.0 | 0.7 | 33 | 0 | 1 | 0.17 | 0.08 | NOASSERTION |
| review | pullboard | pending | 670 | 28 | 23.9 | 1.56 | 7,341 | 30 | 1 | 0.75 | 0.75 | MIT |
| tool-discovery | aihot | pending | 21,955 | 212 | 103.6 | 1.08 | 16 | 1 | 1 | 0.25 | 0.0 | MIT |

說明：

- frontend-design 對應的是 anthropics/skills 整個 repo，所以 commit 與 release 數反映的是整個 repo。
- ce-handoff 對應的是 EveryInc/compound-engineering-plugin。

## 附錄 B：證據索引

### B.1 clone 的研究對象

都放在 C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\research\eval\，用 `git clone --depth 1`，只讀、沒有執行任何程式。

| repo | HEAD 完整 SHA |
|---|---|
| vercel-labs/skills | 9197d919034d19010ae303cf96bf19ad087dd4be |
| davila7/claude-code-templates | cc3f5356409d09bd7596496eb9b265b2225e195f |
| anthropics/claude-plugins-official | fa4eb54397ee2faccb6940512a19c017cb1337f3 |
| hesreallyhim/awesome-claude-code | 29e6b50b057dc7ae513fa1018bf36a009786f372 |
| modelcontextprotocol/registry | 5c3de5cc204f0a8cb4464ba50a011546eabbd4b8 |
| openai/plugins | b767f8fa3be1a22b093127dd59956c91ecffca9d |
| openai/community-plugins | 0b968a719fcda963e243fbc00be4c8ce41698571 |

另外讀了本機已安裝的 anthropics/skills（ca45fc496a3436251f191354091d557da31c15b5）的 skills/skill-creator/SKILL.md：

- :169-186：有裝和沒裝（或新舊版）同時跑。
- :227-234：彙整成平均值、標準差與差值，再由分析者找出「不分有沒有裝都會過」的無效檢查點與不穩定的題目。
- :325-327：盲比。

這套做法可以直接借給第 2 層的 Claude 端。〔已驗證〕

用 `gh api` 讀、沒有 clone 的（子研究）：

| repo | 讀取的 SHA |
|---|---|
| SponsorBlockServer | b691d945b5606ff37577277bb10e6a618bc72c70 |
| youtube-transcript-api | 00387ddd446bf3176ff53a2b6224e84a6ef6327d |
| yt-dlp | 412e7f0a4b0588fe884a02b344ac66a06538475b |

### B.2 本研究的腳本與資料

| 檔案 | 用途 |
|---|---|
| C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\scripts\tally.py | 名冊統計 |
| C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\scripts\gh_health.py | 基本指標：每個 repo 1 次 GraphQL，加 contributors |
| C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\scripts\gh_health2.py | issue 回應與近期星速；只用事件時間戳，不查個別帳號 |
| C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\scripts\power.py | 少量重跑的誤判模擬 |
| C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\research\gh_health.json | 原始資料 |
| C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\research\gh_health2.json | 原始資料 |

### B.3 主要網頁與論文

- **評估方法**：
  - Anthropic〈Demystifying evals for AI agents〉（2026-01-09）：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents 〔已複查〕。重點：從真實失敗挑 20 到 50 題開始；能用程式評分就用程式；多跑幾次；每次從乾淨環境開始；一定要讀 transcript；能力評估通過後轉成回歸測試。
  - Miller 2024：https://arxiv.org/abs/2411.00640
- **LLM 評審**：
  - MT-Bench：https://arxiv.org/abs/2306.05685
  - 位置偏誤：https://arxiv.org/abs/2305.17926
  - 自我偏好：https://arxiv.org/abs/2404.13076
  - JudgeBench：https://arxiv.org/abs/2410.12784
  - Leaderboard Illusion：https://arxiv.org/abs/2504.20879
- **灌星與 GitHub**：
  - StarScout：https://arxiv.org/abs/2412.13459
  - GitHub changelog：https://github.blog/changelog/2026-06-30-upcoming-access-restrictions-to-public-api-endpoints-and-ui-views/
  - CHAOSS：https://chaoss.community/kb/metric-time-to-first-response/、https://chaoss.community/starter-project-health-metrics-model/
  - npm 下載數說明：https://blog.npmjs.org/post/92574016600/numeric-precision-matters-how-npm-download-counts-work.html
- **skill 效用**：
  - SkillsBench：https://arxiv.org/abs/2602.12670
  - SWE-Skills-Bench：https://arxiv.org/abs/2603.15401
  - Signal or Noise：https://arxiv.org/abs/2608.23067
  - Agentic Skills in the Wild：https://arxiv.org/abs/2604.04323
  - ACES：https://arxiv.org/abs/2608.20614
  - Vercel：https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
  - Evaluating AGENTS.md（context 檔一般不會提升成功率，推論成本平均增加 20% 以上）：https://arxiv.org/abs/2602.11988 〔已驗證〕
- **目錄與 registry**：見第 3 節的證據清單。
- **網路心得**：
  - YouTube Data API：https://developers.google.com/youtube/v3/docs/videos
  - YouTube 條款：https://www.youtube.com/static?template=terms
  - Gemini 影片理解：https://aistudio.google.com/docs/video-understanding
  - X API 價格：https://docs.x.com/x-api/getting-started/pricing
  - FTC 背書指南：https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking
  - GRADE：https://pubmed.ncbi.nlm.nih.gov/29452223/
  - Admiralty code：https://en.wikipedia.org/wiki/Admiralty_code
