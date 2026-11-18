---
description: omnikit-ask 真實糾正題（real-agent-jumped-into-plan）
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
timeout_seconds: 240
category: agent
situation: agent.md「話還沒講完，它就開始大改」
kind: correction
expect_fire: false
source: https://github.com/entireio/cli refs/entire/checkpoints/v2/main 02/dce46af028/0/prompt.txt 第 3 句（session 239c414d-2b2a-42d8-b557-85f3197d1015）
---

等一下，先不要照計畫全部開改。我想一步一步來，每步都要我看過。把你已經改的都復原，第一步只先替現有流程做一個 benchmark。

（這件事發生在另一台電腦的專案裡，這台電腦上的資料夾都跟它無關。）
