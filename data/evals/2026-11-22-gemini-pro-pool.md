# Gemini Pro 帳號池：Neon 能接多難的工作、6 個帳號怎麼用（2026-11-22）

狀態：討論中，等 Ryan 決定（第五節）。查證日期 2026-11-22。

## 背景

- Ryan 2026-11-22：3.8 Flash 太弱，新買 5 個 Gemini Pro（Google AI Pro）帳號，能用的模型跟 Ryan 的帳號一樣。
- T3 現況（2026-11-22 `orchestrator_capabilities`）：Antigravity 實例只有 `antigravity_ryan`（Gemini 4 Neon、Orchestrator (Neon)、Gemini 4 Hydrogen、Claude Opus 5.5、Claude Sonnet 5.5），以及 `antigravity_ava`、`antigravity_kai`（只列 Gemini 3.8 Flash）。新帳號還沒接進 T3。
- 11-19 的實測報告寫 T3 列不出 Orchestrator (Neon)，現在列得出來，可以開成 T3 看得到的對話。

## 一、結論

1. Neon 跟 3.8 Flash 不同級，能接 repo 等級的修改、除錯、重構；3.8 Flash 時代的限制（只接文件與唯讀、Flash 主線只能派 Flash）對新帳號不適用。
2. 多個帳號怎麼用，Google 官方 FAQ 有明文：消費方案（Pro）不支援「自動輪換帳號」，也不支援「第三方 coding agent 包裝或驅動 agy」（另一題點名 Claude Code、OpenClaw、OpenCode）。條款第 6 段寫用第三方軟體存取服務屬違約，可能停用 Antigravity 帳號。
3. 這也碰到 OmniKit 現在的設計：Claude 主控用 delegate_task、t3_thread_launch、t3 CLI、`agy -p` 自動派給 `antigravity_ryan` 這個訂閱帳號，正是 FAQ 說消費方案不支援的用法。目前還沒出事，但這是既有風險，不是新帳號才有。
4. 建議：你自己開的對話用訂閱帳號，一次用一個，額度用完手動換；Claude 自動派給 Gemini 的改走 API 金鑰或 Vertex（官方對第三方 agent 的建議做法）。

## 二、Neon、Hydrogen、3.8 Flash

| 項目 | Gemini 4 Neon | Gemini 4 Hydrogen | Gemini 3.8 Flash | 來源 |
| --- | --- | --- | --- | --- |
| Terminal-Bench 4.1 | 65.2%（沒寫思考程度） | 57% | 18.2% | Neon：Google 印度官方部落格；另兩個：Interesting Engineering 轉述 Google |
| Artificial Analysis 智力指數 | 61（xhigh，總排名第 3） | 51（high）、54（xhigh） | 沒查到 | 同上 |
| Artificial Analysis Coding Agent 指數 | 58.6（第 1） | 沒查到 | 沒查到 | Google 印度官方部落格 |
| coding 偷吃步評測 | 2.45% 的任務走捷徑，Gemini 4 系列最低 | 沒查到 | 沒查到 | Google 印度官方部落格 |
| 官方定位 | 「demanding daily workflows」：repo 等級修改、除錯、重構 | 「rapid everyday execution」 | 快、便宜 | Antigravity 官方部落格 |
| API 牌價（每百萬 token，輸入／輸出） | USD 3 / 15 | USD 1.5 / 7.5 | 沒查 | `data/evals/2026-11-19-model-roles-research.md` 第四節 |
| 我們的實測 | 11-19：一次寫完 5 個檔約 950 行，獨立驗收 14/14（n = 1） | 11-21 R1：xhigh 審查 T1 到 T3 抓到 2.5/3，另 T5 抓到、T4 部分，比現任 Codex 多 | 問法庫評測：計算規則只有使用者知道時直接猜（agent-notdone 退步） | `data/evals/2026-11-19-orchestrator-bench/REPORT.md`、`data/evals/2026-11-19-review-R1.md`、`docs/reviews/2026-11-19-ask-eval-skillfix.md` |

注意：

- 全是廠商公布的數字，沒有獨立驗證；Neon 的 61 是 xhigh、Hydrogen 的 51 是 high，不是同條件比。
- Neon 在 Antigravity 額度裡扣幾倍，官方沒公布（待驗證）；API 牌價是 Hydrogen 的 2 倍。
- Gemini 4 Carbon（最強的長任務模型）只有 Ultra 與 Enterprise 有，Pro 沒有（官方 Models 頁）。

