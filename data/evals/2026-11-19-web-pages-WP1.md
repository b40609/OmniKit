# 網頁槽位第 2 層：Huashu Design 對 taste-skill（WP1，2026-11-19）

Ryan 2026-11-19 定案（NOW.md 決定 3）：第 2 層先只跑 Huashu Design，在 WP1 跟 taste-skill 盲選；OpenDesign 等這次的結果再說。

## 要回答的問題

做公司官網、產品介紹頁這類網頁（WP1：「第一眼要有質感，像業界的高品質網頁，不是一般 AI 產生的樣子」），Huashu Design 有沒有比現在試用中的 taste-skill 好？兩個有沒有比不裝設計 skill 好？

會改變的決定：

- Huashu 勝出：web-pages 槽位改試用 Huashu（`trial`），taste-skill 回 `pending`；OpenDesign 維持等待。
- taste-skill 勝出或平手：taste-skill 照原本的試用期（到 2026-11-28）繼續，Huashu 記 `rejected` 或維持 `pending`（看差距），OpenDesign 再看要不要評。
- 兩個都沒贏過不裝 skill：試用到期時 taste-skill 不轉預設，網頁槽位維持「不指定 skill」。

## 題目

替 OmniKeep 做一頁產品介紹頁（官網首頁）。OmniKeep 是 Ryan 自己的產品，正要發 v1.6.0、給同事試用，這頁有真的用途。

- 事實來源：OmniKeep 的 README（2026-11-19 從公開的 GitHub repo `b40609/OmniKeep` 取得，放進每組工作資料夾的 `content/README.md`）。頁面上的功能、安裝方式、限制都要對得上；不准編造功能、數據、使用者評價、合作夥伴 logo。
- 沒有品牌規範、沒有 logo，各組自己定。這是 Huashu 自己說「從零設計品質會掉到 60 到 65 分」的情況，但 WP1 的真實情境就是這樣（Ryan 的產品都沒有品牌規範），所以照實測。
- 不准問問題：這次沒有人回答。skill 要求先問或讓使用者挑方向時，各組照簡報自己決定，並把替使用者做的決定寫在 `site/NOTES.md`。要出多個方向的，挑一個做完整版。這對 Huashu 比較不利（它的流程是「六個候選、使用者看著選」），寫進弱點。

## 組別

| 組 | skill | 版本 |
|---|---|---|
| taste-skill | `.agents/skills/taste-skill` | 本機裝的 plugin 2.5.1（`skills/taste-skill` 整個資料夾） |
| huashu-design | `.agents/skills/huashu-design` | alchaincyf/huashu-design `e8d1148`（v3.3.0，2026-11-19 掃描的那個 commit） |
| 不裝 | 無 | 只給簡報，提示寫明不要叫用任何設計類 skill |

- 執行：T3 子對話，Kai 的 Claude（`claudeAgent_claude_kai`），Opus 5.5，effort high，full-access。三組同一份簡報，同時開跑。前三輪用 retis，這次 retis 的週額度已用 93%，改用 Kai；同一個模型，只換帳號。
- 三組都看得到 Kai 全域裝的 taste-skill 與 unslop。提示要求只用指定的那一個（不裝組不准用），事後讀對話紀錄確認有沒有違規叫用。

## 決策規則（實測前寫下）

1. **硬性條件**（任一不過，該組出局）：
   - 交付在 `site/`，靜態檔，`python -m http.server` 開得起來，不用建置。
   - 1440 寬與 375 寬沒有 console 錯誤、沒有橫向捲動。
   - 內容對得上 README：沒有編造的功能、數字、評價、logo；安裝指令跟 README 一樣。主控逐條核對。
