# OmniKit 分派政策（完整版，要派的時候才讀）

這份不會載入每段對話。常駐的規則是 `data/rules/dispatch.md`（幾行原則）；這裡是任務類型、級別、模型類別、思考程度、管道、升級的完整政策。讀法：用 omnikit-dispatch skill 的 `run.py show`，它會印出套上你的實例之後每一級可用的選項；要看管道與實測備註再讀這份原文。

你有哪些帳號、供應商實例，寫在自己 profile 的 `dispatch.md`（個人層）；沒有那份就只用目前這個 agent 的原生子代理。下面的 YAML 是給 agent 與 `engine/scripts/dispatch.py` 共用的唯一來源，改了要更新 `data/rules/baseline.md` 的規則版本。

怎麼用：
1. 照 `tasks` 判斷任務類型，得到級別；在 `levels.<級別>.route` 由上往下挑第一個「你有實例、額度沒用完、`when` 成立（沒寫就算成立）、`tasks` 有列就要包含這個任務」的選項。
2. 思考程度照選項寫明，不要沿用主線的設定，也不要靠預設值。
3. 照 `channels` 選管道；開子對話或派子代理時，在任務說明寫明級別與思考程度。派給 Antigravity 的模型時，任務說明還要照 `antigravity_turns.brief` 寫明交付檔與完成標記，驗收照 `antigravity_turns.verify`。
4. 子任務結果收回、驗收完、要 settle 之前，記一行委派紀錄（`run.py log`）；一次委派一行，重跑與升級記在同一行。
5. 驗收不過照 `escalation` 升級，升級也要記。
6. 專案規則對模型分工或驗收另有規定時，照專案規則。

