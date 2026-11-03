#!/bin/sh
# 從 stdin 讀變動的檔名；動到 data/rules/ 才同步給 Codex
# （Codex 不支援 import，讀的是 skillshare 複製的副本）
if grep -q '^data/rules/'; then
  if "$LOCALAPPDATA/Programs/skillshare/skillshare.exe" sync extras >/dev/null 2>&1; then
    echo "OmniKit：已把規則同步給 Codex"
  else
    echo "OmniKit：skillshare sync extras 失敗，Codex 的規則可能還是舊的" >&2
  fi
fi
