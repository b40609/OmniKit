# 自我迭代的 OmniKit：雙向閥門、常駐預算棘輪與 Anti-Hobbling 減法架構

- 日期：2026-11-26
- 狀態：使用者已回覆「同意建議 請執行」定案（D1–D5 全採推薦方案）；P0 與核心護欄（常駐瘦身、補丁旁註、預算棘輪、到期與世代錨點檢查、絆線命中計數、盲審中性目錄隔離）於同日落地；3 個新 runtime hook 試點依既有凍結規定排於 2026-12-01 解凍執行。
- 統整與審查：主線 Gemini 4 Carbon (`thought_level=high`) × 跨家兩階段防迎合盲審 Claude Fable 5.2 (`effort=high`)。

## 1. 定案決策（D1–D5）

1. **D1 範圍與節奏**：採**小核心先行、先減後加**。不蓋背景爬蟲或自動改檔引擎；先做零成本體檢與常駐瘦身，再上預算棘輪、到期檢查、絆線計數與手動裸模型對照，其餘功能設明確解鎖條件。
2. **D2 常駐預算強度**：採 **Bytes 預算棘輪（`data/rules/budget.yaml`，由 `validate.py` 與 `doctor.py` 守門）**。超標時 CI 阻斷，除非同一 commit 顯式調高上限檔；每次減肥後將上限下調扣緊。若 P1 期間因合理契約新增被迫調高 >= 3 次，再檢討降為軟警告。
3. **D3 消融測試工具**：Plugin / Skill 型優先使用官方 `claude plugin eval --ablation with-without` 與手動雙目錄對照，不提前改寫封鎖了檔案與指令工具的 `layer2.py`，也不預包易隨上游旗標漂移的薄殼。
4. **D4 整包清零測試**：排入 P2（以使用者過目、先於受測物修改定稿的約 10 題真實原句黃金題，對照「只留安全紅線 Hook 的裸模型」與「完整掛載 OmniKit」）；若零成本體檢後可疑補丁 <= 3 條則改單項對照。
5. **D5 盲審與評測記憶隔離**：實測確認 `claude-mem` 同時經 `SessionStart` 與 `PreToolUse:Read` 雙通道注入觀察標題，任務首行文字標記無效。為遵守「全自動模式主控不跨目錄讀寫」規定，派送盲審時改指定 T3 的「No project」（由 `t3_project_list` 查得對應 `~/.t3/scratch` 之 `projectId`，傳入 `create_threads` / `t3_thread_launch` 或 `t3 thread start <No-project-id>`）建立獨立 Scratch 對話並將輸入證據透過訊息傳入（S1 實測 `SessionStart` 無記憶，`PreToolUse:Read` 在 Scratch 下是否零注入標【待驗證】）；中期視頻率決定是否配置無記憶外掛之乾淨 Claude 實例。

## 2. 綜合最佳做法：兩個正交維度解開頂尖工程師的表面矛盾

綜合 Anthropic（Barry Zhang & Mahesh Murag、Boris Cherny 2026-07-27 YC 逐字稿、Cat Wu & Thariq Shihipar、Diane Sarkis、Addy Osmani）、Vercel、OpenAI Codex、Matt Pocock、HumanLayer、Pi（Mario Zechner & Armin Ronacher）、Thorsten Ball、Mitchell Hashimoto、Geoffrey Huntley、IndyDevDan 一手實證：

### 2.1 依「補什麼」決定生命週期（三分類）

| 分類 | 本質 | OmniKit 對應 | 退場與演化法則 |
|---|---|---|---|
| **紅線（Safety）** | 擋不可逆傷害與合規底線 | 刪檔／外發先問、禁實盤下單、不印金鑰 | **永不因模型變強而退役**；只往下沉成確定性 Hook，文字縮成一行指向 Hook。 |
| **契約（Contract）** | 模型猜不到的個人偏好與私有約定 | 繁體中文、狀態標籤、禁 LaTeX、分派實例 | 只在使用者改主意時變動；刪掉「90% 對但 10% 錯」的死命令與範例，能機械檢查的下沉成 Hook。 |
| **補丁（Patch）** | 補償當代模型的能力短板或壞習慣 | 飽和調研、說做不到先查、Antigravity 收尾 `.done` | **半衰期僅 1–3 代模型（約 6 個月）**；登記於 `data/rules/patches.yaml`，主力模型換代即接受消融檢驗。 |

