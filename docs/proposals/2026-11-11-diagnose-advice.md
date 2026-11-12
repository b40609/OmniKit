# 診斷後給建議：業界做法比較與最小版

日期：2026-11-11。狀態：最小版已實作（`engine/scripts/advise.py`）。

## 結論

- 最小版照這個形狀做：腳本算出事實與三類候選（裝、拿掉、用內建的就好），agent 只能在候選裡挑並寫理由，腳本驗證後寫出建議；使用者同意後，交給各 agent 原生的指令執行。
- 診斷本身只報告、不動手。這是查到的工具裡最一致的做法。
- 「用內建的就好」這一類，查到的工具沒有一個在做；Codex 端的「沒在用」偵測，官方也沒有。這兩塊是 OmniKit 該做的。
- Claude Code 端的「沒在用」與 context 成本，官方已經有（`/skill-doctor`、`/doctor`）。OmniKit 不重做畫面，只把同一份事實拿來跟名冊對照。
- 單一 skill 的停用與移除，兩個 agent 都沒有原生的命令列指令。最小版只給路徑與說明，由 agent 在使用者同意後動手。

## 查證範圍

- 我在這台實跑 `--help` 確認過的（claude 2.1.322、codex-cli 0.167.0）：`claude plugin install|uninstall|disable|list|marketplace add`、`claude mcp remove`、`codex plugin add|remove|list|marketplace add`、`codex mcp remove`、`codex doctor`。
- 其餘是背景調查讀官方文件與原始碼的結果，我沒有逐項實測；下表標「待驗證」的是連文件原文都沒找到的。

## 比較

| 工具 | 事實從哪來 | 建議分哪幾類 | 誰判斷 | 同意與執行 |
|---|---|---|---|---|
| Claude Code `/skill-doctor` | 本機使用紀錄、skill 清單的 context 成本 | 只有「可以關掉」 | 規則 | 只報告，指出去哪裡關 |
| Claude Code `/doctor` | 安裝、設定、擴充項目、用量 | 停用沒在用的 skill、MCP、plugin | LLM（內建 skill） | 先報告，確認後才改 |
| `claude plugin details`、`/context` | plugin 內容、目前的 context | 沒有建議，只有成本數字 | 規則 | 無 |
| `codex doctor` | 安裝、設定、登入、執行環境 | 沒有建議，只有健康報告 | 規則 | 只報告 |
| everything-claude-code 的設定流程 | `claude plugin list --json` 等原生輸出 | 沒有分類，是安裝精靈 | LLM 照流程 | 問 2 題、確認 1 次；先預覽再裝，交給原生指令 |
| everything-claude-code 的 skill 盤點 | 腳本列出 skill；使用紀錄是選配 | 留、改、更新、淘汰、併入 | LLM，每項附證據 | 封存與刪除都要明確確認 |
| vercel-labs/skills | lock 檔與檔案雜湊 | 只有查更新 | 無 | 互動選擇，自己放檔案 |
| claude-code-templates 的健康檢查 | `~/.claude` 與專案設定 | 健康分數加建議 | 腳本 | 只報告 |
| skillshare 的 audit 與 doctor | skill 檔、設定與同步狀態 | 嚴重度；通過、警告、錯誤 | 規則 | audit 擋安裝；doctor 只給下一步指令 |
| skillkit 的 recommend | 專案的技術棧 | 只有「裝」，0 到 100 分 | 腳本加權 | 待驗證 |
| Anthropic 官方 plugin 裡的自動化推薦 skill | 掃專案程式碼 | 只有「裝」，每類 1 到 2 個 | LLM 加對照表 | 唯讀 |
| `brew doctor`、`flutter doctor`、`npm doctor` | 系統狀態 | 警告清單 | 規則 | 只報告 |
| knip、cargo-machete | 靜態分析 | 「沒用到」清單 | 規則 | 預設只報告；自動修要另外加旗標 |
| VS Code 的 `extensions.json` | 人寫的清單 | 推薦、不要推薦 | 人 | 跳提示，使用者自己裝 |

