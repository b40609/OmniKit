# OmniKit 對接 OmniKeep 手機端工具評估閉環（軌 A）交付報告

日期：2026-11-24

## 1. 交付摘要

已完成 OmniKit 側 5 項對接需求，讓 OmniKeep 的 `EvaluatorAdapter`（`OmniKitAdapter`）可透過非互動 subprocess 與 UTF-8 JSON stdio，完成純唯讀單筆評估（Layer 0 + Layer 1）、社群反例驗證、安全徽章分級與拍板落地回寫。

## 2. 需求實作明細

### 需求 1：單筆非互動評估 CLI（`scripts/eval_single.py`）
- 新增實作 `engine/skills/omnikit-eval/scripts/eval_single.py` 與頂層入口 `scripts/eval_single.py`（同時支援 `python scripts/eval_single.py` 與 `uv run scripts/eval_single.py`）。
- 支援 `--health`、`--version`（印出 JSON 狀態並以 0 結束）與 `--selftest`；入口透過 `_omnikit.utf8_stdio()` 確保 Windows `cp950`/`utf-8` 環境下 stdio 不亂碼，除錯與錯誤日誌一律走 `stderr`，`stdout` 僅輸出單一 UTF-8 JSON 物件。
- 接收標準請求 JSON（`schema_version`, `request_id`, `source_item_id`, `eval_track`, `target_url`, `target_repo`, `user_note`, `source_summary`, `community_counterpoints`, `max_layer`）。
- 當 `max_layer <= 1` 時嚴格純唯讀：不寫入 `data/`、不修改工作區檔案、不進入 Layer 2 實測或安裝流程（掃描僅於系統暫存目錄淺層 clone 並於 `finally` 清除）。
- 輸出完整對齊契約：`schema_version`, `status`, `security_badge`, `layer0`, `layer1`（現場通過 `contracts/layer1.schema.json` 驗證）, `slot_comparison`（`matched_slots`, `incumbent_tools`, `delta_summary`）, `suggested_action`（`approve_l2` | `on_demand` | `reject`）, `error`。

### 需求 2：擴充 Layer 1 納入使用者提問與社群反例
- 擴充 `engine/skills/omnikit-eval/scripts/layer1.py` 的 `INSTRUCTIONS`、`build_prompt()` 與 `evaluate()`，支援 `user_note`、`source_summary` 與 `community_counterpoints`（外部內容一律包在 `<<<SOURCE_SUMMARY`、`<<<COUNTERPOINTS` 隔離區塊，維持 prompt injection 防護）。
- 新增 `counterpoint_to_claim()` 與 `ensure_feedback_coverage()`：即使模型回應遺漏，後處理與離線規則初判仍確保 `differences` 明確回應 `user_note`，且社群實測限制自動轉為具體可查證的 `claims`（對應 `capability`/`compat`/`cost`/`quality`/`security` 與 `how_to_verify`），避免只複述原作者 README。

### 需求 3：修補 `layer0.py` 安全掃描盲區與結構化 `security_badge`
- 擴充 `engine/skills/omnikit-eval/scripts/layer0.py`：新增 `inspect_repo_tree()`、`classify_security()`、`scan_local()` 與純函式入口 `evaluate_target()`。
- 盤點目標 repo 是否含 `package.json`、`Cargo.toml`、`pyproject.toml`、建置檔、Shell 安裝腳本（`.sh`/`.ps1`/`.bat`/`.cmd`/shebang）、可執行原始碼（`.py`/`.js`/`.ts`/`.rs`/`.go` 等）、MCP server 設定（`.mcp.json`/`mcp_config.json`/含 `mcpServers` 或 `hooks` 的 `plugin.json`），以及是否掃出 0 個 `SKILL.md`。
- 三態判定：
  - `risk_flagged`：檢出 `HIGH`/`CRITICAL` 規則或高危旗標。
  - `executable_needs_review`：未掃描、掃描報錯、掃出 0 個 `SKILL.md`，或含任何可執行碼／安裝腳本／MCP 設定（此時 `verdict` 不可輸出 `pass`，降為 `warn`）。
  - `skill_scan_pass`：僅確認存在靜態 `SKILL.md` 且無可執行碼／腳本與高風險規則。

