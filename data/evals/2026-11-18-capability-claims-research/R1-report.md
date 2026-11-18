# 調研 R1：讓 coding agent 知道「這台機器上有哪些工具可用」的做法與工具

> 調研日期：2026-11-18
> 停止狀態：長尾未飽和（第 8 組達標；全體名字連續 0 組無新名字，★1,000 以上 GitHub repo 連續 3 組無新名字）

---

## 一、判斷標準與調研設定

### 判斷標準
- **算數的名字**：能自動把「本機或專案裡有哪些可用的 CLI、MCP server、agent 工具」告訴 agent，或讓 agent 依需求搜尋、載入工具定義的工具／腳本／MCP server／skill／官方功能。
- **不算數的名字**：一般的 MCP 目錄網站、純 CLI 開發框架（如 `cobra`、`yargs` 等用來寫 CLI 的函式庫）、單純封裝特定 API 的單一功能 MCP server。

### 挑選與擴展過的關鍵字
1. `agent tool discovery`（起手英文原話）-> 挑出新詞：`tool search`、`dynamic tool loading`、`mcp gateway`
2. `mcp server discovery local`（起手英文同義／本機範圍）-> 挑出新詞：`progressive disclosure`、`mcp2cli`、`lazy loading`
3. `command line tools inventory`（起手一般說法，不含 agent/AI/MCP）-> 挑出新詞：`clidex`、`clihub`
4. `agent 工具 自動 探索 本機 指令`（中文關鍵字）-> 挑出新詞：`SessionStart`、`opencli`
5. `dynamic tool loading`（從第 1、4 組挑出）
6. `sessionstart hook environment tools`（從第 4 組與官方文件挑出）
7. `progressive disclosure cli mcp`（從第 2、5 組挑出）-> 挑出新詞：`capability discovery`
8. `capability discovery agent cli`（從第 7 組與業界文章挑出）

---

## 二、飽和狀態、管道與停點（`sweep.py status` 完整輸出）

- **停止依據**：**長尾未飽和**（第 8 組停）。第 6、7、8 組連續 3 組沒有 ★1,000 以上的新 GitHub repo，但長尾小 repo（★0–★13）每組仍持續冒出，故依「★1,000 以上連續 3 組無新名字」停止；★1,000 以下與無星數的產品名單不保證找齊。
- **查不到或 0 筆的管道說明**：
  - 本次所有腳本管道（`github-topic`、`github-keyword`、`awesome`、`skills-sh`、`npm`、`mcp-registry`、`hn`、`exa`）皆成功連線且無 API 限速或錯誤。
  - 部分管道依 `sweep.py` 規則回 0 筆或不送出查詢：例如第 4 組中文關鍵字因無 3 字元以上英文詞，`mcp-registry` 不查（0 筆）、`skills-sh` 拿掉通用字後無關鍵字不查（0 筆）、`github-keyword` 與 `hn` 回 0 筆；第 2、3、6、7 組的完整多字組合 topic 在 GitHub 上無對應 topic（如 `topic:mcp-server-discovery-local=0`）。

