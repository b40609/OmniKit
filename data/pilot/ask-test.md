# 問法庫第 0 版：實測步驟

要回答的問題：`omnikit-ask` 有沒有讓你少修正幾輪、結果比較滿意？沒有就刪掉沒用的條目，或整個不做。

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

Codex 或 Antigravity（共用 `~/.agents/skills`）：

```powershell
Copy-Item -Recurse OmniKit\engine\skills\omnikit-ask "$env:USERPROFILE\.agents\skills\omnikit-ask"
```

裝完開新的對話，說「我不知道怎麼問：〔狀況〕」，它應該叫用問法庫。沒叫用就記一筆「沒被叫用」，然後改用明確的叫法：Claude Code 打 `/omnikit-ask 〔狀況〕`；其他 agent 說「用 omnikit-ask 這個 skill：〔狀況〕」。

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
