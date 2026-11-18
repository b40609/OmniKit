# 飽和式調研報告：跨 Coding Agent 對話紀錄搜尋、交接、壓縮救回與共用記憶工具

- **開始時間**：2026-11-18T09:53+08:00
- **結束時間**：2026-11-18T10:31+08:00
- **帳本檔案**：`T1-ledger.json`（總計 **538** 個不重複名字：460 個 GitHub repo + 79 筆非 GitHub 網址／套件／產品名，依 `sweep.py` 去重規則合計 538 個不重複名字）
- **驗證日期（`sweep.py verify`）**：`2026-11-18`

## 一、納入與排除標準
- **納入**：會讀取 coding agent（Claude Code、Codex、Cursor、Gemini CLI、OpenCode、Pi、DeepSeek Harness 等）的對話紀錄（`.jsonl`／SQLite／rollout）或工作狀態，並提供（1）對話紀錄搜尋／檢視、（2）跨對話／跨 agent 交接或遷移、（3）壓縮（compaction）後救回脈絡、（4）跨 agent 共用記憶，其中至少一項的工具（開源 repo、產品、skill、plugin、MCP、CLI 皆算）。
- **排除**：只給單一非程式聊天 app 使用的一般記憶、純向量資料庫底層、教學文與學術論文（如 `fudan-generative-vision/Remory`）、純 awesome 清單（如 `hesreallyhim/awesome-claude-code`）、與對話紀錄／記憶／交接無關之終端多工器（如 `manaflow-ai/cmux`）或提示詞輸出壓縮代理（如 `headroomlabs-ai/headroom`）。

## 二、主調研流程（第 1–12 組）、挑詞理由與 `status --min-stars 1000` 輸出

> **主停止點摘要**：本題目於 **第 12 組（`chat log handoff`）** 觸發 **`已經 12 組還沒停（上限 12 組）`** 停止提醒（`over_budget`）。截至第 12 組共收錄 485 個不重複名字，連續無新名字組數為 0、連續無 `★1,000+` 新名字組數亦為 0，兩種「可以停」門檻均未於 12 組內收斂；依試用規範記下主停止點後，續查第 13–14 組作為驗證組。

### 第 1 組：`coding agent 對話紀錄 交接`
- **挑詞理由**：起手組（中文原話）：依題目核心中文關鍵字起手，並搭配中文網頁搜尋涵蓋「對話紀錄、搜尋、交接、壓縮、記憶」。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-zh`
- **`status --min-stars 1000` 輸出**：
```text
總共 36 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
整次調研還沒查過：英文網頁搜尋、Product Hunt（網頁搜尋 site:producthunt.com）、主要專案的 fork 與 README 提到的競品（related）
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
```

### 第 2 組：`coding agent session handoff`
- **挑詞理由**：起手組（英文同義說法）：題目英文核心同義詞；同時於本組補齊 `producthunt`（`site:producthunt.com`）與主要專案（`vshulcz/deja-vu`、`Dicklesworthstone/coding_agent_session_search`、`yigitkonur/cli-continues`）之 `related` 抽檢。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`, `producthunt`, `related`
- **`status --min-stars 1000` 輸出**：
```text
總共 114 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
```

### 第 3 組：`session history search`
- **挑詞理由**：起手組（不含 agent／AI 的一般說法）：避免漏掉以通用 session history 命名或跨出 AI 關鍵字圈的工具。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
總共 160 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
```

### 第 4 組：`context compaction recovery`
- **挑詞理由**：從結果擴展：從第 1、2 組結果挑出高頻新詞 compaction recovery / context compaction，涵蓋 `/compact` 與自動壓縮後的脈絡救回工具。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
總共 199 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
```

### 第 5 組：`cross-agent memory`
- **挑詞理由**：從結果擴展：從前幾組結果挑出高頻詞 cross-agent memory 與 topic `persistent-memory`、`multi-agent-memory`、`memory-plugin`，涵蓋跨 coding agent 共用長期記憶工具。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
總共 273 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
```

### 第 6 組：`session continuity`
- **挑詞理由**：從結果擴展：從第 4、5 組結果中的 session continuity 擴展，涵蓋 session relay、checkpoint 與延續性工具。
- **實查管道**：`github-topic`, `github-keyword`, `npm`, `hn`, `web-en`, `awesome`, `skills-sh`, `mcp-registry`, `exa`
- **`status --min-stars 1000` 輸出**：
```text
總共 309 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
```

### 第 7 組：`session checkpoint`
- **挑詞理由**：從結果擴展：從第 6 組及前面結果挑出高頻詞 session checkpoint，涵蓋檢查點存檔、回退與紀錄匯出工具。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
總共 334 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
第 7 組「session checkpoint」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ellmos-ai/session-checkpoint, SiriLee/dsh-rewind, PerryLink/dsh-checkpoint-rewind, asiagenawi/claude-powernap, mqz0211/Claude-Checkpoint-Manager-CCM, skyhua0224/continuity-plane, sinzin91/claude-checkpoint, entireio/skills, basicmachines-co/basic-memory, maivand-rahmani/opencode-session-port, daniel-munoz/claude-checkpoint-mcp, mohshomis/ckpt, tstockham96/engram, TheJoin95/mnemosyne, docs.syncropel.com, Jyo238/checkpoint, chen-001/claudecode_checkpoints, andrepimenta/claude-code-chat, mariochasco78557/claude-code-toolkit, dstrupl/vardoger, nicknisi/sessions, dosu-ai/decant, simonw/claude-code-transcripts, tim-hua-01/cc_transcript_viewer, 0smboy/agent-migration-cursor-plugin
  ★1000 以上的新名字：basicmachines-co/basic-memory, andrepimenta/claude-code-chat, simonw/claude-code-transcripts
```

### 第 8 組：`coding agent transcript`
- **挑詞理由**：從結果擴展：從第 7 組結果中的 transcript 擴展，涵蓋直接讀取與檢視 coding agent 對話紀錄檔案（JSONL／rollout）的工具。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
總共 358 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
第 7 組「session checkpoint」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ellmos-ai/session-checkpoint, SiriLee/dsh-rewind, PerryLink/dsh-checkpoint-rewind, asiagenawi/claude-powernap, mqz0211/Claude-Checkpoint-Manager-CCM, skyhua0224/continuity-plane, sinzin91/claude-checkpoint, entireio/skills, basicmachines-co/basic-memory, maivand-rahmani/opencode-session-port, daniel-munoz/claude-checkpoint-mcp, mohshomis/ckpt, tstockham96/engram, TheJoin95/mnemosyne, docs.syncropel.com, Jyo238/checkpoint, chen-001/claudecode_checkpoints, andrepimenta/claude-code-chat, mariochasco78557/claude-code-toolkit, dstrupl/vardoger, nicknisi/sessions, dosu-ai/decant, simonw/claude-code-transcripts, tim-hua-01/cc_transcript_viewer, 0smboy/agent-migration-cursor-plugin
  ★1000 以上的新名字：basicmachines-co/basic-memory, andrepimenta/claude-code-chat, simonw/claude-code-transcripts
第 8 組「coding agent transcript」：24 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：Nwflower/dsh-chat-import, jo-inc/pi-reflect, Sigillion-AI/sigillion, henba1/scrubjay, asheshgoplani/agent-deck, senlindesign/coding-wrapped, codexview/codexview, capacitor.kurrent.io, B33BMO/vaportrail, siegerts/agent-transcript, tmustier/pi-agent-transcripts, ianzepp/cassio, docs.otty.sh, ahundt/ai-session-search, Stormix/transcripts-mcp, vulcanshen/clerk, dhruv-anand-aintech/agent-session-viewer, dotneet/agent-session-view, wesm/archived-agent-session-viewer, lililib/ai-session-search, vladar107/claudescope, WiseeCarrot/claude-transcript-viewer, braincompany/sessiongrep, entireio/cli
  ★1000 以上的新名字：asheshgoplani/agent-deck, entireio/cli
```

### 第 9 組：`session recall`
- **挑詞理由**：從結果擴展：從前幾組工具名稱與描述反覆出現的 session recall / conversation recall 擴展，並補查 `conversation-recall` topic。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
總共 392 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 1 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
第 7 組「session checkpoint」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ellmos-ai/session-checkpoint, SiriLee/dsh-rewind, PerryLink/dsh-checkpoint-rewind, asiagenawi/claude-powernap, mqz0211/Claude-Checkpoint-Manager-CCM, skyhua0224/continuity-plane, sinzin91/claude-checkpoint, entireio/skills, basicmachines-co/basic-memory, maivand-rahmani/opencode-session-port, daniel-munoz/claude-checkpoint-mcp, mohshomis/ckpt, tstockham96/engram, TheJoin95/mnemosyne, docs.syncropel.com, Jyo238/checkpoint, chen-001/claudecode_checkpoints, andrepimenta/claude-code-chat, mariochasco78557/claude-code-toolkit, dstrupl/vardoger, nicknisi/sessions, dosu-ai/decant, simonw/claude-code-transcripts, tim-hua-01/cc_transcript_viewer, 0smboy/agent-migration-cursor-plugin
  ★1000 以上的新名字：basicmachines-co/basic-memory, andrepimenta/claude-code-chat, simonw/claude-code-transcripts
第 8 組「coding agent transcript」：24 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：Nwflower/dsh-chat-import, jo-inc/pi-reflect, Sigillion-AI/sigillion, henba1/scrubjay, asheshgoplani/agent-deck, senlindesign/coding-wrapped, codexview/codexview, capacitor.kurrent.io, B33BMO/vaportrail, siegerts/agent-transcript, tmustier/pi-agent-transcripts, ianzepp/cassio, docs.otty.sh, ahundt/ai-session-search, Stormix/transcripts-mcp, vulcanshen/clerk, dhruv-anand-aintech/agent-session-viewer, dotneet/agent-session-view, wesm/archived-agent-session-viewer, lililib/ai-session-search, vladar107/claudescope, WiseeCarrot/claude-transcript-viewer, braincompany/sessiongrep, entireio/cli
  ★1000 以上的新名字：asheshgoplani/agent-deck, entireio/cli
第 9 組「session recall」：34 個名字，新的 34 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：zhaohualiuyuejun/dsh-semantic-recall, pyq1992/codex-session-recall, itsmay21/agent-recall, raiyanyahya/recall, cwinvestments/memstack, dezgit2025/auto-memory, joseairosa/recall, hjertefolger/cortex, dcostenco/prism-coder, babarot/claude-recall, brucee/tokensaver, polinnizhong/dsh-session-workbench, qinling-melon-farmers/dsh-memoir, kittimzhe/dsh-session-recall, rmk40/opencode-session-recall, edwinhao/awareness, davegoldblatt/total-recall, recallmcp.com, recallplugin.dev, engram-ai.dev, buildingopen/session-recall, Davidyooo/session-recall, verve-sh/session-recall, samzong/Recall, pratikgajjar/recall, bluekornchips/gandalf, gitmem-dev/gitmem, purmemo-ai/purmemo-mcp, Eversmile12/sharedcontext, just-every/plugin-recall …
```

### 第 10 組：`session resume`
- **挑詞理由**：從結果擴展：從第 8、9 組及跨工具續聊描述挑出 session resume，並補查 `context-transfer` 與 `native-sessions` topic。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
總共 440 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
第 7 組「session checkpoint」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ellmos-ai/session-checkpoint, SiriLee/dsh-rewind, PerryLink/dsh-checkpoint-rewind, asiagenawi/claude-powernap, mqz0211/Claude-Checkpoint-Manager-CCM, skyhua0224/continuity-plane, sinzin91/claude-checkpoint, entireio/skills, basicmachines-co/basic-memory, maivand-rahmani/opencode-session-port, daniel-munoz/claude-checkpoint-mcp, mohshomis/ckpt, tstockham96/engram, TheJoin95/mnemosyne, docs.syncropel.com, Jyo238/checkpoint, chen-001/claudecode_checkpoints, andrepimenta/claude-code-chat, mariochasco78557/claude-code-toolkit, dstrupl/vardoger, nicknisi/sessions, dosu-ai/decant, simonw/claude-code-transcripts, tim-hua-01/cc_transcript_viewer, 0smboy/agent-migration-cursor-plugin
  ★1000 以上的新名字：basicmachines-co/basic-memory, andrepimenta/claude-code-chat, simonw/claude-code-transcripts
第 8 組「coding agent transcript」：24 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：Nwflower/dsh-chat-import, jo-inc/pi-reflect, Sigillion-AI/sigillion, henba1/scrubjay, asheshgoplani/agent-deck, senlindesign/coding-wrapped, codexview/codexview, capacitor.kurrent.io, B33BMO/vaportrail, siegerts/agent-transcript, tmustier/pi-agent-transcripts, ianzepp/cassio, docs.otty.sh, ahundt/ai-session-search, Stormix/transcripts-mcp, vulcanshen/clerk, dhruv-anand-aintech/agent-session-viewer, dotneet/agent-session-view, wesm/archived-agent-session-viewer, lililib/ai-session-search, vladar107/claudescope, WiseeCarrot/claude-transcript-viewer, braincompany/sessiongrep, entireio/cli
  ★1000 以上的新名字：asheshgoplani/agent-deck, entireio/cli
第 9 組「session recall」：34 個名字，新的 34 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：zhaohualiuyuejun/dsh-semantic-recall, pyq1992/codex-session-recall, itsmay21/agent-recall, raiyanyahya/recall, cwinvestments/memstack, dezgit2025/auto-memory, joseairosa/recall, hjertefolger/cortex, dcostenco/prism-coder, babarot/claude-recall, brucee/tokensaver, polinnizhong/dsh-session-workbench, qinling-melon-farmers/dsh-memoir, kittimzhe/dsh-session-recall, rmk40/opencode-session-recall, edwinhao/awareness, davegoldblatt/total-recall, recallmcp.com, recallplugin.dev, engram-ai.dev, buildingopen/session-recall, Davidyooo/session-recall, verve-sh/session-recall, samzong/Recall, pratikgajjar/recall, bluekornchips/gandalf, gitmem-dev/gitmem, purmemo-ai/purmemo-mcp, Eversmile12/sharedcontext, just-every/plugin-recall …
第 10 組「session resume」：55 個名字，新的 48 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：sergeyramas/session-handoff-skill, amal-david/claude-to-codex, swarno1996/handoff-pill, 1beenlee/universal-context-handoff, gj9159a/codex-restore-chat-context, ojackson08/agenthandoff, hyderhusainarastu/cross-session-agent-handoff-prompt-template, giuliastro/harness-remote, tk1777-sy/-work-journal-skill, yazcaleb/rses, luluanes/native-windows-codex-claude-keepalive, sachind6/pi-resume-harness, ymonster/cc_jsonl_fix, supersistence/warp-claude-resume, eason-22/dsh-autorestart, ivbala1/limit-resume, han719307-dotcom/task-continuity, 2solarmax/pane-resume, m1ku831/codex-continue, roekdnd/dsh-restart-suite, catbusfleet-org/catbus, lpoee/opencac, didvc/web-to-cc, kc1t/alethe-agents, jerrywu001/cc-sessions-viewer, dwsy/pi-session-manager, red-noblue/codex_relay, angristan/fast-resume, 0xsero/parcels, dicklesworthstone/cross_agent_session_resumer …
  ★1000 以上的新名字：kc1t/alethe-agents, siteboon/claudecodeui, cytostack/openwolf, openai/codex-plugin-cc
