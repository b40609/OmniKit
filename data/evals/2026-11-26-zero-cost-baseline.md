# 零成本常駐成本與名冊證據基準盤點（P0-1）

- 日期：2026-11-26
- 目的：作為「自我迭代 OmniKit」（`docs/proposals/2026-11-26-self-iterating-omnikit.md`）P0 階段的零成本實測基準線。所有數字皆來自本機 CLI 實際輸出（0 API token 消耗）。

## 1. Claude Code Plugin 常駐成本實測（`claude plugin list` / `claude plugin details`，v2.1.332）

| Plugin | 狀態 | 元件數 | Always-on 預估成本 | 發現與建議（由使用者決定） |
|---|---|---|---|---|
| `omnikit@omnikit-local` (`0.2.0-3543b71e`) | enabled | 0 skills, 4 hooks, 1 MCP | `~0 tok` | Hooks 為 harness-only，零常駐模型上下文成本。 |
| `claude-mem@thedotmack` (`16.1.3`) | enabled | **30 skills**, 9 hooks, 1 MCP | **`~2,890 tok` / session** | 附帶 30 個附屬 skills（如 `childhood`、`wowerpoint`、`standup`、`babysit` 等）每輪常駐佔約 2,890 tokens；且 `SessionStart` 與 `PreToolUse:Read` 會向盲審子對話注入前輪標題。建議在設定檔用 `skillOverrides` 關閉不用的附屬 skills。 |
| `floorplan@floorplan` (`0.6.3`) | enabled | 1 skill (`floorplan`) | **`~303 tok` / session**（呼叫時 `~7.9k`） | 名冊狀態為 `pending`，且 C1C2 實測（`data/evals/2026-11-16-code-understanding-C1C2.md`）6 次皆未叫用、起手清單已列「內建就夠」。建議若近期不畫產品架構圖可先 disable。 |
| `taste-skill@taste-skill` (`2.5.1`) | enabled | 1 skill (`design-taste-frontend`) | `~331 tok` / session（呼叫時 `~10.9k`） | 試用到 `2026-11-28` 到期檢討。 |
| `agent-skills` / `document-skills` / `example-skills` / `ponytail` / `productivity` | disabled | — | `0 tok` | 已停用，不佔常駐預算。 |

## 2. 三家常駐規則與 Prompt 輸入量測（瘦身前基準）

- **Codex CLI (`0.168.0`)**：
  - `~/.codex/AGENTS.md` 受管合併檔：**15,284 bytes**（上限 32,768 bytes）
  - `codex debug prompt-input` 實測模型可見總輸入字元數：**83,075 chars**
- **Antigravity**：
  - `~/.gemini/AGENTS.md`（共用層）：**6,777 bytes**（上限 24,000 bytes）
  - `~/.gemini/GEMINI.md`（個人層 `ryan`）：**8,606 bytes**（上限 24,000 bytes）
- **第一刀減法目標與實測結果**：
  - 將 `data/rules/mobile-web.md`（1,089 字）移出 `SHARED_RULES`，轉為 `omnikit-mobile-web` 按需 skill（`baseline.md` 僅留 1 行水平路由指標）。
  - **瘦身後實測（`doctor.py` 驗證）**：
    - Antigravity 共用層 `~/.gemini/AGENTS.md`：6,777 -> **5,201 bytes**（受管區塊 **5,200 bytes**，減省 **1,576 bytes / -23.3%**；棘輪鎖定 `5,400 bytes`）。
    - Codex 合併檔 `~/.codex/AGENTS.md`：15,284 -> **13,708 bytes**（受管區塊 **13,707 bytes**，減省 **1,576 bytes / -10.3%**；棘輪鎖定 `14,000 bytes`）。
    - 自動觸發 Skills（7 個）`description` 總長度：**3,529 bytes**（棘輪鎖定 `3,800 bytes`）。

## 3. 名冊 `default` 與 `trial` 工具卡基準盤點

### 3.1 `default` 卡（共 7 張）

| 工具卡 | `decided_at` | 裸模型／基準實測狀態 | 處置 |
|---|---|---|---|
| `chrome-devtools-mcp` | 2026-11-25 | 已有 U1 實測（2026-11-04：Codex 非互動模式 4 分對原生 0 分勝出；Claude 互動模式與原生同為 4 分，`data/evals/2026-11-04-browser-u1.md`） | 寫入 `baseline_eval`（`scoped_beats_vanilla`） |
| `gitleaks` | 2026-11-24 | 已有 Windows 11 本機實測（227ms 零誤報，對手 betterleaks 崩潰） | 寫入 `baseline_eval`（`essential_infra`） |
| `t3-code` | 2026-11-25 | 已有 S1 對話載入實測（2026-11-09，`data/evals/2026-11-09-session-management-s1.md`）與 S1–S6 同步探測報告（`docs/reports/2026-11-25-s1-s6-sync-probes.md`） | 寫入 `baseline_eval`（`essential_infra`） |
| `bmad` | 2026-11-04 | **無裸模型對照**（理由僅訪談預設） | 標記待 P2 跑 With vs. Vanilla 消融 |
| `frontend-design` | 2026-11-04 | **無裸模型對照**（理由僅訪談「有感」） | 標記待 P2 跑 With vs. Vanilla 消融 |
| `rea` | 2026-11-04 | **無裸模型對照**（理由僅訪談「有感」） | 標記待 P2 跑 With vs. Vanilla 消融 |
| `skill-creator` | 2026-11-04 | **無裸模型對照**（理由僅「常用」） | 標記待 P2 跑 With vs. Vanilla 消融 |

### 3.2 即將到期的 `trial` 卡與規則條款

- `taste-skill.yaml`：`trial_until: 2026-11-28`（對應 `data/profiles/ryan/AGENTS.md` 前端設計分工試用期）
- `unslop.yaml`：`trial_until: 2026-11-28`
- `dispatch-policy.md` Sonnet 試行與凍結期：`2026-11-29`
- `exa.yaml`：`trial_until: 2026-11-30`
- `data/profiles/ryan/dispatch.md` Gemini `thinking_preference: max_available`：`2026-12-07`
