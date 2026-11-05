# OmniKit v2 研究：掃描與訪談後依需求推薦安裝工具，以及工作中主動建議

日期：2026-11-05
範圍：ECC configure-ecc、Anthropic setup-claude、Vercel find-skills 與 `npx skills`、Codex skill-installer 與 plugin 推薦、Tessl、aitmpl、BMAD 安裝器、SuperClaude 安裝器、Claude Code 官方的 plugin 探索與推薦、Claude Code `/init`、三個 agent 的 hooks，以及其他 2026 年的做法與 VS Code、JetBrains 的主動推薦先例。
OmniKit repo 全程只讀，沒有改任何檔案。

---

## 0. 先看這裡

### 0.1 需要你決定的事

| # | 決定 | 建議 | 理由 |
|---|---|---|---|
| 1 | 推薦排序的主鍵 | 名冊實測（在你的情境勝出）排第一；安裝數、星數、Snyk、Tessl 分數只用在同分時排先後；沒實測的預設不勾 | 被研究的各家沒有一家用使用者自己的工作情境決定推薦（§2、§6）。這是 OmniKit 的空位 |
| 2 | 專案掃描對應到哪一層 | 對應到「槽位」，不對應到個別函式庫 | Tessl 在 CLI 0.76.0 撤掉了依相依套件自動配對（§2.6）。OmniKit 名冊收的是工作流程工具，不是函式庫文件 |
| 3 | 工作中主動建議走哪個管道 | 由 hook 在本機比對訊號，印 `systemMessage` 給人看；不讓模型在對話中自己搜目錄 | 不花模型 token、不佔 context，三個 agent 共用一份頻率規則（§5.4） |
| 4 | 要不要用 Claude Code 原生的 relevance 建議 | 先不用，列為選配 | 終端機要在 managed settings 列白名單才會生效。Windows 的 HKCU 使用者可寫，但寫進去就變成 managed 層級，公司有派政策時也會被忽略（§5.1） |
| 5 | Antigravity 要不要在工作中主動建議 | 第一階段只做週報與「使用者明確詢問」；hook 提示要等實測確認使用者看得到再開 | 官方 hooks 只能把步驟注入給模型，沒有給使用者看的欄位（§5.6） |
| 6 | 要不要搜外部目錄（skills.sh） | 同事預設關、只搜名冊；需要時才打開 | `npx skills find` 會把查詢字串送到 skills.sh，遙測也帶著查詢字串（§2.3） |

### 0.2 重點發現

1. **最接近「訪談後挑工具包」的 ECC，v2 幾乎推翻了 v1。** 題目從 6 步以上降到 2 題；安裝從「LLM 用 `cp -r` 複製」改成交給各 agent 原生的 plugin 指令；驗證從「grep 檔案引用」改成「腳本回傳 JSON，再用 agent 自己的清單獨立確認」。定位稿（`docs/proposals/2026-11-05-positioning.md:46`）描述的是 v1.10.0 的流程，現行版已經不是那樣。
2. **沒有一家用使用者的情境實測來推薦。** setup-claude 看角色與組織目錄；find-skills 看安裝數與星數；aitmpl 看下載數；ECC、BMAD、SuperClaude 只推自家套件；Tessl 用作者出的 eval。Claude Code 的 `claude plugin eval` 已經能算「有 plugin」與「沒 plugin」的分數差 Δ，但只給作者用，也只支援 Claude Code。
3. **依相依套件自動配對已經有反例。** Tessl CLI 0.76.0 移除 `--project-dependencies`。aitmpl 的偵測有運算順序 bug，判斷 Django 與 Flask 的分支永遠不會成立。
4. **平台的主動建議都在收緊。**
   - Codex 的 `request_plugin_install` 只在使用者明確要求某個 plugin、而且工具搜尋找不到時才能用，並明文禁止推薦「看起來有用」的工具。
   - Claude Code 的情境建議每個 plugin 每 3 個 session 最多提 1 次；CLI 提示每個 plugin 一生只問 1 次；LSP 建議對話框被忽略 5 次就不再出現。
5. **Claude Code 的 relevance 訊號格式值得直接沿用。** 訊號有 `cwd`、`cli`、`hosts`、`filesRead`、`manifestDeps` 五種，在本機比對、不連網。缺點是終端機要管理員列白名單才生效。
6. **三個 agent 都有 hook 可以用。**
   - Claude Code 與 Codex：Stop、SessionStart 都能印給人看的 `systemMessage`。
   - Antigravity：有 SessionStart、PreInvocation、Stop 等事件，但只能注入給模型。
   - OmniKit 已經有在 Claude Code 與 Codex 上跑的 Stop hook（`engine/scripts/session_nudge.py`），工作中建議可以直接建在它上面。
7. **Codex 的 hook 信任綁的是宣告的雜湊**（事件、matcher、指令字串），不是腳本內容。只要指令字串不變，改腳本內容就不用重新信任。
8. **「只留有用的」平台也開始做了。** Claude Code `/plugin` 會把 14 天內沒用、而且 10 個 session 都沒用的 plugin 列到「Not used recently」，`/doctor` 也會建議停用沒用的。OmniKit 的差異要放在兩處：跨三個 agent，以及「有實測證據才建議替換」。

### 0.3 建議的整體做法

照 ECC v2 的骨架做：腳本負責決定、agent 負責轉述；只確認一次；交給各 agent 原生指令安裝；用 agent 自己的清單獨立驗證。各步驟另外借用其他家的做法：

- 預覽格式：借 setup-claude 的「已裝的另外列、組織或團隊的優先」，以及 aitmpl 的「每項會寫到哪」。
- 第一次成功：借 Codex 目錄的 `default_prompts`。
- 頻率控制：借 Claude Code 與 VS Code 的規則。
- 推薦依據：換成 OmniKit 名冊的實測結果。
- 工作中建議：用 hook 在本機比對，只有使用者明確詢問時才讓模型參與。

---

## 1. 範圍、方法與快照

### 1.1 標記

- [已驗證]：看過原始碼或本機檔案。
- [僅文件]：只有官方文件。
- [推論]：我的推斷。
- [子研究]：由 3 個 fork 讀碼回報，證據行號照它們的回報。主線抽查 3 項都相符：Tessl 0.76.0 移除相依掃描（`tessl-docs/llms-full.txt:3303`）、VS Code 的 `TooMany` 規則（N:222-227）、7 天提示間隔（T:255-264）。其餘沒有逐一複核。
- 下載的 repo 與套件都只讀，沒有執行、沒有安裝。

### 1.2 快照

