> 由 Gemini 4 Hydrogen（high）經 agy_cli 管道完成，主控 Claude 驗收：帳本 status 是「可以停」，抽查 6 個 repo 的星數、授權、封存與最後 push（gh api，2026-11-16）都一致。其餘第三方說法以報告第 5 節為準。

# 跨模型、跨應用的多代理分工與編排：飽和式調研報告

調研日期：2026-11-16
調研帳本：只留在當時那台的暫存資料夾（multi-agent-ledger.json），沒有進 repo；執行者：Gemini 4 Hydrogen high，經 agy_cli 派出（dispatch.py agy）
判斷標準：能讓一個主控 agent（例如 Claude Code）把子任務派給不同供應商的模型或不同的 agent CLI（例如 Gemini CLI、Antigravity `agy`、Codex CLI、OpenCode、Aider），收回結果再驗收的工具／框架／路由器／看板；單一供應商 SDK 或純聊天介面多模型切換不納入。

---

## 1. `status` 輸出、停止點與管道狀況

### 1.1 停止條件與收斂過程
- **總計組數與收錄規模**：共執行 **49 組**關鍵字查詢，涵蓋跨 CLI 委派、MCP 橋接、多模型編排器、模型路由器／額度容錯閘道、視覺化任務看板、ACP（Agent Client Protocol）生態、跨模型審查與共識議會、Antigravity (`agy`) / OpenCode / Aider / Codex CLI 子生態、中文社群實作與 Product Hunt。累計記帳 **1,251 個不重複的名字**。
- **第幾組停**：於 **第 49 組**停止（`sweep.py status` 顯示「`連續 3 組沒有新名字（要 3 組）：可以停`」）。
- **最後連續 3 組沒有新名字的組別**：
  1. 第 47 組：`beehiveinnovations/pal-mcp-server GuDaStudio/codexmcp`（2 個名字，新的 0 個）
  2. 第 48 組：`BloopAI/vibe-kanban OrchestratorInc/agent-orchestrator`（3 個名字，新的 0 個）
  3. 第 49 組：`cheaper-inference/OmniRoute router-for-me/CLIProxyAPI`（2 個名字，新的 0 個）
- **整次調研補充管道覆蓋**：
  - 英文網頁搜尋（`web-en`）：幾乎每組皆執行。
  - 中文網頁搜尋（`web-zh`）：第 5 組「多模型 多代理 分工 編排」執行。
  - Product Hunt（`producthunt`）：透過 `site:producthunt.com` 搜尋取得 `MAO`、`Mozzie`。
  - 關聯延伸（`related`）：對高星數代表與 awesome 清單執行，包含 `OrchestratorInc/agent-orchestrator`、`BeehiveInnovations/pal-mcp-server`、`awslabs/cli-agent-orchestrator`、`bradagi/awesome-cli-coding-agents`、`andyrewlee/awesome-agent-orchestrators`、`josephhampton/awesome-gemini-cli-subagents`。

### 1.2 查不到的管道與限制原因
本次 8 個腳本管道（`github-topic`、`github-keyword`、`awesome`、`skills-sh`、`npm`、`mcp-registry`、`hn`、`exa`）與人工搜尋管道皆可正常連線，**未發生連不上或缺少 token 的錯誤**；僅有以下與關鍵字語言／管道機制相關的結構性限制：
1. **中文組（第 5 組「多模型 多代理 分工 編排」）在 `skills-sh` 與 `mcp-registry` 跳過不查**：`sweep.py` 實作規定拿掉通用字後無英文關鍵字時 `skills.sh` 回傳 0 筆（提示「拿掉通用字後沒有關鍵字，skills.sh 不查」）；`mcp-registry` 因沒有 3 字元以上的英文字而跳過不查（提示「關鍵字沒有 3 個字元以上的英文字，Registry 不查」）。
2. **`mcp-registry` 比對限制**：該 API 只接受單一英文字母子字串比對（例如只送出 `code`、`multi`、`bridge`、`pal`、`gemini`），回傳結果雜訊較高，需逐一過濾。
3. **`verify` 個別失效目標**：先前網頁搜尋曾提及但經 `sweep.py verify` 實測回傳 `HTTP 404` 無法驗證存在的專案（如 `shelakh/gemini-bridge`、`agentsmesh/agentsmesh`），已排除於下表之外。

