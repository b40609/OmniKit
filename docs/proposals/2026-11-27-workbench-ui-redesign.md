# OmniKit 大改版提案：本機前端控制面板 × 一鍵滿血工作台

- 日期：2026-11-27
- 狀態：**已拍板定案並實作中**（使用者「全照建議」拍板 1–4，並經跨家兩階段架構盲審收斂 5 項 P0 修補）
- 雙線獨立飽和調研與兩階段盲審依據：
  1. 線 1（Gemini 4 Hydrogen xhigh，12 組 235 項，聚焦控制面板與一鍵工作台精靈）：`~/.omnikit/status/OmniKit/reports/2026-11-27-前端控制面板與一鍵工作台-飽和調研.md`
  2. 線 2（Claude Opus 5.5 xhigh，12 組 155 項、73 repo 實測 verify，廣域 5 維度）：`~/.omnikit/status/OmniKit/reports/2026-11-27-廣域AI工作台與零門檻前端體驗-飽和調研.md`
  3. 兩階段防迎合架構盲審（Stage 1 零錨定設計＋Stage 2 正面對決）：`~/.omnikit/status/OmniKit/reports/2026-11-27-workbench-ui-blind-review.md`

---

## 1. 為什麼大改（問題定性）

創作者以真實新用戶角度實測 `v0.1.2` 後，暴露出「維護者滿血版」與「新用戶開箱版」的嚴重斷層：

1. **前端隱形**：現有 Cockpit（`engine/cockpit/`）被藏在維護者文件，同事版裝完畫面上什麼都沒有。
2. **訪談陽春且強硬**：終端機文字問卷只有 6 題，領域選完不幫裝任何工具，痛點 4 選 2 還彈回逼重選，產出僅十幾行通用規則。
3. **預設全空**：精選 plugin 不自動裝也不加 marketplace，MCP 全套只有 1 個，進階能力全藏在 4b 之後。
4. **狀態板門檻顛倒**：`NOW.md` 與交接要求先建 GitHub 私人 repo，小白第一步就被勸退（其實 `collector.py:638-639` 底層已支援純本機資料夾）。

---

## 2. 產品新定位（一句話）

> **一個本機前端控制面板：裝完自動開啟，選一張角色卡就能一鍵勾選裝齊一整套跨 Claude Code／Codex／Antigravity 的精選工作台；專案進度直接跑在本機看板，零帳號、免先建 GitHub repo。**

---

## 3. 業界雙線調研核心收斂（去重後 7 大設計原則）

| 原則 | 業界標竿（2026-11-27 實測 ★） | OmniKit 落地做法 |
|---|---|---|
| **1. 勾好預設＋價目表式滿血** | Ninite、LazyVim Extras（★27,936）、VS Code Profiles、UniGetUI（★27,282） | 預先勾好核心＋角色套餐，每項可單獨開關、重跑冪等、可匯出分享給同事 |
| **2. 3 分鐘內出現第一個 Wow** | CodePilot（★6,524）、Pinokio（★8,447）、CC Switch（★157,618） | 廢除 6 題阻斷問卷；首次啟動 4 步流（偵測 → 選角色卡 → 預覽 → 一鍵套用），落地即見本機專案看板 |
| **3. 滿血但不塞爆 Context** | MCP Client 最佳實踐（1%–5%）、Claude Code Tool Search（10%）、Skills 漸進揭露（1%） | 每個套餐／工具卡標註「開場 Context 成本」＋首頁預算條（>= 5% 轉黃、>= 10% 轉紅）＋支援按專案資料夾啟用 |
| **4. 本機優先零帳號看板** | Backlog.md（★7,502）、Super Productivity（★24,130）、Vibe Kanban（★28,839） | `NOW.md` 與交接預設直接存 `~/.omnikit/status/<專案>/`，免帳號、免 GitHub repo；跨機同步與手機唯讀改為選配精靈 |
| **5. 單一事實來源＋防漂移** | chezmoi（★22,386）、Homebrew Bundle、WinGet Configuration | GUI／精靈／CLI 統一寫入一份宣告式 `kit.yaml`（暫名），由既有 `sync.py` 冪等渲染到三家受管區塊與薄 plugin；外部手改時跳漂移橫幅三選一 |
| **6. Windows 本機零摩擦啟動** | Vite（自動換 port）、Jupyter（帶 token 網址）、原生 Python＋離線 PWA | 只綁 `127.0.0.1`（免防火牆彈窗），偏好 3780 被占自動順延，記錄實際 port 供 `omnikit open` 使用；不包未簽章 exe（免 SmartScreen）、零 Docker 依賴 |
| **7. 信任分級＋白話介面** | Obsidian 安全計分卡、Docker 誠實聲明、NN/g 空狀態指引 | 工具區分四級信任標章（內建／精選／社群／本機自訂）＋每週自動標示封存 repo；小白模式全白話，維護者術語收進進階模式 |

