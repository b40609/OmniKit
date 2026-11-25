# OmniKit 分派政策（完整版，要派的時候才讀）

這份不會載入每段對話。常駐的規則是 `data/rules/dispatch.md`（幾行原則）；這裡是任務類型、級別、模型類別、思考程度、管道、升級與兩階段盲審協定的完整政策。讀法：用 `omnikit-dispatch` skill 的 `run.py show`，它會印出套上你的實例之後每一級可用的選項；要看管道與實測備註再讀這份原文。

你有哪些帳號、供應商實例，寫在自己 profile 的 `dispatch.md`（個人層，由 `dispatch.py` 讀取，不常駐塞進對話規則）；沒有那份就只用目前這個 agent 的原生子代理。下面的 YAML 是給 agent 與 `engine/scripts/dispatch.py` 共用的唯一來源，改了要更新 `data/rules/baseline.md` 的規則版本。

怎麼用：
1. 照 `tasks` 判斷任務類型，得到級別；在 `levels.<級別>.route` 由上往下挑第一個「你有實例、額度沒用完、`when` 成立（沒寫就算成立）、`tasks` 有列就要包含這個任務」的選項。
2. 思考程度照選項寫明（Claude 叫 `effort`，Antigravity 叫 `thought_level`），不要沿用主線的設定，也不要靠預設值。
3. 照 `channels` 選管道；派給 Antigravity 的模型時，管道照你的偏好 `visibility`（個人層 `dispatch.md` 的 `visibility`，沒寫用這裡的 `visibility.default`）；開子對話或派子代理時，在任務說明寫明級別與思考程度。派給 Antigravity 的模型時，任務說明還要照 `antigravity_turns.brief` 寫明交付檔與完成標記，驗收照 `antigravity_turns.verify`。
4. 重大架構盲審（`architecture`）與工具評測子對話，嚴格遵守 `blind_review` 協定並**隔離跨對話記憶注入**。
5. 子任務結果收回、驗收完、要 settle 之前，記一行委派紀錄（`run.py log`）；一次委派一行，重跑與升級記在同一行。
6. 驗收不過照 `escalation` 升級，升級也要記。
7. 專案規則對模型分工或驗收另有規定時，照專案規則。

