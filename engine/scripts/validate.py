# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""驗證 OmniKit 名冊：data/omnikit.yaml、data/modules/、data/tools/*.yaml、data/profiles/ 與 data/mcp/servers.yaml。

槽位寫在模組裡（data/modules/<層>/<id>.yaml）。層有三種：foundation 是 agent 自己怎麼運作，
capability 是 agent 碰得到什麼，domain 是一種業務要交付的成果。新增一種業務就是新增一個模組檔。

除了 JSON Schema，還檢查跨檔規則：檔名等於 id、id 不重複、模組放對資料夾、requires 指向能力模組、
槽位存在、每個槽位最多一個預設、槽位答案指到的工具卡存在而且對得上、replaces 指向存在的工具；
規則有安全底線，profile 有 default、每個 profile 都有 AGENTS.md，情境指向存在的槽位。

讀出的名冊裡，槽位情境是套上 profile 之後的：這台用 profiles.py 選過的 profile 優先，
沒有就用 data/omnikit.yaml 的 profile；那個 profile 沒寫的槽位沿用模組檔裡的範本。

repo 外的 profile（%LOCALAPPDATA%\\omnikit\\profiles，訪談產生的）只檢查這台在用的那一個：其他的跟名冊無關，
pre-commit 與 CI 也不該因為這台的個人檔案失敗。看板用的 profile（omnikit.yaml）一定要在 repo 裡。

私有模組放在 repo 外的 %LOCALAPPDATA%\\omnikit\\modules\\<層>\\<id>.yaml，格式跟公開的模組檔一樣，只在這台生效，
不會被 commit。只有給這台看的腳本（建議、找候選）才讀它（check 的 private=True）；看板與評估紀錄會寫進 repo，
所以預設不讀。有問題的私有模組不載入、列出原因，不算名冊的錯。

