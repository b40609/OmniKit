---
name: omnikit-dispatch
description: 派子任務或開子對話時，照 OmniKit 分派政策選管道、模型與思考程度，並在收完結果、settle 之前記一行委派紀錄；也能看 Sonnet 試行的比較與本週 Claude 用量。要派子代理、delegate_task、開子對話、記委派紀錄、看「分派統計」「委派紀錄」「Sonnet 試行」「本週 Claude 用量」時使用。Picks the model and effort for a sub-task from the OmniKit dispatch policy and logs each delegation.
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

## 收完結果、settle 之前：記一行

一次委派一行。重跑與升級記在同一行，`--class` 寫一開始派的類別，`--final-class` 寫最後過關的類別。

```
uv run scripts/run.py log --task <任務類型> --class <模型類別> --thinking <程度> --verdict <pass|fail|partial|skipped> \
  [--channel native|agy_cli|delegate_task|t3_thread_launch] [--instance <實例>] [--retries N] [--escalations N] [--final-class <類別>] [--control] [--note <一句話>]
```

- `--task`：共用層 `tasks` 的 key（docs、ui-small、readonly、code-small、accounting、risk、orders、design-decision、hard-bug、acceptance-loop、verify）。級別會自動帶出來。
- `--verdict`：驗收結論。`skipped` 是沒有驗收，不算進通過率。
- 一次通過：沒寫 `--first-pass` 時，結論是 pass 而且沒有重跑、沒有升級才算。
- `--instance`：用 delegate_task 時寫 providerInstanceId；原生子代理不用寫。
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