```text
總共 65 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 3 組沒有新的（要 3 組）：可以停，報告寫「長尾未飽和」並附上面兩種連續數
第 1 組「agent tool discovery」：15 個名字，新的 15 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ibm/mcp-context-forge, agentic-community/mcp-gateway-registry, xfey/mcp-zero, neuronto/agentic-resource-discovery, usefulsoftwareco/executor, mcpjungle/mcpjungle, btsouth/toolport, tuckerschreiber/need, EnactProtocol/encat-spec-and-tools, openai-tool-search, anthropic-tool-search-tool, claude-code-tool-search, DunkelCloud/ToolMesh, TheLunarCompany/lunar, obot-platform/obot
  ★1000 以上的新名字：ibm/mcp-context-forge, agentic-community/mcp-gateway-registry, usefulsoftwareco/executor, mcpjungle/mcpjungle, obot-platform/obot
第 2 組「mcp server discovery local」：13 個名字，新的 12 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：cli-use, activeing123/mcptoon, lirantal/ls-mcp, cubicecho/mcp-discovery, kuldeep-poonia/mcpscan, PrefectHQ/fastmcp, mcp-shark/lazy-tool, abdullah1854/MCPGateway, voicetreelab/lazy-mcp, keybrdist/opencode-lazy-loader, knowsuchagency/mcp2cli, philschmid/mcp-cli
  ★1000 以上的新名字：PrefectHQ/fastmcp, knowsuchagency/mcp2cli, philschmid/mcp-cli
第 3 組「command line tools inventory」：5 個名字，新的 5 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：cli-ai-org/cli, Yaemikoreal/CliLoci, clihub-ai/clihub, syshin0116/clidex, thellimist/clihub
第 4 組「agent 工具 自動 探索 本機 指令」：4 個名字，新的 2 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：linxule/opencli, claude-code-sessionstart-hook
第 5 組「dynamic tool loading」：12 個名字，新的 12 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt
  新：ChandraMohanBusam/mcp-dynamic-tool-loader, asadani/tool-attention, asyrjasalo/dynamic-mcp, mizchi/mcp-reloader, spring-ai-community/spring-ai-tool-search-tool, yulimfish/opencode-tool-search, openrouter-tool-search, kimi-dynamic-tool-loading, morphllm-dynamic-tool-loading, Scalekit, Klavis-AI/klavis, AgentKey
  ★1000 以上的新名字：Klavis-AI/klavis
第 6 組「sessionstart hook environment tools」：4 個名字，新的 1 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related
  新：Alpha-Oi/cc-skill-router
第 7 組「progressive disclosure cli mcp」：9 個名字，新的 9 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：everclear077/dsh-progressive-tools, labmimors/dsh-mcp-lens, runkids/agents-context-router, brunogama/mcp-cli-wrappers, codyaverett/mcp-cli, brunogama/claude-mcp-wrapper, Consiliency/pmcp, nvidia-nemoclaw-progressive-tool-disclosure, anthropic-agent-skills
第 8 組「capability discovery agent cli」：9 個名字，新的 9 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：cordsjon/a2a-cli-registry, 444136347/dsh-capability-discovery, adaptive-interfaces/adaptive-tool-discovery, Rosh1106/WhatTheAgent, expo/agent-cli-detector, SenteLabsAI/extensible-mcp, Magic-Man-us/claude-code-capabilities, gushuaialan1/od-cli-scanner, alpibrusl/acli
```

---

## 三、問題 1：業界與開源的稱呼與解法架構

業界針對「agent 不知道環境裡有哪些工具」或「工具過多導致 context 膨脹（Tools Tax / Context Bloat）與誤判」，已收斂出以下幾種標準術語與工程解法：

1. **Tool Search / Deferred Tool Loading（工具搜尋／延遲載入）**
   - 不在對話開始時把幾十到幾百個工具的完整 JSON Schema 塞進 prompt，而是透過 `defer_loading: true`（OpenAI / Anthropic）只給名稱或索引，讓模型依任務主動呼叫 `tool_search` 按需載入 Schema。
2. **Progressive Disclosure（漸進式揭露）**
   - 分三層載入：第一層只給工具名稱與一行描述（例如 `SKILL.md` 的 frontmatter、CLI 清單、或 `mcp2cli --list`）；第二層在需要時讀 `SKILL.md` 全文或執行 `<cli> --help`；第三層才執行腳本或讀取附屬檔案。
3. **MCP-to-CLI（將 MCP 轉成 CLI，讓 agent 透過 `--help` 探索）**
   - 利用 LLM 在預訓練中對 terminal 與 `--help` 高度熟悉的特性，以一個通用 CLI 包裝器（如 `mcp2cli`、`mcp-cli`、`cli-use`）取代常駐載入的大量 MCP JSON Schema，agent 靠 shell 執行 `--list` / `--help` 按需取用。
4. **Local MCP Gateway / Meta-Tool Proxy（本機 MCP 閘道／元工具代理）**
   - 在 agent client 與多個下游 MCP server 之間放一層本機閘道（如 `toolport`、`mcptoon`、`lazy-mcp`、`mcpjungle`），對 client 只暴露 2 到 3 個 meta-tools（`search_tools`、`describe_tool`、`call_tool`），或利用 MCP `notifications/tools/list_changed` 動態更新清單。
5. **Environment Inventory / Capability Discovery / SessionStart Hook（環境清點與啟動注入）**
   - 利用生命週期 Hook（如 Claude Code 的 `SessionStart`）或專屬清點工具（如 `cli-ai-org/cli`、`ls-mcp`、`a2a-cli-registry`、`claude-code-capabilities`），在 session 啟動時確定性地掃描本機 `PATH`、套件管理器、MCP 設定檔、已安裝 skill，並將精簡摘要注入 stdout context。
