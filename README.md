# OmniKit

讓你的 agent 設定自己汰舊換新，每個決定都有理由。

**[槽位看板 →](https://b40609.github.io/OmniKit/)**

OmniKit 是給 Claude Code 與 Codex 用的工具名冊。每一種需求是一個「槽位」（前端設計、審查、記憶、瀏覽器……），每個槽位配幾個真實情境；每個工具一張卡，記下狀態與決定的理由。新工具進來時，拿槽位的情境跟現任比，比贏了才換。

名冊是唯一來源，其他東西都由它產生或同步：

- 槽位看板：部署在 GitHub Pages，main 有新 commit 就重新產生
- plugin marketplace：Claude Code 與 Codex 各一份，收錄狀態是「預設」的 plugin
- 規則、skills、MCP、權限：由 `install.ps1` 同步到 Claude Code 與 Codex 兩邊

## 怎麼用

依你想投入的程度選一種。

### 1. 看看板

打開[槽位看板](https://b40609.github.io/OmniKit/)，看每個槽位現在用什麼、試過什麼、為什麼。卡片的「原始資料」連回 `data/tools/` 裡的那張卡。

### 2. 安裝預設的 plugin

不用 clone，也不會動到你的其他設定。先把 OmniKit 加成 marketplace：

| | 指令 |
|---|---|
| Claude Code | `/plugin marketplace add b40609/OmniKit` |
| Codex | `codex plugin marketplace add b40609/OmniKit` |

再裝想要的 plugin，例如 frontend-design：

| | 指令 |
|---|---|
| Claude Code | `/plugin install frontend-design@omnikit-b40609` |
| Codex | `codex plugin add frontend-design@omnikit-b40609` |

目前收錄哪些，看板的「安裝預設的 plugin」區塊有最新清單。

### 3. 自己架一份（Windows）

想用 OmniKit 管你自己的設定，就 fork 一份，換成你的資料：

1. Fork 這個 repo，clone 到自己的電腦。
2. 改 `data/omnikit.yaml` 的 `repo`、`owner`、`marketplace`，換成你的帳號。
3. 改 `data/rules/AGENTS.md` 與 `data/slots.yaml`。現在寫的是原作者的規則與專案情境，不改的話會原封不動套到你的 agent 上。
4. 執行安裝（可以重複執行）：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File engine\scripts\install.ps1
   ```

5. 開啟 fork 的 GitHub Pages，來源設成 GitHub Actions，看板就會部署：

   ```powershell
   gh api -X POST repos/<你的帳號>/OmniKit/pages -f build_type=workflow
   ```

需要：Windows、git、Node.js LTS（MCP 用）。

#### install.ps1 會改你電腦上的這些東西

| 位置 | 做什麼 |
|---|---|
| `%LOCALAPPDATA%\Programs\` | 安裝固定版本的 skillshare、uv、gh、gitleaks；比對 SHA256，不改 PATH。這台已有 uv、gh 就沿用 |
| `~/.claude/CLAUDE.md` | 在開頭加一段受管區塊，import `data/rules/AGENTS.md`；其他內容不動 |
| `~/.codex/AGENTS.md` | **整份覆寫**成 `data/rules/AGENTS.md` 的副本；原本有內容的話先自己備份 |
| `~/.claude/skills`、`~/.agents/skills` | 由 skillshare 同步 `engine/skills` 裡的 skills |
| `~/.claude.json`、`~/.codex/config.toml` | 合併寫入 `data/mcp/servers.yaml` 的 MCP server，不動其他設定 |
| npm 全域套件 | 安裝 `data/mcp/packages.txt` 指定的固定版本 |
| `~/.claude/settings.json` | 把 `data/harness/claude-allow.txt` 的規則補進 `permissions.allow`（只增不刪） |
| 這個 repo | `core.hooksPath` 指到 `.githooks`：commit 前掃金鑰、驗證名冊；commit 或 pull 動到規則、MCP、權限時自動同步 |

加上 `-Fresh` 會把 `~/.claude/CLAUDE.md` 受管區塊以外的舊規則移除（先備份成 `CLAUDE.md.pre-omnikit`），只在這台第一次接上 OmniKit 時用。

## 評估新工具

`engine/skills/omnikit-eval` 是評估用的 skill。裝好之後，在 Claude Code 或 Codex 貼上 GitHub 連結說「幫我評估」就會開始。

- 第 0 層（免費）：GitHub 現況、名冊比對、硬性門檻、安全掃描
- 第 1 層（便宜）：對照槽位情境寫卡片，狀態是「待評估」
- 第 2 層（實測）：拿槽位情境實際跑一遍，點名才跑；紀錄放在 `data/evals/`

## 改名冊

改完 `data/` 直接 commit：pre-commit hook 會驗證名冊，並重新產生 marketplace 清單一起放進 commit。要手動檢查：

```powershell
uv run engine/scripts/validate.py
uv run engine/scripts/build.py --site _site
```

CI 會再檢查名冊、marketplace 清單是不是最新、看板能不能產生，並用 gitleaks 掃金鑰。

## 目錄

```text
data/                        資料：fork 後換成你的
  omnikit.yaml               看板與 marketplace 的公開設定
  slots.yaml                 槽位與情境
  tools/<id>.yaml            名冊，一個工具一張卡
  rules/AGENTS.md            Claude Code 與 Codex 共用的規則
  mcp/                       MCP server 定義與 npm 套件版本
  harness/                   Claude Code 免問的權限規則
  evals/                     實測紀錄
engine/                      引擎：不用改
  schema/                    名冊與槽位的 JSON Schema
  scripts/                   安裝、驗證、產生看板與 marketplace
  site/                      看板的樣式與程式
  skills/omnikit-eval/       評估新工具的 skill
.claude-plugin/              Claude Code 的 marketplace（由名冊產生，不要手改）
.agents/plugins/             Codex 的 marketplace（由名冊產生，不要手改）
```
