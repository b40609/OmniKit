# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""驗證 OmniKit 名冊：data/slots.yaml 與 data/tools/*.yaml。

除了 JSON Schema，還檢查跨檔規則：檔名等於 id、id 不重複、槽位存在、
每個槽位最多一個預設、replaces 指向存在的工具。

用法：uv run engine/scripts/validate.py [--data <資料目錄>]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

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


def schema_errors(check, doc, path):
    return [
        f"{show(path)}: {'/'.join(map(str, e.absolute_path)) or '(整份)'}: {e.message}"
        for e in check.iter_errors(doc)
    ]


def main():
    parser = argparse.ArgumentParser(description="驗證 OmniKit 名冊")
    parser.add_argument("--data", type=Path, default=ROOT / "data", help="資料目錄，預設是 repo 的 data/")
    data = parser.parse_args().data.resolve()
    errors = []

    slots_path = data / "slots.yaml"
    slots_doc = load_yaml(slots_path)
    errors += schema_errors(validator("slots.schema.json"), slots_doc, slots_path)
    slot_ids = [s.get("id") for s in (slots_doc or {}).get("slots", []) if isinstance(s, dict)]
    for dup in sorted({i for i in slot_ids if slot_ids.count(i) > 1}):
        errors.append(f"{show(slots_path)}: 槽位 id 重複：{dup}")

    check_tool = validator("tool.schema.json")
    tools = {}
    tool_paths = sorted((data / "tools").glob("*.yaml"))
    for path in tool_paths:
        doc = load_yaml(path)
        found = schema_errors(check_tool, doc, path)
        errors += found
        if found:
            continue
        if doc["id"] != path.stem:
            errors.append(f"{show(path)}: id「{doc['id']}」跟檔名不同")
        tools[doc["id"]] = (path, doc)

    defaults = {}
    for tool_id, (path, doc) in tools.items():
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

    if errors:
        print(f"名冊驗證失敗，共 {len(errors)} 個問題：")
        for e in errors:
            print(f"- {e}")
        return 1
    print(f"名冊驗證通過：{len(slot_ids)} 個槽位、{len(tool_paths)} 張工具卡。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
