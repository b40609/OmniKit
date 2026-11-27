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
1. 沒有完工回執：找不到表頭含「驗證層級」與「證據位置」的表格（程式碼區塊裡的不算，原樣貼出的範本佔位列也不算）。
   表格的格子照 Markdown 切：反引號裡的 | 與跳脫的 \\| 不是分隔。回覆裡沒有時，也看 `.done` 對應的交付檔
   （`x.md.done` 看 `x.md`，`x.done` 看 `x.md`、`x.txt` 與 `.done` 本身），回執寫在交付檔裡也算。
2. 回執沒有「沒驗的範圍：」這一行（沒有也要寫「無」）。
3. 證據位置是檔案路徑的：檔案要存在，修改時間要在這段對話開始之後（對話開始時間取對話紀錄的第一筆時間；
   那筆時間沒帶時區就不知道是本機時間還是 UTC，跳過這項不擋。三家本機紀錄實際都帶 Z）。
4. 標了【完成待收尾】：cwd 的 git 有未提交（git status --porcelain）或未 push（@{u}..HEAD；沒設上游時看 HEAD
   在不在任何遠端分支裡）。不是 git repo、沒有遠端、git 出錯或逾時都跳過不擋。回覆寫明「只在這台」時不查未 push
   （使用者規則對【完成待收尾】的定義：不能 push 的寫明只在這台）；程式碼區塊、行內程式碼與否定句（不是只在這台）不算。
5. 回執每一列都是「靜態」層級：不擋，只提示把標籤降為【等你決定】並寫明「只有靜態檢查」。

模式（環境變數 OMNIKIT_DONE_CHECK，未設時讀 ~/.omnikit/kit.yaml 的 done_check，預設為 block）：
- block（預設）：有第 1 到 4 條、反假綠燈作弊（fake-green）或改程式卻無實跑證據（no-runtime-proof）的缺口就擋一次
  （Claude Code／Codex 印 decision: block，Antigravity 印 decision: continue），只有第 5 條時印 systemMessage 提示。
- log：只把命中寫進 ~/.omnikit/harness/tripwire-hits.jsonl（格式同 claim_check.py，多記 mode 與 event），
  不擋、不印任何東西。
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
NEGATIONS = ("不是", "並非", "不", "非", "沒有", "未必")  # 「不是只在這台」「不只在這台」不算宣告
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
STATIC = re.compile(r"靜態|static|lint|typecheck|型別檢查", re.IGNORECASE)
NOT_STATIC = re.compile(r"單元|unit|整合|integration|實跑|觀察|端到端|e2e|截圖|人工|手動|manual", re.IGNORECASE)
RUNTIME_PROOF = re.compile(r"整合|integration|實跑|觀察|端到端|e2e|瀏覽器|browser|webkit|playwright|截圖|人工|手動|manual", re.IGNORECASE)
CODE_EXTS = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".html", ".css", ".ps1", ".sh"}
DONE_CLAIM_TEXT = re.compile(r"(?:已完成|已經完成|修好了|已經幫你.*修好|全部通過|測試全過|改好了|done\b|all tests pass)", re.IGNORECASE)
FAKE_GREEN_LINE_RE = re.compile(
    r"(?:\b(?:it|test|describe)\.skip\s*\(\s*['\"`]|\b(?:xit|xdescribe|xtest)\s*\(|@pytest\.mark\.skip\b(?!if)|@unittest\.skip\s*\()"
)
TEST_FILE_NAME_RE = re.compile(r"(?:^test_|_test\.py$|\.(?:test|spec)\.[A-Za-z0-9]+$)", re.IGNORECASE)

PATH_EXT = re.compile(r"\.[A-Za-z][A-Za-z0-9]{1,7}$")
LINE_SUFFIX = re.compile(r"(?::\d+(?:[-:]\d+)?|#L\d+(?:-L?\d+)?)$")
NOT_PATHS = {"node.js", "vue.js", "next.js", "nuxt.js", "three.js", "chart.js", "d3.js", "express.js", "socket.io",
             "asp.net", "vite.js"}
# shell 指令裡的 *.done：先找引號包住的（路徑可以有空白），其餘照沒有空白的一段找（done_in_cmd，線性時間）
DONE_QUOTED = re.compile(r""""([^"\r\n]+\.done)"|'([^'\r\n]+\.done)'""")
CMD_TOKEN = re.compile(r"""[^\s"'`<>|;&()]+""")
DONE_END = re.compile(r"\.done(?![\w.\-])")
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

    @property
    def has_runtime(self) -> bool:
        return bool(RUNTIME_PROOF.search(self.level))


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
    return bool(LABEL_LINE.search(strip_fences(text or "")))


