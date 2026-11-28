# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""模型煙霧題組、high vs xhigh 配對比較、試用狀態機與每週差異提醒（帳號池第三階段）。

依據 docs/proposals/2026-11-23-account-pool.md 第七、八、十節：
- 確定性自動批改（不靠 LLM 評審）：Python 題在受限隔離子行程跑固定測資；JSON 題精準比對欄位與禁止字串。
- 同題 high 對 xhigh 配對比較：量化 xhigh 到底有沒有帶來實際增益。
- 試用狀態檔 ~/.omnikit/dispatch/trials.json：新發現模型自動進 discovered/trial，累積 20 筆以上委派紀錄後依數據給升級或下架建議。
- 每週差異提醒：彙整新待測模型、試用成績判定、近 7 天撞額度與 thinking_preference 體檢、規約表過期提醒（每週最多提醒一次）。

用法：
  uv run engine/scripts/model_eval.py suite [--json]                              列出煙霧題組
  uv run engine/scripts/model_eval.py smoke-plan --model <id> [--levels high,xhigh] [--instance <id>] [--json]
                                                                                  產出煙霧測試計畫（含同題 high 對 xhigh）
  uv run engine/scripts/model_eval.py smoke-grade --file <答案 JSON> [--no-save] [--json]
                                                                                  自動批改答案並寫進 smoke-results.jsonl 與 trials.json
  uv run engine/scripts/model_eval.py compare --model <id> [--a high] [--b xhigh] [--json]
                                                                                  同題比較兩種思考程度（或同級不同模型）
  uv run engine/scripts/model_eval.py trials [--sync] [--json]                    檢視或從能力矩陣同步試用狀態
  uv run engine/scripts/model_eval.py trial-set --model <id> --status discovered|trial|promoted|demoted [--role <角色>] [--baseline <類別>] [--note <說明>]
  uv run engine/scripts/model_eval.py diff [--days 7] [--json]                    每週差異提醒（新模型、試用判定、額度體檢）
  uv run engine/scripts/model_eval.py --selftest
"""
import argparse
import ast
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TRIAL_STATES = ("discovered", "trial", "promoted", "demoted")
FORBIDDEN_IMPORTS = {
    "os", "sys", "subprocess", "socket", "urllib", "http", "ftplib", "smtplib",
    "shutil", "pathlib", "ctypes", "importlib", "builtins", "io", "tempfile",
    "multiprocessing", "threading", "signal", "webbrowser", "glob",
}
FORBIDDEN_CALLS = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint"}
CODE_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)\n```", re.S | re.I)
JSON_FENCE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.S | re.I)

MIN_TRIAL_SAMPLES = 20
MIN_BASELINE_SAMPLES = 10
MAX_GAP_PP = 10.0
QUOTA_HIT_WARN = 3      # 近 7 天撞額度達此次數，對 max_available 提出降檔提醒
XHIGH_GAIN_PP = 10.0    # 配對題組 xhigh 領先達此門檻算有量到增益
MIN_PAIRED_SMOKE = 5


# ---------- 路徑與存取 ----------

def suite_path(data):
    return Path(data) / "evals" / "model-smoke-suite.yaml"


def trials_path(state):
    return Path(state) / "dispatch" / "trials.json"


def smoke_log_path(state):
    return Path(state) / "dispatch" / "smoke-results.jsonl"


def load_suite(data):
    import yaml
    raw = yaml.safe_load(suite_path(data).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("tasks"), list):
        raise ValueError("煙霧題組 YAML 格式不對")
    return raw


def load_trials(state):
    p = trials_path(state)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("models"), dict):
            return doc
    except (OSError, ValueError):
        pass
    return {"schema_version": 1, "updated_at": None, "models": {}}


def save_trials(state, doc, now=None):
    p = trials_path(state)
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    doc = {**doc, "schema_version": 1, "updated_at": ts}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return doc


def append_smoke(state, records):
    p = smoke_log_path(state)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_smoke(state):
    p = smoke_log_path(state)
    rows = []
    if not p.is_file():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except ValueError:
            continue
    return rows


# ---------- 確定性批改器（絕不靠 LLM 評審） ----------

def extract_code(text):
    s = str(text or "").strip()
    m = CODE_FENCE.search(s)
    return m.group(1).strip() if m else s


def extract_json(text):
    s = str(text or "").strip()
    m = JSON_FENCE.search(s)
    cand = m.group(1).strip() if m else s
    i = cand.find("{")
    if i < 0:
        return None, "找不到 JSON 物件"
    try:
        obj, _ = json.JSONDecoder().raw_decode(cand[i:])
        return obj, None
    except ValueError as e:
        return None, f"JSON 解析失敗：{e}"


def ast_safety_check(code):
    """靜態檢查待測程式碼：禁止檔案／網路／子行程／反射呼叫，避免煙霧答案帶入危險動作。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"語法錯誤（第 {e.lineno} 行）：{e.msg}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in FORBIDDEN_IMPORTS:
                    return f"禁止匯入模組：{root}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in FORBIDDEN_IMPORTS:
                return f"禁止匯入模組：{root}"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                return f"禁止呼叫：{node.func.id}"
            if isinstance(node.func, ast.Attribute) and node.func.attr.startswith("__"):
                return f"禁止呼叫底線屬性：{node.func.attr}"
    return None