來源：

- Claude Code：<https://code.claude.com/docs/en/skills#find-unused-skills>、<https://code.claude.com/docs/en/commands>、<https://code.claude.com/docs/en/plugins/cli-reference>、<https://code.claude.com/docs/en/plugins/measure>
- Codex：<https://learn.chatgpt.com/docs/developer-commands?surface=cli>、<https://learn.chatgpt.com/docs/build-skills>、<https://learn.chatgpt.com/docs/config-file/config-reference>
- everything-claude-code：<https://github.com/affaan-m/everything-claude-code/blob/main/skills/configure-ecc/SKILL.md>、<https://github.com/affaan-m/everything-claude-code/blob/main/skills/skill-stocktake/SKILL.md>
- skillshare：<https://skillshare.runkids.cc/docs/reference/commands/doctor>
- skillkit：<https://github.com/rohitg00/skillkit/blob/main/packages/core/src/recommend/engine.ts>
- 自動化推薦 skill：<https://github.com/anthropics/claude-plugins-official/blob/main/plugins/claude-code-setup/skills/claude-automation-recommender/SKILL.md>
- knip：<https://knip.dev/features/auto-fix>；cargo-machete：<https://github.com/bnjbvr/cargo-machete>
- VS Code：<https://code.visualstudio.com/docs/configure/extensions/extension-marketplace>

## 從比較裡拿來用的

1. 診斷只報告，附下一步的指令，輸出 JSON。（`brew doctor`、skillshare、`codex doctor`）
2. 動手另外一步，而且先給使用者看。（everything-claude-code、knip）
3. 每個建議附依據；沒有使用紀錄不能當成拿掉的理由。（everything-claude-code 的 skill 盤點）
4. 事實用腳本算，分數與清單不讓 LLM 重算；LLM 只在清單裡挑並寫理由。
5. 自動修會連誤判一起刪（cargo-machete 的說明自己寫明）。拿掉一律先問，先給停用、再給移除。

## 要避開的

- Claude Code 對話裡的 `/plugin install` 只開面板；要真的裝，用命令列的 `claude plugin install`。（背景調查，這台沒實測）
- Codex 裝完 plugin 要開新的對話才會載入。（背景調查，這台沒實測）
- 單一 skill 沒有原生的停用指令：Claude Code 寫 `skillOverrides`，Codex 寫 `config.toml` 的 `[[skills.config]]`。（背景調查讀官方文件，這台沒實測）
- Codex 沒有停用 plugin 的子指令，只有移除。（這台 `codex plugin --help` 確認）

## 最小版

### 腳本給的事實

`uv run engine/scripts/advise.py` 輸出 JSON，只讀本機、不連網、不寫檔：

- 這台有哪些 agent，30 天內有沒有對話紀錄。沒裝或沒紀錄的不出建議。
- 每個 agent 已裝的 skill、plugin、MCP，以及 30 天的使用情況與開頭成本。資料來自 `usage.py` 與 `cost.py`。
- 名冊：槽位在這個 agent 上的答案、名冊上的預設與試用。

### 三類候選的規則

每個 agent 各算各的。

| 類別 | 什麼情況列進候選 | 依據寫什麼 |
|---|---|---|
| 裝 | 槽位的答案是「建議裝某張卡」，這台還沒裝 | 答案的理由與實測紀錄 |
| 裝 | 槽位還沒有答案，名冊上有預設或試用、支援這個 agent、這台還沒裝的卡 | 名冊的理由，註明還沒有分 agent 的實測 |
| 拿掉 | 30 天沒用到（裝不到 30 天的不列） | 天數 |
| 拿掉 | 開頭成本每段對話 1,000 tokens 以上，14 天內與最近 10 段對話都沒用到 | token 數 |
| 拿掉 | 裝著，但名冊上是拒絕或退役 | 名冊的理由 |
| 拿掉 | 同一件事名冊記了內建功能，而這份裝了一週以上從沒用到（不用等 30 天） | 天數、槽位、有沒有實測 |
| 用內建的就好 | 槽位的答案是「內建就夠」 | 答案的理由與實測紀錄 |
| 用內建的就好 | 槽位還沒實測，但名冊記了內建功能 | 註明還沒實測 |

