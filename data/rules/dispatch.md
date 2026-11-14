# OmniKit 規則：子任務分派（共用層）

所有人都套用這一份。你有哪些帳號、供應商實例，寫在自己 profile 的 `dispatch.md`（個人層）；沒有那份就只用目前這個 agent 的原生子代理。下面的 YAML 是給 agent 與 `engine/scripts/dispatch.py` 共用的唯一來源，改了要更新 `data/rules/baseline.md` 的規則版本。

怎麼用：
1. 照 `tasks` 判斷任務類型，得到級別；在 `levels.<級別>.route` 由上往下挑第一個「你有實例、額度沒用完、`when` 成立（沒寫就算成立）、`tasks` 有列就要包含這個任務」的選項。omnikit-dispatch skill 的 `dispatch.py show` 會印出套上你的實例之後的結果。
2. 思考程度照選項寫明，不要沿用主線的設定，也不要靠預設值（Opus 預設 medium、Sonnet 預設 high）。
3. 照 `channels` 選管道；開子對話或派子代理時，在任務說明寫明級別與思考程度。
4. 子任務結果收回、驗收完、要 settle 之前，用 omnikit-dispatch skill 記一行委派紀錄（`dispatch.py log`）；一次委派一行，重跑與升級記在同一行。
5. 驗收不過照 `escalation` 升級，升級也要記。
6. 專案規則對模型分工或驗收另有規定時，照專案規則。

```yaml
policy_version: 1

# 模型類別：個人層把它對到自己的供應商實例。thinking 的名稱：Claude 叫 effort，Gemini／Antigravity 叫 thinking_level。
# 模型代號、預設值與上限取自 T3 orchestrator_capabilities（2026-11-14 實際查到的目錄）。
model_classes:
  claude-opus:      {model: claude-opus-5-5,   driver: claudeAgent, default_thinking: medium, max_thinking: max}
  claude-sonnet:    {model: claude-sonnet-5-5, driver: claudeAgent, default_thinking: high,   max_thinking: max}
  gemini-pro:       {model: gemini-4-hydrogen, driver: antigravity, default_thinking: high,   max_thinking: xhigh, forbid_thinking: [low]}
  gemini-flash:     {model: gemini-3.8-flash,  driver: antigravity, default_thinking: high,   max_thinking: high}
  antigravity-opus: {model: claude-opus-5-5,   driver: antigravity, default_thinking: high,   max_thinking: high}
# 背景數據（第三方來源都待驗證）：
# - Gemini 4 Hydrogen 對 3.8 Flash：Artificial Analysis 指數 high 51 對 31；xhigh 54 但 token 約 2 倍；medium 41、low 27
#   （low 比 Flash 還低，所以禁用 low）。難的寫程式工作階段 71.6% 對 42.2%（bito.ai，在 Claude Code harness 跑；
#   Gemini CLI 底下分數較低，結果跟 harness 有關）。【待驗證】
# - Sonnet 5.5 對 Opus 5.5：SWE-Bench Pro 81.3 對 89.9；Terminal-Bench 依 harness 互有勝負；
#   價格每百萬 token $2/$10 對 $4/$20。【待驗證】
# - Anthropic 多代理研究（anthropic.com/engineering/multi-agent-research-system）：Opus 主控、Sonnet 子代理，
#   比單一 Opus 好 90.2%；把投入分級規則寫進 prompt，可以避免簡單任務投入過多。【待驗證】

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

# 級別 → 依序嘗試的選項。沒有對應實例的類別直接跳過；when 是成立才用的條件，沒寫就是預設。
# Claude 類別在 Claude 底下一定有（原生子代理），其他類別要個人層有實例。
levels:
  medium:
    name: 中
    route:
      - class: claude-sonnet
        thinking: medium
        when: 需要 Claude 子代理（專案規則要求 Claude，或要用只有 Claude 有的工具）
        trial: sonnet-trial
      - {class: gemini-pro, thinking: high, note: 禁用 low；Gemini 的 token 不用省}
      - class: gemini-flash
        thinking: high
        when: gemini-pro 的額度用完
        pending: >-
          【待確認】現行規則是 Flash 接所有中級任務。建議 Flash 只接 docs 與 readonly，
          改程式碼的任務（ui-small、code-small）改派 claude-sonnet（effort medium），因為 Flash 寫程式能力差很多。
      - class: claude-sonnet
        thinking: medium
        note: 上面都沒有可用的實例（例如沒有 Gemini／Antigravity）時的退路
        trial: sonnet-trial
  high:
    name: 高
    route:
      - class: antigravity-opus
        thinking: high
        when: 本週 Claude 用量 >= 80%（見 usage_signal），而且任務是 accounting、risk 或 orders
        tasks: [accounting, risk, orders]
        note: 額度消耗快，只用在這三類，簡單工作不要用
      - {class: claude-opus, thinking: high}
  higher:
    name: 更高
    route:
      - {class: claude-opus, thinking: xhigh, note: max 只在 xhigh 也失敗時才用（見 escalation）}
  verify:
    name: 獨立驗收
    route:
      - {class: claude-opus, thinking: high, role: 主驗收}
    second_opinion:
      - {class: gemini-pro, thinking: xhigh, role: 唯讀第二意見, optional: true}

# 驗收不過時怎麼升級。每次升級都要記進紀錄的 escalations；同設定重跑記 retries。
escalation:
  - {from: claude-sonnet, to: claude-opus, thinking: same, why: Sonnet 試行的品質保護：驗收不過就用 Opus、同一級 effort 重跑}
  - {from: level, to: higher, after_failures: 2, pending: 【待確認】「驗收一直不過」暫定為同一個任務驗收不過 2 次}
  - {from: {class: claude-opus, thinking: xhigh}, to: {class: claude-opus, thinking: max}, why: max 只在 xhigh 也失敗時才用}

# 管道。
channels:
  native:
    use: 同供應商、沒有特殊設定、前景執行（Claude 用 Agent 工具，model 與 effort 都寫明）
  delegate_task:
    use: 跨供應商（Gemini／Antigravity）、要背景執行、要獨立 worktree、要指定別的帳號實例（providerInstanceId）
    note: >-
      現行規則：delegate_task 不能指定別的專案。【待驗證】T3 的 delegate_task 參數裡有 target.projectId，
      實際能不能把子任務開在別的專案還沒實測，驗證前照現行規則。
  t3_thread_launch:
    use: 跨專案的工作，開在那個專案裡

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
    min_baseline: 10   # 【待確認】Opus 同級至少幾筆才拿來比；暫定 10
    max_gap_pp: 10
    action: Sonnet 比 Opus 低 10 個百分點以上，就把 levels.medium 的 claude-sonnet 換回 claude-opus（同一級 effort）
    how: omnikit-dispatch skill 的 dispatch.py stats（repo 裡是 uv run engine/scripts/dispatch.py stats）
    pending: >-
      【待確認】中級任務現在不派 Opus，所以紀錄裡不會自然出現「Opus 在中級的一次通過率」可以比。
      建議加對照組：中級要用 Claude 時每 4 次改派 1 次 Opus（effort medium），記 control: true；
      沒決定前 control_every 是 0（不派對照組），stats 會照實回報基準不足。
    control_every: 0

# 委派紀錄：每次委派結束時一行 JSONL，存在本機，不進 repo。
log:
  path: '%LOCALAPPDATA%\omnikit\dispatch\log.jsonl'
  fields: [ts, project, task, level, channel, instance, model, thinking, first_pass, retries, escalations, final_model, verdict, rules_version, profile, control, note]
```
