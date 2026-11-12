---
name: omnikit-setup
description: 用簡短訪談建立或重新設定使用者自己的 OmniKit profile（回覆語言與詳略、agent 可以自己做到哪、想改善的習慣、評估工具用的情境），並接上 Claude Code、Codex 與 Antigravity。也替名冊沒有的工作加一個只在這台生效的領域（私有模組）。使用者說「幫我設定 OmniKit」「設定我的 profile」「重新設定 OmniKit」「OmniKit 裝好了然後呢」「我的工作不在清單裡」「幫我加一個領域」時使用。Interviews the user and creates their personal OmniKit profile.
---

# OmniKit 設定訪談

目標：依這台電腦和使用者的需求，產生他自己的 profile，並接上這台接好的 agent（Claude Code、Codex、Antigravity）。profile 存在 repo 外的 `%LOCALAPPDATA%\omnikit\profiles\<名稱>\`（掃描結果的 `omnikit.profiles_dir`），不會被 commit 或 push，在 repo 裡跑 `git status` 也看不到。下面的指令路徑都相對於這個 skill 的資料夾；`uv` 不在 PATH 時，用 `%LOCALAPPDATA%\Programs\uv\uv.exe`。

原則：

- 問題最多 6 題，選擇題為主。掃描查得到的不問，只請使用者確認。
- 你只負責問問題、把答案寫成 JSON；規則檔與情境檔一律由 `setup.py` 產生，不要自己寫或改 profile 資料夾裡的檔案，也不要在 repo 的 `data/profiles/` 建檔。
- 寫入之前一定先給使用者看預覽，取得同意。
- 不讀、不印金鑰；掃描結果只有名稱與版本。

## 1. 掃描

```
uv run scripts/setup.py scan --project <使用者現在的專案資料夾>
```

`--project` 只用來預選第 1 題的領域：只看資料夾裡的檔名，不讀內容。使用者沒有開專案就不加。

用 3 到 5 行告訴使用者看到什麼：

- 裝了哪些 agent。OmniKit 接的是 Claude Code、Codex 與 Antigravity（`omnikit_supported`）；已經接上的列在 `omnikit.connected_agents`。有裝、但不在 `connected_agents` 裡的，提醒在 repo 根目錄重跑 `install.ps1` 接上；其他 agent 不在支援範圍，這次不處理。
- 目前的 profile（`omnikit.profile`）；`profile_chosen` 是 false 表示還在用預設的 default（下載、安裝前會先問）。
- `omnikit.previous_answers` 不是 null：那是上次訪談的答案。下面每一題的預設就照它帶入，使用者只改想改的。
- `omnikit.legacy_profiles` 不是空的：舊版把這些 profile 存在 repo 裡（`data/profiles/<名稱>/`），`git status` 看得到。開始訪談前先說明新版改存在 `profiles_dir`、不會被 commit，問「要搬過去嗎？搬好、確認內容一樣之後，會刪掉 repo 裡的舊檔」。同意才跑 `uv run scripts/setup.py migrate --yes`，把輸出照實回報；不同意就不搬，舊的照常可以用，但重新訪談時不能沿用同一個名稱。

## 2. 訪談

Claude Code 用 AskUserQuestion（一次最多 4 題）；Codex 一次列出編號問題，讓使用者用編號回答。

第一輪，選擇題：

| # | 問題 | 選項 → 答案欄位 |
|---|---|---|
| 1 | 你用 agent 做哪幾種工作？（可複選） | 掃描結果 `omnikit.domains` 的每個領域，講 `name` 與 `summary` → `domains`（填領域的 `id`） |
| 2 | 最想改善哪件事？（最多 2 項） | 回覆太長 `too-long`、常改太多超出要求 `scope-creep`、改完沒驗證就說好了 `no-verification`、不確定時亂猜 `guesses` → `pains`；選「其他」說都還好就是 `[]` |
| 3 | 回覆的語言與詳略？ | 繁中精簡、繁中詳細、English concise、English detailed → `language`（`zh-TW`／`en`）與 `verbosity`（`concise`／`detailed`） |
| 4 | agent 可以自己做到哪？ | 每步先問 `cautious`：改檔案、執行指令前先列計畫等你同意；專案內直接做 `balanced`（建議）：下載安裝、改專案以外的才先問；大多放手 `hands-off`：下載安裝也直接做，只有安全底線列的才問 → `autonomy` |

第二輪：

| # | 問題 | 答案欄位 |
|---|---|---|
| 5 | 要不要用 OmniKit 持續評估新工具？（貼 GitHub 連結，它會拿你的專案情境幫你比較；選「先不要」就不裝評估工具的 skill，個人週報照樣有，之後重新訪談可以改） | 要 → `evaluate_tools: true`；先不要 → `false` |
| 6 | 用一句話介紹你的主要工作與技術。第 5 題選「要」的話，再給主要專案名稱；有前端的話，也給前端專案名稱。 | `background`、`projects.main`、`projects.frontend`（自由回答） |

補充：

- 第 1 題決定之後給建議時看哪些槽位：只看選的領域、它們帶入的能力（瀏覽器、Office 檔等），以及每個人都有的基礎模組。
  - `suggested` 是 true 的領域先幫使用者勾起來，並把 `why` 講出來（例如「專案裡有 package.json」）。預選只是建議，使用者可以改。
  - 領域超過 4 個，Claude Code 的 AskUserQuestion 放不下：這一題改成列出編號清單，請使用者回編號，或說「照建議」。
  - 選超過 3 個時提醒一句：選越多，建議會越多。
  - 都不符合：先選最接近的一個（一個都不接近就不選），把實際的工作寫進第 6 題的 `background`；profile 建好之後，問要不要照第 5 節替這份工作加一個領域。
  - 掃描結果的 `omnikit.private_modules` 是這台已經有的私有模組：一律啟用，不用放進這一題，講一句「另外有你自己加的：…」就好。`private_skipped` 不是空的，照實講哪個檔沒載入、原因是什麼。
- 第 2 題選了「回覆太長」、第 3 題又選「詳細」：兩者矛盾，請使用者擇一。
- profile 名稱用掃描的 `suggested_profile`（重新設定時用上次的名稱），在預覽時請使用者確認；沒有建議就問。名稱只能用小寫英數與 `-`，不能叫 `default`。
- 專案名稱不能有 `<`、`>`。

## 3. 預覽

把答案寫成 JSON，存到掃描結果的 `omnikit.answers_file`。例如：

```json
{
  "name": "alice",
  "language": "zh-TW",
  "verbosity": "concise",
  "autonomy": "balanced",
  "domains": ["software-dev", "data-science"],
  "pains": ["scope-creep"],
  "background": "產線設備資料蒐集與分析，Python 與 PLC",
  "projects": {"main": "產線監控系統", "frontend": "監控儀表板"},
  "evaluate_tools": true
}
```

`evaluate_tools` 是 false 時不用 `projects`；沒有 `background` 就省略。格式見 repo 的 `engine/schema/answers.schema.json`。

```
uv run scripts/setup.py profile --answers <answers_file>
```

把預覽裡的 `AGENTS.md` 原樣給使用者看，並說明：

- 這份會跟安全底線（`data/rules/baseline.md`：刪除、對外發送、付款前先確認，不碰金鑰；push 要不要先問，依授權程度寫在 profile）一起生效，底線不能放寬。
- 有 `scenarios.yaml` 的話，評估工具時會用這些情境當考題。
- `domains.yaml` 是第 1 題選的領域；之後想改，重新訪談，或直接改這個檔。
- 預覽最後有「套用時不裝 omnikit-eval」（第 5 題選了先不要）：照實告訴使用者，評估新工具不會有；個人週報（`omnikit-weekly`，說「OmniKit 本週週報」）照樣有。

問「照這樣建立嗎？」。要改就回到對應的題目，改完重新預覽。

腳本的回應：

- 「答案有問題」：照訊息修正 JSON 再預覽，不要自己改規則檔。
- 「已經存在」：是使用者上次訪談建立的（`previous_answers.name` 相同），問要不要覆蓋，同意才加 `--force`，舊檔會備份成 `.bak`。
- 「手寫的 profile」或「repo 裡已經有 profile」：不能覆蓋，請使用者換一個名稱。
- 「repo 裡有舊版存的同名 profile」：回到第 1 步，問使用者要不要搬到 repo 外。

## 4. 建立並套用

```
uv run scripts/setup.py profile --answers <answers_file> --write --apply
```

（要覆蓋時再加 `--force`。）輸出出現「已套用 profile：…」就完成。回報：

- 開新的 session 才會生效。確認方式：問「OmniKit 規則版本與 profile 是什麼？」
- 第 5 題選「先不要」：輸出會有「不裝 omnikit-eval」，評估工具的 skill 已經拿掉；之後想用，重新訪談選「要」就會裝回來。不管選哪個，每週都可以說「OmniKit 本週週報」看個人週報。
- 依第 2 題給一個試試看的例子，例如選了 `scope-creep`：請它改一個小地方，看它會不會順手改別的。
- 想知道這台該裝什麼、拿掉什麼、哪些用內建的就好：說「OmniKit 給我建議」（`omnikit-weekly`）。
- profile 存在這台電腦的 `profiles_dir`（`%LOCALAPPDATA%\omnikit\profiles\<名稱>\`），在 repo 外，不會被 commit 或上傳。之後想手動改，直接改那裡的 `AGENTS.md`，再在 repo 根目錄跑 `uv run engine/scripts/profiles.py` 重新接上（Claude Code 直接讀這份；Codex 與 Antigravity 讀的是接在一起的副本）；想換別的 profile，跑 `uv run engine/scripts/profiles.py --set <名稱>`。
- 輸出提到某個 agent 的規則「沒有覆蓋」或「沒有加回去」：那是使用者自己改過的檔案，這次沒動；要接上就在 repo 根目錄重跑 `install.ps1`。

## 5. 名冊沒有的領域（私有模組）

使用者的工作不在第 1 題的領域裡，或直接說「幫我加一個領域」時做。不用重新訪談。私有模組存在 repo 外的 `omnikit.modules_dir`（`%LOCALAPPDATA%\omnikit\modules\`），只在這台生效，不會被 commit；放進去就啟用，給建議與找候選時會看，公開的看板不會。

1. 請使用者用幾句話講這份工作：平常要交出什麼成果、用到哪些檔案或軟體。不夠具體就追問一次，不要自己編。
2. 草擬一個模組，存成 JSON 放在暫存資料夾（不要放進 repo）：

   ```json
   {
     "id": "events",
     "name": "活動與研討會籌辦",
     "summary": "研討會與工作坊的議程、報名名單與會後整理",
     "requires": ["office-docs"],
     "signals": {"keywords": ["研討會", "議程"]},
     "slots": [
       {"id": "event-agenda", "name": "排議程與聯絡講者",
        "scenarios": ["依講者可以的時段排出兩天的議程表，衝堂的標出來，並草擬給每位講者的確認信。"],
        "search": ["event agenda planning", "calendar scheduling"]}
     ]
   }
   ```

   - 一個槽位是一件要交付的工作，用動作加成果命名，不是工具類別。2 到 6 個；超過就拆成兩個模組。
   - `scenarios` 每個槽位至少一句，寫成可以實測的任務：給什麼、要交出什麼、怎樣算對。寫一句文字就好，編號由腳本給。
   - `search` 是找候選用的關鍵字，會送到 GitHub 與官方 MCP Registry：用通用的英文說法（工具的類別、檔案格式、動作），**不要寫單位、客戶、專案或人的名稱**。
   - `requires` 只能填能力模組的 `id`（repo 的 `data/modules/capability/`），用得到才填。
   - `id` 用小寫英數與 `-`，不能跟名冊已經有的模組或槽位重複。任職單位專屬的內容可以寫在 `name`、`summary`、`scenarios`（這些不會送出去）。
   - 不要寫 `answers`：還沒有人實測過，答案就是還不知道。
3. 預覽，把輸出的模組內容給使用者看，問「照這樣加嗎？」：

   ```
   uv run scripts/setup.py module --draft <草稿檔>
   ```

   - 「草稿有問題」：照訊息修正 JSON 再預覽。
   - 「已經存在」：是這台之前加的同名模組。問使用者要不要覆蓋，同意才在下一步加 `--force`，舊檔會備份成 `.bak`。
4. 同意後寫入：

   ```
   uv run scripts/setup.py module --draft <草稿檔> --write
   ```

   輸出「已經啟用」就完成。告訴使用者：
   - 這些槽位還沒有答案；說「OmniKit 給我建議」就會替它們找名冊外的候選，那些候選沒有實測過。
   - 想改就直接改那個檔，想停用就刪掉它（檔案位置在輸出裡）；不要替使用者刪。
   - 覺得別人也用得到，可以把檔案放進 repo 的 `data/modules/` 提成公版；提之前把單位專屬的內容拿掉。

想看這台有哪些私有模組、哪個沒載入：`uv run scripts/setup.py module --list`。
