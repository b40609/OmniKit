# S1–S6 無帳本同步架構動工前實測報告

- **實測日期**：2026-11-25
- **依據規格**：Fable 5.2 Stage 2《獨立設計與 Option 6 正面對決》第 8–10 節（S1–S6 動工前實測與改判條件）
- **測試環境**：Windows 11｜PowerShell 7 / 5.1 / Git Bash｜Claude Code CLI｜Codex CLI｜T3 Code 內建 Antigravity `agy.exe` `1.5.16`

---

## 1. 六項實測總表與改判對照

| 編號 | 實測項目 | 實測結果 | 關鍵一手證據與輸出摘要 | 對架構的定案影響（對照 Fable 第 10 節） |
|---|---|---|---|---|
| **S1** | Claude Code 在 3 個設定目錄（`~/.claude`、`~/.claude-kai`、`~/.claude-retis`）讀取 `skills/<junction>/SKILL.md` | **通過** | 3 個目錄分別掛載 `skills/omnikit-s1-probe` Directory Junction 後，開啟 `Skill` 工具執行單輪 `claude -p --setting-sources user`，3 個目錄皆 `rc=0` 並準確回傳 `S1_CANARY_9842`；`os.rmdir` 移除連結後目標完好。 | Claude skills 維持 **Directory Junction**（零快取副本、不帶 plugin 命名空間前綴）。 |
| **S2** | Codex 讀取 skills junction 路徑、`codex mcp` CLI 行為、Windows hooks 現況 | **通過（路徑修正為 `<CODEX_HOME>/skills`）** | 1. 透過本機 Mock Responses 伺服器攔截 `codex exec` 請求：設 `CODEX_HOME` 時，`~/.agents/skills/<junc>` 為 `False`，**`$CODEX_HOME/skills/<junc>` 為 `True`**（成功注入 `S2_CODEXDIR_8844`）。<br>2. `codex mcp add / list --json / remove` 全部 `rc=0`，保留頂層註解、`model` 與使用者既有 `[mcp_servers.user_keep]`；同名重跑 `add` 直接冪等更新。<br>3. `codex features list` 顯示 `hooks: stable (true)`、`plugin_hooks: removed (false)`。 | Codex skills 改掛載於每個 Codex 設定目錄的 **`<codex_home>/skills/<junction>`**（預設 `~/.codex/skills`），並清掉舊版 `~/.agents/skills` 遺留項；Codex MCP 採用 **`codex mcp` CLI**。 |
| **S3** | Antigravity 發現 plugin／skills junction、`agy acp` 執行 `hooks.json` 與 `PreToolUse` `deny` 硬攔截、`cmd /c` 引號與 Python 解析 | **Junction 不被 `agy acp` 載入；實體薄目錄與 `skills.json` 100% 通過** | 1. **Junction 限制**：`agy acp`（Go runtime）下，`~/.gemini/config/skills/<junction>`（`AGY skill junction loaded: False`）與 `<inst>/config/plugins/<junction>`（`plug_junc events: []`）皆不被載入。<br>2. **零副本原生替代實測 100% 通過**：<br>   - `~/.gemini/config/skills.json` 寫入 POSIX 磁碟機路徑 `"/C:/..."` 後，`agy acp` 原生載入實體目錄 skills（`has_slashc_9933: true`），且 T3 `copyAntigravityUserConfigFiles` 自動將 `config/skills.json` 同步至全部 8 個 T3 實例。<br>   - `<inst>/config/plugins/omnikit/` 建立**實體薄目錄**（僅含 `plugin.json`、`hooks.json`、`mcp_config.json` 三個純宣告檔）後，`agy acp` 完整觸發 `SessionStart` 與 `PreToolUse` 硬攔截：`{"denied": true, "reason": "tool call denied by pre-tool hook: DENIED_BY_REAL_PLUGIN_DIR"}`，且不觸碰 `config/hooks.json` 與 `config/mcp_config.json`，完整保住 T3 `isAntigravityTextGenerationAvailable == true`。<br>3. **Windows `cmd /c` 引號陷阱**：`cmd /c "C:/.../exe" "C:/dir with space/script.py"` 會被 `cmd.exe` 剝除首尾雙引號報 `rc=1`；加上 `call ` 前綴（`cmd /c call "..." "..."`）為 `rc=0`。<br>4. **Antigravity Hook 輸出契約**：一手核對 `docs/hooks.md` 並實測確認，`PreToolUse` 攔截須回 `{"decision": "deny", "reason": "..."}`，`Stop` 續跑須回 `{"decision": "continue", "reason": "..."}`（與 Claude 格式不同，`harness_hooks.py` 須依方言輸出）。 | 1. Antigravity skills 透過 `~/.gemini/config/skills.json` 參照實體目錄（零複製、零 Junction、T3 自動同步至全實例）。<br>2. Antigravity hooks 與 MCP 於 `~/.gemini` 及每個 T3 實例放置 `config/plugins/omnikit/` 3 檔薄宣告目錄（移除時逐檔 `unlink` 後 `os.rmdir`，維持零 `rmtree`）。<br>3. Windows hook 指令一律加 `call ` 前綴；更新 `harness_hooks.py` 支援 Antigravity 原生 `PreToolUse` / `Stop` 回傳格式。 |
| **S4** | Junction 刪除安全性（Python `os.rmdir`、PowerShell 7/5.1、Git Bash 有無尾斜線） | **抓出 Git Bash 尾斜線穿透刪除風險** | • `os.rmdir(<junc>)`、`pwsh` / `powershell` `Remove-Item -Recurse -Force <junc>`、`Git Bash rm -rf <junc>`（無尾斜線）：全部 `junc=False, target=True, canary=True, nested=True`（安全）。<br>• **`Git Bash rm -rf <junc>/`（帶尾斜線）**：**`junc=True, target=True, canary=False, nested=False`**（穿過 junction 靜默刪光目標目錄內容！）。 | 依 Fable 第 10 節改判條件：**`~/.omnikit/current` 乾淨本地 clone 升為必做預設**（所有連結與路徑預設指向 `~/.omnikit/current`，隔離保護開發工作區未提交變更；另提供 `--dev` 供維護者顯式切換），且同步器原始碼嚴禁 `rmtree`（寫入自動測試）。 |
| **S5** | Antigravity 雙檔（`AGENTS.md` + `GEMINI.md`）同時載入與 `> 24,000 bytes` 截斷表現 | **100% 證實雙檔載入與行界靜默截斷** | 1. 真實 T3 子對話 `mcp:023236b9-09ee-4699-a962-92679d47b864` 實測回報同時載入 `AGENTS.md`（安全底線）與 `GEMINI.md`（個人規則 ryan）。<br>2. 寫入 `25,540 bytes` 的 `AGENTS.md`（頭 `S5_HEAD_1122`、尾 `S5_TAIL_9988`）搭配 `GEMINI.md`（`S5_GEMINI_3344`）於 `agy acp` 實測，模型回報：`{"has_head_1122": true, "has_tail_9988": false, "has_gemini_3344": true}`，超過 `24,000 bytes` 檔尾確實被無聲截斷。 | 維持 Step 1.3 已上線之 `AGENTS.md`（共用）+ `GEMINI.md`（個人）雙檔拆分與 `<= 24,000 bytes` / `<= 20,000 tokens` 硬門禁。 |
| **S6** | `claude plugin install` 在 3 個 `CLAUDE_CONFIG_DIR` 非互動安裝薄 plugin 與 hook 觸發 | **通過** | 3 個隔離 `CLAUDE_CONFIG_DIR` 執行 `claude plugin install omnikit --marketplace <dir> -y --json` 全數 `rc=0`（各約 `0.75s`，`Status: enabled`，直接 `Read from` 本地 marketplace 路徑）；於 `~/.claude` 實跑單輪 `claude -p` 成功觸發薄 plugin 的 `SessionStart` hook（`{"cfg": ".claude", "event": "SessionStart"}`），卸載清理 `rc=0`。 | Claude 的 hooks 與 MCP 採用**本地 marketplace 薄 plugin** 非互動安裝至每個明確列舉的 Claude 設定目錄。 |