「跟內建功能重疊又沒用到」這一條是實跑之後加的：只看 30 天的話，剛整理過工具的電腦會沒有任何拿掉的候選，而這正是「用內建的就好」最有用的場合。它要兩個事實同時成立才列，單獨一個不列。

同一個槽位可以同時出現在「裝」（名冊有試用中的第三方）與「用內建的就好」（名冊記了內建功能），由 agent 依使用情況挑。

不列的：

- OmniKit 自己的 skill 與 MCP。
- 只有維護者才啟用的模組（同事版）。
- 沒有使用紀錄可以判斷的項目（例如 MCP 沒有使用統計），不會只因為「沒看到用」就列進拿掉。

### 挑選與寫入

- agent 讀 JSON，在候選裡挑、每一項寫一句理由，存成一個 JSON 檔。
- `advise.py --picks <檔>` 驗證：每一項都要在候選裡、都要有理由。通過才寫出建議，存在 `%LOCALAPPDATA%\omnikit\advice\<日期>-<agent>.md`。
- 建議分三節，每一項有理由、依據、同意後要跑的指令；候選裡沒被挑的只列數量。

### 同意後怎麼執行

| 動作 | Claude Code | Codex |
|---|---|---|
| 裝 plugin | `claude plugin marketplace add <repo>`、`claude plugin install <名稱>@<marketplace>` | `codex plugin marketplace add <repo>`、`codex plugin add <名稱>@<marketplace>` |
| 停用 plugin | `claude plugin disable <名稱>` | 沒有子指令 |
| 移除 plugin | `claude plugin uninstall <名稱>` | `codex plugin remove <名稱>` |
| 移除 MCP | `claude mcp remove <名稱>` | `codex mcp remove <名稱>` |
| 移除 skill | 沒有原生指令，刪資料夾 | 沒有原生指令，刪資料夾 |

名冊上沒有 plugin 來源的卡，只給官方網址。移除都是刪除，一項一項問。

### 入口

跟個人週報共用 `omnikit-weekly` 這個 skill：`uv run scripts/report.py advise`。使用者說「OmniKit 給我建議」「我該裝什麼」就走這條；訪談結束時也提示一次。

## 這一版不做

- ~~即時上網找名冊以外的候選~~：已做，見下面「候選池」一節。
- 自動安裝或自動移除：一律等使用者同意。
- ~~依領域只看啟用的模組~~：已做，見下面「選領域」一節。
- 重複安裝的偵測：`usage.py` 的摘要已經有，還沒接進候選。
- Antigravity：只接規則，不出建議。

## 選領域（2026-11-11 加上）

訪談第 1 題從「主要用 agent 做什麼」改成選領域，選的結果存在 profile 的 `domains.yaml`。建議只看基礎模組、選的領域，以及領域帶入的能力模組。

查到的做法分兩條路，沒有一家用「先問角色再鎖住推薦」當唯一入口：

| 做法 | 例子 | 怎麼選 | 事後怎麼改 |
|---|---|---|---|
| 只偵測、不問 | Anthropic 官方的 claude-code-setup、JetBrains 的 plugin 推薦、skillkit | 讀專案的設定檔或開啟的檔案類型，給建議 | 「不要再建議」，或手動重查 |
| 讓使用者明確選 | VS Code 的 Profiles 範本、everything-claude-code 的 `--profile`、BMAD 的安裝精靈 | 單選範本或指定模組 | 重跑同一個指令 |
| 依職能分 plugin，自己挑 | Anthropic 的 knowledge-work-plugins（11 個職能） | 沒有題目，照名稱裝 | 停用或移除 |

