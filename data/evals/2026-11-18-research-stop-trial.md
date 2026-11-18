# omnikit-research 新停止條件試用：T1 到 T3（2026-11-18）

使用者 2026-11-18 決定試用 `61f2f0b` 加的停法（`status --min-stars 1000`：★1,000 以上的 GitHub repo 連續 3 組沒有新的就停，標「長尾未飽和」；12 組還沒停先回報）。題目選收件匣裡 deja-vu 那一類：跨 coding agent 的對話紀錄搜尋、交接、壓縮後救回、共用記憶的工具。三次都由 Gemini 4 Hydrogen（high）照 skill 跑；停下來之後再多查 2 組當驗證。帳本與報告原文在 `2026-11-18-research-stop-trial/`。

## 結論

1. **12 組上限有用。** T1、T3 都在 12 組觸發，沒有像 P3 那樣一路跑到額度用完。T1 觸發後照規則問使用者，改成拆子題。
2. **★ 停法只在窄題上會觸發。** 寬題（T1 四個子領域）與記憶這種本身很大的領域（T3）到 12 組都還有新的 ★1,000 以上名字；窄題（T2 對話搜尋與交接）在第 9 組觸發。
3. **觸發了也會漏，而且同一個研究者多查 2 組抓不到。** T2 停在第 9 組，之後 2 組驗證都是 0；但另一次獨立調研（T1）找到 T2 範圍內的 entireio/cli（★5,343）。T3 也漏了 T1 找到的 cytostack/openwolf（★2,401）。P3 的 goplantuml（★2,082）是同一個模式。
4. **判相關要嚴。** T1 把大型 skill 合集（mattpocock/skills、ECC 這類）也記成相關，高星的合集會讓 ★ 停法一直停不下來；T2、T3 改成「拿不準的不記進帳本」之後才收斂得了。

## 三次的數字

| | 題目 | 組數 | 名字 | 停在哪 | 驗證 2 組的新 ★1,000 以上 | 另一次獨立調研補到的漏網 |
|---|---|---|---|---|---|---|
| T1 | 四個子領域合在一起 | 12＋2 | 538 | 第 12 組上限 | 1 個（NevaMind-AI/memU ★14,628） | — |
| T2 | 對話搜尋、檢視、交接遷移 | 9＋2 | 260 | 第 9 組 ★ 停法 | 0 | entireio/cli（★5,343） |
| T3 | 壓縮後救回、共用記憶 | 12＋2 | 309 | 第 12 組上限 | 0 | cytostack/openwolf（★2,401） |

主控逐一用 `sweep.py status --min-stars 1000` 重算過三本帳本，跟研究者的回報一致；T2 截到前 9 組時確實印「可以停」。

## 改了什麼

- `omnikit-research/SKILL.md` 停止一節加一句：★ 停法會漏，要求完整時派兩個研究者用不同的起手關鍵字各跑一次再合併；同一個研究者多查幾組抓不到漏網的。

## 順帶找到、跟 OmniKit 交接有關的（★1,000 以上，2026-11-18 gh api）

| 工具 | 星數、授權 | 做什麼 |
|---|---|---|
| entireio/cli | ★5,343、MIT | 掛在 git 流程上，把 agent 對話跟 commit 一起建索引 |
| cytostack/openwolf | ★2,401、AGPL-3.0 | 跨 Claude Code、Codex、OpenCode 的可攜專案記憶，附 token 計算 |
| jhlee0409/claude-code-history-viewer | ★2,324、MIT | 離線瀏覽、搜尋 30 多種 coding agent 的對話 |
| vshulcz/deja-vu | ★1,608、MIT | 跨 agent 的對話搜尋、交接、壓縮後救回（收件匣 11-17 已記） |
| yigitkonur/cli-continues | ★1,606、MIT | 讀 16 種 CLI 的對話紀錄，產生交接文件給另一個 agent 接手 |
| Dicklesworthstone/coding_agent_session_search | ★1,214 | 30 多種 agent 的統一索引與搜尋 |

這些只是調研結果，沒有實測；要用前照 `omnikit-eval` 先掃描。
