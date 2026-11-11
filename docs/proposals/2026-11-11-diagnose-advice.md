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

- 即時上網找名冊以外的候選：排在候選池之後。
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

## 已知限制

- 「30 天內有沒有對話紀錄」算的是紀錄檔，背景工具用同一個 agent 跑的對話也算在內。
- 獨立程式、線上服務、命令列工具、裝在專案裡的集合掃不到有沒有裝，這類卡會一直出現在「裝」的候選裡，JSON 裡有標記。
- Codex 自帶的 plugin（marketplace 名稱是 `openai-` 開頭）移除之後會不會再同步回來，還沒驗證；建議裡會註明。
- 槽位的答案目前只有瀏覽器有實測（Claude Code 內建就夠，Codex 建議裝 Chrome DevTools MCP）。其他 11 個槽位只記了各 agent 的內建功能，「用內建的就好」的依據都會註明「還沒實測」。
