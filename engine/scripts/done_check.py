# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""完工宣稱 Stop 閘（Claude Code 的 Stop 與 SubagentStop、Codex 的 Stop、Antigravity 的 Stop）。

為什麼要有：「做不到」有 claim_check.py 擋，「做完了」卻沒有任何機制；規則只寫「沒測過就不能說通過」，
長對話裡會衰減。這支把「做完了」當成要附可重查證據的主張，在 agent 收尾那一刻做純機械檢查，不讀語意。

什麼時候檢查（兩個條件有一個就算）：
- 最後一則回覆有一行以【完成待收尾】開頭（句子中間提到這個標籤不算）。
- 這一回合寫了 `.done` 檔：從對話紀錄找這一回合的工具呼叫（Write／Edit 的 file_path，或 shell 指令裡的 `*.done`）。

檢查什麼（設計〈改動 1〉第 1 到 5 條）：
1. 沒有完工回執：找不到表頭含「驗證層級」與「證據位置」的表格。回覆裡沒有時，也看 `.done` 對應的交付檔
   （`x.md.done` 看 `x.md`，`x.done` 看 `x.md`、`x.txt` 與 `.done` 本身），回執寫在交付檔裡也算。
2. 回執沒有「沒驗的範圍：」這一行（沒有也要寫「無」）。
3. 證據位置是檔案路徑的：檔案要存在，修改時間要在這段對話開始之後（對話開始時間取對話紀錄的第一筆時間）。
4. 標了【完成待收尾】：cwd 的 git 有未提交（git status --porcelain）或未 push（@{u}..HEAD；沒設上游時看 HEAD
   在不在任何遠端分支裡）。不是 git repo、沒有遠端、git 出錯或逾時都跳過不擋。回覆寫明「只在這台」時不查未 push
   （使用者規則對【完成待收尾】的定義：不能 push 的寫明只在這台）。
5. 回執每一列都是「靜態」層級：不擋，只提示把標籤降為【等你決定】並寫明「只有靜態檢查」。

模式（環境變數 OMNIKIT_DONE_CHECK）：
- 沒設（預設）＝ log：只把命中寫進 ~/.omnikit/harness/tripwire-hits.jsonl（格式同 claim_check.py，多記 mode 與 event），
  不擋、不印任何東西。上線先只記錄，看誤擋率再開擋。
- block：有第 1 到 4 條的缺口就擋一次（Claude Code／Codex 印 decision: block，Antigravity 印 decision: continue），
  只有第 5 條時印 systemMessage 提示、不擋。
- off（或 0、false、no）：整個關掉。tripwire 紀錄另外可用 OMNIKIT_TRIPWIRE_LOG=off 關掉（同 claim_check.py）。
stop_hook_active（Antigravity 是 continuationActive）為真一定放行，擋一次就好，不會無限迴圈。
任何錯誤都安靜結束（exit 0）；git 每個指令有逾時，逾時就跳過。檢查壞掉不能卡住對話。

限制：回執內容仍是做事者填的，可以填假的。這道閘擋的是「完全沒附」與「機器查得到的不一致」，不是造假。
Antigravity 的 Stop 輸入沒有最後一則回覆，從 transcriptPath 找最後一筆 MODEL 的 PLANNER_RESPONSE（照本機紀錄的格式，
不是官方文件寫的契約，待驗證），也不偵測 .done。Codex 的 .done 偵測照 rollout 的 *call 項目找，未實測。

註冊：claude_allow.py 的 HOOKS（Stop、SubagentStop；薄 plugin 與 settings.json 備案都從這裡產生）、
codex_hooks.py（Stop）、sync.py 的 Antigravity 薄 plugin（Stop）。

用法：uv run engine/scripts/done_check.py                      從 stdin 讀 hook 輸入（hook 用）
      uv run engine/scripts/done_check.py --check <檔案> [--cwd <資料夾>]  檢查一段文字（- 是 stdin），印出判斷
      uv run engine/scripts/done_check.py --selftest
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claim_check import last_message, read_jsonl

OFF = ("0", "off", "false", "no")
GIT_TIMEOUT = 4  # 每個 git 指令的逾時（秒）；hook 本身的逾時在註冊時設 15 秒
SLACK = 2.0  # 檔案修改時間的容許誤差（秒）
TAIL = 4 * 1024 * 1024  # 找這一回合的工具呼叫只讀對話紀錄最後這麼多位元組
MAX_READ = 512 * 1024  # 交付檔最多讀這麼多字

