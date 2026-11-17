# 問法庫：在 Antigravity（Gemini）上的有它與沒它對照

日期：2026-11-17。接續 [Claude Code 那一輪](2026-11-17-ask-eval.md)，同一批 11 題，改在 Antigravity 上用 Gemini 跑。腳本：`data/pilot/ask-eval/agy_eval.py`。

## 結論

**換成 Gemini 一樣有效，差距還更大。** 有它與沒它：Hydrogen 1.00 比 0.62（+0.38），Flash 0.95 比 0.55（+0.41）；Claude Code 那輪是 0.97 比 0.64（+0.33）。三輪都沒有一題變差，有它時 Gemini 每次都叫用問法庫。換 Gemini 當評分者，結論不變（兩位評分者九成以上一致）。

差距一樣集中在：畫面太雜、需求不清、修過又復發、問官方功能。沒它時 Gemini 最弱的是問其他 agent 的指令（`/clear` 那題兩個模型都 0 分），這正是對照表在補的。

量的仍然是「回覆有沒有照好的做法」，不是「用起來少修正幾輪」。

## 怎麼量的

- **跑法**：`agy acp`（Antigravity 的 ACP 伺服器），一次一個新對話。帳號沿用 T3 Code 替每個 Antigravity 實例存好的登入資料夾，用 `--gemini-dir` 指過去，再送 `authenticate`；不讀、不複製金鑰。實際計費帳號沒有照指定切換，見下面「過程中踩到的」。
- **兩組**：有它的工作資料夾放 `.agents/skills/omnikit-ask`（Antigravity 的專案層 skill）；沒它的沒有。兩組都放一份 `AGENTS.md`（這台的 OmniKit 規則），跟平常用 Antigravity 一樣。確認過沒它那組列出的 skill 裡沒有 omnikit-ask，也確認規則檔有讀到（它答得出規則要求的語言）。
- **模型**：Gemini 4 Hydrogen（High）、Gemini 3.8 Flash（High）。每題每組 2 次。
- **評分**：兩位評分者各自判 PASS 或 FAIL。
  - 主要：本機 Claude Code 的 Sonnet，跟 Claude Code 那一輪同一個評分者，三組結果才能比；跟被測的 Gemini 不同家。
  - 第二位：Gemini 4 Hydrogen，只用來看兩位一不一致。同家評分會偏袒自己（arXiv:2604.06996：評分者對自家輸出的不及格項，誤判成及格的機率高 50% 以上）。
- **評分項**跟 Claude Code 那一輪一樣：做法（權重 2）、可以直接貼（權重 1）。

## 結果

主要評分者（Claude Sonnet）的分數。Hydrogen 每題每組 2 次；Flash 跑了兩輪，合起來每題每組 4 次；Claude Code 是前一份的結果。

| 題目 | Hydrogen 有它 | Hydrogen 沒它 | Flash 有它 | Flash 沒它 | Claude Code 有它 | Claude Code 沒它 |
|---|---|---|---|---|---|---|
| 對話聊久越改越亂（agent-long） | 1.00 | 0.67 | 1.00 | 0.67 | 1.00 | 0.67 |
| 說做完了其實沒有（agent-notdone） | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.83 |
| 叫它自己檢查永遠說沒問題（agent-selfreview） | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| 舊程式沒測試想整理（arch-legacy） | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 | 1.00 |
| 測試時好時壞（debug-flaky） | 1.00 | 0.33 | 1.00 | 0.67 | 1.00 | 1.00 |
| 修過又復發的 bug（debug-recur） | 1.00 | 0.67 | 1.00 | 0.00 | 1.00 | 0.00 |
| `/clear` 是什麼、Codex 怎麼做（feature-clear） | 1.00 | 0.00 | 0.67 | 0.00 | 0.83 | 0.33 |
| 同一件事提醒五次（project-repeat） | 1.00 | 1.00 | 1.00 | 1.00 | 0.83 | 0.67 |
| 需求還沒想清楚（req-unclear） | 1.00 | 0.33 | 0.83 | 0.25 | 1.00 | 0.33 |
| 畫面怪怪的說不出哪裡（ui-vague） | 1.00 | 0.67 | 1.00 | 0.58 | 1.00 | 0.83 |
| 畫面太雜想合併入口（ux-merge） | 1.00 | 0.17 | 1.00 | 0.17 | 1.00 | 0.33 |
| **平均** | **1.00** | **0.62** | **0.95** | **0.55** | **0.97** | **0.64** |
| **差距** | | **+0.38** | | **+0.41** | | **+0.33** |

