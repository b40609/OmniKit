# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""驗證 OmniKit 名冊：data/omnikit.yaml、data/slots.yaml、data/tools/*.yaml、data/profiles/ 與 data/mcp/servers.yaml。

除了 JSON Schema，還檢查跨檔規則：檔名等於 id、id 不重複、槽位存在、
每個槽位最多一個預設、replaces 指向存在的工具；規則有安全底線，profile 有 default、
每個 profile 都有 AGENTS.md，情境指向存在的槽位。

讀出的名冊裡，槽位情境是套上 profile 之後的：這台用 profiles.py 選過的 profile 優先，
沒有就用 data/omnikit.yaml 的 profile；那個 profile 沒寫的槽位沿用 slots.yaml 的範本。

repo 外的 profile（%LOCALAPPDATA%\\omnikit\\profiles，訪談產生的）只檢查這台在用的那一個：其他的跟名冊無關，
pre-commit 與 CI 也不該因為這台的個人檔案失敗。看板用的 profile（omnikit.yaml）一定要在 repo 裡。

用法：uv run engine/scripts/validate.py [--data <資料目錄>]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

import profiles  # 同目錄的 profiles.py：這台選的 profile

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "engine" / "schema"


class Loader(yaml.SafeLoader):
    """日期維持字串，交給 schema 的 pattern 檢查。"""