6. **規則檔慣例（`AGENTS.md` / `CLAUDE.md` / `GEMINI.md`）**
   - 作為人類與專案的靜態入口：列出「專案／這台機器上有哪幾個自訂 CLI（如 `xxx thread start`）與何時該用」，但官方與社群共識是**規則檔要極短**，只放指令入口與一句觸發條件，詳細參數交給 agent 執行 `<cli> --help` 或讀取對應 `SKILL.md`（否則長對話後容易被忽略或浪費 token）。
7. **自訂工具探索指令（如 Gemini CLI 的 `tools.discoveryCommand`）**
   - 由 CLI harness 在啟動時執行設定好的 `discoveryCommand`（輸出 JSON 工具定義清單），再透過 `callCommand` 轉呼叫本機腳本或程式，不需要實作完整 MCP server 協定即可把本機工具註冊進 agent 的工具表。

---

## 四、問題 2：工具、腳本、MCP Server、Skill 與官方功能清點

以下所有 GitHub repo 星數、授權、封存與最後 push 日期皆於 **2026-11-18** 以 `sweep.py verify`（透過 `gh api`）實測驗證。效果數據區分為「官方／一手實測」與「作者自述／待驗證」。

### A. 官方原生功能與協定標準
| 名稱 | 運作方式 | 效果與證據 |
|---|---|---|
| OpenAI Tool Search (`gpt-5.4`+ Responses API) | 在 `tools` 陣列加入 `tool_search`，對 function/namespace/MCP 設定 `defer_loading: true`，模型依需求動態載入並保留 prompt cache。 | 官方文件說明可降低整體 token 用量並維持 cache，無公開統一百分比基準（`developers.openai.com` 一手文件）。 |
| Anthropic Tool Search Tool / Claude Code Tool Search | 當工具定義過多（Claude Code 在超過門檻時自動啟用）先隱藏完整 schema，改由 agent 搜尋工具目錄後按需載入。 | 官方文件指出一次載入超過 30–50 個工具會使工具選擇準確率下降，50 個工具可佔 10–20K tokens（`code.claude.com` 一手文件）。 |
| Claude Code `SessionStart` Hook | 在 `.claude/settings.json` 設定 `type: "command"` hook，於啟動／`/clear`／`--resume` 時執行本機清點腳本，將 stdout 直接注入初始 context。 | 官方文件確認為確定性執行（deterministic），先於模型推論注入；不吃 MCP tool context 問題，故必須用 `command` 型態（`code.claude.com` 一手文件）。 |
| Anthropic / OpenAI Agent Skills (`SKILL.md`) | 啟動時只載入各 skill 的 name 與 description（Codex 限制預設 <= 2% context 或 8,000 字元），匹配時才讀全文與跑附屬腳本。 | 一手官方規範支援（`agentskills.io`、`developers.openai.com`、`code.claude.com`）。 |
| Gemini CLI `tools.discoveryCommand` & `/tools` | 在 `settings.json` 設定 `tools.discoveryCommand` 與 `tools.callCommand`，啟動時執行探索指令動態註冊本機自訂工具；使用者可用 `/tools` 檢視已載入清單。 | `google-gemini/gemini-cli` 原始碼與官方文件實證（`packages/core/src/tools/tool-registry.ts`）。 |

