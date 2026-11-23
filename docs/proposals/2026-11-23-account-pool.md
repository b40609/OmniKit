# 帳號池與多模型分工機制（v3，D1 到 D6 已定案）

狀態：定案，第一階段實作中。Ryan 2026-11-23 的要求：完整配套機制、不要寫死的規則；業界頂尖的多模型分工；之後開源，每個使用者的帳號與習慣都不同，要能自己選或照分析給建議。
依據：3 份調研（`data/evals/2026-11-23-account-pool-research-A1.md`、`-A2.md`、`2026-11-23-multimodel-workflow-research.md`）、11-22 的帳號池評估與多使用者角色調研、2026-11-23 實測。

## Ryan 的決定（2026-11-23）

| # | 決定 | 結果 |
|---|---|---|
| D1 | 自動派工的 Gemini 走哪條路 | **不用 Vertex**（Ryan：之前用過抵免額，流程繁雜、設定困難）。維持 2B：自動派工只用 `antigravity_ryan`，不輪換、一次一條；用完照 D2 的接手順序 |
| D2 | 額度用完怎麼辦 | 自動派工照第四節的接手順序，先用同一個帳號的 Claude 額度桶，再換 Claude 帳號，最後停下來列出各帳號剩多少、幾點重置、建議換哪個（`prompt_manual_switch`）。Ryan 自己開的對話也用 `prompt_manual_switch` |
| D3 | 3 個 Claude 帳號依額度自動挑 | 同意。3 個帳號都在 Ryan 本人名下（`owner: self`），只在工作包邊界挑，同一條對話不中途換；`tos_ack` 2026-11-23 |
| D4 | 解凍與實作 | 同意，今天開始，分三階段（第十節） |
| D5 | 調研 | 不再查，接受現有結果 |
| D6 | 回報 T3 | 已送出：(1) bug [pingdotgg/t3code#41197](https://github.com/pingdotgg/t3code/issues/41197)（登入後預設思考程度不固定）(2) 額度開放給 agent：上游規定 feature request 走 Discussions，同類 issue #28202、#31699、#39185 都以 not planned 關掉，所以改在既有討論 [#15137](https://github.com/pingdotgg/t3code/discussions/15137) 補 Antigravity 分桶的用例並按讚（PR #24412 曾實作 `provider_usage` 工具，10-30 關閉未合併） |
| D7 | 舊又 CP 值低的模型（Ryan 11-23 追加） | 3.8 Flash、GPT-OSS 120B 退出 Ryan 的分工；OmniKit 自動過濾這類模型（第七節「模型淘汰過濾」） |

## 一頁統整（每輪討論更新）

| # | 問題 | 現況 | 狀態 |
|---|---|---|---|
| 1 | 第 5 個帳號 | 實例 `antigravity_itri`，6 個模型都能用 | 完成 |
| 2 | 額度用完怎麼辦 | 帳號池五層機制（第三節）＋接手順序（第四節），D1 到 D3 已定 | 第一、二階段實作 |
| 3 | Neon Extra、Plan B 何時做 | Neon Extra 就是 xhigh，伺服器端生效；Ryan 暫定 `max_available`（已寫進 profile），其他使用者可選四種模式（第八節）；Plan B 今天解凍 | 實作中 |
| 4 | 舊資料夾 | 11 個、約 1.9 GB 已刪，剩 6 個現役實例 | 完成 |
| 5 | 預設思考程度不一樣 | T3 探測模型清單時的時序問題，跟帳號無關（第五節） | 完成，已回報 T3 #41197 |
| 6 | 頂尖多模型分工 | 調研證據已併入（第七節） | 已定 |
| 7 | 3.8 Flash、GPT-OSS 這類模型 | 退出分工；OmniKit 自動過濾（第七節） | 第一階段實作 |

## 二、2026-11-23 實測

- 6 個 Antigravity 帳號（`ryan`、`kanny163`、`km0529`、`stk608`、`stk824`、`itri`）× 6 個模型（Neon、Argon、Hydrogen、Orchestrator (Neon)、Orchestrator (Argon)、3.8 Flash）：36/36 能用，每條都讀到規則版本 2026-11-21-1。回覆 4 到 43 秒。11-22 的 403 本人驗證沒再出現。
- itri 改用「一條對話輪流換模型」（`t3_thread_configure` 換模型再送訊息）：一條對話測完 6 個模型；ACP log 確認伺服器端真的切到 `Gemini 4 Neon (XHigh)`、`Gemini 4 Hydrogen (XHigh)`。
- Orchestrator (Neon)、(Argon) 伺服器端只有一個型號，選 xhigh 型號不變：T3 列出的思考程度對 Orchestrator 可能沒作用（待驗證）。
- 6 個帳號的 `mcp_config.json` 都是空的：Gemini 帳號沒接任何 MCP server。

## 三、帳號池機制（五層：設定是資料、狀態另存、規約強制）

業界共同骨架（A1、A2 兩位研究者獨立得到同樣結論；Hermes、OpenClaw、TeamClaude、claude-swap、Antigravity-Manager、opencode-antigravity-auth 的官方文件或原始碼）：

1. **帳號名冊（設定，可進 git）**：自動從 T3 `settings.json` 的 `providerInstances` 讀出實例；只問偵測不到的：
   - `label`、`provider`、`auth_mode`（`subscription`、`api_key`、`vertex`）、`plan_tier`、`owner`（必須是本人）、`usage_scope`（`manual_only`、`auto_dispatch`、`fallback_only`）、`max_concurrency`（Antigravity 訂閱預設 1）、`priority`、`config_dir`、`paused`、`tos_ack`（知情同意的日期與範圍，例如 Ryan 的 2B）。
   - 新帳號預設 `manual_only`；改成 `auto_dispatch` 要對照規約表，規約表說不允許的要填 `tos_ack`。
2. **規約表（共用層，附一手來源與查證日期）**：每個「供應商＋登入方式」一筆：`tos_verdict`（`ok`、`caution`、`avoid`）、`allow_auto_rotation`、`allow_third_party_dispatch`。2026-11-23 一手原文：
   - Google Antigravity FAQ：「Wrapping agy inside third-party coding agents or applications, or automating account rotation, is not supported under consumer plans.」→ 訂閱：`avoid` 自動派工與輪換；API 金鑰、Vertex：`ok`。
   - Anthropic Consumer Terms：除 API 金鑰或明示允許外，不得「access the Services through automated or non-human means」；Claude Code 文件：多帳號「give each account its own configuration directory」。→ 訂閱：`caution`；API 金鑰、Bedrock、Vertex：`ok`。
   - 三家都禁止把帳號給別人用。
3. **狀態（本機、可刪重建，不進 git，不存 token）**：`~/.omnikit/dispatch/pool-state.json`。每個帳號分開記、互不覆寫：
   - `paused`（你手動停）、`auth_expired`（401，要重登）、`validation_required`（403 要本人驗證，附連結）、`tos_banned`（403 `TOS_VIOLATION`）、`model_forbidden`（只停該帳號的該模型）、`quota_cooldown`（429 額度用完，到重置時間）。
   - 速率型 429 不換帳號，原帳號稍等；額度型 429 才換。查不到最新額度時保留上次的值、標 `stale`，不當成 0% 或 100%。
   - 注意（A2，Antigravity-Manager 原始碼）：被停權的帳號查額度仍回 200，只有真的送一輪對話才會回 403 `TOS_VIOLATION`；所以健康檢查要包含一次真正的對話，不能只查額度。
4. **自動探測（新帳號接入）**：名冊多出新實例 → 你按一次觸發 → 一個帳號開一條 T3 對話，輪流換每個模型、開到最高檔 → 記能不能用、實際程度、有沒有讀到規則、耗時 → 寫進能力矩陣 → 自動結案。帳號移除 → 列出孤兒資料夾等你確認。只有登入、本人驗證、付款要你做。
5. **路由**：任務 → 角色 → 候選模型鏈 → 帳號（依規約、狀態、`usage_scope`、`max_concurrency`）→ 思考程度（依第八節的模式）→ 管道（照 visibility）。
   - 帳號黏著：同一個工作包從頭到尾同一個帳號，換帳號只在工作包之間（換帳號會丟 prompt cache）。
   - 選帳號策略（只對允許自動挑的帳號）：`weekly-first`（先用最快重置、還有剩的帳號，因為沒用完的週額度到期作廢）＋門檻＋防來回跳（領先 5 個百分點以上才換、換完至少隔 5 分鐘）。
   - `run.py show` 每一格印原因：選了誰、跳過誰、為什麼。

## 四、額度用完的接手

- 一手證據（T3 v0.1.12 server 原始碼 `summaryWindows`，2026-11-23 讀）：一個 Antigravity 帳號的額度分好幾桶，依 `bucketId` 分家族：`gemini-*` 算「Gemini」、`gemini-argon-*` 算「Gemini Argon」（自己一桶）、`gemini-carbon-*` 算「Gemini Carbon」、`3p-*` 算「Claude & GPT (shared)」；每桶各有 5 小時與每週兩個窗口，各自的剩餘比例與重置時間。所以 Gemini 用完時，同帳號的 Claude 額度桶多半還在（Opus 與 Sonnet 共用這一桶，量少）。哪個模型扣哪一桶，等讀得到額度後實測（待驗證）。
- 自動派工的接手順序（Ryan D1、D2 定案；每段都能在 profile 開關）：
  1. `antigravity_ryan` 的 Gemini（Neon、Hydrogen）。
  2. 同一個帳號的另一個 Gemini 桶（Argon，自己一桶；Argon 還在試用，只接它能做的角色）。
  3. 同一個帳號的「Claude & GPT」桶：Claude Opus 5.5 或 Sonnet 5.5（最高 high；Opus 子任務照 Ryan 規則用 medium）。仍是 2B 這一個帳號，不算輪換。
  4. Claude 實例（`claudeAgent`、`claudeAgent_2`、`claudeAgent_claude_kai`），在工作包邊界依額度挑（D3）。
  5. `prompt_manual_switch`：停下來列出每個帳號剩多少、幾點重置，建議換哪個，等 Ryan 決定。
  - 例外：派給 Gemini 的理由是「跨家審查 Claude 寫的東西」時，跳過第 3、4 步（換成 Claude 就失去跨家的意義），直接到第 5 步，或改用同模型新對話審。
- 你自己開的對話（`prompt_manual_switch`）：顯示「ryan 剩 3%、7 小時後重置；建議下一條改用 km0529（剩 80%）」。換帳號接續靠交接檔，因為每個帳號的 Antigravity 對話記憶是分開的。
- 額度資料來源：
  - Claude：Claude Code 狀態列本來就有 5 小時與 7 天用量（OmniKit 已接 `~/.claude`；要擴到 `~/.claude-kai`、`~/.claude-retis`）。
  - Antigravity：T3 的 Usage → Limits 頁面看得到各帳號各桶的剩餘與重置時間，但 MCP 與 CLI 都沒開放（2026-11-23 查：`t3 --help` 沒有用量子指令，`agy --help` 沒有用量選項，T3 不把額度寫進硬碟）。上游討論 #15137 在等；開放前 `prompt_manual_switch` 列出 OmniKit 自己記到的（429 錯誤帶的重置時間、上次讀到的值，標「舊資料」），其餘請你看 Usage → Limits。A2 提的 `agy -p /usage --output-format json` 不在 help 裡，能不能用、能不能指定帳號待驗證。
  - OmniKit 一律不讀 token。

## 五、為什麼 T3 預設思考程度會不一樣

- 4 個新帳號的 ACP 設定檔一模一樣，伺服器端登入時的預設都是「Gemini 4 Neon (High)」。
- T3 登入後把每個模型都切一次（`publishCatalog`），最後切回 Neon 時只帶模型名、沒帶程度，伺服器給了 Medium；T3 記下的「預設」是最後收到的那次設定更新，兩個事件誰先到不一定，所以有的記成 high、有的記成 medium。
- 結論：T3 的時序問題，跟帳號無關，每次重新登入都可能不同。派工一律明寫程度；自己開對話時看一下程度選單。

## 六、舊資料夾（Ryan 11-23 回「刪」，已刪）

11 個、約 1.9 GB：ava、kai、內建預設實例 `antigravity`、舊 id `antigravity_1` 到 `5`、3 個 11-20 的暫時實例。刪前確認不是現役實例、沒有程序在用；`skills` 連結先拆再刪，共用 `~/.gemini/config/skills` 完好。剩 6 個現役實例。

## 七、多模型分工

調研證據（`2026-11-23-multimodel-workflow-research.md`）：

- **審查者不能比作者弱**：一項實驗裡 Codex 審 Claude 的草稿，通過率從 91.4% 掉到 82.8%；弱模型跨家審查不比同模型新對話好。「同模型新對話審一次＋夠強的另一家審一次」抓到 56.7% 的預埋錯誤，兩次同模型 42.7%。強作者自審沒增益，多 72% 成本。
- **思考程度沒有證據支持全開最高**：Anthropic 官方說 xhigh 給超過 30 分鐘的長任務、max 只在量到增益時開；第三方實測 Gemini 4 Argon 開高檔 token 約 9 倍、分數不變；max 在輸出上限下反而掉分。T3 對 Antigravity 寫死 15 分鐘無輸出逾時，長思考會撞到。
- **orchestrator 加 subagents**：Anthropic 官方數據研究類贏單 agent 90.2%，但用 15 倍 token，「多數寫碼任務可平行的部分少」。
- **council、best-of-N**：沒有程式碼品質的對照實驗；best-of-N 要有測試挑選才划算。
- **新模型上線**：小題組＋能自動判對錯的驗證（跑測試、比對輸出，不靠 LLM 評審）→ 試用 → 累積真實委派紀錄。

分工設計：

- 角色不分廠牌（沿用 11-22 調研）：定案與高風險、主力實作、前置苦工與調研、快速雜事、審查、大工作包。審查者以「主控是誰」相對定義：永遠是另一個、而且不比作者弱的模型。
- 審查有目的才開：一般任務用同模型新對話審；高風險（帳務、風控、下單）或有明確理由才加跨家審查。
- 指派由資料推出：能力矩陣（探測）＋試用成績（委派紀錄一次通過率，樣本 20 筆以上才算）＋規約＋使用者偏好 → 每個角色的候選鏈，每格附原因。
- 新模型、新帳號自動進「試用」：探測通過 → 煙霧題組（5 到 10 題、能自動判對錯）→ 累積委派紀錄 → 每週差異提醒建議升級或下架。
- Ryan 現況的初步分工：

  | 角色 | 第一順位 | 備註 |
  |---|---|---|
  | 主控、定案、高風險 | Claude Opus | 帳務、風控、下單的紅線不變 |
  | 主力實作 | Claude Opus 或 Sonnet；你自己開的對話可用 Neon xhigh | |
  | 前置苦工、調研 | Neon xhigh | 自動派工走 `antigravity_ryan`（D1），用完照第四節 |
  | 審查 | 同模型新對話；高風險加 Neon xhigh 或 Hydrogen xhigh（作者是 Claude 時） | |
  | 可平行的研究、審查、文件大工作包 | Orchestrator (Neon) | 寫碼不拆 |
  | 快速雜事、文件 | Hydrogen | 取代 3.8 Flash（D7） |
  | 待定 | Argon | 進試用，用煙霧題組決定擺哪 |
  | 不用 | 3.8 Flash、GPT-OSS 120B | 被過濾（見下） |

### 模型淘汰過濾（D7，Ryan 11-23：「OmniKit 應該幫用戶自動過濾這種舊又 CP 值低的爛模型」）

- 證據（2026-11-23 查）：T3 每天下載的模型單價表（`~/.t3/userdata/usage-model-rates.json`，內容是 LiteLLM 的模型價格資料）裡，`github_copilot/gemini-3.8-flash` 與 3.6、3.7 Flash 的 `successor_model` 都寫 `gemini-4-hydrogen`（Google 自己的 `gemini/`、`vertex_ai/` 3.8 Flash 條目還沒標，所以規則 1 要跨供應商比對同名模型）；同一份表的 API 單價 Hydrogen 是 3.8 Flash 的 2 倍（每百萬 token 輸入 1.5 對 0.75 美元、輸出 7.5 對 3.75），所以淘汰的理由是「有後繼模型」，不是「比較便宜」。訂閱方案看的是每輪扣多少額度，兩者扣不扣同一桶、各扣多少，等讀得到額度後實測（待驗證）。
- 規則（資料驅動，不寫死模型名）：
  1. **有後繼模型或已公告下架**：價格表的 `successor_model`、`deprecation_date` 有值 → 標「已淘汰」，原因寫出後繼是誰。
  2. **被同帳號的模型完全壓過**：同一個帳號、同一個額度桶裡，有另一個模型的能力等級不低於它、而且已通過探測 → 標「被取代」。
  3. **沒有任何角色會選它**：不在任何角色的候選鏈裡，也沒在試用（例如 GPT-OSS 120B）→ 標「不使用」。
- 被過濾的模型：探測時跳過（省時間），`run.py show` 不列進候選，只在最後一行寫「已過濾：3.8 Flash（後繼 Hydrogen）、GPT-OSS 120B（沒有角色使用）」；使用者可以在 profile 用 `include_models` 撈回來，或用 `exclude_models` 再多排除。
- 給新使用者：只有舊模型可用的帳號（例如 11-22 退掉的 Jio 方案只剩 3.8 Flash）不會被過濾掉，因為規則 2 只在同帳號有更好的模型時才生效；規則 1 也只降順位，該帳號沒別的選擇時仍可用，並標原因。

## 八、每個使用者自己選的設定（開源時的核心）

原則（Ryan 11-23）：Ryan 的偏好只套 Ryan 的 profile；每個選項都有「可選的模式＋依偵測結果給的建議（附原因）」，使用者的選擇永遠優先。

| 選項 | 模式 | Ryan 現在 | 給新使用者的建議規則 |
|---|---|---|---|
| 思考程度 `thinking_preference` | `max_available`（每個模型最高檔）、`balanced`（定案、審查、前置苦工最高，其他 high）、`economy`（只有定案與審查最高）、`custom` | `max_available`（暫定，兩週後用自己的數據檢查） | 同家多帳號且近 7 天很少撞額度 → `max_available`；一到兩個帳號 → `balanced`；單帳號常撞額度 → `economy`；選了最高卻一週撞額度好幾次就提醒降一級 |
| 額度用完 `on_exhausted` | `fail_closed`、`prompt_manual_switch`、`fallback_paid_api` | `prompt_manual_switch`（D2），前面先走第四節的接手順序 | 有 API 金鑰或 Vertex 而且設定得起來 → `fallback_paid_api`；怕意外帳單 → `fail_closed`；其他 → `prompt_manual_switch` |
| 模型過濾 | 預設開；`include_models`、`exclude_models` 覆寫 | 開，排除 3.8 Flash、GPT-OSS 120B（D7） | 預設開，每個被過濾的模型附原因 |
| 帳號用途 `usage_scope` | `manual_only`、`auto_dispatch`、`fallback_only` | Antigravity 訂閱 `manual_only`（除了 2B 的 ryan） | 預設 `manual_only`；規約表 `avoid` 的要填 `tos_ack` 才能改 |
| 選帳號策略 | `sticky`、`weekly-first`、`priority`、`least-used` | Claude 三個帳號 `weekly-first`＋黏著（D3）；Antigravity 自動派工固定 `antigravity_ryan` | 1 個帳號 → `sticky`；同家多帳號 → `weekly-first`＋黏著 |
| 派工可見度 `visibility` | `visible`、`headless` | `visible`（11-21 定案） | 預設 `visible` |
| 通知 | 無、桌面、手機推播 | 待定 | 有帳號進入 `validation_required`、`auth_expired` 時一律通知 |

初次設定（`omnikit-setup` 加 4 到 5 題）：自動掃描 T3 實例、各 `CLAUDE_CONFIG_DIR`、`CODEX_HOME`、環境變數裡有沒有 API 金鑰（只看有沒有，不讀值）→ 問方案、用途、額度用完偏好、思考程度偏好、通知 → 跑探測 → 產出 profile，每格附原因。

## 九、還要處理的事（Ryan 提的之外）

- 帳號身分對應：實例 id、Google 帳號、方案、續訂日；續訂日前提醒。
- 登入過期與本人驗證要主動偵測並通知，不要等派工失敗。
- 每個帳號的對話記憶各自獨立：換帳號靠交接檔。
- 並行上限，以及 Antigravity 寫死的 15 分鐘無回應逾時。
- Gemini 帳號沒接 MCP（`mcp_config.json` 全空）：要不要統一接 T3 MCP 等。
- 多台電腦：實例 id 可能不同，名冊分機器；額度快照可經狀態 repo 共享，避免多台重複查。
- 不是每個使用者都有 T3：名冊也要支援只用 Claude Code 多個 `CLAUDE_CONFIG_DIR`、Codex 多個 `CODEX_HOME`。
- 紅線（預設關、不內建）：訂閱登入代理（CLIProxyAPI 這類）、訂閱帳號自動輪換、多人共用帳號、偽造指紋或換 IP 繞過風控。

## 十、實作階段（D4，解凍後）

1. **第一階段：名冊與探測**：名冊欄位與規約表（遷移 `data/profiles/ryan/dispatch.md`）、`provider-terms-policy`、模型淘汰過濾、探測指令（T3 MCP，一個帳號一條對話、自動結案、跳過被過濾的模型）、`run.py show` 每格附原因、Ryan 的選項寫進 profile。
2. **第二階段：狀態與接手**：錯誤分類寫進委派紀錄、`pool-state.json`、`on_exhausted` 接手、額度視圖（Claude 狀態列擴到三個設定目錄；Antigravity 等 T3 介面或 `agy /usage`）、通知。
3. **第三階段：評測與新使用者**：煙霧題組（含同題 high 對 xhigh）、試用狀態、每週差異提醒、`omnikit-setup` 訪談與建議器。

每階段完成條件：這台實測通過、`run.py show` 印得出來、commit 並 push、更新 NOW.md。
