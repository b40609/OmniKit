# ryan 規則與現行模型、帳號的對帳審查（唯讀）

- 日期：2026-11-25
- 性質：唯讀審查。這份文件不改任何規則檔，要等 ryan 拍板後另外改。
- 審查範圍：`data/profiles/ryan/AGENTS.md`、`data/profiles/ryan/dispatch.md`、`data/rules/dispatch.md`、`data/rules/dispatch-policy.md`、`docs/proposals/2026-11-23-account-pool.md`，以及順帶查到的 `engine/skills/omnikit-dispatch/SKILL.md`、`engine/scripts/dispatch.py`。
- 要對齊的工作：對話「Claude-mem 替代與 OmniKit 工具評估」（de030023）提出的「新模型分工與審查表」，以及它的調研檔 `model-task-ranking-and-effort-guide-2026-11.md`。這份不重做分工表，只標出哪些條文要等那張表定案後一起改。

## 一、這次查到的現況（一手證據）

| # | 事實 | 來源（2026-11-25 實查） |
|---|---|---|
| E1 | 啟用中的 T3 實例：claudeAgent（Ryan）、claudeAgent_claude_kai（Kai_）、claudeAgent_2（retis）、antigravity_ryan、antigravity_m3、antigravity_m2、antigravity_m4、antigravity_m1、antigravity_m5、antigravity_m6。`codex` 停用；沒有 `antigravity_kai`。 | `~/.t3/userdata/settings.json` 的 `providerInstances` |
| E2 | 3 個 Claude 實例都列出 `claude-opus-5-5`、`claude-sonnet-5-5`、`claude-fable-5-2`；effort 可選 low 到 max 與 ultrathink，Opus 和 Fable 預設 medium、Sonnet 預設 high。 | T3 `orchestrator_capabilities` |
| E3 | 7 個 Antigravity 實例（包括 m6）在 T3 目錄裡**都只列 3 個模型**：`gemini-4-neon`（thought_level 最高 xhigh）、`gemini-4-hydrogen`（最高 xhigh）、`gemini-4-carbon`（**最高 high**）。用 `search` 查 orchestrator、flash、opus，Antigravity 實例都查不到。 | T3 `orchestrator_capabilities`（含 search） |
| E4 | Antigravity 選項的 id 是 `thought_level`，值有 low、medium、high、xhigh。 | 同上 |
| E5 | `agy 1.5.16` 的 `/usage`（antigravity_ryan）：「Gemini Models」這一組包含 Neon、Carbon、Argon、Hydrogen、Orchestrator (Neon)、Orchestrator (Carbon)、Orchestrator (Argon)、3.8 Flash，大家共用週額度與 5 小時額度。**Argon 不再單獨一桶**。「Claude and GPT models」組仍在（Opus 5.5、Sonnet 5.5、GPT-OSS 120B），重置時間顯示 1970-01-01，代表從沒用過。當下 Gemini 週額度剩 54%。 | `agy -p /usage --output-format json`（0 token） |
| E6 | `run.py show` 現在的輸出：中級預設 Neon xhigh；高級與驗收用 Opus **effort high**、更高級用 Opus **xhigh**（沒有套用 ryan「Opus 子任務 medium」）；接手順序第 2 步仍是「Gemini 4 Argon 桶」；第 5 步「可手動切換」只列 m3、m2、m4，漏了 m1、m5、m6；另外提醒價格表寫 Opus、Sonnet 的後繼是 Fable 5.2，Argon 的後繼是 Carbon。 | `uv run engine/scripts/dispatch.py show` |
| E7 | 今天實際跑成功的模型：gemini-4-neon、gemini-4-carbon、gemini-4-hydrogen、claude-opus-5-5、claude-sonnet-5-5、claude-haiku-5-5、claude-fable-5-2（de030023 的探測子對話與 Fable 盲審都已完成並 settle）。 | 任務說明提供，de030023 訊息 position 556、585 |
| E8 | de030023 的現行提案（等 ryan 拍板第 1 題）：日常多檔實作 Opus high；高風險驗收 Opus xhigh（不預設 max）；重大架構盲審 Fable 5.2 high；反過來審 Claude 用 Carbon high；大範圍讀檔與雜事用 Hydrogen xhigh 或 Opus medium。另外提出「Google 多帳號：同時間集中用同 1 個帳號開多條對話平行做」。 | `t3_thread_read` de030023，position 585、591 |
| E9 | de030023 調研檔裡的基準分數與價格（FrontierCode 2.0 49.1%、FrontierSWE v2 69.9%、Terminal-Bench 4.0 66.4%、AA 指數約 58 到 62、Fable 單價是 Opus 的 2 倍、max 會多燒 10 到 11 倍 token 等）**都沒附一手來源連結**。本文件一律當成【待驗證】，不拿來當證據。只有「Fable 的價格比 Opus 高」可以從 T3 的價格表部分佐證：`us.anthropic.claude-fable-5` 的單價是每百萬 token 輸入 11、輸出 55 美元（Bedrock 條目）。 | 調研檔原文、`~/.t3/userdata/usage-model-rates.json` |