```

### 第 11 組：`context transfer`
- **挑詞理由**：從結果擴展：從第 10 組高頻出現之 context transfer 與 cross-agent handoff 概念擴展，並補查 `session-handoff` 與 `cross-agent` topic。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
總共 470 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
第 7 組「session checkpoint」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ellmos-ai/session-checkpoint, SiriLee/dsh-rewind, PerryLink/dsh-checkpoint-rewind, asiagenawi/claude-powernap, mqz0211/Claude-Checkpoint-Manager-CCM, skyhua0224/continuity-plane, sinzin91/claude-checkpoint, entireio/skills, basicmachines-co/basic-memory, maivand-rahmani/opencode-session-port, daniel-munoz/claude-checkpoint-mcp, mohshomis/ckpt, tstockham96/engram, TheJoin95/mnemosyne, docs.syncropel.com, Jyo238/checkpoint, chen-001/claudecode_checkpoints, andrepimenta/claude-code-chat, mariochasco78557/claude-code-toolkit, dstrupl/vardoger, nicknisi/sessions, dosu-ai/decant, simonw/claude-code-transcripts, tim-hua-01/cc_transcript_viewer, 0smboy/agent-migration-cursor-plugin
  ★1000 以上的新名字：basicmachines-co/basic-memory, andrepimenta/claude-code-chat, simonw/claude-code-transcripts
第 8 組「coding agent transcript」：24 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：Nwflower/dsh-chat-import, jo-inc/pi-reflect, Sigillion-AI/sigillion, henba1/scrubjay, asheshgoplani/agent-deck, senlindesign/coding-wrapped, codexview/codexview, capacitor.kurrent.io, B33BMO/vaportrail, siegerts/agent-transcript, tmustier/pi-agent-transcripts, ianzepp/cassio, docs.otty.sh, ahundt/ai-session-search, Stormix/transcripts-mcp, vulcanshen/clerk, dhruv-anand-aintech/agent-session-viewer, dotneet/agent-session-view, wesm/archived-agent-session-viewer, lililib/ai-session-search, vladar107/claudescope, WiseeCarrot/claude-transcript-viewer, braincompany/sessiongrep, entireio/cli
  ★1000 以上的新名字：asheshgoplani/agent-deck, entireio/cli
第 9 組「session recall」：34 個名字，新的 34 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：zhaohualiuyuejun/dsh-semantic-recall, pyq1992/codex-session-recall, itsmay21/agent-recall, raiyanyahya/recall, cwinvestments/memstack, dezgit2025/auto-memory, joseairosa/recall, hjertefolger/cortex, dcostenco/prism-coder, babarot/claude-recall, brucee/tokensaver, polinnizhong/dsh-session-workbench, qinling-melon-farmers/dsh-memoir, kittimzhe/dsh-session-recall, rmk40/opencode-session-recall, edwinhao/awareness, davegoldblatt/total-recall, recallmcp.com, recallplugin.dev, engram-ai.dev, buildingopen/session-recall, Davidyooo/session-recall, verve-sh/session-recall, samzong/Recall, pratikgajjar/recall, bluekornchips/gandalf, gitmem-dev/gitmem, purmemo-ai/purmemo-mcp, Eversmile12/sharedcontext, just-every/plugin-recall …
第 10 組「session resume」：55 個名字，新的 48 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：sergeyramas/session-handoff-skill, amal-david/claude-to-codex, swarno1996/handoff-pill, 1beenlee/universal-context-handoff, gj9159a/codex-restore-chat-context, ojackson08/agenthandoff, hyderhusainarastu/cross-session-agent-handoff-prompt-template, giuliastro/harness-remote, tk1777-sy/-work-journal-skill, yazcaleb/rses, luluanes/native-windows-codex-claude-keepalive, sachind6/pi-resume-harness, ymonster/cc_jsonl_fix, supersistence/warp-claude-resume, eason-22/dsh-autorestart, ivbala1/limit-resume, han719307-dotcom/task-continuity, 2solarmax/pane-resume, m1ku831/codex-continue, roekdnd/dsh-restart-suite, catbusfleet-org/catbus, lpoee/opencac, didvc/web-to-cc, kc1t/alethe-agents, jerrywu001/cc-sessions-viewer, dwsy/pi-session-manager, red-noblue/codex_relay, angristan/fast-resume, 0xsero/parcels, dicklesworthstone/cross_agent_session_resumer …
  ★1000 以上的新名字：kc1t/alethe-agents, siteboon/claudecodeui, cytostack/openwolf, openai/codex-plugin-cc
第 11 組「context transfer」：35 個名字，新的 30 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：hetpatel-11/agent-hop, lijma/fcontext, rewfa-ceo/amp, harrychih/hishare, wink305/contextpocket, elecnix/pi-claude-memory, rememora/rememora, dhilipsiva/lucy, Vinyl-Davyl/hermes, softaworks/agent-toolkit, dongshuyan/compass-skills, sahilraut22/handoff, shivala-08/context-shifter, platman02/ctx-bridge, dullnote.com, hiperyon.com, context-transfer.vercel.app, context-transfer-protocol/ctp-spec, Kaseban/baton, FacuVCanale/session-bridge, MisterBrookT/codex2claude, authsec-ai/authsec-bridge, thepushkarp/handoff, who96/claude-code-context-handoff, aproto9787/codex-bridge, SeemSeam/claude_codex_bridge, ptreezh/stigmergy-CLI-Multi-Agents, relai.fyi, agentproto.sh, usespaces.dev
  ★1000 以上的新名字：softaworks/agent-toolkit, SeemSeam/claude_codex_bridge
```

### 第 12 組：`chat log handoff`
- **挑詞理由**：不含 agent／AI 的一般說法擴展：補足不以 coding agent 命名的通用對話紀錄交接與轉換工具。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **`status --min-stars 1000` 輸出**：
```text
已經 12 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續
總共 485 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
第 7 組「session checkpoint」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ellmos-ai/session-checkpoint, SiriLee/dsh-rewind, PerryLink/dsh-checkpoint-rewind, asiagenawi/claude-powernap, mqz0211/Claude-Checkpoint-Manager-CCM, skyhua0224/continuity-plane, sinzin91/claude-checkpoint, entireio/skills, basicmachines-co/basic-memory, maivand-rahmani/opencode-session-port, daniel-munoz/claude-checkpoint-mcp, mohshomis/ckpt, tstockham96/engram, TheJoin95/mnemosyne, docs.syncropel.com, Jyo238/checkpoint, chen-001/claudecode_checkpoints, andrepimenta/claude-code-chat, mariochasco78557/claude-code-toolkit, dstrupl/vardoger, nicknisi/sessions, dosu-ai/decant, simonw/claude-code-transcripts, tim-hua-01/cc_transcript_viewer, 0smboy/agent-migration-cursor-plugin
  ★1000 以上的新名字：basicmachines-co/basic-memory, andrepimenta/claude-code-chat, simonw/claude-code-transcripts
第 8 組「coding agent transcript」：24 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：Nwflower/dsh-chat-import, jo-inc/pi-reflect, Sigillion-AI/sigillion, henba1/scrubjay, asheshgoplani/agent-deck, senlindesign/coding-wrapped, codexview/codexview, capacitor.kurrent.io, B33BMO/vaportrail, siegerts/agent-transcript, tmustier/pi-agent-transcripts, ianzepp/cassio, docs.otty.sh, ahundt/ai-session-search, Stormix/transcripts-mcp, vulcanshen/clerk, dhruv-anand-aintech/agent-session-viewer, dotneet/agent-session-view, wesm/archived-agent-session-viewer, lililib/ai-session-search, vladar107/claudescope, WiseeCarrot/claude-transcript-viewer, braincompany/sessiongrep, entireio/cli
  ★1000 以上的新名字：asheshgoplani/agent-deck, entireio/cli
第 9 組「session recall」：34 個名字，新的 34 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：zhaohualiuyuejun/dsh-semantic-recall, pyq1992/codex-session-recall, itsmay21/agent-recall, raiyanyahya/recall, cwinvestments/memstack, dezgit2025/auto-memory, joseairosa/recall, hjertefolger/cortex, dcostenco/prism-coder, babarot/claude-recall, brucee/tokensaver, polinnizhong/dsh-session-workbench, qinling-melon-farmers/dsh-memoir, kittimzhe/dsh-session-recall, rmk40/opencode-session-recall, edwinhao/awareness, davegoldblatt/total-recall, recallmcp.com, recallplugin.dev, engram-ai.dev, buildingopen/session-recall, Davidyooo/session-recall, verve-sh/session-recall, samzong/Recall, pratikgajjar/recall, bluekornchips/gandalf, gitmem-dev/gitmem, purmemo-ai/purmemo-mcp, Eversmile12/sharedcontext, just-every/plugin-recall …
第 10 組「session resume」：55 個名字，新的 48 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：sergeyramas/session-handoff-skill, amal-david/claude-to-codex, swarno1996/handoff-pill, 1beenlee/universal-context-handoff, gj9159a/codex-restore-chat-context, ojackson08/agenthandoff, hyderhusainarastu/cross-session-agent-handoff-prompt-template, giuliastro/harness-remote, tk1777-sy/-work-journal-skill, yazcaleb/rses, luluanes/native-windows-codex-claude-keepalive, sachind6/pi-resume-harness, ymonster/cc_jsonl_fix, supersistence/warp-claude-resume, eason-22/dsh-autorestart, ivbala1/limit-resume, han719307-dotcom/task-continuity, 2solarmax/pane-resume, m1ku831/codex-continue, roekdnd/dsh-restart-suite, catbusfleet-org/catbus, lpoee/opencac, didvc/web-to-cc, kc1t/alethe-agents, jerrywu001/cc-sessions-viewer, dwsy/pi-session-manager, red-noblue/codex_relay, angristan/fast-resume, 0xsero/parcels, dicklesworthstone/cross_agent_session_resumer …
  ★1000 以上的新名字：kc1t/alethe-agents, siteboon/claudecodeui, cytostack/openwolf, openai/codex-plugin-cc
第 11 組「context transfer」：35 個名字，新的 30 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：hetpatel-11/agent-hop, lijma/fcontext, rewfa-ceo/amp, harrychih/hishare, wink305/contextpocket, elecnix/pi-claude-memory, rememora/rememora, dhilipsiva/lucy, Vinyl-Davyl/hermes, softaworks/agent-toolkit, dongshuyan/compass-skills, sahilraut22/handoff, shivala-08/context-shifter, platman02/ctx-bridge, dullnote.com, hiperyon.com, context-transfer.vercel.app, context-transfer-protocol/ctp-spec, Kaseban/baton, FacuVCanale/session-bridge, MisterBrookT/codex2claude, authsec-ai/authsec-bridge, thepushkarp/handoff, who96/claude-code-context-handoff, aproto9787/codex-bridge, SeemSeam/claude_codex_bridge, ptreezh/stigmergy-CLI-Multi-Agents, relai.fyi, agentproto.sh, usespaces.dev
  ★1000 以上的新名字：softaworks/agent-toolkit, SeemSeam/claude_codex_bridge
第 12 組「chat log handoff」：21 個名字，新的 15 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：dongsheng123132/task-passport, wang5333/ai-handoff-summary-builder, voyfur/llm-wiki-session-memory, mattpocock/skills, shaswat28/handoff-skill, dennyferra/paseo-baton, lippinc/catnap, crosshead.sh, shafiqimtiaz/ctx-handoff, abassaf/baton, ylexliao/chatbridge, vasilispapg/claude-handoff, davo20019/relevo, shuntaka9576/chathist, jigyasudham/veto
  ★1000 以上的新名字：mattpocock/skills
```

## 三、主停止點後驗證（第 13–14 組，分開記錄）

抵達主停止點（第 12 組觸發 `已經 12 組還沒停`）後，依測試設計再多查 2 組不同切角的新關鍵字（同樣走完整 8 支程式管道與網頁搜尋，並寫入同一本帳本 `T1-ledger.json`）：

### 驗證組 1（帳本第 13 組）：`跨 agent 記憶 交接`
- **挑詞理由**：【驗證組 1】補查中文跨 agent 共享記憶與交接說法，驗證中文生態是否仍有遺漏的 `★1,000+` 專案。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-zh`
- **本組該批名字數**：23 個；**新增不重複名字數**：**18 個**
- **有無新的 ★1,000 以上名字**：**1 個**（`NevaMind-AI/memU`）
- **`status --min-stars 1000` 輸出**：
```text
已經 13 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續
總共 503 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 0 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
第 7 組「session checkpoint」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ellmos-ai/session-checkpoint, SiriLee/dsh-rewind, PerryLink/dsh-checkpoint-rewind, asiagenawi/claude-powernap, mqz0211/Claude-Checkpoint-Manager-CCM, skyhua0224/continuity-plane, sinzin91/claude-checkpoint, entireio/skills, basicmachines-co/basic-memory, maivand-rahmani/opencode-session-port, daniel-munoz/claude-checkpoint-mcp, mohshomis/ckpt, tstockham96/engram, TheJoin95/mnemosyne, docs.syncropel.com, Jyo238/checkpoint, chen-001/claudecode_checkpoints, andrepimenta/claude-code-chat, mariochasco78557/claude-code-toolkit, dstrupl/vardoger, nicknisi/sessions, dosu-ai/decant, simonw/claude-code-transcripts, tim-hua-01/cc_transcript_viewer, 0smboy/agent-migration-cursor-plugin
  ★1000 以上的新名字：basicmachines-co/basic-memory, andrepimenta/claude-code-chat, simonw/claude-code-transcripts
第 8 組「coding agent transcript」：24 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：Nwflower/dsh-chat-import, jo-inc/pi-reflect, Sigillion-AI/sigillion, henba1/scrubjay, asheshgoplani/agent-deck, senlindesign/coding-wrapped, codexview/codexview, capacitor.kurrent.io, B33BMO/vaportrail, siegerts/agent-transcript, tmustier/pi-agent-transcripts, ianzepp/cassio, docs.otty.sh, ahundt/ai-session-search, Stormix/transcripts-mcp, vulcanshen/clerk, dhruv-anand-aintech/agent-session-viewer, dotneet/agent-session-view, wesm/archived-agent-session-viewer, lililib/ai-session-search, vladar107/claudescope, WiseeCarrot/claude-transcript-viewer, braincompany/sessiongrep, entireio/cli
  ★1000 以上的新名字：asheshgoplani/agent-deck, entireio/cli