SANDBOX_HARNESS = r'''
import json, math, sys

# -I 會忽略 PYTHONIOENCODING，在英文 Windows（cp1252）下文字模式會炸 UnicodeEncodeError；一律走 binary UTF-8
payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
code = payload["code"]
entry = payload["entry"]
tests = payload["tests"]
tuple_list_args = set(payload.get("tuple_list_args") or [])

def emit(obj):
    sys.stdout.buffer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

ns = {}
try:
    exec(compile(code, "<smoke>", "exec"), ns)
except Exception as e:
    emit({"ok": False, "passed": 0, "total": len(tests), "detail": f"載入失敗：{type(e).__name__}: {e}"})
    sys.exit(0)

fn = ns.get(entry)
if not callable(fn):
    emit({"ok": False, "passed": 0, "total": len(tests), "detail": f"找不到可呼叫函式 {entry}"})
    sys.exit(0)

passed = 0
fails = []
for idx, t in enumerate(tests, 1):
    args = list(t.get("args") or [])
    for pos in tuple_list_args:
        if 0 <= pos < len(args) and isinstance(args[pos], list):
            args[pos] = [tuple(x) if isinstance(x, list) else x for x in args[pos]]
    want_exc = t.get("raises")
    try:
        got = fn(*args)
        if want_exc:
            fails.append(f"#{idx}: 應拋出 {want_exc}，卻回傳 {got!r}")
            continue
        exp = t.get("expect")
        if isinstance(exp, float) and isinstance(got, (int, float)):
            same = math.isclose(float(got), exp, rel_tol=1e-6, abs_tol=1e-6)
        else:
            same = got == exp
        if same:
            passed += 1
        else:
            fails.append(f"#{idx}: 預期 {exp!r}，實際 {got!r}")
    except Exception as e:
        if want_exc and type(e).__name__ == want_exc:
            passed += 1
        else:
            fails.append(f"#{idx}: 拋出 {type(e).__name__}: {e}")

emit({"ok": passed == len(tests), "passed": passed, "total": len(tests),
      "detail": "全部通過" if not fails else "；".join(fails[:3])})
'''


def grade_python(task, response_text, timeout=5):
    code = extract_code(response_text)
    unsafe = ast_safety_check(code)
    if unsafe:
        return {"ok": False, "passed": 0, "total": len(task.get("tests") or []), "detail": unsafe}
    payload = json.dumps({
        "code": code, "entry": task["entry"], "tests": task["tests"],
        "tuple_list_args": task.get("tuple_list_args") or [],
    }, ensure_ascii=False).encode("utf-8")
    safe_env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR", "PATH", "LANG", "LC_ALL") if k in os.environ}
    try:
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(
                [sys.executable, "-I", "-c", SANDBOX_HARNESS],
                input=payload, capture_output=True, cwd=td, timeout=timeout, env=safe_env,
            )
    except subprocess.TimeoutExpired:
        return {"ok": False, "passed": 0, "total": len(task["tests"]), "detail": f"執行逾時（>{timeout} 秒）"}
    except OSError as e:
        return {"ok": False, "passed": 0, "total": len(task["tests"]), "detail": f"子行程啟動失敗：{e}"}
    out = (r.stdout or b"").decode("utf-8", "replace").strip()
    err = (r.stderr or b"").decode("utf-8", "replace").strip()
    try:
        return json.loads(out.splitlines()[-1])
    except (IndexError, ValueError):
        return {"ok": False, "passed": 0, "total": len(task["tests"]),
                "detail": f"無法讀取批改輸出（exit {r.returncode}）：{(err or out)[:160]}"}


