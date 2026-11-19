---
name: omnikit-dispatch
description: 派子任務或開子對話時，照 OmniKit 分派政策選管道、模型與思考程度，並在收完結果、settle 之前記一行委派紀錄；也能看 Sonnet 試行的比較與本週 Claude 用量。要派子代理、delegate_task、開子對話、從 Claude Code 或 Codex 開 T3 對話（t3 thread）、記委派紀錄、看「分派統計」「委派紀錄」「Sonnet 試行」「本週 Claude 用量」時使用。Picks the model and effort for a sub-task from the OmniKit dispatch policy and logs each delegation.
---

# 子任務分派與委派紀錄

載入的規則裡只有分派的原則（`data/rules/dispatch.md`）。完整政策在 repo 的 `data/rules/dispatch-policy.md`，不常駐載入：派之前跑下面的 `show`，它會印出套上你的實例（profile 的 `dispatch.md`；沒有就只用原生子代理）之後每一級可用的選項。管道的細節與實測備註要看原文時再讀那份檔。下面的指令路徑都相對於這個 skill 的資料夾；`uv` 不在 PATH 時，用 `%LOCALAPPDATA%\Programs\uv\uv.exe`。

## 派之前

```
uv run scripts/run.py show
```

印出套上你的實例之後，每一級依序可以用的選項，開頭附本週 Claude 用量。由上往下挑第一個「有實例、額度沒用完、條件成立」的。用量是「未知」時不要假設已達 80%。開子對話或派子代理時，在任務說明寫明級別與思考程度（Claude 寫 effort，Gemini／Antigravity 寫 thinking_level）。

## 派給 Antigravity 的模型（agy_cli 管道）

主控是 Claude Code 或 Codex、而選到的類別是 Antigravity 的（gemini-pro、gemini-flash、antigravity-opus）時，用 agy 無頭派：

```
uv run scripts/run.py agy --class gemini-pro --thinking high --brief-file <任務說明檔> [--cwd <工作資料夾>] [--timeout 1800] [--result-file <交付檔>]
```

- 思考程度由腳本寫進模型代號（`gemini-4-hydrogen-xhigh`），不合政策的（禁用的 low、超過上限）直接擋下。
- 任務說明照常寫明級別、思考程度、完成條件與交付位置；要改檔就說只能改哪些檔。腳本會在後面附上 uv、gh 的絕對路徑（agy 的終端機看不到使用者 PATH）。
- 輸出是 JSON 摘要；`ok` 是 false（終端機指令被拒、沒回覆、逾時）就當這次沒完成，看 `problems`。
- 要跑很久的（調研、大範圍閱讀）用背景執行，完成再收。
- 腳本用略過權限模式跑（無頭模式不能核准指令），並在任務說明前面固定加硬性限制：不 commit、不 push、不刪檔、不對外發送、不安裝。所以要 commit 或 push 的，由主控自己做。
- 腳本也固定加下一節的收尾規定。任務說明沒指定交付位置時，它寫進 `--result-file`（預設在暫存資料夾的 `omnikit-agy`）；輸出的 `result_file`、`done_marker` 說明交付檔與完成標記在不在。沒有標記只會出 `warnings`，不改 `ok`。
- 結果一律由主控驗收（讀它改的檔、跑測試），不要只看它的回覆。
- 記紀錄時 `--channel agy_cli --instance antigravity`。

## 派給 Antigravity 的回合怎麼收尾（所有管道）

agy_cli、t3_cli、`t3_thread_launch`，主控在 T3 裡用 delegate_task 也一樣。原因：2026-11-18 antigravity_kai（gemini-3.8-flash）在 T3 寫完回報後，回合一直不結束，15 分鐘後 T3 印「Antigravity sent nothing for 15 minutes」把對話標成 failed。上游 T3 把這個逾時寫死成 15 分鐘，也不會偵測回合完成。同一次還因為在前景跑伺服器撞到 600 秒工具逾時。證據與出處在 `dispatch-policy.md` 的 `antigravity_turns`。

- **任務說明固定寫四件事**（agy_cli 由腳本自動加，其他管道由主控寫進說明）：
  1. 交付物先寫成檔案，路徑由你在說明裡指定。
  2. 最後一個動作是寫完成標記檔（交付檔路徑加 `.done`，例如 `report.md.done`），寫完才送出最後回覆。
  3. 最後回覆不超過 10 行，附上交付檔路徑。
  4. 伺服器、watcher 這類不會自己結束的程式一律背景啟動，不要在前景跑。