### 1.3 `sweep.py status` 完整輸出
```text
總共 1251 個不重複的名字；連續 3 組沒有新名字（要 3 組）：可以停
第 1 組「claude code delegate to gemini cli」：41 個名字，新的 41 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：chenhg5/agencycli, greenpolo/cc-multi-cli-plugin, markfulton/claude-antigravity-agents, sshahzaiib/agy-bridge, pvjbuilds/delegate-router, ankitdotgg/making-gemini-useful-with-claude, sakibsadmanshajib/antigravity-plugin, davdittrich/delegate-agy, pcx-wave/gemini-skill, rauls-kjarners/claude-to-agy, zqkra/plano, chen941008/claude-code-antigravity-bridge, pymodel/claude-agy-mcp, axisworkflow/axis, jochenyang/agent-comm-hub, salehb1/shunt-anywhere, raedberjaoui/vibecoders-mcp, tentemujin/delegate, alchemiststudiosdotai/claude-code-gemini-manager-skill, wenyuchiou/gemini-delegate-skill, anastasiyaw/codex-claude-code-config, shalomeir/gemini-cli-skill-codex, yuting0624/antigravity-for-claude-code, finolabs/agybird, stevehuang0115/crewly, jamubc/gemini-mcp-tool, m-ghalib/gemini-plugin-cc, joshidikshant/devsquad, rbinar/cli-dispatch, 0x0funky/vibehq-hub …
第 2 組「multi-model agent orchestration cli」：55 個名字，新的 54 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related
  新：ezinsightsinc/ezcoworker, r-design-j/tri-party-framework, vincemakes/model-boss, shttty/smart-cascade, autopus-ai/autopus-adk, hajdu-patrik/trirouter, launchapp-dev/animus-cli, ragavrida/mmcp, giacomosaccaggi/mithril, canoo/agent-nexus, crtxai/crtx, aproto9787/codex-bridge, dubsopenhub/swarm-command, joogy06/agent-foundry, yptang98/costmarshal, sshkeda/pi-council, mastaan66/foreman, istb16/dev-orchestra, zcyynl/claw-multi-agent, nuttapongpun/orchestration-workflow, tellang/triflux, multi-agent-ecosystem/multi-agent-pipeline, paperclipai/paperclip, ruvnet/agentic-flow, ai.getvda/oauth-multi-llm-orchestrator, ai.getvda/authenticated-multi-llm-agent, imran-siddique/agent-os, ducks/lok, llm-use, longlifeio/aog …
第 3 組「agent cli bridge mcp」：27 個名字，新的 27 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：raysonmeng/agent-bridge, elyin/codex-bridge, howardpen9/tmux-bridge-mcp, elyin/gemini-bridge, maksimzayats/acodex, lonetis/claudeleaf, ranausmanai/agentbridge, tizerluo/zcode-open-bridge, varadfromeast/codex-agy-bridge, xyva-yuangui/agent-bridge, agentclientprotocol/claude-agent-acp, thanhdo257205/mcp-bridge, buidangminh23/codex-mcp-bridge, nicobailon/pi-mcp-adapter, leonardsellem/codex-subagents-mcp, swarmclawai/swarmclaw, lailai258/agent-bridge-mcp, blackaxgit/agent-mcp-hub, mateusoliveirab/mcp-workflow-cli-bridge, rodolfonobrega/agentbridge, joaoberne/cli-bridge-mcp, qantara, lakpriya1s/agent-rack, prakshal-jain/agent-bridge, walkindude/cli-bridge, luxuzhou/agent-fleet, llm-cli-gateway
第 4 組「cli to cli delegation」：38 個名字，新的 36 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related
  新：kdcokenny/opencode-background-agents, xiaolai/cc-suite, pymodel/claude-architect, ginkida/agent-dispatch, eddiearc/codex-delegator, virtuosotravlr/cowork-bridge, jesserweigel/toryo, carlosduplar/claude-gemini-delegation, shaokeyibb/agent-delegation, tylersue/claude-grok-delegation, jaimejunr/polyagent-mcp, lovistickk/codex-delegation-skill, csoai-org/agent-delegation-mcp, jostophe-021/mcp-cross-model-delegation, askbudi/roundtable, nikosokratous/agentctl, usemerlin.ai, seigo2016/claude-code-delegate, singhutsav5502/glider, kaiukov/agent-delegation, beehiveinnovations/pal-mcp-server, ai-dispatch, AgentMesh, subagent-cli, aj47/zen-mcp-server, david-strejc/zen-mcp-server, izzoa/unison-mcp-server, parvin528/zen-mcp-server, shelpuk-ai-technology-consulting/pally-mcp-server, sebyddd/zen-mcp-server …
第 5 組「多模型 多代理 分工 編排」：8 個名字，新的 8 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh, producthunt
  新：@qwen-code/arena-agent, dingminhua/dsh-subagent-default-model, osanoai/multicli, GuDaStudio/codexmcp, religa/multi_mcp, KimYx0207/Claudecode-Codex-Gemini, MAO, Mozzie
第 6 組「model router coding agent cli」：31 個名字，新的 29 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：portkey-ai/gateway, maximhq/bifrost, weave-os/router, duolahypercho/codex-router, tzachbon/claude-model-router-hook, kochc/opencode-llm-proxy, ubiomni/mrouter, iamaamir/pi-bifrost, dengmengmian/muxlayer, hex/claude-council, codeking-ai/cligate, nidhi-singh02/agent-router, aunysillyme/model-orchestrator, wzyxdwll/ccgx-workflow, jswortz/gemini-model-router, zx1160763849-hash/codex-cost-router-skills, skills-book/task-router, wangmiaozero/laya-router-skill, i-smiling-buddha/smart-model-router-skill, birbirbrian/codex-task-router, musistudio/claude-code-router, svtlv/agrouter, gargpratyush/jev-router, higress-group/hiroute, code-router/coderouter, qyn.io, anyrouter, vibe-kanban, claude-squad
第 7 組「multi-agent coding kanban board」：26 個名字，新的 25 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：dualface/kander, makifbaysal/tasktrooper, rasimme/flowboard, latand/delegatus, backmeupplz/agentboard, weichenleeeee123/coopagents, pranjal-joshi/claude-crew, keepconcentration/hermes-kanban-fleet, abpai/agent-kanban, breathi3552/paseo-kanban, zorcec/vibeflow, jantcz/cli-kanban, battysh/batty, agentsmesh/agentsmesh, kanzai.io, leodavinci1/kanbots, agentkan.ai, cordane.ai, oh-my-symphony, kanship.com, stilero/bankan, kdlbs/kandev, cx994/ccb, GreenSheep01201/Claw-Kanban, untra/operator
第 8 組「cross-model code review cli mcp」：34 個名字，新的 34 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：delimit-ai/delimit-mcp-server, kinggyusuh/ultracodex, robertoecf/adversarial-review, berrzebb/quorum, eshwarvijay/secondmate, 199-biotechnologies/claude-skill-gpt-pro, zandereins/hydra, hamza-ali-shahjahan/claudex, aarontzeng/dev-lead, modulastack/modula-relay, raichominev/concilium, razzant/claudexor, lploc94/cross-review, futureisinpast/mcp-agent-switchboard, arcobaleno64/agy-plugin-cc, aldenysq/agents-connector, setech-pl/agentctl, hydr0nefn/claude-bridges, chaseai-yt/claudex-loop, tsmura/grill-me-codex, tommasinigiovanni/conclave, agentclientprotocol/codex-acp, luckeyfaraday/master-workflow, makedirectory/modelpeer, brettchangus/cross-review, subvertnormality/paranoia, Joint Chiefs, ryderfreeman4logos/cli-sub-agent, marcelo-henry/mcp-cli-tools, atompilot/claude-code-cross-review …
第 9 組「agent client protocol codex claude gemini」：12 個名字，新的 11 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：opensource03/harnss, mvanhorn/paperclip-plugin-acp, allvegetable/acp-bridge, codingagentprotocol/capd, interjc/subagent-team-skills, mrlesk/agents-council, gilbarbara/agent-hub-mcp, useagentos.dev, syntax-syndicate/Agents-Orchestrator, compozy, SharkBay
第 10 組「ai coding agent tmux swarm」：16 個名字，新的 16 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：twigpine/agentvm, celsiusm/jarvis-workspace, miopea/swarm-legacy, mehmetcanfarsak/agentswarm, 6missedcalls/swarmux, yangliu2060/startmux, zaxbyhub/opencode-swarm, desplega-ai/agent-swarm, mtomcal/swarm, omux.sh, clemens33/ae, standardagents/dmux, dubsopenhub/terminal-stampede, ClawTeam, Soein/swarmesh, tmdgusya/gemini-swarm
第 11 組「claude code spawn codex gemini」：18 個名字，新的 18 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：lonetis/agentor, naman10parikh/agentgrid, rlondner/codespawn, jayphen/coders, applicate2628/mcp-local-hub, slopper-solutions/claude-code-tmux, ferrislucas/circus-chief, generalaction/emdash, moridinamael/platespinner, z3z1ma/agent-loom, Magpie, somsamantray/tmux-claude-bridge, antonioromano/code-orchestrator, curdx/curdx-bridge, cogspro1234/conclave, m-marbouh/claude_code_bridge, openai/codex-plugin-cc, claude-delegator
第 12 組「multi-cli coding agent harness」：16 個名字，新的 16 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：agent-field/codeaf, ssap-pa/free-smart-routing-harness, ethierre/squadkit, chapzin/codex-harness-mcp, sblattj/agentic-coding-harness, mertkayacs/reevesagents, agi-cli.sh, haowjy/meridian-cli, kim3310/multi-cli-pilot, localtaskrepo/harnessmux, first-fluke/oh-my-ag, jayvee/aigon, Consiliency/agent-harness, agentforge-cli, rolemux, AgentRepoRouter
第 13 組「subagent delegation cross-provider」：14 個名字，新的 12 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：binaryhb0916/isparto, strengw/cc-switch-codex-cross-provider-bridge, rodrigorpassos/claude-codex-failover, defuj/opencode-agent-kit, kimurayu45z/subagent, nicobailon/pi-subagents, thang1710/subagent-mcp, parisbs/codex-subagent-mcp, sebstaq/opencode-subagent-mcp, nousresearch/hermes-agent, marikarx/subagent-router, hessenpepper/mcp-delegate
第 14 組「opencode delegate claude codex」：22 個名字，新的 22 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：yaniv-golan/opencode-skill, alexin09/cc-subagent-codex, reoring/roboppi, sublang-ai/boss, valpere/chorus, zahirinatzuke/local-delegate, alejandro-technology/opencode-mcp, rullerzhou-afk/codex-cli-delegate, boss6825/switchboard, amelnagdy/delegate-skills, oil-oil/oil-delegate, muhamadbarzani/forge-delegate, alaeddinemessadi/opencode-mcp, manuotel/opencode-mcp-bridge, jayden99236/consult-opencode, turbosnails/opencodeplugin, mryesiller.github.io/opencode-delegate-mcp, upstream17/opencode-delegate, opencode-cli-dispatch, more-horsepower/opencode-delegate, tuyv/claude-delegate, oh-my-opencode
第 15 組「aider multi-model delegate claude codex」：9 個名字，新的 8 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：andreilungeanu/codex-delegate-mcp, elidickinson/pi-claude-bridge, railkill/mcp-aider-executor, tolmachevmaxim/cli-agents, ycmjason/aibridge, freibergergarcia/phone-a-friend, metaswarm, AgentsRoom
第 16 組「antigravity cli delegate claude codex」：16 個名字，新的 16 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：simplybychris/antigravity-plugin-cc, rfxlamia/claude-foreman, freestyler-arb/imagine-gemini-for-claude-codex, turkeryakup/mcp-server-google-antigravity, kozaksv/antigravity-plugin-cc, cagdasyurekli/agy-worker, shauryaaojha/claude-code-delegate, wenyuchiou/antigravity-delegate, f1rstdan/call-agy, ivanantigravity-lgtm/model-council-mcp-server, x51xxx/antigravity-mcp-server, swjturay/codex-agy-delegator, kushwho/codexeni, silennsong/antigravity-cli-tool, antigravity-plugin-cc, agy-worker
第 17 組「claude code fallback quota rate limit multi-model」：14 個名字，新的 14 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：azumag/opencode-rate-limit-fallback, 9router, smart-coders-hq/opencode-model-fallback, remorses/ai-fallback, smyrna-pergamum/claude-code-fallback, finch-xu/cc-router, upstash/model-multiplexer, luckycat133/crouter, broven/claude-code-fallback, cheaper-inference/OmniRoute, NoeFabris/opencode-antigravity-auth, vimoxshah/claude-router, maslennikov-ig/claude-code-orchestrator-kit, wwhsaber/codex-orchestrator
第 18 組「codex cli gemini cli claude code wrapper」：16 個名字，新的 14 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：potatoqualitee/aitools, open330/tend, minwookim1990/unified_cli, alectivism/cross-model-agent-delegation, stellarlinkco/myclaude, claudlos/cloding, cexll/myclaude, slopedrop/llm-cli-proxy, drewstone/cli-bridge, alice-space/agentbridge, router-for-me/cliproxyapi, horlicks-p/multi-ai-relay-hub, sakibsadmanshajib/gemini-plugin-cc, carloluisito/orchestra
第 19 組「multi-model coding subagent dispatch」：11 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：carolinacherry/compare-mcp, bazley13/dsh-multi-model-orchestrator, surlymochan/swrm, caho1/codex-pi-subagents, noamsto/dispatcher, buckeyes22/subagent-model-routing, zhixuan312/multi-model-agent, lsjwzh/multicc, wineechun/dynamic-model-delegation, parallel-code
第 20 組「claude code codex gemini mcp consensus」：16 個名字，新的 16 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：antonbabenko/deliberation, shelpuk-ai-technology-consulting/lad_mcp_server, cdeust/ai-architect-mcp-spec, 5uck1ess/devkit, stgarca/consensus-mcp, dgdev25/mesh, samoradc/tetrad, leimizzou/crosscheck, yanbrod/council, frontier-infra/roundtable, gokmensercan/ai-consensus-mcp, blueman82/ai-counsel, rachittshah/llmcouncil, smart-lty/Claude-Team, deployhq/review-council, raiyanyahya/ensemble
第 21 組「gemini cli delegate claude code」：5 個名字，新的 5 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：keli-wen/agy-staff, gudastudio/collaborating-with-gemini, spyrae/gemini-plugin-cc, forayconsulting/gemini_cli_skill, ZhenHuangLab/collaborating-with-gemini-cli
第 22 組「claude code delegate to codex cli」：15 個名字，新的 15 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：dpmadsen/multimodels-mcp, harjjotsinghh/locum, newturn2017/fable-senior-mode, booksiyi1412/ask-codex, chapmanjw/rutherford-mcp-server, longranger2/claude-gpt-workflow, Echorb, sonichi/sutando, wenyuchiou/codex-delegate, ai-zixun/codex-delegate, ai-ghostwriter/delegate-to-codex, patriciomase/codex-delegate, y-a-v-a/codex-executor, evgenygurin/codex-bridge, veithly/codex-skill
第 23 組「cli delegation multi-model」：10 個名字，新的 9 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：mehmet-karagoz/codex-advisor, yeimaoz/agy-plugin-cc, observerstudio/orchestrate-skill, alice-marx/dsh-model-router, waroi/claude-multiagent-boiler-plate, srikanthmx/hermes-cli-orchestrator, delegate-agent-cli, isdou/codeck, dev-toolings/cc-delegator
第 24 組「claude codex gemini orchestration」：485 個名字，新的 469 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related
  新：code-yeongyu/oh-my-openagent, golutra/golutra, happier-dev/happier, catlog22/claude-code-workflow, greensheep01201/claw-empire, catlog22/maestro-flow, mixpeek/amux, apm-studio/apm-studio, imnmv/clauder, kelos-dev/kelos, kris-hansen/comanda, mtarcure/claude-vibe-squad, ruvnet/ruflo, yeachan-heo/oh-my-claudecode, sudocode-ai/agent-execution-engine, optio.host, zenflow, axon-core/axon, nxtg-ai/forge-orchestrator, ramarlina/agx, amangsingh/castra, boulagjame-dev/claude-octopus, bingo-taiwan/ccg-workflow, jolulo/claw-multi-ai-orchestrator, orchex-cli, Dokkabei97/all-agents-mcp, yhanottv/awesome-cli-coding-agents, johannesjo/awesome-cli-coding-agents, swisscodernano/awesome-cli-coding-agents, leepokai/awesome-cli-coding-agents …
第 25 組「claude code delegate codex mcp」：13 個名字，新的 13 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：flyhero/antumi, mekoand/sub2sub, sanoval/agent-bridges, arthurkatcher/grok-delegate, luckeyfaraday/frontier-orchestrator, rblank9/cross-claude-mcp, antorsae/dual-agent, aashahin/claude-codex-delegate, agent-dispatcher-mcp, jaegery/codex-exec-mcp, grizzly2005/bidirectional-bridge-claude-codex, yanchuk/claude-plugin-codex, NtTestAlert/cc-codex-mcp
第 26 組「claude code codex gemini cli bridge」：10 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：seemseam/claude_codex_bridge, xuyang-liu16/hermes-code-bridge, firstintent/a2a-bridge, owgit/ai-collab-bridge, kevinargueta96/open-agent-bridge, amirshayegh/codex-claude-bridge, xxlc/claude-codex-gemini-bridge, maxanatsko/llm-cli-bridge, thepushkarp/cc-gemini-plugin, shelakh/gemini-bridge
第 27 組「multi-agent cli handoff orchestration」：6 個名字，新的 5 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：choughton/llm-handoff, iriseye931-ai/agentcodehandoff, alphaelements/handoff-mcp, zevtos/agentpipe, agent-relay.dev
第 28 組「cli agent orchestrator mcp」：13 個名字，新的 6 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：agent-of-empires/agent-of-empires, sudocode-ai/sudocode, codingagentsystem/cas, bobmatnyc/claude-mpm, csoai-org/agent-orchestrator-mcp, crak1644/orchestrator-mcp
第 29 組「claude code gemini cli review mcp」：384 個名字，新的 265 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related
  新：lykhoyda/ask-llm, anamkwon/code-assistant-peers, netwaif/gemini-mcp, win4r/agent-skills-code-review-router, dicklesworthstone/mcp_agent_mail, imnotstealthy/gemini-mcp-connect, wynandw87/claude-code-gemini-mcp, ethan-tsai-tsai/gemini-mcp-server, raiansar/claude_code-gemini-mcp, gsxdsm/awesome-ao, kc1t/awesome-agent-orchestrators, krzyzanowskim/awesome-agent-orchestrators, nathanflurry/awesome-agent-orchestrators, jonathanbossenger/awesome-agent-orchestrators, jmagly/awesome-agent-orchestrators, marlburrow/awesome-agent-orchestrators, niketedm/awesome-agent-orchestrators, chrisman20/awesome-agent-orchestrators, gabrielmoreira/awesome-agent-orchestrators, buhuipao/agent-console, wainmann/agent-manager, izll/agent-session-manager, umputun/agterm, codeaholicguy/ai-devkit, hallsamuel90/craig, cyclops-team/cyclops, thefrederiksen/devthrottle, wenhanweime/herduck, techdufus/openkanban, xseman/pando …
第 30 組「pal-mcp-server zen-mcp-server gemini codex」：2 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 31 組「vibe-kanban claude-squad agent-orchestrator」：6 個名字，新的 2 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：github/squad, mco-org/squad
第 32 組「cc-multi-cli-plugin codex-plugin-cc gemini-plugin-cc」：5 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 33 組「claude-code-router omniroute cliproxyapi」：5 個名字，新的 1 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：BerriAI/litellm
第 34 組「oh-my-openagent oh-my-claudecode cli-agent-orchestrator」：5 個名字，新的 1 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：alvinunreal/oh-my-opencode-slim
第 35 組「agent-bridge claude_codex_bridge codexmcp」：7 個名字，新的 3 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：dunqing/claude-codex-bridge, xiaocang/claude-codex-bridge, vstratful/agent-bridge-mcp
第 36 組「ai-counsel agents-council deliberation mcp」：10 個名字，新的 7 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jacob-bd/the-ai-counsel, hamza-aziz-ai/codex-claude-council, oblogin/consult-mcp, rudysanchez-mfb/council-mcp, nielsmooren/council, 0xNyk/council-of-high-intelligence, am-will/llm-council
第 37 組「oh-my-openagent oh-my-opencode-slim」：2 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 38 組「vibe-kanban kanbots kandev claude codex」：3 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 39 組「multiagents metaswarm claude-octopus」：4 個名字，新的 2 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：nyldn/claude-octopus, rickhallett/sortie
第 40 組「codex-plugin-cc gemini-plugin-cc pal-mcp-server」：5 個名字，新的 2 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：tuannvm/codex-mcp-server, abiswas97/gemini-plugin-cc
第 41 組「nyldn/claude-octopus dsifry/metaswarm」：3 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 42 組「cli-agent-orchestrator agent-orchestrator claude-squad」：5 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 43 組「pal-mcp-server codexmcp agent-bridge」：6 個名字，新的 2 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：creatornader/agent-bridge, hampsterx/codex-mcp-bridge
第 44 組「cli-agent-orchestrator handoff assign tmux」：3 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 45 組「claude-code-router deepseek-reasoner gemini」：5 個名字，新的 2 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：jasonzhangf/gemini-cli-router, xiaoliu10/claude-code-router-next
第 46 組「codex-plugin-cc adversarial-review rescue」：10 個名字，新的 7 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：xuio/claude-code-codex-subagents, bbingz/minimax-plugin-cc, linxule/kimi-plugin-cc, sendbird/cc-plugin-codex, hayate/codex-plugin-oc, imblanker/codex-plugin-pi, kcng0/cc-codex-run
第 47 組「beehiveinnovations/pal-mcp-server GuDaStudio/codexmcp」：2 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 48 組「BloopAI/vibe-kanban OrchestratorInc/agent-orchestrator」：3 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
第 49 組「cheaper-inference/OmniRoute router-for-me/CLIProxyAPI」：2 個名字，新的 0 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
```

