<div align="center">

# OmniKit

**讓你的 agent 設定自己汰舊換新，每個決定都有理由。**

[![檢查](https://github.com/b40609/OmniKit/actions/workflows/validate.yml/badge.svg)](https://github.com/b40609/OmniKit/actions/workflows/validate.yml)
[![看板](https://img.shields.io/badge/%E7%9C%8B%E6%9D%BF-%E7%B7%9A%E4%B8%8A-1d5c47)](https://b40609.github.io/OmniKit/)
[![授權](https://img.shields.io/badge/%E6%8E%88%E6%AC%8A-MIT-blue)](LICENSE)
[![平台](https://img.shields.io/badge/%E5%B9%B3%E5%8F%B0-Windows%2011-0078d4)](#常見問題)

[槽位看板](https://b40609.github.io/OmniKit/) · [架構地圖](https://b40609.github.io/OmniKit/map.html) · [快速開始](#快速開始) · [裝好之後](#裝好之後) · [運作方式](#運作方式) · [常見問題](#常見問題)

</div>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/board-dark.png">
  <img alt="OmniKit 槽位看板：試用中的工具、預設 plugin 的安裝指令與最近的決定" src=".github/assets/board-light.png">
</picture>

Claude Code 與 Codex 的 plugin、skill、MCP 每週都有新的，裝了一堆之後，很難說清楚哪個真的有用、當初為什麼選它。

OmniKit 把「該用哪個」變成一份有紀錄的名冊。每一種需求是一個**槽位**，配上幾個真實的工作情境；每個工具一張**卡片**，記下狀態、日期與理由。新工具進來時，拿槽位的情境跟現任比，比贏了才換，換的理由也會留下來。

## 特色

- **每個決定都有理由**：卡片記下狀態（預設、試用、待評估、拒絕、退役）、決定日期與理由，過了半年還查得到當初為什麼選它。
- **用真實情境比，不看星數**：每個槽位配幾個你實際會遇到的情境，評估新工具就拿這些當考題。
- **一份設定，兩個 agent**：規則、skills、MCP、權限只寫一次，同步到 Claude Code 與 Codex。
- **名冊是唯一來源**：看板與兩份 plugin marketplace 都由名冊產生，CI 會檢查它們跟名冊一致。
- **評估分層、有額度**：第 0 層免費、第 1 層便宜、第 2 層實測；每週的實測次數有上限，不會一直燒 token。
- **安全的預設**：工具固定版本並比對 SHA256、commit 前用 gitleaks 掃金鑰、安裝第三方 skill 前先掃描、權限規則只增不刪。

## 快速開始

Fork 一份，換成你自己的規則與情境。fork 會帶著原作者已經整理好的 100 多張工具卡，可以直接當起點。

**需要：** Windows 11、[Git](https://git-scm.com/download/win)、[Node.js LTS](https://nodejs.org/)（MCP 用）、Claude Code 或 Codex、GitHub 帳號。

1. **Fork 並開啟看板。** 按本頁右上角的 **Fork**，接著在你的 fork 上：
   - **Actions** 分頁：fork 的 workflow 預設是關的，按 **I understand my workflows, go ahead and enable them**。
   - **Settings → Pages**：**Source** 選 **GitHub Actions**。

2. **Clone 到自己的電腦。**

   ```powershell
   git clone https://github.com/<你的帳號>/OmniKit.git
   cd OmniKit
   ```

3. **選你的 profile。** agent 讀到的規則分兩層：
   - `data/rules/baseline.md` 是安全底線，所有人都套用：刪除、對外發送、付款、push 前先確認，不碰金鑰。
   - `data/profiles/<名稱>/` 是個人層：`AGENTS.md` 寫語言、語氣、哪些事可以直接做；`scenarios.yaml` 寫評估工具用的真實情境，沒寫的槽位用 `data/slots.yaml` 的範本。

   不指定的話用 `default`：繁體中文、下載安裝前先問。想要自己的，複製 `data/profiles/default` 成 `data/profiles/<你的名字>` 再改；`data/profiles/ryan` 是原作者的，可以參考。之後再改也行，git hook 會自動同步。

4. **安裝。** 可以重複執行，profile 指定一次就會記住。安裝前建議先看[安裝會改動哪些地方](#安裝會改動哪些地方)。

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 -ProfileName <你的名字>
   ```

   偵測到這是 fork 時，會自動把 `data/omnikit.yaml` 的 `repo`、`owner`、`marketplace` 改成你的、看板用的 `profile` 改回 `default`，並重新產生 marketplace 清單，避免跟原作者的撞名。

5. **推上去。** 推到 main 之後，GitHub Actions 會部署看板到 `https://<你的帳號>.github.io/OmniKit/`。

   ```powershell
   git commit -am "chore: 改成自己的 OmniKit"
   git push
   ```

6. **確認接上了。** 開一個新的 Claude Code 或 Codex session，問「OmniKit 規則版本與 profile 是什麼？」，版本跟 `data/rules/baseline.md` 開頭的一樣、profile 是你選的，就表示兩層規則都生效了。skill 與 MCP 怎麼檢查、裝好之後怎麼用，見[裝好之後](#裝好之後)。

### 只想裝預設的 plugin

不用 fork，也不會動到你的其他設定。先把 OmniKit 加成 marketplace：

| | 指令 |
|---|---|
| Claude Code | `/plugin marketplace add b40609/OmniKit` |
| Codex | `codex plugin marketplace add b40609/OmniKit` |

再裝想要的 plugin，例如 frontend-design：

| | 指令 |
|---|---|
| Claude Code | `/plugin install frontend-design@omnikit-b40609` |
| Codex | `codex plugin add frontend-design@omnikit-b40609` |

目前收錄哪些，看[槽位看板](https://b40609.github.io/OmniKit/)的「安裝預設的 plugin」。

## 裝好之後

安裝不會在 Claude Code 或 Codex 的畫面上多出按鈕或面板。改變的是 agent 開 session 時讀到的規則，以及多了一個 skill、一個 MCP。**已經開著的 session 不會重讀，要開新的 session 才生效。**

### 確認接上了

| 檢查 | Claude Code | Codex |
|---|---|---|
| 規則 | 問「OmniKit 規則版本與 profile 是什麼？」，版本跟 `data/rules/baseline.md` 開頭的「規則版本」一樣，profile 是你選的 | 同左 |
| skill | 輸入 `/omnikit-eval`，選單裡會出現 | 輸入 `$omnikit-eval`，或用 `/skills` 列出來 |
| MCP | 終端機跑 `claude mcp get chrome_devtools`，狀態是 Connected | 終端機跑 `codex mcp list`，`chrome_devtools` 是 enabled |

### 安裝前後差在哪

| 項目 | 會有什麼不同 | Claude Code 與 Codex 的差別 |
|---|---|---|
| 規則（`data/rules/baseline.md` + `data/profiles/<名稱>/AGENTS.md`） | 安全底線所有人都一樣；回覆用什麼語言、寫多詳細、哪些事可以直接做，照你選的 profile。`default` 是繁體中文、下載安裝前先問 | Claude Code 直接讀 repo 裡這兩份，改完開新 session 就生效。Codex 讀的是兩份接在一起的副本，改完要 commit，git hook 才會同步過去 |
| `omnikit-eval` skill | 貼 GitHub 連結說「幫我評估」，agent 會查 GitHub 現況、對照槽位情境，寫成 `data/tools/` 裡的工具卡 | 兩邊說「幫我評估」都會自動觸發；要手動叫，Claude Code 輸入 `/omnikit-eval`，Codex 輸入 `$omnikit-eval` |
| `chrome_devtools` MCP | agent 能自己開瀏覽器：開網頁、截圖、看 console 與網路請求。每次用暫時的瀏覽器設定檔，碰不到你的登入狀態 | Claude Code 已加進免問清單，Codex 設成自動核准，兩邊都不會跳權限確認 |
| 開新對話提醒 | 每回合結束時檢查一次：上下文每跨過 100k tokens、或這一回合成功 `git push`，就跳一行提醒你考慮開新對話。只提醒，不會自己換對話 | Claude Code 裝好就生效。Codex 多看一項：對話累計第 1、3、9、27… 次自動壓縮時也提醒（Codex 常在 100k 前就壓縮）；新 hook 要先信任才會跑，CLI 輸入 `/hooks`、桌面版到設定的 Hooks 按信任；OmniKit 搬位置或原本那支 uv 不在了，指令會改，要再信任一次 |
| git hooks | 只作用在 OmniKit repo：commit 前掃金鑰、驗證名冊；commit 或 pull 動到規則、profile、MCP、權限時自動同步 | 跟 agent 無關 |

開新的 session 試試看：

```text
OmniKit 規則版本與 profile 是什麼？
幫我評估 https://github.com/<owner>/<repo>
用瀏覽器打開 http://localhost:3000，看 console 有沒有錯誤
每週彙整
```

評估、改名冊、跟上原作者的更新，見[日常使用](#日常使用)。

### 預設 plugin 要另外裝

`install.ps1` 不會把 OmniKit 加成 marketplace，也不會安裝看板上的預設 plugin。想用的話，照[只想裝預設的 plugin](#只想裝預設的-plugin) 的指令裝。用自己的 fork 時：

- 把指令裡的 `b40609/OmniKit` 換成你的 fork。
- `@` 後面的 marketplace 名稱換成你 `data/omnikit.yaml` 的 `marketplace`，例如 `omnikit-<你的帳號小寫>`。
- 先 push 到 GitHub，marketplace 才讀得到最新的清單。

## 運作方式

```mermaid
flowchart LR
  E["omnikit-eval<br/>評估新工具"] -->|寫卡片| D
  subgraph D["data/ 名冊"]
    S["slots.yaml<br/>槽位與情境範本"]
    T["tools/*.yaml<br/>工具卡"]
    R["rules/baseline.md<br/>安全底線"]
    F["profiles/*/<br/>個人規則與情境"]
    M["mcp/、harness/<br/>MCP 與權限"]
  end
  S --> B["build.py"]
  T --> B
  F -->|情境| B
  B --> P["槽位看板<br/>GitHub Pages"]
  B --> K["plugin marketplace"]
  R --> I["install.ps1<br/>與 git hooks"]
  F -->|規則| I
  M --> I
  I --> C["Claude Code"]
  I --> X["Codex"]
  K --> C
  K --> X
```

1. **評估**：把工具的 GitHub 連結貼給 agent，`omnikit-eval` 會查 GitHub 現況、對照槽位情境，寫成一張工具卡。
2. **產生**：commit 時 git hook 驗證名冊並重新產生 marketplace 清單；推到 main 之後，GitHub Actions 重建看板。
3. **同步**：`install.ps1` 把規則（安全底線 + 你選的 profile）、skills、MCP、權限接到 Claude Code 與 Codex；之後 commit 或 pull 動到這些檔案時，git hook 會自動再同步。

想看每個部分、每個檔案在做什麼，打開[互動架構地圖](https://b40609.github.io/OmniKit/map.html)：每個檔案都有白話說明，另有 3 條逐步導覽（評估新工具、改規則、第一次安裝）。建議用電腦開。

<a href="https://b40609.github.io/OmniKit/map.html">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/assets/map-dark.png">
  <img alt="OmniKit 互動架構地圖：名冊、評估新工具、檢查與產生、對外成品、接到你的電腦、雲端檢查與部署，以及 GitHub、Claude Code、Codex 之間的連線" src=".github/assets/map-light.png">
</picture>
</a>

## 安裝會改動哪些地方

| 位置 | 做什麼 |
|---|---|
| `%LOCALAPPDATA%\Programs\` | 安裝固定版本的 skillshare、uv、gh、gitleaks；比對 SHA256，不改 PATH。這台已經有 uv、gh 就沿用 |
| `data/omnikit.yaml` | fork 出來的 repo，改成你的 `repo`、`owner`、`marketplace`，`profile` 改回 `default`，並重新產生 marketplace 清單 |
| `~/.claude/CLAUDE.md` | 在開頭加一段受管區塊，import `data/rules/baseline.md` 與你選的 `data/profiles/<名稱>/AGENTS.md`；其他內容不動 |
| `~/.codex/AGENTS.md` | 換成底線與 profile 接在一起的副本；第一次接上時，原本的內容先備份成 `AGENTS.md.pre-omnikit` |
| `%LOCALAPPDATA%\omnikit\` | `profile.json` 記這台選的 profile；`rules\AGENTS.md` 是給 Codex 的副本，由 `engine/scripts/profiles.py` 產生 |
| `~/.claude/skills`、`~/.agents/skills` | 由 skillshare 同步 `engine/skills` 裡的 skills |
| `~/.claude.json`、`~/.codex/config.toml` | 合併寫入 `data/mcp/servers.yaml` 的 MCP server，不動其他設定；`config.toml` 結尾另加一段 `[[hooks.Stop]]` 開新對話提醒，寫入前驗證其他設定沒被動到 |
| npm 全域套件 | 安裝 `data/mcp/packages.txt` 指定的固定版本 |
| `~/.claude/settings.json` | 把 `data/harness/claude-allow.txt` 的規則補進 `permissions.allow`，只增不刪；在 `hooks.Stop` 加上開新對話提醒（`engine/scripts/session_nudge.py`） |
| 這個 repo | `core.hooksPath` 指到 `.githooks`：commit 前掃金鑰、驗證名冊；commit 或 pull 動到規則、profile、MCP、權限、提醒 hook 時自動同步 |
| `%LOCALAPPDATA%\omnikit\install-record.json` | 安裝紀錄：記下這台原本沒有、由 OmniKit 裝上的工具、npm 套件與權限規則，移除時只動這些 |

加上 `-Fresh` 會把 `~/.claude/CLAUDE.md` 受管區塊以外的舊規則移除（先備份成 `CLAUDE.md.pre-omnikit`），適合想讓 OmniKit 的規則完全取代舊規則的人。

## 移除

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\uninstall.ps1
```

會先列出要做的事，確認後才動手：

- 規則、skills、MCP、權限、git hook 還原成安裝前的樣子，安裝前的備份會放回原位。
- 只移除安裝紀錄裡、由 OmniKit 裝上的工具與 npm 套件；安裝前就有的都保留。
- 加 `-KeepTools` 只還原設定、保留工具；加 `-Yes` 不詢問直接移除。
- repo 資料夾不會刪，不需要的話自己刪掉即可。

## 日常使用

### 換 profile

```powershell
uv run engine/scripts/profiles.py --show          # 這台現在用哪個
uv run engine/scripts/profiles.py --set <名稱>    # 換成 data/profiles/<名稱>，Claude Code 與 Codex 一起換
```

換完開新的 session 才生效。還沒選過的電腦會一直用 `default`，並在安裝與同步時提醒。

### 評估新工具

在 Claude Code 或 Codex 裡直接說：

```text
幫我評估 https://github.com/<owner>/<repo>
這個跟現在用的比一下
每週彙整
```

| 層 | 成本 | 做什麼 |
|---|---|---|
| 0 | 免費 | GitHub 現況、名冊比對、硬性門檻、安全掃描 |
| 1 | 便宜 | 讀 README，對照槽位情境寫卡片，狀態是「待評估」 |
| 2 | 實測 | 拿槽位情境實際跑一遍並評分，點名才跑；紀錄放在 `data/evals/` |

### 改名冊

改完 `data/` 直接 commit：pre-commit hook 會驗證名冊，並重新產生 marketplace 清單一起放進 commit。要手動檢查：

```powershell
uv run engine/scripts/validate.py
uv run engine/scripts/build.py --site _site
```

uv 不在 PATH 上的話，把 `uv` 換成 `& "$env:LOCALAPPDATA\Programs\uv\uv.exe"`。CI 會再檢查名冊、marketplace 清單是不是最新、看板能不能產生，並用 gitleaks 掃金鑰。

### 更新架構地圖

`engine/site/map.html` 是用 [Floorplan](https://github.com/haydenschmitty/floorplan) 在本機產生後匯出的，CI 不會重畫。`engine/` 有結構上的改動時，在裝了 Floorplan 的 Claude Code 裡說「更新 floorplan」，再匯出並 commit：

```powershell
node floorplan/serve.mjs --export engine/site/map.html
```

`floorplan/` 本身不進 git；換電腦後第一次要重畫整張地圖。

### 跟上原作者的更新

在你的 fork 頁面按 **Sync fork**，或在本機：

```powershell
git remote add upstream https://github.com/b40609/OmniKit.git   # 只要做一次
git pull upstream main
```

- `data/` 有衝突時，留你自己的版本。
- 兩份 marketplace 清單有衝突時，直接重新產生：`uv run engine/scripts/build.py --marketplace-only`。
- `engine/` 有更新時，重跑一次 `install.ps1`。

## 目錄結構

```text
data/                        資料：fork 後換成你的
  omnikit.yaml               看板與 marketplace 的公開設定
  slots.yaml                 槽位與情境範本
  tools/<id>.yaml            名冊，一個工具一張卡
  rules/baseline.md          安全底線，所有人都套用
  profiles/<名稱>/           個人規則（AGENTS.md）與真實情境（scenarios.yaml）；default 是沒選時的預設
  mcp/                       MCP server 定義與 npm 套件版本
  harness/                   Claude Code 免問的權限規則
  evals/                     實測紀錄
engine/                      引擎：不用改
  schema/                    名冊與槽位的 JSON Schema
  scripts/                   安裝、選 profile、驗證、產生看板與 marketplace、開新對話提醒（Claude Code 與 Codex）
  site/                      看板的樣式與程式，以及匯出的架構地圖（map.html）
  skills/omnikit-eval/       評估新工具的 skill
.claude-plugin/              Claude Code 的 marketplace（由名冊產生，不要手改）
.agents/plugins/             Codex 的 marketplace（由名冊產生，不要手改）
```

## 常見問題

<details>
<summary><b>裝好了，卻看不出有什麼不同？</b></summary>

安裝改的是規則、skill 與 MCP，畫面上不會多出東西，而且要開新的 session 才生效。照[確認接上了](#確認接上了)檢查一遍。預設 plugin 不會自動安裝，見[預設 plugin 要另外裝](#預設-plugin-要另外裝)。

</details>

<details>
<summary><b>會不會蓋掉我原本的設定？</b></summary>

不會直接蓋掉。`~/.claude/CLAUDE.md` 只加一段受管區塊；`~/.codex/AGENTS.md` 第一次接上時會先備份；MCP 與權限都是合併寫入。只有加上 `-Fresh` 才會移除 CLAUDE.md 的其他內容，而且也會先備份。完整清單見[安裝會改動哪些地方](#安裝會改動哪些地方)，不想用了隨時可以[移除](#移除)。

</details>

<details>
<summary><b>支援 macOS 或 Linux 嗎？</b></summary>

`install.ps1` 與 git hooks 目前只支援 Windows（PowerShell 5.1 或 7）。[只裝預設的 plugin](#只想裝預設的-plugin) 不受作業系統限制。

</details>

<details>
<summary><b>不想用某個預設工具怎麼辦？</b></summary>

把那張卡（`data/tools/<id>.yaml`）的 `status` 改掉並 commit，marketplace 與看板會跟著更新。已經裝好的 plugin 要自己移除。

</details>

<details>
<summary><b>公司電腦執行 skillshare 時「存取被拒」？</b></summary>

公司裝的防毒（例如 Trend Micro）可能擋下 `%LOCALAPPDATA%\Programs\skillshare\skillshare.exe`，這時 Codex 的規則、skills 與 MCP 都同步不了。Claude Code 的規則是直接 import repo 裡的檔案，不經過 skillshare，仍然會生效。請 IT 把這個執行檔加進例外，再重跑 `install.ps1`。

</details>

<details>
<summary><b>安裝跑到一半出錯怎麼辦？</b></summary>

`install.ps1` 可以重複執行，修好原因後再跑一次就好。找不到 npm 時會略過 MCP 套件並提示，裝好 Node.js LTS 再重跑。

</details>

## 回報問題

安裝或使用遇到問題，請開 [Issue](https://github.com/b40609/OmniKit/issues)。

## 致謝

OmniKit 建立在這些專案上：[skillshare](https://github.com/runkids/skillshare)（同步規則、skills 與 MCP）、[uv](https://github.com/astral-sh/uv)（執行 Python 腳本）、[gitleaks](https://github.com/gitleaks/gitleaks)（掃描金鑰）、[GitHub CLI](https://github.com/cli/cli)、[Floorplan](https://github.com/haydenschmitty/floorplan)（產生架構地圖）。

## 授權

[MIT](LICENSE)