| 對象 | 來源 | 版本／SHA | 備註 |
|---|---|---|---|
| ECC | github.com/affaan-m/ECC（原 everything-claude-code，297,051 星） | v2.2.3 `b38be6a7f6350964d59328b52f0624e1d1d552d1` | 另抓 v1.10.0 `846ffb75da9a5f4e677d927af1ad4a1951652267` 與 v2.0.0 `8ad4151095e453301ce0e50374103bcd8f50ded2` 的 configure-ecc SKILL.md |
| setup-claude | 本機 Claude 桌面版 skills-plugin | SKILL.md 97 行，sha256 開頭 `9f60020e05da` | manifest 標 `creatorType: anthropic`；另有同描述的 `setup-cowork` |
| Vercel skills | github.com/vercel-labs/skills | 1.7.6 `9197d919034d19010ae303cf96bf19ad087dd4be` | 含 `skills/find-skills` |
| Codex skill-installer | 本機 `~/.codex/skills/.system/skill-installer` | system skills marker `10436c17968d409d` | |
| Codex | github.com/openai/codex（稀疏 clone） | `ba057e43758cb19beead2af9df19d10756cc4100` | plugin、tool_suggest、hooks、config schema |
| Codex 本機快取 | `~/.codex/cache/remote_plugin_catalog/d99c5a7003b2bab2.json` | 2026-11-04T15:44:17Z 抓取，10,631 個 plugin | 只讀欄位與統計 |
| openai/skills | github.com/openai/skills | `49f948faa9258a0c61caceaf225e179651397431` | skill-installer 的清單來源 |
| Claude Code | github.com/anthropics/claude-code | `26382c08758260c9f5deb2019d8fe851f89fa9ae`（CHANGELOG 最新 2.1.318） | 官方文件快照 2026-11-04 17:35 UTC，存在 `recommend\cc-docs\` |
| Antigravity | antigravity.google/docs/hooks；本機 `resources\bin\language_server.exe` | 2026-10-29，182,867,968 bytes | 只比對字串，沒有執行 hook |
| BMAD［子研究］ | bmad-code-org/BMAD-METHOD | HEAD（v7 preview）`022be9314e4facd16826104a9f8033e1c5ed4fdc`；v6.12.4 `bab9082c3e884e0d72c759bcd1a6d90bcc01be84` | |
| SuperClaude［子研究］ | SuperClaude-Org/SuperClaude_Framework | v4.3.0 `fe68862c8ed9e2afb8120c2d9e27d0c3a7ce73a2`；v4.0.9 `b9985e0fe6c8d720ab50acaf5d23547148aa611c`；v4.1.9 `43ca81d1693b1ecfc6648531798e29224cb305c3` | |
| aitmpl［子研究］ | davila7/claude-code-templates | `cc3f5356409d09bd7596496eb9b265b2225e195f`（npm 1.32.1） | Windows 要設 `core.longpaths=true` |
| Tessl［子研究］ | tesslio/cli 只有 README；npm `@tessl/cli@0.119.0` 只有啟動器 | 文件快照 llms-full.txt（2026-11-04 17:22 UTC） | CLI 不開源 |
| VS Code［子研究］ | microsoft/vscode（稀疏 clone） | `becf53f49cda147c27b89fd98a3cd6c6ab1cfa3a` | |
| IntelliJ［子研究］ | JetBrains/intellij-community（稀疏 clone） | `f34642e3957c4fc09ccbf8f9cb29c59d984923fd` | |
| Cline［子研究］ | cline/cline（稀疏 clone） | `7a7878cb52fc33967d8b464b3e3d899beac42d4d` | |
| callstack agent-skills［子研究］ | github.com/callstackincubator/agent-skills | `59e9d17446a248b21d86f078fcd0bd2d36db1ca4` | rn-skills PR 未合併，不納入 |
| OmniKit | 本機 | HEAD `4a4fc3877ee6389a3c9da26fc9b6422a8c0501ec`，加上未追蹤的定位稿 | 只讀 |

---

## 2. 各家拆解

### 2.1 ECC configure-ecc（affaan-m/ECC）

現行 v2.2.3 已經把 configure-ecc 定位成「安裝後的重新設定」，原文為 post-install reconfiguration path（`skills/configure-ecc/SKILL.md:29-30 @ b38be6a`）。定位稿描述的是 v1.10.0。

| 面向 | v2.2.3（現行）[已驗證] | v1.10.0（定位稿描述的版本）[已驗證] |
|---|---|---|
| 觸發 | 安裝、更新、重設、修復、換 hook 設定或範圍（`SKILL.md:3`）。終端機入口是 `ecc setup` 與 `npx ecc-universal setup`（`:15-17`）；多 agent 用 `ecc install --guided`（`scripts/install-guided.js:26-56`） | 「configure ecc」「install ecc」等說法（`v1.10.0 SKILL.md:11-16`） |
| 掃描 | 只盤點已裝狀態：`claude plugin list --json` 與 `claude plugin marketplace list --json`（`:36-42`）；Codex 用 `codex plugin marketplace list --json` 與 `codex plugin list --available --json`（`:142-143`）。既有的範圍與 hook 設定拿來當預設（`scripts/setup.js:224-261`）。不看專案，也不看硬體 | 不掃描，先 clone 到 `/tmp`（`:26-35`） |
| 題目 | Claude Code 只問 2 題：範圍 `user/project/local`、hook 模式 `off/minimal/standard/strict`（`:50-69`）。guided 版會先問裝到哪些 agent，再問範圍（建議 user）、hook（建議 standard）、Kimi 的內容 profile（建議 core）（`install-guided.js:136-182`） | 6 步以上：安裝層級、核心或專門、7 類多選、逐項確認、規則組、要不要最佳化（`:41-297`） |
| 推薦邏輯 | 規則式：預設值寫死（`install-guided.js:167-173`）。`consult.js` 用關鍵字比對元件與 profile，第一個詞完全命中 5 分、其他詞 4 分、模糊命中 1 分；回傳前 5 個元件、前 3 個 profile，附「matched "x"」理由與安裝指令（`scripts/consult.js:11, 257-287, 319-394`）。profile 有 minimal、core、developer、security、research、full 等（`manifests/install-profiles.json`）。不用 LLM，也不看熱門度 | 「Core only (recommended)」為預設（`:69-79`） |
| 預覽與確認 | 先跑 `--dry-run --json`；只出「一份」確認摘要，內容是動作、範圍、hook、marketplace、遷移，只問一題是或否（`:74-93`）。guided 版印 Harness／Channel／Destination 表，hook 不是 off 時列出 6 類能力（`install-guided.js:207-224`；`scripts/lib/install/hook-consent.js:12-37`），確認預設為否（`:226-230`） | 每類列清單逐項確認（`:100-102`） |
| 安裝方式 | 交給各 agent 原生的 plugin 生命週期：`setup.js --mode claude-plugin --scope --hooks --yes --json`（`:96-111`）；Codex 用 `codex plugin marketplace add` 與 `codex plugin add ecc@ecc --json`（`:149-162`）。明文禁止 clone 到暫存資料夾或手動複製元件（`:12-13`）。非互動與 JSON 模式一定要加 `--yes`（`install-guided.js:202-204`）。agent 的 shell 通常不是 TTY，不能跑互動版（`:93-94`） | 由 LLM `cp -r` 複製（`:195-200, 219-228`），最後 `rm -rf /tmp/...`（`:321-325`） |
| 驗證與第一次成功 | 退出碼 0，且回傳的 scope 與 hooks 等於所選；再獨立跑 `claude plugin list --json`，必須剛好有一個啟用的 `ecc@ecc`（`:115-123`）。版本字串符合樣式才顯示歡迎畫面，只顯示一次，失敗時不顯示（`:127-139`）。提醒使用者 `/reload-plugins` 或重開（`:137-138`）。Codex 只用 JSON 回傳的 `installedPath`，不從 JSON 值拼 shell 指令（`:164-177`）。失敗時印出重跑指令（`install-guided.js:319-324`） | 檢查檔案存在、路徑引用與 skill 之間的引用，逐項回報檔案、行號、問題與修法（`:235-283`） |
| 更新與通知 | 重跑 setup 就更新（`setup.js:56`）。`auto-update.js` 拉最新版，再照 install-state 重裝（`scripts/auto-update.js` 開頭說明）。`doctor` 檢查 install-state 的漂移、缺檔與版本（`scripts/lib/install-lifecycle.js:1211-1243`）。沒找到主動通知 [推論：grep 無結果] | 無 |
| 隱私與安全 | hook 能力揭露包含「Send transcript-derived conversation text to an external LLM」（`hook-consent.js:21-24`）。參數長度有上限，輸出到終端的文字會先消毒（`install-guided.js:84-86, 232-234`） | — |

**教訓**：v1 到 v2 的演進就是「LLM 手動做」改成「腳本做、LLM 轉述」。OmniKit v2 應該直接從 v2 的結論出發。

### 2.2 Anthropic setup-claude（本機原始檔）[已驗證]

路徑：`C:\Users\user\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\local-agent-mode-sessions\skills-plugin\486f4ee9-76f7-4c07-b90d-afdbe6ce5648\8b609bb3-7391-4bb3-a985-068e315ff916\skills\setup-claude\SKILL.md`。另一個舊 session 資料夾裡也有一份，雜湊相同。

| 面向 | 做法 | 證據 |
|---|---|---|
| 觸發 | 使用者叫 guided setup | `SKILL.md:2-3` |
| 掃描 | 不看硬體或專案。系統提示裡有帳號 profile 的角色，就跳過角色題。一定先呼叫 list-plugins 看已裝了什麼；連接器也先查哪些已經連上 | `:29, :37, :51` |
| 題目 | 角色 1 題，用 role-picker 的選項面板，不用文字問、也不自己列角色。之後是 3 個是或否的關卡：要不要看連接器、要不要試 skill、要不要建寫作風格（只有該 skill 存在才問） | `:31, :43, :53, :57, :65-79` |
| 推薦邏輯 | 用角色搜 plugin marketplace，排除已裝的。**組織自己的 plugin 一律排最前面**，組織目錄裡沒有接近的才拿通用的補。取 2 到 3 個，搜不到就退回 productivity。連接器取「所有在用的 plugin 宣告的 `mcpServerNames`」，去重後全部列出 | `:39, :41, :49-51` |
| 預覽與確認 | 用卡片元件顯示，使用者自己按 Add。文字只能放在元件後面、回應實際結果，不能先假設結果 | `:43, :96` |
| 安裝方式 | 平台 UI 安裝；連接器點一下就連，OAuth 由平台處理 | `:43, :53` |
| 驗證與第一次成功 | 沒有技術驗證。第一次成功靠「Try a skill」卡片當場跑一個 skill，跑完說「Nice — that's how skills work.」 | `:55-61` |
| 更新與通知 | 無 | — |
| 隱私與安全 | 寫作風格只讀使用者自己寫的內容，存檔前要使用者審 | `:75-77` |
| 流程規則 | 先建 TODO 清單讓使用者看到進度；一次一步；可以跳過；每則訊息 2 到 3 句加元件 | `:10-23, :91-97` |

**可借**：已知的就不問、已裝的分開列、組織優先、2 到 3 個就好、當場試跑。**缺點**：只限 Claude、只看角色、沒有證據、沒有驗證與更新。

### 2.3 Vercel find-skills 與 `npx skills`（vercel-labs/skills 1.7.6 @ 9197d91）[已驗證]

| 面向 | 做法 | 證據 |
|---|---|---|
| 觸發 | find-skills 由 skill 描述觸發：使用者問「how do I do X」、「find a skill for X」，或想擴充能力時 | `skills/find-skills/SKILL.md:3, 12-19` |
| 掃描 | `add` 會偵測本機裝了哪些 agent（檢查各自的設定資料夾，例如 Antigravity 是 `~/.gemini/antigravity`），並記住上次選了哪些 agent | `src/agents.ts:104-121, 834-842`；`src/add.ts:583-605` |
| 掃描（相依套件） | `experimental_sync` 掃 node_modules，裝「直接相依的套件自帶的 skills」與 package.json 的 `skills` 欄位（規格來自 antfu/skills-npm） | `src/sync.ts:237-239, 660`；`src/skills-field.ts` 開頭 |
| 題目 | find 沒有題目。add 會問：裝到哪些 agent（`.agents/skills` 通用區鎖定顯示）、範圍（Project 或 Global）、方法（Symlink（Recommended）或 Copy，只有多個目標資料夾時才問）、最後確認 | `add.ts:598-603, 1057-1071, 1093-1115, 1169` |
| 推薦邏輯 | `GET https://skills.sh/api/search?q=…`，排序在伺服器端，CLI 不再重排。find-skills 要求先看排行榜（依總安裝數），再看品質：1K 以上安裝優先、100 以下要小心、官方來源優先、repo 不到 100 星要懷疑 | `src/find.ts:17, 86-113`；`SKILL.md:43-49, 65-71` |
| 預覽與確認 | Installation Summary 列出 canonical 路徑、agent、檔案數、會覆蓋哪些；安全表列 ATH、Socket、Snyk 的結果。**但 find-skills 建議 agent 用 `npx skills add <pkg> -g -y`，`-y` 會跳過確認** | `add.ts:155-200, 1124-1166`；`SKILL.md:95-103` |
| 安裝方式 | 一份 canonical 副本，再 symlink 或複製到各 agent。`agents.ts` 定義了 79 個 agent 項目 | `add.ts:1093-1115`；`src/agents.ts`（`displayName` 計數） |
| 驗證與第一次成功 | 只有安裝摘要。裝完會出一次性的提示「要不要裝 find-skills」，回絕過就記下來不再問 | `add.ts:2985-3010` |
| 更新與通知 | lock 檔記 `skillFolderHash`，`check` 與 `update` 比對上游雜湊；不會主動通知 | `src/update.ts:721` |
| 隱私與安全 | 遙測預設開，送 install、remove、update、find（**含查詢字串**）、sync 事件；用 `DISABLE_TELEMETRY` 或 `DO_NOT_TRACK` 關。安全稽核只在 GitHub 確認是公開 repo 後才查，私人 repo 的名稱不外送。在 agent 或非 TTY 環境不跑互動式搜尋 | `src/telemetry.ts:3-4, 75-77, 132-166`；`find.ts:343, 370-371, 381`；`add.ts:2280-2290` |

### 2.4 Codex skill-installer（本機）[已驗證]

| 面向 | 做法 | 證據（`~/.codex/skills/.system/skill-installer/`） |
|---|---|---|
| 觸發 | 使用者要列出或安裝 skill | `SKILL.md:3, 12-15` |
| 掃描 | 只看 `$CODEX_HOME/skills` 裝了哪些，列表時標「already installed」 | `scripts/list-skills.py:38-48`；`SKILL.md:58` |
| 題目 | 1 題：「Which ones would you like installed?」 | `SKILL.md:21-28` |
| 推薦邏輯 | 沒有。透過 GitHub API 列出 openai/skills 的 `.curated`（或 `.experimental`） | `SKILL.md:10, 54` |
| 預覽與確認 | 只有清單 | — |
| 安裝方式 | 公開 repo 下載 zip，失敗改用 git sparse checkout；防 zip slip；驗證路徑；一定要有 SKILL.md；拒絕 symlink 與其他檔案類型；目的地已存在就中止 | `SKILL.md:45-50`；`scripts/install-skill-from-github.py:108-128, 195, 201-216, 219-222` |
| 驗證 | 只告訴使用者「下一回合就能用」 | `SKILL.md:30` |
| 更新與通知 | 沒有（目的地存在就中止） | `SKILL.md:47` |
| 隱私與安全 | 需要連網，在沙箱內要申請提權；私人 repo 可用既有 git 憑證或 `GITHUB_TOKEN`／`GH_TOKEN` | `SKILL.md:34, 55` |

### 2.5 Codex 的 plugin 目錄與工作中建議（openai/codex @ ba057e4＋本機）

**目錄欄位**［已驗證，本機快取］：10,631 個 plugin。

| 欄位 | 數值分佈 |
|---|---|
| `discoverability` | LISTED 10,602、UNLISTED 29 |
| `installation_policy` | AVAILABLE 10,608、NOT_AVAILABLE 22、INSTALLED_BY_DEFAULT 1 |
| `status` | DISABLED_BY_ADMIN 22（管理員可以關） |
| `authentication_policy` | ON_INSTALL 或 ON_USE |
| `release.keywords` | 4,452 個有填 |
| `interface.default_prompts` | 9,530 個有填 |
| `onboarding_skill_name` | 830 個有填，例如 `get-started` |

