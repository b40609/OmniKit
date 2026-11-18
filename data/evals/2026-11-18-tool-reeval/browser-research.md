# 給 Coding Agent 用的無頭瀏覽器與瀏覽器引擎飽和式調研報告

- 調研日期：2026-11-18
- 帳本路徑：[browser-ledger.json](file:///C:/Users/user/Desktop/OmniKit/data/evals/2026-11-18-tool-reeval/browser-ledger.json)
- 星數實測原始紀錄：[verify_tmp.jsonl](file:///C:/Users/user/Desktop/OmniKit/data/evals/2026-11-18-tool-reeval/verify_tmp.jsonl)

---

## 一、調研結論與停止狀態

- **查了幾組**：共查 **12 組**關鍵字（含 10 組英文、2 組繁體中文），累計收錄 **185 個不重複名字**（其中 `knq/chromedp` 與 `atroche/rust-headless-chrome` 在實測時重導向至現名 `chromedp/chromedp` 與 `rust-headless-chrome/rust-headless-chrome`，且第 10 組另計入後者，實際不重複 GitHub repo 為 184 個；另有 2 個已在 GitHub 回傳 404 之 npm/網路名稱）。
- **第幾組停**：於 **第 12 組**停下回報（觸及 `MAX_GROUPS = 12` 上限，**尚未**達到連續 3 組無新名字的停止條件）。
  - 全部名字連續無新增組數（`all` streak）：**0 組**（第 12 組仍有 2 個未滿 ★1,000 的新名字）。
  - ★1,000 以上連續無新增組數（`★1,000+` streak）：**1 組**（第 12 組有 0 個 ★1,000+ 新名字；此前第 6、7 組曾連續 2 組為 0，但第 8–11 組因切入 CLI、無障礙樹、CDP 自動化與沙盒而再度冒出 4、2、8、3 個 ★1,000+ 老牌專案與新秀）。
- **為何 12 組未收斂與後續建議**：本題橫跨「非 Chromium 自研無頭引擎（如 Lightpanda、Obscura、Moli）」、「反偵測指紋瀏覽器（如 Camoufox、CloakBrowser）」、「Agent CLI／MCP 包裝（如 agent-browser、playwright-mcp）」與「傳統各語言 CDP 驅動（如 chromedp、go-rod、ferrum）」四個子領域，每切換一組用語就會打開一個新子領域的 ★1,000+ 專案庫。若要繼續補查至完全飽和，建議拆成兩個獨立帳本：**（A）非 Chromium／自研無頭瀏覽器引擎與輕量 Runtime**、**（B）Coding Agent 專用瀏覽器 CLI／MCP／Skill 包裝層**。

---

## 二、判斷標準與排除原則

- **收錄條件**：
  1. 自研瀏覽器引擎或非完整 Chromium 之輕量執行環境，供自動化／agent 解析 DOM、執行 JS、透過 CDP／CLI／MCP 控制或輸出 Markdown／文字。
  2. 包裝瀏覽器（Chromium、Firefox、WebKit 或附帶擴充套件）並提供給 coding agent／AI agent 抓取網頁、操作頁面、取得無障礙樹（accessibility tree）／Markdown、反偵測或重用登入態的工具（CLI、MCP Server、程式庫或 Skill）。
- **不收項目**：
  - 純雲端付費 API 服務本身（下方附註並標「雲端服務」）。
  - 一般爬蟲／資料擷取框架或純 E2E 測試框架（列於「拿不準」或排除清單，不寫進帳本）。
  - 單純 Lightpanda 的 fork 或鏡像（如社群單純重新封裝、無獨立工具能力者）。
- **拿不準項目**：不記進帳本，集中列於「六、拿不準（未記進帳本）」。

---

## 三、`sweep.py status --min-stars 1000` 完整輸出與擴展紀錄

以下為 `uv run engine/skills/omnikit-research/scripts/sweep.py status data/evals/2026-11-18-tool-reeval/browser-ledger.json --min-stars 1000` 實際輸出：

```text
總共 185 個不重複的名字；連續 0 組沒有新名字（要 3 組）：還不能停
★1000 以上的 GitHub repo：連續 1 組沒有新的（要 3 組）：還不能停
已經 12 組還沒停（上限 12 組）：先回報現況，問使用者要縮小題目、拆成幾個子題各自查，還是繼續
第 1 組「headless browser engine」：40 個名字，新的 40 個；管道：seed, github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en, related
  新：lightpanda-io/browser, h4ckf0r0day/obscura, lexmount/moli, jo-inc/camofox-browser, steel-dev/steel-browser, browserless/browserless, vercel-labs/agent-browser, browserbase/stagehand, browser-use/browser-use, microsoft/playwright-mcp, ChromeDevTools/chrome-devtools-mcp, cloakhq/cloakbrowser, ariya/phantomjs, oss-invisible/playwright, proxyshard/shardbrowser, cutetailbud/ff-ruyijs, ovobrowsersupport/ovobrowser, tiliondev/fortress, vakra-dev/reader, gosub-io/gosub-engine, fenbrowser/fenbrowser, koloss777/nokk, albertobarrago/telemaco, alialfredji/lightpanda-browser, terry2010/surfbird, yutuknown/headless-engine, project-oxi/oxibrowser, polymit/phantom-engine, cloudflare/kitesurf, chrome-headless-shell …
  ★1000 以上的新名字：lightpanda-io/browser, h4ckf0r0day/obscura, lexmount/moli, jo-inc/camofox-browser, steel-dev/steel-browser, browserless/browserless, vercel-labs/agent-browser, browserbase/stagehand, browser-use/browser-use, microsoft/playwright-mcp, ChromeDevTools/chrome-devtools-mcp, cloakhq/cloakbrowser, ariya/phantomjs, oss-invisible/playwright, proxyshard/shardbrowser, cutetailbud/ff-ruyijs, ovobrowsersupport/ovobrowser, gosub-io/gosub-engine, cloudflare/kitesurf, scrapinghub/splash, casperjs/casperjs, knq/chromedp, browser-use/browser-harness
第 2 組「ai agent browser automation」：28 個名字，新的 24 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, producthunt, web-en
  新：skyvern-ai/skyvern, citrolabs/ego-lite, jackwener/opencli, tencent/browserskill, agentrhq/webcmd, browserable/browserable, ntegrals/openbrowser, browser-act/skills, magnitudedev/browser-agent, vibheksoni/stealth-browser-mcp, hyperbrowserai/hyperagent, browserwing/browserwing, platonai/browser4, microsoft/playwright-cli, brainfiber/viyv-browser, achiya-automation/safari-mcp, youneslaaroussi/marionette, marinabox/marinabox, kachilu-inc/kachilu-browser, actionbook/actionbook, nottelabs/notte, alejandroqh/browser39, jae-jae/fetcher-mcp, browsermcp/mcp
  ★1000 以上的新名字：skyvern-ai/skyvern, citrolabs/ego-lite, jackwener/opencli, tencent/browserskill, agentrhq/webcmd, browserable/browserable, ntegrals/openbrowser, browser-act/skills, magnitudedev/browser-agent, vibheksoni/stealth-browser-mcp, hyperbrowserai/hyperagent, browserwing/browserwing, platonai/browser4, microsoft/playwright-cli, actionbook/actionbook, nottelabs/notte, jae-jae/fetcher-mcp, browsermcp/mcp
第 3 組「無頭瀏覽器 AI agent」：6 個名字，新的 6 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：botswin/BotBrowser, pinchtab/pinchtab, daijro/camoufox, Bin-Huang/camoufox-cli, WhiteNightShadow/camoufox-reverse-mcp, cloakbrowser-mcp
  ★1000 以上的新名字：botswin/BotBrowser, pinchtab/pinchtab, daijro/camoufox
第 4 組「stealth headless browser」：10 個名字，新的 10 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：autoscrape-labs/pydoll, oss-invisible/playwright_mcp, clearcotelabs/clearcote-browser, dondai44423/bladebro, bablosoft/browser-with-fingerprints, clark-labs-inc/clark-browser, ultrafunkamsterdam/nodriver, Kaliiiiiiiiii-Vinyzu/patchright, Kaliiiiiiiiii-Vinyzu/patchright-python, cdpdriver/zendriver
  ★1000 以上的新名字：autoscrape-labs/pydoll, ultrafunkamsterdam/nodriver, Kaliiiiiiiiii-Vinyzu/patchright, Kaliiiiiiiiii-Vinyzu/patchright-python, cdpdriver/zendriver
第 5 組「browser mcp server」：22 個名字，新的 22 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：hangwin/mcp-chrome, epiral/bb-browser, executeautomation/mcp-playwright, browserbase/mcp-server-browserbase, anomalyco/browse, kontext-security/browser-use-mcp-server, mozilla/firefox-mcp, merajmehrabi/puppeteer-mcp-server, jumodada/drissionpage-mcp-server, ticktockbent/charlotte, redf0x1/camofox-mcp, ykshah1309/stealth-agent-browser-mcp, codeiva4u/brave-real-browser-mcp-server, sailaoda/concurrent-browser-mcp, tushar49/bidi-browser-mcp, shaun0927/openchrome, ofershap/real-browser-mcp, maestrojeong/mcp-patchright, NETWORK101/headlessdev, kevinwatt/playwright-fetch-mcp, DebugBase/glance, Ryn-Mic/ai-browser-tester
  ★1000 以上的新名字：hangwin/mcp-chrome, epiral/bb-browser, executeautomation/mcp-playwright, browserbase/mcp-server-browserbase
第 6 組「headless browser markdown」：19 個名字，新的 19 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：fairjm/md-fetch, scasella/safarimarkdown, dengian/web-to-markdown, io-oi-ai/web2md, dicklesworthstone/markdown_web_browser, alqemist-labs/agent_ferrum, hokupod/sitepanda, 27painter/dsh-moli, pardnchiu/go-browser, firede/agent-fetch, lightfeed/extractor, sidney/playwright-markdown-mcp, KultMember6Banger/kloakt, amarbel-llc/chrest, jkudish/jev-browser, TheSethRose/Fetch-Browser, epicsagas/obscura-plugin, Curzibn/mcp-bisheng, cosinusalpha/webctl
第 7 組「lightweight browser engine」：7 個名字，新的 7 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：plasmate-labs/plasmate, skift-org/vaev, akhil-chaturvedi/inoda-browser, KernelErr/CatPaw, ivanUri/koko-core, yfedoseev/browser_oxide, justrach/kuri
第 8 組「coding agent browser cli」：21 個名字，新的 21 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：vdutts7/glidercli, aipexstudio/browser-cli, schickling/chromeless, adieuadieu/serverless-chrome, keon/browser-control, captivus/chrome-agent, szymdzum/browser-debugger-cli, puffinsoft/peek-cli, cashew-labs/libretto, refreshdotdev/web-eval-agent, runablehq/mini-browser, koltyakov/browser-bridge, steel-dev/cli, mehmetnadir/cdpilot, barockok/brojev, pengelbrecht/chrome-debug-skill, ItSuhsko14/browser-cli, NatiCha/bunwv, juanheyns/gstack-browse, iFurySt/open-browser-use, lexmount/browser-cli
  ★1000 以上的新名字：schickling/chromeless, adieuadieu/serverless-chrome, keon/browser-control, refreshdotdev/web-eval-agent
第 9 組「accessibility tree browser agent」：13 個名字，新的 13 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：go-rod/rod, skyvern-ai/rustwright, siddzzzz/tarsier, varun-patkar/chromepilot, hu-qi/qwebbridge, vercel-labs/next-browser, reworkd/tarsier, paipaipai666/nexus-browser-mcp, rickardp/browser-control, Fusengine/fuse-browser, oil-oil/my-browser, hamr0/mcprune, quantmew/agent-browser-mcp
  ★1000 以上的新名字：go-rod/rod, reworkd/tarsier
第 10 組「headless chrome automation」：12 個名字，新的 12 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：googlechrome/rendertron, vibesurf-ai/vibesurf, michaljach/opencode-browser, tsaijamey/frago, rubycdp/ferrum, microlinkhq/browserless, rebrowser/rebrowser-patches, sawyerhood/dev-browser, imprvhub/mcp-browser-agent, rust-headless-chrome/rust-headless-chrome, mattsse/chromiumoxide, g1879/DrissionPage
  ★1000 以上的新名字：googlechrome/rendertron, rubycdp/ferrum, microlinkhq/browserless, rebrowser/rebrowser-patches, sawyerhood/dev-browser, rust-headless-chrome/rust-headless-chrome, mattsse/chromiumoxide, g1879/DrissionPage
第 11 組「browser sandbox ai agent」：9 個名字，新的 9 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-en
  新：browseroperator/browser-operator-core, ai-xiaodao/ai-browser-mcp, open-gitagent/clawless, leaningtech/browsercode, zzzgydi/verge-browser, remorses/playwriter, vercel-labs/dev3000, vercel-labs/remote-agent-browser, kernel/kernel-images
  ★1000 以上的新名字：remorses/playwriter, vercel-labs/dev3000, kernel/kernel-images
第 12 組「瀏覽器 MCP Claude Code」：2 個名字，新的 2 個；管道：github-topic, github-keyword, awesome, skills-sh, npm, mcp-registry, hn, exa, web-zh
  新：helloios2014/chrome-pilot-mcp, eurafaeldecarvalho/browser-scraper
```

### 關鍵字擴展與 `related` 來源

- **起手 3 組**：
  1. `headless browser engine`（不含 AI/agent/MCP 之一般說法，搭配 11 個題目 seed 與 6 次 `sweep.py related`：`lightpanda-io/browser`、`dhamaniasad/headlessbrowsers`、`browser-use/browser-use`、`vercel-labs/agent-browser`、`h4ckf0r0day/obscura`、`angrykoala/awesome-browser-automation`）
  2. `ai agent browser automation`（英文常見說法，含 `site:producthunt.com` 搜尋）
  3. `無頭瀏覽器 AI agent`（繁簡中文社群討論常用詞）
- **從結果挑詞擴展（第 4–12 組）**：
  - `stealth headless browser`：來自 `camofox-browser`、`CloakBrowser`、`BotBrowser` 等結果的高頻詞 `stealth` 與 `anti-detect`。
  - `browser mcp server`：來自 `playwright-mcp`、`chrome-devtools-mcp`、`mcp-chrome`、`camofox-browser` 與官方 MCP Registry。
  - `headless browser markdown`：來自 `Lightpanda`、`Steel`、`Fetcher MCP` 強調的「轉 Markdown」能力。
  - `lightweight browser engine`：來自 `moli`（Lite, Fast）與 `obscura` 標榜「輕量引擎、無 Chromium」。
  - `coding agent browser cli`：來自 `OpenCLI`、`playwright-cli`、`browser-control`（強調 CLI 比 MCP 省 token，專供 Claude Code/Codex）。
  - `accessibility tree browser agent`：來自 `agent-browser`、`OpenCLI`、`HyperAgent` 強調用無障礙樹／DOM 快照取代截圖座標。
  - `headless chrome automation`：來自 `chromedp`、`awesome-headless-browser` 與 `DrissionPage` 等結果的傳統無頭 Chromium 詞彙。
  - `browser sandbox ai agent`：來自 `steel-browser`（browser sandbox）、`kernel-images`（unikernel／Docker sandbox）、`playwriter`（stateful sandbox）。
  - `瀏覽器 MCP Claude Code`：中文技術文章與知乎／掘金／V2EX 討論 Claude Code 搭配瀏覽器 MCP 的關鍵詞。

### 哪些管道查不到／受限制與原因

所有 12 組透過 `sweep.py channels` 呼叫的 8 個內建管道（`github-topic`、`github-keyword`、`awesome`、`skills-sh`、`npm`、`mcp-registry`、`hn`、`exa`）皆回傳成功（`errors: []`），無連線逾時或限速失敗；實務限制與零命中原因如下：
1. **中文關鍵字在英文主導管道查無結果或失真**：
   - 第 3 組 `無頭瀏覽器 AI agent`：`github-keyword`（0 筆）、`skills-sh`（0 筆）、`hn`（0 筆）、`awesome`（0 筆）；`mcp-registry` 因 `sweep.py` 只拆出長度 >= 3 的英文詞，僅剩 `agent` 而跳過或 0 命中；`github-topic` 拆詞後只搜到泛用標籤 `ai-agent`（20 筆雜訊）。
   - 第 12 組 `瀏覽器 MCP Claude Code`：`github-keyword`（0 筆）、`hn`（0 筆）；其餘管道實際僅靠英文詞 `MCP`、`Claude`、`Code` 命中。
2. **Product Hunt 管道無免金鑰公開 API**：依 skill 規範不接需 token 之 API，第 2 組改以網頁搜尋 `site:producthunt.com` 補齊（命中 `browser-use`、`moli`、`browserless`、`stagehand`、`notte`、`skyvern`）；另以 `site:producthunt.com lightpanda` 查詢時查無對應頁面（0 筆）。
3. **官方 MCP Registry 單詞查詢限制**：`sweep.py` 對 `mcp-registry` 僅取第一個 >= 3 字元的查詢詞作子字串搜尋（例如 `headless`、`browser`、`stealth`、`accessibility`、`coding`），複合詞組（如 `browser mcp server`）會只用 `browser` 搜前 20 筆，部分長尾專案需靠 `exa`、`npm` 與 `web-en` 補齊。
4. **`awesome` 管道命中數偏少**：多數組合中 `awesome <關鍵字>` 回傳 0–5 筆，主要依靠另外對 `dhamaniasad/headlessbrowsers` 與 `angrykoala/awesome-browser-automation` 執行 `sweep.py related` 抽取清單位址。

---

## 四、★1,000 以上相關專案總表（共 70 個，依實測星數排序）

> **驗證說明**：星數、授權 SPDX、封存狀態與最後 push 日期皆以 `sweep.py verify` 於 **2026-11-18** 透過 `gh api` 實測（詳見 [verify_tmp.jsonl](file:///C:/Users/user/Desktop/OmniKit/data/evals/2026-11-18-tool-reeval/verify_tmp.jsonl)）；Windows 原生執行檔（對照 GitHub Releases 資產與 README）、截圖／頁面繪製能力與 MCP 支援則僅採計各專案 GitHub README 與 Releases 一手資料，**README 未寫者一律標「待驗證」**。

| # | Repo（定位與語言） | 實測星數（2026-11-18 gh api） | 授權（SPDX） | 最後 push（狀態） | Windows 原生執行檔 | 截圖／繪製頁面 | MCP 支援 |
|---:|---|---:|---|---|---|---|---|
| 1 | [browser-use/browser-use](https://github.com/browser-use/browser-use)（Python AI 瀏覽器 Agent 框架與 CLI） | ★121,389 | MIT | 2026-11-18（活躍） | 無獨立執行檔（跨平台 Python 套件，依賴本機 Chrome／Cloud） | 可（README 提運作過程會取用截圖 `screenshots`） | 有（README 載 `com.browser-use/browser-use` 與 MCP 文件） |
| 2 | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp)（TypeScript Chrome DevTools MCP Server） | ★58,139 | Apache-2.0 | 2026-11-18（活躍） | 待驗證（README 未寫；Releases 無 Windows 執行檔） | 可（README 載 `take_screenshot`） | 有（官方 MCP Server） |
| 3 | [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser)（Rust AI Agent 瀏覽器 CLI） | ★52,509 | Apache-2.0 | 2026-11-18（活躍） | 有（Releases 附 `agent-browser-win32-x64.exe`） | 可（README 載 `screenshot`、`pdf`） | 有（`agent-browser mcp` stdio） |
| 4 | [lightpanda-io/browser](https://github.com/lightpanda-io/browser)（Zig 自研無頭瀏覽器引擎） | ★42,206 | AGPL-3.0 | 2026-11-18（活躍） | 無（README 明寫無原生 Windows 執行檔，僅支援 WSL2） | 僅文字渲染（README 明寫無圖形渲染引擎，`--dump png/pdf` 為純文字渲染） | 有（README 載內建原生 MCP 與 Skill） |
| 5 | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)（TypeScript Playwright 官方 MCP Server） | ★39,836 | Apache-2.0 | 2026-11-17（活躍） | 無獨立執行檔（Node.js 套件，README 有 Windows 設定說明） | 可（README 載支援 `vision`/`pdf` caps） | 有（官方 MCP Server） |
| 6 | [h4ckf0r0day/obscura](https://github.com/h4ckf0r0day/obscura)（Rust 自研無頭瀏覽器與隱匿引擎） | ★36,294 | Apache-2.0 | 2026-11-18（活躍） | 有（Releases 附 `obscura-x86_64-windows*.zip` 多版本） | 可（README 載原生渲染引擎，支援截圖、錄影與 PDF，不需 Chromium） | 有（README 載內建 MCP Server） |
| 7 | [CloakHQ/CloakBrowser](https://github.com/CloakHQ/CloakBrowser)（Python/C++ 源碼級反偵測 Chromium，需免費／付費 license key） | ★32,966 | MIT | 2026-11-17（活躍） | 無預編譯 Releases 執行檔（透過 `pip`/`npm` 自動下載 Win64 binary；README 載 Windows native GPU passthrough） | 待驗證（README 只提指紋渲染一致性，未明列截圖 API） | 待驗證（README 未寫） |
| 8 | [jackwener/OpenCLI](https://github.com/jackwener/OpenCLI)（JS 將任意網站轉成 Agent CLI，重用已登入瀏覽器） | ★31,158 | Apache-2.0 | 2026-11-07（活躍） | 有桌面端選項（README 載 OpenCLIApp for macOS/Windows；CLI 走 npm + Node >= 20） | 可（README 指令表列 `screenshot`） | 待驗證（README 未寫，主打 Skill/CLI） |
| 9 | [ariya/phantomjs](https://github.com/ariya/phantomjs)（C++ 早期無頭 WebKit 瀏覽器） | ★29,410 | BSD-3-Clause | 2022-11-26（**已封存**） | 無 GitHub Releases 資產（README 載多平台支援 Windows） | 可（README 載 Screen capture，支援 CSS/SVG/Canvas） | 待驗證（README 未寫） |
| 10 | [browserbase/stagehand](https://github.com/browserbase/stagehand)（TypeScript AI 網頁自動化 SDK 與 Server） | ★26,086 | MIT | 2026-11-18（活躍） | 有（Releases 附 `stagehand-server-v3-win32-x64.exe` 與 `win32-arm64.exe`） | 可（README 載 `screenshot` 方法） | 有（README 載 Hosted MCP，本機亦可用） |
| 11 | [lexmount/moli](https://github.com/lexmount/moli)（Rust 自研輕量 AI Agent 無頭瀏覽器） | ★23,987 | Apache-2.0 | 2026-11-18（活躍） | 有（Releases 附 `moli-x86_64-pc-windows-msvc.zip`、`aarch64` 及 `moli-installer.ps1`） | 可（README 載完整渲染與繪製能力、live screencast 及 DevTools 檢視） | 待驗證（README 未寫） |
| 12 | [citrolabs/ego-lite](https://github.com/citrolabs/ego-lite)（JS 供 Codex 等代理重用登入態之輕量瀏覽器套件） | ★23,500 | MIT | 2026-11-18（活躍） | 有桌面安裝檔（README 提供 Windows `.exe` 下載連結與 Skill 安裝） | 待驗證（README 未寫） | 待驗證（README 未寫） |
| 13 | [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern)（Python 視覺與 LLM 驅動瀏覽器工作流自動化） | ★23,438 | AGPL-3.0 | 2026-11-18（活躍） | 無原生獨立執行檔（Python/Docker，README 列 Windows 需 C++ 編譯工具） | 可（README 載視覺元素辨識與頁面操作） | 有（README 載支援 MCP） |
| 14 | [browser-use/browser-harness](https://github.com/browser-use/browser-harness)（Python 讓 Coding Agent 操作使用者本機已登入 Chrome） | ★19,142 | MIT | 2026-11-18（活躍） | 待驗證（README 未寫，現已併入 `browser-use` CLI） | 待驗證（README 未寫） | 有（README 載 `browser-harness-mcp`） |
| 15 | [microsoft/playwright-cli](https://github.com/microsoft/playwright-cli)（TypeScript 省 Token 之 Agent 瀏覽器 CLI） | ★15,281 | Apache-2.0 | 2026-11-17（活躍） | 無獨立執行檔（`npm` 全域安裝 `@playwright/cli`） | 可（README 載 `playwright-cli screenshot`） | 無（README 明寫作為比 Playwright MCP 更省 token 的 CLI/SKILL 替代方案） |
| 16 | [browserless/browserless](https://github.com/browserless/browserless)（TypeScript Docker 化無頭瀏覽器叢集與 REST/WS API） | ★13,945 | NOASSERTION（README 載 `SSPL-1.0 OR 商業授權`） | 2026-11-18（活躍） | 無（主打 Docker 部署，README 未提供 Windows 原生執行檔） | 可（README 載 REST API 支援截圖與 PDF） | 有（README 載 `browserless-mcp-server`） |
| 17 | [daijro/camoufox](https://github.com/daijro/camoufox)（C/C++ 源碼級反偵測 Firefox 核心與 Python/TS SDK） | ★13,386 | MPL-2.0 | 2026-11-16（活躍） | 有（Releases 附 `camoufox-*-win.x86_64.zip` 與 `win.i686.zip`） | 可（Firefox 完整瀏覽器引擎，相容 Playwright 截圖；README 另有渲染指紋說明） | 待驗證（README 未寫；社群另有第三方 MCP） |
| 18 | [chromedp/chromedp](https://github.com/chromedp/chromedp)（Go 語言純 CDP 無頭瀏覽器驅動庫） | ★13,373 | MIT | 2026-11-18（活躍） | 無獨立執行檔（Go 函式庫，README 說明 Windows pipe 運作差異） | 可（README 載全頁／元素 `screenshot` 與 `pdf` 範例） | 待驗證（README 未寫） |
| 19 | [schickling/chromeless](https://github.com/schickling/chromeless)（TS 早期本機／AWS Lambda 無頭 Chrome 自動化） | ★13,211 | MIT | 2018-11-13（**已封存**） | 無獨立執行檔（Node 套件，README 載 Windows headless Chrome 指令） | 可（README 載 `google-screenshot.js` 等截圖範例） | 待驗證（README 未寫） |
| 20 | [g1879/DrissionPage](https://github.com/g1879/DrissionPage)（Python 自研核心網頁自動化與封包雙模工具） | ★12,579 | NOASSERTION（README 載自訂非商用授權條款） | 2026-10-27（活躍） | 待驗證（README 未寫；Python `pip` 套件） | 可（README 明寫可對整個網頁含視口外部分截圖） | 待驗證（README 未寫） |
| 21 | [hangwin/mcp-chrome](https://github.com/hangwin/mcp-chrome)（TS Chrome 擴充套件型 MCP Server） | ★12,554 | MIT | 2026-01-06（活躍） | 無獨立執行檔（Chrome 擴充包 `.zip` + Node CLI，README 支援跨平台） | 可（README 載支援 `screenshots` 與視覺編輯器） | 有（Chrome MCP Server） |
| 22 | [jo-inc/camofox-browser](https://github.com/jo-inc/camofox-browser)（JS 包裝 Camoufox 之 Agent HTTP／MCP 伺服器） | ★12,363 | MIT | 2026-11-10（活躍） | 有（Releases 同步附 Camoufox `win.*.zip`；本專案提供 Windows `build.ps1` + WSL2 Docker） | 可（README 載 `Snapshot Screenshots` base64 PNG 與 noVNC） | 有（README 載 HTTP 與 MCP 工具完全對等） |
| 23 | [pinchtab/pinchtab](https://github.com/pinchtab/pinchtab)（Go 多實例反偵測瀏覽器橋接器與 CLI） | ★10,589 | MIT | 2026-11-10（活躍） | 有（Releases 附 `pinchtab-windows-amd64.exe`、`arm64.exe`；README 註明 Windows 為 best-effort） | 可（README 載 `pinchtab audit` 產出 `screenshots/`） | 有（README 載內建 MCP Server） |
| 24 | [Tencent/BrowserSkill](https://github.com/Tencent/BrowserSkill)（TS 騰訊出品讓 Agent 共用已登入本機瀏覽器之 CLI + Skill） | ★10,543 | MIT | 2026-11-18（活躍） | 有（Releases 附 `bsk-*-x86_64-pc-windows-msvc.zip`） | 可（README 載 `bsk screenshot --full-page`） | 有（README 載 `bsk install-skill --mcp` 與 `docs/mcp.md`） |
| 25 | [ntegrals/openbrowser](https://github.com/ntegrals/openbrowser)（TS 開源瀏覽器 Agent CLI 與沙盒執行套件） | ★9,590 | MIT | 2026-04-02（活躍） | 待驗證（README 未寫） | 可（README 載 `open-browser screenshot` 與 `enableScreenshots`） | 待驗證（README 未寫） |
| 26 | [steel-dev/steel-browser](https://github.com/steel-dev/steel-browser)（TS 開源 AI Agent 瀏覽器沙盒與 API） | ★7,981 | Apache-2.0 | 2026-11-18（活躍） | 無原生獨立執行檔（Docker / Node 本機執行，README 列 Windows Chrome 路徑設定） | 可（README 載內建 `markdown`、截圖與 PDF API） | 待驗證（README 未寫） |
| 27 | [BrowserMCP/mcp](https://github.com/BrowserMCP/mcp)（TS 透過 Chrome 擴充讓 Agent 操作本機瀏覽器之 MCP） | ★7,379 | Apache-2.0 | 2026-11-12（活躍） | 待驗證（README 未寫） | 待驗證（README 未寫截圖工具，僅提 smoke test 用無頭 Chromium） | 有（`@browsermcp/mcp`） |
| 28 | [go-rod/rod](https://github.com/go-rod/rod)（Go 高階 CDP 瀏覽器自動化函式庫） | ★7,159 | MIT | 2026-08-11（活躍） | 待驗證（README 未寫；Go 函式庫） | 待驗證（README 未寫） | 待驗證（README 未寫） |
| 29 | [casperjs/casperjs](https://github.com/casperjs/casperjs)（JS 早期 PhantomJS/SlimerJS 腳本工具） | ★7,152 | MIT | 2020-04-03（**已封存**） | 待驗證（README 未寫） | 可（README 載頁面與區域截圖功能） | 待驗證（README 未寫） |
| 30 | [autoscrape-labs/pydoll](https://github.com/autoscrape-labs/pydoll)（Python 無 WebDriver 之 CDP 反偵測自動化庫） | ★7,143 | MIT | 2026-11-08（活躍） | 待驗證（README 未寫；`pip` 套件支援模擬 Windows 指紋） | 可（README 附 `Screenshots, PDFs & Bundles Docs`） | 待驗證（README 未寫） |
| 31 | [SawyerHood/dev-browser](https://github.com/SawyerHood/dev-browser)（TS 給 Coding Agent 用的持久化瀏覽器 Skill／CLI） | ★6,740 | MIT | 2026-11-03（活躍） | 無（README 明寫 `Windows and musl Linux are not yet supported`；Releases 僅 macOS/Linux） | 可（README 載 `page.shot()`） | 有（README 載 `dev-browser mcp --headless`） |
| 32 | [browser-act/skills](https://github.com/browser-act/skills)（Python AI Agent 反爬蟲瀏覽器 CLI／雲本雙模） | ★6,374 | MIT | 2026-11-04（活躍） | 無獨立執行檔（README 載支援 `OS: Windows, macOS, Linux`） | 待驗證（README 未寫截圖指令） | 待驗證（README 未寫） |
| 33 | [epiral/bb-browser](https://github.com/epiral/bb-browser)（TS 把登入瀏覽器變 API 與 CLI 的 Agent 工具） | ★6,266 | MIT | 2026-05-29（活躍） | 待驗證（README 未寫；透過 `npm`／`npx` 安裝） | 可（README 載 `bb-browser screenshot`） | 有（README 載 `bb-browser --mcp`） |
| 34 | [GoogleChrome/rendertron](https://github.com/GoogleChrome/rendertron)（TS Google 官方無頭 Chrome 預渲染服務） | ★5,949 | Apache-2.0 | 2022-10-06（**已封存／棄用**） | 待驗證（README 未寫；Node／Docker） | 可（無頭 Chrome 渲染服務；截圖 API 細節於 README 未詳列見專案定位） | 待驗證（README 未寫） |
| 35 | [executeautomation/mcp-playwright](https://github.com/executeautomation/mcp-playwright)（TS 社群早期高星 Playwright MCP Server） | ★5,681 | MIT | 2025-12-13（活躍） | 無獨立執行檔（Node 套件，README 列 Windows Playwright 快取路徑） | 可（README 載 `## Screenshot`） | 有（Playwright MCP Server） |
| 36 | [Kaliiiiiiiiii-Vinyzu/patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)（TS 免偵測修補版 Playwright 函式庫） | ★5,211 | Apache-2.0 | 2026-11-13（活躍） | 待驗證（README 未寫） | 待驗證（TypeScript 版 README 未寫截圖範例；Python 版有寫） | 待驗證（README 未寫） |
| 37 | [ultrafunkamsterdam/nodriver](https://github.com/ultrafunkamsterdam/nodriver)（Python 無 WebDriver 免偵測 Chrome 驅動） | ★4,943 | AGPL-3.0 | 2026-10-26（活躍） | 待驗證（README 未寫；`pip` 套件） | 可（README 載 `await page.save_screenshot()`） | 待驗證（README 未寫） |
| 38 | [scrapinghub/splash](https://github.com/scrapinghub/splash)（Python/QtWebKit HTTP API 輕量 JS 渲染服務） | ★4,192 | BSD-3-Clause | 2024-08-02（活躍） | 待驗證（README 未寫；常態透過 Docker 運行） | 可（README 載 JavaScript rendering service） | 待驗證（README 未寫） |
| 39 | [magnitudedev/browser-agent](https://github.com/magnitudedev/browser-agent)（TS 視覺優先開源瀏覽器 Agent） | ★4,140 | Apache-2.0 | 2026-02-08（活躍） | 待驗證（README 未寫） | 待驗證（README 僅寫視覺驗證，未明寫截圖輸出） | 待驗證（README 未寫） |
| 40 | [remorses/playwriter](https://github.com/remorses/playwriter)（TS 讓 Agent 在有狀態沙盒執行 Playwright 片段的 CLI／MCP + 擴充） | ★4,102 | MIT | 2026-11-16（活躍） | 無原生獨立執行檔（Node + 擴充套件；README 表格列 Windows WSL 支援） | 可（README 載 `screenshotWithAccessibilityLabels`） | 有（README 載支援 CLI 或 MCP） |
| 41 | [gosub-io/gosub-engine](https://github.com/gosub-io/gosub-engine)（Rust 自研開源瀏覽器引擎） | ★3,699 | MIT | 2026-11-18（活躍） | 無 Releases 執行檔（Releases 僅 Linux x86_64；README 載 `beacon` 分支支援建置 Windows） | 可（README 載 `gosub_render_pipeline` 與 Cairo CPU 渲染後端） | 待驗證（README 未寫） |
| 42 | [browserbase/mcp-server-browserbase](https://github.com/browserbase/mcp-server-browserbase)（TS Browserbase 雲端瀏覽器自架 MCP Server） | ★3,399 | Apache-2.0 | 2026-07-20（**已封存**） | 待驗證（README 未寫；`npx` 執行） | 待驗證（README 未明列截圖工具） | 有（MCP Server，對應雲端服務 Browserbase） |
| 43 | [vibheksoni/stealth-browser-mcp](https://github.com/vibheksoni/stealth-browser-mcp)（Python CDP 隱匿瀏覽器 MCP Server） | ★3,376 | MIT | 2026-11-16（活躍） | 無獨立執行檔（Python 套件，README 有 `# Windows` 安裝設定） | 可（README 載 `take_screenshot()`） | 有（Stealth Browser MCP） |
| 44 | [keon/browser-control](https://github.com/keon/browser-control)（Rust 專為 Coding Agent 打造的單檔 CDP CLI） | ★3,161 | MIT | 2026-08-27（活躍） | 無（Releases 僅 macOS/Linux，README 未寫 Windows 支援） | 可（README 載 `browser-control screenshot out.png`） | 無（README 明寫 `No MCP requirement`） |
| 45 | [rust-headless-chrome/rust-headless-chrome](https://github.com/rust-headless-chrome/rust-headless-chrome)（Rust 高階 CDP 無頭 Chrome 驅動庫） | ★2,961 | MIT | 2026-06-11（活躍） | 無獨立執行檔（Rust crate，README 載自動下載 Linux/Mac/Windows Chromium） | 可（README 載 `capture_screenshot` 與 `print_to_pdf`） | 待驗證（README 未寫） |
| 46 | [adieuadieu/serverless-chrome](https://github.com/adieuadieu/serverless-chrome)（JS AWS Lambda 用無頭 Chromium 封裝） | ★2,888 | MIT | 2022-12-08（低活躍） | 無（目標平台為 AWS Lambda Amazon Linux） | 可（README 載截圖與 PDF 範例服務） | 待驗證（README 未寫） |
| 47 | [agentrhq/webcmd](https://github.com/agentrhq/webcmd)（TS 具記憶學習能力之 Agent 瀏覽器 CLI） | ★2,782 | Apache-2.0 | 2026-10-20（活躍） | 待驗證（README 未寫是否產出獨立 Windows 執行檔；以 `npm` 安裝） | 待驗證（README 未寫） | 待驗證（README 未寫） |
| 48 | [botswin/BotBrowser](https://github.com/botswin/BotBrowser)（TS/C++ 抗指紋與反偵測 Chromium 核心） | ★2,666 | MIT | 2026-11-18（活躍） | 有（Releases 附 `botbrowser_*_win_x64.7z`，README 列 `chrome.exe` 指令） | 可（完整 Chromium 引擎，README 載 Canvas/WebGL/WebGPU 渲染一致性） | 待驗證（README 未寫） |
| 49 | [oss-invisible/playwright](https://github.com/oss-invisible/playwright)（Python 抗反爬隱匿版無頭 Firefox + Playwright） | ★2,597 | MIT | 2026-11-18（活躍） | 無本 repo Releases（README 明寫支援 **Windows x86_64**，透過 `pip`/PowerShell 安裝） | 可（完整 Firefox 渲染與 WebGL/GPU 模擬，支援 Playwright API） | 有（README 載 `uvx invisible-playwright-mcp`） |
| 50 | [cloudflare/kitesurf](https://github.com/cloudflare/kitesurf)（TS/Rust/WASM 可在 Workers 執行之實驗性瀏覽器引擎） | ★2,326 | Apache-2.0 | 2026-11-18（活躍） | 待驗證（README 未寫 Windows 執行檔；定位為 Cloudflare Workers/WASM 引擎） | 可（README 載解析 HTML/CSS/JS 並繪製 `page.screenshot`） | 待驗證（README 未寫） |
| 51 | [rubycdp/ferrum](https://github.com/rubycdp/ferrum)（Ruby 無頭 Chrome CDP 驅動庫） | ★2,071 | MIT | 2026-11-17（活躍） | 待驗證（README 未寫） | 可（README 載 `browser.screenshot(path: "google.png")`） | 待驗證（README 未寫） |
| 52 | [nottelabs/notte](https://github.com/nottelabs/notte)（Python 雲端與本機瀏覽器自動化平台與 SDK） | ★2,066 | NOASSERTION（README 載 `SSPL-1.0`） | 2026-11-18（活躍） | 待驗證（README 未寫） | 待驗證（README 未寫） | 有（README 載 `Notte MCP` 對應雲端瀏覽器） |
| 53 | [microlinkhq/browserless](https://github.com/microlinkhq/browserless)（JS 基於 Puppeteer 的無頭 Chrome 驅動與 CLI） | ★1,845 | MIT | 2026-11-17（活躍） | 待驗證（README 未寫；Node/`npm` 套件） | 可（README 載 `.screenshot()` 與 `.pdf()`） | 待驗證（README 未寫） |
| 54 | [reworkd/tarsier](https://github.com/reworkd/tarsier)（Python/TS 把網頁渲染結果轉為視覺標記與 ASCII 文字） | ★1,771 | MIT | 2024-11-25（低活躍） | 待驗證（README 未寫） | 可（README 載頁面截圖 OCR 轉文字結構） | 待驗證（README 未寫） |
| 55 | [actionbook/actionbook](https://github.com/actionbook/actionbook)（Rust/Extension 讓 Agent 讀取登入牆／付費牆內容之連線工具） | ★1,631 | Apache-2.0 | 2026-10-19（活躍） | 待驗證（Releases 僅見 Chrome 擴充 `.zip`；README 主打 Hosted MCP） | 待驗證（README 未寫截圖工具，僅含設定圖示） | 有（README 載託管遠端 MCP 端點配 Chrome 擴充） |
| 56 | [hyperbrowserai/HyperAgent](https://github.com/hyperbrowserai/HyperAgent)（TS AI 瀏覽器自動化框架） | ★1,611 | NOASSERTION（LICENSE 檔為 `AGPL-3.0`） | 2026-05-11（活躍） | 待驗證（README 未寫） | 可（README 載 `enableVisualMode` 啟用截圖與元素疊加） | 僅 MCP Client（README 載作為 MCP Client 連接外部工具，未提本身為 MCP Server） |
| 57 | [Kaliiiiiiiiii-Vinyzu/patchright-python](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python)（Python 免偵測修補版 Playwright） | ★1,603 | Apache-2.0 | 2026-11-10（活躍） | 待驗證（README 未寫） | 可（README 載 `page.screenshot(...)` 範例） | 待驗證（README 未寫） |
| 58 | [vercel-labs/dev3000](https://github.com/vercel-labs/dev3000)（TS 網頁開發除錯時間軸與自動截圖沙盒） | ★1,598 | MIT | 2026-11-10（活躍） | 無（README 明寫未發布獨立 binary，為 Node.js 24+ npm 套件） | 可（README 載 `Automatic screenshots` 與本機 CPU/GPU 渲染） | 有（README 載 `d3k mcp --print-config`） |
| 59 | [ProxyShard/ShardBrowser](https://github.com/ProxyShard/ShardBrowser)（TS/C++ 引擎級反偵測修補版 Chromium 157 與啟動器） | ★1,543 | MIT | 2026-11-10（活躍） | 有（Releases 附 `ShardBrowser-Launcher-portable-win-x64.exe`、`.msi` 與 server `.exe`） | 可（完整 Chromium 157 核心 + 桌面 UI） | 有（README 載內建 MCP Server） |
| 60 | [cdpdriver/zendriver](https://github.com/cdpdriver/zendriver)（Python 基於 nodriver 的非同步抗偵測自動化庫） | ★1,482 | AGPL-3.0 | 2026-10-02（活躍） | 待驗證（README 未寫） | 可（README 載 `await page.save_screenshot(...)`） | 待驗證（README 未寫） |
| 61 | [rebrowser/rebrowser-patches](https://github.com/rebrowser/rebrowser-patches)（JS Puppeteer／Playwright 免偵測修補補丁集） | ★1,465 | MIT | 2026-11-02（活躍） | 無獨立執行檔（npm 套件補丁；README 有 `Patch command on Windows` 指引） | 待驗證（README 未寫） | 待驗證（README 未寫） |
| 62 | [cutetailbud/ff-ruyijs](https://github.com/cutetailbud/ff-ruyijs)（C++/Python 抽取 Firefox SpiderMonkey + Necko 之純 JS/網路執行環境） | ★1,460 | AGPL-3.0 | 2026-11-17（活躍） | 有預編譯 Win64 套件（Releases 附 `ruyijs-runtime-*-win-amd64.zip` 與 `win_amd64.whl`） | 否（README 明寫無視窗、無版面配置、無渲染引擎） | 待驗證（README 未寫） |
| 63 | [mattsse/chromiumoxide](https://github.com/mattsse/chromiumoxide)（Rust CDP 非同步函式庫） | ★1,437 | Apache-2.0 | 2026-04-03（活躍） | 待驗證（README 未寫） | 可（README 載 `PrintToPdfParams` 等 CDP 指令） | 待驗證（README 未寫） |
| 64 | [browserwing/browserwing](https://github.com/browserwing/browserwing)（Go 將瀏覽器錄製動作轉為 MCP 指令或 Claude Skill） | ★1,424 | MIT | 2026-08-08（活躍） | 無 Releases Windows 執行檔（Releases 僅 macOS/Linux；README 有 Windows PowerShell 指令） | 待驗證（README 僅提軟體自身介面 Screenshots 與視覺化錄製，未明列頁面截圖工具） | 有（README 載原生 MCP 與 Skills 支援） |
| 65 | [ovobrowsersupport/ovobrowser](https://github.com/ovobrowsersupport/ovobrowser)（源碼級 C++ Chromium 指紋內核） | ★1,253 | MIT | 2026-11-16（活躍） | 有（Releases 附 `ovobrowser-*-win64-portable.zip` 含 `chrome.exe`） | 可（完整 Chromium 核心，README 載 WebGL/Canvas 渲染） | 待驗證（README 未寫） |
| 66 | [refreshdotdev/web-eval-agent](https://github.com/refreshdotdev/web-eval-agent)（Python 自主評估與除錯 Web App 之 MCP Server） | ★1,231 | Apache-2.0 | 2026-02-11（**已封存**） | 無獨立執行檔（Python MCP；README 列 Windows 手動設定） | 可（README 載擷取 `screenshots`、console 與 network logs） | 有（MCP Server） |
| 67 | [browserable/browserable](https://github.com/browserable/browserable)（JS 可自架開源 AI Agent 瀏覽器自動化平台） | ★1,215 | MIT | 2025-08-27（低活躍） | 待驗證（README 未寫；`npx browserable`／Docker） | 待驗證（README 未寫） | 待驗證（README 未寫） |
| 68 | [platonai/Browser4](https://github.com/platonai/Browser4)（Kotlin AI 原生瀏覽器引擎與 Rust CLI／MCP） | ★1,186 | Apache-2.0 | 2026-11-17（活躍） | 有（Releases 附 `browser4-cli-win32-x64.exe` 與 `windows-x64.zip`） | 可（README 載 `scrape --formats "screenshot,pdf"`） | 有（README 載 Rust CLI、MCP 與 MCP-over-HTTP） |
| 69 | [kernel/kernel-images](https://github.com/kernel/kernel-images)（Go Docker／Unikraft Unikernel 瀏覽器沙盒映像） | ★1,140 | Apache-2.0 | 2026-11-18（活躍） | 無（Linux 容器／Unikernel 映像，README 未提供 Windows 原生執行檔） | 可（README 載 `Remote GUI access (live view streaming)` 與 headful Chromium） | 待驗證（README 未寫） |
| 70 | [jae-jae/fetcher-mcp](https://github.com/jae-jae/fetcher-mcp)（TS 以 Playwright 抓動態網頁轉 Markdown 之 MCP Server） | ★1,089 | MIT | 2026-11-05（活躍） | 無獨立執行檔（`npx` Node 套件，README 附 Windows Claude 設定檔路徑） | 待驗證（README 未寫截圖工具，主打 Readability 轉 Markdown） | 有（MCP Server） |

---

## 五、Lightpanda 核心同類補充（非 Chromium 自研引擎與輕量 Runtime）

若聚焦「與 Lightpanda（`lightpanda-io/browser`）最接近、不包完整 Chromium／Firefox，而是自己做引擎、解析或輕量執行層」，除了上表中的 ★1,000+ 項目（`lightpanda-io/browser`、`h4ckf0r0day/obscura`、`lexmount/moli`、`gosub-io/gosub-engine`、`cloudflare/kitesurf`、`cutetailbud/ff-ruyijs`），本次調研亦撈到數個 ★1,000 以下的新興或專題實作，供選型參考（未滿千星之名單不保證找齊）：

- `tiliondev/fortress`：★804（2026-11-18 gh api，NOASSERTION，最後 push 2026-11-03）— 自研瀏覽器／安全引擎方向。
- `vakra-dev/reader`：★575（2026-11-18 gh api，Apache-2.0，最後 push 2026-10-06）— 專注網頁內容萃取與轉 Markdown。
- `justrach/kuri`：★369（2026-11-18 gh api，NOASSERTION，最後 push 2026-10-09）— 輕量瀏覽器引擎方向。
- `skift-org/vaev`：★309（2026-11-18 gh api，LGPL-3.0，最後 push 2026-06-24）— 自研 HTML/CSS 排版與瀏覽器引擎。
- `yfedoseev/browser_oxide`：★129（2026-11-18 gh api，NOASSERTION，最後 push 2026-07-29）— Rust 輕量瀏覽器引擎實驗。
- `alejandroqh/browser39`：★95（2026-11-18 gh api，Apache-2.0，最後 push 2026-10-12）— 輕量無頭瀏覽器方向。
- `project-oxi/oxibrowser`：★49（2026-11-18 gh api，MIT，最後 push 2026-11-04）— Rust 輕量無頭瀏覽器引擎。
- `FENBROWSER/fenbrowser`：★43（2026-11-18 gh api，MIT，最後 push 2026-11-16）— 自研瀏覽器引擎專案。
- `koloss777/nokk`：★29（2026-11-18 gh api，Apache-2.0，最後 push 2026-11-15）— 輕量無頭瀏覽器方向。
- `KultMember6Banger/kloakt`：★2（2026-11-18 gh api，Apache-2.0，最後 push 2026-09-26）— 輕量瀏覽器／Markdown 萃取工具。

---

## 六、拿不準（未記進帳本）與排除項目

### 1. 拿不準（邊界與本題定義有重疊或定位不同，暫不入帳）

- **爬蟲／資料擷取框架（雖含網頁轉 Markdown 或瀏覽器渲染，但重心在爬蟲管線）**：
  - `firecrawl/firecrawl`（雲端與自架爬取轉 Markdown API，亦提供雲端服務）
  - `unclecode/crawl4ai`（AI 爬蟲與非同步網頁擷取框架）
  - `d4vinci/scrapling`（自適應反爬蟲框架）
  - `scrapegraphai/scrapegraph-ai`（LLM 圖狀爬蟲框架）
  - `apify/crawlee`（Node/Python 大規模爬蟲框架）
  - `getmaxun/maxun`、`omkarcloud/botasaurus`、`MontFerret/ferret`、`tinyfish-io/agentql`
- **通用桌面瀏覽器引擎／底層測試驅動／E2E 測試框架（非專為 coding agent 無頭執行設計）**：
  - `ladybirdbrowser/ladybird`、`servo/servo`（通用桌面瀏覽器引擎，非以 headless／coding agent 為主軸）
  - `microsoft/playwright`、`puppeteer/puppeteer`、`berstend/puppeteer-extra`、`mxschmitt/playwright-go`、`getgauge/taiko`、`seleniumbase/seleniumbase`、`web-infra-dev/midscene`、`test-zeus-ai/testzeus-hercules`
- **瀏覽器擴充內嵌 Agent、桌面 GUI 代理或完整作業系統沙盒／JS 逆向工具**：
  - `alibaba/page-agent`（網頁內嵌 JS GUI agent，非無頭引擎）
  - `browseros-ai/BrowserOS`、`nanobrowser/nanobrowser`（圖形介面 Agentic 瀏覽器／側邊欄擴充）
  - `microsoft/magentic-ui`、`microsoft/fara`、`A9T9/RPA`、`agent-infra/sandbox`（AIO 沙盒含 VNC/Terminal/Browser）
  - `zhizhuodemao/js-reverse-mcp`、`vmoranv/jshookmcp`（偏重 JS 逆向工程除錯）、`karust/openserp`（SERP 搜尋 API）

### 2. 已排除之純雲端付費 API 與相關包裝（標記「雲端服務」）

以下主要定位為託管雲端瀏覽器基礎設施或付費 SaaS API，依題目規則不收進本機引擎／包裝帳本（僅記名稱作區隔）：

- **Browserbase**（雲端服務；僅其開源 SDK `browserbase/stagehand` 與已封存自架伺服器 `browserbase/mcp-server-browserbase` 入帳註記）
- **Hyperbrowser**（雲端服務；僅其開源框架 `hyperbrowserai/HyperAgent` 入帳）
- **Anchor Browser**（雲端服務）
- **Gologin Cloud Browser**（雲端服務）
- **Oxylabs Agent-browser**（雲端服務；其 GitHub repo `oxylabs/agent-browser` 為串接雲端 Scraping API 之客戶端）
- **Tabstack by Mozilla**（雲端服務，託管瀏覽器與抓取 API）
- **claude-world/cf-browser**（僅包裝 Cloudflare 付費雲端 Browser Rendering API 之 MCP，與自建本機引擎如 `cloudflare/kitesurf` 不同）
- **Firecrawl Cloud**（雲端服務）
