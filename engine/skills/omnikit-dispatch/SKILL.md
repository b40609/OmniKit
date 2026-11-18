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
uv run scripts/run.py agy --class gemini-pro --thinking high --brief-file <任務說明檔> [--cwd <工作資料夾>] [--timeout 1800]
```

- 思考程度由腳本寫進模型代號（`gemini-4-hydrogen-xhigh`），不合政策的（禁用的 low、超過上限）直接擋下。
- 任務說明照常寫明級別、思考程度、完成條件與交付位置；要改檔就說只能改哪些檔。腳本會在後面附上 uv、gh 的絕對路徑（agy 的終端機看不到使用者 PATH）。
- 輸出是 JSON 摘要；`ok` 是 false（終端機指令被拒、沒回覆、逾時）就當這次沒完成，看 `problems`。
- 要跑很久的（調研、大範圍閱讀）用背景執行，完成再收。
- 腳本用略過權限模式跑（無頭模式不能核准指令），並在任務說明前面固定加硬性限制：不 commit、不 push、不刪檔、不對外發送、不安裝。所以要 commit 或 push 的，由主控自己做。
- 結果一律由主控驗收（讀它改的檔、跑測試），不要只看它的回覆。
- 記紀錄時 `--channel agy_cli --instance antigravity`。

## 不在 T3 裡也能開 T3 對話（t3_cli 管道）

主控是 Claude Code、Codex 或 Antigravity，沒有 `delegate_task`、`t3_thread_launch` 這類 T3 工具時，用 T3 Code 的本機 CLI `t3 thread`。**不要回答「這裡沒有 T3 工具，沒辦法派」**。適合：要指定 T3 上的帳號實例或模型（例如 `antigravity_kai` 加 `gemini-3.8-flash`）、想在 T3 側邊欄看到那條對話、之後要用 `send` 接著問。

- 在 **PowerShell** 呼叫。`t3.cmd` 在 `%USERPROFILE%\.t3\bin`，PowerShell 的 PATH 有、Git Bash 沒有；Bash 的 `command -v t3` 找不到不代表沒裝。先 `t3 --version` 確認。
- 開對話（`.` 是目前 repo；也可以填 project id 或那個專案裡的路徑）：

  ```
  t3 thread start . "<任務說明>" --provider <實例> --model <模型代號> --title "<標題>" --json --wait
  ```

  - `--provider` 是 profile `dispatch.md` 裡 `instances` 的 key，要和 `--model` 一起給。
  - 任務說明很長時訊息填 `-`，從 stdin 讀：`Get-Content brief.md -Raw | t3 thread start . - --provider ... --model ...`。
  - 要獨立 worktree：加 `--worktree <分支或 commit>`，可再加 `--branch <新分支名>`。
  - `--wait` 等它做完並印回覆；結束碼 1 是執行失敗、2 是對話在等人回答（用 `send` 回它）。不加 `--wait` 就只印對話 id，適合長任務。
- 之後：`t3 thread show <id> --json` 看狀態與最新訊息；`t3 thread send <id> "<訊息>" --wait` 追問；`t3 thread list --json` 列出對話。
- 思考程度：t3 v0.1.10 沒有參數可設。Antigravity 的模型把程度寫進代號（`gemini-4-hydrogen-xhigh`）；Claude 的 effort 設不了，要指定 effort 就改用原生子代理。
- 結案：v0.1.10 沒有 settle 子指令。收完結果後，在回報裡列出對話 id 與標題，請使用者在 T3 結案（主控有 `t3_thread_organize` 時自己 settle）。
- 和其他管道的分工：同供應商、不用指定帳號 → 原生子代理；要 Antigravity 模型、要看思考 token 或在背景跑 → agy_cli；要指定 T3 的帳號實例、要在 T3 看到 → t3_cli；主控本身在 T3 裡 → delegate_task。
- 結果一樣由主控驗收。記紀錄時 `--channel t3_cli --instance <實例>`。
- 【待驗證】照上游 `pingdotgg/t3code` 的 `docs/user/outside-agents.md`，Claude Code 可以 `claude mcp add --transport http t3 <環境位址>/mcp` 再 `claude mcp login t3`（Codex 用 `codex mcp add t3 --url ...` 與 `codex mcp login t3`），拿到 `t3_thread_launch`、`t3_thread_wait`、`t3_thread_organize`；在外部 agent 要用 `t3_thread_launch`，`delegate_task` 會回錯。本機還沒實測。

## 收完結果、settle 之前：記一行

一次委派一行。重跑與升級記在同一行，`--class` 寫一開始派的類別，`--final-class` 寫最後過關的類別。

```
uv run scripts/run.py log --task <任務類型> --class <模型類別> --thinking <程度> --verdict <pass|fail|partial|skipped> \
  [--channel native|agy_cli|t3_cli|delegate_task|t3_thread_launch] [--instance <實例>] [--retries N] [--escalations N] [--final-class <類別>] [--control] [--note <一句話>]
```

- `--task`：共用層 `tasks` 的 key（docs、ui-small、readonly、code-small、accounting、risk、orders、design-decision、hard-bug、acceptance-loop、verify）。級別會自動帶出來。
- `--verdict`：驗收結論。`skipped` 是沒有驗收，不算進通過率。
- 一次通過：沒寫 `--first-pass` 時，結論是 pass 而且沒有重跑、沒有升級才算。
- `--instance`：用 delegate_task 時寫 providerInstanceId、用 t3_cli 時寫 `--provider` 的值；原生子代理不用寫。
- `--control`：Sonnet 試行的對照組（中級改派 Opus 的那幾次）。
- `--note`：一句話，不寫專案內容細節、不寫金鑰或 token。
- 時間、專案名稱、規則版本、profile 自動帶；不確定欄位怎麼寫，先加 `--dry-run` 看會寫出什麼。
- 寫在本機 `%LOCALAPPDATA%\omnikit\dispatch\log.jsonl`，不進 repo、不上傳。

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