### 2.2 依「觸發性質」決定四層靜態歸宿

| 層級 | 載體 | 合法居民 | 禁放內容 |
|---|---|---|---|
| **L0 確定性機械層** | `PreToolUse` / `Stop` Hooks、Linter、CI | 零例外紅線、機械格式與指令規範（錯誤訊息自帶修法） | 需語意權衡的架構品味 |
| **L1 常駐水平索引層** | `CLAUDE.md` / `AGENTS.md`（受 `budget.yaml` 棘輪管控） | 幾乎每輪都會碰到且漏載會靜默出錯的水平地圖、核心溝通契約 | 可用 Hook 擋的規則、特定領域長規範（如 `mobile-web`）、舊模型步驟補丁 |
| **L2 按需垂直技能層** | `engine/skills/`（`SKILL.md` + 確定性腳本）與薄 CLI | 有明確觸發時機的多步驟工作流、領域踩坑紀錄、設計規範 | 公共常識、肥大常駐 MCP |
| **L3 狀態與驗證背壓層** | `NOW.md` + 隔離驗證／平行檢索 Subagent | 跨對話完工核取清單；僅限 Context 防火牆／獨立盲審／平行探索的子代理 | 依組織部門切分的常駐專用 Agent |

## 3. 架構機制與防呆規定

1. **入口閥（實證加法）**：不解析對話紀錄；同類糾正在不同對話出現 >= 2 次（安全類 1 次，多步驟流程第 3 次）才升級提案。去向依序問：`程式設計防呆 -> Hook/Linter -> 1 行常駐契約 -> 按需 Skill`。提案固定記錄來源事件並排除外部網頁／MCP 內容（防 Trajectory Poisoning），人點頭才寫入。
2. **Hook 絆線三段式退役**：擋人型 Hook（`harness_hooks.py`、`claim_check.py` 及後續試點）在真實階段攔截時記錄輕量命中計數（由 `doctor.py` 彙總，對話內不跨目錄讀取）。退役順序：**先縮常駐文字留 Hook 絆線 -> 模型換代後絆線一整世代 0 命中 -> 再拆 Hook**。
3. **出口閥（Anti-Hobbling 減法）**：
   - **觸發點**：主力角色模型代號變更（掛接 12-01 上線之 `NOW.md` 新模型差異出口）、規則內 `<!-- review_on: YYYY-MM-DD -->` 到期（Codex 與 Antigravity 同步時由 `profiles.py` 自動剝除註解零額度消耗；Claude Code 直接 `@import` 原檔保留短行尾註解）、工具卡 `trial_until` 到期、或 180 天保底。
   - **考題分離硬規定**：效果黃金題（上限約 10 題）必須取自真實歷史請求且先於受測物修改定稿，嚴禁寫提案的同一段對話自己出效果考題。
4. **預設砍掉條件**：
   - 預算棘輪連續 3 次僅調高上限而無對應減肥 -> 提請降為軟警告或移除。
   - 收尾記糾正掛上 3 週無任何條目走到提案 -> 移除該提示。
   - 到期檢查列出的項目連續 2 次被略過 -> 檢討移除。

## 4. 明確不做清單（Non-goals）

- 不做無監督自動改寫規則或 Skill（Hermes / SkillOpt 夜間自動改檔）。
- 不寫對話紀錄解析器、不重建 `signals.py`。
- 不加 GitHub Actions `schedule:` 或本機日曆報告。
- 不自造通用 Skill 評測沙盒、不提前包 `ablate` 薄殼。
- 不對安全紅線做以退役為目的的消融。
- 在 `on_demand` 工具卡未滿 5 張且未發生找不到備案前，不另蓋第二套召回路徑（沿用既有 `omnikeep-review`）。
- 不做螢幕錄製轉 Skill（避開憑證入鏡與實體桌面紅線）。