Loader.yaml_implicit_resolvers = {
    key: [r for r in resolvers if r[0] != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def show(path):
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_yaml(path):
    with path.open(encoding="utf-8") as f:
        return yaml.load(f, Loader=Loader)


def validator(name):
    return Draft202012Validator(json.loads((SCHEMA / name).read_text(encoding="utf-8")))


def explain(error):
    """oneOf 失敗時只會說「都不符合」；改報 source 類型對得上的那一種格式錯在哪。"""
    if not error.context:
        return [error]
    branches = {}
    for sub in error.context:
        branches.setdefault(sub.relative_schema_path[0], []).append(sub)
    matched = [
        subs for subs in branches.values()
        if not any(s.validator == "const" and list(s.relative_path) == ["source"] for s in subs)
    ]
    return matched[0] if len(matched) == 1 else [best_match(error.context)]


def schema_errors(check, doc, path):
    return [
        f"{show(path)}: {'/'.join(map(str, e.absolute_path)) or '(整份)'}: {e.message}"
        for error in check.iter_errors(doc)
        for e in explain(error)
    ]


def check_profile(d, slot_ids, check_scenarios):
    """一個 profile 資料夾：回傳（問題清單, {槽位: 情境}）；沒有 AGENTS.md 就不是 profile，情境是 None。"""
    if not (d / "AGENTS.md").is_file():
        return [f"{show(d)}: 少了 AGENTS.md（個人規則）"], None
    path = d / "scenarios.yaml"
    if not path.exists():
        return [], {}
    doc = load_yaml(path)
    errors = schema_errors(check_scenarios, doc, path)
    if errors:
        return errors, {}
    for slot, items in doc["scenarios"].items():
        if slot not in slot_ids:
            errors.append(f"{show(path)}: 找不到槽位「{slot}」")
        ids = [s["id"] for s in items]
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            errors.append(f"{show(path)}: 槽位「{slot}」的情境 id 重複：{dup}")
    return errors, doc["scenarios"]


def check_profiles(data, slot_ids, state=None, wanted=None):
    """回傳（問題清單, {profile 名稱: {槽位: 情境}}, repo 裡的 profile 名稱）。
    repo 裡的全部檢查；repo 外的只檢查這台在用的（wanted，沒給就是選過的），同名時它優先。"""
    errors, found = [], {}
    baseline = data / "rules" / "baseline.md"
    if not baseline.is_file():
        errors.append(f"{show(baseline)}: 找不到安全底線")
    root = data / "profiles"
    dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if profiles.DEFAULT not in [p.name for p in dirs]:
        errors.append(f"{show(root)}: 少了 {profiles.DEFAULT} profile（這台沒選 profile 時用它）")
    check_scenarios = validator("scenarios.schema.json")
    for d in dirs:
        if not profiles.NAME.match(d.name):
            errors.append(f"{show(d)}: profile 名稱只能用小寫英數與 -")
            continue
        bad, scenarios = check_profile(d, slot_ids, check_scenarios)
        errors += bad
        if scenarios is not None:
            found[d.name] = scenarios
    in_repo = set(found)
    name = wanted or (profiles.chosen(state) if state is not None else None)
    local = state / "profiles" / name if state is not None and name and profiles.NAME.match(name) else None
    if local and (local / "AGENTS.md").is_file():
        bad, scenarios = check_profile(local, slot_ids, check_scenarios)
        errors += bad
        found[name] = scenarios
    return errors, found, in_repo


def check(data, profile=None, state=None):
    """回傳（問題清單, 名冊）；名冊含 config、套上 profile 情境的 slots、依 id 排序的 tools、profile 名稱
    與它的資料夾（profile_dir）。state 是 %LOCALAPPDATA%\\omnikit（自我測試換成暫存資料夾）。"""
    state = profiles.STATE if state is None else state
    errors = []

    config_path = data / "omnikit.yaml"
    config = load_yaml(config_path) if config_path.exists() else None
    if config is None:
        errors.append(f"{show(config_path)}: 找不到公開設定檔")
    else:
        errors += schema_errors(validator("omnikit.schema.json"), config, config_path)

    mcp_path = data / "mcp" / "servers.yaml"
    if mcp_path.exists():
        errors += schema_errors(validator("mcp.schema.json"), load_yaml(mcp_path), mcp_path)

    slots_path = data / "slots.yaml"
    slots_doc = load_yaml(slots_path)
    errors += schema_errors(validator("slots.schema.json"), slots_doc, slots_path)
    slots = [s for s in (slots_doc or {}).get("slots", []) if isinstance(s, dict)]
    slot_ids = [s.get("id") for s in slots]
    for dup in sorted({i for i in slot_ids if slot_ids.count(i) > 1}):
        errors.append(f"{show(slots_path)}: 槽位 id 重複：{dup}")

    check_tool = validator("tool.schema.json")
    tools = {}
    for path in sorted((data / "tools").glob("*.yaml")):
        doc = load_yaml(path)
        found = schema_errors(check_tool, doc, path)
        errors += found
        if found:
            continue
        if doc["id"] != path.stem:
            errors.append(f"{show(path)}: id「{doc['id']}」跟檔名不同")
        tools[doc["id"]] = doc

    defaults = {}
    for tool_id, doc in tools.items():
        path = data / "tools" / f"{tool_id}.yaml"
        for slot in doc["slots"]:
            if slot not in slot_ids:
                errors.append(f"{show(path)}: 找不到槽位「{slot}」")
            if doc["status"] == "default":
                defaults.setdefault(slot, []).append(tool_id)
        if doc.get("replaces") and doc["replaces"] not in tools:
            errors.append(f"{show(path)}: replaces 指向不存在的工具「{doc['replaces']}」")
    for slot, ids in sorted(defaults.items()):
        if len(ids) > 1:
            errors.append(f"槽位「{slot}」有 {len(ids)} 個預設：{'、'.join(ids)}；一個槽位只能留一個")

    found_errors, found, in_repo = check_profiles(data, slot_ids, state, profile)
    errors += found_errors
    board = (config or {}).get("profile") if isinstance(config, dict) else None
    if board and board not in in_repo:
        errors.append(f"{show(config_path)}: 找不到 profile「{board}」（data/profiles/{board}/AGENTS.md）")
    chosen = profiles.chosen(state)
    name = profile or (chosen if chosen in found else None) or board
    overlay = found.get(name) or {}
    slots = [{**s, "scenarios": overlay.get(s.get("id"), s.get("scenarios"))} for s in slots]
    where = profiles.folder(data, state, name) if name else None

    return errors, {"config": config, "slots": slots, "tools": tools, "profile": name,
                    "profile_dir": str(where) if where else None}


def main():
    parser = argparse.ArgumentParser(description="驗證 OmniKit 名冊")
    parser.add_argument("--data", type=Path, default=ROOT / "data", help="資料目錄，預設是 repo 的 data/")
    data = parser.parse_args().data.resolve()
    errors, roster = check(data)
    if errors:
        print(f"名冊驗證失敗，共 {len(errors)} 個問題：")
        for e in errors:
            print(f"- {e}")
        return 1
    tool_count = len(list((data / "tools").glob("*.yaml")))
    print(f"名冊驗證通過：{len(roster['slots'])} 個槽位、{tool_count} 張工具卡，情境用 profile：{roster['profile'] or '（範本）'}。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
