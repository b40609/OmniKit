# OmniKit v2 交接

日期：2026-11-05　前一段對話已滿，這份給新對話接手用。

## 目標

OmniKit v2 做給同事：裝完 → 可選的環境掃描與專案掃描 → 訪談 → 依名冊自動組出工具包 → 預覽 → 安裝 → 好用。之後持續只留有用的，有更好的選擇時通知，工作中也能主動建議，而且要比 Claude Code 做得更好。

核心主張：**不是幫你裝更多，而是只留證明有用的，而且三個 agent 一致。**

## 已完成

| 項目 | 位置 | 狀態 |
|---|---|---|
| Codex 實測（規則、skills、MCP 都讀得到） | 對話紀錄；記憶 `codex-web-gpt-proxy.md` | 完成 |
| Codex 瘦身：112 → 32 個 skill，token 少約 27% | `~/.codex/config.toml`；備份 `config.toml.bak-skills-20261104-233502` | 完成 |
| usage.py 也統計 Codex 的 plugin | commit `e27c415`，已 push，CI 通過 | 完成 |
| 定位與競品初稿 | `docs/proposals/2026-11-05-positioning.md` | 已 commit（2026-11-05 收尾，未 push） |
| 四項研究：跨 agent 同步、推薦與安裝、評估規模化、RIA | `docs/v2/research.md`；證據在 `docs/v2/research/`；RIA 的完整報告不放公開 repo，存在 `C:\Users\user\Desktop\RIA-Rebuild\OmniKit-RIA查證報告-2026-11-05.md` | 已 commit（未 push） |
| BMAD 產品簡介 | `docs/v2/brief/`（brief、addendum、.memlog） | 草稿，已 commit（未 push） |
| BMAD PRD：39 條需求，已過三項審查並修正 | `docs/v2/prd/`（prd、addendum、.memlog、兩份審查）；`docs/v2/review-editorial.md` | final（2026-11-05 §0.1 九題全部定案） |

## PRD §0.1 的決定

九題都已定案（2026-11-05），細節在 PRD §0.1 與 `docs/v2/prd/.memlog.md`：

- 第 1 題：試點期的實測用團隊情境。
- 第 2 題：名冊更新每週提醒一次，同事說「檢查更新」才連網，預覽後才套用。
- 第 3 題：回流的匯出檔與提案放 Teams 試點頻道的檔案區。頻道連結不寫進公開 repo。
- 第 4 題：解凍「規劃與開發流程」槽位，RIA 不再當比較基準。
- 第 5 題：主動建議先靜默記錄 2 週，標註為「有用」的比例達 50% 以上才打開提示。
- 第 6 題：客觀實測每週 token 上限 2,000 萬，含快取讀取。
- 第 7 題：試點期 6 週。
- 第 8 題：本機模型先用評估漏斗找候選工具，有 E3 以上的候選再決定要不要開槽位。
- 第 9 題：試點前的閘門全部通過才開始；名單到時再確認，存在 repo 外。

## 下一步（依序）

1. ~~**一次問完 §0.1 還沒決定的題目**~~：2026-11-05 完成，PRD 已改成 final。
2. ~~**先修現有的 4 個缺陷**~~：2026-11-05 完成，自我測試全過。新增「維護者版／同事版」（`engine/scripts/edition.py`），兩版只差 git hook 與免問核准：
   - 同事版不設 git hook；萬一跑到 `sync-data.sh` 也只提醒、不同步（FR-1、FR-36）。`install.ps1 -Edition maintainer|colleague`，沒指定時分版前就裝過的電腦是維護者版。
   - 免問核准每個工具問本人，記在 `%LOCALAPPDATA%\omnikit\consent.json`；`agents.py approvals` 查看、`--grant`、`--revoke`（FR-10）。
   - Codex 規則改成受管區塊，原本的留在區塊外照常生效；舊版整份換掉的自動轉成只有區塊（FR-10）。兩版都用。
   - MCP 帳本：`agents.json` 記 OmniKit 管的欄位的雜湊；被改過、被移除、同名不是 OmniKit 的就停下來問，`agents.py resolve <名稱> --use-omnikit|--keep-mine`。Codex 原地更新，工具核准紀錄與使用者加的欄位留著（FR-10）。兩版都用。
   - 這台（維護者）唯讀比對：判斷為維護者版，三個 chrome_devtools 都會直接接手、沒有衝突；下次同步時 `~/.codex/AGENTS.md` 會轉成區塊格式。