第 9 組「session recall」：34 個名字，新的 34 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：zhaohualiuyuejun/dsh-semantic-recall, pyq1992/codex-session-recall, itsmay21/agent-recall, raiyanyahya/recall, cwinvestments/memstack, dezgit2025/auto-memory, joseairosa/recall, hjertefolger/cortex, dcostenco/prism-coder, babarot/claude-recall, brucee/tokensaver, polinnizhong/dsh-session-workbench, qinling-melon-farmers/dsh-memoir, kittimzhe/dsh-session-recall, rmk40/opencode-session-recall, edwinhao/awareness, davegoldblatt/total-recall, recallmcp.com, recallplugin.dev, engram-ai.dev, buildingopen/session-recall, Davidyooo/session-recall, verve-sh/session-recall, samzong/Recall, pratikgajjar/recall, bluekornchips/gandalf, gitmem-dev/gitmem, purmemo-ai/purmemo-mcp, Eversmile12/sharedcontext, just-every/plugin-recall …
第 10 組「session resume」：55 個名字，新的 48 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：sergeyramas/session-handoff-skill, amal-david/claude-to-codex, swarno1996/handoff-pill, 1beenlee/universal-context-handoff, gj9159a/codex-restore-chat-context, ojackson08/agenthandoff, hyderhusainarastu/cross-session-agent-handoff-prompt-template, giuliastro/harness-remote, tk1777-sy/-work-journal-skill, yazcaleb/rses, luluanes/native-windows-codex-claude-keepalive, sachind6/pi-resume-harness, ymonster/cc_jsonl_fix, supersistence/warp-claude-resume, eason-22/dsh-autorestart, ivbala1/limit-resume, han719307-dotcom/task-continuity, 2solarmax/pane-resume, m1ku831/codex-continue, roekdnd/dsh-restart-suite, catbusfleet-org/catbus, lpoee/opencac, didvc/web-to-cc, kc1t/alethe-agents, jerrywu001/cc-sessions-viewer, dwsy/pi-session-manager, red-noblue/codex_relay, angristan/fast-resume, 0xsero/parcels, dicklesworthstone/cross_agent_session_resumer …
  ★1000 以上的新名字：kc1t/alethe-agents, siteboon/claudecodeui, cytostack/openwolf, openai/codex-plugin-cc
第 11 組「context transfer」：35 個名字，新的 30 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：hetpatel-11/agent-hop, lijma/fcontext, rewfa-ceo/amp, harrychih/hishare, wink305/contextpocket, elecnix/pi-claude-memory, rememora/rememora, dhilipsiva/lucy, Vinyl-Davyl/hermes, softaworks/agent-toolkit, dongshuyan/compass-skills, sahilraut22/handoff, shivala-08/context-shifter, platman02/ctx-bridge, dullnote.com, hiperyon.com, context-transfer.vercel.app, context-transfer-protocol/ctp-spec, Kaseban/baton, FacuVCanale/session-bridge, MisterBrookT/codex2claude, authsec-ai/authsec-bridge, thepushkarp/handoff, who96/claude-code-context-handoff, aproto9787/codex-bridge, SeemSeam/claude_codex_bridge, ptreezh/stigmergy-CLI-Multi-Agents, relai.fyi, agentproto.sh, usespaces.dev
  ★1000 以上的新名字：softaworks/agent-toolkit, SeemSeam/claude_codex_bridge
第 12 組「chat log handoff」：21 個名字，新的 15 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：dongsheng123132/task-passport, wang5333/ai-handoff-summary-builder, voyfur/llm-wiki-session-memory, mattpocock/skills, shaswat28/handoff-skill, dennyferra/paseo-baton, lippinc/catnap, crosshead.sh, shafiqimtiaz/ctx-handoff, abassaf/baton, ylexliao/chatbridge, vasilispapg/claude-handoff, davo20019/relevo, shuntaka9576/chathist, jigyasudham/veto
  ★1000 以上的新名字：mattpocock/skills
第 13 組「跨 agent 記憶 交接」：23 個名字，新的 18 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：draiagent/ai-to-agent-memory, kwyeh-cl/agent-memory, askdkc/kiokuko-dsh, frc9427liu-tech/memrot, yunfeng008/codebaton, ihow1/ihow-memory-standard, dunova/contextgo, jordanwei1/jiaojie-skill, NevaMind-AI/memU, timyyf/agent-skills, memoryplugin.com, samemind, totalmemory.dev, klypix.com, snipara.com, datamcp.app, unabyss.com, harkstudio.io
  ★1000 以上的新名字：NevaMind-AI/memU
```

### 驗證組 2（帳本第 14 組）：`session migration`
- **挑詞理由**：【驗證組 2】從「跨工具匯入／遷移 session 紀錄」角度補充搜尋，驗證英文生態在到達 12 組上限後是否仍有新增 `★1,000+` 專案。
- **實查管道**：`github-topic`, `github-keyword`, `awesome`, `skills-sh`, `npm`, `mcp-registry`, `hn`, `exa`, `web-en`
- **本組該批名字數**：39 個；**新增不重複名字數**：**35 個**
- **有無新的 ★1,000 以上名字**：**0 個**（無）
- **`status --min-stars 1000` 輸出**：
```text
已經 14 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續
總共 538 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 1 組沒有新的（要 3 組）：還不能停
第 1 組「coding agent 對話紀錄 交接」：36 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：Adamchanadam/agent-handoff-kit, HildebrandYu/dsh-session-chains, @virtualorz/recap, @eagle4302/dsh-session-relay, ecologyxy/ChatMem, douxy1994/AI-Memory, ccassist, xmemo, thedotmack/claude-mem, rohitg00/agentmemory, AVIDS2/memorix, ChinaCarlos/coding-memory-mcp, vshulcz/deja-vu, AgentWorkforce/relayhistory, aytzey/showagent, ay-bh/chat-history, a2cr/a2cr, polyxmedia/mnemos, 44-pixels/handover-mcp, Vvkmnn/claude-historian-mcp, Vvkmnn/claude-praetorian-mcp, mantra-hq/mantra-releases, pma1999/session-bridge, danyuchn/history-find, bledden/claude-recall-plugin, raine/claude-history, astral303/rearview, jhlee0409/claude-code-history-viewer, artpar/past-conversations-mcp, stackmemoryai/stackmemory …
  ★1000 以上的新名字：thedotmack/claude-mem, rohitg00/agentmemory, vshulcz/deja-vu, jhlee0409/claude-code-history-viewer
第 2 組「coding agent session handoff」：81 個名字，新的 78 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, producthunt, related
  新：Frankie-Xu/threadport, qingsongcui/ContextCore, wilbeibi/catchup, remvisual/claude-handoff, obrenoalvim/zero-drift, staticroostermedia-arch/engram, remembra-ai/remembra, cote-star/agent-chorus, AxmeAI/axme-code, wilbeibi/herdr-catchup, Capetlevrai/resume-claude-codex-grok, yuangyong/handoff-memory, vunm-io/passdown, cantona/herdr-revive, aa2246740/dsh-resume, alexei-led/resume-from, Enderfga/claw-orchestrator, blader/baton, talayash/agentrium, zebbern/agent-collab, kartikkabadi/pi-handoff, sanirudh17/herdr-agent-handoff, ccompactor/ccompactor, handyutils/sctxx, IlyaGorsky/memory-toolkit, z2z23n0/agent-capsule, live9369/session-handoff-skill, sukamenev/baton, hacktivist123/agent-session-resume, alphaelements/handoff-mcp …
  ★1000 以上的新名字：yigitkonur/cli-continues, akitaonrails/ai-memory, OthmanAdi/planning-with-files, Dicklesworthstone/coding_agent_session_search, specstoryai/getspecstory, fujibee/agmsg, Gentleman-Programming/engram
第 3 組「session history search」：47 個名字，新的 46 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jazzyalex/agent-sessions, Pratiyush/llm-wiki, tombelieber/claude-view, StayCurious-Xuan/wayfinder, vitaliyhayda/claude-transplant, gautamgpt1/agent-session-browser, p32929/ccheckpoints, taxueseek/session-digger, noluyorAbi/claude-code-recap, samfoy/pi-session-search, Mahiler1909/claudepath, lovstudio/Ataru, nameforjt-afk/session-knowledge, samfoy/pi-total-recall, HizTam/codex-history-viewer, sinzin91/search-sessions, josephyaduvanshi/claude-history-manager, WSL043/dsh-chat-manager, affaan-m/ECC, PluckSlugSorrow/dsh-session-history-search, JarvusInnovations/agent-recall-axi, beowulf11/pi-scroll, 420247jake/session-forge, BruceXcluding/session-recap, Ryrahul/session-relay, SomeNoneAI/find-my-session, dimitrihilverda/claude-session-relay, mallikcheripally/session-steward, base76-research-lab/cognos-session-memory, tad-hq/universal-session-viewer …
  ★1000 以上的新名字：affaan-m/ECC, ctxrs/ctx
第 4 組「context compaction recovery」：42 個名字，新的 39 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：big0lives/codex-task-pointer, Elevatormusic/hermes-warm-compaction, wrg32786/aigent-os, transcendr/jevpact, andrewbakercloudscale/claude-burst, wangcangshu/codex-desktop-thread-rescue, overbit/fast-jev-compaction-opencode, lennartschoch/opencode-cache-compact, falling-ts/dsh-force-compact, john-walks-slow/dsh-clear-mind, Awenforever/CoDeepSeedeX, codexstar69/pi-lcm, FlineDev/Recall, turvodnik/pf-handoff, kenimo49/compact-ops, mvara-ai/precompact-hook, d0ub1e-d/codebuddy-context-recovery-patch, dxta/claude-dynamic-context-pruning, jlcolton/context-recovery-protocol, midodevelop/compact-recovery, kleosr/cursor-clijev-compaction, machinesbefree/context-bootstrap, jdrhyne/agent-skills, mksglu/context-mode, nijaru/pi-compactor, rochecompaan/pi-context-paging, snailium/dsh-command-context-trim, amcbstudio/mem, hadronmemory.com, trinity-framework-core …
  ★1000 以上的新名字：mksglu/context-mode, WorldFlowAI/everything-claude-code
第 5 組「cross-agent memory」：74 個名字，新的 74 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, CodeAbra/iai-personal-memory-engine, okf-memory/okf-agent-memory, kitfunso/hippo-memory, 0xK3vin/MegaMemory, mnemon-dev/mnemon, memvid/claude-brain, Lyellr88/marm-memory, smaramwbc/statewave-multi-agent-memory, rxthlessbeats/agent-cowork-memory, NeoLi00/memX, joshuaswarren/remnic, hyperb1iss/sibyl, synapselayer/synapse-layer, VladimirGutuev/cross-agent-memory, rainypilgrimage/persistent-memory, caura-ai/caura-long-run-fleet, caura-ai/caura-cross-fleet-gov, kuznecov-anatoliy/opencode-memories, 123caiji/dsh-memory-toolkit, ly028716/dsh-memory-plugin, zzy-fxxxexxxyxxx/dsh-openclaw-memory, tarolcraze/dsh-day-memory, rogers-f/dsh-zcode-memory, jnocode/recall-memory-hermes, lucioliu/relic, pnmcguire480/cairntir …
  ★1000 以上的新名字：breferrari/obsidian-mind, MemMachine/MemMachine, ClaudioDrews/memory-os, omdsh-dev/dsh-mnemon, chunxiaoxx/nautilus-compass, MemPalace/mempalace, pchalasani/claude-code-tools
第 6 組「session continuity」：36 個名字，新的 36 個；管道：github-topic, github-keyword, npm, hn, web-en, awesome, skills-sh, mcp-registry, exa
  新：alexgreensh/token-optimizer, Storybloq/storybloq, pqant/claude-continuity, neverinfamous/memory-journal-mcp, jungjaehoon-lifegamez/MAMA, AliceLJY/recallnest, hotalexnet/agent-checkpoint, archid21/whatsnext, sara-star-quant/presence, jovesun-lab/whetstone, anasnafees1802/continuum, Riley-Coyote/mnemos-mcp, 0xDarkMatter/claude-mods, sshahzaiib/agy-bridge, oldskultxo/aictx, agentsea/flashbacker, Haustorium12/continuity-v2, waterside0219/session-forge, lukasz-fedor/claude-memory-template, jthack/dm-other-claudes, keggan-std/Engram, ymck-x/dsh-session-continuity, @ai2070/memex, vikcena01/ai-continuity-plugin, parcadei/Continuous-Claude-v3, EwanJasper/SessionRelay, Tempuskg/session-control, djannot/code-session-memory, Vopaaz/Agent-Session-Relay, stefan-jansen/coding-agent-toolkit …
  ★1000 以上的新名字：alexgreensh/token-optimizer, parcadei/Continuous-Claude-v3
第 7 組「session checkpoint」：25 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：ellmos-ai/session-checkpoint, SiriLee/dsh-rewind, PerryLink/dsh-checkpoint-rewind, asiagenawi/claude-powernap, mqz0211/Claude-Checkpoint-Manager-CCM, skyhua0224/continuity-plane, sinzin91/claude-checkpoint, entireio/skills, basicmachines-co/basic-memory, maivand-rahmani/opencode-session-port, daniel-munoz/claude-checkpoint-mcp, mohshomis/ckpt, tstockham96/engram, TheJoin95/mnemosyne, docs.syncropel.com, Jyo238/checkpoint, chen-001/claudecode_checkpoints, andrepimenta/claude-code-chat, mariochasco78557/claude-code-toolkit, dstrupl/vardoger, nicknisi/sessions, dosu-ai/decant, simonw/claude-code-transcripts, tim-hua-01/cc_transcript_viewer, 0smboy/agent-migration-cursor-plugin
  ★1000 以上的新名字：basicmachines-co/basic-memory, andrepimenta/claude-code-chat, simonw/claude-code-transcripts
第 8 組「coding agent transcript」：24 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：Nwflower/dsh-chat-import, jo-inc/pi-reflect, Sigillion-AI/sigillion, henba1/scrubjay, asheshgoplani/agent-deck, senlindesign/coding-wrapped, codexview/codexview, capacitor.kurrent.io, B33BMO/vaportrail, siegerts/agent-transcript, tmustier/pi-agent-transcripts, ianzepp/cassio, docs.otty.sh, ahundt/ai-session-search, Stormix/transcripts-mcp, vulcanshen/clerk, dhruv-anand-aintech/agent-session-viewer, dotneet/agent-session-view, wesm/archived-agent-session-viewer, lililib/ai-session-search, vladar107/claudescope, WiseeCarrot/claude-transcript-viewer, braincompany/sessiongrep, entireio/cli
  ★1000 以上的新名字：asheshgoplani/agent-deck, entireio/cli
第 9 組「session recall」：34 個名字，新的 34 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：zhaohualiuyuejun/dsh-semantic-recall, pyq1992/codex-session-recall, itsmay21/agent-recall, raiyanyahya/recall, cwinvestments/memstack, dezgit2025/auto-memory, joseairosa/recall, hjertefolger/cortex, dcostenco/prism-coder, babarot/claude-recall, brucee/tokensaver, polinnizhong/dsh-session-workbench, qinling-melon-farmers/dsh-memoir, kittimzhe/dsh-session-recall, rmk40/opencode-session-recall, edwinhao/awareness, davegoldblatt/total-recall, recallmcp.com, recallplugin.dev, engram-ai.dev, buildingopen/session-recall, Davidyooo/session-recall, verve-sh/session-recall, samzong/Recall, pratikgajjar/recall, bluekornchips/gandalf, gitmem-dev/gitmem, purmemo-ai/purmemo-mcp, Eversmile12/sharedcontext, just-every/plugin-recall …
第 10 組「session resume」：55 個名字，新的 48 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：sergeyramas/session-handoff-skill, amal-david/claude-to-codex, swarno1996/handoff-pill, 1beenlee/universal-context-handoff, gj9159a/codex-restore-chat-context, ojackson08/agenthandoff, hyderhusainarastu/cross-session-agent-handoff-prompt-template, giuliastro/harness-remote, tk1777-sy/-work-journal-skill, yazcaleb/rses, luluanes/native-windows-codex-claude-keepalive, sachind6/pi-resume-harness, ymonster/cc_jsonl_fix, supersistence/warp-claude-resume, eason-22/dsh-autorestart, ivbala1/limit-resume, han719307-dotcom/task-continuity, 2solarmax/pane-resume, m1ku831/codex-continue, roekdnd/dsh-restart-suite, catbusfleet-org/catbus, lpoee/opencac, didvc/web-to-cc, kc1t/alethe-agents, jerrywu001/cc-sessions-viewer, dwsy/pi-session-manager, red-noblue/codex_relay, angristan/fast-resume, 0xsero/parcels, dicklesworthstone/cross_agent_session_resumer …
  ★1000 以上的新名字：kc1t/alethe-agents, siteboon/claudecodeui, cytostack/openwolf, openai/codex-plugin-cc
