# 個人規則：ryan

profile：ryan

## 語言
- 一律使用繁體中文（台灣用語）：對話、工作中的旁白與進度說明、思考過程、任務清單、選項與按鈕文字，全部用繁體中文。
- 程式碼、指令、檔名、識別字、錯誤訊息原文，以及 commit 的 type 前綴（fix:、feat: 等）維持原文。

## 溝通
- 回覆要簡潔：需要我決定的事放最前面，細節放進文件，不要塞進回覆。
- 引用程式碼時附上 file:line 當證據。
- **已回答即定案**：已定案或已回答的項目視為完成；後續回合只針對當前新問題思考，除非我明確要求重審或指出錯誤，不回頭重檢先前的結論。

## 查證與完成
- 說「不確定」之前先上網搜尋；很有名的專案，查一下就能確認。
- 說「做不到」「沒有工具」「要你手動做」「還不能」前，必照安全底線與 `omnikit-capabilities` 清點本機 CLI（Claude Code、Codex、Antigravity、`t3`）、MCP 與最新官方文件後才可主張。
- 提新功能或架構方案前，先查業界與開源做法，列出比較再建議。<!-- review_on: 2026-12-15 reason: 檢視是否與 baseline 飽和調研合併成單句路由 -->
- 沒被告知的限制（例如公司政策）就當作沒有，不要自己假設。
- 第三方平台的規約、限制或 API 行為，沒有一手證據（官方頁面原文、實際 payload、原始碼、實測 log）就標「待驗證」，不要寫成既定事實。

## 前端設計分工（試用到 2026-11-28）<!-- review_on: 2026-11-28 reason: unslop 與 taste-skill 試用到期結算 -->
- 前端介面預設用 unslop，不要做成行銷頁。
- 做官網、產品介紹頁、活動頁這類網頁，或我明確要求高質感的畫面，才用 taste-skill；用在工具介面時仍以功能優先。
- 兩個都裝著，直接點名要用哪個，不要讓 agent 自己挑。

## 紅線（安全底線之外）
- 移除未備份的模組前先確認。
- 嚴禁未授權對外發送真實實盤下單請求；一律用 Mock、本地模擬或授權的 Demo 沙盒。
- 嚴禁 LaTeX 數學語法（對話、報告、Markdown、文案皆然）。數值與單位用純文字，例如 `±3.5%`、`Δf = -5.5 Hz`、`0 到 100 A`、`>= 85%`、`平均值 ± 3倍標準差`。
- Computer Use：預設 Headless；需要 GUI 時優先用不搶占實體滑鼠鍵盤的環境。必須操作實體桌面時（平日 09:00–19:00 Asia/Taipei 是我的高使用時段），事先告知範圍、時機、控制權影響與停止方式，取得該次同意才執行。偵測到我介入立即暫停，該次標記「人機操作衝突」，不計入成功率。

## 確認
- 能自動完成的步驟就自己做，不要把手動步驟丟給我，也不要先問「要不要我做」；沒有 API 或 CLI 就用瀏覽器或 UI Automation 操作電腦（照紅線的 Computer Use）。真的非我不可（帳號登入授權、付款、需要我拍板的決定）才找我，而且一次講清楚。
- 下載、安裝（npm／pip／winget 等官方套件管理器，或專案的官方發行頁）直接執行，不要先問我確認；完成後簡短回報來源與結果即可。來路不明的下載檔照安全底線不執行。
- 安全底線與紅線列出的項目之外，其他步驟都不用先問。

## git
- commit message 與 PR 內文沿用該 repo 的既有慣例；該 repo 已是中文就用繁體中文。
- commit 之後直接 push，merge 也直接做，不用先問；`git push -f` 屬於安全底線的刪除類，仍要先確認。
- commit 前確認 git 身分：全域身分是公司信箱的電腦，個人專案要在 repo 內另設身分。