3. ~~**階段 0a**~~：2026-11-05 完成工具與第一輪實跑，自我測試全過（見下方「階段 0a 的成果」）。
   - git hook 在 linked worktree 同步錯 repo（2026-11-05 已修）：在 `.claude/worktrees/<名稱>` 裡 commit，post-commit 用 worktree 自己的 `agents.py sync`，`~/.claude/skills` 的連結、`~/.agents/skills` 的複製品與 `.omnikit.json` 都改指向 worktree，worktree 清掉後就斷。現在 `sync-data.sh` 比對 `git rev-parse --git-dir` 與 `--git-common-dir`，不同就只印一行提醒、不同步；pre-commit 的金鑰檢查與名冊驗證照跑。測試在 `edition.py --selftest`（暫存 repo 與 linked worktree，假腳本只寫記號檔）。
   - 同步層之後要補的項目（0a 沒做）：FR-36 的「檢查更新」流程（目前同事要先跑 `install.ps1 -WhatIf` 再跑 `install.ps1`）、受管區塊內容的雜湊（區塊裡的手改還是會被蓋掉）、`AGENTS.override.md` 偵測（FR-32）、Windows CI 跑 `install.ps1 -SelfTest`（FR-34）、架構地圖還沒有 `edition.py`。
4. **階段 0b（4 到 6 週）**：用漏斗處理 active 槽位與訪談會用到的槽位；找資料分析的候選工具。2026-11-05 跑完第一輪（見下方「階段 0b 第一輪的成果」）：
   1. ~~勾選 `candidates.yaml` 並寫回卡片、重跑第 0 層~~：完成。
   2. ~~`layer1.py run` 與 `clusters`~~：完成，69 張（含 0a 試跑的 3 張）。
   3. ~~`evidence.py draft --from-layer1` 與 `check`~~：完成，169 張證據卡。
   4. 煙霧測試：`context` 這一輪量了 25 張；jupyter-mcp-server 與 motherduck-mcp 已審程式碼並在沙箱交握。**還沒做**：`smoke.py run`（隔離資料夾要使用者登入）、其他有 MCP、hook 或執行檔的工具的程式碼審查與 `sandbox`。
   5. ~~資料分析~~：新增槽位與 6 張卡，4 張建議排實測。
   6. ~~第 2 層排程~~：`schedule.py` 產生提案（`data/funnel/layer2-schedule.json`），週報列得出來；重題槽位要維護者決定（見下方）。
5. **同時開發** v2.0 其他需求。分組見 PRD §6.1。
6. **調整 `4a4fc38` 的行為**：另一個 session 已推上「不評估就不裝 omnikit-eval」。PRD 的 FR-37 要求個人週報跟訪談第 5 題脫鉤。

## 階段 0a 的成果（2026-11-05）

工具都在 `engine/skills/omnikit-eval/scripts/`（安裝相關的在 `engine/scripts/`），每支都有離線 `--selftest`，已加進 CI；結果放 `data/funnel/`，格式見 `engine/skills/omnikit-eval/contracts/`。