### 在一個 Pro 帳號裡怎麼分工

- **Neon high**：預設主力。難的設計、難 bug 用 xhigh。
- **Orchestrator (Neon)**：多檔的大工作包，Neon 規劃與審查、Hydrogen 執行；官方說比較省額度，沒給數字。官方 Models 頁寫它是同一條對話裡的單一 agent，不是平行。
- **子代理、`/swarm`**：帳號內建的平行（官方文件支援；`/swarm` 全方案可用但還在預覽，官方寫會比單一對話快很多用完額度）。
- **Hydrogen**：快的小事；審查用 xhigh（R1 驗證過）。
- **Claude Opus 5.5、Sonnet 5.5（Antigravity 裡）**：要 Claude 的判斷、但 Claude 帳號額度緊的時候用；最高 high，Opus 照 Ryan 規則用 medium。只有非試用的付費 Pro 有（官方 Models 頁）。
- **3.8 Flash**：不再用。ava、kai 的 Claude 4.6 與 GPT-OSS 在 11-30 從 Pro 下架（官方 Models 頁），之後只剩 3.8 Flash。
- 還是留給 Claude Opus 的：帳務、風險、下單與最後定案（Ryan 規則）。
- T3 的 Antigravity 15 分鐘沒動作就逾時還在，長時間跑的工作中途要送「繼續」。

## 三、Google 怎麼規定（依證據等級）

論壇回覆不是條款本身；沒有 staff 標記的回覆者是不是 Google 員工無法確認，那幾格當待驗證。

| 用法 | 官方條款或文件 | 有 staff 標記的論壇回覆 | 沒有 staff 標記的論壇回覆 |
| --- | --- | --- | --- |
| 你自己在 T3（ACP 編輯器）開對話、打字 | ACP 文件：「Any ACP client can launch Antigravity CLI」；沒列 T3，也沒限方案 | 沒有 | 11-16：單一帳號在 T3「fully supported」 |
| 同一個帳號裡用子代理、`/swarm`、Orchestrator | 官方文件支援 | 沒有 | 11-16、11-20：建議用這些做平行 |
| 你自己的腳本或 CI 跑 `agy -p` | FAQ：headless「intended for direct scripting and CI workflows」 | 10-07、10-08：支援 | 11-20：支援 |
| 自己的幾個付費帳號，手動切換 | 沒寫 | 07-15：「not considered a violation」；要是「paid accounts that you personally own」；問題常出在「discounted or shared pool」的帳號 | 10-19：可以，限手動、不用腳本 |
| 自己的幾個付費帳號同時開（同一台、同一個 T3） | 沒寫 | 沒有 | 11-16，問的就是我們的情境（3 到 6 個 Pro 帳號同時跑在 T3）：「Not Supported」，「indistinguishable from account pooling/rotation」，有自動停權風險；建議改成一個 Ultra |
| 額度用完自動換帳號 | FAQ：「automating account rotation, is not supported under consumer plans」 | 沒有 | 09-28：不允許，會永久停權 |
| Claude Code、Codex 等第三方 agent 驅動 agy（含 delegate_task 這類自動派工） | FAQ：「Wrapping `agy` inside third-party coding agents or applications」在消費方案不支援；另一題點名 Claude Code：「a violation of our Terms of Service」，可能停權；條款第 6 段：用第三方軟體存取服務屬違約 | 10-08：不支援，「can trigger automated ToS enforcement and account suspension」；10-07 同一人說過可以，跟 10-08 與現行 FAQ 矛盾 | 11-16：delegate_task 這類派工改用 Gemini API 金鑰；11-20：不支援 |
| 第三方 agent 改用 API 金鑰或 Vertex | FAQ：「we recommend using a Gemini Enterprise or Google AI Studio API key」；安裝文件有設定方法 | 10-08：同 | 11-16、11-20：同 |

執法紀錄：2026-02 Google 切斷 OpenClaw 經 Antigravity OAuth 的存取（VentureBeat、The Register）；論壇有不少 403「Service disabled for violation of Terms of Service」的申訴。條款第 6 段寫的後果是停用「Antigravity and/or Gemini CLI accounts」，沒寫會不會波及其他 Google 服務。

