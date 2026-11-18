# 對比實測 P3：omnikit-research 對開源 deep research（2026-11-17 起）

## 完成條件

1. A：`/doctor prompt-audit` 的清單（唯讀，不改檔）交給你決定要改哪幾條。
2. B：訓練題與保留題的切分方案寫好，交給正在擴充評測題的那份工作。
3. 實測：照下面的決策規則跑完，報告與原始資料進 OmniKit 的 `data/evals/`，工具卡照判定更新，commit 並 push。

## 決策規則（實測前寫下，2026-11-17 22:45）

**題目**：沿用 P2：「找能把 GitHub repo 自動畫成架構圖的工具」。P2 的資料（3 組關鍵字的 88 個名字聯集、Archify）當參考，不給任何一組看。

**判斷標準**（跟 P2 一樣）：能把 repo 或程式碼自動畫成架構、結構或依賴圖的工具才算相關；只畫 git 歷史的、純圖表函式庫、教學文、論文算雜訊。

**組別**

| 組 | 做法 | 次數 |
|---|---|---|
| A omnikit-research | Hydrogen high 照 skill 跑到 `status` 印「可以停」，不准讀 P2 資料 | 1 次（一次就要跑很多組） |
| B GPT Researcher | 預設設定（Tavily、預設模型），deep research 模式 | 2 次 |
| C Open Deep Research | 預設設定（Tavily、預設模型） | 2 次 |
| D（看 R1 調研） | R1 找到更適合「找齊名單」、能在 Windows 跑的候選，開跑前補進來並在這裡記一筆 | 2 次 |

B、C、D 給同一段英文指令：「Find as many distinct tools as possible (open-source repositories, products, VS Code extensions, coding-agent skills or MCP servers) that automatically generate architecture, structure, or dependency diagrams from a GitHub repository or codebase. For each tool give its name and a link.」

**量什麼**（每組每次）

1. 有沒有找到 Archify。
2. 相關名字數（不重複）。
3. 新名字：A 沒有的相關名字；漏掉：A 有、它沒有的。
4. 雜訊比例：不相關的名字 ÷ 它列出的所有名字。
5. 花多久（牆上時間）、花多少錢（工具自己回報的費用或 token 數；量不到就寫量不到）。

**怎麼判相關**：所有組的名字混在一起、拿掉來源、打亂順序，兩位評審各自判：主控（Claude Opus）與 Hydrogen xhigh（不同家族）。意見不同的由主控定案，並列在報告裡。

**判定**

1. **當成 omnikit-research 的選用管道**（卡片改 `trial` 兩週），全部要成立：
   - 2 次裡至少 1 次找到 Archify，或 2 次平均多出 5 個以上 A 沒有的相關名字；
   - 雜訊比例不比 A 高 20 個百分點以上；
   - 每次平均費用不到 US$1；
   - 在 Windows 不用 Docker 就能跑。
2. **可以取代 omnikit-research**（只提案，要你決定）：2 次都找到 Archify，平均找到 A 相關名字的 80% 以上，而且時間不比 A 長。
3. 都不成立：卡片記 `rejected`（產品研究槽位），理由寫數字。
4. omnikit-research 自己：B、C 的相關名字數都不少於 A 的話，報告寫明「這一題 omnikit-research 在找齊名單上沒有優勢」。

**開跑前的變更（2026-11-17 22:58）**：C 組 Open Deep Research 第 0 層不通過：repo 已封存（archived，最後 push 2026-08-10，README 沒有指向接替的專案）。照 OmniKit 的硬性門檻，它的結果再好也不能進名冊，所以不跑；改從 R1 的候選挑一個通過第 0 層、能在 Windows 不用 Docker 跑的，當新的 C 組，次數與判定不變。GPT Researcher 第 0 層通過（★30,752，Apache-2.0，v3.8.0 是 2026-11-09，兩個 skill 掃描都是 INFO）。

