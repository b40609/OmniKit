# 工具重評：T3「Agent 工具與資源對 OmniKit 的參考價值」加三個新工具（2026-11-18）

範圍有兩批：

1. T3 對話「Agent 工具與資源對 OmniKit 的參考價值」（threadId `c1b3c179-887a-4296-acbc-db8fdd355c26`，Kai 帳號的 Opus，2026-11-17 到 11-18，866 筆活動）提過的每個工具與資源。對話用 `t3_thread_read` 從頭讀到尾，報告檔讀了 `2026-11-17-links-review.md`、`A-prompt-audit.md`（都在 `~/.t3/scratch/2026-11-17-https-ultralab-tw-picks-https-dd355c26/`）；P3 與停止條件試用的結果讀 repo 裡的 `data/evals/2026-11-18-product-research-P3.md`、`data/evals/2026-11-18-research-stop-trial.md`。
2. 使用者新看到的 Lightpanda Browser、REA、OpenDesign，以及後來加的 Claude-BugHunter。
3. 使用者說「我就是要找審查工具給 OmniKit 使用」之後，為 review 槽位（R1）做的飽和調研，以及前 5 名的第 0、1 層（2026-11-19，第 4.5 節）。

做法：照 `omnikit-eval` 的第 0、1 層重做，不沿用原對話的結論。星數、授權、最後 push 都是 2026-11-18 用 `sweep.py verify` 或 `layer0.py` 實測（第 3 批是 2026-11-19）。沒跑第 2 層，所以「採用」都只是建議，要換工具得跑第 2 層。同類工具的飽和調研見第 4 節。

建議三種：**採用**（建議進試用或維持現任）、**觀察**（記卡 `pending`，有情境對得上，值得之後實測）、**不採用**（沒有對得上的情境，或過不了門檻）。

## 1. 要你決定的事

1. **GPT Researcher、local-deep-research 要不要改成不採用。** 原對話因為只能用 8B 本機模型跑，把兩張卡留在「待評估」，你也決定不付費重跑。我重看 P3 的結果：差距主要來自「只靠網頁搜尋」這個設計（omnikit-research 光 GitHub topic 一個管道就找到 65 個），換更大的模型補不了這一塊；P3 事先寫的決策規則也是判不採用。建議改 `rejected`，理由寫「P3 實測，管道結構造成的差距」。卡片這次沒動。**2026-11-19 Ryan 定案：改 `rejected`，兩張卡已改。**
2. **OpenDesign、Huashu Design 要不要跑第 2 層**（在 WP1「官網、形象頁」跟 taste-skill 盲選）。OpenDesign 要裝桌面 app 加本機 daemon，安裝前會再問你。
3. **REA 要不要升到 rea-agents 6.9.0**（名冊固定在 6.8.0；6.9.0 是 2026-11-12 發的）。升級等於改 OmniKit marketplace 發給大家的版本。
4. **審查工具要不要跑第 2 層。** 建議跑 2 個：openai/codex-plugin-cc 與 chaseai-yt/claudex-loop，在 R1 對照現任的 Codex `/review`。第 2 層實測可以在凍結期跑，要不要採用等 12-01 之後再定。理由見第 4.5 節。

## 2. 總表

### 2.1 原對話提過的