另有 `must_show_installation_interstitial`。`config.toml` 裡註冊的 marketplace 有 openai-bundled、openai-primary-runtime、ponytail、claude-mem-local、anthropic-agent-skills、agent-skills（只讀區段名稱）。

**工作中建議（tool_suggest）**［已驗證］：

| 機制 | 做法 | 證據 |
|---|---|---|
| 功能旗標 | `tool_suggest` 穩定版、預設開；`recommended_plugins` 穩定版、預設關。建議要 Apps 加 Plugins 加其中一個旗標都開才有；Apps 另有 ChatGPT 登入的條件 | `codex-rs/features/src/lib.rs:660-668, 1823-1832` |
| 清單版（ListTool） | 模型先呼叫 `list_available_plugins_to_install`，再呼叫 `request_plugin_install`。條件是使用者**明確要求**某個尚未可用的 plugin 或連接器，而且 `tool_search` 沒有或找不到。原文：「Do not use it for adjacent capabilities, broad recommendations, or tools that merely seem useful.」 | `core/src/tools/handlers/list_available_plugins_to_install_spec.rs:9`；`request_plugin_install_spec.rs:48` |
| 推薦清單版（RecommendationContext） | 開 session 時向 `{chatgpt_base_url}/ps/plugins/suggested/codex?scope=GLOBAL` 取清單，用 `<recommended_plugins>` 放進 developer message（「Here is a list of plugins that are available but not installed.」）。工具同樣只在使用者明確要求、而且清單內有的時候才能用。查詢參數只有 scope，沒有專案資訊 | `core-plugins/src/remote.rs:1038-1055`；`core/tests/suite/request_plugin_install.rs:593-596`；`request_plugin_install_spec.rs:69` |
| 候選範圍 | 14 個官方精選 plugin（GitHub、Notion、Slack、Gmail、Google Calendar、Google Drive、OpenAI Developers、Canva、Teams、SharePoint、Outlook 郵件、Outlook 行事曆、Linear、Figma），本機與遠端各一份；加上設定裡的 `tool_suggest.discoverables`；排除已裝、NOT_AVAILABLE 與 `tool_suggest.disabled_tools` | `core-plugins/src/discoverable.rs:18-46, 104-112, 175-185`；`core/src/plugins/discoverable.rs:17-37` |
| 互動 | `suggest_reason` 不能空白；只能在主執行緒用；codex-tui 還不支援；用 elicitation 讓使用者選接受、拒絕或取消；拒絕並選「always」會寫進 `tool_suggest.disabled_tools`；接受後會驗證真的裝好並刷新快取；建議結果會記錄統計 | `request_plugin_install.rs:119, 139-143, 150, 249-265, 295, 341-398, 400-450` |
| 設定格式 | `[[tool_suggest.discoverables]]` 與 `[[tool_suggest.disabled_tools]]`，每項 `type = "plugin"` 或 `"connector"`，加上 `id` | `codex-rs/core/config.schema.json`（ToolSuggestConfig）；`codex-rs/config/src/types.rs:265-316` |

**Codex 桌面版的下一步任務建議**：`~/.codex/ambient-suggestions/<雜湊>/ambient-suggestions.json` 每個專案一份，每則有標題、說明、現成的提示、`appIds` 與狀態。這台電腦有 16 個專案、50 則建議，全部是 `pending`。[已驗證本機資料；產生邏輯不公開]

**hooks**［已驗證］：

- 13 種事件：session-start、user-prompt-submit、stop、pre/post-tool-use、permission-request、pre/post-compact、session-end、subagent-start/stop、interrupt、model-request（`codex-rs/hooks/schema/generated/`）。
- SessionStart 與 UserPromptSubmit 可輸出 `hookSpecificOutput.additionalContext` 與 `systemMessage`；Stop 可輸出 `decision`、`reason`、`systemMessage`。
- 信任雜湊由宣告算出（事件、matcher、handler，包含指令字串）；plugin 提供的 hook 會再加上 plugin 內容雜湊（`hooks/src/engine/discovery.rs:836-841, 981-1003`）。所以寫在 `config.toml`、指令字串固定的 hook，改腳本內容不用重新信任；做成 plugin 的 hook，每次更新都要重新信任。

### 2.6 Tessl［子研究；CLI 不開源，多數是僅文件］

- **觸發**：手動跑 `tessl init`、`install`、`search`；網頁 Registry 按 Setup 會開 PR；工作中由 agent 透過 MCP 呼叫 `search`、`install`、`outdated`、`update`、`status`；`tessl agent` 的「Find work to automate」最多列 5 個排過序的候選，各附證據、預期效益與建議觸發條件（CLI 0.99.0）。
- **掃描**：init 會偵測 Claude Code、Cursor、Gemini、Codex、Copilot CLI、Copilot VS Code。**CLI 0.76.0 移除 `--project-dependencies`，原文「Dependency scanning and automatic tile matching are no longer part of the install flow」**（`tessl-docs/llms-full.txt:3303`，主線複核相符）。目前只剩網頁 Setup 會依相依套件加 plugin。不看硬體。
- **題目**：文件沒寫 init 的互動題目，只有 `--agent`、`--name` 等旗標；實際大約 0 到 2 題。
- **推薦邏輯**：依名稱、PURL 或網址搜尋；用品質分數排序，沒有 eval 時只算 review 分數的 80%，有 3 個以上 eval 才算滿分。impact 是「有無這個 context」的 eval 分數差。安裝已棄用的 plugin 時，會印出作者指定替代品的安裝指令（0.111.0）。
- **預覽與確認**：安裝政策有三種規則：安全分數的警告門檻（要確認）與封鎖門檻、來源限制、git 來源的最短發布天數。政策分 org、workspace、project 三層，最嚴的生效。`outdated` 先列清單，再讓使用者跑 `update`。
- **安裝方式**：
  - 內容放在 `.tessl/plugins/`，`tessl.json` 鎖版本。
  - 規則彙整成 `.tessl/RULES.md`，在 AGENTS.md 裡用標記區塊引用。
  - skill 用 symlink 放進 `.agents/skills`，全域安裝另外 symlink 到 `~/.gemini/config/skills/`（Antigravity）。
  - Windows 可以用 winget，也有簽章安裝程式。啟動器會先驗證有簽章的 SHA256SUMS（`bin/tessl.js:384-416`，子研究已驗證）。
- **驗證與第一次成功**：`tessl doctor`，但文件自己承認 doctor 通過不代表真的能用；請 agent「Use tessl to search for code review skills」，確認 MCP 有被呼叫；新使用者會被帶進 `tessl agent` 的引導。
- **更新與通知**：`outdated --json`；`update` 預設跳過大版本更新，要 `--force` 才更新；CLI 會自動更新，可用 `TESSL_DISABLE_UPDATE` 關（`bin/tessl.js:27`）。
- **隱私與安全**：`shareUsageData` 預設為 true，收集的內容「may include conversations, code snippets and file contents」。

### 2.7 aitmpl（claude-code-templates）［子研究，多數已驗證］

- **觸發**：只在手動執行時。不帶參數會開目錄瀏覽器（`cli-tool/src/index.js:117-121`）；網站購物車會產生一行安裝指令。
- **掃描**：
  - 精靈模式讀 package.json 推斷框架，掃 2 層內的副檔名，再看 requirements 與 Gemfile（`utils.js:4-128`）。
  - 目錄瀏覽器比對 17 個 JS 相依，以及 pyproject、Cargo、go.mod、Gemfile、Dockerfile（`catalog-browser.js:113-138`）。
  - 已裝的 agent 標成「Already installed」（`agents.js:211-233`）。
  - **偵測有 bug**：`await findFilesByPattern(...).length` 運算順序錯誤，Django 與 Flask 的分支永遠不會成立（`utils.js:53,58`）。
- **題目**：精靈最多 8 步（`prompts.js:19-271`）；目錄瀏覽器 3 題。
- **推薦邏輯**：寫死的規則加下載數；跟專案相符的排前面，**只調整排序、不隱藏任何項目**（`catalog-browser.js:110-111, 160-162`）。
- **預覽與確認**：計畫表有 TYPE、COMPONENT、WRITES 三欄（`install-ui.js:37-46, 130-145`）。用旗標直接安裝時，計畫表印完就裝，不再確認；`--dry-run` 只在範本模式有效。
- **安裝方式**：從 GitHub main 分支下載、不釘版本（`index.js:418-424`）；寫進 `.mcp.json` 時同名 server 直接覆蓋（`index.js:459-473`）；只支援 Claude Code；外部 skill 是例外，會釘選 commit 並比對雜湊（`external-skill.js:1-19`）。
- **驗證與第一次成功**：逐項顯示 ✔ 或 ✖，最後給失敗項目的重跑指令（`install-ui.js:298-321`）；`--prompt` 可以裝完直接跑一個提示；health check 有 bug，hooks 檢查失準（`health-check.js:1023-1053`）。
- **更新與通知**：沒有安裝紀錄，所以沒有 update 與 uninstall；他們依遙測數據移除了 17 個沒人用的旗標（`CHANGELOG.md:23-28`）。
- **隱私與安全**：遙測預設開，可用 `CCT_NO_TRACKING` 等環境變數關（`tracking-service.js:9, 23-33`）；送出的錯誤訊息可能含本機路徑。

### 2.8 BMAD 安裝器［子研究，已驗證］

v6.12 用 npm 安裝器，已凍結只修 bug；v7 改用 `npx skills add` 或 plugin marketplace，再由 `bmad setup` 收尾（`README.md:18-61 @ 022be93`）。安裝器正在向 Vercel 的安裝器與原生 marketplace 靠攏。

- **掃描**：不看專案，也不看硬體。只檢查 uv 與 Python 3.11 以上、WSL 是否誤用 Windows 版 node，以及既有的 manifest。不偵測本機裝了哪些 IDE；⭐ 是寫死的偏好清單（`ide/platform-codes.yaml`）。
- **題目（v6）**：安裝目錄、官方模組（bmm 預設勾）、自訂模組、整合哪些工具、core 5 題，加上 Express Setup 或 Customize 的分岔（`modules/official-modules.js:1135-1141`），合計約 10 個提示。
- **推薦邏輯**：純規則，用 registry 裡的 `defaultSelected` 與 `deprecated`。v7 加了模組的 `recommended_skills`，程式註解寫「Worth offering, never a fault」（`skills/bmad/scripts/setup.py:903-910`）。
- **安裝方式**：
  - manifest 有三份：`manifest.yaml`、`skill-manifest.csv`，以及每個檔案附 SHA256 的 `files-manifest.csv`。
  - 重跑時用雜湊找出使用者改過的檔案：使用者自訂的檔還原，改過的官方檔另存 `.bak`（`core/installer.js:561-627`）。
  - 清理只刪 manifest 記錄過的檔案。
  - 非互動旗標齊全：`--modules`、`--tools`、`--yes`、`--list-tools` 等。
- **驗證與第一次成功**：安裝摘要每一步標 ✓、! 或 ✗；結尾提示「從專案資料夾開 agent，叫 `bmad-help`」；沒有煙霧測試。
- **更新與通知**：CLI 啟動時跑 `npm view` 查新版，只有剛好在跑安裝器時看得到。模組升級時 patch 與 minor 預設 Y、major 預設 N，`--yes` 會拒絕 major（`ui.js:2216-2251`）。v7 從來源 repo 比對版本，分成四種狀態。
- **隱私與安全**：沒有遙測。v7 規定模組作者的安裝訊息「照原文引用、絕不當指令」（`references/setup.md:35`）。

