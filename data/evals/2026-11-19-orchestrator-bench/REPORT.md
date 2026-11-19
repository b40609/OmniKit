# Antigravity Orchestrator (Neon) vs Gemini 4 Neon (High) 小實測報告

日期：2026-11-19
執行環境：本機 `agy` CLI（Antigravity Ryan 帳號），依序執行（避免同帳號並發限流）。
規格與腳本：`SPEC.md`、`verify_bench.py`、`run_bench.py`、原始彙總 `summary.json`。

## 1. 先行參數查證（一手實測）

- `agy models` 列出 `gemini-pro-orchestrator-neon`（Orchestrator (Neon)）與 `gemini-pro-orchestrator-g1-pro`（Orchestrator (Argon)），以及 `gemini-4-neon-high` 等模型。
- 實測對 `gemini-pro-orchestrator-neon` 傳入 `--effort high`：
  ```text
  agy -p "..." --model gemini-pro-orchestrator-neon --effort high --output-format json
  ```
  結果：exit code 1，錯誤原文：
  `invalid model selection (--model "gemini-pro-orchestrator-neon" --effort "high"): --effort is not supported for model "gemini-pro-orchestrator-neon"`。
- 結論：透過 `agy_cli` 呼叫 Orchestrator 時不可帶 `--effort`；對照組直接指定 `--model gemini-4-neon-high`（模型代號本身已指定 High）。

## 2. 實測設計

- **任務**：在兩個完全相同的乾淨沙盒（`run_orchestrator/`、`run_neon_high/`）中，依同一份 `SPEC.md` 與真實的 T3 `orchestrator_capabilities`、`agy models` 樣本，使用純 Python 3.12+ 標準函式庫實作 3 個獨立模組（`catalog.py`、`resolver.py`、`cli.py` + `__init__.py`）與 `tests/test_model_router.py`，並通過 `unittest`。
- **客觀驗收**：兩組執行完後，皆以同一份獨立的 `verify_bench.py`（兩組不可見）跑 14 項功能、邊界與 CLI exit code 驗收測試。
- **執行指令**：
  - 組 A：`agy -p <PROMPT> --model gemini-pro-orchestrator-neon --output-format json --disable-slash-commands --dangerously-skip-permissions --print-timeout 600s --log-file log_orchestrator_neon.txt`
  - 組 B：`agy -p <PROMPT> --model gemini-4-neon-high --output-format json --disable-slash-commands --dangerously-skip-permissions --print-timeout 600s --log-file log_neon_high.txt`

## 3. 實測數據（n = 1）

| 指標 | Orchestrator (Neon) | Gemini 4 Neon (High) | 差異（Orchestrator 對 Neon High） |
| --- | ---: | ---: | --- |
| 結束狀態 | SUCCESS (rc=0) | SUCCESS (rc=0) | 持平 |
| 獨立驗收通過數 | 14 / 14 | 14 / 14 | 持平 |
| 自寫 unittest 數 | 18 | 19 | -1 |
| 產出總行數（5 檔） | 949 行 | 952 行 | -3 行（幾乎相同） |
| 牆鐘耗時（wall_seconds） | 213.46 秒 | 247.89 秒 | -34.43 秒（快 13.9%） |
| CLI 回報耗時（duration_seconds） | 208.81 秒 | 244.10 秒 | -35.29 秒（快 14.5%） |
| 扣除安全監控後的 agent LLM 呼叫數 | 6 次 | 7 次 | -1 次 |
| `input_tokens` | 99,276 | 169,591 | -70,315（少 41.5%） |
| `output_tokens` | 22,077 | 18,859 | +3,218（多 17.1%） |
| `thinking_tokens` | 7,982 | 7,947 | +35（幾乎一致，+0.4%） |
| `cache_read_tokens` | 143,934 | 107,474 | +36,460（多 33.9%） |
| `total_tokens` | 121,353 | 188,450 | -67,097（少 35.6%） |

## 4. Log 機制觀察與實驗限制

