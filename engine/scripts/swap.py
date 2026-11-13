# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""替換與換回（FR-17）：把建議裡「換」的那一項套用成 14 天試用，記下替換前的工具清單；換回時照紀錄還原並比對。

流程（每一步都等使用者同意）：
1. start <候選 id> --agent <agent>：預覽要跑的指令、試用到哪天、怎麼換回。加 --write 才記下來，同時用 agent 自己的
   清單（claude plugin list、codex plugin list、codex mcp list，以及 skill 資料夾）拍一張「替換前」的快照。
2. agent 照輸出在終端機跑指令：先裝新的，Claude Code 的 plugin 再把舊的停用（可以再打開）。其他的舊工具先留著，
   試用期間兩個都在。
3. check <id>：再拍一次快照，確認新的出現在 agent 自己的清單、舊的照計畫停用或還在，通過才算開始試用。
4. 試用期間或到期後：
   - revert <id>：印出換回的指令（移除新的、把舊的打開），跑完再 check：舊的與新的都要回到替換前的樣子才算換回。
   - keep <id>：留下新的；印出拿掉舊的指令，拿不拿由使用者決定，一項一項問。
紀錄存在 %LOCALAPPDATA%\\omnikit\\swaps.json，只有工具名稱與狀態，沒有設定內容；MCP 只讀名稱與有沒有啟用，不讀參數。
這支腳本不安裝、不移除任何東西：指令都交給 agent 在使用者同意後執行。

用法：
  uv run engine/scripts/swap.py list
  uv run engine/scripts/swap.py start <候選 id> --agent claude|codex [--write]
  uv run engine/scripts/swap.py check <id>
  uv run engine/scripts/swap.py revert <id>
  uv run engine/scripts/swap.py keep <id>
  uv run engine/scripts/swap.py --selftest
