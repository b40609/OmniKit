# Coding Agent 程式碼審查與抓 Bug 工具飽和式調研報告

> **調研日期**：2026-11-18  
> **帳本**：[review-ledger.json](file:///C:/Users/user/Desktop/OmniKit/data/evals/2026-11-18-tool-reeval/review-ledger.json)  
> **對應情境**：OmniKit 名冊 `review` 槽位 R1（「Claude Code 改完 OmniKeep Python 後端修正，交給 Codex 審 diff，或反過來；重要的才交叉審，小改動自己審」）  
> **狀態**：已達 12 組查詢上限（`over_budget`），停下回報；帳本共收錄 477 個不重複名字，其中實測 ★1,000 以上 GitHub repo 共 66 個（經一手驗證排除誤命中與拿不準項目後，符合納入標準之 ★1,000 以上工具共 **53 個**），★100 至 999 共 116 個。

---

## 1. 判斷標準（納入與排除條件）

本調研聚焦「搭配本機 coding agent（Claude Code、Codex）或針對其產出進行把關的程式碼審查與抓 bug 工具」，對照 OmniKit `review` 槽位 R1 需求（跨模型互審 diff、抓行為或安全 bug、確認 agent 實作確實完成）與現任基準（Claude Code 內建 `/code-review`、`/security-review` 與 Codex `/review`；名冊 pending：`openai/codex-security`、`chaseai-yt/claudex-loop`、`pullboard-dev/pullboard`）。

- **納入標準**：
  1. 可在本機或團隊工作流搭配 Claude Code、Codex 使用的審查工具，形式包含 `skill`、`plugin`、CLI、MCP Server、GitHub Action、可自架 PR review bot，或配合 agent 回送評論的 diff 審查工作台／TUI。
  2. 核心用途符合下列至少一項：審 diff 或 PR、跨模型交叉審查（例如 Claude Code ↔ Codex 互相審查或對抗驗證）、整座 repo 掃描行為 bug、找安全漏洞並給修法、或驗收（查證 agent 宣稱「做完了」是否為真）。
- **明確排除**：
  1. 傳統 linter 與純規則型 SAST／CI 執行器（如 Semgrep、ESLint、`reviewdog/reviewdog`、`danger/danger`、`danger/danger-js`），除非其核心定位為專供 coding agent 調用的代理或 MCP 審查整合。
  2. 大雜燴通用 skill 合集（除非「程式碼審查」是該合集的主角或獨立核心）。
  3. 紅隊攻擊／外部滲透測試與 Bug Bounty 偵查工具（如 `KeygraphHQ/shannon`、`usestrix/strix`、`awarexone/Agentic-Bug-Hunter`、已排除之 `elementalsouls/Claude-BugHunter`）。
  4. 非工具本體之純文章／通用演算法庫／coding agent 本體（如 `openedclaude/claude-reviews-claude`、`ivankovic/omnidiff`、`anthropics/claude-code`）。
- **拿不準者**：包含僅賣商業 SaaS 沒有開源或本機獨立引擎的工具（即使提供 thin client CLI），以及跨界或界線模糊的邊界項目，統一集中於第 5 節列明供使用者拍板。

---

## 2. 停止狀態與調研過程摘要

- **已查組數**：12 組（觸發 `MAX_GROUPS = 12` 上限，依規則停止並回報）
- **停止條件檢查（`sweep.py status --min-stars 1000`）**：
  - 全體不重複名字連續 0 組沒有新名字（`streak = 0`，需 3 組）：`還不能停`
  - ★1,000 以上 GitHub repo 連續 1 組沒有新名字（`notable_streak = 1`，需 3 組）：`還不能停`（第 11 組仍新見 4 個 ★1,000+ repo；第 12 組新增 27 個未滿千星名字，★1,000+ 為 0 個）
  - 系統提醒：`已經 12 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續`
- **挑過的擴展詞路徑（共 12 組）**：
  1. `code review agent`（起手英文組 ＋ `web-en` ＋ `producthunt` ＋ `related`，針對 `alibaba/open-code-review`、`zhuyansen/awesome-claude-code-review` 與 `kodustech/awesome-code-review-tools` 單獨執行 `related` 後人工過濾再 `add`；納入 202 名，含 35 個 ★1,000+）
  2. `AI code review`（全 8 程式管道 ＋ `web-en`；新增 26 名，帶出 `anthropics/claude-plugins-official`、`duriantaco/skylos`、`aiwithremy/claude-skills-llm-council`）
  3. `claude code review plugin`（補入 Claude Code 外掛生態；新增 23 名，帶出 `nyldn/claude-octopus`、`dagoSte/squadra`、`pullfrog/pullfrog`、`anthropics/claude-code-action`）
  4. `codex review`（補入 Codex 審查與雙代理循環；新增 21 名，帶出 `DeepMyst/Mysti`、`umputun/ralphex`、`openai/codex-action`）
  5. `cross-model review`（由 `codex-plugin-cc`、`claudex-loop` 與 `claude-octopus` 常見用語擴展；新增 30 名中小型跨模型對抗審查工具）
  6. `PR review bot open source`（由 `pr-agent` 與 `ChatGPT-CodeReview` 路線擴展；新增 30 名，帶出 `patched-codes/patchwork`、`anc95/ChatGPT-CodeReview`）
  7. `bug finding agent`（涵蓋行為 bug 獵手與審計類；新增 23 名，帶出 `trailofbits/skills`、`awarexone/Agentic-Bug-Hunter`）
  8. `verification agent`（納入「驗收 agent 完成度」面向；新增 27 名，大量出現 ★1,000+ 工具：`cloudflare/security-audit-skill`、`code-yeongyu/lazycodex`、`llm-as-a-verifier/llm-as-a-verifier`、`VibiumDev/vibium`、`reticlehq/reticle`、`2akouwu/reverify`、`maxritter/qualitylayer`、`AMAP-ML/LongHorizon-Harness`、`asklokesh/loki-mode` 等 11 個）
  9. `AI 程式碼審查`（繁簡中文社群檢索 ＋ `web-zh`；新增 6 名，★1,000+ 為 0）
  10. `code security review`（由 `security-audit-skill` 與 `codex-security` 擴展資安審查；新增 25 名，帶出 `Kritt-ai/open-kritt`、`sanyuan0704/sanyuan-skills`）
  11. `git diff review TUI`（不含 AI/agent 的一般檢視器說法，補查搭配 agent 回送評論的 diff TUI／WebUI；新增 37 名，帶出 `remorses/critique`、`yoshiko-pg/difit`、`jnsahaj/lumen` 等）
  12. `pre-push code review`（由 `openqodex`、`git-lrc`、`gga` 常見觸發時機擴展；新增 27 名，★1,000+ 為 0）

### `sweep.py status --min-stars 1000` 完整輸出摘要
```text
總共 477 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 1 組沒有新的（要 3 組）：還不能停
已經 12 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續
第 1 組「code review agent」：202 個名字，新的 202 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  ★1000 以上的新名字：alibaba/open-code-review, tirth8205/code-review-graph, the-pr-agent/pr-agent, backnotprop/plannotator, modem-dev/hunk, reviewdog/reviewdog, lintsinghua/deepaudit, danger/danger, danger/danger-js, agavra/tuicr, google/mantis, the-open-engine/zeroshot, kodustech/kodus-ai, hyhmrright/brooks-lint, hexmostech/git-lrc, openqodex/openqodex, sno-ai/sno-station, mattzcarey/shippie, kenn-io/roborev, openedclaude/claude-reviews-claude, sourcebot-dev/sourcebot, openai/codex-plugin-cc, oneredoak/claude-code-workflows, openai/codex-security, chaseai-yt/claudex-loop, awesome-skills/code-review-skill, persiyanov/herdr-reviewr, amelnagdy/guard-skills, gentleman-programming/gentleman-guardian-angel, sourcery-ai/sourcery, vercel-labs/openreview, villesau/ai-codereviewer, sashiko-dev/sashiko, anthropics/claude-code-security-review, px0-ai/px0
第 2 組「AI code review」：26 個名字，新的 26 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  ★1000 以上的新名字：aiwithremy/claude-skills-llm-council, anthropics/claude-plugins-official
第 3 組「claude code review plugin」：23 個名字，新的 23 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  ★1000 以上的新名字：nyldn/claude-octopus, dagoste/squadra, pullfrog/pullfrog, anthropics/claude-code-action, anthropics/claude-code
第 4 組「codex review」：21 個名字，新的 21 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  ★1000 以上的新名字：deepmyst/mysti, umputun/ralphex, openai/codex-action
第 5 組「cross-model review」：30 個名字，新的 30 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 6 組「PR review bot open source」：30 個名字，新的 30 個；管道：github-topic, github-keyword, npm, hn, exa, web-en, awesome, skills-sh, mcp-registry
  ★1000 以上的新名字：patched-codes/patchwork, anc95/ChatGPT-CodeReview
第 7 組「bug finding agent」：23 個名字，新的 23 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  ★1000 以上的新名字：trailofbits/skills, Awarexone/Agentic-Bug-Hunter
第 8 組「verification agent」：28 個名字，新的 27 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  ★1000 以上的新名字：reticlehq/reticle, asklokesh/loki-mode, 2akouwu/reverify, cloudflare/security-audit-skill, code-yeongyu/lazycodex, llm-as-a-verifier/llm-as-a-verifier, vibiumdev/vibium, sahibzada-allahyar/formal-verification-rsi, teaql/teaql-agent-kit, maxritter/qualitylayer, amap-ml/longhorizon-harness
第 9 組「AI 程式碼審查」：6 個名字，新的 6 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
第 10 組「code security review」：26 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  ★1000 以上的新名字：kritt-ai/open-kritt, sanyuan0704/sanyuan-skills
第 11 組「git diff review TUI」：37 個名字，新的 37 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  ★1000 以上的新名字：ivankovic/omnidiff, remorses/critique, yoshiko-pg/difit, jnsahaj/lumen
第 12 組「pre-push code review」：27 個名字，新的 27 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
```

---

## 3. ★1,000 以上符合納入標準工具總表（共 53 個，依實測星數排序）

> **驗證說明**：星數、授權（SPDX）與最後 push 日期皆於 **2026-11-18** 透過 `sweep.py verify`（`gh api`）實測完成（帳本共 66 個千星 repo，扣除第 5 節列明之 7 個明確排除與 6 個拿不準項目後，以下 53 個皆符合納入標準）。形式、支援 agent、審查能力（審 diff／整 repo／安全／交叉審）與 Windows 可用性均取自各 repo 官方 README、檔案目錄與 Releases 一手資料，無一手證據者一律標「**待驗證**」。

| # | Repo | 星數 | 授權 | 最後 push | 形式 | 支援 Agent | 審 diff / 整 repo / 安全 / 交叉審 | Windows 能不能用 | 一句話 |
|---:|---|---:|---|---|---|---|---|---|---|
| 1 | [cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill) | ★75,115 | MIT | 2026-09-14 | Skill | Claude Code、Codex 等支援 `skills.sh` 的 agent | 否（主打全庫）／可／可／可（獨立驗證子代理，非強制異質模型） | 待驗證（純 Skill＋Node 驗證腳本，README 未寫 Windows） | Cloudflare 開源 6 階段安全審計 skill，附獨立誤報驗證與機器可讀 `findings.json`。 |
| 2 | [alibaba/open-code-review](https://github.com/alibaba/open-code-review) | ★54,088 | Apache-2.0 | 2026-11-18 | CLI + MCP + Skill | Claude Code、Codex、Cursor 等 | 可／待驗證／可（SQLi、XSS 等多語言規則）／可（Delegation Mode） | 支援（Releases 附 `opencodereview-windows-amd64.exe`；README 標支援） | 阿里巴巴開源混合架構審查 CLI（確定性管線＋LLM），Token 耗量約通用代理九分之一。 |
| 3 | [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) | ★47,618 | Apache-2.0 | 2026-11-18 | 官方 Plugin 市集 | Claude Code | 可（`code-review`、`pr-review-toolkit`）／可／可（`claude-security`、`security-guidance`）／否 | 待驗證（隨 Claude Code 運行，README 未單獨列平台） | Anthropic 官方外掛庫，內含 5 代理平行審查與信心閥值過濾的正式版審查插件。 |
| 4 | [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) | ★35,251 | Apache-2.0 | 2026-07-08 | Claude Code Plugin | Claude Code（調用 Codex CLI） | 可（`/codex:review`、`/codex:adversarial-review`）／待驗證／否／可（核心） | 待驗證（README 未載 Windows；依賴本機 Claude Code ＋ Codex CLI） | OpenAI 官方橋接外掛，直接在 Claude Code 內呼叫 Codex 進行唯讀或對抗審查。 |
| 5 | [tirth8205/code-review-graph](https://github.com/tirth8205/code-review-graph) | ★32,839 | MIT | 2026-11-16 | MCP + CLI + GitHub Action | Claude Code、Codex、Cursor、Windsurf、Gemini CLI、Antigravity 等 | 可（變更影響範圍）／可（全庫 Tree-sitter 圖譜）／否／否 | 支援（README 明列 Windows Codex 與 WSL 設定） | 本機 Tree-sitter 知識圖譜 MCP，讓代理審變更時精準抓出受影響的呼叫鏈與測試。 |
| 6 | [The-PR-Agent/pr-agent](https://github.com/The-PR-Agent/pr-agent) | ★16,366 | MIT | 2026-11-18 | PR Bot + CLI + GitHub Action | 模型無關（經 LiteLLM 接 Claude/OpenAI 等，非 Claude Code/Codex 原生插件） | 可／待驗證／可／待驗證 | 待驗證（Python/Docker，README 未單獨寫 Windows 指引） | 原 CodiumAI 轉社群維護的老牌開源 PR 自動審查機器人，支援多種 Git 平台與本地 CLI。 |
| 7 | [openai/codex-security](https://github.com/openai/codex-security) | ★14,044 | Apache-2.0 | 2026-11-18 | CLI + TypeScript SDK + GitHub Action + Codex Skill | Codex（及獨立 CI） | 可（`--diff origin/main`）／可（`--mode deep`）／可（核心）／否 | 待驗證（Node 套件；README 與 Releases 未見 Windows 說明或執行檔） | OpenAI 官方安全掃描 CLI/SDK（名冊 pending），具備跨倉庫偵測、驗證與修補能力。 |
| 8 | [backnotprop/plannotator](https://github.com/backnotprop/plannotator) | ★13,274 | Apache-2.0 | 2026-11-18 | 本機 WebUI 工作台 + Hook/Skill | Claude Code、Codex、Copilot CLI、Gemini CLI、OpenCode 等 | 可（Plan 與 diff/PR 標註）／否／否／否 | 支援（README 附 Windows PowerShell 安裝與 Codex hook 設定） | 瀏覽器介面計畫與 diff 審查工作台，人類批註完一鍵送回 coding agent 修改。 |
| 9 | [anthropics/claude-code-action](https://github.com/anthropics/claude-code-action) | ★10,000 | MIT | 2026-11-18 | GitHub Action | Claude Code | 可／可／待驗證／否 | 雲端 CI（主要跑於 GitHub Actions） | Anthropic 官方 GitHub Action，在 PR/Issue 中透過 `@claude` 自動審查並實作修正。 |
| 10 | [modem-dev/hunk](https://github.com/modem-dev/hunk) | ★9,843 | MIT | 2026-11-17 | TUI / Web diff 檢視器 + Skill | Claude Code、Codex（透過 `hunk-review` skill） | 可／否／否／否 | 支援（Releases 附 `hunkdiff-windows-x64.tar.gz`；README 明載支援 Windows x64） | 專為 agent 工作流打造的終端機與網頁 diff 檢視器，支援 watch 即時刷新改動。 |
| 11 | [trailofbits/skills](https://github.com/trailofbits/skills) | ★8,267 | CC-BY-SA-4.0 | 2026-11-12 | Plugin / Skill 市集 | Claude Code、Codex | 可（`differential-review`）／可（`c-review`、`rust-review` 等）／可（核心＋`fp-check` 驗誤報）／否 | 待驗證（以 Skill 為主，部分技能需 Semgrep/CodeQL） | Trail of Bits 資安審計技能庫，涵蓋 git 歷史差異安全審查與反駁假陽性工作流。 |
| 12 | [lintsinghua/DeepAudit](https://github.com/lintsinghua/DeepAudit) | ★7,322 | AGPL-3.0 | 2026-11-16 | 可自架 Web 平台 + Docker 沙箱 | 多模型 API / Ollama（非外掛進 Claude Code/Codex CLI） | 待驗證／可（多代理協作漏洞挖掘）／可（含沙箱 PoC 驗證）／否 | 支援（README 附 Windows Docker Desktop 部署說明） | 一鍵 Docker 部署的多代理代碼安全審計平台，具備沙箱實跑驗證 PoC 能力。 |
| 13 | [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) | ★6,990 | MIT | 2026-02-11 | GitHub Action（含 `/security-review`） | Claude Code | 可（PR diff-aware）／否／可（核心）／否 | 待驗證（GitHub Action，README 未提 Windows） | Anthropic 官方開源 PR 資安審查 Action，以 Claude Code 語意分析降低誤報。 |
| 14 | [anc95/ChatGPT-CodeReview](https://github.com/anc95/ChatGPT-CodeReview) | ★4,479 | ISC | 2026-08-10 | PR Review Bot + GitHub Action | OpenAI API | 可／否／否／否 | 雲端 CI / Serverless（README 未提本機 Windows） | 早期高星開源 PR Review Bot，透過 GitHub Action 或自架 Bot 以 ChatGPT 審 PR diff。 |
| 15 | [nyldn/claude-octopus](https://github.com/nyldn/claude-octopus) | ★4,467 | MIT | 2026-11-18 | Claude Code Plugin | Claude Code（協調 Codex、Gemini、Antigravity CLI、Ollama 等 12 家） | 可／可／可（整合 `/security-review`）／可（核心：多模型共識與辯論） | 僅 WSL / SSH（README 明寫不支援原生 Windows） | 從 Claude Code 同時驅動 Codex 等多模型進行對抗辯論與共識閘門的編排外掛。 |
| 16 | [sanyuan0704/sanyuan-skills](https://github.com/sanyuan0704/sanyuan-skills) | ★3,986 | MIT | 2026-05-11 | Skill 集（6 個 skill，含主力審查技） | Claude Code 與相容 `npx skills` 終端機 | 可（`code-review-expert`）／待驗證／可／否 | 待驗證（README 未寫） | 含 `code-review-expert` 與 `skill-review` 的精選技能集（另含 4 個非審查 skill）。 |
| 17 | [code-yeongyu/lazycodex](https://github.com/code-yeongyu/lazycodex) | ★3,924 | MIT | 2026-11-18 | Agent Harness CLI | Codex | 待驗證／可／待驗證／可（支援多代理編排與完成驗證） | 待驗證（README 僅載 CLI 安裝指令） | 專為 Codex 打造的專案記憶、規劃與「verified completion」驗收層。 |
| 18 | [OneRedOak/claude-code-workflows](https://github.com/OneRedOak/claude-code-workflows) | ★3,921 | MIT | 2026-10-09 | Workflow / Slash commands + Action | Claude Code、Codex | 可（`code-review`、`design-review`）／可（`security-review`）／可／否 | 待驗證（README 未寫原生 Windows，僅提一般指引） | 實戰導向的雙迴圈 PR 審查、資安掃描與 Playwright 設計審查工作流範本庫。 |
| 19 | [agavra/tuicr](https://github.com/agavra/tuicr) | ★3,616 | MIT | 2026-11-16 | TUI diff 審查器 + Skill | Claude Code、Codex | 可（Git/jj/Mercurial/PR/MR）／否／否／否 | 支援（Releases 附 `windows-msvc.zip`；README 載 `%APPDATA%` 設定） | Vim 快捷鍵終端機 diff 審查工具，支援離線標註並匯出結構化評論給 agent。 |
| 20 | [chaseai-yt/claudex-loop](https://github.com/chaseai-yt/claudex-loop) | ★3,475 | NOASSERTION（LICENSE 檔為 MIT + 來源聲明） | 2026-10-14 | Plugin + Skills | Claude Code、Codex CLI | 可（計畫審查＋diff 終審）／待驗證／可／可（核心：做與審必跨模型） | 支援（README 附 Windows PowerShell；CI 實測 Windows/macOS/Linux） | 強制「寫的不准自評」之 Claude Code ↔ Codex 跨模型規劃與獨立審查閉環（名冊 pending）。 |
| 21 | [llm-as-a-verifier/llm-as-a-verifier](https://github.com/llm-as-a-verifier/llm-as-a-verifier) | ★3,352 | MIT | 2026-10-08 | 驗證框架 + Claude Code Plugin (`TurboAgent`) | Claude Code、Codex 等 | 可（軌跡與產出細粒度審查）／待驗證／否／可（支援異質驗證模型） | 待驗證（README 未寫） | 研究背景雄厚的通用代理驗證框架，可用輕量或異質模型對 coding agent 步驟做細粒度把關。 |
| 22 | [yoshiko-pg/difit](https://github.com/yoshiko-pg/difit) | ★3,337 | MIT | 2026-08-28 | 本機 WebUI diff 檢視器 + Skill | 支援 `.claude` / `.codex` skills 之 agent | 可（local diff、PR、stdin patch）／否／否／否 | 待驗證（Node CLI，README 未寫 Windows） | 輕量 CLI 一鍵啟動仿 GitHub Files Changed 網頁介面，含 `difit-review` skill 供代理使用。 |
| 23 | [jnsahaj/lumen](https://github.com/jnsahaj/lumen) | ★2,921 | MIT | 2026-09-17 | TUI / CLI diff 檢視與 AI 摘要 | OpenAI/Claude 等 API；支援 Claude/Codex 規則 | 可（Stacked diff、PR、標註）／否／否／否 | 待驗證（README 載 Windows 設定路徑，但 Releases 無 Windows 執行檔，需 `cargo install`） | Rust 寫成的極速終端機並排 diff 工具，結合 AI 變更摘要與行內標註。 |
| 24 | [google/mantis](https://github.com/google/mantis) | ★2,806 | Apache-2.0 | 2026-11-17 | Skills + ADK Harness + GitHub Action | Antigravity、Claude Code 等 | 可（Action 附 PR 掃描但官方標未測）／可／可（核心：漏洞挖掘與修補）／待驗證 | 不支援原生（README 明寫 `native Windows is unsupported`，需 WSL2） | Google 開源的模組化安全漏洞挖掘、沙箱復現與修補技能集（高風險執行需隔離環境）。 |
| 25 | [mattzcarey/shippie](https://github.com/mattzcarey/shippie) | ★2,529 | MIT | 2026-10-21 | CLI + GitHub Action + MCP Client | Claude/OpenAI/OpenRouter 等模型 API | 可／可（agent loop 讀取全庫上下文）／可／待驗證 | 待驗證（Node >= 22.19，README 未明寫 Windows） | 可擴充的程式碼審查與 QA 代理（原 Code Review GPT），能接 MCP 工具並主動閱讀 codebase。 |
| 26 | [Kritt-ai/open-kritt](https://github.com/Kritt-ai/open-kritt) | ★2,432 | AGPL-3.0 | 2026-11-16 | 可自架 Web 平台 + Headless CLI + Docker 沙箱 | Codex、Claude Code、Grok Build | 待驗證／可（全庫＋依賴掃描）／可（核心＋PoC 驗證）／否 | 待驗證（需 Docker Compose 與 Node 20+，README 未寫 Windows 測試） | 實戰賞金團隊開源的自架漏洞研究編排平台，在獨立容器內驗證漏洞與排序。 |
| 27 | [awesome-skills/code-review-skill](https://github.com/awesome-skills/code-review-skill) | ★2,285 | MIT | 2026-09-08 | Skill | Claude Code | 可／可／可／否 | 支援（README 附 Windows PowerShell 安裝指引） | 結構化且分語言（Python/TS/Rust/React/Vue）的 Claude Code 審查規範技能包。 |
| 28 | [the-open-engine/zeroshot](https://github.com/the-open-engine/zeroshot) | ★2,195 | MIT | 2026-11-18 | Multi-agent Graph Harness CLI + MCP + Plugin | Claude Code、Codex、Copilot CLI、Pi | 可／可／可／可（核心：圖節點隔離實作與審查者） | 支援（Releases 附 `zeroshot-*-x86_64-pc-windows-msvc.tar.gz`） | JSON 圖編排引擎，強制由獨立模型／會話節點審查與測試，避免 coding agent 自評過關。 |
| 29 | [maxritter/qualitylayer](https://github.com/maxritter/qualitylayer) | ★2,151 | NOASSERTION（商業 Source-Available 授權） | 2026-11-18 | 桌面 App + CLI + Skills | Claude Code、Codex、Cursor、Grok、Antigravity 等 | 可／可／可／可（independent review 獨立代理檢查） | 支援（Releases 附 Windows `.exe` 安裝檔與 `install.ps1`） | 強調人機在迴圈的軟體工廠工作台，支援計畫審查、步驟檢查點與獨立代理驗收。 |
| 30 | [px0-ai/px0](https://github.com/px0-ai/px0) | ★1,959 | MIT | 2026-11-06 | 瀏覽器審查工作台 / 極速 IDE CLI | Claude Code、Codex、Cursor Agent 等 | 可（PR diff 與未 push commit）／可／否／否 | 待驗證（Go/Node；目前安裝腳本與 Releases 未見 Windows binary） | 針對 AI 生成程式碼的高速瀏覽器審查控制台，可將選定程式碼範圍直接派回本地 agent 修正。 |
| 31 | [AMAP-ML/LongHorizon-Harness](https://github.com/AMAP-ML/LongHorizon-Harness) | ★1,877 | MIT | 2026-11-11 | 長時程循環工程 Harness CLI | Claude Code、Codex、OpenCode、DeepSeek Harness | 待驗證／可／待驗證／可（支援獨立稽核角色） | 僅 WSL2（README 明寫原生 Windows 受阻於 POSIX 控制機制） | 讓 Claude Code 與 Codex 跨桌面與終端長跑數十小時，並透過獨立稽核驗證進度。 |
| 32 | [kenn-io/roborev](https://github.com/kenn-io/roborev) | ★1,820 | MIT | 2026-11-18 | 背景審查守護程式 + TUI + MCP + Skill | Claude Code、Codex 等 | 可（自動持續背景審查＋`/roborev-refine`）／待驗證／待驗證／可（支援指定 Codex 審 Claude 變更） | 支援（README 附 Windows PowerShell `install.ps1`） | 背景常駐審查資料庫與 TUI，會自動檢查每次提交並把問題餵回 agent 自動修復。 |
| 33 | [vercel-labs/openreview](https://github.com/vercel-labs/openreview) | ★1,709 | 無 | 2026-03-06 | 可自架 PR Review Bot（Vercel + GitHub App） | Claude（AI SDK）＋ `.agents/skills/` | 可（PR inline suggestion）／否／可（可擴充安全 skill）／否 | 雲端自架（部署於 Vercel，非本機 Windows 工具） | Vercel 開源的輕量自架 PR 審查機器人，支援 `skills.sh` 規範審查技能。 |
| 34 | [kodustech/kodus-ai](https://github.com/kodustech/kodus-ai) | ★1,627 | NOASSERTION（雙授權：核心 AGPL-3.0 ＋ 企業版） | 2026-11-18 | 可自架 AI 審查平台 + CLI | BYOK 模型（Claude、GPT-5、Gemini 等） | 可（PR 與本機 CLI）／待驗證／可／否 | 待驗證（Docker 自架＋CLI；註：自架每日回傳 1 次匿名心跳） | 可自架 BYOK PR 審查與規則治理平台（Kody Rules），並追蹤跨 PR 未修正建議。 |
| 35 | [hyhmrright/brooks-lint](https://github.com/hyhmrright/brooks-lint) | ★1,582 | MIT | 2026-11-17 | Skills（6 支）+ 報告 CLI | Codex、Claude Code、Cursor 等 14 平台 | 可（`$brooks-review`）／可（架構、技術債與測試品質）／待驗證／否 | 待驗證（安裝指令為 `bash` 與 `npx`，README 未明寫 Windows） | 聚焦架構腐化、技術債與測試質量的 6 個可攜式 AI 審查技能與健康儀表板。 |
| 36 | [patched-codes/patchwork](https://github.com/patched-codes/patchwork) | ★1,581 | AGPL-3.0 | 2026-08-24 | 自架 CLI 工作流框架（`patchwork-cli`） | 多模型 API（OpenAI/Anthropic/本地） | 可（`PRReview`）／可／可（漏洞修補）／否 | 待驗證（Python/Poetry，README 未寫 Windows） | 以可組合 patchflow 自動執行 PR 審查、依賴升級與安全補丁的開源 CLI 框架。 |
| 37 | [umputun/ralphex](https://github.com/umputun/ralphex) | ★1,517 | MIT | 2026-11-16 | 自主計畫執行與多階段審查 CLI | Claude Code、Codex | 可（5 代理 → Codex → 2 代理 diff 管線）／可／待驗證／可（核心） | Best-effort（README 明寫無 Windows 預編譯檔、作者無環境實測） | 先用 Claude Code 依計畫實作，再自動經過多代理與 Codex 交叉審查的純終端機管線。 |
| 38 | [HexmosTech/git-lrc](https://github.com/HexmosTech/git-lrc) | ★1,496 | NOASSERTION（Fair-code source-available） | 2026-11-12 | Git Hook CLI | 獨立執行並可「Send to Claude」回送 | 可（commit 前微審查）／否／可（憑證與錯誤處理）／否 | 支援（README 專節附 Windows PowerShell 安裝與設定） | 掛載於 `git commit` 的本地煞車系統，專門攔截 AI agent 偷刪邏輯或洩漏憑證。 |
| 39 | [pullfrog/pullfrog](https://github.com/pullfrog/pullfrog) | ★1,461 | MIT | 2026-11-18 | GitHub Actions BYOK PR Bot | 包裝 Claude Code、Codex、OpenCode | 可／可／待驗證／待驗證 | 雲端 CI（跑在 GitHub Actions） | 號稱「跑在 GitHub Actions 裡的 BYOK CodeRabbit」，直接調用你的 Claude/Codex 額度審 PR。 |
| 40 | [sashiko-dev/sashiko](https://github.com/sashiko-dev/sashiko) | ★1,432 | Apache-2.0 | 2026-11-18 | 本機 CLI + 守護程式 + WebUI | Claude Code CLI、Copilot CLI、Gemini、OpenAI | 可（`sashiko review` 審本地 commit）／可（`codebase scanning`）／可（溢位/越界/TOCTOU）／否 | 待驗證（Releases 僅見 Linux x86_64，面向系統與核心開發） | Linux Foundation 支持的系統級深度補丁審查工具，專抓人工審查容易漏掉的底層記憶體與併發 bug。 |
| 41 | [Gentleman-Programming/gentleman-guardian-angel](https://github.com/Gentleman-Programming/gentleman-guardian-angel) | ★1,350 | MIT | 2026-07-08 | Git Pre-commit Hook CLI（Bash） | Claude Code、Codex、Gemini、Ollama、OpenCode 等 | 可（依規則審 staged diff）／否／待驗證／可（可指定異質審查 CLI） | 支援（README 明記 Git Bash、WSL 與 `gga.bat` 支援 PowerShell） | 輕量 Git hook 把關器，commit 前用任何你指定的 AI CLI 對 staged changes 做規則檢查。 |
| 42 | [2akouwu/reverify](https://github.com/2akouwu/reverify) | ★1,347 | MIT | 2026-11-01 | MCP Server + CLI | Claude Code、Codex、Gemini CLI、OpenCode | 否（著重事實查核與靜態分析驗證）／可／可（二進位與靜態驗證）／否 | 支援（CI 於 Windows 實測 PE/系統檔案驗證） | 讓決定性工具查證 AI 的每個技術宣稱，確保只有經過實證的事實才會保留下來。 |
| 43 | [amElnagdy/guard-skills](https://github.com/amElnagdy/guard-skills) | ★1,316 | MIT | 2026-07-04 | 5 個品質閘門 Skills | Claude Code、Codex | 可（針對 diff 做二輪把關：`clean-code`、`test`、`docs`）／待驗證／可（限 WP/Woo；通用待驗證）／否 | 待驗證（純 Markdown skills，README 未寫 Windows） | 專抓 AI 寫程式常見偷懶模式（濫用 Mock、吞掉例外、幻覺文件）的二輪品質閘門。 |
| 44 | [openai/codex-action](https://github.com/openai/codex-action) | ★1,308 | Apache-2.0 | 2026-11-18 | 官方 GitHub Action | Codex CLI | 可（README 範例主打 PR 自動審查）／可／待驗證／可（CI 端用 Codex 審異質模型產出） | 支援受限（README 明寫 Windows runner 須設 `safety-strategy: unsafe`） | OpenAI 官方 GitHub Action，提供安全代理層在 CI 裡運行 Codex 執行自動化 PR 審查。 |
| 45 | [remorses/critique](https://github.com/remorses/critique) | ★1,290 | MIT | 2026-11-02 | TUI + Web 預覽 + Skill | 終端機 / Agent（依賴 Bun） | 可（含實驗性 `--calldiff` 呼叫樹差異）／否／否／否 | 待驗證（需 Bun runtime，README 未寫 Windows 實測） | 具現代 UI 與函式呼叫堆疊差異檢視能力的終端機 diff 工具，支援產生可分享的審查連結。 |
| 46 | [reticlehq/reticle](https://github.com/reticlehq/reticle) | ★1,289 | NOASSERTION（各 npm 套件採 Apache-2.0） | 2026-11-17 | Runtime 驗收 CLI + MCP + Hooks | Claude Code、Codex、Cursor | 否（對實跑中的網頁/桌面 app 驗收真實功能，回傳 `file:line`）／否／否／否 | 支援（README 專列 Windows PowerShell `--expect-file` 用法） | 「你的 agent 說做完了，Reticle 實際跑起來驗真假」，回傳帶 `file:line` 的通過與否判決。 |
| 47 | [dagoSte/squadra](https://github.com/dagoSte/squadra) | ★1,283 | MIT | 2026-11-12 | 多代理協調 CLI + 本機儀表板 + MCP + Skills | Claude Code、Codex、Cursor | 可（不同視窗獨立審查）／可／可（含安全掃描確認）／可（核心） | 待驗證（README 徽章寫 `macOS | POSIX`） | 讓多個 Claude Code、Codex 與 Cursor 視窗組隊，寫與審嚴格分窗且每步保留本機證據。 |
| 48 | [openqodex/openqodex](https://github.com/openqodex/openqodex) | ★1,207 | Apache-2.0 | 2026-11-17 | Pre-push 獨立審查 CLI + Code Graph + Hooks | Claude Code、Codex CLI、Cursor、Cline | 可（push 前獨立新進程無記憶審查）／可（code graph）／待驗證／可（支援 Claude ↔ Codex） | 未測試（README 明記 `No test runs on Windows or WSL`） | 不需額外 API key，直接使用本機訂閱啟動「失憶的獨立審查進程」在 push 前抓錯。 |
| 49 | [DeepMyst/Mysti](https://github.com/DeepMyst/Mysti) | ★1,159 | Apache-2.0 | 2026-11-10 | VS Code 擴充套件 | Claude Code、Codex、Ollama 等 | 可（`@claude @codex` 各自審查並彙整）／可／待驗證／可（核心） | 支援（README 明記 Windows/macOS/Linux VS Code） | VS Code 內的雙代理協作聊天室，可同時呼叫 Claude Code 與 Codex 獨立檢查邊界案例。 |
| 50 | [asklokesh/loki-mode](https://github.com/asklokesh/loki-mode) | ★1,119 | NOASSERTION（BSL 1.1 Source-Available） | 2026-11-18 | 自治開發與驗收收據 CLI + Plugin + MCP | Claude Code、Codex、OpenCode | 可（specialist review council）／可／可（偵測 secret 攔截 push）／待驗證 | 待驗證（README 未寫 Windows） | 先從任務書寫交付合約與檢查，最後由專家委員會審查並封裝離線可驗證的簽章收據。 |
| 51 | [villesau/ai-codereviewer](https://github.com/villesau/ai-codereviewer) | ★1,047 | MIT | 2024-08-19 | GitHub Action | OpenAI GPT-4 API | 可／否／可／否 | 雲端 CI（註：最後 push 為 `2024-08-19`，低活躍） | 早期純 TypeScript PR Review GitHub Action，將 PR diff 分塊送交 GPT-4 評審。 |
| 52 | [sno-ai/sno-station](https://github.com/sno-ai/sno-station) | ★1,026 | Apache-2.0 | 2026-11-18 | 多代理本機互審工作站 + CLI | Codex、Claude Code、Cursor、Hermes Agent、OpenClaw | 可（建置者 vs 挑戰審查者爭辯定案）／可／待驗證／可（核心） | 支援（README 提及 Windows；tmux 視窗依賴需注意原生 vs WSL 環境） | 讓 Claude Code 與 Codex 同台互審並可在額度耗盡時無縫接棒，問題先由兩者吵完再交給你。 |
| 53 | [persiyanov/herdr-reviewr](https://github.com/persiyanov/herdr-reviewr) | ★1,007 | MIT | 2026-11-15 | 終端機旁置 diff 審查外掛 | Claude Code、Codex、OpenCode、Pi | 可（支援只看最後一輪改動 `last turn`）／可（All files）／否／否 | 支援（Releases 附 `windows-msvc.zip`；README 註明 Windows 快速鍵調整） | `herdr` 終端機外掛，一邊對話寫碼、一邊看語法高亮 diff 並一鍵把評論送回 agent 輸入框。 |

---

## 4. ★100 到 999 裡值得注意的候選（帳本共收錄 116 個）

> **說明**：因達 12 組上限且停等門檻設為 `--min-stars 1000`，`★100–999` 區間不保證已掃盡；以下依 R1 情境精選具代表性或名冊關聯專案（★實測值來自 `2026-11-18` `sweep.py verify` 或帳本紀錄）：

### A. 名冊 pending 與高度貼合 R1（Claude Code ↔ Codex 互審／驗收）
- **[pullboard-dev/pullboard](https://github.com/pullboard-dev/pullboard)**（★846 實測，MIT，最後 push 2026-11-15）— **名冊 pending**：Git 倉庫內建的自治團隊看板與 MCP；強調「green gate on a runner ＋ **另一支不同 agent 驗證該 exact commit**」。目前 CI 僅測 Linux/macOS，Windows 尚未實測。
- **[gmickel/flow-next](https://github.com/gmickel/flow-next)**（★725 實測，MIT，最後 push 2026-11-18）：支援 Claude Code、Codex、Cursor、Grok Build 等的多步驟規格驅動外掛，核心鐵律為「寫出 diff 的模型絕不審查它」，支援跨模型依風險分級審查與 3 OS CI。
- **[hamelsmu/claude-review-loop](https://github.com/hamelsmu/claude-review-loop)**（★734 實測，無授權標示，最後 push 2026-03-15）：Claude Code `/review-loop` 外掛，利用 Stop hook 在 Claude 完成後自動啟動多路平行 Codex 子代理審 `git diff` 與 OWASP Top 10 並回饋修復。
- **[DanMcInerney/architect-loop](https://github.com/DanMcInerney/architect-loop)**（★629 實測，MIT，最後 push 2026-09-13）：附 Windows `install.ps1`，採策略師／對抗審查與建置者分離的 Claude/Codex 循環（作者現註記正被其新作 `orchflows` 取代）。
- **[chorus-codes/chorus](https://github.com/chorus-codes/chorus)**（★534 實測，Apache-2.0，最後 push 2026-08-13）：透過本機訂閱 CLI 同時召集 2–3 家不同廠商（Claude、Codex、Gemini）平行審查同一變更，達成共識才放行，且 README 有專門處理 Windows 路徑與跨平台問題紀錄。
- **[razzant/claudexor](https://github.com/razzant/claudexor)**（★525）：Claude Code 與 Codex 雙模型交叉審查外掛。（註：另有專為 Windows PowerShell 7.4+ 開發實測的雙模型互審 skill [brettchangus/cross-review](https://github.com/brettchangus/cross-review)，雖目前為 ★0 剛起步，但對 R1 Windows 原生環境設計極具參考價值）。

### B. 證據驅動審查閘門、靜態＋AI 安全／Bug 獵手
- **[duriantaco/skylos](https://github.com/duriantaco/skylos)**（★947 實測，Apache-2.0，最後 push 2026-11-18）：專抓 AI 生成程式碼常見錯誤（死碼、安全漏洞、密鑰、品質退化）的本機 PR 掃描器與 MCP，支援 Linux/macOS/Windows。
- **[arm/metis](https://github.com/arm/metis)**（★893 實測，Apache-2.0，最後 push 2026-11-17）：Arm 產品安全團隊開源之深度安全程式碼審查框架，結合 Tree-sitter 切分與語言外掛。
- **[asamassekou10/ship-safe](https://github.com/asamassekou10/ship-safe)**（★872 實測，MIT，最後 push 2026-10-17）：獨立安全驗證 CLI（確定性掃描核心 ＋ LLM 調查驗證 ＋ 互動式修復計畫），支援完全離線 `--no-ai` 與 SARIF 輸出，涵蓋 Windows PowerShell/供應鏈攻擊特徵。
- **[specular-org/Specula](https://github.com/specular-org/Specula)**（★660 實測，Apache-2.0，最後 push 2026-11-18）：用 TLA+ 形式化規格搭配 Claude Code / Codex 挖掘系統深層併發／邏輯 bug 之代理工具（Windows 需於 WSL2 運行）。
- **[codexstar69/bug-hunter](https://github.com/codexstar69/bug-hunter)**（★568 實測，MIT，最後 push 2026-10-29）：支援 Claude Code 與 Codex CLI 的對抗式（Hunter / Skeptic / Referee / Fixer）抓 bug 與安全審查 skill／CLI。
- **[kyy-logs/code-review-gate-skill](https://github.com/kyy-logs/code-review-gate-skill)**（★511 實測，MIT，最後 push 2026-11-18）：強調「可稽核證據」的靜態優先四探針審查 skill（支援 Claude Code / Codex 與 Windows Git Bash）。
- **[imbue-ai/vet](https://github.com/imbue-ai/vet)**（★493 實測，AGPL-3.0，最後 push 2026-09-14）：Imbue 出品的獨立驗證 CLI 與 skill，專門對照「使用者原始要求 vs agent 實際 diff」抓出未明講的行為落差。
- **[getsentry/warden](https://github.com/getsentry/warden)**（★425 實測，NOASSERTION，最後 push 2026-11-17）：Sentry 開發、以 `.agents/skills/` / `.claude/skills/` 為分析單元的本機＋CI PR 審查代理。

### C. Diff 審查工作台與自架 PR Review 工具
- **[umputun/revdiff](https://github.com/umputun/revdiff)**（★960 實測，MIT，最後 push 2026-11-18）：無須離開終端機即可在 Claude Code 工作階段內進行行內註解並輸出結構化回饋至 stdout 的 Go TUI。
- **[nilbuild/diffity](https://github.com/nilbuild/diffity)**（★919 實測，MIT，最後 push 2026-11-17）：仿 GitHub 介面的桌面 diff 審查 app，行內留言可直接與 Claude Code 對話釐清與修補（僅支援 macOS/Linux）。
- **[Nikita-Filonov/ai-review](https://github.com/Nikita-Filonov/ai-review)**（★610 實測，Apache-2.0，最後 push 2026-10-03）：支援 GitHub/GitLab/Bitbucket/Azure DevOps/Gitea 與多種 LLM 的 Python PR 審查工具。
- **[Nayjest/Gito](https://github.com/Nayjest/Gito)**（★476 實測，MIT，最後 push 2026-10-01）：Python AI 審查 CLI／Action，Releases 附 Windows 安裝檔 `gito-setup-4.5.0.exe`。
- **[puemos/lareview](https://github.com/puemos/lareview)**（★185 實測，Apache-2.0，最後 push 2026-11-12）：支援 ACP（Agent Client Protocol）的 Rust 審查工作台，把大型 PR 按風險與流程拆成審查任務（Windows 需跑在 WSL2）。

---

## 5. 「拿不準」（未列入主表）與明確排除項目

### A. 拿不準：只賣 SaaS、無開源或本機獨立引擎者（含僅提供薄客戶端 CLI / 外掛者）
以下商用服務雖然廣泛出現於「AI code review / claude code review」搜尋結果，也常支援整合 Claude Code / Codex 或提供本機 CLI 指令，但核心審查引擎為閉源雲端 SaaS（僅列名稱與現象供判斷，不計入開源主表）：
- **CodeRabbit**：主打雲端 SaaS，雖有本機終端機 CLI 與開源 skill 集 `coderabbitai/skills`（★未滿千），但 CLI 審查仍連向 CodeRabbit 雲端（其早期開源 `coderabbitai/ai-pr-reviewer` 已過時／轉商業閉源）。
- **Greptile**：提供 `greptileai/cli` 與 `greptileai/skills`，但核心索引與審查運算皆依賴 Greptile 閉源雲端平台（自架僅限企業方案）。
- **Cubic**（`cubic.dev`）：主打雲端 PR review SaaS，另提供透過 ACP 驅動本機 Claude Code 的 CLI 封裝，核心平臺閉源。
- **Ellipsis**（`ellipsis-dev/cli`）：CLI 本身為 MIT 薄客戶端，但實際審查與修復邏輯跑在閉源雲端後端。
- **[sourcery-ai/sourcery](https://github.com/sourcery-ai/sourcery)**（★1,887 實測，MIT，最後 push 2026-11-10）：GitHub repo 為 MIT CLI/Action 殼層，但官方文件明載須將程式碼 diff 傳送至 Sourcery 雲端後端調用 OpenAI/Anthropic 審查，且無整合 Claude Code/Codex 本機代理。
- **其他純 SaaS／閉源審查服務**（於網頁／Product Hunt／Exa 管道出現，無開源本機引擎）：**Bito**、**kluster.ai**、**Codity**、**Caliper**、**BeSwarm**、**MatterAI**、**Jazzberry**、**Detail**、**OhMyBug**、**Bugpatrol**。

### B. 拿不準：帳本中界線模糊之 ★1,000+ 邊界項目（共 6 個）
- **[sourcebot-dev/sourcebot](https://github.com/sourcebot-dev/sourcebot)**（★4,034 實測，MIT）：主體為自架 Code Search 與 Ask Sourcebot MCP 伺服器；雖然其官網文件列有 `review-agent` 功能，但經核對開源 repo 目錄結構，未見對應的 open-source review agent 套件實作。
- **[aiwithremy/claude-skills-llm-council](https://github.com/aiwithremy/claude-skills-llm-council)**（★3,126 實測，無授權）：Claude Code skill，把單一決策問題交給 5 個不同角色顧問互評；定位偏「泛用決策委員會」而非專職程式碼 diff／bug 審查。
- **[VibiumDev/vibium](https://github.com/VibiumDev/vibium)**（★2,960 實測，Apache-2.0）：自稱 "verification layer for coding agents"，但實際核心是跨平台瀏覽器自動化與截圖技能（`browser` skill），性質更近瀏覽器 E2E 驅動而非程式碼審查工具（與 `reticlehq/reticle` 主打任務完工程度實機判決不同）。
- **[sahibzada-allahyar/Formal-Verification-RSI](https://github.com/sahibzada-allahyar/Formal-Verification-RSI)**（★2,908 實測，MIT）：研究性質之 Lean 4 / Dafny 形式化定理證明檢查器與防作弊 RSI 循環，面向數學／形式驗證基準測試而非日常程式碼審查。
- **[teaql/teaql-agent-kit](https://github.com/teaql/teaql-agent-kit)**（★2,822 實測，MIT）：深度綁定 TeaQL 模型驅動開發與應用生成的專用套組，非通用程式碼審查工具。
- （註：另有部分多用途開發流程／安全合集如 `dsifry/metaswarm` ★432、`project-codeguard/rules` ★428 位於百星區間，同樣具多用途合集邊界性質。）

### C. 明確排除之 ★1,000+ 誤命中項目（共 7 個，帳本內已標記識別）
- **[anthropics/claude-code](https://github.com/anthropics/claude-code)**（★156,114）：Coding agent 本體（其內建審查指令為本次現任比較基準，非獨立外掛工具）。
- **[reviewdog/reviewdog](https://github.com/reviewdog/reviewdog)**（★9,751）、**[danger/danger](https://github.com/danger/danger)**（★5,697）、**[danger/danger-js](https://github.com/danger/danger-js)**（★5,520）：傳統靜態 linter／PR 規則執行與留言管線，不含 coding agent 或 AI 語意審查整合。
- **[awarexone/Agentic-Bug-Hunter](https://github.com/awarexone/Agentic-Bug-Hunter)**（★5,986）：對接 YesWeHack、Synack、HackenProof 的滲透與漏洞懸賞偵查工具（紅隊攻擊類排除）。
- **[openedclaude/claude-reviews-claude](https://github.com/openedclaude/claude-reviews-claude)**（★1,646）：閱讀與解析 Claude Code 原始碼的 17 章技術專欄文章，非軟體工具。
- **[ivankovic/omnidiff](https://github.com/ivankovic/omnidiff)**（★1,413）：通用檔案／影像／游標（`.cur`）內容感知比對演算法庫，非 coding agent 審查工具。

---

## 6. 哪裡查不到／待驗證說明

1. **各搜尋管道實務限制**：
   - **`AI 程式碼審查`（第 9 組中文搜尋）**：`github-topic`、`awesome`、`skills-sh`、`mcp-registry`、`hn` 皆回傳 **0 筆**（`github-keyword` 僅 7 筆），顯示中文化關鍵字在英文主導的程式管道幾乎無法觸及工具本體，主要依靠 `web-zh` 與雙語 repo 補齊。
   - **`PR review bot open source`（第 6 組）**：`awesome`、`skills-sh`、`mcp-registry` 在此組複合關鍵字下皆為 **0 筆**相關命中。
   - **`awesome` 管道**：在 `cross-model review`（0 筆）、`git diff review TUI`（0 筆）與多數單一關鍵字僅回傳 0–5 筆；故本次另外針對 `zhuyansen/awesome-claude-code-review`、`kodustech/awesome-code-review-tools` 與 `alibaba/open-code-review` 執行 `sweep.py related` 人工挑選補齊。
   - **`mcp-registry`**：僅取第一個長度大於等於 3 的英文詞作名稱子字串搜尋，無法直接搜尋複合主題，需靠 `exa` 與 `web-en` 補回（如 `tirth8205/code-review-graph`、`2akouwu/reverify`、`reticlehq/reticle`）。
   - **`skills.sh`**：受 IP 限速保護，單次最多回傳約 20 筆且對長複合詞命中極低。
   - **`exa`**：匿名免金鑰端點每次回傳上限 10 筆，超過者需靠 `web-en` 與 `github-keyword` 互補。
   - **`producthunt`**：無免金鑰公開 API，第 1 組採網頁搜尋 `site:producthunt.com` 補齊（命中 Cubic、Greptile、CodeRabbit、Bugpatrol、Claudex 等線索，其中多數屬純 SaaS 而歸入第 5 節）。
2. **「待驗證」欄位處理原則**：
   - 凡表列之「Windows 能不能用」與「審 diff／整 repo／安全／交叉審」欄位，皆僅採信各 repo 之 README、`LICENSE` 檔與 GitHub Releases 一手資產清單（不把 README 宣傳與安全宣稱當成已驗證事實，亦不執行 README 內任何安裝或遙測指令）。未於一手檔案明確載明 Windows 支援或測試狀態者，一律標為「**待驗證**」，不依語言（如 Node.js/Python/Markdown）自行臆測在 Windows 原生環境（含 hook/POSIX 路徑相容性）可無痛運作。