| 工具或資源 | 一句話 | 現況（2026-11-18） | 原對話結論 | 這次建議 | 理由 | 換掉什麼 |
|---|---|---|---|---|---|---|
| ultralab.tw/picks | 台灣團隊的開源工具精選，46 個 | — | 中低，記成雷達來源 | 觀察（雷達來源） | 跟名冊重疊 17 個，表示看的是同一批熱門工具；但裡面有 Huashu Design 這種對得上情境的，不是「設計、行銷都不用看」 | 無 |
| ruvnet/ruflo | 多 agent 編排平台（原 Claude Flow） | ★82,005、MIT | 無，已查過 | 不採用 | 重型安裝、寫入 `.claude/` 與 hook；跟「裝得少比較好」相反 | 無 |
| agentusecases.ai | agent 使用案例彙整 | — | 低 | 不採用 | 是「拿 agent 做什麼」，不是卡住時的問法；沒授權、沒 API | 無 |
| elder-plinius/CL4R1T4S | 外洩的系統提示詞 | ★53,650、AGPL-3.0 | 低 | 不採用 | 來源無法驗證；官方 `/doctor prompt-audit` 做的是同一件事 | 無 |
| langchain-ai/langgraph | 自己寫 agent 的編排框架 | ★45,103、MIT | 無 | 不採用 | OmniKit 設定現成 agent，用不到 | 無 |
| tigerless-labs/autoharness | 從對話自動萃取、更新 skill 的 Claude Code plugin | ★11,181、MIT | 低，設計可參考 | 不採用 | 用「有沒有被載入」當有效證據；只支援 Claude Code | 無 |
| xai-org/grok-1 | 2024 年的開放權重模型 | ★52,242，最後 push 2024-08-30 | 無 | 不採用 | 無關、停滯 | 無 |
| YouTube tteVsN8eFxY（Mia 聊 AI） | Skill、MCP 裝太多的實測 | 沒字幕 | 中 | 資源，不收 | 片中數字無法核對，待驗證 | 無 |
| YouTube K_0UezrjoKo（AI 懶人報 EP478） | 系統提示詞瘦身 | — | 中高 | 資源，已收 | 引用的兩篇官方文章已寫進分派政策與 SOURCES | 無 |
| build.nvidia.com | NVIDIA 免費推論端點 | — | 低 | 不採用 | 分派管道接不到；資料使用條款沒查，待驗證 | 無 |
| f/prompts.chat | 角色型提示詞庫，有 MCP | ★177,777、授權 NOASSERTION | 低 | 不採用 | 跟 coding agent 的卡點不同類。原報告寫「提示詞 CC0、程式 MIT」，gh 回 NOASSERTION，待驗證 | 無 |
| google-research/harness2 | 自動改 harness 的研究程式 | ★24,358、Apache-2.0 | 低 | 不採用 | 只能跑 Linux、要 Vertex AI | 無 |
| Gloriaameng/Awesome-Agent-Harness | harness 綜述與證據矩陣 | ★442、CC-BY-4.0 | 中，調研來源 | 觀察（調研來源） | 收件匣保留 | 無 |
| 官方 features-overview 觸發表 | 「什麼症狀加什麼」 | — | 高 | 已收 | `docs/starter.md:65` 已寫入；收件匣那行刪掉 | 無 |
| `/doctor prompt-audit` | 官方規則檢查指令 | — | 跑一次 | 已用 | A-prompt-audit 12 項已處理或交給其他對話 | 無 |
| vshulcz/deja-vu | 跨 agent 對話搜尋、交接、compaction 後救回 | ★1,615、MIT、v0.24.2 | 唯一值得記的新工具 | **觀察** | 直接對上 M1、M2；Go 單檔、不呼叫 LLM。會讀全部紀錄，裝前要掃描 | 若第 2 層勝出，可取代 ce-handoff、claude-handoff 這類交接 skill |
| entireio/cli | 把 agent 對話跟 commit 一起建索引 | ★5,343、MIT、v0.13.4 | 記收件匣 | **觀察** | 對上 M1；綁 commit 的做法跟 deja-vu 互補 | 無 |
| cytostack/openwolf | 跨 agent 的可攜專案記憶 | ★2,402、AGPL-3.0、最後 push 10-19 | 記收件匣 | 觀察（低優先） | 對上 M2，但同槽位已有 claude-mem 在用；排在 deja-vu 後面 | 無 |
| yigitkonur/cli-continues | 讀 16 種 CLI 紀錄、產生交接文件 | ★1,607、MIT、**最後 push 2026-05-07** | 記收件匣 | **不採用** | 半年沒更新、沒有發行版；功能被 deja-vu 涵蓋 | 無 |
| jhlee0409/claude-code-history-viewer | 離線瀏覽 30 多種 agent 的對話 | ★2,325、MIT | 只列在試用紀錄 | 不採用 | 是給人看的瀏覽器，沒有對得上的情境 | 無 |
| Dicklesworthstone/coding_agent_session_search | 多家 agent 對話統一搜尋 | ★1,215、授權 NOASSERTION | 只列在試用紀錄 | 不採用 | 授權不明；跟 deja-vu 重疊 | 無 |
| NevaMind-AI/memU | 通用記憶框架 | ★14,628、授權 NOASSERTION | 只列在試用紀錄 | 不採用 | 給自己寫 agent 的人用；授權不明 | 無 |
| cisco-ai-defense/mcp-scanner | 掃 MCP server 的安全工具 | ★1,122、Apache-2.0、4.8.7 | 記收件匣，補第 0 層缺口 | **採用（凍結結束後優先）** | 這次三個新工具都帶 MCP server，`layer0 --scan` 只掃 skill，Lightpanda 的掃描結果是「沒有 skill」等於什麼都沒掃。缺口是實際碰到的，不是理論上的 | 不換；補在 skill-scanner 旁邊 |
| cisco-ai-defense/skill-scanner | 現在第 0 層用的 skill 掃描 | ★2,747、授權 NOASSERTION | 在用 | 維持 | gh 回 NOASSERTION，授權待驗證 | 無 |
| gitleaks/gitleaks | commit 前掃金鑰 | ★31,155、MIT | 在用 | 維持 | — | 無 |
| anthropics/sandbox-runtime | 不用容器限制檔案與網路 | ★7,169、Apache-2.0 | 用不到 | 不採用 | 沒有對得上的情境 | 無 |
| microsoft/SkillOpt | 用保留題把關的 skill 優化 | ★19,138、MIT | 方法可借 | 不採用（方法已借） | 保留題切分已做進問法庫評測 | 無 |
| first-fluke/oh-my-agent | 一份 skill 裝進 14 家 agent | ★1,471、MIT | 已查過 | 不採用 | 跟 OmniKit 的 `agents.py` 重疊 | 無 |
| ZHangZHengEric/Sage | 保留候選版本、等使用者採用 | ★1,217、MIT | 只是同類想法 | 不採用 | 沒有對得上的情境 | 無 |
| assafelovic/gpt-researcher | 開源 deep research | ★30,769、Apache-2.0 | 維持待評估（8B 小模型只算下限） | **不採用（待你決定）** | 見第 1 節第 1 項 | 無 |
| LearningCircuit/local-deep-research | 開源 deep research，預設本機模型 | ★9,600、MIT | 維持待評估 | **不採用（待你決定）** | 同上；P3 兩次各 18、19 個編造的連結 | 無 |
| langchain-ai/open_deep_research | 開源 deep research | ★12,675、**已封存** | 不採用 | 不採用 | 封存，過不了門檻 | 無 |
| tt-a1i/archify | 把 repo 畫成架構圖 | ★97,614、Apache-2.0 | P2、P3 的標準答案 | 不在這次範圍 | 是調研題目的答案，不是這批要評的工具；名冊沒有卡 | — |
| jfeliu007/goplantuml、Cocoon-AI/architecture-diagram-generator、ahmedkhaleel2004/gitdiagram、sverweij/dependency-cruiser | P3 調研裡出現的架構圖工具 | ★2,082、★7,616（最後 push 2026-05-13）、★18,980、★7,440 | 只當調研結果 | 不採用 | 沒有對得上的情境 | 無 |
| Ultra Lab 清單裡點名的：harry0703/MoneyPrinterTurbo、heygen-com/hyperframes、JimLiu/baoyu-skills | 影片生成、agent 寫動畫、中文內容 skill | ★144,332、★86,221、★27,665 | 不用看 | 不採用 | ryan 的情境沒有影片；baoyu-skills 可能對上 D1（簡報），待驗證 | 無 |
| alchaincyf/huashu-design | 一句話產生網頁、原型、PPTX 的設計 skill | ★29,792、MIT、v3.3.0 | 歸在「設計、行銷，不用看」 | **觀察** | skill 形式、跨 agent，直接對上 WP1 與 F2；是 taste-skill 的正面對手 | 若第 2 層勝出，可能取代 taste-skill（web-pages） |
| Toonflow | Ultra Lab 清單裡的影片工具 | 找不到確定的 repo | 不用看 | 不收 | 沒查到一手來源 | 無 |

