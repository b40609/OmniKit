# 工作階段管理槽位實測：S1（2026-11-09）

## 要回答的問題

T3 Code 開的 Claude 對話，會不會跟桌面版一樣載入 OmniKit 的規則、skills 與 hooks？這一項不過，T3 就不用往下比 S2 到 S5。

## 決策規則（實測前寫下）

- 對話紀錄裡要看得到：全域 CLAUDE.md、baseline 的規則版本 `2026-11-04-3`、ryan 的 AGENTS.md、OmniKit 與 claude-mem 的 skills、claude-mem 的 SessionStart hook。
- 全部看得到：S1 通過。缺任何一項：S1 不過，T3 不能接下 Claude 的工作。
- OmniKit 的 Stop 提醒（`engine/scripts/session_nudge.py`）只在跨過 100k tokens 或成功 git push 時才輸出；沒觸發不算失敗，另外記成未驗證。

## 設定

- 對象：T3 Code 0.1.7（Beta），provider 是 claudeAgent。
- 提示：「你載入了哪些規則？列出 baseline.md 的規則版本。」由使用者在 T3 送出。
- 比對基準：同一天桌面版在 OmniKit 的對話紀錄（entrypoint `claude-desktop`，Claude Code 2.1.317）。
- 證據來源：`~/.claude/projects/` 底下的對話紀錄 JSONL，看 attachment 的 type 與 hookName；只讀這些標記，不讀對話內容。

## 結果

| 項目 | T3 Code | 桌面版 |
|---|---|---|
| entrypoint、Claude Code 版本 | `t3-code`、2.1.319 | `claude-desktop`、2.1.317 |
| instructions 含 `baseline.md`、`2026-11-04-3`、ryan 的 AGENTS.md | 有 | 有 |
| skill 清單含 omnikit-eval、caveman、claude-mem、graphify | 有 | 有 |
| SessionStart hook（`claude-mem hook claude-code context`） | hook_success、hook_system_message、hook_additional_context 各 1 | 同 |
| Stop hook（OmniKit 提醒） | 沒有紀錄 | 只在跨過 100k、200k 時各 1 筆 |
| 模型回答的規則版本 | `2026-11-04-3`（使用者截圖） | — |

判定：**S1 通過**，Stop hook 未驗證。

## 未驗證與注意事項

- Stop hook：跟 claude-mem 的 hook 讀的是同一份 `~/.claude/settings.json`，應該有載入，但要等 T3 的對話跨過 100k 或 git push 才看得到。
- hook 訊息（systemMessage）會不會顯示在 T3 介面，還沒確認；不顯示的話，OmniKit 的「該開新對話」提醒在 T3 裡看不到，會影響 S4。
- 這次的 thread 選了「No project」，跑在 `~/.t3/scratch/2026-11-09-baseline-md-bddd8bff`；claude-mem 把它當新專案（「This project has no memory yet」）。做正事要先選專案，記憶才會累積。
- 只測了 Claude；Codex、Antigravity 在 T3 裡會不會載入各自的 OmniKit 規則（`~/.codex/AGENTS.md`、`~/.gemini/GEMINI.md`）還沒測。

## 下一步

試用到 2026-11-23，期間用真實工作觀察 S2 到 S5，到期時跟內建的工作階段管理比（槽位 `session-management` 的答案；細節在 [2026-11-11-builtin-features.md](2026-11-11-builtin-features.md)），再決定 T3 要不要接下 Claude 的工作。