**開跑前的變更 2（2026-11-17 23:15）**：B 組原訂用預設的 OpenAI 模型，但那把金鑰的帳戶沒有額度（API 回 429「You have no credits remaining」，沒有任何一次請求成功、沒有花到錢）。使用者選改用 Gemini 免費金鑰。設定改成：`FAST_LLM`、`SMART_LLM`、`STRATEGIC_LLM` 都是 `google_genai:gemini-4-hydrogen`（跟 A 組同一個模型；Gemini 3.8 Flash 與 flash-latest 連試兩次都回 503，沒用），`EMBEDDING` 是 `google_genai:gemini-embedding-001`，搜尋照預設用 Tavily。所以 B 組**不是預設設定**，報告要註明。另外在繁中 Windows 上，GPT Researcher 0.17.0 印 emoji 會因為 cp950 編碼直接崩潰，要用 Python 的 UTF-8 模式（`-X utf8`）才跑得動。

**開跑前的變更 3（2026-11-17 23:20）**：用 Gemini 4 跑 GPT Researcher 第一次就當掉（`deep_research.py` 的 `response.strip()`：`'list' object has no attribute 'strip'`）。原因：langchain-google-genai 4.5.0 回傳的 content 是分段的 list，GPT Researcher 0.17.0 只對 `minimax_anthropic` 改用 `.text`。執行腳本加了一處相容修正，讓 `google_genai` 也走它既有的 `.text` 路徑；搜尋、規劃、寫報告的流程都沒動。報告要註明：**GPT Researcher 0.17.0 要改這一處才能用 Gemini 4**。

**開跑前的變更 4（2026-11-17 23:45）**：

- **Antigravity（ryan）額度用完**（R1 續跑回「You have reached your Antigravity quota」，3 天 11 小時後重置）。這時 R2 跑了 11 組、243 個名字，R1 跑了 13 組、296 個名字，兩邊每一組都還有一大半是新名字，**完全沒有收斂**。
- 決定：**A 組在額度用完那一刻停**，名單照帳本當下的內容算，報告標「未飽和」。不改派 Claude 續跑：照現在的速度看不出幾組會收斂，改派會燒掉稀缺的 Claude 額度，帳本留著，額度重置後可以從帳本接著跑。
- **C 組改用 LearningCircuit/local-deep-research 2.0.1**（★9,597、MIT、v2.0.1 是 2026-11-15，第 0 層通過，名冊沒有）。從 R1 帳本挑的，理由：近期有更新、pip 就能在 Windows 裝、能用 Gemini 金鑰、研究過程會自己挑搜尋引擎（最接近多管道）。R1 沒飽和，所以「C 組是最好的對手」這點不成立，只能說「是帳本裡符合條件的一個」。
- C 組設定：模型 Gemini 4 Hydrogen（預設是 ollama）；主搜尋 Tavily（預設 SearXNG 要自己架伺服器）；關掉 SearXNG；GitHub 引擎照預設不開（要 token）。其他照預設（langgraph-agent 策略）。用 `generate_report`。
- B、C 共用同一把 AI Studio 免費金鑰，同時跑可能互相擠到速率限制，時間數字要打折看。

**開跑前的變更 5（2026-11-18 02:25）**：B、C 用 Gemini 免費金鑰都沒跑成。`gemini-4-hydrogen` 的免費額度是**一天 20 次請求**（429 RESOURCE_EXHAUSTED，`generate_content_free_tier_requests, limit: 20`，要 16 小時後才重置）。B 第 1 次跑了 31 分鐘、0 個來源、報告 468 字（工具自己說找不到資料）；B 第 2 次、C 兩次都在開頭就被拒。這 4 次不算結果，存在 `out/` 與 `out/failed/`。

改用這台的本機模型跑 B、C：Ollama 的 `qwen3:8b`（RTX 2000 Ada，16 GB；local-deep-research 的預設本來就是 Ollama）。兩邊 context 都設 20,480（LDR 的本機預設），思考模式照 LDR 預設開著；B 的 embedding 用 `ollama:qwen3-embedding:8b`。一次只跑一個，免得搶 GPU。**B、C 用的是 8B 小模型、A 組是 Gemini 4 Hydrogen，所以 B、C 的結果只能當下限**；要公平比，得用付費的前沿模型再跑一輪，留給使用者決定。每次上限 45 分鐘，超時就記超時。

R1、R2 第一次在 22:49 同時斷線（Antigravity 回 provider 錯誤），帳本保留了進度，同一管道重派續跑（記為重跑 1 次）。

**已知限制（先寫下）**：只有一個題目；A 是 agent 照流程跑，B、C 是全自動；B、C 用英文指令、A 中英文都查；評審只有兩位。
