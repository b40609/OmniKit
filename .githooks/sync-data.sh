#!/bin/sh
# 從 stdin 讀變動的檔名，只同步有變動的部分：
#   data/rules/：同步給 Codex（Codex 不支援 import，讀的是 skillshare 複製的副本）
#   data/mcp/：同步兩邊的 MCP 設定
#   data/harness/：把權限規則補進 Claude Code 的使用者設定
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

if printf '%s\n' "$changed" | grep -q '^data/harness/'; then
  uv=$(command -v uv || echo "$LOCALAPPDATA/Programs/uv/uv.exe")
  if "$uv" run --quiet engine/scripts/claude_allow.py >/dev/null 2>&1; then
    echo "OmniKit：已同步 Claude 的權限規則"
  else
    echo "OmniKit：claude_allow.py 失敗，Claude 的權限規則可能還是舊的" >&2
  fi
fi
