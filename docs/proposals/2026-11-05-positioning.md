# OmniKit 的定位、競品與下一步（討論稿）

日期：2026-11-05　狀態：討論中，尚未決定

起因：使用者覺得 OmniKit 還很陽春。原本預期訪談之後，會依需求裝上對應的工具、skills，並建立規則；實際上訪談只改規則與情境。

## 0. 需要你決定的事

| # | 決定 | 建議 |
|---|---|---|
| 1 | v2 主要做給誰用 | 先做給同事：裝完就好用。你的治理引擎（名冊、評估、汰換）退到幕後，當推薦工具的依據 |
| 2 | 工具包怎麼做 | 不手工維護工具包。訪談答案對應到槽位，裝的就是槽位的預設工具；名冊改了，工具包跟著變 |
| 3 | 先補內容還是先做安裝 | 先補內容。訪談會用到的槽位裡，有 3 個沒有預設、1 個連槽位都沒有，現在就算做好安裝流程，也沒東西可裝 |
| 4 | 要不要用 BMAD 跑一次 | 不跑全套。先用 RIA 拆解 2 到 3 個競品的安裝精靈；v2 範圍要定案時，再用 BMAD 的 PRD 寫成規格。兩次都記成凍結槽位的實測 |

## 1. 為什麼感覺陽春

根本原因不在安裝流程，而在可以推薦的內容太少：就算訪談想裝工具，名冊裡也幾乎沒有驗證過、能裝的。

- **訪談只改規則**：6 題的答案只會產生 `AGENTS.md` 與 `scenarios.yaml`。會改變安裝內容的只有第 5 題：答「不評估」就不裝 `omnikit-eval`。這一項還在另一個 session 裡開發，尚未 commit。
- **預設工具不會自動安裝**：`engine/scripts/install.ps1:408` 只印出「預設 plugin 不會自動安裝」。
- **名冊裡驗證過的工具很少**：116 張卡片中，預設 11 張、試用 1 張、待評估 104 張。預設的 11 張裡有 7 張是 agent 內建功能（native-*），不需要安裝；真正要裝的只有 bmad、frontend-design、rea、skill-creator 這 4 個，加上試用中的 chrome-devtools-mcp。
- **評估速度追不上**：每週最多跑 2 次深度評估（`data/omnikit.yaml`），104 張全部評完要將近一年。

各槽位目前能裝什麼：

| 槽位 | 預設 | 待評估 |
|---|---|---|
| 前端設計 | frontend-design | 4 |
| 審查與驗收、記憶與交接、程式碼理解與搜尋、權限與通知、輸出精簡、文件與簡報產出 | agent 內建（不用裝） | 1 到 8 |
| 瀏覽器操作與驗證 | agent 內建；chrome-devtools-mcp 試用中 | 9 |
| 指令輸出壓縮、工具發現、行為準則包 | **沒有** | 2 到 3 |
| 逆向工程、skill 製作與評估 | rea、skill-creator | 1、4 |
| 產品研究與方向、規劃與開發流程 | bmad（凍結中，等 RIA） | 33、16 |

## 2. 同類競品

| 類型 | 代表 | 做什麼 | 跟 OmniKit 的關係 |
|---|---|---|---|
| 跨 agent 同步設定 | rulesync | 一份設定產生 20 多種工具的規則、ignore、MCP、commands、subagents、skills、hooks、權限 | 「一份設定、三個 agent」它做得更完整 |
| | rulebook-ai | **工具包（packs）＋ profiles（幾個工具包的組合）**＋記憶庫，支援 Claude Code、Codex、Gemini 等 10 種 | 最接近 OmniKit 原本的工具包構想 |
| | Ruler、skillshare | 規則或 skills 同步到多種 agent | OmniKit 已經拿掉 skillshare |
| 目錄與安裝器 | skills.sh（`npx skills`） | Vercel 的 skill 目錄，支援 40 多種 agent，依安裝數排名，每個 skill 有 Snyk 與 Socket 的安全掃描；安裝數第一名是 find-skills（依需求找 skill） | 規模大好幾個數量級，比的是誰裝得多 |
| | aitmpl（claude-code-templates） | 數百個 agents、commands、MCP、hooks 一行安裝；有 Claude Code 的使用統計 | 只支援 Claude Code |
| | Tessl registry | skill 結構評分、task evals（比較有沒有用這個 skill 的分數）、Snyk 安全分數 | 有評估，但考題由作者出，不是用你的工作情境 |
| 整套方法論＋互動安裝 | ECC 的 configure-ecc | 互動精靈：選核心或專門工具包、選規則組合，裝完檢查 skill 之間的引用。（更正：這是 v1.10.0 的做法；現行的 v2.2.3 已改成只問 2 題、確認 1 次、交給各 agent 原生指令安裝並驗證，見 `docs/v2/research.md`） | 「訪談挑工具」最接近的實作，但只能從它自己的套件裡挑 |
| | Agent OS | profiles 可以繼承；從既有程式碼整理出團隊標準 | profile 繼承可以借用 |
| | BMAD 安裝器、SuperClaude | 安裝時選模組、選 IDE | 同上，只裝自家套件 |
| 平台內建 | Anthropic 的 setup-claude | 依角色裝 plugin、接上工具、試跑一個 skill | 這就是你預期的流程，但只支援 Claude，也只從 Anthropic 的目錄挑 |
| | Claude Code、Codex 本身 | Claude Code 會在任務中主動建議 plugin 或 skill（這個 session 就有這類工具）；Codex 有 plugin marketplace 與 skill-installer | 「依需求推薦安裝」平台正在自己做 |
| 不安裝，用到才載入 | 用 MCP 提供 skills（Microsoft Agent Framework）、skill router | agent 用到時才從 server 拿 skill | 另一種解法；不過 skill 清單本身就有成本，見第 3 節 |