### 2.2 新提出的工具

| 工具 | 一句話 | 現況（2026-11-18） | 建議 | 理由 | 換掉什麼 |
|---|---|---|---|---|---|
| **Lightpanda Browser**（lightpanda-io/browser） | Zig 從頭寫的無頭瀏覽器，CDP、內建 MCP、Markdown 輸出 | ★42,205、AGPL-3.0、v1.0.4（11-13） | **不採用**（卡片 `rejected`） | U1 要在 Windows 上讓 agent 看畫面：它沒有 Windows 原生執行檔（只能 WSL 或 Docker），而且不繪製頁面，截圖只有佔位內容；預設送遙測 | 換不掉 Claude 內建瀏覽器與 chrome-devtools-mcp。要這類輕量引擎，先看同類的 Obscura、Moli（第 4 節） |
| **REA**（morluto/rea） | 一個 CLI 加 MCP，讓 agent 逆向 APK、.NET、Electron、原生程式 | ★467,233、MIT、rea-agents 6.9.0（11-12） | **採用（維持現任）** | 名冊裡已經是 X1 的預設；這次沒找到更好的。`layer0 --scan` 有 1 個 HIGH，出在維護者發版用的 `.agents/skills/rea-changelog-update/SKILL.md:120`（重抓 PR 內文再跑檢查），npm 套件不含這個 skill，判定誤判。同名的其他「REA」：Meta 的 REA 是內部的 ML 實驗 agent，不能下載；ThemeHackers/REAA 是 ★1 的不同專案。REA 的 README 也提醒有仿冒，只從 GitHub、rea.tools、npm 的 rea-agents 安裝 | 無；只差版本要不要跟上 6.9.0 |
| **OpenDesign**（nexu-io/open-design） | 設計工作台：叫用你已有的 coding agent，依 DESIGN.md 產生原型、簡報、影片 | ★108,215、Apache-2.0 | **觀察**（卡片 `pending`） | 跟 unslop、taste-skill 不是同一種東西：那兩個在既有程式碼裡改畫面；OpenDesign 另開工作台先出原型。比較的對象是 claude-design（Claude Design）。疑慮：安全遙測一律開、首段推付費點數、要裝桌面 app 加 daemon | 不換 unslop（工具介面）；可能跟 taste-skill 競爭 WP1，要第 2 層盲選才知道 |
| **Claude-BugHunter**（elementalsouls/Claude-BugHunter） | 授權滲透測試、bug bounty、紅隊用的 skill 包（83 個 skill、15 個指令、Burp MCP） | ★10,362、MIT、v2.1（06-05），11-18 仍有 push | **不採用**（卡片 `rejected`，放在 review 槽位以便比較） | 名字有 bug，但抓的是別人網站的資安漏洞，不是審自己 repo 的 diff。ryan 沒有授權攻擊外部目標的情境；R1 是交叉審 diff，現有的 /code-review、/security-review、Codex /review 才對得上。`layer0 --scan` 有 15 個 CRITICAL、12 個 HIGH，多半是攻擊教材裡的 payload 範例（第 6 節）。README 也提醒 Anthropic 的即時資安防護會擋這類請求或把模型切回舊版。同名的 mbijon/bughunter（★1）才是整個 repo 掃程式 bug 的 plugin，但用的人太少、4 月後沒更新，不建卡 | 不換 |

