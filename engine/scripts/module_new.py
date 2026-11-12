# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""把 agent 草擬的模組寫成這台的私有模組：%LOCALAPPDATA%\\omnikit\\modules\\<層>\\<id>.yaml。

名冊的領域不符合使用者的工作時用：使用者用幾句話描述工作，agent 草擬槽位、情境與找候選用的關鍵字，
存成 JSON；這支腳本補上預設值、驗證、預覽，使用者同意後才寫入。跟產生 profile 一樣：agent 出內容，腳本寫入。

私有模組在 repo 外，不會被 commit 或 push；只有給這台看的腳本（建議、找候選）會讀，看板與評估紀錄不會。
放進去就啟用，刪掉檔案就停用。格式跟公開的模組檔一樣（engine/schema/module.schema.json），差別：
- 只能是領域（domain）或能力（capability）。
- id、槽位 id、情境 id 不能跟名冊已經有的重複。
- 答案不能指向工具卡。

草稿可以省略的：kind（預設 domain）、槽位的 focus（預設 active）、情境的 id（可以只寫一句文字，腳本編號）。
草稿另外要求（手寫的檔不受限）：最多 6 個槽位；每個槽位都要有 search；
search 不能有這個 profile 的專案名稱，因為找候選時會把關鍵字送到外面。

用法：
  uv run engine/scripts/module_new.py --draft <草稿.json>            預覽，不寫檔
  uv run engine/scripts/module_new.py --draft <草稿.json> --write    寫檔
  加 --force：同名的私有模組已經存在時覆蓋，舊檔先備份成 .bak
  uv run engine/scripts/module_new.py --list                         這台的私有模組，與沒載入的原因
  uv run engine/scripts/module_new.py --selftest
