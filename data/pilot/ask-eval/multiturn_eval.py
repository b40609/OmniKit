#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""問法庫（omnikit-ask）多輪評測：小型壞專案 + 模擬使用者。

agy_eval.py 量的是單輪、工作資料夾是空的、評分者看「回覆有沒有照好的做法」。這支改量實際結果：
每題是一個很小的真專案（multiturn/<題目>/project），有可重現的 bug、亂掉的畫面或需求不清；
模擬使用者只知道處境與想要的結果，依 agent 的回覆回話；每輪 agent 回完就跑一次隱藏的自動檢查
（multiturn/<題目>/check.py，agent 看不到），通過就結束。

記錄：最後有沒有修好、agent 回了幾輪、使用者糾正了幾次、問法庫有沒有被叫用。

組別（--arms）沿用 agy_eval.py：
- global：工作資料夾不放 skill，全域照平常（使用者實際裝好的樣子）。
- without：全域 skill 用 overlay 拿掉 omnikit-ask、ok、ok-ask。
- with：工作資料夾另放一份 skill（多數情況用不到）。

模擬使用者：本機 Claude Code 的 Sonnet（`claude -p`，關掉工具、MCP 與設定檔）。跟被測的 Gemini 不同家，
也不吃 Antigravity 帳號的額度；跟 agy_eval.py 的評分者用同一套呼叫方式。
每次回話輸出一行 JSON：message 與 kind（correction 糾正、answer 回答或補資訊、go 請它繼續、stop 放棄）。
使用者「試用」的結果來自 check.py 印的 symptom（使用者看得到的症狀，不含原因與解法）；只有 agent
說改好或要使用者試時，模擬使用者才會用到它。

每題的資料夾：
- case.md：front matter（base：對應 cases/ 的題目、max_turns），段落「開場」「處境」「想要的結果」「細節」。
- project/：複製到暫存資料夾、git init 後當工作資料夾。
- check.py：`python check.py <工作資料夾>`，最後一行印 JSON {"pass", "symptom", "detail"}；不寫入工作資料夾。
- reference/：參考修法（只蓋過部分檔案），--selftest 用它確認 check.py 對壞專案判失敗、對修好的判通過。

用法：
  uv run data/pilot/ask-eval/multiturn_eval.py --selftest
  uv run data/pilot/ask-eval/multiturn_eval.py --list
  uv run data/pilot/ask-eval/multiturn_eval.py --account kai --model gemini-3.8-flash-high --arms global,without -j 3
  uv run data/pilot/ask-eval/multiturn_eval.py --case debug-recur --runs 1 --arms global
  uv run data/pilot/ask-eval/multiturn_eval.py --out <結果資料夾>     # 接著跑，已完成的沿用
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE / "multiturn"
sys.path.insert(0, str(HERE))
import agy_eval as base  # noqa: E402  共用 ACP 用戶端、帳號資料夾、沒它組的 overlay、保留題清單

MAX_REPLY_FOR_SIM = 3500


# ---------- cases ----------

def load_case(d: pathlib.Path) -> dict:
    front, body = base.split_front(d / "case.md")
    sections, cur = {}, None
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1)
            sections[cur] = []
        elif cur:
            sections[cur].append(line)
    sec = {k: "\n".join(v).strip() for k, v in sections.items()}
    missing = [k for k in ("開場", "處境", "想要的結果", "細節") if k not in sec]
    if missing:
        sys.exit(f"{d.name}/case.md 少了段落：{missing}")
    return {"name": d.name, "dir": d, "base": front.get("base", d.name),
            "category": d.name.split("-")[0], "max_turns": int(front.get("max_turns", 6)),
            "opener": sec["開場"], "situation": sec["處境"], "goal": sec["想要的結果"], "facts": sec["細節"]}


