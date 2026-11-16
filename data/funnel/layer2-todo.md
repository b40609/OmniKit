# 第 2 層待測清單（手寫）

2026-11-15 起取代 `schedule.py` 的自動排程與 `evidence.py` 的證據卡（見 `docs/proposals/2026-11-15-maturity.md` 的「瘦身」）。
維護者手動維護：想實測的寫一行，測完就刪掉並把結果寫進 `data/evals/`。`digest.py` 會列出這裡沒打勾的項目。

格式：`- [ ] 槽位：現任 對 挑戰者（客觀或盲選；備註）`

起始內容取自 2026-11-05 的排程（`data/funnel/layer2-schedule.json`），拿掉前端設計（11-13、11-14 已實測）。

- [ ] behavior-rules：（無現任）對 addy-agent-skills、alirezarezvani-claude-skills（客觀）
- [ ] behavior-rules：（無現任）對 ecc、ponytail（客觀）
- [ ] output-compression：（無現任）對 rtk（客觀，短）
- [ ] tool-discovery：（無現任）對 mcp-registry（客觀，短）
- [ ] code-understanding：native-search 對 claude-lsp、deepwiki-open（客觀，短；graphify 與 Floorplan 2026-11-16 已測，見 data/evals/2026-11-16-code-understanding-C1C2.md）
- [ ] browser：chrome-devtools-mcp 對 agent-browser、playwright-mcp（客觀，短）
- [ ] dev-workflow：bmad 對 compound-engineering 等 7 個（客觀，重；單組就超過每週額度，要先決定只跑一個 agent 或減少次數）
- [ ] memory：native-memory 對 ce-handoff、claude-mem、planning-with-files（客觀，重；同上）