### 2.9 SuperClaude 安裝器［子研究，已驗證］

- **現版 v4.3.0**：
  - `install` 一題都不問，全部裝；`mcp` 只有一題，再逐一問各 server 的金鑰。
  - `doctor` 只檢查 3 件不相干的事，skill 檢查的檔名還寫錯（`doctor.py:88-147`）。
  - `update` 只是強制重新複製，不查新版。
  - 預設推薦需要 Docker、而且沒鎖版本的第三方 gateway。
- **舊版 v4.0.9 的優點**：
  - 兩階段選擇（先 MCP、再元件），會列出安裝計畫並請使用者確認（`cli/commands/install.py:170-372`）。
  - 改寫 `~/.claude/CLAUDE.md` 的 @import 區塊時保留使用者內容，並先備份。
  - 查 PyPI 新版 24 小時最多一次，可以用環境變數關掉（`utils/updater.py:25-27, 135-190`）。
- **Windows**：子行程不用 `shell=True`，一律加 `cmd /c`（`install_mcp.py:101-123`）。
- **反例（金鑰）**：
  - `--dry-run` 也會先問金鑰，再把含金鑰的完整指令印到終端（`install_mcp.py:553-585`）。
  - v4.0.9 在 Windows 用 `setx` 把金鑰永久寫進使用者環境變數（`utils/environment.py:134-145`）。
  - 解除安裝時會產生明文的還原批次檔（`:340-352`）。

### 2.10 Claude Code 官方：探索、推薦、瘦身、評估、`/init`、hooks

