# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Agent Harness 確定性護欄（Claude Code 的 PreToolUse、PostToolUse、Stop hook，跨專案共用）。

為什麼要有：提示詞與 skill（例如 ponytail 的 SessionStart 注入）是機率性的，長對話裡會衰減；
agent 為了讓檢查變綠，常見的捷徑（reward hacking）是繞過 hook、把 lint 規則關掉、或把機密檔讀進對話。
這支只做「確定性」的事：看工具呼叫的參數，擋下或把 linter 的輸出回饋給 agent。

一、PreToolUse（擋下時印 permissionDecision: deny，理由會回給 agent）
  1. 防繞過：`git commit --no-verify`／`-n`、`git push --no-verify`、`git -c core.hooksPath=…`、`HUSKY=0 git commit`、
     `SKIP=… git commit`（pre-commit／prek 的跳過變數）。
  2. 機密檔不進對話：Read／Grep 讀 `.env`、`.env.local`、`*.pem`、`*.key`、`*.secret.key`、`cookies*.txt`、`id_rsa` 這類檔，
     或 Bash 用 cat、type、Get-Content、head、tail、less、grep、sed… 讀它們。範例檔（`.env.example`、`.env.sample`、
     `.env.template`、`*.example.pem`…）放行；只看檔名或存不存在（ls、test -f、git check-ignore）不擋。
  3. 門禁設定不准偷關：Edit／Write／MultiEdit 改 linter 或 hook 設定（pyproject.toml、ruff.toml、.eslintrc*、eslint.config.*、
     .stylelintrc*、stylelint.config.*、biome.json、.oxlintrc.json、.pre-commit-config.yaml、setup.cfg、tox.ini…），
     一次新增 3 個以上的 ignore／disable／skip 類項目就擋，要 agent 改程式碼而不是關規則；1、2 個放行，
     PostToolUse 時提醒一次。使用者真的要放寬：設 OMNIKIT_LINT_RELAX=allow。
二、PostToolUse：改完 `.py`／`.pyi` 時，本機有 ruff 就對那一個檔案跑 `ruff check --output-format concise --no-fix`
   （毫秒級），有錯就用 decision: block 把輸出回給 agent 當場修；沒裝 ruff、逾時或任何錯誤都安靜略過。
   改過的 .py 記在 ~/.omnikit/harness/edited-<session>.json，給 Stop 用。
三、Stop：這段對話改過的 .py 還有 ruff 錯誤，就擋回去一次；第二次收尾（stop_hook_active）一定放行，不會無限迴圈。

所有錯誤都安靜結束（exit 0），檢查壞掉不能卡住對話。OMNIKIT_HARNESS=off 整個關掉。
註冊範圍：Claude Code（薄 plugin 與 claude_allow.py 備案）與 Antigravity（薄 plugin）。輸入同時吃 Claude Code／Codex 的
snake_case（hook_event_name、tool_name、tool_input）與 Antigravity 的 camelCase（hookEventName、toolCall.name 為
run_command／write_file／edit_file、toolCall.args、continuationActive），見 normalize()。Antigravity 的 PostToolUse
只收空 JSON {}、不能注入文字，所以只記下改過的檔案、一律回 {}，ruff 問題在 Stop 擋（continuationActive 當
stop_hook_active，第二次放行）；PreToolUse 放行回傳官方必填的 {"decision": "allow"}，攔截回傳 {"decision": "deny", "reason": ...}。

用法：uv run engine/scripts/harness_hooks.py             從 stdin 讀 hook 輸入（hook 用）
      uv run engine/scripts/harness_hooks.py --selftest
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

OFF = ("0", "off", "false", "no")
RUFF_TIMEOUT = 10
MAX_FEEDBACK = 3000
RELAX_BLOCK_AT = 3  # 一次新增這麼多個 ignore／disable／skip 類項目就擋


def state_dir() -> Path:
    raw = os.environ.get("OMNIKIT_STATE")
    return Path(raw) if raw else Path.home() / ".omnikit"


# ---------- 1. 防繞過 ----------