來源：<https://raw.githubusercontent.com/anthropics/claude-plugins-official/main/plugins/claude-code-setup/skills/claude-automation-recommender/SKILL.md>、<https://plugins.jetbrains.com/docs/marketplace/intellij-plugin-recommendations.html>、<https://code.visualstudio.com/docs/configure/profiles>、<https://raw.githubusercontent.com/anthropics/knowledge-work-plugins/main/README.md>、<https://www.nngroup.com/articles/the-power-of-defaults/>。以上是背景調查讀官方文件的結果，我沒有逐項實測。

採用的設計是兩條路並用：

- 掃描先偵測，把對得上的領域預先勾起來，並寫出依據（例如「專案裡有 package.json」）。只看檔名，不讀內容。
- 使用者複選確認，可以改。選超過 3 個時提醒建議會變多。
- 上次選過的照上次的，不再用檔名猜。
- 事後重新訪談，或直接改 `domains.yaml`；刪掉這個檔就是全部模組都看。
- 手寫的 profile 沒有這個檔，行為跟以前一樣。

連帶的改變：新版訪談不再問「主要用 agent 做什麼」，所以新產生的規則少了那一題對應的通用工作習慣（例如「改程式前先讀相關的程式碼」）。舊的答案檔照樣讀得懂。

## 規則檔瘦身（2026-11-11 加上）

建議多一節：每段對話實際載入的規則檔有多大，以及哪些規則可以拿掉。

### 依據與它的限制

| 來源 | 測了什麼 | 結論 | 限制 |
|---|---|---|---|
| arXiv:2602.11988（ETH Zurich 等） | Claude Code、Codex、Qwen Code；SWE-bench Lite 300 題加自建 138 題 | LLM 生成的規則檔不提升成功率，成本多約 20%；開發者手寫的成功率 +2.4%（不顯著），成本最多 +19%。repo 總覽沒有幫助 | 只測 Python、只量解題率 |
| arXiv:2607.27250 | Claude Code、Codex；3 個 repo、288 次執行 | 有沒有規則檔，正確率沒有差異 | 作者自己說檢定力不足 |
| arXiv:2601.20404 | Codex；10 個 repo、124 個 PR | 有 AGENTS.md 時執行時間中位數少 28.64% | 沒有完整量正確性，只是相關 |
| Anthropic 與 OpenAI 的提示詞指南 | 不是實驗 | 全大寫的強調、「be thorough」這類口號、為舊模型寫的修正，在新模型上會過度套用 | 是指引，不是量測 |

來源：<https://arxiv.org/abs/2602.11988>、<https://arxiv.org/abs/2607.27250>、<https://arxiv.org/abs/2601.20404>、<https://code.claude.com/docs/en/best-practices>、<https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>、<https://developers.openai.com/api/docs/guides/prompt-guidance?model=gpt-5.5>。以上是背景調查讀摘要與官方文件的結果，我沒有逐篇讀全文。

最重要的限制：這些研究測的都是 repo 裡的規則檔對解題率的影響，**沒有一篇直接測「刪掉使用者自己寫的行為規則」**。所以每一條都只能當候選，要使用者同意，而且建議裡寫明沒有逐條實測。

### 現成的工具

| 工具 | 檢查什麼 | 誰判斷 | 會不會自己改 |
|---|---|---|---|
| Claude Code `/doctor` | 本地檔與已 commit 檔重複、codebase 推得出的內容、可以搬到 skill 的常駐內容；`prompt-audit` 另外抓為舊模型寫的指令、不存在的檔案、互相矛盾 | LLM | 先報告，確認後才改 |
| Claude Code 啟動時與 `/context` | 單檔過長的警告、已載入的規則檔與用量 | 規則 | 不改 |
| 官方 plugin claude-md-management | 用 100 分量表評 CLAUDE.md，偏向補內容 | LLM | 核准後才改 |
| agnix | 超過 200 行、強調語過多、跟 README 重複、目錄樹、import 失效、籠統的通用指令 | 規則 | 有自動修，分安全與不安全 |
| AgentLint、ctxlint | 強調詞密度、長度、失效的路徑、token 成本、跨檔重複 | 規則為主 | 只修路徑 |
| Codex | 官方文件沒有記載檢查或瘦身的功能（待驗證，沒有查原始碼） | | |

