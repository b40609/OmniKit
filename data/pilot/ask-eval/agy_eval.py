#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""問法庫（omnikit-ask）在 Antigravity 上的有它與沒它對照評測。

跟 run.ps1（Claude Code 的 `claude plugin eval`）用同一批題目（cases/），改由 Antigravity 的 ACP 伺服器跑。
帳號沿用 T3 Code 替每個 Antigravity 實例存好的登入資料夾（不讀、不複製金鑰），用 --account 指定。
有裝 T3 時用 T3 自己管理的 `agy_acp_server.exe`（加 localharness），環境變數照 T3 設，額度才會算在
指定帳號；2026-11-17 實測 `agy acp` 不管指定哪個資料夾，額度都算在系統登入的帳號（ryan）。
沒有 T3 或設了 ASK_EVAL_USE_AGY=1 時退回 `agy acp`。

題組（--set）：
- cases：每個情境一題，有它與沒它對照，看回覆品質。
- variants：同一個情境換兩種說法（explicit：直接說不知道怎麼問；vague：只抱怨或只貼錯誤），
  只跑有它，看叫用穩不穩；評分沿用 cases 裡對應題目（front matter 的 base）的 method 評分項。
- negatives：需求講得很清楚、不該叫用問法庫的請求，只跑有它，看誤叫用；評分項在 negatives/_graders。

每題兩組：
- 有它：工作資料夾放 `.agents/skills/omnikit-ask`（Antigravity 的專案層 skill）；全域 skill 照平常
  （T3 登入資料夾的 `config/skills`，連到 `~/.gemini/config/skills`）。
- 沒它：同樣的資料夾，沒有那個 skill；另建一個暫時的 gemini 資料夾，登入與對話資料用 junction 連回原處，
  全域 skill 拿掉 omnikit-ask 與會轉去它的 ok、ok-ask。2026-11-17 起問法庫裝進了全域（3d2ce2f），
  不拿掉的話沒它組也叫得到，對照就失效。暫時資料夾跑完只拆連結，不做遞迴刪除。
- 只裝全域（--arms global）：工作資料夾不放 skill，全域照平常，也就是使用者實際裝好的樣子。
  工作資料夾是空的，有它組的 agent 會翻到 `.agents/skills` 裡唯一的東西就去讀，叫用率會偏高；
  量叫用率（variants、negatives）用 global 比較準。
兩組都放一份 `AGENTS.md`（預設是 ~/.gemini/GEMINI.md，也就是平常的 OmniKit 規則）。

評分：每個 llm 評分項由評分者判 PASS 或 FAIL，加權平均成 0 到 1 分。
- 主要評分者：本機 Claude Code 的 Sonnet（`claude -p`，關掉工具、MCP 與設定檔，一次約 700 個輸入 token），
  跟 run.ps1 的評分者同一個，結果才能比；也跟被測的 Gemini 不同家（同家評分會偏袒自己，arXiv:2604.06996）。
- 可以用第二個 --judge（例如 agy:ryan/gemini-4-hydrogen-high）算兩位的一致率。
評分出錯記為沒評到，不算進分數；用 --rejudge 補評。
agent 回覆是額度用完的訊息時記為錯誤；連續 3 次就停止開新對話，之後用同一個 --out 接著跑。
是否叫用問法庫看工具呼叫裡有沒有 omnikit-ask。

用法：
  uv run data/pilot/ask-eval/agy_eval.py --account ryan --model gemini-4-hydrogen-high
  uv run data/pilot/ask-eval/agy_eval.py --model gemini-3.8-flash-high --case ux-merge --runs 1
  uv run data/pilot/ask-eval/agy_eval.py --set negatives --model gemini-3.8-flash-high --runs 1
  uv run data/pilot/ask-eval/agy_eval.py --set variants --arms global --kind vague --runs 1
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
SETS = ("cases", "variants", "negatives")
# 只看短回覆，避免把在討論額度的正常回答（例如 feature 題）誤判成額度用完
QUOTA_RE = re.compile(r"Individual quota reached|quota (?:reached|exceeded|exhausted)|RESOURCE_EXHAUSTED"
                      r"|exceeded your current quota|rate.?limit(?:ed)? exceeded|額度已用完", re.I)
STOP = threading.Event()
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