"""
import argparse
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profiles  # noqa: E402
import validate  # noqa: E402
from fsretry import retry  # noqa: E402

DATA = profiles.DATA
STATE = profiles.STATE
MAX_SLOTS = 6
SCENARIO_ID = re.compile(r"^[A-Z]{1,3}[0-9]+$")
HEADER = ("# 私有模組：只在這台生效，在 repo 外，不會被 commit。{date} 由 module_new.py 寫入。\n"
          "# 可以直接改（格式見 repo 的 engine/schema/module.schema.json）；刪掉這個檔就停用。\n")


def read_draft(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        return json.loads(text)
    except ValueError:
        return yaml.load(text, Loader=validate.Loader)


def prefix(module_id):
    """情境 id 的字首：模組 id 每一段的第一個英文字母，最多 3 個；一個都沒有就用 PM。"""
    letters = "".join(part[0] for part in str(module_id).split("-") if part[:1].isalpha())
    return letters[:3].upper() or "PM"


def normalize(draft, taken):
    """補上預設值，替只寫文字的情境編號。taken 是名冊已經用掉的情境 id。回傳新的 dict，不改草稿。"""
    doc = {k: v for k, v in draft.items() if k != "slots"}
    doc.setdefault("kind", "domain")
    slots = draft.get("slots")
    if not isinstance(slots, list):
        return {**doc, "slots": slots}
    used = set(taken)
    for s in slots:
        for sc in (s.get("scenarios") or []) if isinstance(s, dict) and isinstance(s.get("scenarios"), list) else []:
            if isinstance(sc, dict) and isinstance(sc.get("id"), str):
                used.add(sc["id"])
    head, n, out = prefix(doc.get("id")), 0, []
    for s in slots:
        if not isinstance(s, dict):
            out.append(s)
            continue
        s = dict(s)
        s.setdefault("focus", "active")
        if isinstance(s.get("scenarios"), list):
            scenarios = []
            for sc in s["scenarios"]:
                if isinstance(sc, str):
                    sc = {"text": sc}
                if isinstance(sc, dict) and "id" not in sc:
                    n += 1
                    while f"{head}{n}" in used:
                        n += 1
                    used.add(f"{head}{n}")
                    sc = {"id": f"{head}{n}", **sc}
                scenarios.append(sc)
            s["scenarios"] = scenarios
        # 欄位照公開模組檔的順序排，寫出來的檔才好讀
        out.append({k: s[k] for k in ("id", "name", "focus", "scenarios", "search", "answers") if k in s}
                   | {k: v for k, v in s.items() if k not in ("id", "name", "focus", "scenarios", "search", "answers")})
    order = ("id", "kind", "name", "summary", "requires", "signals", "maps_to")
    return {**{k: doc[k] for k in order if k in doc}, **{k: v for k, v in doc.items() if k not in order}, "slots": out}


def banned_words(data, state):
    """這個 profile 訪談時寫的專案名稱：不能出現在找候選用的關鍵字裡。"""
    name = profiles.chosen(state)
    answers = profiles.answers(data, state, name) if name else None
    projects = (answers or {}).get("projects") or {}
    return sorted({str(v).strip() for v in projects.values() if isinstance(v, str) and len(v.strip()) >= 2})


def draft_problems(doc, banned):
    """只對草稿多要求的（格式本身交給 validate.module_problems）。"""
    out = []
    slots = [s for s in doc.get("slots") or [] if isinstance(s, dict)] if isinstance(doc.get("slots"), list) else []
    if len(slots) > MAX_SLOTS:
        out.append(f"槽位有 {len(slots)} 個，最多 {MAX_SLOTS} 個；工作太多就拆成兩個模組")
    for s in slots:
        words = s.get("search") if isinstance(s.get("search"), list) else []
        if not words:
            out.append(f"槽位「{s.get('id')}」沒有 search：沒有關鍵字就找不到候選")
        for w in words:
            for b in banned:
                if isinstance(w, str) and b.lower() in w.lower():
                    out.append(f"槽位「{s.get('id')}」的關鍵字「{w}」有專案名稱「{b}」：找候選時會把關鍵字送到外面，改成通用的說法")
    return out


def known(roster, module_id):
    """名冊已經用掉的 id；要覆蓋的那個私有模組自己的不算。"""
    def mine(m_id, private):
        return private and m_id == module_id
    modules = {m["id"]: m["kind"] for m in roster["modules"] if not mine(m["id"], m.get("private"))}
    slots = [s for s in roster["slots"] if not mine(s["module"], s.get("private"))]
    scenarios = {sc["id"]: s["id"] for s in slots for sc in s.get("scenarios") or [] if isinstance(sc, dict) and "id" in sc}
    return modules, {s["id"] for s in slots}, scenarios


def render(doc, today):
    return HEADER.format(date=today) + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=10000)


def write_module(path, text):
    """寫入；同名舊檔先改名成 .bak（已經有 .bak 就加時間）。回傳備份檔或 None。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        if backup.exists():
            backup = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d%H%M%S}")
        retry(path.replace, backup)
    retry(path.write_bytes, text.encode("utf-8"))
    return backup


def load_roster(data, state):
    errors, roster = validate.check(data, state=state, private=True)
    if errors:
        print("名冊驗證沒過，先修好：")
        print("\n".join(f"- {e}" for e in errors))
        return None
    return roster


