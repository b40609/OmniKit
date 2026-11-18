# T2 飽和式調研報告

- **題目（窄題）**：搜尋、檢視 coding agent（Claude Code、Codex、Cursor、Gemini CLI 等）的對話紀錄，或把一段工作交接、遷移到新對話或另一個 agent 的工具
- **開始時間**：2026-11-18 11:08 +08:00
- **結束時間**：2026-11-18 11:37 +08:00
- **納入標準（從嚴）**：
  - **算相關**：主要功能即為「搜尋／檢視／匯出 coding agent 對話紀錄（transcript / session history）」或「把一段工作交接／遷移到新對話或另一個 agent（session handoff / cross-agent session migration / converter）」的工具（開源 repo、產品、skill、plugin、MCP、CLI）。
  - **不算**：長期記憶／知識庫／壓縮後救回脈絡工具、僅含一兩個相關 skill 的大型合集／工具箱、遙控／即時傳訊／多 agent 委派控制台、教學文／論文。
  - **拿不準**：不 `add` 進帳本，集中記錄於報告「拿不準」一節。

## 各組查詢紀錄與 `status` 輸出

### 第 1 組：`coding agent 對話紀錄 交接`
- **挑詞理由**：起手第 1 組，依題目核心概念的中文原話設計，覆蓋 coding agent 對話紀錄與工作交接。
- **納入工具**：
  - `npm`: `@adamchanadam/agent-handoff-kit`, `HildebrandYu/dsh-session-chains`
  - `exa`: `ccassist`
  - `web-zh`: `jhlee0409/claude-code-history-viewer`, `XZL-CODE/cc-codex-history-viewer`, `chrzamz/sessio`, `specstoryai/getspecstory`, `HizTam/codex-history-viewer`, `ay-bh/chat-history`, `pratikgajjar/recall`, `ccassist`
- **排除／拿不準**：
  - 排除：`ecologyxy/chatmem`, `douxy1994/ai-memory`, `XMemo`, `MemoryPlugin`, `Snipara`（長期記憶／知識庫為主）；`pingdotgg/t3code`（多 agent 遙控控制台為主）；`feiskyer/codex-settings`（設定與 skill 合集）。
  - 拿不準（未寫入帳本）：`vshulcz/deja-vu`、`@eagle4302/dsh-session-relay`、`@virtualorz/recap`。
- **`status --min-stars 1000` 輸出**：
```text
總共 10 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
整次調研還沒查過：英文網頁搜尋、Product Hunt（網頁搜尋 site:producthunt.com）、主要專案的 fork 與 README 提到的競品（related）
第 1 組「coding agent 對話紀錄 交接」：10 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：@adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, ccassist, jhlee0409/claude-code-history-viewer, XZL-CODE/cc-codex-history-viewer, chrzamz/sessio, specstoryai/getspecstory, HizTam/codex-history-viewer, ay-bh/chat-history, pratikgajjar/recall
  ★1000 以上的新名字：jhlee0409/claude-code-history-viewer, specstoryai/getspecstory
```

### 第 2 組：`coding agent conversation history`（`--topic session-viewer`）
- **挑詞理由**：起手第 2 組（英文同義說法），涵蓋 coding agent 與 conversation history；並依第 1 組 `jhlee0409/claude-code-history-viewer` 的 topic 補查 `session-viewer`。
- **納入工具**：
  - `github-topic`: `matt1398/claude-devtools`, `jerrywu001/cc-sessions-viewer`, `delexw/claude-code-trace`, `a7t-ai/poirot`, `PixelPaw-Labs/codex-trace`, `S40911120/recensa`, `tuo-lei/vibe-replay`, `VACInc/openclaw-tool-call-viewer`, `2ykwang/cview`, `zhuchongba-01/AgentSessionManager`, `wellwelwel/sessioner`, `thevibeworks/ccx`, `qiaolei81/copilot-session-viewer`, `HeavyBunny19C/OpenSession`, `Ryheff24/agentlog`, `karanb192/hindcast`, `wanderer-yk/agent-chatlens`, `yuluod/AllSessions`, `Vvkmnn/claude-historian-mcp`, `kuroko1t/claude-vault`, `jhammant/ClaudeHistoryMCP`, `WSL043/dsh-chat-manager`, `IvyYang1999/swob`, `vibheksoni/session-export`, `drewburchfield/claude-code-chat-explorer`, `coolcorexix/claude-grep`, `DazzleML/Claude-Session-Backup`
  - `github-keyword`: `Nwflower/dsh-chat-import`, `zhangxj9819/agent-conversation-graph`, `monk1337/clicodelog`, `builderpepc/agent-migrator`, `shivamstaq/ccview`, `Seanium/koto`, `dotneet/agent-session-view`, `nimishgj/agentswap`, `frknyldz/ai-session-bridge`, `HeiGeAi/agent-history-rescue`
  - `skills-sh` & `npm`: `adlternative/agent-historian`
  - `hn`: `skillsynchq/txcript`（Launch HN: Skillsync 核心引擎）, `Dicklesworthstone/coding_agent_session_search`
  - `exa`: `xingkaixin/codesesh`, `nihen/ah`
  - `web-en`: `jazzyalex/agent-sessions`, `Dicklesworthstone/coding_agent_session_search`, `dotneet/agent-session-view`, `jlreyes/agent-history-skills`, `AgentWorkforce/relayhistory`, `aytzey/showagent`, `bvolpato/omnisession`, `yigitkonur/cli-continues`, `sukamenev/baton`, `aploe/claude-handoff-skill`, `chrichuang218/agent-handoff`
  - `producthunt`: `matt1398/claude-devtools`, `claudebin`（`wunderlabs-dev/claudebin.com`）, `ccgather`
- **排除／拿不準**：
  - 排除：長期記憶／知識庫（`rustytensor/pi-noodle`, `CheshiAI/Cheshi`）；遠端操作／多 agent 編排或控制台（`twidi/twicc`, `Aploide/spettro`, `crystl.dev`, `legcli.com`, `Cursor Glass`, `ADE`, `Replicas`, `Codemind`, `MAO`, `mpai`, `ccshare`, `claude-share`, `Hallmonitor`, `Hako`, `AgentManager`, `Bloblings`, `beacon.sh`, `Greplica`）；帳號切換／安全工具／通用 ChatGPT 匯出（`koi128bit/WorkBuddy-Switch`, `marelucent/chatgpt-export-reader`, `7h30th3r0n3/MindJack`, `ag-donald/antigravity-database-manager`）；依紀錄生成 skill 或日誌／回顧（`raghavpillai/distill`, `Coding Wrapped`）。
  - 拿不準（未寫入帳本）：`bilalpeera86/claude-session-flow`、`kunwar-shah/claudex`、`cvelasquez/agent-workbench`、`VARVE-ai/adit-core`、`tjboudreaux/rosetta`、`centauri-ai/coslash`、`herdbell`、`asymptote beacon handoff`、`Conan`、`Bench for Claude Code`、`Termi Protocol`。
- **`status --min-stars 1000` 輸出**：
```text
總共 63 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
整次調研還沒查過：主要專案的 fork 與 README 提到的競品（related）
第 2 組「coding agent conversation history」：53 個名字，新的 53 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt
  新：matt1398/claude-devtools, jerrywu001/cc-sessions-viewer, delexw/claude-code-trace, a7t-ai/poirot, PixelPaw-Labs/codex-trace, S40911120/recensa, tuo-lei/vibe-replay, VACInc/openclaw-tool-call-viewer, 2ykwang/cview, zhuchongba-01/AgentSessionManager, wellwelwel/sessioner, thevibeworks/ccx, qiaolei81/copilot-session-viewer, HeavyBunny19C/OpenSession, Ryheff24/agentlog, karanb192/hindcast, wanderer-yk/agent-chatlens, yuluod/AllSessions, Vvkmnn/claude-historian-mcp, kuroko1t/claude-vault, jhammant/ClaudeHistoryMCP, WSL043/dsh-chat-manager, IvyYang1999/swob, vibheksoni/session-export, drewburchfield/claude-code-chat-explorer, coolcorexix/claude-grep, DazzleML/Claude-Session-Backup, Nwflower/dsh-chat-import, zhangxj9819/agent-conversation-graph, monk1337/clicodelog …
  ★1000 以上的新名字：matt1398/claude-devtools, Dicklesworthstone/coding_agent_session_search, yigitkonur/cli-continues
```

### 第 3 組：`session transcript viewer`（`--topic session-history`）
- **挑詞理由**：起手第 3 組（不含 `agent`、`AI`、`skill`、`MCP` 的一般說法），鎖定 session transcript / history viewer 類工具，並依第 2 組出現的 `session-history` topic 補查。
- **納入工具**：
  - `github-topic`: `jazzyalex/agent-sessions`, `jerrywu001/cc-sessions-viewer`, `a7t-ai/poirot`, `S40911120/recensa`, `karanb192/hindcast`, `wilbeibi/catchup`, `valpere/session-indexer`, `gautamgpt1/agent-session-browser`, `noluyorAbi/claude-code-recap`, `samfoy/pi-session-search`, `masonc15/codex-transcript-viewer`, `yfge/TalkReplay`, `hitmman55/claude-code-chat-viewer`, `tanghong123/claude-replay`, `phpmypython/claude-viewer`, `POSTTTT/agent-cli-session`, `alexxxtat/claude-transcript-viewer`
  - `github-keyword`: `S40911120/recensa`, `masonc15/codex-transcript-viewer`, `tad-hq/universal-session-viewer`, `tim-hua-01/cc_transcript_viewer`, `mirekholec/copilot-debugger`, `hitmman55/claude-code-chat-viewer`, `hopp1395/cc-outline`, `gpolaert/trace`, `codesweep-ai/tracer`, `alexxxtat/claude-transcript-viewer`, `forensicdave/claude-export-viewer`
  - `exa`: `sessionviewer.cc`, `ravikanchikare/cc-session-viewer`
  - `web-en`: `jhlee0409/claude-code-history-viewer`, `ccassist`, `mantra-hq/mantra-releases`, `ay-bh/chat-history`, `specstoryai/getspecstory`, `simonw/claude-code-transcripts`, `Kirushanthan03/claude-code-chat-history-viewer`
- **排除／拿不準**：
  - 排除：長期記憶／知識管理（`Sigillion-AI/sigillion`, `taxueseek/session-digger`, `MemoryPlugin`）；多 agent 編排或 IDE（`AgentsRoom`, `Latand/delegatus`, `Almclean/selenai`, `r1c7/CluxMate`）；Markdown 編輯器為主（`markdossier`）；僅計費／審計成本（`luoyuctl/agenttrace`, `nickelsec/bough`）；純 bash 歷史（`dkolmakov/hm`）。
  - 拿不準（未寫入帳本）：`tombelieber/claude-view`（即時監控儀表板兼搜尋）、`StayCurious-Xuan/wayfinder`、`p32929/ccheckpoints`、`vitaliyhayda/claude-transplant`（僅遷移帳號側邊欄紀錄）、`Mahiler1909/claudepath`（僅修正搬遷目錄路徑）。
- **`status --min-stars 1000` 輸出**：
```text
總共 87 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
整次調研還沒查過：主要專案的 fork 與 README 提到的競品（related）
第 1 組「coding agent 對話紀錄 交接」：10 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：@adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, ccassist, jhlee0409/claude-code-history-viewer, XZL-CODE/cc-codex-history-viewer, chrzamz/sessio, specstoryai/getspecstory, HizTam/codex-history-viewer, ay-bh/chat-history, pratikgajjar/recall
  ★1000 以上的新名字：jhlee0409/claude-code-history-viewer, specstoryai/getspecstory
第 2 組「coding agent conversation history」：53 個名字，新的 53 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt
  新：matt1398/claude-devtools, jerrywu001/cc-sessions-viewer, delexw/claude-code-trace, a7t-ai/poirot, PixelPaw-Labs/codex-trace, S40911120/recensa, tuo-lei/vibe-replay, VACInc/openclaw-tool-call-viewer, 2ykwang/cview, zhuchongba-01/AgentSessionManager, wellwelwel/sessioner, thevibeworks/ccx, qiaolei81/copilot-session-viewer, HeavyBunny19C/OpenSession, Ryheff24/agentlog, karanb192/hindcast, wanderer-yk/agent-chatlens, yuluod/AllSessions, Vvkmnn/claude-historian-mcp, kuroko1t/claude-vault, jhammant/ClaudeHistoryMCP, WSL043/dsh-chat-manager, IvyYang1999/swob, vibheksoni/session-export, drewburchfield/claude-code-chat-explorer, coolcorexix/claude-grep, DazzleML/Claude-Session-Backup, Nwflower/dsh-chat-import, zhangxj9819/agent-conversation-graph, monk1337/clicodelog …
  ★1000 以上的新名字：matt1398/claude-devtools, Dicklesworthstone/coding_agent_session_search, yigitkonur/cli-continues
第 3 組「session transcript viewer」：33 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：wilbeibi/catchup, valpere/session-indexer, gautamgpt1/agent-session-browser, noluyorAbi/claude-code-recap, samfoy/pi-session-search, masonc15/codex-transcript-viewer, yfge/TalkReplay, hitmman55/claude-code-chat-viewer, tanghong123/claude-replay, phpmypython/claude-viewer, POSTTTT/agent-cli-session, alexxxtat/claude-transcript-viewer, tad-hq/universal-session-viewer, tim-hua-01/cc_transcript_viewer, mirekholec/copilot-debugger, hopp1395/cc-outline, gpolaert/trace, codesweep-ai/tracer, forensicdave/claude-export-viewer, sessionviewer.cc, ravikanchikare/cc-session-viewer, mantra-hq/mantra-releases, simonw/claude-code-transcripts, Kirushanthan03/claude-code-chat-history-viewer
  ★1000 以上的新名字：simonw/claude-code-transcripts
```

### 第 4 組：`session handoff cross-agent`（`--topic session-handoff` + `related`）
- **挑詞理由**：從第 2–3 組結果出現的新詞 `session handoff`、`cross-agent` 切入，補足跨 agent 工作交接／會話遷移工具；並對 `matt1398/claude-devtools`、`Dicklesworthstone/coding_agent_session_search`、`yigitkonur/cli-continues` 執行 `related`。
- **納入工具**：
  - `github-topic`: `wilbeibi/catchup`, `REMvisual/claude-handoff`, `aytzey/showagent`, `Vinyl-Davyl/hermes`, `remembra-ai/remembra`, `Adamchanadam/agent-handoff-kit`, `HaiYangBG1/BuildBeat`, `cote-star/agent-chorus`, `wilbeibi/herdr-catchup`, `Capetlevrai/resume-claude-codex-grok`, `aa2246740/dsh-resume`, `alexei-led/resume-from`
  - `github-keyword`: `wilbeibi/herdr-catchup`, `HarryHeYu/sessionFlow`, `harrychih/hishare`, `awithi-co/acdc`, `TStansel/handoff`
  - `npm`: `AgentWorkforce/relayhistory`, `dennyferra/paseo-baton`, `kittimzhe/dsh-session-recall`, `azzgo/pi-xfer`
  - `exa`: `wilbeibi/catchup`, `awithi-co/acdc`, `TStansel/handoff`
  - `web-en`: `skillsynchq/txcript`, `xhluca/session-migrate`, `yigitkonur/cli-continues`, `Ryu0118/ctxmv`, `0smboy/agent-migration-cursor-plugin`, `wilbeibi/catchup`, `wilbeibi/herdr-catchup`, `yuzushi-dev/session-handoff`
  - `related`: `Yanvi-Robotics/mnemo`（由 `cli-continues` README 連結查得，經確認為跨工具本機工作階段全文檢索與索引工具；另 `sweep.py related --ledger` 自動寫入的 forks 與 `hesreallyhim/awesome-claude-code`、`dicklesworthstone/frankentui` 等非同類工具於最終名單排除）