---

## 2. 代表性工具比較表（含 `verify` 實測數據，檢查日期：2026-11-16）

以下選取各類別星數最高、架構最具代表性、且經 `sweep.py verify` 實測之開源專案進行比較。

| 工具（owner/repo） | 類型 | 主控與工作者支援 CLI／模型 | 能否指定思考程度 | 結果回收與驗收機制 | 額度用完處理（Fallback / 輪替） | ★星數與授權（2026-11-16 實測） |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `NousResearch/hermes-agent` | 編排器（含子代理委派） | 主控 Hermes Agent；可透過 `delegate_task` 與 `DelegationProvider` 外掛派給 OpenRouter、OpenAI、Anthropic、Gemini 等模型 | 依目標供應商設定，可在 `~/.hermes/config.yaml` 或 Desktop 設定子代理模型與參數 | 子代理各自隔離上下文執行，完成後回傳摘錄結果給主控彙整 | 透過 `DelegationProvider` 外掛與多模型設定切換供應商 | ★263,665 \| MIT \| 未封存 \| push 2026-11-16 |
| `paperclipai/paperclip` | 編排器／組織控制平面 | 控制平面協調多團隊代理；支援掛載 Claude Code、Codex、本地模型等 harness／runtime | 依掛載的外部代理／harness 原生參數設定（控制平面未統一覆寫） | Node.js server + React UI 統一追蹤任務看板、執行日誌與預算消耗 | 以任務預算上限控管單代理花費；跨模型容錯依掛載代理自行設定 | ★114,165 \| MIT \| 未封存 \| push 2026-11-16 |
| `cheaper-inference/OmniRoute` | 路由器／額度容錯閘道 | 前端相容 Claude Code、Cursor、OpenCode、Cline；後端路由數百供應商（OpenAI、Anthropic、Gemini、免費層等） | 透傳／轉換上游請求參數；整合 RTK/Caveman 上下文壓縮降低 token | 單一 OpenAI/Anthropic 相容 API 端點同步回傳串流／工具呼叫結果給主控 CLI | **核心強項**：偵測 HTTP 429／額度耗盡後，依序自動 Cascading Fallback（付費帳號 → API key → 低價層 → 免費模型） | ★87,825 \| MIT \| 未封存 \| push 2026-11-16 |
| `ruvnet/ruflo` | 編排器／Agent Harness | 包裝 Claude Code、Codex、Hermes 等多執行期作為工作者 | 可依任務配置對應執行期與迴圈限制 | 具備共享記憶、RAG 與多代理安全護欄（監控串謀與無限委派迴圈） | 支援將任務轉派給其他已接線的後端執行期 | ★81,826 \| MIT \| 未封存 \| push 2026-11-16 |
| `code-yeongyu/oh-my-openagent` | 編排器（OpenCode 團隊） | 主控 *Sisyphus*，子代理 *Prometheus*、*Atlas*、*Hephaestus* 等跨模型分工（Claude、GPT/Codex、Gemini、Kimi、GLM） | **可**：依角色動態配置思考等級（如 `claude-opus-thinking`、`antigravity-claude-opus-thinking`） | 主控派發背景專家子代理完成工作後回收結果彙整 | 支援優先級 Fallback 鏈（高階思考模型降級至 `glm-4.7` 或 `claude-haiku`）；可搭 `@azumag/opencode-rate-limit-fallback` 攔截 429 中斷重試迴圈 | ★70,931 \| NOASSERTION \| 未封存 \| push 2026-11-15 |
| `BerriAI/litellm` | 路由器／Proxy Gateway | 各類 CLI 與 SDK 透過統一 OpenAI/Anthropic 相容介面呼叫 100+ LLM 供應商 | **可**：統一參數轉換與透傳 `reasoning_effort`／thinking 區塊 | Proxy 層同步／串流回傳並記錄 Spend／Trace | 內建多部署／多金鑰 Fallback 與 cooldown 機制（429 自動切換） | ★63,318 \| NOASSERTION \| 未封存 \| push 2026-11-16 |
| `router-for-me/CLIProxyAPI` | 路由器／CLI 憑證代理 | 將本地 Claude Code、Codex、Gemini CLI、Grok 登入憑證包裝為標準 OpenAI/Claude/Gemini/Codex API | 透傳原生協議的串流與推理參數 | 透過標準 API 協議與 WebUI (`EasyCLIProxyAPI`) 回傳結果與用量統計 | **支援多帳號 Round-Robin 負載平衡**（跨多個 Gemini/OpenAI/Claude/Grok 帳號） | ★58,658 \| MIT \| 未封存 \| push 2026-11-16 |
| `Yeachan-Heo/oh-my-claudecode` | 編排器（Claude Code 外掛） | 主控 Claude Code；可派工給 Claude 子代理及 tmux 裡的 **Codex**、**Gemini** worker | 依角色階段與工作者 CLI 參數指定 | 結構化階段管線：`team-plan → team-prd → team-exec → team-verify → team-fix`，具獨立 verify 關卡 | 可切換至池中可用的替代 CLI worker 或原生子代理 | ★40,848 \| MIT \| 未封存 \| push 2026-11-16 |
| `musistudio/claude-code-router` | 路由器（Claude Code 專用） | 前端鎖定 Claude Code；後端可路由至 DeepSeek（`deepseek-reasoner`）、Gemini、OpenRouter、Ollama | **可**：`Router.think` 層指定推理模型，或透過 Transformer 處理 `anthropic-thinking` header | 本地 Proxy（預設 loopback port）將回應轉譯回 Claude Code 格式，不中斷工具執行迴圈 | 支援規則式 Fallback（`rules[].fallback`，例如 `retryCount` 或切換備援 profile） | ★38,170 \| MIT \| 未封存 \| push 2026-10-10 |
| `openai/codex-plugin-cc` | 跨 CLI 官方外掛 | 主控 **Claude Code**；工作者 **Codex CLI**（透過本地 App Server 與 `codex exec`） | **可（有限制）**：驗證白名單 `VALID_REASONING_EFFORTS`（`none`/`minimal`/`low`/`medium`/`high`/`xhigh`；實務 issue 曾回報未列於白名單之 `max` 會被本地腳本攔截） | `/codex:review` 與 `/codex:adversarial-review` 做唯讀審查；`/codex:rescue` 介入除錯；`/codex:status`、`/codex:result` 非同步回收結果 | 未自動切換他家；撞到 ChatGPT 5 小時限流曾回報 hook 失敗／空輸出，需人工介入 | ★35,153 \| Apache-2.0 \| 未封存 \| push 2026-07-08 |
| `BloopAI/vibe-kanban` | 任務看板／多代理工作區 | 支援在同一看板調度 Claude Code、Codex、Gemini CLI、GitHub Copilot、Cursor、OpenCode 等 | 依卡片指定的 CLI 原生旗標或設定決定 | 每個卡片配置獨立 Git worktree 與 dev server，提供視覺化 Diff 審查、行內註解與 PR 建立 | 無自動跨商切換；需由人工於看板重新指派另一種代理執行 | ★28,701 \| Apache-2.0 \| 未封存 \| push 2026-11-15 |
| `getpaseo/paseo` | 編排器（跨桌面／行動端守護進程） | Daemon 管理 Claude Code、Codex 等代理，配合 MCP 技能（`/paseo-handoff`、`/paseo-advisor`、`/paseo-committee`） | 依各代理與技能設定決定 | 支援結構化交接（plan in Claude → execute in Codex），並以手機／桌面端監控進度 | 由代理或使用者透過 `/paseo-handoff` 手動交接給其他代理 | ★24,135 \| NOASSERTION \| 未封存 \| push 2026-11-16 |
| `OrchestratorInc/agent-orchestrator` | 編排器＋看板（跨平台桌面） | 主代理拆解任務並派工至支援 35+ 種代理（Claude Code、Codex、OpenCode、Gemini CLI、Cursor 等） | 依各工作者代理設定決定 | 獨立 Git worktree 平行執行，看板追蹤分支、CI 狀態與 PR，手機推播人工審批 | 看板監控狀態，單一工作失敗可重試或改派其他代理 | ★14,754 \| Apache-2.0 \| 未封存 \| push 2026-11-15 |
| `BeehiveInnovations/pal-mcp-server` | MCP 橋接（含 CLI `clink`） | 主控 Claude Code / Cursor / Codex；透過 MCP 與 `clink` 呼叫 Gemini CLI、Codex CLI、OpenAI、OpenRouter、Ollama、Grok 等 | **可（細粒度）**：支援 5 級 token 預算（`minimal` ~128、`low` ~2,048、`medium` ~8,192、`high` ~16,384、`max` ~32,768）與環境變數預設 | `clink` 啟動隔離的子 CLI 執行審查／深思，僅回傳精煉結果，不汙染主線上下文；另有共識工具匯整多模型意見 | 依賴上游 API key（429 易發生於多輪共識迴圈）；實務上社群多接 OpenRouter 或 Ollama 當備援（原生自動跨商容錯在 Issue #244 曾被大量請求） | ★11,840 \| NOASSERTION \| 未封存 \| push 2025-12-15 |
| `alvinunreal/oh-my-opencode-slim` | 編排器（輕量 OpenCode 外掛） | 基於 OpenCode 調度不同供應商模型給 *Orchestrator*、*Explorer*、*Oracle*、*Council*、*Librarian*、*Fixer* | **可**：依角色映射不同推理能力模型與 `/preset` 熱切換 | 背景派發專家後由 Orchestrator 整合；內建 *Council* 角色對單一問題併行多模型共識 | 透過 `/preset` 或 OpenCode 供應商設定快速切換模型 | ★10,235 \| MIT \| 未封存 \| push 2026-11-16 |
| `smtg-ai/claude-squad` | TUI 多終端管理（`tmux`） | 在同個終端介面平行管理 Claude Code、Codex、Gemini、Aider | 依各別終端分頁內執行的 CLI 原生設定 | 每項任務隔離在獨立 `tmux` 與 Git worktree；人工切分頁看 Diff、預覽、提交並推上 GitHub | 無自動容錯；可手動開新分頁切換為其他 CLI 接手同分支 | ★8,814 \| AGPL-3.0 \| 未封存 \| push 2026-11-13 |
| `agent-of-empires/agent-of-empires` | TUI/Web 多代理工作區（Rust） | 平行管理 Claude Code、OpenCode、Codex、Gemini CLI、Copilot CLI、Pi 等（含 `CityHall` 分散式後端） | 依各受管 CLI 原生設定 | 透過 Git worktree 與 Docker/容器沙盒隔離，TUI 與 Web 儀表板即時檢視會話狀態 | 無自動跨商切換；由操作者切換或重建沙盒內的代理類型 | ★4,536 \| MIT \| 未封存 \| push 2026-11-16 |
| `nyldn/claude-octopus` | 多模型共識編排外掛 | 主控 Claude Code；整合多達 12 種外部供應商（Codex、Copilot、Qwen、Ollama、Perplexity、Grok、Kimi 等） | **可（角色分級）**：透過 `OCTO_TIER` 與角色分工控制深度與費用 | 內建 **75% 共識關卡**交叉比對多模型輸出，支援全自動 Dark Factory 管線 | **內建熔斷器（Circuit Breaker）與自動 Fallback**：前置健康檢查區分超時與硬限流，遇 429/認證失敗自動退避並切換至健康供應商或本地 Ollama | ★4,446 \| MIT \| 未封存 \| push 2026-11-16 |
| `SeemSeam/claude_codex_bridge` | 多 CLI 終端協作橋（CCB） | 在 tmux / WezTerm 中即時串聯 Claude、Codex、Gemini、Qwen 等 CLI（透過 `caskd`/`gaskd` 等背景守護程序） | 支援透傳各 CLI 旗標與 `--chain`／`--silence` 控制阻塞／非阻塞 | 透過 `/ask` 協定與共享專案記憶（`.ccb/ccb_memory.md`）互傳精簡訊息，隔離執行上下文 | 具備 tmux pane 斷線偵測與重連監控，未見跨商自動切換說明 | ★3,625 \| NOASSERTION \| 未封存 \| push 2026-11-11 |
| `github/squad` | 倉庫原生團隊架構 | 與 GitHub Copilot / Claude Code 外掛生態整合之多代理角色團隊 | 依底層代理工具設定 | 倉庫內強制委派規則與共享任務清單，分工扮演 Lead、前後端與測試員 | 依配置團隊成員角色重試或轉派 | ★3,393 \| MIT \| 未封存 \| push 2026-11-14 |
| `agentclientprotocol/claude-agent-acp` | 協議橋接（ACP Adapter） | 透過標準 Agent Client Protocol（JSON-RPC over stdio）讓任意 ACP 編排器／編輯器控制 Claude Code（同系列另有 `codex-acp` 576★） | 透過 ACP 協議參數傳遞模型與工作模式 | 標準化結構化事件流與工具呼叫核准介面回傳給上層編排端 | 由上層 ACP 客戶端／編排器負責重試或改派另一條 ACP 連線（如 `codex-acp`） | ★2,777 \| Apache-2.0 \| 未封存 \| push 2026-11-14 |
| `jamubc/gemini-mcp-tool` | MCP 橋接（Gemini CLI） | 主控 Claude Code 等 MCP 客戶端；工作者 Google Gemini CLI | 依 Gemini CLI 預設／傳遞旗標，主打零額外 API key 設定 | 透過 stdio MCP 工具回傳 Gemini 大上下文分析結果（唯讀查詢為主） | 仰賴本地 Gemini CLI 登入配額，無跨商自動備援 | ★2,299 \| NOASSERTION \| 未封存 \| push 2026-11-15 |
| `Dicklesworthstone/mcp_agent_mail` | MCP 跨代理信箱協調 | 跨任意支援 MCP 的本地代理（Claude Code、Codex、Gemini 等）收發非同步訊息與宣告檔案鎖定 | 不介入各代理自身思考設定 | 類似信箱的持久化收件匣、Thread 回覆與檔案租約（File Lease）機制，避免互蓋檔案 | 代理離線時訊息留存信箱，待其他活躍代理領取接手 | ★2,235 \| NOASSERTION \| 未封存 \| push 2026-11-05 |
| `GuDaStudio/codexmcp` | MCP 橋接（Codex 專用） | 主控 Claude Code；工作者 OpenAI Codex | 可追蹤推理過程（reasoning trace）與多輪會話參數 | 支援多輪對話、並行任務與嚴格 diff-patch 回傳給 Claude Code 驗收 | 支援會話持久化；遇單次失敗可保留上下文重試 | ★2,002 \| MIT \| 未封存 \| push 2026-01-13 |
| `awslabs/cli-agent-orchestrator` | 編排器（Supervisor-Worker） | 支援 Claude Code、Codex CLI、OpenCode、Gemini CLI、Kiro CLI、Copilot CLI、Cursor 等 | 依各 tmux 視窗啟動的 CLI profile 設定 | 三大原語：**Handoff**（同步移交）、**Assign**（平行非同步派工）、**Send Message**；透過本地 MCP server 與 Web UI (`9889` port) 回收狀態與結果 | 每個工作者在獨立 tmux 視窗運作，可由監督代理重新 `assign` 給不同供應商 profile | ★1,562 \| Apache-2.0 \| 未封存 \| push 2026-11-16 |
| `first-fluke/oh-my-agent` | 編排器／多 CLI Harness | 支援 Antigravity / Claude Code / Codex / Gemini CLI 等多 CLI 編排 | 依角色與技能規範設定 | 以專責角色技能與結構化階段驗證推進工作流 | 依 harness 規則回退至其他可用 CLI | ★1,466 \| MIT \| 未封存 \| push 2026-11-15 |
| `kdlbs/kandev` | 任務看板／多代理環境 | 支援 Claude Code、Codex、Gemini CLI、Amp、Auggie、Cursor、Qwen 等 | 依各卡片代理配置 | Git worktree 隔離＋內建 LSP 編輯器與 Git 變更面板；支援多步驟管線（A 規劃 → B 實作 → C 審查） | 人工或管線規則於看板切換卡關步驟的執行代理 | ★1,131 \| AGPL-3.0 \| 未封存 \| push 2026-11-16 |
| `jarrodwatts/claude-delegator` | MCP 專家委派外掛 | 主控 Claude Code；透過 MCP 委派給外部專家模型（Codex 等）擔任 Architect／Reviewer／Security Analyst | 依專家子代理定義設定 | 回傳專家審查／建議給主控整合；**注意：本專案已於 GitHub 封存（archived）** | 已封存不再維護，建議轉往 `openai/codex-plugin-cc` 等活躍專案 | ★997 \| MIT \| **已封存** \| push 2026-10-12 |
| `hex/claude-council` | 跨模型議會外掛 | 主控 Claude Code；同時向 Gemini、Codex 與 OpenRouter 模型發問並處理跨分支程式任務 | 依所選各家模型特性決定 | 並排呈現各家模型回答，或將程式碼任務分派到不同 Git 分支由人／主控比對 | 單一成員失敗不影響其餘成員併行回傳 | ★942 \| MIT \| 未封存 \| push 2026-11-08 |
| `dsifry/metaswarm` | 全生命週期多代理編排 | 主控常駐 Claude Code；自動委派實作與審查給 **Gemini CLI** 與 **Codex CLI**（共 18+ 專責代理） | 依角色階層（架構師、審查員、實作員）分級配置，並強制 **TDD 與對抗式跨模型審查** | **嚴格品質閘門**：強制「寫扣的模型不能自己過審，須由另一模型審查」，結合 Playwright 視覺驗證與 Git 原生知識庫 | **內建健康檢查、預算熔斷器與跨模型升級鏈（escalation chain）**：特定席次失敗或超額時自動重路由至備援 CLI／模型 | ★432 \| MIT \| 未封存 \| push 2026-11-12 |
| `raysonmeng/agent-bridge` | 雙向 CLI-MCP 橋接守護程式 | 雙向連接 **Claude Code**（MCP Channel 通知）與 **Codex**（App Server 協議），不鎖死誰為主控 | 由各自原生 CLI 對話保留獨立思考設定 | 「只傳訊息不傳原始上下文」，搭配 busy-guard 防止回合衝突與無限對話迴圈 | 內建排隊佇列與 per-project port 隔離，確保單一回合阻塞時不流失訊息 | ★431 \| MIT \| 未封存 \| push 2026-11-15 |
| `greenpolo/cc-multi-cli-plugin` | 跨 CLI 原生子代理外掛 | 主控 Claude Code；可切換 `/model` 並派工給 ChatGPT/Codex、Cursor、OpenCode Zen、Antigravity，或透過 `/multi-cli-anything` 掛接任何 ACP CLI | 保留各供應商原生登入權限與 CLI 旗標 | 派給具名原生子代理（如 `/codex:execute`、`/cursor:debug`），完成後將結果回傳至同一 Claude Code 工作階段 | 可直接透過 `/model` 切換到其他尚有額度的原生 CLI 帳號／供應商 | ★195 \| Apache-2.0 \| 未封存 \| push 2026-10-30 |
| `antonbabenko/deliberation` | 跨模型議會／第二意見 MCP | 主控 Claude Code / Codex / Cursor；查詢 Codex、Gemini、Grok 與 OpenRouter | 依查詢角色與目標模型設定 | 提供第二意見或由仲裁者（Arbiter）彙整多模型共識結論 | 透過 OpenRouter 與多後端分散單一供應商風險 | ★183 \| MIT \| 未封存 \| push 2026-11-13 |
| `sakibsadmanshajib/gemini-plugin-cc` | 跨 CLI 社群外掛（ACP 移植） | 主控 Claude Code；透過 ACP over stdio 驅動 Gemini CLI | 依 Gemini CLI 原生選項傳遞 | 1:1 移植 `codex-plugin-cc` 指令體驗（`/gemini:review`、`/gemini:adversarial-review`、`/gemini:rescue`）；**注意：本倉庫已標記封存** | 已封存；同生態另可參考 `thepushkarp/cc-gemini-plugin`（74★）或 `yuting0624/antigravity-for-claude-code`（492★） | ★23 \| MIT \| **已封存** \| push 2026-05-22 |