### B. MCP 轉 CLI 與 `--help` 漸進式探索（高星主流）
| Repo / 名稱 | 實測星數與授權（2026-11-18 gh api） | 運作方式 | 效果證據 |
|---|---|---|---|
| `knowsuchagency/mcp2cli` | ★2,440、MIT、未封存、最後 push 2026-11-09 | 在執行期零 codegen 將任何 MCP、OpenAPI、GraphQL 轉成 CLI，提供 `--list` 扁平清單與本地呼叫頻率排序，並附帶可安裝 skill 教 agent 探索使用。 | README 作者自述可省 96%–99% 工具 schema token（第三方獨立復現待驗證）。 |
| `philschmid/mcp-cli` | ★1,285、MIT、未封存、最後 push 2026-02-05 | Bun 編譯的獨立 CLI，支援 stdio 與 HTTP/SSE MCP，讓 coding agent 用 `mcp-cli grep` 動態搜尋並按需呼叫工具。 | 專案與作者部落格說明可大幅減少啟動 token 消耗（具體量化數據待驗證）。 |
| `thellimist/clihub` | ★669、MIT、未封存、最後 push 2026-03-12 | 把任意 MCP server 轉為 CLI 指令，讓 agent 透過標準 shell 與 `--help` 探索呼叫。 | 功能實作於 repo；省 token 具體基準待驗證。 |
| `cli-use` | HN 發布（無單一高星 GitHub repo） | 零依賴 Python CLI，加入 MCP server 後會自動產出 `SKILL.md` 與 `AGENTS.md` 指標，讓 repo 內的 coding agent 自動發現可用指令。 | Show HN 作者說明（效果與長期穩定性待驗證）。 |
| `linxule/opencli` | ★3、Apache-2.0、**已封存**、最後 push 2026-04-04 | 將網站、Electron app 或本機 binary 轉為統一 CLI 並整合 `AGENT.md` 供 agent 發現學習。 | 已封存，僅作設計參考。 |

### C. 本機 MCP 清點、CLI 環境掃描與 Agent CLI 偵測
| Repo / 名稱 | 實測星數與授權（2026-11-18 gh api） | 運作方式 | 效果證據 |
|---|---|---|---|
| `PrefectHQ/fastmcp` | ★28,640、Apache-2.0、未封存、最後 push 2026-11-18 | 內建 `fastmcp list` / discovery CLI 指令，可直接掃描本機已設定在 Claude Code、Cursor、Goose 等編輯器的 MCP server 與工具簽名。 | 官方文件與套件實測支援，穩定度高（偏向開發者與腳本查詢工具）。 |
| `lirantal/ls-mcp` | ★84、Apache-2.0、未封存、最後 push 2026-11-16 | 掃描並列出系統中 Cursor、Claude Desktop、VS Code 等 AI 應用已設定的 MCP server 清單。 | Repo 實作，偏向環境清點／資安盤點（作為 agent 自動探索效果待驗證）。 |
| `expo/agent-cli-detector` | ★5、MIT、未封存、最後 push 2026-10-24 | 偵測本機環境安裝了哪些 AI coding agent CLI 工具。 | 早期套件，支援 agent 清單有限（待驗證）。 |
| `cordsjon/a2a-cli-registry` | ★2、Apache-2.0、未封存、最後 push 2026-11-06 | 探索本機 CLI 工具群（local CLI fleet）並進行健康檢查，透過 MCP 與 A2A 介面暴露給 agent。 | 早期專案（★2），概念高度切題但實效待驗證。 |
| `cli-ai-org/cli` | ★1、MIT、未封存、最後 push 2026-01-14 | 掃描本機 `PATH` 與套件管理器（npm、pip、cargo 等），輸出結構化 JSON 目錄給 agent 查詢已裝工具。 | 早期專案（★1），Windows 跨 shell 支援度待驗證。 |
| `Magic-Man-us/claude-code-capabilities` | ★1、MIT、未封存、最後 push 2026-10-02 | 盤點 Claude Code 的 skills、agents、plugins、MCP servers、hooks 並輸出環境報告。 | 早期專案（★1），僅針對 Claude Code（效果待驗證）。 |
| `syshin0116/clidex` / `clihub-ai/clihub` | `clidex`: ★3 MIT（push 2026-11-15）；`clihub`: ★5 MIT（push 2026-03-19） | 提供 JSON/YAML 格式的 CLI 工具索引與 MCP server，讓 agent 依任務需求搜尋 CLI 用法與安裝指令。 | 偏向外部 CLI 索引查詢，非自動掃描本機私有腳本（效果待驗證）。 |
| `Alpha-Oi/cc-skill-router` | ★0、MIT、未封存、最後 push 2026-09-09 | Claude Code 全域 skill + `SessionStart` hook，依專案環境與任務推薦已安裝的 skill。 | 早期實驗專案（效果待驗證）。 |

