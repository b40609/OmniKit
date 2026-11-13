# 找來源槽位實測：WR1，firecrawl（2026-11-13）

第 2 層的第一次試跑：Claude 執行、Gemini 評審，評審跑在 T3 的子對話。起因是自我迭代的訊號（OmniKeep 收錄 `omnikeep:3b397bda2ad1`），第 1 層建議深入評估（`data/funnel/layer1/firecrawl.json`）。

## 要回答的問題

1. 找一手來源並附出處（WR1），Claude Code 內建的 WebSearch、WebFetch 夠不夠用？
2. 加上 firecrawl 的免金鑰 MCP，結果有沒有明顯變好，值不值得進兩週試用？

## 決策規則（實測前寫下）

- 槽位沒有現任，比的是「內建」對上「內建加 firecrawl」。兩組只差 MCP，其他設定一樣。
- 每個回答的客觀檢查點（評審逐條打開連結核對）：
  1. 每個結論都附連結。
  2. 連結是一手來源（官方文件、官方 repo、法規、論文），不是轉述的文章。
  3. 回答引用的原文或位置，打開連結找得到。
  4. 查不到的標「待驗證」，沒有證據的不寫成事實。
- 評審做兩兩比較，不打分數：不給它看組別，A、B 兩種順序各評一次，兩次結果一致才算一勝；不一致算平手。可以回「無法判斷」。
- firecrawl 組勝出的條件，全部要成立：
  1. 6 組（3 題 × 每題 2 次）裡贏 4 組以上。
  2. 檢查點 3 的通過率不比內建組低。
  3. firecrawl 的工具在一半以上的執行裡真的被叫用；沒被叫用就是「沒用到」，維持待評估，不算輸也不算贏。
- 其他情況都是 Keep：內建就夠，不多加一個雲端依賴。差距在 1 組以內算平手，也是 Keep。
- firecrawl 組的 token 多 50% 以上又沒有勝出：記下來，當成 Keep 的另一個理由。
- 勝出 → firecrawl 改 `trial`，兩週後再看；Keep → firecrawl 記 `rejected` 並寫理由，或沒用到時維持 `pending`。

## 題目

都是 OmniKit 文件裡標著「待驗證」的真實問題，不是合成題：

- Q1：Claude Code 的 `/doctor` 有沒有檢查規則檔（CLAUDE.md）的功能？檢查哪些項目？（`docs/proposals/2026-11-11-diagnose-advice.md:173,180`）
- Q2：OpenAI Codex 官方文件有沒有記載檢查或精簡 AGENTS.md 的功能？（同上，第 178 行）
- Q3：GitHub Agentic Workflows（gh-aw）建立的 pull request 為什麼預設不會觸發 CI？官方建議怎麼處理？（`docs/proposals/2026-11-13-self-iteration.md`）

## 設定

- 執行：`claude -p`（Claude Code 2.1.323），模型 Claude Sonnet 5.5。用 Sonnet 不用 Opus，是因為本週 Claude 用量已經過 80%。
  - 在空的暫存資料夾跑，`--setting-sources ""`、`--strict-mcp-config`，不載入使用者的規則、hook 與 plugin，兩組條件一樣。
  - 兩組都開 WebSearch、WebFetch；firecrawl 組另外接 `https://mcp.firecrawl.dev/v2/mcp`（免金鑰，只有 scrape、search、parse）。
  - 每題每組跑 2 次（研究建議 3 次；這次是第一次試跑，又受 Claude 用量限制，先跑 2 次，結論裡寫明）。
- 評審：T3 子對話，provider `antigravity`、模型 `gemini-4-hydrogen`，跟執行的 Claude 不同家族。評審拿到的回答去掉組別與工具名稱。

## 結果

原始資料在 `2026-11-13-web-sources-WR1/`：`out/` 是 12 次執行（回答、叫用的工具、token），`judge-1.json`、`judge-2.json` 是兩位評審的輸出，`key.json` 是組別對照表。

### 判定：沒用到，firecrawl 維持 `pending`

條件 3 不成立：firecrawl 的工具在 6 次執行裡只被叫用 1 次（Q1 第 2 次，scrape 一次），其他 5 次模型都只用內建的 WebSearch、WebFetch。照事先寫的規則，這是「沒用到」，不算輸也不算贏。

### 評審結果（兩個 T3 子對話，Gemini 4 Hydrogen，順序相反）

