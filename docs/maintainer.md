# 維護名冊

[← 回到首頁](../README.md) · [安裝說明](install.md) · [使用指南](usage.md) · [子任務分派](dispatch.md) · [運作方式](architecture.md)

給 fork 一份自己維護、或要改名冊的人。只用 OmniKit 的同事不需要讀這份。

- [槽位看板與新模型提醒](#槽位看板與新模型提醒)
- [新增一種業務](#新增一種業務)
- [槽位的答案](#槽位的答案)
- [改名冊](#改名冊)
- [更新 README 門面圖](#更新-readme-門面圖)
- [更新架構地圖](#更新架構地圖)
- [跟上原作者的更新](#跟上原作者的更新)
- [本機 Cockpit 多專案面板](#本機-cockpit-多專案面板個人進階功能)

## 槽位看板與新模型提醒

- **線上槽位看板**：[b40609.github.io/OmniKit](https://b40609.github.io/OmniKit/) 列出試用中的工具、預設 plugin 的安裝指令與最近的決定。看板不自動部署，要更新時到 Actions 手動觸發「部署看板」（`.github/workflows/pages.yml`，`workflow_dispatch`）。

  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../.github/assets/board-dark.png">
    <img alt="OmniKit 槽位看板：試用中的工具、預設 plugin 的安裝指令與最近的決定" src="../.github/assets/board-light.png">
  </picture>

- **每週新模型差異提醒**（規劃中，只提建議、不會靜默換模型）：看板首頁的「新模型」區塊列出每週偵測到的新模型、淘汰與建議對應；專案狀態板 `NOW.md` 的待決事項整理異動清單與建議角色順位，維護者拍板後才寫入政策；T3 排程任務在發現新模型或舊模型消失時開新對話通知。

## 新增一種業務

槽位寫在模組檔裡，一個模組一個檔：`data/modules/<層>/<id>.yaml`。

| 層 | 放什麼 | 例子 |
|---|---|---|
| `foundation` 基礎 | agent 自己怎麼運作，做什麼工作都會遇到 | 對話與記憶、輸出與品質 |
| `capability` 能力 | agent 要碰得到某種東西才做得了事；不只一個領域會用到才獨立出來 | 瀏覽器、文件與簡報檔、桌面程式 |
| `domain` 領域 | 一種業務要交付的成果 | 軟體開發、計畫書與專案管理、CAD 與機構設計 |

要加一種新的業務：

1. 複製一個現成的領域模組（例如 `data/modules/domain/video.yaml`）成新檔，檔名就是模組的 `id`。
2. 改名稱與一句說明，再列出槽位。一個槽位是一件要交付的工作，用動作加成果命名（「撰寫計畫書」「粗剪」），不是工具的類別；一個模組 3 到 6 個槽位。
3. 每個槽位至少寫一個情境，寫成可以實測的任務；`search` 填找工具用的關鍵字。
4. 需要瀏覽器、Office 檔這類能力，在 `requires` 列出能力模組的 `id`。
5. 跑 `uv run engine/scripts/validate.py` 檢查，再 commit。

規則：模組、槽位、情境的 `id` 在整份名冊裡都不能重複；情境 `id` 是 1 到 3 個大寫字母加數字（`PR1`、`CD4`）。任職單位或個人專屬的內容（補助單位的範本、公司內的規定）不要寫進模組檔，寫在自己 profile 的 `scenarios.yaml`。

## 槽位的答案

同一件工作在不同 agent 上的答案可以不一樣，寫在槽位的 `answers`，Claude Code 與 Codex 分開：

```yaml
answers:
  claude:
    verdict: native        # 內建的就夠
    reason: 實測的結論，一句話
    evidence: data/evals/<實測紀錄>.md
    decided_at: '2026-11-11'
  codex:
    verdict: tool          # 建議裝 tool 指的那張卡
    tool: chrome-devtools-mcp
    reason: 為什麼內建的不夠
    decided_at: '2026-11-11'
```

| `verdict` | 意思 | 要填什麼 |
|---|---|---|
| `native` | 內建的就夠 | `reason`、`decided_at` |
| `tool` | 建議裝某張卡 | `tool`、`reason`、`decided_at`；那張卡要放在這個槽位，而且支援這個 agent |
| `none` | 找過了，沒有好選擇 | `reason`、`decided_at` |
| `unknown` | 還沒實測 | 可以先在 `reason` 寫這個 agent 內建的功能是什麼 |

沒列的 agent 就是還不知道；看板與評估紀錄會據此標明各槽位應該用內建功能還是外裝工具。目前有實測的只有瀏覽器。

## 改名冊

改完 `data/` 直接 commit：維護者版的 pre-commit hook 會驗證名冊，並重新產生 marketplace 清單一起放進 commit。要手動檢查：

```powershell
uv run engine/scripts/validate.py
uv run engine/scripts/build.py --site _site
```

uv 不在 PATH 上的話，把 `uv` 換成 `& "$env:LOCALAPPDATA\Programs\uv\uv.exe"`。CI 會再檢查名冊、marketplace 清單是不是最新、看板能不能產生，並用 gitleaks 掃金鑰。

## 更新 README 門面圖

`.github/assets/hero-*.svg` 與 `session-*.svg` 由 `engine/site/readme_art.py` 產生，文字都轉成向量路徑，在任何系統上字形都一樣。改了文案、選單或護欄訊息時重跑：

```powershell
uv run engine/site/readme_art.py --fonts <字體資料夾>
```

字體是 SIL OFL 的 Geist、Geist Mono 與 Noto Sans TC，下載網址寫在 `readme_art.py` 檔頭，不進 repo。終端機預覽的字串要跟 `engine/skills/ok/SKILL.md` 的主選單、`engine/scripts/harness_hooks.py` 的攔截訊息一致（攔截訊息只取每則的前半句）。

貼連結到 LINE、Slack 時顯示的社群預覽圖是 `.github/assets/social-preview.png`（1280×640，`hero-light.svg` 置中放在同色底上的截圖）。GitHub 沒有上傳預覽圖的 API，要到 repo 的 **Settings → General → Social preview → Edit → Upload an image** 手動換。

## 更新架構地圖

`engine/site/map.html` 是用 [Floorplan](https://github.com/haydenschmitty/floorplan) 在本機產生後匯出的，CI 不會重畫。`engine/` 有結構上的改動時，在裝了 Floorplan 的 Claude Code 裡說「更新 floorplan」，再匯出並 commit：

```powershell
node floorplan/serve.mjs --export engine/site/map.html
```

`floorplan/` 本身不進 git；換電腦後第一次要重畫整張地圖。

## 跟上原作者的更新

在你的 fork 頁面按 **Sync fork**，或在本機：

```powershell
git remote add upstream https://github.com/b40609/OmniKit.git   # 只要做一次
git pull upstream main
```

- `data/` 有衝突時，留你自己的版本。
- 兩份 marketplace 清單有衝突時，直接重新產生：`uv run engine/scripts/build.py --marketplace-only`。
- `engine/` 有更新時，重跑一次 `install.ps1`。

## 本機 Cockpit 多專案面板（個人進階功能）

同時開多個專案與狀態板（`NOW.md`）時，可以用本機指揮台一次看清「等你決定／待收尾／執行中／停泊」與過期提醒。同事版安裝時預設不會啟用，也不會註冊開機自啟：

```powershell
uv run scripts/cockpit.py snapshot            # 終端機檢視所有已註冊專案現況
uv run scripts/cockpit.py serve --open        # 啟動本機網頁面板（預設 127.0.0.1:3780）
uv run scripts/cockpit.py register --name <專案> --path <目錄>
uv run scripts/cockpit.py autostart --status  # 查詢／管理 Windows 登入自啟（--install / --uninstall）
```