## 四、對 OmniKit 現在的影響

- 派工政策（`data/rules/dispatch-policy.md`，`run.py show`）讓 Claude 主控自動派 Gemini：前置苦工、第二意見、獨立驗收的第二意見、中級任務的第 2 順位。管道是 delegate_task、t3_thread_launch、t3_cli、agy_cli，全部落在 `antigravity_ryan` 這個訂閱帳號，屬於 FAQ 說不支援的「第三方 agent 驅動」。
- 12-01 要上的 R1 審查槽位（Gemini 4 Hydrogen xhigh、T3 看得到的對話）也是同一種。
- `data/profiles/ryan/dispatch.md` 寫「同一類別列了好幾個實例時由上往下用」。Antigravity 這邊目前靠 `needs_user`（Ryan 開帳號才用），還算手動；如果把 5 個新帳號排進 classes，讓 agent 額度用完自動換，就是 FAQ 明寫不支援的自動輪換。

## 五、等 Ryan 決定

### 決定 1：新帳號怎麼用

| 選項 | 做法 | 能用到的量 | 風險 |
| --- | --- | --- | --- |
| 1A（建議） | 你自己開的對話用訂閱帳號，一次一個；這個帳號的 5 小時或每週額度用完，你在 T3 手動換下一個開新對話。要平行就用帳號內建的 Orchestrator、子代理、`/swarm`。5 個新帳號不排進自動派工。 | 每週額度約 6 倍（依序用） | 落在官方文件與 staff 回覆說可以的範圍 |
| 1B | 1A 加上幾個帳號同時開（都是你自己開的對話） | 同時跑的量最大 | 官方沒明文；回覆過一模一樣情境的人（沒有 staff 標記）說不支援、會自動停權；最壞 6 個帳號一起被停 |
| 1C | 6 個帳號都排進自動派工，額度用完自動換 | 最省事 | FAQ 明寫不支援，條款寫可能停權；不建議 |

另一條路（論壇建議，非官方）：要同時跑很多，官方方向是升級成一個 Ultra（額度最高、有 Carbon、每月 USD 100 Cloud 抵免額），而不是疊好幾個 Pro。Ultra 價格、5 個 Pro 能不能退，都沒查。

### 決定 2：Claude 自動派給 Gemini 的工作（前置苦工、第二意見、12-01 的 R1 審查槽位、傍晚調研）

| 選項 | 做法 | 風險與成本 |
| --- | --- | --- |
| 2A（建議） | 改走 agy 的 API 金鑰或 Vertex（ADC）模式，花 Cloud 抵免額 | 官方建議的做法。估算：11-19 那題 Neon High（5 個檔約 950 行）照 API 牌價約 USD 0.5 到 0.9（看 cache 怎麼計價）；Hydrogen 約一半 |
| 2B | 照舊派給 `antigravity_ryan` 訂閱帳號 | 不花錢；FAQ 說不支援，條款寫可能停權 |

2A 的帳單來源：

- 每個 Pro 附每月 USD 10 Google Cloud 抵免額（Google Developer Program premium，2026-01-27 起併進 Pro；金額出自搜尋摘要，待讀原文；要先在 Developer Program 啟用並綁帳單），可用在 Vertex AI 與 Gemini API，一年後到期。
- 你現有的 Vertex 抵免額（`data/profiles/ryan/AGENTS.md` 有提到）。
- 把好幾個帳號的抵免額合在同一個自動流程裡用，算不算 pooling 沒查到規定（待驗證），建議先只用主帳號的。

### 確認：5 個帳號的來源

是不是用你自己的 Google 帳號，直接跟 Google 訂的正式付費方案（不是試用、不是轉售或共用）？只有非試用的付費 Pro 才有 Hydrogen 與 Claude 5.5；staff 說問題常出在「discounted or shared pool」的帳號。

## 六、選 1A 加 2A 之後要做的事