| 需求 | 工具 | 這台實跑 |
|---|---|---|
| FR-22 第 0 層 | `batch0.py`：gh 或 `GITHUB_TOKEN`、GraphQL 一批 12 個 repo；H1 到 H6、A4、相容線索；只淘汰四種，其他標旗標；每週星數快照 | 116 張 3 分鐘：通過 56、只標旗標 4、淘汰 1（open-deep-research 已封存）、未知 44、內建 11。第一份快照 `data/funnel/stars/2026-11-05.json`，爆紅從下週起算得出來 |
| FR-22 補 url | `candidates.yaml`：同名唯一而且星數最多（至少 50 星）或符合括號擁有者才自動採用；名稱包含、星數是其他的 10 倍以上只當建議 | 44 張待勾選，其中 15 張有建議（`--accept-suggested`）。第一版規則把 gsd、tavily、hn-algolia 配到冷門同名 repo，已改掉 |
| FR-23 第 1 層 | `layer1.py`：Claude Haiku、`--tools ""`、`--setting-sources ""`，README 當資料；記槽位與情境、可查證主張、內建涵蓋、相似群組 | 試跑 3 張，每張約 1.6 萬輸入 token；agent-browser、codegraph 建議排實測，floorplan 先收著。有認出 README 裡的提示注入 |
| FR-23 證據卡 | `evidence.py`：GitHub issue（90 天內有更新）與 HN；引用最多 15 個字、到期最多 90 天；算 E0 到 E2 與排除效果 | agent-browser 8 張（6 張是已關閉的舊 issue，已過期） |
| FR-24 第 1c 層 | `smoke.py`：`env`、`login`、`context`（零 token）、`run`（真實非互動）、`sandbox`（Windows Sandbox） | 見下方 |
| FR-35 | `engine/scripts/preflight.ps1`，install.ps1 第 0 步（`-WhatIf` 也跑）；`-SkipCheck` 略過已自己處理的項目 | 7 項全過；PS 5.1 與 7 都測過 |
| FR-11 doctor | `engine/scripts/doctor.py`：寫入檢查照 agents.json 與 install-record.json，清單用 `claude mcp list`、`codex mcp list --json`、`agy mcp list` | 通過 17、失敗 0、未知 3（三個 agent 都沒有列 skill 的指令） |

隔離環境實測（FR-24 的 `[ASSUMPTION]` 有答案了）：

- **Windows Sandbox 可用**：`wsb start` 不開視窗，`wsb exec -r System` 執行、輸出經共用資料夾取回；啟動到結束約 45 秒。沙箱裡沒有 git 與 node，連得到 GitHub。chrome-devtools-mcp@1.12.0 在沙箱裡裝好並做 MCP 交握共 124 秒：32 個工具、定義 29,661 bytes。Node 固定 v24.22.1 並核對 SHA256。
- **WSL2**：功能已啟用，但這台沒有任何發行版，暫不支援。
- **獨立設定資料夾**：Claude 用 `CLAUDE_CONFIG_DIR`、Codex 用 `CODEX_HOME`，兩邊都要另外登入。
  - worktree 要放在使用者資料夾外（預設 `C:\omnikit-eval`），不然 Claude 會往上讀到 `~/.claude/CLAUDE.md`。
  - Codex 仍會讀 `~/.agents/skills`（覆寫 USERPROFILE 無效），要在隔離的 config.toml 逐一 `[[skills.config]] enabled = false`。
  - 從 agent 裡執行時，要清掉外層的 `ANTHROPIC_BASE_URL`、`CLAUDE_CODE_*` 等環境變數，不然基準會多出桌面版的工具。
- **零 token 量 context**：API 位址指向本機攔截伺服器，比較有裝與沒裝的請求大小。基準 Claude 約 99 KB、Codex 約 70 KB；caveman 讓 Claude 每回合多 4,970 bytes（約 1,243 token）、Codex 多 6,832 bytes（約 1,710 token）。

還沒做到、或要使用者處理的：