### D. MCP Gateway / Proxy / 主動工具探索
| Repo / 名稱 | 實測星數與授權（2026-11-18 gh api） | 運作方式 | 效果證據 |
|---|---|---|---|
| `Klavis-AI/klavis` (Strata) | ★5,826、Apache-2.0、**已封存**、最後 push 2026-11-05 | 舊版 Klavis MCP 整合庫（Product Hunt 上的 Strata 採階層式意圖 -> 整合 -> 動作工具探索）。 | Repo 已封存（標註 DEPRECATED），其 Strata 雲端服務效能待驗證。 |
| `IBM/mcp-context-forge` | ★4,847、Apache-2.0、未封存、最後 push 2026-11-17 | 企業級 AI Gateway / Registry / Proxy，統一納管 MCP、A2A、REST/gRPC 並提供集中式工具探索。 | 企業架構完整，適合作為集中閘道（單機輕量場景較重）。 |
| `UsefulSoftwareCo/executor` | ★4,511、MIT、未封存、最後 push 2026-11-18 | 讓 agent 透過單一安全執行層搜尋並呼叫 OpenAPI / MCP / GraphQL / JS 函式。 | 高星活躍專案，具體 token 節省基準待驗證。 |
| `mcpjungle/MCPJungle` | ★1,628、MPL-2.0、未封存、最後 push 2026-11-03 | 自架 MCP gateway，統一管理、註冊並提供多個 MCP server 的探索入口。 | 高星活躍專案，聚焦多 server 管理。 |
| `obot-platform/obot` | ★1,198、MIT、未封存、最後 push 2026-11-17 | 完整 AI 治理與 MCP gateway 平台，含工具目錄與權限控管。 | 偏向企業治理平台。 |
| `agentic-community/mcp-gateway-registry` | ★1,052、Apache-2.0、未封存、最後 push 2026-11-17 | 提供動態工具探索與 OAuth 權限治理的 MCP Gateway & Registry。 | 偏向企業與團隊共用。 |
| `xfey/MCP-Zero` | ★519、MIT、未封存、最後 push 2025-07-02 | 主動工具探索（Active Tool Discovery）研究框架：模型主動提出需求描述，經兩階段語意路由找出對應 server 與 tool。 | 附有 arXiv 論文與 `experiment_apibank.py`；論文稱在 APIBank 基準可降低大量 context token（第三方真實 coding agent 環境效果待驗證）。 |
| `TheLunarCompany/lunar` (MCPX) | ★510、MIT、未封存、最後 push 2026-11-17 | Agent 原生 MCP Gateway，代理與過濾多個 MCP server 工具。 | 商業公司維護開源核心，省 token 實測待驗證。 |
| `activeing123/mcptoon` | ★437、Apache-2.0、未封存、最後 push 2026-11-18 | 零依賴純 Python 單一設定 CLI（支援 Claude Code、Codex、Cursor），提供按需 schema 擷取與壓縮。 | README 附 `docs/real-world-benchmark.md` 與 `mcptoon bench` 自測：合成 255 工具 71,929 -> 581 tokens (-99.2%)；7 個公開 server 209 工具 640,606 -> 905 tokens (-99.86%)（作者自述實測，第三方復現待驗證）。 |
| `btsouth/toolport` | ★241、MIT、未封存、最後 push 2026-11-17 | Local-first MCP gateway（Rust/Tauri），OS keychain 存金鑰，對 client 提供按需 tool search。 | README 附 `BENCHMARK.md` 連結，自述可減少數倍輸入 token（待驗證）。 |
| `voicetreelab/lazy-mcp` | ★115、MIT、未封存、最後 push 2026-01-09 | MCP 延遲載入 proxy，將工具組織成樹狀結構供 agent 按需展開啟用。 | 社群實作，具體基準待驗證。 |
| `mcp-shark/lazy-tool` | ★40、MIT、未封存、最後 push 2026-05-10 | 單一 Go 執行檔本機 MCP 探索 proxy，讀取 Claude Desktop/Cursor/VS Code 設定建立 SQLite 索引，支援 direct/search/hybrid 模式。 | 小型開源專案，實效待驗證。 |
| `tuckerschreiber/need` | ★11、MIT、未封存、最後 push 2026-03-18 | 以 MCP server 形式提供語意 CLI 工具探索（避免 agent 幻覺不存在的 CLI 套件）。 | 極早期專案（★11），偏向外部 CLI 目錄搜尋。 |

---

## 五、問題 3：Anthropic、OpenAI、Google 官方文件建議