---

## 4. 新版前端資訊架構（從 4 頁唯讀面板升級為 5 區控制中心）

將既有 `engine/cockpit/` 原生離線 PWA 升級（零建置工具、零外部 CDN、保有既有 Host 白名單＋Token＋Tailscale 唯讀安全邊界）：

```text
┌ OmniKit 控制面板（http://127.0.0.1:<port>/?t=…）────────────────────────┐
│ 1. 首頁 / 精靈   首次：4 步開箱精靈；日常：今日狀態、健康紅綠燈、快速微調  │
│ 2. 專案看板      本機 NOW.md 卡片（零帳號免 GitHub）、一鍵加入本機資料夾   │
│ 3. 工作台商店    角色套餐一鍵勾選、精選 Plugin/Skill/MCP/CLI 開關、預算條  │
│ 4. Agent 與額度  三家接上狀態、Doctor 健檢＋一鍵修復、多帳號額度與重置倒數 │
│ 5. 設定          語言／習慣（自由複選無上限）、安全規則、選配同步、匯出入  │
└─────────────────────────────────────────────────────────────────────────┘
```

- **小白模式（預設）**：只顯示白話文案（例如「工具清單、工作類型、更新進度、結案、我的設定」），每個頁面底部可選擇展開「對應 CLI 指令」與「進階檢視（`kit.yaml` 原文、架構地圖、渲染差異）」。
- **終端機與對話入口保留為備援**：`/ok`、`$ok` 與 `omnikit-setup` 保留給純終端用戶，但預設優先引導開啟本機前端控制面板。

---

## 5. 首次開箱體驗流（目標：3 分鐘內、點擊 <= 5 次、必填 1 步）

1. **`install.ps1` 跑完自動開瀏覽器**（終端同步印出帶 token 網址，加 `-NoBrowser` 可略過；無須系統管理員權限）。
2. **步驟 1｜自動偵測（零提問）**：顯示已偵測的 Claude Code／Codex／Antigravity、既有規則與 MCP（標明不覆蓋）、掃描到的本機專案資料夾、環境前檢（Node／Git／uv／防毒）。
3. **步驟 2｜選工作台角色卡（唯一必選，可複選）**：
   - 內建角色：軟體開發全配、科研與數據分析、研究與寫作、辦公與文件、量化工程、CAD 機構、輕量安全護欄、我都要。
   - 每張卡直接預勾對應套餐，右下角可展開微調單項工具、語言詳略與工作習慣（**完全移除「最多 2 項」限制**，所有習慣自由複選，只擋真正矛盾的組合）。
4. **步驟 3｜預覽與價目表（Dry-Run）**：
   - 顯示將寫入／新增 N 項、保留不動 M 項。
   - 顯示三家 Agent 各自的**開場 Context 預算條**。
   - 需要 API Key 的選配項提供「先略過」或「安全輸入（存環境變數／OS Credential Manager，絕不寫明文）」。