## 二、逐條審查

判斷分類：仍然正確／已過時／互相矛盾／缺漏。「拍板」欄：要 ryan 決定的打「是」，「併 de030023」表示要跟 de030023 的分工表一起定。

### A. `data/profiles/ryan/AGENTS.md`

| # | 條文位置 | 原文摘要 | 判斷 | 證據 | 建議 | 拍板 |
|---|---|---|---|---|---|---|
| A1 | `data/profiles/ryan/AGENTS.md:46` | Gemini 思考程度一律 high 以上，不准 low、medium、不准靠預設；列舉的類別是「gemini-pro、gemini-flash」；`t3 thread start` 要把程度寫進代號 | 主旨仍然正確；列舉**已過時**，也有**缺漏** | 現行類別有 gemini-pro、gemini-fast、gemini-orchestrator、gemini-argon、gemini-flash（`dispatch-policy.md:23-27`），Carbon 沒有類別（E3）。m6、m1 的 Neon 預設是 medium（E3），所以「不准靠預設值」這條確實需要 | 改寫成「所有 Gemini 模型（Neon、Hydrogen、Carbon、Orchestrator 系列，以及之後新增的）的思考程度一律 high 以上……」，不要列舉類別名稱 | 否 |
| A2 | `data/profiles/ryan/AGENTS.md:46` 後半 | 直接呼叫 Gemini API 時用 Hydrogen，不能用才退到 3.8 Flash | **已過時**；也跟 D1 **矛盾** | 3.8 Flash 在 11-23 已放進 `exclude_models`（`dispatch.md:20`）；D1 定案不走 Vertex（`2026-11-23-account-pool.md:10`）；價格表寫 Flash 的後繼是 Hydrogen（E6） | 刪掉「退到 3.8 Flash」。整句改成「直接呼叫 Gemini API（目前不用，D1）時，程度一樣 high 以上；模型照分工表」。要不要保留整句，看 ryan 還會不會用 API | 是（小） |
| A3 | `data/profiles/ryan/AGENTS.md:47` | 派出去的 Claude Opus 子任務 effort 一律 medium；policy 寫的 high、xhigh 在 ryan 這裡先用 medium，要升先問 | **矛盾**（跟 policy、引擎、de030023 都對不上） | `run.py show` 印的是 high、xhigh（E6），沒套用這條；ryan 在 de030023 已回「1. 同意」，同意把審查分級升上去（E8）；當初訂 medium 的前提是怕單帳號額度燒爆，現在 3 個 Claude 帳號週額度約 84% 以上（E6） | 改寫，**併 de030023**。建議文字：「派出去的 Claude 子任務 effort 照分派政策的 levels（日常 medium 或 high、高風險驗收 xhigh、max 只在 xhigh 失敗時用）；Fable 5.2 用 high，死結才 xhigh。」同時要讓 `dispatch.py show` 讀 profile 覆寫，不然規則和引擎輸出還是兩套 | 是，併 de030023 |
| A4 | `data/profiles/ryan/AGENTS.md:47` 範圍 | 範圍是「claude-opus、antigravity-opus」 | **缺漏** | Fable 5.2、Sonnet 5.5 都沒提到（E2）；antigravity-opus 在 T3 目錄已經看不到（E3） | 併進 A3，一起改成以模型為單位的 effort 表 | 併 de030023 |
| A5 | `data/profiles/ryan/AGENTS.md:56` | 子任務開在 T3 看得到的對話；agy 無頭只在同意或 T3 沒跑時用 | 仍然正確 | `show` 的管道順序符合（E6） | 保留 | 否 |
| A6 | `data/profiles/ryan/AGENTS.md:58` | 3.8 Flash 主線只能派給 kai 或 m6 的 3.8 Flash，程度固定 high，嚴禁跨模型 | **已過時**，而且**自相矛盾** | antigravity_kai 已不存在（E1）；m6 在 T3 目錄只有 Neon、Hydrogen、Carbon（E3）；`gemini-3.8-flash` 已排除（`dispatch.md:20`）；這條規定派給一個已排除的模型 | **刪除**。如果 ryan 想保留「主線模型低階時不要往上派」的精神，改寫成：「主線跑的是 Hydrogen 這類快速模型時，派出去的子任務照分派政策的 levels 選模型，不要從快速模型主線替 Opus、Fable 下判斷。」 | 是 |
| A7 | `data/profiles/ryan/AGENTS.md:44` | 子對話自動 settle；`t3_cli` 開的對話由父對話 settle | 仍然正確 | 跟模型無關，管道說明跟 policy 一致 | 保留 | 否 |