| 組 | 題 | 順序 1 | 順序 2 | 結果 |
|---|---|---|---|---|
| P1 | Q1 第 1 次 | firecrawl 組 | firecrawl 組 | firecrawl 組 |
| P2 | Q1 第 2 次 | firecrawl 組 | firecrawl 組 | firecrawl 組 |
| P3 | Q2 第 1 次 | firecrawl 組 | 平手 | 平手 |
| P4 | Q2 第 2 次 | firecrawl 組 | firecrawl 組 | firecrawl 組 |
| P5 | Q3 第 1 次 | 內建組 | 內建組 | 內建組 |
| P6 | Q3 第 2 次 | firecrawl 組 | firecrawl 組 | firecrawl 組 |

- firecrawl 組 4 勝、內建組 1 勝、1 平手；6 組裡 5 組兩種順序結果一致。
- 評審核對得到的引用：內建組 32／48 個連結（67%），firecrawl 組 31／40（78%）。
- **這 4 勝不能算在 firecrawl 頭上**：其中只有 P2 那次真的用了 firecrawl。兩組實際用的工具幾乎一樣，勝負來自同一套設定每次跑出的差異（例如 P1 勝的那次多抓了 commands 與 memory 兩頁）。換句話說，**同一個設定跑 2 次，就可能出現 4 比 1 的差距**。這是這次最重要的發現：每題 2 次太少，之後要照研究建議至少 3 次，勝出門檻也要把這個雜訊算進去。
- 評審理由裡指出的錯誤（找錯頁面、被截斷而漏讀）兩組都有，跟工具無關。

### 成本

| 組 | 每次平均輸入 token（含快取） | 每次平均輸出 token | 每次平均秒數 |
|---|---|---|---|
| 內建 | 約 3.5 萬 | 約 2,500 | 38 |
| firecrawl | 約 9.2 萬 | 約 2,550 | 41 |

firecrawl 組幾乎沒用到它的工具，輸入 token 卻多了約 1.6 倍。原因沒有查證，可能是多抓了頁面（P1 那次 WebFetch 9 次）加上工具定義；只有 6 次，不下結論。

### 這條流程本身（T3 加 Gemini 當評審）

- 可以用：`t3 thread start . - --provider antigravity --model gemini-4-hydrogen --worktree main --wait --json`，從這裡開子對話、等它跑完、拿回結果；兩個評審約 7 分鐘。子對話會留在 T3 側邊欄，可以點開看評審實際開了哪些網頁。
- T3 把 worktree 建在 T3 自己的資料夾（使用者目錄下的 `.t3\worktrees\OmniKit\`），這次沒有跳出跨目錄審批。
- 評審有照規則逐條打開連結核對，理由寫得具體；兩種順序結果大多一致，順序偏誤看起來不大（6 組裡 1 組不一致）。

### 過程中的疏失

- `--tools WebSearch,WebFetch` 沒有擋掉 Bash 與 Grep：有 4 次執行叫用了它們（在空的暫存資料夾裡，沒有影響外面）。兩組都有，對比較影響不大，但下次要用 `--disallowedTools` 明確擋掉。
- PowerShell 把 `t3` 的輸出用系統編碼存檔，中文變成亂碼；改用 `t3 thread show --json` 加 UTF-8 重讀才解決。
- 沒有檢查評審的 worktree 有沒有被改動（評審被要求唯讀，worktree 也跟這個 repo 分開）。

### 改成正式工具之後重算（2026-11-13）

試跑腳本改寫成 `engine/skills/omnikit-eval/scripts/layer2.py` 之後，把這次的資料補成它的格式（`spec.yaml`、`key.json`）重算，結果在 `result.json` 與 `verdict.json`：Keep，firecrawl 叫用率 17%（沒用到），而且這次沒有雜訊組，本來就不能判勝出。數字跟上面手算的一致（4 勝 1 負 1 平、核對得到 78% 比 67%）。輸入 token 合計：firecrawl 組約 55 萬、內建組約 21 萬。

改寫時順便實測到兩件事，已經寫進 `layer2.py`：

- WebSearch、WebFetch 在 Claude Code 2.1.323 是延遲載入的工具，要用 `--tools` 點名才拿得到；只給 `--tools` 又擋不住 Bash、Grep。所以兩個都要帶。
- 在使用者資料夾底下執行，Claude 會往上找到使用者的 CLAUDE.md（`_cheap.py` 的說明）；試跑時就是在使用者的暫存資料夾裡跑，可能讀到了。正式工具改在使用者資料夾外的中性目錄跑。

## 下一步

- firecrawl 維持 `pending`。要再測的話，題目要改成內建工具做不到的（例如要渲染 JavaScript 的頁面、要一次抓整站），否則模型不會去用它。
- 第 2 層的通用做法要改：每題至少 3 次，並先量「同一個設定跑兩次」的差距當雜訊基準，再訂勝出門檻。