def grade_json(task, response_text):
    raw = str(response_text or "")
    checks = task.get("checks") or {}
    fails = []
    for bad in checks.get("forbid_substrings") or []:
        if bad in raw:
            fails.append(f"輸出外洩禁止字串：{bad}")
    obj, err = extract_json(raw)
    if err or not isinstance(obj, dict):
        return {"ok": False, "passed": 0, "total": 1, "detail": err or "最外層要是 JSON 物件"}
    total, passed = 0, 0
    for k, exp in (checks.get("exact_fields") or {}).items():
        total += 1
        if obj.get(k) == exp:
            passed += 1
        else:
            fails.append(f"{k} 預期 {exp!r}，實際 {obj.get(k)!r}")
    for k, limit in (checks.get("max_len_fields") or {}).items():
        total += 1
        val = obj.get(k)
        if isinstance(val, str) and 0 < len(val) <= limit:
            passed += 1
        else:
            fails.append(f"{k} 需為 1..{limit} 字元的字串")
    req_types = checks.get("required_bug_types") or []
    if req_types:
        bugs = obj.get("bugs") if isinstance(obj.get("bugs"), list) else []
        by_type = {b.get("type"): b.get("line") for b in bugs if isinstance(b, dict)}
        ranges = checks.get("bug_line_ranges") or {}
        for bt in req_types:
            total += 1
            ln = by_type.get(bt)
            lo, hi = ranges.get(bt, (1, 10**9))
            if isinstance(ln, int) and lo <= ln <= hi:
                passed += 1
            else:
                fails.append(f"缺少或行號錯誤：{bt}（應在 {lo}-{hi}，實際 {ln!r}）")
        if len(bugs) != len(req_types):
            fails.append(f"錯誤數量應為 {len(req_types)}，實際 {len(bugs)}")
    if checks.get("forbid_substrings"):
        total += 1
        if not any("禁止字串" in f for f in fails):
            passed += 1
    return {"ok": not fails and passed == total, "passed": passed, "total": max(total, 1),
            "detail": "全部通過" if not fails else "；".join(fails[:3])}


def grade_task(task, response_text):
    if task.get("kind") == "python_fn":
        return grade_python(task, response_text)
    if task.get("kind") == "json_match":
        return grade_json(task, response_text)
    return {"ok": False, "passed": 0, "total": 1, "detail": f"不支援的題型：{task.get('kind')}"}


def grade_submission(suite, items, state=None, save=True, now=None):
    """items：[{model, thinking, task_id, response, seconds?, instance?}] → 批改結果並可寫入紀錄與 trials.json。"""
    by_id = {t["id"]: t for t in suite["tasks"]}
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    graded = []
    for it in items:
        tid = it.get("task_id")
        if tid not in by_id:
            raise ValueError(f"題號不存在：{tid}")
        model = str(it.get("model") or "").strip()
        thinking = str(it.get("thinking") or "").strip()
        if not model or not thinking:
            raise ValueError(f"每筆答案都要寫 model 與 thinking：{it}")
        res = grade_task(by_id[tid], it.get("response", ""))
        graded.append({
            "ts": ts, "suite_version": suite.get("suite_version", 1),
            "model": model, "thinking": thinking, "instance": it.get("instance"),
            "task_id": tid, "category": by_id[tid].get("category"),
            "ok": bool(res["ok"]), "passed": res["passed"], "total": res["total"],
            "seconds": it.get("seconds"), "detail": res["detail"],
        })
    if save and state is not None and graded:
        append_smoke(state, graded)
        _update_trials_from_smoke(state, graded, now)
    return graded


def _update_trials_from_smoke(state, graded, now=None):
    doc = load_trials(state)
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    touched = {(g["model"], g["thinking"]) for g in graded}
    # 從整份煙霧紀錄取每題最新一筆彙總，避免分批補測時後批覆蓋前批題數
    latest = {}
    for r in read_smoke(state):
        key = (r.get("model"), r.get("thinking"))
        if key in touched and r.get("task_id"):
            latest[(key[0], key[1], r["task_id"])] = r
    for model, th in sorted(touched):
        rows = [r for (m, lv, _), r in latest.items() if m == model and lv == th]
        if not rows:
            continue
        m = doc["models"].setdefault(model, {"status": "discovered", "role": None, "baseline": None, "smoke": {}, "updated_at": ts})
        ok_n = sum(1 for r in rows if r["ok"])
        m.setdefault("smoke", {})[th] = {
            "passed": ok_n, "total": len(rows), "rate": round(ok_n / len(rows), 3),
            "checked_at": ts,
        }
        if m.get("status") == "discovered" and len(rows) >= MIN_PAIRED_SMOKE and ok_n / len(rows) >= 0.75:
            m["status"] = "trial"
        m["updated_at"] = ts
    save_trials(state, doc, now)


# ---------- 同題 high vs xhigh 配對比較 ----------

