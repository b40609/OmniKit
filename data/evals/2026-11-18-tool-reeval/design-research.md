# Coding Agent 前端設計質感與原型開發開源工具飽和式調研

> **調研日期**：2026-11-18  
> **帳本**：[design-ledger.json](file:///C:/Users/user/Desktop/OmniKit/data/evals/2026-11-18-tool-reeval/design-ledger.json)  
> **狀態**：已達 12 組查詢上限（`over_budget`），停下回報；共收錄 297 個不重複相關名字，其中 ★1,000 以上共 46 個，★100 至 999 共 74 個。

---

## 1. 判斷標準（納入與排除條件）

本調研收錄讓 coding agent（如 Claude Code、Codex）產出有設計質感的前端畫面或原型的開源工具，分為兩類：
- **(a) 設計工作台／App**：搭配使用者既有的 coding agent，提供畫布編輯、即時預覽、互動原型生成或設計系統（如 `DESIGN.md`）套用的開源工作台／編輯器。
- **(b) 前端設計 Skill／Plugin／規則工具**：安裝給 coding agent 使用的 `SKILL.md`、外掛市集、anti-slop 檢查閘門、`DESIGN.md` 生成／提取器與動效規範。

**明確排除**：純圖片生成工具、一般 UI 元件庫（如 daisyUI、Oat、Animal Island UI、Cult UI）、僅放提示詞的靜態清單、Open Design 的 fork 或鏡像、大型雜燴通用 skill 合集（如 `openai/skills`、`vercel-labs/agent-skills`、`mattpocock/skills`、`kkkkhazix/khazix-skills`）、簡報／影片專用產生器、寫作去 AI 味工具。  
**拿不準者**：不記進帳本，統一列於第 6 節「拿不準」供拍板。

---

## 2. 停止狀態與調研過程摘要

- **已查組數**：12 組（觸發 `MAX_GROUPS = 12` 上限，依規則停止並回報）
- **停止條件檢查（`status --min-stars 1000`）**：
  - 全體不重複名字連續 0 組沒有新名字（`streak = 0`，需 3 組）：`還不能停`
  - ★1,000 以上 GitHub repo 連續 1 組沒有新名字（`notable_streak = 1`，需 3 組）：`還不能停`（第 11 組仍發現 `plannotator/effective-html` ★4,247；第 12 組發現 29 個新名字，其中 ★1,000 以上為 0 個）
  - 系統提醒：`已經 12 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續`
- **管道可用性與限制**：
  - 本次 `github-topic`、`github-keyword`、`awesome`、`skills-sh`、`npm`、`mcp-registry`、`hn`、`exa`、`web-zh`、`web-en`、`producthunt`、`related` 共 12 種管道皆成功執行，無請求報錯（`errors = []`）。
  - 實作觀察限制：`github-keyword` 對中文複合長句回傳 0 筆；`mcp-registry` 僅比對名稱子字串（如「ui」「html」「vibe」），中文關鍵字無效；`hn` 許多回傳為討論標題（`lead=true`）而非直接 repo；`exa` 匿名每次回傳上限 10 筆；`skills-sh` 按 IP 限速需間隔 3 秒；`sweep.py related` 預設會將所有 fork 與 README 連結直接寫入帳本，故本次採單獨執行 `related` 後人工篩選再以 `add` 記帳，避免誤納 Open Design fork 與無關套件。
- **挑過的擴展詞路徑（共 12 組）**：
  1. `coding agent 前端設計 原型`（起手中文組；納入已知 9 名與 `related` 抽詞，引出 `openpencil`、`onlook`、`superdesign`、`doop`、`typeui`）
  2. `frontend design agent skill`（起手英文組 ＋ `producthunt`；從結果擴出 `anti-slop`、`design-taste`、`stitch-skills`、`hallmark`）
  3. `design system prototype canvas`（加 `--topic figma-alternative`、`claude-design`、`claude-design-alternative` ＋ `related`；帶出 `open-pencil`、`interface-design`、`design.md`）
  4. `anti-slop ui design`（由第 2 組擴展之反 AI 味關鍵詞，加 `--topic anti-slop`、`ai-slop` ＋ `related`；帶出 `auteur`、`mengto/skills`、`design-motion-principles`）
  5. `design-md`（由第 1、3 組發現的 Google Stitch `DESIGN.md` 生態擴展，加 `--topic design-md`、`google-stitch`；帶出 `dembrandt`、`ui-skills`、`awesome-design-md-jp`）
  6. `design engineering ui`（由 `ui-skills`、`emilkowalski` 等結果用語擴展，加 `--topic design-engineering`、`design-taste` ＋ `related`；帶出 `design-extract`、`ux-ui-agent-skills`、`scroll-craft`）
  7. `ui generator prototype`（補不含 AI/skill/agent 的一般說法，加 `--topic ui-generator`、`vibe-design` ＋ `related`；帶出 `make-interfaces-feel-better`、`material-3-skill`）
  8. `ai design workspace`（由 Open Design 自稱詞彙擴展，加 `--topic ai-design`、`design-workspace`；新增 6 個、★1,000 以上 0 個）
  9. `Claude Design 開源 替代`（中文競品詞擴展，加 `--topic claude-code-for-design`、`codex-design`；發現 `jakubkrehel/skills` ★12,347）
  10. `codex ui ux skill`（針對 Codex 生態橫向補查，加 `--topic codex-skills`、`ui-ux-design`；新增 17 個小 repo、★1,000 以上 0 個）
  11. `html prototype design skill`（針對瀏覽器 HTML 原型與 UI 審查補查，加 `--topic ui-critique`、`design-review`；發現 `plannotator/effective-html` ★4,247）
  12. `vibe coding ui design`（由結果中頻繁出現的 vibe coding／design-inspiration 擴展，加 `--topic vibe-coding-skills`、`design-inspiration`；新增 29 個、★1,000 以上 0 個）

### `sweep.py status --min-stars 1000` 摘要輸出
```text
總共 297 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 1 組沒有新的（要 3 組）：還不能停
已經 12 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續
第 1 組「coding agent 前端設計 原型」：24 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, related, web-zh（★1000 以上新名字：18 個）
第 2 組「frontend design agent skill」：42 個名字，新的 35 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt（★1000 以上新名字：4 個）
第 3 組「design system prototype canvas」：38 個名字，新的 33 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, related, web-en（★1000 以上新名字：6 個）
第 4 組「anti-slop ui design」：30 個名字，新的 30 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, related, web-en（★1000 以上新名字：5 個）
第 5 組「design-md」：32 個名字，新的 32 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en（★1000 以上新名字：3 個）
第 6 組「design engineering ui」：40 個名字，新的 40 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, related, web-en（★1000 以上新名字：6 個）
第 7 組「ui generator prototype」：21 個名字，新的 16 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, related, web-en（★1000 以上新名字：2 個）
第 8 組「ai design workspace」：6 個名字，新的 6 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en（★1000 以上新名字：0 個）
第 9 組「Claude Design 開源 替代」：12 個名字，新的 6 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh（★1000 以上新名字：1 個）
第 10 組「codex ui ux skill」：23 個名字，新的 17 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en（★1000 以上新名字：0 個）
第 11 組「html prototype design skill」：29 個名字，新的 29 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en（★1000 以上新名字：1 個）
第 12 組「vibe coding ui design」：30 個名字，新的 29 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en（★1000 以上新名字：0 個）
```

---

## 3. ★1,000 以上相關工具一覽（共 46 個，均經 `sweep.py verify` 實測）

> 註：星數、授權與最後 push 皆為 `2026-11-18` 透過 `sweep.py verify`（`gh api`）實測；Windows 與遙測欄位以各 repo 官方 README／`SECURITY.md`／`privacy.md` 一手文件為準，未明寫者標為「待驗證」。

| Repo | 類型 | 實測星數（2026-11-18 gh api） | 授權 | 最後 push | 支援 Agent | Windows 可用性 | 預設遙測 | 備註 |
|---|---|---|---|---|---|---|---|---|
| [anthropics/skills](https://github.com/anthropics/skills) | b | ★196,979 | 無（含 Apache-2.0 子目錄） | 2026-11-16 | Claude、Claude Code | 待驗證 | 待驗證 | 含 `frontend-design` skill |
| [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | b | ★151,129 | MIT | 2026-11-18 | Claude Code、Codex、Cursor、Windsurf、OpenCode、Gemini CLI、Antigravity、Copilot、Roo、Trae 等 | 支援（README 附 Windows PowerShell 指令） | 待驗證 | 內含 80 種 UI 風格與 192 條推理規則 |
| [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) | b（`DESIGN.md` 索引庫） | ★128,061 | MIT | 2026-10-28 | Claude Code、Cursor、OpenCode、Roo 等支援 `DESIGN.md` 工具 | 待驗證 | 待驗證 | 收錄 84+ 知名網站分析後之 `DESIGN.md` |
| [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | b | ★118,085 | MIT | 2026-11-08 | Claude Code、Codex 等 | 支援（README 明記 Windows Git Bash 支援） | 待驗證 | 另推桌面版 TasteCode |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | b | ★112,565 | Apache-2.0 | 2026-11-18 | Claude Code、Codex CLI、Cursor、Gemini CLI、OpenCode、Antigravity、Copilot、Kiro、Trae、Hermes 等 | 支援（CI 測 Linux/Windows 並提供 `npx`） | 有（預設開啟匿名方向選擇紀錄；可 `npx impeccable telemetry off` 或 `DO_NOT_TRACK=1` 關閉） | 含 `polish`、`critique`、`audit` 等指令 |
| [nexu-io/open-design](https://github.com/nexu-io/open-design) | a | ★108,224 | Apache-2.0 | 2026-11-18 | Claude Code、Codex、Cursor、Gemini、OpenCode、Antigravity、Copilot、Cline 等 | 支援（提供 Windows x64 原生安裝檔） | 有（安全與可靠性遙測預設開啟；產品分析與錄影需同意） | 本題基準比較對象 |
| [emilkowalski/skills](https://github.com/emilkowalski/skills) | b | ★57,894 | MIT | 2026-11-15 | 支援 `skills.sh` 規範之 agent（README 未逐一列舉） | 待驗證 | 待驗證 | 動效與 UI 細節品味 skill |
| [Nutlope/hallmark](https://github.com/Nutlope/hallmark) | b | ★57,218 | MIT | 2026-11-11 | Claude Code、Codex、Cursor、OpenCode、Copilot 等 | 待驗證 | 待驗證 | 50 套材質主題 ＋ 實機瀏覽器 `/hallmark audit` 審查 |
| [alchaincyf/huashu-design](https://github.com/alchaincyf/huashu-design) | b | ★29,795 | MIT | 2026-11-10 | Claude Code、Codex、Cursor、OpenClaw、Hermes 等 | 待驗證 | 無（README ＋ `SECURITY.md` 明示 100% 本地運行、無 telemetry） | 含 92 種風格與實機預覽 |
| [google-labs-code/design.md](https://github.com/google-labs-code/design.md) | b（規格 ＋ CLI） | ★28,937 | Apache-2.0 | 2026-11-18 | 支援 `DESIGN.md` 之 coding agents（README 未鎖定單一品牌） | 支援（README 專節附 Windows/PowerShell 指令） | 待驗證 | `DESIGN.md` 官方格式規格 ＋ `@google/design.md` linter/exporter |
| [onlook-dev/onlook](https://github.com/onlook-dev/onlook) | a | ★27,256 | Apache-2.0 | 2026-11-17 | Claude Code、Codex 等（本地 code-first 視覺編輯） | 尚未支援（README 寫 Windows coming soon / waitlist） | 有（官方下載版預設開啟；可用 `STUDIO_TELEMETRY=0` 關閉） | 本地視覺化 React/網頁設計編輯器 |
| [heydamir/unslop](https://github.com/heydamir/unslop) | b | ★18,017 | CC-BY-4.0 | 2026-11-15 | Claude Code、Codex、Google Antigravity 等 | 待驗證 | 待驗證 | 紅線審查與多輪修復去 AI 味 |
| [jakubkrehel/skills](https://github.com/jakubkrehel/skills) | b | ★12,347 | MIT | 2026-11-18 | 支援 `skills.sh` 規範之 agent（README 未逐一列舉） | 待驗證 | 待驗證 | 含 `better-interface`、`better-ui`、`better-typography` 等 |
| [ibelick/ui-skills](https://github.com/ibelick/ui-skills) | b | ★11,177 | MIT | 2026-11-18 | 支援 `npx ui-skills` / MCP 之 agent（README 未逐一列舉） | 待驗證 | 待驗證 | Design engineering 規範與 MCP |
| [google-labs-code/stitch-skills](https://github.com/google-labs-code/stitch-skills) | b | ★10,263 | Apache-2.0 | 2026-11-18 | Codex、Claude Code、Cursor、Antigravity、Gemini CLI、OpenCode | 待驗證 | 待驗證 | Google Stitch 官方設計／建置 skill 套件 |
| [open-pencil/open-pencil](https://github.com/open-pencil/open-pencil) | a | ★9,925 | MIT | 2026-11-18 | Claude Code、Codex、Cursor、Windsurf、Gemini、Antigravity 等（含 HTTP/stdio MCP） | 支援（Windows 10+ Tauri v2 桌面版與 PWA） | 有（官方版預設每日 1 次匿名 ping，可關閉；使用統計需同意） | 支援 `.fig` 與 `.pen` 檔 |
| [miqdadbadjuber/anti-slop](https://github.com/miqdadbadjuber/anti-slop) | b | ★9,466 | MIT | 2026-11-17 | Claude Code、Codex、Cursor、OpenCode、Gemini CLI、Antigravity、Copilot、Cline、Hermes 等 | 支援（README 附 Windows PowerShell 設定說明） | 待驗證 | 反模板化設計規則集 CLI |
| [OpenCoworkAI/open-codesign](https://github.com/OpenCoworkAI/open-codesign) | a | ★8,238 | MIT | 2026-11-10 | Claude Code、Codex、OpenCode、Gemini 等 | 支援（Windows 10+ 安裝檔與 Scoop） | 待驗證（README 稱資料留本機、無明確 telemetry 條款） | Open-source Claude Design / v0 替代工作台 |
| [MengTo/Skills](https://github.com/MengTo/Skills) | b | ★7,699 | MIT | 2026-11-14 | Codex、Claude Code、Cursor 等 | 待驗證 | 待驗證 | Design+Code 作者團隊之 UI/Three.js/擷取提示詞 skill |
| [superdesigndev/superdesign](https://github.com/superdesigndev/superdesign) | a | ★7,621 | NOASSERTION | 2026-06-29 | Cursor、Windsurf、Claude Code、VS Code | 待驗證 | 待驗證 | 原開源 IDE 擴充（官方宣告已停維，轉向 `superdesign-skill`） |
| [ZSeven-W/openpencil](https://github.com/ZSeven-W/openpencil) | a | ★7,275 | MIT | 2026-11-18 | Claude Code、Codex、Cursor、OpenCode、Gemini、Copilot、Kiro 等（內建 MCP） | 支援（Windows 原生 `.exe`、Scoop 與 `install-op.ps1`） | 待驗證 | Rust/WASM 向量設計畫布與 `.op` 格式，與 `open-pencil/open-pencil` 不同專案 |
| [Dammyjay93/interface-design](https://github.com/Dammyjay93/interface-design) | b | ★5,997 | MIT | 2026-06-20 | Claude Code、Codex 等 | 待驗證 | 待驗證 | 專注儀表板／應用介面一致性記憶 skill |
| [Appllama/appllama-skills](https://github.com/Appllama/appllama-skills) | b | ★5,228 | MIT | 2026-09-06 | Claude Code、Codex、Cursor 等 | 待驗證 | 待驗證 | 專攻行動端 App UI 與模擬器驗證 |
| [nateherkai/scroll-craft](https://github.com/nateherkai/scroll-craft) | b | ★5,216 | MIT | 2026-09-30 | Codex、Claude Code 等 | 支援（README 明寫僅在 Windows 實測過） | 待驗證 | 捲動敘事型網站標準與瀏覽器驗證 |
| [Manavarya09/design-extract](https://github.com/Manavarya09/design-extract) | b | ★5,147 | MIT | 2026-11-18 | Claude Code、Codex、Cursor、Windsurf、Gemini 等 | 待驗證（Node + Playwright CLI） | 待驗證 | 從任一網站提取 W3C DTCG tokens 與 Tailwind 設定 |
| [plannotator/effective-html](https://github.com/plannotator/effective-html) | b | ★4,247 | MIT | 2026-10-31 | Claude Code、Codex 等 | 待驗證 | 待驗證 | 單檔互動 HTML 線框與原型 skill 集 |
| [jakubkrehel/make-interfaces-feel-better](https://github.com/jakubkrehel/make-interfaces-feel-better) | b | ★4,137 | MIT | 2026-11-18 | 支援 `skills.sh` 規範之 agent（README 未逐一列舉） | 待驗證 | 待驗證 | 專注光學對齊、同心圓角、互動微細節 |
| [dembrandt/dembrandt](https://github.com/dembrandt/dembrandt) | b | ★4,040 | MIT | 2026-11-14 | Claude Code、Cursor、Windsurf、Copilot 等 | 待驗證（Node + Playwright CLI） | 待驗證（選用 `--key` CI 飄移追蹤會上傳快照） | 單指令擷取網站設計系統為 W3C tokens |
| [bergside/awesome-design-skills](https://github.com/bergside/awesome-design-skills) | b（skill 集合） | ★3,716 | MIT | 2026-06-28 | Claude Code、Codex、Cursor 等 | 待驗證 | 待驗證 | 67 套含 `SKILL.md` ＋ `DESIGN.md` 設計系統包 |
| [dickwu/apple-design-skill](https://github.com/dickwu/apple-design-skill) | b | ★3,536 | 無 | 2026-11-13 | Claude Code、Codex、Cursor、Antigravity、OpenCode、Windsurf、Gemini | 待驗證 | 待驗證 | 依據 Apple HIG 與 Liquid Glass 審查，含 Electron/Tauri/Flutter 轉譯 |
| [oil-oil/oil-ui](https://github.com/oil-oil/oil-ui) | b | ★3,510 | MIT | 2026-11-18 | Claude Code、Codex、Cursor、Windsurf、Cline、Antigravity、OpenCode、Copilot、Trae 等 | 支援（README 明記 Windows 路徑 `%LOCALAPPDATA%\oil\`） | 無專案遙測（每 10 分鐘檢查版本清單，可用 `OIL_NO_UPDATE_CHECK=1` 關閉） | 實機截圖迭代 ＋ 3 方向並排探索 |
| [Owl-Listener/designer-skills](https://github.com/Owl-Listener/designer-skills) | b | ★3,411 | MIT | 2026-09-05 | Claude Code、Gemini CLI | 待驗證 | 待驗證 | 涵蓋 UX 研究到介面交付的 33 個外掛集 |
| [plugin87/ux-ui-agent-skills](https://github.com/plugin87/ux-ui-agent-skills) | b | ★3,192 | MIT | 2026-11-18 | Claude Code、Codex、Cursor、Copilot、Gemini CLI、Antigravity、Aider、MCP | 待驗證 | 無（`SECURITY.md` 明示無任何遙測與追蹤） | 2,144 套設計系統 ＋ 52 道自動品質閘門 |
| [bergside/design-md-chrome](https://github.com/bergside/design-md-chrome) | b（Chrome 擴充） | ★3,192 | MIT | 2026-05-25 | Claude Code、Codex、Google Stitch | 待驗證（Chrome 擴充理論跨平台） | 待驗證 | 瀏覽器一鍵萃取當前網頁為 `DESIGN.md` / `SKILL.md` |
| [dominikmartn/nothing-design-skill](https://github.com/dominikmartn/nothing-design-skill) | b | ★2,888 | MIT | 2026-11-10 | Claude Code、Codex（`SKILL.md`） | 待驗證 | 待驗證 | Nothing 工業風單色設計系統 skill |
| [bergside/typeui](https://github.com/bergside/typeui) | b | ★2,263 | NOASSERTION | 2026-10-22 | Codex、Claude、Cursor、Windsurf、OpenCode、Antigravity、Copilot、Cline、Hermes 等 | 待驗證 | 待驗證 | TypeUI MCP 與設計系統規範平台 |
| [zanwei/design-dna](https://github.com/zanwei/design-dna) | b | ★2,139 | MIT | 2026-08-28 | Claude Code、Codex、Cursor、Copilot 等 | 待驗證 | 待驗證 | 提取並套用「Design DNA」（tokens＋質性風格＋視覺特效） |
| [kgoedecke/doop](https://github.com/kgoedecke/doop) | a | ★2,133 | AGPL-3.0 | 2026-11-17 | Claude Code、Codex、Cursor、OpenCode、Gemini CLI、Copilot 等（MCP） | 支援（macOS/Windows Tauri 桌面版與瀏覽器） | 無預設開啟（PostHog 為選配環境變數，未設則無分析） | Paper.design 開源替代，多人與多 agent 即時共編 HTML 畫布 |
| [kylezantos/design-motion-principles](https://github.com/kylezantos/design-motion-principles) | b | ★1,604 | MIT | 2026-05-30 | Claude Code、Cursor、Windsurf 等 | 待驗證 | 待驗證 | 依 Emil / Jakub / Jhey 三種動效哲學建置與審查動畫 |
| [hamen/material-3-skill](https://github.com/hamen/material-3-skill) | b | ★1,593 | MIT | 2026-07-15 | Claude Code、Codex、Cursor 等 | 待驗證 | 待驗證 | Material Design 3（Material You）完整 skill |
| [freshtechbro/claudedesignskills](https://github.com/freshtechbro/claudedesignskills) | b | ★1,388 | MIT | 2025-11-20 | Claude Code | 待驗證 | 待驗證 | 專攻 3D/WebGL、GSAP、Framer Motion 外掛市集 |
| [feimacode/open-design-agent-kit](https://github.com/feimacode/open-design-agent-kit) | b | ★1,147 | MIT | 2026-11-18 | Claude Code、Codex、Cursor、GitHub Copilot、OpenCode、Cline、ChatGPT Desktop | 支援（README 含 Windows ChatGPT/Node 安裝指引） | 本機安裝無遙測（`privacy.md` 明示不收分析與遙測；託管服務另計） | 將 Open Design 技能與品牌設計系統直接內嵌既有 agent |
| [agiwhitelist/auteur](https://github.com/agiwhitelist/auteur) | b | ★1,053 | MIT | 2026-08-06 | Claude Code、Codex、Cursor、Windsurf、OpenCode、Gemini、Copilot 等 | 待驗證 | 待驗證 | 電影導演式鎖定美術方向 ＋ 可執行 anti-slop linter |
| [superdesigndev/superdesign-skill](https://github.com/superdesigndev/superdesign-skill) | b（接雲端後端） | ★1,024 | MIT | 2026-08-21 | Claude Code、Codex、Cursor 等 | 待驗證 | 待驗證（需 `superdesign login` 連線 `superdesign.dev`） | Superdesign 官方現行 CLI/skill 入口 |
| [bitjaru/styleseed](https://github.com/bitjaru/styleseed) | b | ★1,023 | MIT | 2026-11-18 | Claude Code、Codex、Cursor、Windsurf、Gemini、Copilot 等 | 支援（README 附 `WINDOWS-INSTALL.md` PowerShell 驗證路徑） | 待驗證 | 強制規則閘門與「渲染→評分→修訂」閉環 |
| [kzhrknt/awesome-design-md-jp](https://github.com/kzhrknt/awesome-design-md-jp) | b（`DESIGN.md` 索引庫） | ★1,017 | MIT | 2026-11-18 | 支援 `DESIGN.md` 之 AI coding agents | 待驗證 | 待驗證 | 針對日文網頁服務與日文排版規範的 `DESIGN.md` 集 |

---

## 4. 整體觀察與類型比較

1. **類型 (a) 設計工作台／畫布 app 的三大路線**：
   - **Open Design 生態系**：`nexu-io/open-design`（★108,224）、`OpenCoworkAI/open-codesign`（★8,238），以及反其道而行「不開桌面 app、把同樣內容塞回既有 IDE/agent」的 `feimacode/open-design-agent-kit`（★1,147）。
   - **即時程式碼／HTML 畫布工作台**：`onlook-dev/onlook`（★27,256，目前無 Windows 版）與 `kgoedecke/doop`（★2,133，支援 Windows 與多 agent MCP 同畫布協作）。
   - **開源 Figma 替代 AI 向量畫布**：`open-pencil/open-pencil`（★9,925）與 `ZSeven-W/openpencil`（★7,275）兩者為完全獨立專案，皆支援 Windows 與 MCP，讓 Claude Code/Codex 直接讀寫設計稿。
2. **類型 (b) 前端設計 Skill／閘門的明顯演化**：
   - 早期的純提示詞規範（如 `anthropics/skills` 的 `frontend-design`）正迅速演進為**「可執行驗證閉環」**：包含真實瀏覽器截圖對比與 anti-slop linter（`pbakaus/impeccable`、`Nutlope/hallmark`、`oil-oil/oil-ui`、`plugin87/ux-ui-agent-skills`、`agiwhitelist/auteur`、`bitjaru/styleseed`），以及**可移植設計系統描述檔 `DESIGN.md`／W3C DTCG tokens**（`google-labs-code/design.md`、`Manavarya09/design-extract`、`dembrandt/dembrandt`、`zanwei/design-dna`）。

---

## 5. ★1,000 以下值得注意的候選（未飽和，僅列代表項目）

> 註：因未達飽和且停等門檻設為 `--min-stars 1000`，以下 `★100..999` 項目不保證已找齊（帳本共收錄 74 個此區間專案）：

- **工作台／原型審查介面 (a)**：`Innei/ryugi`（★529，含畫板、設計文件與回饋回傳 agent）、`ShuaiMXu/happyhands`（★515，本地截圖 UI 審查工作台）、`manalkaff/opendesign`（★269）、`Protovibe-Studio/protovibe-studio`（★13，React+Tailwind 視覺編輯器接本地 coding agent）、`alibaba-damo-academy/yugoo-design`（★10）。
- **高密度設計／原型 Skill (b)**：`op7418/dsh-guizang-design`（★963）、`dominikmartn/hue`（★921）、`carmahhawwari/ui-design-brain`（★909）、`rshankras/claude-code-apple-skills`（★898）、`anxforever/stylekit`（★857）、`insane0777/awwwards-mcp`（★839）、`zeroz-lab/cc-design`（★831，高擬真 HTML 原型）、`xiaopu-ai/web-design`（★823）、`athevon/genjutsu`（★816）、`0xdesign/design-plugin`（★785）、`itsssssjack/power-design`（★777）、`s0xdk/refactoring-ui-skill`（★703）、`adobe/skills`（★332）。

---

## 6. 「拿不準」（未記進帳本）與明確排除項目

### 拿不準（邊界項目，未計入帳本與停止門檻）
- **`lnkiai/m3e-canvas`**（★10,593）：瀏覽器繪製 Material 3 畫面後複製 prompt 給 coding agent，未直接接 coding agent 執行原型或設計檔雙向連動。
- **`Jakubantalik/transitions.dev`**（★6,386）：主體為 CSS 過場動畫片段元件庫（含付費登入 Pro API），只是額外打包成 `SKILL.md`。
- **`anthropics/knowledge-work-plugins`**（★36,490）：面向 Claude Cowork 知識工作者的泛用外掛大合集，僅其中包含一組 `design`／`design-critique` 外掛。
- **`penpot/penpot`**（★62,500+）與 **`penpot/penpot-mcp`**：通用開源 UI 設計軟體及其 MCP 橋接，非專為 coding agent 原型工作流而生。
- **`dyad-sh/dyad`**（★22,300+）、**`sammwyy/singulary`**（★74）：AI 全端應用產生器（Bolt／Lovable 開源替代），而非配合使用者既有 coding agent 的設計工作台。
- **`stagewise-io/stagewise`**（★6,800+）、**`aidenybai/react-grab`**（★7,700+）：前端 DOM／React 元素選取與 agent 橋接工具，偏除錯輔助而非設計系統／原型工具。
- **`gridaco/grida`**（★2,700+）、**`devdotfast/whiteboard`**（★3,500+）：開放畫布引擎與架構白板，與前端原型／`DESIGN.md` 工作流距離較遠。
- **`GLips/Figma-Context-MCP`**（★16,200+）、**`southleft/figma-console-mcp`**（★3,300+）：Figma 讀取／控制 MCP，核心前提仍依賴閉源 Figma。
- **`21st-dev/magic-mcp`**（★6,500+）：商業 UI 元件市集搭配的產生 MCP。
- **`JCodesMore/ai-website-cloner-template`**（★39,400+）：整站複製範本而非一般設計能力工具。
- **`Anionex/agent-vision-toolkit`**（★1,200+）：幫純文字模型補視覺能力工具包，非前端設計專屬。
- **`Devin-AXIS/deepseek-design`**（★1,800+）、**`Ebony-Vinyl/EAC-design-world`**（★1,600+）：綁定 DeepSeek Harness 且重心在簡報／影片而非一般前端介面。
- **`voltagent/awesome-claude-design`**（★4,600+）、**`rohitg00/awesome-claude-design`**（★1,200+）、**`wilwaldon/Claude-Code-Frontend-Design-Toolkit`**（★1,300+）、**`maxbogo/awesome-ai-tools-for-ui`**（★1,040+）：屬「精選清單／工具導覽列表」性質，非單一工具或 `DESIGN.md` 實作庫。

### 明確排除代表項目
- **大型雜燴 skill／規則合集**：`openai/skills`、`vercel-labs/agent-skills`、`mattpocock/skills`、`kkkkhazix/khazix-skills`、`borghei/Claude-Skills`、`rohitg00/pro-workflow`、`huytieu/COG-second-brain`、`yeachan-heo/oh-my-claudecode`。
- **一般 UI 元件庫／著色器庫**：`saadeghi/daisyui`、`nolly-studio/cult-ui`、`guokaigdg/animal-island-ui`、`knadh/oat`、`DavidHDev/canvas-ui`、`paper-design/shaders`。
- **簡報／影片／純動效產生器**：`zarazhangrui/frontend-slides`、`zarazhangrui/beautiful-html-templates`、`op7418/guizang-ppt-skill`、`lewislulu/html-ppt-skill`、`heygen-com/hyperframes`、`nexu-io/openmotion`、`nolangz/pixel2motion`。
- **Open Design 衍生修改版／鏡像／寫作 anti-slop**：`0xcjl/open-design-pro`、`DevvGwardo/impeccable`、`adryanmoldokkr32-pixel/anthropics-skills`、`MohamedAbdallah-14/unslop`、`mrgediao/shuorenhua`；以及非 UI 相關誤命中（如 KiCad PCB 設計 `aklofas/kicad-happy`）。

---

## 7. 後續建議（請使用者決定）

目前已達 12 組查詢上限（`notable_streak = 1`，第 11 組仍新出現 `plannotator/effective-html`，且 `★1,000` 以上已累積 46 個相關專案）。由於「(a) 設計工作台」與「(b) 設計 Skill／DESIGN.md 工具」合計涵蓋範圍較廣，若要繼續追到完全飽和，建議擇一：
1. **停止擴搜、直接收尾**：現有 46 個 ★1,000 以上專案已涵蓋主流設計工作台與設計 skill，可直接選候選進 `omnikit-eval` 評測。
2. **拆成子題另開帳本續查**：將 **(a) 設計工作台／畫布 app** 與 **(b) `DESIGN.md`／UI 審查 skill** 拆成兩本帳本分頭收斂。
3. **保留原帳本加查**：從第 13 組起繼續補查至 `notable_streak = 3`。