### 需求 4：拍板回寫 CLI（`scripts/record_decision.py`）
- 新增實作 `engine/skills/omnikit-eval/scripts/record_decision.py` 與頂層入口 `scripts/record_decision.py`，支援 `--health`、`--version`、`--data` 與 `--selftest`。
- 擴充 `engine/schema/tool.schema.json` 支援 `status: "on_demand"` 與 `trigger_when` 欄位，並允許不在任何槽位範圍的工具記為 `rejected` 或 `on_demand`；同步更新 `engine/scripts/build.py`、`engine/site/style.css`、`engine/scripts/advise.py` 與 `_omnikit.py` 相容 `on_demand`。
- 三種拍板落地行為（皆於寫入後跑 `validate.check()` 驗證）：
  - `approve_l2`：產出符合 `contracts/layer2-request.schema.json` 的請求檔至 `data/funnel/layer2-requests/<tool_id>.json`，更新 `data/funnel/layer2-todo.md`（具冪等性）並補齊 `data/tools/<tool_id>.yaml`。
  - `on_demand`：以 Progressive Disclosure 原則將卡片寫入 `data/tools/<tool_id>.yaml`（`status: "on_demand"` 與 `trigger_when` 索引），不掛 `plugin`、不進 marketplace、不修改規則與 MCP 設定（維持 0 token 常駐）。
  - `reject`：寫入 `data/tools/<tool_id>.yaml`（`status: "rejected"`、`reason`）與 `data/funnel/rejected-history.jsonl`；同步強化 `layer0.similar_rejected()` 讀取名冊與拒絕歷史，確保下次遇見同 repo（`similarity = 1.0`）或同類工具皆命中 `similar_rejected`。

### 需求 5：契約測試與 `.omnikit.json` 路徑一致性檢查
- 新增 `tests/test_omnikeep_eval_bridge.py`（28 項測試全過），並將 `scripts/eval_single.py --selftest` 與 `scripts/record_decision.py --selftest` 加入 `.github/workflows/validate.yml`（自動涵蓋 Linux CI 與 Windows PowerShell 5.1/7 cp950 長路徑 CI）。
- `.omnikit.json` 路徑配置對照（依據 `engine/scripts/agents.py:144-150` 與 `364-392`）：
  | OmniKeep 偵測路徑 | OmniKit `agents.py` 實際配置 | 一致性與說明 |
  |---|---|---|
  | `~/.agents/skills/omnikit-eval/.omnikit.json` | Codex（`copy` 模式，寫入 `{"source", "repo", "hash"}`） | **完全一致（直接命中）**，並已由測試驗證從該 `repo` 可直接定位 `scripts/eval_single.py` 與 `scripts/record_decision.py` |
  | `~/.claude/skills/omnikit-eval/.omnikit.json` | Claude Code（預設 `link`/junction 指向 `<repo>/engine/skills/omnikit-eval`；建不起連結時 fallback 為 `copy` 並寫 `.omnikit.json`） | fallback 複製模式一致；預設連結模式不於 repo 內產生 `.omnikit.json`（避免污染工作樹與違反 FR-38），建議上游若僅安裝 Claude Code 時補充對 symlink/junction 的 `resolve().parents[2]` 解析 |
  | `~/.codex/skills/omnikit-eval/.omnikit.json` | OmniKit 的 Codex skills 依官方慣例放於 `~/.agents/skills/`，不寫入 `~/.codex/skills/` | 由第一條 `~/.agents/skills/omnikit-eval/.omnikit.json` 涵蓋；另 OmniKit 對 Antigravity 寫入 `~/.gemini/config/skills/omnikit-eval/.omnikit.json`（`copy` 模式），上游可視需要納入備援偵測 |

## 3. 驗證結果

- `python -m pytest tests/test_omnikeep_eval_bridge.py -v`：**28 passed**（含 `max_layer=1` 子程序執行前後工作區檔案 SHA-256 零變動驗證）
- Windows `cp950` stdio 實測（未設 `PYTHONUTF8`）：`scripts/eval_single.py --health`、`scripts/record_decision.py --health` 均回傳合法 UTF-8 JSON 且 exit 0
- `uv run engine/scripts/validate.py`：名冊驗證通過（16 模組、44 槽位、139 工具卡）
- `uv run engine/scripts/build.py --check` & `--site _site`：通過
- `uv run scripts/eval_single.py --selftest`：6/6 通過
- `uv run scripts/record_decision.py --selftest`：5/5 通過
- `uv run engine/skills/omnikit-eval/scripts/selftest.py`：30/30 通過
- `uv run engine/skills/omnikit-eval/scripts/layer1.py --selftest`：16/16 通過
- `uv run engine/skills/omnikit-eval/scripts/batch0.py --selftest`：通過
- `uv run engine/scripts/advise.py --selftest` & `engine/scripts/agents.py --selftest`：全部通過
