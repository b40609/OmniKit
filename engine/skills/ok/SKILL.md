---
name: ok
description: OmniKit 的總入口選單。只在使用者明確輸入 /ok 或 $ok（後面可以接交接、調研等子選項）時使用；使用者單純回覆「ok」「好」表示同意時不要用。Menu entry point for OmniKit; use only when the user types /ok or $ok.
argument-hint: "[交接|調研|分派|設定|清點]"
disable-model-invocation: true
---

# OmniKit 選單

使用者打的是 `/ok`（Claude Code、Antigravity）或 `$ok`（Codex），後面的字是參數：$ARGUMENTS

依參數的第一個詞決定做什麼。比對時不分大小寫，中英文都算。

| 第一個詞 | 做什麼 |
|---|---|
| （沒有參數） | 列出下面的「主選單」，請使用者回一個編號 |
| `handoff`、`交接`、`接手` | 照 `omnikit-handoff` 做，後面的字一併交給它 |
| `research`、`調研` | 照 `omnikit-research` 做 |
| `dispatch`、`分派` | 照 `omnikit-dispatch` 做 |
| `setup`、`設定` | 照 `omnikit-setup` 做 |
| `capabilities`、`清點`、`能力` | 照 `omnikit-capabilities` 做 |
| `eval`、`評估` | 照 `omnikit-eval` 做（若有安裝） |
| 其他任何字 | 列出下面的「主選單」，並提醒：若需求還沒想清楚，可直接用內建 `/plan`（Antigravity 亦可用 `/grill-me`）讓 agent 先訪談對焦 |

「照某個 skill 做」：Claude Code 用 Skill 工具叫用它；其他 agent 讀同一層資料夾裡的 `../<skill 名稱>/SKILL.md`，照裡面的步驟做。

## 主選單

原樣列出，不要加說明：

```
1. 交接：把做到一半的工作交給新對話，或照交接檔接手
2. 調研：查業界做法、找同類工具、比較方案
3. 分派：派子任務給別的模型或帳號
4. 設定：建立或修改我的 OmniKit 設定
5. 清點：檢查這台電腦可用的 CLI、MCP 與端點
```

使用者回 1 到 5 就照對應的 skill 做。選單只列編號與名稱，不要先解釋每一項；使用者要的是少打字。
