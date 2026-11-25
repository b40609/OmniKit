# 問法庫（omnikit-ask）修錯驗證與近兩週真實對話分歧過濾實測

日期：2026-11-25  
執行模型：`gemini-4-hydrogen`（`thought_level: xhigh`，`antigravity_ryan` 單線低併發，空白暫存工作區隔離記憶注入）  
跨家盲評：`Claude Sonnet`（`claude -p --setting-sources "" --tools ""`，奇偶交替雙盲位置消除順序偏誤）

---

## 一、`agent-notdone` 已知退步修錯驗證

- **問題根因**：先前將 `omnikit-ask` 第 1 步改為「能在工作資料夾裡重現的，先動手修」後，遇到症狀可重現但**商業／計價規則只有使用者知道**的題目（如稅額先加總再四捨五入 vs 單項四捨五入），模型會自己猜規則硬改，導致 `agent-notdone` 平均需 `4.0` 輪、被糾正 `3.0` 次。
- **修補內容**：於 `engine/skills/omnikit-ask/SKILL.md` 與 `situations/agent.md` 明確補上：「即使症狀能重現，只要『修成什麼樣才對』只有使用者知道（例如計算或計價規則、四捨五入方式、資料格式、取捨標準），先問一題確認規則再動手，不要自己猜規則硬改。」
- **多輪實測對照**（`data/pilot/ask-eval/results/2026-11-25-agent-notdone-skillfix.json`）：

| 版本 | 修好率 | 平均 Agent 輪數 | 平均使用者糾正次數 | 首輪叫用率 | 行為表現 |
|---|---|---|---|---|---|
| 修錯前（11-19） | 2/2（100%） | 4.0 輪 | **3.0 次** | 2/2 | 直接猜稅額算法硬改，反覆與發票總額不符遭糾正 |
| **修錯後（11-25）** | **2/2（100%）** | **2.0 輪** | **0.0 次** | **2/2** | 首輪叫用問法庫並主動詢問計稅四捨五入規則，使用者回答（`answer`）後第 2 輪一次修對通過隱藏檢查 |

---

## 二、近兩週真實對話抽樣 × 分歧過濾（Disagreement Filtering）

從近兩週（`2026-11-11` 至 `2026-11-25`）跨 5 個真實開發專案的 28 條使用者對話中，脫敏抽取 **10 筆真實訊息**（8 題卡住／抱怨／問做法正向題 ＋ 2 題需求明確負樣本），執行 `with_skill`（全域啟用 `omnikit-ask`）對照 `without_skill`（透過 `skills.json` `exclude` 遮蔽 `omnikit-ask`、`ok-ask`、`ok`）。

### 1. 客觀指標摘要

| 指標 | 結果 | 說明 |
|---|---|---|
| 正向題叫用率（Recall） | **8 / 8（100%）** | 8 題真實卡住／問做法情境全數觸發讀取 `omnikit-ask` |
| 負樣本誤叫用率（False Positive） | **0 / 2（0%）** | 2 題明確寫程式指令皆直接交付，零說教干擾 |
| 對照組遮蔽隔離度 | **0 / 10（0% 洩漏）** | `without_skill` 透過 `skills.json` 原生 `exclude` 100% 隔離 |
| 準則通過率（`with` vs `without`） | **90% vs 80%**（`+10%`） | `r01` 多專案混亂題 `with_skill` 緊扣輕量四欄位勝出，`without_skill` 塞入重型工具比較未過 |
| 分歧過濾壓縮比 | **自動收斂 2 題 / 保留 8 題** | 2 題負樣本雙雙通過且零叫用自動收斂；8 題正向分歧進入 `generate_review.py` 單頁檢視器 |
| 跨家盲評勝負（10 題） | **`with` 4 勝｜`without` 4 勝｜平手 2** | 無一面倒偏袒，清楚暴露問法庫強項與可微調處 |

### 2. 逐題盲評與分歧摘要

| 題號 | 來源專案類型 | 預期叫用 | 實際叫用 (`with`/`without`) | 盲評勝負 | 分歧重點摘要 |
|---|---|---|---|---|---|
| `r01-multiproject-chaos` | 多專案進度管理 | 是 | `True` / `False` | **with_skill** | `with` 聚焦四個缺失欄位與輕量狀態板（Pass）；`without` 塞入重型多代理平台比較（Fail） |
| `r02-threads-sprawl` | 對話發散收斂 | 是 | `True` / `False` | **with_skill** | `with` 精準給出單一主線、`/btw` 子對話與 `/clear` 交接收斂問法，結構更精煉 |
| `r03-ui-ugly-stuck` | 介面質感不知從何改 | 是 | `True` / `False` | **without_skill** | 兩組皆過；`without` 多給具體視窗尺寸與 Windows 縮放毛邊成因分類 |
| `r04-broke-again` | 修好又壞與部署未更新 | 是 | `True` / `False` | **with_skill** | `with` 要求先寫失敗重現測試、橫向搜尋同類寫法、目標端版號與 hook 護欄，只問 3 題更聚焦 |
| `r05-report-no-action-sycophancy` | 報告無結論且順從討好 | 是 | `True` / `False` | **without_skill** | 兩組皆過；`with` 把問法庫內部 `situations/docs.md` 路徑當成參考連結貼進回覆，略顯多餘 |
| `r06-early-agent-drift` | 早期規則偏離預期校準 | 是 | `True` / `False` | **without_skill** | 兩組皆過；`without` 白話表格更直覺，`with` 多列了部分工具指令 |
| `r07-ai-verbose-novice` | 幫純新手減少 AI 廢話 | 是 | `True` / `False` | **without_skill** | 兩組皆過；`with` 同樣在給新手的說明裡附上了本機問法庫檔案連結 |
| `r08-relogin-config-fragile` | 重登換名導致設定損壞 | 是 | `True` / `False` | **with_skill** | `with` 多給出具體映射結構、重登 upsert 規則與唯讀盤點→重構兩步問法 |
| `r09-neg-backtest-clear` | 明確統計回測腳本（負樣本） | 否 | `False` / `False` | 平手（自動收斂） | 兩組皆未誤叫用並直接交付完整腳本 |
| `r10-neg-parse-iso-ts` | 明確時間格式化函式（負樣本） | 否 | `False` / `False` | 平手（自動收斂） | 兩組皆未誤叫用並直接交付函式與 3 個邊界測試 |

### 3. 盲評抓出的關鍵可改進點（供人工檢視一併裁決）

- `with_skill` 落後的其中 2 題（`r05`、`r07`），共同扣分點都是「Agent 讀取 `omnikit-ask/situations/*.md` 後，受到全域『引用檔案附路徑』習慣影響，將問法庫內部的 `.md` 路徑貼進給使用者的回覆中」。
- 若人工 3 分鐘檢視後決定**保留 `omnikit-ask`**，只需在 `SKILL.md` 補半句「問法庫是給你自己看的內部指引，回覆使用者時不要貼出問法庫自己的檔案路徑」，即可消除此扣分項。