5. **步驟 4｜一鍵套用 → 直達 Wow 看板**：
   - 三家 Agent 與套餐安裝即時進度條（含自動補裝勾選的精選 plugin／skill／MCP／CLI，不再叫人手打 marketplace 指令），失敗直接顯示 stderr 與一鍵重試。
   - 完成後自動落地「專案看板」：已帶出偵測到的本機專案與首張 `NOW.md` 草稿，頂部掛可收合「3 步體驗卡」（1. 打開專案試打 `/ok`；2. 試一個護欄或研究範例；3. 跑一次 Doctor 綠燈）。

---

## 6. 套件五層架構與本機狀態板演進

### 6.1 套件五層（Kitfile 宣告式管理）

| 層級 | 內容 | 預設勾選 | 治理門檻 |
|---|---|---|---|
| **L0 安全底線** | `baseline.md`、金鑰／捷徑確定性護欄、刪除／外發／付款前確認 | 一律開啟（不可關） | 只能更嚴 |
| **L1 核心工作台** | 6 個核心 skill、`/ok`、`chrome_devtools` MCP、本機 `NOW.md` 看板與交接、環境 Doctor | **預設全勾** | 零帳號、零外連、開場 Context 低於 1% |
| **L2 角色套餐** | 對應領域精選 plugin／skill／CLI（如 `frontend-design`／`impeccable`、`skill-creator`、`bmad`、`rea`、`deja-vu` 等） | 依角色卡預勾 | 標註開場 Context 成本；可按專案目錄啟用 |
| **L3 Extras 商店** | 166 張工具卡的單項自選安裝／開關 | 不預勾 | 顯示四級信任標章與健康度（封存／久未更新紅標） |
| **L4 實驗試用** | 試用中工具（帶到期日與自動提醒結算） | 不預勾 | 到期提醒決定轉正或退場 |

### 6.2 本機狀態板四段演進（徹底拔除 GitHub 前置門檻）

| 階段 | 儲存與同步方式 | 需要什麼 | 適用對象 |
|---|---|---|---|
| **第 0–1 段（開箱預設）** | `~/.omnikit/status/<專案>/NOW.md` 本機資料夾（背景自動 `git init` 留本地歷史與還原，UI 不露 git 術語） | 零帳號、零設定 | 所有小白與單機用戶，裝完即用 |
| **第 2 段（選配）** | 設定頁「跨電腦同步精靈」綁定私人 GitHub repo 或任意 git remote | GitHub 帳號（選配） | 多台電腦同步的進階用戶 |
| **第 3 段（選配）** | Tailscale Serve HTTPS 唯讀檢視（Cockpit 現有功能） | Tailscale（選配） | 手機隨時看進度與球權 |

*(一次只允許單一同步來源，並於 UI 明示不可疊加 Syncthing／OneDrive／iCloud 鏡像避免檔案衝突。)*

---

## 7. 建議分期落地切片（待拍板後展開實作計畫）

| 階段 | 核心交付 | 驗收門檻 |
|---|---|---|
| **M1｜底座與零門檻解鎖（P0）** | ① Cockpit 自動選 port＋寫狀態檔＋`omnikit open`＋帶 token URL；② `omnikit-handoff` 與 Cockpit 轉正「純本機 `NOW.md`（背景本地 git）」免建 GitHub repo；③ 移除 `pains` 限選 2 項、補齊更豐富工作習慣與角色選項 | 3780 被占仍 5 秒開頁無防火牆彈窗；零帳號 1 分鐘內完成「新增本機專案 → 建 `NOW.md` → 寫交接」 |
| **M2｜前端四步開箱精靈與一鍵套用（P0）** | ① `install.ps1` 收尾自動開啟 Cockpit 開箱精靈；② 串接 `scan.py`＋`doctor.py`＋`profile_new.py`＋`sync.py` 實作偵測→選角色→預覽→套用＋進度條；③ 首次完成落地看板＋3 步體驗卡＋Doctor 紅綠燈修復頁 | 新機乾淨安裝至看到本機專案與套用完成 <= 3 分鐘、點擊 <= 5 次、必填 1 步 |
| **M3｜工作台一鍵勾選商店與 Kitfile（P1）** | ① 導入 `~/.omnikit/kit.yaml` 單一事實來源＋漂移橫幅；② 前端「工作台」分頁支援一鍵安裝／開關精選 plugin／skill／MCP／CLI（自動處理 marketplace 與三家同步）；③ 工具卡補 `context_cost`、`trust`、`health` 與預算條 | 前端勾選即自動完成跨三家同步與 plugin 安裝；手改受管設定後 GUI 出現漂移處理橫幅 |
| **M4｜跨機分享與進階同步（P2）** | ① 一鍵匯出／匯入工作台套件包（Bundle）；② 設定頁「綁定 GitHub 跨機同步」精靈；③ 依專案資料夾啟用角色套餐（待先實測 Codex／Antigravity 延後載入能力） | 匯出檔傳給另一台電腦一鍵重現完整工作台 |