- **排除／拿不準**：
  - 排除：長期記憶／合集／多路複用器（`staticroostermedia-arch/engram`, `AxmeAI/axme-code`, `alphaelements/handoff-mcp`, `alirezarezvani/claude-skills`, `LeeJuOh/claude-code-zero`, `PonyMux`, `ccmux`, `Lians-ai/Lians`, `obrenoalvim/zero-drift`, `vunm-io/passdown`, `cantona/herdr-revive`, `treesoop/claude2codex`（僅遷移設定/skill，非對話）, `agent-skill-sync`, `AksharP5/skillsync`）。
  - 拿不準（未寫入帳本）：`Frankie-Xu/threadport`、`qingsongcui/ContextCore`、`yuangyong/handoff-memory`、`WeirdSky924/agent-handoff-skill`、`mem0ai/openmemory`。
- **`status --min-stars 1000` 輸出**：
```text
總共 133 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：10 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：@adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, ccassist, jhlee0409/claude-code-history-viewer, XZL-CODE/cc-codex-history-viewer, chrzamz/sessio, specstoryai/getspecstory, HizTam/codex-history-viewer, ay-bh/chat-history, pratikgajjar/recall
  ★1000 以上的新名字：jhlee0409/claude-code-history-viewer, specstoryai/getspecstory
第 2 組「coding agent conversation history」：53 個名字，新的 53 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt
  新：matt1398/claude-devtools, jerrywu001/cc-sessions-viewer, delexw/claude-code-trace, a7t-ai/poirot, PixelPaw-Labs/codex-trace, S40911120/recensa, tuo-lei/vibe-replay, VACInc/openclaw-tool-call-viewer, 2ykwang/cview, zhuchongba-01/AgentSessionManager, wellwelwel/sessioner, thevibeworks/ccx, qiaolei81/copilot-session-viewer, HeavyBunny19C/OpenSession, Ryheff24/agentlog, karanb192/hindcast, wanderer-yk/agent-chatlens, yuluod/AllSessions, Vvkmnn/claude-historian-mcp, kuroko1t/claude-vault, jhammant/ClaudeHistoryMCP, WSL043/dsh-chat-manager, IvyYang1999/swob, vibheksoni/session-export, drewburchfield/claude-code-chat-explorer, coolcorexix/claude-grep, DazzleML/Claude-Session-Backup, Nwflower/dsh-chat-import, zhangxj9819/agent-conversation-graph, monk1337/clicodelog …
  ★1000 以上的新名字：matt1398/claude-devtools, Dicklesworthstone/coding_agent_session_search, yigitkonur/cli-continues
第 3 組「session transcript viewer」：33 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：wilbeibi/catchup, valpere/session-indexer, gautamgpt1/agent-session-browser, noluyorAbi/claude-code-recap, samfoy/pi-session-search, masonc15/codex-transcript-viewer, yfge/TalkReplay, hitmman55/claude-code-chat-viewer, tanghong123/claude-replay, phpmypython/claude-viewer, POSTTTT/agent-cli-session, alexxxtat/claude-transcript-viewer, tad-hq/universal-session-viewer, tim-hua-01/cc_transcript_viewer, mirekholec/copilot-debugger, hopp1395/cc-outline, gpolaert/trace, codesweep-ai/tracer, forensicdave/claude-export-viewer, sessionviewer.cc, ravikanchikare/cc-session-viewer, mantra-hq/mantra-releases, simonw/claude-code-transcripts, Kirushanthan03/claude-code-chat-history-viewer
  ★1000 以上的新名字：simonw/claude-code-transcripts
第 4 組「session handoff cross-agent」：51 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, related, web-en
  新：REMvisual/claude-handoff, Vinyl-Davyl/hermes, remembra-ai/remembra, Adamchanadam/agent-handoff-kit, HaiYangBG1/BuildBeat, cote-star/agent-chorus, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, aa2246740/dsh-resume, alexei-led/resume-from, HarryHeYu/sessionFlow, harrychih/hishare, awithi-co/acdc, TStansel/handoff, dennyferra/paseo-baton, kittimzhe/dsh-session-recall, azzgo/pi-xfer, axisrow/claude-devtools, alexeyv/claude-devtools, jawhnycooke/claude-devtools, powerappsdarren/claude-devtools, vince81/claude-devtools, adriencaccia/claude-devtools, huongctu/claude-devtools, cpiprint/claude-devtools, agarwalpragy/claude-devtools, dev-null-undefined/claude-devtools, hesreallyhim/awesome-claude-code, mrowrpurr-forks/coding_agent_session_search, mic92/coding_agent_session_search …
  ★1000 以上的新名字：hesreallyhim/awesome-claude-code
```

### 第 5 組：`session export migrate`（`--topic chat-history`）
- **挑詞理由**：從第 2–4 組結果出現的新詞 `session-export`、`migrate` 切入，補足對話匯出、封存與遷移工具，並補查第 1–2 組出現的 `chat-history` topic。
- **納入工具**：
  - `github-topic`: `jhlee0409/claude-code-history-viewer`, `specstoryai/getspecstory`, `S40911120/recensa`, `vibheksoni/session-export`, `hanityx/threadlens`, `linfanxxxx/codex-session-exporter`, `Ann-Diana/codex-project-chat-exporter`, `MeXenon/kiro-session-export`, `GaoSSR/codex-export-skill`, `chaybits/ectype`, `fabiocampolim-design/claude-session-publisher`, `bwndlct/dsh-session-export`, `ZelinZhou-THU/opencode-export`, `zyx3721/session-exporter-skills`, `deveduar/vscode-copilot-export-cli`, `zhaoxuejie/dsh-plugin-session-export`, `davidqyc/session-preserve`, `zhyunran/dsh-session-bundle`
  - `skills-sh`: `Camji55/agent-handoff`
  - `hn`: `S2thend/cursor-history`
  - `exa`: `Sertelegger/claude-sesh-mover`, `yanzhi0922/codex-session-migrator`, `avikalpa/codex-session-tui`, `omdsh-dev/dsh-shuttle`
  - `web-en`: `es617/claude-replay`, `yfge/TalkReplay`, `vibheksoni/session-export`, `pma1999/session-bridge`, `ahmojo/codex-claude-transfer`, `grapeot/ai_session_export`, `ay-bh/chat-history`, `POSTTTT/agent-cli-session`, `didvc/web-to-cc`, `escoffier-labs/stationtrail`, `akoserwal/export-conversation-skill`
- **排除／拿不準**：
  - 排除：微信／Telegram／抖音／一般網頁聊天匯出（`weclone`, `chatlab`, `echotrace`, `wechatbridge`, `moect`, `telegram-bot-dumper`, `welink`, `telegram-archive`, `weflow-cli`, `tg-search`, `wechat-chat-export`, `douyindatareview`, `robbings/chatgpt-graph-navigator`, `firenzelor/gemini-collector`）；長期記憶／代理健康監控（`ukkit/memcord`, `wu079/dsh-memory-keeper`, `AinGerI/claude-pulse`）；可觀測性平台或程式碼審查／委派外掛（`openai/codex-plugin-cc`（以委派 Codex 審查為主，僅附帶 `/codex:transfer`）、`LangSmith Traces`、`Operon`）。
  - 拿不準（未寫入帳本）：`SakuraByteCore/codexmate`（含多工具對話搜尋匯出，亦含 provider 切換／技能／任務管理）、`vega-llc/cowork-migrate`、`Agensi`（技能市集內含 Session Replay / Session Finder）、`tretuttle/ai-stuff`、`xduwt/claude-desktop-history`、`sterramind/opencode-session-transfer`、`erickrus/opencode_migrate`。
- **`status --min-stars 1000` 輸出**：
```text
總共 160 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 1 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：10 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：@adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, ccassist, jhlee0409/claude-code-history-viewer, XZL-CODE/cc-codex-history-viewer, chrzamz/sessio, specstoryai/getspecstory, HizTam/codex-history-viewer, ay-bh/chat-history, pratikgajjar/recall
  ★1000 以上的新名字：jhlee0409/claude-code-history-viewer, specstoryai/getspecstory
第 2 組「coding agent conversation history」：53 個名字，新的 53 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt
  新：matt1398/claude-devtools, jerrywu001/cc-sessions-viewer, delexw/claude-code-trace, a7t-ai/poirot, PixelPaw-Labs/codex-trace, S40911120/recensa, tuo-lei/vibe-replay, VACInc/openclaw-tool-call-viewer, 2ykwang/cview, zhuchongba-01/AgentSessionManager, wellwelwel/sessioner, thevibeworks/ccx, qiaolei81/copilot-session-viewer, HeavyBunny19C/OpenSession, Ryheff24/agentlog, karanb192/hindcast, wanderer-yk/agent-chatlens, yuluod/AllSessions, Vvkmnn/claude-historian-mcp, kuroko1t/claude-vault, jhammant/ClaudeHistoryMCP, WSL043/dsh-chat-manager, IvyYang1999/swob, vibheksoni/session-export, drewburchfield/claude-code-chat-explorer, coolcorexix/claude-grep, DazzleML/Claude-Session-Backup, Nwflower/dsh-chat-import, zhangxj9819/agent-conversation-graph, monk1337/clicodelog …
  ★1000 以上的新名字：matt1398/claude-devtools, Dicklesworthstone/coding_agent_session_search, yigitkonur/cli-continues
第 3 組「session transcript viewer」：33 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：wilbeibi/catchup, valpere/session-indexer, gautamgpt1/agent-session-browser, noluyorAbi/claude-code-recap, samfoy/pi-session-search, masonc15/codex-transcript-viewer, yfge/TalkReplay, hitmman55/claude-code-chat-viewer, tanghong123/claude-replay, phpmypython/claude-viewer, POSTTTT/agent-cli-session, alexxxtat/claude-transcript-viewer, tad-hq/universal-session-viewer, tim-hua-01/cc_transcript_viewer, mirekholec/copilot-debugger, hopp1395/cc-outline, gpolaert/trace, codesweep-ai/tracer, forensicdave/claude-export-viewer, sessionviewer.cc, ravikanchikare/cc-session-viewer, mantra-hq/mantra-releases, simonw/claude-code-transcripts, Kirushanthan03/claude-code-chat-history-viewer
  ★1000 以上的新名字：simonw/claude-code-transcripts
第 4 組「session handoff cross-agent」：51 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, related, web-en
  新：REMvisual/claude-handoff, Vinyl-Davyl/hermes, remembra-ai/remembra, Adamchanadam/agent-handoff-kit, HaiYangBG1/BuildBeat, cote-star/agent-chorus, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, aa2246740/dsh-resume, alexei-led/resume-from, HarryHeYu/sessionFlow, harrychih/hishare, awithi-co/acdc, TStansel/handoff, dennyferra/paseo-baton, kittimzhe/dsh-session-recall, azzgo/pi-xfer, axisrow/claude-devtools, alexeyv/claude-devtools, jawhnycooke/claude-devtools, powerappsdarren/claude-devtools, vince81/claude-devtools, adriencaccia/claude-devtools, huongctu/claude-devtools, cpiprint/claude-devtools, agarwalpragy/claude-devtools, dev-null-undefined/claude-devtools, hesreallyhim/awesome-claude-code, mrowrpurr-forks/coding_agent_session_search, mic92/coding_agent_session_search …
  ★1000 以上的新名字：hesreallyhim/awesome-claude-code
第 5 組「session export migrate」：34 個名字，新的 27 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：hanityx/threadlens, linfanxxxx/codex-session-exporter, Ann-Diana/codex-project-chat-exporter, MeXenon/kiro-session-export, GaoSSR/codex-export-skill, chaybits/ectype, fabiocampolim-design/claude-session-publisher, bwndlct/dsh-session-export, ZelinZhou-THU/opencode-export, zyx3721/session-exporter-skills, deveduar/vscode-copilot-export-cli, zhaoxuejie/dsh-plugin-session-export, davidqyc/session-preserve, zhyunran/dsh-session-bundle, Camji55/agent-handoff, S2thend/cursor-history, Sertelegger/claude-sesh-mover, yanzhi0922/codex-session-migrator, avikalpa/codex-session-tui, omdsh-dev/dsh-shuttle, es617/claude-replay, pma1999/session-bridge, ahmojo/codex-claude-transfer, grapeot/ai_session_export, didvc/web-to-cc, escoffier-labs/stationtrail, akoserwal/export-conversation-skill
```

### 第 6 組：`agent session replay`（`--topic session-replay`）
- **挑詞理由**：從第 2、3、5 組出現的新詞 `session replay`、`claude-replay`、`TalkReplay` 切入，查重播與時間軸檢視工具，並搭配中文網頁搜尋補足跨工具遷移與重播關鍵字。
- **納入工具**：
  - `github-topic`: `tuo-lei/vibe-replay`, `Entelligence-AI/agentplay`
  - `github-keyword`: `thevibeworks/cctrace`, `camtrik/agent-trail`
  - `hn`: `cosmtrek/mindwalk`
  - `exa`: `Entelligence-AI/agentplay`, `MingoZhou/dsh-replay`
  - `web-zh`: `pma1999/session-bridge`, `inmzhang/transession`, `MisterBrookT/codex2claude`, `ostiums/leftoff`, `AaronWong1999/ccx`, `arghhhhh/claude-conversation-transfer`, `thevibeworks/ccx`, `jazzyalex/agent-sessions`, `kvsankar/agent-history`, `XZL-CODE/cc-codex-history-viewer`, `daaain/claude-code-log`, `es617/claude-replay`, `yfge/TalkReplay`, `furkankly/zoetrope`, `PrashnaLabs/agent-race`, `cosmtrek/mindwalk`
- **排除／拿不準**：
  - 排除：網頁／DOM session replay（`posthog`, `rrweb`, `openreplay`, `highlight`, `clarity`, `sentry-rrweb` 等）；多終端控制塔或系統可觀測／安全／成本最佳化（`eraycoskunai/Termspire`, `ArkFelix7/agentlens`, `hkochar/openclaw-deck`, `ixchio/agent-vcr`, `kixel-ai/token-max`, `princejain756/agentblast`, `openai/codex-plugin-cc`, `AgentsRoom`, `Cooontext`（團隊知識分享庫））。
  - 拿不準（未寫入帳本）：`TaewoooPark/Agent-Blackbox`（replay + context 評分並回寫 `AGENTS.md`）、`yx0716/clawd-insights`（replay + 知識摘要與桌面寵物）、`Buildlog`（錄製為可重播 workflow recipe）。
