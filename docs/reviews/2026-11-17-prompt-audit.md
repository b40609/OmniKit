# `/doctor prompt-audit` 的結果與核對（2026-11-17）

怎麼跑的：Claude Code 2.1.326 無頭模式，`claude -p "/doctor prompt-audit" --model claude-sonnet-5-5 --effort medium --permission-mode plan`。plan 模式不能改檔，所以**什麼都沒改**。16 回合、2 分 47 秒、US$0.82（它自己回報的）。第一次跑失敗：Git Bash 把 `/doctor` 轉成了路徑，關掉路徑轉換才跑成，那次花了 US$0.09。

它的完整報告與提案 diff：`C:\Users\user\.claude-kai\plans\prompt-audit-jolly-metcalfe.md`。

範圍：使用者層的 `CLAUDE.md` 和它載入的 4 份 OmniKit 規則檔（`baseline.md`、`dispatch.md`、ryan 的 `AGENTS.md` 與 `dispatch.md`），以及 `~/.claude/skills/` 底下不是連結的 skill（caveman、omnikeep-setup、unslop、web-unblock）。連結到 OmniKit 的 skill 它沒讀。

## 逐項核對（我對過原檔）

| # | 它說的 | 核對結果 | 我的建議 |
|---|---|---|---|
| 1 | `omnikeep-setup/SKILL.md:115` 寫死 Kilo、OVHcloud 的限額數字，同檔第 109 行又說以卡片為準 | **對，但原始檔已經改好了**：OmniKeep repo 的 `skills/omnikeep-setup/SKILL.md` 今天改過（`52050d3`），裡面已經沒有這行。`~/.claude/skills/` 的是 11-06 的舊複本 | 不用照它的 diff 改；重新安裝 OmniKeep 的 skill，把舊複本換掉 |
| 2 | `web-unblock/SKILL.md:15` 寫死 Antigravity 的雜湊路徑 | 對（原文核對過） | 改成相對於 skill 資料夾的路徑。三份複本（`~/.claude`、`~/.agents`、`~/.gemini/config`）內容一樣，要一起改，或者只留一份來源 |
| 3 | `web-unblock` 用 Antigravity 的工具名（`read_url_content`、`search_web`、`view_file`） | 對（第 3、8、32、38 行） | 跟第 2 項一起改成不綁定特定 agent 的說法 |
| 4 | `caveman/SKILL.md:12` 列了一串禁止的開場白 | 對 | **不建議改**：caveman 是第三方的，改了更新時會被蓋掉。起手清單已經寫了它的回覆風格跟內建 Concise 重疊；要處理就決定要不要停用 caveman |
| 5 | `caveman/SKILL.md:16、18` 壓掉所有旁白 | 對 | 同第 4 項 |
| 6 | `AGENTS.md`「安全底線列出的項目之外，其他步驟都不用先問」跟「紅線」要先確認的條目互相矛盾 | **對**：紅線要求「移除未備份的模組前先確認」與操作實體桌面前取得同意 | 改成「安全底線與紅線列出的項目之外，其他步驟都不用先問」。這是你的規則，要你同意 |
| 7 | `AGENTS.md`「下載、安裝直接執行」對上 `baseline.md`「不執行來路不明的下載檔」 | 兩條可以並存，但字面上有張力 | 補一句「來源限官方套件管理器（npm、pip、winget）與官方發行頁」。安全相關，要你同意 |
| 8 | 殘留項目：「試用到 2026-11-28」、「過渡規則，RIA 上線後再決定」、ryan `dispatch.md` 的【待確認】三個 Claude 帳號的優先順序 | 對。試用日期還沒到期；【待確認】一直沒定 | 【待確認】那條請你定，或刪掉 |
| 9 | taste-skill「兩個都裝著」，但三個 skill 目錄都找不到 | **一半誤報**：它裝成 plugin（`~/.claude` 的 `taste-skill@taste-skill` 2.5.1）。但 Kai 帳號的設定目錄（`~/.claude-kai`）沒裝，用 Kai 開的對話叫不到 | 要在 Kai 帳號也用，就在那邊裝 |
| 10 | 規則要求呼叫 `t3_thread_organize`，但這個 session 沒有這個工具 | **誤報**：只有無頭模式沒有，T3 的對話裡有（剛才收件匣那條子對話就是自己用它結案的） | 不用改 |
| 11 | `~/.claude/CLAUDE.md` 和 `~/.claude-kai/CLAUDE.md` 內容一樣，規則被載入兩次 | 待驗證：這段 T3 對話裡我只看到一份 | 先不動 |
| 12 | `omnikit-weekly` 已經停用，卻還裝在兩個 skill 目錄，每次對話都付它說明文字的 token | 對（我這段對話的 skill 清單裡也看得到它） | 等統整第 7 節「兩週沒人用就刪」時一起拿掉；要提早，就把它的連結從 skill 目錄移掉（算刪除類，要你同意） |

OmniKit 自己的 `baseline.md` 與 `dispatch.md`：除了第 7 項的張力，沒有找到問題。

## 處理狀態（2026-11-18）

- 第 6、7 項：已改（`28627af`）。
- 第 1 項：在 OmniKeep 專案的對話重新安裝 skill。
- 第 2、3 項：已改（2026-11-18）：將 `~/.claude`、`~/.agents`、`~/.gemini/config` 下三份 `web-unblock/SKILL.md` 先備份為同資料夾的 `SKILL.md.bak-20261118`，第 15 行寫死路徑改為 `<this skill's folder>\scripts\fetch_unblock.py`（保留第 3 行 `description` 原樣），第 8、32、38 行的 Antigravity 專用工具名（`read_url_content`、`search_web`／`agent-browser --headed`、`view_file`）改為不綁定 agent 的通用說法；以 Python SHA-256 與 `fc /b` 比對三份完全相同，且三處的 `scripts\fetch_unblock.py` 皆存在。
- 第 4、5 項：不改 caveman 的檔。
- 第 9 項：Kai 帳號要用 taste-skill 時再裝。
- 第 12 項：等統整第 7 節「確認兩週沒人用之後刪掉停用的腳本」那次一起拿掉。
- 第 8 項：使用者沒有偏好，定為先用目前這段對話的帳號、額度用完照設定檔順序換下一個（`data/profiles/ryan/dispatch.md`）。

## 原本列給使用者決定的

1. 第 6、7 項的規則改法同不同意（改的是 OmniKit 的 `data/profiles/ryan/AGENTS.md`，規則版本要升）。
2. 第 8 項【待確認】的三個 Claude 帳號優先順序。
3. 第 2、3 項 web-unblock 要不要改、改哪一份當來源。
4. caveman 留不留（第 4、5 項）；第 12 項 omnikit-weekly 要不要提早拿掉。
5. 第 1 項：要不要重新安裝 OmniKeep 的 skill。
