---
name: omnikit-weekly
description: 產生使用者自己的 OmniKit 個人週報：沒在用的工具、上游有新版的工具、有更好的選擇、被手動改過的設定、主動建議的接受率，以及成本（新裝工具的開頭成本、背景用量、對話開頭的大小）。使用者說「OmniKit 本週週報」「本週週報」「我的週報」時使用；不管訪談時有沒有選評估新工具都有。Generates the user's personal weekly OmniKit report.
---

# OmniKit 個人週報

每位使用者每週一份，只讀這台的紀錄與設定，不連網、不上傳。下面的指令路徑都相對於這個 skill 的資料夾；`uv` 不在 PATH 時，用 `%LOCALAPPDATA%\Programs\uv\uv.exe`。

```
uv run scripts/report.py
```

輸出是 Markdown，第一行是週次，接著一行摘要，再依序是六個區塊（第 6 個是成本）。最後一行是完整內容存放的位置（`%LOCALAPPDATA%\omnikit\weekly\<年>-W<週>.md`，同一週重跑會換成最新的）。

照這樣回報：

1. 先講摘要那一行，再照區塊順序講；不要自己加區塊或改數字。
2. 標「未知」的區塊照實說是「還查不到」，並帶一句原因，不要說成「沒有」。
3. **沒在用的工具**：列給使用者看，問要不要停用或移除。移除是刪除，一定要先問，使用者同意後才動手；Claude Code 的 plugin 用 `/plugin uninstall`。OmniKit 自己的 skill 不會列在這裡。使用者說「先留著」就不要再追問，下週還會列出來。
4. **設定被手動改過的項目**：說明是哪一項、被改了什麼（輸出裡有），問使用者那是不是自己改的：
   - 是自己改的、想保留：不用動。MCP 的話，在 repo 根目錄跑 `uv run engine/scripts/agents.py resolve <名稱> --keep-mine`，之後 OmniKit 就不再管它。
   - 想改回 OmniKit 的設定：在 repo 根目錄先跑 `install.ps1 -WhatIf` 預覽，同意再跑 `install.ps1`；MCP 也可以用 `agents.py resolve <名稱> --use-omnikit`。
5. **成本**（第 6 區塊）：
   - 新裝的工具：講每段對話多出的 token；標「估計」或「未知」的照實說。
   - 成本高又沒在用的：不用等 30 天，問使用者要不要停用（Claude Code 的 plugin 用 `/plugin disable`，可以再打開）；停用與移除都要先問。
   - 背景與非互動的用量：說明是哪個工具或資料夾在背景用模型、用了多少；這些不是使用者在對話裡用的。
   - 對話開頭的大小：比上週多 10% 以上時，講輸出列的主要原因。
   - 名冊比對：名冊上是待評估、拒絕或退役的工具，講狀態與理由，問要不要留著。
6. 只列名稱、次數與日期，不含對話內容；不要另外去讀對話紀錄補細節。

這份跟 `omnikit-eval` 的「每週彙整」不同：每週彙整是維護者評估新工具用的（評估額度、建議評估的槽位、評估漏斗），只有選了評估新工具才有；個人週報每個人都有。