用法：uv run engine/scripts/validate.py [--data <資料目錄>]
"""
import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

import dispatch  # 同目錄的 dispatch.py：子任務分派政策的檢查
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


# 模組的三層，也是看板與攤平槽位的順序：先看要交付什麼（領域），再看用到什麼（能力），最後是 agent 自己的運作（基礎）
KINDS = ("domain", "capability", "foundation")


def load_modules(data):
    """讀 data/modules/<層>/<id>.yaml，回傳（問題清單, 模組清單）。模組照層、再照 id 排；每個模組多一個 path。"""
    root = data / "modules"
    if not root.is_dir():
        return [f"{show(root)}: 找不到模組資料夾"], []
    errors, modules = [], []
    check_module = validator("module.schema.json")
    for extra in sorted(p for p in root.iterdir() if p.name not in KINDS):
        errors.append(f"{show(extra)}: 模組只能放在 {'、'.join(KINDS)} 這三個資料夾裡")
    for kind in KINDS:
        for path in sorted((root / kind).glob("*.yaml")):
            doc = load_yaml(path)
            found = schema_errors(check_module, doc, path)
            errors += found
            if found:
                continue
            if doc["id"] != path.stem:
                errors.append(f"{show(path)}: id「{doc['id']}」跟檔名不同")
            if doc["kind"] != kind:
                errors.append(f"{show(path)}: kind 是「{doc['kind']}」，卻放在 {kind} 資料夾")
            if kind != "domain" and ("requires" in doc or "signals" in doc):
                errors.append(f"{show(path)}: requires 與 signals 只有領域模組（domain）能用")
            if kind != "foundation" and "maintainer_only" in doc:
                errors.append(f"{show(path)}: maintainer_only 只有基礎模組（foundation）能用")
            modules.append({**doc, "path": path})
    ids = [m["id"] for m in modules]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"{show(root)}: 模組 id 重複：{dup}")
    kinds = {m["id"]: m["kind"] for m in modules}
    for m in modules:
        for need in m.get("requires", []):
            if kinds.get(need) != "capability":
                errors.append(f"{show(m['path'])}: requires 的「{need}」不是能力模組（capability）")
    return errors, modules


# 私有模組只能是領域或能力；基礎模組是每個人都有的，只放在公開名冊
PRIVATE_KINDS = ("capability", "domain")


def module_problems(doc, known_modules, known_slots, known_scenarios, kind=None, stem=None):
    """一個私有模組檔的問題（空的就是可以載入）。known_* 是已經在名冊裡的：{模組 id: 層}、槽位 id、{情境 id: 槽位}。
    kind 與 stem 是它所在的資料夾與檔名，草稿還沒有檔案時不給。"""
    found = [f"{'/'.join(map(str, e.absolute_path)) or '(整份)'}: {e.message}"
             for error in validator("module.schema.json").iter_errors(doc) for e in explain(error)]
    if found:
        return found
    out = []
    if stem is not None and doc["id"] != stem:
        out.append(f"id「{doc['id']}」跟檔名不同")
    if doc["kind"] not in PRIVATE_KINDS:
        out.append(f"私有模組只能是 {'、'.join(PRIVATE_KINDS)}，不能是 {doc['kind']}")
    elif kind is not None and doc["kind"] != kind:
        out.append(f"kind 是「{doc['kind']}」，卻放在 {kind} 資料夾")
    if doc["kind"] != "domain" and ("requires" in doc or "signals" in doc):
        out.append("requires 與 signals 只有領域模組（domain）能用")
    if "maintainer_only" in doc:
        out.append("maintainer_only 只有公開名冊的基礎模組能用")
    if doc["id"] in known_modules:
        out.append(f"模組 id「{doc['id']}」名冊裡已經有了，換一個 id")
    for need in doc.get("requires", []):
        if known_modules.get(need) != "capability":
            out.append(f"requires 的「{need}」不是能力模組（capability）")
    slot_ids = [s["id"] for s in doc["slots"]]
    for sid in sorted(set(slot_ids)):
        if slot_ids.count(sid) > 1:
            out.append(f"槽位 id 重複：{sid}")
        if sid in known_slots:
            out.append(f"槽位 id「{sid}」名冊裡已經有了，換一個 id")
    owner = {}
    for s in doc["slots"]:
        for sc in s["scenarios"]:
            if sc["id"] in known_scenarios:
                out.append(f"情境 id「{sc['id']}」已經是槽位「{known_scenarios[sc['id']]}」的")
            elif owner.get(sc["id"], s["id"]) != s["id"]:
                out.append(f"情境 id「{sc['id']}」同時用在槽位「{owner[sc['id']]}」與「{s['id']}」")
            owner.setdefault(sc["id"], s["id"])
        for agent, answer in (s.get("answers") or {}).items():
            if answer["verdict"] == "tool":
                out.append(f"槽位「{s['id']}」（{agent}）: 私有模組的答案不能指向工具卡（卡片在公開名冊裡，不會列私有的槽位）；"
                           f"先寫 unknown 或 native")
    return out


def load_private(state, modules, slots, scenarios):
    """讀 state/modules/<層>/<id>.yaml，回傳（載入的模組, 沒載入的 [{file, problems}]）。
    一個一個檢查：有問題的不載入，其他的照常；跟公開名冊撞 id 的一律是私有的讓。先讀能力、再讀領域，領域才 requires 得到私有的能力。"""
    root = state / "modules"
    if not root.is_dir():
        return [], []
    known_modules = {m["id"]: m["kind"] for m in modules}
    known_slots = {s["id"] for s in slots}
    known_scenarios = dict(scenarios)
    loaded, skipped = [], []
    for extra in sorted(p for p in root.iterdir() if p.name not in PRIVATE_KINDS):
        skipped.append({"file": str(extra), "problems": [f"私有模組只能放在 {'、'.join(PRIVATE_KINDS)} 這兩個資料夾裡"]})
    for kind in PRIVATE_KINDS:
        for path in sorted((root / kind).glob("*.yaml")):
            try:
                doc = load_yaml(path)
                problems = module_problems(doc, known_modules, known_slots, known_scenarios, kind, path.stem)
            except (OSError, UnicodeError, yaml.YAMLError) as e:
                problems = [f"讀不懂這個檔：{str(e).splitlines()[0]}"]
            if problems:
                skipped.append({"file": str(path), "problems": problems})
                continue
            known_modules[doc["id"]] = doc["kind"]
            for s in doc["slots"]:
                known_slots.add(s["id"])
                known_scenarios.update({sc["id"]: s["id"] for sc in s["scenarios"]})
            loaded.append({**doc, "path": path, "private": True})
    # 跟公開的一樣照 KINDS 的順序排：領域在前
    loaded.sort(key=lambda m: (KINDS.index(m["kind"]), m["id"]))
    return loaded, skipped


def private_modules(data, state):
    """只要知道這台有哪些私有模組時用（掃描）：對照公開的模組檔，不看工具卡與 profile。回傳同 load_private。"""
    modules = load_modules(data)[1]
    slots = flatten(modules)
    scenarios = {sc["id"]: s["id"] for s in slots for sc in s.get("scenarios") or [] if isinstance(sc, dict) and "id" in sc}
    return load_private(state, modules, slots, scenarios)


def flatten(modules):
    """把模組攤平成槽位清單；每個槽位記下它屬於哪個模組、哪一層。"""
    return [{**s, "module": m["id"], "kind": m["kind"], **({"private": True} if m.get("private") else {})}
            for m in modules for s in m["slots"] if isinstance(s, dict)]


def template_slots(data):
    """模組檔裡原本的槽位（還沒套 profile 的情境），給產生 profile 的腳本用。"""
    return flatten(load_modules(data)[1])


def profile_domains(folder, modules=None):
    """profile 啟用的領域（domains.yaml）：回傳（問題清單, 模組 id 清單）；沒有這個檔回 None，表示全部模組都看。
    給了 modules 就一併檢查 id 存在，而且是領域或能力模組。"""
    path = folder / "domains.yaml" if folder else None
    if path is None or not path.exists():
        return [], None
    doc = load_yaml(path)
    errors = schema_errors(validator("domains.schema.json"), doc, path)
    if errors:
        return errors, None
    kinds = {m["id"]: m["kind"] for m in modules} if modules is not None else None
    for mid in doc["domains"] if kinds is not None else []:
        if mid not in kinds:
            errors.append(f"{show(path)}: 找不到模組「{mid}」")
        elif kinds[mid] == "foundation":
            errors.append(f"{show(path)}: 「{mid}」是基礎模組，每個人都有，不用列")
    return errors, doc["domains"]


def enabled_modules(modules, selected):
    """這個 profile 看哪些模組：基礎模組、選的領域與能力、領域帶入的能力。selected 是 None 就是全部。"""
    if selected is None:
        return [m["id"] for m in modules]
    pulled = {need for m in modules if m["id"] in selected for need in m.get("requires", [])}
    return [m["id"] for m in modules if m["kind"] == "foundation" or m["id"] in selected or m["id"] in pulled]


def check_dispatch(data, d=None):
    """子任務分派：共用層 data/rules/dispatch.md，加上 profile 的 dispatch.md（有才檢查）。沒有共用層不算錯。"""
    try:
        pol = dispatch.policy(data)
        if pol is None:
            return []
        mine = dispatch.personal(d) if d is not None else None
    except (ValueError, yaml.YAMLError) as e:
        return [f"分派政策讀不懂：{e}"]
    where = show(d / "dispatch.md") if mine is not None else show(data / "rules" / "dispatch.md")
    return [f"{where}: {e}" for e in dispatch.check(pol, mine if d is not None else None)
            if d is None or e.startswith("個人層")]


def check_profile(d, slot_ids, check_scenarios, modules=None):
    """一個 profile 資料夾：回傳（問題清單, {槽位: 情境}）；沒有 AGENTS.md 就不是 profile，情境是 None。"""
    if not (d / "AGENTS.md").is_file():
        return [f"{show(d)}: 少了 AGENTS.md（個人規則）"], None
    domain_errors, _ = profile_domains(d, modules)
    path = d / "scenarios.yaml"
    if not path.exists():
        return domain_errors, {}
    doc = load_yaml(path)
    errors = domain_errors + schema_errors(check_scenarios, doc, path)
    if errors:
        return errors, {}
    for slot, items in doc["scenarios"].items():
        if slot not in slot_ids:
            errors.append(f"{show(path)}: 找不到槽位「{slot}」")
        ids = [s["id"] for s in items]
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            errors.append(f"{show(path)}: 槽位「{slot}」的情境 id 重複：{dup}")
    return errors, doc["scenarios"]


def check_profiles(data, slot_ids, state=None, wanted=None, modules=None):
    """回傳（問題清單, {profile 名稱: {槽位: 情境}}, repo 裡的 profile 名稱）。
    repo 裡的全部檢查；repo 外的只檢查這台在用的（wanted，沒給就是選過的），同名時它優先。"""
    errors, found = [], {}
    baseline = data / "rules" / "baseline.md"
    if not baseline.is_file():
        errors.append(f"{show(baseline)}: 找不到安全底線")
    errors += check_dispatch(data)
    root = data / "profiles"
    dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if profiles.DEFAULT not in [p.name for p in dirs]:
        errors.append(f"{show(root)}: 少了 {profiles.DEFAULT} profile（這台沒選 profile 時用它）")
    check_scenarios = validator("scenarios.schema.json")
    for d in dirs:
        if not profiles.NAME.match(d.name):
            errors.append(f"{show(d)}: profile 名稱只能用小寫英數與 -")
            continue
        bad, scenarios = check_profile(d, slot_ids, check_scenarios, modules)
        errors += bad + (check_dispatch(data, d) if (d / "dispatch.md").is_file() else [])
        if scenarios is not None:
            found[d.name] = scenarios
    in_repo = set(found)
    name = wanted or (profiles.chosen(state) if state is not None else None)
    local = state / "profiles" / name if state is not None and name and profiles.NAME.match(name) else None
    if local and (local / "AGENTS.md").is_file():
        bad, scenarios = check_profile(local, slot_ids, check_scenarios, modules)
        errors += bad + (check_dispatch(data, local) if (local / "dispatch.md").is_file() else [])
        found[name] = scenarios
    return errors, found, in_repo


def check(data, profile=None, state=None, private=False):
    """回傳（問題清單, 名冊）；名冊含 config、套上 profile 情境的 slots、依 id 排序的 tools、profile 名稱
    與它的資料夾（profile_dir）。state 是 %LOCALAPPDATA%\\omnikit（自我測試換成暫存資料夾）。
    private=True 才把這台的私有模組（state/modules）接在公開名冊後面，名冊多一個 private：{dir, loaded, skipped}。
    私有模組一律啟用（放進去就是要用，刪掉檔案就停用）；它的問題不算名冊的錯，只列在 skipped。
    會把結果寫進 repo 或公開看板的腳本不要開 private。"""
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

    module_errors, modules = load_modules(data)
    errors += module_errors
    modules_path = data / "modules"
    slots = flatten(modules)
    slot_ids = [s.get("id") for s in slots]
    # 槽位 id 跨模組也不能重複：工具卡、情境檔與評估紀錄都只記槽位 id
    for dup in sorted({i for i in slot_ids if slot_ids.count(i) > 1}):
        where = "、".join(s["module"] for s in slots if s.get("id") == dup)
        errors.append(f"{show(modules_path)}: 槽位 id 重複：{dup}（在模組 {where}）")
    # 情境 id 跨槽位也不能重複：評估紀錄與第 1 層結果只記情境 id，重複就分不出是哪個槽位
    owner = {}
    for s in slots:
        for sc in s.get("scenarios") or []:
            sid = sc.get("id") if isinstance(sc, dict) else None
            if sid in owner and owner[sid] != s.get("id"):
                errors.append(f"{show(modules_path)}: 情境 id「{sid}」同時用在槽位「{owner[sid]}」與「{s.get('id')}」")
            owner.setdefault(sid, s.get("id"))

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
    # 槽位在每個 agent 上的答案：建議裝的那張卡要存在、放在這個槽位，而且支援那個 agent
    for s in slots:
        for agent, answer in (s.get("answers") or {}).items():
            if answer.get("verdict") != "tool":
                continue
            where = f"模組「{s['module']}」的槽位「{s['id']}」（{agent}）"
            card = tools.get(answer["tool"])
            if card is None:
                errors.append(f"{where}: 答案指向不存在的工具「{answer['tool']}」")
            elif s["id"] not in card["slots"]:
                errors.append(f"{where}: 工具「{answer['tool']}」的卡片沒有列這個槽位")
            elif card.get("works_with") and agent not in card["works_with"]:
                errors.append(f"{where}: 工具「{answer['tool']}」的卡片沒有寫支援 {agent}")

    found_errors, found, in_repo = check_profiles(data, slot_ids, state, profile, modules)
    errors += found_errors
    for pname, scen in found.items():
        for slot, items in scen.items():
            for sc in items or []:
                sid = sc.get("id") if isinstance(sc, dict) else None
                if owner.get(sid) not in (None, slot):
                    errors.append(f"data/profiles/{pname}/scenarios.yaml: 槽位「{slot}」的情境 id「{sid}」已經是槽位「{owner[sid]}」的")
    board = (config or {}).get("profile") if isinstance(config, dict) else None
    if board and board not in in_repo:
        errors.append(f"{show(config_path)}: 找不到 profile「{board}」（data/profiles/{board}/AGENTS.md）")
    chosen = profiles.chosen(state)
    name = profile or (chosen if chosen in found else None) or board
    overlay = found.get(name) or {}
    slots = [{**s, "scenarios": overlay.get(s.get("id"), s.get("scenarios"))} for s in slots]
    where = profiles.folder(data, state, name) if name else None

    # 這個 profile 啟用的領域（問題已經在 check_profiles 報過）：domains 是 None 表示沒選過，全部模組都看
    _, selected = profile_domains(where, modules)
    enabled = enabled_modules(modules, selected)
    extra = {}
    if private:
        # 情境 id 也不能撞到這個 profile 自己寫的情境
        taken = {**owner, **{sc["id"]: slot for slot, items in overlay.items() for sc in items or [] if isinstance(sc, dict)}}
        loaded, skipped = load_private(state, modules, slots, taken)
        slots = slots + flatten(loaded)
        # 私有模組一律啟用，連同它 requires 的能力模組
        enabled = list(dict.fromkeys(enabled + [i for m in loaded for i in (m["id"], *m.get("requires", []))]))
        modules = modules + loaded
        extra = {"private": {"dir": str(state / "modules"), "loaded": [m["id"] for m in loaded], "skipped": skipped}}
    summary = [{**{k: v for k, v in m.items() if k not in ("slots", "path")},
                "slots": [s["id"] for s in m["slots"] if isinstance(s, dict)]} for m in modules]
    return errors, {"config": config, "modules": summary, "slots": slots, "tools": tools, "profile": name,
                    "profile_dir": str(where) if where else None,
                    "domains": selected, "enabled": enabled, **extra}


def main():
    parser = argparse.ArgumentParser(description="驗證 OmniKit 名冊")
    parser.add_argument("--data", type=Path, default=ROOT / "data", help="資料目錄，預設是 repo 的 data/")
    data = parser.parse_args().data.resolve()
    errors, roster = check(data, private=True)
    if errors:
        print(f"名冊驗證失敗，共 {len(errors)} 個問題：")
        for e in errors:
            print(f"- {e}")
        return 1
    tool_count = len(list((data / "tools").glob("*.yaml")))
    mine = roster["private"]
    public = [m for m in roster["modules"] if not m.get("private")]
    print(f"名冊驗證通過：{len(public)} 個模組、{len([s for s in roster['slots'] if not s.get('private')])} 個槽位、"
          f"{tool_count} 張工具卡，情境用 profile：{roster['profile'] or '（範本）'}。")
    # 私有模組只在這台生效：有問題只提醒，不算驗證失敗（pre-commit 不該因為個人檔案擋下來）
    if mine["loaded"]:
        print(f"這台另外有 {len(mine['loaded'])} 個私有模組：{'、'.join(mine['loaded'])}（{mine['dir']}）。")
    for item in mine["skipped"]:
        print(f"私有模組沒載入：{item['file']}")
        for p in item["problems"]:
            print(f"- {p}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