def run(draft_path, data, state=None, write=False, force=False, today=None):
    state = STATE if state is None else state
    try:
        draft = read_draft(draft_path)
    except (OSError, UnicodeError, yaml.YAMLError) as e:
        print(f"讀不到草稿 {draft_path}：{str(e).splitlines()[0]}")
        return 1
    if not isinstance(draft, dict):
        print("草稿有問題，請重新確認：\n- 草稿的最外層要是 JSON 物件")
        return 1
    roster = load_roster(data, state)
    if roster is None:
        return 1
    modules, slot_ids, scenarios = known(roster, draft.get("id"))
    doc = normalize(draft, scenarios)
    problems = validate.module_problems(doc, modules, slot_ids, scenarios)
    problems += draft_problems(doc, banned_words(data, state)) if not problems else []
    if problems:
        print("草稿有問題，請重新確認：")
        print("\n".join(f"- {p}" for p in problems))
        return 1
    path = state / "modules" / doc["kind"] / f"{doc['id']}.yaml"
    other = [state / "modules" / k / f"{doc['id']}.yaml" for k in validate.PRIVATE_KINDS if k != doc["kind"]]
    problem = None
    if any(p.exists() for p in other):
        problem = f"已經有同名的私有模組在另一層：{next(p for p in other if p.exists())}；換一個 id，或先處理那個檔。"
    elif path.exists() and not force:
        problem = f"{path} 已經存在；要用新草稿覆蓋就加 --force，舊檔會先備份成 .bak。"
    text = render(doc, today or date.today().isoformat())

    if not write:
        names = {m["id"]: m["name"] for m in roster["modules"]}
        print(f"預覽：會寫入 {path}（repo 外，不會被 commit）")
        print(f"\n----- {path.name} -----\n{text.rstrip()}")
        print(f"\n{doc['name']}：{len(doc['slots'])} 個槽位（{'、'.join(s['name'] for s in doc['slots'])}）。")
        if doc.get("requires"):
            print(f"會一起帶入的能力：{'、'.join(names.get(r, r) for r in doc['requires'])}。")
        print("寫入後一律啟用；找候選時會把 search 的關鍵字送到 GitHub 與官方 MCP Registry，所以關鍵字不要寫單位或專案的名稱。")
        if problem:
            print(f"\n不能寫入：{problem}")
            return 1
        print("\n這是預覽，還沒寫檔。確認後加 --write。")
        return 0

    if problem:
        print(f"不能寫入：{problem}")
        return 1
    backup = write_module(path, text)
    print(f"已寫入 {path}")
    if backup:
        print(f"舊檔備份成：{backup.name}")
    after = load_roster(data, state)
    if after is None:
        return 1
    if doc["id"] not in after["private"]["loaded"]:
        print("寫入了，但是沒有載入：")
        for item in after["private"]["skipped"]:
            if Path(item["file"]) == path:
                print("\n".join(f"- {p}" for p in item["problems"]))
        return 1
    print(f"已經啟用：{doc['name']}（{len(doc['slots'])} 個槽位）。接著跑「OmniKit 給我建議」（omnikit-weekly）就會替這些槽位找候選。")
    return 0


def listing(data, state=None):
    state = STATE if state is None else state
    roster = load_roster(data, state)
    if roster is None:
        return 1
    mine = roster["private"]
    slots = {}
    for s in roster["slots"]:
        slots.setdefault(s["module"], []).append(s["name"])
    loaded = [m for m in roster["modules"] if m.get("private")]
    print(f"私有模組的位置：{mine['dir']}")
    if not loaded and not mine["skipped"]:
        print("這台還沒有私有模組。")
    for m in loaded:
        print(f"- {m['id']}（{m['kind']}）{m['name']}：{'、'.join(slots.get(m['id'], []))}")
    for item in mine["skipped"]:
        print(f"沒載入：{item['file']}")
        print("\n".join(f"  - {p}" for p in item["problems"]))
    return 0