- `smoke.py run`（有沒有被叫用、非互動能不能跑）還沒實跑：隔離資料夾要使用者登入一次（`smoke.py login` 印出做法），沒登入時記「未知」。
- 有 hook、MCP 或執行檔的工具，`run` 要先做程式碼審查（強模型），審查過加 `--reviewed`；審查流程本身還沒工具化。
- Antigravity 還沒納入煙霧測試（`agy -p` 有非互動模式，可以照 Claude 的做法補）。
- 第 0 層還沒做：A1 下載數只看 npm 來源、A2 被依賴與 A3 策展沒做；H7 的 skills.sh 稽核與 MCP Registry 沒接（單張卡可以用 `layer0.py --scan`）。
- 新的自我測試只在 Windows 跑過，Linux（CI）要 push 後才知道。

## 階段 0b 第一輪的成果（2026-11-05）

名冊變動：

- 「規劃與開發流程」槽位解凍，改成 active（PRD §0.1 第 4 題）；spec-kit、pullboard 卡片裡「凍結中」的註記一併改掉。
- 新增「資料分析」槽位（active，情境 A1 探索分析大檔、A2 改 notebook 後重跑）與 6 張卡：native-data（default，比較基準）、jupyter-mcp-server、anthropic-data、scientific-agent-skills（只取 7 個資料分析 skill）、motherduck-mcp、marimo-skills。
- 情境 id 一開始用了 D1，跟「文件與簡報」的 D1 撞號，讓 8 張卡的第 1 層判讀混亂；已改成 A1、A2 並重跑。`validate.py` 現在會擋跨槽位重複的情境 id。

漏斗結果（都在 `data/funnel/`）：

| 層 | 結果 |
|---|---|
| 第 0 層 | 41 張寫回 url（5 張確認不在 GitHub 填 none；browserbase、mcp-registry 原本就有官網網址，不覆蓋）。122 張：通過 94、只標旗標 10（停滯 8、冷卻期 2）、淘汰 1（open-deep-research 已封存）、未知 5、不適用 12 |
| 第 1 層 | 69 張（含 0a 試跑的 3 張）：建議排實測 35、先收著 18、建議拒絕 16；7 個相似群組（`clusters.json`）。資料分析 4 張建議排實測（jupyter-mcp-server、motherduck-mcp、scientific-agent-skills、marimo-skills），符合 FR-6 的「至少 2 張」 |
| 證據卡 | 169 張，其中 40 張建立時就過期（見下方「已知問題」）；只有 codex-security 到 E1，沒有 E2，也沒有可以查證的負面證據 |
| 煙霧測試 context | 這一輪 25 張量到每回合增加的 context（Claude 基準約 99 KB、Codex 約 70 KB）。最重的是 ECC（935 個 skill，Claude 多約 6,273 token）、alirezarezvani、moai-adk、jeffallan（各約 6,000 token）；最輕的是 ce-handoff（52 token）、graphify（92 token）、karpathy-guidelines（127 token） |
| 程式碼審查與沙箱 | jupyter-mcp-server 2.2.4：可以在本機加 --reviewed 跑；啟動要加 `--start-new-code-sandbox false`；沙箱交握成功，18 個工具、定義 41,866 bytes。motherduck-mcp 1.1.0：可以在本機加 --reviewed 跑，但 DuckDB 要用 `--init-sql` 鎖住檔案存取與 extension；沙箱交握成功，4 個工具、定義 2,914 bytes。沙箱用固定版本的 uv 0.12.10（核對 SHA256） |
| 第 2 層排程提案 | 11-09 那週：behavior-rules 客觀題（addy-agent-skills、alirezarezvani）加 frontend-design 兩組盲選；11-16：behavior-rules（ecc、ponytail）；11-23：output-compression、tool-discovery、code-understanding、browser；11-30 與 12-07：data-analysis 兩組；12-14：review。排不進 11 組（dev-workflow 8、memory 3） |

實際 token 用量：