- **叫用率**：兩個 Gemini 模型，有它那組 66 次都叫用（100%），沒它那組 0 次。Claude Code 那輪改說明文字前有一題 0/2。
- **評分者一致率**：Claude 與 Gemini 兩位評分者在 Hydrogen 這輪 88 個判斷裡有 80 個相同（91%），Flash 兩輪各 82/88、80/88（93%、91%）。用 Gemini 當評分者，差距是 Hydrogen +0.38、Flash +0.47；結論不因評分者換家而改變。
- Flash 兩輪分開看：第一輪 0.97 比 0.59，第二輪 0.94 比 0.50。
- **沒有一題變差**，三輪都是。
- **差最多的題目三輪一致**：畫面太雜、需求不清、修過又復發、問官方功能。agent 本來就會的（找別人審、舊程式先補測試、說做完了其實沒有）三輪都沒差。
- `/clear` 那題 Gemini 沒它時兩次都 0 分：它不熟 Claude Code 與 Codex 的指令；有它時讀 `features.md` 答對。這是對照表最直接的價值。

## 過程中踩到的

- **Antigravity 不讀 `~/.agents/skills`。** 官方文件寫全域 skill 在 `~/.gemini/config/skills`，`.agents/skills` 只在專案資料夾裡有效；在這台用 `agy -p` 列出 skill 也證實了，OmniKit 的 8 個 skill 一個都沒有。OmniKit 的安裝一直把它們複製到 `~/.agents/skills` 給 Codex 與 Antigravity 共用，所以 **Antigravity 從來沒載入過 OmniKit 的 skill**。實測步驟（`data/pilot/ask-test.md`）已改成正確路徑；安裝程式要另外修。
- **第一次跑時評分者額度用完。** 原本用 ryan 在 Antigravity 上的 Claude Sonnet 評分，跑到一半回「Individual quota reached」，腳本把它當成不及格。改成評分出錯就不算分、可以只補評分（`--rejudge`），評分者換成本機 Claude Code。這一下把 ryan 在 Antigravity 的 Claude 週額度從約 34% 用到約 86%（下次重置 11-20）。
- **指定 ava 帳號沒成功。** 腳本照 T3 的方式把 agy 指到 ava 的登入資料夾（對話檔確實寫進 ava 的資料夾），第二輪也照 T3 補送了 `authenticate`，但兩輪 Flash 跑完，T3 顯示的 ava 額度都還是 0.11%（週）、0%（5 小時），ryan 的 Gemini 5 小時額度則從約 17% 漲到約 63%（中間也包含 Hydrogen 那輪與 Gemini 評分）。所以這些用量都算在 ryan 身上。回覆確實是 Flash 產生的，結果照算。原因待查：可能 agy 優先用系統裡存的登入（ryan），T3 的 ava 實例可能也一樣（待驗證）。
- **這一輪用掉的額度**（T3 顯示，ryan 帳號）：Gemini 5 小時約 14% 到 63%、週 63% 到 77%；Antigravity 的 Claude 週額度 34% 到 87%（11-20 重置）。本機 Claude Code 的評分約 270 次短呼叫，用量沒有量。

## 題目怎麼加（待討論）