def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def call(fn, *args, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(*args, **kwargs)
        return code, buf.getvalue()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data, state = tmp / "data", tmp / "state"
        for rel in ("omnikit.yaml", "rules/baseline.md", "profiles/default/AGENTS.md", "profiles/ryan/AGENTS.md"):
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(DATA / rel, data / rel)
        (data / "tools").mkdir()
        write(data / "modules" / "domain" / "dev.yaml", "id: dev\nkind: domain\nname: 軟體開發\nsummary: 寫程式\nrequires: [docs]\n"
              "slots:\n  - id: dev-review\n    name: 審查\n    focus: watch\n    scenarios:\n      - {id: GA1, text: 情境}\n")
        write(data / "modules" / "capability" / "docs.yaml", "id: docs\nkind: capability\nname: 文件\nsummary: 讀寫文件\n"
              "slots:\n  - id: docs-read\n    name: 讀文件\n    focus: watch\n    scenarios:\n      - {id: D1, text: 情境}\n")
        write(data / "modules" / "foundation" / "ops.yaml", "id: ops\nkind: foundation\nname: 基礎\nsummary: 每個人都有\n"
              "slots:\n  - id: ops-memory\n    name: 記憶\n    focus: watch\n    scenarios:\n      - {id: C1, text: 情境}\n")
        errors, public = validate.check(data, state=state)
        check("測試用的名冊驗證通過", not errors and "private" not in public)

        draft = {"id": "grant-admin", "name": "補助案行政", "summary": "補助案的核銷與報告",
                 "requires": ["docs"], "signals": {"keywords": ["核銷"]},
                 "slots": [{"id": "grant-expense", "name": "整理核銷單據", "scenarios": ["把一批單據整理成核銷清冊。", {"text": "核對金額。"}],
                            "search": ["expense report automation"]},
                           {"id": "grant-report", "name": "寫期中報告", "scenarios": [{"id": "ZZ9", "text": "照範本寫報告。"}],
                            "search": ["progress report template"], "focus": "watch"}]}
        path = tmp / "draft.json"
        write(path, json.dumps(draft, ensure_ascii=False))
        target = state / "modules" / "domain" / "grant-admin.yaml"

        code, out = call(run, path, data, state, today="2026-11-12")
        check("預覽：不寫檔，講明寫到哪裡、還沒寫", code == 0 and not target.exists() and str(target) in out and "還沒寫檔" in out)
        check("預覽：情境自動編號，避開名冊已經用掉的 GA1", "id: GA2" in out and "id: GA3" in out and "id: GA1" not in out and "id: ZZ9" in out)
        check("預覽：補上 kind 與 focus 的預設值，草稿寫了的照草稿", "kind: domain" in out and out.count("focus: active") == 1
              and out.count("focus: watch") == 1)
        check("預覽：講明帶入的能力與關鍵字會送到外面", "會一起帶入的能力：文件" in out and "送到 GitHub 與官方 MCP Registry" in out)

        code, out = call(run, path, data, state, write=True, today="2026-11-12")
        check("寫入：檔案在 repo 外，寫完確認有載入", code == 0 and target.exists() and "已經啟用：補助案行政（2 個槽位）" in out)
        check("寫入的檔通過模組的格式，開頭有說明", target.read_text(encoding="utf-8").startswith("# 私有模組")
              and not validate.schema_errors(validate.validator("module.schema.json"), validate.load_yaml(target), target))
        errors, roster = validate.check(data, state=state, private=True)
        private_slots = [s for s in roster["slots"] if s.get("private")]
        check("名冊（private=True）：私有模組接在後面，槽位標 private", not errors and roster["private"]["loaded"] == ["grant-admin"]
              and [s["id"] for s in private_slots] == ["grant-expense", "grant-report"]
              and [m["id"] for m in roster["modules"] if m.get("private")] == ["grant-admin"])
        check("名冊（預設）：看板與評估用的名冊看不到私有模組", validate.check(data, state=state)[1] == public)

        write(data / "profiles" / "ryan" / "domains.yaml", "domains: [dev]\n")
        _, picked = validate.check(data, profile="ryan", state=state, private=True)
        check("私有模組一律啟用，不用列在 profile 的領域裡", "grant-admin" in picked["enabled"] and picked["domains"] == ["dev"])
        (data / "profiles" / "ryan" / "domains.yaml").unlink()

        code, out = call(run, path, data, state, write=True)
        check("已經存在：不加 --force 不覆蓋", code == 1 and "加 --force" in out and not list(target.parent.glob("*.bak")))
        code, out = call(run, path, data, state, write=True, force=True)
        check("--force：舊檔備份成 .bak 再寫，自己的 id 不算重複", code == 0 and (target.parent / "grant-admin.yaml.bak").exists()
              and "舊檔備份成：grant-admin.yaml.bak" in out)

        def refused(change, needle, **kwargs):
            bad = json.loads(json.dumps(draft))
            bad["id"] = "other"
            change(bad)
            write(tmp / "bad.json", json.dumps(bad, ensure_ascii=False))
            code, out = call(run, tmp / "bad.json", data, state, write=True, **kwargs)
            ok = code == 1 and needle in out and not (state / "modules" / "domain" / "other.yaml").exists()
            return ok or print(out)

        def rename_slots(d):
            d["slots"][0]["id"], d["slots"][1]["id"] = "o-one", "o-two"

        def fresh(d):
            rename_slots(d)
            d["slots"][1]["scenarios"][0]["id"] = "ZZ8"

        check("模組 id 跟公開名冊重複：不寫", refused(lambda d: (fresh(d), d.update(id="dev")), "模組 id「dev」名冊裡已經有了"))
        check("槽位 id 跟公開名冊重複：不寫", refused(lambda d: (fresh(d), d["slots"][0].update(id="dev-review")), "槽位 id「dev-review」名冊裡已經有了"))
        check("槽位 id 跟別的私有模組重複：不寫", refused(lambda d: d["slots"][1]["scenarios"][0].update(id="ZZ8"), "槽位 id「grant-expense」名冊裡已經有了"))
        check("情境 id 跟名冊重複：不寫", refused(lambda d: (fresh(d), d["slots"][1]["scenarios"][0].update(id="D1")), "情境 id「D1」已經是槽位「docs-read」的"))
        check("情境 id 跟別的私有模組重複：不寫", refused(rename_slots, "情境 id「ZZ9」已經是槽位「grant-report」的"))
        check("基礎模組不能是私有的", refused(lambda d: (fresh(d), d.update(kind="foundation"), d.pop("requires"), d.pop("signals")),
                                    "私有模組只能是 capability、domain"))
        check("requires 要是能力模組", refused(lambda d: (fresh(d), d.update(requires=["dev"])), "requires 的「dev」不是能力模組"))
        check("能力模組不能有 requires", refused(lambda d: (fresh(d), d.update(kind="capability")), "只有領域模組（domain）能用"))
        check("答案不能指向工具卡", refused(lambda d: (fresh(d), d["slots"][0].update(answers={"claude": {
            "verdict": "tool", "tool": "x", "reason": "r", "decided_at": "2026-11-12"}})), "不能指向工具卡"))
        check("格式不對（少了 summary）：不寫", refused(lambda d: (fresh(d), d.pop("summary")), "'summary' is a required property"))
        check("超過 6 個槽位：不寫", refused(lambda d: d.update(slots=[
            {"id": f"o-{i}", "name": "n", "scenarios": ["情境"], "search": ["k"]} for i in range(7)]), "最多 6 個"))
        check("槽位沒有 search：不寫", refused(lambda d: (fresh(d), d["slots"][0].pop("search")), "沒有 search"))
        check("草稿不是物件：不寫", call(run, (write(tmp / "list.json", "[]"), tmp / "list.json")[1], data, state, write=True)[0] == 1)
        check("讀不到草稿：講明", "讀不到草稿" in call(run, tmp / "missing.json", data, state)[1])

        # 找候選時關鍵字會送到外面：不能有訪談時寫的專案名稱
        write(state / "profiles" / "amy" / "AGENTS.md", "規則\n")
        write(state / "profiles" / "amy" / "answers.json", json.dumps({"name": "amy", "projects": {"main": "Falcon 產線"}}, ensure_ascii=False))
        write(state / "profile.json", json.dumps({"profile": "amy"}))
        check("關鍵字有專案名稱：不寫", refused(lambda d: (fresh(d), d["slots"][0].update(search=["falcon 產線 dashboard"])), "有專案名稱「Falcon 產線」"))
        (state / "profile.json").unlink()

        # 同名的私有模組在另一層
        write(tmp / "cap.json", json.dumps({"id": "grant-admin", "kind": "capability", "name": "n", "summary": "s", "slots": [
            {"id": "cap-one", "name": "n", "scenarios": ["情境"], "search": ["k"]}]}, ensure_ascii=False))
        code, out = call(run, tmp / "cap.json", data, state, write=True, force=True)
        check("同名的私有模組在另一層：不寫", code == 1 and "另一層" in out and not (state / "modules" / "capability" / "grant-admin.yaml").exists())

        # 私有的能力模組，私有的領域 requires 得到
        write(tmp / "cap.json", json.dumps({"id": "lab-gear", "kind": "capability", "name": "實驗設備", "summary": "s", "slots": [
            {"id": "gear-read", "name": "讀設備資料", "scenarios": ["情境"], "search": ["instrument data"]}]}, ensure_ascii=False))
        code, _ = call(run, tmp / "cap.json", data, state, write=True)
        write(tmp / "dom.json", json.dumps({"id": "lab-work", "name": "實驗", "summary": "s", "requires": ["lab-gear", "docs"], "slots": [
            {"id": "lab-run", "name": "跑實驗", "scenarios": ["情境"], "search": ["lab automation"]}]}, ensure_ascii=False))
        code2, _ = call(run, tmp / "dom.json", data, state, write=True)
        _, roster = validate.check(data, state=state, private=True)
        check("私有的領域可以 requires 私有的能力；排序領域在前", code == 0 and code2 == 0
              and roster["private"]["loaded"] == ["grant-admin", "lab-work", "lab-gear"])

        # 手寫壞的私有模組：不載入、列出原因，其他的照常，名冊不算錯
        write(state / "modules" / "domain" / "broken.yaml", "id: wrong-name\nkind: domain\nname: n\nsummary: s\n"
              "slots:\n  - id: dev-review\n    name: n\n    focus: watch\n    scenarios:\n      - {id: Q1, text: t}\n")
        write(state / "modules" / "domain" / "garbage.yaml", "id: [\n")
        write(state / "modules" / "foundation" / "mine.yaml", "id: mine\n")
        errors, roster = validate.check(data, state=state, private=True)
        skipped = {Path(i["file"]).name: " ".join(i["problems"]) for i in roster["private"]["skipped"]}
        check("壞的私有模組不載入、列原因，名冊不算錯，好的照常", not errors and "grant-admin" in roster["private"]["loaded"]
              and "跟檔名不同" in skipped.get("broken.yaml", "") and "槽位 id「dev-review」名冊裡已經有了" in skipped["broken.yaml"]
              and "讀不懂這個檔" in skipped.get("garbage.yaml", "") and "這兩個資料夾" in skipped.get("foundation", "")
              and not any(s["module"] in ("wrong-name", "mine") for s in roster["slots"]))
        # 手寫的檔之間也互相檢查：先讀到的算數，後面撞到的不載入
        write(state / "modules" / "capability" / "misplaced.yaml", "id: misplaced\nkind: domain\nname: n\nsummary: s\n"
              "slots:\n  - id: mis-one\n    name: n\n    focus: watch\n    scenarios:\n      - {id: MS1, text: t}\n")
        write(state / "modules" / "domain" / "zz-slot.yaml", "id: zz-slot\nkind: domain\nname: n\nsummary: s\n"
              "slots:\n  - id: grant-expense\n    name: n\n    focus: watch\n    scenarios:\n      - {id: ZS1, text: t}\n")
        write(state / "modules" / "domain" / "zz-scenario.yaml", "id: zz-scenario\nkind: domain\nname: n\nsummary: s\n"
              "slots:\n  - id: zz-own\n    name: n\n    focus: watch\n    scenarios:\n      - {id: ZZ9, text: t}\n")
        write(state / "modules" / "domain" / "zz-overlay.yaml", "id: zz-overlay\nkind: domain\nname: n\nsummary: s\n"
              "slots:\n  - id: zz-over\n    name: n\n    focus: watch\n    scenarios:\n      - {id: OV1, text: t}\n")
        write(data / "profiles" / "ryan" / "scenarios.yaml", "scenarios:\n  dev-review:\n    - {id: OV1, text: 我自己的情境}\n")
        errors, roster = validate.check(data, profile="ryan", state=state, private=True)
        skipped = {Path(i["file"]).name: " ".join(i["problems"]) for i in roster["private"]["skipped"]}
        check("放錯資料夾的不載入", not errors and "卻放在 capability 資料夾" in skipped.get("misplaced.yaml", ""))
        check("手寫的私有模組之間槽位 id 重複：後面的不載入", "槽位 id「grant-expense」名冊裡已經有了" in skipped.get("zz-slot.yaml", ""))
        check("手寫的私有模組之間情境 id 重複：後面的不載入", "情境 id「ZZ9」已經是槽位「grant-report」的" in skipped.get("zz-scenario.yaml", ""))
        check("情境 id 跟這個 profile 自己寫的情境重複：不載入", "情境 id「OV1」已經是槽位「dev-review」的" in skipped.get("zz-overlay.yaml", ""))
        (data / "profiles" / "ryan" / "scenarios.yaml").unlink()
        for name in ("capability/misplaced.yaml", "domain/zz-slot.yaml", "domain/zz-scenario.yaml", "domain/zz-overlay.yaml"):
            (state / "modules" / name).unlink()

        # 寫進去的檔沒有載入（例如寫到一半被別的程式改掉）：照實說，不說已經啟用
        real = globals()["write_module"]
        globals()["write_module"] = lambda p, _text: (p.parent.mkdir(parents=True, exist_ok=True), p.write_text("id: [\n", encoding="utf-8"))[0]
        try:
            write(tmp / "late.json", json.dumps({"id": "late", "name": "n", "summary": "s", "slots": [
                {"id": "late-one", "name": "n", "scenarios": ["情境"], "search": ["k"]}]}, ensure_ascii=False))
            code, out = call(run, tmp / "late.json", data, state, write=True)
        finally:
            globals()["write_module"] = real
        check("寫完沒有載入：講明，不說已經啟用", code == 1 and "寫入了，但是沒有載入" in out and "讀不懂這個檔" in out and "已經啟用" not in out)
        (state / "modules" / "domain" / "late.yaml").unlink()

        code, out = call(listing, data, state)
        check("--list：列出載入的與沒載入的原因", code == 0 and "grant-admin（domain）補助案行政：整理核銷單據、寫期中報告" in out
              and "沒載入" in out and "broken.yaml" in out)
        # 公開名冊後來加了同一個 id：私有的讓
        write(data / "modules" / "domain" / "lab-work.yaml", "id: lab-work\nkind: domain\nname: 公開的\nsummary: s\n"
              "slots:\n  - id: pub-run\n    name: n\n    focus: watch\n    scenarios:\n      - {id: P1, text: t}\n")
        errors, roster = validate.check(data, state=state, private=True)
        check("公開名冊後來有了同一個 id：私有的不載入，公開的照常", not errors and "lab-work" not in roster["private"]["loaded"]
              and [m["name"] for m in roster["modules"] if m["id"] == "lab-work"] == ["公開的"])

        empty = tmp / "empty"
        code, out = call(listing, data, empty)
        check("沒有私有模組：照實說，也不建資料夾", code == 0 and "還沒有私有模組" in out and not empty.exists())
        numbered = normalize({"id": "a-b", "slots": [{"id": "x", "scenarios": ["t"]}, {"id": "y", "scenarios": [{"id": "AB1", "text": "t"}]}]}, set())
        check("情境編號也避開草稿自己寫的 id", [sc["id"] for s in numbered["slots"] for sc in s["scenarios"]] == ["AB2", "AB1"])
        check("情境字首：取每段第一個字母，最多 3 個；沒有字母用 PM", prefix("grant-admin") == "GA" and prefix("a-b-c-d") == "ABC"
              and prefix("2026") == "PM")

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="把 agent 草擬的模組寫成這台的私有模組")
    parser.add_argument("--draft", type=Path, help="模組草稿（JSON 或 YAML）")
    parser.add_argument("--write", action="store_true", help="寫檔；沒加只預覽")
    parser.add_argument("--force", action="store_true", help="同名的私有模組已經存在時覆蓋，舊檔先備份")
    parser.add_argument("--list", action="store_true", help="列出這台的私有模組")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.list:
        return listing(DATA)
    if not args.draft:
        parser.error("要給 --draft <草稿.json>，或 --list")
    return run(args.draft, DATA, write=args.write, force=args.force)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