| 項目 | 模型 | 輸入（含快取） | 輸出 |
|---|---|---|---|
| 第 1 層第一輪（63 張） | Haiku | 950,280（快取 240,110） | 275,337 |
| 第 1 層重跑（撞號 8 張與失敗 3 張） | Haiku | 168,037（快取 40,634） | 47,209 |
| 證據卡第一輪（24 張） | Haiku | 沒記到：程式中途以 exit 3 結束，沒印出合計 | 沒記到 |
| 證據卡補跑（11 張） | Haiku | 59,334（快取 47,513） | 22,611 |
| 程式碼審查（2 個 MCP） | 強模型子代理 | 合計 342,790（子代理只回報總數） | 含在左欄 |
| context 量測與沙箱 | 不呼叫模型 | 0 | 0 |

記到的合計約 186 萬 token。第 1 層原本估 90 萬，實際約 144 萬；第一輪有 3 張結構化輸出重試失敗，那幾次的用量也沒記到。

要維護者決定的：

1. **重題槽位排不進每週上限**：memory 與 dev-workflow 照估算每組約 4,680 萬 token（每次 390 萬 × 3 次 × 2 組 × 2 個 agent），超過每週 2,000 萬。可以：把 M1、V1 縮成中型題（每次約 100 萬，一組約 1,200 萬）、只跑試點同事用的那個 agent、或讓一組跨兩週的額度。
2. `data/funnel/schedule.yaml` 把資料分析的痛點手動設成 3（新槽位，試點前要有實測過的候選）；不設的話會排到最後。
3. 第 1 層把 mattpocock-skills 歸到 frontend-design（F2），所以排進了盲選；不合理就從那組拿掉。
4. 第 1 層有 52 張卡附了要維護者決定的問題（`data/funnel/layer1/<id>.json` 的 `needs_user`），例如集合要整包評還是只評子集、ponytail 與 planning-with-files 的 hook 每回合注入能不能接受。排到該槽位的實測前再處理即可。
5. 登入兩個隔離設定資料夾（`smoke.py login`），才能跑 `smoke.py run`。

已知問題（之後修）：

- 證據卡的到期日從發佈日算，但收集時看的是「90 天內有更新」，所以舊 issue 一建立就過期（40 張）。
- `evidence.py draft --from-layer1` 第一輪跑到第 24 張時以 exit 3 結束，沒有任何輸出；補跑同樣的卡沒有再發生，原因不明。合計 token 只在最後才印，中途結束就沒有紀錄。
- `smoke.py context` 量不到只在 marketplace 定義、沒有 `.claude-plugin/plugin.json` 的 plugin（claude-lsp、feature-dev），也量不到純 CLI 或 MCP 的工具（task-master 0 個 skill）；這些要用 `sandbox` 或手動量。
- 已修：`smoke.py` 遇到三個以上同名 skill 會出錯（claude-mem、ECC）；`layer1.py run --max 0` 被當成不限張數。

## 要實測才能確定的

- Antigravity 的 hook 訊息，使用者看不看得到。
- `agy` 讀取 skill 的位置：`~/.agents/skills`，還是 `~/.gemini/antigravity-cli/skills`。
- ~~隔離環境~~：Windows Sandbox 可用；WSL2 沒有發行版（見上）。
- Codex 的 `tool_suggest.discoverables` 能不能觸發原生的安裝建議。

## 不要重做

- 四項研究都已完成，關鍵主張也抽查過原始碼與論文。直接用 `docs/v2/research.md`。
- Codex 已經實測過。Codex 連不上時，先看 Codex Web GPT（127.0.0.1:17841）有沒有在跑，見記憶 `codex-web-gpt-proxy.md`。
- BMAD v6.12.4 的流程已經跑過，對應 commit `bab9082`。之後要更新 PRD，照 bmad-prd 的 Update 模式做：先讀 `.memlog.md`，再改，並把改動寫回 memlog。

## 注意

- OmniKit 是公開 repo。同事的個人資料、RIA 的內部細節都不要 commit。
- push 只在使用者明確指示時做。