> 註：`agentclientprotocol/codex-acp`（★576、NOASSERTION、未封存、push 2026-11-12）與 `agentclientprotocol/claude-agent-acp` 同屬 ACP 官方標準適配器；`Z-M-Huang/claude-codex-gemini`（★21、GPL-3.0、未封存、push 2026-02-06）與 `KimYx0207/Claudecode-Codex-Gemini`（★118、MIT、未封存、push 2026-10-16）為社群具代表性的三模型生命週期串接範本。

---

## 3. 業界與開源共通的分工模式

透過 49 組、1,251 個工具的收斂盤點，業界與開源社群在「跨模型、跨應用多代理分工」已穩定收束出 **6 種核心模式**：

### 模式一：主控規劃＋專長／低成本模型執行（Architect + Specialist / Cost Tiering）
- **核心邏輯**：主控代理保留最強的推理與工具協調能力（高單價／低限流額度），把「全倉掃描、大量文件與 log 分析、樣板程式碼生成、背景探索」派給大 Context Window 或低價／本地模型。
- **典型角色分工**：
  - **Claude Code**：架構設計、任務拆解、跨檔協調與最終整合。
  - **Gemini CLI / Antigravity (`agy`)**：利用長上下文掃描整個專案依賴、閱讀大型 PDF／規格或截圖轉碼（如 `KimYx0207/Claudecode-Codex-Gemini` 的 `/kim-ui2code`）。
  - **Codex CLI / OpenCode / DeepSeek**：演算法實作、重構與快速局部修復。