T3_REMOVED_ENV = {"GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
                  "GOOGLE_CLOUD_LOCATION", "GOOGLE_CLOUD_QUOTA_PROJECT", "GOOGLE_GENAI_USE_VERTEXAI", "GCLOUD_PROJECT",
                  "CLOUDSDK_CORE_PROJECT", "AGY_ACP_CCPA_PROJECT", "AGY_ACP_ENABLE_OAUTH", "GEMINI_HOME",
                  "AGY_ACP_FORCE_FILE_STORAGE", "ANTIGRAVITY_HARNESS_PATH", "BROWSER"}


def runtime_temp(gemini_dir: pathlib.Path) -> pathlib.Path:
    """T3 給每個實例的暫存資料夾：antigravity-tmp/<登入資料夾名稱前 12 碼>。沒它組的暫時資料夾沿用原帳號的。"""
    key = gemini_dir.name if gemini_dir.parent == T3_PROFILES else OVERLAY_OF.get(gemini_dir, gemini_dir).name
    path = T3_PROFILES.parent.parent / "antigravity-tmp" / key[:12]
    path.mkdir(parents=True, exist_ok=True)
    return path


OVERLAY_OF: dict = {}
T3_ACP_VERSIONS = pathlib.Path.home() / ".t3" / "tools" / "antigravity-acp" / "win32-x64" / "versions"


def t3_acp_server():
    """T3 Code 裝好的最新一版 (agy_acp_server.exe, localharness_external.exe)；沒有就回 None。"""
    if os.environ.get("ASK_EVAL_USE_AGY"):
        return None
    found = [d for d in T3_ACP_VERSIONS.glob("*")
             if (d / "agy_acp_server.exe").is_file() and (d / "localharness_external.exe").is_file()]
    if not found:
        return None
    d = max(found, key=lambda p: p.stat().st_mtime)
    return d / "agy_acp_server.exe", d / "localharness_external.exe"
HIDDEN_SKILLS = {"omnikit-ask", "ok-ask", "ok"}


def _link_dir(link: pathlib.Path, target: pathlib.Path, made: list):
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)
    made.append(("link", link))


def _link_file(link: pathlib.Path, target: pathlib.Path, made: list):
    try:
        os.link(target, link)
    except OSError:
        shutil.copy2(target, link)  # 只有設定檔走到這裡（.migrated、config.json、mcp_config.json）
    made.append(("file", link))


def without_skill_dir(gemini_dir: pathlib.Path) -> tuple[pathlib.Path, list]:
    """沒它組用的 gemini 資料夾：除了 config/skills 都連回原處，skills 只連沒被拿掉的那些。"""
    root = pathlib.Path(tempfile.mkdtemp(prefix="ask-gemini-noskill-"))
    made: list = [("dir", root)]
    for item in gemini_dir.iterdir():
        if item.name != "config":
            (_link_dir if item.is_dir() else _link_file)(root / item.name, item.resolve(), made)
    cfg = root / "config"
    cfg.mkdir()
    made.append(("dir", cfg))
    for item in (gemini_dir / "config").iterdir():
        if item.name != "skills":
            (_link_dir if item.is_dir() else _link_file)(cfg / item.name, item.resolve(), made)
    skills = cfg / "skills"
    skills.mkdir()
    made.append(("dir", skills))
    src = gemini_dir / "config" / "skills"
    for item in (src.iterdir() if src.is_dir() else []):
        if item.name not in HIDDEN_SKILLS and item.is_dir():
            _link_dir(skills / item.name, item.resolve(), made)
    OVERLAY_OF[root] = gemini_dir
    return root, made


def drop_dir(made: list):
    """照建立的反序拆掉：junction 用 rmdir 只拆連結本身（Windows 文件寫明不動目標內容），不做遞迴刪除。"""
    for kind, p in reversed(made):
        try:
            if kind == "file":
                os.unlink(p)
            elif kind == "link" and p.is_symlink():
                os.unlink(p)
            else:
                os.rmdir(p)
        except OSError as e:
            print(f"  清不掉 {p}：{e}", flush=True)


# ---------- ACP client ----------

class AcpError(RuntimeError):
    pass