def load_cases(names=None) -> list[dict]:
    cases = [load_case(d) for d in sorted(ROOT.iterdir()) if d.is_dir() and not d.name.startswith("_")]
    if names:
        cases = [c for c in cases if c["name"] in names]
        if len(cases) != len(set(names)):
            sys.exit(f"有題目找不到：{sorted(set(names) - {c['name'] for c in cases})}")
    held = base.load_holdout()
    bad = [c["name"] for c in cases if c["base"] in held]
    if bad:
        sys.exit(f"這些題目的 base 是保留題，不該拿來做多輪題：{bad}")
    return cases


def make_workspace(case, rules: pathlib.Path | None, arm: str) -> pathlib.Path:
    ws = pathlib.Path(tempfile.mkdtemp(prefix=f"ask-mt-{case['name']}-"))
    shutil.copytree(case["dir"] / "project", ws, dirs_exist_ok=True)
    if rules and rules.exists():
        shutil.copyfile(rules, ws / "AGENTS.md")
    if arm == "with":
        shutil.copytree(base.SKILL, ws / ".agents" / "skills" / "omnikit-ask")
    git = ["git", "-c", "user.name=dev", "-c", "user.email=dev@example.com", "-c", "core.autocrlf=false"]
    subprocess.run(git + ["init", "-q"], cwd=ws, check=True)
    subprocess.run(git + ["add", "-A"], cwd=ws, check=True)
    subprocess.run(git + ["commit", "-q", "-m", "目前的版本"], cwd=ws, check=True)
    return ws