來源調研：Gemini 4 Hydrogen 做飽和式調研（11 輪、70 多組關鍵字，第 11 輪連續 3 組沒有新名字才停），列了約 40 個來源、17 個問法庫還沒有的情境。我抽查了最重要的 5 個，都存在、數字對得上：

| 來源 | 是什麼 | 能拿來做什麼 |
|---|---|---|
| [How Coding Agents Fail Their Users](https://arxiv.org/abs/2605.29442)（2026-05） | 20,574 個真實 coding agent 對話，歸納出 7 類人與 agent 對不上的情況；91% 的情況最後要靠使用者明確糾正 | 對照問法庫的「跟 agent 協作」類，補沒涵蓋的類型 |
| [SWE-chat](https://huggingface.co/datasets/SALT-NLP/SWE-chat)（ODC-BY） | 約 1.8 萬個真實 Claude Code、Codex、Gemini CLI 對話，使用者每句話都標了是不是在糾正、拒絕或回報失敗 | 抽「使用者糾正」的那一句前後，改寫成真實題目；這是最接近「少修正幾輪」的資料 |
| [ClarifyCodeBench](https://arxiv.org/abs/2607.00711)（2026-07） | 需求不清時會不會先問對的問題；結論是會寫程式不等於會問 | 對應「需求還沒想清楚」這類，借它的量法（問到關鍵問題的比例、輪數） |
| [NVIDIA SkillEvaluator](https://github.com/NVIDIA/SkillEvaluator)（Apache-2.0） | 專門評 skill 的框架：格式檢查、跟其他 skill 重疊、沙盒實跑 | 借它的「不該觸發」題與重疊檢查 |
| [Self-Preference Bias in Rubric-Based Evaluation](https://arxiv.org/abs/2604.06996) | 評分者對自家輸出明顯放水，多個評分者能降低但不能消除 | 已採用：主評分者跟被測模型不同家，另算一致率 |

調研原文：[2026-11-17-ask-sources-research.md](2026-11-17-ask-sources-research.md)。其他來源（`ClarEval`、`Ask or Assume?`、`SWE-Clar`、`UserSWE`、`Evaluating AGENTS.md`、`Guardrails Beat Guidance`、各家 GitHub issue、Reddit、METR、Stack Overflow 調查等）只列在調研報告裡，沒逐一核對，視為待驗證。

可以加的方向：

1. **72 條每條至少一題**（現在 11 題）。從條目自動產生題目與評分標準，便宜，但評分標準更同源。
2. **同一情境三種說法**：明確求助（「我不知道怎麼問」）、抱怨或講不清楚、只貼錯誤訊息。量觸發穩不穩。
3. **不該觸發的題目**：資訊已經講清楚的一般請求（例如「修 `src/auth.ts` 第 42 行的過期判斷，跑 `pytest` 貼結果」），問法庫不該跳出來。現在完全沒有這種題。
4. **小型壞專案資料夾加多輪模擬使用者**：放一個真的有 bug 或真的很亂的小專案，另一個模型扮演只知道隱藏細節的使用者，量 agent 實際做完沒有、來回幾輪。最接近「少修正幾輪」，但要做的最多。
5. **問法庫還沒有的情境**（調研列了 17 個，例如：對話壓縮後忘掉剛定的決定、MCP 裝太多、hook 其實沒擋住、下了「不要做 X」結果它連正常功能也砍、我中途手改了程式它還照舊印象改、只做表面的空值防呆把問題藏起來、剛補的測試是不是真的抓得到錯、該讓它先猜著做還是先問我、到了 90% 剩下 10% 怎麼都修不好）。要先加進問法庫，再出題。
6. **用 SWE-chat 的真實糾正改寫題目**：要先在 Hugging Face 同意條款才能下載。

## 要打折看的地方

- 跟 Claude Code 那一輪一樣：評分標準跟問法庫同源、工作資料夾是空的、樣本小。
- 有它那組的 skill 放在專案層（`.agents/skills`），不是使用者層；實際安裝在 `~/.gemini/config/skills` 時叫用率可能不同。
