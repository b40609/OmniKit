# OmniKit 規則：子任務分派（共用層）

所有人都套用。這裡只有原則；完整政策（任務類型、級別、模型、思考程度、管道、升級）在 `data/rules/dispatch-policy.md`，要派的時候用 omnikit-dispatch skill 的 `run.py show` 讀，它會印出套上你的實例之後每一級可用的選項。你有哪些帳號寫在自己 profile 的 `dispatch.md`；沒有那份就只用目前這個 agent 的原生子代理。

- **什麼時候派**：省稀缺的額度、平行、把很長的輸出隔在主對話外、要一個沒看過過程的審查者。派出去不會讓答案更好；範圍清楚的小修改留在主線做。
- **誰來派**：結果要回到同一個決定的（前置苦工、調研、審查），由主控派。彼此獨立的工作包，各開一條對話。
- **寫的與審的不同家**：有第二家模型時，重要的結果換一家唯讀審查。
- **看不看得到過程是個人偏好**：派給 Antigravity 的子任務要開在 T3 看得到的對話（visible），還是走 agy 無頭模式只看結果（headless），照自己 profile `dispatch.md` 的 `visibility`；沒寫用政策的預設，`run.py show` 會印出這次該用的管道。
- **派之前**：先跑 `run.py show` 選級別、模型與思考程度，寫進任務說明；不要沿用主線的設定，也不要靠預設值。
- **派之後**：結果由主控驗收（讀它改的檔、跑測試），不只看它的回覆。收完、settle 之前用 `run.py log` 記一行；驗收不過照 `show` 印的順序升級，升級也記。
- **不在 T3 裡也能派給 T3**：主控是 Claude Code、Codex 或 Antigravity 時，用 T3 Code 的本機 CLI `t3 thread start`（PowerShell 打 `t3`；Git Bash 要打 `t3.cmd`，Bash 不會自動補 `.cmd`）開 T3 對話、指定帳號實例與模型；沒有 `delegate_task` 這類 T3 工具不代表派不了。接了 T3 的 MCP（`t3_thread_launch`）優先用它，能設思考程度、能結案；沒接才用 CLI。用法在政策的 `t3_thread_launch` 與 `t3_cli` 管道。
- 專案規則對模型分工或驗收另有規定時，照專案規則。