### B. `data/profiles/ryan/dispatch.md`

| # | 條文位置 | 原文摘要 | 判斷 | 證據 | 建議 | 拍板 |
|---|---|---|---|---|---|---|
| B1 | `data/profiles/ryan/dispatch.md:3` | 範例 `--provider antigravity_kai --model gemini-3.8-flash`，以及 Flash 帶程度代號沒實測的說明 | **已過時** | kai 不存在（E1），Flash 已排除 | 範例改成 `--provider antigravity_ryan --model gemini-4-hydrogen-high`，刪掉 Flash 的那段說明 | 否 |
| B2 | `data/profiles/ryan/dispatch.md:8` | `visibility: visible` | 仍然正確 | `show` 照 visible 印管道（E6） | 保留 | 否 |
| B3 | `data/profiles/ryan/dispatch.md:10-12` | `thinking_preference: max_available`；註解寫「Neon、Hydrogen、Orchestrator 用 xhigh；Antigravity 的 Claude 最高 high」；暫定兩週 | 主旨仍然有效；註解**已過時**也有**缺漏**；而且跟 A3 **矛盾** | Carbon 最高只到 high（E3），註解沒寫；Orchestrator 在 T3 目錄看不到（E3）；max_available 套到 Claude 等於 max，跟 A3 的 medium、以及 de030023「不預設 max」都衝突（E8） | 改寫，**併 de030023**。建議把範圍限定在 Gemini：「Gemini 系列開到該模型的最高檔（Neon、Hydrogen xhigh；Carbon high）；Claude 的 effort 照分工表，不套用 max_available。」到期日（11-23 加兩週，也就是 12-07）寫進註解 | 是，併 de030023 |
| B4 | `data/profiles/ryan/dispatch.md:14-17` | `on_exhausted: prompt_manual_switch`；接手順序：antigravity_ryan 的 Gemini → 同帳號 Claude & GPT 桶的 Opus → Claude 三個實例 → 停下來 | 骨架仍然正確；第 2 步**已過時** | 這段註解本身沒提 Argon，但 `show` 的第 2 步仍是「Argon 桶」（E6），而 agy 1.5.16 的 Argon 已經併進 Gemini 大組（E5），帳號池文件第四節也要一起改（見 D2）。同帳號的 Claude & GPT 桶在 T3 目錄裡看不到 Opus（E3），經 T3 派到 antigravity-opus 還能不能用，要實測 | 註解保留；接手順序拿掉 Argon 那一步（改程式與帳號池文件第四節）。第 2 步「同帳號 Opus」標【待驗證：T3 目錄沒列，要實測一次】 | 否（實測完再定） |
| B5 | `data/profiles/ryan/dispatch.md:19-20` | `exclude_models: [gemini-3.8-flash, gpt-oss-120b, gemini-4-argon]` | 仍然正確；有**缺漏** | 三個都已經從 T3 目錄消失，或價格表寫有後繼（E3、E6）。Carbon、Fable、Haiku 5.5 都沒有分工規則（見 C4） | 保留。Carbon、Fable 的處理放進 de030023 的分工表；Haiku 5.5 要不要排除，請 ryan 決定（建議：沒有角色就排除，跟 GPT-OSS 一樣） | 是（Haiku） |
| B6 | `data/profiles/ryan/dispatch.md:22-26` | 3 個 Claude 實例，classes 是 `[claude-opus, claude-sonnet]` | **缺漏** | 3 個實例都有 Fable 5.2（E2） | 等 C4 新增 `claude-fable` 類別後，三個實例都加上 `claude-fable` | 併 de030023 |
| B7 | `data/profiles/ryan/dispatch.md:27-33` | antigravity_ryan 的 classes 是 `[gemini-pro, gemini-fast, gemini-orchestrator, antigravity-opus]`；note 寫「Neon、Hydrogen、Orchestrator 最高 xhigh；Claude 最高 high」 | 部分**已過時**、有**缺漏** | T3 目錄只有 Neon、Hydrogen、Carbon（E3）；orchestrator 和 antigravity-opus 在 T3 都看不到，但 agy 的額度分組還列著（E5），所以「後端有，但 T3 沒列」 | classes 改成 `[gemini-pro, gemini-fast, gemini-carbon]`；`gemini-orchestrator`、`antigravity-opus` 先拿掉，或標【待驗證：T3 目錄沒列，經 T3 送代號實測通過才放回】。note 改成「Neon、Hydrogen 最高 xhigh；Carbon 最高 high」 | 是 |
| B8 | `data/profiles/ryan/dispatch.md:34-36` | 5 個 Pro 帳號是 1A（manual_only）；「11-23 實測 6 個實例 × Neon、Argon、Hydrogen、Orchestrator、3.8 Flash 全部能用」 | 1A 主旨仍然正確；實測那行**已過時** | 現在每個實例只列 Neon、Hydrogen、Carbon（E3） | 實測那行改成「2026-11-25 T3 目錄：每個 Antigravity 實例都列 Neon、Hydrogen、Carbon」，舊的實測紀錄移到帳號池文件 | 否 |
| B9 | `data/profiles/ryan/dispatch.md:42-44` | m6 恢復 Neon、manual_only；kai 已移除 | 仍然正確 | E1、E3 | 保留 | 否 |
| B10 | `data/profiles/ryan/dispatch.md:46-51` | 1A＋2B：5 個 Pro 只給 ryan 自己用、一次一個帳號；自動派工固定 antigravity_ryan、不輪換、一次一條 | 仍然有效，但跟 de030023 的新說法**矛盾** | de030023 的結論 3 寫「同時間集中用同 1 個帳號開多條對話平行做」（E8）。這跟 2B 的「一次一條」相反（2B 的依據是 staff 2026-10-07 建議低並行），也沒說它說的是手動帳號（1A）還是自動派工（2B）；另一條對話整理的多帳號風險表（Google 把同機多帳號背景打額度 API 視為帳號池），以及 DeskCat 改成閒置帳號不再換新 token（t3-deskcat `4e9d336`），都支持維持低並行 | 保留 1A＋2B。de030023 的「同帳號多條平行」如果要採用，限定在 1A 的手動帳號，而且要寫並行上限（建議 2）；自動派工維持 2B 的「一次一條」 | 是，併 de030023 |
| B11 | `data/profiles/ryan/dispatch.md:53` | delegate_task 派 Claude 先用目前實例，用完照順序換 | 跟 D3 **小矛盾** | D3 是「工作包邊界依額度挑」，用 weekly-first 策略（`2026-11-23-account-pool.md:12`，E6 的 show 也照 weekly-first 推薦） | 改寫：「派給 Claude 時照 `show` 的實例推薦（weekly-first，在工作包邊界挑，同一條對話不中途換）。」 | 否 |
| B12 | `data/profiles/ryan/dispatch.md:54` | Opus 子任務 effort 預設 medium（跟 AGENTS.md 重複） | 同 A3 | 同 A3 | 跟 A3 一起改；這裡只留一句「effort 照分工表」，不要寫兩份 | 併 de030023 |
| B13 | `data/profiles/ryan/dispatch.md:55` | Codex 註記：訂閱已到期，官方 Codex 不要當長期審查管道 | 仍然正確 | `codex` 實例停用（E1） | 保留；可以補一句「T3 的 codex 實例目前停用（2026-11-25）」 | 否 |
| B14 | `data/profiles/ryan/dispatch.md:56` | Antigravity 15 分鐘逾時；長主線優先用 Claude | 原則仍然正確，有一點**待驗證** | 上游寫死的事實來自 `dispatch-policy.md:261` 的原始碼查證（11-19）；T3 已經升過好幾版，這次沒有重查 | 保留；註記加上「下次 T3 升版時重查 `promptInactivityTimeout`」。ryan 現在自己的主線就跑在 Antigravity Carbon 上（de030023），更需要這條 | 否 |
| B15 | `data/profiles/ryan/dispatch.md:57` | 11-20 agy 多帳號修好；kai、m6 沿用原 id；Ryan 23 個模型、kai 6 個 | **已過時**（歷史紀錄） | kai 已移除，模型數不同了（E1、E3） | 移到帳號池文件的歷史段落，或刪掉 | 否 |
| B16 | `data/profiles/ryan/dispatch.md:60` | 3.8 Flash 分派限制（yaml 區塊外的重複版本） | 同 A6；而且這行寫在 yaml 區塊外，用 `#` 開頭，Markdown 會把它當成一級標題 | 同 A6 | **刪除**（跟 A6 一起） | 是（跟 A6 一起） |

