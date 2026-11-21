---
name: omnikit-capabilities
description: 要回答「做不到」「沒有工具」「這裡沒辦法」「請你手動做」「還不能」之前先用：清點這台電腦上 agent 能用的 CLI（含 Git Bash 找不到、只有 PowerShell 找得到的）、各 agent 登記的 MCP server 與本機 MCP 端點，列出最省事的做法，再對照 --help 與最新官方文件。使用者問「你能不能 X」「有沒有辦法派給 Y」「有沒有工具做 Z」，或你正要把某一步交給使用者手動做時也用。Inventories local CLIs, MCP servers and endpoints before an agent claims it cannot do something.
---

# 能力清點：說做不到之前

「做不到、沒有工具、要你手動做、還不能」也是要查證的主張，語氣再確定也一樣（安全底線的「說做不到之前」）。這個 skill 是那份檢查清單的做法。下面的指令路徑都相對於這個 skill 的資料夾；`uv` 不在 PATH 時，用 `%LOCALAPPDATA%\Programs\uv\uv.exe`。

## 1. 清點這台有什麼

```
uv run scripts/run.py                 指令、各 agent 的 MCP、本機端點、建議
uv run scripts/run.py --cmd <名稱>    多找特定指令（可重複），例如 --cmd ffmpeg
uv run scripts/run.py --versions      加印每個指令的版本
```

它會標出容易誤判的情況：Git Bash 只會自動補 `.exe`，所以只有 `.cmd` 的指令（例如 `t3.cmd`）在 Bash 打 `t3` 找不到；在 PowerShell 跑或打完整檔名就好。還有裝好之後才加進 PATH、舊的行程看不到的指令，以及開著但還沒接進某個 agent 的本機 MCP 端點。它只看檔案、PATH 與本機連線，不印金鑰。

## 2. 問工具自己

對要用的指令跑 `--help`，子指令也跑（例如 `t3 thread start --help`）。清單沒列到的指令，用 `--cmd` 再找，或在 PowerShell 跑 `Get-Command <名稱>`、在 Bash 跑 `command -v <名稱>`，兩邊都找過才算找不到。

## 3. 查最新的官方文件或原始碼

新工具、新功能常比模型的訓練資料新，以官方文件為準，不以記憶為準：該工具的官方文件、repo 的 `docs/`、CHANGELOG、release notes，必要時讀原始碼（GitHub 用 `gh api` 或 `gh search code`）。同一件事常有 CLI、MCP、API 好幾種接法；自己的工具清單裡沒有，不代表其他接法也沒有。

## 看到 `t3 (ECONNREFUSED)`：T3 當時在重啟，不是沒裝

`/mcp` 或啟動訊息顯示 `t3 (ECONNREFUSED)`、`failed`，或工具清單少了 `mcp__t3__*`，多半是這段對話開的時候 T3 Code 正在重啟、更新或沒開（t3 MCP 跑在 T3 桌面程式裡，`http://127.0.0.1:3773/mcp`）。user scope 的 MCP server agent 不能自己重撥（`reconnect_session_connector` 會回 not a connector），一斷整段對話都沒有 T3 工具。處理順序：

1. 請使用者在這段對話打 `/mcp`，選 t3 按 Reconnect（這是非他不可的一步，一次講清楚）。
2. 同時改走 `t3 thread` CLI（`t3_cli` 管道；PowerShell 打 `t3`，Git Bash 打 `t3.cmd`）。CLI 每次都重新連線，T3 起來了就能用。不要回答「派不了」。

OmniKit 的 SessionStart hook（`engine/scripts/t3_watch.py`）會在開對話時檢查埠：連不上就把 T3 叫起來，並在 context 留一段同樣的提醒。

## 4. 回答

- 有路就直接做。要使用者動手的只有非他不可的步驟（帳號登入核准、付款、需要他拍板的決定，以及安全底線列的項目），而且一次講清楚。
- 先寫最省事、現在就能做的路（附指令），限制與沒實測的部分放後面。能做但還沒實測，寫「可以這樣做（未實測）」，不要寫成「還不能」。
- 查完還是做不到，寫明查了什麼（清點結果、跑過的 `--help`、文件網址）、卡在哪一步、還有什麼替代做法。
