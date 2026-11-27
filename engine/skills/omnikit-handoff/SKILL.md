---
name: omnikit-handoff
description: 把做到一半的工作交給新對話，或照交接檔接手；也管每個專案的狀態板 NOW.md（主線開工先讀、每條對話收尾前更新）。使用者說「交接」「handoff」「接手」「讀 <交接檔路徑> 接著做」「更新 NOW.md」時使用；OmniKit 的開新對話提醒出現、而工作還沒做完時，先問使用者要不要交接。Hands unfinished work over to a new conversation, takes over from a handoff file, and keeps each project's NOW.md status board current.
---

# 交接與接手

狀態板 `NOW.md` 與交接檔預設直接存在這台電腦本機的 `~/.omnikit/status/`（零帳號、免先建立 GitHub 私人 repo，內建自動保留本機版本歷史）。若使用者已經把 `~/.omnikit/status` 綁定遠端私人狀態庫，`status.py` 會自動識別並同步，用法完全相同。

- 找到 OmniKit 的 `status.py`：在 OmniKit repo 內為 `engine/scripts/status.py`，在其他專案對話中為 `~/.omnikit/current/engine/scripts/status.py`（`uv` 不在 PATH 時用 `%LOCALAPPDATA%\Programs\uv\uv.exe`）。
- 專案代號：優先取專案的 GitHub repo 名稱，沒有遠端時取專案資料夾名稱（支援中文、英數字、點、底線、連字號）。
- 狀態板路徑：`uv run ~/.omnikit/current/engine/scripts/status.py path <專案代號> --project-path "<專案路徑>" --ensure`
- 綁定遠端私人同步庫（使用者主動要求跨電腦同步時才用）：`uv run ~/.omnikit/current/engine/scripts/status.py bind-remote <遠端私人儲存庫網址>`
- 交接檔路徑：`~/.omnikit/status/<專案代號>/handoffs/<YYYY-MM-DD-HHmm>-<主題>.md`
- 嚴禁寫入金鑰、token、密碼；**嚴禁自行設定使用者的全域 git 身分，也嚴禁自行建立遠端 GitHub repo**（需要跨電腦同步時，請使用者在 OmniKit 本機控制面板設定）。

## 狀態板 NOW.md

每個專案在 `~/.omnikit/status/<專案代號>/NOW.md` 有一份狀態板，只放現況，細節連到交接檔或報告：

- 開頭：更新時間（ISO 或 `YYYY-MM-DD HH:mm`）、主線對話（名稱與 id）、專案路徑與分支。
- 完工路徑（對應「做到哪／完成度」）：放在開頭之後。這一階段做到完工還剩哪幾步，每步寫完成條件（要能驗證：測試、實際輸出、筆數）、目前進度與卡在誰身上，第一句寫「還有 N 步，完成 M 步」，並標出目前坡度（`上坡`：還在探索做法或有未知風險；`下坡`：做法已定只剩執行驗證）。下一步就是第一個沒完成的。清單外的事不放這裡。**若專案已接 GitHub Actions CI，把任一步從 `- [ ]` 改成 `- [x]` 之前，必須先用確定性腳本查證該 commit 的 CI 結論**（見規則第 5 點），不可直接手改打勾。
- 目前結論（對應「目前結論」）：最新生效的 1 到 3 條拍板定案，新決定直接覆蓋舊決定；詳細過程連到交接檔或報告。
- 不滿意待改（對應「我不滿意還要怎麼改」）：用核取方塊列出尚未收斂的驗收差距，每條寫「`- [ ] 現況 -> 不滿意點 -> 過關標準`」（手機端或控制面板可先隨手記一句大白話，進對話時搭配 `/plan` 或 `/grill-me` 對焦補齊）；驗證通過才改成 `- [x]`。
- 進行中的線：一行一條，附對話連結或交接檔路徑；工作包開始時寫明完成條件。每條對話開頭講清楚它做完工路徑的哪一步；清單外的想法記收件匣，急件記「插單紀錄」，修完就停、不順手延伸。
- 等使用者決定的事：每件附建議與理由。
- 下一步（對應「下一步」）：第一條放目前唯一沒有被擋住的最優先動作，每項標【agent 可直接做】或【等使用者】。

規則：

1. 主線開工先執行 `uv run ~/.omnikit/current/engine/scripts/status.py sync`，再讀 `<專案代號>/NOW.md`（沒有就用 `status.py path <專案代號> --project-path "<專案路徑>" --ensure` 建立首份）。
2. 每條對話（主線與子對話）收尾前更新它：做完的拿掉或改寫，新的決定與下一步補上，改更新時間。子對話寫不到狀態目錄時，把要改的內容寫進最終回報，由主線更新。
3. 寫完 `NOW.md` 後執行 `uv run ~/.omnikit/current/engine/scripts/status.py save -m "status(<專案代號>): 更新進度" --path "<專案代號>/NOW.md"`（若個人規則要求同步遠端再加 `--push`）。若專案程式碼 repo 本身已開啟 `main` 分支保護（例如 OmniKit），程式碼一律開分支推上遠端並開 PR，等 CI 全綠再合併。
4. 使用者回答了「等決定」的事，就把那一項移到進行中或下一步，不要留著。
5. **完工路徑打勾前必查 CI（確定性門檻）**：已接 GitHub CI 的專案要把「完工路徑」步驟從 `- [ ]` 改成 `- [x]` 時，一律執行：
   ```
   uv run ~/.omnikit/current/engine/scripts/now_tick.py tick --now <NOW.md 路徑> --match "<步驟關鍵字>" --commit <sha> --project-dir <專案路徑>
   ```
   腳本會查 `gh run list --commit <sha>`，全部最新 workflow 皆為 `success` 才會打勾並重算「還有 N 步，完成 M 步」；CI 失敗、進行中、查無紀錄或離線時會拒絕打勾（exit 1）。需要暫記現況時可加 `--mark-unverified`，維持 `- [ ]` 並標註「（CI 未綠：…）」。

## 交接

1. 工作的修改先 commit（有遠端的專案一併上傳工作分支，未完成用 `wip:` 前綴；純本機專案寫明「只在這台」）。
2. 先跑 `status.py sync`，在 `~/.omnikit/status/<專案代號>/handoffs/` 寫入交接檔（記下目標、已完成、進行中、下三步、規則版本與分支），同時更新 `NOW.md`（進行中的線改連到新交接檔），再跑 `status.py save -m "handoff(<專案代號>): <主題>"`（有設遠端同步者加 `--push`）。
3. Claude 桌面版：直接開新對話接手，簡報裡寫交接檔路徑。其他介面：給使用者一句可以貼進新對話的起始 prompt：「讀 <交接檔路徑> 接著做」。

## 接手

1. 先跑 `status.py sync`（專案有遠端也同步專案 repo），讀 `~/.omnikit/status/<專案代號>/NOW.md`。
2. 讀交接檔。沒給路徑就看 `NOW.md` 連到哪一份；沒有 `NOW.md` 就到 `<專案代號>/handoffs/` 拿檔名排序最後的一份。
3. 比對交接檔的規則版本與自己載入的是否一致；不一致先講。
4. 「接手紀錄」已經有別的對話時，先問使用者再接。
5. 確認分支與「下三步」，回報看到的狀態再開工。
6. 開工後第一次儲存時，在交接檔的「接手紀錄」加一行（時間、裝置、介面、對話 id），並用 `status.py save` 記錄。