### C. `data/rules/dispatch-policy.md`

| # | 條文位置 | 原文摘要 | 判斷 | 證據 | 建議 | 拍板 |
|---|---|---|---|---|---|---|
| C1 | `data/rules/dispatch-policy.md:19` | 模型代號取自 2026-11-14 的 capabilities | **已過時** | 目錄已經變了（E2、E3） | 日期改成這次重查的日期 | 否 |
| C2 | `data/rules/dispatch-policy.md:25` | `gemini-argon` 類別 | **已過時** | 已排除（`dispatch.md:20`），價格表寫後繼是 Carbon（E6），T3 目錄沒有（E3） | 刪掉這個類別，或在註解標「已淘汰，後繼 gemini-carbon」 | 否 |
| C3 | `data/rules/dispatch-policy.md:26` | `gemini-orchestrator`：`gemini-pro-orchestrator-neon` | **待驗證**（可能過時） | T3 目錄沒有；agy 的額度分組還列著 Orchestrator (Neon/Carbon/Argon)（E5） | 實測一次能不能經 T3 送這個代號；不能就刪掉，同時刪掉 `2026-11-23-account-pool.md:112` 那一列 | 是（實測後） |
| C4 | `data/rules/dispatch-policy.md:20-28` | model_classes 沒有 Carbon、Fable、Haiku | **缺漏** | E2、E3、E7 | 新增 `gemini-carbon: {model: gemini-4-carbon, driver: antigravity, default_thinking: high, max_thinking: high, forbid_thinking: [low, medium]}`，以及 `claude-fable: {model: claude-fable-5-2, driver: claudeAgent, default_thinking: high, max_thinking: max}`。要放進哪幾級，照 de030023 的分工表 | 併 de030023 |
| C5 | `data/rules/dispatch-policy.md:27`、`76-82` | `gemini-flash` 類別，以及中級 route 的 Flash 保底 | **已過時** | Flash 已排除、T3 目錄沒有；`show` 已經印「已過濾，跳過」（E6） | 刪掉這個類別和中級 route 第 3 項；帳號池文件 `:125` 那句「只有舊模型的帳號不過濾」的精神，留給開源給其他使用者用就好 | 否 |
| C6 | `data/rules/dispatch-policy.md:28`、`92-96` | `antigravity-opus` 類別，以及高級 route 第 1 項（Claude 用量 >= 80% 時用） | **待驗證** | T3 目錄沒有 Antigravity 的 Opus（E3）；agy 額度組還有，而且從沒用過（E5） | 實測一次（經 T3 用 `antigravity_ryan` 加 `claude-opus-5-5`）。能用就保留；不能用就刪掉，接手順序第 2 步也一起刪 | 是（實測後） |
| C7 | `data/rules/dispatch-policy.md:58-62` | 分工原則 A：Neon xhigh 是中級預設；Opus 只做重要的事；審查要跨家 | 骨架仍然正確；細節要**併 de030023** | de030023 提出「審 >= 做」、Fable 盲審、Carbon 反審（E8） | 等分工表定案後，在這段加上「審查者不比作者弱」與 Fable、Carbon 的角色 | 併 de030023 |
| C8 | `data/rules/dispatch-policy.md:97`、`105`、`111` | 高級 Opus high、更高級 Opus xhigh、驗收 Opus high | 跟 A3 **矛盾**；跟 de030023 **部分不一致** | de030023 建議高風險驗收用 xhigh、架構盲審用 Fable high（E8） | 併 de030023 一起定。建議：高級 Opus high；更高級 Opus xhigh；驗收 Opus xhigh；重大架構決策加一層 Fable high 盲審（新的 second_opinion，或新的 `architecture` 任務類型） | 併 de030023 |
| C9 | `data/rules/dispatch-policy.md:99`、`107`、`113` | second_opinion 一律 gemini-pro（Neon xhigh） | **缺漏** | de030023 建議「審 Claude 用 Carbon high」（E8）；帳號池文件第七節也寫「審查者不能比作者弱」 | 併 de030023：作者是 Opus 或 Fable 時，第二意見改成 Carbon high 或 Neon xhigh（哪個優先，看分工表） | 併 de030023 |
| C10 | `data/rules/dispatch-policy.md:116-121` | 升級路徑：Hydrogen → Neon → Opus high → higher → Opus max | 骨架仍然可用；有**缺漏** | 路徑裡沒有 Fable。de030023 主張不預設 max，改成升到 Fable high（E8，理由的數據【待驗證】） | 併 de030023。建議把最後一步改成 `{from: {class: claude-opus, thinking: xhigh}, to: {class: claude-fable, thinking: high}}`，max 留作 ryan 手動指定 | 併 de030023 |
| C11 | `data/rules/dispatch-policy.md:130`、`154`、`156`、`190`、`232` | 範例與實測寫 antigravity_kai、gemini-3.8-flash | **已過時**（範例指向不存在的實例） | E1 | 範例換成 antigravity_ryan 或 antigravity_m6 加 gemini-4-hydrogen；`:190` 的【待驗證】（m6、kai 模型清單是空的）已經不成立：m6 現在列 3 個模型（E3），刪掉 | 否 |
| C12 | `data/rules/dispatch-policy.md:188` | t3_thread_launch 的 Antigravity 選項 id 是 `thinking_level`，值是 low、medium、high | **錯誤**（已過時） | capabilities 的 id 是 `thought_level`，值多了 xhigh（E4）；`engine/scripts/accounts.py:280` 也用 `thought_level` | 改成 `thought_level`（low、medium、high、xhigh；Carbon 到 high 為止）。`dispatch.py:296` 印的 `thinking_level` 也要一起改，`engine/skills/omnikit-dispatch/SKILL.md:94` 同樣要改 | 否 |
| C13 | `data/rules/dispatch-policy.md:143-146` | t3 v0.1.10 沒有設定程度的參數；只測過 Hydrogen | **待驗證**（可能過時） | T3 已經升到 0.1.12 以上（`:174`）；這次沒查 `t3 thread start --help` | 下次改規則時重查 `--help`，有 `--option` 就改寫 | 否 |
| C14 | `data/rules/dispatch-policy.md:212-232` | visibility 的模式與退路 | 仍然正確（只有 `:232` 的範例要改，見 C11） | E6 | 保留 | 否 |
| C15 | `data/rules/dispatch-policy.md:256-262` | 15 分鐘逾時與主線處理 | 仍然正確（同 B14） | | 保留 | 否 |
| C16 | `data/rules/dispatch-policy.md:282-295` | Sonnet 試行；凍結到 2026-11-29 | 仍然有效；快要**到期** | 4 天後到期 | 到期時跟 de030023 的分工表一起決定 Sonnet 還留不留在中級 | 是（11-29） |
| C17 | `data/rules/baseline.md:3` | 改 policy 要更新規則版本（`dispatch-policy.md:5`） | 提醒 | 現在是 2026-11-23-1 | 照上面改完時，版本跳到 2026-11-2x-1 | 否 |