LABEL = "【完成待收尾】"
LABEL_LINE = re.compile(r"(?m)^[ \t]*(?:#{1,6}[ \t]+|[-*+][ \t]+)?(?:\*\*)?【完成待收尾】")
FENCE = re.compile(r"```[\s\S]*?(?:```|$)")
SCOPE = re.compile(r"(?m)^[ \t>*\-]*(?:\*\*)?(?:沒驗的範圍|沒有驗的範圍|未驗證的範圍|未驗的範圍)(?:\*\*)?[ \t]*[:：]"
                   r"[ \t]*(?:\*\*)?[ \t]*(\S.*)?$")
LOCAL_ONLY = re.compile(r"只在這台")
STATIC = re.compile(r"靜態|static|lint|typecheck|型別檢查", re.IGNORECASE)
NOT_STATIC = re.compile(r"單元|unit|整合|integration|實跑|觀察|端到端|e2e|截圖|人工|手動|manual", re.IGNORECASE)

PATH_EXT = re.compile(r"\.[A-Za-z][A-Za-z0-9]{1,7}$")
LINE_SUFFIX = re.compile(r"(?::\d+(?:[-:]\d+)?|#L\d+(?:-L?\d+)?)$")
NOT_PATHS = {"node.js", "vue.js", "next.js", "nuxt.js", "three.js", "chart.js", "d3.js", "express.js", "socket.io",
             "asp.net", "vite.js"}
DONE_IN_CMD = re.compile(r"""(?:[A-Za-z]:)?[^\s"'`<>|;&()]+\.done(?![\w.\-])""")
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

RECEIPT_FORMAT = ("## 完工回執\n"
                  "| 需求項 | 驗證層級 | 驗證指令或觀察 | 結果 | 證據位置 |\n"
                  "|---|---|---|---|---|\n"
                  "| （每項需求一列） | 靜態／單元／整合／實跑觀察 | 跑了什麼或看了什麼 | 實際結果 | 檔案路徑或第幾次工具呼叫 |\n"
                  "沒驗的範圍：…（沒有就寫「無」）")
STATIC_HINT = ("只有靜態檢查：完工回執每一列都是「靜態」層級（lint、typecheck 這類），"
               "標籤應降為【等你決定】，並在回覆寫明「只有靜態檢查」，或補上單元、整合或實跑觀察的驗證。")


@dataclass
class Row:
    item: str
    level: str
    evidence: str

    @property
    def static(self) -> bool:
        return bool(STATIC.search(self.level)) and not NOT_STATIC.search(self.level)


@dataclass
class Receipt:
    rows: list
    has_scope: bool


@dataclass
class Result:
    triggered: bool = False
    label: bool = False
    done_paths: list = field(default_factory=list)
    problems: list = field(default_factory=list)  # (規則代號, 說明)：會擋
    hints: list = field(default_factory=list)  # (規則代號, 說明)：只提示
    receipt_from: str = ""


# ---- 回執 ----

def has_label(text: str) -> bool:
    return bool(LABEL_LINE.search(FENCE.sub("", text or "")))


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_receipt(text: str) -> Receipt | None:
    """找表頭含「層級」與「證據」的表格（程式碼區塊裡的也算）；沒有就回傳 None。"""
    lines = (text or "").splitlines()
    rows, found = [], False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and "層級" in line and "證據" in line:
            found = True
            head = _cells(line)
            level_i = next(k for k, c in enumerate(head) if "層級" in c)
            ev_i = next(k for k, c in enumerate(head) if "證據" in c)
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = _cells(lines[i])
                i += 1
                if all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells):
                    continue  # |---|---| 分隔列
                cells += [""] * (max(level_i, ev_i) + 1 - len(cells))
                rows.append(Row(cells[0], cells[level_i], cells[ev_i]))
            continue
        i += 1
    if not found:
        return None
    return Receipt(rows, any(m.group(1) and m.group(1).strip("*").strip() for m in SCOPE.finditer(text)))


