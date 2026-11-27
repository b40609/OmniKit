# 使用指南

[← 回到首頁](../README.md) · [安裝說明](install.md) · [子任務分派](dispatch.md) · [運作方式](architecture.md) · [維護名冊](maintainer.md)

- [裝好之後會有什麼](#裝好之後會有什麼)
- [確認接上了](#確認接上了)
- [安裝前後差在哪](#安裝前後差在哪)
- [建立自己的 profile](#建立自己的-profile)
- [日常使用](#日常使用)：換 profile、簡短指令、評估新工具、診斷與小提示
- [常見問題](#常見問題)

## 裝好之後會有什麼

安裝不會在 Claude Code、Codex 或 Antigravity 的畫面上多出按鈕或面板。改變的是 agent 開 session 時讀到的規則，以及多了六個核心 skill（`omnikit-setup`、`omnikit-handoff`、`omnikit-dispatch`、`omnikit-research`、`omnikit-capabilities`、`omnikit-eval`，搭配唯一的 `/ok` 簡短總入口；訪談選了不評估新工具的沒有 `omnikit-eval`）、一個按需讀取的前端底線 skill（`omnikit-mobile-web`）、一個 MCP。**已經開著的 session 不會重讀，要開新的 session 才生效。**

**第一次開新對話會主動帶你設定**：還沒建立自己的 profile 時，開新對話隨便打一句（例如「嗨」），agent 會先打招呼、直接開始 1 分鐘的設定訪談；第一句是具體工作的話，它先做完，最後提一句可以設定。設定完會給一段新手導覽（背後已經在做的事、現在就能試的 3 句話）。說「先不要」會暫緩 7 天，期間開新對話不再主動提，到期自動恢復；說「不要再提醒」會改用預設 profile，之後不再問。三家都有（寫在規則裡，不靠 hook；暫緩到期後，Claude Code 開新對話時會在背景把它接回來，只用 Codex 或 Antigravity 的電腦要等下次更新或同步）。讓 agent 幫你安裝的話，它裝完會在同一段對話直接接著訪談，不用另外開對話。

設定完開新的 session 試試看：

```text
OmniKit 規則版本與 profile 是什麼？
幫我設定 OmniKit
/ok
幫我評估 https://github.com/<owner>/<repo>
用瀏覽器打開 http://localhost:3000，看 console 有沒有錯誤
```

需求還沒想清楚想先對焦，直接用內建 `/plan`（Antigravity 亦可用 `/grill-me`），三家內建指令對照見 [cli-features.md](cli-features.md)。

## 確認接上了

| 檢查 | Claude Code | Codex | Antigravity |
|---|---|---|---|
| 規則 | 問「OmniKit 規則版本與 profile 是什麼？」，版本跟 `data/rules/baseline.md` 開頭的「規則版本」一樣，profile 是你選的 | 同左 | 同左 |
| skill | 輸入 `/omnikit` 或 `/ok`，選單裡會出現 `omnikit-setup`、`omnikit-handoff` 等（訪談選了不評估新工具的，沒有 `omnikit-eval`） | 輸入 `$omnikit` 或 `$ok`，或用 `/skills` 列出來 | 問「你可用的 skill 有哪些？」，會列出這幾個 |
| MCP | 終端機跑 `uv run engine/scripts/doctor.py`（或 `claude plugin list` 確認 `omnikit@omnikit-local` 已啟用） | 終端機跑 `codex mcp list`，`chrome_devtools` 是 enabled | 終端機跑 `agy mcp list`，`chrome_devtools` 是 enabled |

終端機跑 `uv run engine/scripts/sync.py status`，可以看到這台接上了哪些 agent 與無帳本對帳狀態。

逐項檢查跑 `uv run engine/scripts/doctor.py`：規則區塊、skills、MCP、權限規則與 hook 都還在、跟寫入時一樣，這台每個 agent 設定目錄（多帳號、T3 Code 的實例）都接上了，並對護欄 hook 做三方言端到端自測；查不到的標「未知」，不算通過。加 `--preflight` 一併跑安裝前檢查。

## 安裝前後差在哪

| 項目 | 會有什麼不同 | 三個 agent 的差別 |
|---|---|---|
| 規則（`data/rules/baseline.md` + `data/rules/dispatch.md` + profile 的 `AGENTS.md`） | 安全底線與分派原則所有人都一樣；回覆用什麼語言、寫多詳細、哪些事可以直接做，照你選的 profile。`default` 是繁體中文、下載安裝前先問。完整分派政策在 `dispatch-policy.md`、個人帳號對應在 `dispatch.md`、行動端前端底線在 `omnikit-mobile-web` skill，都不常駐載入，需要時才讀 | Claude Code 直接 import 來源檔，改完開新 session 就生效；Codex 讀合併後的 `~/.codex/AGENTS.md` 受管區塊（<= 32 KiB）；Antigravity 拆成 `~/.gemini/AGENTS.md`（共用層）與 `~/.gemini/GEMINI.md`（個人層），單檔限制 <= 24,000 bytes 避免靜默截斷。改了 profile 跑 `uv run engine/scripts/profiles.py` 重新接上（維護者版 commit 時 git hook 自動同步） |
| `ok` 總入口 | 唯一簡短手動入口：不知用哪個就打 `/ok`（Codex 打 `$ok`），後面可直接講白話或選 1 到 5 號主選單（交接、調研、分派、設定、清點） | Claude Code 與 Antigravity 輸入 `/ok`（如 `/ok 交接`），Codex 輸入 `$ok` |
| `omnikit-setup` skill | 說「幫我設定 OmniKit」，agent 先掃描這台的環境，再問最多 6 題，產生你自己的 profile 並接上。見[建立自己的 profile](#建立自己的-profile) | 三邊說「幫我設定 OmniKit」都會觸發；要手動叫，Claude Code 輸入 `/omnikit-setup` 或 `/ok 設定`，Codex 輸入 `$omnikit-setup` 或 `$ok 設定` |
| `omnikit-handoff` skill | 說「交接」，agent 把做到一半的工作 commit、push，寫一份交接檔到你的狀態 repo，再開新對話接著做；新對話說「讀 <交接檔路徑> 接著做」就照交接檔接手。狀態 repo 的位置寫在你的 profile，沒寫 agent 會先問 | 三邊說「交接」都會觸發；要手動叫，Claude Code 輸入 `/omnikit-handoff` 或 `/ok 交接`，Codex 輸入 `$omnikit-handoff` 或 `$ok 交接` |
| `omnikit-dispatch` skill | 派子任務、開子對話時照分派政策選模型與思考程度，收完結果後記一行委派紀錄（存在這台，不上傳）；也能看 Sonnet 試行的比較與本週 Claude 用量。見[子任務分派](dispatch.md) | 三邊說「委派紀錄」「分派統計」都會觸發；要手動叫，Claude Code 輸入 `/omnikit-dispatch` 或 `/ok 分派`，Codex 輸入 `$omnikit-dispatch` 或 `$ok 分派`。本週用量的快照只有 Claude Code 的狀態列存得到 |
| `omnikit-research` skill | 說「先查業界做法」「找同類工具」「比較方案」，agent 每個管道都查（網頁中英文、GitHub topic 與星數、fork 與競品、skill／MCP 目錄、Hacker News、Product Hunt），關鍵字從結果擴展，連續 3 組沒有新名字才停（長尾題目改看 ★1,000 以上的名字，標「長尾未飽和」；12 組還沒停先回報）；報告附查了哪些管道與關鍵字、第幾組停、哪裡查不到，星數與授權用 `gh api` 實測並寫日期。安全底線有一行要求調研照這個 skill 做 | 三邊說「找同類工具」「調研」都會觸發；要手動叫，Claude Code 輸入 `/omnikit-research` 或 `/ok 調研`，Codex 輸入 `$omnikit-research` 或 `$ok 調研`。GitHub 的管道要先 `gh auth login` |
| `omnikit-capabilities` skill | agent 要說「做不到」「沒有工具」「請你手動做」之前，先清點這台能用的 CLI（標出 Git Bash 找不到、只有 PowerShell 找得到的，例如只有 `t3.cmd` 的 T3）、各 agent 登記的 MCP server、本機 MCP 端點（開著沒、要不要登入、哪個 agent 還沒接），列出最省事的做法，再對照 `--help` 與最新官方文件。只看檔案、PATH 與本機連線，不印金鑰。安全底線的「說做不到之前」要求先照這個 skill 查完 | 三邊要說做不到、或使用者問「你能不能…」「有沒有辦法派給…」時觸發；要手動叫，Claude Code 輸入 `/omnikit-capabilities`，Codex 輸入 `$omnikit-capabilities`。也能直接跑 `uv run engine/scripts/capabilities.py` |
| `omnikit-eval` skill | 貼 GitHub 連結說「幫我評估」，agent 會查 GitHub 現況、對照槽位情境，寫成 `data/tools/` 裡的工具卡；「每週彙整」是維護者評估工具用的 | 三邊說「幫我評估」都會觸發；要手動叫，Claude Code 輸入 `/omnikit-eval` 或 `/ok 評估`，Codex 輸入 `$omnikit-eval` 或 `$ok 評估`。三邊皆透過無複製參照指向 `~/.omnikit/current/engine/skills`（維護者版 commit 時由 git hook 自動更新，同事版重跑 `install.ps1`） |
| `chrome_devtools` MCP | agent 能自己開瀏覽器：開網頁、截圖、看 console 與網路請求。每次用暫時的瀏覽器設定檔，碰不到你的登入狀態 | Claude Code 由薄 plugin 掛載並可加進免問清單，Codex 設成自動核准（同事版皆需本人同意），Antigravity 由薄 plugin 掛載並照它自己的權限設定 |
| 護欄與提醒 hooks | 包含確定性護欄（`harness_hooks.py`，擋常見繞過捷徑與敏感檔讀取，不是沙箱）、開新對話提醒（`session_nudge.py`，含每日最多一則用法小提示）、說做不到查證（`claim_check.py`，未附查證擋回一次；設 `OMNIKIT_CLAIM_CHECK=off` 可暫關）、完工宣稱檢查（`done_check.py`，【完成待收尾】或寫 `.done` 時檢查完工回執、證據檔與 git 是否已 push；預設只記錄到 `tripwire-hits.jsonl`，設 `OMNIKIT_DONE_CHECK=block` 才擋、`off` 關掉）、設定目錄檢查（`home_watch.py`）與 T3 MCP 斷線防護（`t3_watch.py`） | Claude Code 透過本地薄 plugin `omnikit@omnikit-local` 掛載（所有 Claude 設定目錄皆接）；Codex 只接開新對話提醒、說做不到查證、完工宣稱檢查與 T3 MCP 斷線防護，寫進 `config.toml`（需在 `/hooks` 信任才會跑），確定性護欄目前沒有接 Codex；Antigravity 於薄 plugin `config/plugins/omnikit/hooks.json` 掛載確定性護欄與完工宣稱檢查 |
| git hooks（只有維護者版） | 只作用在 OmniKit repo：commit 前掃金鑰、驗證名冊；commit 或 pull 動到規則、profile、MCP、權限時自動同步。同事版不設 | 跟 agent 無關 |

## 建立自己的 profile

還沒選過 profile 的電腦，開新對話時 agent 會主動開始；之後想重新設定，在新的 session 說「幫我設定 OmniKit」。`omnikit-setup` 會：

1. **掃描**：列出這台裝了哪些 agent、目前的規則、skills 與 MCP（只看名稱與版本，不讀金鑰）；另外依你現在的專案資料夾裡的檔名（只看檔名），預選第 1 題的領域。
2. **訪談**：最多 6 題，大多是選擇題：做哪幾種工作（領域，可複選）、最想改善的習慣、回覆的語言與詳略、agent 可以自己做到哪、要不要評估新工具、主要專案。
3. **預覽**：先給你看產生的規則，同意才寫入。
4. **建立並套用**：寫進 repo 外的 `~/.omnikit/profiles/<名稱>/`，接上這台接好的 agent，開新 session 生效；接著給一段新手導覽（背後已經在做的事、依你的答案挑的 3 句可以馬上試的話）。

| 你選的 | 規則裡寫成 |
|---|---|
| 做哪幾種工作（領域） | 不寫進規則，存成 `domains.yaml`，記錄你選的領域、它們帶入的能力（例如軟體開發會帶入瀏覽器），以及每個人都有的基礎模組。之後想改，重新訪談或直接改這個檔；刪掉這個檔就是不限領域 |
| agent 可以自己做到哪 | 每步先問：改檔案、執行指令前先列計畫等你同意。專案內直接做（建議）：下載安裝、改專案以外的才先問。大多放手：下載安裝也直接做 |
| 最想改善的習慣 | 例如「常改太多」變成「只改需求相關的地方，其他想改的先列出來問你」 |
| 要評估新工具 | 情境範本裡的 `<你的專案>` 換成你的專案，評估工具時拿來當考題 |
| 不評估新工具 | 不裝 `omnikit-eval`（評估工具與維護者的每週彙整都在這個 skill 裡）；已經裝了的會拿掉。之後改主意，重新訪談選「要」就會裝回來 |

規則檔與情境檔都由 `engine/scripts/profile_new.py` 依固定範本產生、驗證，agent 只負責問問題；寫入後可以直接改，改完跑 `uv run engine/scripts/profiles.py` 重新接上。重新訪談時會帶入上次的答案，舊檔先備份成 `.bak`；手寫的 profile 與 repo 裡已經有的名稱不會被覆蓋。安全底線不能從 profile 放寬。

profile 存在 repo 外的 `~/.omnikit/profiles/<名稱>/`（`AGENTS.md`、`scenarios.yaml`、`domains.yaml`，以及下次訪談預填用的 `answers.json`），不會被 commit、push 或上傳，在 repo 裡跑 `git status` 也看不到。舊版存在 repo 裡（`data/profiles/<名稱>/`）的，重跑 `install.ps1` 或說「幫我設定 OmniKit」時會問你要不要搬過去；搬好、確認內容一樣才刪 repo 裡的舊檔，不同意就不動。

子任務要派給別的模型或帳號，另外在同一個資料夾放 `dispatch.md`，見[子任務分派](dispatch.md#設定自己的帳號對應)。

## 日常使用

### 換 profile

```powershell
uv run engine/scripts/profiles.py --show          # 這台現在用哪個
uv run engine/scripts/profiles.py --set <名稱>    # 換成這個 profile，接上的 agent 一起換
uv run engine/scripts/profiles.py --migrate       # 舊版存在 repo 裡的 profile 搬到 repo 外（先問你）
```

找 profile 時先找 repo 外的 `~/.omnikit/profiles/<名稱>`，再找 repo 裡的 `data/profiles/<名稱>`。換完開新的 session 才生效。skills 也會跟著同步：換到訪談選了不評估新工具的 profile，`omnikit-eval` 會拿掉，換回來再裝上。還沒選過的電腦會一直用 `default`，並在安裝與同步時提醒。想重新訪談、改掉原本的答案，說「幫我設定 OmniKit」就好。

### 簡短總入口（`/ok` / `$ok`）

不想記完整 skill 名稱時，直接打唯一總入口 `/ok`（Claude Code、Antigravity）或 `$ok`（Codex），後面可以直接講白話，或留空列出 1 到 5 號主選單：

| 指令（Claude／Antigravity；Codex 改用 `$`） | 對應 skill |
|---|---|
| `/ok` | 列出主選單，回編號執行 |
| `/ok 交接`（或 `/ok handoff`） | `omnikit-handoff`（交接、接手與更新 `NOW.md`） |
| `/ok 調研`（或 `/ok research`） | `omnikit-research`（飽和式調研） |
| `/ok 分派`（或 `/ok dispatch`） | `omnikit-dispatch`（子任務分派與委派紀錄） |
| `/ok 設定`（或 `/ok setup`） | `omnikit-setup`（訪談建立個人 profile） |
| `/ok 評估`（或 `/ok eval`） | `omnikit-eval`（評估新工具；選不評估時不裝） |
| `/ok <白話需求>` | 依語意對應最接近的一項，拿不準列主選單並提示 `/plan`、`/grill-me` |

### 評估新工具

在 Claude Code、Codex 或 Antigravity 裡直接說（訪談選了評估新工具才有；「每週彙整」是維護者看評估額度與評估漏斗用的）：

```text
幫我評估 https://github.com/<owner>/<repo>
這個跟現在用的比一下
每週彙整
```

| 層 | 成本 | 做什麼 |
|---|---|---|
| 0 | 免費 | GitHub 現況、名冊比對、硬性門檻、安全掃描 |
| 1 | 便宜 | 讀 README，對照槽位情境寫卡片，狀態是「待評估」 |
| 2 | 實測 | 拿槽位情境實際跑一遍並評分，點名才跑；紀錄放在 `data/evals/` |

### 診斷、小提示與已停用項目

- **健康檢查**：`uv run engine/scripts/doctor.py` 全面檢查；`uv run engine/scripts/sync.py sync --check` 純唯讀對帳，有差異回傳 exit 1。細節見[運作方式的無帳本對帳](architecture.md#無帳本對帳與檢查)。
- **用法小提示**：主線對話第一回合結束時由 `session_nudge.py` 呼叫 `engine/scripts/tips.py`（內容在 `data/tips.json`）講一則官方功能小提示，一天最多一則、每則只講一次；Claude Code 第一次 `git push` 時若 `/insights` 超過 14 天沒跑會提醒一次。設環境變數 `OMNIKIT_NO_NOTIFY` 可關閉。
- **系統檢查與起步清單**：原週報、建議、替換、回流、訊號與對話掃描等舊腳本已於 `6359488` 移除，原問法庫 `omnikit-ask` 已於 `87bbb81` 退役刪除（改用各家內建 `/plan` 或 `/grill-me`）。檢查工具用量與使用習慣請改用官方 `/doctor`、`/usage`、`/insights`，三家內建功能對照見 [cli-features.md](cli-features.md)，新電腦該裝什麼看 [starter.md](starter.md)。

## 常見問題

<details>
<summary><b>裝好了，卻看不出有什麼不同？</b></summary>

安裝改的是規則、skill 與 MCP，畫面上不會多出東西，而且要開新的 session 才生效。照[確認接上了](#確認接上了)檢查一遍。預設 plugin 不會自動安裝，見[預設 plugin 要另外裝](install.md#預設-plugin-要另外裝)。

</details>

<details>
<summary><b>不想用某個預設工具怎麼辦？</b></summary>

把那張卡（`data/tools/<id>.yaml`）的 `status` 改掉並 commit，marketplace 與看板會跟著更新。已經裝好的 plugin 要自己移除。

</details>

<details>
<summary><b>Antigravity 看不到 OmniKit 的 skill？</b></summary>

Antigravity 的全域 skill 不跟隨資料夾連結，因此 OmniKit 改透過 `~/.gemini/config/skills.json` 原生參照實體 skills 目錄（T3 Code 也會自動同步到所有 Antigravity 實例）。更新 OmniKit 後跑一次 `uv run engine/scripts/sync.py sync`（維護者版 commit 或 pull 時 git hook 會自動跑，同事版重跑 `install.ps1`）就會補齊並清掉舊版複製品。

</details>
