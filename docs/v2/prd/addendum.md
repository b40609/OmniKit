# PRD 附錄：實作方式與沒採用的方案

PRD 只寫能力，怎麼做寫在這裡。研究依據在 `docs/v2/research.md`，完整證據在 `docs/v2/research/`。

## A. 實作方式

### A.1 計畫、帳本與受管區塊（FR-7、FR-10）

- **計畫**：
  - `agents.py` 加 `plan` 指令，輸出有版本號的 JSON。每一項記錄 agent、檔案、key 或區塊、動作、理由、來源槽位與工具卡。
  - `install.ps1 -WhatIf`、omnikit-setup 的預覽、實際安裝與移除，都讀這份計畫。
  - 計畫附 revision。revision 只算受管項目（MCP entry、受管區塊、skill 複製品）的雜湊，不算整個檔案，因為 `~/.claude.json` 這類檔案 agent 自己會持續寫入。安裝時不一致就要求重新預覽。
  - 衝突在產生計畫時就檢查（preflight），有衝突整份不執行；執行時的個別失敗不中斷其他項目。
  - 檢查模式：`--check`，有差異就 exit 1。
  - 參考：rulesync `generate-plan.ts`、skillshare `write.go`（`research/sync.md` §5.1）。
- **同事版不設 git hook**（FR-1、FR-36）：
  - 現況是 `install.ps1` 設定 `core.hooksPath`，pull 之後 `.githooks/post-merge` 會呼叫 `sync-data.sh`，直接重新套用規則、MCP、skills、權限與 hook。
  - 這適合維護者自己的電腦；同事版改成「檢查更新」：fetch 之後產生計畫的差異，預覽、同意後才套用。
