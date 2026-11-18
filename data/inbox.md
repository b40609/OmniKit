# 新看到的工具與來源（凍結期間的收件匣）

2026-11-15 到 2026-11-29 凍結：不加新功能、不接新來源（見 `docs/proposals/2026-11-15-maturity.md` 的 A）。
看到值得看的，在這裡記一行；每週用 `omnikit-eval` 一次看完，看完的刪掉或移到名冊。

格式：`- 日期｜名稱｜網址｜可能對應的槽位｜一句話`

- 2026-11-15｜Claude Code Setup｜github.com/anthropics/claude-plugins-official（plugins/claude-code-setup）｜專案層自動化（名冊還沒有這個槽位）｜官方，依專案檔建議 hook、skill、subagent、MCP、plugin 各 1 到 2 個；唯讀；跟 OmniKit 幾乎不重疊
- 2026-11-15｜mcp-graveyard、skill-graveyard、mcp-usage｜（套件頁，見成熟度提案）｜使用統計｜只管 Claude Code 的「找沒在用」，品質沒驗證
- 2026-11-17｜deja-vu｜github.com/vshulcz/deja-vu｜交接、讀紀錄（名冊沒有這個槽位）｜跨 46 家 agent 的對話搜尋、交接、壓縮後救回；Go 單檔、不呼叫 LLM；可取代自己寫的紀錄解析，沒實測
- 2026-11-17｜mcp-scanner｜github.com/cisco-ai-defense/mcp-scanner｜第 0 層掃描｜跟現在用的 skill-scanner 同一家，補 MCP server 的掃描；Apache-2.0
- 2026-11-17｜Ultra Lab 開源工具精選｜ultralab.tw/picks｜雷達來源｜台灣團隊、46 個、有「我們跑過」標記、每週一寄漲星前十；跟名冊重疊 17 個
- 2026-11-17｜Awesome-Agent-Harness｜github.com/Gloriaameng/Awesome-Agent-Harness｜調研來源｜harness 綜述加 34 個系統的證據矩陣，截到 2026-10-13
- 2026-11-17｜features-overview 觸發表｜code.claude.com/docs/en/features-overview｜起手清單、對照表｜官方「什麼症狀加什麼」；12-01 雷達補進去
- 2026-11-18｜entire CLI｜github.com/entireio/cli｜交接、讀紀錄｜★5,343，把 agent 對話跟 commit 一起建索引；見 data/evals/2026-11-18-research-stop-trial.md
- 2026-11-18｜cli-continues｜github.com/yigitkonur/cli-continues｜交接｜★1,606，讀 16 種 CLI 的對話紀錄產生交接文件；可對照 omnikit-handoff
- 2026-11-18｜openwolf｜github.com/cytostack/openwolf｜記憶｜★2,401，AGPL-3.0，跨 Claude Code、Codex、OpenCode 的可攜專案記憶
