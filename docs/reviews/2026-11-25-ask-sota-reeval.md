# 問法庫（`omnikit-ask`）設計必要性重審與業界頂尖做法飽和調研

日期：2026-11-25  
起因：使用者檢視近兩週真實對話盲評結果（`with_skill` 4 勝 vs `without_skill` 4 勝 vs 平手 2）後指出「差異沒有很明顯」，質疑業界是否有這種「情境問法百科」用法、該設計是否有必要，並要求對照業界頂尖（SOTA）做法。

---

## 一、直球結論

1. **你的直覺完全正確：業界頂尖（SOTA）沒有人在做「73 條情境百科全書教你怎麼問 AI」這種 Skill。**
2. **「問法庫（`omnikit-ask`）」這個設計在 2026 年前沿模型（Claude 5 / Gemini 4 / Codex）上已無存在必要。**
   - 外部唯一公開實測同類「思考框架／問法百科」的專案 `tjboudreaux/cc-thinking-skills`（★1,771），測完 28 個 skill 後在 README 坦承 **`no automatic-retain verdict`**（無一達到自動留存門檻）。
   - OmniKit 自己前後跑了 **3 次獨立實測**（外部真實對話 41 題、微縮壞專案多輪 26 段、你本人近兩週真實對話 10 題），三次結果完全一致：**裝與不裝幾乎沒差（勝率 50:50、多輪修好率同為 100%）**，甚至偶爾誤觸發說教或洩漏內部檔案路徑，每回合還固定消耗所有 Agent 的 skill description 上下文。
3. **業界頂尖怎麼解決「需求沒想清楚／不知道怎麼開口」？**
   - 不是「AI 吐一段問法範本教你重貼」，而是 **「Agent 反過來訪談使用者（Interview-to-Spec）＋ 唯讀規劃硬閘門（Plan Mode）」**。
   - 官方已原生內建（Claude Code `AskUserQuestion` + `/plan`、Cursor `Plan Mode`、Antigravity 原生 `/grill-me` + `/plan` + `ask_question`、Codex `/plan`）。
   - 開源社群星數最高（★32 萬～★33 萬、安裝逾 160 萬次）的做法是**極簡互動協定**（如 `mattpocock/skills` 的 `/grill-me` 全文僅 5 句話，且設 `disable-model-invocation: true` 只在人主動呼叫時啟動），絕不寫幾千行的領域常識百科。

---

## 二、為什麼當初（11-17）會做出 `omnikit-ask`？歷史盲點對帳