來源：<https://code.claude.com/docs/en/memory>、<https://code.claude.com/docs/en/commands>、<https://github.com/anthropics/claude-plugins-official/tree/main/plugins/claude-md-management>、<https://agent-sh.github.io/agnix/docs/rules>、<https://github.com/0xmariowu/AgentLint>、<https://github.com/YawLabs/ctxlint>、<https://learn.chatgpt.com/docs/agent-configuration/agents-md>。`/doctor prompt-audit` 是背景調查讀官方文件的結果；這台只用 `claude doctor --help` 確認「完整的檢查在對話裡跑 `/doctor`」，沒有實跑。

### OmniKit 做的與不做的

Claude Code 那一邊的內容判斷官方已經有，不重做。OmniKit 補四件事：

1. **成本照實際載入的量**：Claude Code 的對話紀錄會記下每段對話載入的每個規則檔與內容，Codex 的紀錄開頭有整段 AGENTS.md。算出每段對話多少 token、佔對話開頭多少、一週合計。
2. **Codex 那一邊**：官方沒有對應的檢查。
3. **安全底線受保護**：底線的每一條都不會變成候選，使用者在自己的檔裡重寫同一句也一樣。
4. **知道來源檔在哪**：Codex 讀的是 OmniKit 接好的副本，要回 profile 的來源檔改，改完重新接上。

分類照調查的結論修正過，不是「事實留、修正刪」兩分：

| 這一條是什麼 | 怎麼處理 |
|---|---|
| 使用者的偏好、紅線、專案裡讀不到的事實、被糾正過才加的規則 | 留著，不挑 |
| 通用的口號、agent 現在預設就會做的行為修正、重複的、訪談帶進來的通用規則、專案裡讀得到的內容 | 候選拿掉 |
| 不能有例外的規則 | 不拿掉；口頭建議改用 hook 或權限規則 |

腳本只標得出來的訊號：訪談範本產生的、重複、通用的口號、語氣很重、一條很長，以及整個檔超過 200 行或 Codex 的 32 KiB。一條規則是不是「現在預設就會做」，腳本判斷不了，由 agent 挑選並寫理由，腳本驗證後才寫進建議。

這一版不做：自動改檔、把規則搬到 hook、檢查失效的路徑與目錄樹（agnix 與 ctxlint 已經有）、專案層的規則檔逐一掃描（只看對話實際載入的那幾個）。

## 候選池（2026-11-11 加上）

名冊還沒有答案、也沒有可以裝的卡的槽位，原本什麼都不列。這一步讓腳本去外面的目錄找候選，agent 也可以自己上網找，找到的交給腳本檢查。程式在 `engine/scripts/pool.py`。

### 三個來源查到的實情

都是 2026-11-11 在這台實際抓到的。

| 來源 | 實際內容 | 怎麼接 |
|---|---|---|
| Anthropic 官方 plugin 目錄（`anthropics/claude-plugins-official`） | 一個 `marketplace.json`，317 筆，每筆有說明、分類、來源；repo 是 Apache-2.0。分類以開發（124）、生產力（70）、資料庫（39）為主 | 整個檔抓下來存在本機，只給 Claude Code |
| OpenAI 官方 plugin 目錄（`openai/plugins`） | 兩個清單檔（65 與 51 筆，合併去重）只有名稱與分類，說明在每個 plugin 的 `plugin.json`；repo 沒有標授權。Codex 會把整份同步到 `~/.codex/.tmp/plugins`（這台有，62 個） | 這台有 Codex 就讀本機那份，不連網；沒有才上網抓。只給 Codex |
| OpenAI 的 skill 目錄（`openai/skills`） | README 第一段寫明已經停止維護，請改用 `openai/plugins` | 不接（跟 11-10 檢視報告第 8.4 節的建議不同） |
| 官方 MCP Registry | 三萬筆以上。官方文件寫的定位是給下游的整理者定期抓，還在 preview、資料可能重置；搜尋只比對名稱的子字串（實測：查 `browser` 回來 100 筆名稱都含 browser，沒有一筆是只有說明含），不到 3 個字元回 422。沒有審核，也沒有品質訊號 | 不整包匯入。用槽位的關鍵字查，只留狀態正常、有 GitHub repo 的，再用 GitHub 現況篩 |

