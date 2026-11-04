#!/bin/sh
# 從 stdin 讀變動的檔名，只同步有變動的部分（都不經過 skillshare）：
#   data/rules/、data/profiles/、profiles.py：用這台選的 profile 重新接上規則
#     （Claude 的 import 路徑、Codex 的 AGENTS.md、Antigravity 的 GEMINI.md 區塊）
#   data/mcp/：把 MCP server 同步到接上的 agent
#   engine/skills/：同步 skills（Claude 用連結，內容改動本來就會反映；Codex 與 Antigravity 用複製品，要重新複製）
#   data/profiles/：也同步 skills（訪談答案決定裝哪些，例如不評估工具就不裝 omnikit-eval）
#   agents.py：skills 與 MCP 都重新同步
#   data/harness/、claude_allow.py、session_nudge.py：把權限規則與開新對話提醒補進 Claude Code 的使用者設定
#   codex_hooks.py、claude_allow.py、session_nudge.py：把開新對話提醒補進 Codex 的 config.toml
changed=$(cat)
uv=$(command -v uv || echo "$LOCALAPPDATA/Programs/uv/uv.exe")

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
}

if printf '%s\n' "$changed" | grep -qE '^(data/rules/|data/profiles/|engine/scripts/profiles\.py$)'; then
  run "規則同步" engine/scripts/profiles.py
fi

skills=0
mcp=0
printf '%s\n' "$changed" | grep -qE '^(engine/skills/|data/profiles/|engine/scripts/(agents|profiles)\.py$)' && skills=1
printf '%s\n' "$changed" | grep -qE '^(data/mcp/|engine/scripts/agents\.py$)' && mcp=1
if [ $skills = 1 ] && [ $mcp = 1 ]; then
  run "skills 與 MCP 同步" engine/scripts/agents.py sync
elif [ $skills = 1 ]; then
  run "skills 同步" engine/scripts/agents.py sync --skills
elif [ $mcp = 1 ]; then
  run "MCP 同步" engine/scripts/agents.py sync --mcp
fi

if printf '%s\n' "$changed" | grep -qE '^(data/harness/|engine/scripts/(claude_allow|session_nudge)\.py$)'; then
  if "$uv" run --quiet engine/scripts/claude_allow.py >/dev/null 2>&1; then
    echo "OmniKit：已同步 Claude 的權限規則與開新對話提醒"
  else
    echo "OmniKit：claude_allow.py 失敗，Claude 的權限規則與開新對話提醒可能還是舊的" >&2
  fi
fi

if printf '%s\n' "$changed" | grep -qE '^engine/scripts/(codex_hooks|claude_allow|session_nudge)\.py$'; then
  if out=$("$uv" run --quiet engine/scripts/codex_hooks.py 2>&1); then
    # 只有新註冊或改了指令才需要使用者到 Codex 重新信任，這時把提示轉出來
    case "$out" in 已註冊*) echo "OmniKit：$out" ;; esac
  else
    echo "OmniKit：codex_hooks.py 失敗，Codex 的開新對話提醒可能還是舊的" >&2
  fi
fi
