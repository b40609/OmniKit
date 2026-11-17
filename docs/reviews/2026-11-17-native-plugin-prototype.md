# 原生 plugin 原型：能不能取代自製的安裝與移除

日期：2026-11-17。這台：Windows 11、Claude Code 2.1.326、Codex 0.168.0。原型放在暫存資料夾，裝一次、測、移除一次，沒有進 repo。

## 結論

**能取代大部分，但不是全部。** skill、MCP、提醒 hook 都能用 plugin 帶，規則可以用 SessionStart hook 注入，兩家都實測通過，移除也乾淨。取代不了的是：下載 uv、gh、gitleaks，維護者的 git hook，Claude Code 的權限規則，以及 profile 的搬移。這幾項要留一支小腳本，或寫進 `docs/starter.md` 讓 agent 照做。

建議：凍結結束（2026-11-29）後，在現有的 marketplace（`omnikit-b40609`）加一個 `omnikit` plugin，取代 `agents.py` 裡接 skill、MCP、hook 的部分；`install.ps1` 縮成只做 plugin 帶不了的那幾項。拿掉舊程式前先問。

## 測了什麼

原型內容：6 個 skill（`omnikit-weekly` 已停用，不放）、Stop hook（`session_nudge.py`）、SessionStart hook（印出規則檔）、一個 MCP server。兩家各一份 manifest（`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`），共用同一個資料夾。

| 項目 | Claude Code | Codex |
|---|---|---|
| 從本機資料夾加 marketplace、安裝 | 通過，約 3 秒 | 通過 |
| skill 載入 | 通過，名稱變成 `omnikit:omnikit-ask` 這種 | 通過，同樣有前綴 |
| 規則（SessionStart hook 印到 context） | 通過：問「原型標記是什麼」答出規則裡的標記 | 通過，但 hook 要先信任（見下） |
| Stop hook | 有執行，exit 0 | 沒測 |
| MCP | 通過；跟使用者設定**完全相同**的 server 會被略過，改一個參數就出現 `plugin:omnikit:proto_devtools` | 對話紀錄裡有它 |
| 移除 plugin 與 marketplace | 通過；設定檔內容不變（只有鍵的順序變了） | 通過；`config.toml` 完全不變 |
| 移除後的殘留 | 快取裡留一個版本資料夾，標了 `.orphaned_at`，會不會自動清掉待驗證 | 快取裡留一個空資料夾 `omnikit-proto` |
| 防毒 | 這次沒有被擋的錯誤 | 同左 |

`claude plugin details` 估計這 6 個 skill 每段對話固定多約 1,273 tokens，這批 skill 現在用 junction 裝，本來就在付這筆。

## 踩到的事（之後實作要照做）

1. **Codex 的 plugin hook 要先信任。** 沒信任時 hook 不執行，也沒有錯誤訊息。使用者要在 Codex 裡開 `/hooks` 信任一次；自動化可以加 `--dangerously-bypass-hook-trust`（只對那一次有效）。證據：Codex 原始碼 `codex-rs/hooks/src/engine/plugin_trust.rs`，`codex exec --help` 的說明。
2. **Codex 在 Windows 用 PowerShell 跑 `commandWindows`。** `%PLUGIN_ROOT%` 不會展開，要寫 `$env:PLUGIN_ROOT`。實測：同一個 hook 用 `%PLUGIN_ROOT%` 失敗，改成 `$env:PLUGIN_ROOT` 就成功。
3. **Codex 會給 hook 兩個變數：`PLUGIN_ROOT` 與 `CLAUDE_PLUGIN_ROOT`**，指向 Codex 自己的快取。所以 hook 腳本可以兩家共用，只有 Windows 指令的寫法不同。
4. **本機資料夾的 marketplace，兩家行為不同。** Claude Code 直接讀原始資料夾（改了馬上生效，跟現在的 junction 一樣）；Codex 會複製到快取，改了要重裝。
5. **skill 名稱會多前綴。** 叫用靠的是說明文字，影響不大；但文件裡寫「打 /omnikit-ask」的地方要改。舊的 junction 與 plugin 同時存在時，兩份都會列出來，換的時候要先拿掉 junction。
6. **規則改用 hook 注入的取捨**：每個 profile 的規則不同，hook 腳本要在執行時讀這台選的 profile（`profiles.py` 已經知道放哪裡）。hook 注入的內容跟 `CLAUDE.md` 的權重一不一樣，待驗證。

## 還沒測的

- Antigravity：官方文件寫 plugin 能包 skill、MCP、子代理、規則、hook，可以從 GitHub 安裝（`agy plugin install`），這次沒試。
- 從 GitHub 上的 marketplace 安裝（這次只用本機資料夾）。
- 同事那種沒有 uv 的電腦：hook 用 `uv run`，沒有 uv 就會失敗。
- Claude Code 的 plugin 能不能帶權限規則（`claude_allow.py` 在做的事）。

## 順帶發現

`claude plugin eval` 可以對一個 plugin 跑測試題，**而且會自動加一組「沒有這個 plugin」的對照**。問法庫 72 條目前沒有任何「有它與沒它」的比較，這可以補上 agent 能自己做的那一半（使用者實測仍然要做，它量的是使用者覺得有沒有比較好）。

## 原型的 manifest（給之後實作參考）

Codex 的 hook（Windows 要用 PowerShell 語法）：

```json
{ "hooks": { "SessionStart": [ { "hooks": [ { "type": "command",
  "command": "uv run --quiet --script \"$PLUGIN_ROOT/engine/scripts/rules_context.py\"",
  "commandWindows": "uv run --quiet --script \"$env:PLUGIN_ROOT\\engine\\scripts\\rules_context.py\"",
  "timeout": 10 } ] } ] } }
```

Claude Code 的 hook 用 `${CLAUDE_PLUGIN_ROOT}`，`command` 一個欄位就夠。Codex 的 `.codex-plugin/plugin.json` 用 `"skills": "./skills/"`、`"mcpServers": "./.mcp.json"`、`"hooks": "./hooks/codex-hooks.json"` 指過去。
