#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""問法庫（omnikit-ask）在 Antigravity 上的有它與沒它對照評測。

跟 run.ps1（Claude Code 的 `claude plugin eval`）用同一批題目（cases/），改由 `agy acp` 跑。
帳號沿用 T3 Code 替每個 Antigravity 實例存好的登入資料夾（不讀、不複製金鑰），用 --account 指定。
注意：2026-11-17 實測指定 ava 時對話檔寫進 ava 的資料夾，但額度仍算在本機預設帳號（ryan）上，
--account 目前不能當成省額度的方法。

每題兩組：
- 有它：工作資料夾放 `.agents/skills/omnikit-ask`（Antigravity 的專案層 skill）。
- 沒它：同樣的資料夾，沒有那個 skill。
兩組都放一份 `AGENTS.md`（預設是 ~/.gemini/GEMINI.md，也就是平常的 OmniKit 規則）。

評分：每個 llm 評分項由兩位評分者各自判 PASS 或 FAIL，加權平均成 0 到 1 分。
- 主要評分者：本機 Claude Code 的 Sonnet（`claude -p`），跟 run.ps1 的評分者同一個，三組結果才能比；
  也跟被測的 Gemini 不同家（同家評分會偏袒自己，arXiv:2604.06996）。
- 第二位：Gemini Hydrogen，只用來算兩位的一致率。
評分出錯（例如額度用完）記為沒評到，不算進分數；用 --rejudge 補評。
是否叫用問法庫看工具呼叫裡有沒有 omnikit-ask。

用法：
  uv run data/pilot/ask-eval/agy_eval.py --account ryan --model gemini-4-hydrogen-high
  uv run data/pilot/ask-eval/agy_eval.py --account ava --model gemini-3.8-flash-high --case ux-merge --runs 1
  uv run data/pilot/ask-eval/agy_eval.py --out <結果資料夾> --rejudge
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import pathlib
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
CASES = HERE / "cases"
SKILL = REPO / "engine" / "skills" / "omnikit-ask"
T3_PROFILES = pathlib.Path.home() / ".t3" / "userdata" / "providers" / "antigravity"
ACCOUNTS = {"ryan": "antigravity", "ava": "antigravity_ava", "kai": "antigravity_kai"}
DEFAULT_RULES = pathlib.Path.home() / ".gemini" / "GEMINI.md"


def profile_dir(account: str) -> pathlib.Path:
    instance = ACCOUNTS.get(account, account)
    path = T3_PROFILES / hashlib.sha256(instance.encode()).hexdigest()
    if not (path / "antigravity-acp").is_dir():
        sys.exit(f"找不到 {account} 的 T3 登入資料夾：{path}")
    return path


# ---------- ACP client ----------

class AcpError(RuntimeError):
    pass


