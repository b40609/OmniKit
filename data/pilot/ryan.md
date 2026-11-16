# 試點紀錄：ryan（這台，Claude Code）

試點規則見 `docs/proposals/2026-11-15-maturity.md` 的 C：兩週、3 個指標（每週有沒有跑「給我建議」或週報、建議採納率、兩週後「少了 OmniKit 會不會非常失望」）。

## 2026-11-16（第 1 天）

- 指標 1：跑了「給我建議」（`%LOCALAPPDATA%\omnikit\advice\2026-11-16-claude.md`）。
- 建議內容：瀏覽器用內建的就好（U1 實測）。原本還有「拿掉 graphify」，使用者指出證據不夠（見問題 6），已撤回並重出建議。裝與規則檔瘦身都沒有挑。
- 發現的問題：
  1. **已修**：plugin 裡附帶的 skill 不算已安裝。`document-skills` 帶了 skill-creator 與 frontend-design，建議卻叫你再裝 skill-creator；同一個 plugin 又因為「12 天沒用到」被列進拿掉，照做會連帶刪掉這兩個。修正：`usage.py` 列出 plugin 附帶的 skill，`advise.py` 不再建議裝、拿掉時警告。
  2. **待使用者**：profile 沒選領域，名冊外候選有 144 個，大多在沒做的領域（量化、CAD、影片）。agent 只能逐一略過。說「幫我設定 OmniKit」選領域後會只看選的。
  3. 規則檔每段對話約 5,020 tokens（佔開頭 5.9%），最大的是 `data/rules/dispatch.md`（約 2,559）。不值得現在動。
  4. `install:t3-code` 偵測不到（T3 是桌面程式），每次都會列；`detectable` 是 false，照 skill 規則先問使用者。
  5. **已修**：拿掉的建議沒寫「它做什麼、拿掉之後少了什麼」，使用者要自己問（「這不就是 OmniKit 的工作嗎？」）。現在每一項都附名冊的說明，以及這台同一件事還剩哪些工具與內建功能。
  6. **已修**：「拿掉」的依據之一是「同一件事名冊記了內建功能」，但內建功能沒實測過也算，graphify 因此被建議刪掉。使用者：「還沒實際比過就不能叫用戶拿掉，證據不夠」。現在只認實測過夠用的內建功能；graphify 與 document-skills 都不再列。agent 挑選時也犯了同樣的錯（理由寫了「內建夠不夠還沒實測」卻照樣挑）。
  7. 使用者要求實測 graphify：第 2 層（`data/evals/2026-11-16-code-understanding-C1C2.md`）結果是內建在兩個真實情境都不輸，graphify、Floorplan 裝著也 12 次沒被叫用。槽位答案改成內建（實測過），之後拿掉 graphify 的建議才有證據。順帶修了 `dispatch.py agy` 長說明放參數會讓呼叫端靜默結束的問題。
  8. **待修**：實測沒隔離設定資料夾，graphify 被算成今天用過，30 天內不會出現在拿掉。要不要拿掉由使用者看實測紀錄直接決定。實測腳本之後要用獨立的 `CLAUDE_CONFIG_DIR`。
- 指標 2：採納 1 項。使用者看完實測決定拿掉 graphify：Claude 端的 skill（`~/.claude/skills/graphify`）移到 `%LOCALAPPDATA%\omnikit\backup\2026-11-16-graphify-claude-skill`，要換回就移回原處。Codex 端的 skill 與 `graphify` CLI（`~/.local/bin`）沒動，這次實測只測 Claude Code。