def compare_levels(rows, model, level_a="high", level_b="xhigh"):
    """依同一個模型、同一套題目的最新一筆結果做配對比較（level_a 對 level_b）。"""
    latest = {}
    for r in rows:
        if r.get("model") != model or r.get("thinking") not in (level_a, level_b):
            continue
        latest[(r["thinking"], r["task_id"])] = r
    tasks_a = {tid for (lv, tid) in latest if lv == level_a}
    tasks_b = {tid for (lv, tid) in latest if lv == level_b}
    paired = sorted(tasks_a & tasks_b)
    wins_a, wins_b, ties_pass, ties_fail = [], [], [], []
    sec_a, sec_b = [], []
    for tid in paired:
        ra, rb = latest[(level_a, tid)], latest[(level_b, tid)]
        if isinstance(ra.get("seconds"), (int, float)):
            sec_a.append(float(ra["seconds"]))
        if isinstance(rb.get("seconds"), (int, float)):
            sec_b.append(float(rb["seconds"]))
        if ra["ok"] and not rb["ok"]:
            wins_a.append(tid)
        elif rb["ok"] and not ra["ok"]:
            wins_b.append(tid)
        elif ra["ok"] and rb["ok"]:
            ties_pass.append(tid)
        else:
            ties_fail.append(tid)
    n = len(paired)
    rate_a = round((len(wins_a) + len(ties_pass)) / n * 100, 1) if n else None
    rate_b = round((len(wins_b) + len(ties_pass)) / n * 100, 1) if n else None
    diff_pp = round(rate_b - rate_a, 1) if n else None
    med_a = round(statistics.median(sec_a), 1) if sec_a else None
    med_b = round(statistics.median(sec_b), 1) if sec_b else None
    if n < MIN_PAIRED_SMOKE:
        verdict = f"配對題數不足（{n}/{MIN_PAIRED_SMOKE} 題），先補測同題 {level_a} 與 {level_b}"
    elif diff_pp >= XHIGH_GAIN_PP and not wins_a:
        verdict = f"{level_b} 量到明確增益（+{diff_pp} 個百分點，無退步題）"
    elif diff_pp > 0:
        verdict = f"{level_b} 略高（+{diff_pp} 個百分點，{level_a} 勝 {len(wins_a)} 題、{level_b} 勝 {len(wins_b)} 題）"
    elif diff_pp == 0:
        verdict = f"{level_a} 與 {level_b} 同題平手（各 {rate_a}%）；額度有限的使用者用 {level_a} 即可"
    else:
        verdict = f"{level_b} 反而較低（{diff_pp} 個百分點）；不要開 {level_b}"
    return {
        "model": model, "level_a": level_a, "level_b": level_b, "paired": n,
        "rate_a_pct": rate_a, "rate_b_pct": rate_b, "diff_pp": diff_pp,
        "wins_a": wins_a, "wins_b": wins_b, "ties_pass": ties_pass, "ties_fail": ties_fail,
        "median_sec_a": med_a, "median_sec_b": med_b, "verdict": verdict,
    }


def smoke_plan(suite, model, levels=("high", "xhigh"), instance=None):
    steps = []
    for lv in levels:
        for t in suite["tasks"]:
            steps.append({
                "model": model, "thinking": lv, "instance": instance,
                "task_id": t["id"], "category": t["category"], "title": t["title"],
                "prompt": t["prompt"].strip(),
            })
    return {"suite_version": suite.get("suite_version", 1), "model": model, "levels": list(levels),
            "instance": instance, "total_runs": len(steps), "steps": steps}


# ---------- 試用同步與每週差異提醒 ----------

def sync_trials_from_matrix(state, data, mine=None, now=None):
    """從能力矩陣掃出已通過探測、沒被過濾、但不在正式分工裡的模型，自動建 discovered 紀錄。"""
    import accounts
    import dispatch
    pol = dispatch.policy(data)
    rates = accounts.rates_index()
    matrix = accounts.load_matrix(state)
    doc = load_trials(state)
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    # 正式分工裡的主力模型（排除只有試用／未進路線的）
    in_route = set()
    for lv in (pol.get("levels") or {}).values():
        for sec in ("prework", "route", "second_opinion"):
            for o in lv.get(sec) or []:
                c = (pol.get("model_classes") or {}).get(o.get("class"))
                if c:
                    in_route.add(accounts.norm(c["model"]))
    added = []
    for iid, rec in matrix.items():
        for m, info in (rec.get("models") or {}).items():
            if not isinstance(info, dict) or info.get("ok") is not True:
                continue
            nm = accounts.norm(m)
            st, _ = accounts.model_status(nm, list((rec.get("models") or {}).keys()), mine, rates, accounts.role_models(pol))
            if st == "filtered" or nm in in_route or nm in doc["models"]:
                continue
            doc["models"][nm] = {
                "status": "discovered", "role": None, "baseline": None,
                "first_seen_instance": iid, "smoke": {}, "updated_at": ts,
            }
            added.append(nm)
    if added:
        save_trials(state, doc, now)
    return doc, added