- **代表工具**：`BeehiveInnovations/pal-mcp-server`、`GuDaStudio/codexmcp`、`musistudio/claude-code-router`（`Router.think` / `longContext` / `background` 分層）、`code-yeongyu/oh-my-openagent`、`alvinunreal/oh-my-opencode-slim`、`Yeachan-Heo/oh-my-claudecode`、`jamubc/gemini-mcp-tool`、`isdou/codeck`。

### 模式二：對抗式審查與第二意見（Cross-Model Adversarial Review / Second Opinion）
- **核心邏輯**：避免「單一模型盲點共振（Correlated Blind Spots）」——讓寫扣的模型自己審查容易放過相同假設錯誤，因此刻意由**不同模型家族**擔任唯讀審查員（Reviewer），挑出邏輯邊界、競態條件與安全風險後再退回主控修正。
- **代表工具**：`openai/codex-plugin-cc`（`/codex:adversarial-review`）、`dsifry/metaswarm`（強制寫與審不同模型）、`sakibsadmanshajib/gemini-plugin-cc`（`/gemini:adversarial-review`）、`lploc94/cross-review`（167★）、`raine/consult-llm`（148★）、`razzant/claudexor`（525★）、`atompilot/claude-code-cross-review`。

### 模式三：多模型議會與共識辯論（LLM Council / Deliberation Consensus）
- **核心邏輯**：受「LLM Council」概念啟發，針對架構決策或疑難 Bug，同時平行詢問 3 個以上不同模型，彼此**盲審（Blind Peer Review）**或經過多輪辯論／反駁，最後由主席模型（Chairman / Arbiter）綜合少數意見並產出共識判決。
- **代表工具**：`nyldn/claude-octopus`（75% 共識關卡）、`hex/claude-council`、`antonbabenko/deliberation`、`blueman82/ai-counsel`、`MrLesk/agents-council`、`rachittshah/llmcouncil`、`raiyanyahya/ensemble`、`religa/multi_mcp`。

