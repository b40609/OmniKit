# 安裝說明

[← 回到首頁](../README.md) · [使用指南](usage.md) · [子任務分派](dispatch.md) · [運作方式](architecture.md) · [維護名冊](maintainer.md)

- [直接安裝（同事用）](#直接安裝同事用不用-fork不用-github-帳號)
- [Fork 一份自己維護（維護者用）](#fork-一份自己維護維護者用)
- [只想裝預設的 plugin](#只想裝預設的-plugin)
- [安裝會改動哪些地方](#安裝會改動哪些地方)
- [維護者版與同事版](#維護者版與同事版)
- [移除](#移除)
- [疑難排解](#疑難排解)

## 直接安裝（同事用，不用 fork、不用 GitHub 帳號）

**需要：** Windows 11、[Git](https://git-scm.com/download/win)、[Node.js LTS](https://nodejs.org/)（MCP 用）、Claude Code、Codex、Antigravity 至少一個（裝了的都會接上）。不需要 GitHub 帳號，也不用開 Actions 或 Pages。

可以直接在 Claude Code、Codex 或 Antigravity 說「幫我安裝 OmniKit：https://github.com/b40609/OmniKit」，agent 會照下面的步驟做；也可以自己在 PowerShell 跑。

> **給幫忙安裝的 agent：** 第 2 步裝完、`install.ps1` 印出「下一步」之後，不用叫使用者開新對話：直接讀 `engine/skills/omnikit-setup/SKILL.md`，在同一段對話接著跟使用者做設定訪談，做完給新手導覽。

1. **Clone。** 放在之後不會搬動的淺層路徑（如 `$env:USERPROFILE\OmniKit`，避免 Windows 預設長路徑上限）：規則與 skills 會連到這個資料夾。建議直接指定最新穩定發行 tag（第一個 tag 由維護者建立；若直接 clone 預設分支，`install.ps1` 在同事版偵測到 `v*` 發行 tag 時也會自動切過去）：

   ```powershell
   git clone https://github.com/b40609/OmniKit.git "$env:USERPROFILE\OmniKit"
   cd "$env:USERPROFILE\OmniKit"
   # 若已知發行版號，也可直接：git clone --branch v0.1.0 https://github.com/b40609/OmniKit.git "$env:USERPROFILE\OmniKit"
   ```

2. **安裝。** 先加 `-WhatIf` 預覽，什麼都不會改；確認之後拿掉 `-WhatIf` 再跑一次。開始前會先做安裝前檢查（git、連得到 GitHub、npm、PyPI、proxy、防毒、PowerShell 執行原則），任一項不通過就停下來、列出處理方式，什麼都不寫入。完整清單見[安裝會改動哪些地方](#安裝會改動哪些地方)。

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 -WhatIf
   powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1
   # 指定特定發行 tag：加上 -Tag v0.1.0
   ```

   這樣裝的是同事版：不設 git hook，預設鎖定穩定發行 tag（維護者推 `main` 不會影響你）；讓 agent 免問就能用某個工具之前，會先問你。見[維護者版與同事版](#維護者版與同事版)。

3. **確認接上了。** 開一個新的 Claude Code 或 Codex session，問「OmniKit 規則版本與 profile 是什麼？」，版本跟 `data/rules/baseline.md` 開頭的一樣，就表示規則生效了。skill 與 MCP 怎麼檢查，見[使用指南的確認接上了](usage.md#確認接上了)。

4. **建立自己的 profile。** 開新的 session 隨便打一句，agent 會主動帶你設定（也可以直接說「幫我設定 OmniKit」），回答最多 6 題，看過預覽才寫入，見[建立自己的 profile](usage.md#建立自己的-profile)。profile 存在 `~/.omnikit/profiles/<名稱>/`，不在 repo 裡，不會被 commit 或上傳。

之後要更新到新發行版：`git fetch --tags`，先跑 `install.ps1 -Tag <新版本> -WhatIf` 預覽，確認後跑 `install.ps1 -Tag <新版本>` 套用（不帶 `-Tag` 時若尚未停在 tag 上會自動鎖定最新 `v*` tag）。`git fetch` 本身不會改任何設定。

## Fork 一份自己維護（維護者用）

想換成自己的名冊、看板與 marketplace，就 fork 一份。fork 會帶著原作者已經整理好的 160 多張工具卡，可以直接當起點。另外需要 GitHub 帳號。

1. **Fork 並開啟看板。** 按 repo 頁右上角的 **Fork**，接著在你的 fork 上：
   - **Actions** 分頁：fork 的 workflow 預設是關的，按 **I understand my workflows, go ahead and enable them**。
   - **Settings → Pages**：**Source** 選 **GitHub Actions**。

2. **Clone 你的 fork。**

   ```powershell
   git clone https://github.com/<你的帳號>/OmniKit.git
   cd OmniKit
   ```

3. **認識 profile。** agent 讀到的規則分兩層：
   - `data/rules/baseline.md` 是安全底線，所有人都套用：刪除、對外發送、付款前先確認，不碰金鑰。
   - profile 是個人層：`AGENTS.md` 寫語言、語氣、哪些事可以直接做；`scenarios.yaml` 寫評估工具用的真實情境，沒寫的槽位用模組檔（`data/modules/`）的範本。訪談產生的 profile 存在 repo 外的 `~/.omnikit/profiles/<名稱>/`；repo 裡的 `data/profiles/<名稱>/` 放 `default` 與維護者手寫、要跟著 repo 的 profile。兩邊同名時，repo 外的優先。

   不用先改檔案：先用 `default` 安裝（繁體中文、下載安裝前先問），裝好之後用[訪談](usage.md#建立自己的-profile)產生你自己的 profile（存在 repo 外的 `~/.omnikit/profiles/`，不進公開 repo）。想手寫也行：複製 `data/profiles/default` 成 `~/.omnikit/profiles/<你的名字>` 再改。

4. **安裝。** 加上 `-Edition maintainer`（指定一次就會記住）：commit 前驗證名冊、掃金鑰，commit 或 pull 後自動同步。已經有自己的 profile，就加上 `-ProfileName <名稱>`，一樣指定一次就會記住。

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 -Edition maintainer -WhatIf
   powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1 -Edition maintainer
   ```

   偵測到這是 fork 時，會自動把 `data/omnikit.yaml` 的 `repo`、`owner`、`marketplace` 改成你的、看板用的 `profile` 改回 `default`，並重新產生 marketplace 清單，避免跟原作者的撞名。

5. **推上去並開啟看板。** 若你自己的 fork 還沒開 `main` 分支保護，可直接推上預設分支；若已開分支保護（建議做法，見[維護名冊的發版與合併流程](maintainer.md#發版與合併流程分支保護prtag)），改開分支推 PR 等 CI 綠燈後再合併。進 `main` 之後，到 Actions 的「部署看板」手動觸發一次（`workflow_dispatch`），就會部署到 `https://<你的帳號>.github.io/OmniKit/`。

   ```powershell
   git checkout -b chore/init-fork
   git commit -am "chore: 改成自己的 OmniKit"
   git push -u origin chore/init-fork
   # 用 gh pr create 開 PR，等 CI 全綠後合併進 main
   ```

6. **確認接上了，再建立自己的 profile。** 跟上面直接安裝的第 3、4 步一樣。

之後跟上原作者的更新，見[維護名冊的跟上原作者的更新](maintainer.md#跟上原作者的更新)。

## 只想裝預設的 plugin

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

### 預設 plugin 要另外裝

`install.ps1` 不會把 OmniKit 加成 marketplace，也不會安裝看板上的預設 plugin。想用的話，照上面的指令裝。用自己的 fork 時：

- 把指令裡的 `b40609/OmniKit` 換成你的 fork。
- `@` 後面的 marketplace 名稱換成你 `data/omnikit.yaml` 的 `marketplace`，例如 `omnikit-<你的帳號小寫>`。
- 先 push 到 GitHub，marketplace 才讀得到最新的清單。

## 安裝會改動哪些地方

| 位置 | 做什麼 |
|---|---|
| `%LOCALAPPDATA%\Programs\` | 安裝固定版本的 uv、gh，以及維護者版才裝的 gitleaks；比對 SHA256，不改 PATH。這台已經有 uv、gh 就沿用 |
| `data/omnikit.yaml` | fork 出來的 repo，改成你的 `repo`、`owner`、`marketplace`，`profile` 改回 `default`，並重新產生 marketplace 清單 |
| `~/.claude/CLAUDE.md` | 在開頭加一段受管區塊，import `data/rules/baseline.md` 與你選的 profile 的 `AGENTS.md`（訪談產生的在 `~/.omnikit/profiles`，其他在 `data/profiles`）；路徑有空白時用 `\ ` 跳脫，不然 Claude Code 讀到空白就斷掉。其他內容不動 |
| `~/.codex/AGENTS.md` | 在開頭加一段受管區塊，放底線與 profile 接在一起的內容；原本的規則留在區塊外，照常生效，也先備份成 `AGENTS.md.pre-omnikit`。舊版整份換掉的，同步時換成只有區塊（規則內容一樣）；區塊被拿掉的話，同步時不加回去 |
| `~/.gemini/AGENTS.md`、`~/.gemini/GEMINI.md` | Antigravity 的規則：拆成 `AGENTS.md`（共用層）與 `GEMINI.md`（個人層）兩份受管區塊，強制檢查單檔 <= 24,000 bytes 避免靜默截斷；原本的內容留在區塊外，先備份成 `.pre-omnikit`。原地改寫，避免硬連結斷裂 |
| `~/.claude/skills`、`~/.codex/skills` | `engine/skills` 的每個 skill 用 Directory Junction 連結至 `~/.omnikit/current/engine/skills`（加 `--dev` 則直連工作區），零檔案複製與零雜湊帳本 |
| `~/.gemini/config/skills.json` | Antigravity 的（App、IDE、CLI 與 T3 Code 實例共用）：原生參照實體 skills 路徑，T3 自動同步至全部實例 |
| `~/.omnikit/claude-marketplace`、`~/.codex/config.toml`、`~/.gemini/config/plugins/omnikit/` | 無帳本掛載 `data/mcp/servers.yaml` 的 MCP server 與護欄 hooks：Claude 安裝本地薄 plugin `omnikit@omnikit-local`；Codex 用 `codex mcp` CLI 與 `config.toml` 的提醒類 hooks（不含確定性護欄）；Antigravity 與各 T3 實例放置三檔薄 plugin 宣告（不動頂層 `mcp_config.json`，保留 T3 自動標題生成） |
| `~/.omnikit/`（Windows 是 `%USERPROFILE%\.omnikit`；可用環境變數 `OMNIKIT_STATE_DIR` 改位置） | 不放 `%LOCALAPPDATA%`：從 Claude 桌面版這類 MSIX 封裝的 app 裡跑時，那裡新建的檔會被轉存成另一份；舊版留在 `%LOCALAPPDATA%\omnikit` 與轉存副本的，安裝、同步時會合併過來（原檔備份在 `legacy\`）。`current/` 是保護工作區免受穿透刪除的乾淨 git clone；`profiles/<名稱>/` 是訪談產生的 profile（個人資料，不在 repo 裡；移除時也不刪）；`profile.json` 記這台選的 profile；`edition.json` 記這台是維護者版還是同事版；`consent.json` 記你同意了哪些工具免問；`config.json` 記啟用的 agent 與明確列舉的額外設定目錄 |
| 舊版的 skillshare | 以前用 skillshare 接的電腦，重跑 `install.ps1` 會改由 OmniKit 接手，並拿掉 skillshare 設定裡 OmniKit 的部分；skillshare 本身不刪 |
| npm 全域套件 | 安裝 `data/mcp/packages.txt` 指定的固定版本 |
| `~/.claude/settings.json` | 把 `data/harness/claude-allow.txt` 的規則補進 `permissions.allow`（現行＋墓碑清單管理，只增不刪使用者自訂規則；同事版只補你同意過的工具），並設定 `statusLine`。hooks 優先透過本地薄 plugin `omnikit@omnikit-local` 提供（找不到 `claude` CLI 時才退回 `settings.json` hooks 備案） |
| 其他設定目錄 | 多帳號或啟動器另外指定的設定目錄（`CLAUDE_CONFIG_DIR`、`CODEX_HOME`、T3 Code 每個實例的 homePath、以及 `config.json` 明確列舉的額外目錄，`engine/scripts/homes.py` 找）：規則區塊、MCP、skills、權限規則與 hook 都跟預設目錄一樣寫。Claude 的其他設定目錄另外無帳本同步你自己裝在 `~/.claude` 的東西：`~/.claude/skills` 的第三方 skill 用 Directory Junction 連過去（`.bak-*` 這類備份、`.` 開頭的、無 `SKILL.md` 的系統目錄不連），`~/.claude/settings.json` 啟用中的第三方 plugin 用官方的 `claude plugin marketplace add` 與 `claude plugin install`（`CLAUDE_CONFIG_DIR` 指到那個目錄）裝進去，停用的不裝；設定檔其他欄位與金鑰不碰。之後在 `~/.claude` 新裝的，重跑 `uv run engine/scripts/sync.py sync`（只同步 plugin：`--plugins`）就補上 |
| T3 Code Antigravity 實例 | T3 Code 0.1.11 起原生同步 `~/.gemini` 的規則與 `skills.json`；OmniKit 會在每個實例補上 `config/plugins/omnikit/` 薄 plugin（確定性護欄與 MCP），並自動清理早期版本遺留的 `~/.omnikit/acp/` 轉接程式與 `binaryPath` 設定 |
| 這個 repo | 維護者版：`core.hooksPath` 指到 `.githooks`，commit 前掃金鑰、驗證名冊；commit 或 pull 動到規則、profile、skills、MCP、權限、提醒 hook 時自動同步。同事版不設 git hook |
| `~/.omnikit/install-record.json` | 安裝紀錄：記下這台原本沒有、由 OmniKit 裝上的工具、npm 套件與權限規則，移除時只動這些 |

加上 `-Fresh` 會把 `~/.claude/CLAUDE.md` 受管區塊以外的舊規則移除（先備份成 `CLAUDE.md.pre-omnikit`），適合想讓 OmniKit 的規則完全取代舊規則的人。

## 維護者版與同事版

兩版的規則、skills、MCP 接法都一樣，只差下面三件事。用 `install.ps1 -Edition maintainer` 或 `-Edition colleague` 指定，指定一次就會記住；沒指定過的話，分版之前就裝過的電腦是維護者版，其他都是同事版。

| | 維護者版 | 同事版（預設） |
|---|---|---|
| 版本來源 | 追蹤開發分支，透過分支＋PR＋CI 綠燈合進 `main` | 預設鎖定穩定發行 tag（`v*`），不受維護者推 `main` 影響；升級用 `git fetch --tags`＋`install.ps1 -Tag <版本>` |
| git hook | commit 前掃金鑰、驗證名冊；commit 或 pull 後自動同步。在 git worktree（例如 `.claude/worktrees/` 底下）裡只掃金鑰、驗證名冊，不同步，合進 main 後由主 checkout 同步 | 不設。pull 或 fetch 不會改任何設定；要套用更新，先跑 `install.ps1 -WhatIf` 預覽，再跑 `install.ps1` |
| 免問核准 | 照 `data/harness/claude-allow.txt` 與 `data/mcp/servers.yaml` 寫入，那是維護者自己同意的 | 每個工具先問你，同意了才寫入（預設否）。之後可以改：`uv run engine/scripts/sync.py approvals` 查看，`--grant <名稱>` 同意、`--revoke <名稱>` 撤回 |
| gitleaks | 裝，給 pre-commit 用 | 不裝 |

看這台是哪一版：`uv run engine/scripts/edition.py`。

## 移除

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\uninstall.ps1
```

會先列出要做的事，確認後才動手：

- 三個 agent 的規則、skills、MCP，以及權限、git hook 還原成安裝前的樣子，安裝前的備份會放回原位；只拿掉 OmniKit 的，其他的不碰。
- 只移除安裝紀錄裡、由 OmniKit 裝上的工具與 npm 套件；安裝前就有的都保留。
- 加 `-KeepTools` 只還原設定、保留工具；加 `-Yes` 不詢問直接移除。
- repo 資料夾與訪談產生的 profile（`~/.omnikit/profiles`）不會刪，重新安裝就能接著用；不需要的話自己刪掉即可。

## 疑難排解

<details>
<summary><b>安裝跑到一半出錯怎麼辦？</b></summary>

`install.ps1` 可以重複執行，修好原因後再跑一次就好。找不到 npm 時會略過 MCP 套件並提示，裝好 Node.js LTS 再重跑。

</details>

<details>
<summary><b>支援 macOS 或 Linux 嗎？</b></summary>

`install.ps1` 與 git hooks 目前只支援 Windows（PowerShell 5.1 或 7）。[只裝預設的 plugin](#只想裝預設的-plugin) 不受作業系統限制。

</details>

<details>
<summary><b>為什麼不用 skillshare 了？</b></summary>

以前規則、skills 與 MCP 是靠 [skillshare](https://github.com/runkids/skillshare) 同步。公司電腦的防毒（例如 Trend Micro 的「新出現的程式」偵測）會擋下從網路下載、很少人用或剛發布的程式：執行前跳通知要你按允許，要剛好盯著畫面才按得到，錯過就擋下。git hook 與 agent 在背景同步時常沒人看畫面，同步就失敗，放行之後也可能又被擋。

OmniKit 只支援 Claude Code、Codex 與 Antigravity 三個 agent，所以改由自己的無帳本同步腳本（`engine/scripts/sync.py`）直接接，用的是 uv 與 Python，不再需要另外放行。以前用 skillshare 接的電腦，重跑一次 `install.ps1` 就會改由 OmniKit 接手；skillshare 本身留著，不需要的話可以自己移除。

</details>
