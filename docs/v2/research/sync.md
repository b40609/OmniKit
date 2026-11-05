# 一份設定接多個 coding agent：同類工具研究與 OmniKit v2 建議

日期：2026-11-05　範圍：7 個工具（指定 5 個＋2026 年新興 2 個）　OmniKit 對照版本：`4a4fc38`（engine/scripts 與 `.github/workflows/validate.yml` 跟 HEAD 相同）

標記：【驗】看過原始碼、官方文件或 issue；【推】從原始碼推論，沒有實測。原始碼證據寫成 `path:行號 @ 短 SHA`；OmniKit 的檔案寫成 `OmniKit path:行號`。

## 0. 需要你決定的事

| # | 決定 | 建議 | 理由 |
|---|---|---|---|
| 1 | 預覽要不要改成跟安裝共用同一個規劃器 | 要：`agents.py plan --json` 產生計畫，`-WhatIf`、訪談預覽與實際安裝都用這份 | 現在 `-WhatIf` 在 PowerShell 另寫一套判斷，只靠註解保持一致（OmniKit install.ps1:93、349）；rulesync、skillshare 的預覽與套用都來自同一份計畫。v2 的工具包改成自動組出之後，兩套判斷更難對齊 |
| 2 | Codex 規則要不要改成受管區塊 | 要：做法跟 GEMINI.md 一樣，保留使用者原本的內容 | 現在是整份換掉，原本的規則只剩備份（OmniKit profiles.py:189-203），同事原有的 Codex 規則裝完就失效；Claude 與 Antigravity 原有的規則則照樣生效 |
| 3 | 「底線只能更嚴」要不要做成機器檢查 | 要，先從權限、MCP、hooks 做 | 現在只是 baseline.md 的文字約定；APM 的 policy 繼承明確實作了「每層只能更嚴」 |

## 1. 研究對象與方法

| 工具 | repo | HEAD（完整 SHA） | 語言 | 星數 | 最新 release | 備註 |
|---|---|---|---|---|---|---|
| rulesync | dyoshikawa/rulesync | d088ccc8f436255115e0e7fb95f9ce0778375a4a | TypeScript | 1,583 | v43.6.0（2026-11-03） | 2026-10-01 起 35 個 release；v28（10/08）到 v43（10/26），18 天內 15 次 major |
| rulebook-ai | botingw/rulebook-ai | 7bc8531cdaaa3b49bf5a6cef82485725a9bcaae9 | Python | 613 | 沒有 release | 最後 push 2025-10-03；PyPI 查不到（HTTP 404） |
| Ruler | intellectronica/ruler | 5e551e60952fb1c81c6c5ad6f5fe8b7a412bda87 | TypeScript | 2,959 | v0.3.46（2026-10-22） | open issue 10 |
| skillshare | runkids/skillshare | add5753ab9cac045e12b14d1ffe5b1871471fdf8 | Go | 2,898 | v0.28.4（2026-11-04） | 2026-10-01 起 37 個 release；維護集中在一個人 |
| Agent OS | buildermethods/agent-os | e892e61d322759165e7d9173e92c1010406c9f4d | Bash、Markdown | 5,579 | v3.0.0（2026-01-20） | 最後 push 2026-10-07；issue 由 stale bot 關閉 |
| skills CLI（新） | vercel-labs/skills | 9197d919034d19010ae303cf96bf19ad087dd4be | TypeScript | 38,088 | v1.7.6（2026-11-03） | 2026-01-14 建立；open issue 841 |
| APM（新） | microsoft/apm | 2920043258932f0f67e6f01df7b9047eb42f358c | Python | 4,216 | v0.35.0（2026-10-22） | 2025-09-18 建立，主要成長在 2026 年；open issue 211 |

新增的兩個為什麼納入：

- **skills CLI（`npx skills`）**：2026 年同類工具中採用度最高。它把一個來源的 skills 裝到 40 多種 agent，Claude Code、Codex、Antigravity 都在清單上。它在 Windows 與 Antigravity 上遇到的問題，正好是 OmniKit 同事的環境。
- **APM**：唯一把工具包做成套件管理的工具，有相依、lock 與政策繼承。它的 policy 規定「每層只能更嚴、不能放寬」，正是 OmniKit 底線要的語意。CI 也設有 Windows 專用的檢查關卡。
- 看過但沒有納入：getsentry/dotagents（81fa16f2bb6645dae9b8f8a5cb04297c838474fd，262 星，2026-02 建立）。它有 `agents.toml`、lock 與使用者範圍，但功能跟 APM、skills CLI 重疊，採用度也低。

方法：

