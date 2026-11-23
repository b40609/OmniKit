# 帳號池與多模型分工機制（討論稿）

狀態：討論中（Ryan 2026-11-23 要求：完整配套機制，不要寫死的規則；業界頂尖的多模型分工；之後開源，每個使用者都不同）。
業界做法的證據等 3 份調研回來再補（`data/evals/2026-11-23-account-pool-research-A1.md`、`-A2.md`、`2026-11-23-multimodel-workflow-research.md`）。

## 一頁統整（每輪討論更新）

| # | 問題 | 現況 | 狀態 |
|---|---|---|---|
| 1 | 第 5 個帳號 | 已登入，實例 `antigravity_itri`，6 個模型實測都能用 | 完成 |
| 2 | 額度用完怎麼辦 | 提出「帳號池機制」五層（第三節），額度用完走四段接手（第四節） | 等 Ryan 選接手模式 |
| 3 | Neon Extra、Plan B 何時做 | Neon Extra 就是 Neon xhigh（T3 標成 Extra High），伺服器端實測生效。Ryan 11-23 暫定「每個模型開到最高檔」（已寫進 `data/profiles/ryan/dispatch.md` 的 `thinking_preference: max_available`）；其他使用者要能自己選或照分析建議（第七節）。Plan B 不等 12-01 | 思考程度：Ryan 暫定；解凍：照提議 |
| 4 | 舊資料夾 | 11 個、約 1.9 GB，Ryan 11-23 同意後已刪（共用 skills 資料夾完好，剩 6 個現役實例） | 完成 |
| 5 | 預設思考程度不一樣 | T3 探測模型清單時的時序問題，不是帳號差異（第五節） | 已查清 |
| 6 | 頂尖多模型分工 | 角色不分廠牌、指派由資料推出、新模型自動試用（第七節） | 等調研補證據 |

## 二、2026-11-23 實測

- 6 個 Antigravity 帳號（`ryan`、`kanny163`、`km0529`、`stk608`、`stk824`、`itri`）× 6 個模型（Neon、Argon、Hydrogen、Orchestrator (Neon)、Orchestrator (Argon)、3.8 Flash）：36/36 能用，每條都讀到規則版本 2026-11-21-1（GEMINI.md 有載入）。回覆時間 4 到 43 秒。11-22 的 403 本人驗證沒再出現。
- itri 改用「一條對話輪流換模型」測（`t3_thread_configure` 換模型再送訊息）：6 個模型一條對話測完，ACP log 確認伺服器端真的切到 `Gemini 4 Neon (XHigh)`、`Gemini 4 Hydrogen (XHigh)`。之後新帳號照這個做，一個帳號一條對話。
- Orchestrator (Neon)、Orchestrator (Argon) 伺服器端只有一個型號（`MODEL_PLACEHOLDER_M537`、`M668`），選 xhigh 時型號不變，回覆也說「未另列思考程度」：T3 雖然列出思考程度選項，對 Orchestrator 可能沒有作用（待驗證）。
- 每個帳號的 `mcp_config.json` 都是空的：Gemini 帳號沒有接任何 MCP server（要不要接，見第八節）。

## 三、帳號池機制（五層，全部是資料＋程式，不寫死）

1. **帳號名冊（registry）**：自動從 T3 的 `settings.json` `providerInstances` 讀出所有實例（Claude 的 `homePath`、Antigravity 的 `sha256(實例 id)` 資料夾，`engine/scripts/homes.py` 已會算），只問使用者偵測不到的事：方案、用途（只給人用／可自動派工）、是否同意某項風險。存在個人 profile，不進共用 repo。
2. **自動探測（onboarding probe）**：名冊多出新實例 → 自動開一條探測對話，輪流換每個模型、開到最高思考程度，記錄能不能用、實際程度、有沒有讀到規則、回覆時間 → 寫進能力矩陣 → 自動結案。帳號移除 → 列出孤兒資料夾等確認。不用再像今天這樣手動開 30 條。
3. **帳號狀態**：`ready`、`cooling`（429，記到重置時間）、`needs_verification`（403，要本人驗證）、`signed_out`（登入過期）、`retired`。來源：派工失敗的錯誤分類（委派紀錄加 `error_type`），以及 T3 自己的額度探測（T3 已經對每個 Claude、Antigravity 實例查剩餘額度與重置時間，但只推給畫面，沒有給 agent 的介面：要讀得向 T3 提功能需求，或走 T3 的 WebSocket，待驗證）。OmniKit 不讀 token。
4. **規約層**：每個「供應商＋登入方式」一筆政策資料（沿用 11-22 調研的 `tos_verdict`、`allow_third_party_dispatch`、`allow_auto_account_rotation`、`max_concurrent_runs`），附一手來源與查證日期。使用者明示同意某項風險時，記下同意的日期與範圍（例如 Ryan 11-22 的 2B）。
5. **路由**：任務 → 角色 → 候選模型鏈（由能力矩陣、試用成績、使用者偏好排出）→ 帳號（依規約與狀態挑）→ 思考程度（預設該模型最高檔）→ 管道（照 visibility）。每次選擇附一行原因，`run.py show` 印得出來。

