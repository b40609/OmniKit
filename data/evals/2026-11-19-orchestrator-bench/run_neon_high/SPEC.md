# 任務規格：model_router（純 Python 標準函式庫）

在目前工作目錄實作 Python 套件 `model_router/` 與單元測試 `tests/test_model_router.py`，只使用 Python 3.12+ 標準函式庫（禁止第三方套件）。

## 1. `model_router/catalog.py`

實作三個函式：

1. `parse_t3_capabilities(data: dict) -> list[dict]`
   - 讀取 T3 `orchestrator_capabilities` 的 JSON dict（內含 `providers` 清單）。
   - 為每個 provider 的每個 model 輸出一筆 dict，包含欄位：
     - `source`: `"t3"`
     - `provider_id`: `provider["providerInstanceId"]`
     - `driver`: `provider["driverKind"]`
     - `enabled`: `bool(provider.get("canRunChildTask"))` 且 `constraints` 裡不含 `"disabled"`（不分大小寫）
     - `model_id`: `model["id"]`
     - `label`: `model.get("label") or model["id"]`
     - `thinking_param`: 從 `model.get("options", [])` 找 `id` 為 `"effort"` 或 `"thinking_level"` 的選項 id，沒有則為 `None`
     - `thinking_values`: 對應選項的 `values` list[str]，沒有則為 `[]`
     - `default_thinking`: 對應選項的 `default`，沒有則為 `None`

2. `parse_agy_models(text: str) -> list[dict]`
   - 解析 `agy models` 的純文字輸出（每行 `<model_id>\t<label>`）。
   - 忽略空白行或不含 `\t` 的訊息行（例如 `Fetching available models...`）。
   - 若 `model_id` 以 `-low`、`-medium`、`-high`、`-xhigh`、`-max` 結尾，拆出 `base_model`（去掉後綴）與 `thinking_suffix`（不含連字號）；否則 `base_model` 等於 `model_id`、`thinking_suffix` 為 `None`。
   - 每筆回傳：`{"source": "agy", "model_id": ..., "label": ..., "base_model": ..., "thinking_suffix": ...}`。

3. `diff_catalogs(old_items: list[dict], new_items: list[dict]) -> dict`
   - 索引鍵：`(item.get("provider_id") or item.get("source"), item["model_id"])`。
   - 回傳 `{"added": [...], "removed": [...], "changed": [...]}`：
     - `added`: 新清單有、舊清單無的項目（依鍵排序）。
     - `removed`: 舊清單有、新清單無的項目（依鍵排序）。
     - `changed`: 鍵相同但 `enabled`、`thinking_values` 或 `default_thinking` 不同的項目，每筆格式 `{"key": [provider_or_source, model_id], "old": old_item, "new": new_item, "changes": [變動的欄位名清單]}`（依鍵排序）。

## 2. `model_router/resolver.py`

實作函式：

`resolve_role(role_name: str, policy: dict, catalog: list[dict], overrides: dict | None = None) -> dict`

- `policy` 結構：
  ```json
  {
    "roles": {
      "gemini-strong": {
        "forbid_thinking": ["low", "medium"],
        "candidates": [
          {
            "provider_id": "antigravity",
            "model_pattern": "gemini-4-*",
            "exclude_patterns": ["*-argon*"],
            "prefer_order": ["gemini-4-neon", "gemini-4-hydrogen"],
            "thinking": "high"
          }
        ]
      }
    }
  }
  ```
- 規則：
  1. 若 `role_name` 不在 `policy.get("roles", {})`，回傳 `{"ok": False, "reason": "unknown_role", "error": ...}`。
  2. 先處理 `overrides`（若提供且含 `role_name`）：
     - `overrides[role_name]` 格式為 `{"provider_id": ..., "model_id": ..., "thinking": ...}`。
     - 檢查 `thinking` 是否在該角色的 `forbid_thinking` 內；若違反，立即回傳 `{"ok": False, "reason": "forbidden_thinking", "error": ...}`（不可靜默降級或忽略）。
     - 在 `catalog` 中尋找對應 `provider_id` 與 `model_id`：
       - 不存在或 `enabled` 為 `False` → 回傳 `{"ok": False, "reason": "override_unavailable", "error": ...}`。
       - 若該模型有 `thinking_values` 且 `thinking` 不在其中 → 回傳 `{"ok": False, "reason": "unsupported_thinking", "error": ...}`。
       - 否則回傳 `{"ok": True, "provider_id": ..., "model_id": ..., "thinking": ..., "thinking_param": ..., "matched_by": "override", "fallback_index": -1}`。
  3. 無 override 時，依序遍歷 `role["candidates"]`（索引 `idx = 0, 1, ...`）：
     - 候選的 `thinking` 若在角色的 `forbid_thinking` 內，跳過並記錄到 `tried`。
     - 從 `catalog` 篩選符合：`enabled == True`、`provider_id` 相符（若候選有寫）、`fnmatch` 符合 `model_pattern`、不符合任一 `exclude_patterns`、且（若模型有 `thinking_values`）`thinking` 在 `thinking_values` 內。
     - 若有多個符合的模型：先依候選的 `prefer_order` 順序排（在 `prefer_order` 裡越前面越優先），其餘依 `model_id` 字典序排。
     - 取第一個符合的模型回傳：
       `{"ok": True, "provider_id": ..., "model_id": ..., "thinking": ..., "thinking_param": ..., "matched_by": "policy", "fallback_index": idx}`。
  4. 若全部候選都失敗，回傳 `{"ok": False, "reason": "no_candidate_available", "error": ..., "tried": [...]}`。

## 3. `model_router/cli.py`

支援 `python -m model_router.cli` 三個子指令（皆支援 `--json` 輸出 JSON 到 stdout）：
- `catalog --t3 <t3_json_path> [--agy <agy_txt_path>] [--json]`
- `diff --old <old_t3_json_path> --new <new_t3_json_path> [--json]`（先 parse 再 diff）
- `resolve --role <role_name> --policy <policy_json_path> --t3 <t3_json_path> [--override <provider_id:model_id:thinking>] [--json]`
  - `resolve` 成功結束碼 `0`；失敗（`ok: False`）仍印出結果 JSON 且結束碼 `2`。

## 4. 驗收要求

- 在 `model_router/__init__.py` 匯出核心函式。
- 在 `tests/test_model_router.py` 以 `unittest` 覆蓋三個模組與 CLI 的正常與邊界情況（至少 10 個測試案例）。
- 必須實際執行 `python -m unittest discover -s tests -v` 並確認全部通過。
- 不要修改目前工作目錄以外的任何檔案。
