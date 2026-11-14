# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "jsonschema"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""影子比對：試用到期前，拿試用期間的真實任務，用舊工具在副本重跑，讓使用者盲選新舊成果。

業界做法與取捨見 docs/proposals/2026-11-14-decision-evidence.md（影子測試、冠軍與挑戰者；重播不等於原場景）。

一次比對一個替換（swaps.json 的 id），紀錄都在 %LOCALAPPDATA%\\omnikit\\shadow\\<替換 id>\\，只在這台，不進 repo、不回流。
1. record：從對話紀錄找試用期間叫用過新工具的對話（Claude Code 與 Codex），記下專案、使用者的第一個要求、
   開始前的 commit 與結束時的 commit。對話結束時沒有新的 commit 的記成「沒有成果可以比」。
2. pick：挑 2 到 3 筆（有成果、要求看得懂、不同專案優先、新的優先）。不到 2 筆就照實說沒辦法比，建議延長或換回，不硬湊。
3. prepare：每筆在 repo 外的副本準備三份：base（開始前的 commit，原版）、new（結束時的 commit，新工具真的做出來的）、
   old（開始前的 commit 加上舊工具，等重跑）。--setup 可以在每份跑安裝指令（例如 npm ci）。
4. rerun：old 那份用舊工具跑一次「第一個要求」（預設 T3 子對話、retis 的 Claude）。只重跑第一個要求：
   使用者後來追加的修改比不到，結果會寫明。
5. compare：每筆寫出 base→old、base→new 的 diff；有畫面的加 --serve-cmd，建一個 blind.py 的盲選資料夾（原版不蒙）並封存。
   使用者照 blind.py serve、choose、reveal 選。
6. result：彙整每筆的盲選結果，寫 result.json；到期通知（notify.py）會附上這一行。

這支腳本只讀對話紀錄與 git，只寫 shadow 資料夾與副本；不動真的專案、不 push、不連外網（rerun 透過 T3 叫 agent）。

用法：
  uv run engine/scripts/shadow.py record <替換 id>
  uv run engine/scripts/shadow.py pick <替換 id> [--n 3]
  uv run engine/scripts/shadow.py prepare <替換 id> --old-skill <舊工具的 skill 資料夾> [--setup "npm ci"] [--subdir 子資料夾]
  uv run engine/scripts/shadow.py rerun <替換 id> [--model claude-opus-5-5]
  uv run engine/scripts/shadow.py compare <替換 id> [--serve-cmd "node ui-mock.mjs"] [--port-env 變數] [--fingerprint index.html]
  uv run engine/scripts/shadow.py result <替換 id>
  uv run engine/scripts/shadow.py status <替換 id>
  uv run engine/scripts/shadow.py --selftest
"""
import argparse
import contextlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "skills" / "omnikit-eval" / "scripts"))
import blind  # noqa: E402
import swap  # noqa: E402
import usage  # noqa: E402

STATE = swap.STATE
MIN_TASKS = 2
MAX_TASKS = 3
SKIP_CWD = re.compile(r"omnikit-eval|[\\/]\.t3[\\/]", re.I)  # 實測與暫存的副本不算真實任務
INJECTED = re.compile(r"^\s*(#\s*AGENTS\.md|<environment_context>|<user_instructions>|<app-context>|<permissions|<INSTRUCTIONS>)")
T3 = str(Path.home() / ".t3" / "bin" / ("t3.cmd" if os.name == "nt" else "t3"))
RETIS = "claudeAgent_2"
PROMPT = """你在一個專案的副本裡，這是一次比對用的重跑：不會影響真的專案。
先完整讀 .agents/skills/{skill}/SKILL.md，照它的方法做這個要求；它要求讀的參考檔也要讀。
不要 commit、不要 push、不要裝新的全域工具。做完用三五行說明改了什麼。

