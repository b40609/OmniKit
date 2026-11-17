# 問法庫第 0 版：實測步驟

要回答的問題：`omnikit-ask` 有沒有讓你少修正幾輪、結果比較滿意？沒有就刪掉沒用的條目，或整個不做。

agent 自己能量的那一半已經做了：11 題有它與沒它的自動對照，平均 0.97 比 0.64（`docs/reviews/2026-11-17-ask-eval.md`）。它只看回覆照不照好的做法，量不到你用起來的感受，所以下面的實測還是要做。

實測的電腦：筆電與家裡的電腦（工具少、規則簡單，最接近同事的起點）。

## 判定規則（先寫好）

- **留下**：至少用 10 次，其中 6 次以上你認為比自己問的好（修正比較少，或結果比較滿意）。
- **說了卻沒被叫用**：10 次裡超過 2 次，就要改 skill 的說明文字，或改成一定要打指令。
- **個別條目**：用到的條目裡，你評為「沒比較好」的刪掉或重寫。兩週都沒用到的條目先留著，只記下來。
- 樣本很小，結論只代表你自己。給同事之前要有同事的紀錄。

## 安裝

需要 git。在終端機執行：

```bash
git clone https://github.com/b40609/OmniKit.git
```

Claude Code（Windows PowerShell）：

```powershell
Copy-Item -Recurse OmniKit\engine\skills\omnikit-ask "$env:USERPROFILE\.claude\skills\omnikit-ask"
```

Codex（`~/.agents/skills`）：

```powershell
Copy-Item -Recurse OmniKit\engine\skills\omnikit-ask "$env:USERPROFILE\.agents\skills\omnikit-ask"
```

Antigravity（`~/.gemini/config/skills`；它不讀 `~/.agents/skills`，2026-11-17 實測與官方文件都是這樣）：

```powershell
Copy-Item -Recurse OmniKit\engine\skills\omnikit-ask "$env:USERPROFILE\.gemini\config\skills\omnikit-ask"
```

想少打字，`ok`（選單入口）也一起複製，路徑同上，把 `omnikit-ask` 換成 `ok`。

裝完開新的對話，說「我不知道怎麼問：〔狀況〕」，它應該叫用問法庫。沒叫用就記一筆「沒被叫用」，然後改用明確的叫法：

| agent | 直接講狀況 | 跳出選單挑 |
|---|---|---|
| Claude Code | `/omnikit-ask 〔狀況〕` 或 `/ok ask 〔狀況〕` | `/ok ask` |
| Codex | `$omnikit-ask 〔狀況〕` 或 `$ok ask 〔狀況〕` | `$ok ask` |
| Antigravity | `/omnikit-ask 〔狀況〕` 或 `/ok ask 〔狀況〕` | `/ok ask` |

只打 `/ok`（Codex 是 `$ok`）會列出 OmniKit 的主選單（問法庫、交接、調研、分派、設定）。`/ok`、`/ok ask` 在 Claude Code 與 Antigravity 都實測過（2026-11-17）；Codex 的 `$ok` 照官方文件寫，還沒實測。

第一次用時，agent 可能會問能不能讀 skill 資料夾裡的檔案（各類情境分開存放）。選「一律允許」。不允許它也會回答，但只有索引層級的內容。

## 怎麼測

兩種都做。

**平常用（主要的資料）**：工作中卡住時，說「我不知道怎麼問：〔你的狀況〕」，照它的做法做完，然後在下面的表記一行。

**對照（至少 3 次）**：挑你真的遇到的 3 件事，建議就用你舉過的三個：

1. 前端畫面不滿意，不知道從何改起。
2. 畫面太雜，想合併功能與按鍵入口。
3. bug 修好又再發生。

每件事做兩次，起點要一樣：

```bash
git worktree add ../ask-test-a
```

```bash
git worktree add ../ask-test-b
```

- 在 a 開新對話，照你平常的方式問。
- 在 b 開新對話，說「我不知道怎麼問：〔同一件事〕」。
- 兩邊都做到你滿意或放棄為止，各記一行。

## 紀錄

每次一行。「修正幾輪」是你說了幾次「不對，要這樣」。

| 日期 | 電腦與 agent | 狀況 | 有沒有被叫用 | 對到哪一條 | 方式（平常問／問法庫） | 修正幾輪 | 滿意嗎（1 到 5） | 比自己問的好嗎 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | |

## 測完之後

把這張表填好，commit 到這個檔（或直接貼給 agent）。照判定規則決定留、改、刪。