第 11 組「context transfer」：35 個名字，新的 30 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：hetpatel-11/agent-hop, lijma/fcontext, rewfa-ceo/amp, harrychih/hishare, wink305/contextpocket, elecnix/pi-claude-memory, rememora/rememora, dhilipsiva/lucy, Vinyl-Davyl/hermes, softaworks/agent-toolkit, dongshuyan/compass-skills, sahilraut22/handoff, shivala-08/context-shifter, platman02/ctx-bridge, dullnote.com, hiperyon.com, context-transfer.vercel.app, context-transfer-protocol/ctp-spec, Kaseban/baton, FacuVCanale/session-bridge, MisterBrookT/codex2claude, authsec-ai/authsec-bridge, thepushkarp/handoff, who96/claude-code-context-handoff, aproto9787/codex-bridge, SeemSeam/claude_codex_bridge, ptreezh/stigmergy-CLI-Multi-Agents, relai.fyi, agentproto.sh, usespaces.dev
  ★1000 以上的新名字：softaworks/agent-toolkit, SeemSeam/claude_codex_bridge
第 12 組「chat log handoff」：21 個名字，新的 15 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：dongsheng123132/task-passport, wang5333/ai-handoff-summary-builder, voyfur/llm-wiki-session-memory, mattpocock/skills, shaswat28/handoff-skill, dennyferra/paseo-baton, lippinc/catnap, crosshead.sh, shafiqimtiaz/ctx-handoff, abassaf/baton, ylexliao/chatbridge, vasilispapg/claude-handoff, davo20019/relevo, shuntaka9576/chathist, jigyasudham/veto
  ★1000 以上的新名字：mattpocock/skills
第 13 組「跨 agent 記憶 交接」：23 個名字，新的 18 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：draiagent/ai-to-agent-memory, kwyeh-cl/agent-memory, askdkc/kiokuko-dsh, frc9427liu-tech/memrot, yunfeng008/codebaton, ihow1/ihow-memory-standard, dunova/contextgo, jordanwei1/jiaojie-skill, NevaMind-AI/memU, timyyf/agent-skills, memoryplugin.com, samemind, totalmemory.dev, klypix.com, snipara.com, datamcp.app, unabyss.com, harkstudio.io
  ★1000 以上的新名字：NevaMind-AI/memU
