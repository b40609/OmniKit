# T3 MCP 斷線防護與 T3 更新選項（2026-11-21）

查證環境：Claude Code 2.1.329、T3 Code 0.1.12-nightly.20261120.4994（Windows，`%LOCALAPPDATA%\Programs\t3code`）。

## 發生什麼事

- t3 MCP 是 user scope 的 http server `http://127.0.0.1:3773/mcp`，伺服器跑在 T3 桌面程式裡（`~/.t3/userdata/server-runtime.json` 記 pid、port、startedAt）。
- 2026-11-20 22:15（台北）T3 下載 nightly 更新、寫入 `%LOCALAPPDATA%\t3code-updater\installer.exe`，22:16 重啟。這段期間開的 Claude Code 對話回報 `t3 (ECONNREFUSED)`，之後整段對話都沒有 T3 工具。
- user-config 的 MCP server agent 不能自己重撥（`reconnect_session_connector` 回「t3 is not a connector」），只能使用者在該對話打 `/mcp` 按 Reconnect。`t3` CLI 每次重新連線，不受影響。

## 做了什麼

- `engine/scripts/t3_watch.py`：SessionStart hook。埠連得上就不輸出；連不上就看 T3 有沒有在跑、是不是正在更新，都不是才在背景最小化啟動，最多等 20 秒；只要一開始連不上，就用 `hookSpecificOutput.additionalContext` 提醒 agent 請使用者 `/mcp` 重連、先改用 `t3 thread` CLI。整支壓在 25 秒內（hook 設 30 秒），錯誤一律安靜結束。
- Claude Code：`claude_allow.HOOKS` 註冊進每個 Claude 設定目錄（`~/.claude`、`~/.claude-kai`、`~/.claude-retis`），install.ps1、`agents.py sync` 都會帶上，重裝不會被蓋掉。
- Codex：codex-cli 0.168.0 的 hook 有 SessionStart（claude-mem 的 codex-hooks.json 就用了 `session_start`），`codex_hooks.py` 改成每支 hook 各自的事件，寫成 `[[hooks.SessionStart]]`。Codex 要使用者在 `/hooks`（桌面版：設定的 Hooks）信任後才會執行。Codex 吃不吃 `hookSpecificOutput.additionalContext` 格式【待驗證：沒在 Codex 實跑】；Codex 有沒有對應 `/mcp` Reconnect 的重連方式也【待驗證】，斷線時至少 t3 CLI 可用。
- skills：`omnikit-capabilities`、`omnikit-dispatch` 與 `dispatch-policy.md` 的 `t3_thread_launch` 寫明 ECONNREFUSED 的意思與處理順序。

## 等 Ryan 決定：T3 的更新要不要改

從 T3 0.1.12-nightly.20261120.4994 的 `app.asar`、`server.asar` 原始碼讀到（一手證據是安裝目錄裡的程式碼，不是官方文件）：

- T3 本來就**不會**自己安裝：桌面端在設定 updater 時呼叫 `setAutoDownload(false)` 與 `setAutoInstallOnAppQuit(false)`；`installUpdate` 只有介面上的動作會呼叫（「Restart to update」按鈕、確認對話框、「Update everything」）。`desktop.trace.ndjson` 有 `desktop.ipc.updates.install` 紀錄，所以 22:15 那次是從介面觸發的（推論：程式碼裡沒有找到自動呼叫的路徑）。
- 沒有「關閉程式時才安裝」的設定：`autoInstallOnAppQuit` 寫死成 false，`client-settings.json`、`desktop-settings.json` 也沒有更新相關的鍵。
- 能關掉更新的開關有兩個，都會連 nightly 修正一起擋掉：
  1. 環境變數 `T3CODE_DISABLE_AUTO_UPDATE=1`（使用者層級即可）：介面顯示「Automatic updates are disabled by the T3CODE_DISABLE_AUTO_UPDATE setting」，要更新只能自己去 GitHub releases 下載安裝。
  2. 管理政策 `HKLM\SOFTWARE\Policies\T3Tools\T3Code`（`limits.updates.mode` 設 `off`，或 `allowNightly` 設 false）：要系統管理員權限，屬於改系統設定。

建議：**不改設定**。Ryan 依賴 nightly 修正，而安裝本來就要按按鈕。只要在按「Restart to update」之後，對還開著的 Claude Code／Codex 對話打一次 `/mcp` 重連 t3（或開新對話；新對話有 `t3_watch.py` 提醒）。這兩個開關都沒有動。

## 測試

`uv run engine/scripts/t3_watch.py --selftest`（埠開著、埠關著、runtime 檔不存在等 11 項全過）、`claude_allow.py`、`codex_hooks.py`、`agents.py`、`doctor.py`、`home_watch.py` 的 selftest 全過；端到端用設定檔裡的實際 hook 指令跑：3773 開著時不輸出，假的 home 指向關閉的埠時輸出 additionalContext，約 1.2 秒。
