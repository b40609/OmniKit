# 試點紀錄：ryan（這台，Claude Code）

試點規則見 `docs/proposals/2026-11-15-maturity.md` 的 C：兩週、3 個指標（每週有沒有跑「給我建議」或週報、建議採納率、兩週後「少了 OmniKit 會不會非常失望」）。

## 2026-11-16（第 1 天）

- 指標 1：跑了「給我建議」（`%LOCALAPPDATA%\omnikit\advice\2026-11-16-claude.md`）。
- 建議內容：拿掉 graphify（裝 12 天、0 段對話）；瀏覽器用內建的就好（U1 實測）。裝與規則檔瘦身都沒有挑。採納與否等使用者回覆。
- 發現的問題：
  1. **已修**：plugin 裡附帶的 skill 不算已安裝。`document-skills` 帶了 skill-creator 與 frontend-design，建議卻叫你再裝 skill-creator；同一個 plugin 又因為「12 天沒用到」被列進拿掉，照做會連帶刪掉這兩個。修正：`usage.py` 列出 plugin 附帶的 skill，`advise.py` 不再建議裝、拿掉時警告。
  2. **待使用者**：profile 沒選領域，名冊外候選有 144 個，大多在沒做的領域（量化、CAD、影片）。agent 只能逐一略過。說「幫我設定 OmniKit」選領域後會只看選的。
  3. 規則檔每段對話約 5,020 tokens（佔開頭 5.9%），最大的是 `data/rules/dispatch.md`（約 2,559）。不值得現在動。
  4. `install:t3-code` 偵測不到（T3 是桌面程式），每次都會列；`detectable` 是 false，照 skill 規則先問使用者。
