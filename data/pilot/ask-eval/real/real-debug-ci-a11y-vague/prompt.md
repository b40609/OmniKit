---
description: omnikit-ask 真實糾正題（real-debug-ci-a11y-vague）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: debug
situation: debug.md「我的電腦正常，CI 或正式環境壞掉」
kind: correction
expect_fire: false
source: https://github.com/thedannywahl/pantoken refs/entire/checkpoints/20/01M66XGJ1YBY82KCZJMT95EB20 0/prompt.txt 第 2 句（session 78bb7939-3afc-40ea-b4de-14cf9e3c463c）
---

元件的無障礙檢查在 CI 還是失敗：https://github.com/example/repo/actions/runs/1/job/2?pr=239

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