- **`status --min-stars 1000` 輸出**：
```text
總共 174 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：10 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：@adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, ccassist, jhlee0409/claude-code-history-viewer, XZL-CODE/cc-codex-history-viewer, chrzamz/sessio, specstoryai/getspecstory, HizTam/codex-history-viewer, ay-bh/chat-history, pratikgajjar/recall
  ★1000 以上的新名字：jhlee0409/claude-code-history-viewer, specstoryai/getspecstory
第 2 組「coding agent conversation history」：53 個名字，新的 53 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt
  新：matt1398/claude-devtools, jerrywu001/cc-sessions-viewer, delexw/claude-code-trace, a7t-ai/poirot, PixelPaw-Labs/codex-trace, S40911120/recensa, tuo-lei/vibe-replay, VACInc/openclaw-tool-call-viewer, 2ykwang/cview, zhuchongba-01/AgentSessionManager, wellwelwel/sessioner, thevibeworks/ccx, qiaolei81/copilot-session-viewer, HeavyBunny19C/OpenSession, Ryheff24/agentlog, karanb192/hindcast, wanderer-yk/agent-chatlens, yuluod/AllSessions, Vvkmnn/claude-historian-mcp, kuroko1t/claude-vault, jhammant/ClaudeHistoryMCP, WSL043/dsh-chat-manager, IvyYang1999/swob, vibheksoni/session-export, drewburchfield/claude-code-chat-explorer, coolcorexix/claude-grep, DazzleML/Claude-Session-Backup, Nwflower/dsh-chat-import, zhangxj9819/agent-conversation-graph, monk1337/clicodelog …
  ★1000 以上的新名字：matt1398/claude-devtools, Dicklesworthstone/coding_agent_session_search, yigitkonur/cli-continues
第 3 組「session transcript viewer」：33 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：wilbeibi/catchup, valpere/session-indexer, gautamgpt1/agent-session-browser, noluyorAbi/claude-code-recap, samfoy/pi-session-search, masonc15/codex-transcript-viewer, yfge/TalkReplay, hitmman55/claude-code-chat-viewer, tanghong123/claude-replay, phpmypython/claude-viewer, POSTTTT/agent-cli-session, alexxxtat/claude-transcript-viewer, tad-hq/universal-session-viewer, tim-hua-01/cc_transcript_viewer, mirekholec/copilot-debugger, hopp1395/cc-outline, gpolaert/trace, codesweep-ai/tracer, forensicdave/claude-export-viewer, sessionviewer.cc, ravikanchikare/cc-session-viewer, mantra-hq/mantra-releases, simonw/claude-code-transcripts, Kirushanthan03/claude-code-chat-history-viewer
  ★1000 以上的新名字：simonw/claude-code-transcripts
第 4 組「session handoff cross-agent」：51 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, related, web-en
  新：REMvisual/claude-handoff, Vinyl-Davyl/hermes, remembra-ai/remembra, Adamchanadam/agent-handoff-kit, HaiYangBG1/BuildBeat, cote-star/agent-chorus, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, aa2246740/dsh-resume, alexei-led/resume-from, HarryHeYu/sessionFlow, harrychih/hishare, awithi-co/acdc, TStansel/handoff, dennyferra/paseo-baton, kittimzhe/dsh-session-recall, azzgo/pi-xfer, axisrow/claude-devtools, alexeyv/claude-devtools, jawhnycooke/claude-devtools, powerappsdarren/claude-devtools, vince81/claude-devtools, adriencaccia/claude-devtools, huongctu/claude-devtools, cpiprint/claude-devtools, agarwalpragy/claude-devtools, dev-null-undefined/claude-devtools, hesreallyhim/awesome-claude-code, mrowrpurr-forks/coding_agent_session_search, mic92/coding_agent_session_search …
  ★1000 以上的新名字：hesreallyhim/awesome-claude-code
第 5 組「session export migrate」：34 個名字，新的 27 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：hanityx/threadlens, linfanxxxx/codex-session-exporter, Ann-Diana/codex-project-chat-exporter, MeXenon/kiro-session-export, GaoSSR/codex-export-skill, chaybits/ectype, fabiocampolim-design/claude-session-publisher, bwndlct/dsh-session-export, ZelinZhou-THU/opencode-export, zyx3721/session-exporter-skills, deveduar/vscode-copilot-export-cli, zhaoxuejie/dsh-plugin-session-export, davidqyc/session-preserve, zhyunran/dsh-session-bundle, Camji55/agent-handoff, S2thend/cursor-history, Sertelegger/claude-sesh-mover, yanzhi0922/codex-session-migrator, avikalpa/codex-session-tui, omdsh-dev/dsh-shuttle, es617/claude-replay, pma1999/session-bridge, ahmojo/codex-claude-transfer, grapeot/ai_session_export, didvc/web-to-cc, escoffier-labs/stationtrail, akoserwal/export-conversation-skill
第 6 組「agent session replay」：21 個名字，新的 14 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Entelligence-AI/agentplay, thevibeworks/cctrace, camtrik/agent-trail, cosmtrek/mindwalk, MingoZhou/dsh-replay, inmzhang/transession, MisterBrookT/codex2claude, ostiums/leftoff, AaronWong1999/ccx, arghhhhh/claude-conversation-transfer, kvsankar/agent-history, daaain/claude-code-log, furkankly/zoetrope, PrashnaLabs/agent-race
  ★1000 以上的新名字：cosmtrek/mindwalk, daaain/claude-code-log, furkankly/zoetrope
```

### 第 7 組：`claude codex chat history`
- **挑詞理由**：從前 6 組高頻工具與搜尋結果觀察到多數工具圍繞 Claude Code 與 Codex CLI，改以具體 agent 名稱 `claude codex` 搭配 `chat history` 補漏各家專屬瀏覽／搜尋工具。
- **納入工具**：
  - `github-topic`: `jhlee0409/claude-code-history-viewer`, `specstoryai/getspecstory`, `S40911120/recensa`, `hanityx/threadlens`
  - `github-keyword`: `ssanaullahrais/Chat-Vault`, `yashagldit/Claude-Code-History-VSCode`, `ay-bh/chat-history`, `pratikgajjar/recall`, `SmallHorseBrother/ai-cli-chat-search`, `pmarreck/chatscan`, `cygmris/chatdex`, `fengerwoo/chat-history-skill`, `roccodaffuso/sift`, `Mark-Libetter/ai-conversation-hub`, `jiantao88/ai-history`
  - `hn`: `pratikgajjar/recall`, `skillsynchq/txcript`
  - `exa`: `xingkaixin/codesesh`, `bquenin/mnemonai`, `The-Zombie0/Codex-Claude-History-Viewer`, `jdinkla/ai-history`, `ay-bh/chat-history`
  - `web-en`: `jhlee0409/claude-code-history-viewer`, `monk1337/clicodelog`, `mantra-hq/mantra-releases`, `jerrywu001/cc-sessions-viewer`, `tyql688/sessionview`, `kvsankar/agent-history`, `specstoryai/getspecstory`, `HizTam/codex-history-viewer`, `ccassist`, `raine/claude-history`, `lef237/clauhist`, `FlorianBruniaux/cc-sessions`, `agentic-utils/ccs`, `contextify.sh`
- **排除／拿不準**：
  - 排除：一般聊天機器人歷史（非 coding agent）、多終端即時監控與通知（如 `claude-squad` 等編排器）、單純 token／帳單統計（`ccusage` 等）、長期記憶庫。
  - 拿不準（未寫入帳本）：`Kanary Agents`（`kanary.to/agents`，主打跨專案 session 瀏覽與搜尋，但同時含 agent 編排與監控工作台功能）。
- **`status --min-stars 1000` 輸出**：
```text
總共 192 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 1 組沒有新的（要 3 組）：還不能停
第 7 組「claude codex chat history」：32 個名字，新的 18 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ssanaullahrais/Chat-Vault, yashagldit/Claude-Code-History-VSCode, SmallHorseBrother/ai-cli-chat-search, pmarreck/chatscan, cygmris/chatdex, fengerwoo/chat-history-skill, roccodaffuso/sift, Mark-Libetter/ai-conversation-hub, jiantao88/ai-history, bquenin/mnemonai, The-Zombie0/Codex-Claude-History-Viewer, jdinkla/ai-history, tyql688/sessionview, raine/claude-history, lef237/clauhist, FlorianBruniaux/cc-sessions, agentic-utils/ccs, contextify.sh
```

### 第 8 組：`cursor chat history export`（`--topic cursor-ide`）
- **挑詞理由**：第 5、7 組出現 `S2thend/cursor-history` 等 Cursor 專屬工具，顯示 IDE 型 coding agent（Cursor）的對話資料庫匯出／檢視是獨立長尾分支，因此以 `cursor chat history export` 搭配 `--topic cursor-ide` 追查。
- **納入工具**：
  - `github-topic`: `S2thend/cursor-history`, `hanityx/threadlens`, `S40911120/recensa`, `jhlee0409/claude-code-history-viewer`, `specstoryai/getspecstory`
  - `github-keyword`: `thomas-pedersen/cursor-chat-browser`, `Nwflower/dsh-chat-import`, `S2thend/cursor-history`, `saharmor/cursor-view`, `S2thend/cursor-history-mcp`, `ay-bh/chat-history`, `Cedriccmh/cursor-trace-exporter`, `changlehu/cursor-chat-export-to-markdown`, `livyn-inc/cursor-chat-history-exporter`, `kwiscion/cursor-chat-recovery`, `jitrak-dev/cursor-export`, `the-ensemble/ai-chat-exporters`, `KyawZaw-cmd/Cursor-Multiple-Project-local-chat-History-Find-Export`
  - `skills-sh`: `jlreyes/agent-history-skills`, `Chendestiny/agent-session-sync`
  - `mcp-registry`: `S2thend/cursor-history-mcp`
  - `hn`: `S2thend/cursor-history-mcp`, `S2thend/cursor-history`
  - `exa`: `iksnae/cursor-session`, `johnlindquist/cursor-history`, `S2thend/cursor-history`, `kwiscion/cursor-chat-recovery`, `mikhailsal/cursor-chronicle`
  - `web-en`: `S2thend/cursor-history`, `mikhailsal/cursor-chronicle`, `saharmor/cursor-view`, `thomas-pedersen/cursor-chat-browser`, `iksnae/cursor-session`, `somogyijanos/cursor-chat-export`, `markwroberts0/cursor-chat-recovery`, `M6ZeroG/cursor2md`, `xiaoheilong3112/cursor-chat-exporter`, `anasabbasdev/cursor-chat-bulk-export`, `dwqs/cursor-trace`, `abakermi/vscode-cursorchat-downloader`, `lohasle/AI-Conversation-Viewer`, `jhlee0409/claude-code-history-viewer`, `ay-bh/chat-history`
- **排除／拿不準**：
  - 排除：通用即時通訊匯出（WeChat/Telegram 等 `weclone`, `chatlab`, `echotrace`）、Web ChatGPT 圖譜或記憶庫（`ukkit/memcord`, `1ch1n/mychatarchive`）、Figma 風格多人游標聊天（`jackyzha0/cursor-chat`）、透過 Telegram/Issue 遙控 Cursor（`udah1/cursor-chat-bridge`）、Cursor 帳號／額度重置或 token 統計工具（`codeburn`, `tokscale`, `cursor-stats`）。
  - 拿不準（未寫入帳本）：`shayne-snap/WayLog`（★77，匯出 AI 對話為 Git 知識庫，同時主打「知識庫」定位）。
- **`status --min-stars 1000` 輸出**：
```text
總共 214 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 2 組沒有新的（要 3 組）：還不能停
第 8 組「cursor chat history export」：30 個名字，新的 22 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：thomas-pedersen/cursor-chat-browser, saharmor/cursor-view, S2thend/cursor-history-mcp, Cedriccmh/cursor-trace-exporter, changlehu/cursor-chat-export-to-markdown, livyn-inc/cursor-chat-history-exporter, kwiscion/cursor-chat-recovery, jitrak-dev/cursor-export, the-ensemble/ai-chat-exporters, KyawZaw-cmd/Cursor-Multiple-Project-local-chat-History-Find-Export, Chendestiny/agent-session-sync, iksnae/cursor-session, johnlindquist/cursor-history, mikhailsal/cursor-chronicle, somogyijanos/cursor-chat-export, markwroberts0/cursor-chat-recovery, M6ZeroG/cursor2md, xiaoheilong3112/cursor-chat-exporter, anasabbasdev/cursor-chat-bulk-export, dwqs/cursor-trace, abakermi/vscode-cursorchat-downloader, lohasle/AI-Conversation-Viewer
```

### 第 9 組：`gemini cli opencode session history`（`--topic gemini-cli`）
- **挑詞理由**：第 5、6 組陸續出現 `opencode-export`、Gemini CLI 支援工具，為確認是否遺漏以 Gemini CLI 與 OpenCode 為主體的對話檢視／交接專案，因此以 `gemini cli opencode session history` 搭配 `--topic gemini-cli` 補查。
- **納入工具**：
  - `github-topic`: `jazzyalex/agent-sessions`, `wilbeibi/catchup`, `valpere/session-indexer`, `gautamgpt1/agent-session-browser`, `noluyorabi/claude-code-recap`, `samfoy/pi-session-search`
  - `github-keyword`: `youdie006/sessionwiki`, `seastart/aicoder-session-viewer`, `DnaMes/lore`, `Yaagik/session-recall`, `samanvaya5/session-query`, `williamfzc/ferry`, `itswl/agent-session-query`
  - `npm`: `joe-broadhead/opencode-history`
  - `hn`: `contextify.sh`, `Dicklesworthstone/coding_agent_session_search`
  - `exa`: `ddarmon/sesh`, `youdie006/sessionwiki`, `nicomen/saisons`, `Mert-coderoid/agf`, `agentdrive.sh`
  - `web-en`: `aytzey/showagent`, `yigitkonur/cli-continues`, `rymalia/agent-session-manager`, `44-pixels/handover-mcp`, `AgentWorkforce/relayhistory`, `vibheksoni/session-export`, `gautamgpt1/agent-session-browser`, `nogataka/opencode-viewer`, `jerrywu001/cc-sessions-viewer`, `rcwalter24/opencode-export`, `neuronalism/opencode-session-manager-cli`, `gowtham-sai-yadav/entangle`, `jazzyalex/agent-sessions`
- **排除／拿不準**：
  - 排除：大型 skill 合集與框架（`composiohq/awesome-claude-skills`, `sickn33/agentic-awesome-skills`, `yetone/magpie`, `aionui` 等）、長期記憶／知識圖譜（`deusdata/codebase-memory-mcp`, `zilliztech/claude-context`, `obsidian-mind`, `pratiyush/llm-wiki`, `ix-infrastructure/Ix`）、中繼／遙控／壓縮修剪（`claude-relay-service`, `tiann/hapi`, `debadityahait/agent-session-prune`, `opencode-dynamic-context-pruning`, `wolfiesch/agent-session-compress`）。
  - 拿不準（未寫入帳本）：`vshulcz/deja-vu`（★1,608，第 1 組已列拿不準，跨 agent 檢索與交接外並主打長期記憶與 LongMemEval 基準）、`lyfuci/ai-terminal-manager`（★20，統一 session 歷史外主要是持續性 tmux 終端機管理器）、`ShrimpScript/lectern`（★2，多 agent 共享大腦與任務路由編排）、`reyanshgupta/ditto-cli`（★0，多帳號設定檔切換器附帶保留歷史）、`saadnvd1/hydra`（★21，限流自動切換包裝器附帶脈絡轉移）、`cvelasquez/agent-workbench`（★13，第 2 組已列拿不準）、`ccswitch.io`（API provider 切換器附帶 session 管理擴充）。
- **`status --min-stars 1000` 輸出**：
```text
總共 232 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 3 組沒有新的（要 3 組）：可以停，報告寫「長尾未飽和」並附上面兩種連續數
第 9 組「gemini cli opencode session history」：31 個名字，新的 18 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：youdie006/sessionwiki, seastart/aicoder-session-viewer, DnaMes/lore, Yaagik/session-recall, samanvaya5/session-query, williamfzc/ferry, itswl/agent-session-query, joe-broadhead/opencode-history, ddarmon/sesh, nicomen/saisons, Mert-coderoid/agf, agentdrive.sh, rymalia/agent-session-manager, 44-pixels/handover-mcp, nogataka/opencode-viewer, rcwalter24/opencode-export, neuronalism/opencode-session-manager-cli, gowtham-sai-yadav/entangle
```

## 主停止點
- **停止組別**：第 9 組「`gemini cli opencode session history`」
- **觸發條件**：`★1000 以上的 GitHub repo：連續 3 組沒有新的（要 3 組）：可以停，報告寫「長尾未飽和」並附上面兩種連續數`
- **停止時連續數**：
  - 不重複名字總數：232 個；連續 0 組沒有新名字（未達 3 組，長尾小專案仍持續出現）
  - ★1,000 以上的 GitHub repo：連續 3 組（第 7、8、9 組）沒有新名字 → **主停止點成立（長尾未飽和）**

## 驗證階段（主停止點後多查 2 組）