### 模式四：Worktree 隔離平行群體＋看板人工驗收（Git Worktree Swarm + Diff Kanban）
- **核心邏輯**：多位 CLI 代理若同時改同一個工作目錄一定會衝突。業界標準解法是「**一張任務卡／一個子任務 ＝ 一個獨立 `git worktree` ＋ 一個隔離終端 (`tmux` / PTY / 容器)**」，由看板或 TUI 統一監控執行流、即時預覽並由開發者或主控審查 Git Diff 後合併 PR。
- **代表工具**：`BloopAI/vibe-kanban`、`OrchestratorInc/agent-orchestrator`、`smtg-ai/claude-squad`、`agent-of-empires/agent-of-empires`、`kdlbs/kandev`、`leodavinci1/kanbots`、`standardagents/dmux`（1,819★）、`desplega-ai/agent-swarm`（1,059★）、`awslabs/cli-agent-orchestrator`。

### 模式五：CLI-to-CLI 原生協議與雙向訊息匯流排（ACP / App-Server / PTY Bridge）
- **核心邏輯**：早期工具多把別家 API 包成自訂 MCP server（常面臨 OAuth token 提取與服務條款風險，見 `Dokkabei97/all-agents-mcp` 說明）；2026 年主流已轉向**直接驅動各家官方 CLI 二進位檔**，保留各自本地訂閱登入與權限沙盒，並透過標準協議（**ACP** over stdio、Codex App Server、Headless PTY 或檔案信箱）雙向溝通，且「只傳簡明指令與 Diff，不互相汙染完整對話歷史」。
- **代表工具**：`agentclientprotocol/claude-agent-acp` 與 `codex-acp`、`greenpolo/cc-multi-cli-plugin`、[`openai/codex-plugin-cc`](https://github.com/openai/codex-plugin-cc)、`raysonmeng/agent-bridge`、`SeemSeam/claude_codex_bridge`、`Dicklesworthstone/mcp_agent_mail`、`subagent-cli`。

### 模式六：額度感知與 429 熔斷容錯（Quota-Aware Failover & Multi-Account Rotation）
- **核心邏輯**：多代理並行會成倍加速觸發各家 5 小時／每週／RPM 限流（HTTP 429）。成熟方案分為兩條路：
  1. **Proxy Gateway 層攔截**：攔截 429 與 quota 錯誤，依優先級鏈切換付費 API → 備援供應商 → 低價／免費模型 → 本地 Ollama，或做多帳號 Round-Robin 輪替。
  2. **Harness 事件層中斷**：攔截閘道器陷入長指數退避重試的事件（如 OpenCode retry loop），主動中止卡死回合並熱切換至 Fallback 鏈，配合前置健康檢查與單任務預算熔斷器。
- **代表工具**：`cheaper-inference/OmniRoute`、`router-for-me/CLIProxyAPI`、`musistudio/claude-code-router`、`nyldn/claude-octopus`（Circuit Breaker）、`dsifry/metaswarm`（Budget Circuit Breaker）、`azumag/opencode-rate-limit-fallback`、`NoeFabris/opencode-antigravity-auth`（11,053★）、`BerriAI/litellm`。

---

## 4. Anthropic 多代理研究系統 vs. 跨模型版本實踐

### 4.1 Anthropic 原系統的定位與限制
Anthropic 工程文章《How we built our multi-agent research system》（`anthropic.com/engineering/multi-agent-research-system`）採用的是**同模型家族的階層式架構（Orchestrator-Worker）**：由高推理能力的 **Claude Opus** 擔任 Lead Agent 負責拆解研究策略、控制投入規模與綜合報告，並動態派發多個並行的 **Claude Sonnet** Subagent 各自在獨立上下文視窗做「Search as Compression（搜尋即壓縮）」，過濾雜訊後僅回傳精煉摘要給主控。
- **同模型局限**：僅在 Anthropic 自家模型家族內調度，無法利用 Gemini 的超長上下文窗口或 Codex 的獨立代碼審查視角，也無法在單一供應商配額（Rate Limit / 每週用量上限）觸頂時跨商退避。
- **Anthropic 對跨模型多代理的研究補充**：Anthropic 安全團隊另有論文 *Worse Together: How Performance Breaks Down in Multi-User Multi-Agent Teams*（含 Anthropic、OpenAI 等前沿模型跨模型測試），指出多代理協作容易出現任務停滯、互相覆蓋約束或捏造對同伴狀態的宣稱，因此跨模型團隊必須靠**明確的領導權責、固定通訊順序與強制檢查閘門**來約束，不能只依賴單模型智商。

### 4.2 誰在開源與業界實作「跨模型版本」的 Lead-Subagent 系統？
將 Anthropic 的「Lead Agent 規劃＋平行隔離 Subagent 壓縮回傳＋最終綜合驗收」範式跨模型／跨 CLI 落地的代表專案包括：
1. **`BeehiveInnovations/pal-mcp-server`（11,840★）**：最接近「主控不動、子代理跨模型並行探索與壓縮回報」的 MCP 實作。透過 `clink` 派發獨立隔離的 Gemini CLI / Codex CLI 子任務，只把精簡結論帶回主代理上下文，並提供明確的 5 級思考 token 預算控制（對齊 Anthropic 的 Effort Scaling 原則）。
2. **`code-yeongyu/oh-my-openagent`（70,931★）與 `alvinunreal/oh-my-opencode-slim`（10,235★）**：直接將 Lead-Subagent 角色團隊拆給不同供應商模型——主控 *Sisyphus* 規劃拆解，同時派發背景 *Explorer*、*Librarian*、*Oracle*、*Fixer* 分別跑在 Claude、GPT/Codex、Gemini 或低價模型上，且具備預算與 Fallback 鏈。
3. **`dsifry/metaswarm`（432★）與 `nyldn/claude-octopus`（4,446★）**：在 Claude Code 主控之外，強制加入跨模型對抗式審查與共識關卡（如 `metaswarm` 規定程式碼生成與審查必須跨模型；`claude-octopus` 設定 75% 跨模型共識閘門），並補上 Anthropic 原架構未提及的「跨商預算熔斷與 429 Fallback」。
4. **`awslabs/cli-agent-orchestrator`（1,562★）**：由 AWS Labs 提出的企業級跨 CLI 版本，以 Supervisor Agent 透過 `assign`（平行非同步）與 `handoff`（同步移交）調度隔離 `tmux` 視窗中的各家 CLI（Claude Code、Codex、OpenCode、Kiro 等）。
5. **輕量三模型管線（`Z-M-Huang/claude-codex-gemini`、`KimYx0207/Claudecode-Codex-Gemini`）**：將「長上下文研究／規劃（Gemini）→ 實作（Claude Code）→ 獨立審查（Codex）」寫死成標準化生命週期目錄（`.task/`）交接。

---

## 5. 第三方數據與未經一手實測之「待驗證」清單

依據誠實回報原則，除本機 `sweep.py verify` 實測之 GitHub 星數、授權、封存與最後 push 日期（2026-11-16）為確定事實外，以下轉述自原廠部落格、專案 README 或第三方評測之效能、成本與基準數據，因本次調研未在本機執行實測基準，一律標記為 **【待驗證】**：

1. **Anthropic 多代理研究系統內部評估數據**【待驗證】：Anthropic 工程文章宣稱「Opus 主控＋Sonnet 子代理在廣度優先研究查詢上比單一 Claude 代理表現高出 90.2%」，且多代理研究工作階段約消耗單一對話「15 倍」token——此為 Anthropic 官方自述數據，未經本次獨立重現。
2. **`cheaper-inference/OmniRoute` 上下文壓縮與降本宣稱**【待驗證】：專案宣稱透過 RTK/Caveman 等壓縮演算法可在多輪程式迴圈大幅削減 token 消耗，具體節省百分比與對工具呼叫準確率之影響未經本機實測。
3. **`alvinunreal/oh-my-opencode-slim` 與 `code-yeongyu/oh-my-openagent` 之 token 差異**【待驗證】：社群部落格與 README 稱 slim 版可顯著降低 prompt 膨脹與 token 成本，具體倍率與複雜任務成功率差異未經對照實測。
4. **`musistudio/claude-code-router`（v3.x+ SQLite 轉譯相容性）**【待驗證】：社群 issues 指出將 Claude Code 請求轉譯給非 Anthropic 端點（如 DeepSeek、OpenAI 相容端點）時，部分版本曾出現 `anthropic-thinking` 或 tool-use JSON 欄位不相容之 `400 Bad Request` 錯誤，實際穩定度隨各上游 API 版本變動。
5. **`openai/codex-plugin-cc` `--effort` 白名單限制與限流行為**【待驗證】：GitHub Issue 回報 `scripts/codex-companion.mjs` 之 `VALID_REASONING_EFFORTS` 曾阻擋 `max`/`ultra` 等級且遇 5 小時限流可能導致 stop hook 空輸出，實際行為隨外掛後續 commit 更新而異。
6. **跨模型對抗審查與共識品質提升幅度**【待驗證】：如 `nyldn/claude-octopus`（75% 共識關卡）、`dsifry/metaswarm`、`lploc94/cross-review` 等主張跨模型審查能大幅減少幻覺與盲點，但實際降錯率與額外花費／延遲比缺乏公開統一基準實測。