**探索與安裝** [僅文件，https://code.claude.com/docs/en/plugins/install.md]

- 詳細頁會列「Will install」（會裝哪些 commands、agents、skills、hooks、MCP 與 LSP），官方 marketplace 的 plugin 另外顯示「Context cost」：每回合多少 token、用到時多少 token。
- 範圍有三種：user、project、local。
- 安裝摘要有四種結果：Active now、Active 但 MCP 需要設定、Run /reload-plugins、載入失敗。
- 確認是否能用：打 `/` 看有沒有 `/<plugin>:<skill>`。
- 第一次開互動式終端時，會自動加入官方 marketplace。
- 官方 marketplace 預設自動更新，第三方預設不更新；更新後提示「Plugin updated: <name> · Run /reload-plugins to apply」。

**情境建議（relevance）** [僅文件，`cc-docs/plugins_relevance.md`]

- marketplace.json 的 plugin 項目可以加 `relevance`：一個 `topic` 加上 `signals`。訊號有 `cwd`、`cli`、`hosts`、`filesRead`、`manifestDeps`，`filesRead` 與 `manifestDeps` 也比對寫過的檔與 CLAUDE.md（`:91-99`）。
- 比對在本機進行，不連網，也不回報哪個訊號符合（`:29`）。
- 顯示位置有三個：spinner 提示、session 開頭的一行通知（只有 `cwd` 能觸發）、Discover 分頁置頂（`:31-35`）。永遠不自動安裝，一定由使用者確認（`:39`）。
- 頻率限制（`:211-216`）：
  - spinner 提示與開頭通知合計，每 3 個 session 最多 1 次。
  - 開頭通知合計顯示 2 次就停。
  - 裝了就不再提。
  - Discover 只在第一次打開時置頂，記錄在 `~/.claude.json`。
- 終端機要管理員在 managed settings 的 `pluginSuggestionMarketplaces` 加白名單，並宣告來源才會生效（`:159-168`）。`spinnerTipsEnabled: false` 會連帶關掉（`:41`）。

**CLI 提示** [僅文件，`cc-docs/plugins_cli-hints.md`]

- 工具在 Claude Code 內執行時，往 stderr 寫一行 `<claude-code-hint v="1" type="plugin" value="name@marketplace" />`（`:9, 69-79`）。
- 只限官方 marketplace 的 plugin（`:11`）。
- 遙測關掉時不提示；`-p`、子 agent、hook 輸出、雲端、無人值守的 session 也不提示（`:85-91`）。
- 頻率：每個 session 1 次、每個 plugin 一生 1 次、整台電腦問過 100 個後就不再問（`:89`）。
- 選項：Yes、No、No and don't show again；30 秒沒回答算 No（`:107-119`）。

**LSP 建議對話框** [僅文件，`cc-docs/plugins_code-intelligence.md:83-110`]

- PATH 上已有 language server、但對應的 plugin 沒裝時，在編輯該類檔案後提示；有多個來源時官方優先；每個 session 最多 1 次。
- 選項：No, not now、Never for this plugin、Disable all LSP recommendations。
- 30 秒沒回答算忽略，次數跨 session 累計；忽略 5 次就停。狀態存在 `~/.claude.json` 的 `lspRecommendationDisabled`、`lspRecommendationIgnoredCount`、`lspRecommendationNeverPlugins`。

**spinner 提示的調整** [已驗證 CHANGELOG @ 26382c0]

| 變更 | CHANGELOG 行 | 版本 |
|---|---|---|
| frontend-design 的建議提示一生最多顯示 3 次 | `:4820` | 2.1.217 |
| 修正讀或發佈 Artifacts 後誤推 frontend-design | `:3154` | 2.1.273 |
| 已經有的就不提示 | `:6676` | 2.1.120 |
| 移除啟動時的 JetBrains plugin 安裝建議 | `:5861` | 2.1.160 |
| plugin 與 LSP 安裝建議等使用者送出或清掉輸入才出現 | `:3986` | 2.1.251 |
| Discover 分頁標「suggested for this directory」 | `:5926` | 2.1.154 |
| 新增 `pluginSuggestionMarketplaces` | `:6006` | 2.1.152 |

**對話中由模型建議**：模型用 SearchPlugins 搜 claude.ai 的組織目錄與 Anthropic 官方目錄，用 SuggestPluginInstall、SuggestSkills 顯示安裝卡片；同一段對話裡使用者沒理會就不再建議，不確定有沒有幫助時不建議。[依委託方提供的工具定義摘要；本 session 的 SearchPlugins 工具說明一致] 雲端 session 不受 `pluginSuggestionMarketplaces` 限制（`plugins_org.md:366`）。

**瘦身** [僅文件，`cc-docs/plugins_measure.md:95-119`]

- `/plugin` 的「Not used recently」條件是至少 14 天**而且**至少 10 個 session 沒用。
- 不列入的：用 `--plugin-dir` 或 managed settings 啟用的 plugin，以及含主題、輸出風格、monitor、workflow 的 plugin；LSP 有回診斷就算用到。
- `/skill-doctor` 列出從沒被叫過的 skill；`/doctor` 建議停用沒用的 skill、MCP 與 plugin；`/usage` 顯示各項的使用占比。CHANGELOG `:5452`（2.1.187）。

**評估** [僅文件，`cc-docs/plugin-evals.md:44-52, 111`]

- `claude plugin eval` 每個案例預設跑 3 次，分別在有 plugin 與沒 plugin 的情況下跑，得到 WITH、W/OUT 與 Δ。
- 常見的第一個發現是 Δ 接近 0、而且 `tool_used: Skill` 沒通過，意思是 skill 根本沒被選到。
- `claude plugin eval init` 會問作者問題、提案例、試跑後寫檔。

**`/init`** [僅文件]

- 預設：分析 codebase，產生 CLAUDE.md；已有就建議改進、不覆蓋（`memory.md:76`）。
- 設 `CLAUDE_CODE_NEW_INIT=1`：先問要建哪些產物（CLAUDE.md、skills、hooks），用 subagent 探索 codebase，追問缺的資訊，**寫檔前給可審查的提案**（`memory.md:78`）。
- 找到 Codex 或 Gemini CLI 的設定時，會提議用 `/import` 帶過來（`commands.md:102`）。

**hooks** [僅文件，`cc-docs/hooks.md`]

- `systemMessage` 是給使用者看的警告訊息（`:1067`）。
- `additionalContext` 會包成 system reminder 放進對話（`:1113`）；上限 10,000 字元（`:1050`）。
- SessionStart 可輸出 `additionalContext`、`sessionTitle`、`reloadSkills`；`reloadSkills: true` 會在 hook 跑完後重新掃描 skill 資料夾（`:1169, 1295-1305`）。
- UserPromptSubmit 不能改寫使用者的 prompt，只能附加 context（`:1177`）。
- Stop 的 `additionalContext` 會讓對話繼續跑（`:1158`），不能拿來放提示。Stop 時 transcript 不保證已含最後一則回覆，要用 `last_assistant_message`。

**managed settings（Windows）** [僅文件]

- 檔案在 `C:\Program Files\ClaudeCode\managed-settings.json`，一般使用者不能寫。
- `HKCU\SOFTWARE\Policies\ClaudeCode` 的 `Settings` 是使用者可寫的備援來源，只有在沒有任何管理員文件時才會採用。
- 開發者不能寫 HKLM。

### 2.11 Antigravity hooks [僅文件＋本機字串比對]

- **官方文件**（https://antigravity.google/docs/hooks）：

  | 事件 | 時機 | 輸出 |
  |---|---|---|
  | `SessionStart` | 第一次呼叫模型之前 | 可選 `injectSteps`，例如 `systemMessage` 步驟 |
  | `PreToolUse` | 工具執行前 | `decision`：allow、auto_approve、deny、ask、force_ask、deny_unless_prior_grant；可附 `reason`、`overwrite`、`permissionOverrides` |
  | `PostToolUse` | 工具執行後 | 只能輸出 `{}` |
  | `PreInvocation` | 每次呼叫模型前 | `injectSteps`：`systemMessage`、`userMessage`、`ephemeralMessage` 或 `toolCall` |
  | `PostInvocation` | 每次模型呼叫後 | `injectSteps`，加上 `terminationBehavior` |
  | `Stop` | 執行迴圈結束時 | `decision: "continue"` 才會繼續，`reason` 會以 system message 注入 |

- matcher 只對 PreToolUse 與 PostToolUse 有效。逾時預設 30 秒。
- 位置：工作區是 `.agents/hooks.json`，全域是 `~/.gemini/config/hooks.json`；plugin 的 hook 只有 CLI 版支援。
- **文件沒有描述信任模型，也沒有給使用者看的訊息欄位。**
- **本機**：`C:\Users\user\AppData\Local\Programs\antigravity\resources\bin\language_server.exe`（2026-10-29）內含這些字串：PreInvocation 113 次、PostInvocation 104 次、SessionStart 84 次、injectSteps 16 次、ephemeralMessage 11 次、hooks.json 26 次、deny_unless_prior_grant 3 次。這只證明這版二進位有這些功能的字串，沒有實際跑過 hook。`~/.gemini/config/` 目前沒有 hooks.json。
- 第三方 wiki（alexherrero/crickets）說 Antigravity 的 plugin hook 只能觀察、不能注入，這不是官方說法，未驗證。

### 2.12 其他 2026 年做法［子研究］

| 工具 | 類型 | 要點 | OmniKit 可借或要避開 |
|---|---|---|---|
| Docker MCP Toolkit 的 Dynamic MCP [僅文件] | 工作中動態加 MCP | agent 在對話中用 `mcp-find` 搜 catalog、用 `mcp-add` 加入；加入的只在這個 session 有效；預設開啟；文件沒寫加入前要使用者同意 | 可借：只從白名單加，而且只在 session 內有效。要避開：預設開、沒有確認 |
| Goose Extension Manager [僅文件] | 工作中啟用或停用 | 官方建議同時啟用 5 個以下 extension，工具合計 50 個以下 | 用數量上限支持「做減法」；先啟停已裝的，再考慮新裝 |
| Kiro Powers [僅文件] | 依關鍵字載入 | manifest 宣告觸發關鍵字；開始任務時只載入相關的 power；可一鍵安裝，沒寫預覽 | 卡片加觸發訊號；先比對已裝但沒啟用的 |
| Cline Marketplace [已驗證 `marketplace-helpers.ts:51, 152-170, 369-404 @ 7a7878c`] | 精選目錄，用固定程式安裝 | 目錄是一份 JSON；企業可以全關或用 MCP 白名單；安裝逾時 120,000 ms；輸出上限 12,000 字元並遮蔽敏感字樣 | 安裝走固定程式，不讓 LLM 讀 README 照做；白名單 |
| SmartSkills.Cli、skillgrab、stackskills、TanStack Intent [僅文件] | 依相依套件推薦 skill | lock 檔記 commit SHA 加內容雜湊；有 `--dry-run`；偵測器是純函式；TanStack 讓函式庫作者隨套件發布 skill | 偵測器寫法與 lock 檔可借；人氣排序不可借 |
| llm-checker、llmfit [僅文件] | 依硬體推薦本地模型 | 偵測 CUDA、RAM、VRAM，分成 Perfect、Good、Marginal、Too Tight | 硬體掃描只要輸出「適配等級加理由」 |
| VS Code MCP、Warp、Gemini CLI extensions [僅文件] | 輔助 | VS Code 加 MCP 要使用者先審來源再按 Allow；Warp 依使用模式建議規則，接受才建立；Gemini extensions 依安裝方式檢查更新 | — |
| 不納入 | — | Smithery（現行 CLI 無法確認，Toolbox 是雲端代管）；mcp-installer（讓 LLM 裝任意套件、沒白名單）；rn-skills（PR 未合併）；LM Studio（相容性標籤沒有公開門檻）；Cursor、Roo Code（沒找到掃描後推薦的公開說明） | — |

### 2.13 主動推薦但不煩人的先例：VS Code、JetBrains［子研究，已驗證］

**VS Code @ becf53f**。N = `src/vs/workbench/contrib/extensions/browser/extensionRecommendationNotificationService.ts`，T = `src/vs/platform/extensionManagement/common/extensionTipsService.ts`。

- 同時只顯示 1 則通知；新的進來時，舊的那則顯示滿 3 秒就收進通知中心（N:355-375）。
- 依本機程式推薦（exe）：同一個視窗已出過 exe 推薦、或已出過任意 2 則推薦，就回傳 `TooMany`，1 小時後再試（N:222-227，T:244-247，主線複核）。
- 高重要度每次重啟最多 1 次；中重要度每 7 天最多 1 次；第一次執行時把「上次提示時間」設成當下，所以新安裝的頭 7 天都不提（T:221, 255-264, 317-322）。
- 已裝或無法安裝的不提（N:236-238）。
- 「不要再顯示」分 profile 與 workspace 兩層；按了之後會再問「要不要忽略全部推薦」（N:43-44, 165-205）。
- 只有按了按鈕才記成「已提示」；直接按 X 關掉不記，之後可能再跳出來 [推論]。

**JetBrains @ f34642e**

- 只在受信任的專案觸發（`PluginsAdvertiserStartupActivity.kt:62`）。
- 每個生態系的 `DependencyCollector` 回傳套件座標與給人看的理由，格式是「This plugin is suggested because XYZ」（`DependencyCollector.kt:38-66`）。
- 依本機程式推論的建議不發通知（`PluginAdvertiserService.kt:184, 224-245`）。
- 一次只顯示一則（`SingletonNotificationManager`）。
- 忽略分專案與全域兩層。

---

## 3. 橫向比較

### 3.1 觸發、掃描、題數、推薦邏輯

| 工具 | 觸發 | 掃描 | 題數 | 推薦邏輯 |
|---|---|---|---|---|
| ECC v2 | 手動或 skill | 已裝狀態 | 2 | 規則、寫死預設、關鍵字評分 |
| setup-claude | skill | 帳號角色、已裝的 plugin、已連的連接器 | 角色 0 或 1 題，加 3 個是或否 | LLM 加目錄搜尋，組織優先，2 到 3 個 |
| find-skills／npx skills | skill 描述（LLM） | 已裝的 agent；選配 node_modules | find 0；add 3 到 4 | 伺服器端排序、安裝數、星數 |
| Codex skill-installer | skill | 已裝的 skill | 1 | 沒有，只列精選清單 |
| Codex tool_suggest | 模型（只限明確要求） | 已裝與停用 | 1 次 elicitation | 精選 14 個、設定的 discoverables、伺服器推薦清單 |
| Tessl | 手動、MCP、網頁 | 已裝的 agent（相依掃描已撤） | 0 到 2 | 品質分數、impact、依 eval 數打折 |
| aitmpl | 手動 | 相依與副檔名（有 bug） | 最多 8 | 規則加下載數，只排序不隱藏 |
| BMAD | 手動或 skill | 前置工具、manifest | 約 10（有 Express） | 寫死的 `defaultSelected` |
| SuperClaude v4.3 | 手動 | 前置工具 | 0 到 1 | 寫死 |
| Claude Code relevance | 本機訊號 | cwd、cli、hosts、檔案、manifest | 0（卡片） | 訊號符合就提，要管理員白名單 |
| Claude Code `/init`（新流程） | 手動 | codebase（subagent） | 視缺口追問 | LLM 加可審查的提案 |

### 3.2 預覽、安裝、驗證、更新、隱私

| 工具 | 預覽與確認 | 安裝 | 驗證與第一次成功 | 更新與通知 | 隱私 |
|---|---|---|---|---|---|
| ECC v2 | dry-run JSON、單一確認、hook 能力揭露 | 原生 plugin 指令 | 獨立清單驗證、成功才顯示歡迎 | 重跑或 auto-update，不通知 | 揭露把對話送外部 LLM 的能力 |
| setup-claude | 卡片 | 平台 UI | Try a skill | 無 | 只讀使用者自己寫的內容 |
| npx skills | 摘要＋覆蓋＋安全表 | symlink 或複製 | 摘要 | check／update 比雜湊 | 遙測預設開、送查詢字串 |
| Codex skill-installer | 清單 | zip 或 sparse | 下一回合能用 | 無 | 需要提權 |
| Codex tool_suggest | elicitation | 原生 | 安裝後驗證 | — | 推薦清單由伺服器提供 |
| Tessl | 政策門檻、PR diff | `.tessl` 加 symlink | doctor（不可靠） | outdated，大版本要同意 | 使用資料預設分享 |
| aitmpl | WRITES 表 | main 不釘版本 | ✔／✖、重跑指令 | 無 | 遙測預設開 |
| BMAD | 只列選項 | 複製、SHA256 manifest | 摘要、提示 bmad-help | 只在跑安裝器時查 | 無遙測 |
| SuperClaude v4.3 | 只有 dry-run | 複製、`npx -y` | doctor 失準 | 無 | dry-run 會印出金鑰 |
| Claude Code | Will install、Context cost | 原生 | 安裝摘要、`/` 選單 | 官方 marketplace 自動更新 | 訊號在本機比對 |

---

## 4. OmniKit v2 流程：每一步採用誰的做法

現況：訪談 6 題只產生 `AGENTS.md` 與 `scenarios.yaml`（`engine/skills/omnikit-setup/SKILL.md:33-47`）；`install.ps1:408` 寫明預設 plugin 不自動安裝；`scan.py` 只看 agent 與工具在不在、版本多少（`engine/scripts/scan.py:5-8, 154-185`）。

### 4.0 總原則

1. **腳本做決定，agent 只轉述。** 每個會寫入的步驟都有 `--dry-run --json` 與 `--yes --json` 兩種模式（ECC `SKILL.md:74-111`；BMAD v7；OmniKit 現有 `omnikit-setup/SKILL.md:13` 已經是這樣）。
2. **掃描結果只拿來預選與排序，不拿來隱藏**（aitmpl `catalog-browser.js:110-111`）。每個預選都附一句理由（JetBrains `DependencyCollector.kt:38-66`）。
3. **只確認一次。** 預設路徑最多 6 題加 1 次確認（ECC `SKILL.md:91-93`）。
4. **交給各 agent 原生指令安裝**，不讓 LLM 手動複製（ECC `SKILL.md:12-13`，對照 v1.10.0 `:26-35, 195-200`）。
5. **用 agent 自己的清單獨立驗證**，不只看「寫入成功」（ECC `SKILL.md:115-123`；Codex `request_plugin_install.rs:400-450`）。
6. **推薦依據有優先序**：名冊實測、名冊狀態、外部訊號。find-skills 的安裝數門檻（`SKILL.md:65-71`）只在同分時用來排先後。
7. **本機優先、不外送。** 掃描結果、使用紀錄、查詢字串預設都不離開這台電腦（Claude Code `relevance.md:29` 的做法；對照 skills.sh、aitmpl、Tessl 的預設遙測）。

### 4.1 入口與觸發

- install.ps1 結束時已經提示「說『幫我設定 OmniKit』」（`install.ps1:400-408`）。
- 另外加一個一次性提示：還沒建 profile 時，SessionStart hook 印一行 `systemMessage`，最多 2 次（借 Claude Code session 開頭通知「合計 2 次就停」：`relevance.md:203-214`）。
- skill 開頭先判斷自己在哪個 agent，照該 agent 能做的走；不確定就說出依據再問（ECC `SKILL.md:19-27`）。
- 開頭建 6 項進度清單（setup-claude `SKILL.md:10-23`）：環境掃描、專案掃描、確認需求、預覽工具包、安裝與驗證、試用一次。
- 重新設定時帶入上次的答案（OmniKit 已有 `previous_answers`；Vercel 會記住上次選的 agent：`add.ts:583-605`）。

### 4.2 環境與硬體掃描（可選）

各家幾乎都不掃硬體：aitmpl 只看記憶體有沒有 4GB，也不拿來推薦；BMAD 與 SuperClaude 只檢查前置工具。建議改名「環境掃描」，硬體只是其中一部分，**只收會改變推薦或安裝方式的欄位**：

| 欄位 | 為什麼要 | 唯讀的讀法 | 影響 |
|---|---|---|---|
| 系統管理員權限、開發人員模式 | Windows 建 symlink 需要其中之一；Vercel 預設推薦 symlink（`add.ts:1093-1115`） | 讀 token 群組；讀 `AllowDevelopmentWithoutDevLicense` 登錄值 | 都沒有就改用複製 |
| 長路徑支援 | aitmpl repo 在 Windows checkout 有 9,904 個檔案失敗，要設 `core.longpaths=true`［子研究］ | 讀 `LongPathsEnabled`、`git config core.longpaths` | 預覽時警告；改用打包版 |
| 防毒產品名稱 | Trend Micro 擋過 skillshare（定位稿 §3） | `root/SecurityCenter2` 的 `AntiVirusProduct.displayName` | 卡片的 `blocked_on` 符合就不推 |
| Proxy、PowerShell 執行原則 | `npx`、`uv` 下載會失敗 | 只看環境變數名稱、`Get-ExecutionPolicy -List` | 列入「要你處理的事」 |
| Node、Python、uv、git、gh、Docker、WSL 版本 | 對照卡片的 `requires` | 擴充 scan.py 現有的 TOOLS | 不相容就不推 |
| CPU 執行緒、記憶體、顯示卡型號與 VRAM、可用磁碟空間 | 本地模型、Docker 類 MCP | `Win32_Processor`、`Win32_ComputerSystem`；有 `nvidia-smi` 就用它查 VRAM | 輸出「適配等級加理由」（llm-checker、llmfit 的做法） |

- [推論] `Win32_VideoController.AdapterRAM` 是 32 位元，超過 4GB 的顯示卡會讀錯；VRAM 要用 `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader`。
- 只輸出名稱與數值，不上傳，跟 scan.py 現有原則一致（`scan.py:5-8`）。
- 依本機程式推論的建議只出現在預覽與週報，不在工作中跳出（JetBrains `PluginAdvertiserService.kt:184, 224-245`）。

### 4.3 專案掃描（可選）

- **候選專案**從三個 agent 的本機紀錄拿：Claude Code 的 `~/.claude/projects`、Codex `config.toml` 的 `[projects]`、Antigravity 的 `~/.gemini/projects.json`。列成勾選清單，使用者勾了才掃；只掃受信任的專案（JetBrains `:62`）。
- **偵測器**寫成純函式（rootDir 進、signals 出），並行執行後去重（skillgrab）。每個偵測器都附 fixture 自我測試，避免 aitmpl 那種永遠不成立的分支。OmniKit 本來就有 `--selftest` 的習慣。
- **訊號格式**沿用 Claude Code relevance 的 `cwd`、`cli`、`hosts`、`filesRead`、`manifestDeps`（`relevance.md:91-97`），再加一個 `files`（專案內的檔案樣式，例如 `**/*.ipynb`）。
- **對應到槽位，不對應到函式庫**（Tessl 已撤掉依相依配對：`llms-full.txt:3303`）。例如：
  - 有 `vite.config.*`，或 package.json 有 react → 前端設計
  - 有 `*.ipynb`，或 pyproject 有 pandas → 資料分析（新槽位）
  - 檔案數很多的大型 repo → 程式碼理解與搜尋
  - 有測試設定 → 審查與驗收
- 只預選與排序，不隱藏；每個加選都附「因為 <專案> 有 <檔案>」。

### 4.4 訪談

- 保留現有 6 題（`omnikit-setup/SKILL.md:33-47`）；掃描查得到的只請使用者確認（`:12`）。
- 第 6 題的專案名稱改成從 4.3 的清單勾選，少打字。
- 推薦的選項放第一個，並標「（建議）」（Claude Code 的選擇題支援 Recommended 標記：CHANGELOG 2.0.62 `:8923`；ECC `install-guided.js:125`）。
- 組完工具包只多問 1 題：「照建議裝（建議）／我要逐項調整」（BMAD 的 Express 與 Customize 分岔：`official-modules.js:1135-1141`）。
- 不要回到 ECC v1 的分類多選加逐項確認（v1.10.0 `:65-102`）；ECC 自己在 v2 已改成 2 題（`SKILL.md:50-69`）。

### 4.5 自動組工具包（推薦邏輯）

工具包 = 訪談答案對應的槽位，加上專案訊號對應的槽位，再到每個槽位取名冊裡的工具。

1. **對應表**：定位稿 §4.1 的表（`positioning.md:79-89`），加上 4.3 的專案訊號。
2. **每個槽位依序過濾**：
   - 狀態：`default` 勾選；`trial` 列為可選但不勾；`pending` 只在槽位沒有預設時列為「社群推薦（未實測）」，也不勾；`rejected` 與 `retired` 不列（對應 Tessl 的政策分級）。
   - 相容：`works_with` 要包含這台的 agent，`requires` 要符合 4.2 的結果，`blocked_on` 不能符合。
   - 已裝：已裝的另列「已經有了」，不重複推（setup-claude `SKILL.md:37-41`）。
   - `native`：不用裝，寫進規則就好，例如「改完先跑 /review」（`positioning.md:92`）。
3. **同一槽位有多個候選時**：先看在使用者情境的實測分數或 Δ，再看決定日期較新的，最後才看外部訊號（skills.sh 安裝數、Snyk 與 Socket 掃描、依 eval 數量打折後的 Tessl 分數）。
4. **團隊名冊優先於個人預設**（setup-claude 的「組織 plugin 一律排第一」：`SKILL.md:39`）。之後若有 ITRI 團隊共用的名冊，就排在通用預設前面。
5. **數量上限**：第一次最多裝 5 個需要安裝的工具，並顯示合計的 context 成本。依據有兩個：Goose 建議同時啟用 5 個以下 extension；OmniKit 自己的實測，skill 清單從 49,335 字元降到 15,877 字元，token 少約 27%（`positioning.md:64-67`）。
6. **腳本輸出 JSON**：每項附 `reason`（取自卡片）、`evidence`（評估檔路徑）、`why_selected`（由哪題答案或哪個專案訊號選上）。理由的格式可以借 ECC consult.js 的「matched x」（`consult.js:257-287`）。

### 4.6 預覽

| 欄位 | 借自 |
|---|---|
| 勾選、工具、類型 | aitmpl 的 TYPE 與 COMPONENT 欄（`install-ui.js:37-46`） |
| 為什麼選它：槽位、卡片理由、實測證據、由哪題答案或哪個專案訊號選上 | OmniKit 卡片的 `reason`；JetBrains 的理由字串 |
| 狀態：預設、試用中、社群推薦（未實測） | Tessl 的政策分級；定位稿 §4.2 |
| 裝到哪些 agent、寫到哪些檔案 | aitmpl 的 WRITES 欄；ECC 的 Harness／Destination 表（`install-guided.js:207-213`） |
| 會覆蓋什麼 | Vercel 的 overwrites（`add.ts:1155-1161`） |
| context 成本（每回合、用到時） | Claude Code 詳細頁的 Context cost |
| 能力揭露：改原始碼、改寫指令、把對話送外部 LLM、連網、寫紀錄、改權限 | ECC 的 6 類（`hook-consent.js:12-37`） |
| 遙測：預設開不開、怎麼關 | aitmpl、skills.sh、Tessl 的教訓 |
| 要你做的事（一次講清楚）：Codex 要信任 hook、要開新 session、Windows 要開長路徑 | `engine/scripts/codex_hooks.py` 的說明 |

- 另外列「不會裝」的工具與原因：不相容、被防毒擋、拒絕過。
- 只確認一次，預設為否（ECC `install-guided.js:226-230`）。agent 端用 dry-run 的 JSON 產生預覽（ECC `SKILL.md:80-93`）。

### 4.7 安裝

- **skills 與 MCP**：沿用 `engine/scripts/agents.py`。它已經能接三個 agent、記錄安裝內容，而且只刪自己裝的（`agents.py` 的 `owned`、`remove_owned`、`tree_hash`、`load_record`）。
- **plugin**：用各 agent 原生的指令。Claude Code 用 `claude plugin install <name>@<marketplace> --scope user`（plugins/install.md 的「Install from your shell」）；Codex 用 `codex plugin add <name>@<marketplace> --json`（ECC `SKILL.md:156-162`）。
- **版本釘選**：卡片的 `plugin` 欄位已經要求 git 來源固定 sha、npm 固定版本（`engine/schema/tool.schema.json`）。外部 skill 要釘 commit 並比對雜湊（aitmpl `external-skill.js:1-19`；Vercel `update.ts:721`；SmartSkills 的 lock 檔）。
- **保護使用者改過的檔**：安裝紀錄加上每個檔案的 hash，重跑時遇到使用者改過的檔就另存 `.bak`（BMAD `installer.js:561-627`）。
- **Windows**：
  - 子行程不用 `shell=True`，npx 走 `cmd /c`（SuperClaude `install_mcp.py:101-123`）。
  - 沒辦法建 symlink 就改用複製。
  - 執行期不跑沒釘版本的 `npx -y`。
- **金鑰**：只記環境變數名稱，不收值、不印出。SuperClaude 的 dry-run 印出金鑰、用 `setx` 寫永久環境變數，都是反例。
- **失敗不中斷整批**：逐項顯示 ✔ 或 ✖，最後給重跑指令（aitmpl `install-ui.js:298-321`；ECC `install-guided.js:319-324`）。
- **非互動模式一定要 `--yes`**（ECC `install-guided.js:202-204`）。agent 的 shell 不是 TTY，不要跑互動指令（ECC `SKILL.md:93-94`；Vercel `find.ts:370-371`）。

### 4.8 驗證

分三層：

1. **寫入檢查**：agents.py 的 status，加上安裝紀錄比對。
2. **agent 自己的清單**：
   - Claude Code：`claude plugin list --json`，必須剛好一個啟用的項目（ECC `SKILL.md:119-123`）。
   - Codex：`codex plugin list --json`（ECC `SKILL.md:161-165`）。
   - Antigravity：看 `~/.gemini/config/skills`。
   - Claude Code 的安裝摘要有四種結果，照實轉述。
3. **煙霧測試**（選配，會花 token，先問使用者）：用卡片的 `try` 提示跑一次非互動 session，確認工具真的被叫到（Claude Code plugin eval 的 `tool_used` 檢查：`plugin-evals.md:111`）。

不要做假的 doctor：SuperClaude 的 doctor 檢查錯的檔名，aitmpl 把 hooks 物件當陣列處理。ECC 的 doctor 看 install-state 漂移、缺檔與版本（`install-lifecycle.js:1211-1243`），是好範本。

最後一次列出所有還要使用者做的事，例如開新 session、在 Codex 信任 hook、在 Claude Code 跑 `/reload-plugins`。

### 4.9 第一次成功

- 每張卡片加 `try`：一句繁體中文提示，對應槽位的情境。依據：Codex 目錄有 9,530 個 plugin 填了 `default_prompts`、830 個填了 `onboarding_skill_name`（本機快取）；setup-claude 有 Try a skill（`SKILL.md:55-61`）。
- 依第 2 題的痛點挑 1 個工具，在 4.3 掃到的真實專案上跑，跑完說明「這就是 X 的作用」，再給下一步。依據：BMAD 結尾提示 bmad-help；Claude Code 的 LSP 驗證法「故意弄出型別錯誤再修」（`plugins_code-intelligence.md:63`）。
- 可以跳過；跳過不影響安裝完成（setup-claude `SKILL.md:94`）。

### 4.10 之後：只留有用的，有更好的就通知

- **只留有用的**：沿用 `usage.py` 讀三個 agent 的紀錄。「沒在用」改成雙門檻：14 天**而且** 10 個 session 都沒用（Claude Code `plugins_measure.md:95`）。排除剛裝的（usage.py 已有）、主題與輸出風格這類沒有呼叫紀錄的（`:97-103`）；LSP 有回診斷就算用到。
- **有新版**：用鎖定檔比對上游；每 24 小時最多查一次，可以關（SuperClaude v4.0.9）；跨大版本要使用者同意（Tessl `update`；BMAD major 預設 N）。
- **有更好的**：名冊換了某槽位的預設，或卡片有 `replaces`，而使用者裝的是舊的，就通知（Tessl 安裝已棄用的 plugin 時會印出替代品）。
- **送達方式**：週報（已有）加上 SessionStart 的一行 `systemMessage`，每週最多 1 次。使用者說「套用本週建議」，就走同一條預覽、確認、安裝、驗證的流程。

### 4.11 工具卡要補的欄位

現有欄位見 `engine/schema/tool.schema.json`：id、name、kind、slots、status、url、works_with、decided_at、reason、trial_until、replaces、plugin、sources、notes、added。建議新增：

| 欄位 | 用途 | 誰填 |
|---|---|---|
| `signals` | 專案掃描與工作中建議的比對條件（cwd、cli、hosts、filesRead、manifestDeps、files、pains） | 評估時寫 |
| `requires` | 環境需求：OS、Node、Python、Docker、VRAM、管理員權限、連網 | 評估時寫 |
| `blocked_on` | 已知會被哪些防毒或政策擋下，附證據 | 實測後寫 |
| `install` | 各 agent 的安裝方式與釘選版本（擴充現有的 `plugin`） | 評估時寫 |
| `verify` | 各 agent 的驗證方式 | 評估時寫 |
| `try` | 第一次成功的提示 | 評估時寫 |
| `cost` | 每回合與用到時的 context 成本 | build.py 計算，不手寫 |
| `capabilities` | 6 類能力、連網、遙測 | 第 0 層掃描，加上人工確認 |
| `replaced_by` | 替代品 | 由 `replaces` 反推，不手寫 |

---

## 5. 工作中主動建議：怎麼做得比 Claude Code 更好

### 5.1 Claude Code 現況

| 管道 | 觸發 | 頻率限制 | 限制 | 證據 |
|---|---|---|---|---|
| 對話中由模型建議（SearchPlugins → SuggestPluginInstall、SuggestSkills） | 模型判斷 plugin 或 skill 能接手任務，或讓這類任務可以重複 | 同一段對話使用者沒理會就不再建議；不確定不建議 | 只搜 claude.ai 組織目錄與 Anthropic 官方目錄 | 委託方提供的工具定義摘要 |
| 情境建議（relevance） | 本機訊號 | 每個 plugin 每 3 個 session 最多 1 次；開頭通知合計 2 次就停；裝了就不提；Discover 只置頂一次 | 終端機要管理員白名單；`spinnerTipsEnabled=false` 會關掉 | `relevance.md:9-41, 91-97, 159-168, 211-216` |
| CLI 提示 | 工具寫 stderr | 每 session 1 次；每個 plugin 一生 1 次；整台電腦問過 100 個後停；30 秒沒回答算否 | 只限官方 marketplace；遙測關掉、雲端、無人值守、子 agent、`-p` 都不提示 | `cli-hints.md:9-11, 85-91, 115-119` |
| LSP 對話框 | 編輯檔案、PATH 上有對應的 language server | 每 session 1 次；忽略 5 次就停 | 雲端不提示 | `code-intelligence.md:83-110` |
| spinner 提示 | 內建規則 | frontend-design 一生最多 3 次；已經有的不提 | — | CHANGELOG `:4820, :6676` |
| 瘦身 | `/plugin`、`/doctor`、`/skill-doctor` | 14 天而且 10 個 session | 只看 Claude Code | `plugins_measure.md:95-119` |

### 5.2 Codex 現況

- `tool_suggest`：只在使用者明確要求、而且工具搜尋找不到時才建議；候選限 14 個官方精選，加上設定的 `discoverables`；codex-tui 還不支援；拒絕後可以永久記下（§2.5）。
- `recommended_plugins`（預設關）：由伺服器提供「可裝但沒裝」的清單，放進 developer message，每個 session 都要花 token。
- 可以接的地方：把名冊預設、但這台 Codex 沒裝的 plugin 寫進 `[[tool_suggest.discoverables]]`，讓 Codex 原生流程在使用者明確要求時接手（`core-plugins/src/discoverable.rs:104-112`）。[推論：實際能不能觸發要在桌面版實測；TUI 目前不支援]

### 5.3 兩者的限制

1. **依據不是實測。** 建議依目錄、訊號或熱門度，沒有「在你的工作上比較好」的證據。
2. **只看自己。** Claude Code 不知道 Codex 裝了什麼，反過來也一樣；「不再建議」不會跨 agent。
3. **只加，不減也不換。** Claude Code 有「Not used recently」，但不會說「X 可以換成 Y，理由是…」。
4. **公司環境門檻高。** Claude Code 的 relevance 要 managed settings；Codex 的建議要 ChatGPT 登入與 Apps；CLI 提示要遙測開著。
5. **花 token。** 模型在對話中搜目錄、或把 `<recommended_plugins>` 放進 developer message，都佔 context。
6. **管道各自為政。** 每條管道各有自己的頻率規則，沒有全域上限。

### 5.4 OmniKit 的設計：兩層

**第 1 層：在本機比對（被動，不花模型 token）**

- Stop hook：擴充 `session_nudge.py`，或在同一支 dispatcher 加子命令。目前它已經會讀 Claude Code 與 Codex 的 transcript、算上下文長度與壓縮次數，再印 `systemMessage`（`session_nudge.py:5-19`）。新的流程：
  1. 增量讀 transcript；
  2. 抽出訊號；
  3. 比對由名冊產生的訊號索引；
  4. 經過政策關卡；
  5. 最多印 1 則 `systemMessage`。
- 只推狀態是 `default` 或 `trial`、`works_with` 包含目前的 agent、沒裝、也沒被拒絕過的工具。
- 訊息用固定格式：

  > 建議：X（槽位）｜為什麼現在：<訊號，例如這週 3 個 session 的測試輸出都超過 2 萬字元>｜為什麼是它：<名冊實測一句，附評估檔>｜成本：<每回合約 N tokens>｜要裝就說「OmniKit 裝 X」；不要再提就說「OmniKit 不要再建議 X」

**第 2 層：使用者明確詢問時（主動，才用到模型）**

- 新增 `omnikit-find` skill（或併入 omnikit-setup），描述寫成「有沒有工具可以…」「推薦…工具」時觸發。
- 腳本先查名冊：用 ECC consult.js 式的關鍵字評分，附理由，回傳前 5 個；再依設定查外部目錄（`npx skills find`，同事預設關）。
- 一律走 §4 的預覽、確認、安裝、驗證。MCP 可以先「只在這個 session 試用」，要長期用再確認（Docker Dynamic MCP 的 session 範圍）。
- Codex 端同時寫 `tool_suggest.discoverables`，讓 Codex 原生流程也能接手（§5.2）。

### 5.5 訊號

| 類型 | 例子 | 對應槽位 | 依據 |
|---|---|---|---|
| 專案（cwd、filesRead、manifestDeps） | 讀了 `vite.config.ts`、package.json 有 react | 前端設計 | Claude Code relevance |
| 指令（cli、hosts） | 跑了 `docker`、`terraform` | 依卡片 | Claude Code relevance |
| 痛點：長輸出 | 單一指令輸出超過 2 萬字元，同一 session 3 次以上 | 指令輸出壓縮 | session_nudge 已經在讀 transcript |
| 痛點：沒驗證 | 改了前端檔案，沒開瀏覽器就回報完成 | 瀏覽器操作與驗證 | 槽位 U1 情境 |
| 痛點：權限 | 同一 session 權限提示很多次、任務跑很久 | 權限與通知 | 槽位 W1 情境 |
| 痛點：接手 | 一週內壓縮很多次、換 session 接手 | 記憶與交接 | session_nudge 已經在算壓縮次數 |
| 痛點：糾正 | 使用者說「不是叫你改這個」「你沒測」 | 行為準則包、審查與驗收 | 槽位 B1、R1 |

降低誤報：痛點訊號要跨 2 個 session、或同一 session 出現 3 次才算；每則建議都寫出符合的證據。[推論：門檻要實測調整]

### 5.6 三個 agent 的掛勾

| agent | 事件 | 給使用者看 | 給模型看 | 信任 | 設定位置 | 證據 |
|---|---|---|---|---|---|---|
| Claude Code | Stop | `systemMessage` | 不要用 `additionalContext`，它會讓對話繼續跑 | 不需要 | `~/.claude/settings.json` 的 hooks | `hooks.md:1067, 1158`；OmniKit `claude_allow.py` 已經在寫 Stop |
| Claude Code | SessionStart | `systemMessage` | `additionalContext`；`reloadSkills` | 不需要 | 同上 | `hooks.md:1169, 1295-1305` |
| Claude Code | UserPromptSubmit（選配） | — | `additionalContext`（不能改 prompt） | 不需要 | 同上 | `hooks.md:1177, 1511-1528` |
| Codex | Stop | `systemMessage` | `decision`、`reason` | 要信任；雜湊綁宣告 | `~/.codex/config.toml` 的 `[[hooks.Stop]]` | schema；`codex_hooks.py` 說明；`discovery.rs:981-1003` |
| Codex | SessionStart、UserPromptSubmit | `systemMessage` | `hookSpecificOutput.additionalContext` | 要信任 | 同上 | `hooks/schema/generated/*` |
| Antigravity | SessionStart | 文件沒定義 | `injectSteps`（systemMessage 等） | 文件沒描述 | `~/.gemini/config/hooks.json`、`.agents/hooks.json` | 官方文件；本機二進位字串 |
| Antigravity | PreInvocation | — | `injectSteps` | 同上 | 同上 | 官方文件 |
| Antigravity | Stop | 只有 `reason`，而且只在選擇繼續時注入 | `decision` | 同上 | 同上 | 官方文件 |
| Antigravity | PostToolUse | — | 只能 `{}` | 同上 | 同上 | 官方文件 |

**實作注意**：

- Codex 的 hook 指令字串保持固定，例如 `uv run --script <OmniKit>/engine/scripts/omnikit_hook.py stop`；邏輯放在腳本裡，更新腳本就不用重新信任（`discovery.rs:836-841`）。不要做成 plugin hook，因為 plugin hook 還綁 plugin 內容的雜湊。
- Codex 在 Windows 用 `pwsh -NoProfile -Command` 跑 hook（`codex_hooks.py` 說明）。
- Claude Code 的 Stop 要用 `last_assistant_message`，transcript 不保證已經寫入最後一則回覆。
- 大型 rollout 會到上百 MB（`session_nudge.py` 的 `CODEX_MARKS` 註解），要記住讀到的位置，只讀新增的部分。
- hook 出任何錯都安靜結束，不能擋到對話（`session_nudge.py` 現有原則）。
- 輸出要遠低於 10,000 字元上限。

### 5.7 頻率控制（建議數字）

| 規則 | 數字 | 依據 |
|---|---|---|
| 每個 session 最多主動建議 | 1 則 | Claude Code CLI 提示（`cli-hints.md:89`）、LSP（`code-intelligence.md:91`）、VS Code 同一視窗（N:222-227） |
| 全域上限 | 每天 1 則、每週 3 則 | [推論] 綜合各家；VS Code 一次只顯示一則 |
| 同一工具 | 每 3 個 session 最多 1 次；沒回應的提示累計 2 次後，只留在週報 | Claude Code relevance（`relevance.md:213-214`）；frontend-design 一生 3 次 |
| 設定後的寬限期 | 設定完成後 7 天內不主動建議 | VS Code 第一次執行設成當下、7 天不提（T:317-322）；usage.py 也不判斷剛裝的 |
| 沒回應 | 算「否」。連續 5 次沒回應或拒絕就全部靜音，並告訴使用者怎麼打開 | LSP 忽略 5 次就停（`code-intelligence.md:103`）；CLI 提示 30 秒算否（`cli-hints.md:119`） |
| 不再建議 | 分三種範圍：單一工具、這個專案、全部；三個 agent 共用 | VS Code profile 與 workspace 兩層（N:43-44, 165-181）；JetBrains 兩層；Codex 寫入 `disabled_tools` |
| 時機 | 只在回合結束（Stop）或 session 開頭；非互動（`claude -p`、`codex exec`）、子 agent、雲端、CI 都不提示 | `cli-hints.md:85-91`；CHANGELOG 2.1.251 `:3986` |
| 分級 | 實測勝出的可以主動提；沒實測的只在使用者明確詢問時出現；依本機程式推論的只進週報 | JetBrains `:184, 224-245`；Codex 只限明確要求 |
| 一律不提 | 已裝、停用、被擋、不相容、被拒絕過的 | VS Code N:236-238；Codex `discoverable.rs:104-112` |
| 記錄 | 每次顯示都記時間；直接關掉視同延後 7 天 | 補 VS Code「按 X 不記」的漏洞 |

### 5.8 「有更好的選擇」與「只留有用的」通知

- 觸發條件：
  - 名冊把某槽位的預設換掉，而使用者裝的是舊的；
  - 卡片有 `replaces`；
  - 同一槽位的試用工具在使用者情境的實測勝出；
  - 跨 agent 的「沒在用」（14 天而且 10 個 session）。
- 內容：舊工具 → 新工具；實測差異與證據檔；影響哪些 agent；切換會改哪些檔；還原方式。
- 送達：SessionStart 的一行 `systemMessage`，每週最多 1 次；細節進週報。Claude Code 已經會標「Not used recently」，OmniKit 不重複提同一件事，改補「另外兩個 agent 也沒在用」與「可以換成什麼」。

### 5.9 隱私與安全

- 所有比對都在本機做；狀態檔只存工具 id、次數與時間（照 usage.py 的原則）。
- 不把 transcript 文字送出去。ECC 列為要揭露的「把對話送外部 LLM」，OmniKit 不做。
- 外部搜尋只送抽象的關鍵字，不含專案名稱與路徑，而且預設關閉。設了 `DISABLE_TELEMETRY=1`，搜尋 API 本身還是會收到查詢字串（`find.ts:90`；`telemetry.ts:75-77`）。
- 從建議發起的安裝，一律走同一條預覽與確認的流程。Claude Code 也是「永遠不自動安裝，一定由使用者確認」（`relevance.md:39`）。
- Codex 的 hook 用 config.toml 註冊、指令字串固定（§5.6）。

### 5.10 怎麼證明它有用

- 在本機記錄每則建議的顯示、接受、拒絕與沒回應，列進週報。
- 某條訊號規則顯示 10 次以上都沒人接受，就自動停用，並在週報說明原因。aitmpl 用使用數據刪掉沒人用的旗標（`CHANGELOG.md:23-28`）；OmniKit 等於把「只留有用的」用在自己身上。
- 這台電腦上，Codex 的 50 則下一步任務建議全部停在 `pending` [推論：沒被處理的主動建議很常見]。所以主動建議的預設值要保守。

---

## 6. 各家缺點與 OmniKit 的補法

| 工具 | 缺點 | OmniKit 補法 |
|---|---|---|
| ECC | 只裝自家；v2 只剩範圍與 hook 兩題，不依需求挑內容；沒有主動通知 | 依槽位組工具包；週報加 SessionStart 通知 |
| setup-claude | 只支援 Claude、只看角色與目錄；沒有驗證、沒有更新 | 三個 agent；實測證據；驗證與週報 |
| find-skills 與 npx skills | 依安裝數與星數；建議 agent 用 `-g -y` 跳過確認；查詢字串外送；遙測預設開 | 實測優先；一律預覽與確認；本機優先；外部搜尋預設關 |
| Codex skill-installer | 只列清單，沒有推薦；目的地已存在就中止，沒有更新 | 名冊推薦；鎖定檔與更新 |
| Codex tool_suggest | 只在明確要求時才建議；候選窄；TUI 不支援；要 ChatGPT 登入 | 第 1 層被動建議；寫 `discoverables` 接上原生流程 |
| Tessl | eval 由作者出；遙測可能含程式碼；CLI 不開源；相依配對已撤 | 用使用者情境；本機；對應到槽位 |
| aitmpl | 只支援 Claude Code；不釘版本、沒有安裝紀錄；偵測與 health check 有 bug；遙測預設開 | 釘版本並留紀錄；偵測器自我測試；遙測預設關 |
| BMAD | 不偵測 agent 與專案；只推自家；更新通知只在跑安裝器時看得到；新裝沒有寫入總覽 | 掃描後預選；SessionStart 通知；預覽列出寫入位置 |
| SuperClaude | 現版一題不問就全裝；doctor 失準；金鑰會外洩；README 與實作不一致 | 預覽、真的驗證、只記環境變數名稱 |
| Claude Code | 依目錄推薦；只看單一 agent；relevance 要管理員；只說沒在用，不說換什麼 | 跨 agent；有實測才建議替換；不需要管理員 |
| VS Code 與 JetBrains | 按 X 關掉不記錄，可能重複跳出［子研究推論］ | 每次顯示都記，關掉視同延後 |

---

## 7. 要避開的坑

1. **用熱門度當主要排序**（find-skills、aitmpl、stackskills）：安裝數高不等於在你的工作上有用。
2. **依函式庫相依自動配對**（Tessl 已撤；aitmpl 的偵測有 bug）：雜訊大、維護成本高。要做也只對應到槽位。
3. **讓 LLM 手動複製檔案**（ECC v1；v2 已改掉）：結果不可重現，也無法驗證。
4. **預設開遙測、搜尋字串外送**（aitmpl、skills.sh、Tessl 的 `shareUsageData`）：公司電腦尤其不行。
5. **金鑰外洩**（SuperClaude 的 dry-run 印出金鑰、`setx`、明文還原檔）。
6. **假的 doctor**（SuperClaude、aitmpl）：比沒有更糟，會讓人誤以為裝好了。
7. **沒有安裝紀錄**（aitmpl）：之後無法更新、也無法移除。
8. **題目太少或太多**：SuperClaude v4.3 一題都不問就全裝；ECC v1 有 6 步以上的多選與逐項確認。
9. **主動建議太積極**：Codex 已收緊到只在明確要求時建議；Claude Code 移除了啟動時的 JetBrains 建議，也替 frontend-design 提示加了上限、修了誤判。
10. **不釘版本**（aitmpl 從 main 下載、SuperClaude 用沒鎖版本的 `npx -y`）：再加上防毒，失敗率會很高。
11. **建議和安裝流程脫鉤**（Kiro、Docker 一鍵加入；find-skills 的 `-y`）：建議卡一按就裝，沒有預覽。
12. **在非互動環境卡在等輸入**（ECC 與 Vercel 都特別處理了）：agent 的 shell 不是 TTY。
13. **Stop hook 用 `additionalContext`**：會讓 Claude Code 繼續跑，變成迴圈。
14. **把 hook 做成 Codex plugin**：每次更新都要重新信任。
15. **Windows 長路徑與 symlink**：clone 或安裝會失敗，或者需要管理員權限。

---

## 8. 還不確定的地方，以及怎麼驗證

| 項目 | 現況 | 建議驗證 |
|---|---|---|
| Antigravity 的 SessionStart `injectSteps` 使用者看不看得到 | 文件沒定義給使用者看的欄位；本機二進位有相關字串 | 在這台寫一個只印固定字串的 `~/.gemini/config/hooks.json`，分別在 App、IDE、CLI 開新 session 觀察 |
| Antigravity 的 hook 信任與 plugin hook 只能觀察的說法 | 文件沒寫；第三方說法 | 同上，再用 CLI 的 `/hooks` 確認 |
| Codex 寫 `tool_suggest.discoverables` 後原生流程會不會觸發 | 原始碼支援；TUI 回傳不支援 | 在 Codex 桌面版明確要求某個名冊 plugin |
| Claude Code 經 HKCU 開 `pluginSuggestionMarketplaces` | 文件說只有在沒有管理員文件時才採用 | 先確認公司政策；寫 HKCU 屬於修改設定，要先問使用者，而且它會變成 managed 層級 |
| Claude Code 的 SuggestPluginInstall 內部規則 | 只有工具定義摘要；文件沒寫 | 不依賴它 |
| skills.sh 的搜尋排序、Codex 推薦清單的伺服器邏輯 | 都在伺服器端，看不到 | 只當外部訊號 |
| Tessl 的多數主張 | CLI 不開源，只能看文件 | 需要時用 npm 套件或實際執行驗證（要你同意） |
| 子研究的證據 | 主線抽查 3 項相符，其餘沒有逐一複核 | 要引用到規格前，先重讀對應的 file:line |
| 痛點訊號的準確度 | 沒有資料 | 先在你這台跑兩週，只記錄不顯示，算誤報率再開 |
| Codex ambient suggestions 都是 pending 代表什麼 | 可能是預設狀態，處理過的也可能被移除 | 不當成量化依據 |

---

## 附錄 A：證據檔位置

- 研究用的 clone：`C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\research\recommend\`
  - 主線：`ecc\`、`ecc-v1.10.0\configure-ecc-v1.10.0.SKILL.md`、`ecc-v1.10.0\configure-ecc-v2.0.0.SKILL.md`、`vercel-skills\`、`claude-code\`、`openai-skills\`、`codex\`（稀疏）、`cc-docs\*.md`（Claude Code 官方文件快照與 llms.txt）
  - 子研究：`bmad-method\`、`bmad-method-v6.12.4\`、`superclaude\`、`superclaude-v4.0.9\`、`superclaude-v4.1.9\`、`claude-code-templates\`、`tessl-cli-npm-0.119.0\`、`tessl-docs\llms-full.txt`、`vscode\`、`intellij-community\`、`cline\`、`callstack-agent-skills\`
- setup-claude：`C:\Users\user\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\local-agent-mode-sessions\skills-plugin\486f4ee9-76f7-4c07-b90d-afdbe6ce5648\8b609bb3-7391-4bb3-a985-068e315ff916\skills\setup-claude\SKILL.md`
- Codex 本機：`C:\Users\user\.codex\skills\.system\skill-installer\`、`C:\Users\user\.codex\cache\remote_plugin_catalog\`、`C:\Users\user\.codex\ambient-suggestions\`（只讀結構與統計，沒有讀 `auth.json`）
- Antigravity 本機：`C:\Users\user\AppData\Local\Programs\antigravity\resources\bin\language_server.exe`（只做字串計數）
- OmniKit（只讀）：`docs/proposals/2026-11-05-positioning.md`、`engine/skills/omnikit-setup/SKILL.md`、`engine/scripts/scan.py`、`engine/scripts/install.ps1`、`engine/scripts/agents.py`、`engine/scripts/usage.py`、`engine/scripts/session_nudge.py`、`engine/scripts/codex_hooks.py`、`engine/schema/tool.schema.json`、`data/slots.yaml`、`data/omnikit.yaml`、`data/tools/chrome-devtools-mcp.yaml`、`engine/skills/omnikit-eval/SKILL.md`
- 線上來源：
  - https://code.claude.com/docs/en/plugins/install.md
  - https://code.claude.com/docs/en/plugins/relevance.md
  - https://code.claude.com/docs/en/plugins/cli-hints.md
  - https://code.claude.com/docs/en/plugins/code-intelligence.md
  - https://code.claude.com/docs/en/plugins/measure.md
  - https://code.claude.com/docs/en/plugin-evals.md
  - https://code.claude.com/docs/en/hooks.md
  - https://code.claude.com/docs/en/memory.md
  - https://code.claude.com/docs/en/commands.md
  - https://code.claude.com/docs/en/managed-settings.md
  - https://antigravity.google/docs/hooks
  - 子研究使用的 Tessl、Docker、Goose、Kiro、llm-checker、llmfit 等網址，見各節
