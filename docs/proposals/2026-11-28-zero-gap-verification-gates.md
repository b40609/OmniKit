# OmniKit 全路徑斷層清查總表 × 防「假完工／一用就壞」永久機械閘門提案

- 日期：2026-11-28
- 狀態：**待使用者拍板後連同工作台改版一併實作**
- 三線飽和調研依據（共 36 組關鍵字、逾 690 個項目、60+ 個 GitHub 專案 `gh api` 實測星數）：
  1. 工具與閘門線（12 組 491 項，Gemini 4 Neon）：`~/.omnikit/status/OmniKit/reports/2026-11-28-防假完工與端到端驗收工具-飽和調研.md`
  2. 頂尖方法論線 A（12 組 100 項，Claude Opus 5.5）：`~/.omnikit/status/OmniKit/reports/2026-11-27-防假完工與一用就壞-頂尖方法論調研.md`
  3. 頂尖方法論線 B（12 組 99 項，Gemini 4 Neon 重跑）：`~/.omnikit/status/OmniKit/reports/2026-11-28-防假完工與一用就壞-頂尖方法論調研-Neon.md`

---

## 1. 為什麼從 OmniKeep 到 OmniKit 一直「說完工卻一用就爆」？（6 大結構性病根）

綜合 Anthropic（2025-11 長任務 Harness、2026-03 GAN 式三角色分離）、OpenAI（Codex Harness Engineering）、Stripe（Minions Blueprints）、Mitchell Hashimoto、Simon Willison、Google Testing Blog 與開源驗收工具原始碼，單測全綠卻一用就壞並非偶然，而是以下 6 個結構漏洞同時存在：

| # | 結構性病根 | 業界定義與一手出處 | OmniKit 現有程式碼的確切破口 |
|---|---|---|---|
| **R1** | **球員兼裁判（同腦自評寬容）** | Anthropic 證實同一個生成程式碼的模型評估自己產出時極度寬容，且會在 context 快滿時提早喊完工（*Declaring Victory Too Early*） | `engine/scripts/done_check.py:24-26` 預設 `OMNIKIT_DONE_CHECK=log`（**只記錄、完全不攔截**） |
| **R2** | **只跑乾跑與開發機環境污染** | Google *Hermetic Servers*、Stripe 隔離 Devbox：開發機早裝好工具與快取，`-WhatIf` 乾跑完全碰不到真實寫入失敗 | `engine/scripts/windows-ci.ps1:22, 213-218` **全程只跑 `-WhatIf` 與 `-SelfTest`**，且假家目錄**預先塞好 Claude、Codex 與現成 profile**，結構上 100% 抓不到新電腦預設全空 |
| **R3** | **過度 Mock 的「快樂表」測試** | Google *Don't Overuse Mocks* & *Change-Detector Tests*、Fowler *ContractTest* | `.github/workflows/validate.yml:17-104` 逾 40 支腳本全靠離線假輸入 `--selftest`，跨腳本欄位與外部真 CLI 一改就脫節 |
| **R4** | **寫新漏接、刪舊留空（Unwired & Orphan Drift）** | `Doric-builder/wireline`、`sid732/loose-ends`、OpenAI *Garbage Collection Agent* | 11-16 刪掉 `advise.py` 等 12 支腳本後，沒反向掃描拆掉 `omnikit-setup` 的領域題，也沒把官方 `/doctor` 與 `claude-code-setup` 接進入口 |
| **R5** | **驗證收據無真實執行綁定** | `majiayu000/receipt`、`obra/superpowers`（★328,076） | `done_check.py:126-150` 只檢查有沒有貼一張 Markdown 表格，填「單元測試通過」就過關，不要求「端到端使用者旅程」證據 |
| **R6** | **首分鐘零狀態無人負責** | GitLab *Customer 0*、Anthropic *Clean-Slate Evaluator* | 子代理只對局部 1–2 個檔案負責，從未有獨立跨家驗收者拿空白家目錄與真實瀏覽器走過新用戶前 5 分鐘 |

---

## 2. 一次攤開、不再擠牙膏：OmniKit 全路徑現存 12 個斷層總表

我們順著**「空白新電腦／無 Claude 只裝 Codex 或 Antigravity／無既有專案新手／Fork 用戶／同事版升級／舊機手改」**從第 0 秒走到移除，現存問題一共就是這 **12 個**（7 個體驗與接線斷層 ＋ 5 個盲審底層 P0）：

### A. 使用者旅程與跨工具體驗斷層（7 項）
1. **第三方精選預裝為 0，且名冊漏掉 Antigravity**：
   - `engine/scripts/install.ps1:664` 不自動裝任何精選外掛；`engine/scripts/build.py:64` 與 `data/tools/*.yaml` 只認 `claude` 與 `codex`（漏掉 `antigravity`，且誤把 Codex 原生已內建的 `skill-creator` 標為 Claude 專屬）；`impeccable`／`bmad` 無自動安裝來源；`claude-code-setup` 躺在 `data/inbox.md:8`；`gitleaks` 同事版不裝（`install.ps1:863`）。
