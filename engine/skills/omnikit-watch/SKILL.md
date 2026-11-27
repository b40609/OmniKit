---
name: omnikit-watch
description: 範圍 C 外部競品與收錄交叉檢視：從 OmniKeep 近期手動收錄或指定 GitHub 專案出發，經兩段降噪漏斗、gh api 與一手原始碼檢核，產出含反例、改判條件與五選一處置的決策報告。僅在手動輸入 /omnikit-watch 或每週排程明確呼叫時啟用。Scope-C external competitor cross-check against active projects.
argument-hint: "[--days 7 | <github-url-or-owner/repo> [專案名]]"
disable-model-invocation: true
---

# /omnikit-watch：範圍 C 外部競品與收錄交叉檢視

> 本 skill 設為 `disable-model-invocation: true`（Claude Code 常駐 0 bytes，不佔自動預算棘輪；並已附 Codex `agents/openai.yaml` `allow_implicit_invocation: false`，Antigravity 與 Codex 是否完全移出清單待驗證）。完整規範見 `docs/scope-c-competitor-watch.md`。

## 執行步驟

### 1. 判斷觸發模式並跑確定性前置漏斗

腳本位置：`engine/scripts/competitor_watch.py`（若在非 OmniKit 目錄，先從 `~/.omnikit/config.json` 讀 `repo` 路徑）。

- **每週定時／手動全盤檢視**（無參數或帶 `--days N`）：
  ```bash
  uv run <OmniKit>/engine/scripts/competitor_watch.py scan --days 7
  ```
- **丟特定專案即時對決**（參數包含 GitHub URL 或 `owner/repo`）：
  ```bash
  uv run <OmniKit>/engine/scripts/competitor_watch.py target "<url-or-owner/repo>" --project "<可選專案名>" --note "<使用者提問>"
  ```

### 2. 深挖最多 3 項（一手原始碼 + 反例）

對前置漏斗產出的深挖標的（**嚴格上限 3 項**；若 0 項則誠實回報本期無需動作並結束）：
1. 核對 `gh api` 實測星數、授權、最新 release、最後 push 與查證日期（不抄貼文或二手轉述）。
2. 檢視關鍵原始碼（`gh api repos/<o>/<r>/contents/...` 或淺層克隆至暫存區），對照我方對應專案的實際程式碼與 `NOW.md`。
3. 若該標的為純文字敘述且牽涉同類開源生態，必要時補用 `omnikit-research` 檢查是否有更強的同類主競品。

### 3. 反迎合結案（強制五選一，禁建 pending 墳場）

每項深挖標的必須具備四要素，缺一不可：
1. **一手證據對照**：附 `owner/repo`、實測星數與日期、檢視過的原始檔與我方對應檔案（`file:line`）。
2. **至少 1 條反例／適用邊界**：明確寫出弱點、Windows 環境風險或為何現任可能更好（不得順著使用者丟出的工具迎合吹捧）。
3. **可檢驗的改判條件**：寫明未來出現什麼客觀事實才需要重審。
4. **五選一處置**（必擇一，嚴禁留 `pending`）：
   - `adopt_or_integrate`（直接導入／改接）
   - `steal_pattern`（只借鏡關鍵模式）
   - `replace_or_retire`（取代／退役我方過重實作）
   - `watch_with_trigger`（帶明確觸發條件的觀望）
   - `dismiss_with_evidence`（附證據排除）

### 4. 重大改向升級規則

若結論涉及推翻某專案核心架構或入口設計，只提出建議與風險，**不直接改碼**，改觸發 OmniKit 兩階段防迎合盲審（開在 `No project` 隔離記憶）與跨家對等審查。
