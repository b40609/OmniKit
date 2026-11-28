# 子任務分派與委派紀錄

[← 回到首頁](../README.md) · [安裝說明](install.md) · [使用指南](usage.md) · [運作方式](architecture.md) · [維護名冊](maintainer.md)

派子任務或開子對話時，用哪個管道、哪個模型、多少思考程度，由 `omnikit-dispatch` skill 照政策決定。政策只會派給**你方案裡有的模型**：沒有 Gemini 就不做跨家審查，沒有 Fable 5.2 就改用 Opus，不會出現派不出去的級別。

- [兩層設定](#兩層設定)
- [每一級用什麼](#每一級用什麼)
- [設定自己的帳號對應](#設定自己的帳號對應)
- [選配模型：Fable 5.2](#選配模型fable-52)
- [委派紀錄與 Sonnet 試行](#委派紀錄與-sonnet-試行)
- [本週 Claude 用量](#本週-claude-用量給高級的-80-條件)

## 兩層設定

| 層 | 檔案 | 寫什麼 |
|---|---|---|
| 共用（所有人） | `data/rules/dispatch.md`（原則，常駐載入）與 `data/rules/dispatch-policy.md`（完整政策，要派才讀） | 任務類型 → 級別（中、高、更高、獨立驗收、重大架構）→ 模型類別 → 思考程度 → 升級路徑；管道怎麼選；Sonnet 試行的品質保護；委派紀錄的欄位 |
| 個人（profile） | profile 資料夾的 `dispatch.md` | 你有哪些供應商實例（T3 的 providerInstanceId）、每個模型類別用哪個、要不要啟用選配模型；沒有這份就只用原生子代理 |

共用層 `data/rules/dispatch.md` 會跟安全底線、profile 的 `AGENTS.md` 一起常駐載入三個 agent；完整政策 `dispatch-policy.md` 與個人層 `dispatch.md` 不佔常駐規則字數，需要派工時由 `engine/scripts/dispatch.py` 讀取。改共用層要更新 `data/rules/baseline.md` 的規則版本（標準安裝套用更新重跑 `install.ps1` 或 `uv run engine/scripts/profiles.py`）。

派之前跑 `uv run engine/scripts/dispatch.py show`（或 skill 裡的 `run.py show`），會印出套上你的實例之後每一級依序能用的選項；沒有實例的、選配沒宣告的、已有更好選項的備援，都會標明跳過的原因。

## 每一級用什麼

下表是**沒有寫個人 `dispatch.md`、只有 Claude** 時 `show` 會給的結果（多數單一供應商環境的情況）：

| 級別 | 任務 | 用什麼 |
|---|---|---|
| 中 | 文件整理、大範圍讀檔、介面與小修改 | 讀檔／雜務用 Opus（effort medium），多檔／UI 用 Opus（effort high），退路 Sonnet（effort medium） |
| 高 | 重要統整、設計決策、核心改動、帳務、風控、下單 | Opus（effort high） |
| 更高 | 難查的錯誤、驗收一直不過 | Opus（effort xhigh） |
| 獨立驗收 | 高風險改動的獨立審查 | Opus（effort xhigh） |
| 重大架構 | 兩階段防迎合盲審 | Opus（effort xhigh），協定照政策的 `blind_review` |

沒有第二家模型時，跨家第二意見全部跳過，不會出現同模型自己審自己；「本週用量 80% 改派 Antigravity」那條也不會用到。只有其他 Claude 帳號要給 T3 的 `delegate_task` 指定時，才需要寫 `claudeAgent` 類的實例。

有 Gemini（Antigravity）實例時，中級改由 Gemini 4 Hydrogen／Neon（thought_level xhigh）先接，高級加入 Gemini 4 Carbon（thought_level high），並啟用雙向跨家審查：Claude 的重要產出給 Carbon 審，Gemini 的重要產出給 Claude 審，審查者不比作者弱。完整路由見 `dispatch-policy.md`。

## 設定自己的帳號對應

最省事的是跟 agent 說「幫我設定 OmniKit」，訪談的帳號池那幾題會掃描這台、逐格給建議並產生這份檔（背後是 `engine/scripts/pool_setup.py`）。要自己寫的話，在你的 profile 資料夾（訪談產生的在 `~/.omnikit/profiles/<名稱>/`）新增 `dispatch.md`。實例 id 用 T3 的 `orchestrator_capabilities` 查（列出的 `providerInstanceId`），`classes` 只能寫共用層 `model_classes` 裡有的類別，而且要跟實例的 driver 對得上：

````markdown
# 個人分派設定：<名稱>

```yaml
instances:
  claudeAgent:  {driver: claudeAgent, account: 我的 Claude, owner: self, tos_ack: "<日期>：讀過規約表，本人帳號、自己用", classes: [claude-opus, claude-sonnet]}
  antigravity:  {driver: antigravity, account: 我的 Google, owner: self, tos_ack: "<日期>：讀過規約表，知道消費方案的限制", classes: [gemini-carbon, gemini-pro, gemini-fast, antigravity-opus]}
```
````

`owner: self` 表示帳號是你本人的；三家條款都禁止把帳號給別人用，不是本人的一律不自動派。訂閱方案登入的帳號，規約表 [`data/rules/provider-terms.md`](../data/rules/provider-terms.md) 標的是「要知情同意」：讀過那一列的原文、仍要讓 agent 自動派，才填 `tos_ack`（寫日期與一句理由，要你自己填，agent 不會代填）。沒填的實例 `show` 會列在「不派」並寫原因；規約寫 `forbidden` 的填了也不派。

寫完跑 `uv run engine/scripts/dispatch.py check` 檢查，再跑 `uv run engine/scripts/dispatch.py show` 看套上之後每一級會用什麼。`data/profiles/ryan/dispatch.md` 是完整的例子。

## 選配模型：Fable 5.2

多數訂閱方案沒有 Claude Fable 5.2，所以政策把它標成選配（`opt_in: true`）：**沒宣告就不會派給它**，連原生子代理也一樣。你的方案有 Fable，擇一宣告：

```yaml
# 只用原生子代理（不經 T3）時
opt_in_classes: [claude-fable]

# 或者在實例的 classes 列出它
instances:
  claudeAgent: {driver: claudeAgent, account: 我的 Claude, owner: self, tos_ack: "<日期>：…", classes: [claude-opus, claude-sonnet, claude-fable]}
```

宣告之後：

- 高級的首選變成 Fable 5.2（effort high），本週用量達 80% 時自動退回下一順位。
- 重大架構盲審改用 Fable 5.2（effort high），死結才升 xhigh。
- 更高與獨立驗收仍用 Opus xhigh，驗收不過或遇到高風險架構才升 Fable。
- 政策裡標 `fallback_for: claude-fable` 的 Opus 備援自動跳過，`show` 會寫「已有 claude-fable，不用這個備援」。

沒宣告的人，升級鏈的終點是 Opus xhigh：仍不過就停下來回報、等你決定，不會自動開 max。

## 委派紀錄與 Sonnet 試行

**委派紀錄。** 子任務結果收回、驗收完、settle 之前，agent 用 `omnikit-dispatch` skill 記一行到 `~/.omnikit/dispatch/log.jsonl`：時間、專案名稱、任務類型、級別、管道、供應商實例、模型類別與模型、思考程度、是否一次通過、重試次數、升級次數、最後過關的類別、驗收結論、規則版本、profile。只存在這台，不進 repo、不上傳；專案只記資料夾名稱。目前是規則要求 agent 寫，不是 hook 自動寫：一次通過、驗收結論這些只有主對話知道。

```powershell
uv run engine/scripts/dispatch.py stats     # 依級別與模型類別的一次通過率，以及 Sonnet 試行的判定
```

**Sonnet 試行。** 中級要用 Claude 時可改派 Sonnet（effort medium）。品質保護：Sonnet 的產出照常驗收，不過就用 Opus、同一級 effort 重跑，記成升級；Sonnet 累積 20 筆後，跟 Opus 同級的一次通過率比，低 10 個百分點以上就退回 Opus。`stats` 會照這條判定，但不會自己改規則。

## 本週 Claude 用量（給高級的 80% 條件）

官方的來源是 Claude Code 狀態列的 JSON 輸入 `rate_limits.seven_day.used_percentage`（只有 Pro、Max、Ultra 訂閱，而且要對話第一個回應之後才有）。要讓 OmniKit 讀得到，把狀態列設成 `dispatch.py statusline`；原本有狀態列的，用 `--then` 串在前面，原本的輸出照樣顯示。在 `~/.claude/settings.json`（或你的 `CLAUDE_CONFIG_DIR`）加：

```json
"statusLine": { "type": "command", "command": "uv run --quiet <OmniKit 路徑>/engine/scripts/dispatch.py statusline --then \"<原本的指令>\"" }
```

快照存在 `~/.omnikit/dispatch/claude-usage.json`，依帳號的設定資料夾分開；`uv run engine/scripts/dispatch.py usage` 讀它。沒有快照、快照的這一週已經重置，就回報「未知」，agent 不會假設已達 80%。在 T3 裡跑 Claude 時狀態列不會觸發，改讀 T3 供應商快取 `~/.t3/caches/<實例>.json` 的 `usageLimits`（只讀額度數字，不讀 auth 欄位）。
