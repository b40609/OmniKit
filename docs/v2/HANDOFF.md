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
| BMAD PRD：39 條需求，已過三項審查並修正 | `docs/v2/prd/`（prd、addendum、.memlog、兩份審查）；`docs/v2/review-editorial.md` | final（2026-11-05 §0.1 九題全部定案） |

## PRD §0.1 的決定

九題都已定案（2026-11-05），細節在 PRD §0.1 與 `docs/v2/prd/.memlog.md`：

- 第 1 題：試點期的實測用團隊情境。
- 第 2 題：名冊更新每週提醒一次，同事說「檢查更新」才連網，預覽後才套用。
- 第 3 題：回流的匯出檔與提案放 Teams 試點頻道的檔案區。頻道連結不寫進公開 repo。
- 第 4 題：解凍「規劃與開發流程」槽位，RIA 不再當比較基準。
- 第 5 題：主動建議先靜默記錄 2 週，標註為「有用」的比例達 50% 以上才打開提示。
- 第 6 題：客觀實測每週 token 上限 2,000 萬，含快取讀取。
- 第 7 題：試點期 6 週。
- 第 8 題：本機模型先用評估漏斗找候選工具，有 E3 以上的候選再決定要不要開槽位。
- 第 9 題：試點前的閘門全部通過才開始；名單到時再確認，存在 repo 外。

## 下一步（依序）

1. ~~**一次問完 §0.1 還沒決定的題目**~~：2026-11-05 完成，PRD 已改成 final。
2. ~~**先修現有的 4 個缺陷**~~：2026-11-05 完成，自我測試全過。新增「維護者版／同事版」（`engine/scripts/edition.py`），兩版只差 git hook 與免問核准：
   - 同事版不設 git hook；萬一跑到 `sync-data.sh` 也只提醒、不同步（FR-1、FR-36）。`install.ps1 -Edition maintainer|colleague`，沒指定時分版前就裝過的電腦是維護者版。
   - 免問核准每個工具問本人，記在 `%LOCALAPPDATA%\omnikit\consent.json`；`agents.py approvals` 查看、`--grant`、`--revoke`（FR-10）。
   - Codex 規則改成受管區塊，原本的留在區塊外照常生效；舊版整份換掉的自動轉成只有區塊（FR-10）。兩版都用。
   - MCP 帳本：`agents.json` 記 OmniKit 管的欄位的雜湊；被改過、被移除、同名不是 OmniKit 的就停下來問，`agents.py resolve <名稱> --use-omnikit|--keep-mine`。Codex 原地更新，工具核准紀錄與使用者加的欄位留著（FR-10）。兩版都用。
   - 這台（維護者）唯讀比對：判斷為維護者版，三個 chrome_devtools 都會直接接手、沒有衝突；下次同步時 `~/.codex/AGENTS.md` 會轉成區塊格式。
3. **階段 0a（約 2 週）**：做評估漏斗的批次工具（FR-22 到 FR-24）、安裝前檢查（FR-35）與 doctor。
   - 這次沒做、之後要補的同步層項目：FR-36 的「檢查更新」流程（目前同事要先跑 `install.ps1 -WhatIf` 再跑 `install.ps1`）、受管區塊內容的雜湊（區塊裡的手改還是會被蓋掉）、`AGENTS.override.md` 偵測（FR-32）、Windows CI 跑 `install.ps1 -SelfTest`（FR-34）、架構地圖還沒有 `edition.py`。
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