def evidence_paths(cell: str) -> list:
    """證據位置裡看起來是檔案路徑的字串（連結、反引號裡的優先，其餘照空白與頓號切開）。"""
    cands = re.findall(r"\]\(([^)\s]+)\)", cell)
    rest = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", cell)
    cands += re.findall(r"`([^`]+)`", rest)
    rest = re.sub(r"`[^`]*`", " ", rest)
    cands += re.split(r"[\s、，,；;（）()「」]+", rest)
    out = []
    for c in cands:
        c = c.strip().strip("'\"").rstrip("。，,")
        if not c or "://" in c or any(ch in c for ch in "<>*?=|") or c.lower() in NOT_PATHS:
            continue
        c = LINE_SUFFIX.sub("", c)
        if not re.search(r"[^\W\d_]", c):
            continue  # 只有數字與符號：3/3、0.5
        if (c.startswith(("/", "~", "./", "../", ".\\", "..\\")) or re.match(r"^[A-Za-z]:[\\/]", c) or "\\" in c
                or c.endswith(("/", "\\")) or PATH_EXT.search(c)):
            out.append(c)
    return list(dict.fromkeys(out))


def cell_paths(cell: str, base: Path) -> list:
    """整格本身就是一個存在的路徑（含空白、沒包反引號，例如 C:/My Files/a.png）就整格算一個；否則照 evidence_paths 切。"""
    whole = LINE_SUFFIX.sub("", cell.strip().strip("`'\""))
    if whole and "://" not in whole and (" " in whole or "	" in whole):
        try:
            if resolve(whole, base).exists():
                return [whole]
        except (OSError, ValueError):
            pass
    return evidence_paths(cell)


def resolve(raw: str, base: Path) -> Path:
    s = raw
    if os.name == "nt" and re.match(r"^/[a-zA-Z]/", s):
        s = f"{s[1]}:{s[2:]}"  # Git Bash 的 /c/Users/… 寫法
    p = Path(os.path.expanduser(s))
    return p if p.is_absolute() else base / p


def companions(p: Path) -> list:
    """`.done` 對應的交付檔：x.md.done → x.md；x.done → x、x.md、x.txt；最後是 .done 本身。"""
    out = []
    if p.suffix == ".done":
        stem = p.with_suffix("")
        out.append(stem)
        if not stem.suffix:
            out += [stem.with_suffix(".md"), stem.with_suffix(".txt")]
    out.append(p)
    return [c for c in out if c.is_file()]


# ---- git ----

def _git(cwd: str):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}

    def run(args):
        try:
            p = subprocess.run(["git", "-C", cwd, "-c", "core.longpaths=true", *args], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL, env=env, check=False)
            return p.returncode, p.stdout
        except (OSError, subprocess.SubprocessError):
            return 1, ""
    return run


def git_problems(cwd: str, message: str = "", runner=None) -> list:
    run = runner or _git(cwd)
    rc, out = run(["rev-parse", "--is-inside-work-tree"])
    if rc != 0 or out.strip() != "true":
        return []  # 不是 git repo：跳過
    problems = []
    rc, out = run(["status", "--porcelain"])
    changed = [line for line in out.splitlines() if line.strip()] if rc == 0 else []
    if changed:
        sample = "、".join(line[3:].strip() for line in changed[:3])
        problems.append(("git-dirty", f"cwd 的 git 有 {len(changed)} 個未提交的變更（git status --porcelain），例如 {sample}"))
    if LOCAL_ONLY.search(message or ""):
        return problems
    rc, out = run(["rev-list", "--count", "@{u}..HEAD"])
    if rc == 0:
        n = int(out.strip() or 0) if out.strip().isdigit() else 0
        if n:
            problems.append(("git-unpushed", f"cwd 的 git 有 {n} 個 commit 還沒 push（git log @{{u}}..HEAD）"))
        return problems
    rc, remotes = run(["remote"])
    if rc != 0 or not remotes.strip():
        return problems  # 沒有遠端：只查未提交
    rc, _ = run(["rev-parse", "--verify", "-q", "HEAD"])
    if rc != 0:
        return problems
    rc, contained = run(["for-each-ref", "--contains", "HEAD", "--count=1", "--format=%(refname)", "refs/remotes"])
    if rc == 0 and not contained.strip():
        problems.append(("git-unpushed", "cwd 的目前分支沒有設定上游，HEAD 也不在任何遠端分支裡（還沒 push）"))
    return problems


# ---- 判斷 ----