def weekly_diff(state, data, mine=None, *, days=7, now=None):
    """每週差異提醒：彙整新待測模型、試用判定、近 7 天撞額度體檢、規約表時效、high vs xhigh 配對結果。"""
    import accounts
    import dispatch
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    pol = dispatch.policy(data)
    trials = load_trials(state)
    log_rows, _ = dispatch.read_log(dispatch.log_path(state))
    anns = dispatch.read_annotations(state)
    proj_rows = [dispatch.project_record(r, annotations=anns, pol=pol) for r in log_rows]
    smoke_rows = read_smoke(state)
    items = []

    # 1. 新模型待跑煙霧題組 / 試用模型委派紀錄達標檢查（改採去噪口徑：只計 origin=="field" 且 model_ok is not None）
    clean_field = [p for p in proj_rows if p.get("origin") == "field" and p.get("model_ok") is not None]
    classes_cfg = pol.get("model_classes") or {}
    for model, info in sorted(trials.get("models", {}).items()):
        st = info.get("status")
        if st == "discovered":
            items.append({"kind": "smoke_needed", "model": model,
                          "message": f"新模型 {model} 已探測通過但還沒跑煙霧題組（model_eval.py smoke-plan --model {model}）"})
        elif st == "trial":
            norm_m = accounts.norm(model)
            m_rows = [p for p in clean_field if accounts.norm(p.get("judged_model") or p.get("model")) == norm_m]
            base_cls = info.get("baseline")
            base_model = (classes_cfg.get(base_cls) or {}).get("model") if base_cls else None
            if base_model:
                norm_b = accounts.norm(base_model)
                b_rows = [
                    p for p in clean_field
                    if accounts.norm(p.get("judged_model") or p.get("model")) == norm_b or p.get("class") == base_cls
                ]
            elif base_cls:
                b_rows = [p for p in clean_field if p.get("class") == base_cls]
            else:
                b_rows = []
            if len(m_rows) < MIN_TRIAL_SAMPLES:
                items.append({"kind": "trial_progress", "model": model,
                              "message": f"試用中 {model}：目前去噪可評 {len(m_rows)}/{MIN_TRIAL_SAMPLES} 筆委派紀錄，樣本不足尚不判定"})
            else:
                ra = sum(1 for p in m_rows if p.get("model_ok") is True) / len(m_rows) * 100
                if base_cls and len(b_rows) >= MIN_BASELINE_SAMPLES:
                    rb = sum(1 for p in b_rows if p.get("model_ok") is True) / len(b_rows) * 100
                    gap = round(rb - ra, 1)
                    if gap >= MAX_GAP_PP:
                        items.append({"kind": "trial_demote", "model": model,
                                      "message": f"建議下架／退回 {model}：去噪 model_ok 良率 {ra:.1f}%，比 {base_cls}（{rb:.1f}%）低 {gap} 個百分點"})
                    else:
                        items.append({"kind": "trial_promote", "model": model,
                                      "message": f"建議升級進正式分工 {model}：去噪 model_ok 良率 {ra:.1f}%（{len(m_rows)} 筆），與 {base_cls} 差距 {gap} 個百分點（門檻 {MAX_GAP_PP}）"})
                else:
                    items.append({"kind": "trial_ready", "model": model,
                                  "message": f"試用中 {model} 已達去噪 {len(m_rows)} 筆（model_ok 良率 {ra:.1f}%），可決定是否升級進正式分工"})

    # 1b. 實地良率觸頂提醒（clean_table 有 ceiling_warn：n >= 20 且 Wilson 95% CI 下限 > 85%）
    st_summary = dispatch.stats(pol, log_rows, annotations=anns)
    ceilings = [c for c in (st_summary.get("clean_table") or []) if c.get("ceiling_warn")]
    if ceilings:
        labels = "、".join(f"{c['level']}/{c['model']}({c['thinking']} {c['ok']}/{c['n']})" for c in ceilings[:4])
        more = f" 等 {len(ceilings)} 組" if len(ceilings) > 4 else ""
        items.append({
            "kind": "ceiling_warn",
            "model": None,
            "message": f"實地良率觸頂提醒：{labels}{more} 的 Wilson 95% CI 下限已高於 85%，跨模型排名請改看同題配對盲評",
        })

    # 2. high vs xhigh 配對結果摘要
    for model in sorted({r.get("model") for r in smoke_rows if r.get("model")}):
        cmp = compare_levels(smoke_rows, model, "high", "xhigh")
        if cmp["paired"] >= MIN_PAIRED_SMOKE:
            items.append({"kind": "thinking_compare", "model": model,
                          "message": f"{model} 同題比較（{cmp['paired']} 題）：{cmp['verdict']}"})

    # 3. 近 N 天撞額度體檢（納入 error_kind == "quota_exhausted" 與投影後 infra_issue == "quota"）
    cutoff = now_dt - timedelta(days=days)
    recent_quota = 0
    for r, p in zip(log_rows, proj_rows):
        if r.get("error_kind") != "quota_exhausted" and p.get("infra_issue") != "quota":
            continue
        ts_s = str(p.get("ts") or r.get("ts") or "")
        try:
            dt = datetime.fromisoformat(ts_s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                recent_quota += 1
        except ValueError:
            continue
    pref = (mine or {}).get("thinking_preference")
    if pref == "max_available" and recent_quota >= QUOTA_HIT_WARN:
        items.append({"kind": "thinking_downgrade_hint", "model": None,
                      "message": f"近 {days} 天撞額度（quota_exhausted）{recent_quota} 次；目前 thinking_preference 是 max_available，可考慮降一級到 balanced（由你決定）"})

    # 4. 規約表新鮮度檢查
    term_errs = accounts.check_terms(accounts.load_terms(data), now_dt.date())
    for e in term_errs:
        items.append({"kind": "terms_check", "model": None, "message": f"規約表提醒：{e}"})

    return {"generated_at": now_dt.isoformat(timespec="seconds"), "window_days": days,
            "recent_quota_hits": recent_quota, "items": items}


# ---------- CLI ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description="模型煙霧題組、high/xhigh 配對比較、試用狀態與每週差異提醒")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("suite")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("smoke-plan")
    p.add_argument("--model", required=True)
    p.add_argument("--levels", default="high,xhigh")
    p.add_argument("--instance")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("smoke-grade")
    p.add_argument("--file", required=True)
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("compare")
    p.add_argument("--model", required=True)
    p.add_argument("--a", default="high")
    p.add_argument("--b", default="xhigh")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("trials")
    p.add_argument("--sync", action="store_true", help="從能力矩陣掃出新模型並加入 discovered")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("trial-set")
    p.add_argument("--model", required=True)
    p.add_argument("--status", required=True, choices=TRIAL_STATES)
    p.add_argument("--role")
    p.add_argument("--baseline")
    p.add_argument("--note")

    p = sub.add_parser("diff")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    import dispatch
    data, state, _, folder = dispatch.context()
    mine = dispatch.personal(folder)

    if args.cmd == "suite":
        s = load_suite(data)
        if args.json:
            print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"煙霧題組 v{s.get('suite_version')}（{len(s['tasks'])} 題，全自動確定性批改）：")
            for t in s["tasks"]:
                print(f"  {t['id']} [{t['category']}/{t['kind']}]：{t['title']}")
        return 0

    if args.cmd == "smoke-plan":
        s = load_suite(data)
        lvs = [x.strip() for x in args.levels.split(",") if x.strip()]
        plan = smoke_plan(s, args.model, lvs, args.instance)
        if args.json:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        else:
            print(f"煙霧測試計畫：{plan['model']} × {' / '.join(plan['levels'])}（共 {plan['total_runs']} 次）")
            print("把每題回覆寫成 JSON 陣列（model, thinking, task_id, response, seconds），交給 model_eval.py smoke-grade --file <檔>。")
        return 0

    if args.cmd == "smoke-grade":
        s = load_suite(data)
        raw = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
        items = raw if isinstance(raw, list) else raw.get("results") or []
        graded = grade_submission(s, items, state=state, save=not args.no_save)
        if args.json:
            print(json.dumps(graded, ensure_ascii=False, indent=2))
        else:
            ok_n = sum(1 for g in graded if g["ok"])
            print(f"批改完成：{ok_n}/{len(graded)} 通過" + ("（未存檔）" if args.no_save else f"（已寫入 {smoke_log_path(state)}）"))
            for g in graded:
                print(f"  [{'通過' if g['ok'] else '失敗'}] {g['model']}({g['thinking']}) {g['task_id']}：{g['detail']}")
        return 0

    if args.cmd == "compare":
        cmp = compare_levels(read_smoke(state), args.model, args.a, args.b)
        if args.json:
            print(json.dumps(cmp, ensure_ascii=False, indent=2))
        else:
            print(f"{cmp['model']} 同題比較（{cmp['level_a']} vs {cmp['level_b']}，配對 {cmp['paired']} 題）：{cmp['verdict']}")
            if cmp["paired"]:
                print(f"  通過率：{cmp['level_a']} {cmp['rate_a_pct']}% vs {cmp['level_b']} {cmp['rate_b_pct']}%（差距 {cmp['diff_pp']:+.1f}pp）")
                if cmp["median_sec_a"] is not None and cmp["median_sec_b"] is not None:
                    print(f"  中位耗時：{cmp['level_a']} {cmp['median_sec_a']}s vs {cmp['level_b']} {cmp['median_sec_b']}s")
        return 0

    if args.cmd == "trials":
        added = []
        if args.sync:
            doc, added = sync_trials_from_matrix(state, data, mine)
        else:
            doc = load_trials(state)
        if args.json:
            print(json.dumps({"added": added, "trials": doc}, ensure_ascii=False, indent=2))
        else:
            if added:
                print(f"已從能力矩陣加入新模型：{'、'.join(added)}")
            if not doc["models"]:
                print("目前沒有試用紀錄（加 --sync 可從能力矩陣掃出新模型）。")
            for m, info in sorted(doc["models"].items()):
                sm = "、".join(f"{lv}:{v['passed']}/{v['total']}" for lv, v in sorted((info.get("smoke") or {}).items()))
                print(f"  {m}：狀態 {info.get('status')}" + (f"；角色 {info['role']}" if info.get("role") else "")
                      + (f"；煙霧 {sm}" if sm else ""))
        return 0

    if args.cmd == "trial-set":
        doc = load_trials(state)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry = doc["models"].setdefault(args.model, {"smoke": {}})
        entry["status"] = args.status
        if args.role is not None:
            entry["role"] = args.role
        if args.baseline is not None:
            entry["baseline"] = args.baseline
        if args.note is not None:
            entry["note"] = args.note
        entry["updated_at"] = ts
        save_trials(state, doc)
        print(f"已更新 {args.model} 試用狀態為 {args.status}")
        return 0

    if args.cmd == "diff":
        d = weekly_diff(state, data, mine, days=args.days)
        if args.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print(f"每週差異提醒（近 {d['window_days']} 天撞額度 {d['recent_quota_hits']} 次）：")
            if not d["items"]:
                print("  目前沒有需要調整的項目。")
            for it in d["items"]:
                print(f"  - [{it['kind']}] {it['message']}")
        return 0

    ap.print_help()
    return 2