---

## 8. 必避的工程紅線

1. **嚴守無帳本邊界**：前端寫入只能透過受管區塊與薄 plugin，絕不整檔 `JSON.stringify` 覆寫使用者手寫設定，絕不弄斷 symlink。
2. **禁止無上限預載**：不因「給到滿」就一次把幾十個 MCP／全域 Skill 全塞進開局 context，必守 5% 警戒線與漸進揭露。
3. **零 Docker／零未簽章 exe／零雲端綁定**：Windows 11 開箱僅依賴既有 Git＋Node＋uv＋原生離線 PWA。
4. **必須有「跳過／靜音」逃生口**：不想走精靈的人可一鍵用安全預設跳過，絕不每次啟動重複彈窗。

---

## 9. 已拍板決策與兩階段盲審 P0 修補定案（2026-11-27）

1. **單一事實來源 `~/.omnikit/kit.yaml`（已定案）**：GUI／精靈／CLI 統一經 `engine/scripts/kit.py`（含 OS 層全機鎖與 `rev` 樂觀鎖、保留未知鍵）寫入 `~/.omnikit/kit.yaml` 並同步鏡像 `profile.json`；搭配 `~/.omnikit/state/applied.json` 三方比對，`sync.py --background` 遇使用者外部手改絕不覆蓋，改由控制面板跳漂移橫幅三選一（收進設定／還原面板設定／暫緩 7 天）。
2. **L1／L2 預設「給到滿」邊界（已定案）**：L1 核心預設全勾；L2 角色套餐透過本機鎖定版本的工作台 marketplace 與安裝器一鍵幫裝不需金鑰的精選工具，需要 API Key 的工具留到選配（金鑰不落明文設定檔、不寫登錄檔環境變數）。
3. **本機 `NOW.md` 免 GitHub＋`status.py`（已定案＋P0-3 修補）**：由 `engine/scripts/status.py` 自動在 `~/.omnikit/status` 執行 `git init -b main`，僅對新初始化的本機狀態庫寫入 repo 級固定身分（`OmniKit <omnikit@localhost.invalid>`）與 `commit.gpgsign=false`、加上 `GIT_TERMINAL_PROMPT=0` 與 `GIT_CEILING_DIRECTORIES`，確保未設 git 身分的新電腦也能 100% 成功保留本地版本歷史與還原；既有遠端狀態庫原封不動相容。
4. **伺服器獨佔綁定、安全認證與按需啟動（已定案＋P0-1／P0-5／P1-1 修補）**：
   - 認證維持同源 `/api/session` + `X-OmniKit-Token`（**網址不帶 `?t=` token、也不用 cookie**，避免進 log／PWA 快取／瀏覽器歷史），並補齊 `Origin` 精確埠號比對、`Sec-Fetch-Site` 檢查與 `sw.js` 去 query 快取鍵。
   - Windows 伺服器強制開啟 `SO_EXCLUSIVEADDRUSE` 與 `allow_reuse_address=False`，杜絕重複綁埠；`cockpit.py launch` 透過 WMI 脫離背景啟動並以 `/api/health` 的 `instance` 驗證重用，日常預設用完可關＋開始功能表捷徑／`cockpit.py open` 一鍵開啟，登入常駐留於設定頁手動開（常駐與 Tailscale 模式固定埠不順延）。