def check(message: str, cwd: str | None = None, session_start: float | None = None, done_paths=(),
          runner=None) -> Result:
    r = Result(label=has_label(message), done_paths=list(done_paths))
    r.triggered = r.label or bool(r.done_paths)
    if not r.triggered:
        return r
    base = Path(cwd) if cwd else Path.cwd()
    text, where = message or "", "這則回覆"
    rc = parse_receipt(text)
    if rc is None:
        for raw in r.done_paths:
            for cand in companions(resolve(raw, base)):
                try:
                    body = cand.read_text(encoding="utf-8", errors="replace")[:MAX_READ]
                except OSError:
                    continue
                if (found := parse_receipt(body)) is not None:
                    rc, text, where = found, body, str(cand)
                    break
            if rc is not None:
                break
    if rc is None:
        r.problems.append(("no-receipt", "沒有完工回執（找不到表頭含「驗證層級」與「證據位置」的表格）"))
    else:
        r.receipt_from = where
        if not rc.rows:
            r.problems.append(("receipt-empty", "完工回執的表格沒有任何一列"))
        if not rc.has_scope:
            r.problems.append(("no-scope", "完工回執沒有「沒驗的範圍：」這一行（沒有也要寫「無」）"))
        missing, stale = [], []
        for row in rc.rows:
            for raw in cell_paths(row.evidence, base):
                p = resolve(raw, base)
                try:
                    if not p.exists():
                        missing.append(raw)
                    elif session_start and p.is_file() and p.stat().st_mtime < session_start - SLACK:
                        stale.append(raw)
                except OSError:
                    continue
        if missing:
            r.problems.append(("evidence-missing", f"證據位置的檔案不存在：{'、'.join(missing[:5])}"))
        if stale:
            r.problems.append(("evidence-stale", f"證據檔的修改時間早於這段對話開始，不是這次產生的：{'、'.join(stale[:5])}"))
        if rc.rows and all(row.static for row in rc.rows):
            r.hints.append(("static-only", STATIC_HINT))
    if r.label and cwd:
        r.problems += git_problems(str(base), message, runner)
    return r


def reason_for(r: Result) -> str:
    why = []
    if r.label:
        why.append(f"這則回覆標了{LABEL}")
    if r.done_paths:
        why.append(f"這一回合寫了 .done（{'、'.join(r.done_paths[:3])}）")
    lines = [f"OmniKit 完工檢查：{'，'.join(why)}，但有機器查得到的缺口（只擋這一次）："]
    lines += [f"- {text}" for _, text in r.problems]
    lines += [f"- {text}" for _, text in r.hints]
    lines.append("照完工回執格式補齊後重新收尾；回執裡每一項都要照實寫，這道閘只檢查機器查得到的部分：")
    lines.append(RECEIPT_FORMAT)
    if any(rule.startswith("git-") for rule, _ in r.problems):
        lines.append(f"git 有未提交或未 push：commit 並 push 後再標{LABEL}；真的不能 push，寫明「只在這台」，"
                     "或改標【進行中】。")
    return "\n".join(lines)


# ---- 讀 hook 輸入 ----

def _epoch(ts) -> float | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp()


def session_start(path: str | None) -> float | None:
    """對話紀錄第一筆有時間的項目（Claude 的 timestamp、Codex 的 payload.timestamp、Antigravity 的 created_at）。"""
    if not path or not Path(path).is_file():
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f):
            if n >= 50:
                break
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not isinstance(e, dict):
                continue
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            t = _epoch(e.get("timestamp")) or _epoch(p.get("timestamp")) or _epoch(e.get("created_at"))
            if t:
                return t
    return None


def _tail_entries(path: str) -> list:
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - TAIL))
        raw = f.read()
    if size > TAIL:
        raw = raw.split(b"\n", 1)[-1]  # 第一行可能只讀到一半
    if b".done" not in raw:
        return []
    out = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def _is_prompt(e: dict, subagent: bool) -> bool:
    if e.get("type") != "user" or e.get("isMeta") or (e.get("isSidechain") and not subagent):
        return False
    content = (e.get("message") or {}).get("content")
    return isinstance(content, str) or any(isinstance(b, dict) and b.get("type") == "text" for b in content or [])