同事的電腦上有沒有 `~/.codex/.tmp/plugins` 這份，待驗證；沒有的話會走上網抓那條路。

### 做法

- **只找還沒有答案的槽位**：這個 agent 的答案是內建就夠、建議裝某張卡，或名冊記了內建功能的，都不找；名冊已經有預設或試用的卡也不找。
- **比對只看字面**：槽位的關鍵字一組一組比，一組裡的字要在名稱或說明的同一句裡都出現才算。雜訊很多，所以每個來源最多列 3 個，由 agent 從嚴挑。
- **檢查沿用第 0 層的門檻**：封存的不列；沒有授權、一年沒更新、建立不到 14 天、星數不到 50 只標出來；查不到寫「未知」。Registry 的候選查不到 GitHub 現況就不列，星數不到 50 的排在後面。
- **名冊記了別裝的不列**，並附上名冊記的理由；名冊已經有卡的照名冊的評估走。
- **agent 上網找到的走同一條路**：`pool.py add` 檢查過才會變成候選，沒檢查過的挑不了。留 30 天。
- **只送槽位的關鍵字**：Registry 一組關鍵字只送一個字；不送專案名稱。`advise.py` 自己不連網，只讀 `pool.py` 存下來的檔。
- **建議裡照實寫**：名冊外、沒有實測過、依據只有外部訊號；安裝指令是照目錄登記的資料組的，沒有實際執行過。

### 這台跑出來的

28 個槽位要找，21 個有候選，共 73 個：Registry 52 個、Anthropic 目錄 12 個、OpenAI 目錄 9 個。7 個槽位一個都沒有：工程圖與材料表、結構初步驗算、訊號與量測數據、圖表與技術報告、回覆審查意見、字幕與逐字稿、轉檔與輸出。跟預期一致：官方目錄以開發為主，這些領域要靠 agent 上網找。

### 沒做的

- 沒有跑 `batch0.py` 的完整健康指標，也沒有做安全掃描（`layer0.py` 的掃描器）。
- 使用者採用之後寫回成名冊的候選卡：還沒做，現在只記在本機。
- skills.sh、aitmpl 這些有安裝數的來源：還沒接。
- Antigravity 不出建議。

## 私有模組（2026-11-12 加上）

名冊的領域是公版，不會有每個人的工作。這一步讓使用者在 repo 外加自己的模組，並讓 agent 代寫。設計照 `2026-11-10-slot-architecture.md` 的 3.4 節。程式在 `engine/scripts/validate.py`（讀取）與 `engine/scripts/module_new.py`（代寫的寫入）。

### 別人怎麼做