回查本機紀錄（[2026-11-17-guide-and-playbook.md](../proposals/2026-11-17-guide-and-playbook.md#L183-L255)）：

1. **11-17 的調研其實「未飽和」，且把五種不同東西混成一題**：當時跑滿 15 組上限仍未收斂，因為同時混查了提示詞改寫、思考框架、新手課程、起手包、團隊上手套件。
2. **提案自己寫了警訊，實作卻走偏成大百科**：
   - 11-17 提案第 5.2 節其實已查到 `cc-thinking-skills` 實測沒過，並明寫：「不要做成一大包思考框架……第 0 版要比三組：直接問、官方那一句、`/grill-me`，不是先自己寫一份。」
   - 結果後續實作未做 `/grill-me` 對照，反而擴寫成 **73 個情境、10 個分類檔（`situations/*.md`）的靜態問法百科**，之後一週陷入沉沒成本（反覆修補退步題與評測腳本）。
3. **OmniKit 三次自家實測數據全紀錄**：

| 實測批次 | 題目規模與來源 | 有 `omnikit-ask` | 無 `omnikit-ask` | 實測結論 |
|---|---|---|---|---|
| 11-18 外部真實對話（[報告](2026-11-18-ask-eval-real.md#L9-L18)） | `SWE-chat` 上游 41 題真實對話 | 總分 `0.60`；卡住題 `0.76` | 總分 `0.55`；卡住題 `0.76` | **卡住題差距為 0**；直接糾正題還出現 45% 誤叫用變成說教 |
| 11-18/19 多輪壞專案沙盒（[報告](2026-11-19-ask-eval-skillfix.md#L37-L44)） | 13 個微縮真專案 × 2 次（26 段多輪對話） | 修好 `26/26`；平均 `1.88` 輪 | 修好 `26/26`；平均 `1.92` 輪 | **修好率同為 100%**，輪數差 `-0.04` 在雜訊內；僅純需求缺漏題先反問有幫助 |
| 11-25 近兩週本人真實對話（[報告](../../data/evals/2026-11-25-ask-disagreement-review.md#L28-L35)） | 本人跨 5 專案 10 題脫敏原句（跨家雙盲評審） | **4 勝**（通過率 90%） | **4 勝**（通過率 80%），平手 2 | **盲評勝負 4:4 打平**；`with` 還有 2 題把問法庫內部路徑貼進回覆被扣分 |

---

## 三、業界頂尖（SOTA）做法飽和調研與四大流派比較

本次針對單一收斂子題 **「Coding Agent 面對需求模糊或使用者卡住時的需求澄清與互動對焦機制」** 依 `omnikit-research` 執行 10 組多管道檢索，共納管 73 個相關工具／專案（星數與授權皆為 `2026-11-25 gh api` 一手實測）：

### 1. 四大流派全景對照

| 流派 | 代表產品／開源專案（2026-11-25 `gh api` 實測） | 核心運作方式 | 業界採用度與實證評價 |
|---|---|---|---|
| **A. 靜態情境問法百科／思考框架集**（`omnikit-ask` 現況） | `tjboudreaux/cc-thinking-skills`（★1,771，MIT）；各類 `prompt-coach` 小專案（★0～★107） | 預寫幾十種情境指南與提問模板，靠 skill description 自動觸發，教使用者怎麼問或照表回答 | **邊緣化／實測未過**：前沿模型已內建通用軟體工程常識（Anthropic 2026-07 將 Claude Code 系統提示砍掉逾 80% 不退步）；公開 A/B 與本機三次實測皆無顯著淨增益 |
| **B. 自動攔截改寫 Hook**（Prompt Improver） | `severity1/claude-code-prompt-improver`（★1,975，MIT）；`chengzhongwei/Prompt-sensei`（★107，Apache-2.0）；`GaZmagik/claude-prompt-improver`（★4，MIT） | 掛載 `UserPromptSubmit` hook 攔截每次輸入，若判定模糊就強制追問 1～6 題或背後改寫 prompt | **小眾且具摩擦成本**：星數不到主流工作流 1%；社群（Reddit `r/ClaudeCode`）常反映快速實驗時被強制攔截盤問造成節奏中斷（agent fatigue）（社群討論，體感比例待驗證） |
| **C. 官方原生互動原語 ＋ Plan Mode**（內建零安裝） | Claude Code（`AskUserQuestion` + `/plan`）；Cursor（`Plan Mode` 澄清問答 + 虛擬計畫檔）；Antigravity（原生 `/grill-me` + `/plan` + `ask_question`）；Codex（`/plan`） | 鎖定寫檔權限（唯讀探索 codebase），透過原生結構化選擇題 UI 反問缺漏決策，核准計畫才動手改檔 | **業界基礎標配（SOTA 1）**：零額外 context 負擔、UI 互動體驗最佳（點選單選／多選題即可，不用複製貼上問法句子） |
| **D. 極簡「反向拷問／規格訪談」協定 Skill**（Spec-First Interview） | `mattpocock/skills` `/grill-me`（★332,579，MIT，skills.sh 裝 160.9 萬次）；`obra/superpowers` `brainstorming`（★326,237，MIT）；`github/spec-kit`（★151,341，MIT）；`garrytan/gstack` `/office-hours`（★142,617，MIT）；`addyosmani/agent-skills` `interview-me`（★120,336，MIT）；`Fission-AI/OpenSpec`（★75,696，MIT） | **不教使用者寫提示詞**，而是規定 Agent 扮演嚴格架構師：1) 程式碼查得到的事實自己查、禁問人類；2) 決策沿決策樹一次問一題並附推薦答案；3) 共識寫成規格檔簽核前嚴禁改 code | **開源社群絕對主流（SOTA 2）**：星數是流派 A/B 的 **150 倍以上**。關鍵在於「短而硬的互動協定」而非「長篇領域知識百科」 |

### 2. 頂尖專案怎麼寫？以安裝量第一的 `/grill-me` 為例

`mattpocock/skills` 的 `grill-me/SKILL.md`（★332,579，skills.sh 安裝 1,609,476 次）核心全文僅 5 句話，且設定 `disable-model-invocation: true`（平常不自動亂跳出來說教，只有使用者想對焦時主動呼叫）：

1. 針對計畫或想法沿決策樹逐一訪談使用者，直到達成共識。
2. 每一題都必須附上 Agent 根據現況建議的答案（讓使用者點頭或微調即可，不必從零思考）。
3. 一次只問一題（或當前決策邊界）。
4. **只要能透過探索 codebase 查到的事實，Agent 自己去查，不准問使用者**（事實歸 Agent 查，決策歸人類拍板）。
5. 達成共識前不寫程式。

對比之下，`omnikit-ask` 寫了 73 個情境（從 CSS 圓角、資料庫遷移、簡報文字牆到合併衝突），95% 都是 Gemini 4 與 Claude 5 本來就會的常識，真正有用的其實只有上面那 4 條「事實自己查、決策附建議先問、沒對齊不動手」的互動原則——而且 Antigravity 甚至已經把 `/grill-me` 直接內建為官方斜線指令。

---

## 四、`omnikit-ask` 拆解與處置方案比較

盤點目前 `engine/skills/omnikit-ask/` 目錄內的實際內容：
- `SKILL.md` + `situations/*.md`（10 檔、73 條情境問法百科）+ `SOURCES.md`：**與模型內建能力高度重疊，三次實測無顯著效益**。
- `features.md`（Claude Code / Codex / Antigravity 三家官方指令對照表，如 `/clear`、`/btw`、`/compact`、`/doctor`）：**唯一有一手核對價值的跨工具查表資料**，本質上屬於「本機工具與官方功能參考」（對應 `omnikit-capabilities` 或 `docs/`），不屬於問法庫。

| 方案 | 具體做法 | 優點 | 缺點／取捨 |
|---|---|---|---|
| **方案 A（推薦）：直接退役刪除 `omnikit-ask`，零多餘包裝** | 1. 刪除 `engine/skills/omnikit-ask/`（將唯一有查表價值的 `features.md` 移至 `docs/cli-features.md` 留存備查），同步更新名冊與文件並跑 `sync.py`。<br>2. 日常卡住或需求模糊時，直接用官方原生 `/plan`、Antigravity 內建 `/grill-me`、Claude `AskUserQuestion`。<br>3. 封存或清理不再需要的 `data/pilot/ask-eval/` 龐大測試包袱。 | 最符合精簡原則與實證結論；每回合省下三家 Agent 的 skill description 上下文；零誤觸發、零維護成本。 | 在 Claude Code / Codex 中若想打 `/grill-me` 需用 `/plan` 或講一句「先問我問題對齊再動手」（見方案 B）。 |
| **方案 B：砍掉 73 條百科，換成 15 行極簡手動 `/grill-me`（或直接裝 `mattpocock/skills` 的 `grill-me`）** | 刪除 73 條情境百科，只留一個設為 `disable-model-invocation: true`（不自動攔截日常對話）、僅 15 行的純中文訪談協定 skill（事實自己查、決策附建議一次問完、對齊寫入 `NOW.md`／規格前不動手），讓 Claude Code 與 Codex 也能跟 Antigravity 一樣手動呼叫。 | 對齊業界 ★33 萬星 SOTA 做法；平常 `0` 誤觸發，你腦袋卡住想被追問對焦時三家都有同一個指令可用。 | 多維護一個 15 行小 skill（在 Antigravity 裡與官方內建 `/grill-me` 名稱相近，可取名 `omnikit-grill` 或直接用官方）。 |
| **方案 C：維持現狀保留 `omnikit-ask`** | 保留 73 條情境問法庫，僅小修不貼內部路徑。 | 不用改名冊。 | 違背三次實測證據與業界 SOTA 共識，繼續背負 2,000+ 行無明顯增益的規則與上下文成本（不建議）。 |

---

## 五、飽和式調研帳本紀錄（依 `omnikit-research` 規範必附）

### 1. 納入標準與範圍
- **子題**：針對 Coding Agent 使用者「需求模糊／不知道怎麼開口」的互動式需求澄清、規格訪談（Spec Interview / Grilling）或提示詞教練／改寫工具與技能。
- **納入標準**：專為軟體開發／Coding Agent 設計的需求澄清互動技能、規格訪談框架、提示詞攔截增強 hook 才計入；排除圖片生成提示詞增強器（如 ComfyUI / Hunyuan T2I enhancer）、通用聊天角色詞庫與純 CLI 輸入元件庫（如 `inquirer.js`）。

### 2. 管道與每組關鍵字（`sweep.py status --min-stars 1000` 輸出）

- **查核管道**：每組皆跑齊 `github-topic`、`github-keyword`、`awesome`、`skills-sh`、`npm`、`mcp-registry`、`hn`、`exa`，並搭配中文網頁搜尋（`web-zh` 第 1、10 組）、英文網頁搜尋（`web-en` 第 2–9 組）、`producthunt`（第 4 組 `site:producthunt.com`）與 `related`（對 `mattpocock/skills`、`obra/superpowers` 抽高星 fork 與 README 連結）。
- **收斂與停止狀態**：共執行 **10 組關鍵字**，總計 **73 個不重複相關名字**。
  - 全部名字連續無新增數：**連續 2 組沒有新名字**（第 9、10 組為 0 新增）。
  - ★1,000 以上 GitHub repo 連續無新增數：**連續 4 組沒有新的**（第 7、8、9、10 組皆無新的 ★1,000+ 專案，超過 3 組門檻），`sweep.py status --min-stars 1000` 判定 **「可以停（長尾未飽和）」**（註：★1,000 以下的小型個人 repo 與無星數商業網頁產品不保證窮盡）。
- **逐組關鍵字紀錄**：
  1. `不知道怎麼問 需求釐清 問法`（新 10，★1,000+：`mattpocock/skills`、`obra/superpowers`、`pcvelz/superpowers`、`openai/plugins`）
  2. `clarifying questions interview spec coding agent`（新 7，★1,000+：`gotalab/cc-sdd`、`anthropics/skills`）
  3. `interactive requirement elicitation specification interview`（新 17，不含 AI/agent 一般工程說法；★1,000+：`github/spec-kit`、`Fission-AI/OpenSpec`、`addyosmani/agent-skills`）
  4. `prompt improver prompt coach claude code`（新 15，含 Product Hunt；★1,000+：`severity1/claude-code-prompt-improver`、`bmad-code-org/BMAD-METHOD`、`tjboudreaux/cc-thinking-skills`）
  5. `grill-me interview-me brainstorming skill`（新 7，從前輪結果新詞擴展；★1,000+：`garrytan/gstack`）
  6. `socratic questioning software specification`（新 9，從前輪結果新詞擴展；★1,000+：`giancarloerra/socraticode`）
  7. `spec-first interview workflow developer`（新 5，★1,000+：**0 個**）
  8. `prompt enhancer hook clarifying questions`（新 3，★1,000+：**0 個**）
  9. `askuserquestion interview mode claude`（新 **0 個**，★1,000+：**0 個**）
  10. `規格驅動 反問 需求對焦 coding`（新 **0 個**，★1,000+：**0 個**）

### 3. 查不到與受限的管道
- 第 1、10 組純中文關鍵字在 `skills.sh`（去停用詞後無英文字母）與官方 `mcp-registry`（僅比對 3 字元以上英文字串）回傳不查詢，已由英文同義組（第 2–9 組）與中文網頁搜尋（`web-zh` + `exa`）完整覆蓋。
- Product Hunt 官方 API 需開發者 token，依規範改用 `site:producthunt.com` 網頁搜尋覆蓋。
- 閉源商業 IDE（如 Cursor、Windsurf）內部觸發 Clarifying Questions 的系統提示詞未公開原始碼，其具體分類邏輯標為「待驗證」，僅引用官方公開文件說明之 Plan Mode 行為。

### 4. 主要專案 `sweep.py verify` 一手實測數據（查詢日期：2026-11-25，`gh api`）

| Repo | Stars | 授權 | 封存 | 最後 Push |
|---|---:|---|---|---|
| `mattpocock/skills` | ★332,579 | MIT | 否 | 2026-11-25 |
| `obra/superpowers` | ★326,237 | MIT | 否 | 2026-11-24 |
| `anthropics/skills` | ★200,250 | 無（多授權混合） | 否 | 2026-11-16 |
| `github/spec-kit` | ★151,341 | MIT | 否 | 2026-11-24 |
| `garrytan/gstack` | ★142,617 | MIT | 否 | 2026-11-25 |
| `addyosmani/agent-skills` | ★120,336 | MIT | 否 | 2026-11-24 |
| `Fission-AI/OpenSpec` | ★75,696 | MIT | 否 | 2026-11-25 |
| `bmad-code-org/BMAD-METHOD` | ★55,725 | NOASSERTION | 否 | 2026-11-25 |
| `openai/plugins` | ★8,365 | 無 | 否 | 2026-11-18 |
| `gotalab/cc-sdd` | ★3,779 | MIT | 否 | 2026-10-22 |
| `giancarloerra/SocratiCode` | ★3,382 | AGPL-3.0 | 否 | 2026-11-22 |
| `severity1/claude-code-prompt-improver` | ★1,975 | MIT | 否 | 2026-10-01 |
| `tjboudreaux/cc-thinking-skills` | ★1,771 | MIT | 否 | 2026-08-07 |
| `pcvelz/superpowers` | ★1,330 | MIT | 否 | 2026-11-21 |
| `MageByte-Zero/spec-superflow` | ★897 | MIT | 否 | 2026-11-01 |
| `MaxInGaussian/pi-plans` | ★237 | MIT | 否 | 2026-10-11 |
| `chengzhongwei/Prompt-sensei` | ★107 | Apache-2.0 | 否 | 2026-07-13 |
| `GaZmagik/claude-prompt-improver` | ★4 | MIT | 否 | 2026-07-21 |