def done_paths_this_turn(path: str | None, subagent: bool = False) -> list:
    """這一回合（最後一則使用者訊息之後）寫的 .done 檔。子代理的對話紀錄每一筆都是 isSidechain，要一起看。"""
    if not path or not Path(path).is_file():
        return []
    entries = _tail_entries(path)
    if not entries:
        return []
    paths = []
    if any(e.get("type") in ("session_meta", "response_item") for e in entries[:5]):
        # Codex 的 rollout：最後一個 task_started 或 user_message 之後的 *call 項目（未實測）
        start = max((i + 1 for i, e in enumerate(entries) if e.get("type") == "event_msg"
                     and (e.get("payload") or {}).get("type") in ("task_started", "user_message")), default=0)
        for e in entries[start:]:
            p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            if e.get("type") == "response_item" and "call" in str(p.get("type") or "") and not str(p.get("type")).endswith("output"):
                for v in (p.get("arguments"), p.get("input"), p.get("action")):
                    if v:
                        paths += DONE_IN_CMD.findall(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
        return list(dict.fromkeys(paths))
    start = max((i + 1 for i, e in enumerate(entries) if _is_prompt(e, subagent)), default=0)
    for e in entries[start:]:
        if e.get("type") != "assistant" or (e.get("isSidechain") and not subagent):
            continue
        for b in (e.get("message") or {}).get("content") or []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
            if b.get("name") in WRITE_TOOLS:
                fp = str(inp.get("file_path") or inp.get("notebook_path") or "")
                if fp.endswith(".done"):
                    paths.append(fp)
            elif b.get("name") in SHELL_TOOLS:
                paths += DONE_IN_CMD.findall(str(inp.get("command") or ""))
    return list(dict.fromkeys(paths))


def agy_last_message(path: str | None) -> str:
    if not path or not Path(path).is_file():
        return ""
    last = ""
    for e in read_jsonl(path):
        if e.get("source") == "MODEL" and e.get("type") == "PLANNER_RESPONSE" and isinstance(e.get("content"), str):
            last = e["content"]
    return last


def normalize(data: dict):
    """Antigravity 的 camelCase（hookEventName、conversationId、transcriptPath、continuationActive）換成同一個形狀。"""
    if not isinstance(data, dict) or "hookEventName" not in data:
        return data, False
    paths = data.get("workspacePaths") if isinstance(data.get("workspacePaths"), list) else []
    return {"hook_event_name": data.get("hookEventName") or "",
            "session_id": data.get("conversationId") or data.get("sessionId") or "",
            "stop_hook_active": bool(data.get("continuationActive")),
            "cwd": data.get("cwd") or (paths[0] if paths else ""),
            "termination_reason": data.get("terminationReason") or "",
            "agy_transcript": data.get("transcriptPath") or ""}, True


def mode_of(env) -> str:
    v = str(env.get("OMNIKIT_DONE_CHECK", "") or "").lower()
    return "off" if v in OFF else ("block" if v == "block" else "log")


def record_tripwire(rule: str, session_id: str, agy: bool, mode: str, event: str, env) -> None:
    if not session_id or str(env.get("OMNIKIT_TRIPWIRE_LOG", "") or "").lower() in OFF:
        return
    try:
        raw = env.get("OMNIKIT_STATE_DIR") or env.get("OMNIKIT_STATE") or \
            os.environ.get("OMNIKIT_STATE_DIR") or os.environ.get("OMNIKIT_STATE")
        p = (Path(raw) if raw else Path.home() / ".omnikit") / "harness" / "tripwire-hits.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "hook": "done_check", "rule": rule,
               "agent": "antigravity" if agy else "claude_or_codex", "mode": mode, "event": event or "Stop"}
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def handle(data: dict, env=None, runner=None):
    """回傳要印的 JSON（dict），或 None（不印）。Antigravity 一律要回 JSON，放行時回 {}。"""
    env = os.environ if env is None else env
    data, agy = normalize(data)
    allow = {} if agy else None
    mode = mode_of(env)
    if mode == "off" or data.get("stop_hook_active"):
        return allow  # 關掉，或已經擋過一次、agent 重新收尾了：放行
    if agy and data.get("termination_reason") not in ("", "NO_TOOL_CALL"):
        return allow  # 出錯、使用者取消、到上限：不是正常收尾
    event = data.get("hook_event_name") or "Stop"
    cwd = data.get("cwd") or os.getcwd()
    if agy:
        message, transcript, done = agy_last_message(data.get("agy_transcript")), data.get("agy_transcript"), []
    else:
        subagent = event == "SubagentStop"
        transcript = (data.get("agent_transcript_path") if subagent else None) or data.get("transcript_path")
        msg = data.get("last_assistant_message")
        message = msg if isinstance(msg, str) else ("" if subagent else last_message(data))
        done = done_paths_this_turn(transcript, subagent)
    r = check(message, cwd=cwd, session_start=session_start(transcript), done_paths=done, runner=runner)
    if not r.triggered:
        return allow
    sid = str(data.get("session_id") or "")
    for rule, _ in r.problems + r.hints:
        record_tripwire(rule, sid, agy, mode, event, env)
    if mode != "block":
        return allow
    if r.problems:
        return {"decision": "continue" if agy else "block", "reason": reason_for(r)}
    if r.hints and not agy:
        return {"systemMessage": f"OmniKit 完工檢查：{r.hints[0][1]}"}
    return allow