### 2.3 審查工具調研的前 5 名（2026-11-19）

| 工具 | 一句話 | 現況（2026-11-19） | 建議 | 理由 | 換掉什麼 |
|---|---|---|---|---|---|
| **openai/codex-plugin-cc** | 在 Claude Code 裡叫 Codex 唯讀審 diff（`/codex:review`、`/codex:adversarial-review`） | ★35,266、Apache-2.0、v1.0.6（07-08） | **觀察，建議跑第 2 層**（新卡 `pending`） | 直接對上 R1「Claude Code 改完交給 Codex 審」；OpenAI 官方；掃描 3 個 skill 都是 INFO，hook 沒有對外連線。只支援 Claude 寫、Codex 審這個方向 | 可能補在 Codex `/review` 旁邊（不用另開 Codex），要第 2 層才知道 |
| **chaseai-yt/claudex-loop** | Claude Code 與 Codex 寫審分離的完整流程（需求、計畫審查、實作、終審） | ★3,483、授權實質 MIT、沒有發行版 | **觀察，建議跑第 2 層**（卡片已是 `pending`，補上重評） | 兩個方向都能做，審查端跑唯讀 sandbox；CI 跑 Windows。流程重，小改動用不到 | 同上 |
| **alibaba/open-code-review** | 用固定流程與規則框住 LLM 審查的 CLI，加 skill 與 plugin | ★54,185、Apache-2.0、v1.13.12（11-18） | **觀察**（新卡 `pending`） | 不是「換一家審」，是「審得比較穩」；delegation 模式可以用宿主 agent 的訂閱。效能數字是自家基準，待驗證 | 無；排在前兩個之後 |
| **kenn-io/roborev** | 每個 commit 都在背景審，結果帶回 agent，`refine` 反覆修到過 | ★1,821、MIT、v0.75.0（11-09） | **觀察**（新卡 `pending`） | 節奏跟 R1「重要的才交叉審」不同；常駐 daemon、改 git hook 與 agent hook，侵入程度高 | 無 |
| **tirth8205/code-review-graph** | Tree-sitter 程式碼圖，透過 MCP 給 agent 改動的影響範圍 | ★32,850、MIT、v2.4.0（11-11） | **觀察**（新卡 `pending`，放 code-understanding） | 做的是 C1（影響範圍），不是審查；C1 在 11-16 的第 2 層實測裡內建工具就夠了。`install` 會改這台每個 agent 的設定 | 無 |

