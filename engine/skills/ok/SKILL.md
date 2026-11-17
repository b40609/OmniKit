---
name: ok
description: OmniKit 的總入口選單。只在使用者明確輸入 /ok 或 $ok（後面可以接 ask、交接等子選項）時使用；使用者單純回覆「ok」「好」表示同意時不要用。Menu entry point for OmniKit; use only when the user types /ok or $ok.
argument-hint: "[ask|交接|調研|分派|設定] [你的狀況]"
disable-model-invocation: true
---

# OmniKit 選單

使用者打的是 `/ok`（Claude Code、Antigravity）或 `$ok`（Codex），後面的字是參數：$ARGUMENTS

依參數的第一個詞決定做什麼。比對時不分大小寫，中英文都算。

| 第一個詞 | 做什麼 |
|---|---|
| （沒有參數） | 列出下面的「主選單」，請使用者回一個編號 |
| `ask`、`問`、`問法` | 問法庫。後面還有字，就把那些字當成使用者的狀況，直接照 `omnikit-ask` 做；後面沒有字，就列出「問法庫選單」 |
| `handoff`、`交接`、`接手` | 照 `omnikit-handoff` 做，後面的字一併交給它 |
| `research`、`調研` | 照 `omnikit-research` 做 |
| `dispatch`、`分派` | 照 `omnikit-dispatch` 做 |
| `setup`、`設定` | 照 `omnikit-setup` 做 |
| 其他任何字 | 當成使用者的狀況，照 `omnikit-ask` 做 |

「照某個 skill 做」：Claude Code 用 Skill 工具叫用它；其他 agent 讀同一層資料夾裡的 `../<skill 名稱>/SKILL.md`，照裡面的步驟做。

## 主選單

原樣列出，不要加說明：

```
1. 問法庫：卡住、不知道怎麼開口
2. 交接：把做到一半的工作交給新對話，或照交接檔接手
3. 調研：查業界做法、找同類工具、比較方案
4. 分派：派子任務給別的模型或帳號
5. 設定：建立或修改我的 OmniKit 設定
```

回 1 就列「問法庫選單」；回 2 到 5 就照對應的 skill 做。

## 問法庫選單

讀 `../omnikit-ask/SKILL.md` 的「索引」，依索引裡的類別順序編號，每類一行，例如：

```
1. 前端與畫面
2. 操作流程與功能入口
3. 除錯
...
10. 拆任務、排順序、複盤
直接打字描述也可以。
```

使用者回類別編號後，列出那一類的情境（照索引原文，編號從 1 開始），最後一行加「都不像：直接描述你的狀況」。使用者再回編號，就把那一條當成已經對到的情境，從 `omnikit-ask` 的第 2 步（讀那一類的檔案）開始做。

選單只列編號與名稱，不要先解釋每一項；使用者要的是少打字。
