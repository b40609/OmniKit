# 跨模型、跨應用的多代理分工

日期：2026-11-16。狀態：已採用（規則版本 2026-11-16-3），政策在 `data/rules/dispatch.md`，派法在 omnikit-dispatch skill 的 `run.py agy`。

## 要解決的事

ryan 的要求：Claude 只拿來做真正重要的事；Hydrogen 又快又便宜，要用上。要的是 Anthropic 多代理研究系統那種「主控加工作者」，但工作者跨模型、跨應用。

改之前的實況（委派紀錄，2026-11-14 到 11-16）：中級 7 筆裡 6 筆派給 Sonnet，Hydrogen 1 筆而且失敗。原因是 Claude Code 只有原生子代理一條路，規則裡「或要用只有 Claude 有的工具」成了通行證。

## 業界做法

飽和式調研由 Hydrogen 完成，49 組關鍵字、帳本「可以停」，全文在 `data/evals/2026-11-16-cross-model-dispatch-research.md`。歸納出 6 種模式：

| 模式 | 做法 | 代表（★ 為 2026-11-16 gh api 實測） | OmniKit |
|---|---|---|---|
| 1. 主控規劃、便宜模型執行 | 主控保留判斷，掃描、閱讀、樣板改動派給便宜或長上下文模型 | pal-mcp-server ★11,840（`clink` 叫別家 CLI）、oh-my-claudecode ★40,848、oh-my-openagent ★70,931 | 採用：中級全部、重要任務的前置苦工派 Hydrogen |
| 2. 不同家的模型互審 | 寫的模型不能自己過審，換一家審 | codex-plugin-cc ★35,153（adversarial-review）、metaswarm ★432 | 採用：Hydrogen 寫的由 Claude 驗收；Opus 做的由 Hydrogen xhigh 唯讀審查 |
| 3. 多模型議會 | 同一題問 3 家以上，再綜合 | claude-octopus、claude-council | 不做：成本高、沒有證據顯示值得 |
| 4. worktree 平行加看板 | 一個子任務一個 worktree，人看 diff 合併 | vibe-kanban ★28,701、claude-squad、awslabs/cli-agent-orchestrator ★1,562 | 不做：T3 已有子對話；凍結期間不加 |
| 5. 直接驅動別家官方 CLI | 用各家 CLI 的無頭模式或 ACP，保留各自登入與額度 | ACP 轉接器、cc-multi-cli-plugin、agent-bridge | 採用：`agy -p` 無頭呼叫（agy 也有 `acp` 子指令，之後再看） |
| 6. 額度感知、429 自動換 | 額度用完照順序換到下一個 | OmniRoute、CLIProxyAPI、claude-code-router | 部分：規則裡有退路順序，靠主控判斷；不做自動攔截 |

## 分工

| 工作 | 誰做 | 管道 |
|---|---|---|
| 主線：規劃、拆解、定案、最後驗收 | Claude（主線對話） | — |
| 中級：docs、readonly（含調研）、ui-small、code-small | Hydrogen high | agy_cli |
| 高級（帳務、風控、下單、設計決策） | 前置：Hydrogen high 收資料、列候選；定案：Opus high；審查：Hydrogen xhigh 唯讀 | agy_cli、native |
| 更高級（難查的錯誤、驗收一直不過） | 前置：Hydrogen xhigh 重現、縮範圍；定案：Opus xhigh；審查：Hydrogen xhigh | agy_cli、native |
| 獨立驗收 | Opus high 主驗收，Hydrogen xhigh 第二意見（預設要跑） | native、agy_cli |
| Hydrogen 額度用完 | docs、readonly 給 Flash；改程式碼的給 Sonnet medium | agy_cli、native |
| Hydrogen 驗收不過 | Sonnet medium 重跑，再不過升 Opus | native |

Codex 已改免費版，不排進路由。

## 實測（2026-11-16，agy 1.5.9）

- **思考程度能指定**：`--model gemini-4-hydrogen-xhigh` 或 `--effort xhigh` 都生效，log 印 `resolved to "gemini-4-hydrogen-xhigh"`。思考 token 各 3 次：high 892 到 1145，xhigh 1846 到 3333。只寫 `gemini-4-hydrogen` 會落到 medium（684 到 837）。T3 也能用：`t3 thread start --provider antigravity --model gemini-4-hydrogen-xhigh`，T3 介面標 Unavailable（目錄裡沒有這個代號），但後端 antigravity-acp 的紀錄寫「as gemini-4-hydrogen-xhigh」；只寫 `gemini-4-hydrogen` 在 T3 會用 high。T3 看不到思考 token，xhigh 多想多少待驗證。
- **能改檔、能自己跑測試**：在暫存資料夾修兩個小 bug，改對並跑過測試。
- **權限**：無頭模式不能核准。agy 的安全監控把不認得的指令送審就自動拒絕，時好時壞（第一次調研跑到一半被拒）；`--mode accept-edits` 一律拒終端機指令；`--settings` 的允許規則讓指令落進沙盒，uv 跑不起來。`--dangerously-skip-permissions` 連 3 次穩定。所以 `dispatch.py agy` 用它，任務說明前面固定加硬性限制（不 commit、不 push、不刪檔、不對外發送、不安裝），結果由主控驗收。
- **PATH**：agy 的終端機只有系統 PATH，`dispatch.py agy` 會附上 uv、gh、git、node 的絕對路徑。
- **成本與時間**：簡單問題 14 到 18 秒；每次開頭約 2.3 萬 token 的規則。這次調研 32 分鐘、約 107 萬 token、思考 3.3 萬 token。

## 風險

- 第三方評測裡 Sonnet 5.5 寫程式小幅領先 Hydrogen（BenchLM，待驗證），所以 Hydrogen 的結果一定經主控驗收；驗收不過照升級路徑走。
- 略過權限模式只靠任務說明的限制約束；主控派之前要寫清楚能改哪些檔，收回時看 `git status` 與 diff。
- 調研的帳本記了 1,251 個名字，裡面有不少雜訊（Hydrogen 收得太寬）；結論以報告第 2、3 節實測過的專案為準。

## 怎麼看有沒有用

委派紀錄 `dispatch.py stats` 依級別與類別列一次通過率。兩週後（2026-11-30）看：中級裡 Hydrogen 的筆數是否過半、一次通過率跟 Sonnet 差多少。差 10 個百分點以上，就把改程式碼的中級任務退回 Sonnet。