## 3. 跟原對話結論不同的地方

1. **cli-continues：記收件匣 → 不採用。** 原對話記進收件匣時沒看最後 push；實測是 2026-05-07，半年沒更新、沒有發行版。
2. **Huashu Design：不用看 → 觀察。** 原對話把 Ultra Lab 的新名字整批歸成「影片、行銷、設計」。Huashu Design 是 skill、跨 agent，直接對上 WP1、F2，是 taste-skill 的對手。
3. **mcp-scanner：記收件匣 → 凍結結束後優先補。** 這次評的三個新工具都帶 MCP server，第 0 層只掃得到 skill，缺口實際碰到了。
4. **GPT Researcher、local-deep-research：維持待評估 → 建議不採用**（等你決定，卡片沒動）。原對話的理由是 8B 模型只能當下限；但差距主要來自只查網頁的設計，換模型補不了。
5. **features-overview 觸發表：記收件匣 → 已完成，刪掉。** `docs/starter.md:65` 已經寫進去，收件匣那行是舊的。
6. **f/prompts.chat 的授權：** 原報告寫 CC0 加 MIT，`gh api` 回 NOASSERTION，改標待驗證。
7. 其他項目結論相同，只更新了星數。

## 4. 同類工具調研（飽和式）

照 `omnikit-research` 派給 Gemini 4 Hydrogen（high）兩條 T3 對話各跑一次，帳本與原始報告在 `2026-11-18-tool-reeval/`（審查工具是後來另開的第三題，見第 4.5 節，結果一樣）。兩題都在 **12 組上限停下，沒有飽和**（★1,000 以上連續 1 組沒有新名字，要 3 組）：題目各自橫跨好幾個子領域，每換一組說法就冒出一批新的高星專案。主控用 `sweep.py status --min-stars 1000` 重算過兩本帳本，跟研究者的回報一致。所以下面只能說「目前找到的」，不能說「找齊了」。

### 4.1 Lightpanda 同類（`browser-research.md`，185 個名字，★1,000 以上 70 個）

跟 Lightpanda 一樣「自己做引擎、不包整個 Chromium」的 ★1,000 以上只有 6 個：

| repo | 星數、授權 | Windows 原生 | 能截圖、繪製頁面 | MCP |
|---|---|---|---|---|
| lightpanda-io/browser | ★42,206、AGPL-3.0 | 沒有（WSL2） | 不行（只有文字渲染） | 有 |
| h4ckf0r0day/obscura | ★36,294、Apache-2.0 | 有 | 可以 | 有 |
| lexmount/moli | ★23,987、Apache-2.0 | 有 | 可以 | 待驗證 |
| gosub-io/gosub-engine | ★3,699、MIT | 發行版只有 Linux | 可以 | 待驗證 |
| cloudflare/kitesurf | ★2,326、Apache-2.0 | 待驗證（給 Workers 用） | 可以 | 待驗證 |
| cutetailbud/ff-ruyijs | ★1,460、AGPL-3.0 | 有 | 不行 | 待驗證 |