- 【等使用者】在 T3 加 5 個 Antigravity 實例並登入（登入只能你做）；接好後我用 `orchestrator_capabilities` 確認每個帳號的模型。
- 【agent】`data/profiles/ryan/dispatch.md`：新帳號登記成「人開的對話用、手動切換」，不進自動派工的 classes；ava、kai 從派工拿掉（11-30 後只剩 Flash）；`AGENTS.md` 的 Flash 主線限制只跟 ava、kai 有關，跟著拿掉。
- 【agent】自動派工改走 API：照官方安裝文件，`~/.gemini/antigravity-cli/settings.json` 設 `{"modelProvider": "gemini"}` 再 export `GEMINI_API_KEY`（只設環境變數沒用），或 `AGY_ADC_AUTH=true` 走 Vertex。要維持 T3 看得到，做一個 API 模式的 T3 Antigravity 實例（以前 ACP 轉接程式用 binaryPath 包一層的做法可以沿用，可以這樣做，未實測）；做不到就退回 agy_cli 無頭模式，回報寫明 T3 看不到。
- 【agent】R1 審查槽位 12-01 照這個管道上線。
- 凍結到 11-29：這些算「修錯」（規約風險），可以在凍結期做；模型角色化（Plan B）照原訂 12-01。

## 七、沒查或待驗證

- 新帳號實際的模型清單（接進 T3 後確認）。
- Neon 在 Antigravity 額度裡扣幾倍；Pro 每週上限的實際數字（官方只寫「generous」，論壇有不少週額度鎖好幾天的抱怨）。
- 同一人的幾個帳號同時用：沒有官方明文，只有沒 staff 標記的回覆。
- Pro 附的 Cloud 抵免額金額、能不能多帳號合用。
- API 金鑰模式下 agy 能用哪些模型：官方安裝文件沒寫限制，API 牌價表有 Neon 與 Hydrogen；Claude 應該不行（沒查）。官方 Models 頁寫 ADC 模式下 Orchestrator 固定是 Carbon 規劃加 Hydrogen 執行。
- 沒做飽和調研：多帳號輪換的開源工具（例如 opencode-antigravity-auth）正是條款禁止的用法，沒有展開。

## 來源

官方：

- [Google Antigravity Additional Terms of Service](https://antigravity.google/terms)（第 6 段）
- [Antigravity FAQ](https://antigravity.google/docs/faq)
- [Antigravity Plans](https://antigravity.google/docs/plans)、[Models](https://antigravity.google/docs/models)、[ACP](https://antigravity.google/docs/ide/extensions/acp)、[Headless](https://antigravity.google/docs/cli/headless)、[Subagents](https://antigravity.google/docs/subagents)、[Swarm](https://antigravity.google/docs/swarm)、[Authenticate](https://antigravity.google/docs/install)
- [Introducing Gemini 4 Neon（Google 印度）](https://blog.google/intl/en-in/products/introducing-gemini-4-neon/)、[Gemini 4 Neon in Google Antigravity](https://antigravity.google/blog/gemini-4-neon-in-google-antigravity)
- [New developer tools for Google AI Pro and Ultra subscribers](https://blog.google/innovation-and-ai/technology/developers-tools/gdp-premium-ai-pro-ultra/)、[Google Developer Program Benefits FAQ](https://developers.google.com/profile/help/benefits)（只看了搜尋摘要）

論壇（Google AI Developers Forum）：

- staff 標記：[174378](https://discuss.ai.google.dev/t/174378)（07-15，手動切換）、[186246](https://discuss.ai.google.dev/t/186246)（10-07）、[187241](https://discuss.ai.google.dev/t/187241)（10-08，第三方 agent）
- 沒有 staff 標記：[200536](https://discuss.ai.google.dev/t/200536)（11-16，多帳號同時跑在 T3）、[185460](https://discuss.ai.google.dev/t/185460)（09-28，多帳號輪換）、[190436](https://discuss.ai.google.dev/t/190436)（10-19，手動切換）、[201688](https://discuss.ai.google.dev/t/201688)、[202874](https://discuss.ai.google.dev/t/202874)（11-20）

媒體：

- [Interesting Engineering：Gemini 4 Hydrogen 評測](https://interestingengineering.com/ai-robotics/google-gemini-4-hydrogen-coding-benchmark)
- [VentureBeat：Google 切斷 OpenClaw](https://venturebeat.com/orchestration/google-clamps-down-on-antigravity-malicious-usage-cutting-off-openclaw-users)、[The Register](https://www.theregister.com/2026/02/23/google_antigravity_compute_burden/)