2. **主要依據：Ryan 盲選**，用 `scripts/blind.py`，三組隨機標成 A、B、C，選完才解封。照前三輪的做法分兩段：先灰階只評版面與層級，再彩色只評配色；判定以灰階為主，配色只在灰階平手時分高下。Ryan 另外說「哪一個最像業界的高品質網頁」。
3. **次要依據：Gemini 評審**（Gemini 4 Hydrogen，thinking xhigh，不同模型家族），只看 `blind.py shots` 的截圖、不知道組別，評「第一眼質感」與「像不像一般 AI 做的」兩項，Ryan 選完才公開。
4. **判定：**
   - Ryan 灰階選 Huashu 第一：Huashu 進試用（上面第一種）。
   - Ryan 灰階選 taste-skill 第一，或 Huashu 與 taste-skill 平手：維持 taste-skill 試用。
   - Ryan 選不裝的第一：兩個都沒證明比不裝好（上面第三種）。
   - 每組只跑 1 次，有隨機性；差距小時寫明「這一輪」，不當定論。

## 設定與紀錄

- 準備與執行：`2026-11-19-web-pages-WP1/prepare.py`；三組的交付、截圖、對話 id、耗時、額度放在 `2026-11-19-web-pages-WP1/`。
- Huashu 的第 0 層：門檻 warn（掃描有 CRITICAL），1 個 skill、58 個 finding。CRITICAL 都是 `scripts/` 裡 4 支用 `child_process` 的腳本（`tts-doubao.mjs`、`narrate-pipeline.mjs`、`render-video-seek.js`、`render-video.js`），讀過程式碼：都是用參數陣列呼叫固定的 `ffprobe`、`ffmpeg`、`node`，沒有開 shell，判定誤判。MEDIUM 是選用的雲端配音（要自己的 key）、`fetch_images.py` 抓免版權圖片，以及音效 mp3 這類掃不了的二進位檔。它會在 `~/.huashu-design/` 寫本機的品味紀錄（README 說法）。

## 第二版（2026-11-19 15:20，盲選前改的規則）

- 第一版做到一半，Ryan 先打開了 taste-skill 那一版，直接在那條子對話留話：「為什麼檢查 1440 與 390？大部分螢幕都是 1080x1920 要我講幾次？現在這個畫面很普通，我偏好深色 iOS 官網風格 https://www.apple.com.cn/iphone-18-pro/」。
- 檢查寬度 1440 是主控寫錯的簡報，不是 skill 的問題。為了公平，主控把同一段要求原樣轉給另外兩組，三組都做第二版：深色、iOS 官網風格，桌機 1920×1080、手機 390 檢查。盲選、截圖、評審都改用 1920 寬。
- 這輪的弱點：Ryan 盲選前已看過 taste-skill 的第一版，盲選時可能認得出來；第一版的結果只存檔，不進判定。
- 第一版的額度中斷：Kai 的 5 小時額度在 12:28 用完，taste-skill、huashu-design 兩組中途停下，14:42 從斷點續跑（不是重來）。

## 第二版的執行（2026-11-19 下午到晚上）

- 三組由桌面版改到 Ryan 帳號的 Claude Opus 5.5（effort 改 medium，見 ryan 規則 2026-11-19 定案），並換上 Ryan 自選的 15 則收藏：taste-skill 組在隔離的示範版產生共用的 11 張真實截圖（`~/.omnikit-wp1-demo/screens/`），另兩組拿同一批截圖換掉自己畫的示意畫面。所以三組的產品畫面都是同一批真實截圖，差別在版面、文案與配色。
- 三條子對話都在 18:19 settle。成品搬進 `2026-11-19-web-pages-WP1/sites/<組>/`：`collect.py` 從 index.html 追引用到的檔，再照盲選服務的 404 紀錄補上 taste-skill 的響應式圖片與動態載入的 CSS，三組都是 0 筆 404（各約 1 MB；skill 的工作檔、打磨截圖沒搬）。
- 盲選：`2026-11-19-web-pages-WP1/blind/`（`spec.json`，封存 SHA-256 開頭 `15dd7f74`）。`blind.py shots` 的 1920×1080 與 390×844 截圖在 `blind/shots/`，檔名只有標籤。
- `blind.py` 順手修了三個問題：截圖尺寸預設改 1920×1080／390×844 並可由 spec 的 `sizes` 指定；傳給 Chrome 的截圖路徑改絕對路徑（相對路徑在 Windows 不會寫出檔）；每張截圖用自己的 `--user-data-dir`。

## 結果

（Ryan 盲選後填）