## 四、額度用完的接手（要你選模式）

查證背景（11-22，`data/evals/2026-11-22-gemini-pro-pool.md`）：Google 官方 FAQ 寫消費方案不支援「自動輪換帳號」與「第三方 coding agent 驅動 agy」，條款寫可能停權；官方建議自動化改用 Gemini API 金鑰或 Vertex。新發現：T3 的 Antigravity 實例本來就支援四種登入方式：Google account、Gemini Enterprise、Gemini API key、Agent Platform (Vertex AI)（T3 原始碼 `ANTIGRAVITY_AUTH_METHODS`）。

接手順序（由上往下，每一段都可以在 profile 開關）：

1. **合規的自動通道**：新增一個用 Agent Platform (Vertex AI) 登入的 Antigravity 實例，吃你的 Vertex 抵免額。自動派工都走這裡，就不用碰「訂閱帳號被第三方驅動、自動輪換」這兩條紅線。待驗證：Vertex 上有沒有 Neon、Hydrogen，價格多少。
2. **換一家**：同一個角色改派 Claude（3 個實例）。
3. **同家換訂閱帳號**，三種模式給你選：
   - 手動：通知你「ryan 已用完，建議換 km0529（剩 80%，重置時間 X）」，你在 T3 自己換。
   - 半自動：agent 把要派的對話準備好、指定到建議的帳號，你按一下送出。
   - 全自動：額度用完就自動換下一個帳號。FAQ 明寫不支援，最壞 6 個帳號一起被停；要選就記下你的同意。
4. **排隊等重置**：在 NOW.md 和手機通知寫重置時間。

我的建議：1＋2 給自動派工，3 用半自動給你自己開的對話，全自動不開。

## 五、為什麼 T3 預設思考程度會不一樣

- 4 個新帳號的 ACP 設定檔一模一樣，伺服器端登入時的預設都是「Gemini 4 Neon (High)」（ACP log `Setting default model override: Gemini 4 Neon (High)`）。
- T3 登入後會把每個模型都切一次，看各自有哪些思考程度（`publishCatalog` 逐一 `setModel`），最後切回 Neon；但切回時只帶模型名、沒帶程度，伺服器就給了 Medium（log：`Switching model ... to: Gemini 4 Neon (Medium)`）。T3 記下的「預設」是它最後收到的那次設定更新，兩個事件誰先到不一定，所以有的帳號記成 high、有的記成 medium。
- 結論：是 T3 探測時序造成的，跟帳號無關，每次重新登入都可能不同。對策：派工一律明寫程度（已經是這樣）；你自己開對話時看一下程度選單。要的話可以向 T3 回報這個 bug（對外發送，先問你）。

## 六、舊資料夾（Ryan 11-23 回「刪」，已刪：失敗 0，剩 6 個現役實例，共用 `~/.gemini/config/skills` 完好）

位置 `~/.t3/userdata/providers/antigravity/`，資料夾名是 `sha256(實例 id)`。T3 目前登記的 6 個實例都不在下表。

