# 個人分派設定：ryan

分派規則（任務類型、級別、模型類別、思考程度、升級）照共用層 `data/rules/dispatch.md` 與 `data/rules/dispatch-policy.md`；這份只寫 ryan 有哪些供應商實例，以及每個模型類別用哪個實例（這份屬查表設定，不常駐載入對話規則，由 `omnikit-dispatch` 的 `run.py show` 讀取）。`instances` 的 key 是 T3 的供應商實例 id：在 T3 裡是 `delegate_task` 的 `target.providerInstanceId`，不在 T3 裡（Claude Code、Codex、Antigravity）就是 `t3 thread start --provider` 的值（例如 `t3 thread start . "<任務>" --provider antigravity_ryan --model gemini-4-hydrogen-xhigh --option thought_level=xhigh --json --wait`，在 PowerShell 跑；Git Bash 要打 `t3.cmd`；見政策的 `t3_cli` 與 `t3_thread_launch` 管道）；`classes` 裡同一個類別列了好幾個實例時，由上往下或照 `account_strategy` 挑選。

```yaml
# 2026-11-21 ryan 定案：派出去的子任務要開在 T3 看得到的對話（要能確認 prompt 符不符合預期、看過程），
# 無頭派送（agy_cli）只在 ryan 同意或 T3 沒在跑時用。
visibility: visible

# 2026-11-23 ryan 暫定（兩週後 2026-12-07 檢討）、2026-11-25 對齊：限定在 Gemini 系列開到該模型的最高檔 <!-- review_on: 2026-12-07 reason: Gemini max_available 兩週試用期滿體檢 -->
# （Neon、Hydrogen、Orchestrator 用 xhigh；Carbon 最高 high）。Claude 系列的 effort 照分派政策 levels 分級，不套用 max_available 誤拉成 max。
thinking_preference: max_available

# 2026-11-23 ryan 定案（D2）、2026-11-25 對齊兩桶結構：額度用完照接手順序（antigravity_ryan Gemini Models 桶 →
# 同帳號 Claude & GPT 桶的 Opus → Claude 三個實例依 weekly-first 挑 → 停下來列全部 6 個手動帳號狀態與重置時間由我決定）。
# 派跨家審查時雙向跳過同供應商（審 Claude 產出跳過換成 Claude，審 Gemini 產出跳過換回 Gemini）。細節 docs/proposals/2026-11-23-account-pool.md 第四節。
on_exhausted: prompt_manual_switch

# 2026-11-23 ryan 定案（D7＋屏蔽 Argon）、2026-11-25 加入 Haiku 5.5：
# 3.8 Flash 有後繼 Hydrogen、Argon 已併桶且耗時慢、GPT-OSS 120B 與 Claude Haiku 5.5 在分派角色皆不使用，一併排除。
exclude_models: [gemini-3.8-flash, gpt-oss-120b, gemini-4-argon, claude-haiku-5-5]

instances:
  # 2026-11-23 ryan 確認（D3）：3 個 Claude 帳號都在 ryan 本人名下；開新子對話時依額度（weekly-first）在工作包邊界自動挑，同一條對話不中途換。
  # claude-fable 只宣告在 claudeAgent（Ryan）：2026-11-25 曾替三個實例都補上 claude-fable，但沒實測。
  # 實測依據：2026-11-26 14:19 UTC 派 Fable 5.2 到 claudeAgent_2（retis）五條全失敗，T3 回「Fable 5.2 requires usage credits.
  # Switch to another model to continue.」，所以移除。claudeAgent_claude_kai（Kai）沒實測過；T3 目錄雖然列了 claude-fable-5-2，
  # 但 retis 也有列、實際卻不能用，所以 Kai 在實測成功前不宣告。pool-state 兩者都記了 model_forbidden。
  # Kai 的 access_ends：ryan 2026-11-27 原話「現在多一個Kai Claude帳號要消耗 因為我訂閱28號就到期了」。
  # 確切到期時刻【待驗證】（沒有一手證據），先以 11-28 當天開始前（台北 00:00）為準、提早燒；
  # 到期前 48 小時內 weekly-first 把它排第一、第二意見的燒額度改判也算它，過了就不再自動派、不再推薦。
  claudeAgent:            {driver: claudeAgent, account: Ryan,  owner: self, tos_ack: "2026-11-23 D3：本人名下，工作包邊界依額度挑", classes: [claude-opus, claude-sonnet, claude-fable]}
  claudeAgent_2:          {driver: claudeAgent, account: retis, owner: self, tos_ack: "2026-11-23 D3：本人名下，工作包邊界依額度挑", classes: [claude-opus, claude-sonnet]}
  claudeAgent_claude_kai: {driver: claudeAgent, account: Kai,   owner: self, tos_ack: "2026-11-23 D3：本人名下，工作包邊界依額度挑", classes: [claude-opus, claude-sonnet], access_ends: "2026-11-28T00:00:00+08:00"}
  antigravity_ryan:
    driver: antigravity
    account: ryan
    classes: [gemini-pro, gemini-fast, gemini-carbon, gemini-orchestrator, antigravity-opus]
    owner: self
    tos_ack: "2026-11-22 2B：知道 Google FAQ 寫消費方案不支援別家 agent 驅動 agy，選擇照舊；固定這一個、不輪換、一次一條"
    note: Neon、Hydrogen、Orchestrator 最高 xhigh；Carbon 與這裡的 Claude Opus 最高 high（2026-11-25 經 T3 實測 Orchestrator 與 Opus 皆通過；Argon 已屏蔽）
  # 以下 6 個是 1A 手動帳號（classes 留空，agent 不自動派、不自動輪換）：
  # 2026-11-25 T3 目錄實查：每個 Antigravity 實例皆列出 Neon、Hydrogen、Carbon，且獨立檔案式 token 儲存已生效。
  # 併發與主線互補原則（2026-11-26 定案）：
  # - antigravity_ryan（2B 跨家自動派工）：維持一次一條低併發；
  # - ryan 本人手動開的 1A 帳號（kanny163 / km0529 / stk608 / stk824 / itri / ava）：一次集中啟用 1 隻帳號，
  #   該帳號內可手動平行開 2 條對話跑不同專案，5 小時額度滿再換下一隻；
  # - 當主線本身開在手動 1A 帳號（Carbon／Neon）時，重要統整與設計留在主線做，反向跨家審查與獨立改動優先派給 3 隻 Claude 實例
  #   （Fable 5.2／Opus），不硬派回 antigravity_ryan 造成單帳號排隊塞車與撞額度。
  antigravity_kanny163: {driver: antigravity, account: kanny163, classes: []}
  antigravity_km0529:   {driver: antigravity, account: km0529,   classes: []}
  antigravity_stk608:   {driver: antigravity, account: stk608,   classes: []}
  antigravity_stk824:   {driver: antigravity, account: stk824,   classes: []}
  antigravity_itri:     {driver: antigravity, account: itri,     classes: []}
  antigravity_ava:      {driver: antigravity, account: ava,      classes: []}
  # antigravity_kai（舊方案）：11-22 退出派工並從 T3 移除；資料夾 2026-11-23 已刪。

# 備註：
# - 派給 Claude 時照 run.py show 的實例推薦（weekly-first，距週重置 < 48h 優先燒完，在工作包邊界挑，同一條對話不中途換）；effort 照分派政策 levels 分工表。
# - Codex（2026-11-21 更正、2026-11-25 實查）：訂閱已到期，T3 的 codex 實例目前停用；長期審查流程不依賴官方 Codex，改派 Carbon high / Fable 5.2 high / Opus xhigh 或走本機橋接。
# - Antigravity 15 分鐘逾時：不限制主線供應商；Antigravity（Carbon／Neon）主線遇大型任務採背景子對話或分階段回報避開 15 分鐘靜默逾時（下次 T3 升版時重查），遇橫幅先檢查完成狀態與交付物再續跑。
```