第 14 組「session migration」：39 個名字，新的 35 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：xhluca/session-migrate, totoro-qaq/dsh-plugin-bridge, chenglongli777/codex-migrate, chang-tong/dsh-unified-context, vibheksoni/session-export, agentairlift/agentairlift, larrtroffen/harnessbridge, bigwhite/cc-session-migrate, bug-gao/session-weaver, shivanshtalwar0/claude-buddy, yanzhi0922/codex-session-migrator, austinhoang8386/claude-history-windows, ikook-wang/cc-sync, llxgdtop/agent-session-migration, ahnafnafee/harness-bridge, mr-grimwig/dsh-zcode-migrate, ostiums/leftoff, liangyuan0219/session-migrator, agent-session-protocol/universal-session-log, xiaoyuyu6420/dsh-backup, myyimu/codex-session-transfer, tongtongtju/sessionbridge, devmom/dsh-session-import, hucj09/dsh-move-session, ingram-technologies/claude-git-sessions, avinash-jetwani/jevmem, aviator.co/runbooks, groundtrack.dev, CyrusSE/agenthop, nxxxsooo/another …
```

### 驗證組觀察結論
- **驗證組 1（中文：`跨 agent 記憶 交接`）**：新增 **18** 個名字，且再撈出 **1 個 ★1,000+ 專案**：`NevaMind-AI/memU`（★14,628，跨 coding agent LLM Wiki 記憶系統），證明先前第 2–12 組連續使用英文關鍵字時仍會漏掉以中文社群或跨語系介紹擴散的高星工具。
- **驗證組 2（英文：`session migration`）**：新增 **35** 個名字（多為 `<200★` 的專職 `.jsonl` 遷移 CLI／GUI，如 `xhluca/session-migrate` ★180、`totoro-qaq/dsh-plugin-bridge` ★168、`chenglongli777/codex-migrate` ★87），但 **★1,000+ 新名字為 0 個**（`★1,000+` 連續未新增組數升至 1）。
- **對 `--min-stars 1000` 停止條件的啟示**：此題目同時橫跨 4 個子生態（對話紀錄檢索、跨工具交接／遷移、壓縮恢復、跨 agent 記憶），長尾小工具（`<100★`）每換一組詞就新增十數至數十個，幾乎不可能在 12 組內達到「連續 3 組 0 新名字」；而 `★1,000+` 門檻在第 9 組曾歸零一次、第 14 組再次歸零，但受「記憶系統」與「大合集 skill 庫」兩類高星邊界專案影響，到第 12 組仍會觸發上限提醒。若實務上將主題拆細（例如專找「跨工具 session 轉換／交接」或排除大合集技能包），`--min-stars 1000` 會更快收斂。

## 四、最終相關名單（`sweep.py verify` 實測，查詢日期 `2026-11-18`）

### 4.1 ★1,000 以上高星專案（共 37 個實測 `★1,000+`，★標示）

> 以下依實測星數由高至低排列；其中標記「※另列於拿不準」者，已在第五節說明界線原因。

| 標記 | 名稱 (`owner/repo`) | 實測星數 | 授權 | 封存 | 最後 push | 一句話功能說明 |
|---|---|---:|---|---|---|
| ★1,000+ (※拿不準) | [`mattpocock/skills`](https://github.com/mattpocock/skills) | 326,805 | MIT | 否 | 2026-11-17 | 【技能包內含交接技能】工程師技能庫，內含 `handoff` skill，將當前對話壓縮整理為供下一位 agent 接手的交接文件。（屬多技能合集，另列於拿不準說明） |
| **★1,000+** | [`affaan-m/ECC`](https://github.com/affaan-m/ECC) | 305,571 | MIT | 否 | 2026-11-17 | 跨 Claude Code、Codex、OpenCode、Cursor 的 agent harness 最佳化系統，包含跨工作階段記憶（instincts/memory）、hooks 與上下文管理。 |
| **★1,000+** | [`thedotmack/claude-mem`](https://github.com/thedotmack/claude-mem) | 118,010 | Apache-2.0 | 否 | 2026-11-18 | 跨對話持久脈絡記憶外掛，自動擷取工作階段紀錄、壓縮摘要並注入後續對話；支援 Claude Code、Codex、Gemini、OpenCode、Copilot 等。 |
| **★1,000+** | [`MemPalace/mempalace`](https://github.com/MemPalace/mempalace) | 60,597 | MIT | 否 | 2026-11-17 | 本地優先 AI 記憶系統，支援將 Claude Code 對話紀錄原文存檔與檢索，並提供 CLI 與 MCP 介面跨對話重用。 |
| ★1,000+ (※拿不準) | [`openai/codex-plugin-cc`](https://github.com/openai/codex-plugin-cc) | 35,200 | Apache-2.0 | 否 | 2026-07-08 | 【複合套件含轉移指令】OpenAI 官方 Claude Code 外掛，主打在 Claude Code 內呼叫 Codex 審查／委派任務，內建 `/codex:transfer` 可將 Claude Code `.jsonl` 工作階段轉為可續聊的 Codex thread。（另列於拿不準說明） |
| **★1,000+** | [`mksglu/context-mode`](https://github.com/mksglu/context-mode) | 34,240 | NOASSERTION | 否 | 2026-11-17 | 本地外掛，透過沙盒與 SQLite FTS5 將大型工具輸出移出上下文視窗並支援事後檢索，支援 Claude Code、Codex、OpenCode、Gemini CLI 等 10+ 工具。 |
| **★1,000+** | [`rohitg00/agentmemory`](https://github.com/rohitg00/agentmemory) | 30,430 | Apache-2.0 | 否 | 2026-11-17 | 跨 coding agent 持久記憶層與 MCP 工具（50+ 工具、BM25＋向量檢索），支援 Claude Code 與 Codex 等工作階段記憶延續。 |
| **★1,000+** | [`OthmanAdi/planning-with-files`](https://github.com/OthmanAdi/planning-with-files) | 28,114 | MIT | 否 | 2026-11-11 | 檔案式持久規劃系統，支援 `/clear` 與壓縮後的工作階段恢復與每輪脈絡重注，支援 Claude Code、Codex、Cursor、OpenCode 等 60+ agent。 |
| **★1,000+** | [`akitaonrails/ai-memory`](https://github.com/akitaonrails/ai-memory) | 16,074 | MIT | 否 | 2026-11-18 | Rust 打造的 Git-backed Markdown Wiki 長期記憶與跨 CLI 交接工具，支援 Claude Code、Codex、Cursor、Gemini CLI 等 20+ 工具。 |
| ★1,000+ (※拿不準) | [`siteboon/claudecodeui`](https://github.com/siteboon/claudecodeui) | 14,669 | AGPL-3.0 | 否 | 2026-11-16 | 【遙控 WebUI 含工作階段管理】開源 CloudCLI 網頁與行動端介面，自動掃描 `~/.claude` 紀錄並支援 Claude Code、OpenCode、Cursor CLI、Codex 工作階段瀏覽、恢復與外掛交接。（另列於拿不準說明） |
| **★1,000+** | [`NevaMind-AI/memU`](https://github.com/NevaMind-AI/memU) | 14,628 | NOASSERTION | 否 | 2026-11-16 | 【驗證組 1 新發現】跨工作階段、跨 agent、跨裝置的個人 LLM Wiki 記憶系統，從歷史紀錄自動萃取技能並支援 Codex、Claude Code、Cursor 等。 |
| **★1,000+** | [`Gentleman-Programming/engram`](https://github.com/Gentleman-Programming/engram) | 8,215 | MIT | 否 | 2026-11-17 | Go 撰寫的跨 agent 持久記憶系統（SQLite + FTS5、MCP、HTTP API、CLI、TUI），無依賴單一執行檔。 |
| ★1,000+ (※拿不準) | [`WorldFlowAI/everything-claude-code`](https://github.com/WorldFlowAI/everything-claude-code) | 6,558 | 無 | 否 | 2026-01-23 | 【重複鏡像】內容為 `affaan-m/ECC`（everything-claude-code）的獨立複製倉（未標 Fork、無授權且停更於 2026-01）。（另列於拿不準說明） |
| **★1,000+** | [`breferrari/obsidian-mind`](https://github.com/breferrari/obsidian-mind) | 5,544 | MIT | 否 | 2026-10-17 | 以 Obsidian vault 為核心的自我組織持久記憶系統，原生支援 Claude Code 並提供 Codex CLI 與 Gemini CLI 的 hooks 與指令。 |
| **★1,000+** | [`entireio/cli`](https://github.com/entireio/cli) | 5,342 | MIT | 否 | 2026-11-18 | 將 AI coding agent 工作階段紀錄直接掛鉤至 Git 提交歷程建立可搜尋脈絡索引（Checkpoints 與 Git 並存）。 |
| **★1,000+** | [`basicmachines-co/basic-memory`](https://github.com/basicmachines-co/basic-memory) | 4,614 | AGPL-3.0 | 否 | 2026-11-17 | 基於本機 Markdown 與知識圖譜的 MCP 持久記憶系統，讓 AI 對話在跨工作階段與跨客戶端間保有結構化專案記憶。 |
| **★1,000+** | [`parcadei/Continuous-Claude-v3`](https://github.com/parcadei/Continuous-Claude-v3) | 3,951 | MIT | 否 | 2026-11-16 | 透過 hooks 維持帳本（ledgers）與交接檔（handoffs）的 Claude Code 上下文管理與隔離視窗協調框架。 |
| **★1,000+** | [`SeemSeam/claude_codex_bridge`](https://github.com/SeemSeam/claude_codex_bridge) | 3,630 | NOASSERTION | 否 | 2026-11-11 | 多 agent CLI 視覺化協作工作區，強調對話連續性、斷線恢復與跨 Claude、Codex、Gemini、Cursor、Pi、OpenCode 的紀錄保留。 |
| ★1,000+ (※拿不準) | [`MemMachine/MemMachine`](https://github.com/MemMachine/MemMachine) | 3,090 | Apache-2.0 | 否 | 2026-11-16 | 【通用型記憶層】通用 AI Agent 記憶層與 MCP 伺服器，支援 Claude Desktop、Cursor 等客戶端跨對話記憶儲存與檢索。（另列於拿不準說明） |
| **★1,000+** | [`alexgreensh/token-optimizer`](https://github.com/alexgreensh/token-optimizer) | 3,016 | NOASSERTION | 否 | 2026-11-16 | 偵測上下文浪費並提供壓縮前檢查點與恢復（checkpoint + restore）機制的上下文最佳化技能工具。 |
| ★1,000+ (※拿不準) | [`softaworks/agent-toolkit`](https://github.com/softaworks/agent-toolkit) | 2,695 | MIT | 否 | 2026-03-05 | 【技能包內含交接技能】AI coding agent 技能集，內含 `session-handoff` skill 支援跨對話無縫交接。（另列於拿不準說明） |
| **★1,000+** | [`cytostack/openwolf`](https://github.com/cytostack/openwolf) | 2,401 | AGPL-3.0 | 否 | 2026-10-19 | 跨 Claude Code、Codex 與 OpenCode 的可攜式本機專案記憶系統，並從 harness transcripts 量測 token 消耗。 |
| **★1,000+** | [`jhlee0409/claude-code-history-viewer`](https://github.com/jhlee0409/claude-code-history-viewer) | 2,324 | MIT | 否 | 2026-11-18 | 100% 離線桌面與網頁檢視器，瀏覽、搜尋並分析 Claude Code、Codex CLI、Copilot、Gemini CLI、Cursor、OpenCode 等對話紀錄。 |
| **★1,000+** | [`pchalasani/claude-code-tools`](https://github.com/pchalasani/claude-code-tools) | 2,040 | MIT | 否 | 2026-11-10 | Claude Code / Codex CLI 實用工具組，內含 Rust 對話搜尋工具 `aichat-search` 與損壞工作階段修復工具 `session-repair`。 |
| **★1,000+** | [`simonw/claude-code-transcripts`](https://github.com/simonw/claude-code-transcripts) | 1,734 | Apache-2.0 | 否 | 2026-02-12 | 將 Claude Code 工作階段對話紀錄轉換與發布為可檢視、可分享網頁／靜態紀錄的 CLI 工具。 |
| **★1,000+** | [`vshulcz/deja-vu`](https://github.com/vshulcz/deja-vu) | 1,608 | MIT | 否 | 2026-11-17 | 單一 Go 執行檔提供本地記憶、對話搜尋與跨 48 種 coding agent（Claude Code、Codex、Cursor、OpenCode、Gemini CLI 等）交接（7 hooks + MCP）。 |
| **★1,000+** | [`yigitkonur/cli-continues`](https://github.com/yigitkonur/cli-continues) | 1,605 | MIT | 否 | 2026-05-07 | 跨 Claude Code、Copilot、Gemini、Codex、Cursor、OpenCode、Cline 等 16 種工具掃描本機對話紀錄並打包接續交接的 CLI。 |
| ★1,000+ (※拿不準) | [`fujibee/agmsg`](https://github.com/fujibee/agmsg) | 1,591 | MIT | 否 | 2026-11-17 | 【跨 agent 傳訊為主】基於本機共用 SQLite 讓 Claude Code、Codex、Gemini CLI 與 Copilot CLI 工作階段彼此傳訊交辦，非傳統對話日誌搜尋／還原工具。（另列於拿不準說明） |
| ★1,000+ (※拿不準) | [`ClaudioDrews/memory-os`](https://github.com/ClaudioDrews/memory-os) | 1,396 | MIT | 否 | 2026-09-20 | 【單一 agent 生態】專為 Hermes Agent 設計的 7 層記憶作業系統（Qdrant、FTS5 session 搜尋與自動策展 wiki）。（另列於拿不準說明） |
| **★1,000+** | [`specstoryai/getspecstory`](https://github.com/specstoryai/getspecstory) | 1,375 | Apache-2.0 | 否 | 2026-11-17 | 跨 IDE 與終端機 agent 的本地優先歷史紀錄擴充套件，儲存、搜尋並將歷史紀錄轉為可重用技能與專案規範。 |
| **★1,000+** | [`asheshgoplani/agent-deck`](https://github.com/asheshgoplani/agent-deck) | 1,274 | MIT | 否 | 2026-11-18 | 跨 Claude、Gemini、OpenCode、Codex 等 AI coding agent 的終端工作階段管理 TUI，整合工作階段切換與恢復。 |
| **★1,000+** | [`chunxiaoxx/nautilus-compass`](https://github.com/chunxiaoxx/nautilus-compass) | 1,258 | NOASSERTION | 否 | 2026-11-18 | 開放式 AI agent 記憶與可靠度層，提供 17 個 MCP 工具並支援 Claude Code、Cline、Cursor、Continue.dev、Zed 等。 |
| **★1,000+** | [`Dicklesworthstone/coding_agent_session_search`](https://github.com/Dicklesworthstone/coding_agent_session_search) | 1,214 | NOASSERTION | 否 | 2026-11-17 | 統一 TUI 與 CLI，索引並搜尋超過 30 種 coding agent（Codex、Claude Code、Gemini、Cursor、Aider 等）的本地對話紀錄成單一時間軸。 |
| **★1,000+** | [`Kc1t/alethe-agents`](https://github.com/Kc1t/alethe-agents) | 1,210 | AGPL-3.0 | 否 | 2026-11-08 | 本地優先桌面工作區，以真實 PTY 與分頁管理多個 coding agent，具備本地工作階段歷史與恢復能力。 |
| **★1,000+** | [`ctxrs/ctx`](https://github.com/ctxrs/ctx) | 1,184 | Apache-2.0 | 否 | 2026-11-05 | 專為 coding agent 設計的本地歷史即時召回工具（類似 agent session 的 `git blame`），可直接搜尋機器上既有的對話紀錄。 |
| **★1,000+** | [`andrepimenta/claude-code-chat`](https://github.com/andrepimenta/claude-code-chat) | 1,087 | NOASSERTION | 否 | 2026-09-18 | VS Code 專用 Claude Code 聊天介面擴充套件，內建自動對話歷史記錄、工作階段管理與檢查點還原（Restore Checkpoints）。 |
| ★1,000+ (※拿不準) | [`omdsh-dev/dsh-mnemon`](https://github.com/omdsh-dev/dsh-mnemon) | 1,030 | MIT | 否 | 2026-11-17 | 【單一 harness 生態】專為 DeepSeek Harness（dsh）設計的可組合分層記憶與上下文策略系統。（另列於拿不準說明） |

### 4.2 實測 ★100–999 中堅專案（共 65 個，全部經 `sweep.py verify` 驗證）

| 名稱 (`owner/repo`) | 實測星數 | 授權 | 封存 | 最後 push | 一句話功能說明（GitHub 簡介整理） |
|---|---:|---|---|---|---|
| [`im4codes/imcodes`](https://github.com/im4codes/imcodes) | 964 | MIT | 否 | 2026-11-17 | The IM for agents. Shared Agent Context & Memory, supervised execution, and cross-agent audit across AI providers. |
| [`jazzyalex/agent-sessions`](https://github.com/jazzyalex/agent-sessions) | 949 | MIT | 否 | 2026-11-17 | Local-first macOS app to browse, search, analyze, and resume supported AI coding-agent session history across Codex, Claude Code, OpenCode, Cursor Agent, Antigravity, Hermes, OpenClaw, Copilot CLI, and more. |
| [`AVIDS2/memorix`](https://github.com/AVIDS2/memorix) | 942 | Apache-2.0 | 否 | 2026-11-11 | Open-source cross-agent memory layer for coding agents via MCP. Compatible with Claude Code, Codex, Cursor, Windsurf, Gemini CLI, Antigravity, OpenClaw, Hermes Agent, Oh-my-Pi, Pi, Copilot, Kiro, OpenCode, and Trae. |
| [`CodeAbra/iai-personal-memory-engine`](https://github.com/CodeAbra/iai-personal-memory-engine) | 923 | MIT | 否 | 2026-11-13 | A cyber brain for your AI. It never forgets a detail, remembers exactly what you said, and learns how you work over time. Free, local, works with Cursor, Claude Code, Codex, OpenClaw, Hermes and more. MIT. |
| [`okf-memory/okf-agent-memory`](https://github.com/okf-memory/okf-agent-memory) | 867 | MIT | 否 | 2026-11-14 | Git-native persistent memory for AI coding agents. Implements Google OKF v0.2 with sub-300µs in-memory BM25 search, embedded MCP server, and progressive disclosure. Slashes token bloat by 80% with zero external databases or dependencies. Built in pure Go. |
| [`es617/claude-replay`](https://github.com/es617/claude-replay) | 862 | MIT | 否 | 2026-11-13 | Convert AI coding agent sessions (Claude Code, Cursor, Codex, Gemini, OpenCode, Kimi Code, Hermes) into self-contained, embeddable HTML  replays |
| [`kitfunso/hippo-memory`](https://github.com/kitfunso/hippo-memory) | 794 | MIT | 否 | 2026-11-17 | One memory for every agent you'll ever use. Hippo writes what you teach a coding agent into a store in your repo, and your other agents read that same store. |
| [`Storybloq/storybloq`](https://github.com/Storybloq/storybloq) | 788 | NOASSERTION | 否 | 2026-11-17 | Project memory and workflows for Claude Code and Codex. Keep stories, plans, handovers, and review evidence in your repo. Resume across sessions and follow progress in the Mac app. |
| [`raiyanyahya/recall`](https://github.com/raiyanyahya/recall) | 770 | MIT | 否 | 2026-09-07 | Stop wasting tokens and re-explaining your project every session. Recall gives Claude Code , Opencode durable memory — entirely offline. |
| [`dongshuyan/compass-skills`](https://github.com/dongshuyan/compass-skills) | 770 | MIT | 否 | 2026-11-15 | 司南：个性化 AI 任务总控 Skills 系统 /COMPASS: Personal Alignment Skills OS for AI Agents |
| [`0xK3vin/MegaMemory`](https://github.com/0xK3vin/MegaMemory) | 737 | MIT | 否 | 2026-05-03 | Persistent project knowledge graph for coding agents. MCP server with semantic search, in-process embeddings, and web explorer. |
| [`mnemon-dev/mnemon`](https://github.com/mnemon-dev/mnemon) | 720 | Apache-2.0 | 否 | 2026-11-17 | LLM-supervised persistent memory for AI agents — graph-based recall, cross-session knowledge, single binary. Works with DeepSeek Harness, Claude Code, OpenClaw, and any agent runtime. |
| [`JuliusBrussee/cavemem`](https://github.com/JuliusBrussee/cavemem) | 679 | MIT | 否 | 2026-11-17 | Frozen — cross-agent persistent memory for coding assistants. Still works; the compressed-memory core now ships inside JuliusBrussee/caveman. |
| [`Enderfga/claw-orchestrator`](https://github.com/Enderfga/claw-orchestrator) | 614 | MIT | 否 | 2026-11-15 | Run Claude Code, Codex, Antigravity, Grok Build and OpenCode behind one runtime, and a run only counts as done when checks it didn't write pass. Cross-engine fan-out, councils, session handoff, spend caps, MCP server, ACP agent. |
| [`memvid/claude-brain`](https://github.com/memvid/claude-brain) | 585 | MIT | 否 | 2026-01-19 | Give Claude Code photographic memory in ONE portable file. No database, no SQLite, no ChromaDB - just a single .mv2 file you can git commit, scp, or share. Native Rust core with sub-ms operations. |
| [`raine/claude-history`](https://github.com/raine/claude-history) | 544 | MIT | 否 | 2026-11-04 | Fuzzy-search Claude Code conversation history |
| [`Dicklesworthstone/cass_memory_system`](https://github.com/Dicklesworthstone/cass_memory_system) | 466 | NOASSERTION | 否 | 2026-11-16 | Procedural memory for AI coding agents: transforms scattered session history into persistent, cross-agent memory so every agent learns from every other |
| [`giuliastro/harness-remote`](https://github.com/giuliastro/harness-remote) | 446 | Apache-2.0 | 否 | 2026-11-16 | Native-session control plane for Codex, Claude Code, OpenCode, PI and many others. Run, resume and hand off coding sessions across your machines. |
| [`Autoloops/greplica`](https://github.com/Autoloops/greplica) | 443 | MIT | 否 | 2026-07-30 | Persistent, searchable engineering memory for AI coding agents. Saves ~50% tokens and ~30% time while planning |
| [`Lyellr88/marm-memory`](https://github.com/Lyellr88/marm-memory) | 438 | Apache-2.0 | 否 | 2026-11-12 | Local-first 3-in-1 AI memory layer & MCP server for Claude Code, Codex, Grok, Gemini, VS Code and Cursor. Fuses session history, codebase indexing & concept graphs in SQLite. Enables zero-cloud, privacy-first context & instant recall, supports multi-agent swarms. |
| [`cwinvestments/memstack`](https://github.com/cwinvestments/memstack) | 433 | MIT | 否 | 2026-11-12 | Persistent memory and skill framework for Claude Code: session diary, fact recall, 87 free skills, MCP skill loader |
| [`jerrywu001/cc-sessions-viewer`](https://github.com/jerrywu001/cc-sessions-viewer) | 420 | MIT | 否 | 2026-11-02 | support cc/codex/grok build/kimicode/pi/antigravity cli/opencode sessions viewer, skills manage, token usage statistics, global search, resume, and export to html |
| [`CooperJiang/coding-tool`](https://github.com/CooperJiang/coding-tool) | 416 | MIT | 否 | 2025-12-08 | claudecode\|codex\|gemini  cli增强工具。 |
| [`Pratiyush/llm-wiki`](https://github.com/Pratiyush/llm-wiki) | 402 | MIT | 否 | 2026-06-18 | LLM-powered knowledge base from your Claude Code, Codex CLI, Copilot, Cursor & Gemini sessions. Karpathy's LLM Wiki pattern — implemented and shipped. |
| [`NeoLi00/memX`](https://github.com/NeoLi00/memX) | 401 | MIT | 否 | 2026-05-26 | memX: self-learning, self-maintaining memory plugin for AI agents; native support for claude code, codex, and openclaw |
| [`lovstudio/Ataru`](https://github.com/lovstudio/Ataru) | 363 | Apache-2.0 | 否 | 2026-08-24 | High-performance AI memory retrieval for local agent history — a Rust search core (SDK / API / JSON CLI) plus a desktop GUI. Tantivy + Jieba keyword search, optional semantic recall, stable Turn/Run/Session/Project IDs. |
| [`dezgit2025/auto-memory`](https://github.com/dezgit2025/auto-memory) | 363 | MIT | 否 | 2026-11-17 | Your AI coding agent never forgets — progressive session recall CLI |
| [`Nwflower/dsh-chat-import`](https://github.com/Nwflower/dsh-chat-import) | 317 | MIT | 否 | 2026-11-15 | Import conversation history from 25+ AI coding agents into DeepSeek Harness as resumable sessions — tool calls, reasoning and results kept intact, with reverse export and sync. \| 把 25+ AI 编程 Agent 的聊天记录导入 DeepSeek Harness 继续对话，保留工具调用、推理与结果，支持反向导出与同步。 |
| [`nameforjt-afk/session-knowledge`](https://github.com/nameforjt-afk/session-knowledge) | 307 | MIT | 否 | 2026-10-23 | Turn your Claude Code session history into a searchable local knowledge base — 13 MCP tools, pure stdlib, nothing leaves your machine |
| [`yan5xu/code-relay`](https://github.com/yan5xu/code-relay) | 307 | 無 | 否 | 2026-02-10 | AI Coding Agent 工作协议 — 跨会话记忆、多仓库全局视野、结构化上下文管理 |
| [`oleksiijko/pmb`](https://github.com/oleksiijko/pmb) | 291 | Apache-2.0 | 否 | 2026-11-11 | Local-first persistent memory for AI coding agents (Claude Code, Cursor, Codex) over MCP. Decisions, lessons and facts live in one SQLite file on your disk. Offline, multilingual. |
| [`SiriLee/dsh-rewind`](https://github.com/SiriLee/dsh-rewind) | 282 | MIT | 否 | 2026-11-16 | DSH 插件：便捷无感的同窗口内对话回退，从不新建分支；自带轻量工作区备份，可一并还原文件（Claude Code /rewind 语义）。 ·  DSH plugin: effortless in-window conversation rewind — never forking a new session; ships a lightweight workspace backup that restores files together with the rewind (Claude Code /rewind semantics). |
| [`hacktivist123/agent-session-resume`](https://github.com/hacktivist123/agent-session-resume) | 244 | MIT | 否 | 2026-06-30 | Cross-agent session resume skill for Claude Code, Codex, Antigravity, and OpenCode. |
| [`jdrhyne/agent-skills`](https://github.com/jdrhyne/agent-skills) | 240 | MIT | 否 | 2026-08-30 | A collection of AI agent skills for Clawdbot, Claude Code, Codex |
| [`entireio/skills`](https://github.com/entireio/skills) | 240 | MIT | 否 | 2026-11-15 | ✨ Cross-agent skills that help coding agents use Entire context from Checkpoints, sessions, and git history to search past work, explain code, and hand off sessions. |
| [`joshuaswarren/remnic`](https://github.com/joshuaswarren/remnic) | 233 | MIT | 否 | 2026-11-18 | Open-source memory and context for user-aware agents: scoped memory, provenance, retrieval quality, correction, boundaries, evals, and MCP/HTTP access. |
| [`big0lives/codex-task-pointer`](https://github.com/big0lives/codex-task-pointer) | 214 | MIT | 否 | 2026-10-16 | Pre-compaction hooks + a CAS-guarded task pointer that keep Codex agents on-goal across context auto-compaction — no mainline drift, no duplicate work, no conflicting progress in long runs. |
| [`yoloshii/ClawMem`](https://github.com/yoloshii/ClawMem) | 212 | MIT | 否 | 2026-11-07 | On-device memory layer for AI agents. Claude Code, OpenClaw and Hermes. Hooks + MCP server + hybrid RAG search. |
| [`u-ichi/compact-plus`](https://github.com/u-ichi/compact-plus) | 211 | MIT | 否 | 2026-07-27 | Claude Code plugin: preserve and restore working state around /compact |
| [`alibaizhanov/mengram`](https://github.com/alibaizhanov/mengram) | 207 | Apache-2.0 | 否 | 2026-11-09 | Human-like memory for AI agents — semantic, episodic & procedural. Experience-driven procedures that learn from failures. Free API, Python & JS SDKs, LangChain, CrewAI & OpenClaw integrations. |
| [`Dwsy/pi-session-manager`](https://github.com/Dwsy/pi-session-manager) | 206 | 無 | 否 | 2026-11-13 | Pi session manager for browsing, searching, and resuming Pi AI coding sessions. Related project: https://github.com/badlogic/pi-mono |
| [`davegoldblatt/total-recall`](https://github.com/davegoldblatt/total-recall) | 203 | 無 | 否 | 2026-02-12 | Persistent memory plugin for Claude Code. Tiered memory system with write gates, correction propagation, and slash commands. |
| [`Red-noblue/Codex_Relay`](https://github.com/Red-noblue/Codex_Relay) | 200 | 無 | 否 | 2026-03-01 | Cross-device export/import + local vault for Codex CLI sessions (.jsonl). Resume the same session on macOS/Windows/Manage, backup, and transfer Codex CLI sessions (.jsonl) across devices with preview + conflict-safe import.Linux. |
| [`zippoxer/recall`](https://github.com/zippoxer/recall) | 198 | MIT | 否 | 2026-01-14 | Full-text search and resume for Claude/Codex conversations |
| [`angristan/fast-resume`](https://github.com/angristan/fast-resume) | 195 | MIT | 否 | 2026-11-13 | Find that one coding agent session you want to get back to! |
| [`Vvkmnn/claude-historian-mcp`](https://github.com/Vvkmnn/claude-historian-mcp) | 180 | MIT | 否 | 2026-11-02 | 📜 An MCP server for conversation history search and retrieval in Claude Code |
| [`xhluca/session-migrate`](https://github.com/xhluca/session-migrate) | 180 | MIT | 否 | 2026-11-16 | Migrate coding agent sessions across 18 harnesses (Claude Code, Codex, Pi, OpenCode, Copilot, Antigravity, Vibe, Muse, Qwen, Kimi, Cursor, etc.) |
| [`joseairosa/recall`](https://github.com/joseairosa/recall) | 179 | MIT | 否 | 2026-10-26 | Persistent cross-session memory for Claude & AI agents. Self-host on Redis/Valkey, or use the managed SaaS at recallmcp.com. |
| [`0xSero/parcels`](https://github.com/0xSero/parcels) | 175 | MIT | 否 | 2026-09-03 | Ship your repo + live coding-agent session (Claude Code / Codex / pi / Droid) to another machine over Tailscale; it resumes in tmux and keeps working. |
| [`hjertefolger/cortex`](https://github.com/hjertefolger/cortex) | 173 | MIT | 否 | 2026-03-14 | Persistent local memory for Claude Code. Longer sessions. Cross-session recall. Zero cloud. |
| [`Riley-Coyote/mnemos-mcp`](https://github.com/Riley-Coyote/mnemos-mcp) | 168 | Apache-2.0 | 否 | 2026-11-12 | Continuity for the agent itself. An MCP server that gives an AI agent a memory of its own, written in its own words and kept on your machine, so it wakes as itself every session. |
| [`Totoro-qaq/dsh-plugin-bridge`](https://github.com/Totoro-qaq/dsh-plugin-bridge) | 168 | MIT | 否 | 2026-11-06 | DeepSeek Harness plugin for previewable cross-preset session migration. Fixed-schema handoffs preserve state, source-model intent, and unresolved images; the original session stays untouched. |
| [`dcostenco/prism-coder`](https://github.com/dcostenco/prism-coder) | 156 | Apache-2.0 | 否 | 2026-11-14 | Persistent session memory for AI coding agents — local-first, with on-device inference, associative recall, and drift detection. Works with Claude Code, Cursor, and Codex. |
| [`Avinash-jetwani/jevmem`](https://github.com/Avinash-jetwani/jevmem) | 153 | MIT | 否 | 2026-11-17 | Shared project rules and memory for AI coding agents. Decisions, rules and failed approaches in one JEVMEM.md in your repo, read by Claude Code, Cursor and Codex, with a guard that checks Claude's commands before they run. |
| [`mkreyman/mcp-memory-keeper`](https://github.com/mkreyman/mcp-memory-keeper) | 136 | MIT | 否 | 2026-09-03 | MCP server for persistent context management in AI coding assistants |
| [`neilberkman/ccrider`](https://github.com/neilberkman/ccrider) | 136 | MIT | 否 | 2026-11-16 | Search, browse, and resume your Claude Code sessions. Fast. |
| [`AppachiTech/suvadu`](https://github.com/AppachiTech/suvadu) | 130 | MIT | 否 | 2026-11-11 | Shell history replacement with AI agent tracking and MCP server. Built in Rust, 100% local. |
| [`Dicklesworthstone/cross_agent_session_resumer`](https://github.com/Dicklesworthstone/cross_agent_session_resumer) | 129 | NOASSERTION | 否 | 2026-10-14 | Resume AI coding sessions across providers: converts Codex, Claude, Gemini, and other session formats through a canonical IR so you can pick up where you left off in any tool |
| [`tombelieber/claude-view`](https://github.com/tombelieber/claude-view) | 127 | MIT | 否 | 2026-11-09 | 10 Claude sessions running. What are they doing? Live dashboard — monitor, cost tracking, search, sub-agent visibility. |
| [`loryoncloud/Memory-Like-A-Tree`](https://github.com/loryoncloud/Memory-Like-A-Tree) | 126 | 無 | 否 | 2026-02-28 | Memory-Like-A-Tree🌳 Memory management system for AI Agents - Let knowledge grow like a tree. Features confidence-based lifecycle, auto-decay, cross-agent search, and Obsidian sync. 🌳 AI Agent 记忆管理系统 - 让知识像树一样生长。支持置信度生命周期、自动衰减、跨 Agent 搜索、Obsidian 同步。 |
| [`Frankie-Xu/threadport`](https://github.com/Frankie-Xu/threadport) | 123 | Apache-2.0 | 否 | 2026-11-08 | Portable, verifiable work state for coding agents |
| [`samzong/Recall`](https://github.com/samzong/Recall) | 109 | MIT | 否 | 2026-11-12 | Switch agents. Keep the history. Local-first search across your AI coding sessions. |
| [`MedivhStory/ClaudeSessionHub`](https://github.com/MedivhStory/ClaudeSessionHub) | 104 | MIT | 否 | 2026-05-07 | Native macOS task manager for Claude Code sessions with session browsing, overview dashboard, resume actions, and local-only data scanning. |
| [`qingsongcui/ContextCore`](https://github.com/qingsongcui/ContextCore) | 101 | MIT | 否 | 2026-11-17 | Senrelay · 续境 — Local-first macOS multi-Agent conversation relay, source-linked persistent memory, and unified host configuration workbench. |
| [`yuvalsuede/memory-mcp`](https://github.com/yuvalsuede/memory-mcp) | 100 | MIT | 否 | 2026-01-29 | Persistent memory for Claude Code — never lose context between sessions |

### 4.3 重點 `<100★` 跨 Agent／專精工具精選（皆經 `sweep.py verify` 實測）

許多專為「跨工具轉換對話紀錄」或「跨 harness 交接」打造的新工具星數尚低但切題度極高，精選代表如下：

| 名稱 (`owner/repo`) | 實測星數 | 授權 | 最後 push | 一句話功能說明 |
|---|---:|---|---|---|
| [`Jordanwei1/jiaojie-skill`](https://github.com/Jordanwei1/jiaojie-skill) | 91 | MIT | 2026-08-20 | 跨視窗、跨模型、跨裝置、跨語言的 AI 上下文交接 Skill（Jiaojie）。 |
| [`wilbeibi/catchup`](https://github.com/wilbeibi/catchup) | 83 | MIT | 2026-10-24 | 本地優先跨工具上下文交接 CLI（Claude Code、Codex、Cursor、Cline、Kimi、Antigravity、OpenCode、Pi）。 |
| [`REMvisual/claude-handoff`](https://github.com/REMvisual/claude-handoff) | 75 | MIT | 2026-11-11 | Claude Code `/compact-handoff` 與交接技能，以結構化驗證交接取代原生壓縮。 |
| [`aytzey/showagent`](https://github.com/aytzey/showagent) | 64 | MIT | 2026-11-16 | Go 撰寫的終端選擇器與 MCP 伺服器，整合 Claude Code、Codex、Gemini CLI、OpenCode、Antigravity、Pi 本地紀錄並支援原生轉交。 |
| [`agent-session-protocol/universal-session-log`](https://github.com/agent-session-protocol/universal-session-log) | 56 | MIT | 2026-11-07 | Agent Session Protocol (ASP) 儲存層實作（USL），提供跨執行環境工作階段遷移的通用日誌格式。 |
| [`vitaliyhayda/claude-transplant`](https://github.com/vitaliyhayda/claude-transplant) | 54 | MIT | 2026-11-15 | 在切換 Claude 帳號後遷移本機 Claude Desktop Code 工作階段紀錄（macOS / CLI）。 |
| [`Ryu0118/ctxmv`](https://github.com/Ryu0118/ctxmv) | 44 | MIT | 2026-11-17 | Swift 撰寫的 CLI，跨 Claude Code、Codex、Cursor CLI、Kimi Code、Copilot CLI 遷移可續聊工作階段。 |
| [`Manavarya09/relay`](https://github.com/Manavarya09/relay) | 41 | MIT | 2026-09-15 | Claude Code 達額度上限時，自動將完整上下文交接至 Codex、Gemini、Aider 等工具接續工作。 |
| [`hetpatel-11/agent-hop`](https://github.com/hetpatel-11/agent-hop) | 36 | MIT | 2026-08-31 | 單一終端運行並即時切換／搜尋／恢復 Claude Code、Codex、OpenCode、Pi、Grok 工作階段。 |
| [`obrenoalvim/zero-drift`](https://github.com/obrenoalvim/zero-drift) | 37 | MIT | 2026-10-22 | 跨工作階段追蹤任務目標，避免長對話期間 AI 偏離主線。 |
| [`Kaseban/baton`](https://github.com/Kaseban/baton) | 29 | Apache-2.0 | 2026-10-16 | Rust CLI + MCP server，無損雙向轉換 Claude Code、Codex、OpenCode、Zed、Aider、Gemini CLI、Cursor、Cline 對話紀錄。 |
| [`dunova/ContextGO`](https://github.com/dunova/ContextGO) | 28 | AGPL-3.0 | 2026-09-26 | 無 MCP 依賴、Rust/Go 加速的本地優先多 agent 寫程式團隊上下文與記憶執行層。 |
| [`vibheksoni/session-export`](https://github.com/vibheksoni/session-export) | 22 | MIT | 2026-10-27 | CLI／SDK／MCP，支援 Codex、Claude Code、Pi、OpenCode、Devin、Factory 工作階段雙向轉換與對話召回。 |
| [`Vinyl-Davyl/hermes`](https://github.com/Vinyl-Davyl/hermes) | 17 | MIT | 2026-09-28 | 本地優先交接 CLI，將磁碟上未完成進度打包交給下一個 coding agent（Claude、Cursor、Codex、Antigravity）。 |
| [`AgentWorkforce/relayhistory`](https://github.com/AgentWorkforce/relayhistory) | 15 | MIT | 2026-11-17 | 將本機所有 coding agent 的歷史工作階段索引進單一可搜尋本地資料庫。 |
| [`cote-star/agent-chorus`](https://github.com/cote-star/agent-chorus) | 15 | MIT | 2026-09-28 | 零 npm 依賴本機 CLI，跨 Claude Code、Codex、Gemini、Cursor 讀取、比對與交接工作階段。 |
| [`bvolpato/omnisession`](https://github.com/bvolpato/omnisession) | 10 | MIT | 2026-11-17 | 本地優先 CLI/TUI，搜尋任何 coding agent 工作階段並在 Claude Code、Codex、OpenCode、Pi、Cursor 等任意工具接續。 |
| [`yazcaleb/rses`](https://github.com/yazcaleb/rses) | 10 | 無 | 2026-03-26 | 在 Claude Code、Codex CLI 與 OpenCode 之間跨工具直接恢復（cross-resume）工作階段。 |
| [`Capetlevrai/resume-claude-codex-grok`](https://github.com/Capetlevrai/resume-claude-codex-grok) | 10 | MIT | 2026-08-29 | 跨 Claude Code、Codex、Grok Build、OpenCode、Cursor 接續進行中工作階段的 CLI 工具。 |
| [`MisterBrookT/codex2claude`](https://github.com/MisterBrookT/codex2claude) | 7 | MIT | 2026-11-12 | Claude Code 外掛（`/import-codex`），將 Codex 工作階段匯入 Claude Code 並以 `claude -r` 接續。 |
| [`Larrtroffen/harnessbridge`](https://github.com/Larrtroffen/harnessbridge) | 7 | MIT | 2026-11-01 | macOS 原生 SwiftUI 應用與 CLI，跨 Claude Code、Codex、DSH、Pi、Gemini CLI 等 40+ harness 遷移工作階段。 |
| [`authsec-ai/authsec-bridge`](https://github.com/authsec-ai/authsec-bridge) | 9 | 無 | 2026-05-08 | Python CLI，轉換 Claude Code、Codex 與 Gemini CLI 本機紀錄以原生 `--resume` 接續。 |
| [`harrychih/hiShare`](https://github.com/harrychih/hiShare) | 6 | MIT | 2026-07-30 | 在 Claude Code 與 OpenAI Codex 之間索引、匯出、匯入並恢復可攜式工作階段交接。 |
| [`nxxxsooo/another`](https://github.com/nxxxsooo/another) | 6 | MIT | 2026-11-18 | Go TUI/CLI（`agenthop` 分支），跨 10 種 agent 原生格式遷移工作階段並支援 Git worktree 聚合與回滾驗證。 |
| [`pma1999/session-bridge`](https://github.com/pma1999/session-bridge) | 4 | MIT | 2026-11-09 | Claude Code、OpenCode 與 Codex 之間 6 個方向的本機工作階段轉換與同步。 |
| [`44-pixels/handover-mcp`](https://github.com/44-pixels/handover-mcp) | 4 | MIT | 2026-08-05 | 跨 Claude Code、Codex、Cursor、Gemini CLI 的共享版本化上下文 MCP server、CLI 與技能。 |
| [`jigyasudham/veto`](https://github.com/jigyasudham/veto) | 4 | MIT | 2026-11-14 | Veto MCP 內建 `veto_handoff`／`veto_continue`，在觸及速率或上下文上限時跨 Claude Code、Codex、Gemini、Cursor、Windsurf 切換。 |
| [`shuntaka9576/chathist`](https://github.com/shuntaka9576/chathist) | 4 | MIT | 2026-04-11 | Rust CLI 搭配 `fzf` 與 Jinja2 模板搜尋、預覽、匯出與恢復 AI coding agent 對話紀錄。 |
| [`astral303/rearview`](https://github.com/astral303/rearview) | 2 | MIT | 2026-11-17 | 終端語意／關鍵字搜尋 Claude Code、Codex、OpenCode、Kimi、Pi、OMP 對話紀錄。 |
| [`FacuVCanale/session-bridge`](https://github.com/FacuVCanale/session-bridge) | 0 | 無 | 2026-05-27 | Python CLI，對應雙邊工具呼叫格式轉換 Claude Code 與 Codex CLI 工作階段。 |

### 4.4 其餘實測 `★10–99` GitHub Repo 清單（共 151 個，皆經 `sweep.py verify` 驗證）

<details>
<summary>點擊展開全部 151 個 ★10–99 repo（含實測星數、授權與最後 push 日期，查詢日期 2026-11-18）</summary>

| 名稱 (`owner/repo`) | 星數 | 授權 | 最後 push |
|---|---:|---|---|
| [`kunwar-shah/claudex`](https://github.com/kunwar-shah/claudex) | 98 | MIT | 2026-06-20 |
| [`coding-by-feng/ai-agent-session-center`](https://github.com/coding-by-feng/ai-agent-session-center) | 96 | MIT | 2026-11-15 |
| [`caura-ai/caura-long-run-fleet`](https://github.com/caura-ai/caura-long-run-fleet) | 92 | MIT | 2026-10-22 |
| [`StayCurious-Xuan/wayfinder`](https://github.com/StayCurious-Xuan/wayfinder) | 92 | MIT | 2026-10-18 |
| [`Jordanwei1/jiaojie-skill`](https://github.com/Jordanwei1/jiaojie-skill) | 91 | MIT | 2026-08-20 |
| [`wesm/archived-agent-session-viewer`](https://github.com/wesm/archived-agent-session-viewer) | 88 | MIT | 2026-02-23 |
| [`ChenglongLi777/codex-migrate`](https://github.com/ChenglongLi777/codex-migrate) | 87 | MIT | 2026-08-01 |
| [`samfoy/pi-total-recall`](https://github.com/samfoy/pi-total-recall) | 86 | MIT | 2026-10-29 |
| [`wilbeibi/catchup`](https://github.com/wilbeibi/catchup) | 83 | MIT | 2026-10-24 |
| [`EverMind-AI/EverMe`](https://github.com/EverMind-AI/EverMe) | 82 | Apache-2.0 | 2026-11-17 |
| [`0xDarkMatter/claude-mods`](https://github.com/0xDarkMatter/claude-mods) | 81 | MIT | 2026-11-07 |
| [`ahundt/ai-session-search`](https://github.com/ahundt/ai-session-search) | 81 | Apache-2.0 | 2026-11-18 |
| [`cdeust/Cortex`](https://github.com/cdeust/Cortex) | 77 | MIT | 2026-11-17 |
| [`dosu-ai/decant`](https://github.com/dosu-ai/decant) | 75 | Apache-2.0 | 2026-11-18 |
| [`Elevatormusic/hermes-warm-compaction`](https://github.com/Elevatormusic/hermes-warm-compaction) | 75 | Apache-2.0 | 2026-11-17 |
| [`REMvisual/claude-handoff`](https://github.com/REMvisual/claude-handoff) | 75 | MIT | 2026-11-11 |
| [`caura-ai/caura-cross-fleet-gov`](https://github.com/caura-ai/caura-cross-fleet-gov) | 72 | MIT | 2026-09-14 |
| [`wunderlabs-dev/claudebin.com`](https://github.com/wunderlabs-dev/claudebin.com) | 71 | MIT | 2026-06-23 |
| [`hyperb1iss/sibyl`](https://github.com/hyperb1iss/sibyl) | 70 | Apache-2.0 | 2026-11-16 |
| [`jhammant/ClaudeHistoryMCP`](https://github.com/jhammant/ClaudeHistoryMCP) | 69 | MIT | 2026-09-20 |
| [`oliver-kriska/scribe`](https://github.com/oliver-kriska/scribe) | 69 | MIT | 2026-11-17 |
| [`sshahzaiib/agy-bridge`](https://github.com/sshahzaiib/agy-bridge) | 68 | MIT | 2026-10-28 |
| [`aytzey/showagent`](https://github.com/aytzey/showagent) | 64 | MIT | 2026-11-16 |
| [`babarot/claude-recall`](https://github.com/babarot/claude-recall) | 64 | MIT | 2026-11-14 |
| [`blader/baton`](https://github.com/blader/baton) | 62 | MIT | 2026-06-14 |
| [`oldskultxo/aictx`](https://github.com/oldskultxo/aictx) | 59 | MIT | 2026-06-17 |
| [`agentsea/flashbacker`](https://github.com/agentsea/flashbacker) | 57 | MIT | 2026-01-14 |
| [`agent-session-protocol/universal-session-log`](https://github.com/agent-session-protocol/universal-session-log) | 56 | MIT | 2026-11-07 |
| [`jo-inc/pi-reflect`](https://github.com/jo-inc/pi-reflect) | 56 | MIT | 2026-10-11 |
| [`Dicklesworthstone/post_compact_reminder`](https://github.com/Dicklesworthstone/post_compact_reminder) | 55 | NOASSERTION | 2026-10-14 |
| [`gemron/Termexo`](https://github.com/gemron/Termexo) | 55 | MIT | 2026-11-04 |
| [`Brucee/tokensaver`](https://github.com/Brucee/tokensaver) | 54 | MIT | 2026-10-27 |
| [`vitaliyhayda/claude-transplant`](https://github.com/vitaliyhayda/claude-transplant) | 54 | MIT | 2026-11-15 |
| [`Eversmile12/sharedcontext`](https://github.com/Eversmile12/sharedcontext) | 50 | 無 | 2026-02-24 |
| [`nicknisi/sessions`](https://github.com/nicknisi/sessions) | 50 | MIT | 2026-11-16 |
| [`HizTam/codex-history-viewer`](https://github.com/HizTam/codex-history-viewer) | 49 | MIT | 2026-11-12 |
| [`talayash/agentrium`](https://github.com/talayash/agentrium) | 49 | MIT | 2026-11-14 |
| [`ej31/claude-session-tracker`](https://github.com/ej31/claude-session-tracker) | 48 | MIT | 2026-11-04 |
| [`josephyaduvanshi/claude-history-manager`](https://github.com/josephyaduvanshi/claude-history-manager) | 48 | NOASSERTION | 2026-04-26 |
| [`sinzin91/search-sessions`](https://github.com/sinzin91/search-sessions) | 48 | MIT | 2026-10-25 |
| [`PolinniZhong/dsh-session-workbench`](https://github.com/PolinniZhong/dsh-session-workbench) | 47 | MIT | 2026-09-28 |
| [`tstockham96/engram`](https://github.com/tstockham96/engram) | 47 | MIT | 2026-10-16 |
| [`win4r/memory-lancedb-pro-skill`](https://github.com/win4r/memory-lancedb-pro-skill) | 47 | 無 | 2026-11-16 |
| [`braincompany/sessiongrep`](https://github.com/braincompany/sessiongrep) | 45 | Apache-2.0 | 2026-11-09 |
| [`WSL043/dsh-chat-manager`](https://github.com/WSL043/dsh-chat-manager) | 45 | MIT | 2026-11-17 |
| [`xiaoyuyu6420/dsh-backup`](https://github.com/xiaoyuyu6420/dsh-backup) | 45 | MIT | 2026-11-10 |
| [`redstone-md/Continuum`](https://github.com/redstone-md/Continuum) | 44 | MIT | 2026-08-16 |
| [`Ryu0118/ctxmv`](https://github.com/Ryu0118/ctxmv) | 44 | MIT | 2026-11-17 |
| [`valpere/session-indexer`](https://github.com/valpere/session-indexer) | 42 | Apache-2.0 | 2026-11-16 |
| [`Manavarya09/relay`](https://github.com/Manavarya09/relay) | 41 | MIT | 2026-09-15 |
| [`vulcanshen/clerk`](https://github.com/vulcanshen/clerk) | 40 | GPL-3.0 | 2026-11-03 |
| [`LittleBlackTong/dsh-plugin-memory`](https://github.com/LittleBlackTong/dsh-plugin-memory) | 39 | MIT | 2026-11-17 |
| [`Qinling-Melon-Farmers/dsh-memoir`](https://github.com/Qinling-Melon-Farmers/dsh-memoir) | 39 | Apache-2.0 | 2026-11-06 |
| [`rochecompaan/pi-context-paging`](https://github.com/rochecompaan/pi-context-paging) | 38 | MIT | 2026-11-16 |
| [`obrenoalvim/zero-drift`](https://github.com/obrenoalvim/zero-drift) | 37 | MIT | 2026-10-22 |
| [`rcarmo/memento`](https://github.com/rcarmo/memento) | 37 | MIT | 2026-11-16 |
| [`gautamgpt1/agent-session-browser`](https://github.com/gautamgpt1/agent-session-browser) | 36 | MIT | 2026-09-12 |
| [`hetpatel-11/agent-hop`](https://github.com/hetpatel-11/agent-hop) | 36 | MIT | 2026-08-31 |
| [`stefan-jansen/coding-agent-toolkit`](https://github.com/stefan-jansen/coding-agent-toolkit) | 36 | MIT | 2026-10-27 |
| [`Haustorium12/continuity-v2`](https://github.com/Haustorium12/continuity-v2) | 35 | MIT | 2026-06-14 |
| [`p32929/ccheckpoints`](https://github.com/p32929/ccheckpoints) | 35 | MIT | 2026-11-18 |
| [`zebbern/agent-collab`](https://github.com/zebbern/agent-collab) | 35 | Apache-2.0 | 2026-09-29 |
| [`taxueseek/session-digger`](https://github.com/taxueseek/session-digger) | 34 | ISC | 2026-11-15 |
| [`majiayu000/remem`](https://github.com/majiayu000/remem) | 33 | MIT | 2026-11-18 |
| [`waterside0219/session-forge`](https://github.com/waterside0219/session-forge) | 33 | MIT | 2026-06-11 |
| [`Dumpling-Dragon/memory-hub`](https://github.com/Dumpling-Dragon/memory-hub) | 31 | MIT | 2026-09-08 |
| [`lukasz-fedor/claude-memory-template`](https://github.com/lukasz-fedor/claude-memory-template) | 31 | MIT | 2026-03-05 |
| [`Sigillion-AI/sigillion`](https://github.com/Sigillion-AI/sigillion) | 31 | NOASSERTION | 2026-11-10 |
| [`smaramwbc/statewave-multi-agent-memory`](https://github.com/smaramwbc/statewave-multi-agent-memory) | 31 | Apache-2.0 | 2026-11-16 |
| [`noluyorAbi/claude-code-recap`](https://github.com/noluyorAbi/claude-code-recap) | 30 | MIT | 2026-08-08 |
| [`PerryLink/dsh-checkpoint-rewind`](https://github.com/PerryLink/dsh-checkpoint-rewind) | 30 | Apache-2.0 | 2026-11-13 |
| [`Kaseban/baton`](https://github.com/Kaseban/baton) | 29 | Apache-2.0 | 2026-10-16 |
| [`dunova/ContextGO`](https://github.com/dunova/ContextGO) | 28 | AGPL-3.0 | 2026-09-26 |
| [`myyimu/codex-session-transfer`](https://github.com/myyimu/codex-session-transfer) | 28 | MIT | 2026-08-21 |
| [`Tk1777-sy/-work-journal-skill`](https://github.com/Tk1777-sy/-work-journal-skill) | 28 | MIT | 2026-06-17 |
| [`pqant/claude-continuity`](https://github.com/pqant/claude-continuity) | 27 | MIT | 2026-11-17 |
| [`samfoy/pi-session-search`](https://github.com/samfoy/pi-session-search) | 27 | MIT | 2026-10-29 |
| [`wrg32786/aigent-os`](https://github.com/wrg32786/aigent-os) | 26 | MIT | 2026-11-17 |
| [`Mahiler1909/claudepath`](https://github.com/Mahiler1909/claudepath) | 25 | MIT | 2026-07-03 |
| [`polyxmedia/mnemos`](https://github.com/polyxmedia/mnemos) | 24 | MIT | 2026-11-07 |
| [`basicmachines-co/basic-memory-skills`](https://github.com/basicmachines-co/basic-memory-skills) | 23 | 無 | 2026-04-20 |
| [`bledden/claude-recall-plugin`](https://github.com/bledden/claude-recall-plugin) | 23 | MIT | 2026-09-09 |
| [`kartikkabadi/pi-handoff`](https://github.com/kartikkabadi/pi-handoff) | 23 | NOASSERTION | 2026-10-24 |
| [`Chang-Tong/dsh-unified-context`](https://github.com/Chang-Tong/dsh-unified-context) | 22 | MIT | 2026-11-09 |
| [`rmk40/opencode-session-recall`](https://github.com/rmk40/opencode-session-recall) | 22 | MIT | 2026-08-31 |
| [`sanirudh17/herdr-agent-handoff`](https://github.com/sanirudh17/herdr-agent-handoff) | 22 | MIT | 2026-09-30 |
| [`vibheksoni/session-export`](https://github.com/vibheksoni/session-export) | 22 | MIT | 2026-10-27 |
| [`vladar107/claudescope`](https://github.com/vladar107/claudescope) | 22 | MIT | 2026-11-14 |
| [`Awenforever/CoDeepSeedeX`](https://github.com/Awenforever/CoDeepSeedeX) | 21 | MIT | 2026-06-20 |
| [`ccompactor/ccompactor`](https://github.com/ccompactor/ccompactor) | 21 | MIT | 2026-09-14 |
| [`staticroostermedia-arch/engram`](https://github.com/staticroostermedia-arch/engram) | 21 | AGPL-3.0 | 2026-08-07 |
| [`trytofly94/handoff-compact`](https://github.com/trytofly94/handoff-compact) | 21 | MIT | 2026-10-03 |
| [`djannot/code-session-memory`](https://github.com/djannot/code-session-memory) | 20 | 無 | 2026-11-04 |
| [`handyutils/sctxx`](https://github.com/handyutils/sctxx) | 20 | Apache-2.0 | 2026-09-11 |
| [`neverinfamous/memory-journal-mcp`](https://github.com/neverinfamous/memory-journal-mcp) | 20 | MIT | 2026-11-17 |
| [`TStansel/handoff`](https://github.com/TStansel/handoff) | 20 | MIT | 2026-05-24 |
| [`avksp/agent-lifecycle-kit`](https://github.com/avksp/agent-lifecycle-kit) | 19 | Apache-2.0 | 2026-11-17 |
| [`codexstar69/pi-lcm`](https://github.com/codexstar69/pi-lcm) | 19 | MIT | 2026-04-02 |
| [`tad-hq/universal-session-viewer`](https://github.com/tad-hq/universal-session-viewer) | 19 | AGPL-3.0 | 2026-03-23 |
| [`transcendr/jevpact`](https://github.com/transcendr/jevpact) | 19 | NOASSERTION | 2026-11-02 |
| [`henba1/scrubjay`](https://github.com/henba1/scrubjay) | 18 | NOASSERTION | 2026-11-14 |
| [`andrewbakercloudscale/claude-burst`](https://github.com/andrewbakercloudscale/claude-burst) | 17 | MIT | 2026-11-17 |
| [`jthack/dm-other-claudes`](https://github.com/jthack/dm-other-claudes) | 17 | 無 | 2026-04-12 |
| [`Vinyl-Davyl/hermes`](https://github.com/Vinyl-Davyl/hermes) | 17 | MIT | 2026-09-28 |
| [`Adamchanadam/agent-handoff-kit`](https://github.com/Adamchanadam/agent-handoff-kit) | 16 | MIT | 2026-11-15 |
| [`michielinksee/linksee-memory`](https://github.com/michielinksee/linksee-memory) | 16 | MIT | 2026-11-16 |
| [`Mr8BitHK/claude-terminal`](https://github.com/Mr8BitHK/claude-terminal) | 16 | MIT | 2026-04-15 |
| [`remembra-ai/remembra`](https://github.com/remembra-ai/remembra) | 16 | MIT | 2026-11-14 |
| [`Sonovore/claude-code-handoff`](https://github.com/Sonovore/claude-code-handoff) | 16 | MIT | 2026-06-03 |
| [`tim-hua-01/cc_transcript_viewer`](https://github.com/tim-hua-01/cc_transcript_viewer) | 16 | MIT | 2026-11-10 |
| [`AgentWorkforce/relayhistory`](https://github.com/AgentWorkforce/relayhistory) | 15 | MIT | 2026-11-17 |
| [`AliceLJY/recallnest`](https://github.com/AliceLJY/recallnest) | 15 | MIT | 2026-11-13 |
| [`ay-bh/chat-history`](https://github.com/ay-bh/chat-history) | 15 | MIT | 2026-11-12 |
| [`cote-star/agent-chorus`](https://github.com/cote-star/agent-chorus) | 15 | MIT | 2026-09-28 |
| [`ingram-technologies/claude-git-sessions`](https://github.com/ingram-technologies/claude-git-sessions) | 15 | 無 | 2026-06-06 |
| [`jungjaehoon-lifegamez/MAMA`](https://github.com/jungjaehoon-lifegamez/MAMA) | 15 | MIT | 2026-11-17 |
| [`kvsankar/agent-history`](https://github.com/kvsankar/agent-history) | 15 | MIT | 2026-10-15 |
| [`overbit/fast-jev-compaction-opencode`](https://github.com/overbit/fast-jev-compaction-opencode) | 15 | MIT | 2026-10-26 |
| [`wangcangshu/codex-desktop-thread-rescue`](https://github.com/wangcangshu/codex-desktop-thread-rescue) | 15 | 無 | 2026-05-04 |
| [`AxmeAI/axme-code`](https://github.com/AxmeAI/axme-code) | 14 | MIT | 2026-11-02 |
| [`hotalexnet/agent-checkpoint`](https://github.com/hotalexnet/agent-checkpoint) | 14 | MIT | 2026-09-21 |
| [`Stormix/transcripts-mcp`](https://github.com/Stormix/transcripts-mcp) | 14 | MIT | 2026-11-09 |
| [`IlyaGorsky/memory-toolkit`](https://github.com/IlyaGorsky/memory-toolkit) | 13 | MIT | 2026-11-01 |
| [`SynapseLayer/synapse-layer`](https://github.com/SynapseLayer/synapse-layer) | 13 | Apache-2.0 | 2026-11-04 |
| [`AgentAirlift/AgentAirlift`](https://github.com/AgentAirlift/AgentAirlift) | 12 | MIT | 2026-06-30 |
| [`archid21/whatsnext`](https://github.com/archid21/whatsnext) | 12 | MIT | 2026-11-17 |
| [`Davidyooo/session-recall`](https://github.com/Davidyooo/session-recall) | 12 | 無 | 2026-07-02 |
| [`dotneet/agent-session-view`](https://github.com/dotneet/agent-session-view) | 12 | 無 | 2026-02-03 |
| [`lennartschoch/opencode-cache-compact`](https://github.com/lennartschoch/opencode-cache-compact) | 12 | MIT | 2026-09-24 |
| [`leox255/termem`](https://github.com/leox255/termem) | 12 | 無 | 2026-07-19 |
| [`thepushkarp/handoff`](https://github.com/thepushkarp/handoff) | 12 | MIT | 2026-03-01 |
| [`wangjohn/agent-archive`](https://github.com/wangjohn/agent-archive) | 12 | MIT | 2026-11-05 |
| [`wilbeibi/herdr-catchup`](https://github.com/wilbeibi/herdr-catchup) | 12 | MIT | 2026-09-28 |
| [`context-transfer-protocol/ctp-spec`](https://github.com/context-transfer-protocol/ctp-spec) | 11 | NOASSERTION | 2025-09-20 |
| [`huangpufan/SSOT-CONTEXT`](https://github.com/huangpufan/SSOT-CONTEXT) | 11 | MIT | 2026-11-16 |
| [`agentkitai/lore`](https://github.com/agentkitai/lore) | 10 | MIT | 2026-11-01 |
| [`beowulf11/pi-scroll`](https://github.com/beowulf11/pi-scroll) | 10 | MIT | 2026-05-25 |
| [`bvolpato/omnisession`](https://github.com/bvolpato/omnisession) | 10 | MIT | 2026-11-17 |
| [`Capetlevrai/resume-claude-codex-grok`](https://github.com/Capetlevrai/resume-claude-codex-grok) | 10 | MIT | 2026-08-29 |
| [`dahshanlabs/klypix-mcp`](https://github.com/dahshanlabs/klypix-mcp) | 10 | MIT | 2026-11-09 |
| [`danyuchn/history-find`](https://github.com/danyuchn/history-find) | 10 | MIT | 2026-09-06 |
| [`dongsheng123132/task-passport`](https://github.com/dongsheng123132/task-passport) | 10 | MIT | 2026-11-06 |
| [`falling-ts/dsh-force-compact`](https://github.com/falling-ts/dsh-force-compact) | 10 | MIT | 2026-11-10 |
| [`FlineDev/Recall`](https://github.com/FlineDev/Recall) | 10 | MIT | 2026-09-29 |
| [`john-walks-slow/dsh-clear-mind`](https://github.com/john-walks-slow/dsh-clear-mind) | 10 | MIT | 2026-10-26 |
| [`live9369/session-handoff-skill`](https://github.com/live9369/session-handoff-skill) | 10 | 無 | 2026-06-11 |
| [`LucioLiu/relic`](https://github.com/LucioLiu/relic) | 10 | NOASSERTION | 2026-07-23 |
| [`mantra-hq/mantra-releases`](https://github.com/mantra-hq/mantra-releases) | 10 | 無 | 2026-08-28 |
| [`Vvkmnn/claude-praetorian-mcp`](https://github.com/Vvkmnn/claude-praetorian-mcp) | 10 | MIT | 2026-03-16 |
| [`yazcaleb/rses`](https://github.com/yazcaleb/rses) | 10 | 無 | 2026-03-26 |
| [`z2z23n0/agent-capsule`](https://github.com/z2z23n0/agent-capsule) | 10 | Apache-2.0 | 2026-07-23 |

</details>

### 4.5 非 GitHub 網址、套件與產品清單（帳本收錄共 79 筆，不含星數比較）

下列工具於官網、HN、Exa、npm 或中文網頁實查收錄（部分同時擁有 GitHub repo 如 `leox255/termem`／`dahshanlabs/klypix-mcp`，已於上表以 repo 驗證，下表保留原始收錄入口供查對）：

- **獨立產品／雲端平台／桌面服務**：`aviator.co/runbooks`（Shareable Claude Code Sessions）、`capacitor.kurrent.io`（Kurrent Capacitor 跨 agent 錄製與交接）、`clinch.sh`（Warp 分支本地 agent session 管理）、`codeform.io`、`crosshead.sh`、`datamcp.app`、`devctrl.dev`、`docs.beacon.sh`、`docs.otty.sh`、`docs.syncropel.com`、`dullnote.com`、`engram-ai.dev`、`groundtrack.dev`、`hadronmemory.com`、`hansard.dev`、`harkstudio.io`、`hiperyon.com`、`klypix.com`、`kraklabs.com/mie`、`lanes.sh`、`memoryplugin.com`、`oacp.dev`、`opencheckpoint.org`、`papercompute.com`、`ponymux.com`、`recallmcp.com`、`recallplugin.dev`、`reinstate.dev`、`relai.fyi`（Claude Code -> Codex 桌面交接工具）、`snipara.com`、`spec-weave.com`、`termem.com`、`termic.dev`、`totalmemory.dev`、`unabyss.com`、`usespaces.dev`、`withadmiral.com`、`agentproto.sh`、`atomicagent.io`、`context-transfer.vercel.app`
- **CLI／npm／PyPI／VS Code／社群專案名**：`@ai2070/memex`、`@domencai/dsh-memory`、`@eagle4302/dsh-session-relay`、`@echomem/mcp`、`@event4u/agent-switch`、`@virtualorz/recap`、`agenttm`、`ccassist`、`ccshare`、`chat-memory-mcp-vscode`、`claude-handoff-pypi`、`codeyam`、`contextify.sh`、`contextpool`、`continuity-vscode`、`coolmem`、`crossagentmemory-pypi`、`cursor-history`、`gps-memory`、`mao-canvas`、`memmy-agent`、`mother-terminal`、`moxie-claude`、`mpai`、`recall-agents-pypi`、`reflect-memory-mcp`、`resumecontext`、`samemind`、`scmd`、`scritty`、`session-indexer`、`sharedmemory-mcp-server`、`snipara`、`steroid-kit`、`subspace-ai`、`termi-protocol`、`trinity-framework-core`、`vokal`、`xmemo`
- **另註**：帳本中另有 **181 個 `<10★` 之早期或長尾 GitHub repo**（例如 `swarno1996/handoff-pill`、`1beenlee/universal-context-handoff`、`didvc/web-to-cc`、`davo20019/relevo`、`ptreezh/stigmergy-CLI-Multi-Agents`、`kwyeh-cl/agent-memory`、`yunfeng008/codebaton` 等，完整清單存於 `T1-ledger.json`）。

## 五、查不到的管道與原因、拿不準的名字

### 5.1 查不到的管道與原因
- **全數 14 組無任何網路或限速失敗（`errors=[]`）**：`github-topic`、`github-keyword`、`awesome`、`skills-sh`、`npm`、`mcp-registry`、`hn`、`exa` 以及 `web-zh`／`web-en`／`producthunt`／`related` 皆成功完成呼叫。
- **腳本內建查詢條件限制（回傳 0 筆而非錯誤）**：
  1. **中文關鍵字組（第 1 組、第 13 組）**：`skills-sh` 在去除通用詞彙後因無足夠英文關鍵字自動不查（0 筆）；`mcp-registry` 因規定需含 3 字元以上英文字母自動不查（0 筆）；`github-topic` 在中文片語下僅能命中寬泛單詞 topic（如 `agent`）。
  2. **非 AI 一般詞彙組（第 3、12 組）**：`awesome` 清單於第 11、12 組回傳 0 筆（無對應 awesome 專欄）。
  3. **平台回傳上限**：`exa` 匿名模式每組最多回傳 10 筆；`mcp-registry` 僅依單一關鍵字比對名稱子字串（例如只送出 `session` 或 `context`），雜訊較高需人工逐筆篩選。

### 5.2 拿不準的名字（邊界案例與拆註理由）

| 名稱 | 實測星數 | 拿不準的原因與處置建議 |
|---|---:|---|
| [`WorldFlowAI/everything-claude-code`](https://github.com/WorldFlowAI/everything-claude-code) | 6,558 | **疑似非官方鏡像／重複**：無授權、停更於 2026-01-23，內容實為 `affaan-m/ECC`（everything-claude-code）的早期複製品，不建議視為獨立產品。 |
| [`mattpocock/skills`](https://github.com/mattpocock/skills) | 326,805 | **複合技能包**：收錄多個工程技能，僅其中一個 `./skills/productivity/handoff/SKILL.md` 負責壓縮對話並產生跨 session 交接文件；星數反映整套技能庫而非單一交接工具。 |
| [`softaworks/agent-toolkit`](https://github.com/softaworks/agent-toolkit) | 2,695 | **複合技能包**：整體為通用開發技能包，內含單一 `session-handoff` skill。 |
| [`daymade/claude-code-skills`](https://github.com/daymade/claude-code-skills) | 1,537（註：來自 group 10 查核） | **複合技能包**：一般 Claude Code 技能市集／合集，非專注對話紀錄或記憶工具，未計入主名單 `★1,000+` 新增。 |
| [`openai/codex-plugin-cc`](https://github.com/openai/codex-plugin-cc) | 35,200 | **主功能偏委派／審查**：主用途為在 Claude Code 內呼叫 Codex 進行 code review 或委派任務，但內建 `/codex:transfer` 會讀取 `~/.claude/projects/.../*.jsonl` 轉換為可續聊 Codex thread，屬半重疊。 |
| [`siteboon/claudecodeui`](https://github.com/siteboon/claudecodeui) | 14,669 | **主功能偏 Web/行動端遙控介面**：主打多端 UI 操作 Claude Code／OpenCode／Cursor CLI／Codex，但其核心確實自動掃描 `~/.claude` 歷史工作階段並支援恢復與外掛交接（如 `cloudcli-plugin-ccx`）。 |
| [`MemMachine/MemMachine`](https://github.com/MemMachine/MemMachine) | 3,090 | **偏通用 AI Agent 記憶層**：定位接近一般通用型 agent memory 基礎設施，非專讀 coding agent 對話日誌，但官方提供 Cursor／Claude Desktop MCP 支援。 |
| [`fujibee/agmsg`](https://github.com/fujibee/agmsg) | 1,591 | **偏跨 agent 即時傳訊**：讓 Claude Code、Codex、Gemini、Copilot 透過 SQLite 彼此發訊協作，屬於 live inter-agent messaging 而非事後搜尋或壓縮恢復。 |
| [`ClaudioDrews/memory-os`](https://github.com/ClaudioDrews/memory-os) | 1,396 | **單一 agent 專屬**：專為 Hermes Agent 打造的 7 層記憶系統（含 FTS5 session 搜尋），不直接支援跨 coding agent 交接。 |
| [`omdsh-dev/dsh-mnemon`](https://github.com/omdsh-dev/dsh-mnemon) | 1,030 | **單一 harness 專屬**：專為 DeepSeek Harness（dsh）設計的記憶策略套件；類似的單一 harness 專屬套件還有 `Nwflower/dsh-chat-import`（★317，雖支援從 25+ agent 匯入但目標限 DSH）、`Totoro-qaq/dsh-plugin-bridge`（★168）等。 |
| `MemTether` / `AIKB` / `brigade-cli` / `cc-sessions-cli` / `claude-mem-handoff` | — | **僅見於第 12 組網頁搜尋摘要**：未附明確 GitHub `owner/repo` 連結且未跨出多個獨立管道佐證，待進一步查證來源倉庫後再決定是否納入帳本。 |