觀察：

- 「一份設定、多個 agent」已經是常見功能，不能當主要賣點。
- 「依需求推薦並安裝」有平台內建，也有超大目錄，正面競爭沒有勝算。
- 我在搜尋範圍內沒找到能同時做到這三件事的工具：用你自己的工作情境比較新工具和現任、記下每個決定的理由、依三個 agent 的實際使用紀錄建議汰除。這是空位。

## 3. OmniKit 的賣點（建議主打）

一句話：**不是幫你裝更多，而是只留證明有用的，而且三個 agent 一致。**

1. **少而精、有根據**：推薦的工具都用你的工作情境實測過，不是看安裝數或星數。skills.sh 的排行榜比的是誰裝得多，OmniKit 反過來。
2. **會自己瘦身**：讀三個 agent 的本機紀錄，找出沒在用的。2026-11-04 在這台實測，依使用紀錄停用 Codex 沒在用的 skills：
   - skill 從 112 個降到 32 個
   - 每次對話開頭的 skill 清單從 49,335 字元降到 15,877 字元
   - 同一個問題的 token 從 27,038 降到 19,695，約少 27%

   就算 agent 用到才讀 skill 全文（progressive disclosure），光是名稱與說明的清單就有成本，所以精選仍然有價值。
3. **安全底線不能放寬，裝之前預覽、隨時能還原**：公司電腦也能用。Trend Micro 擋掉第三方同步工具後，OmniKit 改用自己的腳本接 agent，照樣能裝。
4. **繁體中文、Windows、公司環境優先**：同事上手的門檻低。

## 4. 改進空間（依優先順序）

### 4.1 訪談 → 自動組工具包 → 預覽 → 安裝（你原本的預期）

工具包不另外維護，由「訪談答案 → 槽位 → 槽位的預設工具」組出來：

| 訪談答案 | 對應槽位 | 現在能裝的 |
|---|---|---|
| 寫程式 | 程式碼理解與搜尋、審查與驗收、瀏覽器操作與驗證、規劃與開發流程；有前端專案再加前端設計 | chrome-devtools-mcp、bmad、frontend-design |
| 資料分析 | **沒有對應的槽位** | 無 |
| 文件與簡報 | 文件與簡報產出 | agent 內建 |
| 研究調查 | 產品研究與方向 | bmad（凍結中） |
| 回覆太長 | 輸出精簡、指令輸出壓縮 | agent 內建；指令輸出壓縮沒有預設 |
| 常改太多 | 行為準則包、規劃與開發流程 | 行為準則包沒有預設；bmad |
| 沒驗證就說好了 | 審查與驗收、瀏覽器操作與驗證 | agent 內建、chrome-devtools-mcp |
| 不確定時亂猜 | 行為準則包、產品研究與方向 | 沒有預設；bmad |
| 要評估新工具 | 工具發現、skill 製作與評估 | 工具發現沒有預設；skill-creator、omnikit-eval |

- 預覽列出每個工具、取自卡片的理由，以及會裝到哪些 agent。試用與待評估的工具只列成「可以試用」的選項，預設不勾。
- 內建功能也有用：規則可以寫明什麼時候用，例如「改完先跑 /review」。
- 裝完用第 2 題的痛點實際跑一次對應工具，讓使用者看到效果（原提案的「第一次成功」）。

