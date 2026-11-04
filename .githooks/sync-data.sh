#!/bin/sh
# 從 stdin 讀變動的檔名，只同步有變動的部分：
#   data/rules/：同步給 Codex（Codex 不支援 import，讀的是 skillshare 複製的副本）
#   data/mcp/：同步兩邊的 MCP 設定
#   data/harness/、claude_allow.py、session_nudge.py：把權限規則與開新對話提醒補進 Claude Code 的使用者設定
#   codex_hooks.py、claude_allow.py、session_nudge.py：把開新對話提醒補進 Codex 的 config.toml
#   engine/skills/：同步 skills（內容改動本來就會反映，新增或刪除 skill 才需要）
ss="$LOCALAPPDATA/Programs/skillshare/skillshare.exe"
changed=$(cat)

if printf '%s\n' "$changed" | grep -q '^data/rules/'; then
  if "$ss" sync extras >/dev/null 2>&1; then
    echo "OmniKit：已把規則同步給 Codex"
  else
    echo "OmniKit：skillshare sync extras 失敗，Codex 的規則可能還是舊的" >&2
  fi
fi

if printf '%s\n' "$changed" | grep -q '^data/mcp/'; then
  if "$ss" sync mcp --no-tui >/dev/null 2>&1; then
    echo "OmniKit：已把 MCP 設定同步給 Claude Code 與 Codex"
  else
    echo "OmniKit：skillshare sync mcp 失敗，兩邊的 MCP 設定可能還是舊的" >&2
  fi
fi

if printf '%s\n' "$changed" | grep -qE '^(data/harness/|engine/scripts/(claude_allow|session_nudge)\.py$)'; then
  uv=$(command -v uv || echo "$LOCALAPPDATA/Programs/uv/uv.exe")
  if "$uv" run --quiet engine/scripts/claude_allow.py >/dev/null 2>&1; then
    echo "OmniKit：已同步 Claude 的權限規則與開新對話提醒"
  else
    echo "OmniKit：claude_allow.py 失敗，Claude 的權限規則與開新對話提醒可能還是舊的" >&2
  fi
fi

if printf '%s\n' "$changed" | grep -qE '^engine/scripts/(codex_hooks|claude_allow|session_nudge)\.py$'; then
  uv=$(command -v uv || echo "$LOCALAPPDATA/Programs/uv/uv.exe")
  if out=$("$uv" run --quiet engine/scripts/codex_hooks.py 2>&1); then
    # 只有新註冊或改了指令才需要使用者到 Codex 重新信任，這時把提示轉出來
    case "$out" in 已註冊*) echo "OmniKit：$out" ;; esac
  else
    echo "OmniKit：codex_hooks.py 失敗，Codex 的開新對話提醒可能還是舊的" >&2
  fi
fi

if printf '%s\n' "$changed" | grep -q '^engine/skills/'; then
  if "$ss" sync >/dev/null 2>&1; then
    echo "OmniKit：已把 skills 同步給 Claude Code 與 Codex"
  else
    echo "OmniKit：skillshare sync 失敗，兩邊的 skills 可能還是舊的" >&2
  fi
fi