### D. `data/rules/dispatch.md` 與 `docs/proposals/2026-11-23-account-pool.md`

| # | 條文位置 | 原文摘要 | 判斷 | 證據 | 建議 | 拍板 |
|---|---|---|---|---|---|---|
| D1 | `data/rules/dispatch.md:3-12` | 共用層原則：什麼時候派、寫的與審的不同家、派前跑 show、派後驗收記帳 | 仍然正確 | 沒寫死任何模型 | 保留。de030023 的「審 >= 做」如果定案，可以在「寫的與審的不同家」那條後面補「而且審的不比寫的弱」 | 併 de030023 |
| D2 | `docs/proposals/2026-11-23-account-pool.md:60-64`、`67` | 額度三桶，Argon 獨立一桶；接手順序第 2 步是 Argon 桶 | **已過時** | agy 1.5.16 的 Argon 併進 Gemini 大組，也新增了 Carbon、Orchestrator (Carbon)（E5） | 改寫成兩組（Gemini Models、Claude and GPT models）；接手順序刪掉第 2 步；`engine/scripts/account_pool.py:1126-1140` 的 Argon 桶邏輯一起改 | 否 |
| D3 | `docs/proposals/2026-11-23-account-pool.md:104-115` | Ryan 現況的初步分工表（Argon 待定，Orchestrator 做大工作包） | **已過時**，會被 de030023 的表取代 | E3、E8 | 加一行「已由 2026-11-25 新分工表取代」並附連結，不要兩份並存 | 併 de030023 |
| D4 | `docs/proposals/2026-11-23-account-pool.md:117-125` | 模型淘汰過濾（資料驅動） | 機制仍然正確；有新的提醒要處理 | 價格表寫 Opus、Sonnet 的後繼是 Fable（E6）。照規則 1，那只會提醒、不會過濾（`show` 寫「提醒（不過濾）」），行為合理 | 保留。在文件註明「Claude 這邊的後繼提醒，只代表有更新的型號，不等於該換掉；Fable 比較貴，只放在特定角色」 | 否 |

