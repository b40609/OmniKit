---
name: omnikit-weekly
description: 產生使用者自己的 OmniKit 個人週報：沒在用的工具、上游有新版的工具、有更好的選擇、被手動改過的設定、主動建議的接受率，以及成本（新裝工具的開頭成本、背景用量、對話開頭的大小）；也依這台裝了什麼、用了什麼給建議，分成裝、拿掉、用內建的就好三類。使用者說「OmniKit 本週週報」「本週週報」「我的週報」「OmniKit 給我建議」「我該裝什麼」「哪些可以拿掉」時使用；不管訪談時有沒有選評估新工具都有。Generates the user's personal weekly OmniKit report and install, remove, or use-built-in advice.
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

## 建議：裝、拿掉、用內建的就好

使用者說「OmniKit 給我建議」「我該裝什麼」「哪些可以拿掉」，或剛做完設定訪談時用。讀的是跟週報同一份紀錄，再對照名冊。分工是：腳本給事實與候選，你挑選並寫理由，腳本驗證後寫出建議。

1. 只處理你自己這個 agent（Claude Code 填 `claude`，Codex 填 `codex`）：

   ```
   uv run scripts/report.py advise --agent <claude 或 codex>
   ```

   輸出是 JSON。`active` 是 false 就照 `skip` 的原因回報，不出建議。Antigravity 目前不出建議。
2. 在 `candidates` 的三類裡挑：`install` 是裝，`remove` 是拿掉，`native` 是用內建的就好。
   - 只能挑候選裡有的 `id`。你知道名冊外更好的工具，另外用一句話告訴使用者，並說明「名冊外、沒有實測」，不要寫進挑選檔。
   - 每一項寫一句理由，要用到 JSON 裡的事實：用了幾段對話、裝了幾天、`basis`、`installed_here`。不要只重複名稱。
   - 你自己已經內建的功能，就是挑 `native`、或不挑某個 `install` 的理由，照實寫。
   - `tested` 是 false 的 `native` 候選還沒實測：可以挑，理由不要寫成驗證過。
   - `detectable` 是 false 的 `install` 候選掃不到有沒有裝：先問使用者是不是已經在用。
   - 不用每個都挑，沒把握的留著。某一類一個都沒有就照實。
3. 把挑選存成 JSON 檔，放在暫存資料夾，不要放進 repo：

   ```json
   {"agent": "claude", "picks": [{"id": "install:frontend-design", "reason": "一句理由"}]}
   ```

   ```
   uv run scripts/report.py advise --picks <檔案路徑>
   ```

   出現「挑選有問題」就照訊息修正再跑。建議的 Markdown 由腳本寫，不要自己寫。通過後的輸出就是建議，最後一行是存檔位置（`%LOCALAPPDATA%\omnikit\advice\<日期>-<agent>.md`）。
4. 照三節講給使用者聽，問要做哪幾項。使用者同意的才做，用輸出裡寫的指令：
   - 裝：照「同意後執行」在終端機跑（Claude Code 是 `claude plugin install`，Codex 是 `codex plugin add`）。對話裡的 `/plugin install` 只會開面板。裝好提醒開新的對話。
   - 拿掉：是刪除，一項一項問。有「先停用」的先建議停用。要刪資料夾時把路徑講清楚；寫了別的 agent「也在讀這一份」的，提醒會一起影響。
   - 用內建的就好：不用動手。同一件事另外裝的工具要不要留，由使用者決定。
5. 使用者說「先這樣」「先留著」就停，不追問。