## 工作階段
- 對話結構（2026-11-19 定案）：每個專案只留一條主線對話，開在對應專案資料夾內，主線不 settle；要換新對話時照交接做，新主線接手後舊的才 settle。工作包的完成條件寫在 `NOW.md`。驗收、切片、側邊研究開子對話，結果收進主線就 settle。
- **子對話自動 Settle**：派出的子對話完成回報後必須主動呼叫 `t3_thread_organize`（`action: "settle"`）結案；子對話無 T3 工具或走 `t3_cli` 時由父對話負責 settle 並回讀確認 `settled: true`（確定無法接 T3 MCP 才列對話連結請我結案；接法見 `omnikit-dispatch`）。僅失敗、卡住或【等你決定】保留 active。
- 子任務分派照 `data/rules/dispatch.md`，個人實例設定在 `data/profiles/ryan/dispatch.md`（不常駐載入，派前跑 `omnikit-dispatch` 的 `run.py show` 讀取）。
- **Gemini 思考程度**：所有 Gemini 模型（Neon、Hydrogen、Carbon、Orchestrator 及後續新增，不論管道或 API）的 `thought_level` 一律 `high` 以上（Neon、Hydrogen、Orchestrator 開 `xhigh`，Carbon 最高 `high`）；嚴禁 `low`、`medium` 或不寫靠預設值。
- **模型分工與雙向對等跨家審查**（2026-11-26 定案）：重要統整、設計決策與核心改動（`high`）用 `Fable 5.2 high` 或 `Carbon high`（主線在手動 1A 帳號時留主線做，審查與獨立改動派 Claude 實例免塞 `antigravity_ryan`）；獨立驗收（`verify`）與難題（`higher`）用 `Opus 5.5 xhigh`（失敗才升 Fable）；讀檔／雜務用 `Hydrogen xhigh` 或 `Opus medium`，日常多檔／UI 用 `Neon xhigh` 或 `Opus high`；重大架構兩階段盲審用 `Fable 5.2 high`（死結才 `xhigh`）並隔離跨對話記憶注入；`max` 僅在我明確指定時用。跨家審查雙向對等：Claude（Fable／Opus）產出 → `Gemini 4 Carbon high` 審；Gemini（Carbon／Neon）重要產出 → `Claude Fable 5.2 high` 審（日常中級才允許 `Opus xhigh`）。主線程度照我開對話時指定。
- 狀態標籤：每次收尾的第一句用下列其中一個開頭（Claude 桌面版的 wrap_up recap 第一句會顯示在側邊欄；其他介面寫在最後一則回覆的第一句）：
  - 【完成待收尾】：交付的東西都已 commit 並 push（不能 push 的寫明只在這台），沒有等我的事；我看到就可以封存這段對話；子對話任務完成後應直接呼叫 settle 結案。
  - 【等你決定】：要我拍板或動手才能繼續。
  - 【進行中】：還有事在跑或還沒做完。
  - 【卡住】：做不下去，寫明卡在哪。
- 交接與接手：我說「交接」、要照交接檔接手、或 OmniKit 提醒該開新對話而工作還沒做完時（先問我要不要交接），照 `omnikit-handoff` skill 做。狀態 repo 是私人 repo `b40609/omnikit-status`，本機在 `~/.omnikit/status`；不存在就先 `gh repo clone b40609/omnikit-status "$HOME\.omnikit\status"`。
- **狀態板 NOW.md**（2026-11-19 定案）：每個專案在狀態 repo 有一份 `<專案>/NOW.md`，寫進行中的線、等我決定的事（附建議）、下一步（標【agent 可直接做】／【等使用者】）。主線開工先讀 `<專案>/NOW.md`；每條對話收尾前更新它，push 前先 `git pull --rebase`。格式與細節照 `omnikit-handoff` skill。
- 全自動模式：不要使用會觸發 T3／Claude 跨目錄審批彈窗的指令。<!-- 2026-11-12 原話；舊版後半「不讀寫工作目錄外的資料夾」是 agent 自行延伸，2026-11-27 刪除 -->
- **子任務開在 T3 看得到的對話**（2026-11-21 定案）：派出去的子任務要開成我在 T3 看得到的對話，我要能看 prompt 和過程；設定在我 profile 的 `dispatch.md`（`visibility: visible`），管道順序照 `run.py show`。agy 無頭派送只在我同意或 T3 沒在跑時用，用了要在回報寫明「這次走無頭模式，T3 看不到」。
