---
name: omnikit-watch
description: 巡檢 OmniKeep 近期手動收錄或指定 GitHub 專案，對照各專案 NOW.md 與一手原始碼，產出全景分組表、反例與五選一處置。使用者說「巡一下 OmniKeep」「看 OmniKeep 新連結」「分析 OmniKeep 收錄」「跟專案比對」或打 /omnikit-watch 時使用；非競品／收藏對照任務不觸發。Cross-checks OmniKeep captures against active projects.
argument-hint: "[--since-last | --days 7 | <github-url-or-owner/repo> [專案名]]"
---

# /omnikit-watch：外部競品與 OmniKeep 收錄交叉檢視

> 通用設計：任何安裝 OmniKit＋OmniKeep 的使用者皆可開箱使用。腳本自動掃描本機 `~/.omnikit/status/*/NOW.md`（與無帳號模式 `~/.omnikit/local-status/*/NOW.md`）推導專案領域關鍵詞，亦可透過個人設定檔 `~/.omnikit/watch.yaml` 自訂專案關鍵詞與 DB 路徑。完整規範見 `docs/scope-c-competitor-watch.md`。

## 手動觸發方式（三家 Agent 通用）

- **自然語言**：直接說「巡一下 OmniKeep」「看 OmniKeep 新連結」「分析我剛丟進 OmniKeep 的連結」。
- **斜線指令**：`/omnikit-watch`（預設增量看上次水位線之後）、`/omnikit-watch --days 7`、或 `/omnikit-watch <github-url> [專案名]`。

## 執行步驟

### 1. 判斷觸發模式並跑確定性前置漏斗

腳本位置：`engine/scripts/competitor_watch.py`（若在非 OmniKit 目錄，先從 `~/.omnikit/config.json` 讀 `repo` 路徑）。

- **增量巡檢（預設／每週排程／手動清收錄）**：
  ```bash
  uv run <OmniKit>/engine/scripts/competitor_watch.py scan --since-last
  ```
  - 若想固定回看 N 天：`uv run <OmniKit>/engine/scripts/competitor_watch.py scan --days 7`
  - **結案後才推進水位線**（確認分析已交付給使用者後，補跑 `--since-last --mark-seen --no-gh`，避免中途失敗遺漏未處理連結）。
- **丟特定專案即時對決**（參數包含 GitHub URL 或 `owner/repo`）：
  ```bash
  uv run <OmniKit>/engine/scripts/competitor_watch.py target "<url-or-owner/repo>" --project "<可選專案名>" --note "<使用者提問>"
  ```

### 2. 呈現兩層輸出（Layer A 全景 ＋ Layer B Top 3 深挖）

1. **Layer A（30 秒全景分組表）**：把本次新收錄依專案歸類為「值得深挖／借鏡模式／已排除或踩雷」，讓使用者一眼掃完所有關聯連結。
2. **Layer B（嚴格上限 3 項一手原始碼深挖；若 0 項則誠實回報無需動作）**：
   - 核對 `gh api` 實測星數、授權、最新 release、最後 push 與查證日期（不抄貼文或二手摘要）。
   - 檢視關鍵原始碼（`gh api repos/<o>/<r>/contents/...` 或淺層克隆至暫存區），對照我方對應專案的實際程式碼與 `NOW.md`。
   - 必要時對關鍵缺口補用 `omnikit-research` 檢查是否有更強的同類主競品。

### 3. 反迎合結案（強制五選一，禁建 pending 墳場）

每項深挖標的必須具備四要素，缺一不可：
1. **一手證據對照**：附 `owner/repo`、實測星數與日期、檢視過的原始檔與我方對應檔案（`file:line`）。
2. **至少 1 條反例／適用邊界**：明確寫出弱點、Windows 環境風險或為何現任可能更好（不得迎合吹捧）。
3. **可檢驗的改判條件**：寫明未來出現什麼客觀事實才需要重審。
4. **五選一處置**（必擇一，嚴禁留 `pending`）：
   - `adopt_or_integrate`（直接導入／改接）
   - `steal_pattern`（只借鏡關鍵模式）
   - `replace_or_retire`（取代／退役我方過重實作）
   - `watch_with_trigger`（帶明確觸發條件的觀望）
   - `dismiss_with_evidence`（附證據排除）

### 4. 重大改向升級規則

若結論涉及推翻某專案核心架構或入口設計，只提出建議與風險，**不直接改碼**，改觸發 OmniKit 兩階段防迎合盲審（開在 `No project` 隔離記憶）與跨家對等審查。