2. **開箱問卷半數是殭屍題目，且「無專案／第一次用 Agent」的新手缺乏起手引導**：
   - `engine/skills/omnikit-setup/SKILL.md:39-52` 仍在問已刪除功能留下的 `domains`、`evaluate_tools` 與專案填空題；而當新手電腦裡沒有現成大型 repo 時，掃描結果為空，缺少「通用滿血底座＋白話目標卡＋一鍵建新專案與破冰提示詞」。
3. **控制面板「工具」頁純唯讀，缺開箱精靈、Doctor 健康修復頁與官方工具入口**：
   - `engine/cockpit/static/index.html:105-153` 只能看名冊文字，無法勾選安裝／啟停外掛，也沒有 Doctor 檢查／修復按鈕與 `/claude-automation-recommender`、`/doctor`、`/skill-doctor`、`/init` 一鍵指令入口。
4. **無 T3 Code／無 Claude 用戶在面板按「自動對帳」直接報錯，且額度頁漏掉 Codex**：
   - `engine/cockpit/reconciler.py:27, 178-179` 寫死找 `t3` CLI 並預設派給 `gemini-4-hydrogen`；`engine/cockpit/collector.py:1426-1428` 額度頁只顯示 Claude 與 Antigravity，純 Codex 用戶打開一片空白。
5. **新電腦打開面板看不到使用者現有開發專案**：
   - `engine/cockpit/collector.py:977-1041` 只讀空的 `config.json` 與空的 `status/`，新機打開只有 `OmniKit` 自己，不會自動掃描本機常用開發目錄（如 `Desktop`、`Documents\GitHub`、`source\repos` 等）供一鍵勾選匯入，也無「建立第一個新專案」按鈕。
6. **Fork 用戶安裝會弄髒工作區導致下次鎖 tag 升級報錯卡死；缺 npm 直接擋死全套安裝**：
   - `engine/scripts/install.ps1:256-264` 的 `Sync-RepoConfig` 直接改寫 repo 內追蹤檔，導致下次跑同事版升級時被 `install.ps1:429-431` 的 dirty 檢查擋死；`engine/scripts/preflight.ps1:94` 在沒裝 Node/npm 的新電腦上直接拒絕安裝整個 OmniKit（應先裝好規則、skills、面板，僅將 Node 型 MCP 標為待安裝 Node 後啟用並附一鍵 `winget` 指令）。
7. **Codex Hook 未信任靜默失效，Doctor 卻誤判綠燈**：
   - Codex 的 `config.toml` Stop hooks 需使用者在 `/hooks` 信任才會跑（記錄於 `~/.codex/.hook-trust`），但 `engine/scripts/doctor.py:274` 只看設定檔有字串就打勾 `OK`，應核對信任狀態並誠實標示 `WARN（待執行 /hooks 信任）`。

### B. 跨家盲審 Stage 2 抓出的底層技術斷層（5 項 P0）
8. **Windows 同埠重複綁定漏洞**：`server.py` 需設 `allow_reuse_address = False` 與 `SO_EXCLUSIVEADDRUSE`，並寫入 `server.json` 供健康核對。
9. **背景同步覆蓋使用者手改**：新增 `sync.py --background` 與 `applied.json` 三向比對，手改標漂移橫幅而非靜默覆蓋。
10. **新機無 git 全域身分時 `NOW.md` 自動 commit 失敗**：已實作 `engine/scripts/status.py`（`git init -b main`＋repo 本地固定身分＋關簽章，`--selftest` 已通過）。
11. **Profile 雙軌狀態打架與存檔吃欄位**：統一以 `~/.omnikit/kit.yaml` 為主並鏡像 `profile.json`，修補 `sync.py:238` 與 `collector.py:244-255` 保留未知欄位。
12. **Agent 代跑安裝時背景伺服器被回收或卡住**：改用 WMI 脫鉤啟動 `cockpit.py launch`，CI/SSH 自動略過開瀏覽器，Origin 檢查精確比對到埠號。

---

## 3. 頂尖高手與開源工具收斂：焊進 OmniKit 的 5 道永久防假完工閘門

我們不另造龐大框架，直接挑選三份飽和調研中**零外部雲端依賴、確定性最高**的 5 個機制焊進 OmniKit（同時保護 OmniKit 自己，以及你在跑的所有專案如 OmniKeep）：