def run_check(case, ws: pathlib.Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    try:
        p = subprocess.run([sys.executable, "-B", str(case["dir"] / "check.py"), str(ws)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=env, timeout=180)
    except subprocess.TimeoutExpired:
        return {"pass": False, "symptom": "跑起來卡住沒反應", "detail": "check 逾時"}
    lines = [x for x in (p.stdout or "").strip().splitlines() if x.strip()]
    try:
        out = json.loads(lines[-1])
    except (IndexError, ValueError):
        return {"pass": False, "symptom": "跑起來直接出錯", "detail": f"check 沒有 JSON：{(p.stderr or p.stdout)[-300:]}"}
    out["pass"] = bool(out.get("pass"))
    return out


# ---------- simulated user ----------

SIM = """你在扮演一位正在用 coding agent 的使用者，跟 agent 在聊天室裡對話。agent 在你的專案資料夾裡工作。

## 你的處境
{situation}

## 你心裡想要的結果（不要一次整段講出來；agent 問到、或它做的跟你要的不一樣時，才講相關的那一點）
{goal}

## 你知道、但 agent 沒問就不會主動講的細節
{facts}

## 規則
- 你不會寫程式，也不知道問題出在哪一行；不要提出解法、檔名、函式名稱或程式碼。
- 每次回話 1 到 3 句，像真人在聊天室打字，用繁體中文。
- agent 問你問題：只回答它問到的那幾點，照上面你知道的回答；它沒問到的要求不要順便講出來，
  也不要把「想要的結果」整份列給它。上面沒寫的就說不知道或「你決定」。
- agent 給你選項或預設值：只針對它列的項目回答；它的預設跟你要的一樣就同意，不一樣才說你要的那一點。
- agent 說改好了、或請你試試看：照「你剛剛試的結果」回報。沒好就描述你看到的症狀，不要猜原因。
  agent 沒說改好、也沒請你試的時候，不要拿試的結果出來講。
- agent 只給建議、教你怎麼問、或列計畫沒動手：建議合理就照做（補上它要的資訊），然後請它直接動手改。
- agent 做了你不要的事、方向錯、或忽略你講過的話：直接糾正。
- 已經沒救、或 agent 一直要你做你做不到的事，才放棄。
- 你最多還能回 {left} 次話。

## 你剛剛試的結果
{tried}

## 到目前為止的對話
{transcript}

只輸出一行 JSON，不要其他文字：{{"message": "你要回的話", "kind": "correction 或 answer 或 go 或 stop"}}
kind：correction＝指出 agent 做錯、沒修好、方向不對或忽略你說過的話；answer＝回答 agent 的問題或補它要的資訊；
go＝同意它的計畫、請它繼續或動手；stop＝放棄。同時有糾正與回答時選 correction。"""


def claude_env():
    return {k: v for k, v in os.environ.items()
            if not (k.startswith(("ANTHROPIC_", "CLAUDE_")) or k == "CLAUDECODE")}


def simulate(case, transcript, tried, left, model, timeout=300) -> dict:
    lines = []
    for who, text in transcript:
        if who == "agent" and len(text) > MAX_REPLY_FOR_SIM:
            text = text[:MAX_REPLY_FOR_SIM] + "\n…（後面省略）"
        lines.append(f"[{'你' if who == 'user' else 'agent'}]\n{text}")
    prompt = SIM.format(situation=case["situation"], goal=case["goal"], facts=case["facts"], left=left,
                        tried=tried, transcript="\n\n".join(lines))
    cmd = [shutil.which("claude") or "claude", "-p", "--model", model, "--system-prompt",
           "你在扮演軟體專案的使用者，只輸出要求的 JSON。", "--tools", "", "--strict-mcp-config",
           "--setting-sources", "", "--no-session-persistence", "--max-turns", "1"]
    last = ""
    for _ in range(2):
        with tempfile.TemporaryDirectory(prefix="ask-sim-") as cwd:
            try:
                p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", cwd=cwd, env=claude_env(), timeout=timeout)
            except subprocess.TimeoutExpired:
                last = "模擬使用者逾時"
                continue
        m = re.search(r"\{.*\"message\".*\}", p.stdout or "", re.S)
        if m:
            try:
                data = json.loads(m.group(0))
                kind = str(data.get("kind", "")).strip().lower()
                if kind not in ("correction", "answer", "go", "stop"):
                    kind = "go"
                return {"message": str(data.get("message", "")).strip(), "kind": kind}
            except ValueError:
                pass
        last = (p.stderr or p.stdout or "")[-300:]
    return {"message": "", "kind": "error", "error": last or "模擬使用者沒有輸出"}


# ---------- one conversation ----------

def fired_tools(tools) -> bool:
    return base.fired({"tools": tools})


def converse(args, gemini_dir, case, arm, idx, out_dir) -> dict:
    if base.STOP.is_set():
        raise base.Skipped("額度用完，略過")
    rules = None if args.no_rules else pathlib.Path(args.rules)
    ws = make_workspace(case, rules, arm)
    acp = base.Acp(gemini_dir, ws)
    run = {"case": case["name"], "base": case["base"], "category": case["category"], "arm": arm, "run": idx,
           "account": args.account, "agent_model": args.model, "sim_model": args.sim_model,
           "max_turns": case["max_turns"], "turns": [], "fixed": False, "fixed_at": None, "error": None,
           "quota": False, "outcome": None}
    started = time.monotonic()
    buf = {"text": [], "tools": []}

    def on_update(msg):
        if msg.get("method") != "session/update":
            return
        update = msg["params"].get("update", {})
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            buf["text"].append((update.get("content") or {}).get("text", ""))
        elif kind in ("tool_call", "tool_call_update"):
            buf["tools"].append({k: update.get(k) for k in ("toolCallId", "title", "kind", "status", "rawInput")})

    transcript = []
    try:
        acp.call("initialize", {"protocolVersion": 1, "clientCapabilities": {
            "fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}})
        acp.call("authenticate", {"methodId": "oauth-personal"}, timeout=120)
        sid = acp.call("session/new", {"cwd": str(ws), "mcpServers": []})["sessionId"]
        run["model_applied"] = base.set_model(acp, sid, args.model)
        message, kind = case["opener"], "opener"
        for turn in range(1, case["max_turns"] + 1):
            buf["text"], buf["tools"] = [], []
            t0 = time.monotonic()
            res = acp.call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": message}]},
                           on_update, args.timeout)
            reply = "".join(buf["text"])
            transcript += [("user", message), ("agent", reply)]
            check = run_check(case, ws)
            quota = len(reply) < 600 and bool(base.QUOTA_RE.search(reply))
            run["turns"].append({"turn": turn, "user": message, "user_kind": kind, "reply": reply,
                                 "tools": len(buf["tools"]), "fired": fired_tools(buf["tools"]),
                                 "tool_titles": [t.get("title") for t in buf["tools"] if t.get("title")][:60],
                                 "stop": res.get("stopReason"), "seconds": round(time.monotonic() - t0),
                                 "check": check})
            if quota:
                run.update(error=f"額度用完：{reply.strip()[:160]}", quota=True)
                break
            if check["pass"]:
                run.update(fixed=True, fixed_at=turn, outcome="fixed")
                break
            if turn == case["max_turns"]:
                run["outcome"] = "out_of_turns"
                break
            tried = (f"你照平常的方式用了一下：{check.get('symptom') or '還是不對'}" if check.get("symptom")
                     else "你照平常的方式用了一下：還是不對")
            sim = simulate(case, transcript, tried, case["max_turns"] - turn, args.sim_model)
            if sim["kind"] == "error":
                run["error"] = f"模擬使用者出錯：{sim.get('error', '')[:200]}"
                break
            if sim["kind"] == "stop":
                run["turns"][-1]["sim_stop"] = sim["message"]
                run["outcome"] = "gave_up"
                break
            message, kind = sim["message"], sim["kind"]
    except base.AcpError as e:
        run["error"] = str(e)
        run["quota"] = bool(base.QUOTA_RE.search(str(e)))
    finally:
        acp.close()
        shutil.rmtree(ws, ignore_errors=True)
    run["fired"] = any(t["fired"] for t in run["turns"])
    run["fired_first"] = bool(run["turns"] and run["turns"][0]["fired"])
    run["agent_turns"] = len(run["turns"])
    run["user_turns"] = sum(1 for t in run["turns"] if t["user_kind"] != "opener")
    run["corrections"] = sum(1 for t in run["turns"] if t["user_kind"] == "correction")
    run["answers"] = sum(1 for t in run["turns"] if t["user_kind"] == "answer")
    run["seconds"] = round(time.monotonic() - started)
    base.note_quota(run["quota"])
    (out_dir / f"{case['name']}.{arm}.{idx}.json").write_text(json.dumps(run, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
    return run


# ---------- summary ----------

def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def arm_stats(runs):
    ok = [r for r in runs if not r["error"]]
    fixed = [r for r in ok if r["fixed"]]
    return {"runs": len(ok), "errors": len(runs) - len(ok), "fixed": len(fixed),
            "fix_rate": round(len(fixed) / len(ok), 3) if ok else None,
            "agent_turns": mean([r["agent_turns"] for r in ok]),
            "turns_when_fixed": mean([r["fixed_at"] for r in fixed]),
            "corrections": mean([r["corrections"] for r in ok]),
            "user_turns": mean([r["user_turns"] for r in ok]),
            "fired": sum(r["fired"] for r in ok), "fired_first": sum(r["fired_first"] for r in ok)}


def summarize(results, cases, arms):
    rows, by_cat = [], {}
    for c in cases:
        row = {"case": c["name"], "category": c["category"]}
        for arm in arms:
            rs = [r for r in results if r["case"] == c["name"] and r["arm"] == arm]
            st = arm_stats(rs)
            st["all_fixed"] = bool(st["runs"]) and st["fixed"] == st["runs"]
            row[arm] = st
        rows.append(row)
    overall = {}
    for arm in arms:
        rs = [r for r in results if r["arm"] == arm]
        st = arm_stats(rs)
        cases_run = [row for row in rows if row[arm]["runs"]]
        # 每題 k 次都修好才算（tau-bench 的 pass^k）
        st["pass_all_k"] = (f"{sum(row[arm]['all_fixed'] for row in cases_run)}/{len(cases_run)}")
        overall[arm] = st
        for row in rows:
            by_cat.setdefault(row["category"], {}).setdefault(arm, []).extend(
                [r for r in rs if r["case"] == row["case"]])
    cats = {cat: {arm: arm_stats(v) for arm, v in d.items()} for cat, d in sorted(by_cat.items())}
    return {"overall": overall, "by_category": cats, "rows": rows}


def fmt(v):
    return "-" if v is None else str(v)


def print_summary(s, arms):
    print("\n### 整體")
    print("| 組 | 對話 | 修好 | 修好率 | 每題 k 次全修好 | 平均 agent 輪數 | 修好時第幾輪 | 平均糾正 | 平均使用者回話 | 叫用 | 錯誤 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for arm in arms:
        o = s["overall"][arm]
        print(f"| {arm} | {o['runs']} | {o['fixed']} | {fmt(o['fix_rate'])} | {o['pass_all_k']} | {fmt(o['agent_turns'])} "
              f"| {fmt(o['turns_when_fixed'])} | {fmt(o['corrections'])} | {fmt(o['user_turns'])} | {o['fired']} | {o['errors']} |")
    print("\n### 每題（修好次數/對話數，平均輪數，平均糾正）")
    print("| 題目 | " + " | ".join(arms) + " |")
    print("|---|" + "---|" * len(arms))
    for row in s["rows"]:
        cells = [f"{row[a]['fixed']}/{row[a]['runs']}，{fmt(row[a]['agent_turns'])} 輪，糾正 {fmt(row[a]['corrections'])}"
                 + (f"，叫用 {row[a]['fired']}" if row[a]["fired"] else "") for a in arms]
        print(f"| {row['case']} | " + " | ".join(cells) + " |")
    print("\n### 分類")
    print("| 分類 | " + " | ".join(arms) + " |")
    print("|---|" + "---|" * len(arms))
    for cat, d in s["by_category"].items():
        cells = [f"{d[a]['fixed']}/{d[a]['runs']}，{fmt(d[a]['agent_turns'])} 輪，糾正 {fmt(d[a]['corrections'])}"
                 if a in d else "-" for a in arms]
        print(f"| {cat} | " + " | ".join(cells) + " |")


# ---------- selftest ----------

def selftest(cases) -> int:
    """壞專案必須判失敗、蓋上 reference/ 必須判通過，而且 check 不能在工作資料夾留下檔案。"""
    bad = 0
    for c in cases:
        with tempfile.TemporaryDirectory(prefix="ask-mt-self-") as tmp:
            ws = pathlib.Path(tmp) / "ws"
            shutil.copytree(c["dir"] / "project", ws)
            before = sorted(str(p.relative_to(ws)) for p in ws.rglob("*"))
            broken = run_check(c, ws)
            after = sorted(str(p.relative_to(ws)) for p in ws.rglob("*"))
            shutil.copytree(c["dir"] / "reference", ws, dirs_exist_ok=True)
            fixed = run_check(c, ws)
        ok = (not broken["pass"]) and fixed["pass"] and before == after and bool(broken.get("symptom"))
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {c['name']}: 壞的 pass={broken['pass']}（{broken.get('symptom')}）"
              f"；參考修法 pass={fixed['pass']}{'' if fixed['pass'] else '（' + str(fixed.get('detail')) + '）'}"
              f"{'' if before == after else '；check 在工作資料夾留下檔案'}")
    print(f"\n{len(cases) - bad}/{len(cases)} 題的 check 正常")
    return 1 if bad else 0


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", default="kai", help="ryan、ava、kai，或 T3 的實例 id")
    ap.add_argument("--model", default="gemini-3.8-flash-high")
    ap.add_argument("--sim-model", default="sonnet", help="模擬使用者用的 Claude 模型（claude -p --model）")
    ap.add_argument("--arms", default="global,without", help="global、without、with，逗號分隔")
    ap.add_argument("--case", action="append", help="只跑這題（可重複）")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("-j", "--jobs", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=900, help="每輪 agent 回覆的上限秒數")
    ap.add_argument("--rules", default=str(base.DEFAULT_RULES), help="放進工作資料夾當 AGENTS.md 的規則檔")
    ap.add_argument("--no-rules", action="store_true")
    ap.add_argument("--out", help="結果資料夾；給已經有結果的資料夾就接著跑")
    ap.add_argument("--summary", help="另外把摘要（不含對話全文）寫到這個檔")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="只檢查每題的 check.py（不開對話、不花額度）")
    args = ap.parse_args()

    cases = load_cases(args.case)
    if args.selftest:
        sys.exit(selftest(cases))
    if args.list:
        for c in cases:
            print(f"{c['category']}\t{c['name']}\tbase={c['base']}\tmax_turns={c['max_turns']}")
        print(f"{len(cases)} 題")
        return
    arms = args.arms.split(",")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = (pathlib.Path(args.out) if args.out else pathlib.Path(tempfile.gettempdir())
               / f"ask-multiturn-{stamp}-{args.account}-{args.model}")
    out_dir.mkdir(parents=True, exist_ok=True)

    results, todo = [], []
    for c in cases:
        for arm in arms:
            for i in range(1, args.runs + 1):
                f = out_dir / f"{c['name']}.{arm}.{i}.json"
                old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
                if old and not old["error"]:
                    results.append(old)
                else:
                    todo.append((c, arm, i))
    gemini_dirs, made = {}, []
    gemini_dirs["with"] = gemini_dirs["global"] = base.profile_dir(args.account)
    if "without" in arms:
        gemini_dirs["without"], made = base.without_skill_dir(gemini_dirs["global"])
    print(f"{len(todo)} 次新對話、{len(results)} 次沿用：{len(cases)} 題 × {args.arms} × {args.runs} 次；"
          f"帳號 {args.account}、模型 {args.model}、模擬使用者 {args.sim_model}；結果寫到 {out_dir}", flush=True)
    lock = threading.Lock()
    skipped = 0
    try:
        with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(converse, args, gemini_dirs[arm], c, arm, i, out_dir): (c["name"], arm, i)
                       for c, arm, i in todo}
            for fut in cf.as_completed(futures):
                name, arm, i = futures[fut]
                try:
                    r = fut.result()
                except base.Skipped:
                    skipped += 1
                    continue
                except Exception as e:  # noqa: BLE001 - keep the batch going
                    print(f"  {name} {arm} #{i}: 例外 {e!r}", flush=True)
                    continue
                with lock:
                    results.append(r)
                kinds = ",".join(t["user_kind"] for t in r["turns"][1:])
                print(f"  [{len(results)}] {name} {arm} #{i}: "
                      f"{'修好' if r['fixed'] else r['outcome'] or '未完'} 第 {r['fixed_at'] or r['agent_turns']} 輪；"
                      f"使用者 [{kinds}] 叫用 {r['fired']} {r['seconds']}s"
                      f"{' 錯誤：' + r['error'][:120] if r['error'] else ''}", flush=True)
    finally:
        base.drop_dir(made)

    s = summarize(results, cases, arms)
    errors = sum(1 for r in results if r["error"])
    summary = {"kind": "multiturn", "arms": arms, "account": args.account, "model": args.model,
               "sim_model": args.sim_model, "runs_per_case": args.runs,
               "finished": dt.datetime.now().isoformat(timespec="seconds"), "conversations": len(results),
               "errors": errors, "skipped": skipped, "stopped_on_quota": base.STOP.is_set(),
               "rules": None if args.no_rules else args.rules, **s,
               "runs": [{k: r[k] for k in ("case", "arm", "run", "fixed", "fixed_at", "outcome", "agent_turns",
                                           "user_turns", "corrections", "answers", "fired", "fired_first",
                                           "seconds", "error")}
                        | {"user_kinds": [t["user_kind"] for t in r["turns"]],
                           "symptoms": [t["check"].get("symptom") for t in r["turns"]]}
                        for r in sorted(results, key=lambda r: (r["case"], r["arm"], r["run"]))]}
    text = json.dumps(summary, ensure_ascii=False, indent=1)
    (out_dir / "summary.json").write_text(text, encoding="utf-8")
    if args.summary:
        pathlib.Path(args.summary).write_text(text, encoding="utf-8")
    print_summary(s, arms)
    if errors or skipped:
        print(f"\n錯誤 {errors} 次、略過 {skipped} 次；用同一個 --out 再跑一次會只補這些")
    print(f"\n結果：{out_dir}")


if __name__ == "__main__":
    main()
