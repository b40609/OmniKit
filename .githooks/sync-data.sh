#!/bin/sh
# 從 stdin 讀變動的檔名，只同步有變動的部分（都不經過 skillshare）：
#   data/rules/、data/profiles/、profiles.py：用這台選的 profile 重新接上規則
#     （Claude 的 import 路徑、Codex 的 AGENTS.md、Antigravity 的 GEMINI.md 區塊）
#   data/mcp/：把 MCP server 同步到接上的 agent
#   engine/skills/：同步 skills（Claude 用連結，內容改動本來就會反映；Codex 與 Antigravity 用複製品，要重新複製）
#   data/profiles/：也同步 skills（訪談答案決定裝哪些，例如不評估工具就不裝 omnikit-eval）
#   sync.py、homes.py、t3_acp.py、acp_shim.py：skills、hooks 與 MCP 都重新同步（新找到的設定目錄也一起接上）
#   data/harness/、claude_allow.py、codex_hooks.py、session_nudge.py、claim_check.py、t3_watch.py、home_watch.py、harness_hooks.py：
#     透過 sync.py sync --mcp 依各目錄薄 plugin 實際狀態更新快取版本、權限清單、狀態列與備案 hooks（不會無條件誤刪備案 hooks）
# 只有維護者版會自動同步。同事版不設 git hook；萬一還是跑到這裡，也只提醒、不改任何設定（edition.py）
# linked worktree（例如 .claude/worktrees/ 底下）也不同步：worktree 共用主 repo 的 core.hooksPath，
# 在這裡同步會把 skills 連結與複製品改指向 worktree，worktree 清掉後就斷了。合進 main 後由主 checkout 同步。
changed=$(cat)
uv=$(command -v uv || echo "$LOCALAPPDATA/Programs/uv/uv.exe")
# 會觸發下面任何一種同步的檔案
syncable='^(data/(rules|profiles|mcp|harness)/|engine/(skills/|scripts/))'

# git-dir 跟 git-common-dir 不同就是 linked worktree；兩個都換成實際路徑再比，避免相對路徑或斜線寫法不同
git_dir=$(cd "$(git rev-parse --git-dir 2>/dev/null)" 2>/dev/null && pwd -P)
common_dir=$(cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P)

# 狀態檔改放 ~/.omnikit（statedir.py）：判斷版本之前，先把舊位置（%LOCALAPPDATA%\omnikit 與封裝的 app 轉存的副本）
# 合併過來，不然 edition.json 還在舊位置，會誤判成同事版而不同步。只在主 checkout、而且有要同步的檔案時做
if [ "$git_dir" = "$common_dir" ] && printf '%s\n' "$changed" | grep -qE "$syncable"; then
  moved=$("$uv" run --quiet engine/scripts/statedir.py migrate --quiet 2>/dev/null | tr -d '\r')
  [ -n "$moved" ] && printf '%s\n' "$moved" | sed 's/^/OmniKit：/'
fi

# Windows 的 Python 印出來是 CRLF，比對前拿掉 \r；判斷失敗就當成同事版，不自動套用
edition=$("$uv" run --quiet engine/scripts/edition.py --show 2>/dev/null | tr -d '\r')
if [ "$edition" != "maintainer" ]; then
  if printf '%s\n' "$changed" | grep -qE "$syncable"; then
    echo "OmniKit：這台不是維護者版，這次的更新沒有自動套用；要套用就先跑 install.ps1 -WhatIf 預覽，再跑 install.ps1"
  fi
  exit 0
fi

if [ -n "$git_dir" ] && [ -n "$common_dir" ] && [ "$git_dir" != "$common_dir" ]; then
  if printf '%s\n' "$changed" | grep -qE "$syncable"; then
    echo "OmniKit：在 worktree 裡，不同步；合進 main 後主 checkout 會同步"
  fi
  exit 0
fi

# 把腳本的每一行輸出加上 OmniKit 前綴；失敗時轉到 stderr，再補一行說明
run() {
  label=$1
  shift
  if out=$("$uv" run --quiet "$@" 2>&1); then
    [ -n "$out" ] && printf '%s\n' "$out" | sed 's/^/OmniKit：/'
  else
    [ -n "$out" ] && printf '%s\n' "$out" | sed 's/^/OmniKit：/' >&2
    echo "OmniKit：$label 沒有完成，原因見上一行" >&2
  fi
  return 0
}

if printf '%s\n' "$changed" | grep -qE '^(data/rules/|data/profiles/|engine/scripts/profiles\.py$)'; then
  run "規則同步" engine/scripts/profiles.py
fi

skills=0
mcp=0
printf '%s\n' "$changed" | grep -qE '^(engine/skills/|data/profiles/|engine/scripts/(sync|profiles|homes|t3_acp|acp_shim)\.py$)' && skills=1
printf '%s\n' "$changed" | grep -qE '^(data/(mcp|harness)/|engine/scripts/(sync|homes|t3_acp|acp_shim|claude_allow|codex_hooks|session_nudge|claim_check|t3_watch|home_watch|harness_hooks)\.py$)' && mcp=1
if [ $skills = 1 ] && [ $mcp = 1 ]; then
  run "skills、hooks 與 MCP 同步" engine/scripts/sync.py sync
elif [ $skills = 1 ]; then
  run "skills 同步" engine/scripts/sync.py sync --skills
elif [ $mcp = 1 ]; then
  run "hooks、權限與 MCP 同步" engine/scripts/sync.py sync --mcp
fi