QUOTED = re.compile(r"\"(?:\\.|[^\"\\])*\"|'[^']*'")
SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\||\n|`|\$\(")


def _strip_quotes(cmd: str) -> str:
    return QUOTED.sub(" ", cmd)


def _git_segments(cmd: str):
    """拆成一段一段的指令，回傳 (環境變數前綴, git 之後的 token) ；不是 git 的段落略過。"""
    for seg in SEGMENT_SPLIT.split(_strip_quotes(cmd)):
        toks = seg.split()
        env = []
        while toks and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", toks[0]):
            env.append(toks.pop(0))
        if toks and toks[0] in ("env", "command", "sudo"):
            toks = toks[1:]
            while toks and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", toks[0]):
                env.append(toks.pop(0))
        if toks and re.fullmatch(r"(?:.*[/\\])?git(?:\.exe)?", toks[0]):
            yield env, toks[1:]


def _subcommand(args):
    """跳過 git 的全域參數，回傳 (子指令, 子指令後面的參數, 全域參數)。"""
    glob = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-c", "-C", "--git-dir", "--work-tree", "--namespace"):
            glob += args[i:i + 2]
            i += 2
            continue
        if a.startswith("-"):
            glob.append(a)
            i += 1
            continue
        return a, args[i + 1:], glob
    return None, [], glob


def bypass_reason(cmd: str):
    """git 指令有繞過 hook 的寫法就回傳原因，沒有就 None。"""
    for env, args in _git_segments(cmd or ""):
        sub, rest, glob = _subcommand(args)
        if any(re.match(r"core\.hookspath=", g, re.IGNORECASE) for g in glob) or any("hookspath" in g.lower() for g in glob):
            return "用 -c core.hooksPath 換掉 hook 目錄會跳過 pre-commit 門禁"
        if sub not in ("commit", "push", "merge", "am", "rebase", "cherry-pick"):
            continue
        if "--no-verify" in rest:
            return f"git {sub} --no-verify 會跳過 pre-commit／pre-push 門禁"
        if sub == "commit":
            for t in rest:
                if t == "--":
                    break
                if re.fullmatch(r"-[A-Za-z]+", t) and "n" in t[1:t.find("m") if "m" in t else len(t)]:
                    return "git commit -n（--no-verify 的短寫）會跳過 pre-commit 門禁"
        for e in env:
            k, _, v = e.partition("=")
            if k == "HUSKY" and v == "0":
                return "HUSKY=0 會關掉 husky 的 git hook"
            if k in ("SKIP", "PRE_COMMIT_ALLOW_NO_CONFIG", "PREK_SKIP") and v:
                return f"{k}=… 會讓 pre-commit／prek 跳過檢查"
    return None


# ---------- 2. 機密檔 ----------

SAMPLE = re.compile(r"(?i)(?:^|[._-])(?:example|sample|template|dist|tmpl|defaults?|schema)(?:[._-]|$)")
SECRET_NAME = re.compile(
    r"(?i)^(?:[\w.-]*\.env(?:\.[\w-]+)*|[\w.-]+\.pem|[\w.-]+\.key|[\w.-]*\.secret(?:\.[\w-]+)*|[\w.-]*secrets?\.(?:json|ya?ml|toml)"
    r"|cookies?[\w.-]*\.txt|id_(?:rsa|ed25519|ecdsa|dsa)|[\w.-]+\.p12|[\w.-]+\.pfx|\.netrc|\.pgpass|credentials(?:\.json)?)$")
READ_VERBS = {"cat", "type", "get-content", "gc", "head", "tail", "less", "more", "bat", "batcat", "sed", "awk", "grep",
              "rg", "egrep", "fgrep", "findstr", "select-string", "sls", "nl", "od", "xxd", "hexdump", "strings", "base64",
              "openssl", "jq", "yq", "python", "python3", "py", "node", "iconv", "tac", "cut", "sort", "uniq", "diff",
              "scp", "curl", "wget", "source", "export", "dotenv"}
CODE_EXT = re.compile(r"(?i)\.(?:py|pyi|js|mjs|cjs|ts|tsx|jsx|vue|svelte|go|rs|java|cs|rb|php|md|mdx|html|css|scss|sh|ps1)$")


def is_secret_path(path: str) -> bool:
    name = re.split(r"[/\\]", str(path or "").strip().strip("\"'"))[-1]
    if not name or not SECRET_NAME.match(name) or CODE_EXT.search(name):
        return False
    return not SAMPLE.search(name)


def secret_read_reason(tool: str, inp: dict):
    if tool in ("Read", "NotebookRead"):
        p = inp.get("file_path") or inp.get("notebook_path") or ""
        if is_secret_path(p):
            return f"不把機密檔 {Path(p).name} 讀進對話（安全底線：不讀取、不印出金鑰）"
    if tool == "Grep":
        p = inp.get("path") or ""
        if p and is_secret_path(p):
            return f"不搜尋機密檔 {Path(p).name} 的內容進對話"
    if tool in ("Bash", "PowerShell"):
        cmd = inp.get("command") or ""
        for seg in SEGMENT_SPLIT.split(cmd):
            try:
                toks = shlex.split(seg, posix=(tool != "PowerShell"))
            except ValueError:
                toks = []
            toks = [t for t in dict.fromkeys(toks + seg.split()) if t]
            if not toks:
                continue
            verbs = {re.split(r"[/\\]", t)[-1].lower().removesuffix(".exe") for t in toks}
            redirect_in = "<" in seg
            hits = [t for t in toks if is_secret_path(t) or any(is_secret_path(x) for x in re.split(r"[<>=]", t))]
            if hits and (verbs & READ_VERBS or redirect_in):
                return f"不用 shell 把機密檔 {Path(hits[0].strip('<>')).name} 的內容讀進對話；要用的話請程式從環境變數讀"
    return None


# ---------- 3. 門禁設定不准偷關 ----------

LINT_CONFIG = re.compile(
    r"(?i)(?:^|[/\\])(?:pyproject\.toml|ruff\.toml|\.ruff\.toml|setup\.cfg|tox\.ini|\.flake8|mypy\.ini|\.mypy\.ini|pyrightconfig\.json"
    r"|\.eslintrc(?:\.\w+)?|eslint\.config\.\w+|\.stylelintrc(?:\.\w+)?|stylelint\.config\.\w+|biome\.jsonc?|\.oxlintrc\.json"
    r"|\.pre-commit-config\.ya?ml|prek\.toml|lefthook\.ya?ml|\.importlinter|knip\.jsonc?|\.knip\.jsonc?)$")
RELAX_TOKENS = re.compile(
    r"(?i)\b(?:ignore|extend-ignore|per-file-ignores|ignorePatterns|ignores|disable|disabled|skip|exclude|extend-exclude|off|"
    r"reportGeneralTypeIssues|typeCheckingMode)\b|[\"']off[\"']|=\s*[\"']?off|# *noqa|eslint-disable|stylelint-disable|"
    r"\bstages:\s*\[\s*manual\s*\]")
RULE_CODE = re.compile(r"\b[A-Z]{1,4}\d{2,4}\b|[\"'][@\w/-]+[\"']\s*:\s*(?:[\"']off[\"']|0)")


def _relax_count(old: str, new: str) -> int:
    """新增的放寬項目數：新內容比舊內容多出來的 ignore／disable 類關鍵字，加上新增的規則代碼（在 ignore 區附近）。"""
    def score(text):
        n = 0
        for line in (text or "").splitlines():
            if RELAX_TOKENS.search(line):
                n += 1 + max(0, len(RULE_CODE.findall(line)) - 1)
            elif RULE_CODE.search(line) and re.search(r"(?i)ignore|disable|off", line):
                n += len(RULE_CODE.findall(line))
        return n
    return max(0, score(new) - score(old))


def lint_relax(tool: str, inp: dict):
    """(新增的放寬數, 檔名)；不是門禁設定檔就 (0, None)。"""
    p = inp.get("file_path") or ""
    if not LINT_CONFIG.search(p):
        return 0, None
    if tool == "Edit":
        n = _relax_count(inp.get("old_string"), inp.get("new_string"))
    elif tool == "MultiEdit":
        n = sum(_relax_count(e.get("old_string"), e.get("new_string")) for e in inp.get("edits") or [] if isinstance(e, dict))
    elif tool == "Write":
        try:
            old = Path(p).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            old = ""
        n = _relax_count(old, inp.get("content"))
    else:
        return 0, None
    return n, Path(p).name


# ---------- ruff ----------

def ruff_exe():
    return os.environ.get("OMNIKIT_RUFF") or shutil.which("ruff")


def run_ruff(path: str, runner=None):
    """回傳 ruff 的錯誤輸出（沒有錯誤、沒裝或失敗都回 None）。"""
    exe = ruff_exe()
    if not exe and runner is None:
        return None
    cmd = [exe or "ruff", "check", "--output-format", "concise", "--no-fix", "--quiet", path]
    try:
        if runner is not None:
            rc, out = runner(cmd)
        else:
            r = subprocess.run(cmd, capture_output=True, timeout=RUFF_TIMEOUT, cwd=str(Path(path).parent) or None)
            rc, out = r.returncode, (r.stdout or b"").decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return None
    if rc == 1 and out.strip():
        return out.strip()[:MAX_FEEDBACK]
    return None  # 0 沒問題；2 以上是 ruff 自己的錯誤（設定壞了），不怪 agent


def issue_keys(out):
    """ruff concise 輸出 → 不含行號的問題鍵（規則代碼＋訊息），用來比對「這次新增的」問題。"""
    keys = []
    for line in (out or "").splitlines():
        m = re.match(r"^.*?:\d+:\d+:\s*(.+)$", line.strip())
        if m:
            keys.append(re.sub(r"\s*\[\*\]\s*", " ", m.group(1)).strip())
    return keys


def new_issues(out, baseline):
    """只留比改之前多出來的問題（同一種問題出現次數變多才算）；舊債不怪這次的修改。"""
    if not out:
        return None
    left = Counter(baseline or [])
    kept = []
    for line in out.splitlines():
        k = issue_keys(line)
        if not k:
            continue
        if left[k[0]] > 0:
            left[k[0]] -= 1
            continue
        kept.append(line)
    return "\n".join(kept) if kept else None


def _session_file(sid: str) -> Path:
    h = hashlib.sha256((sid or "nosession").encode("utf-8")).hexdigest()[:16]
    return state_dir() / "harness" / f"edited-{h}.json"


def _load_session(sid: str) -> dict:
    try:
        cur = json.loads(_session_file(sid).read_text(encoding="utf-8"))
        return cur if isinstance(cur, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_session(sid: str, doc: dict):
    f = _session_file(sid)
    if len(doc) > 50:
        doc = dict(list(doc.items())[-50:])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def remember_baseline(sid: str, path: str, runner=None):
    """改 .py 之前記下這個檔案原本就有的 ruff 問題（同一段對話只記第一次）。"""
    doc = _load_session(sid)
    if path in doc:
        return
    doc[path] = {"baseline": issue_keys(run_ruff(path, runner)) if Path(path).is_file() else []}
    _save_session(sid, doc)


def remember_edit(sid: str, path: str):
    doc = _load_session(sid)
    if path not in doc:
        doc[path] = {"baseline": []}
        _save_session(sid, doc)


def edited_files(sid: str) -> dict:
    return {p: (v.get("baseline") if isinstance(v, dict) else []) for p, v in _load_session(sid).items()}


# ---------- hook 本身 ----------

def deny(reason: str, agy: bool = False) -> dict:
    msg = f"OmniKit 護欄：{reason}"
    if agy:
        return {"decision": "deny", "reason": msg}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": msg}}


AGY_TOOLS = {"run_command": "Bash", "write_file": "Write", "edit_file": "Edit", "read_file": "Read",
             "view_file": "Read", "grep_search": "Grep"}
AGY_ARGS = {"command": ("command", "commandLine", "CommandLine", "cmd"),
            "file_path": ("file_path", "filePath", "path", "TargetFile", "targetFile", "AbsolutePath", "absolutePath"),
            "content": ("content", "CodeContent", "codeContent", "fileContent"),
            "old_string": ("old_string", "oldString", "TargetContent", "targetContent"),
            "new_string": ("new_string", "newString", "ReplacementContent", "replacementContent")}


def normalize(data: dict):
    """Claude Code／Codex 的 snake_case（hook_event_name、tool_name、tool_input）原樣用；
    Antigravity 的 camelCase（hookEventName、toolCall.name、toolCall.args、continuationActive）換成同一個形狀。
    回傳 (data, 是不是 Antigravity)。Antigravity 的參數鍵名依工單轉述的 agy hooks.md，未在本機一手核對，多收幾種寫法。"""
    if not isinstance(data, dict) or ("toolCall" not in data and "hookEventName" not in data):
        return data, False
    call = data.get("toolCall") if isinstance(data.get("toolCall"), dict) else {}
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    inp = {}
    for key, names in AGY_ARGS.items():
        for n in names:
            if isinstance(args.get(n), str):
                inp[key] = args[n]
                break
    name = call.get("name") or ""
    out = {"hook_event_name": data.get("hookEventName") or "", "tool_name": AGY_TOOLS.get(name, name),
           "tool_input": inp, "session_id": data.get("sessionId") or data.get("conversationId") or "",
           "stop_hook_active": bool(data.get("continuationActive"))}
    return out, True


def handle(data: dict, runner=None, env=None):
    """回傳要印的 JSON（dict）或 None（放行、不印）。
    Antigravity 的 PostToolUse 只收空 JSON {}、不能把文字注入給模型：照樣記下改過的 .py，ruff 的問題留到 Stop 再擋。"""
    env = os.environ if env is None else env
    data, agy = normalize(data)
    if agy and data.get("hook_event_name") == "PostToolUse":
        tool, inp = data["tool_name"], data["tool_input"]
        path = inp.get("file_path") or ""
        if tool in ("Edit", "Write", "MultiEdit") and re.search(r"\.pyi?$", path, re.IGNORECASE) and Path(path).is_file():
            remember_edit(data.get("session_id") or "", path)
        return {}
    event = data.get("hook_event_name") or ""
    tool = data.get("tool_name") or ""
    inp = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}

    if event == "PreToolUse":
        if tool in ("Bash", "PowerShell"):
            why = bypass_reason(inp.get("command") or "")
            if why:
                return deny(f"{why}。請修好讓檢查通過，不要繞過；真的要跳過請使用者自己下指令。", agy)
        why = secret_read_reason(tool, inp)
        if why:
            return deny(why + "。範例檔（.env.example 等）可以讀。", agy)
        if tool in ("Edit", "Write", "MultiEdit"):
            fp = inp.get("file_path") or ""
            if re.search(r"\.pyi?$", fp, re.IGNORECASE) and (runner is not None or ruff_exe()):
                remember_baseline(data.get("session_id") or "", fp, runner)
            n, name = lint_relax(tool, inp)
            if n >= RELAX_BLOCK_AT and str(env.get("OMNIKIT_LINT_RELAX", "")).lower() != "allow":
                return deny(f"這次修改在 {name} 一次新增 {n} 個 ignore／disable／skip 類項目，看起來是在關掉門禁規則。"
                            "請改程式碼讓檢查通過；使用者明確要放寬時，請他設 OMNIKIT_LINT_RELAX=allow。", agy)
        return {"decision": "allow"} if agy else None

    if event == "PostToolUse":
        if tool not in ("Edit", "Write", "MultiEdit"):
            return None
        path = inp.get("file_path") or ""
        n, name = lint_relax(tool, inp) if tool != "Write" else (0, None)
        if n:
            return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
                    f"OmniKit 護欄提醒：剛在 {name} 新增 {n} 個 ignore／disable 類項目。確定是使用者要的嗎？不是的話改回來、改修程式碼。"}}
        if not re.search(r"\.pyi?$", path, re.IGNORECASE) or not Path(path).is_file():
            return None
        sid = data.get("session_id") or ""
        remember_edit(sid, path)
        out = new_issues(run_ruff(path, runner), edited_files(sid).get(path))
        if out:
            return {"decision": "block", "reason": f"OmniKit 護欄：ruff 在 {Path(path).name} 找到問題，請當場修好：\n{out}"}
        return None

    if event == "Stop":
        if data.get("stop_hook_active"):
            return {} if agy else None  # 已經擋過一次、agent 重新收尾了：放行，不無限迴圈
        problems = []
        for p, base in edited_files(data.get("session_id") or "").items():
            if Path(p).is_file():
                out = new_issues(run_ruff(p, runner), base)
                if out:
                    problems.append(out)
        if problems:
            text = "\n".join(problems)[:MAX_FEEDBACK]
            reason_msg = f"OmniKit 護欄：這段對話改過的 Python 檔還有 ruff 錯誤，修好再收尾（只擋這一次）：\n{text}"
            return {"decision": "continue" if agy else "block", "reason": reason_msg}
        return {} if agy else None
    return None


def main() -> int:
    try:
        if os.environ.get("OMNIKIT_HARNESS", "").lower() in OFF:
            return 0
        data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
        out = handle(data)
        if out is not None:
            sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    except Exception:  # noqa: BLE001  檢查壞掉不能卡住對話
        return 0
    return 0


# ---------- 自我測試 ----------

def selftest() -> int:
    failures = []

    def ok(label, cond):
        print(("通過：" if cond else "失敗：") + label)
        if not cond:
            failures.append(label)

    def pre(tool, **inp):
        return handle({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": inp}, env={})

    def denied(r):
        return bool(r) and r["hookSpecificOutput"]["permissionDecision"] == "deny"

    blocked_cmds = [
        "git commit --no-verify -m 'x'", "git commit -n -m x", "git commit -anm wip", "git add . && git commit -nm x",
        "git -c core.hooksPath=/dev/null commit -m x", "HUSKY=0 git commit -m x", "SKIP=ruff git commit -m x",
        "git push --no-verify origin main", "cd repo; git commit --no-verify", "/usr/bin/git commit -n",
    ]
    allowed_cmds = [
        "git commit -m 'fix: handle -n flag and --no-verify docs'", "git commit -am 'msg'", "git log -n 5",
        "git status", "git commit -m \"說明 --no-verify 為什麼被擋\"", "npm run lint -- --no-verify-ssl",
        "git commit --amend --no-edit", "git rev-list -n 1 HEAD", "echo git commit --no-verify > notes.txt",
        "git commit -F msg.txt", "git diff --name-only",
    ]
    ok("防繞過：--no-verify、-n、-anm、core.hooksPath、HUSKY=0、SKIP=、push --no-verify 全擋",
       all(denied(pre("Bash", command=c)) for c in blocked_cmds))
    wrong = [c for c in allowed_cmds if denied(pre("Bash", command=c))]
    ok(f"防繞過不誤擋：訊息裡的字、git log -n、--amend、其他工具的同名參數放行（誤擋 {wrong}）",
       not wrong)

    sec_block = [("Read", {"file_path": "C:/proj/.env"}), ("Read", {"file_path": "/a/.env.local"}),
                 ("Read", {"file_path": "/a/server.pem"}), ("Read", {"file_path": "/a/prod.secret.key"}),
                 ("Read", {"file_path": "/a/cookies-x.txt"}), ("Read", {"file_path": "/home/u/.ssh/id_rsa"}),
                 ("Grep", {"pattern": "KEY", "path": ".env"}),
                 ("Bash", {"command": "cat .env"}), ("Bash", {"command": "type config\\.env.production"}),
                 ("PowerShell", {"command": "Get-Content .\\.env"}), ("Bash", {"command": "grep TOKEN .env | head"}),
                 ("Bash", {"command": "python -c 'print(1)' < secrets.json"})]
    sec_allow = [("Read", {"file_path": "/a/.env.example"}), ("Read", {"file_path": "/a/.env.sample"}),
                 ("Read", {"file_path": "/a/.env.template"}), ("Read", {"file_path": "/a/README.md"}),
                 ("Read", {"file_path": "/a/env.py"}), ("Read", {"file_path": "/a/keyboard.ts"}),
                 ("Bash", {"command": "ls -la .env"}), ("Bash", {"command": "test -f .env && echo yes"}),
                 ("Bash", {"command": "git check-ignore .env"}), ("Bash", {"command": "cp .env.example .env.example.bak"}),
                 ("Bash", {"command": "cat .env.example"}), ("Grep", {"pattern": "x", "path": "src"}),
                 ("Bash", {"command": "cp .env.example .env"}), ("Read", {"file_path": "/a/src/config.env.ts"}),
                 ("Bash", {"command": "git add . && git commit -m 'add .env.example'"})]
    ok("機密檔：Read／Grep／Bash／PowerShell 讀 .env、.pem、.secret.key、cookies*.txt、id_rsa 全擋",
       all(denied(pre(t, **i)) for t, i in sec_block))
    wrong = [i for t, i in sec_allow if denied(pre(t, **i))]
    ok(f"機密檔不誤擋：.env.example 等範例檔、只看存不存在、一般檔案放行（誤擋 {wrong}）", not wrong)

    relax_old = "[tool.ruff.lint]\nselect = [\"F\", \"E\"]\n"
    relax_new = relax_old + "ignore = [\"F401\", \"E501\", \"F841\", \"E722\"]\nper-file-ignores = {\"*\" = [\"ALL\"]}\n"
    ok("門禁設定：pyproject.toml 一次新增大量 ignore 就擋",
       denied(pre("Edit", file_path="/p/pyproject.toml", old_string=relax_old, new_string=relax_new)))
    ok("門禁設定：OMNIKIT_LINT_RELAX=allow 時放行",
       handle({"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {
           "file_path": "/p/pyproject.toml", "old_string": relax_old, "new_string": relax_new}},
           env={"OMNIKIT_LINT_RELAX": "allow"}) is None)
    eslint_new = "export default [{ rules: { 'no-unused-vars': 'off', 'no-undef': 'off', 'vue/no-v-html': 'off' } }]"
    ok("門禁設定：eslint.config.js 一次關三條規則就擋",
       denied(pre("Write", file_path="/p/eslint.config.js", content=eslint_new)))
    ok("門禁設定：一般修改（加 select、改版本、改非門禁檔）放行",
       pre("Edit", file_path="/p/pyproject.toml", old_string=relax_old, new_string=relax_old.replace('"E"]', '"E", "B"]')) is None
       and pre("Edit", file_path="/p/pyproject.toml", old_string='version = "1"', new_string='version = "2"') is None
       and pre("Edit", file_path="/p/app.py", old_string="a", new_string="# ignore off skip disable\n" * 5) is None)
    one = handle({"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {
        "file_path": "/p/ruff.toml", "old_string": "", "new_string": "ignore = [\"E501\"]"}}, env={})
    ok("門禁設定：只加 1 個 ignore 放行，PostToolUse 提醒一次",
       pre("Edit", file_path="/p/ruff.toml", old_string="", new_string="ignore = [\"E501\"]") is None
       and one and "additionalContext" in one["hookSpecificOutput"])

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["OMNIKIT_STATE"] = tmp
        try:
            py = Path(tmp) / "mod.py"
            py.write_text("import os\n", encoding="utf-8")
            calls = []

            def fake_bad(cmd):
                calls.append(cmd)
                return 1, f"{cmd[-1]}:1:8: F401 [*] `os` imported but unused\n"

            def fake_good(cmd):
                calls.append(cmd)
                return 0, ""
            post = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "session_id": "s1",
                    "tool_input": {"file_path": str(py), "old_string": "", "new_string": "import os"}}
            r = handle(post, runner=fake_bad, env={})
            ok("PostToolUse：改 .py 後對單一檔案跑 ruff check --output-format concise，有錯回 decision: block",
               r and r["decision"] == "block" and "F401" in r["reason"]
               and calls[0][1:5] == ["check", "--output-format", "concise", "--no-fix"] and calls[0][-1] == str(py))
            ok("PostToolUse：沒錯不印", handle(post, runner=fake_good, env={}) is None)
            # 舊債：改之前就有的同一種問題不回報，只回報這次新增的
            legacy = Path(tmp) / "legacy.py"
            legacy.write_text("import os\n", encoding="utf-8")
            pre_l = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "s2",
                     "tool_input": {"file_path": str(legacy), "old_string": "a", "new_string": "b"}}
            handle(pre_l, runner=fake_bad, env={})
            post_l = {**pre_l, "hook_event_name": "PostToolUse"}
            r_same = handle(post_l, runner=fake_bad, env={})

            def fake_more(cmd):
                return 1, (f"{cmd[-1]}:1:8: F401 [*] `os` imported but unused\n"
                           f"{cmd[-1]}:3:1: F821 Undefined name `foo`\n")
            r_more = handle(post_l, runner=fake_more, env={})
            ok("PostToolUse：舊債不回報，只回報這次新增的問題（F821）",
               r_same is None and bool(r_more) and "F821" in r_more["reason"] and "F401" not in r_more["reason"])
            ok("Stop：只有舊債時不擋", handle({"hook_event_name": "Stop", "session_id": "s2"}, runner=fake_bad, env={}) is None)
            ok("PostToolUse：非 .py、Read、檔案不存在都略過",
               handle({**post, "tool_input": {"file_path": str(Path(tmp) / "a.ts")}}, runner=fake_bad, env={}) is None
               and handle({**post, "tool_name": "Read"}, runner=fake_bad, env={}) is None
               and handle({**post, "tool_input": {"file_path": str(Path(tmp) / "gone.py")}}, runner=fake_bad, env={}) is None)

            def boom(cmd):
                raise OSError("no ruff")
            ok("PostToolUse：ruff 跑不起來（沒裝、逾時）安靜略過", handle(post, runner=boom, env={}) is None)
            ok("PostToolUse：ruff 自己出錯（rc=2，設定壞掉）不怪 agent", run_ruff(str(py), runner=lambda c: (2, "config error")) is None)
            old_path = os.environ.get("PATH")
            old_ruff = os.environ.pop("OMNIKIT_RUFF", None)
            os.environ["PATH"] = tmp
            try:
                ok("沒裝 ruff 時 run_ruff 回 None、不報錯", run_ruff(str(py)) is None)
            finally:
                os.environ["PATH"] = old_path or ""
                if old_ruff is not None:
                    os.environ["OMNIKIT_RUFF"] = old_ruff

            stop = {"hook_event_name": "Stop", "session_id": "s1"}
            r1 = handle(stop, runner=fake_bad, env={})
            r2 = handle({**stop, "stop_hook_active": True}, runner=fake_bad, env={})
            ok("Stop：改過的 .py 還有 ruff 錯誤擋一次；stop_hook_active 時一定放行（不無限迴圈）",
               r1 and r1["decision"] == "block" and r2 is None)
            ok("Stop：其他對話（session 不同）不受影響、ruff 通過也放行",
               handle({**stop, "session_id": "other"}, runner=fake_bad, env={}) is None
               and handle(stop, runner=fake_good, env={}) is None)
        finally:
            os.environ.pop("OMNIKIT_STATE", None)

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["OMNIKIT_STATE"] = tmp
        try:
            py = Path(tmp) / "agy.py"
            py.write_text("import os\n", encoding="utf-8")
            def bad(cmd):
                return 1, f"{cmd[-1]}:1:8: F401 `os` imported but unused\n"
            a_pre = handle({"hookEventName": "PreToolUse", "toolCall": {"name": "run_command",
                            "args": {"CommandLine": "git commit --no-verify -m x"}}}, env={})
            a_sec = handle({"hookEventName": "PreToolUse", "toolCall": {"name": "view_file",
                            "args": {"AbsolutePath": "C:/p/.env"}}}, env={})
            a_ok = handle({"hookEventName": "PreToolUse", "toolCall": {"name": "run_command",
                           "args": {"CommandLine": "git status"}}}, env={})
            ok("Antigravity camelCase：原生 decision=deny 擋 --no-verify 與讀 .env，正常指令回 decision=allow 放行",
               a_pre.get("decision") == "deny" and a_sec.get("decision") == "deny" and a_ok == {"decision": "allow"})
            a_post = handle({"hookEventName": "PostToolUse", "sessionId": "ag1", "toolCall": {"name": "write_file",
                             "args": {"TargetFile": str(py)}}}, runner=bad, env={})
            a_stop1 = handle({"hookEventName": "Stop", "sessionId": "ag1"}, runner=bad, env={})
            a_stop2 = handle({"hookEventName": "Stop", "sessionId": "ag1", "continuationActive": True}, runner=bad, env={})
            ok("Antigravity：PostToolUse 回 {}，問題留到 Stop 回 decision=continue 擋一次，continuationActive 回 {} 放行",
               a_post == {} and a_stop1 and a_stop1["decision"] == "continue" and a_stop2 == {})
        finally:
            os.environ.pop("OMNIKIT_STATE", None)

    ok("其他事件、壞輸入不印", handle({}) is None and handle({"hook_event_name": "SessionStart"}) is None
       and handle({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": "x"}) is None)

    # 整支跑起來：stdin → stdout、OMNIKIT_HARNESS=off 關掉、壞 JSON 安靜結束
    me = str(Path(__file__).resolve())
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_input": {"command": "git commit --no-verify"}}).encode("utf-8")
    r_on = subprocess.run([sys.executable, me], input=payload, capture_output=True)
    r_off = subprocess.run([sys.executable, me], input=payload, capture_output=True, env={**os.environ, "OMNIKIT_HARNESS": "off"})
    r_bad = subprocess.run([sys.executable, me], input=b"{not json", capture_output=True)
    ok("hook 進出：擋的時候印 permissionDecision deny、可關閉、壞輸入 exit 0 不印",
       r_on.returncode == 0 and b'"deny"' in r_on.stdout and r_off.stdout == b"" and r_bad.returncode == 0 and r_bad.stdout == b"")

    print(f"\n{'harness_hooks.py selftest：全部通過' if not failures else f'harness_hooks.py selftest：{len(failures)} 項失敗'}")
    return 1 if failures else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.exit(selftest())
    sys.exit(main())