def windows_job(proc):
    """把程序放進 Windows Job Object，之後它開的子程序都在同一個 job，可以一次結束。失敗就回 None。"""
    import ctypes
    k = ctypes.windll.kernel32
    job = k.CreateJobObjectW(None, None)
    handle = k.OpenProcess(0x1F0FFF, False, proc.pid)  # PROCESS_ALL_ACCESS
    ok = bool(job and handle and k.AssignProcessToJobObject(job, handle))
    if handle:
        k.CloseHandle(handle)
    return job if ok else None


class Acp:
    """Minimal ACP (JSON-RPC over stdio) client for `agy acp`."""

    def __init__(self, gemini_dir: pathlib.Path, cwd: pathlib.Path):
        # 照 T3 Code 的 antigravityEnvironment：拿掉會蓋過帳號的變數，TEMP 用每個帳號自己的資料夾
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("ANTHROPIC_", "CLAUDE")) and k.upper() not in T3_REMOVED_ENV}
        tmp = runtime_temp(gemini_dir)
        env.update(GEMINI_HOME=str(gemini_dir), AGY_ACP_FORCE_FILE_STORAGE="1",
                   BROWSER="cmd.exe /c rem", PYTHONUTF8="1", PYTHONUNBUFFERED="1", TEMP=str(tmp), TMP=str(tmp))
        server = t3_acp_server()
        if server:
            # T3 自己管理的 Antigravity ACP（agy_acp_server + localharness）；登入照各帳號資料夾裡的檔案，
            # 額度才會算在指定的帳號上。`agy acp` 會改用系統裡存的登入（2026-11-17 實測都算到 ryan）。
            env["ANTIGRAVITY_HARNESS_PATH"] = str(server[1])
            cmd = [str(server[0])]
        else:
            cmd = ["agy", "acp", "--gemini-dir", str(gemini_dir), "--app-data-dir", "antigravity-acp",
                   "--dangerously-skip-permissions"]
        self.proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL)
        self.job = windows_job(self.proc) if os.name == "nt" else None
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
        if self.job:
            # agy_acp_server 會另開一個自己再加 localharness，原本那個先結束，關 stdin 也不會停；整個 job 一起結束
            import ctypes
            ctypes.windll.kernel32.TerminateJobObject(self.job, 1)
            ctypes.windll.kernel32.CloseHandle(self.job)
            self.job = None


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
        reply = "".join(text)
        quota = len(reply) < 600 and bool(QUOTA_RE.search(reply))
        return {"reply": reply, "tools": tools, "stop": result.get("stopReason"),
                "meta": result.get("_meta"), "model": applied, "seconds": round(time.monotonic() - started),
                "error": f"額度用完：{reply.strip()[:160]}" if quota else None, "quota": quota}
    except AcpError as e:
        return {"reply": "".join(text), "tools": tools, "stop": None, "meta": None, "model": model,
                "seconds": round(time.monotonic() - started), "error": str(e),
                "quota": bool(QUOTA_RE.search(str(e)))}
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


def read_graders(gdir: pathlib.Path):
    graders = []
    for g in sorted(gdir.glob("*.md")):
        front, body = split_front(g)
        if front.get("type") == "llm":
            graders.append({"name": g.stem, "weight": float(front.get("weight", 1)), "rubric": body})
    return graders


def load_cases(set_name, names):
    """題目資料夾裡有 graders/ 就用自己的；沒有而 front matter 有 base 就借 cases/<base> 的 method；
    都沒有就用題組的 _graders/。"""
    root = HERE / set_name
    shared = read_graders(root / "_graders") if (root / "_graders").is_dir() else []
    cases = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if names and d.name not in names:
            continue
        front, prompt = split_front(d / "prompt.md")
        if (d / "graders").is_dir():
            graders = read_graders(d / "graders")
        elif front.get("base"):
            graders = [g for g in read_graders(CASES / front["base"] / "graders") if g["name"] == "method"]
            if not graders:
                sys.exit(f"{d.name} 的 base {front['base']} 沒有 method 評分項")
        else:
            graders = shared
        cases.append({"name": d.name, "prompt": prompt, "graders": graders, "base": front.get("base"),
                      "kind": front.get("kind") or "base", "category": d.name.split("-")[0],
                      "expect_fire": front.get("expect_fire", "true").lower() != "false"})
    if names and len(cases) != len(set(names)):
        sys.exit(f"有題目找不到：{sorted(set(names) - {c['name'] for c in cases})}")
    return cases