（以上是研究者讀 README 與發行版檔案的結果，都沒實測。）

結論：**Lightpanda 在同類裡剛好是對 Windows 與「看畫面」最不利的那一個。** 要試這類引擎，Obscura、Moli 比較對得上 U1，已記進收件匣。另外，U1 真正的對手不是這些引擎，而是包一層的工具：調研裡有 Windows 執行檔、能截圖、有 MCP 的還有 Tencent/BrowserSkill（★10,543）、vercel-labs/agent-browser（★52,509，名冊已有卡）、browserbase/stagehand（★26,086），名冊現任是 Claude 內建瀏覽器與 chrome-devtools-mcp（★58,139）。

### 4.2 OpenDesign 同類（`design-research.md`，297 個名字，★1,000 以上 46 個）

- **設計工作台（跟 OpenDesign 同一種）**：OpenCoworkAI/open-codesign（★8,238，Windows 有安裝檔）、onlook-dev/onlook（★27,256，還沒有 Windows 版）、open-pencil/open-pencil（★9,925）、ZSeven-W/openpencil（★7,275）、kgoedecke/doop（★2,133）。OpenDesign 星數最高，也是唯一同時接 Claude Code、Codex、Antigravity 又有 Windows 安裝檔的。
- **前端設計 skill（跟 unslop、taste-skill 同一種）**，星數比現任高、名冊卻沒有卡的：nextlevelbuilder/ui-ux-pro-max-skill（★151,129）、Nutlope/hallmark（★57,218）、emilkowalski/skills（★57,894）。taste-skill（★118,085）、impeccable（★112,565，名冊待評估）、unslop（★18,017）都在裡面。
- **DESIGN.md 格式**：google-labs-code/design.md（★28,937）是官方格式規格加 linter；OpenDesign 的 151 套設計系統讀的就是這種檔。
- 研究者讀 README 看到的遙測：OpenDesign 安全遙測一律開、impeccable 預設開（可關）、onlook 下載版預設開；Huashu Design 寫明不送遙測。

結論：OpenDesign 換不掉 unslop（工具介面改既有程式碼）；它跟 taste-skill 爭的是 WP1，要第 2 層盲選。這次調研顯示 frontend-design 這個槽位名冊漏了好幾個高星 skill，ui-ux-pro-max-skill、hallmark、emilkowalski/skills 記進收件匣，凍結結束後一起評。

### 4.3 REA

`gh search repos rea` 依星數排第一的就是 morluto/rea（★467,231），沒有其他做 agent 工具的同名專案。網頁搜尋另找到 Meta 的 REA（內部 ML 實驗 agent，不能下載）與 ThemeHackers/REAA（★1，不同專案）。沒有另外做逆向工具的飽和調研：REA 是現任，這次的問題只是「使用者說的是不是它」。

### 4.4 Claude-BugHunter

用 `gh search repos`（「Claude-BugHunter」「claude bughunter」）和兩組網頁搜尋確認身分。正主是 elementalsouls/Claude-BugHunter（★10,362）；GitHub 上其他同名 repo 都是它的 fork 或鏡像（vishvacyber ★3、sseshachala ★2、haxshadow ★2、0xultronprime/ULTRON-PRIME-BugHunter ★0、rizkrisk ★0 等），不用分開評。

名字裡有 bug，但跟名冊的審查工具不是同一件事：

| 工具 | 抓什麼 | 對上 R1（交叉審 diff）嗎 |
|---|---|---|
| Claude Code `/code-review`、`/security-review`（內建） | 這次改動的正確性與安全問題 | 對上，是現任答案 |
| Codex `/review`（內建） | 同上，跨家交叉審 | 對上 |
| codex-security（名冊 pending） | OpenAI 的資安審查 plugin | 部分 |
| elementalsouls/Claude-BugHunter | 別人網站、企業外網的可利用漏洞，產出 bug bounty 報告 | 不對上 |
| mbijon/bughunter（★1，MIT） | 整個 repo 的行為 bug（Haiku 掃、Opus 複審，報告附重現步驟），掃描 3 個 skill 都只有 INFO | 補得上「整個 repo 掃一遍」，但只有 1 顆星、2026-04-23 後沒更新，不建卡 |
| 其他叫 bug-hunter／bug-hunt 的 skill（sickn33/agentic-awesome-skills ★49,929 合集裡的一支、chrisallenlane/claude-swe-workflows ★21 等） | 除錯流程 | 沒評，作者都不同，別跟這個搞混 |