使用者的要求（原文）：
{request}"""


def folder(sid, state=STATE):
    return state / "shadow" / sid


def read_json(path, default=None):
    return blind.read_json(path, default)


def write_json(path, doc):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    blind.write_json(path, doc)


def get_swap(sid, state):
    rec = next((s for s in swap.load(state) if s["id"] == sid), None)
    if rec is None:
        raise SystemExit(f"swaps.json 裡沒有 {sid}（swap.py list 看有哪些）")
    return rec


def git(args, cwd, env=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.stdout.strip() if r.returncode == 0 else None


# ---------- 1. 記下真實任務 ----------

def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") in ("text", "input_text"))
    return ""


def first_request(text):
    """使用者真正打的字：去掉注入的規則、slash 指令標記與系統提醒。"""
    if not text or INJECTED.match(text) or text.lstrip().startswith(("<command-", "<local-command", "<system-reminder", "Caveat:")):
        cmd = usage.COMMAND.match(text or "")
        if cmd:
            args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
            return f"/{cmd.group(1)} {args.group(1).strip() if args else ''}".strip()
        return None
    return text.strip()


def session_info(path):
    """對話紀錄 → cwd、第一個要求、開始與結束時間。"""
    cwd = req = None
    first = last = None
    try:
        f = open(path, "rb")
    except OSError:
        return None
    with f:
        for raw in f:
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            ts = usage.parse_time(d.get("timestamp"))
            if ts:
                first, last = first or ts, ts
            payload = d.get("payload") if isinstance(d.get("payload"), dict) else {}
            cwd = cwd or d.get("cwd") or (payload.get("cwd") if d.get("type") == "session_meta" else None)
            if req:
                continue
            if d.get("type") == "user" and not d.get("isSidechain") and not d.get("isMeta"):
                req = first_request(text_of((d.get("message") or {}).get("content")))
            elif d.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
                req = first_request(text_of(payload.get("content")))
            elif d.get("type") == "event_msg" and payload.get("type") == "user_message":
                req = first_request(payload.get("message"))
    if not cwd or first is None:
        return None
    return {"cwd": cwd, "request": req, "first": first, "last": last}


def commit_at(root, ts):
    return git(["rev-list", "-1", f"--before={iso(ts)}", "HEAD"], root)


def record(sid, home, state, now=None):
    rec = get_swap(sid, state)
    since = datetime.fromisoformat(rec["started"]).timestamp()  # 試用開始那天的本地午夜
    events = {}
    usage.claude_events(home, since, events)
    usage.codex_events(home, since, events)
    agent = swap.UID[rec["agent"]]
    keys = swap.keys_of(rec["new"])
    sessions = set()
    for name, use in (events.get(agent) or {}).items():
        base = name.split("@")[0].split(":")[0]
        if swap.cost.norm(base) in keys or swap.cost.norm(name.split("@")[0]) in keys:
            sessions |= {s for s in use["sessions"] if s}
    doc = read_json(folder(sid, state) / "tasks.json", {"tasks": []})
    have = {t["session"] for t in doc["tasks"]}
    added = 0
    for s in sorted(sessions - have):
        info = session_info(s)
        if not info:
            continue
        task = {"id": f"t{len(doc['tasks']) + 1}", "agent": rec["agent"], "session": s, "cwd": info["cwd"],
                "request": info["request"], "started": iso(info["first"]), "ended": iso(info["last"])}
        root = git(["rev-parse", "--show-toplevel"], info["cwd"]) if Path(info["cwd"]).is_dir() else None
        if SKIP_CWD.search(info["cwd"]):
            task["skip"] = "實測或暫存的副本，不是真實任務"
        elif not root:
            task["skip"] = "不是 git 專案，沒有起點可以重跑"
        elif not info["request"]:
            task["skip"] = "找不到使用者的第一個要求"
        else:
            start, end = commit_at(root, info["first"]), commit_at(root, info["last"] + 600)
            task.update(root=root, start_commit=start, end_commit=end,
                        subdir=str(Path(info["cwd"]).resolve().relative_to(Path(root).resolve())).replace("\\", "/"))
            if not start:
                task["skip"] = "對話開始前沒有 commit"
            elif start == end:
                task["skip"] = "對話結束時沒有新的 commit，沒有成果可以比"
        doc["tasks"].append(task)
        added += 1
    doc["recorded"] = (now or date.today()).isoformat()
    write_json(folder(sid, state) / "tasks.json", doc)
    usable = [t for t in doc["tasks"] if not t.get("skip")]
    print(f"{sid}：試用期間叫用 {rec['new']['name']} 的對話 {len(doc['tasks'])} 段（這次新記 {added} 段），可以比的 {len(usable)} 段。")
    for t in doc["tasks"]:
        print(f"- {t['id']} {Path(t['cwd']).name}：{(t['request'] or '（沒有要求）')[:60]}" + (f"　→ 不比：{t['skip']}" if t.get("skip") else ""))
    return 0


# ---------- 2. 挑題 ----------

def pick(sid, state, n=MAX_TASKS):
    doc = read_json(folder(sid, state) / "tasks.json", {"tasks": []})
    usable = [t for t in doc["tasks"] if not t.get("skip") and 10 <= len(t["request"] or "") <= 4000]
    usable.sort(key=lambda t: t["ended"], reverse=True)
    chosen, roots = [], set()
    for t in usable:  # 不同專案優先
        if t["root"] not in roots:
            chosen.append(t)
            roots.add(t["root"])
    chosen += [t for t in usable if t not in chosen]
    chosen = chosen[:n]
    if len(chosen) < MIN_TASKS:
        write_json(folder(sid, state) / "picks.json", {"picks": [], "reason": "too-few", "usable": len(chosen)})
        print(f"試用期間能比的真實任務只有 {len(chosen)} 筆（至少要 {MIN_TASKS} 筆），沒辦法比。"
              "建議延長試用，或憑使用感覺決定留下或換回；不硬湊。")
        return 1
    write_json(folder(sid, state) / "picks.json", {"picks": [t["id"] for t in chosen]})
    print(f"挑了 {len(chosen)} 筆：" + "、".join(f"{t['id']}（{Path(t['cwd']).name}）" for t in chosen))
    return 0


def picked(sid, state):
    doc = read_json(folder(sid, state) / "tasks.json", {"tasks": []})
    ids = read_json(folder(sid, state) / "picks.json", {}).get("picks") or []
    if not ids:
        raise SystemExit("還沒挑題：先跑 pick")
    return [t for t in doc["tasks"] if t["id"] in ids]


# ---------- 3. 準備副本 ----------

def extract(root, commit, dest):
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tar = Path(td) / "a.tar"
        if git(["archive", "--format=tar", "-o", str(tar), commit], root) is None:
            raise SystemExit(f"git archive {commit} 失敗（{root}）")
        with tarfile.open(tar) as t:
            t.extractall(dest, filter="data")


def baseline(repo):
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(repo.parent)}
    git(["init", "-q"], repo, env)
    (repo / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "info" / "exclude").write_text("node_modules/\n.agents/\n", encoding="utf-8")  # 不動專案自己的 .gitignore
    for args in (["add", "-A"], ["-c", "user.name=shadow", "-c", "user.email=shadow@local", "commit", "-qm", "baseline"]):
        git(args, repo, env)


def prepare(sid, state, old_skill, setup=None, subdir=None):
    rec = get_swap(sid, state)
    old_skill = Path(old_skill) if old_skill else None
    if not old_skill or not (old_skill / "SKILL.md").is_file():
        print(f"要給舊工具（{rec['old']['name']}）的 skill 資料夾（裡面有 SKILL.md）：--old-skill <資料夾>")
        return 1
    for t in picked(sid, state):
        base = folder(sid, state) / "runs" / t["id"]
        if base.exists():
            shutil.rmtree(base)
        for arm in ("base", "old", "new"):
            repo = base / arm / "repo"
            extract(t["root"], t["start_commit"], repo)
            if arm == "old":
                shutil.copytree(old_skill, repo / ".agents" / "skills" / rec["old"]["name"])
            baseline(repo)
            if arm == "new":  # 開始前的 commit 當基準，換成結束時的檔案：工作目錄的差異就是新工具做出來的
                for x in repo.iterdir():
                    if x.name != ".git":
                        shutil.rmtree(x) if x.is_dir() else x.unlink()
                extract(t["root"], t["end_commit"], repo)
            work = repo / (subdir or t.get("subdir") or "")
            if setup:
                r = subprocess.run(setup, cwd=work, shell=True, capture_output=True, text=True, errors="replace", timeout=1800)
                if r.returncode:
                    print(f"{t['id']} {arm}：{setup} 失敗：{r.stderr[-500:]}")
                    return 1
        write_json(base / "task.json", {**t, "old_tool": rec["old"]["name"], "subdir": subdir or t.get("subdir") or ""})
        print(f"{t['id']}：副本準備好了（base、old、new）在 {base}")
    return 0


# ---------- 4. 重跑 ----------

def exec_t3(repo, prompt, model):
    subprocess.run([T3, "project", "add", str(repo), "--title", "OmniKit 影子比對"], capture_output=True, timeout=120)
    p = subprocess.run([T3, "thread", "start", str(repo), "-", "--title", "OmniKit 影子比對（舊工具重跑）", "--provider", RETIS,
                        "--model", model, "--wait", "--json"], input=prompt, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=7200)
    try:
        doc = json.loads(p.stdout)
        return {"status": doc.get("status"), "thread": doc.get("threadId"), "reply": doc.get("reply")}
    except ValueError:
        return {"status": "parse-error", "raw": p.stdout[-1000:], "stderr": p.stderr[-1000:]}


def rerun(sid, state, model="claude-opus-5-5", executor=exec_t3):
    rec = get_swap(sid, state)
    for t in picked(sid, state):
        base = folder(sid, state) / "runs" / t["id"]
        if not (base / "old" / "repo").is_dir():
            print(f"{t['id']}：還沒準備副本，先跑 prepare")
            return 1
        t0 = time.time()
        print(f"{t['id']}：用 {rec['old']['name']} 重跑第一個要求……", flush=True)
        out = executor(base / "old" / "repo", PROMPT.format(skill=rec["old"]["name"], request=t["request"]), model)
        out.update(secs=round(time.time() - t0), model=model, at=datetime.now().isoformat(timespec="seconds"))
        write_json(base / "rerun.json", out)
        print(f"  {out.get('status')}，{out['secs']} 秒")
    return 0


# ---------- 5. 比對 ----------

def diff_of(repo):
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(repo.parent)}
    git(["add", "-A"], repo, env)
    return git(["diff", "--cached", "--", ".", ":!.agents"], repo, env) or ""


def split_cmd(text):
    if os.name != "nt":
        return shlex.split(text)
    return [x[1:-1] if len(x) > 1 and x[0] == x[-1] == '"' else x for x in shlex.split(text, posix=False)]


def compare(sid, state, serve_cmd=None, port_env=None, fingerprint="index.html"):
    for t in picked(sid, state):
        base = folder(sid, state) / "runs" / t["id"]
        info = read_json(base / "task.json", {})
        if not read_json(base / "rerun.json"):
            print(f"{t['id']}：舊工具還沒重跑，先跑 rerun")
            return 1
        old = diff_of(base / "old" / "repo")
        (base / "old.patch").write_text(old, encoding="utf-8")
        (base / "new.patch").write_text(diff_of(base / "new" / "repo"), encoding="utf-8")
        print(f"{t['id']}：diff 寫在 {base}（old.patch、new.patch）" + ("；舊工具什麼都沒改" if not old.strip() else ""))
        if serve_cmd:
            sub = info.get("subdir") or ""
            spec = {"title": f"影子比對 {sid} {t['id']}", "reference": "base", "phases": ["gray", "color"],
                    "fingerprint": [{"path": "/", "file": fingerprint}],
                    "versions": {arm: {"dir": str(base / arm / "repo" / sub), "cmd": split_cmd(serve_cmd),
                                       **({"port_env": port_env} if port_env else {})} for arm in ("base", "old", "new")}}
            bf = base / "blind"
            if bf.exists():
                shutil.rmtree(bf)
            bf.mkdir()
            write_json(bf / "spec.json", spec)
            blind.seal(bf)
            print(f"  盲選：uv run engine/skills/omnikit-eval/scripts/blind.py serve {bf}")
    return 0


# ---------- 6. 結果 ----------

def result(sid, state):
    rec = get_swap(sid, state)
    tasks = picked(sid, state) if read_json(folder(sid, state) / "picks.json", {}).get("picks") else []
    tally = {"new": 0, "old": 0, "tie": 0}
    rows, pending = [], []
    for t in tasks:
        res = read_json(folder(sid, state) / "runs" / t["id"] / "blind" / "result.json")
        if not res:
            pending.append(t["id"])
            continue
        main = next((c for c in res["choices"] if c["phase"] == "gray"), None) or res["choices"][0]
        side = main["pick_name"] if main["pick_name"] in ("new", "old") else "tie"
        tally[side] += 1
        rows.append({"task": t["id"], "pick": side, "forced": res.get("forced", False),
                     "color": next((c["pick_name"] for c in res["choices"] if c["phase"] == "color"), None)})
    caveats = ["只重跑第一個要求：新工具的成果包含使用者後來追加的修改，舊工具沒有"]
    if not tasks:
        summary = f"影子比對：試用期間能比的真實任務不到 {MIN_TASKS} 筆，沒辦法比"
    elif pending:
        summary = f"影子比對：{len(rows)}/{len(tasks)} 筆選完（{'、'.join(pending)} 還沒選）"
    else:
        summary = (f"影子比對 {len(rows)} 筆：{rec['new']['name']} 勝 {tally['new']}、{rec['old']['name']} 勝 {tally['old']}、"
                   f"平手 {tally['tie']}（以灰階為準）")
    doc = {"swap": sid, "summary": summary, "tally": tally, "rows": rows, "pending": pending, "caveats": caveats,
           "folder": str(folder(sid, state)), "at": date.today().isoformat()}
    write_json(folder(sid, state) / "result.json", doc)
    print(summary + "。注意：" + "；".join(caveats))
    return 0


def status(sid, state):
    f = folder(sid, state)
    tasks = read_json(f / "tasks.json", {"tasks": []})["tasks"]
    picks = read_json(f / "picks.json", {}).get("picks") or []
    print(f"{sid}：記下 {len(tasks)} 段對話，可以比的 {sum(1 for t in tasks if not t.get('skip'))} 段，挑了 {len(picks)} 筆。")
    for tid in picks:
        b = f / "runs" / tid
        steps = [("副本", (b / "old" / "repo").is_dir()), ("重跑", (b / "rerun.json").exists()),
                 ("封存", (b / "blind" / "sealed.json").exists()), ("選完", (b / "blind" / "result.json").exists())]
        print(f"- {tid}：" + "、".join(f"{n}{'✓' if ok else '…'}" for n, ok in steps))
    res = read_json(f / "result.json")
    if res:
        print(res["summary"])
    return 0


def summary_line(sid, state=STATE):
    """給通知用：有結果就回一行，沒有就 None。"""
    res = read_json(folder(sid, state) / "result.json")
    return res.get("summary") if isinstance(res, dict) else None


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def ok(cond, msg):
        print(f"{'通過' if cond else '失敗'}：{msg}")
        if not cond:
            failures.append(msg)

    def quiet(fn, *a, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                rc = fn(*a, **kw)
            except SystemExit as e:
                rc = f"exit:{e}"
        return rc, buf.getvalue()

    ok(first_request("# AGENTS.md instructions for C:\\x\n<INSTRUCTIONS>") is None, "注入的 AGENTS.md 不算使用者的要求")
    ok(first_request("<command-name>/unslop</command-name><command-args>把設定頁整理一下</command-args>") == "/unslop 把設定頁整理一下",
       "slash 指令帶參數算要求")
    ok(first_request("  幫我改首頁  ") == "幫我改首頁", "一般要求原樣保留")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        home, state = tmp / "home", tmp / "state"
        env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp)}

        def commit(repo, files, msg, when):
            for k, v in files.items():
                (repo / k).parent.mkdir(parents=True, exist_ok=True)
                (repo / k).write_text(v, encoding="utf-8")
            git(["add", "-A"], repo, env)
            git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg, "--date", when],
                repo, {**env, "GIT_COMMITTER_DATE": when})

        def project(name):
            repo = tmp / "projects" / name
            repo.mkdir(parents=True)
            git(["init", "-q"], repo, env)
            commit(repo, {"web/index.html": f"<html><head></head><body>\n<h1>{name}</h1>\n" + "\n".join(f"<p>{i}</p>" for i in range(20))
                          + "\n</body></html>"}, "init", "2026-11-14T00:00:00Z")
            return repo

        p1, p2, p3 = project("shop"), project("blog"), project("nocommit")
        commit(p1, {"web/index.html": "<html><head></head><body>\n<h1>shop 新版</h1>\n"
                    + "\n".join(f"<p>新 {i}</p>" for i in range(20)) + "\n</body></html>"}, "redesign", "2026-11-15T10:20:00Z")
        commit(p2, {"web/index.html": "<html><head></head><body>\n<h1>blog 新版</h1>\n"
                    + "\n".join(f"<p>改 {i}</p>" for i in range(20)) + "\n</body></html>"}, "redesign", "2026-11-16T09:30:00Z")
        commit(p2, {"web/later.txt": "之後的工作"}, "later", "2026-11-20T09:00:00Z")

        proj = home / ".claude" / "projects" / "x"
        proj.mkdir(parents=True)

        def session(name, cwd, req, t0, t1, skill="unslop", sidechain=False):
            lines = [{"type": "user", "cwd": str(cwd), "timestamp": t0, "isMeta": True, "message": {"content": "<system-reminder>x"}},
                     {"type": "user", "cwd": str(cwd), "timestamp": t0, "isSidechain": sidechain, "message": {"content": req}},
                     {"type": "assistant", "cwd": str(cwd), "timestamp": t1,
                      "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": skill}}]}}]
            p = proj / f"{name}.jsonl"
            p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8")
            end = usage.parse_time(t1)
            os.utime(p, (end, end))

        session("s1", p1 / "web", "把商店首頁重新設計，看起來更專業", "2026-11-15T10:00:00Z", "2026-11-15T10:15:00Z")
        session("s2", p2, "部落格首頁改得好讀一點", "2026-11-16T09:00:00Z", "2026-11-16T09:25:00Z")
        session("s3", p3, "改一下按鈕的樣式就好", "2026-11-17T09:00:00Z", "2026-11-17T09:10:00Z")
        session("s4", tmp / "omnikit-eval" / "x", "實測", "2026-11-17T09:00:00Z", "2026-11-17T09:10:00Z")
        session("s5", p1, "別的工具做的", "2026-11-15T11:00:00Z", "2026-11-15T11:10:00Z", skill="other")
        swap.save(state, [{"id": "fe-1", "agent": "claude", "slot": "fe", "slot_name": "前端", "state": "trial",
                           "started": "2026-11-14", "trial_until": "2026-11-28",
                           "old": {"kind": "skill", "name": "frontend-design", "where": ""},
                           "new": {"tool": "unslop", "name": "unslop", "kind": "skill", "plugin_name": "unslop"}}])

        rc, out = quiet(record, "fe-1", home, state)
        tasks = read_json(folder("fe-1", state) / "tasks.json")["tasks"]
        by = {Path(t["cwd"]).name if Path(t["cwd"]).name != "web" else "shop": t for t in tasks}
        ok(rc == 0 and len(tasks) == 4, f"只記叫用過新工具的對話（4 段，別的工具的不記）：{len(tasks)}")
        ok(by["shop"]["request"] == "把商店首頁重新設計，看起來更專業" and by["shop"]["subdir"] == "web",
           "記下第一個要求（跳過系統提醒）與專案裡的子資料夾")
        ok(by["shop"]["start_commit"] != by["shop"]["end_commit"] and not by["shop"].get("skip"), "開始前與結束時的 commit 不同")
        ok(git(["log", "-1", "--format=%s", by["blog"]["end_commit"]], p2) == "redesign", "結束時的 commit 不算之後的工作")
        ok("沒有新的 commit" in (by["nocommit"].get("skip") or ""), "對話結束沒有 commit：記成沒有成果可以比")
        ok("實測" in (by["x"].get("skip") or ""), "實測的副本不算真實任務")
        rc, _ = quiet(record, "fe-1", home, state)
        ok(len(read_json(folder("fe-1", state) / "tasks.json")["tasks"]) == 4, "再記一次不重複")

        rc, out = quiet(pick, "fe-1", state)
        picks = read_json(folder("fe-1", state) / "picks.json")["picks"]
        ok(rc == 0 and len(picks) == 2 and "沒辦法比" not in out, f"挑兩筆可以比的：{picks}")

        # 不到兩筆
        state2 = tmp / "state2"
        swap.save(state2, [{**swap.load(state)[0], "new": {"tool": "nothing", "name": "nothing", "kind": "skill"}}])
        quiet(record, "fe-1", home, state2)
        rc, out = quiet(pick, "fe-1", state2)
        ok(rc == 1 and "沒辦法比" in out and "不硬湊" in out, "不到兩筆：照實說沒辦法比")
        quiet(result, "fe-1", state2)
        ok("不到 2 筆" in (summary_line("fe-1", state2) or ""), "結果也照實寫沒辦法比")

        skill = tmp / "old-skill"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: frontend-design\n---\n", encoding="utf-8")
        ok(quiet(prepare, "fe-1", state, None)[0] == 1, "沒給舊工具的資料夾：不準備")
        rc, out = quiet(prepare, "fe-1", state, str(skill))
        runs = folder("fe-1", state) / "runs"
        shop = next(runs / t for t in picks if by["shop"]["id"] == t)
        ok(rc == 0 and (shop / "old" / "repo" / ".agents" / "skills" / "frontend-design" / "SKILL.md").is_file()
           and not (shop / "new" / "repo" / ".agents").exists(), "副本：舊工具只放進 old")
        ok("shop 新版" in (shop / "new" / "repo" / "web" / "index.html").read_text(encoding="utf-8")
           and "shop 新版" not in (shop / "base" / "repo" / "web" / "index.html").read_text(encoding="utf-8"),
           "new 是結束時的 commit、base 是開始前的")
        ok(git(["status", "--porcelain"], p1) == "", "真的專案沒有被動到")
        ok(quiet(compare, "fe-1", state)[0] == 1, "還沒重跑就比對：擋下來")

        prompts = []

        def fake(repo, prompt, model):
            prompts.append(prompt)
            f = repo / "web" / "index.html"
            f.write_text(f.read_text(encoding="utf-8").replace("<h1>", "<h1>舊工具 "), encoding="utf-8")
            return {"status": "completed"}

        rc, _ = quiet(rerun, "fe-1", state, executor=fake)
        ok(rc == 0 and len(prompts) == 2 and "frontend-design/SKILL.md" in prompts[0]
           and any("把商店首頁重新設計" in p for p in prompts), "重跑：用舊工具、帶原本的第一個要求")
        rc, out = quiet(compare, "fe-1", state, serve_cmd=f'"{sys.executable}" -m http.server {{port}} --bind 127.0.0.1')
        ok(rc == 0 and "舊工具 " in (shop / "old.patch").read_text(encoding="utf-8")
           and "shop 新版" in (shop / "new.patch").read_text(encoding="utf-8"), "比對：寫出新舊兩份 diff")
        sealed = read_json(shop / "blind" / "sealed.json")
        ok(sealed and sealed["labels"] == ["A", "B", blind.REF_LABEL], "盲選資料夾：新舊兩個蒙起來、原版不蒙")
        spec = read_json(shop / "blind" / "spec.json")
        ok(spec["versions"]["old"]["dir"].endswith(str(Path("old/repo/web"))), "盲選開在任務的子資料夾")

        # 盲選結果彙整
        quiet(result, "fe-1", state)
        ok("還沒選" in summary_line("fe-1", state), "還沒選完：照實寫")
        for i, t in enumerate(picks):
            bf = runs / t / "blind"
            mapping, _ = blind.unseal(bf)
            want = "new" if i == 0 else "old"
            label = next(k for k, v in mapping.items() if v == want)
            quiet(blind.choose, bf, "gray", label)
            quiet(blind.choose, bf, "color", "tie")
            quiet(blind.reveal, bf)
        quiet(result, "fe-1", state)
        line = summary_line("fe-1", state)
        ok(line == "影子比對 2 筆：unslop 勝 1、frontend-design 勝 1、平手 0（以灰階為準）", f"彙整：{line}")
        ok("第一個要求" in read_json(folder("fe-1", state) / "result.json")["caveats"][0], "結果寫明只重跑第一個要求")
        ok(summary_line("nope", state) is None, "沒有比對的替換：沒有結果")

    print(f"\n{'shadow.py 自我測試全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="影子比對：真實任務、舊工具重跑、盲選")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("command", nargs="?", choices=["record", "pick", "prepare", "rerun", "compare", "result", "status"])
    ap.add_argument("sid", nargs="?")
    ap.add_argument("--n", type=int, default=MAX_TASKS)
    ap.add_argument("--old-skill")
    ap.add_argument("--setup")
    ap.add_argument("--subdir")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--serve-cmd")
    ap.add_argument("--port-env")
    ap.add_argument("--fingerprint", default="index.html")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.command or not a.sid:
        ap.error("要給指令與替換 id")
    if a.command == "record":
        return record(a.sid, Path.home(), STATE)
    if a.command == "pick":
        return pick(a.sid, STATE, a.n)
    if a.command == "prepare":
        return prepare(a.sid, STATE, a.old_skill, a.setup, a.subdir)
    if a.command == "rerun":
        return rerun(a.sid, STATE, a.model)
    if a.command == "compare":
        return compare(a.sid, STATE, a.serve_cmd, a.port_env, a.fingerprint)
    if a.command == "result":
        return result(a.sid, STATE)
    return status(a.sid, STATE)


if __name__ == "__main__":
    sys.exit(main())