```yaml
policy_version: 1

# 模型類別：個人層把它對到自己的供應商實例。thinking 的名稱：Claude 叫 effort，Gemini／Antigravity 叫 thinking_level。
# 模型代號、預設值與上限取自 T3 orchestrator_capabilities（2026-11-14 實際查到的目錄）。
model_classes:
  claude-opus:      {model: claude-opus-5-5,   driver: claudeAgent, default_thinking: medium, max_thinking: max}
  claude-sonnet:    {model: claude-sonnet-5-5, driver: claudeAgent, default_thinking: high,   max_thinking: max}
  gemini-pro:       {model: gemini-4-hydrogen, driver: antigravity, default_thinking: high,   max_thinking: xhigh, forbid_thinking: [low, medium]}
  gemini-flash:     {model: gemini-3.8-flash,  driver: antigravity, default_thinking: high,   max_thinking: high,  forbid_thinking: [low, medium]}
  antigravity-opus: {model: claude-opus-5-5,   driver: antigravity, default_thinking: high,   max_thinking: high}
# 2026-11-18 ryan 定案：所有 Gemini 模型的調用，思考程度永遠是 high 或更高（gemini-pro、gemini-flash 都禁用 low、medium；
#   dispatch.py check 與 run.py agy 會擋）。
# 背景數據（第三方來源都待驗證）：
# - Gemini 4 Hydrogen 對 3.8 Flash：Artificial Analysis 指數 high 51 對 31；xhigh 54 但 token 約 2 倍；medium 41、low 27
#   （low 比 Flash 還低，所以禁用 low）。難的寫程式工作階段 71.6% 對 42.2%（bito.ai，在 Claude Code harness 跑；
#   Gemini CLI 底下分數較低，結果跟 harness 有關）。【待驗證】
# - Sonnet 5.5 對 Opus 5.5：SWE-Bench Pro 81.3 對 89.9；Terminal-Bench 依 harness 互有勝負；
#   價格每百萬 token $2/$10 對 $4/$20。【待驗證】
# - Anthropic 多代理研究（anthropic.com/engineering/multi-agent-research-system）：Opus 主控、Sonnet 子代理，
#   比單一 Opus 好 90.2%；把投入分級規則寫進 prompt，可以避免簡單任務投入過多。【待驗證】
# - Anthropic Applied AI〈When to fold subagents into your main agent loop〉（Diane Sarkis，2026-10-22，原文讀過）：
#   幾家企業的部署裡，單一 agent 加 skill 常比整組子代理好，成本與等待也較低；只在 context 塞到測得出變差、
#   要平行而且各要乾淨的 context、或選不到工具、指示互相打架時才拆。收回時先建小評測、一次收一個、有它沒它各比一次。
#   跟 data/rules/dispatch.md「派出去不會讓答案更好」同方向。

# 任務類型 → 級別。紀錄的 task 欄位用這裡的 key。
tasks:
  docs:            {level: medium, desc: 規格明確的文件、報表}
  ui-small:        {level: medium, desc: 介面小改}
  readonly:        {level: medium, desc: 唯讀檢查、盤點、查資料}
  code-small:      {level: medium, desc: 規格明確的小修改}
  accounting:      {level: high,   desc: 碰到帳務}
  risk:            {level: high,   desc: 碰到風控}
  orders:          {level: high,   desc: 碰到下單}
  design-decision: {level: high,   desc: 要做設計決策}
  hard-bug:        {level: higher, desc: 難查的錯誤}
  acceptance-loop: {level: higher, desc: 驗收一直不過}
  verify:          {level: verify, desc: 獨立驗收}

# 分工原則（2026-11-16，ryan：Claude 只拿來做真正重要的事）：跨模型、跨應用的主控與工作者。
# - 主控（規劃、拆解、定案、最後驗收）是主線的 Claude；量大、不關鍵的工作派 Hydrogen，開成 T3 看得到的對話（順序見 antigravity_turns.default_channels；agy_cli 無頭模式只當例外）。
# - 寫的模型與審的模型不同家：Hydrogen 寫的由主控驗收；Opus 做的重要任務由 Hydrogen xhigh 唯讀審查（second_opinion）。
# - 重要任務先派 Hydrogen 做前置苦工（prework），Opus 只花在判斷與定案。
# 業界對照與實測在 docs/proposals/2026-11-16-cross-model-dispatch.md。
# 級別 → 依序嘗試的選項。沒有對應實例的類別直接跳過；when 是成立才用的條件，沒寫就是預設。
# prework 在 route 之前跑、second_opinion 在 route 之後跑；兩者都沒有實例就跳過，不擋 route。
# Claude 類別在 Claude 底下一定有（原生子代理），其他類別要個人層有實例。
levels:
  medium:
    name: 中
    route:
      - class: claude-sonnet
        thinking: medium
        when: 專案規則要求 Claude，或任務要用的工具 agy 沒有（寫明是哪個工具）；「主控是 Claude」不算理由
        trial: sonnet-trial
      - {class: gemini-pro, thinking: high, note: 中級的預設；禁用 low；Gemini 的 token 不用省。管道照 antigravity_turns.default_channels（開成 T3 看得到的對話），agy_cli 只當例外}
      - class: gemini-flash
        thinking: high
        when: gemini-pro 的額度用完
        tasks: [docs, readonly]
        note: >-
          2026-11-16 定案：Flash 只接 docs 與 readonly；改程式碼的任務（ui-small、code-small）落到下一個選項
          claude-sonnet（effort medium），因為 Flash 寫程式能力差很多（BenchLM 寫程式綜合 53.7 對 Sonnet 5.5 的 81.1，第三方【待驗證】）。
      - class: claude-sonnet
        thinking: medium
        note: 退路：上面都沒有可用的實例（例如沒有 Gemini／Antigravity），或 gemini-pro 額度用完時的 ui-small、code-small
        trial: sonnet-trial
  high:
    name: 高
    prework:
      - {class: gemini-pro, thinking: high, role: 前置苦工：讀程式、收資料、重現、列候選與證據，不下結論、不改檔；Opus 拿它的整理定案}
    route:
      - class: antigravity-opus
        thinking: high
        when: 本週 Claude 用量 >= 80%（見 usage_signal），而且任務是 accounting、risk 或 orders
        tasks: [accounting, risk, orders]
        note: 額度消耗快，只用在這三類，簡單工作不要用
      - {class: claude-opus, thinking: high}
    second_opinion:
      - {class: gemini-pro, thinking: xhigh, role: 唯讀審查 Opus 的結果（不同模型家族，避免同樣的盲點）；有異議由 Opus 判斷}
  higher:
    name: 更高
    prework:
      - {class: gemini-pro, thinking: xhigh, role: 前置苦工：讀程式、重現錯誤、縮小範圍、列假設與證據，不改檔；Opus 拿它的整理定案}
    route:
      - {class: claude-opus, thinking: xhigh, note: max 只在 xhigh 也失敗時才用（見 escalation）}
    second_opinion:
      - {class: gemini-pro, thinking: xhigh, role: 唯讀審查 Opus 的修法；有異議由 Opus 判斷}
  verify:
    name: 獨立驗收
    route:
      - {class: claude-opus, thinking: high, role: 主驗收}
    second_opinion:
      - {class: gemini-pro, thinking: xhigh, role: 唯讀第二意見（預設要跑，Gemini 的 token 不用省）}

# 驗收不過時怎麼升級。每次升級都要記進紀錄的 escalations；同設定重跑記 retries。
escalation:
  - {from: gemini-pro, to: claude-sonnet, thinking: medium, why: Hydrogen 驗收不過，先用 Sonnet medium 重跑；再不過照下一條升 Opus}
  - {from: claude-sonnet, to: claude-opus, thinking: same, why: Sonnet 試行的品質保護：驗收不過就用 Opus、同一級 effort 重跑}
  - {from: level, to: higher, after_failures: 2, why: 「驗收一直不過」定義為同一個任務驗收不過 2 次（2026-11-16 定案）}
  - {from: {class: claude-opus, thinking: xhigh}, to: {class: claude-opus, thinking: max}, why: max 只在 xhigh 也失敗時才用}

# 管道。
channels:
  native:
    use: 同供應商、沒有特殊設定、前景執行（Claude 用 Agent 工具，model 與 effort 都寫明）
  t3_cli:
    use: >-
      不在 T3 裡、這個 agent 還沒授權 T3 的 MCP 時，用 T3 Code 的本機 t3 thread CLI 開 T3 對話。
      已經接上 T3 MCP 的，優先用 t3_thread_launch 管道（能設思考程度、能自己結案）。使用者要指定 T3 上的帳號實例或模型（例如 antigravity_kai 加 gemini-3.8-flash）、想在 T3 側邊欄看到那條對話、
      要開在獨立 worktree，或要派給 T3 才有的帳號實例時用它。不要因為這裡沒有 delegate_task、t3_thread_launch 這類
      MCP 工具就回答「沒辦法派給 T3」。
    how: >-
      PowerShell 打 t3；Git Bash 要打 t3.cmd。%USERPROFILE%\.t3\bin 只有 t3.cmd，Bash 只會自動補 .exe，所以 Bash 的
      command -v t3 找不到，不代表沒裝（2026-11-18 查證：Git Bash 的 PATH 有這個資料夾，t3.cmd --version 跑得動）。
      找不到時先跑 omnikit-capabilities 的清點。
      開對話：t3 thread start <project id 或專案內路徑，. 是目前 repo> "<任務說明>" --provider <實例> --model <模型代號>
      --title "<標題>" --json [--wait]；說明很長時訊息填 -，從 stdin 讀。--provider 的值就是個人層 instances 的 key，
      要和 --model 一起給；不給 --model 用專案預設模型。要獨立 worktree 加 --worktree <分支或 commit> [--branch <新分支名>]。
      --wait 等到做完並印出回覆：結束碼 1 是執行失敗、2 是對話在等人回答。
      其他：t3 thread show <id> --json 看狀態與最新訊息；t3 thread send <id> "<訊息>" --wait 追問；t3 thread list --json 列出對話。
    thinking: >-
      t3 v0.1.10 沒有設定思考程度的參數（上游 main 的文件有 --option effort=...，要等 T3 更新）。要設思考程度就改走
      t3_thread_launch 管道（T3 MCP）。只能用 CLI 時，Antigravity 的模型照 delegate_task 的做法把程度寫進模型代號
      （gemini-4-hydrogen-xhigh）；Gemini 一定要帶 -high 以上，不帶就不知道後端用哪一級。【待驗證】代號帶程度經 t3 thread start 生效，
      是 2026-11-16 的實測，只測過 Hydrogen；Flash 的 gemini-3.8-flash-high 還沒實測，要確定程度就改走 t3_thread_launch（agy_cli 看得到 thinking_tokens，但屬例外，見 agy_cli）。
    settle: >-
      v0.1.10 沒有 settle 子指令。主控有 T3 MCP 就用 t3_thread_organize 結案（見 t3_thread_launch）；沒有就在回報裡
      列出對話 id 與標題，請使用者在 T3 結案。
    vs: >-
      和其他管道的分工：同供應商、不需要指定帳號、不用在 T3 看到的，用原生子代理（最省事、結果直接回主線）；
      派給 Antigravity 的模型一律開成 T3 看得到的對話（2026-11-21 定案，順序見 antigravity_turns.default_channels）：
      主控在 T3 裡用 delegate_task；T3 外接了 T3 MCP 用 t3_thread_launch；沒接（或 MCP 斷線）用 t3_cli。
      要指定 T3 上的帳號實例（antigravity_kai、claudeAgent_2…）也走這三個。agy_cli 只在它 use 寫的三種例外情況用。
    note: >-
      2026-11-18 實測（t3 v0.1.10）：t3 thread start . "只回 OK" --provider antigravity_kai --model gemini-3.8-flash --wait --json
      回傳 {"status":"completed","reply":"OK"}，不用登入。
  delegate_task:
    use: 在 T3 裡跨供應商（Gemini／Antigravity）、要獨立 worktree、要指定別的帳號實例（providerInstanceId）
    thinking: >-
      思考程度：model 直接寫帶程度的代號（gemini-4-hydrogen-xhigh）。2026-11-16 用 t3 thread start --provider antigravity 實測：
      T3 介面在模型旁標 Unavailable（T3 的模型目錄只有 gemini-4-hydrogen），但 T3 經 antigravity-acp 送到後端的就是這個代號，
      後端紀錄寫「running ... as gemini-4-hydrogen-xhigh」，回覆正確；只寫 gemini-4-hydrogen 時後端用 high。
      所以 Unavailable 可以不理：這是介面的標示，不是代號錯誤，不要因此改代號或當成幻覺（2026-11-17 ryan 確認繼續用 xhigh）。【待驗證】思考 token 在 T3 的紀錄裡看不到，xhigh 有沒有多想只有耗時佐證（77 秒對 high 54 秒，各 1 次）；
      一定要確認思考程度時才用 agy_cli（輸出有 thinking_tokens；屬例外，回報要寫明這次走無頭模式）。
    note: >-
      現行規則：delegate_task 不能指定別的專案。【待驗證】T3 的 delegate_task 參數裡有 target.projectId，
      實際能不能把子任務開在別的專案還沒實測，驗證前照現行規則。
  t3_thread_launch:
    use: >-
      T3 的 MCP 工具（t3_thread_launch、t3_thread_wait、t3_thread_read、t3_thread_organize）。T3 外的 Claude Code、Codex
      接上 T3 MCP 之後，要指定 T3 的帳號實例與模型、要設思考程度、要自己結案時優先用它，比 t3_cli 完整；
      跨專案的工作也用它，開在那個專案裡。外部 agent 呼叫 delegate_task 會回錯，要用 t3_thread_launch。
      斷線（2026-11-21 查證，Claude Code 2.1.329、T3 0.1.12-nightly.20261120.4994）：t3 MCP 跑在 T3 桌面程式裡，
      看到 t3 (ECONNREFUSED) 或工具清單沒有 mcp__t3__*，是這段對話開的時候 T3 在重啟、更新或沒開，不是沒裝。
      user scope 的 MCP server agent 不能自己重撥，請使用者在本對話打 /mcp 選 t3 按 Reconnect；同時改走 t3_cli
      （CLI 每次重新連線），不要回答派不了。SessionStart hook engine/scripts/t3_watch.py 連不上時會叫起 T3 並留提醒。
    how: >-
      接法（2026-11-18 在這台用 Claude Code 實測通過）：claude mcp add --scope user --transport http t3 http://127.0.0.1:3773/mcp，
      再 claude mcp login t3。login 要在互動式終端機跑（agent 的 Bash 工具會回 this isn't an interactive terminal，改用終端機分頁）。
      核准頁要 Sign-in code 時用 t3 auth pairing create --ttl 10m 產生，要用預設 scope（只給 orchestration 兩個 scope 的碼
      不能核准 Full access）。瀏覽器跳到 localhost callback 連不上時，把完整網址貼回終端機的 paste the redirect URL。
      核准一次有效 30 天；每個 CLAUDE_CONFIG_DIR（以及 Codex 的每個 CODEX_HOME）都要各做一次，要使用者核准。
      Codex 照上游 pingdotgg/t3code 的 docs/user/outside-agents.md 用 codex mcp add t3 --url http://127.0.0.1:3773/mcp
      再 codex mcp login t3【待驗證：Codex 還沒實測】。omnikit-capabilities 的清點會列出哪些 agent 已經登記、授權。
    thinking: >-
      t3_thread_launch 的 modelSelection.options 是陣列，例如 [{id: "thinking_level", value: "high"}]。id 依 provider 不同：
      claudeAgent 系列用 effort（low、medium、high、xhigh、max、ultrathink），antigravity 用 thinking_level（low、medium、high；Gemini 只能用 high，見 model_classes）；
      實際可用的值以 orchestrator_capabilities 查到的為準（2026-11-18 實測）。
      【待驗證】antigravity_ava、antigravity_kai 在 capabilities 裡的模型清單是空的；帶 thinking_level high 開 gemini-3.8-flash
      會被接受也能跑完，但 t3_thread_read 沒有回傳 options，在 Gemini 端有沒有生效還不知道。
    settle: >-
      t3_thread_organize 帶 action settle 與 threadId，再用 t3_thread_read 回讀確認 settled 是 true（2026-11-18 實測）。

  agy_cli:
    use: >-
      例外管道（2026-11-21 起不是預設）：用 agy 無頭模式派給 Antigravity 的模型，T3 看不到這條對話，使用者看不到 prompt 和過程。
      只在這三種情況用：使用者明確要求或同意走無頭模式、要看 thinking_tokens 確認思考程度有沒有生效、T3 沒在跑（t3 thread list 連不上）。
      用了要在回報裡寫明「這次走無頭模式，T3 看不到」與原因。
      用 omnikit-dispatch skill 的 run.py agy --class <類別> --thinking <程度> --brief-file <任務說明>；
      思考程度寫進模型代號（gemini-4-hydrogen-xhigh），只寫 gemini-4-hydrogen 會落到 medium，違反 Gemini 至少 high 的規則，一定要帶程度。
    note: >-
      2026-11-16 用 agy 1.5.9 實測：xhigh 確實生效（log 印 resolved to gemini-4-hydrogen-xhigh，思考 token 約 high 的 2 到 3 倍）；
      能改檔並自己跑測試；終端機 PATH 只有系統路徑，腳本會把 uv、gh 的絕對路徑附在任務說明後面；
      權限：無頭模式不能核准，agy 的安全監控送審就自動拒絕（時好時壞）；accept-edits 一律擋終端機指令；允許規則會落進沙盒。
      所以腳本用 --dangerously-skip-permissions，任務說明前面固定加硬性限制（不 commit、不 push、不刪檔、不對外發送、不安裝），
      以及 antigravity_turns.brief 的收尾規定（交付檔沒指定時寫進 --result-file，預設在暫存資料夾）；
      結果一律由主控讀檔、跑測試驗收。用的是 antigravity_ryan 實例（ryan 帳號）。

# 派給 Antigravity 的回合怎麼收尾。所有管道都適用：agy_cli、t3_cli、t3_thread_launch，主控在 T3 裡用 delegate_task 也一樣。
antigravity_turns:
  default_channels:
    - {channel: delegate_task, when: 主控在 T3 裡}
    - {channel: t3_thread_launch, when: 主控在 T3 外、接了 T3 MCP}
    - {channel: t3_cli, when: 主控在 T3 外、沒接 T3 MCP 或 MCP 斷線（ECONNREFUSED）；t3 thread start ... --provider <實例> --model <帶程度的代號> --title "<標題>"}
  default_channels_why: >-
    2026-11-21 ryan 回報：T3 主線與 Claude 桌面版派出去的 Gemini 任務都走 agy_cli 無頭模式，T3 看不到對話，
    沒辦法確認 prompt 符不符合預期、看過程。所以派給 Antigravity 的模型預設開成 T3 看得到的對話；agy_cli 降為例外（見 channels.agy_cli）。
  why: >-
    2026-11-18 實測：antigravity_kai（gemini-3.8-flash）的 T3 對話在 08:31:29 UTC 跑完最後一個指令，回報檔早就寫好，
    之後 15 分 14 秒沒有任何活動；08:46:43 T3 印「Antigravity sent nothing for 15 minutes, so T3 Code stopped the turn
    and restarted the agent」，對話被標成 failed，最後那則回覆在錯誤前 17 毫秒才收進來（t3_thread_read 的活動紀錄）。
    上游 pingdotgg/t3code 的 PR #30377（2026-11-05，issue #30271）：Antigravity 的 ACP 程序在最後一次輸出後，可能讓
    session/prompt 一直不結束；AntigravityAdapterV2.ts 寫死 promptInactivityTimeout 15 分鐘，不能設定，本機 T3 v0.1.10 已含這個修正。
    AntigravityTurnOutcome.ts 的 watchAntigravityPromptOutcome 只抓錯誤（例如額度用完），不偵測回合完成。
    同一次的第一輪另外因為在前景跑伺服器（python -u run.py）撞到 600 秒工具逾時而中斷。
  brief:
    - 交付物先寫成檔案，路徑由主控在任務說明裡指定
    - 最後一個動作是寫完成標記檔（交付檔路徑加 .done，例如 report.md.done），寫完才送出最後回覆
    - 最後回覆不超過 10 行，附上交付檔路徑
    - 伺服器、watcher 這類不會自己結束的程式一律背景啟動，不要在前景跑
  verify: >-
    有 T3 MCP 時：用 t3_thread_wait 搭配短逾時（約 60 秒）輪詢；看到完成標記，而且 1 到 2 分鐘沒有新活動，就呼叫
    t3_thread_interrupt 中斷回合，再用 t3_thread_organize 帶 action settle 結案（照 t3_thread_launch 的 settle 回讀確認），
    不用空等 15 分鐘。只有 t3_cli 時：t3 v0.1.10 的 thread 只有 list、start、send、show，沒有中斷子指令（2026-11-18 查 --help）；
    Antigravity 的長任務不加 --wait（回合卡住時會跟著等到 15 分鐘逾時，推論，未實測），改用 t3 thread show 看狀態並檢查完成標記，
    標記在就當作完成去驗收，回報裡列出對話 id 與標題，請使用者在 T3 停止並結案。agy_cli：run.py agy 會在任務說明前面自動加這四件事，
    輸出的 done_marker 說明標記檔在不在。
  failed_15min: >-
    對話以「sent nothing for 15 minutes」失敗收場時，先檢查交付檔和完成標記，不要直接重派：東西都在就當作完成、照常驗收並結案；
    不在就用 send（t3_thread_launch 的對話用 MCP，t3_cli 用 t3 thread send）請它接著做。Antigravity 主線出現這個橫幅時，
    同樣先看工作是否已完成，未完成再送「繼續」。
  main_thread: >-
    T3 server 原始碼把 Antigravity 的 promptInactivityTimeout 寫死成 "15 minutes"（Claude 與 Codex 都沒有，也沒有設定可以改）。
    因此長時間跑的主線優先用 Claude 實例；不得不改用 Antigravity 跑主線、又遇到這個橫幅時，先檢查交付與狀態，未完成再送「繼續」（2026-11-19 定案）。
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
    只有 Pro、Max、Ultra 訂閱，而且要該對話第一個回應之後才有）。OmniKit 用 dispatch.py statusline 把它存成本機快照，
    dispatch.py usage 讀快照。
  pending: >-
    【待驗證】T3 透過 Agent SDK 跑 Claude 時，狀態列指令會不會執行還沒實測；快照可能只在 Claude Code CLI 更新，
    而且是「當時那個帳號」的用量。查不到（unknown）時不要假設已達 80%；照預設選項走，使用者說已達 80% 才切換。

# Sonnet 試行的品質保護（ryan 的要求：可以改用 Sonnet，但品質不能受影響）。
trials:
  sonnet-trial:
    class: claude-sonnet
    baseline: claude-opus
    compare: 同一級任務的一次通過率（first_pass），以一開始派的模型分組
    min_samples: 20
    min_baseline: 10   # Opus 同級至少 10 筆才拿來比（2026-11-16 定案）
    max_gap_pp: 10
    action: Sonnet 比 Opus 低 10 個百分點以上，就把 levels.medium 的 claude-sonnet 換回 claude-opus（同一級 effort）
    how: omnikit-dispatch skill 的 dispatch.py stats（repo 裡是 uv run engine/scripts/dispatch.py stats）
    note: >-
      中級任務不派 Opus，所以紀錄裡不會自然出現「Opus 在中級的一次通過率」可以比。2026-11-16 定案：凍結期間
      （到 2026-11-29）不派對照組，control_every 維持 0，stats 會照實回報基準不足；凍結結束再決定要不要每 4 次派 1 次 Opus。
    control_every: 0

# 委派紀錄：每次委派結束時一行 JSONL，存在本機，不進 repo。
log:
  path: '~/.omnikit/dispatch/log.jsonl'
  fields: [ts, project, task, level, channel, instance, model, thinking, first_pass, retries, escalations, final_model, verdict, rules_version, profile, control, note]
```