| 做法 | 例子 | 重點 | 這裡怎麼用 |
|---|---|---|---|
| 分層設定，個人那層不進版控 | Claude Code 的設定分 user、project、local；`.claude/settings.local.json` 建立時會設成 git 忽略；陣列型的設定跨層合併 | 個人的東西跟共用的分開放，載入時合在一起 | 私有模組放 `%LOCALAPPDATA%\omnikit\modules\`，跟 profile 同一個地方；載入時接在公開名冊後面 |
| 公版是起點，由 agent 幫忙改成自己的 | Anthropic 的 `knowledge-work-plugins`：README 寫明公版外掛是通用的起點，另外附一個外掛（`cowork-plugin-management`）替你的單位建立新外掛或改現有的 | 改的是公版的副本，之後公版更新要自己合 | 不改公版的檔，只在旁邊加；公版更新不用合。撞 id 時私有的讓，並講原因 |
| 目錄從登記的位置載入額外的檔 | Backstage 的 catalog：在設定裡登記範本檔的位置才會出現 | 要多一步登記 | 不用登記：固定一個資料夾，放進去就生效 |

Claude Code 的設定行為出自官方文件，`knowledge-work-plugins` 出自它的 README（2026-11-12 讀的）；Backstage 那一列出自官方文件的搜尋摘要，沒有讀原文。

### 做法

- **只加不改**：私有模組不能蓋掉公開的模組、槽位或情境；id 重複的那個私有模組不載入。公開名冊之後加了同一個 id，也是私有的讓。
- **壞的不拖累別人**：一個私有模組有問題，只有它不載入，原因列出來；名冊驗證照樣通過，pre-commit 與 CI 不會因為這台的個人檔案擋下來。
- **預設不讀**：`validate.check` 要給 `private=True` 才讀。開的只有給建議（`advise.py`）、找候選（`pool.py`）、掃描（`scan.py`）與驗證的摘要；看板（`build.py`）與評估 skill 會把結果寫進 repo，所以不開，私有的內容不會跑進公開的檔。
- **一律啟用**：不用列在 profile 的領域裡。刪掉檔案就停用。
- **只能是領域或能力**；答案不能指向工具卡（卡片在公開名冊，不會列私有的槽位）。
- **agent 代寫走腳本**：agent 出草稿（JSON），腳本補預設值、替情境編號、驗證、預覽，使用者同意才寫入；覆蓋要 `--force`，舊檔備份成 `.bak`。草稿比手寫多三個要求：最多 6 個槽位、每個槽位都要有關鍵字、關鍵字不能有訪談時寫的專案名稱。
- **入口**：`omnikit-setup` 第 5 節，「幫我加一個領域」。

### 實跑

在暫存的狀態資料夾跑完整一遍（沒有動這台真的設定）：草擬「活動與研討會籌辦」兩個槽位 → 預覽 → 寫入 → 驗證列出 1 個私有模組 → `pool find` 替兩個槽位找候選（排議程那格找到官方目錄的行事曆外掛，整理名單那格沒有）→ `advise` 的備註與待找清單都有這兩格。

實跑時發現並修掉一個候選池的問題：`pool find --slot` 會把其他槽位上次的結果蓋掉。

### 沒做的

- 評估 skill（`omnikit-eval`）看不到私有的槽位：不能拿私有的情境跑實測，答案只能手動改檔。
- profile 的情境檔不能替私有的槽位換情境；直接改模組檔。
- 沒有停用或刪除的指令：刪檔由使用者自己做。
- 關鍵字只擋得住訪談時寫的專案名稱；單位或客戶的名稱腳本認不出來，靠 skill 的說明與預覽時使用者自己看。
- 「提進公版」沒有工具，手動把檔放進 `data/modules/`。

## 已知限制

- 名冊外的候選是字面比對出來的，會有跟槽位無關的（例如關鍵字是 `speech to text`，比中的是文字轉語音）。腳本不判斷相關性，靠 agent 讀說明。
- OpenAI 目錄的 plugin 本體都在 `openai/plugins` 裡，沒有各自的 repo，所以沒有 GitHub 現況可以查。
- 沒有登入 GitHub（`gh auth login` 或 `GITHUB_TOKEN`）時每小時只能查 60 次，超過的候選會標「查不到」；Registry 的候選查不到就不列。

- 「30 天內有沒有對話紀錄」算的是紀錄檔，背景工具用同一個 agent 跑的對話也算在內。
- 獨立程式、線上服務、命令列工具、裝在專案裡的集合掃不到有沒有裝，這類卡會一直出現在「裝」的候選裡，JSON 裡有標記。
- Codex 自帶的 plugin（marketplace 名稱是 `openai-` 開頭）移除之後會不會再同步回來，還沒驗證；建議裡會註明。
- 槽位的答案目前只有瀏覽器有實測（Claude Code 內建就夠，Codex 建議裝 Chrome DevTools MCP）。其他 11 個槽位只記了各 agent 的內建功能，「用內建的就好」的依據都會註明「還沒實測」。