# ---------- 自我測試 ----------

REFERENCE_SOLUTIONS = {
    "S1": """```python
def moving_avg(nums, window):
    if window <= 0:
        raise ValueError("window must be positive")
    if not nums or window > len(nums):
        return []
    return [round(sum(nums[i:i + window]) / window, 4) for i in range(len(nums) - window + 1)]
```""",
    "S2": """```python
import re
def parse_amount(text):
    s = (text or "").strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    for p in ("NT$", "USD", "$"):
        if s.startswith(p):
            s = s[len(p):].strip()
            break
    if not s or not re.fullmatch(r"[+-]?(?:\\d{1,3}(?:,\\d{3})*|\\d+)(?:\\.\\d+)?", s):
        return None
    v = float(s.replace(",", ""))
    return -abs(v) if neg else v
```""",
    "S3": """```python
def pick_account(current, scores, seconds_since_switch, cooldown=300, margin=5.0, floor=10.0):
    valid = {k: v for k, v in scores.items() if v > 0}
    if not valid:
        return ""
    best = sorted(valid, key=lambda k: (-valid[k], k))[0]
    if current in valid and valid[current] > floor:
        if seconds_since_switch < cooldown:
            return current
        if valid[best] - valid[current] <= margin:
            return current
    return best
```""",
    "S4": """```json
{"bugs": [
  {"line": 4, "type": "zero_on_fetch_error"},
  {"line": 7, "type": "overwrite_ban_flag"},
  {"line": 10, "type": "naive_datetime_compare"}
]}
```""",
    "S5": """```json
{"status_code": 403, "kind": "validation_required", "url": "https://accounts.google.com/verify?t=42", "safe_summary": "403 validation required (credentials redacted)"}
```""",
    "S6": """```json
{"c1": false, "c2": true, "c3": false, "c4": false}
```""",
    "S7": """```python
def sort_semver(versions):
    def key(v):
        core = v.split("+", 1)[0]
        main, *pre = core.split("-", 1)
        nums = tuple(int(x) for x in main.split("."))
        if not pre:
            return (nums, 1, ())
        parts = tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre[0].split("."))
        return (nums, 0, parts)
    return sorted(versions, key=key)
```""",
    "S8": """```python
import heapq
def topo_min(nodes, edges):
    adj = {n: set() for n in nodes}
    indeg = {n: 0 for n in nodes}
    for u, v in set(edges):
        adj[u].add(v)
        indeg[v] += 1
    h = [n for n in nodes if indeg[n] == 0]
    heapq.heapify(h)
    out = []
    while h:
        u = heapq.heappop(h)
        out.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                heapq.heappush(h, v)
    return out if len(out) == len(nodes) else None
```""",
}