以下僅引用本次調研直接讀取之官方文件原文短句（每句 <= 15 英文字）與直連 URL：

### 1. Anthropic（Claude Platform & Claude Code）
- **優先用現有 CLI + 指示 `--help`，比寫新整合簡單**：
  - URL：https://code.claude.com/docs/en/best-practices
  - 原文短句：`"If that system has a CLI, that's usually the easiest way in."`
  - 原文短句：`"For a CLI it hasn't seen before, pointing it at --help is enough."`
- **用 `CLAUDE.md` 與 Skills 分層控制 Context**：
  - URL：https://code.claude.com/docs/en/best-practices
  - 建議把專案專屬指令精簡放進 `CLAUDE.md`，長流程或專門工具手冊改放 Skill（只在需要時才載入全文）。
- **工具數量大時用 Tool Search 避免準確率下降**：
  - URL：https://code.claude.com/docs/en/agent-sdk/tool-search
  - 原文短句：`"Tool selection accuracy degrades with more than 30-50 tools loaded at once."`
  - URL：https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool
- **用 `SessionStart` Hook（`command` 類型）確定性注入開局環境狀態**：
  - URL：https://code.claude.com/docs/en/hooks
  - 原文短句：`"Claude Code adds plain-text stdout as context that Claude can see and act on."`
  - 註記：官方明確提醒開局時的 `SessionStart` 尚未就緒 MCP client context，因此需要開局注入環境工具資訊時必須使用 `type: "command"` 的 shell 指令，不可用 `mcp_tool` hook。

### 2. OpenAI（Responses API & Codex）
- **用 `AGENTS.md` 分層提供專案指令與工具入口**：
  - URL：https://developers.openai.com/codex/guides/agents-md
  - 原文短句：`"Codex reads AGENTS.md files before doing any work."`
  - 機制：從 `~/.codex/AGENTS.md` 到專案根目錄再往下合併（預設上限 `project_doc_max_bytes` 為 32 KiB）。
- **用 Skills（`SKILL.md`）實作漸進式揭露**：
  - URL：https://developers.openai.com/codex/skills
  - 原文短句：`"Skills use progressive disclosure to manage context efficiently."`
- **API 層使用 Tool Search + Namespace / MCP 延遲載入**：
  - URL：https://developers.openai.com/api/docs/guides/tools-tool-search
  - 原文短句：`"Tool search allows the model to dynamically search for and load tools"`
  - 原文短句：`"For optimal cost and latency, tool search is designed to preserve the model’s cache."`

### 3. Google（Gemini CLI & Gemini API）
- **支援 `GEMINI.md` 分層 + JIT 上下文發現**：
  - URL：https://geminicli.com/docs/cli/gemini-md/ （原始檔：`google-gemini/gemini-cli` `docs/cli/gemini-md.md`）
  - 除全域 `~/.gemini/GEMINI.md` 與工作區層級外，當工具存取子目錄時會自動向上掃描載入鄰近 `GEMINI.md`（Just-In-Time context）。
- **官方內建 `tools.discoveryCommand` 讓本機腳本／CLI 自動註冊為工具**：
  - URL：https://geminicli.com/docs/reference/tools/ （原始檔：`google-gemini/gemini-cli` `docs/reference/tools.md`）
  - 原文短句：`"You can extend Gemini CLI with custom tools by configuring tools.discoveryCommand in your settings"`
  - 原文短句：`"Use the /tools command to see what tools are currently active in your session."`
- **Windows 上預設透過無 Profile 的 PowerShell 執行指令**：
  - URL：https://geminicli.com/docs/tools/shell/ （原始檔：`google-gemini/gemini-cli` `docs/tools/shell.md`）
  - 原文短句：`"On Windows, commands execute with powershell.exe -NoProfile -Command."`

---

## 六、問題 4：跨 Shell（PowerShell、cmd、Git Bash、WSL）找指令的做法與坑

Windows 上同時跑多個 coding agent 時，「某個 CLI 在 PowerShell 有，但 agent 說沒裝」幾乎都源自以下五個機制落差：