def strip_fences(text: str) -> str:
    """拿掉 fenced code block（``` 或 ~~~，三個以上；沒關的到結尾為止），每行換成空行，行數不變。"""
    out, fence = [], None
    for line in (text or "").splitlines():
        if fence is None:
            m = FENCE_OPEN.match(line)
            if m:
                fence = m.group(1)
            out.append("" if m else line)
            continue
        if re.match(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", line):
            fence = None
        out.append("")
    return "\n".join(out)


def _code_mask(line: str) -> list:
    """一行裡每個字元在不在行內程式碼裡。反引號要配到同樣長度的才算一段，配不到的照字面（線性時間）。"""
    runs = [(m.start(), m.end()) for m in re.finditer(r"`+", line)]
    nxt, last = [None] * len(runs), {}
    for i in range(len(runs) - 1, -1, -1):
        n = runs[i][1] - runs[i][0]
        nxt[i], last[n] = last.get(n), i
    mask = [False] * len(line)
    i = 0
    while i < len(runs):
        j = nxt[i]
        if j is None:
            i += 1
            continue
        mask[runs[i][0]:runs[j][1]] = [True] * (runs[j][1] - runs[i][0])
        i = j + 1
    return mask


def _cells(line: str) -> list:
    """表格一列切成格子：反引號裡的 | 與跳脫的 \\| 不是分隔（GFM 的規則），不然欄位會右移、證據欄讀錯格。"""
    s = line.strip().removeprefix("|")
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    code = _code_mask(s)
    cells, cur, i = [], [], 0
    while i < len(s):
        if s[i] == "\\" and s[i + 1:i + 2] == "|":
            cur.append("|")
            i += 2
            continue
        if s[i] == "|" and not code[i]:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(s[i])
        i += 1
    cells.append("".join(cur).strip())
    return cells


TEMPLATE_ROW = _cells(RECEIPT_FORMAT.splitlines()[3])  # 範本的佔位列：原樣貼出來不算一列
SCOPE_PLACEHOLDER = SCOPE.search(RECEIPT_FORMAT).group(1).strip()  # 「…（沒有就寫「無」）」不算有寫


def _scope_filled(value) -> bool:
    v = (value or "").strip("*").strip()
    return bool(v.strip("….。 ")) and v != SCOPE_PLACEHOLDER


def parse_receipt(text: str) -> Receipt | None:
    """找表頭含「層級」與「證據」的表格；沒有就回傳 None。
    程式碼區塊裡的不算（貼出來的範本或例子不能自己通過），範本的佔位列也不算一列。"""
    text = strip_fences(text)
    lines = text.splitlines()
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
                if cells == TEMPLATE_ROW:
                    continue  # 範本的佔位列
                cells += [""] * (max(level_i, ev_i) + 1 - len(cells))
                rows.append(Row(cells[0], cells[level_i], cells[ev_i]))
            continue
        i += 1
    if not found:
        return None
    return Receipt(rows, any(_scope_filled(m.group(1)) for m in SCOPE.finditer(text)))


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


def local_only(message: str) -> bool:
    """回覆宣告了「只在這台」：程式碼區塊、行內程式碼與否定句（不是只在這台、並非只在這台、不只在這台）不算。"""
    for line in strip_fences(message).splitlines():
        if "只在這台" not in line:
            continue
        code = _code_mask(line)
        for m in LOCAL_ONLY.finditer(line):
            if code[m.start()] or line[max(0, m.start() - 4):m.start()].rstrip().endswith(NEGATIONS):
                continue
            return True
    return False


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
    if local_only(message):
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


def _is_test_or_ci_rel(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    name = norm.rsplit("/", 1)[-1]
    return bool(TEST_FILE_NAME_RE.search(name)) or (norm.startswith(".github/workflows/") and norm.endswith((".yml", ".yaml")))


def fakegreen_problems(cwd: str, runner=None, only_files: set[str] | None = None) -> list:
    """掃描工作區 git diff HEAD 與新建未追蹤測試檔是否偷加無條件假綠燈跳過標記（排除條件式 test.skip(cond, reason)）。"""
    run = runner or _git(cwd)
    exempt = {"engine/scripts/wiring_audit.py", "engine/scripts/done_check.py", "engine/scripts/cleanroom_e2e.py"}
    rc, out = run(["diff", "HEAD", "--unified=0"])
    if rc == 0 and out.strip():
        cur_file = ""
        for line in out.splitlines():
            if line.startswith("+++ b/"):
                cur_file = line[6:].strip()
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            if cur_file in exempt or cur_file.endswith(".md"):
                continue
            if only_files is not None and cur_file not in only_files:
                continue
            added = line[1:].strip()
            if not added or added.startswith(("#", "//", "/*", "*")):
                continue
            if FAKE_GREEN_LINE_RE.search(added):
                return [("fake-green", f"偵測到新增假綠燈跳過標記（{cur_file}：{added[:90]}），請修好測試而非跳過")]

    # 補掃新建尚未 git add 的 untracked 測試檔（堵住漏網）
    rc_u, untracked_out = run(["ls-files", "--others", "--exclude-standard"])
    if rc_u == 0 and untracked_out.strip():
        base = Path(cwd)
        for rel in untracked_out.splitlines():
            rel = rel.strip()
            if not rel or rel in exempt or not _is_test_or_ci_rel(rel):
                continue
            if only_files is not None and rel not in only_files:
                continue
            fp = base / rel
            if not fp.is_file():
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")[:MAX_READ]
            except OSError:
                continue
            for raw_ln in content.splitlines():
                s = raw_ln.strip()
                if not s or s.startswith(("#", "//", "/*", "*")):
                    continue
                if FAKE_GREEN_LINE_RE.search(s):
                    return [("fake-green", f"新建測試檔含有假綠燈跳過標記（{rel}：{s[:90]}），請修好測試而非跳過")]
    return []


def turn_edit_summary(path: str | None, cwd: str | None = None, subagent: bool = False) -> tuple[bool, set[str]]:
    """回傳（這一回合是否改過非測試程式碼/前端檔, 這一回合寫入過的相對路徑集合）。"""
    if not path or not Path(path).is_file():
        return False, set()
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - TAIL))
            raw = f.read()
    except OSError:
        return False, set()
    lines = raw.decode("utf-8", errors="replace").splitlines()
    entries = []
    for ln in lines:
        try:
            e = json.loads(ln)
            if isinstance(e, dict):
                entries.append(e)
        except ValueError:
            continue
    start = max((i + 1 for i, e in enumerate(entries) if _is_prompt(e, subagent)), default=0)
    base_res = Path(cwd).resolve() if cwd else None
    changed_app_code = False
    rel_touched: set[str] = set()

    def _record_fp(raw_fp: str) -> None:
        nonlocal changed_app_code
        if not raw_fp:
            return
        fp = Path(raw_fp)
        name_low = fp.name.lower()
        if fp.suffix.lower() in CODE_EXTS and not TEST_FILE_NAME_RE.search(name_low):
            changed_app_code = True
        if base_res is not None:
            try:
                rel_touched.add(fp.resolve().relative_to(base_res).as_posix())
            except (OSError, ValueError):
                pass

    for e in entries[start:]:
        if e.get("type") == "assistant":
            for b in (e.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in WRITE_TOOLS:
                    inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                    _record_fp(str(inp.get("file_path") or ""))
        elif e.get("source") == "MODEL" and e.get("type") == "TOOL_CALL":
            _record_fp(str((e.get("args") or {}).get("Path") or ""))
    return changed_app_code, rel_touched


def edited_code_this_turn(path: str | None, subagent: bool = False) -> bool:
    return turn_edit_summary(path, None, subagent)[0]


# ---- 判斷 ----

def check(message: str, cwd: str | None = None, session_start: float | None = None, done_paths=(),
          runner=None, changed_code: bool = False, touched_files: set[str] | None = None) -> Result:
    r = Result(label=has_label(message), done_paths=list(done_paths))
    claims_done_plain = bool(DONE_CLAIM_TEXT.search(strip_fences(message or "")))
    fg_hits = []
    if cwd and (r.label or r.done_paths or claims_done_plain or touched_files):
        scope_files = None if (r.label or r.done_paths or claims_done_plain) else touched_files
        fg_hits = fakegreen_problems(str(Path(cwd)), runner, only_files=scope_files)
    r.triggered = r.label or bool(r.done_paths) or (bool(fg_hits) and bool((message or "").strip()))
    if not r.triggered:
        return r
    if fg_hits:
        r.problems.extend(fg_hits)
        if not (r.label or r.done_paths):
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
        elif changed_code and rc.rows and not any(row.has_runtime for row in rc.rows):
            r.problems.append((
                "no-runtime-proof",
                "這一回合修改了程式、前端或腳本，但完工回執只有靜態或離線單元測試，缺少「實跑觀察／整合／端到端／瀏覽器」驗證證據（防假完工閘門）",
            ))
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

def _parse_ts(ts):
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _epoch(ts) -> float | None:
    """ISO 8601 轉 epoch。沒帶時區的回傳 None：不知道是本機時間還是 UTC，不拿來判斷（硬套 UTC 在 UTC+8 會差 8 小時）。"""
    dt = _parse_ts(ts)
    if dt is None or dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.timestamp()


def session_start(path: str | None) -> float | None:
    """對話紀錄第一筆有時間的項目（Claude 的 timestamp、Codex 的 payload.timestamp、Antigravity 的 created_at）。
    那筆時間沒帶時區就回傳 None（跳過 evidence-stale），不往後找：後面的時間比對話開始晚，拿來比反而會誤擋。
    三家本機紀錄實際都帶 Z（2026-11-28 查過：Claude、Codex 是 ...dd.dddZ，Antigravity 是 ...ddZ）。"""
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
            for raw in (e.get("timestamp"), p.get("timestamp"), e.get("created_at")):
                if _parse_ts(raw) is not None:
                    return _epoch(raw)
    return None


def done_in_cmd(cmd: str) -> list:
    """shell 指令裡寫到的 *.done 路徑，照出現順序。先找引號包住的（可以含空白，例如 "…/my reports/out.md.done"），
    其餘照沒有空白的一段找、取那段裡最後一個 .done。都是線性時間：很長、沒有空白的指令也不會二次方回溯。"""
    found, masked, pos = [], [], 0
    for m in DONE_QUOTED.finditer(cmd):
        found.append((m.start(), m.group(1) or m.group(2)))
        masked += [cmd[pos:m.start()], " " * (m.end() - m.start())]
        pos = m.end()
    masked.append(cmd[pos:])
    for m in CMD_TOKEN.finditer("".join(masked)):
        ends = [d.end() for d in DONE_END.finditer(m.group()) if d.start() > 0]
        if ends:
            found.append((m.start(), m.group()[:ends[-1]]))
    return [path for _, path in sorted(found)]


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
                        paths += done_in_cmd(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
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
                paths += done_in_cmd(str(inp.get("command") or ""))
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


def _parse_kit_done_check(txt: str) -> str | None:
    """精準解析 kit.yaml 內 active_profile 對應段落的 done_check 值（零外部相依，修盲審 P0-1）。"""
    active = "default"
    for line in txt.splitlines():
        m_act = re.match(r"^active_profile:\s*(\S+)", line)
        if m_act:
            active = m_act.group(1).strip("'\"") or "default"
            break
    in_profiles = False
    in_target_prof = False
    for raw in txt.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if indent == 0:
            in_profiles = stripped == "profiles:"
            in_target_prof = False
            continue
        if in_profiles and indent == 2 and stripped.endswith(":"):
            pname = stripped[:-1].strip("'\"")
            in_target_prof = pname == active
            continue
        if in_profiles and in_target_prof and indent == 4:
            m_dc = re.match(r"^done_check:\s*(\S+)", stripped)
            if m_dc:
                return m_dc.group(1).strip("'\"").lower()
    return None


def mode_of(env) -> str:
    v = str(env.get("OMNIKIT_DONE_CHECK", "") or "").strip().lower()
    if v in OFF:
        return "off"
    if v in ("log", "block"):
        return v
    # 未指定環境變數時，讀取 ~/.omnikit/kit.yaml 中目前 active_profile 的 done_check 設定；預設為 block
    try:
        raw_st = env.get("OMNIKIT_STATE_DIR") or env.get("OMNIKIT_STATE") or os.environ.get("OMNIKIT_STATE_DIR")
        st_dir = Path(raw_st) if raw_st else Path.home() / ".omnikit"
        kit_f = st_dir / "kit.yaml"
        if kit_f.is_file():
            kv = _parse_kit_done_check(kit_f.read_text(encoding="utf-8", errors="replace"))
            if kv in OFF:
                return "off"
            if kv == "log":
                return "log"
            if kv == "block":
                return "block"
    except OSError:
        pass
    return "block"


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
        transcript = data.get("agy_transcript")
        message, done = agy_last_message(transcript), []
        changed_code, touched_files = turn_edit_summary(transcript, cwd, False)
    else:
        subagent = event == "SubagentStop"
        transcript = (data.get("agent_transcript_path") if subagent else None) or data.get("transcript_path")
        msg = data.get("last_assistant_message")
        message = msg if isinstance(msg, str) else ("" if subagent else last_message(data))
        done = done_paths_this_turn(transcript, subagent)
        changed_code, touched_files = turn_edit_summary(transcript, cwd, subagent)
    r = check(message, cwd=cwd, session_start=session_start(transcript), done_paths=done, runner=runner,
              changed_code=changed_code, touched_files=touched_files)
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
        ok("否定句、程式碼裡的「只在這台」不算：照查未 push", all(
            "git-unpushed" in rules(check(RECEIPT_OK.replace("改好了。", extra), cwd=tmp,
                                          runner=lambda a: fake.get(tuple(a), (1, ""))))
            for extra in ("改好了，不是只在這台。", "改好了。規則寫 `只在這台`。")))
        ok("表格格子：反引號裡與跳脫的 | 不是分隔", _cells("| a | `x|y` | b \\| c |") == ["a", "`x|y`", "b | c"])
        ok("程式碼區塊裡、原樣貼出的回執範本不能自己通過",
           "no-receipt" in rules(check(f"{LABEL}\n```\n{RECEIPT_FORMAT}\n```\n", cwd=tmp))
           and {"receipt-empty", "no-scope"} <= rules(check(f"{LABEL}\n{RECEIPT_FORMAT}\n", cwd=tmp)))
        ok("含空白、引號包住的 .done 路徑整段抓", done_in_cmd("echo ok > \"a b/c.md.done\" && touch x.done")
           == ["a b/c.md.done", "x.done"])
        ok("沒帶時區的時間不拿來判斷對話開始", _epoch("2026-01-01T00:00:00") is None
           and _epoch("2026-01-01T00:00:00Z") is not None)
        bad = {"hook_event_name": "Stop", "session_id": "s", "cwd": tmp,
               "last_assistant_message": "【完成待收尾】已驗證，errors=0"}
        ok("預設模式為 block（防假完工硬攔截）：沒設環境變數時直接印 decision block",
           handle(bad, env={"OMNIKIT_STATE_DIR": str(base / "st")})["decision"] == "block")
        ok("記錄模式（OMNIKIT_DONE_CHECK=log）：不擋，寫一筆 tripwire",
           handle(bad, env={"OMNIKIT_DONE_CHECK": "log", "OMNIKIT_STATE_DIR": str(base / "st")}) is None
           and '"done_check"' in (base / "st" / "harness" / "tripwire-hits.jsonl").read_text(encoding="utf-8"))
        unit_only = RECEIPT_OK.replace("| 實跑觀察 |", "| 單元 |")
        ok("改程式碼卻只有單元測試無實跑證據：判定 no-runtime-proof 擋回",
           "no-runtime-proof" in rules(check(unit_only, cwd=tmp, changed_code=True))
           and "no-runtime-proof" not in rules(check(RECEIPT_OK, cwd=tmp, changed_code=True)))
        fake_fg = {("diff", "HEAD", "--unified=0"): (0, "+++ b/tests/x.test.js\n+  test.skip('skip broken', () => {})\n")}
        ok("一般用戶沒寫狀態標籤但宣稱修好且偷加無條件 test.skip：自動觸發 fake-green 攔截",
           "fake-green" in rules(check("已經幫你把功能修好了！", cwd=tmp, runner=lambda a: fake_fg.get(tuple(a), (1, "")))))
        cond_fg = {("diff", "HEAD", "--unified=0"): (0, "+++ b/tests/x.spec.ts\n+  test.skip(process.platform === 'darwin', 'mac only')\n")}
        ok("Playwright 條件式 test.skip(cond, reason) 與一般討論回合不誤擋",
           not check("已經幫你把功能修好了！", cwd=tmp, runner=lambda a: cond_fg.get(tuple(a), (1, ""))).problems
           and not check("請問下一步要做哪一頁？", cwd=tmp, runner=lambda a: fake_fg.get(tuple(a), (1, ""))).triggered)
        kit_sample = (
            "schema: 1\nactive_profile: personal\nprofiles:\n"
            "  default:\n    done_check: block\n  personal:\n    done_check: 'off'\n"
        )
        (base / "st_multi").mkdir(parents=True, exist_ok=True)
        (base / "st_multi" / "kit.yaml").write_text(kit_sample, encoding="utf-8")
        ok("P0-1 回歸：kit.yaml 同時有 default(block) 與 personal(off) 時，精準讀 active_profile=personal 回傳 off",
           mode_of({"OMNIKIT_STATE_DIR": str(base / "st_multi")}) == "off")
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