### E. 引擎與 skill（不是規則檔，但會讓規則和輸出對不上）

| # | 位置 | 問題 | 建議 |
|---|---|---|---|
| X1 | `engine/scripts/dispatch.py`（`show`） | 沒有讀 ryan 的 Opus effort 覆寫（A3）：規則寫 medium，畫面印 high 或 xhigh | A3 定案後，在 profile 加一個 `effort_overrides` 之類的欄位，讓 `show` 讀它 |
| X2 | `engine/scripts/dispatch.py`（接手順序第 5 步） | 「可手動切換」只列 3 個實例，漏了 m1、m5、m6（E6） | 修這個列舉的 bug |
| X3 | `engine/scripts/dispatch.py:296`、`engine/skills/omnikit-dispatch/SKILL.md:94` | 寫 `thinking_level`，實際是 `thought_level`（C12） | 一起改 |
| X4 | `engine/skills/omnikit-dispatch/SKILL.md:63`、`79` | 範例寫 antigravity_kai 加 3.8 Flash | 範例換掉（`:63` 是歷史事件，可以保留，但加註「kai 已移除」） |

## 三、需要 ryan 決定的事

每一項都附建議。標「併 de030023」的，請跟那張分工表一起定，新主線一次改完，避免改兩次。

1. **刪除 3.8 Flash 分派限制（A6、B16）**：建議直接刪除。kai 不存在、Flash 已排除，這條規定派給一個已排除的模型。要保留精神的話，用 A6 的改寫文字。
2. **Claude 子任務的 effort（A3、A4、B3、B12、C8、C10）**：併 de030023。建議採用 de030023 的方向：日常 medium 或 high，高風險驗收 xhigh，max 不預設，最後一層升到 Fable 5.2 high。同時把 `thinking_preference: max_available` 限定在 Gemini。要讓 `show` 讀到覆寫，不然又會兩套。
3. **Fable 5.2 與 Carbon 的角色（C4、C7、C9、B6、B7）**：併 de030023。建議新增 `claude-fable`、`gemini-carbon` 兩個類別：Fable 只用在重大架構盲審與升級的最後一層；Carbon 當「作者是 Claude 時」的審查者。注意 Carbon 最高只到 high，跟「Gemini 一律最高檔」不衝突，但要寫明。de030023 調研裡的分數與價格都還沒有一手來源，建議定案時不要寫進規則，只寫角色。
4. **Antigravity 上的 Orchestrator 與 Opus 還能不能用（B4、B7、C3、C6）**：T3 目錄已經看不到它們，但 agy 的額度分組還列著。建議授權我（或新主線）各跑 1 輪最小實測（經 T3，`antigravity_ryan`，「只回 OK」），結果決定要刪掉還是保留。這兩個結果也會影響接手順序的第 2、3 步。
5. **同帳號多條平行對話（B10）**：併 de030023。de030023 建議同一個 Google 帳號開多條平行對話，這跟 2B 的「一次一條」相反。建議：自動派工維持 2B 一次一條；你自己手動用的 1A 帳號可以平行，但並行上限寫 2。依據是多帳號風險表，以及 Google 對低並行的建議。
6. **Haiku 5.5（B5）**：沒有任何角色會用到。建議放進 `exclude_models`，比照 GPT-OSS。
7. **Gemini API 的退路（A2）**：建議刪掉「退到 3.8 Flash」。整句要不要留，看你還會不會直接用 Gemini API（D1 已經決定不用 Vertex）。
8. **Sonnet 試行 11-29 到期（C16）**：併 de030023 一起決定 Sonnet 還留不留在中級。

**可以直接改、不用拍板的項目**（等上面定案時一起做，規則版本跳一版）：B1、B8、B11、B13、B15、C1、C2、C5、C11、C12、C13、D2、D4、X1 到 X4。

**跟 de030023 的分工**：de030023 負責「哪個角色用哪個模型、哪個程度」（第 2、3、5、8 項）。這份文件提供哪些條文要跟著改、哪些過時、哪些可以直接刪的清單。建議新主線開工時，把這份文件跟 de030023 的分工表放在一起，一次 commit 改完 `AGENTS.md`、`dispatch.md`、`dispatch-policy.md`、帳號池文件與引擎。