這題沒做審查工具的飽和調研：使用者問的是「這個工具」，答案是它不屬於審查槽位。要找更好的審查工具，得另外開一題（就是第 4.5 節）。

### 4.5 審查工具（R1，`review-research.md`，477 個名字，★1,000 以上 66 個）

使用者說「我就是要找審查工具給 OmniKit 使用」，另開一題：「給 coding agent（Claude Code、Codex）用的程式碼審查與抓 bug 工具」。照 `omnikit-research` 派給 Gemini 4 Hydrogen（high，T3 對話「OmniKit 審查工具飽和調研」，`mcp:a5f136c4-e763-4225-adfa-e3c449cfa8e7`），帳本 `2026-11-18-tool-reeval/review-ledger.json`。

**驗收（2026-11-19，主控）：** 12 組到上限停下，**沒飽和**（全體 streak 0、★1,000 以上 streak 1）；主控重跑 `sweep.py status --min-stars 1000`，數字跟研究者的報告一致。`gh api` 抽查 7 個（cloudflare/security-audit-skill、alibaba/open-code-review、openai/codex-plugin-cc、chaseai-yt/claudex-loop、kenn-io/roborev、tirth8205/code-review-graph、anthropics/claude-plugins-official），星數、授權、最後 push 都對得上，只有一天份的自然成長。★1,000 以上 66 個，扣掉 7 個誤命中、6 個拿不準，符合納入標準的有 53 個（報告第 3 節）。

**挑前 5 名的標準：** R1 是「Claude Code 改完交給 Codex 審 diff，或反過來；重要的才交叉審」。看重：能不能讓另一家模型審同一份 diff、在本機搭配 Claude Code 或 Codex、Windows 能不能用、侵入程度。53 個裡很多是 PR bot、GitHub Action（R1 在本機，不經 PR）、diff 檢視器（給人看的），或只有單一家模型。

**第 0 層（2026-11-19，`layer0.py --scan`，cisco skill-scanner 靜態模式）：**

| 工具 | 門檻 | skill 掃描 | 掃描沒涵蓋、主控另外看的 |
|---|---|---|---|
| openai/codex-plugin-cc | pass | 3 個，都是 INFO | 3 個 hook：SessionStart、SessionEnd 只寫環境變數、清背景工作；Stop hook 只在開了 review gate 才審（預設關）。讀過兩支 hook 程式，沒有對外連線 |
| chaseai-yt/claudex-loop | warn（授權） | 6 個：4 個 INFO，legacy 的 2 個 LOW | 授權：GitHub 回 NOASSERTION，LICENSE 原文是 MIT 加一段出處說明，實質 MIT |
| kenn-io/roborev | pass | 48 個，都是 INFO | 常駐 daemon、post-commit hook、各 agent 的 hook 沒掃；Windows 安裝方式是 `irm … \| iex`，要裝改用 Releases 或 `go install` |
| tirth8205/code-review-graph | pass | 8 個，都是 INFO | `install` 會在每個找到的 agent 寫 MCP 設定、hook、skill 與規則檔，agent 執行時預設回答「是」 |
| alibaba/open-code-review | pass | 4 個，都是 SAFE | 遙測文件寫 OpenTelemetry 整合，預設開不開沒查 |

**跟現任比（`peers.py review`）：** 現任是內建的 `/code-review`、`/security-review` 與 Codex `/review`，pending 有 codex-security、claudex-loop、pullboard。codex-plugin-cc 把「另開 Codex 跑 `/review`」搬進 Claude Code，結果留在同一條對話；claudex-loop 是完整的寫審分離流程，兩個方向都能做。這兩個是唯一直接回答「換一家審」的；其他三個補的是別的面向（審得穩、每次都審、影響範圍）。

**結論：** 建議 codex-plugin-cc 與 claudex-loop 跑第 2 層（第 1 節第 4 項）：R1 用 OmniKeep 的真實 diff，現任的 Codex `/review` 當基準，Claude 執行、Codex 評，或反過來。open-code-review、roborev、code-review-graph 記 pending，等前兩個的結果再說。名冊 pending 的 codex-security 與 pullboard 這次沒重評。

