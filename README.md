<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/hero-dark.svg">
  <img alt="OmniKit：Coding agent 的共用設定層。安全底線、技能、MCP 與護欄寫一次，同步到 Claude Code、Codex 與 Antigravity。" src=".github/assets/hero-light.svg">
</picture>

<br>

[![檢查](https://github.com/b40609/OmniKit/actions/workflows/validate.yml/badge.svg)](https://github.com/b40609/OmniKit/actions/workflows/validate.yml)
[![授權 MIT](https://img.shields.io/badge/%E6%8E%88%E6%AC%8A-MIT-2456d6)](LICENSE)
[![平台 Windows 11](https://img.shields.io/badge/%E5%B9%B3%E5%8F%B0-Windows%2011-26251e)](docs/install.md#疑難排解)
[![支援 Claude Code、Codex、Antigravity](https://img.shields.io/badge/agent-Claude%20Code%20%C2%B7%20Codex%20%C2%B7%20Antigravity-2456d6)](#一份設定三個-agent)

[快速開始](#快速開始) · [裝好之後](#裝好之後) · [功能](#功能) · [文件](#文件) · [常見問題](#常見問題) · [線上槽位看板](https://b40609.github.io/OmniKit/)

</div>

<br>

同時用 Claude Code、Codex 與 Antigravity，同一套規矩就得寫三遍：哪些事要先問、金鑰不能碰、改完沒真跑實測就說「好了」結果一開就爆。plugin、skill、MCP 每週都有新的，裝到後來也說不清哪個真的有用、吃了多少開場 Context。

OmniKit 把這些收成一套**本機網頁控制面板 ＋ 開箱即用精選工作台 ＋ 防假完工真機驗收護欄**，一次同步到三個 agent。它不蓋掉你原本的規則，免建 GitHub 帳號就能用本機 `NOW.md` 專案狀態板，不想用了一行指令乾淨還原。

## 快速開始

**需要：** Windows 11、[Git](https://git-scm.com/download/win)，以及 Claude Code、Codex、Antigravity 至少一個（裝 [Node.js LTS](https://nodejs.org/) 可啟用瀏覽器自動實測 MCP；沒裝也能先用規則、技能與控制面板）。**不需要 GitHub 帳號。**

最省事的做法是直接跟 Claude Code、Codex 或 Antigravity 說：

```text
幫我安裝 OmniKit：https://github.com/b40609/OmniKit
```

> **給 agent：** 照[安裝說明](docs/install.md#直接安裝同事用不用-fork不用-github-帳號)執行 `install.ps1`。裝完會自動啟動本機控制面板（`http://127.0.0.1:3780/`），使用者在網頁勾選即可一鍵完成個人化與精選工作台設定；若在無頭環境也可讀 `engine/skills/omnikit-setup/SKILL.md` 在對話內設定。

想自己來，在 PowerShell 跑（同事版預設鎖定最新穩定發行 tag，維護者推 `main` 不會影響你；也可加上 `-Tag <版本>` 指定版本）：

```powershell
git clone https://github.com/b40609/OmniKit.git "$env:USERPROFILE\OmniKit"
cd "$env:USERPROFILE\OmniKit"
powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 -WhatIf   # 只列出會改哪裡，什麼都不寫
powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1
```

裝完會自動打開**本機控制面板**（`http://127.0.0.1:3780/`）：預先勾好免金鑰精選套件與防假完工習慣（9 項習慣自由複選不設上限），看得到三家 Agent 的開場 Context 預算佔比，按一下「一鍵套用」就全部裝好。就算手邊還沒有任何專案，也能在面板裡一鍵建立第一個專案與破冰提示詞。

| 你在意的 | OmniKit 怎麼做 |
|---|---|
| 原本的設定會不會被蓋掉 | 規則只加一段受管區塊，第一次接上先備份；若你外部手動改過受管區塊，背景同步自動保留並在面板提示三選一 |
| 裝了什麼、吃多少額度看得到嗎 | 控制面板即時顯示每個工具佔用的開場 Context token 數；`-WhatIf` 預覽零寫入副作用 |
| AI 老是只跑假測試就說完工怎麼辦 | 內建防假完工護欄（`done_check` 記錄並可切強制攔截 `.skip` 假綠燈與無實測宣稱）＋ `/ok 驗收` 真機瀏覽器驗收 |
| 不想用了怎麼辦 | `engine\scripts\uninstall.ps1` 停止面板並只拿掉 OmniKit 加的東西，備份放回原位 |

之後要更新到新發行版：`git fetch --tags`，再跑 `install.ps1 -Tag <版本> -WhatIf` 預覽、`install.ps1 -Tag <版本>` 套用。fork 一份自己維護與每一處改動的完整清單，見[安裝說明](docs/install.md)。

## 裝好之後

安裝完成會自動開啟本機控制面板（隨時可在對話打 `/ok 面板` 或執行 `uv run ~/.omnikit/current/scripts/cockpit.py open` 叫出來，預設按需啟動不常駐吃資源），並在對話裡提供 `/ok` 總入口：

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/session-dark.svg">
  <img alt="示意：輸入 /ok 呼叫面板、防假完工驗收、交接、調研、分派、設定、清點；要 agent 讀 .env 或跳過驗證時，OmniKit 護欄直接擋下。" src=".github/assets/session-light.svg">
</picture>

## 功能

<table>
<tr>
<td width="50%" valign="top">

### 本機控制面板與精選工作台

不用背指令、不用手改 YAML：在瀏覽器一頁勾選目標套餐、個人習慣與精選工具（外掛與內建 MCP 一鍵同步啟停，外部 CLI 記錄偏好並附安裝指令），即時預覽三家 Agent 開場 Context 預算估算。

</td>
<td width="50%" valign="top">

### 防假完工護欄與 `/ok 驗收`

根治「AI 寫一堆 Mock 單測全綠就宣稱完工，真人一打開就白屏報錯」：`done_check` 追蹤偷加 `.skip` 的假綠燈與無實測證據的完工宣稱（預設記錄模式，面板可隨時切換強制攔截）；搭配 `/ok 驗收`（`omnikit-verify`）自動掃描斷頭引用、真開服務與桌機／手機寬度瀏覽器確認 0 錯誤。

</td>
</tr>
<tr>
<td valign="top">

### 零帳號本機 `NOW.md` 專案狀態板

不用先去開 GitHub 私人 repo：安裝即自動在 `~/.omnikit/status` 建立本機 Git 狀態庫，記錄每個專案的完工進度、現行結論、三段式不滿意待改與下一步，支援面板一鍵檢視歷史與還原舊版；日後想跨機同步再綁遠端即可。

</td>
<td valign="top">

### 一份設定，三個 agent（含純單家環境）

規則、skills、MCP 與護欄寫一次，同步到 Claude Code、Codex 與 Antigravity（只裝其中一家如純 Codex 或純 Antigravity 也完整可用）。`doctor.py` 與面板健康檢查頁隨時對帳並支援一鍵修復。

</td>
</tr>
<tr>
<td valign="top">

### 安全底線與確定性護欄

刪檔、`git push -f`、對外發送、付款之前先問你；金鑰不讀、不印、不寫死（需 API Key 的工具只讀環境變數，絕不明文落盤）。Claude Code 與 Antigravity 另有確定性 hook 擋下偷讀 `.env`、`--no-verify` 等繞過捷徑。

</td>
<td valign="top">

### 實測工具名冊與自動瘦身

160 多張工具卡分在 26 個槽位，附信任徽章與選用理由，線上可看[槽位看板](https://b40609.github.io/OmniKit/)。常駐規則有位元組預算棘輪，超過即擋 CI，確保開場 Context 永遠精實。

</td>
</tr>
</table>

## 文件

| 文件 | 內容 |
|---|---|
| [安裝說明](docs/install.md) | 直接安裝、fork 自己維護、只裝預設 plugin、安裝會改動哪些地方、維護者版與同事版、移除 |
| [使用指南](docs/usage.md) | 確認接上了、安裝前後差在哪、建立 profile、`/ok` 與簡短指令、評估新工具、診斷 |
| [子任務分派](docs/dispatch.md) | 每一級用什麼模型、設定自己的帳號、選配模型 Fable 5.2、委派紀錄 |
| [運作方式](docs/architecture.md) | 設計原則、資料怎麼流、無帳本對帳、互動架構地圖、目錄結構 |
| [維護名冊](docs/maintainer.md) | 槽位看板、新增一種業務、改名冊、更新門面圖、跟上原作者的更新 |
| [三家內建功能對照](docs/cli-features.md) | Claude Code、Codex、Antigravity 內建指令一覽 |
| [新電腦起步清單](docs/starter.md) | 新電腦該裝哪些東西 |

## 常見問題

<details>
<summary><b>會不會蓋掉我原本的設定？</b></summary>

不會直接蓋掉。`~/.claude/CLAUDE.md`、`~/.gemini/AGENTS.md` 與 `~/.gemini/GEMINI.md` 只加一段受管區塊，原本的內容留在區塊外；`~/.codex/AGENTS.md` 第一次接上時會先備份；MCP 與權限都是合併寫入，同名但不是 OmniKit 的 skill 也不碰。只有加上 `-Fresh` 才會移除 CLAUDE.md 的其他內容，而且也會先備份。完整清單見[安裝會改動哪些地方](docs/install.md#安裝會改動哪些地方)。

</details>

<details>
<summary><b>我沒有 Fable 5.2，也沒有 Gemini，能用嗎？</b></summary>

可以。分派政策只會派給你方案裡有的模型：只有 Claude 時，各級用 Opus（effort medium 到 xhigh）與 Sonnet，跨家審查自動跳過，不會同一個模型自己審自己。方案有 Fable 5.2 的，在 profile 的 `dispatch.md` 寫一行 `opt_in_classes: [claude-fable]` 才會啟用。見[子任務分派](docs/dispatch.md)。

</details>

<details>
<summary><b>裝好了，要去哪裡調整設定或開關工具？</b></summary>

安裝完成會自動打開本機控制面板（`http://127.0.0.1:3780/`）；平常關閉瀏覽器後，隨時可在對話輸入 `/ok 面板`、從 Windows 開始功能表點「OmniKit 控制面板」，或在任意資料夾執行 `uv run ~/.omnikit/current/scripts/cockpit.py open` 重新開啟。改完規則與工具後，新開的 Agent 對話即生效。

</details>

<details>
<summary><b>支援 macOS 或 Linux 嗎？</b></summary>

`install.ps1` 與 git hooks 目前只支援 Windows（PowerShell 5.1 或 7）。[只裝預設的 plugin](docs/install.md#只想裝預設的-plugin) 不受作業系統限制。

</details>

更多問題見[安裝說明的疑難排解](docs/install.md#疑難排解)與[使用指南的常見問題](docs/usage.md#常見問題)。遇到問題請開 [Issue](https://github.com/b40609/OmniKit/issues)。

## 致謝與授權

OmniKit 建立在 [uv](https://github.com/astral-sh/uv)、[gitleaks](https://github.com/gitleaks/gitleaks)、[GitHub CLI](https://github.com/cli/cli) 與 [Floorplan](https://github.com/haydenschmitty/floorplan) 之上；門面圖的字體是 [Geist](https://github.com/vercel/geist-font) 與 [Noto Sans TC](https://github.com/notofonts/noto-cjk)（SIL OFL）。以 [MIT](LICENSE) 授權釋出。
