---
name: omnikit-dispatch
description: 派子任務或開子對話時，照 OmniKit 分派政策選管道、模型與思考程度，並在收完結果、settle 之前記一行委派紀錄；也能看 Sonnet 試行的比較與本週 Claude 用量。要派子代理、delegate_task、開子對話、記委派紀錄、看「分派統計」「委派紀錄」「Sonnet 試行」「本週 Claude 用量」時使用。Picks the model and effort for a sub-task from the OmniKit dispatch policy and logs each delegation.
---

# 子任務分派與委派紀錄

分派規則已經在你載入的規則裡：共用層 `data/rules/dispatch.md`，加上 profile 的 `dispatch.md`（自己的供應商實例；沒有就只用原生子代理）。這個 skill 只負責跑腳本。下面的指令路徑都相對於這個 skill 的資料夾；`uv` 不在 PATH 時，用 `%LOCALAPPDATA%\Programs\uv\uv.exe`。

## 派之前

```
uv run scripts/run.py show
```

印出套上你的實例之後，每一級依序可以用的選項，開頭附本週 Claude 用量。由上往下挑第一個「有實例、額度沒用完、條件成立」的。用量是「未知」時不要假設已達 80%。開子對話或派子代理時，在任務說明寫明級別與思考程度（Claude 寫 effort，Gemini／Antigravity 寫 thinking_level）。

## 收完結果、settle 之前：記一行

一次委派一行。重跑與升級記在同一行，`--class` 寫一開始派的類別，`--final-class` 寫最後過關的類別。

```
uv run scripts/run.py log --task <任務類型> --class <模型類別> --thinking <程度> --verdict <pass|fail|partial|skipped> \
  [--channel native|delegate_task|t3_thread_launch] [--instance <實例>] [--retries N] [--escalations N] [--final-class <類別>] [--control] [--note <一句話>]
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