調研停在 12 組上限沒飽和，下一步不建議整題續查：第 12 組已經沒有新的 ★1,000 以上名字，R1 對得上的前幾名也很清楚。要補的話，只拆「交叉審 diff」一題查 3 組。

## 5. 收件匣與名冊的變動

- 新卡：`lightpanda`（rejected）、`open-design`（pending）、`huashu-design`（pending）、`deja-vu`（pending）、`entire-cli`（pending）、`openwolf`（pending）、`cli-continues`（rejected）、`claude-bughunter`（rejected）。
- 收件匣：deja-vu、entire CLI、cli-continues、openwolf 移進名冊；features-overview 已完成，刪掉；mcp-scanner 補一句重評；新增 Obscura、Moli、Open CoDesign、ui-ux-pro-max-skill、hallmark、emilkowalski/skills 與 design.md。
- `rea`：notes 補上這次的掃描與版本，狀態與版本沒動（升版在第 1 節問）。
- `gpt-researcher`、`local-deep-research`：2026-11-19 Ryan 定案後改 `rejected`。
- 2026-11-19 審查工具：新卡 `codex-plugin-cc`、`open-code-review`、`roborev`（review）、`code-review-graph`（code-understanding），都是 pending；`claudex-loop` 的 notes 補上重評。

## 6. 沒查到、待驗證的

- 沒跑第 2 層，所有「觀察」都沒實測。
- Lightpanda「快 9 倍、記憶體少 16 倍」是官方自己的基準。
- deja-vu、entire、openwolf 的功能是 README 或調研摘要的說法，沒裝來試。
- prompts.chat、skill-scanner、memU、coding_agent_session_search 的授權：gh 回 NOASSERTION。
- Toonflow 找不到確定的 repo。
- OpenDesign 的遙測實際送什麼，沒讀程式碼。
- **OpenDesign 的 `layer0 --scan` 沒跑完**：repo 裡有上百個設計範本與 skill，逐一掃了一個多小時還沒結束，2026-11-18 手動停掉，沒有結果。要試用前得重跑（建議只掃它實際會裝的 skill 資料夾，或在背景跑整晚）。Lightpanda 的掃描跑完但「沒有 skill」，等於沒掃到東西（見 mcp-scanner 那列）。
- 三份同類調研都在 12 組上限停下、沒有飽和（第 4 節）。
- 審查工具前 5 名的功能、Windows 支援都是 README 的說法，沒裝來試；skill-scanner 只掃 skill，plugin 的 hook、常駐程式、安裝腳本只有 codex-plugin-cc 的 hook 是主控讀過程式碼的。
- Claude-BugHunter 的 skill 數各來源說法不一（README 開頭 83、搜尋結果與舊文 51 到 82）；以 2026-11-18 的 README 為準。
- Claude-BugHunter 的 `layer0 --scan`（2026-11-18）：83 個 skill 中 15 個 CRITICAL、12 個 HIGH、1 個 MEDIUM、55 個 INFO。看過片段，命中的幾乎都是攻擊教材裡的 payload 範例（SQL 注入、XSS、`; rm -rf /` 檔名注入、find -exec 抽 APK 字串、講 Codecov 事件的 `curl | bash`、Jenkins 憑證外洩手法），不是安裝時會自動執行的程式；但這也表示裝了之後，agent 會照這些 skill 對目標送攻擊流量。沒有逐個 skill 讀完整程式碼。判定不影響「不採用」，因為理由是情境對不上。

## 來源

- T3 對話：https://app.t3.codes/threads/0847f0dd-f941-4d6a-8b23-fda04fe00a52/c1b3c179-887a-4296-acbc-db8fdd355c26
- https://github.com/lightpanda-io/browser 、https://github.com/nexu-io/open-design 、https://github.com/morluto/rea 、https://github.com/elementalsouls/Claude-BugHunter 、https://github.com/mbijon/bughunter （README 用 `gh api repos/<repo>/readme` 讀，2026-11-18）
- 星數、授權、最後 push：`sweep.py verify`、`layer0.py`，2026-11-18