```yaml
policy_version: 1

# 模型類別：個人層把它對到自己的供應商實例。思考程度選項 id：Claude（claudeAgent）叫 effort，Antigravity 叫 thought_level。
# 模型代號、預設值與上限取自 T3 orchestrator_capabilities 與實機探測（2026-11-25 實際查證）：
# - gemini-4-argon（後繼 gemini-4-carbon，且已併入 Gemini Models 桶）與 gemini-3.8-flash（後繼 gemini-4-hydrogen）已於 2026-11-25 移出類別；
#   舊模型淘汰過濾由 engine/scripts/accounts.py 依價格表資料驅動處理。
# - gemini-orchestrator 與 antigravity-opus 在 T3 目錄未列出，但 2026-11-25 經 T3 對 antigravity_ryan 送代號實測皆正常回傳 OK。
model_classes:
  claude-fable:        {model: claude-fable-5-2,            driver: claudeAgent, default_thinking: high,   max_thinking: max}
  claude-opus:         {model: claude-opus-5-5,             driver: claudeAgent, default_thinking: medium, max_thinking: max}
  claude-sonnet:       {model: claude-sonnet-5-5,           driver: claudeAgent, default_thinking: high,   max_thinking: max}
  gemini-carbon:       {model: gemini-4-carbon,             driver: antigravity, default_thinking: high,   max_thinking: high,  forbid_thinking: [low, medium]}
  gemini-pro:          {model: gemini-4-neon,               driver: antigravity, default_thinking: xhigh,  max_thinking: xhigh, forbid_thinking: [low, medium]}
  gemini-fast:         {model: gemini-4-hydrogen,           driver: antigravity, default_thinking: xhigh,  max_thinking: xhigh, forbid_thinking: [low, medium]}
  gemini-orchestrator: {model: gemini-pro-orchestrator-neon, driver: antigravity, default_thinking: xhigh, max_thinking: xhigh, forbid_thinking: [low, medium]}
  antigravity-opus:    {model: claude-opus-5-5,             driver: antigravity, default_thinking: high,   max_thinking: high}
# 2026-11-18、2026-11-25 ryan 定案：所有 Gemini 模型的調用，thought_level 永遠是 high 或更高（Neon、Hydrogen、Orchestrator 開 xhigh；
#   Carbon 最高 high；一律禁用 low、medium，dispatch.py check 與 run.py agy 會擋）。
# 背景參考（未逐一附官方原始頁 URL 的第三方網搜數據一律標【待驗證】，分派規則只寫定案後的角色與檔位）：
# - Gemini 4 Hydrogen 對 3.8 Flash：Artificial Analysis 指數與寫程式工作階段勝出，low 表現退步故禁用【待驗證】。
# - Sonnet 5.5 對 Opus 5.5：SWE-Bench Pro 與 Terminal-Bench 差異依 harness 而定【待驗證】。
# - Anthropic Applied AI〈When to fold subagents into your main agent loop〉（Diane Sarkis，2026-10-22，原文讀過）：
#   單一 agent 加 skill 常比整組子代理好，成本與等待也較低；只在 context 塞到測得出變差、要平行且各要乾淨 context、
#   或需要零錨定審查時才拆。

# 任務類型 → 級別。紀錄的 task 欄位用這裡的 key。
tasks:
  docs:            {level: medium,       desc: 規格明確的文件、報表与整理}
  readonly:        {level: medium,       desc: 大範圍讀檔、唯讀檢查、盤點、查資料}
  ui-small:        {level: medium,       desc: 介面與多檔實作}
  code-small:      {level: medium,       desc: 規格明確的小修改與多檔實作}
  accounting:      {level: high,         desc: 碰到帳務}
  risk:            {level: high,         desc: 碰到風控}
  orders:          {level: high,         desc: 碰到下單}
  design-decision: {level: high,         desc: 要做設計決策}
  hard-bug:        {level: higher,       desc: 難查的錯誤}
  acceptance-loop: {level: higher,       desc: 驗收一直不過}
  verify:          {level: verify,       desc: 獨立高風險驗收}
  architecture:    {level: architecture, desc: 重大架構決策與兩階段防迎合盲審}

# 分工與審查原則（2026-11-25 定案）：
# - 讀檔／雜務（docs、readonly）：Gemini 4 Hydrogen xhigh，或 Claude Opus effort medium。
# - 多檔／UI 實作（ui-small、code-small）：Gemini 4 Neon xhigh，或 Claude Opus effort high。
# - 高風險實作（accounting、risk、orders、design-decision）：前置 Neon xhigh，定案 Opus effort high，反向審查 Carbon high。
# - 高風險獨立驗收（verify）與難題（higher）：Claude Opus effort xhigh（不預設 max），反向審查 Gemini 4 Carbon high。
# - 重大架構兩階段盲審（architecture）：Claude Fable 5.2 effort high（死結才升 xhigh），反向審查 Gemini 4 Carbon high；
#   盲審子對話必須隔離跨對話記憶注入（見 blind_review）。
levels:
  medium:
    name: 中
    route:
      - class: gemini-fast
        thinking: xhigh
        tasks: [docs, readonly]
        note: 大範圍讀檔、唯讀檢查與文件雜務預設用 Hydrogen xhigh（2026-11-25 定案）
      - class: gemini-pro
        thinking: xhigh
        note: 多檔／UI 與中級實作預設用 Neon xhigh；Hydrogen 不可用時也接 docs／readonly
      - class: claude-opus
        thinking: medium
        tasks: [docs, readonly]
        note: 讀檔／雜務的 Claude 選項（Opus effort medium），或沒有 Gemini 實例時使用
      - class: claude-opus
        thinking: high
        tasks: [ui-small, code-small]
        note: 日常多檔／UI 實作的 Claude 選項（Opus effort high），或沒有 Gemini 實例時使用
      - class: claude-sonnet
        thinking: medium
        note: 退路：Sonnet 試行（凍結至 2026-11-29 到期檢討；沒有 Gemini 實例或省 Opus 額度時可選）
        trial: sonnet-trial
  high:
    name: 高
    prework:
      - {class: gemini-pro, thinking: xhigh, role: 前置苦工：讀程式、收資料、重現、列候選與證據，不下結論、不改檔；Opus 拿它的整理定案}
    route:
      - class: antigravity-opus
        thinking: high
        when: 本週 Claude 用量 >= 80%（見 usage_signal），而且任務是 accounting、risk 或 orders
        tasks: [accounting, risk, orders]
        note: 同帳號 Claude & GPT 桶的 Opus（2026-11-25 經 T3 實測通過），只用在這三類
      - {class: claude-opus, thinking: high}
    second_opinion:
      - {class: gemini-carbon, thinking: high, role: 反向跨家唯讀審查 Claude 的產出（審查者不比作者弱，Carbon 最高 high）}
      - {class: gemini-pro, thinking: xhigh, role: Carbon 不可用時的跨家唯讀審查備援（Neon xhigh）}
  higher:
    name: 更高
    prework:
      - {class: gemini-pro, thinking: xhigh, role: 前置苦工：讀程式、重現錯誤、縮小範圍、列假設與證據，不改檔；Opus 拿它的整理定案}
    route:
      - {class: claude-opus, thinking: xhigh, note: 不預設 max；xhigh 仍失敗時依 escalation 升 Fable 5.2 high}
    second_opinion:
      - {class: gemini-carbon, thinking: high, role: 反向跨家唯讀審查 Opus 的修法（Carbon high）}
  verify:
    name: 獨立驗收
    route:
      - {class: claude-opus, thinking: xhigh, role: 高風險主驗收（Opus effort xhigh，不預設 max）}
    second_opinion:
      - {class: gemini-carbon, thinking: high, role: 反向跨家唯讀第二意見（作者是 Claude 時用 Carbon high；預設要跑）}
  architecture:
    name: 重大架構盲審
    route:
      - {class: claude-fable, thinking: high, role: 兩階段防迎合盲審（Stage 1 零錨定獨立設計寫盤 → Stage 2 讀提案對決；強制隔離記憶注入；死結才 xhigh）}
    second_opinion:
      - {class: gemini-carbon, thinking: high, role: 反向跨家架構盲審（作者或主審是 Claude 時用 Carbon high；強制隔離記憶注入）}

# 重大架構兩階段防迎合盲審協定（2026-11-25 定案）。
blind_review:
  stages:
    - Stage 1（零錨定獨立設計）：只提供問題邊界、限制條件與一手環境／原始碼證據，絕不提供既有提案、選項排名或前人結論；審查者必須先將獨立設計寫入磁碟檔案。
    - Stage 2（正面對決）：確認 Stage 1 檔案寫入磁碟後，才讀取待審提案，逐項對決優劣、潛在靜默漏洞與具體改判條件。
  memory_isolation: >-
    盲審與工具評測子對話必須隔離跨對話記憶注入（在中性目錄執行、停用 claude-mem 等記憶 plugin 的 SessionStart／Read 注入，
    或將受審專案排除在觀察注入之外），避免記憶 hook 把前輪審查結論標題提前餵給審查者而破壞零錨定。

# 驗收不過時怎麼升級。每次升級都要記進紀錄的 escalations；同設定重跑記 retries。
escalation:
  - {from: gemini-fast, to: gemini-pro, thinking: xhigh, why: Hydrogen xhigh 驗收不過，先升 Neon xhigh 重跑}
  - {from: gemini-pro, to: claude-opus, thinking: high, why: Neon xhigh 驗收不過，改由 Opus high 定案重跑}
  - {from: claude-sonnet, to: claude-opus, thinking: same, why: Sonnet 試行的品質保護：驗收不過就用 Opus、同一級 effort 重跑}
  - {from: level, to: higher, after_failures: 2, why: 「驗收一直不過」定義為同一個任務驗收不過 2 次（升到 Opus xhigh）}
  - {from: {class: claude-opus, thinking: xhigh}, to: {class: claude-fable, thinking: high}, why: Opus xhigh 仍無法收斂時升到 Fable 5.2 high（max 不預設，僅限使用者明確指定）}

# 管道。
channels:
  native:
    use: 同供應商、沒有特殊設定、前景執行（Claude 用 Agent 工具，model 與 effort 都寫明）
  t3_cli:
    use: >-
      不在 T3 裡、這個 agent 還沒授權 T3 的 MCP 時，用 T3 Code 的本機 t3 thread CLI 開 T3 對話。
      已經接上 T3 MCP 的，優先用 t3_thread_launch 管道（能自己結案）。使用者要指定 T3 上的帳號實例或模型（例如 antigravity_ryan 加 gemini-4-hydrogen-xhigh）、
      想在 T3 側邊欄看到那條對話、要開在獨立 worktree，或要派給 T3 才有的帳號實例時用它。不要因為這裡沒有 delegate_task、
      t3_thread_launch 這類 MCP 工具就回答「沒辦法派給 T3」。
    how: >-
      PowerShell 打 t3；Git Bash 要打 t3.cmd。%USERPROFILE%\.t3\bin 只有 t3.cmd，Bash 只會自動補 .exe，所以 Bash 的
      command -v t3 找不到，不代表沒裝（2026-11-18 查證：Git Bash 的 PATH 有這個資料夾，t3.cmd --version 跑得動）。
      找不到時先跑 omnikit-capabilities 的清點。
      開對話：t3 thread start <project id 或專案內路徑，. 是目前 repo> "<任務說明>" --provider <實例> --model <模型代號>
      [--option <id=value>] --title "<標題>" --json [--wait]；說明很長時訊息填 -，從 stdin 讀。--provider 的值就是個人層 instances 的 key，
      要和 --model 一起給；不給 --model 用專案預設模型。要獨立 worktree 加 --worktree <分支或 commit> [--branch <新分支名>]。
      --wait 等到做完並印出回覆：結束碼 1 是執行失敗、2 是對話在等人回答。
      其他：t3 thread show <id> --json 看狀態與最新訊息；t3 thread send <id> "<訊息>" --wait 追問；t3 thread list --json 列出對話。
    thinking: >-
      t3 v0.1.12（2026-11-25 查 --help 確認）已支援 --option id=value（Claude 用 --option effort=high；Antigravity 用 --option thought_level=xhigh）。
      Antigravity 的模型也可把程度寫進模型代號（gemini-4-hydrogen-xhigh）；Gemini 一定要明確帶 high 以上（Carbon 最高 high；Neon、Hydrogen 最高 xhigh），
      不帶就不知道後端用哪一級。
    settle: >-
      t3 CLI 目前沒有 settle 子指令。主控有 T3 MCP 就用 t3_thread_organize 結案（見 t3_thread_launch）；沒有就在回報裡
      列出對話 id 與標題，請使用者在 T3 結案。
    vs: >-
      和其他管道的分工：同供應商、不需要指定帳號、不用在 T3 看到的，用原生子代理（最省事、結果直接回主線）；
      派給 Antigravity 的模型照使用者偏好 visibility 選（見 visibility）：visible 依序用 delegate_task（主控在 T3 裡）、
      t3_thread_launch（T3 外、接了 T3 MCP）、t3_cli（沒接或 MCP 斷線）；headless 用 agy_cli。
      要指定 T3 上的帳號實例（antigravity_ryan、claudeAgent_2…）一律走 T3 的三個管道（agy_cli 只有本機 agy 單一登入帳號）。
    note: >-
      2026-11-25 實測（t3 v0.1.12-nightly.20261125.5222）：t3 thread start . "Probe: reply with exact word OK only, do nothing else."
      --provider antigravity_ryan --model gemini-pro-orchestrator-neon --wait --json 回傳 {"status":"completed","reply":"OK"}。
  delegate_task:
    use: 在 T3 裡跨供應商（Gemini／Antigravity）、要獨立 worktree、要指定別的帳號實例（providerInstanceId）
    thinking: >-
      思考程度：在 target.options 傳 {thought_level: "xhigh"}（Claude 傳 {effort: "high"}），或直接寫帶程度的代號（gemini-4-hydrogen-xhigh）。
      T3 介面若對目錄外的代號（如 gemini-pro-orchestrator-neon、antigravity 的 claude-opus-5-5）標示未列出，後端仍正常轉送執行（2026-11-25 實測通過）。
    note: >-
      現行規則：delegate_task 不能指定別的專案。【待驗證】T3 的 delegate_task 參數裡有 target.projectId，
      實際能不能把子任務開在別的專案還沒實測，驗證前照現行規則。
  t3_thread_launch:
    use: >-
      T3 的 MCP 工具（t3_thread_launch、t3_thread_wait、t3_thread_read、t3_thread_organize）。T3 外的 Claude Code、Codex
      接上 T3 MCP 之後，要指定 T3 的帳號實例與模型、要設思考程度、要自己結案時優先用它，比 t3_cli 完整；
      跨專案的工作也用它，開在那個專案裡。外部 agent 呼叫 delegate_task 會回錯，要用 t3_thread_launch。
      斷線（2026-11-21 查證）：t3 MCP 跑在 T3 桌面程式裡，看到 t3 (ECONNREFUSED) 或工具清單沒有 mcp__t3__*，
      是這段對話開的時候 T3 在重啟、更新或沒開，不是沒裝。請使用者在本對話打 /mcp 選 t3 按 Reconnect；同時改走 t3_cli，
      不要回答派不了。SessionStart hook engine/scripts/t3_watch.py 連不上時會叫起 T3 並留提醒。
    how: >-
      接法（2026-11-18 在這台用 Claude Code 實測通過）：claude mcp add --scope user --transport http t3 http://127.0.0.1:3773/mcp，
      再 claude mcp login t3。login 要在互動式終端機跑（agent 的 Bash 工具會回 this isn't an interactive terminal，改用終端機分頁）。
      核准頁要 Sign-in code 時用 t3 auth pairing create --ttl 10m 產生，要用預設 scope（只給 orchestration 兩個 scope 的碼
      不能核准 Full access）。瀏覽器跳到 localhost callback 連不上時，把完整網址貼回終端機的 paste the redirect URL。
      核准一次有效 30 天；每個 CLAUDE_CONFIG_DIR（以及 Codex 的每個 CODEX_HOME）都要各做一次，要使用者核准。
      Codex 照上游 pingdotgg/t3code 的 docs/user/outside-agents.md 用 codex mcp add t3 --url http://127.0.0.1:3773/mcp
      再 codex mcp login t3【待驗證：Codex 登入後叫用工具還沒實測】。omnikit-capabilities 的清點會列出哪些 agent 已經登記、授權。
    thinking: >-
      t3_thread_launch 的 modelSelection.options 是陣列，例如 [{id: "thought_level", value: "xhigh"}]。id 依 provider 不同：
      claudeAgent 系列用 effort（low、medium、high、xhigh、max、ultrathink），antigravity 用 thought_level（low、medium、high、xhigh；
      Carbon 最高 high；Gemini 政策禁用 low、medium）；實際可用的值以 orchestrator_capabilities 查到的為準（2026-11-25 實查 7 個 Antigravity 實例皆列出 Neon、Hydrogen、Carbon）。
    settle: >-
      t3_thread_organize 帶 action settle 與 threadId，再用 t3_thread_read 回讀確認 settled 是 true（2026-11-18 實測）。

  agy_cli:
    use: >-
      用 agy 無頭模式派給 Antigravity 的模型：在背景跑、比較省事，但 T3 看不到這條對話，使用者看不到 prompt 和過程。
      visibility 是 headless 的使用者預設用它；visible 的使用者只在 T3 沒在跑、或使用者同意時用（見 visibility.modes.visible.fallback），
      用了要在回報裡寫明「這次走無頭模式，T3 看不到」與原因。
      用 omnikit-dispatch skill 的 run.py agy --class <類別> --thinking <程度> --brief-file <任務說明>；
      思考程度寫進模型代號（gemini-4-hydrogen-xhigh），只寫 gemini-4-hydrogen 會落到 medium，違反 Gemini 至少 high 的規則，一定要帶程度。
    note: >-
      2026-11-16 用 agy 1.5.9 實測：xhigh 確實生效（log 印 resolved to gemini-4-hydrogen-xhigh，思考 token 約 high 的 2 到 3 倍）；
      能改檔並自己跑測試；終端機 PATH 只有系統路徑，腳本會把 uv、gh 的絕對路徑附在任務說明後面；
      腳本用 --dangerously-skip-permissions，任務說明前面固定加硬性限制（不 commit、不 push、不刪檔、不對外發送、不安裝），
      以及 antigravity_turns.brief 的收尾規定（交付檔沒指定時寫進 --result-file，預設在暫存資料夾）；
      結果一律由主控讀檔、跑測試驗收。用的是本機 agy CLI 登入帳號。

# 使用者偏好：派給 Antigravity 的子任務要不要開在 T3 看得到的對話。
visibility:
  default: visible
  default_why: >-
    沒設定時用 visible：使用者看得到派出去的 prompt 與過程，比較容易發現說明寫錯；T3 沒在跑時會自動退到 headless，
    不會因此派不出去。想要省事、只看結果的，在 profile 寫 headless。
  modes:
    visible:
      desc: 開成 T3 看得到的對話，能看 prompt 與過程、中途追問或停止
      channels:
        - {channel: delegate_task, when: 主控在 T3 裡}
        - {channel: t3_thread_launch, when: 主控在 T3 外、接了 T3 MCP}
        - {channel: t3_cli, when: 主控在 T3 外、沒接 T3 MCP 或 MCP 斷線（ECONNREFUSED）；t3 thread start ... --provider <實例> --model <帶程度的代號> --title "<標題>"}
      fallback: >-
        T3 沒在跑（t3 thread list 連不上，叫起 T3 也起不來）時退到 agy_cli，回報裡寫明「這次走無頭模式，T3 看不到」與原因；
        這台沒有 agy 就停下來請使用者開 T3。要看 thinking_tokens 確認思考程度而改走 agy_cli 時，先問使用者。
    headless:
      desc: 走 agy 無頭模式，在背景跑、比較省事，只看結果；T3 看不到過程
      channels:
        - {channel: agy_cli, when: 這台有 agy（Antigravity CLI），而且用的是 agy 登入的那個帳號}
      fallback: >-
        要指定 agy 沒登入的帳號實例（例如 antigravity_ava、antigravity_stk608），或這台沒有 agy 時，改用 visible 的三個管道。

# 派給 Antigravity 的回合怎麼收尾。所有管道都適用：agy_cli、t3_cli、t3_thread_launch，主控在 T3 裡用 delegate_task 也一樣。
antigravity_turns:
  why: >-
    2026-11-18 實測：Antigravity 的 T3 對話跑完最後一個指令、回報檔寫好後，ACP 程序可能讓 session/prompt 一直不結束；
    上游 pingdotgg/t3code PR #30377 在 AntigravityAdapterV2.ts 寫死 promptInactivityTimeout 15 分鐘，不能設定，
    15 分鐘無輸出後 T3 會印「Antigravity sent nothing for 15 minutes」並標成 failed。同一次也曾因前景跑伺服器撞到 600 秒工具逾時。
  brief:
    - 交付物先寫成檔案，路徑由主控在任務說明裡指定
    - 最後一個動作是寫完成標記檔（交付檔路徑加 .done，例如 report.md.done），寫完才送出最後回覆
    - 最後回覆不超過 10 行，附上交付檔路徑
    - 伺服器、watcher 這類不會自己結束的程式一律背景啟動，不要在前景跑
  verify: >-
    有 T3 MCP 時：用 t3_thread_wait 搭配短逾時（約 60 秒）輪詢；看到完成標記，而且 1 到 2 分鐘沒有新活動，就呼叫
    t3_thread_interrupt 中斷回合，再用 t3_thread_organize 帶 action settle 結案（照 t3_thread_launch 的 settle 回讀確認），
    不用空等 15 分鐘。只有 t3_cli 時：t3 thread 沒有中斷子指令；Antigravity 的長任務不加 --wait，改用 t3 thread show 看狀態並檢查完成標記，
    標記在就當作完成去驗收，回報裡列出對話 id 與標題，請使用者在 T3 停止並結案。agy_cli：run.py agy 會在任務說明前面自動加這四件事，
    輸出的 done_marker 說明標記檔在不在。
  failed_15min: >-
    對話以「sent nothing for 15 minutes」失敗收場時，先檢查交付檔和完成標記，不要直接重派：東西都在就當作完成、照常驗收並結案；
    不在就用 send（t3_thread_launch 的對話用 MCP，t3_cli 用 t3 thread send）請它接著做。Antigravity 主線出現這個橫幅時，
    同樣先看工作是否已完成，未完成再送「繼續」。
  main_thread: >-
    T3 server 原始碼把 Antigravity 的 promptInactivityTimeout 寫死成 "15 minutes"（Claude 與 Codex 都沒有，也沒有設定可以改；下次 T3 升版時重查）。
    因此長時間跑的主線優先用 Claude 實例；改用 Antigravity 跑主線時採分階段回報節奏避免單回合靜默超過 15 分鐘，遇到橫幅時先檢查交付與狀態，未完成再送「繼續」。
  user_in_t3: 使用者自己在 T3 開的對話：看到回報檔已經出現、對話卻還顯示 working，直接按停止。
  pending:
    - 【待驗證】t3_thread_interrupt 能不能立刻收掉這種卡住的回合
    - 【待驗證】中斷會不會把最後那則回覆一起吃掉
    - 【待驗證】agy CLI 的無頭模式（agy_cli）會不會有同樣的問題

# 本週 Claude 用量（給 high 級的 80% 條件用）。
usage_signal:
  claude_weekly_threshold_pct: 80
  source: >-
    Claude Code 狀態列的 JSON 輸入有 rate_limits.seven_day.used_percentage（官方文件 code.claude.com/docs/en/statusline，
    只有 Pro、Max、Ultra 訂閱，而且要該對話第一個回應之後才有），加上 T3 供應商快取 ~/.t3/caches/<實例>.json 的 usageLimits。
  pending: >-
    2026-11-23 實測：claude_allow.py 已把 dispatch.py statusline --dir 接進 ~/.claude、~/.claude-kai、~/.claude-retis 三個目錄；
    T3 裡跑 Claude 則由 account_pool.py 讀取 ~/.t3/caches/<實例>.json 的 usageLimits（不讀 auth 欄位）。查不到（unknown）時不要假設已達 80%。

# Sonnet 試行的品質保護（凍結至 2026-11-29 到期檢討）。
trials:
  sonnet-trial:
    class: claude-sonnet
    baseline: claude-opus
    compare: 同一級任務的一次通過率（first_pass），以一開始派的模型分組
    min_samples: 20
    min_baseline: 10
    max_gap_pp: 10
    action: Sonnet 比 Opus 低 10 個百分點以上，就把 levels.medium 的 claude-sonnet 換回 claude-opus（同一級 effort）
    how: omnikit-dispatch skill 的 dispatch.py stats（repo 裡是 uv run engine/scripts/dispatch.py stats）
    note: >-
      凍結期間（到 2026-11-29）control_every 維持 0，到期時併新分工表一起決定 Sonnet 是否保留在中級退路。
    control_every: 0

# 委派紀錄：每次委派結束時一行 JSONL，存在本機，不進 repo。
log:
  path: '~/.omnikit/dispatch/log.jsonl'
  fields: [ts, project, task, level, channel, instance, model, thinking, first_pass, retries, escalations, final_model, verdict, error_kind, rules_version, profile, control, note]
```