- **驗收**：
  - 有 T3 MCP：用 `t3_thread_wait` 搭配短逾時（約 60 秒）輪詢。看到完成標記，而且 1 到 2 分鐘沒有新活動，就呼叫 `t3_thread_interrupt` 中斷回合，再用 `t3_thread_organize` 帶 `action: "settle"` 結案。不用空等 15 分鐘。
  - 只有 t3_cli：t3 v0.1.10 的 `thread` 只有 list、start、send、show，沒有中斷子指令（2026-11-18 查 `--help`）。Antigravity 的長任務不加 `--wait`（回合卡住時會跟著等到逾時，推論，未實測），改用 `t3 thread show <id> --json` 看狀態並檢查完成標記；標記在就去驗收，回報裡列出對話 id 與標題，請使用者在 T3 停止並結案。
- **以「sent nothing for 15 minutes」失敗收場時**：先檢查交付檔和完成標記，不要直接重派。東西都在就當作完成，照常驗收並結案；不在就用 send 請它接著做。
- **使用者自己在 T3 開的對話**：看到回報檔已經出現、對話卻還顯示 working，跟他說直接按停止。
- 【待驗證】`t3_thread_interrupt` 能不能立刻收掉這種卡住的回合；中斷會不會把最後那則回覆一起吃掉；agy CLI 的無頭模式會不會有同樣的問題。下次實際發生時測。

## 不在 T3 裡也能開 T3 對話（T3 MCP 優先，t3_cli 是退路）

主控是 Claude Code、Codex 或 Antigravity 時，也能開 T3 對話、指定 T3 上的帳號實例與模型（例如 `antigravity_kai` 加 `gemini-3.8-flash`），讓那條對話出現在 T3 側邊欄。**不要回答「這裡沒有 T3 工具，沒辦法派」**。有兩條路：

1. **T3 MCP（`t3_thread_launch` 管道，優先）**：能設思考程度、能自己結案。工具清單裡有 `t3_thread_launch` 就用它；沒有就先跑 `omnikit-capabilities` 看這個 agent 登記、授權了沒。
2. **`t3 thread` CLI（`t3_cli` 管道）**：這個 agent 還沒授權 T3 MCP 時用。不用登入，但不能設思考程度、不能結案。

### T3 MCP

- 接法（2026-11-18 用 Claude Code 實測通過）：`claude mcp add --scope user --transport http t3 http://127.0.0.1:3773/mcp`，再 `claude mcp login t3`。
  - login 要在互動式終端機跑：Bash 工具會回 `this isn't an interactive terminal`，請使用者在終端機分頁跑。
  - 核准頁要 Sign-in code 時，用 `t3 auth pairing create --ttl 10m` 產生，要用預設 scope；只給 orchestration 兩個 scope 的碼不能核准 Full access。
  - 瀏覽器跳到 localhost callback 連不上時，把完整網址貼回終端機的「paste the redirect URL」。
  - 核准一次有效 30 天；每個 `CLAUDE_CONFIG_DIR`、`CODEX_HOME` 都要各做一次。
  - Codex：`codex mcp add t3 --url http://127.0.0.1:3773/mcp` 再 `codex mcp login t3`（2026-11-19 實測 codex-cli 0.168.0：`add` 會寫進 `~/.codex/config.toml` 的 `[mcp_servers.t3]`，並偵測到 OAuth、直接印出授權網址等瀏覽器回呼；沒有核准時 `codex mcp list` 顯示 Not logged in。登入核准後能不能叫用 T3 工具【待驗證】）。
- 在外部 agent 用 `t3_thread_launch`，不要用 `delegate_task`（會回錯）。
- 思考程度：`modelSelection.options` 是陣列，例如 `[{id: "thinking_level", value: "high"}]`。claudeAgent 系列的 id 是 `effort`（low、medium、high、xhigh、max、ultrathink），antigravity 是 `thinking_level`（low、medium、high；Gemini 只能用 high，政策禁用 low、medium）；值以 `orchestrator_capabilities` 查到的為準。【待驗證】antigravity_ava、antigravity_kai 的 capabilities 模型清單是空的，帶 `thinking_level` 開 Flash 能跑完，但在 Gemini 端有沒有生效還不知道。
- 結案：`t3_thread_organize` 帶 `action: "settle"` 與 `threadId`，再用 `t3_thread_read` 回讀確認 `settled: true`。
- 記紀錄時 `--channel t3_thread_launch --instance <實例>`。

### t3 thread CLI