"""
import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cost  # noqa: E402
import profiles  # noqa: E402
import scan  # noqa: E402
import usage  # noqa: E402

STATE = profiles.STATE
TRIAL_DAYS = 14   # FR-16：建議進 14 天試用
QUIET_DAYS = 30   # FR-16：同一個槽位判定之後，30 天內不再推同一個工具
ACTIVE = ("started", "trial", "reverting")
UID = {"claude": "claude-code", "codex": "codex"}
STATES = {"started": "記下了，還沒確認裝好", "trial": "試用中", "reverting": "換回中，還沒確認", "reverted": "已經換回",
          "kept": "留下新的"}


# ---------- 紀錄 ----------

def load(state):
    try:
        doc = json.loads((state / "swaps.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = doc.get("swaps") if isinstance(doc, dict) else None
    return [s for s in items if isinstance(s, dict) and s.get("id")] if isinstance(items, list) else []


def save(state, swaps):
    state.mkdir(parents=True, exist_ok=True)
    (state / "swaps.json").write_bytes((json.dumps({"swaps": swaps}, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


def days_between(a, b):
    try:
        return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
    except ValueError:
        return None


def recent(swaps, agent, today):
    """換回不到 30 天的 {(槽位, 新工具)}：這段期間不再推同一個工具（FR-16）。"""
    return {(s["slot"], s["new"]["tool"]) for s in swaps or [] if s.get("agent") == agent and s.get("state") == "reverted"
            and (days_between(s.get("reverted"), today) or 0) < QUIET_DAYS}


def trials(swaps, agent, today):
    """這個 agent 還沒結束的替換：試用到哪天、還剩幾天、到期了沒。"""
    out = []
    for s in swaps or []:
        if s.get("agent") != agent or s.get("state") not in ACTIVE:
            continue
        left = days_between(today, s.get("trial_until"))
        out.append({"id": s["id"], "slot": s["slot"], "slot_name": s.get("slot_name"), "old": s["old"]["name"],
                    "new": s["new"]["name"], "state": s["state"], "trial_until": s.get("trial_until"), "days_left": left,
                    "expired": left is not None and left < 0})
    return out


# ---------- agent 自己的清單 ----------

def run_cli(args, timeout=120):
    """跑 agent 自己的指令，回傳 stdout；找不到或失敗回 None。Windows 上的 claude、codex 可能是 .cmd，先用 which 找。"""
    exe = shutil.which(args[0])
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *args[1:]], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def snapshot(agent, home, run=run_cli):
    """這個 agent 自己看到的工具：[{kind, name, enabled}]。查不到的那一類記在 unknown，不當成「沒有」。
    MCP 只取名稱與有沒有啟用，不讀指令、參數與環境變數。"""
    items, unknown = [], []

    def as_json(text):
        try:
            return json.loads(text) if text else None
        except ValueError:
            return None

    if agent == "claude":
        plugins = as_json(run(["claude", "plugin", "list", "--json"]))
        if isinstance(plugins, list):
            items += [{"kind": "plugin", "name": p["id"], "enabled": bool(p.get("enabled"))}
                      for p in plugins if isinstance(p, dict) and p.get("id")]
        else:
            unknown.append("plugin")
        names = scan.mcp_names("claude-code", home)  # claude mcp list 會一個一個連線檢查，太慢；名稱照設定檔
        if isinstance(names, list):
            items += [{"kind": "mcp", "name": n, "enabled": True} for n in names]
        else:
            unknown.append("mcp")
    else:
        plugins = as_json(run(["codex", "plugin", "list", "--json"]))
        if isinstance(plugins, dict) and isinstance(plugins.get("installed"), list):
            items += [{"kind": "plugin", "name": p["pluginId"], "enabled": bool(p.get("enabled"))}
                      for p in plugins["installed"] if isinstance(p, dict) and p.get("pluginId") and p.get("installed", True)]
        else:
            unknown.append("plugin")
        servers = as_json(run(["codex", "mcp", "list", "--json"]))
        if isinstance(servers, list):
            items += [{"kind": "mcp", "name": m["name"], "enabled": bool(m.get("enabled", True))}
                      for m in servers if isinstance(m, dict) and m.get("name")]
        else:
            unknown.append("mcp")
    uid = UID[agent]
    items += [{"kind": "skill", "name": i["name"], "enabled": True}
              for i in usage.inventory(home, set(), lambda _p: None) if i["kind"] == "skill" and uid in i["agents"]]
    items.sort(key=lambda x: (x["kind"], x["name"]))
    return {"items": items, "unknown": unknown}


def keys_of(new):
    return {cost.norm(k) for k in (new.get("tool"), new.get("name"), new.get("plugin_name")) if k} - {""}


def find_new(snap, new):
    keys = keys_of(new)
    return [x for x in snap["items"] if cost.norm(x["name"].split("@")[0]) in keys]


def find_old(snap, old):
    return next((x for x in snap["items"] if x["kind"] == old["kind"] and x["name"] == old["name"]), None)


def unknown_for(snap, kinds):
    return [k for k in kinds if k in snap["unknown"]]


# ---------- 指令 ----------

def plan_lines(cand):
    how = cand["how"]
    lines = [f"把「{cand['slot_name']}」的 {cand['old']['name']} 換成 {cand['new']['name']}，試用 {TRIAL_DAYS} 天到 {cand['trial_until']}。"]
    if how["apply"]:
        lines.append("同意後依序執行：" + "，再 ".join(f"`{c}`" for c in how["apply"]))
    lines.append(f"注意：{how['note']}")
    if how["revert"]:
        lines.append("要換回時執行：" + "，再 ".join(f"`{c}`" for c in how["revert"]))
    if how.get("revert_note"):
        lines.append(f"換回的注意：{how['revert_note']}")
    if cand.get("also"):
        lines.append(f"舊的還管：{'、'.join(cand['also'])}；停用之後這幾件事也會受影響。")
    return lines


def start(cand_id, agent, home, data, state, write=False, run=run_cli, today=None, facts=None):
    today = today or date.today()
    if facts is None:
        import advise  # 這裡才 import：advise 也會讀這支的紀錄
        facts = advise.collect(home, data, state)
    entry = (facts.get("agents") or {}).get(agent)
    if not entry or not entry.get("active"):
        print(f"{agent} 這次沒有建議：{(entry or {}).get('skip') or '不是 claude 或 codex'}")
        return 1
    cands = {c["id"]: c for c in entry["candidates"].get("replace", [])}
    cand = cands.get(cand_id)
    if not cand:
        print(f"「{cand_id}」不在這次「換」的候選裡。" + (f"可以選：{'、'.join(cands)}" if cands else "這次沒有「換」的候選。"))
        return 1
    swaps = load(state)
    busy = next((s for s in swaps if s.get("agent") == agent and s.get("slot") == cand["slot"] and s.get("state") in ACTIVE), None)
    if busy:
        print(f"「{cand['slot_name']}」已經有一個替換還沒結束（{busy['id']}，{STATES[busy['state']]}）：先 check、keep 或 revert 它。")
        return 1
    lines = plan_lines(cand)
    if not write:
        print("預覽：\n" + "\n".join(f"- {line}" for line in lines))
        print("\n這是預覽，還沒記下來。使用者同意後加 --write：會先記下替換前的工具清單，再給要跑的指令。")
        return 0
    before = snapshot(agent, home, run)
    sid = f"{cand['slot']}-{today:%Y%m%d}"
    n = 2
    while any(s["id"] == sid for s in swaps):
        sid, n = f"{cand['slot']}-{today:%Y%m%d}-{n}", n + 1
    swaps.append({"id": sid, "agent": agent, "slot": cand["slot"], "slot_name": cand["slot_name"],
                  "old": {k: cand["old"][k] for k in ("kind", "name", "where")},
                  "new": {k: cand["new"].get(k) for k in ("tool", "name", "kind", "plugin_name", "url")},
                  "how": cand["how"], "disable_old": bool(cand["how"].get("disable_old")),
                  "state": "started", "started": today.isoformat(), "trial_until": cand["trial_until"], "before": before})
    save(state, swaps)
    print(f"已記下替換 {sid}，也記下了替換前的工具清單（{len(before['items'])} 項）。")
    if before["unknown"]:
        print(f"注意：這幾類查不到，換回時沒辦法比對：{'、'.join(before['unknown'])}。")
    print("\n".join(f"- {line}" for line in lines))
    print(f"\n跑完之後執行：swap check {sid}")
    return 0


def check(sid, home, state, run=run_cli, today=None):
    today = today or date.today()
    swaps = load(state)
    rec = next((s for s in swaps if s["id"] == sid), None)
    if rec is None:
        print(f"找不到替換 {sid}。")
        return 1
    if rec["state"] not in ("started", "reverting"):
        left = days_between(today, rec.get("trial_until"))
        print(f"{sid}：{STATES[rec['state']]}" + (f"，試用到 {rec['trial_until']}（還有 {left} 天）" if rec["state"] == "trial" and left is not None else ""))
        return 0
    now = snapshot(rec["agent"], home, run)
    kinds = {rec["old"]["kind"], rec["new"].get("kind") or "plugin"}
    missing = unknown_for(now, kinds) or (unknown_for(rec["before"], kinds) if rec["state"] == "reverting" else [])
    if missing:
        print(f"{sid}：查不到 {'、'.join(missing)} 的清單，沒辦法確認（未知，不算通過）。")
        return 1
    new_now, old_now = find_new(now, rec["new"]), find_old(now, rec["old"])
    problems = []
    if rec["state"] == "started":
        if not any(x["enabled"] for x in new_now):
            problems.append(f"{rec['new']['name']} 還沒出現在 agent 自己的清單裡，或沒有啟用")
        if old_now is None:
            problems.append(f"舊的 {rec['old']['name']} 不見了：試用期間先留著，換回才有東西可以打開")
        elif rec["disable_old"] and old_now["enabled"]:
            problems.append(f"舊的 {rec['old']['name']} 還沒停用")
        if problems:
            print(f"{sid}：還沒好。\n" + "\n".join(f"- {p}" for p in problems))
            return 1
        rec.update(state="trial", checked=today.isoformat())
        save(state, swaps)
        print(f"{sid}：確認好了，開始試用，到 {rec['trial_until']}。新的：{'、'.join(x['name'] for x in new_now)}；"
              f"舊的：{old_now['name']}（{'已停用' if not old_now['enabled'] else '還在，先留著'}）。開新的對話才會載入。")
        return 0
    # 換回：這次動到的兩個都要回到替換前的樣子
    before_old, before_new = find_old(rec["before"], rec["old"]), find_new(rec["before"], rec["new"])
    if old_now != before_old:
        problems.append(f"舊的 {rec['old']['name']}：替換前是 {state_text(before_old)}，現在是 {state_text(old_now)}")
    if sorted(map(json.dumps, new_now)) != sorted(map(json.dumps, before_new)):
        problems.append(f"新的 {rec['new']['name']}：替換前是 {state_text(before_new[0] if before_new else None)}，"
                        f"現在是 {'、'.join(state_text(x) for x in new_now) or state_text(None)}")
    if problems:
        print(f"{sid}：還沒換回。\n" + "\n".join(f"- {p}" for p in problems))
        return 1
    involved = {json.dumps(x) for x in [before_old, *before_new, old_now, *new_now] if x}
    others = sorted({x["name"] for x in diff(rec["before"]["items"], now["items"]) if json.dumps(x) not in involved})
    rec.update(state="reverted", reverted=today.isoformat())
    save(state, swaps)
    print(f"{sid}：已經換回，這次動到的兩個都跟替換前一樣。{QUIET_DAYS} 天內不會再建議換成 {rec['new']['name']}。開新的對話才會生效。")
    if others:
        print(f"另外，這段期間 agent 的清單還有這些變動，不是這次替換造成的，沒有動：{'、'.join(others)}")
    return 0


def state_text(x):
    return "沒有" if x is None else ("啟用" if x["enabled"] else "停用")


def diff(before, after):
    a, b = {json.dumps(x, sort_keys=True) for x in before}, {json.dumps(x, sort_keys=True) for x in after}
    return [json.loads(x) for x in a ^ b]


def revert(sid, state):
    swaps = load(state)
    rec = next((s for s in swaps if s["id"] == sid), None)
    if rec is None or rec["state"] not in ("started", "trial", "reverting"):
        print(f"{sid}：" + ("找不到" if rec is None else f"{STATES[rec['state']]}，不能換回"))
        return 1
    how = rec["how"]
    print(f"換回 {sid}：拿掉 {rec['new']['name']}，回到 {rec['old']['name']}。")
    if how["revert"]:
        print("依序執行：" + "，再 ".join(f"`{c}`" for c in how["revert"]))
    if how.get("revert_note"):
        print(f"注意：{how['revert_note']}")
    print(f"跑完之後執行：swap check {sid}")
    rec["state"] = "reverting"
    save(state, swaps)
    return 0


def keep(sid, state, today=None):
    today = today or date.today()
    swaps = load(state)
    rec = next((s for s in swaps if s["id"] == sid), None)
    if rec is None or rec["state"] != "trial":
        print(f"{sid}：" + ("找不到" if rec is None else f"{STATES[rec['state']]}；要先 check 確認裝好才能留下"))
        return 1
    rec.update(state="kept", kept=today.isoformat())
    save(state, swaps)
    finish = rec["how"]["finish"]
    print(f"{sid}：留下 {rec['new']['name']}。舊的 {rec['old']['name']} 要不要拿掉由你決定；拿掉是刪除，先問過再做：")
    for key, text in (("disable", "只停用（可以再打開）"), ("remove", "移除"), ("remove_path", "刪掉資料夾")):
        if finish.get(key):
            print(f"- {text}：`{finish[key]}`")
    if finish.get("note"):
        print(f"- 注意：{finish['note']}")
    return 0


def listing(state, today=None):
    today = today or date.today()
    swaps = load(state)
    if not swaps:
        print("還沒有替換紀錄。")
        return 0
    for s in swaps:
        extra = ""
        if s["state"] in ACTIVE:
            left = days_between(today, s.get("trial_until"))
            extra = f"，試用到 {s.get('trial_until')}" + (f"（已經過期 {-left} 天，問要留新的還是換回）" if left is not None and left < 0 else
                                                     f"（還有 {left} 天）" if left is not None else "")
        print(f"- {s['id']}（{s['agent']}）：{s['old']['name']} → {s['new']['name']}，{STATES.get(s['state'], s['state'])}{extra}")
    return 0


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check_(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    def call(fn, *args, **kwargs):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(*args, **kwargs)
        return code, buf.getvalue()

    class Fake:
        """假的 agent：記著裝了哪些 plugin 與 MCP，照指令改。"""
        def __init__(self, plugins, mcp, broken=()):
            self.plugins, self.mcp, self.broken, self.calls = dict(plugins), dict(mcp), set(broken), []

        def __call__(self, args):
            self.calls.append(args)
            if args[:3] == ["claude", "plugin", "list"]:
                return None if "plugin" in self.broken else json.dumps([{"id": k, "enabled": v} for k, v in self.plugins.items()])
            if args[:3] == ["codex", "plugin", "list"]:
                return None if "plugin" in self.broken else json.dumps({"installed": [
                    {"pluginId": k, "enabled": v, "installed": True} for k, v in self.plugins.items()]})
            if args[:3] == ["codex", "mcp", "list"]:
                return json.dumps([{"name": k, "enabled": v, "transport": {"env": {"SECRET": "x"}}} for k, v in self.mcp.items()])
            return None

        def do(self, command):
            word = command.split()
            name = word[-1]
            if word[1:3] in (["plugin", "install"], ["plugin", "add"]):
                self.plugins[name] = True
            elif word[1:3] in (["plugin", "uninstall"], ["plugin", "remove"]):
                self.plugins.pop(name, None)
            elif word[1:3] == ["plugin", "disable"]:
                self.plugins[name] = False
            elif word[1:3] == ["plugin", "enable"]:
                self.plugins[name] = True

    today = date(2026, 11, 14)
    cand = {"id": "replace:fe:old-fe:fe", "slot": "fe", "slot_name": "前端", "module": "dev", "trial_until": "2026-11-28",
            "old": {"kind": "plugin", "name": "old-fe@x", "where": "~/.claude/plugins", "status": "used"},
            "new": {"tool": "fe", "name": "fe", "kind": "plugin", "plugin_name": "fe-plugin", "url": "https://example.com/fe"},
            "also": [],
            "how": {"apply": ["claude plugin install fe-plugin@mk", "claude plugin disable old-fe@x"], "disable_old": True,
                    "revert": ["claude plugin uninstall fe-plugin@mk", "claude plugin enable old-fe@x"], "note": "開新的對話才會載入",
                    "finish": {"disable": "claude plugin disable old-fe@x", "remove": "claude plugin uninstall old-fe@x"}}}
    facts = {"agents": {"claude": {"active": True, "candidates": {"replace": [cand]}},
                        "codex": {"active": False, "skip": "這台沒有裝，不出建議", "candidates": {}}}}

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        home, state = tmp / "home", tmp / "state"
        (home / ".claude" / "skills" / "my-skill").mkdir(parents=True)
        (home / ".claude" / "skills" / "my-skill" / "SKILL.md").write_text("---\nname: my-skill\n---\n", encoding="utf-8")
        (home / ".claude.json").write_text(json.dumps({"mcpServers": {"srv": {"env": {"TOKEN": "secret"}}}}), encoding="utf-8")
        agent = Fake({"old-fe@x": True, "other@y": True}, {})

        snap = snapshot("claude", home, agent)
        check_("快照：plugin 用 agent 自己的清單、MCP 只有名稱、skill 照資料夾；不帶設定內容",
               snap == {"items": [{"kind": "mcp", "name": "srv", "enabled": True},
                                  {"kind": "plugin", "name": "old-fe@x", "enabled": True},
                                  {"kind": "plugin", "name": "other@y", "enabled": True},
                                  {"kind": "skill", "name": "my-skill", "enabled": True}], "unknown": []}
               and "secret" not in json.dumps(snap))
        codex_snap = snapshot("codex", home, Fake({"p@m": False}, {"chrome": True, "off": False}))
        check_("快照（Codex）：plugin 與 MCP 都用 agent 自己的清單，只取名稱與有沒有啟用",
               [x for x in codex_snap["items"] if x["kind"] != "skill"] == [
                   {"kind": "mcp", "name": "chrome", "enabled": True}, {"kind": "mcp", "name": "off", "enabled": False},
                   {"kind": "plugin", "name": "p@m", "enabled": False}] and "SECRET" not in json.dumps(codex_snap))
        check_("快照：查不到的那一類記成未知，不當成沒有", snapshot("claude", home, Fake({}, {}, broken={"plugin"}))["unknown"] == ["plugin"])

        code, out = call(start, cand["id"], "claude", home, None, state, facts=facts, today=today, run=agent)
        check_("預覽：講要跑的指令、試用到哪天、怎麼換回；不記任何東西", code == 0 and "2026-11-28" in out
               and "claude plugin uninstall fe-plugin@mk" in out and "還沒記下來" in out and not (state / "swaps.json").exists())
        check_("不在候選裡的：不記", call(start, "replace:nope", "claude", home, None, state, facts=facts, run=agent)[0] == 1)
        check_("這個 agent 沒有建議：不記", "這台沒有裝" in call(start, cand["id"], "codex", home, None, state, facts=facts, run=agent)[1])

        code, out = call(start, cand["id"], "claude", home, None, state, write=True, facts=facts, today=today, run=agent)
        rec = load(state)[0]
        check_("--write：記下替換與替換前的清單，狀態是還沒確認", code == 0 and rec["id"] == "fe-20261114" and rec["state"] == "started"
               and rec["before"] == snap and "swap check fe-20261114" in out)
        check_("同一個槽位還沒結束，不能再開一個", "還沒結束" in call(start, cand["id"], "claude", home, None, state, write=True, facts=facts, run=agent)[1])

        code, out = call(check, "fe-20261114", home, state, agent, today)
        check_("還沒跑指令就 check：講明還沒好，不算開始試用", code == 1 and "還沒出現" in out and load(state)[0]["state"] == "started")
        agent.do("claude plugin install fe-plugin@mk")
        agent.plugins["fe-plugin@mk"] = False
        code, out = call(check, "fe-20261114", home, state, agent, today)
        check_("新的裝了但是停用：還沒好", code == 1 and "沒有啟用" in out)
        agent.plugins["fe-plugin@mk"] = True
        gone = agent.plugins.pop("old-fe@x")
        code, out = call(check, "fe-20261114", home, state, agent, today)
        check_("舊的被拿掉了：還沒好，試用期間要留著", code == 1 and "不見了" in out)
        agent.plugins["old-fe@x"] = gone
        code, out = call(check, "fe-20261114", home, state, agent, today)
        check_("新的裝好了、舊的還沒停用：還沒好", code == 1 and "還沒停用" in out)
        agent.do("claude plugin disable old-fe@x")
        code, out = call(check, "fe-20261114", home, state, agent, today)
        check_("新的出現、舊的停用：開始試用", code == 0 and load(state)[0]["state"] == "trial" and "到 2026-11-28" in out)
        check_("試用中再 check：只講狀態與剩幾天", "還有 4 天" in call(check, "fe-20261114", home, state, agent, today + timedelta(days=10))[1])

        check_("試用中的：列出來，到期了另外講", trials(load(state), "claude", today + timedelta(days=15))[0]["expired"]
               and not trials(load(state), "claude", today)[0]["expired"] and trials(load(state), "codex", today) == [])
        check_("清單：過期的提醒要決定", "已經過期 1 天" in call(listing, state, today + timedelta(days=15))[1])

        agent.plugins["unrelated@z"] = True  # 試用期間使用者自己另外裝的
        code, out = call(revert, "fe-20261114", state)
        check_("換回：印出移除新的、打開舊的指令，狀態改成換回中", code == 0 and "claude plugin uninstall fe-plugin@mk" in out
               and "claude plugin enable old-fe@x" in out and load(state)[0]["state"] == "reverting")
        agent.do("claude plugin enable old-fe@x")
        code, out = call(check, "fe-20261114", home, state, agent, today)
        check_("只打開舊的、新的還在：不算換回", code == 1 and "新的 fe" in out and load(state)[0]["state"] == "reverting")
        agent.do("claude plugin disable old-fe@x")
        agent.do("claude plugin uninstall fe-plugin@mk")
        code, out = call(check, "fe-20261114", home, state, agent, today)
        check_("只做一半：舊的還是停用，不算換回", code == 1 and "替換前是 啟用，現在是 停用" in out)
        agent.do("claude plugin enable old-fe@x")
        code, out = call(check, "fe-20261114", home, state, agent, today + timedelta(days=3))
        check_("換回：動到的兩個都跟替換前一樣才算；另外的變動列出來但不動", code == 0 and load(state)[0]["state"] == "reverted"
               and "unrelated@z" in out and "old-fe" not in out.split("另外")[-1])
        check_("換回之後 30 天內不再推同一個工具，之後才再推；只看同一個 agent",
               recent(load(state), "claude", today + timedelta(days=20)) == {("fe", "fe")}
               and recent(load(state), "codex", today + timedelta(days=20)) == set()
               and recent(load(state), "claude", today + timedelta(days=3 + QUIET_DAYS)) == set())
        check_("已經換回的不能再換回或留下", call(revert, "fe-20261114", state)[0] == 1 and call(keep, "fe-20261114", state)[0] == 1)

        # 留下新的
        state2 = tmp / "state2"
        agent2 = Fake({"old-fe@x": True}, {})
        call(start, cand["id"], "claude", home, None, state2, write=True, facts=facts, today=today, run=agent2)
        check_("還沒確認裝好就留下：不行", call(keep, "fe-20261114", state2)[0] == 1)
        for c in cand["how"]["apply"]:
            agent2.do(c)
        call(check, "fe-20261114", home, state2, agent2, today)
        code, out = call(keep, "fe-20261114", state2, today)
        check_("留下新的：舊的拿不拿由使用者決定，給停用與移除兩種", code == 0 and load(state2)[0]["state"] == "kept"
               and "claude plugin uninstall old-fe@x" in out and "由你決定" in out)

        # 舊的沒有停用的指令（例如 Codex 的 plugin）：試用期間兩個都在
        keep_old = {**cand, "how": {**cand["how"], "apply": ["codex plugin add fe-plugin@mk"], "disable_old": False,
                                    "revert": ["codex plugin remove fe-plugin@mk"]},
                    "old": {**cand["old"], "name": "old-fe@x", "where": "~/.codex/plugins"}}
        state3 = tmp / "state3"
        agent3 = Fake({"old-fe@x": True}, {})
        call(start, cand["id"], "codex", home, None, state3, write=True, today=today, run=agent3,
             facts={"agents": {"codex": {"active": True, "candidates": {"replace": [keep_old]}}}})
        agent3.do("codex plugin add fe-plugin@mk")
        code, out = call(check, "fe-20261114", home, state3, agent3, today)
        check_("舊的沒有停用的指令：兩個都在就算開始試用", code == 0 and "還在，先留著" in out)
        agent3.plugins.pop("old-fe@x")
        call(revert, "fe-20261114", state3)
        agent3.do("codex plugin remove fe-plugin@mk")
        check_("試用期間舊的被拿掉了：換回時講明舊的不在", "替換前是 啟用，現在是 沒有" in call(check, "fe-20261114", home, state3, agent3, today)[1])
        broken = Fake({"old-fe@x": True}, {}, broken={"plugin"})
        check_("查不到清單：未知，不算通過", "未知" in call(check, "fe-20261114", home, state3, broken, today)[1])

        (state / "swaps.json").write_text("{壞掉", encoding="utf-8")
        check_("紀錄壞了：當成沒有紀錄", load(state) == [])
        check_("找不到的 id：講明", call(check, "nope", home, state, agent, today)[0] == 1)

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="替換與換回：14 天試用，記下替換前的工具清單")
    parser.add_argument("command", nargs="?", choices=["list", "start", "check", "revert", "keep"])
    parser.add_argument("target", nargs="?", help="start：候選 id；check、revert、keep：替換的 id")
    parser.add_argument("--agent", choices=["claude", "codex"])
    parser.add_argument("--write", action="store_true", help="start：記下來；沒加只預覽")
    parser.add_argument("--selftest", action="store_true")
    a = parser.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.command == "list":
        return listing(STATE)
    if not a.target:
        parser.error("要給候選 id 或替換的 id")
    if a.command == "start":
        if not a.agent:
            parser.error("start 要給 --agent")
        return start(a.target, a.agent, Path.home(), profiles.DATA, STATE, write=a.write)
    if a.command == "check":
        return check(a.target, Path.home(), STATE)
    if a.command == "revert":
        return revert(a.target, STATE)
    if a.command == "keep":
        return keep(a.target, STATE)
    parser.error("要給 list、start、check、revert 或 keep")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