| 資料夾（前 12 碼） | 原本的實例 | 大小 | 最後修改 |
|---|---|---|---|
| `7488c9f1793f` | `antigravity_ava`（已退出） | 654 MB | 11-20 |
| `ac0a3dfd6ddd` | `antigravity`（T3 內建預設實例，已停用） | 560 MB | 11-20 |
| `0c69a60468f0` | `antigravity_kai`（已退出） | 518 MB | 11-20 |
| `7be9b928ae8c` | `antigravity_2`（舊 id） | 32 MB | 11-23 00:50 |
| `e4d159578bfd` | `antigravity_3`（舊 id） | 32 MB | 11-23 00:19 |
| `b6f03d61511d` | `antigravity_1`（舊 id） | 27 MB | 11-23 00:18 |
| `614749390569` | 不明（11-20 建立，內容提到 kai、ava，推測是 11-20 修多帳號時的暫時實例） | 23 MB | 11-20 |
| `de4ec83f4744` | `antigravity_4`（舊 id） | 22 MB | 11-22 |
| `6603e1c9dd51` | `antigravity_5`（舊 id，沒登入過） | 21 MB | 11-23 00:19 |
| `2e75f2907653` | 不明（11-20 建立） | 21 MB | 11-20 |
| `b67963594b2b` | 不明（11-20 建立） | 21 MB | 11-20 |

共 11 個、約 1.9 GB。刪除前確認：沒有一個是現役實例的雜湊、沒有程序在用；`skills` 是指向共用資料夾的連結，先拆連結再刪，避免刪到共用 skills。`antigravity`（內建預設實例）之後如果重新啟用，T3 會自己重建資料夾。

## 七、多模型分工（等調研補證據）

- 角色不分廠牌（沿用 11-22 調研的 6 個角色）：定案與高風險、主力實作、前置苦工與調研、快速雜事、跨家審查、大工作包。
- 指派由資料推出：能力矩陣（探測）＋試用成績（委派紀錄的一次通過率）＋規約＋你的偏好 → 每個角色的候選鏈，每格附原因。
- 思考程度做成使用者自己選的模式，不是全體預設（Ryan 11-23：「其他用戶不見得跟我一樣有很多帳號可以消耗」）：

  | 模式 | 做法 | 適合誰 |
  |---|---|---|
  | `max_available` | 每個模型開到它最高檔（Neon、Hydrogen xhigh；Argon、Flash high） | 同家有多個帳號、很少撞額度（Ryan 11-23 暫定這個） |
  | `balanced` | 定案、審查、前置苦工開最高檔；雜事與文件用 high | 一家一到兩個帳號 |
  | `economy` | 只有定案與審查開最高檔，其他用供應商預設 | 單一帳號、常撞額度 |
  | `custom` | 每個角色自己填 | 想細調的人 |

  - 硬限制另外放（例如 Ryan 個人規則「Gemini 不准 low、medium」），任何模式都不能違反。
  - 建議器：setup 時與每週，依偵測到的帳號數、方案、近 7 天委派紀錄裡撞額度（429）的次數、T3 回報的剩餘額度，建議一個模式並附原因；選了 `max_available` 卻一週撞額度好幾次，就提醒降一級。使用者的選擇永遠優先。
  - 同樣的「可選模式＋分析建議」也套在：額度用完的接手模式（第四節）、選帳號策略（第三節）、自動派工能不能用訂閱帳號（規約層）。
- 新模型與新帳號自動進入「試用」：探測通過 → 小型評測 → 累積委派紀錄 → 每週差異提醒建議升級或下架。
- 以 Ryan 現況的初步分工（待調研確認）：定案與高風險、主控是 Claude Opus；前置苦工與調研是 Neon xhigh；跨家審查是 Hydrogen xhigh 或 Neon xhigh（作者是 Claude 時）；大工作包是 Orchestrator (Neon)；快速雜事是 3.8 Flash high；Argon 先進試用，用小型評測決定擺哪。

## 八、還要處理的事（你提的之外）

- 帳號身分對應：實例 id、Google 帳號、方案、續訂日要有一張表（續訂日到期前提醒）。
- 登入過期與本人驗證：狀態層要能偵測並通知，不要等派工失敗。
- 每個帳號的對話記憶各自獨立：換帳號會失去上下文，要靠交接檔。
- 每個帳號的並行上限，以及 Antigravity 寫死的 15 分鐘無回應逾時。
- Gemini 帳號沒有接 MCP（`mcp_config.json` 全是空的）：要不要統一接 T3 MCP 等。
- 多台電腦（筆電、家裡電腦）：實例 id 可能不同，名冊要分機器。
- 開源給別人：不是每個人都有 T3；名冊也要支援只用 Claude Code 多個 `CLAUDE_CONFIG_DIR`、Codex 多個 `CODEX_HOME` 的人。