- 一律 `git clone --depth 1`，放在 `C:\Users\user\AppData\Local\Temp\claude\07f6cb4a104ab615\94882482-db11-4c17-b78c-34dd27b0c3f0\scratchpad\research\sync\`。只讀，沒有執行任何下載來的程式。
- issue、release 與星數用 `gh` 查（2026-11-05）。官方文件用網頁查。
- rulesync 與 skillshare 的程式量大（1,565 與 2,826 個檔），細節由兩個平行的子研究讀原始碼整理。關鍵主張我另外抽查過原始碼，包括：MCP 整個 key 換掉、global delete、擁有權宣告表、JSON plan、`--check`、MCP 衝突即停、revision、區塊雜湊、install.ps1、版本檢查、targets 路徑與 import 路徑。

## 2. 各工具重點（依原任務 6 題）

### 2.1 rulesync

1. **來源與產生方式**
   - 【驗】單一來源放在 `.rulesync/`：`rules/*.md`、`commands/`、`subagents/`、`skills/<名稱>/SKILL.md`、`mcp.jsonc`、`hooks.jsonc`、`permissions.jsonc`、`.aiignore`（src/constants/rulesync-paths.ts:7-8、49-68 @ d088ccc）。
   - 設定檔是 `rulesync.jsonc`，個人覆蓋用 `rulesync.local.jsonc`。規則的 frontmatter 有 `root`、`targets`、`globs`（src/features/rules/rulesync-rule.ts:34-58 @ d088ccc）。
   - 【驗】一律產生實體檔，不用 symlink（src/utils/file.ts:519-522 @ d088ccc）。
   - `--global` 會把輸出改寫到家目錄。坑：設定檔裡只要寫了 `inputRoots`，`global: true` 就會被忽略，只印一行警告（src/config/config-resolver.ts:228-236 @ d088ccc）。

2. **支援項目與三個 agent**
   - 【驗】支援 rules、mcp、commands、subagents、skills、hooks、permissions；ignore 已併入 permissions。目標有 20 多種。

     | | Claude Code | Codex | Antigravity |
     |---|---|---|---|
     | 規則 | `~/.claude/CLAUDE.md`＋`~/.claude/rules/` | `~/.codex/AGENTS.md`，非 root 的規則全部併進這一份 | `~/.gemini/GEMINI.md`；非 root 規則拆到 `~/.gemini/config/rules/`，加上 trigger |
     | MCP | `~/.claude.json` | `~/.codex/config.toml` 的 `mcp_servers` | `~/.gemini/config/mcp_config.json` |
     | skills | `~/.claude/skills` | `~/.agents/skills` | IDE：`~/.gemini/config/skills`；CLI：`~/.gemini/antigravity-cli/skills` |

     來源：docs/reference/supported-tools.md:134、src/features/skills/codexcli-skill.ts:253-254 @ d088ccc。
   - 【驗】Gemini CLI 已經不是 target：清單由各功能的支援表合併產生（src/types/tool-targets.ts:7-15 @ d088ccc），非測試原始碼裡搜不到 geminicli。
   - 【驗】寫不了 Codex 的 `[[skills.config]]`（#2496 還開著），所以做不到 OmniKit「停用但不刪檔」的瘦身。

3. **既有檔案、移除、預覽、冪等**
   - 【驗】規則檔整份覆寫：`shouldMergeExistingFileContent()` 回傳 false（src/types/ai-file.ts:122-124 @ d088ccc），沒有受管區塊，也不備份。
   - 【驗】MCP 整個 key 換掉：`{ ...json, mcpServers: rulesyncMcp.getMcpServers() }`（src/features/mcp/claudecode-mcp.ts:139-141 @ d088ccc）。
   - Codex 的 `mcp_servers` 只用來源裡的 server 組出來，既有 server 只保留工具核准紀錄（src/features/mcp/codexcli-mcp.ts:999-1045 @ d088ccc）。TOML 整份重寫，只有 JSONC 與 JSON5 保留原本格式（src/features/shared/shared-config-gateway.ts:958-961 @ d088ccc）。
   - 【推】使用者自己加的 MCP server、config.toml 裡的註解與排版，都會不見。
   - 【驗】共用設定檔有一張擁有權宣告表：每個功能宣告自己擁有哪些頂層 key（shared-config-gateway.ts:1406-1420 @ d088ccc）。hooks 要開 `preserveUnownedHooks` 才會另記鎖檔（src/features/hooks/hooks-ownership-lock.ts:10-21 @ d088ccc）。
   - 【驗】global 模式開 `delete` 時，會刪掉 `~/.claude/skills`、`~/.agents/skills` 底下這次沒產生的所有 skill，別的工具裝的也算在內（docs/guide/global-mode.md:79-85 @ d088ccc）。有任何來源讀取失敗，就整個不刪（src/lib/generate.ts:174 @ d088ccc）。
   - 【驗】移除用的 `retireTargets` 不支援 global（src/lib/retire-targets.ts:148-151 @ d088ccc）。
   - 【驗】預覽有三種：`--dry-run`；`--check` 有差異就 exit 1（src/cli/commands/generate.ts:239-252 @ d088ccc）；`--json` 輸出有版本號的 plan，細到共用設定檔的 key（src/lib/generate-plan.ts:7-30 @ d088ccc）。
   - 【驗】冪等：結構相同就不寫（src/utils/content-equivalence.ts:190-210 @ d088ccc）。

4. **組合與繼承**
   - 【驗】沒有 packs 或 profiles，靠三種疊加：
     - `inputRoots` 依序疊加，後面的勝出：規則逐檔、MCP 逐個 server（src/features/rules/rules-processor.ts:1479-1490 @ d088ccc）。
     - `rulesync.local.jsonc` 逐個 key 覆蓋。
     - `sources` 從 GitHub、git 或 npm 抓，`rulesync.lock` 記 SHA。`install --outdated` 只讀不寫，回報落後的來源（src/lib/install.ts:30-38 @ d088ccc）。
   - 【推】後面的同名檔整檔取代前面的，所以擋不住「放寬底線」。

5. **Windows 與測試**
   - 【驗】單元測試只在 ubuntu 跑（.github/workflows/ci.yml:24 @ d088ccc）；Windows 只跑單一執行檔的 e2e（.github/workflows/e2e-binaries.yml:43-44 @ d088ccc）。
   - 【驗】Windows 相關 issue：
     - #2740：只改檔名大小寫，就會刪掉剛產生的檔（2026-08-24 回報，10 天修好）。
     - #1239：Windows 與 Linux 產生的換行與路徑不同（3 月回報，7 月才關）。
   - 【驗】讀 `~/.claude.json` 直接 `JSON.parse`（claudecode-mcp.ts:139-140）。子研究用 Node 試過，帶 BOM 會丟例外，結果是失敗，不會把檔寫壞。
   - 【驗】安裝需要 Node 22.22.0 以上（package.json:127）。也可以下載單一 exe，文件教人搬進 `C:\Windows\System32`，這要系統管理員權限（docs/getting-started/installation.md:94 @ d088ccc）；文件也教人用 `gh attestation verify` 驗證出處（同檔 :134）。

6. **採用度（背景）**：1,583 星，發版極快。

### 2.2 rulebook-ai

1. **來源與產生方式**
   - 【驗】只有 project 範圍。來源單位是 pack：`manifest.yaml`（name、version、summary）、`README.md`、`rules/NN-rules[-mode]/NN-*.md`，加上選配的 `memory_starters/`、`tool_starters/`。結構有嚴格驗證（src/rulebook_ai/community_packs.py:31-108 @ 7bc8531）。
   - `packs add` 把 pack 複製進專案的 `.rulebook-ai/packs/<名稱>`，選擇記在 `.rulebook-ai/selection.json`（src/rulebook_ai/core.py:167-181、298-313、335-357 @ 7bc8531）。
   - 【驗】一律複製：
     - 單檔 agent：規則串成一份，每段前面加 `# Rule: 檔名`，段與段之間用 `---` 分隔（core.py:122-132）。
     - 多檔 agent：依序編號，或保留原本的階層（core.py:103-120、134-161）。

2. **支援項目與三個 agent**
   - 【驗】只有規則，加上 memory 與 tools 範本。支援 10 種 agent，全部寫在專案根目錄：Claude Code 寫 `CLAUDE.md`、Codex 寫 `AGENTS.md`、Gemini CLI 寫 `.gemini/GEMINI.md`（src/rulebook_ai/assistants.py:104-127 @ 7bc8531）。
   - 沒有 Antigravity，沒有 global，沒有 skills。MCP 是 #24，還開著。

3. **既有檔案、移除、預覽**
   - 【驗】`project sync` 沒加 `--assistant` 時，10 種 agent 全部同步（core.py:556）。每一種都先刪掉 `clean_path` 再重寫（core.py:557-566、assistants.py:46-127 @ 7bc8531）：
     - `CLAUDE.md`、`AGENTS.md`、`.github/copilot-instructions.md` 直接刪。
     - `.cursor`、`.windsurf`、`.roo` 整個資料夾 rmtree。
   - 不備份、不加標記、沒有 dry-run。【推】使用者手寫的 `CLAUDE.md`、`.cursor/mcp.json` 都會被刪掉。
   - `clean-rules` 也一樣，不看檔案是不是它產生的就刪（core.py:611-628）。
   - 【驗】做得好的一點：`memory_starters`、`tool_starters` 只補缺、不覆蓋（core.py:83-101），並用 `file_manifest.json` 記哪個檔由哪個 pack 建立。拿掉 pack 之後，`clean-context` 會列出孤兒檔，問過才刪（core.py:540-553、641-692 @ 7bc8531）。

4. **packs 與 profiles**
   - 【驗】profile 只是幾個 pack 名稱的清單，存在專案的 `selection.json`，沒有繼承（core.py:443-499）。`project sync` 只能二選一：`--profile`，或 `--pack`（core.py:515-527）。
   - 【驗】幾個 pack 有同名的規則檔時，先複製的勝出，不會警告（core.py:535-537 搭配 83-101）。
   - 【驗】社群 pack 從 GitHub 上的索引抓，可以釘 commit。安裝前印出「This code is not audited」，要輸入 yes 才繼續（community_packs.py:273-288），並記下 commit（:293-294）。

5. **Windows 與測試**
   - 【驗】CI 三個 job 都只跑 ubuntu-latest（.github/workflows/ci.yml:11、37、75 @ 7bc8531），共 20 個測試檔。
   - 【推】多處 `read_text()` 沒指定編碼（core.py:174、229、353；community_packs.py:53）。繁體中文 Windows 的預設編碼是 cp950，manifest 或 selection.json 裡有中文就會解碼失敗。`shutil.rmtree` 也沒處理唯讀屬性。
   - 【驗】README 教用 `uvx rulebook-ai`，但 PyPI 查不到這個套件：2026-11-05 查詢回 404；#61 回報「not found in the package registry」，#60「Upload to pypi」還開著。

6. **採用度（背景）**：613 星，近一年沒有維護。

### 2.3 Ruler

1. **來源與產生方式**
   - 【驗】來源放在 `.ruler/`：
     - `*.md` 規則，遞迴找出後依序串接。
     - `ruler.toml`：agents、MCP、gitignore、backup 等設定。
     - `skills/` 與 subagents。
   - `ruler init --global` 會建在 `$XDG_CONFIG_HOME/ruler`，只在專案沒有 `.ruler/` 時當來源（README.md:121-127、227；src/core/FileSystemUtils.ts:196-230 @ 5e551e6）。也支援巢狀的 `.ruler/`。
   - 【驗】輸出一律寫在專案裡：`assertManagedPathInsideRoot` 擋掉專案外的路徑（src/agents/AbstractAgent.ts:45-57 @ 5e551e6）。README 明講「never writes MCP configuration files outside your project root」（README.md:589）。所以 Ruler 沒辦法接 `~/.claude`、`~/.codex`。
   - 【驗】寫檔時拒絕穿過 symlink 或硬連結（FileSystemUtils.ts:492-522）。skills 用複製（src/core/SkillsUtils.ts:113-154）。

2. **支援項目與三個 agent**
   - 【驗】支援規則、MCP、skills、subagents，30 多種 agent；沒有 hooks 與權限。
     - Claude：`CLAUDE.md`（src/agents/ClaudeAgent.ts:16-18）。
     - Codex：`AGENTS.md`，加上專案裡的 `.codex/config.toml`（src/agents/CodexCliAgent.ts:161-166）。
     - Gemini CLI：寫 `AGENTS.md`，並在 `.gemini/settings.json` 設 `contextFileName`（src/agents/GeminiCliAgent.ts:17-29、70-73）。
     - Antigravity：`.agent/rules/ruler.md`，不寫 MCP（src/agents/AntigravityAgent.ts:16-18）。
     - skills 目錄：Claude `.claude/skills`、Codex `.agents/skills`、Antigravity `.agent/skills`（src/constants.ts:57-70）。

3. **既有檔案、移除、預覽、冪等**
   - 【驗】覆寫前備份成 `.bak`，只保留第一次的備份；已經是 Ruler 產生的檔就不備份（FileSystemUtils.ts:524-560）。
   - 【驗】AGENTS.md 開頭加 `<!-- Generated by Ruler -->`，內容相同就不寫（src/agents/AgentsMdAgent.ts:47-67）。
   - 【驗】MCP 有兩種策略：merge（聯集，Ruler 的勝出）與 overwrite（src/mcp/merge.ts:53-78）。
   - 【驗】`.gitignore` 用 START／END 標記的區塊管理（src/core/revert-engine.ts:25-26）。
   - 【驗】skills 用 `.ruler-managed.json` 記受管項目，只刪自己的（src/core/SkillsProcessor.ts:29、256-277、392-410）。
   - 【驗】`revert` 會還原 `.bak`、刪掉產生的檔（README.md:310-343）；有 `--dry-run`。
   - 【驗】坑：Codex 的 `config.toml` 解析失敗時，會當成空設定，再用 `@iarna/toml` 整份寫回，而且這個檔不備份（CodexCliAgent.ts:103-109、151-157 @ 5e551e6）。【推】Ruler 讀不懂的 config.toml，會被換成只剩 `mcp_servers`。

4. **組合**：【驗】沒有 packs 或 profiles；組合靠巢狀的 `.ruler/`、`ruler.toml` 的 agent 開關與 `default_agents`。

5. **Windows 與測試**
   - 【驗】CI 只在 ubuntu 跑，涵蓋 Node 20、22、24 三版（.github/workflows/ci.yml:15 @ 5e551e6），共 169 個測試檔。
   - 【驗】Windows 相關 issue：
     - #412：apply 在 skills 資料夾 rename 時遇到 EPERM（4 月回報，5 月修好）。修法是重試 5 次，還不行就改用 cp 加 rm（SkillsProcessor.ts:282-335）。
     - #60：Windows 與 *nix 產生的規則檔不同。

6. **採用度（背景）**：2,959 星，v0.3.46。

### 2.4 skillshare

1. **來源與產生方式**
   - 【驗】設定放在 `%APPDATA%\skillshare`，有設 XDG 就用 XDG（internal/config/config.go:622-638 @ add5753）。
   - 【驗】`config.yaml` 的欄位（config.go:372-433）：
     - `sources`：skills、agents、extras、mcp
     - `mode`：merge、symlink、copy
     - `targets`：每個 target 各有 include 與 exclude
     - 其他：`extras`、`ignore`、`audit`、`backup`、`context_budget`、`hooks`
     - 另外 `.skillignore` 用 gitignore 語法篩 skill。
   - 【驗】目前目錄有 `.skillshare/config.yaml` 就進 project 模式（cmd/skillshare/mode.go:75-87）。
   - 【驗】三種產生方式：merge（每個 skill 一個連結）、symlink（整個資料夾一個連結）、copy（每個 skill 複製一份，用 SHA-256 判斷要不要更新）（internal/sync/sync.go:283-347、562-715；internal/sync/copy.go:110-233）。
   - 【驗】Windows 依序試相對 symlink、junction、絕對 symlink（internal/sync/symlink_windows.go:15-79）。每個 target 放一份 `.skillshare-manifest.json`，記錄受管項目（internal/sync/manifest.go:13-26）。

2. **支援項目與三個 agent**
   - 【驗】內建 79 個 target。skills 的位置（internal/config/targets.yaml:25-42、134-143 @ add5753）：
     - Claude：`~/.claude/skills`
     - Codex：`~/.agents/skills`，也會掃 `~/.codex/skills`
     - Antigravity：`~/.gemini/config/skills`
     - Antigravity CLI：`~/.gemini/antigravity-cli/skills`
   - 【驗】規則：一份 AGENTS.md 接到各 agent。Claude 用 `@path` import，其他用連結，或 copy、prepend、append 模式（internal/instructions/assign.go:142-160；internal/config/extras_validate.go:38）。
   - 【驗】MCP 支援 22 種 client：
     - Claude：`~/.claude.json` 用 hujson patch，只改 mcpServers（internal/mcp/native.go:187-243）。
     - Codex：在 config.toml 原地換掉 `[mcp_servers.X]` 那一段，保留 CRLF；遇到 inline 寫法就拒絕，寫完重新解析比對（internal/mcp/native_toml.go:16-129）。思路跟 OmniKit 一樣。
     - Antigravity：`~/.gemini/config/mcp_config.json`。
   - 【驗】hooks 支援 13 種，Codex 寫進 `~/.codex/hooks.json`（internal/hooks/model.go:275-289）。commands 只當成 extras 目錄同步；權限與 ignore 不同步。
   - 【驗】MCP 的 env 可以寫 `{fromEnv: VAR}`，到了 Codex 會轉成 `env_vars`（internal/mcp/model.go:18-37、render.go:134、168）。

3. **既有檔案、移除與還原、預覽**
   - 【驗】MCP 有擁有權帳本（internal/mcp/plan.go:718-766）：
     - 每個 entry 記擁有者與雜湊，分成 add、update、remove、adopt、unchanged、conflict。
     - 使用者改過受管的 entry，或已經有同名但不受管的 entry，都算 conflict。
     - 有任何 conflict，整次 sync 什麼都不寫（cmd/skillshare/sync.go:163-193）。
     - Apply 要帶預覽時的 revision；預覽之後設定變了，就要求重新預覽（internal/mcp/write.go:133-156）。
     - 寫入前先存 before／after 與 pending journal（write.go:64-90、247-283）。
   - 【驗】規則區塊的標記寫成 `<!-- skillshare:extra src="…" sha256=… -->`，帶來源路徑與內容雜湊，手改過就拒絕同步（internal/sync/extras_block.go:14-30、290-291）。
   - 【驗】第一次接上時存一份還原紀錄：原本的檔案，或「原本不存在」的標記（internal/sync/extras_backup.go:18-27）。
   - 【驗】sync 前自動備份 target，預設保留 10 份或 500 MB；還原可以先用 `restore --dry-run` 預覽（cmd/skillshare/backup.go:434）。
   - 【驗】坑：
     - merge 模式遇到同名連結，只要不是指向來源，就直接刪掉重建，不管是誰建的（internal/sync/sync.go:650-682）。
     - #314：merge 模式的清理會刪掉使用者自己建、指向來源的 junction（2026-10-01 回報，當天修好）。
     - copy 模式在來源變動時整份重拷，不檢查 target 裡的副本有沒有被改過（copy.go:195-227）。

4. **組合**
   - 【驗】沒有 profile；#202「Add a profile feature」從 2026-06 開到現在，沒有回應。
   - 能組合的方式：來源子資料夾分組、include 與 exclude、`.skillignore`、tracked repo、registry。
   - 【驗】有 context budget：估算每次對話開頭載入的 skill 說明有多少 token，超過 10,000 就警告（config.go:311-333、internal/sync/context.go:14-19）。
   - 【驗】安裝前有 audit 掃描（internal/audit/rules.yaml）。

5. **Windows 與測試**
   - 【驗】install.ps1 下載 zip 後不驗 checksum，還會改使用者的 PATH（install.ps1:71-79、99-118 @ add5753）。
   - 【驗】每個指令跑完後，每 24 小時連一次 api.github.com 查新版（cmd/skillshare/main.go:168-180、internal/version/check.go:20）。
   - 【驗】goreleaser 沒有簽章步驟（.goreleaser.yaml:21-22）。
   - 【推】可能被 Trend Micro 擋的原因：exe 沒簽章、安裝時改 PATH、平均一天不只一版（每版都是新的雜湊，信譽要重新累積）、從 git hook 在背景啟動、執行時會連網。上游沒有任何防毒相關的 issue，這些都是推論。
   - 【驗】Windows 相關 issue：
     - #255：Antigravity 讀不到連結的 skill。8 月修正了預設路徑，但預設模式仍是 merge（建連結）。
     - #275：`.skillignore` 遇到 CRLF 就失效（隔天修好）。
     - #344：在 windows-latest 跑測試，28 個套件有 14 個失敗；還開著。
   - 【驗】Claude 的 import 行用絕對路徑時，寫的是 `"@" + f.Source`，沒有轉成正斜線（internal/sync/extras_file.go:303-307）。OmniKit 實測過，Claude Code 不會載入反斜線路徑（OmniKit profiles.py:173-174）。
   - 【驗】整合測試只在 ubuntu 與 macOS 跑；Windows 只跑部分單元測試（.github/workflows/test.yaml:70-73、93-159）。

6. **採用度（背景）**：2,898 星，共 244 個 release。issue 回應很快（從開到關的中位數約 28 小時）。

### 2.5 Agent OS（v3）

1. **來源與產生方式**
   - 【驗】基底安裝（通常在 `~/agent-os`）放 `config.yml`、`profiles/<名稱>/standards/**/*.md` 與 `commands/agent-os/*.md`。
   - `project-install.sh` 做三件事（scripts/project-install.sh:195-276、384-411 @ e892e61）：
     - 把標準複製進專案的 `agent-os/standards/`
     - 產生 `index.yml`
     - 把指令複製到 `.claude/commands/agent-os/`
   - 只有 project 範圍；「全域」只是指基底安裝這份來源。

2. **支援項目與三個 agent**
   - 【驗】只處理標準（規則）與 Claude Code 的 slash commands，沒有 skills、MCP、hooks 與權限。README 說可以搭配 Antigravity 使用，但安裝程式只寫 `.claude/commands`。
   - 指令：
     - `/discover-standards`：從程式碼整理出標準
     - `/index-standards`
     - `/inject-standards`：依 `index.yml` 只注入相關的標準
     - `/plan-product`
     - `/shape-spec`

3. **既有檔案與預覽**
   - 【驗】專案已經有 `agent-os/standards` 時先問 y/N，答 y 就整批覆蓋；`--commands-only` 只更新指令（project-install.sh:164-189、37-39）。
   - 【驗】重建 `index.yml` 時保留舊的描述（:278-382）。
   - 【驗】反方向的 `sync-to-profile.sh` 把專案裡改好的標準推回 profile：偵測衝突後可以選覆蓋（先備份到 `.backups/<時間>/`）、略過或取消（scripts/sync-to-profile.sh:353-458）。
   - 沒有 dry-run（v2 有，v3 拿掉了），也沒有移除指令。

4. **profiles 與繼承（重點）**
   - 【驗】繼承寫在 `config.yml`：`profiles: <名稱>: inherits_from: <父>`（config.yml:4-10）。
   - 【驗】依父鏈組出「基底在前」的順序，偵測循環與不存在的 profile（scripts/common-functions.sh:85-178）。
   - 【驗】依序複製，同一個相對路徑由後面的勝出，也就是檔案層級的覆蓋（project-install.sh:220-250）。有繼承時，會列出每個檔來自哪個 profile（:258-266）。
   - 官方文件的說明一致（[Agent OS profiles](https://buildermethods.com/agent-os/profiles)）：沒列在 `config.yml` 的資料夾也算 profile，只是沒有父層。
   - 【推】預設 profile 的檔案放在 `profiles/default/global/tech-stack.md`，少了一層 `standards/`；安裝程式讀的是 `profiles/<名稱>/standards`（project-install.sh:224），所以這個檔不會被複製。沒有測試能抓到這種問題。

5. **Windows 與測試**
   - 【驗】只有 bash 腳本。
     - Windows 要用 Git Bash；在 PowerShell 執行會裝進 WSL（#28）。
     - 有使用者自己寫了 PowerShell 版（#50）。
   - 【驗】`set -e` 底下的 `((var++))` 會讓腳本無聲中止（#319；修正記在 CHANGELOG.md 的 Unreleased）。
   - 【驗】沒有測試；CI 只有 PR 關閉與 stale 兩個 workflow。

6. **採用度（背景）**：5,579 星，v3.0.0。

### 2.6 skills CLI（vercel-labs/skills）

1. **來源與產生方式**
   - 【驗】來源是任何 git repo，或 skills.sh 目錄裡的 skill。安裝模式有三種（src/installer.ts:34-38、324-462 @ 9197d91）：
     - `symlink`（預設）：複製到標準位置 `.agents/skills/<名稱>`，再把各 agent 的資料夾連過去
     - `copy`
     - `link`
   - Windows 用 junction（:290-293），建不起來就改用複製。
   - global 的鎖檔放在 `~/.agents/.skill-lock.json`，記來源與資料夾雜湊（src/skill-lock.ts:7-26、65-74）。

2. **支援項目與三個 agent**
   - 【驗】只管 skills，支援 40 多種 agent。各 agent 的全域 skills 位置（src/agents.ts:104-122、160-168、229-236 @ 9197d91）：
     - Claude Code：`~/.claude/skills`
     - Codex：`~/.agents/skills`
     - Antigravity：`~/.gemini/antigravity/skills`
     - Antigravity CLI：`~/.gemini/antigravity-cli/skills`
   - 【驗】它的 Antigravity 路徑跟 rulesync、skillshare 以及 OmniKit 實測的 `~/.gemini/config/skills` 不同。相關 issue 都還開著：#1470「Add support for Antigravity 2.0」、#633「Antigravity IDE does not discover symlinked skills」。

3. **既有檔案與預覽**
   - 【驗】目標位置已經有同名的真資料夾時，直接 `rm -r` 再建連結，不檢查是誰的（src/installer.ts:259-270）。`cleanAndCreateDirectory` 也是先整個刪掉再複製（:194-203）。
   - 【驗】鎖檔格式升版時，直接清空舊的鎖檔（skill-lock.ts:80）。
   - 有 `remove`、`check`、`update`，沒有 dry-run。
   - 【驗】安裝時顯示 Socket、Snyk 等合作廠商的稽核結果（src/add.ts:142-170）。

4. **組合**
   - 【驗】skills.sh 有 packs：一組 skill，每個釘在一個 tree hash，內容相符才從原 repo 安裝（src/add.ts:694-760）。
   - 【驗】從 `package.json` 同步時的衝突規則：直接相依勝過間接相依；同一層有兩個套件提供同名 skill 時，兩個都不裝，由使用者用 `--exclude` 挑（docs/commands.md:326-329）。

5. **Windows 與測試**
   - 【驗】CI 在 ubuntu 與 windows 都跑（.github/workflows/ci.yml:17-19）。
   - 【驗】Windows 相關 issue 多半還開著：
     - #399：鎖檔在 Windows 上是空的。
     - #840、#941、#1457：Node 裝在含空白的路徑或 `C:\Program Files` 時，update 失敗。
     - #2613：路徑太長。
     - #2461：送出遙測請求後程式中止。
   - 【驗】預設會送遙測到 `skills.sh/tele/t`，要設 `DISABLE_TELEMETRY` 或 `DO_NOT_TRACK` 才會關（src/telemetry.ts:3-4、76）。

6. **採用度（背景）**：38,088 星，open issue 841。

### 2.7 APM（microsoft/apm）

1. **來源與產生方式**
   - 【驗】在 `apm.yml` 宣告相依：skills、prompts、instructions 與 MCP，可以有間接相依。`apm.lock.yaml` 釘住整棵相依樹，每個套件記一個 SHA-256 內容雜湊（src/apm_cli/deps/lockfile.py:333 @ 2920043）。
   - 【驗】`apm install` 把內容整合到各 agent，`apm compile` 產生 AGENTS.md、CLAUDE.md。加 `--global`（或 `-g`）就裝到使用者範圍（src/apm_cli/commands/install.py:965-966）。

2. **支援項目與三個 agent**
   - 【驗】支援十多種 client，三個 agent 的 MCP 寫法：
     - Codex：使用者範圍寫 `~/.codex/config.toml`，專案範圍寫 `.codex/`。用 tomlkit 讀改寫，寫完再 parse 一次（src/apm_cli/adapters/client/codex.py:10-12、86-107、173-176）。
     - Antigravity：使用者範圍寫 `~/.gemini/config/mcp_config.json`（adapters/client/antigravity.py:22、46-49）。
     - Claude：寫進 `$CLAUDE_CONFIG_DIR/.claude.json`，沒設才用 `~/.claude.json`（adapters/client/claude.py:7、248-253）。
   - hooks、skills、指令與 LSP 都有各自的 integrator（src/apm_cli/integration/）。

3. **既有檔案與預覽**
   - 【驗】install 與 uninstall 都有 dry-run（commands/install.py:25；commands/uninstall/__init__.py:7）。另外有 `prune`、`outdated`、`update`、`audit`、`doctor`。
   - 【驗】policy 可以規定 apm.lock 沒記錄的檔要怎麼處理：忽略、警告或拒絕（src/apm_cli/policy/schema.py:109-115）。

4. **繼承（重點）**
   - 【驗】政策繼承分企業、組織、repo 三層，原始碼寫明「Each level can tighten but never relax the parent」。繼承鏈最多 5 層，每種設定都有一條由寬到嚴的階梯，例如 off、warn、block（src/apm_cli/policy/inheritance.py:1-8、34-43 @ 2920043）。
   - 【驗】hooks、MCP 指令這類可執行的東西預設拒絕，deny 永遠勝出。判斷順序從 org-deny-all、org-deny、user-deny、project-deny 往下排（src/apm_cli/security/executables.py:7、183-202、368-375）。

5. **Windows 與測試**
   - 【驗】CI 有兩道 Windows 關卡：Windows 相容檢查，以及「一般使用者權限建 symlink」的檢查（.github/workflows/ci.yml:113-115、173-175）。另外有一個檢查 CRLF 不影響結果的 workflow（crlf-invariance.yml）。
   - 【驗】Windows 相關 issue 仍然不少：
     - #3386：安裝最後一步的 rename 遇到 WinError 5／32 就失敗，沒有重試。
     - #3056：Windows 中文語系出現 gbk 解碼錯誤。
     - #3270、#3368：`text=auto` 或 `core.autocrlf` 讓內容雜湊在 Windows 上不同，`--frozen` 因此失敗。
     - #2545：在公司的 TLS 檢查代理後面出問題。

6. **採用度（背景）**：4,216 星。manifest schema 還是 working draft。

## 3. 對照表

### 3.1 範圍與支援項目

| | 使用者範圍（全域） | 規則 | skills | MCP | commands | subagents | hooks | 權限 |
|---|---|---|---|---|---|---|---|---|
| rulesync | 有（`--global`） | 有 | 有 | 有 | 有 | 有 | 有 | 有 |
| rulebook-ai | 無 | 有 | 無 | 無 | 無 | 無 | 無 | 無 |
| Ruler | 無（全域只當來源） | 有 | 有 | 有 | 無 | 有 | 無 | 無 |
| skillshare | 有（預設） | 有（extras） | 有 | 有 | 只同步目錄 | 部分 agent | 有 | 無 |
| Agent OS | 無 | 標準 | 無 | 無 | 只有 Claude | 無 | 無 | 無 |
| skills CLI | 有（`-g`） | 無 | 有 | 無 | 無 | 無 | 無 | 無 |
| APM | 有（`-g`） | 有（compile） | 有 | 有 | 有 | 有 | 有 | 政策 |
| OmniKit | 只做全域 | 有 | 有 | 有 | 無 | 無 | 提醒 hook | Claude 免問清單 |

### 3.2 三個 agent 的全域位置

| | Claude Code | Codex | Antigravity |
|---|---|---|---|
| 規則 | OmniKit：CLAUDE.md 受管區塊 import；rulesync：整份 CLAUDE.md；skillshare：`@` import | OmniKit、rulesync：整份 AGENTS.md；skillshare：copy 或 prepend | OmniKit：GEMINI.md 受管區塊（放內容）；rulesync：整份 GEMINI.md 加 `config/rules/`；skillshare：跟 Gemini CLI 共用 GEMINI.md |
| skills | 各家都是 `~/.claude/skills` | 各家都是 `~/.agents/skills` | OmniKit：`~/.agents/skills`；rulesync、skillshare：`~/.gemini/config/skills`；skills CLI：`~/.gemini/antigravity/skills`；CLI 版另有 `~/.gemini/antigravity-cli/skills` |
| MCP | `~/.claude.json`（APM 會看 `CLAUDE_CONFIG_DIR`） | `~/.codex/config.toml` | `~/.gemini/config/mcp_config.json` |

### 3.3 既有設定怎麼處理

| | 規則檔 | JSON、TOML 設定 | 同名 skill | 備份 | 預覽 | 移除 |
|---|---|---|---|---|---|---|
| rulesync | 整份覆寫 | 整個 key 換掉；TOML 整份重寫 | global delete 會掃掉別人的 | 無 | dry-run、check、JSON plan | global 不支援 |
| rulebook-ai | 先刪再寫，10 種一起 | 不適用 | 不適用 | 無 | 無 | clean（不分是誰的） |
| Ruler | 覆寫，先存 .bak | merge 或 overwrite；Codex TOML 整份重寫 | manifest 記錄，只動自己的 | .bak（只留第一份） | dry-run | revert |
| skillshare | 帶雜湊的區塊，手改就停 | 擁有權帳本、有衝突全部不寫、帶 revision | 同名連結直接重建 | 自動備份 10 份，加還原紀錄 | 多數指令有 dry-run | detach、restore |
| Agent OS | 先問，再整批覆蓋 | 不適用 | 不適用 | 推回 profile 時備份 | 無 | 無 |
| skills CLI | 不適用 | 不適用 | 同名資料夾直接刪 | 無 | 無 | remove |
| APM | compile 產生 | tomlkit 改寫 | 不適用 | 不適用 | install、uninstall 有 dry-run | uninstall、prune |
| OmniKit | Claude、Antigravity 用受管區塊；Codex 整份 | 只改自己的段落，用 tomllib 驗證，讀不懂就不寫 | 只動有標記或有紀錄的 | .pre-omnikit | -WhatIf（另寫一套） | uninstall（沒有預覽） |

## 4. OmniKit 現況（讀過的部分）

- **規則**：底線加 profile 兩層。
  - Claude：受管區塊 import（OmniKit profiles.py:173-186）。
  - Codex：先備份，再整份換掉（:189-203）。
  - Antigravity：在開頭加受管區塊，原地改寫，硬連結不會斷（:77-87、206-220）。
- **skills**：
  - Claude 用 junction（OmniKit agents.py:172-177）。
  - Codex 與 Antigravity 共用 `~/.agents/skills`，用複製；複製品裡放 `.omnikit.json`（:237-268）。
  - 是不是 OmniKit 的，看標記與 agents.json 的紀錄（:188-206）。
- **MCP**：
  - Claude 用 `claude mcp add-json`（:419-436）。
  - Codex 在文字層級刪改段落，用 tomllib 比對結果符合預期才寫（:465-528）。
  - Antigravity 寫入時拿掉 BOM（:531-547）。
- **hooks**：Codex 的 Stop hook 加在 config.toml 最後面，用 tomllib 驗證，不代替使用者信任（OmniKit codex_hooks.py:71-87、12-14）。
- **安裝**：
  - uv、gh、gitleaks 固定版本、比對 SHA256、不改 PATH（OmniKit install.ps1:47-62、128-149）。
  - `-WhatIf` 在 PowerShell 另寫一套判斷（:286-386）。
  - 預設 plugin 不會自動安裝（:408）。
- **測試**：每支腳本都有 selftest，但 CI 只在 ubuntu 跑（OmniKit .github/workflows/validate.yml:13）。

## 5. OmniKit 應該採用的做法（依價值排序）

### 5.1 預覽與安裝用同一份計畫（規模：中到大）

- **做法**：
  - agents.py 加 `plan` 指令，輸出有版本號的 JSON 計畫。每一項記 agent、檔案、key 或區塊、動作、理由，以及來源槽位與工具卡。
  - `-WhatIf`、omnikit-setup 的預覽與實際安裝都讀這份計畫。
  - 安裝時帶上計畫的 revision（各檔的雜湊）；預覽之後設定被改過，就要求重新預覽。
  - `--check` 有差異就 exit 1，讓每週彙整偵測「設定被手動改過」。
- **證據**：rulesync generate-plan.ts:7-30、generate.ts:239-252 @ d088ccc；skillshare write.go:133-156、cmd/skillshare/sync.go:163-193 @ add5753。
- **OmniKit 現況**：兩套判斷只靠註解保持一致，例如 install.ps1:93 寫「跟 agents.py 的 detect 一樣」、:349 寫「跟 profiles.py 的 OPTIONAL_SKILLS 一樣」。v2 的工具包改由訪談自動組出之後，PowerShell 這一套會更難跟上。
- **價值**：v2 的「預覽 → 安裝」才可信；訪談 skill 不用解析文字；CI 可以直接測計畫。

### 5.2 每個受管項目記擁有者與雜湊，被改過就停下來問（規模：中）

- **做法**：
  - 把 agents.json 擴充成帳本：每個 MCP entry、規則區塊、skill 複製品，都記 OmniKit 寫入時的雜湊。
  - 同步時分成五類：新增、更新、移除、接手（內容完全一樣的同名項目）、衝突（OmniKit 管的但被改過，或同名但不是 OmniKit 的）。
  - 有衝突就整批不寫，列出來讓使用者選。
  - 受管區塊的開始標記帶內容雜湊。
- **證據**：skillshare plan.go:718-766、extras_block.go:14-30 @ add5753；rulesync shared-config-gateway.ts:1406-1420、hooks-ownership-lock.ts:10-21 @ d088ccc。
- **OmniKit 現況【推】**：
  - `same()` 只比 OmniKit 設的欄位，不同就直接覆寫（OmniKit agents.py:380-388）：使用者在 agent 裡改過的 args 會被悄悄改回。
  - Antigravity 更新時整個 entry 換掉（:537-540），使用者加的 `disabled` 也會不見；selftest 只測了「沒變動時不改回」。
  - Codex 更新時連子表格一起刪（:61、465-493）。Codex 會把工具核准紀錄存在 `[mcp_servers.<名稱>.tools.<工具>]`，這些紀錄會跟著消失（這個位置是 rulesync codexcli-mcp.ts:999-1009 @ d088ccc 的註解寫的，相關 issue 是 rulesync #1709）。
  - 受管區塊沒有雜湊（OmniKit profiles.py:55-56、179-181）：GEMINI.md 區塊裡的手改，下次同步就會被蓋掉。
  - Codex 的檔案只要開頭的產生標記還在，就整份照蓋（:189-203）。

### 5.3 既有設定改成接手或匯入，不要備份後停用（規模：小）

- **做法**：
  - Codex 也改成受管區塊，跟 GEMINI.md 一樣放在開頭；使用者原有的規則留在區塊外，照常生效。
  - 訪談時列出掃描到的既有規則、skills 與 MCP，讓使用者選「保留」或「收進 profile」。
- **證據**：rulesync 的 `import` 會讀既有設定（docs/reference/supported-tools.md:134 @ d088ccc）；skillshare 的 `collect` 與首次接上時存的還原紀錄（extras_backup.go:18-27 @ add5753）；Agent OS 推回 profile 時的衝突處理與備份（sync-to-profile.sh:353-458 @ e892e61）。
- **OmniKit 現況**：Codex 整份換掉，原本的規則只剩 `.pre-omnikit` 備份（OmniKit profiles.py:189-203）；Claude 與 Antigravity 原有的規則則照樣生效，三邊不一致。
- **注意【驗】**：`~/.codex/AGENTS.override.md` 存在時，Codex 就不讀 `AGENTS.md`（[Codex 文件](https://learn.chatgpt.com/docs/agent-configuration/agents-md)），接手前要先偵測。

### 5.4 agent 的位置與限制改成偵測，不寫死（規模：小到中）

- **`CODEX_HOME`**：Codex 文件說 Codex home 預設是 `~/.codex`，可以用 `CODEX_HOME` 改。OmniKit 只有 codex_hooks.py:168 有看這個變數，agents.py:88-107、profiles.py:45-49 與 scan.py 都寫死 `~/.codex`。
- **`CLAUDE_CONFIG_DIR`**：APM 的 Claude adapter 有處理（adapters/client/claude.py:7、248-253 @ 2920043），OmniKit 沒有。
- **`~/.codex/AGENTS.override.md` 優先**：偵測到就警告。OmniKit 的 engine/ 裡搜不到 `AGENTS.override`。
- **Antigravity 的大小限制【驗】**：單一規則檔超過 24,000 bytes 會被截斷；所有常駐規則合計上限 20,000 token，超過時最大的檔會改成只放指標（[Antigravity rules](https://antigravity.google/docs/rules)）。
  - 預覽時要算 GEMINI.md 的大小。
  - OmniKit 的區塊放在開頭，被截斷的是尾端，所以 OmniKit 的內容不受影響。
- **Antigravity CLI（`agy`）**：它的全域 skills 在 `~/.gemini/antigravity-cli/skills`（rulesync docs/reference/supported-tools.md:134 @ d088ccc；skillshare targets.yaml:34-42 @ add5753）。OmniKit 偵測到 `agy` 就算接上 Antigravity，skills 卻只放 `~/.agents/skills`（OmniKit agents.py:124、298-304），要實測 agy 讀不讀這個位置。
- **做法**：
  - scan.py 輸出每個 agent 實際用的路徑與來源（預設值、環境變數或覆蓋檔）。
  - agents.py 一律從 scan 的結果取路徑。
  - 加一個 `doctor` 指令，逐項確認。

### 5.5 工具包的 lock：記來源、版本與雜湊，支撐「只留有用的」與主動通知（規模：中）

- **做法**：
  - v2 自動組出工具包、裝好之後，寫一份 lock。每個工具記：
    - 哪一題的答案 → 哪個槽位 → 哪張卡
    - 上游 repo 與 commit
    - 內容雜湊
    - 安裝日期
  - 每週彙整列三種：上游有新版（像 rulesync 的 `--outdated`）、名冊裡同槽位有評估勝出的新卡、30 天沒用到（usage.py 已經有）。
  - 使用者改了答案，就照 lock 拿掉不再需要的工具。
  - 同一個槽位有兩個候選衝突時，不自動挑，列出來問（skills CLI 的做法）。
- **證據**：
  - rulesync install.ts:30-38（`rulesync.lock`、`--outdated`）@ d088ccc
  - skills CLI skill-lock.ts:7-26 @ 9197d91
  - APM deps/lockfile.py:333 @ 2920043
  - rulebook-ai 用 file_manifest 記檔案由哪個 pack 建立（core.py:540-553、641-692 @ 7bc8531）
  - skills CLI：同一層衝突就兩個都不裝（docs/commands.md:326-329 @ 9197d91）
  - Agent OS 列出每個檔來自哪個 profile（project-install.sh:258-266 @ e892e61）
- **注意**：lock 格式升版時要轉換舊資料，不要像 skills CLI 那樣直接清空（skill-lock.ts:80）。

### 5.6 「底線只能更嚴」做成機器檢查，分層用繼承鏈（規模：中）

- **做法**：
  - validate.py 加一項檢查：profile 不能拿掉或改寫底線的條目。
  - 權限（claude-allow）、MCP 與 hooks 採「預設拒絕、deny 勝出」。
  - 以後真的需要團隊層（例如 itri）時，借 Agent OS 的 `inherits_from` 鏈：基底在前、偵測循環、顯示每項來自哪一層；但底線那一層的條目鎖定，不能被覆蓋。
- **證據**：APM policy/inheritance.py:1-8、34-43 與 security/executables.py:183-202、368-375 @ 2920043；Agent OS common-functions.sh:120-178、project-install.sh:220-250 @ e892e61。
- **反例**：rulesync 的 inputRoots 由後面的勝出（rules-processor.ts:1479-1490 @ d088ccc）；rulebook-ai 同名時先到先贏，而且不警告（core.py:83-101、535-537 @ 7bc8531）。這兩種都擋不住「放寬底線」。
- **OmniKit 現況**：只有 data/rules/baseline.md 的文字約定（「可以更嚴，不能放寬」）；compose 只是把兩份接在一起（OmniKit profiles.py:145-149）。

### 5.7 Windows：CI 跑 Windows，並防檔案鎖、語系與路徑問題（規模：小）

- **做法**：
  - validate.yml 加一個 windows-latest job，跑全部 selftest 與 `install.ps1 -WhatIf`。PowerShell 5.1 與 7 各跑一次，HOME 指到暫存資料夾。
  - 改檔或刪資料夾遇到 EPERM、EBUSY、WinError 5 或 32 時，先重試幾次（防毒掃描常會短暫鎖住檔案）。
  - 用 cp950 語系跑一次測試。
  - 長路徑與含空白的路徑各加一個案例。
- **證據**：APM ci.yml:113-115、173-175 @ 2920043；skills CLI ci.yml:17-19 @ 9197d91；Ruler SkillsProcessor.ts:282-335 @ 5e551e6（#412）；APM #3386、#3056；skills CLI #2613、#941、#1457；rulesync #1239。
- **OmniKit 現況**：CI 只有 ubuntu（validate.yml:13）。junction（agents.py:172-177）、唯讀屬性（:213-227）與硬連結（profiles.py:77-87）這些只在 Windows 才會走到的程式，CI 上都沒跑到。

### 5.8 預覽列出每次對話開頭的成本（規模：小）

- **做法**：預覽列出這包工具每次對話開頭大約佔多少 token（skill 名稱與說明，加上規則），超過門檻就提醒。這跟 usage.py 的瘦身互補：裝之前就看得到成本。
- **證據**：skillshare internal/sync/context.go:14-19、config.go:311-333 @ add5753。OmniKit 2026-11-04 的實測：skill 清單從 49,335 字元降到 15,877 字元（OmniKit docs/proposals/2026-11-05-positioning.md:64-67）。

### 5.9 移除也要能預覽，還原紀錄集中存放（規模：小到中）

- **做法**：
  - uninstall.ps1 加 `-WhatIf`，同樣讀 plan。
  - 把每個檔接上前的狀態（原檔的雜湊，或「原本不存在」）集中記在 `%LOCALAPPDATA%\omnikit`，還原只依這份紀錄。
- **證據**：skillshare extras_backup.go:18-27 與 backup.go:434（`restore --dry-run`）@ add5753；APM uninstall 的 dry-run（commands/uninstall/__init__.py:7 @ 2920043）；Ruler 的 revert（README.md:310-343 @ 5e551e6）。
- **OmniKit 現況**：uninstall.ps1 沒有預覽（搜不到 WhatIf）；備份散在各檔旁邊的 `.pre-omnikit`。

### 5.10 小而值得做的

- **MCP 金鑰**：在設定裡寫成環境變數參照，再產生各 agent 原生的寫法（skillshare model.go:18-37、render.go:134、168 @ add5753），符合底線「不寫死金鑰」。
- **第三方工具進工具包之前**：
  - 釘住 commit，明白標示「未稽核」，要使用者確認（rulebook-ai community_packs.py:273-288 @ 7bc8531）。
  - 顯示 Socket、Snyk 的掃描結果（skills CLI add.ts:142-170 @ 9197d91）。
  - 第三方的 hooks 與 MCP 指令預設不放行（APM executables.py:7 @ 2920043）。
- **專案掃描**：借用 Agent OS 的 `/discover-standards` 與 `index.yml`，從程式碼整理出慣例，再用索引只注入相關的部分（commands/agent-os/discover-standards.md、inject-standards.md @ e892e61）。
- **出處驗證**：工具有發佈出處證明的，用 `gh attestation verify` 驗證（rulesync docs/getting-started/installation.md:134 @ d088ccc），補足 SHA256 之外的來源確認。

## 6. OmniKit 已經做得比較好的地方

1. **只動自己的東西**：skills 靠 `.omnikit.json` 標記與 agents.json 的紀錄判斷擁有權，同名但不是 OmniKit 的一律不碰（OmniKit agents.py:188-206、271-295）。對照：
   - rulesync global 模式的 delete 會掃掉別人的 skill（global-mode.md:79-85）
   - skillshare 遇到同名連結直接重建（sync.go:650-682）
   - skills CLI 遇到同名資料夾直接刪（installer.ts:259-270）
   - rulebook-ai 連 `.cursor` 整個資料夾都刪（core.py:557-566）
2. **用手術的方式改 config.toml**：只刪改自己的段落，用 tomllib 確認結果剛好是「原設定加上或拿掉這一段」才寫入，保留註解與 CRLF，讀不懂就不寫（OmniKit agents.py:496-528；codex_hooks.py:65-87）。
   - 對照：rulesync 用 smol-toml 整份重寫；Ruler 解析失敗就當空檔，再整份寫回（CodexCliAgent.ts:103-109、151-157）。
   - 做法相近的只有 skillshare（native_toml.go:16-129）。
3. **Antigravity 的實測細節**：
   - skills 用複製，不用連結（OmniKit agents.py:15-17）。skills CLI #633 與 skillshare #255 都證實連結會讀不到。
   - 寫 mcp_config.json 時拿掉 BOM（agents.py:531-547）。rulesync 遇到 BOM 直接失敗。
   - GEMINI.md 原地改寫，保住硬連結（profiles.py:77-87）。Ruler 遇到硬連結直接拒絕寫入（FileSystemUtils.ts:492-522）；skillshare 用暫存檔 rename 寫入，硬連結會斷（write.go:64-90）。
4. **Claude 的 import 路徑轉成正斜線**（OmniKit profiles.py:173-176）。skillshare 的絕對路徑 import 沒有轉（extras_file.go:303-307）。
5. **供應鏈**：工具固定版本、比對 SHA256、不改 PATH（OmniKit install.ps1:47-62、128-149）。對照：
   - skillshare 的 install.ps1 不驗 checksum 又改 PATH（install.ps1:71-79），而且每 24 小時連網查新版（main.go:168-180）。
   - rulesync 的文件教人把 exe 搬進 System32。
   - skills CLI 預設送遙測。
6. **Codex hook 的位置與信任**：新的 hook 加在最後面，不改變別人 hook 的位置，也不代替使用者信任（OmniKit codex_hooks.py:84-87、12-14）。rulesync 就曾因為把 hook 插在前面，讓別人的 hook 要重新信任（#3495）。
7. **編碼**：讀寫一律指定 UTF-8，stdout 也重設成 UTF-8（OmniKit agents.py:998-999；profiles.py:63-64）。對照：rulebook-ai 多處用預設編碼讀檔；APM #3056 在中文語系出現解碼錯誤。
8. **Windows 唯讀屬性**：資料夾帶唯讀屬性時，照樣能更新與移除（OmniKit agents.py:213-227、242-268）。
9. **依使用紀錄瘦身、用自己的工作情境評估**：usage.py 與 omnikit-eval 這兩件事，七個工具都沒有。skillshare 只估 token；rulesync、APM、skills CLI 只查同一個工具的上游新版。
10. **同一份底線**：三個 agent 套用同一份底線，而且不給選；預設值以繁體中文與公司環境為準。

## 7. 各家共同的缺點，以及 OmniKit 怎麼補

| 共同缺點 | 證據 | OmniKit 怎麼補 |
|---|---|---|
| 只管同步，不管該不該裝：沒有一家會依實際使用汰除工具，也沒有一家會依你的工作情境推薦更好的替代 | skillshare 只估 context 成本；rulesync `--outdated`、APM `outdated`、skills CLI `check` 只看同一個工具的新版 | 名冊、評估、usage.py 加上 5.5 的 lock：每週列出「沒在用」「上游有新版」「同槽位有更好的」，使用者同意才換 |
| 共用全域資料夾的擁有權很弱 | rulesync global delete、skillshare #314、skills CLI installer.ts:259-270 | 已經有標記與紀錄；再補 5.2 的雜湊帳本與「有衝突就停」 |
| Windows 是次要平台 | rulesync 單元測試、Ruler、rulebook-ai 只在 ubuntu 跑；Agent OS 沒有測試；skillshare 在 Windows 有一半套件測試失敗（#344）。symlink、rename、CRLF、長路徑、語系問題一再出現 | 5.7：Windows CI、重試、cp950 測試；維持 Windows 優先 |
| 追不上 agent 改版 | Antigravity 的 skills 路徑三家寫成三種；rulesync 拿掉了 Gemini CLI，18 天內 15 次 major | 只支援三個 agent；路徑交給 scan 偵測，並記下哪天在哪台實測；用 doctor 檢查 |
| 規則檔多半整份覆寫 | rulesync ai-file.ts:122-124；rulebook-ai core.py:557-566；Ruler 覆寫加 .bak | 一律用受管區塊（含 Codex），標記加雜湊 |
| 預設連網、送遙測、發版頻繁，在公司環境容易被防毒或代理擋下 | skills CLI telemetry.ts:3-4、76；skillshare main.go:168-180；APM #2545 | 不送遙測；只在使用者明確執行的步驟連網；固定版本加 SHA256；同事的環境預設不常駐、不在背景更新 |
| 第三方內容的信任多半交給使用者自己判斷 | rulebook-ai 只印一行警告；skills CLI 顯示稽核結果，但照樣預設安裝 | 名冊評估加安全掃描；第三方的 hooks 與 MCP 預設不放行 |
| 文件與實作不一致 | rulebook-ai README 的 `uvx rulebook-ai` 在 PyPI 查不到；Agent OS 預設 profile 少一層 `standards/`（推論） | selftest 涵蓋安裝路徑；README 的指令也放進 CI 跑 |

## 8. 要避開的坑

1. 整份覆寫全域規則檔，又不備份（rulesync ai-file.ts:122-124）。
2. 把 MCP 整個 key 換掉，刪掉使用者自己的 server（rulesync claudecode-mcp.ts:139-141、codexcli-mcp.ts:1010-1045）。
3. TOML 解析失敗就當成空檔，或整份重寫、弄丟註解（Ruler CodexCliAgent.ts:103-109、151-157；rulesync shared-config-gateway.ts:958-961）。
4. 對 Antigravity 用連結（skills CLI #633；skillshare #255）。
5. 遇到同名就刪，不看擁有者（skillshare sync.go:650-682；skills CLI installer.ts:259-270；rulesync global delete）。
6. 讓後面的層整檔蓋掉前面的層，或同名時先到先贏又不警告（rulesync inputRoots；rulebook-ai core.py:83-101）。
7. 用暫存檔加 rename 做原子寫入，會斷掉硬連結（skillshare write.go:64-90）。反過來，原地寫入不是原子操作，所以 OmniKit 要先存備份或 journal 再寫；skillshare 的 pending journal 可以借（write.go:247-283）。
8. 只有 bash 的安裝程式（Agent OS #28、#50）；`set -e` 底下的 `((var++))` 會讓腳本無聲中止（#319）。
9. lock 格式升版就直接清空（skills CLI skill-lock.ts:80）。
10. 沒簽章的 exe、安裝時改 PATH、發版頻繁、在背景啟動：這是 skillshare 的狀況，推論也是它被 Trend Micro 擋下的原因。

## 9. 還不確定、需要實測的地方

1. **Antigravity 的 `@[label](path)` include**：官方文件說規則檔支援，相對路徑從規則檔所在的資料夾算起，`~/` 會展開成家目錄；但沒說全域的 GEMINI.md 支不支援，也沒提絕對路徑。
   - 如果在這台實測可行，Antigravity 可以改成像 Claude 一樣只放 include，改規則就不用重新同步。
   - 不行的話，維持現在的複製。
2. **agy 讀不讀 `~/.agents/skills`**：rulesync 與 skillshare 都另外寫到 `~/.gemini/antigravity-cli/skills`。
3. **Codex 工具核准紀錄的位置**：說是存在 `[mcp_servers.<名稱>.tools.<工具>]`，這只來自 rulesync 原始碼的註解，還沒對照 Codex 文件。
4. **Codex hook 的 Windows 專用指令欄位**：rulesync 的註解說 Codex 0.131.0 加入了這個欄位，在 config.toml 叫 `command_windows`、在 hooks.json 叫 `commandWindows`。它可能取代現在在指令前面加 `& ` 的做法，但還沒查 Codex 文件確認。
5. **移除 Stop hook 時的重新信任**：拿掉 OmniKit 的 Stop hook 後，排在後面的別人的 hook 位置會往前移。Codex 的 hook_key 包含 group 與 handler 的位置（rulesync #3495 引用了 Codex 原始碼），推論這會讓那些 hook 要重新信任；沒有實測。
6. **Trend Micro 的判斷依據**：skillshare 被擋的確切原因不明，上游沒有任何防毒相關 issue，2.4 節列的原因都是推論。固定版本的 uv 會不會一直順利放行，也只能在同事的電腦上觀察。
7. **Codex 全域 AGENTS.md 的大小上限**：不確定它算不算進 `project_doc_max_bytes`（預設 32 KiB）；文件只說合計大小到上限就不再加入檔案。
8. **tomlkit 保留格式的程度**：APM 用 tomlkit 改 config.toml，實際能保留多少原本的格式沒測。OmniKit codex_hooks.py:7-11 寫 tomlkit 會重排表格，這次沒有重測。
9. **Agent OS 預設 profile 的路徑問題**：少一層 `standards/`、安裝時不會被複製，只是讀程式碼的推論，沒有實際跑過。

## 10. 參考來源

- repo：[rulesync](https://github.com/dyoshikawa/rulesync)、[rulebook-ai](https://github.com/botingw/rulebook-ai)、[Ruler](https://github.com/intellectronica/ruler)、[skillshare](https://github.com/runkids/skillshare)、[Agent OS](https://github.com/buildermethods/agent-os)、[skills CLI](https://github.com/vercel-labs/skills)、[APM](https://github.com/microsoft/apm)、[dotagents](https://github.com/getsentry/dotagents)
- 官方文件：[Agent OS profiles](https://buildermethods.com/agent-os/profiles)、[Antigravity rules](https://antigravity.google/docs/rules)、[Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)、[APM manifest schema](https://microsoft.github.io/apm/reference/manifest-schema/)
- PyPI：[rulebook-ai JSON API](https://pypi.org/pypi/rulebook-ai/json)（2026-11-05 回 404）
- issue：
  - rulesync：[#1239](https://github.com/dyoshikawa/rulesync/issues/1239)、[#2496](https://github.com/dyoshikawa/rulesync/issues/2496)、[#2740](https://github.com/dyoshikawa/rulesync/issues/2740)、[#3495](https://github.com/dyoshikawa/rulesync/issues/3495)
  - skillshare：[#202](https://github.com/runkids/skillshare/issues/202)、[#255](https://github.com/runkids/skillshare/issues/255)、[#275](https://github.com/runkids/skillshare/issues/275)、[#314](https://github.com/runkids/skillshare/issues/314)、[#344](https://github.com/runkids/skillshare/issues/344)
  - Ruler：[#60](https://github.com/intellectronica/ruler/issues/60)、[#412](https://github.com/intellectronica/ruler/issues/412)
  - Agent OS：[#28](https://github.com/buildermethods/agent-os/issues/28)、[#50](https://github.com/buildermethods/agent-os/issues/50)、[#319](https://github.com/buildermethods/agent-os/issues/319)
  - rulebook-ai：[#24](https://github.com/botingw/rulebook-ai/issues/24)、[#60](https://github.com/botingw/rulebook-ai/issues/60)、[#61](https://github.com/botingw/rulebook-ai/issues/61)
  - skills CLI：[#399](https://github.com/vercel-labs/skills/issues/399)、[#633](https://github.com/vercel-labs/skills/issues/633)、[#840](https://github.com/vercel-labs/skills/issues/840)、[#941](https://github.com/vercel-labs/skills/issues/941)、[#1457](https://github.com/vercel-labs/skills/issues/1457)、[#1470](https://github.com/vercel-labs/skills/issues/1470)、[#2461](https://github.com/vercel-labs/skills/issues/2461)、[#2613](https://github.com/vercel-labs/skills/issues/2613)
  - APM：[#2545](https://github.com/microsoft/apm/issues/2545)、[#3056](https://github.com/microsoft/apm/issues/3056)、[#3270](https://github.com/microsoft/apm/issues/3270)、[#3368](https://github.com/microsoft/apm/issues/3368)、[#3386](https://github.com/microsoft/apm/issues/3386)