def main() -> int:
    try:
        if mode_of(os.environ) == "off":
            return 0
        data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        out = handle(data)
        if out is not None:
            sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    except Exception:  # noqa: BLE001  檢查壞掉不能卡住對話
        return 0
    return 0


# ---- --check 與 --selftest ----

def describe(r: Result) -> list:
    if not r.triggered:
        return ["判斷：沒有完工宣稱，不檢查"]
    lines = [f"判斷：{'有缺口（擋下模式會擋）' if r.problems else '通過'}"
             + (f"；回執在 {r.receipt_from}" if r.receipt_from else "")]
    lines += [f"  缺口 {rule}：{text}" for rule, text in r.problems]
    lines += [f"  提示 {rule}：{text}" for rule, text in r.hints]
    return lines


RECEIPT_OK = ("【完成待收尾】改好了。\n\n## 完工回執\n| 需求項 | 驗證層級 | 驗證指令或觀察 | 結果 | 證據位置 |\n|---|---|---|---|---|\n"
              "| 型別沒壞 | 靜態 | npm run typecheck | exit 0 | 本回合第 4 次工具呼叫 |\n"
              "| 警示改成黃色 | 實跑觀察 | 開面板截圖 | 顏色正確 | 本回合第 9 次工具呼叫 |\n沒驗的範圍：無\n")