def selftest():
    import profiles
    failures = []

    def ok(label, cond):
        print(f"{'通過' if cond else '失敗'}：{label}")
        if not cond:
            failures.append(label)

    suite = load_suite(profiles.DATA)
    ok("煙霧題組：載入 8 題，涵蓋 python_fn 與 json_match，且可正確序列化為 JSON",
       len(suite["tasks"]) == 8 and {t["kind"] for t in suite["tasks"]} == {"python_fn", "json_match"}
       and json.loads(json.dumps(suite, ensure_ascii=False, default=str))["suite_version"] == suite["suite_version"])

    # 1. 參考解答全部通過確定性批改
    t0 = datetime(2026, 11, 23, 6, 0, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        st = Path(tmp)
        sub_xhigh = [{"model": "gemini-4-argon", "thinking": "xhigh", "task_id": tid, "response": resp, "seconds": 18}
                     for tid, resp in REFERENCE_SOLUTIONS.items()]
        graded_x = grade_submission(suite, sub_xhigh, state=st, save=True, now=t0)
        ok("參考解答 8/8 全部通過確定性批改，並自動升為 trial",
           all(g["ok"] for g in graded_x) and load_trials(st)["models"]["gemini-4-argon"]["status"] == "trial")

        # 2. 壞解答、外洩假 token、危險 import 都被精準擋下
        bad_py = grade_task(suite["tasks"][0], "```python\nimport os\ndef moving_avg(a, w): return []\n```")
        bad_leak = grade_task(suite["tasks"][4], '{"status_code":403,"kind":"validation_required","url":"https://accounts.google.com/verify?t=42","safe_summary":"ya29.secret_demo_98765"}')
        ok("沙盒靜態檢查擋掉危險 import；JSON 批改抓到敏感字串外洩",
           not bad_py["ok"] and "禁止匯入" in bad_py["detail"]
           and not bad_leak["ok"] and "外洩禁止字串" in bad_leak["detail"])

        # 3. 同題 high vs xhigh 配對比較（模擬 high 錯 S7、S8 兩題 → xhigh 領先 +25pp）
        sub_high = []
        for tid, resp in REFERENCE_SOLUTIONS.items():
            ans = "```python\ndef sort_semver(v): return sorted(v)\n```" if tid == "S7" else (
                  "```python\ndef topo_min(n, e): return sorted(n)\n```" if tid == "S8" else resp)
            sub_high.append({"model": "gemini-4-argon", "thinking": "high", "task_id": tid, "response": ans, "seconds": 8})
        grade_submission(suite, sub_high, state=st, save=True, now=t0)
        cmp = compare_levels(read_smoke(st), "gemini-4-argon", "high", "xhigh")
        ok("同題 high 對 xhigh 配對比較：算對通過率差距與勝敗題目",
           cmp["paired"] == 8 and cmp["rate_a_pct"] == 75.0 and cmp["rate_b_pct"] == 100.0
           and cmp["diff_pp"] == 25.0 and cmp["wins_b"] == ["S7", "S8"] and "明確增益" in cmp["verdict"])

        # 4. 試用判定與每週差異提醒（20 筆委派紀錄＋近 7 天 3 次撞額度）
        import dispatch
        tr_doc = load_trials(st)
        tr_doc["models"]["gemini-4-argon"]["baseline"] = "gemini-pro"
        tr_doc["models"]["gemini-new-beta"] = {"status": "discovered", "smoke": {}}
        save_trials(st, tr_doc, t0)
        lp = dispatch.log_path(st)
        for i in range(20):
            dispatch.append(lp, {"ts": t0.isoformat(), "class": "gemini-argon", "model": "gemini-4-argon",
                                 "verdict": "pass" if i < 18 else "fail", "first_pass": i < 18,
                                 "error_kind": "quota_exhausted" if i < 3 else None})
        for i in range(10):
            dispatch.append(lp, {"ts": t0.isoformat(), "class": "gemini-pro", "model": "gemini-4-neon",
                                 "verdict": "pass" if i < 9 else "fail", "first_pass": i < 9})
        diff = weekly_diff(st, profiles.DATA, {"thinking_preference": "max_available"}, days=7, now=t0)
        kinds = {it["kind"] for it in diff["items"]}
        ok("每週差異提醒：抓出待測新模型、達標試用升級建議、high/xhigh 比較與撞額度降檔提醒",
           {"smoke_needed", "trial_promote", "thinking_compare", "thinking_downgrade_hint"} <= kinds
           and diff["recent_quota_hits"] == 3)

    print(f"\n{'model_eval.py selftest：全部通過' if not failures else f'model_eval.py selftest：{len(failures)} 項失敗'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