### 1. 設定檔完全隔離（`$PROFILE` vs `.bashrc` vs System PATH）
- **坑**：若某個 CLI（例如自訂工具或工具管理器的 shim）是透過 PowerShell `$PROFILE`（`Microsoft.PowerShell_profile.ps1`）動態加進 `$env:PATH`，則 **Git Bash**（讀 `~/.bashrc` / `~/.bash_profile`）、**cmd**、甚至 **Gemini CLI 呼叫的 `powershell.exe -NoProfile`** 都**看不到**該 PATH！
- **解法**：需要跨所有 agent 與 shell 都能找到的指令，必須寫進 Windows User/Machine 環境變數（Registry PATH）或透過全域共用目錄；若無法寫入系統 PATH，必須在清點腳本或規則檔寫明絕對路徑。

### 2. 各 Shell 找指令的內建命令與搜尋範圍不同
| 環境 | 查指令命令 | 搜尋順序與範圍 | 常見誤判坑 |
|---|---|---|---|
| PowerShell | `Get-Command <name>`（簡寫 `gcm`） | 先找 PowerShell Cmdlet / Function / Alias，再掃 `$env:PATH` 的 `.ps1`、`.exe`、`.cmd`、`.bat`。 | 會抓到 PowerShell 專屬 function 或 `.ps1`，但這些在 Git Bash / cmd 不能直接跑。 |
| cmd.exe | `where <name>` | 掃 `%PATH%` 與 `%PATHEXT%`（`.exe`、`.cmd`、`.bat`），不看 alias。 | 在 Git Bash 下直接打 `where` 可能沒反應或撞名；回傳多行時若沒加引號處理空白路徑（如 `C:\Program Files\...`）會出錯。 |
| Git Bash (MSYS2) | `command -v <name>` / `which <name>` | 掃 MSYS2 轉譯後的 POSIX `$PATH`（如 `/c/Program Files/...`），找 shell function、builtin 與可執行檔。 | **不認得 Windows `.ps1` 腳本**；對某些沒有 shebang 或僅靠 Windows `PATHEXT` 關聯的 `.cmd`/`.bat` 檔，有時需明確加上 `.cmd`（如 `foo.cmd`）才找得到／跑得動；且若啟動該 Git Bash 的父行程 PATH 本身就缺項目（例如某些 IDE/agent 鎖定的精簡環境變數），`command -v` 就會直接失敗。 |
| WSL | `command -v <name>` / `which <name>` | 掃 Linux `$PATH`；啟用 WSL Interop 時會把 Windows PATH 附加進來（受 `/etc/wsl.conf` `[interop] appendWindowsPath` 控制）。 | Windows 的執行檔在 WSL 裡**必須帶 `.exe` 副檔名**（例如 `uv.exe`、`gh.exe`）才會觸發 Windows binary；只查 `command -v uv` 會回傳找不到，除非 Linux 端也另裝一份（造成雙重安裝陰影／版本不一致）。 |

### 3. Agent Harness 本身的「環境變數快照／`-NoProfile`」坑
- 不同 agent 呼叫 shell 的方式不同：例如 Gemini CLI 在 Windows 官方明確記載使用 `powershell.exe -NoProfile -Command`（不載入 `$PROFILE`）；Claude Code 在 Windows 通常走 Git Bash（MSYS2）；某些 GUI/IDE 外掛則是繼承啟動該 IDE 當下的環境變數快照（安裝新 CLI 後沒重啟 IDE 就找不到）。
- **影響**：同一個使用者電腦上，手開 PowerShell 視窗測得到指令，不代表 coding agent 的 subshell 看得到。

### 4. 實務避坑做法
1. **統一註冊或顯式清點**：把真正要給所有 agent 共用的 CLI 放進 Windows 使用者環境變數 `PATH`（不用只寫在 `$PROFILE`），並確保關鍵路徑無依賴單一 shell 才能啟動的 wrapper。
2. **規則檔／`SessionStart` 腳本提供「環境真相」**：對於位於非標準目錄、或只在特定 shell（如 PowerShell vs Git Bash）可見的工具，在 session 啟動 hook 或規則檔中直接列出「工具名 -> 建議呼叫的 shell 與絕對路徑／檢查方式」，並明訂**禁止僅因單一 shell 的 `command -v` 失敗就宣告未安裝**（需先檢查常見安裝路徑或改用 `powershell.exe -Command "Get-Command ..."` 複查）。
3. **WSL 與 Windows 混用時帶副檔名**：在 WSL 呼叫 Windows 工具一律明確呼叫 `<tool>.exe`，並注意路徑需經 `wslpath` 轉換。