class Acp:
    """Minimal ACP (JSON-RPC over stdio) client for `agy acp`."""

    def __init__(self, gemini_dir: pathlib.Path, cwd: pathlib.Path):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE"))}
        env.update(GEMINI_HOME=str(gemini_dir), AGY_ACP_FORCE_FILE_STORAGE="1",
                   BROWSER="cmd.exe /c rem", PYTHONUTF8="1")
        self.proc = subprocess.Popen(
            ["agy", "acp", "--gemini-dir", str(gemini_dir), "--app-data-dir", "antigravity-acp",
             "--dangerously-skip-permissions"],
            cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.inbox: queue.Queue = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            try:
                self.inbox.put(json.loads(line))
            except ValueError:
                pass
        self.inbox.put(None)

    def _send(self, obj):
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def call(self, method, params, on_update=None, timeout=90):
        self.next_id += 1
        my_id = self.next_id
        self._send({"jsonrpc": "2.0", "id": my_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise AcpError(f"{method} 逾時（{timeout} 秒）")
            try:
                msg = self.inbox.get(timeout=left)
            except queue.Empty:
                raise AcpError(f"{method} 逾時（{timeout} 秒）") from None
            if msg is None:
                raise AcpError("agy acp 提前結束")
            if "method" in msg and "id" in msg:
                self._answer(msg)
            elif "method" in msg:
                if on_update:
                    on_update(msg)
            elif msg.get("id") == my_id:
                if "error" in msg:
                    raise AcpError(json.dumps(msg["error"], ensure_ascii=False))
                return msg.get("result") or {}

    def _answer(self, msg):
        if msg["method"] == "session/request_permission":
            options = msg["params"].get("options", [])
            pick = next((o for o in options if str(o.get("kind", "")).startswith("allow")), None)
            result = ({"outcome": {"outcome": "selected", "optionId": pick["optionId"]}} if pick
                      else {"outcome": {"outcome": "cancelled"}})
            self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        else:
            self._send({"jsonrpc": "2.0", "id": msg["id"],
                        "error": {"code": -32601, "message": "not supported by eval client"}})

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def set_model(acp: Acp, session_id: str, model: str) -> str:
    try:
        acp.call("session/set_model", {"sessionId": session_id, "modelId": model})
        return f"set_model {model}"
    except AcpError:
        pass
    base, _, level = model.rpartition("-")
    if level not in ("low", "medium", "high", "xhigh"):
        base, level = model, ""
    acp.call("session/set_config_option", {"sessionId": session_id, "configId": "model", "value": base})
    if level:
        acp.call("session/set_config_option", {"sessionId": session_id, "configId": "thought_level", "value": level})
    return f"config {base} {level}"


def run_turn(gemini_dir, cwd, model, prompt, timeout):
    acp = Acp(gemini_dir, cwd)
    text, tools = [], []

    def on_update(msg):
        if msg.get("method") != "session/update":
            return
        update = msg["params"].get("update", {})
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            content = update.get("content") or {}
            text.append(content.get("text", ""))
        elif kind in ("tool_call", "tool_call_update"):
            tools.append({k: update.get(k) for k in ("toolCallId", "title", "kind", "status", "rawInput", "locations")})

    started = time.monotonic()
    try:
        acp.call("initialize", {"protocolVersion": 1, "clientCapabilities": {
            "fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}})
        # 跟 T3 一樣明確登入；少了這步，agy 會退回本機預設帳號（2026-11-17 實測：ava 的額度沒動、ryan 的漲了）
        acp.call("authenticate", {"methodId": "oauth-personal"}, timeout=120)
        session = acp.call("session/new", {"cwd": str(cwd), "mcpServers": []})
        sid = session["sessionId"]
        applied = set_model(acp, sid, model)
        result = acp.call("session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": prompt}]},
                          on_update, timeout)
        return {"reply": "".join(text), "tools": tools, "stop": result.get("stopReason"),
                "meta": result.get("_meta"), "model": applied, "seconds": round(time.monotonic() - started),
                "error": None}
    except AcpError as e:
        return {"reply": "".join(text), "tools": tools, "stop": None, "meta": None, "model": model,
                "seconds": round(time.monotonic() - started), "error": str(e)}
    finally:
        acp.close()


# ---------- cases ----------

def split_front(path: pathlib.Path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.S)
    if not m:
        return {}, raw.strip()
    front = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            front[k.strip()] = v.strip().strip("'\"")
    return front, m.group(2).strip()


def load_cases(names):
    cases = []
    for d in sorted(p for p in CASES.iterdir() if p.is_dir()):
        if names and d.name not in names:
            continue
        _, prompt = split_front(d / "prompt.md")
        graders = []
        for g in sorted((d / "graders").glob("*.md")):
            front, body = split_front(g)
            if front.get("type") == "llm":
                graders.append({"name": g.stem, "weight": float(front.get("weight", 1)), "rubric": body})
        cases.append({"name": d.name, "prompt": prompt, "graders": graders})
    if names and len(cases) != len(set(names)):
        sys.exit(f"有題目找不到：{sorted(set(names) - {c['name'] for c in cases})}")
    return cases



# ---------- judge ----------

JUDGE = """你是評分者。只根據評分標準判斷 agent 的回覆，不要用任何工具，不要讀檔。

## 評分標準
{rubric}

## 使用者的訊息
{prompt}

## agent 的回覆
{reply}

只輸出一行 JSON，不要其他文字：{{"verdict": "PASS" 或 "FAIL", "reason": "一句理由"}}"""


def parse_verdict(text, error=None):
    m = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", text or "", re.S)
    if not m:
        return {"verdict": "ERROR", "reason": (error or (text or "")[:200] or "沒有輸出")}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        v = re.search(r'"verdict"\s*:\s*"(PASS|FAIL)"', m.group(0))
        return {"verdict": v.group(1) if v else "ERROR", "reason": m.group(0)[:200]}
    verdict = str(data.get("verdict", "")).upper()
    return {"verdict": verdict if verdict in ("PASS", "FAIL") else "ERROR", "reason": data.get("reason", "")}


def judge_once(spec: str, text: str, timeout=300):
    """spec：`claude:<模型>` 用本機 Claude Code（claude -p）；`agy:<帳號>/<模型>` 用 Antigravity。"""
    kind, _, target = spec.partition(":")
    with tempfile.TemporaryDirectory(prefix="ask-judge-") as cwd:
        if kind == "claude":
            env = {k: v for k, v in os.environ.items()
                   if not (k.startswith(("ANTHROPIC_", "CLAUDE_")) or k == "CLAUDECODE")}
            try:
                p = subprocess.run([shutil.which("claude") or "claude", "-p", "--model", target, "--max-turns", "1"],
                                   input=text, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   cwd=cwd, env=env, timeout=timeout)
            except subprocess.TimeoutExpired:
                return {"verdict": "ERROR", "reason": "逾時"}
            return parse_verdict(p.stdout, (p.stderr or "")[-200:] or f"exit {p.returncode}")
        if kind == "agy":
            account, _, model = target.partition("/")
            out = run_turn(profile_dir(account), pathlib.Path(cwd), model, text, timeout)
            return parse_verdict(out["reply"], out["error"])
    sys.exit(f"不認得的評分者：{spec}（要用 claude:<模型> 或 agy:<帳號>/<模型>）")


def score_of(grades: dict, case) -> float | None:
    total = got = 0.0
    for g in case["graders"]:
        ok = grades.get(g["name"], {}).get("pass")
        if ok is None:
            return None
        total += g["weight"]
        got += g["weight"] if ok else 0
    return round(got / total, 3) if total else None


def judge_run(run, case, judges, votes):
    """每位評分者各自評每個評分項；已經有有效結果的不重評。評分出錯的記 None，不算進分數。"""
    grades = run.get("grades") or {}
    if any("pass" in v for v in grades.values() if isinstance(v, dict)):
        grades = {}  # 舊格式（單一評分者），整份重評
    for spec in judges:
        per = grades.setdefault(spec, {})
        for g in case["graders"]:
            if per.get(g["name"], {}).get("pass") is not None:
                continue
            if not run["reply"].strip():
                verdicts = [{"verdict": "FAIL", "reason": "沒有回覆"}]
            else:
                text = JUDGE.format(rubric=g["rubric"], prompt=case["prompt"], reply=run["reply"])
                verdicts = [judge_once(spec, text) for _ in range(votes)]
            valid = [v for v in verdicts if v["verdict"] in ("PASS", "FAIL")]
            ok = (sum(v["verdict"] == "PASS" for v in valid) * 2 > len(valid)) if valid else None
            per[g["name"]] = {"pass": ok, "votes": verdicts}
    run["grades"] = grades
    run["scores"] = {spec: score_of(grades.get(spec, {}), case) for spec in judges}
    run.pop("score", None)
    return run


# ---------- main ----------

def make_workspace(arm: str, rules: pathlib.Path | None) -> pathlib.Path:
    ws = pathlib.Path(tempfile.mkdtemp(prefix=f"ask-{arm}-"))
    if rules and rules.exists():
        shutil.copyfile(rules, ws / "AGENTS.md")
    if arm == "with":
        shutil.copytree(SKILL, ws / ".agents" / "skills" / "omnikit-ask")
    return ws


def fired(run) -> bool:
    return "omnikit-ask" in json.dumps(run["tools"], ensure_ascii=False)


def save(run, out_dir):
    (out_dir / f"{run['case']}.{run['arm']}.{run['run']}.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")


def agent_job(args, gemini_dir, case, arm, idx, out_dir):
    ws = make_workspace(arm, None if args.no_rules else pathlib.Path(args.rules))
    try:
        run = run_turn(gemini_dir, ws, args.model, case["prompt"], args.timeout)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    run.update(case=case["name"], arm=arm, run=idx, fired=fired(run), account=args.account, agent_model=args.model)
    save(run, out_dir)
    judge_run(run, case, args.judge, args.votes)
    save(run, out_dir)
    return run


def judge_job(args, case, run, out_dir):
    judge_run(run, case, args.judge, args.votes)
    save(run, out_dir)
    return run


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def summarize(results, cases, judges):
    out = {}
    for spec in judges:
        rows = []
        for c in cases:
            row = {"case": c["name"]}
            for arm in ("with", "without"):
                runs = [r for r in results if r["case"] == c["name"] and r["arm"] == arm]
                scores = [r.get("scores", {}).get(spec) for r in runs]
                row[arm] = mean(scores)
                row[f"{arm}_fired"] = f"{sum(r['fired'] for r in runs)}/{len(runs)}"
                row[f"{arm}_unscored"] = sum(1 for s in scores if s is None)
                row[f"{arm}_errors"] = sum(1 for r in runs if r["error"])
            row["delta"] = (round(row["with"] - row["without"], 3)
                            if row["with"] is not None and row["without"] is not None else None)
            rows.append(row)
        valid = [r for r in rows if r["delta"] is not None]
        out[spec] = {"mean_with": mean([r["with"] for r in valid]), "mean_without": mean([r["without"] for r in valid]),
                     "mean_delta": mean([r["delta"] for r in valid]), "rows": rows}
    agree = None
    if len(judges) >= 2:
        same = total = 0
        for r in results:
            a, b = r.get("grades", {}).get(judges[0], {}), r.get("grades", {}).get(judges[1], {})
            for name, ga in a.items():
                gb = b.get(name, {})
                if ga.get("pass") is not None and gb.get("pass") is not None:
                    total += 1
                    same += ga["pass"] == gb["pass"]
        agree = {"pairs": total, "same": same, "rate": round(same / total, 3) if total else None}
    return out, agree


def print_table(spec, s):
    print(f"\n### 評分者 {spec}")
    print("| 題目 | 有它 | 沒它 | 差距 | 有它時叫用 | 沒它時叫用 | 沒評到 | 錯誤 |")
    print("|---|---|---|---|---|---|---|---|")
    for r in s["rows"]:
        print(f"| {r['case']} | {r['with']} | {r['without']} | {r['delta']} | {r['with_fired']} | {r['without_fired']} "
              f"| {r['with_unscored'] + r['without_unscored']} | {r['with_errors'] + r['without_errors']} |")
    print(f"| **平均** | **{s['mean_with']}** | **{s['mean_without']}** | **{s['mean_delta']}** | | | | |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", default="ryan", help="ryan、ava、kai，或 T3 的實例 id")
    ap.add_argument("--model", default="gemini-4-hydrogen-high")
    ap.add_argument("--judge", action="append",
                    help="評分者，可給多個；預設 claude:sonnet 與 agy:ryan/gemini-4-hydrogen-high。"
                         "第一個是主要評分者，第二個用來算一致率")
    ap.add_argument("--case", action="append", help="只跑這題（可重複）")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--votes", type=int, default=1, help="每個評分項投票幾次（取多數）")
    ap.add_argument("--arms", default="with,without")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="放進工作資料夾當 AGENTS.md 的規則檔")
    ap.add_argument("--no-rules", action="store_true")
    ap.add_argument("--out", help="結果資料夾（預設在暫存資料夾）；給已經有結果的資料夾就接著跑")
    ap.add_argument("--rejudge", action="store_true", help="不跑 agent，只替 --out 裡已有的回覆補評分")
    args = ap.parse_args()
    args.judge = args.judge or ["claude:sonnet", "agy:ryan/gemini-4-hydrogen-high"]

    cases = load_cases(args.case)
    by_name = {c["name"]: c for c in cases}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = pathlib.Path(args.out) if args.out else pathlib.Path(tempfile.gettempdir()) / f"ask-agy-eval-{stamp}-{args.account}-{args.model}"
    out_dir.mkdir(parents=True, exist_ok=True)
    arms = args.arms.split(",")

    results, agent_todo, judge_todo = [], [], []
    if args.rejudge:
        for f in sorted(out_dir.glob("*.json")):
            if f.name == "summary.json":
                continue
            run = json.loads(f.read_text(encoding="utf-8"))
            if run["case"] in by_name and run["arm"] in arms:
                judge_todo.append(run)
        print(f"補評分 {len(judge_todo)} 次對話；評分者 {', '.join(args.judge)}；資料夾 {out_dir}", flush=True)
    else:
        gemini_dir = profile_dir(args.account)
        for c in cases:
            for arm in arms:
                for i in range(1, args.runs + 1):
                    done = out_dir / f"{c['name']}.{arm}.{i}.json"
                    old = json.loads(done.read_text(encoding="utf-8")) if done.exists() else None
                    if old and not old["error"]:
                        judge_todo.append(old)  # 沿用回覆，缺的評分補上
                    else:
                        agent_todo.append((c, arm, i))
        print(f"{len(agent_todo)} 次新對話、{len(judge_todo)} 次沿用：{len(cases)} 題 × {args.arms} × {args.runs} 次；"
              f"帳號 {args.account}、模型 {args.model}；評分者 {', '.join(args.judge)}；結果寫到 {out_dir}", flush=True)

    total = len(agent_todo) + len(judge_todo)
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(judge_job, args, by_name[r["case"]], r, out_dir): (r["case"], r["arm"], r["run"])
                   for r in judge_todo}
        if not args.rejudge:
            futures.update({pool.submit(agent_job, args, gemini_dir, c, arm, i, out_dir): (c["name"], arm, i)
                            for c, arm, i in agent_todo})
        for fut in cf.as_completed(futures):
            name, arm, i = futures[fut]
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001 - keep the batch going
                print(f"  {name} {arm} #{i}: 例外 {e}", flush=True)
                continue
            results.append(r)
            scores = " ".join(f"{s.split(':')[0]}={v}" for s, v in r["scores"].items())
            print(f"  [{len(results)}/{total}] {name} {arm} #{i}: {scores} 叫用 {r['fired']} "
                  f"{r['seconds']}s{' 錯誤：' + r['error'][:120] if r['error'] else ''}", flush=True)

    per_judge, agree = summarize(results, cases, args.judge)
    first = next(iter(results), {})
    summary = {"account": first.get("account", args.account), "model": first.get("agent_model", args.model),
               "judges": args.judge, "votes": args.votes, "rules": None if args.no_rules else args.rules,
               "finished": dt.datetime.now().isoformat(timespec="seconds"), "agreement": agree, "by_judge": per_judge}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    for spec, s in per_judge.items():
        print_table(spec, s)
    if agree:
        print(f"\n兩位評分者一致率：{agree['same']}/{agree['pairs']}（{agree['rate']}）")
    print(f"\n結果：{out_dir}")


if __name__ == "__main__":
    main()