### 驗證第 1 組（第 10 組）：`session backup conversation archive`（`--topic session-search`）
- **挑詞理由**：主停止點後驗證「備份、封存、全文搜尋」方向是否還有未捕獲的 ★1,000 以上工具。
- **納入工具**：
  - `github-topic`: `angristan/fast-resume`, `samzong/Recall`, `ahundt/ai-session-search`, `PolinniZhong/dsh-session-workbench`, `lee-fuhr/claude-session-index`, `vibheksoni/session-export`, `bvolpato/omnisession`, `hxreborn/herdr-transcripts`, `HarryHeYu/sessionFlow`, `demirciAhmet/ocsearch`, `Augl-l/dsh-session-search`, `helo060228/dsh-chat-search`, `WangPeterXF/session-harbor`, `DazzleML/Claude-Session-Backup`, `davidqyc/session-preserve`
  - `github-keyword`: `mienfong/dsh-session-mgr`
  - `skills-sh`: `mapleleo-hub/chat-share-reader`
  - `mcp-registry`: `brucexcluding/session-recap`, `SomeNoneAI/find-my-session`, `mallikcheripally/session-steward`
  - `hn`: `wangjohn/agent-archive`
  - `exa`: `xxxily/convx`, `chunxue-ai/cc-archive`, `Ultroncn/dsh-archived-chats`
  - `web-en`: `Dicklesworthstone/coding_agent_session_search`, `youdie006/sessionwiki`, `bvolpato/omnisession`, `wangjohn/agent-archive`, `mallikcheripally/session-steward`, `jazzyalex/agent-sessions`, `wesm/archived-agent-session-viewer`, `DazzleML/Claude-Session-Backup`, `genspark-ai/cc-conversation-archiver`, `2389-research/ccvault`, `babarot/claude-recall`, `GunitBindal/claude-transcript-exporter`, `softagram/cc-search`, `coolcorexix/claude-grep`, `simonw/claude-code-transcripts`
- **驗證結果（單獨統計）**：
  - 總計納入 35 個名字，其中 **新名字 25 個**（最高星數為 `WangPeterXF/session-harbor` ★86、`wesm/archived-agent-session-viewer` ★88、`ahundt/ai-session-search` ★81、`samzong/Recall` ★109、`angristan/fast-resume` ★195）。
  - **新的 ★1,000 以上 GitHub repo：0 個**。
- **排除／拿不準**：
  - 排除：大型合集/編排（`code-yeongyu/oh-my-openagent`, `dimitrihilverda/claude-session-relay`）、非 coding agent 匯出（`willwefind/mufy-batch-export`）、成本駕駛艙（`Lxiayu/DshCockpit`）、原生對話回退外掛（`SiriLee/dsh-rewind`）。
  - 拿不準（未寫入帳本）：`hetpatel-11/agent-hop`（★36，多 agent 終端執行環境附帶跨 agent 切換與搜尋）、`abraxas914/VESTI`（★363，泛用 AI 網頁對話記憶與知識中台，非專注 coding agent）。

### 驗證第 2 組（第 11 組）：`copilot cline chat history export`（`--topic copilot-chat`）
- **挑詞理由**：主停止點後驗證 IDE 擴充型 agent（GitHub Copilot、Cline、Roo Code）的對話匯出與檢視工具是否還有遺漏的 ★1,000 以上專案。
- **納入工具**：
  - `github-topic`: `specstoryai/getspecstory`, `jhlee0409/claude-code-history-viewer`, `S40911120/recensa`, `hanityx/threadlens`
  - `exa`: `T-Gojo/ContextBridgeAi`
  - `web-en`: `jhlee0409/claude-code-history-viewer`, `TomSchmidtDev/vscode-ai-chat-exporter`, `pandaxbacon/github-copilot-chat-exporter`
- **驗證結果（單獨統計）**：
  - 總計納入 7 個名字，其中 **新名字 3 個**（`T-Gojo/ContextBridgeAi` ★1、`TomSchmidtDev/vscode-ai-chat-exporter` ★2、`pandaxbacon/github-copilot-chat-exporter` ★1）。
  - **新的 ★1,000 以上 GitHub repo：0 個**。
- **排除／拿不準**：
  - 排除：Copilot 框架或編輯器本體（`copilotkit/copilotkit`, `copilotchat.nvim`, `cline/cline`, `vscode-copilot-release`）、非 coding agent 聊天匯出（`weclone`, `chatlab`, `echotrace`, `shuya-abe/copilot-chat-exporter`）。
  - 拿不準（未寫入帳本）：`CodeAgentSwarm`（主要為多 agent 編排協調平台，另支援唯讀檢視 Cline 本機 session 歷史）。
- **驗證後 `status --min-stars 1000` 輸出**：
```text
總共 260 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 5 組沒有新的（要 3 組）：可以停，報告寫「長尾未飽和」並附上面兩種連續數
第 10 組「session backup conversation archive」：35 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：angristan/fast-resume, samzong/Recall, ahundt/ai-session-search, PolinniZhong/dsh-session-workbench, lee-fuhr/claude-session-index, hxreborn/herdr-transcripts, demirciAhmet/ocsearch, Augl-l/dsh-session-search, helo060228/dsh-chat-search, WangPeterXF/session-harbor, mienfong/dsh-session-mgr, mapleleo-hub/chat-share-reader, brucexcluding/session-recap, SomeNoneAI/find-my-session, mallikcheripally/session-steward, wangjohn/agent-archive, xxxily/convx, chunxue-ai/cc-archive, Ultroncn/dsh-archived-chats, wesm/archived-agent-session-viewer, genspark-ai/cc-conversation-archiver, 2389-research/ccvault, babarot/claude-recall, GunitBindal/claude-transcript-exporter, softagram/cc-search
第 11 組「copilot cline chat history export」：7 個名字，新的 3 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：T-Gojo/ContextBridgeAi, TomSchmidtDev/vscode-ai-chat-exporter, pandaxbacon/github-copilot-chat-exporter
```

---

## 最終名單（已於 2026-11-18 透過 `sweep.py verify` 查核）

> [!IMPORTANT]
> **長尾未飽和**：本題目於第 9 組達成主停止點（連續 3 組無新的 ★1,000 以上 GitHub repo），且驗證第 10、11 組亦均為 **0 個新的 ★1,000 以上專案**（合計連續 5 組無 ★1,000 以上新專案），顯示高星數主流工具已趨近收斂；但因小眾／個人開源專案仍持續湧現（總計 260 個帳本名字，連續 0 組無新名字），因此長尾仍未飽和，★1,000 以下名單僅代表本次 11 組橫跨中英文與多平台的代表性發現，並非窮盡全網所有小專案。

### 一、★1,000 以上主流工具（共 9 個）

| 名字 / `owner/repo` | 網址 | verified 星數 | 授權 | 封存 | 最後 push | 一句話做什麼 |
|---|---|---:|---|---|---|
| **matt1398/claude-devtools** (`★1,000+`) | https://github.com/matt1398/claude-devtools | ★4,042 | MIT | 否 | 2026-09-26 | 視覺化檢查 Claude Code session 日誌、工具呼叫、token 用量與子代理脈絡的桌面除錯工具。 |
| **jhlee0409/claude-code-history-viewer** (`★1,000+`) | https://github.com/jhlee0409/claude-code-history-viewer | ★2,324 | MIT | 否 | 2026-11-18 | 支援 Claude Code、Codex、Copilot、Gemini CLI、Cursor、OpenCode 等 30+ 助理的離線對話瀏覽、搜尋與分析桌面／Web 工具。 |
| **simonw/claude-code-transcripts** (`★1,000+`) | https://github.com/simonw/claude-code-transcripts | ★1,734 | Apache-2.0 | 否 | 2026-02-12 | 將 Claude Code session 對話紀錄發布與匯出為可讀 HTML 網頁的 CLI 工具。 |
| **yigitkonur/cli-continues** (`★1,000+`) | https://github.com/yigitkonur/cli-continues | ★1,605 | MIT | 否 | 2026-05-07 | 讀取本機 16 種 coding CLI 對話紀錄並產生結構化交接文件，無縫轉往另一個 agent 接手續做。 |
| **cosmtrek/mindwalk** (`★1,000+`) | https://github.com/cosmtrek/mindwalk | ★1,400 | MIT | 否 | 2026-08-10 | 將 coding agent session 操作過程於 3D 程式碼地圖上重播與視覺化的檢視工具。 |
| **specstoryai/getspecstory** (`★1,000+`) | https://github.com/specstoryai/getspecstory | ★1,375 | Apache-2.0 | 否 | 2026-11-17 | IDE 與終端 agent 的本機優先擴充套件，自動保存、檢視與同步 coding agent 對話紀錄。 |
| **daaain/claude-code-log** (`★1,000+`) | https://github.com/daaain/claude-code-log | ★1,266 | MIT | 否 | 2026-11-18 | 將 Claude Code 的 JSONL 對話紀錄轉為易讀 HTML 與 Markdown 的 Python CLI 工具。 |
| **Dicklesworthstone/coding_agent_session_search** (`★1,000+`) | https://github.com/Dicklesworthstone/coding_agent_session_search | ★1,214 | NOASSERTION | 否 | 2026-11-17 | 為 30+ 種本機 coding agent 建立統一索引並提供 TUI／CLI 混合檢索與 JSON 輸出的搜尋工具。 |
| **furkankly/zoetrope** (`★1,000+`) | https://github.com/furkankly/zoetrope | ★1,182 | MIT | 否 | 2026-11-03 | 在終端或瀏覽器中以即時流程圖重播並檢視 Claude Code 或 Codex session 的工具。 |

### 二、獨立網站／非 GitHub 主體工具（共 3 個；另註去重項目）

| 名字 | 網址 | 備註／授權 | 一句話做什麼 |
|---|---|---|---|
| **SessionViewer** (`sessionviewer.cc`) | https://sessionviewer.cc | 線上免安裝解析器 | 在瀏覽器本機端檢視 Codex 與 Claude Code session 日誌並產生可分享頁面。 |
| **Contextify** (`contextify.sh`) | https://contextify.sh | 桌面端／跨機同步產品 | 保存即將過期刪除的 Claude Code 與 Codex 歷史對話於可搜尋資料庫並跨機同步。 |
| **AgentDrive** (`agentdrive.sh`) | https://agentdrive.sh | 跨 agent 續聊服務 | 在背景同步 Gemini CLI / Antigravity 與 OpenCode session 並帶入目標、修改檔案與近期對話接續工作。 |

- **已去重合併之同名／同源項目**：`ccassist`（`ccassist.dev`，即表列 `yashagldit/Claude-Code-History-VSCode`，★42，專有授權／issue repo）；`@adamchanadam/agent-handoff-kit`（npm 套件，即 `Adamchanadam/agent-handoff-kit`，★16）；`claudebin`（Product Hunt 名稱，即 `wunderlabs-dev/claudebin.com`，★71）。
- **帳本複檢剔除／失效註記**：
  - 第 4 組 `sweep.py related --ledger` 自動寫入之 forks（`claude-devtools` 與 `coding_agent_session_search` 之 forks）及合集清單 `hesreallyhim/awesome-claude-code`、UI 元件庫 `dicklesworthstone/frankentui` 已自最終名單剔除。
  - 第 2 組由 Product Hunt 摘要暫收之 `ccgather`（`DHxWhy/CCgather`，★48，MIT，2026-11-18）經複查實為 Claude Code 用量全球排行榜，非對話紀錄檢視／交接工具，已自最終名單剔除。
  - 第 2 組收錄之 `WSL043/dsh-chat-manager` 於 `sweep.py verify` 查核時回傳 HTTP 404（已刪除或更名），未列入可用名單。

### 三、★1,000 以下長尾開源工具（共 220 個，依 verify 星數排序）