---

## 2. 原始實測指令與關鍵輸出節錄

### 2.1 S4 五種刪除方式對照輸出
```text
python os.rmdir(<junc>):                              rc=0 junc=False target=True canary=True  nested=True
pwsh Remove-Item -Recurse -Force <junc>:              rc=0 junc=False target=True canary=True  nested=True
powershell 5.1 Remove-Item -Recurse -Force <junc>:    rc=0 junc=False target=True canary=True  nested=True
Git Bash rm -rf <junc> (no trailing slash):           rc=0 junc=False target=True canary=True  nested=True
Git Bash rm -rf <junc>/ (WITH trailing slash):        rc=0 junc=True  target=True canary=False nested=False
```

### 2.2 S1 與 S6（Claude Code 3 目錄 Skills Junction 與薄 Plugin）
```text
[S1] .claude:       rc=0 found=True stdout='S1_CANARY_9842'
[S1] .claude-kai:   rc=0 found=True stdout='S1_CANARY_9842'
[S1] .claude-retis: rc=0 found=True stdout='S1_CANARY_9842'

[S6] cfg_1..cfg_3:  install_rc=0 {"command":"install","outcome":"ok","plugin":"omnikit@omnikit-local","scope":"user"}
[S6] live ~/.claude SessionStart hook hits=['{"cfg": ".claude", "event": "SessionStart", "tool": null}']
```

### 2.3 S2（Codex Skills Junction 與 `codex mcp` CLI）
```text
[S2] codex mock exec: rc=0 reqs=1 ~/.agents/skills/<junc>=False $CODEX_HOME/skills/<junc>=True
[S2] codex mcp: add1=0 add2_dup=0 list=0 rm=0 user_mcp_preserved=True top_comment_preserved=True
[S2] codex features: hooks = stable (true), plugin_hooks = removed (false)
```

### 2.4 S3 與 S5（Antigravity `agy acp` 1.5.16 實測）
```text
[S3 cmd /c quoting]
  WITHOUT call (spaced path): rc=1 err='The filename, directory name, or volume label syntax is incorrect.'
  WITH    call (spaced path): rc=0 out='OK_PY: C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe'

[S3 & S5 agy acp 25,540-byte AGENTS.md + GEMINI.md]
  {"denied":true,"deny_reason":"tool call denied by pre-tool hook: HARD_DENIED_BY_CONFIG_HOOKS_JSON","has_head_1122":true,"has_tail_9988":false,"has_gemini_3344":true}

[S3 agy acp thin real plugin dir + skills.json "/C:/..."]
  {"denied": true, "reason": "tool call denied by pre-tool hook: DENIED_BY_REAL_PLUGIN_DIR", "has_hl_7722": true, "has_slashc_9933": true}
  ev_realplug: ['{"event": "SessionStart", "tool": null}', '{"event": "PreToolUse", "tool": "run_command"}']
```
