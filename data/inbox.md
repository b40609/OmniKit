# 新看到的工具與來源（凍結期間的收件匣）

2026-11-15 到 2026-11-29 凍結：不加新功能、不接新來源（見 `docs/proposals/2026-11-15-maturity.md` 的 A）。
看到值得看的，在這裡記一行；每週用 `omnikit-eval` 一次看完，看完的刪掉或移到名冊。

格式：`- 日期｜名稱｜網址｜可能對應的槽位｜一句話`

- 2026-11-15｜Claude Code Setup｜github.com/anthropics/claude-plugins-official（plugins/claude-code-setup）｜專案層自動化（名冊還沒有這個槽位）｜官方，依專案檔建議 hook、skill、subagent、MCP、plugin 各 1 到 2 個；唯讀；跟 OmniKit 幾乎不重疊
- 2026-11-15｜mcp-graveyard、skill-graveyard、mcp-usage｜（套件頁，見成熟度提案）｜使用統計｜只管 Claude Code 的「找沒在用」，品質沒驗證
- 2026-11-17｜mcp-scanner｜github.com/cisco-ai-defense/mcp-scanner｜第 0 層掃描｜跟現在用的 skill-scanner 同一家，補 MCP server 的掃描；Apache-2.0。2026-11-18 重評：Lightpanda、OpenDesign、REA 都帶 MCP server，layer0 --scan 只掃 skill、MCP 那一半沒掃到，凍結結束後優先補
- 2026-11-17｜Ultra Lab 開源工具精選｜ultralab.tw/picks｜雷達來源｜台灣團隊、46 個、有「我們跑過」標記、每週一寄漲星前十；跟名冊重疊 17 個
- 2026-11-17｜Awesome-Agent-Harness｜github.com/Gloriaameng/Awesome-Agent-Harness｜調研來源｜harness 綜述加 34 個系統的證據矩陣，截到 2026-10-13
- 2026-11-18｜Obscura｜github.com/h4ckf0r0day/obscura｜browser、web-sources｜★36,291、Apache-2.0；Lightpanda 同類，README 寫有 Windows 版與頁面繪製、截圖；沒實測
- 2026-11-18｜Moli｜github.com/lexmount/moli｜browser、web-sources｜★23,987、Apache-2.0；Rust 無頭瀏覽器，README 寫支援 Windows、可截圖、有 WebMCP；沒實測
- 2026-11-18｜Open CoDesign｜github.com/OpenCoworkAI/open-codesign｜frontend-design｜★8,238、MIT；另一個開源 Claude Design 替代，自帶 agent 的 Electron app、沒有 CLI；OpenDesign 的對照
- 2026-11-18｜ui-ux-pro-max-skill｜github.com/nextlevelbuilder/ui-ux-pro-max-skill｜frontend-design｜★151,129、MIT；跨 10 多家 agent 的 UI 設計 skill，名冊還沒有卡；來源 data/evals/2026-11-18-tool-reeval/design-research.md
- 2026-11-18｜hallmark｜github.com/Nutlope/hallmark｜frontend-design、web-pages｜★57,218、MIT；50 套主題加真瀏覽器審查（/hallmark audit）；名冊還沒有卡
- 2026-11-18｜emilkowalski/skills、google-labs-code/design.md｜github.com/emilkowalski/skills、github.com/google-labs-code/design.md｜frontend-design｜★57,894、★28,937；動效細節 skill 與 DESIGN.md 官方格式加 linter；OpenDesign 讀的就是 DESIGN.md
- 2026-11-19｜Claude Code Code Mode｜code.claude.com/docs/en/code-mode｜官方功能雷達（12-01 一起看）｜實驗功能，`CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=1`、v2.1.323+，只在終端機互動 `claude` 有效（不支援桌面版、Agent SDK、`-p`、Remote Control、Claude in Chrome）。初判（桌面版查的，待核對官方原文）：OmniKit 只有 Stop、SessionStart hook，不受影響；claude-mem 的 PreToolUse hook（timeout 15s）在 Code Mode 下失敗或逾時會擋掉工具呼叫，claude-mem 會不會被列為不相容 plugin【待驗證】；`git push -f` 的 ask 規則在 Code Mode 下仍照 Bash 規則比對複合指令【待驗證】