| # | `owner/repo` | 網址 | verified 星數 | 授權 | 封存 | 最後 push | 一句話做什麼 |
|---:|---|---|---:|---|---|---|
| 1 | jazzyalex/agent-sessions | https://github.com/jazzyalex/agent-sessions | ★949 | MIT | 否 | 2026-11-17 | Local-first macOS app to browse, search, analyze, and resume supported AI coding-agent session history across Codex, Claude Code, OpenCode, Cursor Agent, Antigravity, Hermes, OpenClaw, Copilot CLI, and more. |
| 2 | es617/claude-replay | https://github.com/es617/claude-replay | ★862 | MIT | 否 | 2026-11-13 | Convert AI coding agent sessions (Claude Code, Cursor, Codex, Gemini, OpenCode, Kimi Code, Hermes) into self-contained, embeddable HTML  replays |
| 3 | raine/claude-history | https://github.com/raine/claude-history | ★544 | MIT | 否 | 2026-11-04 | Fuzzy-search Claude Code conversation history |
| 4 | thomas-pedersen/cursor-chat-browser | https://github.com/thomas-pedersen/cursor-chat-browser | ★516 | 無 | 否 | 2026-08-23 | A web application for browsing and managing chat histories from the Cursor editor's AI chat feature. View, search, and export your AI conversations in various formats. |
| 5 | jerrywu001/cc-sessions-viewer | https://github.com/jerrywu001/cc-sessions-viewer | ★420 | MIT | 否 | 2026-11-02 | support cc/codex/grok build/kimicode/pi/antigravity cli/opencode sessions viewer, skills manage, token usage statistics, global search, resume, and export to html |
| 6 | delexw/claude-code-trace | https://github.com/delexw/claude-code-trace | ★391 | MIT | 否 | 2026-11-17 | Claude Code session log viewer for JSONL files in ~/.claude/projects. Browse conversations, tool calls, tokens, and live tail sessions on desktop, web, and TUI. |
| 7 | Entelligence-AI/agentplay | https://github.com/Entelligence-AI/agentplay | ★370 | Apache-2.0 | 否 | 2026-11-11 | Replay your coding agent sessions as a map and a timeline |
| 8 | Nwflower/dsh-chat-import | https://github.com/Nwflower/dsh-chat-import | ★317 | MIT | 否 | 2026-11-15 | Import conversation history from 25+ AI coding agents into DeepSeek Harness as resumable sessions — tool calls, reasoning and results kept intact, with reverse export and sync. ｜ 把 25+ AI 编程 Agent 的聊天记录导入 DeepSeek Harness 继续对话，保留工具调用、推理与结果，支持反向导出与同步。 |
| 9 | somogyijanos/cursor-chat-export | https://github.com/somogyijanos/cursor-chat-export | ★247 | 無 | 是 | 2024-08-30 | Export your chats from Cursor to Markdown. |
| 10 | skillsynchq/txcript | https://github.com/skillsynchq/txcript | ★222 | Apache-2.0 | 否 | 2026-11-18 | Pandoc for AI chats. Move ai chats across harnesses: Claude Code, Codex, OpenCode, Cursor, and more. Rust library, CLI, and WASM. |
| 11 | a7t-ai/poirot | https://github.com/a7t-ai/poirot | ★215 | MIT | 否 | 2026-10-27 | A native macOS companion for Claude Code that lets you browse sessions, explore diffs, and re-run commands. |
| 12 | angristan/fast-resume | https://github.com/angristan/fast-resume | ★195 | MIT | 否 | 2026-11-13 | Find that one coding agent session you want to get back to! |
| 13 | Vvkmnn/claude-historian-mcp | https://github.com/Vvkmnn/claude-historian-mcp | ★180 | MIT | 否 | 2026-11-02 | 📜 An MCP server for conversation history search and retrieval in Claude Code |
| 14 | xhluca/session-migrate | https://github.com/xhluca/session-migrate | ★180 | MIT | 否 | 2026-11-16 | Migrate coding agent sessions across 18 harnesses (Claude Code, Codex, Pi, OpenCode, Copilot, Antigravity, Vibe, Muse, Qwen, Kimi, Cursor, etc.) |
| 15 | S2thend/cursor-history | https://github.com/S2thend/cursor-history | ★153 | MIT | 否 | 2026-10-26 | The ultimate open-source tool for browsing, searching, exporting, and backing up your Cursor AI chat history. |
| 16 | saharmor/cursor-view | https://github.com/saharmor/cursor-view | ★134 | Apache-2.0 | 否 | 2025-09-12 | Browse, search, export, and share your entire Cursor AI chat history |
| 17 | PixelPaw-Labs/codex-trace | https://github.com/PixelPaw-Labs/codex-trace | ★120 | MIT | 否 | 2026-11-15 | OpenAI Codex CLI session log viewer for JSONL files in ~/.codex/sessions. Browse conversations, tool calls, tokens, collaboration chains, and live sessions on desktop and web. |
| 18 | samzong/Recall | https://github.com/samzong/Recall | ★109 | MIT | 否 | 2026-11-12 | Switch agents. Keep the history. Local-first search across your AI coding sessions. |
| 19 | ssanaullahrais/Chat-Vault | https://github.com/ssanaullahrais/Chat-Vault | ★94 | MIT | 否 | 2026-11-15 | Access conversations from Claude Code, Codex, Cursor, Gemini CLI, and OpenCode in one desktop app, with local backups to keep your chat history and context safe. |
| 20 | wesm/archived-agent-session-viewer | https://github.com/wesm/archived-agent-session-viewer | ★88 | MIT | 是 | 2026-02-23 | Browse, search, and revisit your AI coding sessions. |
| 21 | WangPeterXF/session-harbor | https://github.com/WangPeterXF/session-harbor | ★86 | NOASSERTION | 否 | 2026-08-27 | Local-first Codex session backup, verified cleanup, restore, and reviewed cross-device context for macOS and Windows. |
| 22 | ahmojo/codex-claude-transfer | https://github.com/ahmojo/codex-claude-transfer | ★84 | MIT | 否 | 2026-11-17 | Local-first CLI (cct) that moves Codex & Claude Code sessions between machines: export to a .codexbundle, copy, import. No cloud, no account, optional LAN sync. |
| 23 | wilbeibi/catchup | https://github.com/wilbeibi/catchup | ★83 | MIT | 否 | 2026-10-24 | Local-first CLI for coding-agent context handoff. Transfer and resume sessions across Claude Code, Codex, Cursor, Cline, Kimi, Antigravity, OpenCode, and Pi Agent. |
| 24 | ahundt/ai-session-search | https://github.com/ahundt/ai-session-search | ★81 | Apache-2.0 | 否 | 2026-11-18 | Ultra-fast rust-powered AI agent session search and analysis. Search millions of messages in under a second. Claude Code, Claude Desktop, Codex, Cursor, Antigravity, Pi, Google AI Studio, and Gemini CLI. One Rust core behind the aise CLI, an MCP server, a Rust library, and a Python API. |
| 25 | REMvisual/claude-handoff | https://github.com/REMvisual/claude-handoff | ★75 | MIT | 否 | 2026-11-11 | Session handoffs for Claude Code: skills that capture decisions, failed approaches and next steps, plus a Claude Code mod (/compact-handoff) that replaces the conversation with a validated handoff and keeps going. A better /compact. |
| 26 | kuroko1t/claude-vault | https://github.com/kuroko1t/claude-vault | ★74 | MIT | 否 | 2026-08-31 | Archive Claude Code conversations into SQLite with FTS5 search. Single binary, zero dependencies. |
| 27 | S40911120/recensa | https://github.com/S40911120/recensa | ★73 | MIT | 否 | 2026-10-11 | Self-hosted web viewer for Claude Code session transcripts — read, search, replay, and audit every session you have ever run |
| 28 | wunderlabs-dev/claudebin.com | https://github.com/wunderlabs-dev/claudebin.com | ★71 | MIT | 否 | 2026-06-23 | Claudebin is a minimalistic tool for publishing and sharing Claude coding sessions |
| 29 | jhammant/ClaudeHistoryMCP | https://github.com/jhammant/ClaudeHistoryMCP | ★69 | MIT | 否 | 2026-09-20 | MCP server for searching and surfacing Claude Code conversation history |
| 30 | yuzushi-dev/session-handoff | https://github.com/yuzushi-dev/session-handoff | ★67 | MIT | 否 | 2026-11-18 | Create handoff documents and migrate active sessions between Claude Code and Codex. |
| 31 | aytzey/showagent | https://github.com/aytzey/showagent | ★64 | MIT | 否 | 2026-11-16 | Switch coding agents mid-task and keep the conversation. Find every local Claude Code, Codex, Gemini CLI, OpenCode, Antigravity & Pi session in one terminal picker; resume it, branch it from any message, or hand it off to another agent as a native session. TUI + CLI + MCP server. |
| 32 | babarot/claude-recall | https://github.com/babarot/claude-recall | ★64 | MIT | 否 | 2026-11-14 | Recall any past Claude Code session: ask Claude to look into it, or find it yourself and go back to it. |
| 33 | hanityx/threadlens | https://github.com/hanityx/threadlens | ★61 | MIT | 否 | 2026-05-20 | Search, review, back up, and safely clean up local sessions from Codex, Claude, Gemini, and Copilot. |
| 34 | Yanvi-Robotics/mnemo | https://github.com/Yanvi-Robotics/mnemo | ★58 | MIT | 否 | 2026-10-02 | （GitHub repo 未填寫簡介，依專案名稱／搜尋摘要判定為對應對話紀錄或交接工具） |
| 35 | zhangxj9819/agent-conversation-graph | https://github.com/zhangxj9819/agent-conversation-graph | ★53 | 無 | 否 | 2026-08-18 | Visualize Codex/Cluade Code conversation history as a git-style branch graph |
| 36 | HizTam/codex-history-viewer | https://github.com/HizTam/codex-history-viewer | ★49 | MIT | 否 | 2026-11-12 | A VS Code extension to browse, search, tag, import/export, and manage local Codex CLI / Claude Code session history, then resume selected sessions directly in the related VS Code extension. |
| 37 | monk1337/clicodelog | https://github.com/monk1337/clicodelog | ★49 | MIT | 否 | 2026-08-24 | Browse & Inspect CLI agents : Claude Code, Codex, Gemini CLI code & conversation history |
| 38 | PolinniZhong/dsh-session-workbench | https://github.com/PolinniZhong/dsh-session-workbench | ★47 | MIT | 否 | 2026-09-28 | Session Workbench for DeepSeek Harness: session-library full-text search + recall + conversation-view management (show/hide + reorder). 会话工作台：会话库（历史会话全文搜索与召回）+ 会话视图（标签栏显示/隐藏 + 拖拽排序）。 |
| 39 | camtrik/agent-trail | https://github.com/camtrik/agent-trail | ★45 | MIT | 否 | 2026-11-11 | Local dashboard for Claude Code, Codex, OpenCode, OpenClaw and Qoder session history, token usage, cost tracking, tool calls and subagent replay. |
| 40 | Ryu0118/ctxmv | https://github.com/Ryu0118/ctxmv | ★44 | MIT | 否 | 2026-11-17 | 🏠 A CLI tool to migrate sessions between AI coding agents |
| 41 | IvyYang1999/swob | https://github.com/IvyYang1999/swob | ★42 | Apache-2.0 | 否 | 2026-09-28 | Local-first git graph and session debugger for Claude Code, Codex, Cursor, OpenCode, and 7 more AI coding harnesses. |
| 42 | valpere/session-indexer | https://github.com/valpere/session-indexer | ★42 | Apache-2.0 | 否 | 2026-11-16 | Per-project semantic search over Claude Code session history. Indexes JSONL transcripts into SQLite; retrieves via bge-m3 embeddings (Ollama) with FTS5 fallback. |
| 43 | yashagldit/Claude-Code-History-VSCode | https://github.com/yashagldit/Claude-Code-History-VSCode | ★42 | NOASSERTION | 否 | 2026-11-17 | VS Code extension to browse Claude Code, Codex, OpenCode, Grok and GitHub Copilot chat history — file diffs, full-text search, file timeline, token usage and cost analytics. |
| 44 | lohasle/AI-Conversation-Viewer | https://github.com/lohasle/AI-Conversation-Viewer | ★40 | Apache-2.0 | 否 | 2025-12-02 | AI Conversation Viewer - A beautiful web interface to browse and search your AI conversation history across multiple platforms (Claude, Qwen,Cursor,Trae,Kiro). Features full-text search, syntax highlighting, and unified view for all your AI chats. |
| 45 | tuo-lei/vibe-replay | https://github.com/tuo-lei/vibe-replay | ★39 | MIT | 否 | 2026-11-08 | Turn AI coding sessions into animated, interactive web replays |
| 46 | gautamgpt1/agent-session-browser | https://github.com/gautamgpt1/agent-session-browser | ★36 | MIT | 否 | 2026-09-12 | Browse, filter, export, and resume local Codex, Claude Code, Gemini CLI, Pi, and Antigravity sessions. |
| 47 | S2thend/cursor-history-mcp | https://github.com/S2thend/cursor-history-mcp | ★34 | MIT | 否 | 2026-09-08 | MCP server for browsing, searching, and exporting Cursor AI chat history. |
| 48 | youdie006/sessionwiki | https://github.com/youdie006/sessionwiki | ★34 | MIT | 否 | 2026-11-10 | Search every AI coding session already on your disk - including the months from before you installed this - and trace any file back to the conversation that wrote it. Claude Code, Codex, Cline, OpenCode, Gemini CLI history and 6 more. No embeddings, no server, one local Rust binary. |
| 49 | lee-fuhr/claude-session-index | https://github.com/lee-fuhr/claude-session-index | ★31 | MIT | 否 | 2026-03-21 | Index, search, and analyze your Claude Code sessions. Full-text search, conversation retrieval, analytics, and cross-session synthesis. |
| 50 | noluyorAbi/claude-code-recap | https://github.com/noluyorAbi/claude-code-recap | ★30 | MIT | 否 | 2026-08-08 | Browse every recent Claude Code session across all your projects and jump back into any of them. Shows project path, summary, git branch, model, turn count, and a ready-to-paste resume command. --open re-opens a whole working set in terminal tabs. Local files only: no network, no telemetry. |
| 51 | Ultroncn/dsh-archived-chats | https://github.com/Ultroncn/dsh-archived-chats | ★30 | MIT | 否 | 2026-11-18 | Search archived and unarchived chats within separate scopes, preview conversations, manage tags and notes, archive by workspace, import and export ZIP backups, explore conversation lineage, confirm permanent deletions with retry, and check for updates. |
| 52 | chunxue-ai/cc-archive | https://github.com/chunxue-ai/cc-archive | ★29 | 無 | 否 | 2026-04-24 | Portable backup and migration for Claude Code sessions. |
| 53 | inmzhang/transession | https://github.com/inmzhang/transession | ★29 | MIT | 否 | 2026-08-18 | Translate sessions between claude code and codex |
| 54 | VACInc/openclaw-tool-call-viewer | https://github.com/VACInc/openclaw-tool-call-viewer | ★29 | MIT | 否 | 2026-03-25 | 🦞 Web UI for browsing OpenClaw session tool call history. Zero dependencies, just Node.js. |
| 55 | gowtham-sai-yadav/entangle | https://github.com/gowtham-sai-yadav/entangle | ★28 | MIT | 否 | 2026-08-05 | Hand a live Claude Code, Codex, or opencode session to anyone with three spoken words - encrypted, no account. Or carry your whole Claude Code history to a new laptop, every path rewritten. |
| 56 | samfoy/pi-session-search | https://github.com/samfoy/pi-session-search | ★27 | MIT | 否 | 2026-10-29 | Semantic search over past pi coding sessions — index, browse, and read your coding history |
| 57 | abakermi/vscode-cursorchat-downloader | https://github.com/abakermi/vscode-cursorchat-downloader | ★24 | 無 | 否 | 2024-11-13 | View and download your Cursor AI chat history |
| 58 | masonc15/codex-transcript-viewer | https://github.com/masonc15/codex-transcript-viewer | ★24 | MIT | 否 | 2026-10-25 | Turn Codex CLI session logs into browsable HTML transcripts |
| 59 | mikhailsal/cursor-chronicle | https://github.com/mikhailsal/cursor-chronicle | ★24 | AGPL-3.0 | 否 | 2026-07-20 | The ultimate Cursor IDE database companion: full-text search, chat extraction, usage statistics & token tracking, tool call analysis, Markdown export, and secure backup & restore. |
| 60 | vibheksoni/session-export | https://github.com/vibheksoni/session-export | ★22 | MIT | 否 | 2026-10-27 | Convert AI coding CLI sessions between Codex, Claude Code, Pi, OpenCode, Devin, and Factory. SDK, CLI, MCP chat recall, and trace export for fine-tuning. |
| 61 | yfge/TalkReplay | https://github.com/yfge/TalkReplay | ★22 | MIT | 否 | 2026-02-03 | The only tool that replays Claude, Codex, Cursor, AND Gemini AI coding sessions in one unified UI. Vibe coding companion for reviewing, searching, and sharing your AI pair programming transcripts. |
| 62 | drewburchfield/claude-code-chat-explorer | https://github.com/drewburchfield/claude-code-chat-explorer | ★21 | MIT | 否 | 2026-07-29 | Browse, search, and explore your Claude Code conversation history with a fast SQLite-powered web interface |
| 63 | linfanxxxx/codex-session-exporter | https://github.com/linfanxxxx/codex-session-exporter | ★20 | MIT | 否 | 2026-03-20 | Export, inspect, and share local Codex sessions as Markdown, HTML, or portable bundles. |
| 64 | TStansel/handoff | https://github.com/TStansel/handoff | ★20 | MIT | 否 | 2026-05-24 | Handoff context from one agent to another agent |
| 65 | tyql688/sessionview | https://github.com/tyql688/sessionview | ★20 | MIT | 否 | 2026-10-20 | Browse, search, resume and manage your AI coding sessions in one local desktop app. (Claude Code, Codex,  Gemini,OpenCode, Cursor, kimi) |
| 66 | 2ykwang/cview | https://github.com/2ykwang/cview | ★19 | MIT | 否 | 2026-08-07 | Local viewer for Claude Code sessions with search, timeline, and export. |
| 67 | builderpepc/agent-migrator | https://github.com/builderpepc/agent-migrator | ★19 | CC-BY-SA-4.0 | 否 | 2026-06-26 | Migrate conversation history between AI coding tools (Cursor, Claude Code, Codex, Gemini) |
| 68 | tad-hq/universal-session-viewer | https://github.com/tad-hq/universal-session-viewer | ★19 | AGPL-3.0 | 否 | 2026-03-23 | 🔍 Desktop app for browsing, searching, and analyzing Claude Code conversation transcripts. Features continuation chain detection, full-text search, AI-powered session summaries, and real-time file watching. Built with Electron, React, TypeScript, Go, and SQLite. AGPL-3.0 open source. |
| 69 | M6ZeroG/cursor2md | https://github.com/M6ZeroG/cursor2md | ★18 | 無 | 否 | 2025-02-08 | 一个适用于cursor 0.43版本以后的Cursor聊天记录提取工具，代码使用cursor自动生成，主要用于将Cursor编辑器中的AI聊天记录提取并转换为Markdown文件的工具。 |
| 70 | coolcorexix/claude-grep | https://github.com/coolcorexix/claude-grep | ★17 | MIT | 否 | 2026-08-17 | Search your Claude Code conversation history by content (not just titles), then resume any session. grep + fzf, no index. |
| 71 | DazzleML/Claude-Session-Backup | https://github.com/DazzleML/Claude-Session-Backup | ★17 | GPL-3.0 | 否 | 2026-09-09 | Git-backed Claude Code session backup with timeline view, folder analysis, deletion detection, and session restore |
| 72 | MingoZhou/dsh-replay | https://github.com/MingoZhou/dsh-replay | ★17 | MIT | 否 | 2026-11-16 | Agent 会话的时光机。 一个 DeepSeek Harness 插件,把 append-only 会话日志变成可交互的回放:可播放的时间线 + 逐步 token 账单、安全审计视图、fork 血缘树、双会话对比 —— 全部内嵌在 Harness 的 Web UI 里。 |
| 73 | Vinyl-Davyl/hermes | https://github.com/Vinyl-Davyl/hermes | ★17 | MIT | 否 | 2026-09-28 | Local-first handoff CLI that packs unfinished work on your disk and hands it to the next coding agent: Claude, Cursor, Codex, Antigravity, and more. No plugin. No cloud. |
| 74 | AaronWong1999/ccx | https://github.com/AaronWong1999/ccx | ★16 | MIT | 否 | 2026-11-16 | Sync task context between Claude Code, Codex and Antigravity. Hit a limit? Switch agents and keep going. |
| 75 | Adamchanadam/agent-handoff-kit | https://github.com/Adamchanadam/agent-handoff-kit | ★16 | MIT | 否 | 2026-11-15 | Session 接力棒：以 context engineering（為 AI 準備它需要知道的背景資料）為核心，把進度、 決策和下一步留在專案資料夾，讓不同的 AI 工具接手繼續工作。Your session relay baton — context engineering at its core: keep progress, decisions and next steps in your project folder, so supported AI tools can pick up where the last one left off. |
| 76 | HaiYangBG1/BuildBeat | https://github.com/HaiYangBG1/BuildBeat | ★16 | MIT | 否 | 2026-11-16 | 换会话、换工具、换人，项目都能接着干：每项需求的上下文跟代码一起存在 Git 里。｜ Switch sessions, tools or people and the project carries on: each piece of work's context lives in Git with the code. |
| 77 | remembra-ai/remembra | https://github.com/remembra-ai/remembra | ★16 | MIT | 否 | 2026-11-14 | Remembra Relay: one agent stops, the next one already knows. Session handoffs built from git facts, for the next coding agent in any MCP tool, on any machine. MCP server + CLI. MIT. |
| 78 | tim-hua-01/cc_transcript_viewer | https://github.com/tim-hua-01/cc_transcript_viewer | ★16 | MIT | 否 | 2026-11-10 | Zero-dependency local web app for browsing Claude Code session transcripts |
| 79 | zhuchongba-01/AgentSessionManager | https://github.com/zhuchongba-01/AgentSessionManager | ★16 | MIT | 否 | 2026-11-09 | Codex / Claude Code / DeepSeek Harness 会话管理工具：浏览、搜索、按项目分组，查看历史会话与对话记录，清理会话记录、批量删除会话（删除会话为永久操作，不支持会话恢复）。本地会话查看器，会话数据留在本机，支持 Windows 与 Linux 桌面。 ｜ Local-first desktop session manager & viewer for Codex, Claude Code, DeepSeek Harness, OpenCode and more AI coding agents. Tauri + Rust. |
| 80 | AgentWorkforce/relayhistory | https://github.com/AgentWorkforce/relayhistory | ★15 | MIT | 否 | 2026-11-17 | Indexes every coding-agent session on your machine into one local, searchable database. |
| 81 | ay-bh/chat-history | https://github.com/ay-bh/chat-history | ★15 | MIT | 否 | 2026-11-12 | Search, inspect, and export Claude Code, Cursor & Codex history |
| 82 | cote-star/agent-chorus | https://github.com/cote-star/agent-chorus | ★15 | MIT | 否 | 2026-09-28 | Local-first CLI to read, compare, and hand off sessions across Claude Code, Codex, Gemini, and Cursor agents. Checkpoints, cross-agent messaging, zero npm deps. |
| 83 | kvsankar/agent-history | https://github.com/kvsankar/agent-history | ★15 | MIT | 否 | 2026-10-15 | Browse and export AI coding assistant history across Claude Code, Codex CLI, Gemini CLI, and Pi. |
| 84 | shivamstaq/ccview | https://github.com/shivamstaq/ccview | ★15 | MIT | 否 | 2026-04-04 | A terminal-based explorer and renderer for Claude Code conversation histories. Browse projects, view conversations with markdown rendering, inspect sub-agents, and export to HTML/Markdown/JSONL. |
| 85 | Ann-Diana/codex-project-chat-exporter | https://github.com/Ann-Diana/codex-project-chat-exporter | ★14 | MIT | 否 | 2026-10-02 | Bulk-export local Codex session history into portable, project-aware archives with Markdown, responsive HTML, editable Word documents, searchable PDFs, manifests and optional verified Raw JSONL snapshots. Local-first, read-only, with CLI and Visual Studio Code support. |
| 86 | FlorianBruniaux/cc-sessions | https://github.com/FlorianBruniaux/cc-sessions | ★14 | MIT | 否 | 2026-09-01 | Fast CLI to search, browse & analyze Claude Code session history |
| 87 | wellwelwel/sessioner | https://github.com/wellwelwel/sessioner | ★14 | MIT | 否 | 2026-06-12 | ✨ An interactive CLI to search, fork, merge, prune, trim, and manage Claude Code sessions from the terminal. |
| 88 | qiaolei81/copilot-session-viewer | https://github.com/qiaolei81/copilot-session-viewer | ★13 | MIT | 否 | 2026-08-31 | 🔍 Web UI for GitHub Copilot session logs - visualize events, analyze timelines, get AI insights |
| 89 | Seanium/koto | https://github.com/Seanium/koto | ★13 | MIT | 否 | 2026-10-19 | Move conversations between Claude Code, Codex, Cursor, and more. Keep your conversation history, branch into different agents, and compare what happens next. |
| 90 | thevibeworks/ccx | https://github.com/thevibeworks/ccx | ★13 | Apache-2.0 | 否 | 2026-10-17 | Session viewer for coding agents — browse, search, trace, and export Claude Code, Codex, and Grok conversations |
| 91 | dotneet/agent-session-view | https://github.com/dotneet/agent-session-view | ★12 | 無 | 否 | 2026-02-03 | A coding agent session viewer for browsing, viewing, and exporting conversation history from Claude Code and Codex CLI. Available as both a web interface and a terminal UI. |
| 92 | HeavyBunny19C/OpenSession | https://github.com/HeavyBunny19C/OpenSession | ★12 | MIT | 否 | 2026-03-22 | 开发者的 AI 编年史——把散落四处的对话日记，装订成册。支持 OpenCode、Claude Code、Codex CLI、Gemini CLI，智能路径检测，Agent/Skill/MCP/Tool 调用链路可视化。零依赖。 |
| 93 | iksnae/cursor-session | https://github.com/iksnae/cursor-session | ★12 | 無 | 否 | 2025-11-13 | A command-line tool to extract and export chat sessions from Cursor |
| 94 | wangjohn/agent-archive | https://github.com/wangjohn/agent-archive | ★12 | MIT | 否 | 2026-11-05 | Archive your Claude Code, Codex, and Cursor sessions to your own S3/R2 bucket and hand them off between agents or machines. |
| 95 | wilbeibi/herdr-catchup | https://github.com/wilbeibi/herdr-catchup | ★12 | MIT | 否 | 2026-09-28 | Cross-agent coding-session handoff for herdr: from a live pane, summarize, fork, or hand a Claude Code, Codex, Cursor, Cline, or OpenCode session to another agent. |
| 96 | xingkaixin/codesesh | https://github.com/xingkaixin/codesesh | ★12 | MIT | 否 | 2026-11-18 | One place to see every AI coding session you've ever had. |
| 97 | 2389-research/ccvault | https://github.com/2389-research/ccvault | ★11 | MIT | 否 | 2026-11-05 | Archive, search, and analyze Claude Code conversation history through a CLI, terminal UI, and MCP server. |
| 98 | Ryheff24/agentlog | https://github.com/Ryheff24/agentlog | ★11 | Apache-2.0 | 否 | 2026-11-11 | CLI that lets coding agents search and read other agents' session logs and transcripts (Claude Code, Codex, Copilot CLI). Read-only, no network, pure Go. |
| 99 | seastart/aicoder-session-viewer | https://github.com/seastart/aicoder-session-viewer | ★11 | 無 | 否 | 2026-08-18 | A unified desktop application for browsing session history / resume session/ export session / new conversation session for multiple AI coding assistants — **Claude Code**, **Codex**, **Gemini CLI**,  **Antigravity CLI**, and **OpenCode** — all in one place. 一个统一的桌面应用，用于多种 AI 编码助手的session对话历史 浏览 / 恢复 / 导出 / 新建 |
| 100 | bvolpato/omnisession | https://github.com/bvolpato/omnisession | ★10 | MIT | 否 | 2026-11-17 | Find any coding-agent session and continue it in any agent. Local-first CLI and TUI for Claude Code, Codex, OpenCode, Pi, Grok, Cursor, Antigravity, and Hermes. |
| 101 | Capetlevrai/resume-claude-codex-grok | https://github.com/Capetlevrai/resume-claude-codex-grok | ★10 | MIT | 否 | 2026-08-29 | Pick up in-progress work from one CLI agent inside another: Claude Code, Codex, Grok Build, OpenCode, oh-my-pi, Cursor. Inspired by Grok Build (xAI). |
| 102 | grapeot/ai_session_export | https://github.com/grapeot/ai_session_export | ★10 | 無 | 否 | 2026-11-15 | Export AI coding session transcripts from multiple tools into a unified Markdown archive. |
| 103 | johnlindquist/cursor-history | https://github.com/johnlindquist/cursor-history | ★10 | 無 | 否 | 2025-07-14 | （GitHub repo 未填寫簡介，依專案名稱／搜尋摘要判定為對應對話紀錄或交接工具） |
| 104 | karanb192/hindcast | https://github.com/karanb192/hindcast | ★10 | MIT | 否 | 2026-11-02 | Browse, search & replay every Claude Code session on your Mac. Local-first session viewer, timeline scrubber & cost tracker (ccusage alternative). |
| 105 | mantra-hq/mantra-releases | https://github.com/mantra-hq/mantra-releases | ★10 | 無 | 否 | 2026-08-28 | Time Travel for AI-Assisted Programming — Replay Claude Code, Cursor & Gemini CLI sessions as navigable timelines. Desktop app for macOS, Windows, Linux. |
| 106 | thevibeworks/cctrace | https://github.com/thevibeworks/cctrace | ★10 | MIT | 否 | 2026-10-05 | See exactly what your coding agent does on the wire. TLS-intercepting tracer for the Claude Code, Codex, Grok and Kimi CLIs: full first-party capture in a live web UI — reconstructed sessions, session replay, find-in-session, per-turn cost/cache/latency, and a cross-project dashboard of every run. |
| 107 | XZL-CODE/cc-codex-history-viewer | https://github.com/XZL-CODE/cc-codex-history-viewer | ★10 | MIT | 否 | 2026-10-20 | 本地 Claude Code 历史 Prompt 与对话可视化工具 · Local desktop viewer for Claude Code prompt & conversation history |
| 108 | agentic-utils/ccs | https://github.com/agentic-utils/ccs | ★9 | MIT | 否 | 2026-11-17 | Coding CLI Sessions: launch, watch, search and resume Claude Code and Codex sessions |
| 109 | bquenin/mnemonai | https://github.com/bquenin/mnemonai | ★9 | MIT | 否 | 2026-10-15 | Universal AI coding conversation history browser |
| 110 | mienfong/dsh-session-mgr | https://github.com/mienfong/dsh-session-mgr | ★9 | MIT | 否 | 2026-11-17 | Session manager for the DeepSeek Harness web UI: move, archive, restore, backup/export and import conversations across workspaces. Trilingual (English / 简体 / 繁體). |
| 111 | nihen/ah | https://github.com/nihen/ah | ★9 | MIT | 否 | 2026-10-16 | Agent History — search and browse AI coding agent sessions (Claude, Codex, Gemini, Copilot, Cursor) from a single CLI |
| 112 | nogataka/opencode-viewer | https://github.com/nogataka/opencode-viewer | ★9 | NOASSERTION | 否 | 2025-10-03 | （GitHub repo 未填寫簡介，依專案名稱／搜尋摘要判定為對應對話紀錄或交接工具） |
| 113 | pratikgajjar/recall | https://github.com/pratikgajjar/recall | ★9 | MIT | 否 | 2026-11-17 | Search your AI chat history across Cursor, Claude Code, Codex, and pi - fast, local, read-only. |
| 114 | sukamenev/baton | https://github.com/sukamenev/baton | ★9 | MIT | 否 | 2026-11-17 | Lossless session handoff across CLI coding agents (Claude, Codex, AGY, Pi, OpenCode, Kimi) and encrypted cross-machine session transfer in pure Go. |
| 115 | aa2246740/dsh-resume | https://github.com/aa2246740/dsh-resume | ★8 | Apache-2.0 | 否 | 2026-11-05 | Continue Codex, Claude Code, and Cursor work in DeepSeek Harness |
| 116 | alexei-led/resume-from | https://github.com/alexei-led/resume-from | ★8 | MIT | 否 | 2026-11-16 | Continue coding sessions across Pi, Claude Code, and Codex with a preview-first native handoff. |
| 117 | hxreborn/herdr-transcripts | https://github.com/hxreborn/herdr-transcripts | ★8 | GPL-3.0 | 否 | 2026-10-08 | Search your coding-agent sessions, past and live, by any word you remember, then jump to them or resume them |
| 118 | lef237/clauhist | https://github.com/lef237/clauhist | ★8 | MIT | 否 | 2026-10-31 | Browse Claude Code history across working directories and resume sessions |
| 119 | wanderer-yk/agent-chatlens | https://github.com/wanderer-yk/agent-chatlens | ★8 | MIT | 否 | 2026-05-19 | 🔍 A beautiful web viewer for AI agent session files. Browse Claude Code & OpenClaw conversations with chat-style UI, timeline visualization, and zero setup. |
| 120 | xiaoheilong3112/cursor-chat-exporter | https://github.com/xiaoheilong3112/cursor-chat-exporter | ★8 | MIT | 否 | 2024-11-23 | （GitHub repo 未填寫簡介，依專案名稱／搜尋摘要判定為對應對話紀錄或交接工具） |
| 121 | yuluod/AllSessions | https://github.com/yuluod/AllSessions | ★8 | Apache-2.0 | 否 | 2026-11-16 | A local-first desktop workspace for browsing, searching, and managing Codex, Claude Code, and Gemini CLI sessions. |
| 122 | Cedriccmh/cursor-trace-exporter | https://github.com/Cedriccmh/cursor-trace-exporter | ★7 | MIT | 否 | 2026-04-13 | Export your Cursor chat history (JSON format, more detailed than official) |
| 123 | GaoSSR/codex-export-skill | https://github.com/GaoSSR/codex-export-skill | ★7 | Apache-2.0 | 否 | 2026-04-24 | Codex Skill for exporting sessions as LLM-ready Markdown transcripts |
| 124 | mallikcheripally/session-steward | https://github.com/mallikcheripally/session-steward | ★7 | MIT | 否 | 2026-11-14 | Claude Code and Codex session manager. Browse sessions, back up, and safely delete old ones — from a local browser UI or terminal or MCP. |
| 125 | MeXenon/kiro-session-export | https://github.com/MeXenon/kiro-session-export | ★7 | Apache-2.0 | 否 | 2026-11-17 | Kiro session conversation chat export markdown interactive terminal tool. |
| 126 | MisterBrookT/codex2claude | https://github.com/MisterBrookT/codex2claude | ★7 | MIT | 否 | 2026-11-12 | Import a Codex session into Claude Code and resume into it — the reverse of Codex's import-from-Claude. A one-command Claude Code plugin. |
| 127 | genspark-ai/cc-conversation-archiver | https://github.com/genspark-ai/cc-conversation-archiver | ★6 | 無 | 否 | 2026-07-29 | Claude Code plugin: archive each conversation turn to a per-session markdown file in a git repo. Published from genspark monorepo. |
| 128 | GunitBindal/claude-transcript-exporter | https://github.com/GunitBindal/claude-transcript-exporter | ★6 | MIT | 否 | 2026-03-06 | Export, migrate, and archive Claude Code conversations. Perfect for migrating to GPT-5.4, Gemini 3.1 Pro, Codex, and other AI platforms. |
| 129 | harrychih/hiShare | https://github.com/harrychih/hiShare | ★6 | MIT | 否 | 2026-07-30 | Portable session handoffs between Claude Code and OpenAI Codex — index, export, import, and resume AI coding sessions across agents. |
| 130 | HarryHeYu/sessionFlow | https://github.com/HarryHeYu/sessionFlow | ★6 | MIT | 否 | 2026-11-17 | Local session indexing and cross-agent work continuity for AI coding assistants. One local index over Codex, Claude Code, ZCode, DSH, Grok, Cursor, Antigravity and Kiro — search, cross-agent timelines, WorkThread continuity, context handoff. No cloud, no telemetry. |
| 131 | hitmman55/claude-code-chat-viewer | https://github.com/hitmman55/claude-code-chat-viewer | ★6 | Unlicense | 否 | 2026-10-26 | Browse and search Claude Code conversation history offline: one HTML file that reads JSONL session transcripts from ~/.claude/projects |
| 132 | mirekholec/copilot-debugger | https://github.com/mirekholec/copilot-debugger | ★6 | MIT | 否 | 2026-08-19 | Local viewer for VS Code GitHub Copilot Chat sessions. Reads transcript & debug JSONL files locally and shows session metadata, turns, models, tools, agents, token usage and estimated AI costs. No data leaves your machine. |
| 133 | neuronalism/opencode-session-manager-cli | https://github.com/neuronalism/opencode-session-manager-cli | ★6 | 無 | 否 | 2026-11-11 | An CLI for managing opencode sessions. Allows exporting/importing sessions with sub-sessions (tree-like), and synchronization between projects and the local database. |
| 134 | nimishgj/agentswap | https://github.com/nimishgj/agentswap | ★6 | MIT | 否 | 2026-03-12 | Transfer conversation history between AI coding agents (Claude Code, Gemini CLI, Codex CLI) seamlessly |
| 135 | awithi-co/acdc | https://github.com/awithi-co/acdc | ★5 | MIT | 否 | 2026-11-08 | Cross-agent session handoff between Claude Code and Codex |
| 136 | changlehu/cursor-chat-export-to-markdown | https://github.com/changlehu/cursor-chat-export-to-markdown | ★5 | MIT | 否 | 2026-08-17 | Export Cursor Chat and Composer conversations to Markdown for portable AI coding history, archival, and reuse. |
| 137 | chaybits/ectype | https://github.com/chaybits/ectype | ★5 | GPL-3.0 | 否 | 2026-10-11 | Read, filter, redact and export the on-disk sessions of ten AI coding agents (Claude Code, Codex CLI, Gemini CLI, Antigravity, Copilot Chat, Cursor, Cline, Roo Code, Continue, Aider) and three chat apps (LM Studio, Open WebUI, SillyTavern), or copy one back into its agent and resume it. Command line and a local web UI. |
| 138 | Chendestiny/agent-session-sync | https://github.com/Chendestiny/agent-session-sync | ★5 | NOASSERTION | 否 | 2026-09-16 | 跨 Agent 会话同步工具包：codex/claude/dsh/opencode/cursor 等 19 家 AI agent 会话归一导入 dsh 续聊，反向写入 12 家；C 规范库中转、幂等增量防环、人在回路三道确认，附 Markdown 归档与本地 webui dashboard。Cross-agent session sync: import 19 AI agents sessions into dsh to resume chat; MD archive, human-in-the-loop. |
| 139 | cygmris/chatdex | https://github.com/cygmris/chatdex | ★5 | MIT | 否 | 2026-11-01 | 本地检索 Claude Code / Codex / Grok CLI 的全部历史会话：CJK 友好的 SQLite FTS5 全文检索 + 本地 LLM 摘要 + MCP 端点。只读、只监听 127.0.0.1。Search your entire Claude Code / Codex / Grok CLI session history locally. |
| 140 | DnaMes/lore | https://github.com/DnaMes/lore | ★5 | MIT | 否 | 2026-11-11 | Local-first AI session history browser for Claude Code, Cursor, Gemini CLI, OpenCode, Warp, Codex and more — web UI + MCP server |
| 141 | frknyldz/ai-session-bridge | https://github.com/frknyldz/ai-session-bridge | ★5 | MIT | 否 | 2026-01-26 | 🔗 MCP server and CLI for reading AI conversation history across VS Code Copilot, Cursor, and Rovodev. Enables AI agents to access cross-tool chat context within the same workspace. Built with Python, supports full-text search and automatic secret filtering. |
| 142 | pmarreck/chatscan | https://github.com/pmarreck/chatscan | ★5 | MIT | 否 | 2026-10-14 | Search Claude Code/Gemini/Codex conversation history with semantic + lexical search |
| 143 | 44-pixels/handover-mcp | https://github.com/44-pixels/handover-mcp | ★4 | MIT | 否 | 2026-08-05 | MCP server, CLI, and Agent Skills for shared, versioned context across Claude Code, Codex, Cursor, Gemini CLI, humans, and AI agents |
| 144 | adlternative/agent-historian | https://github.com/adlternative/agent-historian | ★4 | MIT | 否 | 2026-08-04 | Search and read past AI coding-agent conversation history (OpenCode, Claude Code, …) from the CLI. Pluggable per-agent sources, project/global scope, subagent-aware. |
| 145 | azzgo/pi-xfer | https://github.com/azzgo/pi-xfer | ★4 | MIT | 否 | 2026-11-12 | Cross-context handoff for pi coding agents |
| 146 | ddarmon/sesh | https://github.com/ddarmon/sesh | ★4 | MIT | 否 | 2026-10-29 | TUI and JSON CLI for browsing Claude Code, Codex, Cursor, Copilot, pi, Gemini CLI, and opencode sessions |
| 147 | fengerwoo/chat-history-skill | https://github.com/fengerwoo/chat-history-skill | ★4 | 無 | 否 | 2026-06-11 | 让 Claude Code / Codex 读取自己的历史聊天记录. A skill that lets Claude Code / Codex read their own past conversations |
| 148 | HeiGeAi/agent-history-rescue | https://github.com/HeiGeAi/agent-history-rescue | ★4 | MIT | 否 | 2026-10-08 | Recover Claude Code and Codex conversations that disappeared after switching accounts or providers, or rebuild them from an official data-export zip after a ban. Restores into the desktop app and writes an agent-readable archive. 换账号、换 provider 或被封号后找回 Claude Code 和 Codex 对话。 |
| 149 | hopp1395/cc-outline | https://github.com/hopp1395/cc-outline | ★4 | MIT | 否 | 2026-11-11 | Split-pane viewer for Claude Code in Windows Terminal and tmux: the session as rendered Markdown with subagents, live git diffs, plan-mode plans and a session browser |
| 150 | Mark-Libetter/ai-conversation-hub | https://github.com/Mark-Libetter/ai-conversation-hub | ★4 | MIT | 否 | 2026-08-21 | Local-first hub for AI coding agent conversations: aggregate chat history from Codex CLI, Claude Code, Hermes, ZCode, QoderWork & WorkBuddy into one searchable timeline. Cross-agent boolean search, daily review, projects, tags, Markdown export. Pure Python stdlib, 127.0.0.1 only. ｜ 本地 AI 对话中心：跨编程助手对话聚合、搜索、回顾与归档 |
| 151 | nicomen/saisons | https://github.com/nicomen/saisons | ★4 | Artistic-2.0 | 否 | 2026-11-17 | Terminal UI for browsing and resuming AI coding agent sessions (Claude Code, Codex, Gemini CLI, Aider, opencode) |
| 152 | pma1999/session-bridge | https://github.com/pma1999/session-bridge | ★4 | MIT | 否 | 2026-11-09 | Local session exchange and opt-in synchronization for Claude Code, OpenCode and Codex. |
| 153 | rcwalter24/opencode-export | https://github.com/rcwalter24/opencode-export | ★4 | 無 | 否 | 2026-09-18 | The tool of exporting and sharing open code chat history |
| 154 | roccodaffuso/sift | https://github.com/roccodaffuso/sift | ★4 | MIT | 否 | 2026-08-03 | Local-first CLI to index and search your Claude Code, Codex, and Cursor chat history from one place. 100% offline, read-only. |
| 155 | SmallHorseBrother/ai-cli-chat-search | https://github.com/SmallHorseBrother/ai-cli-chat-search | ★4 | MIT | 否 | 2026-05-17 | Unified chat history search across Codex / Claude Code / Kimi Code CLI tools — CLI + Tkinter GUI, zero dependencies. |
| 156 | bwndlct/dsh-session-export | https://github.com/bwndlct/dsh-session-export | ★3 | MIT | 否 | 2026-08-14 | Export DeepSeek Harness (DSH) sessions to portable Markdown and JSON — dsh plugin |
| 157 | fabiocampolim-design/claude-session-publisher | https://github.com/fabiocampolim-design/claude-session-publisher | ★3 | Apache-2.0 | 否 | 2026-09-19 | Turn a Claude Code session into a self-contained HTML/text/Markdown/LaTeX/PDF document — with a fidelity report proving nothing was silently dropped. |
| 158 | gpolaert/trace | https://github.com/gpolaert/trace | ★3 | 無 | 否 | 2026-05-29 | Local viewer for Claude Code and Codex session transcripts. |
| 159 | jiantao88/ai-history | https://github.com/jiantao88/ai-history | ★3 | MIT | 否 | 2026-06-23 | Search and reuse Claude Code, Codex CLI, and Cursor chat history as AI context. |
| 160 | jlreyes/agent-history-skills | https://github.com/jlreyes/agent-history-skills | ★3 | MIT | 否 | 2026-10-30 | Agent skills for exploring locally stored AI coding agent history: Claude Code, Codex CLI, and Cursor |
| 161 | Kirushanthan03/claude-code-chat-history-viewer | https://github.com/Kirushanthan03/claude-code-chat-history-viewer | ★3 | MIT | 否 | 2026-01-27 | A beautiful, human-readable viewer for your Claude Code  conversation history.  Claude Code stores your chat sessions in JSONL format at `~/.claude/` - which is not exactly easy to read. This tool converts those conversations into beautifully styled HTML pages that you can browse in your web browser. |
| 162 | livyn-inc/cursor-chat-history-exporter | https://github.com/livyn-inc/cursor-chat-history-exporter | ★3 | MIT | 否 | 2025-09-08 | （GitHub repo 未填寫簡介，依專案名稱／搜尋摘要判定為對應對話紀錄或交接工具） |
| 163 | tanghong123/claude-replay | https://github.com/tanghong123/claude-replay | ★3 | MIT | 否 | 2026-11-18 | agent-replay & agent-monitor: read-only replay, live monitoring and search for coding-agent sessions (Claude Code, Codex, Qoder). Rust TUI + local web UI. |
| 164 | yanzhi0922/codex-session-migrator | https://github.com/yanzhi0922/codex-session-migrator | ★3 | MIT | 否 | 2026-04-03 | A safe local-first Codex session migration toolkit with web UI, backups, restore, and health checks. |
| 165 | alexxxtat/claude-transcript-viewer | https://github.com/alexxxtat/claude-transcript-viewer | ★2 | MIT | 否 | 2026-08-04 | Turn a Claude Code session into a single HTML file you can actually read. One file, no dependencies, no network. |
| 166 | Augl-l/dsh-session-search | https://github.com/Augl-l/dsh-session-search | ★2 | MIT | 否 | 2026-10-28 | Cross-session message search for DSH desktop: local SQLite FTS5 index, compact turn results, jump and highlight. |
| 167 | avikalpa/codex-session-tui | https://github.com/avikalpa/codex-session-tui | ★2 | Apache-2.0 | 否 | 2026-08-13 | Search, move, copy, fork, and repair Codex sessions from any terminal or SSH session. |
| 168 | chrichuang218/agent-handoff | https://github.com/chrichuang218/agent-handoff | ★2 | MIT | 否 | 2026-11-02 | Session handoffs for Codex or Claude Code. Continue from saved handoff files, or use session mentions and IDs when supported by your host. |
| 169 | codesweep-ai/tracer | https://github.com/codesweep-ai/tracer | ★2 | Apache-2.0 | 否 | 2026-11-13 | Turn AI coding-CLI session transcripts into one self-contained, browsable HTML trace viewer. |
| 170 | demirciAhmet/ocsearch | https://github.com/demirciAhmet/ocsearch | ★2 | MIT | 否 | 2026-11-11 | Read-only CLI for searching local OpenCode session history (no index) |
| 171 | dwqs/cursor-trace | https://github.com/dwqs/cursor-trace | ★2 | MIT | 否 | 2026-05-19 | Browse and visualize Cursor AI agent session transcripts with thinking detection, tool call inspection, and HTML export |
| 172 | forensicdave/claude-export-viewer | https://github.com/forensicdave/claude-export-viewer | ★2 | MIT | 否 | 2026-06-05 | A zero-dependency two-pane terminal UI for browsing Claude Code session transcripts |
| 173 | helo060228/dsh-chat-search | https://github.com/helo060228/dsh-chat-search | ★2 | MIT | 否 | 2026-11-10 | DSH chat search plugin: global cross-session & in-chat search with context navigation |
| 174 | kwiscion/cursor-chat-recovery | https://github.com/kwiscion/cursor-chat-recovery | ★2 | MIT | 否 | 2026-06-13 | Terminal UI to recover, browse, move, and export Cursor AI chat history - fix chats that vanished after moving or renaming a project |
| 175 | markwroberts0/cursor-chat-recovery | https://github.com/markwroberts0/cursor-chat-recovery | ★2 | MIT | 否 | 2026-01-05 | （GitHub repo 未填寫簡介，依專案名稱／搜尋摘要判定為對應對話紀錄或交接工具） |
| 176 | omdsh-dev/dsh-shuttle | https://github.com/omdsh-dev/dsh-shuttle | ★2 | MIT | 否 | 2026-08-14 | 在 DeepSeek Harness 与 Codex、Claude Code、Pi、Reasonix、OpenCode 之间双向迁移对话记录，支持 CLI 与 Web UI |
| 177 | phpmypython/claude-viewer | https://github.com/phpmypython/claude-viewer | ★2 | MIT | 否 | 2025-06-27 | Browse and view your Claude conversation transcripts with a modern web interface |
| 178 | POSTTTT/agent-cli-session | https://github.com/POSTTTT/agent-cli-session | ★2 | MIT | 否 | 2026-09-16 | A local web app for browsing, searching, and managing the session logs your coding agents leave behind for Claude Code, Codex, Gemini CLI, opencode, cursor-agent, grok and Muse Code. Runs entirely on your machine. |
| 179 | TomSchmidtDev/vscode-ai-chat-exporter | https://github.com/TomSchmidtDev/vscode-ai-chat-exporter | ★2 | NOASSERTION | 否 | 2026-06-11 | An Visual Studio Code plugin that lets you export your GitHub Copilot chat history to Markdown or styled HTML — directly from your IDE. |
| 180 | ZelinZhou-THU/opencode-export | https://github.com/ZelinZhou-THU/opencode-export | ★2 | MIT | 否 | 2026-06-30 | Export opencode AI coding sessions to beautiful HTML + JSON archives. CLI + MCP server with secret redaction. |
| 181 | akoserwal/export-conversation-skill | https://github.com/akoserwal/export-conversation-skill | ★1 | MIT | 否 | 2026-04-09 | Export Conversation - Claude Code Skill |
| 182 | anasabbasdev/cursor-chat-bulk-export | https://github.com/anasabbasdev/cursor-chat-bulk-export | ★1 | MIT | 否 | 2026-05-25 | VS code and Cursor AI extension for Export Cursor chat/composer/agent conversations to Markdown files bulk |
| 183 | aploe/claude-handoff-skill | https://github.com/aploe/claude-handoff-skill | ★1 | MIT | 否 | 2026-10-22 | Agent-agnostic session handoff for Claude Code. Pick up work across sessions and across LLM agents (Codex, Cursor, Gemini, GPT). |
| 184 | BruceXcluding/session-recap | https://github.com/BruceXcluding/session-recap | ★1 | MIT | 否 | 2026-11-08 | Claude Code plugin: recap any session's intent, key decisions, changes, open threads and where to resume, in a side pane. Built for long, many-session projects. |
| 185 | davidqyc/session-preserve | https://github.com/davidqyc/session-preserve | ★1 | Apache-2.0 | 否 | 2026-10-06 | Local-first preservation and integrity verification for persisted coding-agent sessions from Codex, Claude Code, Kimi Code, and ZCode. |
| 186 | deveduar/vscode-copilot-export-cli | https://github.com/deveduar/vscode-copilot-export-cli | ★1 | MIT | 否 | 2026-11-17 | CLI to export GitHub Copilot chat history stored locally by VS Code. Read-only, dependency-free, Markdown/JSON/JSONL output. |
| 187 | didvc/web-to-cc | https://github.com/didvc/web-to-cc | ★1 | MIT | 否 | 2026-10-21 | Resume the web chat in Claude Code. The JSONL session converter & importer. Continue from your idea. |
| 188 | escoffier-labs/stationtrail | https://github.com/escoffier-labs/stationtrail | ★1 | MIT | 是 | 2026-07-02 | StationTrail exports local station and agent-session logs to portable miseledger.adapter.v1 JSONL. Local-only, no network calls. |
| 189 | jitrak-dev/cursor-export | https://github.com/jitrak-dev/cursor-export | ★1 | MIT | 否 | 2026-05-11 | Auto-export your Cursor AI chat history as Markdown files into your project repo |
| 190 | joe-broadhead/opencode-history | https://github.com/joe-broadhead/opencode-history | ★1 | MIT | 否 | 2026-11-17 | Unofficial OpenCode plugin: search, read and recall your past OpenCode sessions |
| 191 | ostiums/leftoff | https://github.com/ostiums/leftoff | ★1 | MIT | 否 | 2026-11-06 | Pick up your ChatGPT Work and Codex chats where you left off, in Claude Code |
| 192 | pandaxbacon/github-copilot-chat-exporter | https://github.com/pandaxbacon/github-copilot-chat-exporter | ★1 | MIT | 否 | 2025-12-08 | Export GitHub Copilot Chat (copilot.share) conversations to Markdown & PDF. |
| 193 | PrashnaLabs/agent-race | https://github.com/PrashnaLabs/agent-race | ★1 | MIT | 否 | 2026-11-15 | Replay Claude Code and Codex sessions on a 3D map of your repo, solo or side by side. |
| 194 | Sertelegger/claude-sesh-mover | https://github.com/Sertelegger/claude-sesh-mover | ★1 | MIT | 否 | 2026-10-21 | Claude Code Plugin for session import, export and migration between profiles, containers, and machines |
| 195 | softagram/cc-search | https://github.com/softagram/cc-search | ★1 | MIT | 否 | 2026-10-05 | Fast full-text search for Claude Code conversation history |
| 196 | SomeNoneAI/find-my-session | https://github.com/SomeNoneAI/find-my-session | ★1 | MIT | 否 | 2026-11-17 | Read-only, cross-harness agent-session finder and handoff tool |
| 197 | T-Gojo/ContextBridgeAi | https://github.com/T-Gojo/ContextBridgeAi | ★1 | MIT | 否 | 2026-05-27 | Local AI prompt extractor & conversation history browser for Cursor, Claude Code, Codex CLI, Rovo Dev, Kiro, Windsurf, Antigravity, VS Code Copilot, Cline, Continue, Zed, Qodo Gen & Gemini CLI. Hybrid BM25+semantic search. Privacy-first, macOS. |
| 198 | the-ensemble/ai-chat-exporters | https://github.com/the-ensemble/ai-chat-exporters | ★1 | MIT | 否 | 2026-05-07 | Export local AI chat history from Claude Code, VS Code Copilot, and Cursor into clean per-project Markdown archives. Idempotent; handles Cursor's split per-workspace + global SQLite stores and Lexical richText. |
| 199 | xxxily/convx | https://github.com/xxxily/convx | ★1 | MIT | 否 | 2026-04-18 | Git-commit your AI conversations before they disappear. |
| 200 | Yaagik/session-recall | https://github.com/Yaagik/session-recall | ★1 | MIT | 否 | 2026-10-02 | Never lose your AI coding history when you switch laptops. A Claude Code plugin and Agent Skill that summarizes a project's sessions from Claude Code, Codex CLI, Gemini CLI, opencode, Aider, Cline and Roo into Markdown in your repo. You pick the sessions and approve the token cost first. |
| 201 | zhaoxuejie/dsh-plugin-session-export | https://github.com/zhaoxuejie/dsh-plugin-session-export | ★1 | MIT | 否 | 2026-09-10 | DeepSeek Harness 会话黑匣子插件：全量旁路采集会话事件，一键导出美化 Markdown / HTML 复盘报告，内置 Web 统计面板 |
| 202 | zhyunran/dsh-session-bundle | https://github.com/zhyunran/dsh-session-bundle | ★1 | MIT | 否 | 2026-11-15 | DSH plugin: one /bundle command exports a readable transcript, raw log, attachments and the files a session produced into a ZIP on disk. 一条命令导出可读对话、原始日志、附件与本会话产出文件。 |
| 203 | zyx3721/session-exporter-skills | https://github.com/zyx3721/session-exporter-skills | ★1 | MIT | 否 | 2026-09-29 | Codex、ZCode、DSH 三端会话存档技能：按标题或ID定位会话、导出成 Markdown、脱敏归档进 Obsidian，全程只读原会话，落盘自动提交而推送等待确认。 |
| 204 | 0smboy/agent-migration-cursor-plugin | https://github.com/0smboy/agent-migration-cursor-plugin | ★0 | MIT | 否 | 2026-07-30 | Cursor importer API proposal and safe agent-history migration plugin scaffold |
| 205 | arghhhhh/claude-conversation-transfer | https://github.com/arghhhhh/claude-conversation-transfer | ★0 | MIT | 否 | 2026-08-05 | Export/import a Claude Code project's conversation history across machines and OSes |
| 206 | Camji55/agent-handoff | https://github.com/Camji55/agent-handoff | ★0 | MIT | 否 | 2026-08-19 | Move a coding session between AI agents with two slash commands |
| 207 | chrzamz/sessio | https://github.com/chrzamz/sessio | ★0 | Apache-2.0 | 否 | 2026-05-14 | Unified search & browse for your Claude Code and Codex CLI conversations. Local-first, SQLite FTS5, dual-licensed MIT/Apache-2.0. |
| 208 | dennyferra/paseo-baton | https://github.com/dennyferra/paseo-baton | ★0 | Apache-2.0 | 否 | 2026-11-08 | Paseo plugin that writes a handoff document when an agent goes idle, then lets you continue the task in a fresh agent |
| 209 | HildebrandYu/dsh-session-chains | https://github.com/HildebrandYu/dsh-session-chains | ★0 | MIT | 否 | 2026-11-16 | DSH 交接鏈面板：把互相交接的對話聚成一條鏈（卡片／編號／面板／HUD／門檻提醒／自動交接） |
| 210 | itswl/agent-session-query | https://github.com/itswl/agent-session-query | ★0 | MIT | 否 | 2026-11-18 | asq — the session history of every agent CLI on your machine (Claude Code, Codex, Gemini CLI, OpenCode, Grok, Antigravity, Pi, DeepSeek Harness, Hermes, OpenClaw) as one record you can search, read, hand over and measure. One static binary: a command line, a local page, an HTTP API and an MCP server. It only reads. |
| 211 | jdinkla/ai-history | https://github.com/jdinkla/ai-history | ★0 | Apache-2.0 | 否 | 2026-11-05 | Extract, browse, and reflect on your Claude Code and Codex session history (stdlib-only Python) |
| 212 | kittimzhe/dsh-session-recall | https://github.com/kittimzhe/dsh-session-recall | ★0 | MIT | 否 | 2026-11-05 | Cross-session full-text recall for DeepSeek Harness: the model-facing recall tool searches past session transcripts via ctx.sessionQuery, with a persistent FTS index |
| 213 | KyawZaw-cmd/Cursor-Multiple-Project-local-chat-History-Find-Export | https://github.com/KyawZaw-cmd/Cursor-Multiple-Project-local-chat-History-Find-Export | ★0 | 無 | 否 | 2025-07-29 | （GitHub repo 未填寫簡介，依專案名稱／搜尋摘要判定為對應對話紀錄或交接工具） |
| 214 | mapleleo-hub/chat-share-reader | https://github.com/mapleleo-hub/chat-share-reader | ★0 | MIT | 否 | 2026-11-15 | Export AI chat conversations to markdown: 10 share-link sites (ChatGPT, Claude, Gemini, Grok, Perplexity, DeepSeek, Kimi, Qwen) plus 15 local agent session stores (Claude Code, Codex, Cursor, opencode). Node only, redacted by default. |
| 215 | Mert-coderoid/agf | https://github.com/Mert-coderoid/agf | ★0 | MIT | 否 | 2026-04-29 | AI Agent Session Finder — TUI to find, resume and manage sessions across Claude Code, Codex, Gemini, Kiro, OpenCode, Cursor, pi |
| 216 | ravikanchikare/cc-session-viewer | https://github.com/ravikanchikare/cc-session-viewer | ★0 | 無 | 否 | 2026-05-12 | Browse, compare, and copy Claude Code session logs locally with checkpointed transcripts, tool-call groups, token counts, and side-by-side comparisons.  npx cc-session-viewer |
| 217 | rymalia/agent-session-manager | https://github.com/rymalia/agent-session-manager | ★0 | MIT | 否 | 2026-10-19 | Browse, search, and resume your local AI coding CLI sessions — Claude Code, Codex, Grok, opencode, Cursor, Gemini, Copilot, Goose, Droid — in one place. Local-first, nothing leaves your machine. |
| 218 | samanvaya5/session-query | https://github.com/samanvaya5/session-query | ★0 | MIT | 否 | 2026-05-05 | Search your AI coding history. Agent skill for querying OpenCode, Claude Code, and Gemini CLI sessions. |
| 219 | The-Zombie0/Codex-Claude-History-Viewer | https://github.com/The-Zombie0/Codex-Claude-History-Viewer | ★0 | MIT | 否 | 2026-04-01 | Local-first, dependency-free web viewer for Codex CLI and Claude Code session logs. |
| 220 | williamfzc/ferry | https://github.com/williamfzc/ferry | ★0 | Apache-2.0 | 否 | 2026-11-07 | Convert AI coding-agent session histories between Claude Code, Codex CLI, Gemini CLI, OpenCode, and more. Go library with byte-exact source capture and lossless round trips. |