| 閘門 | 借鏡頂尖做法／開源專案 | 落地實作位置 | 擋掉什麼問題 |
|---|---|---|---|
| **G1. 不可竄改旅程清單 `journeys.json` ＋ 真實 Clean-Room E2E** | Anthropic `feature_list.json`、Stripe Devbox、`vercel-labs/agent-browser`（★54,281）、`peteretelej/smokepod` | `data/harness/journeys.json` ＋ `engine/scripts/cleanroom_e2e.py`（接進 `windows-ci.ps1` 與 `validate.yml`） | 在**完全空白的假家目錄**真跑 `install.ps1`（非 `-WhatIf`）→ 真開面板伺服器 → 用真實無頭瀏覽器（桌機＋iPhone 15 WebKit）走完一鍵套用、建專案、檢查 0 console/network error 與 0 橫向溢出 → 真跑 `doctor.py` 全綠 → 真跑 `uninstall.ps1 -Yes` 驗證 100% 還原；也測「無 Claude 純 Codex／純 Antigravity」矩陣 |
| **G2. 入口可達性與刪舊孤兒稽核 `wiring_audit.py`** | `sid732/loose-ends`、`Doric-builder/wireline`、OpenAI Garbage Collection、`jendrikseipp/vulture`（★5,009） | `engine/scripts/wiring_audit.py`（接進 `validate.py` / pre-commit / CI） | 自動檢查：(1) 名冊每個 `default`/`trial` 工具是否都有實際安裝接線；(2) 全 repo 的 `.md`、`SKILL.md`、`.ps1`、`.py` 引用的腳本路徑、CLI 旗標、skill 名是否真實存在（刪舊留殭屍立刻紅燈） |
| **G3. 反假綠燈 Diff 掃描** | `fitzyracing1/fakegreen`、`tupe12334/block-no-verify` | 併入 `engine/scripts/wiring_audit.py` 與 `harness_hooks.py` | 攔截 `git commit --no-verify`／`core.hooksPath` 繞過，並掃描 diff 是否偷加 `.skip`、空 `except: pass`、或在 CI 偷加 `\|\| true` |
| **G4. `done_check.py` 升級為分級硬攔截＋新鮮證據檢查** | Boris Cherny Stop Hook、`obra/superpowers`（★328,076）、`majiayu000/receipt`、`OthmanAdi/planning-with-files`（★28,260） | `engine/scripts/done_check.py`（預設改為分級 `block`，含 `stop_hook_active` 與上限熔斷） | **所有接上 OmniKit 的專案（含 OmniKeep）同步生效**：只要這回合改了程式／腳本／前端，Agent 喊【完成待收尾】時若回執只有 `單元／selftest` 而沒有**改碼後新鮮執行的「整合／實跑旅程」證據**，Stop hook 當場擋回不准收尾 |
| **G5. 跨家獨立「Customer-0 盲驗者」** | Anthropic 2026-03 *Planner / Generator / Evaluator*、GitLab *Customer 0* | 寫入 `omnikit-dispatch` `verify` 流程與本次改版最終驗收 | 收尾發 PR 前，派一條**零記憶、不看開發對話、不同家族模型**的子對話，只讀 `README.md` 與真實啟動的面板走完新用戶前 5 分鐘挑錯，有 Blocker 必退回修到過 |

---

## 4. 關鍵開源代表專案備忘（2026-11-28 `gh api` 實測）

- `mattpocock/skills`（★334,089，MIT）：垂直切片與 `/tdd` 紅綠循環
- `obra/superpowers`（★328,076，MIT）：`verification-before-completion` 五步實證鐵律
- `affaan-m/ECC`（★311,648，MIT）：`gateguard-fact-force` 改碼前強制查證呼叫端
- `github/spec-kit`（★152,094，MIT）／`Fission-AI/OpenSpec`（★75,877，MIT）：活規格與變更增量嚴格驗證
- `garrytan/gstack`（★142,793，MIT）：`/qa`、`/browse` 真機狗食流程與 `gstack-verify-gate` Stop Hook
- `ChromeDevTools/chrome-devtools-mcp`（★59,590，Apache-2.0）／`vercel-labs/agent-browser`（★54,281，Apache-2.0）：無頭瀏覽器真實互動與 `dogfood` 技能
- `OthmanAdi/planning-with-files`（★28,260，MIT）：Stop-hook `--gate` 五重決策與防死迴圈熔斷
- `snarktank/ralph`（★22,354，MIT）／`frankbria/ralph-claude-code`（★9,742，MIT）：`prd.json` `passes` 欄位與外層乾淨 context 迴圈
- `Q00/ouroboros`（★6,388，MIT）：不可變 Seed 規格與 Mechanical / Semantic / Multi-Model 三階段驗證閘門
- `jendrikseipp/vulture`（★5,009，MIT）／`fallow-rs/fallow`（★5,420，MIT）：靜態死碼與孤兒檔案偵測
- `majiayu000/receipt`（MIT）／`sid732/loose-ends`（MIT）／`fitzyracing1/fakegreen`（MIT）／`greenlitbooks/mustfail`（MIT）：零 LLM 確定性執行收據、入口可達性圖與反假綠燈檢查