1. **實際執行行為**：檢視 `log_orchestrator_neon.txt`，Orchestrator 啟動後先進入 Plan Mode 規劃（17:04:56 到 17:06:22），呼叫 `exit_plan_mode` 離開規劃模式後，在單一推論步驟批次寫出 4 個模組檔，再寫測試與執行驗證。
2. **本題未觸發平行子代理**：兩個 log 都只建立 1 個 conversation（`6e90fa97-...` 與 `de69a726-...`），沒有啟動額外子代理對話。推測本題規模（5 檔、約 950 行）尚未達 Orchestrator 拆派 Hydrogen 平行子代理的門檻。
3. **為什麼本題 total_tokens 較少**：Orchestrator 因為先規劃清楚，少跑了 1 輪 agent LLM 呼叫（6 次對 7 次），且 `cache_read_tokens` 命中較多（143,934 對 107,474），使未快取 `input_tokens` 少 41.5%；`output_tokens` 因多出規劃輸出反而略高 17.1%。
4. **思考量觀察**：雖然 Orchestrator 不能帶 `--effort`，實測 `thinking_tokens`（7,982）與 `gemini-4-neon-high`（7,947）幾乎完全相同；其內部預設應屬 high 級別思考量，但官方未公開內部設定，屬實測觀察推論。
5. **仍待驗證的項目**：
   - 真正觸發平行 Hydrogen 子代理的大任務（例如跨多目錄、多子系統重構）時，子代理的 token 是否計入 CLI 回傳的 `usage`、總體是否真的比單跑 Neon High 省 token：【待驗證】。
   - Antigravity 帳號週額度實際扣除比例（Orchestrator 對 Neon High 對 Hydrogen）：【待驗證】（需在實測前後查帳號額度變化）。
   - `antigravity_ava`、`antigravity_kai`（印度 Jio 方案）能否使用 Orchestrator：待實測驗證（已知兩帳號無 Gemini 4 系列，預期不能用，標【待驗證】）。
   - 本次為單次對照（n = 1），快取命中率可能受時間與伺服器狀態波動影響。

## 5. 候選角色比較：Antigravity Orchestrator vs OmniKit 自派子任務

將 Orchestrator 視為分派政策裡的一個候選角色（例如 `gemini-orchestrator`：「大任務的規劃＋平行實作」），與目前 OmniKit「主控（Claude/Gemini）＋自派子代理（`delegate_task` / `agy_cli`）」比較：

| 面向 | Antigravity Orchestrator（`gemini-pro-orchestrator-neon`） | OmniKit 自派子任務（主控＋子代理） |
| --- | --- | --- |
| 跨家審查（寫與審不同家） | 不支援（全在 Google Gemini 體系內：Neon＋Hydrogen） | 支援（Claude 定案＋Gemini 唯讀審查，或反之） |
| 派工粒度與可控性 | 黑盒自決定是否拆子代理、不可設 `--effort`、不可強制套用各角色獨立規則 | 可精準指定每個子任務的模型、thinking 程度、worktree 隔離、完成標記與驗收條件 |
| T3 介面整合度 | T3 `antigravity` 實例目前（2026-11-19）尚未列出，只能走 `agy_cli` 管道 | 完整支援 `delegate_task`、`t3_thread_launch`、T3 側邊欄追蹤與自動 settle |
| 任務規劃與多檔實作效率 | 內建 Plan Mode＋自動平行實作，免主控手寫多個子任務 brief；本實測快 13.9%、total_tokens 少 35.6%（未觸發子代理場景） | 主控需自行拆包、撰寫 brief、回收並整合，編排開銷較高 |
| 額度與帳號彈性 | 綁定單一 Antigravity 進階帳號（Ryan）；ava／kai 預期無法用【待驗證】 | 可跨帳號、跨供應商調度（Ryan／retis／Kai／ava／kai） |
| 適合納入的角色定位 | **選配候選角色**（`gemini-orchestrator`）：非關鍵／非高風險的大型單一工作包（例如多檔原型、大量文件與測試實作），走 `agy_cli` 單次交付，完成後仍由主控驗收 | **核心架構**：跨專案、跨模型寫審分離、需 worktree 隔離、需記錄委派帳本與嚴格分級的任務 |