## 查不到的管道與限制
- **awesome**：`sweep.py channels` 內建 `awesome` 管道僅傳回 awesome 清單索引（如 `hesreallyhim/awesome-claude-code`），非單一工具，需搭配 `related` 或人工閱讀抽取。
- **MCP Registry**：官方 Registry API 僅支援單字子字串比對（例如只會送出 `coding`、`session`、`chat`、`cursor`、`gemini`、`copilot`），長尾複合關鍵字雜訊極高，多數回傳與對話檢視／交接無關之 MCP。
- **Product Hunt**：無官方開放搜尋 API，依指示以網頁搜尋 `site:producthunt.com` 完成涵蓋，惟無對應 GitHub repo 之純閉源產品無法以 `sweep.py verify` 取得開源星數與授權。
- **GitHub 404**：`WSL043/dsh-chat-manager`（第 2 組收錄）於最終 `sweep.py verify` 時回傳 `gh: Not Found (HTTP 404)`。

## 拿不準的名字（未寫入帳本，共 29 個）
以下工具雖提及對話歷史、重播或交接，但因主要功能踩在**長期記憶／知識庫、多 agent 終端控制／編排、帳號切換或流程錄製**邊界，依從嚴原則不列入帳本，集中附於此供參考：
- **第 1 組**：`vshulcz/deja-vu`（★1,608，兼做本機 session 搜尋／交接與 `Shared local memory` 及 LongMemEval-S 基準）、`@eagle4302/dsh-session-relay`（跨 session 訊息中繼，介於即時傳訊與交接）、`@virtualorz/recap`（轉為月度開發日誌與 AI 摘要，偏報表生成）。
- **第 2 組**：`bilalpeera86/claude-session-flow`、`kunwar-shah/claudex`、`cvelasquez/agent-workbench`（★13，多 CLI 頁籤整合介面兼跨 CLI 交接）、`VARVE-ai/adit-core`、`tjboudreaux/rosetta`、`centauri-ai/coslash`、`herdbell`、`asymptote beacon handoff`、`Conan`、`Bench for Claude Code`、`Termi Protocol`。
- **第 3 組**：`tombelieber/claude-view`（★127，即時監控儀表板兼搜尋）、`StayCurious-Xuan/wayfinder`（★92）、`p32929/ccheckpoints`（★35，偏檢查點還原）、`vitaliyhayda/claude-transplant`（★54，偏帳號側邊欄紀錄遷移）、`Mahiler1909/claudepath`（★25，偏修正目錄搬遷後的路徑指向）。
- **第 4 組**：`Frankie-Xu/threadport`、`qingsongcui/ContextCore`、`yuangyong/handoff-memory`、`WeirdSky924/agent-handoff-skill`、`mem0ai/openmemory`（多含長期記憶／跨工具記憶層）。
- **第 5 組**：`SakuraByteCore/codexmate`（★356，Codex 綜合伴侶含設定/切換/歷史）、`vega-llc/cowork-migrate`、`Agensi`、`tretuttle/ai-stuff`、`xduwt/claude-desktop-history`（偏 Claude Desktop 網頁桌面版）、`sterramind/opencode-session-transfer`、`erickrus/opencode_migrate`。
- **第 6 組**：`TaewoooPark/Agent-Blackbox`（replay 兼 context 評分並回寫 `AGENTS.md`）、`yx0716/clawd-insights`（replay 兼知識摘要與桌面寵物）、`Buildlog`（錄製為可重播 workflow recipe）。
- **第 7 組**：`Kanary Agents`（`kanary.to/agents`，跨專案 session 瀏覽兼 agent 編排與監控工作台）。
- **第 8 組**：`shayne-snap/WayLog`（★77，匯出 AI 對話為 Git 知識庫，主打「知識庫」定位）。
- **第 9 組**：`lyfuci/ai-terminal-manager`（★20，統一 session 歷史外主要是持續性 tmux 終端機管理器）、`ShrimpScript/lectern`（★2，多 agent 共享大腦與任務路由編排）、`reyanshgupta/ditto-cli`（★0，多帳號切換器附帶保留歷史）、`saadnvd1/hydra`（★21，限流自動切換包裝器附帶脈絡轉移）、`ccswitch.io`（API provider 切換器附帶 session 管理擴充）。
- **第 10 組（驗證 1）**：`hetpatel-11/agent-hop`（★36，多 agent 終端執行環境附帶切換與搜尋）、`abraxas914/VESTI`（★363，泛用 AI 網頁對話記憶與知識中台）。
- **第 11 組（驗證 2）**：`CodeAgentSwarm`（主要為多 agent 編排協調平台，另附唯讀檢視 Cline 本機 session 歷史）。