# ---------- judge ----------

JUDGE = """你是評分者。只根據評分標準判斷 agent 的回覆，不要用任何工具，不要讀檔。
標準寫「做到幾項以上就 PASS」時，逐項數回覆做到幾項；達到門檻、又沒有踩到標準裡列的 FAIL 條件就判 PASS，不要加標準以外的要求。

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
            # 精簡呼叫：不載工具、MCP、設定檔與 CLAUDE.md，也不存對話（--bare 要 API key，所以不用它）
            cmd = [shutil.which("claude") or "claude", "-p", "--model", target,
                   "--system-prompt", "你是評分者，只輸出要求的 JSON。", "--tools", "", "--strict-mcp-config",
                   "--setting-sources", "", "--no-session-persistence", "--max-turns", "1"]
            try:
                p = subprocess.run(cmd, input=text, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", cwd=cwd, env=env, timeout=timeout)
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


class Skipped(Exception):
    pass


QUOTA_LOCK = threading.Lock()
QUOTA_STREAK = [0]


def note_quota(hit: bool):
    with QUOTA_LOCK:
        QUOTA_STREAK[0] = QUOTA_STREAK[0] + 1 if hit else 0
        if QUOTA_STREAK[0] >= 3:
            STOP.set()


def agent_job(args, gemini_dirs, case, arm, idx, out_dir):
    if STOP.is_set():
        raise Skipped("額度用完，略過")
    ws = make_workspace(arm, None if args.no_rules else pathlib.Path(args.rules))
    try:
        run = run_turn(gemini_dirs[arm], ws, args.model, case["prompt"], args.timeout)
    finally:
        shutil.rmtree(ws, ignore_errors=True)
    run.update(case=case["name"], arm=arm, run=idx, fired=fired(run), account=args.account, agent_model=args.model,
               global_skill_hidden=arm == "without", workspace_skill=arm == "with")
    note_quota(run.get("quota", False))
    save(run, out_dir)
    if run["error"]:
        return run  # 錯誤的回覆不評分；下次用同一個 --out 會重跑
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


def group_means(rows, key):
    groups = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    return {k: {"n": len(v), "with": mean([r["with"] for r in v]), "without": mean([r["without"] for r in v]),
                "delta": mean([r["delta"] for r in v])} for k, v in sorted(groups.items())}


def fire_stats(results, cases):
    """有它那組的叫用率：該叫用的（expect_fire）有幾次叫用、不該叫用的有幾次誤叫用；依分類與說法分組。"""
    by_name = {c["name"]: c for c in cases}
    runs = [r for r in results if r["arm"] in ("with", "global") and not r["error"] and r["case"] in by_name]

    def rate(rs):
        return {"fired": sum(r["fired"] for r in rs), "runs": len(rs),
                "rate": round(sum(r["fired"] for r in rs) / len(rs), 3) if rs else None}

    expect = [r for r in runs if by_name[r["case"]]["expect_fire"]]
    negative = [r for r in runs if not by_name[r["case"]]["expect_fire"]]
    out = {"expected": rate(expect), "negative": rate(negative),
           "missed": sorted({r["case"] for r in expect if not r["fired"]}),
           "false_fired": sorted({r["case"] for r in negative if r["fired"]})}
    for key in ("category", "kind"):
        groups = {}
        for r in runs:
            groups.setdefault(by_name[r["case"]][key], []).append(r)
        out[f"by_{key}"] = {k: rate(v) for k, v in sorted(groups.items())}
    return out


def summarize(results, cases, judges):
    out = {}
    for spec in judges:
        rows = []
        for c in cases:
            row = {"case": c["name"], "category": c["category"], "kind": c["kind"]}
            for arm in ("with", "without"):  # global 放在 with 這一欄（同一個資料夾只會有其中一種）
                runs = [r for r in results if r["case"] == c["name"]
                        and (r["arm"] == arm or (arm == "with" and r["arm"] == "global"))]
                scores = [r.get("scores", {}).get(spec) for r in runs if not r["error"]]
                row[arm] = mean(scores)
                row[f"{arm}_fired"] = f"{sum(r['fired'] for r in runs)}/{len(runs)}"
                row[f"{arm}_unscored"] = sum(1 for s in scores if s is None)
                row[f"{arm}_errors"] = sum(1 for r in runs if r["error"])
            row["delta"] = (round(row["with"] - row["without"], 3)
                            if row["with"] is not None and row["without"] is not None else None)
            rows.append(row)
        paired = [r for r in rows if r["delta"] is not None]
        out[spec] = {"mean_with": mean([r["with"] for r in rows]), "mean_without": mean([r["without"] for r in rows]),
                     "mean_delta": mean([r["delta"] for r in paired]),
                     "paired_with": mean([r["with"] for r in paired]),
                     "paired_without": mean([r["without"] for r in paired]),
                     "by_category": group_means(rows, "category"), "by_kind": group_means(rows, "kind"),
                     "rows": rows}
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
    return out, agree, fire_stats(results, cases)


def print_table(spec, s):
    print(f"\n### 評分者 {spec}")
    print("| 題目 | 有它 | 沒它 | 差距 | 有它時叫用 | 沒它時叫用 | 沒評到 | 錯誤 |")
    print("|---|---|---|---|---|---|---|---|")
    for r in s["rows"]:
        print(f"| {r['case']} | {r['with']} | {r['without']} | {r['delta']} | {r['with_fired']} | {r['without_fired']} "
              f"| {r['with_unscored'] + r['without_unscored']} | {r['with_errors'] + r['without_errors']} |")
    print(f"| **平均** | **{s['mean_with']}** | **{s['mean_without']}** | **{s['mean_delta']}** | | | | |")
    for key, title in (("by_category", "分類"), ("by_kind", "說法")):
        if len(s[key]) < 2:
            continue
        print(f"\n| {title} | 題數 | 有它 | 沒它 | 差距 |\n|---|---|---|---|---|")
        for k, g in s[key].items():
            print(f"| {k} | {g['n']} | {g['with']} | {g['without']} | {g['delta']} |")


def print_fire(f):
    e, n = f["expected"], f["negative"]
    print("\n### 叫用（有它那組）")
    if e["runs"]:
        print(f"該叫用：{e['fired']}/{e['runs']}（{e['rate']}）；沒叫用的題目：{', '.join(f['missed']) or '無'}")
    if n["runs"]:
        print(f"不該叫用：誤叫用 {n['fired']}/{n['runs']}（{n['rate']}）；誤叫用的題目：{', '.join(f['false_fired']) or '無'}")
    for key, title in (("by_category", "分類"), ("by_kind", "說法")):
        if len(f[key]) < 2:
            continue
        print(f"\n| {title} | 叫用 | 次數 | 比率 |\n|---|---|---|---|")
        for k, g in f[key].items():
            print(f"| {k} | {g['fired']} | {g['runs']} | {g['rate']} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", default="ryan", help="ryan、ava、kai，或 T3 的實例 id")
    ap.add_argument("--model", default="gemini-4-hydrogen-high")
    ap.add_argument("--judge", action="append",
                    help="評分者，可給多個；預設只有 claude:sonnet。第一個是主要評分者，第二個用來算一致率，"
                         "例如再加 agy:ryan/gemini-4-hydrogen-high")
    ap.add_argument("--set", default="cases", choices=SETS, help="題組；variants 與 negatives 預設只跑有它")
    ap.add_argument("--case", action="append", help="只跑這題（可重複）")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--votes", type=int, default=1, help="每個評分項投票幾次（取多數）")
    ap.add_argument("--arms", help="with、without、global，逗號分隔；預設 cases 跑 with,without，"
                                   "variants 與 negatives 跑 with")
    ap.add_argument("--kind", action="append", help="只跑這種說法（base、explicit、vague、negative），可重複")
    ap.add_argument("-j", "--jobs", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="放進工作資料夾當 AGENTS.md 的規則檔")
    ap.add_argument("--no-rules", action="store_true")
    ap.add_argument("--out", help="結果資料夾（預設在暫存資料夾）；給已經有結果的資料夾就接著跑")
    ap.add_argument("--rejudge", action="store_true", help="不跑 agent，只替 --out 裡已有的回覆補評分")
    args = ap.parse_args()
    args.judge = args.judge or ["claude:sonnet"]
    args.arms = args.arms or ("with,without" if args.set == "cases" else "with")

    cases = [c for c in load_cases(args.set, args.case) if not args.kind or c["kind"] in args.kind]
    by_name = {c["name"]: c for c in cases}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = (pathlib.Path(args.out) if args.out else pathlib.Path(tempfile.gettempdir())
               / f"ask-agy-eval-{stamp}-{args.set}-{args.account}-{args.model}")
    out_dir.mkdir(parents=True, exist_ok=True)
    arms = args.arms.split(",")

    results, agent_todo, judge_todo = [], [], []
    gemini_dirs, made = {}, []
    if args.rejudge:
        for f in sorted(out_dir.glob("*.json")):
            if f.name == "summary.json":
                continue
            run = json.loads(f.read_text(encoding="utf-8"))
            if run["case"] in by_name and run["arm"] in arms and not run["error"]:
                judge_todo.append(run)
        print(f"補評分 {len(judge_todo)} 次對話；評分者 {', '.join(args.judge)}；資料夾 {out_dir}", flush=True)
    else:
        gemini_dirs["with"] = gemini_dirs["global"] = profile_dir(args.account)
        if "without" in arms:
            gemini_dirs["without"], made = without_skill_dir(gemini_dirs["with"])
        for c in cases:
            for arm in arms:
                for i in range(1, args.runs + 1):
                    done = out_dir / f"{c['name']}.{arm}.{i}.json"
                    old = json.loads(done.read_text(encoding="utf-8")) if done.exists() else None
                    if old and not old["error"]:
                        judge_todo.append(old)  # 沿用回覆，缺的評分補上
                    else:
                        agent_todo.append((c, arm, i))
        print(f"{len(agent_todo)} 次新對話、{len(judge_todo)} 次沿用：{args.set} {len(cases)} 題 × {args.arms} × {args.runs} 次；"
              f"帳號 {args.account}、模型 {args.model}；評分者 {', '.join(args.judge)}；結果寫到 {out_dir}", flush=True)

    total = len(agent_todo) + len(judge_todo)
    skipped = 0
    try:
        with cf.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = {pool.submit(judge_job, args, by_name[r["case"]], r, out_dir): (r["case"], r["arm"], r["run"])
                       for r in judge_todo}
            if not args.rejudge:
                futures.update({pool.submit(agent_job, args, gemini_dirs, c, arm, i, out_dir): (c["name"], arm, i)
                                for c, arm, i in agent_todo})
            for fut in cf.as_completed(futures):
                name, arm, i = futures[fut]
                try:
                    r = fut.result()
                except Skipped:
                    skipped += 1
                    continue
                except Exception as e:  # noqa: BLE001 - keep the batch going
                    print(f"  {name} {arm} #{i}: 例外 {e}", flush=True)
                    continue
                results.append(r)
                scores = " ".join(f"{s.split(':')[0]}={v}" for s, v in (r.get("scores") or {}).items())
                print(f"  [{len(results)}/{total}] {name} {arm} #{i}: {scores} 叫用 {r['fired']} "
                      f"{r['seconds']}s{' 錯誤：' + r['error'][:120] if r['error'] else ''}", flush=True)
    finally:
        drop_dir(made)

    per_judge, agree, fire = summarize(results, cases, args.judge)
    first = next(iter(results), {})
    errors = sum(1 for r in results if r["error"])
    summary = {"set": args.set, "arms": args.arms, "kind": args.kind, "account": first.get("account", args.account),
               "model": first.get("agent_model", args.model), "judges": args.judge, "votes": args.votes,
               "rules": None if args.no_rules else args.rules,
               "finished": dt.datetime.now().isoformat(timespec="seconds"),
               "runs_done": len(results) - errors, "runs_error": errors, "runs_skipped": skipped,
               "stopped_on_quota": STOP.is_set(), "fire": fire, "agreement": agree, "by_judge": per_judge}
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    for spec, s in per_judge.items():
        print_table(spec, s)
    print_fire(fire)
    if agree:
        print(f"\n兩位評分者一致率：{agree['same']}/{agree['pairs']}（{agree['rate']}）")
    if errors or skipped:
        print(f"\n錯誤 {errors} 次、略過 {skipped} 次{'（額度用完而停止）' if STOP.is_set() else ''}；"
              f"用同一個 --out 再跑一次會只補這些")
    print(f"\n結果：{out_dir}")


if __name__ == "__main__":
    main()