- **個人資料的位置**（FR-38）：同事的 profile、answers.json、scenarios.yaml 改存在 `%LOCALAPPDATA%\omnikit\profiles\`，或至少列進 `.gitignore`。`[ASSUMPTION]`
- **免問核准**（FR-10）：
  - 現況是 `data/harness/claude-allow.txt` 的 `mcp__chrome_devtools`，以及 `data/mcp/servers.yaml` 的 `default_tools_approval_mode: approve`，都依維護者 2026-11-04 的同意寫給所有人。
  - 改成由個人的計畫產生，每個人在預覽中自己同意。
- **帳本**：
  - 擴充 `agents.json`，記錄每個 MCP entry、規則區塊與 skill 複製品寫入時的雜湊。
  - 同步時分成五類：新增、更新、移除、接手（同名而且內容完全一樣）、衝突。有衝突就整批不寫（`research/sync.md` §5.2）。
- **受管區塊**：
  - Codex 改成跟 GEMINI.md 一樣，放在開頭；開始標記帶內容雜湊。
  - 偵測到 `~/.codex/AGENTS.override.md` 時提出警告。
  - 現況的缺陷：`profiles.py:189-203` 整份換掉；`agents.py:380-388` 不同就覆寫。

### A.2 掃描（FR-2、FR-3）

- **環境**：
  - 擴充 `scan.py` 現有的 TOOLS。
  - VRAM 用 `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader`。不要用 `Win32_VideoController.AdapterRAM`，它是 32 位元，超過 4GB 會讀錯。
  - 防毒產品從 `root/SecurityCenter2` 的 `AntiVirusProduct` 讀取。
- **專案**：
  - 候選專案取自 `~/.claude/projects`、Codex `config.toml` 的 `[projects]`、`~/.gemini/projects.json`。
  - 偵測器寫成純函式，附 fixture 自我測試。
  - 訊號格式沿用 Claude Code relevance 的 `cwd`、`cli`、`hosts`、`filesRead`、`manifestDeps`，再加上 `files` 與 `pains`。
  - 參考：`research/recommend.md` §4.2、§4.3。

### A.3 安裝與驗證（FR-9、FR-11）

| agent | 安裝 plugin | 驗證 |
|---|---|---|
| Claude Code | `claude plugin install <name>@<marketplace> --scope user` | `claude plugin list --json` |
| Codex | `codex plugin add <name>@<marketplace> --json` | `codex plugin list --json` |
| Antigravity | 照現有 `agents.py`，用複製的方式放 skill | 檢查 `agents.py` 實際寫入的 `~/.agents/skills`（`agents.py:16、93-95`），並實測 `agy` 讀取的位置（研究指出 Antigravity CLI 的全域 skills 在 `~/.gemini/antigravity-cli/skills`） |

- **OmniKit 自己的 skills 與全域 MCP**：沿用 `agents.py`。它已經有擁有權判斷、`tree_hash` 與安裝紀錄。
- **第三方工具卡的 skill 與 MCP**（FR-9）：`agents.py` 目前只會裝 `engine/skills` 與 `data/mcp/servers.yaml`（`agents.py:322-324、359-367`），所以要新增一個依工具卡 `install` 欄位安裝的元件，並沿用同一套擁有權判斷與帳本。
- **marketplace**：目前只收狀態是預設、而且有 plugin 來源的卡；整個名冊只有 3 張卡有釘選來源（`build.py:14、67-68`）。補內容的階段要一併補上 `install` 欄位。
- 子行程不用 `shell=True`；npx 透過 `cmd /c` 執行；執行期間不跑沒釘版本的 `npx -y`。

### A.4 停用（FR-15）

| agent | 停用方式 |
|---|---|
| Codex 一般 plugin | `[plugins."x@y"] enabled = false` |
| Codex 跟帳號同步的 plugin | `[[skills.config]] name = "plugin:skill"`、`enabled = false`。`[plugins]` 對這類 plugin 無效（2026-11-04 實測） |
| Claude Code | plugin disable |
| Antigravity | 移除 OmniKit 放的複製品 |

### A.5 主動建議的 hook（FR-18、FR-19）

| agent | 事件 | 給使用者看的訊息 | 注意 |
|---|---|---|---|
| Claude Code | Stop、SessionStart | `systemMessage` | Stop 不要用 `additionalContext`，它會讓對話繼續跑；Stop 時用 `last_assistant_message` 判斷最後一則回覆 |
| Codex | Stop、SessionStart | `systemMessage` | hook 的信任綁在指令字串上。維護者的電腦可以用固定字串，例如 `uv run --script <OmniKit>/engine/scripts/omnikit_hook.py stop`。同事版要在指令裡帶腳本內容的雜湊（例如 `... stop --sha <前 12 碼>`），腳本一改字串就變，Codex 會要求重新信任（FR-39）。不要做成 plugin hook |
| Antigravity | SessionStart、Stop 等 | 文件沒有定義 | 第一階段不用 |

- 擴充 `session_nudge.py`（它已經會讀 Claude Code 與 Codex 的對話紀錄）。
- 只讀新增的紀錄：rollout 可能有上百 MB，要記住上次讀到的位置。
- 狀態檔只存工具 id、次數與時間。
- 參考：`research/recommend.md` §5.4 到 §5.7。

### A.6 評估漏斗（FR-22 到 FR-27）

- **健康與採用度指標**：H1 到 H7、A1 到 A4 的定義見 `research/eval.md` §4.3。
  - 改用 `gh` 或 `GITHUB_TOKEN` 環境變數，避開未登入每小時 60 次的上限。
  - stargazers 清單從 2026-06-30 起不再對外開放；事件 API 也只回最近 300 筆事件。所以星數成長速度改成由 OmniKit 每週記錄星數快照來計算，前兩週只算得出總數，還不能判斷爆紅。
- **隔離環境**（FR-24）：獨立的使用者設定資料夾與 worktree。需要 shell 權限的套件，在 Windows Sandbox（這台的 `C:\Windows\System32\WindowsSandbox.exe` 存在）或 WSL2 裡跑，要實測哪一種可行。
- **cp950 測試**（FR-34）：GitHub 的 windows-latest 是英文系統語系，CI 裡沒辦法改；改用程式模擬 cp950 的輸出與檔名，真實環境在試點同事的電腦上確認。
- **第 2 層**：
  - Claude 端可以用 `claude plugin eval`：給 shell 權限的套件要在 WSL2 跑，並用 `--max-cost-usd` 設上限（未實測）。
  - Codex 端用 `codex exec`。
- **誤判率**（`research/eval.md` §6，模擬，偏樂觀）：兩個一樣好的工具，「總分高就算贏」跑 3 次有 41% 會誤判挑戰者勝出；改成「平均每次多 1 個檢查點才算贏」降到 13%。

### A.7 工具卡欄位（FR-28）

新增 `signals`、`requires`、`blocked_on`、`install`、`verify`、`try`、`cost`、`capabilities`、`replaced_by`。

- `cost` 由 `build.py` 計算。
- `replaced_by` 由 `replaces` 反推。
- 其他欄位在評估時填寫。

參考：`research/recommend.md` §4.11。

## B. 考慮過但沒有採用的方案

| 方案 | 為什麼不採用 |
|---|---|
| 讓模型在對話中搜尋目錄並建議（Claude Code 的 SearchPlugins 做法） | 花 token、佔 context；依據是目錄而不是實測；不能跨 agent 共用頻率規則 |
| 用 HKCU 打開 Claude Code 原生的情境建議 | 寫進去就成為 managed 層級，公司有派政策時也會被忽略；先列為選配 |
| 依相依套件自動配對（例如 pandas 就裝 pandas 的 skill） | Tessl CLI 0.76.0 已撤掉這個功能；OmniKit 名冊收的是工作流程工具，不是函式庫文件 |
| 依熱門度排序推薦 | 名冊 50 個 repo 星數中位數 31,000，沒有鑑別力；而且有灌星問題 |
| 手工維護工具包清單 | 使用者決定不手工維護；從名冊即時組出，名冊一改就跟著變 |
| 對 Antigravity 用連結 | 它讀不到連結；skills CLI #633、skillshare #255 都證實 |
| 拿 RIA 整包對 BMAD | 範圍不對等；RIA 仍是原型（`docs/v2/research.md` §9） |
| ECC v1 的逐項多選 | ECC 自己在 v2 已改成 2 題 |