def selftest() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    failures = []

    def ok(label, cond):
        print(f"{'通過' if cond else '失敗'}：{label}")
        if not cond:
            failures.append(label)

    def rules(r):
        return {rule for rule, _ in r.problems}

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        env_block = {"OMNIKIT_DONE_CHECK": "block", "OMNIKIT_STATE_DIR": str(base / "st")}
        ok("沒附回執：判定 no-receipt", "no-receipt" in rules(check("【完成待收尾】已驗證桌機與手機，errors=0", cwd=tmp)))
        ok("句中提到標籤不算完工宣稱", not check("收尾時要用【完成待收尾】這類標籤。", cwd=tmp).triggered)
        ok("回執齊全、不在 git repo：通過", not check(RECEIPT_OK, cwd=tmp).problems)
        ok("沒有「沒驗的範圍」：判定 no-scope", "no-scope" in rules(check(RECEIPT_OK.replace("沒驗的範圍：無\n", ""), cwd=tmp)))
        static = RECEIPT_OK.replace("| 實跑觀察 |", "| 靜態 |")
        r = check(static, cwd=tmp)
        ok("只有靜態列：不擋、提示降級", not r.problems and any("只有靜態檢查" in t for _, t in r.hints))
        ok("證據檔不存在：判定 evidence-missing",
           "evidence-missing" in rules(check(RECEIPT_OK.replace("本回合第 9 次工具呼叫", "out/shot.png"), cwd=tmp)))
        ok("證據欄的非路徑字串（3/3、Node.js、第幾次工具呼叫）不當成檔案",
           evidence_paths("3/3 通過、Node.js、本回合第 2 次工具呼叫") == [])
        ok("證據欄的路徑（反引號、行號、連結）", evidence_paths("`a b/c.png`、x.py:12、[看](docs/r.md)")
           == ["docs/r.md", "a b/c.png", "x.py"])
        stale = base / "old.txt"
        stale.write_text("x", encoding="utf-8")
        os.utime(stale, (1_000_000_000, 1_000_000_000))
        ok("證據檔早於對話開始：判定 evidence-stale",
           "evidence-stale" in rules(check(RECEIPT_OK.replace("本回合第 9 次工具呼叫", str(stale)), cwd=tmp,
                                           session_start=1_500_000_000)))
        fake = {("rev-parse", "--is-inside-work-tree"): (0, "true\n"), ("status", "--porcelain"): (0, ""),
                ("rev-list", "--count", "@{u}..HEAD"): (0, "2\n")}
        ok("git 有未 push 的 commit：判定 git-unpushed",
           "git-unpushed" in rules(check(RECEIPT_OK, cwd=tmp, runner=lambda a: fake.get(tuple(a), (1, "")))))
        ok("寫明只在這台：不查未 push",
           not rules(check(RECEIPT_OK.replace("改好了。", "改好了，只在這台。"), cwd=tmp,
                           runner=lambda a: fake.get(tuple(a), (1, "")))))
        ok("git 逾時或出錯：跳過不擋", not rules(check(RECEIPT_OK, cwd=tmp, runner=lambda a: (1, ""))))
        bad = {"hook_event_name": "Stop", "session_id": "s", "cwd": tmp,
               "last_assistant_message": "【完成待收尾】已驗證，errors=0"}
        ok("記錄模式：不擋，寫一筆 tripwire",
           handle(bad, env={"OMNIKIT_STATE_DIR": str(base / "st")}) is None
           and '"done_check"' in (base / "st" / "harness" / "tripwire-hits.jsonl").read_text(encoding="utf-8"))
        out = handle(bad, env=env_block)
        ok("擋下模式：印 decision block 與回執格式", out["decision"] == "block" and "完工回執" in out["reason"])
        ok("stop_hook_active：放行", handle({**bad, "stop_hook_active": True}, env=env_block) is None)
        ok("OMNIKIT_DONE_CHECK=off：關掉", handle(bad, env={"OMNIKIT_DONE_CHECK": "off"}) is None)
        tr = base / "t.jsonl"
        tr.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in [
            {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {"content": "做完寫 .done"}},
            {"type": "assistant", "message": {"id": "m", "content": [
                {"type": "tool_use", "id": "t", "name": "Write", "input": {"file_path": str(base / "r.md.done")}}]}}]) + "\n",
            encoding="utf-8")
        ok("這一回合寫了 .done：找得到路徑", done_paths_this_turn(str(tr)) == [str(base / "r.md.done")])
        ok("對話開始時間取第一筆", session_start(str(tr)) == _epoch("2026-01-01T00:00:00Z"))
        (base / "r.md").write_text(RECEIPT_OK, encoding="utf-8")
        ok("回執寫在交付檔：通過",
           handle({"hook_event_name": "Stop", "cwd": tmp, "last_assistant_message": "寫好了。",
                   "transcript_path": str(tr)}, env=env_block) is None)
        agy = base / "a.jsonl"
        agy.write_text(json.dumps({"type": "PLANNER_RESPONSE", "source": "MODEL", "content": bad["last_assistant_message"],
                                   "created_at": "2026-01-01T00:00:00Z"}, ensure_ascii=False) + "\n", encoding="utf-8")
        a = {"hookEventName": "Stop", "conversationId": "c", "transcriptPath": str(agy), "cwd": tmp,
             "terminationReason": "NO_TOOL_CALL"}
        ok("Antigravity：擋下模式回 decision continue，continuationActive 回 {}",
           handle(a, env=env_block)["decision"] == "continue" and handle({**a, "continuationActive": True}, env=env_block) == {})
        # 整支跑起來：壞 JSON 安靜結束
        p = subprocess.run([sys.executable, __file__], input=b"not json", capture_output=True, check=False,
                           env={**os.environ, **env_block})
        ok("壞輸入：exit 0、不印東西", p.returncode == 0 and p.stdout == b"")
    print(f"\n{'done_check selftest OK' if not failures else f'done_check selftest 失敗：{len(failures)} 項'}")
    return 1 if failures else 0


def arg_after(flag: str, default=None):
    i = sys.argv.index(flag)
    return sys.argv[i + 1] if len(sys.argv) > i + 1 and not sys.argv[i + 1].startswith("--") else default


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--check" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        arg = arg_after("--check", "-")
        text = sys.stdin.buffer.read().decode("utf-8") if arg == "-" else Path(arg).read_text(encoding="utf-8")
        cwd = arg_after("--cwd") if "--cwd" in sys.argv else os.getcwd()
        print("\n".join(describe(check(text, cwd=cwd))))
        sys.exit(0)
    sys.exit(main())
