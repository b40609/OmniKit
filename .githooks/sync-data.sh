#!/bin/sh
# 從 stdin 讀變動的檔名，只同步有變動的部分：
#   data/rules/：同步給 Codex（Codex 不支援 import，讀的是 skillshare 複製的副本）
#   data/mcp/：同步兩邊的 MCP 設定
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