- PowerShell 打 `t3`；Git Bash 要打 `t3.cmd`。`%USERPROFILE%\.t3\bin` 只有 `t3.cmd`，Bash 只會自動補 `.exe`，所以 Bash 的 `command -v t3` 找不到，不代表沒裝。先 `t3 --version` 確認；找不到就跑 `omnikit-capabilities` 的清點。
- 開對話（`.` 是目前 repo；也可以填 project id 或那個專案裡的路徑）：

  ```
  t3 thread start . "<任務說明>" --provider <實例> --model <模型代號> --title "<標題>" --json --wait
  ```

  - `--provider` 是 profile `dispatch.md` 裡 `instances` 的 key，要和 `--model` 一起給。
  - 任務說明很長時訊息填 `-`，從 stdin 讀：`Get-Content brief.md -Raw | t3 thread start . - --provider ... --model ...`。
  - 要獨立 worktree：加 `--worktree <分支或 commit>`，可再加 `--branch <新分支名>`。
  - `--wait` 等它做完並印回覆；結束碼 1 是執行失敗、2 是對話在等人回答（用 `send` 回它）。不加 `--wait` 就只印對話 id，適合長任務。
- 之後：`t3 thread show <id> --json` 看狀態與最新訊息；`t3 thread send <id> "<訊息>" --wait` 追問；`t3 thread list --json` 列出對話。
- 限制（t3 v0.1.10）：沒有思考程度參數，Antigravity 的模型只能把程度寫進代號（`gemini-4-hydrogen-xhigh`）；沒有 settle 子指令，主控有 T3 MCP 就用 `t3_thread_organize` 結案，沒有就在回報裡列出對話 id 與標題，請使用者在 T3 結案。
- 記紀錄時 `--channel t3_cli --instance <實例>`。

### 和其他管道的分工

同供應商、不用指定帳號 → 原生子代理；要 Antigravity 模型、要看思考 token 或在背景跑 → agy_cli；要指定 T3 的帳號實例、要在 T3 看到 → 接了 T3 MCP 用 `t3_thread_launch`，沒接用 `t3_cli`；主控本身在 T3 裡 → delegate_task。結果一律由主控驗收。

## 收完結果、settle 之前：記一行

一次委派一行。重跑與升級記在同一行，`--class` 寫一開始派的類別，`--final-class` 寫最後過關的類別。

```
uv run scripts/run.py log --task <任務類型> --class <模型類別> --thinking <程度> --verdict <pass|fail|partial|skipped> \
  [--channel native|agy_cli|t3_cli|delegate_task|t3_thread_launch] [--instance <實例>] [--retries N] [--escalations N] [--final-class <類別>] [--control] [--note <一句話>]
```

- `--task`：共用層 `tasks` 的 key（docs、ui-small、readonly、code-small、accounting、risk、orders、design-decision、hard-bug、acceptance-loop、verify）。級別會自動帶出來。
- `--verdict`：驗收結論。`skipped` 是沒有驗收，不算進通過率。
- 一次通過：沒寫 `--first-pass` 時，結論是 pass 而且沒有重跑、沒有升級才算。
- `--instance`：用 delegate_task、t3_thread_launch 時寫 providerInstanceId，用 t3_cli 時寫 `--provider` 的值；原生子代理不用寫。
- `--control`：Sonnet 試行的對照組（中級改派 Opus 的那幾次）。
- `--note`：一句話，不寫專案內容細節、不寫金鑰或 token。
- 時間、專案名稱、規則版本、profile 自動帶；不確定欄位怎麼寫，先加 `--dry-run` 看會寫出什麼。
- 寫在本機 `~/.omnikit/dispatch/log.jsonl`，不進 repo、不上傳。

範例：Sonnet 做的文件驗收不過，改 Opus（同一級 effort）重跑後過關：

```
uv run scripts/run.py log --task docs --class claude-sonnet --thinking medium --verdict pass --escalations 1 --final-class claude-opus
```

## 看統計

```
uv run scripts/run.py stats
```

依級別與一開始派的類別列一次通過率，再列 Sonnet 試行的判定：Sonnet 累積 20 筆、Opus 同級也有足夠基準時，Sonnet 低 10 個百分點以上就是「退回」。照輸出回報，不要自己改規則；要退回或調整，先問使用者。

## 本週 Claude 用量

```
uv run scripts/run.py usage
```

讀 Claude Code 狀態列存下的快照。沒接狀態列、不是訂閱制、或快照的這一週已經重置，就是「未知」。怎麼接狀態列，見 README 的「子任務分派與委派紀錄」。