### 4.2 補內容：先讓訪談會用到的槽位都有預設

- 優先補行為準則包、指令輸出壓縮、工具發現，並新增「資料分析」槽位。
- 外部訊號自動列進第 0 層：skills.sh 的安裝數、Snyk 與 Socket 的掃描結果、Tessl 的分數，用來排評估的先後，不取代實測。
- 只有一個候選、又排不到實測的，可以標成「社群推薦（未實測）」，預覽時寫明。

### 4.3 瘦身自動化

把 2026-11-04 手動做的事變成功能：每週彙整列出沒在用的工具，使用者同意後直接停用。Codex 用 `[[skills.config]] name = ...`（跟帳號同步的 plugin 只能用這個方法），Claude Code 用 plugin disable，不用刪檔。

### 4.4 降低門檻

同事不需要 fork、Actions、Pages。提供「只用不治理」的模式：clone 下來跑 install 就好，看板選配。

### 4.5 中長期

- macOS 與 Linux：scan、agents 已經是 Python，`install.ps1` 改成薄殼即可。
- 更多 agent：交給 AGENTS.md 標準或 rulesync 一類的工具，不自己逐一接。

### 不建議做的

- 跟 skills.sh、aitmpl 比目錄規模。
- 自己做 skill 安全掃描：直接用 Snyk 與 Socket 的結果，加上現有的 skill 掃描。

## 5. 要不要用 BMAD 跑一次

- **現在卡住的是產品定義**：為誰做、成功的樣子、v2 範圍，不是工程問題。BMAD 的前半段（brief、PRD）會逼你回答這些，有幫助；後半段（架構、epic、story）對這個規模太重，也會跟現有提案重複。
- **你的名冊已經安排了這個比較**：產品研究與方向、規劃與開發流程兩個槽位凍結中，等 RIA 跟 BMAD 比（`data/tools/ria.yaml`）。RIA 的定位就是「針對一個有範圍的產品決定，用原始碼證據研究現有方案」，「工具包與安裝精靈怎麼做」正是這種題目。
- **建議流程**：
  1. 先在對話裡定下第 0 節的第 1、2 題，不需要框架。
  2. 用 RIA 拆解 ECC 的 configure-ecc、rulebook-ai 的 packs 與 profiles、Agent OS 的 profile 繼承，看它們怎麼做「選工具包、安裝、驗證」，產出附 `file:line @ sha` 的採用建議。RIA 裝在 `~/.agents/skills`，目前 Codex 與 Antigravity 讀得到。
  3. v2 算大功能，照你「規劃與開發流程」槽位的 V1 情境走重流程：要用 BMAD 就用 bmad-prd 寫 v2 的 PRD，之後獨立審查、實作、驗收。
  4. 兩次都記進凍結槽位的評估紀錄。這樣做 OmniKit 自己的 v2，同時也產出 RIA 對 BMAD 的實測資料。

## 參考來源

- [rulesync](https://github.com/dyoshikawa/rulesync)
- [rulebook-ai](https://github.com/botingw/rulebook-ai)
- [skills.sh 與 npx skills 介紹](https://www.webreactiva.com/blog/skills-sh)、[skills.sh 安全掃描頁面範例](https://skills.sh/socketdev/skills/socket-fix/security/snyk)
- [aitmpl CLI 文件](https://docs.aitmpl.com/cli/overview)
- [ECC configure-ecc](https://skills.cat/skills/affaan-m/everything-claude-code/configure-ecc)
- [Agent OS profiles](https://buildermethods.com/agent-os/profiles)、[Agent OS repo](https://github.com/buildermethods/agent-os)
- [Tessl：評估 skill](https://docs.tessl.io/improving-your-skills/evaluating-skills)、[Tessl task evals](https://tessl.io/blog/introducing-task-evals-measure-whether-your-skills-actually-work/)、[Tessl 安全分數](https://tessl.io/blog/the-tessl-registry-now-has-security-scores-powered-by-snyk/)
- [Microsoft Agent Framework：從 MCP server 取得 skills](https://devblogs.microsoft.com/agent-framework/discover-agent-skills-from-mcp-servers-in-net/)
- [BMAD v6.11.0 release](https://github.com/bmad-code-org/BMAD-METHOD/releases/tag/v6.11.0)、[BMAD v6.7.0 release notes](https://overctrl-web.vercel.app/r/bmad-code-org/BMAD-METHOD/releases/v6.7.0)
- [Codex：停用 skill 的設定](https://learn.chatgpt.com/docs/build-skills.md)
