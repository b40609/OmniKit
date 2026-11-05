# OmniKit v2 交接

日期：2026-11-05　前一段對話已滿，這份給新對話接手用。

## 目標

OmniKit v2 做給同事：裝完 → 可選的環境掃描與專案掃描 → 訪談 → 依名冊自動組出工具包 → 預覽 → 安裝 → 好用。之後持續只留有用的，有更好的選擇時通知，工作中也能主動建議，而且要比 Claude Code 做得更好。

核心主張：**不是幫你裝更多，而是只留證明有用的，而且三個 agent 一致。**

## 已完成

| 項目 | 位置 | 狀態 |
|---|---|---|
| Codex 實測（規則、skills、MCP 都讀得到） | 對話紀錄；記憶 `codex-web-gpt-proxy.md` | 完成 |
| Codex 瘦身：112 → 32 個 skill，token 少約 27% | `~/.codex/config.toml`；備份 `config.toml.bak-skills-20261104-233502` | 完成 |
| usage.py 也統計 Codex 的 plugin | commit `e27c415`，已 push，CI 通過 | 完成 |
| 定位與競品初稿 | `docs/proposals/2026-11-05-positioning.md` | 已 commit（2026-11-05 收尾，未 push） |
| 四項研究：跨 agent 同步、推薦與安裝、評估規模化、RIA | `docs/v2/research.md`；證據在 `docs/v2/research/`；RIA 的完整報告不放公開 repo，存在 `C:\Users\user\Desktop\RIA-Rebuild\OmniKit-RIA查證報告-2026-11-05.md` | 已 commit（未 push） |
| BMAD 產品簡介 | `docs/v2/brief/`（brief、addendum、.memlog） | 草稿，已 commit（未 push） |
| BMAD PRD：39 條需求，已過三項審查並修正 | `docs/v2/prd/`（prd、addendum、.memlog、兩份審查）；`docs/v2/review-editorial.md` | 草稿，等 §0.1 的決定 |

## PRD §0.1 的決定

**已定案（2026-11-05）**：

- 第 1 題：試點期的實測用團隊情境。
- 第 2 題：名冊更新每週提醒一次，同事說「檢查更新」才連網，預覽後才套用。
- 第 4 題：解凍「規劃與開發流程」槽位，RIA 不再當比較基準。

**還沒決定**：

- 第 3 題：回流用哪個非公開的共用資料夾。需要使用者指定；定了之後，PRD 才能改成 final。
- 第 5 題：客觀實測的每週 token 上限。需要使用者給數字。
- 第 6 到 9 題：主動建議提示的開啟門檻、試點期長度、本機模型槽位、試點名單。

## 下一步（依序）

1. **一次問完 §0.1 還沒決定的題目**：把答案寫進 PRD 與 `.memlog.md`；第 3 題定了就把 PRD 改成 final。
2. **先修現有的 4 個缺陷，再讓任何同事安裝**：
   - 同事的 `git pull` 會自動套用設定：`install.ps1:20-23` 設定 git hooks，`.githooks/sync-data.sh` 會直接重新套用（FR-1、FR-36）。
   - 免問核准用的是維護者的同意：`data/harness/claude-allow.txt:5`、`data/mcp/servers.yaml:23`（FR-10）。
   - Codex 的規則被整份換掉：`engine/scripts/profiles.py:189-203`。要改成受管區塊（FR-10）。
   - 使用者改過的 MCP 參數會被改回：`engine/scripts/agents.py:380-388`。要加帳本雜湊（FR-10）。
3. **階段 0a（約 2 週）**：做評估漏斗的批次工具（FR-22 到 FR-24）、安裝前檢查（FR-35）與 doctor。
4. **階段 0b（4 到 6 週）**：用漏斗處理 active 槽位與訪談會用到的槽位；找資料分析的候選工具。名冊目前沒有任何資料分析相關的卡片。
5. **同時開發** v2.0 其他需求。分組見 PRD §6.1。
6. **調整 `4a4fc38` 的行為**：另一個 session 已推上「不評估就不裝 omnikit-eval」。PRD 的 FR-37 要求個人週報跟訪談第 5 題脫鉤。

## 要實測才能確定的

- Antigravity 的 hook 訊息，使用者看不看得到。
- `agy` 讀取 skill 的位置：`~/.agents/skills`，還是 `~/.gemini/antigravity-cli/skills`。
- 隔離環境：這台有 Windows Sandbox；WSL2 要確認。
- Codex 的 `tool_suggest.discoverables` 能不能觸發原生的安裝建議。

## 不要重做

- 四項研究都已完成，關鍵主張也抽查過原始碼與論文。直接用 `docs/v2/research.md`。
- Codex 已經實測過。Codex 連不上時，先看 Codex Web GPT（127.0.0.1:17841）有沒有在跑，見記憶 `codex-web-gpt-proxy.md`。
- BMAD v6.12.4 的流程已經跑過，對應 commit `bab9082`。之後要更新 PRD，照 bmad-prd 的 Update 模式做：先讀 `.memlog.md`，再改，並把改動寫回 memlog。

## 注意

- OmniKit 是公開 repo。同事的個人資料、RIA 的內部細節都不要 commit。
- push 只在使用者明確指示時做。
