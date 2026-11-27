# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""副作用量測：指令前後各做一次檔案快照（SHA-256），允許清單外有變動就列出來並 exit 非 0（D10 改動 3）。

為什麼：唯讀審查只看 git status，看不到被 .gitignore 的資料夾（例如 private/data）與家目錄底下的設定資料夾
（例如 ~/.demo-bot）。測試在那裡覆寫資料檔或留下鎖檔，審查照樣寫「沒改任何檔」。
要宣稱「沒改檔」「唯讀完成」，回執裡要有一列是這支的輸出；唯讀任務要跑測試，就包在 run 裡。

用法：
  uv run engine/scripts/fs_guard.py snapshot <根目錄…> --out before.json [--ignore <glob>…] [--no-default-ignore]
  uv run engine/scripts/fs_guard.py diff before.json [after.json] [--allow <路徑或 glob>…] [--full-hash] [--json]
  uv run engine/scripts/fs_guard.py run --watch <根目錄…> [--allow <路徑或 glob>…] [--ignore <glob>…] [--full-hash] \\
      [--no-default-ignore] [--report <檔>] -- <指令…>
  uv run engine/scripts/fs_guard.py --selftest

  diff 只給 before.json 時，照快照裡記的根目錄現在再掃一次來比；給兩個檔就比兩份快照。

比對規則：
- 只比內容雜湊，不比修改時間：只碰時間戳不算變動。
- 預篩：之後那次快照，大小與修改時間都跟之前一樣就沿用之前的雜湊、不重讀，大目錄才跑得快；
  --full-hash 一律重讀（大小與修改時間都被刻意還原的改寫，只有 --full-hash 抓得到）。
- 內建忽略：__pycache__、.pytest_cache、.ruff_cache 資料夾不記錄。*.log 檔照記：新增或只在後面附加
  （之前的內容一個位元組都沒變）不算失敗，另外列出；刪除、清空、改寫照算允許清單外的變動。
  --no-default-ignore 把這兩項都關掉（快取資料夾照記、log 附加也算變動）；設定記在快照裡，diff 照快照的設定。
  其他用 --ignore（不記錄）或 --allow（照列出來，但不算失敗）。
- --allow 不含萬用字元（* ? [）的是字面路徑：相對路徑只比對「相對於根目錄」的那一個與它底下的檔，
  絕對路徑比對絕對路徑；不比對子資料夾裡的同名檔（--allow report.md 不會放行 private/data/report.md）。
  交付檔寫絕對路徑或相對於根目錄的路徑；--allow out 放行根目錄的整個 out 資料夾。
- 含萬用字元的用 fnmatch：「相對於根目錄的路徑」、它的上層資料夾、絕對路徑、檔名任一個對上就算；`*` 可以跨資料夾。
  路徑裡字面的 [ ]（例如 [id] 資料夾）先照字面比，比不上才當萬用字元。例：--allow "out/*"、--allow "*.tmp"。
- --ignore 同上，另外不含萬用字元的名稱也比對任一層的檔名與資料夾名（--ignore node_modules）。
- Windows 不分大小寫：--allow 與兩份快照的路徑（C:\\ 與 c:\\）都照不分大小寫對齊。
- 根目錄不存在也可以監看（當成空的），之後出現的檔都算新增。
- 符號連結與 junction 不跟進，只記它指向哪裡。
- 讀不到內容的檔（被鎖住、沒權限）記下原因，只比大小與修改時間，並在輸出標明。
  連大小與修改時間都讀不到（資料夾不能列出、檔案資訊讀不到），就列為「無法確認」，算在允許清單外：不能背書沒改檔。
- .git 資料夾不在內建忽略：監看 repo 根目錄時，git 指令改了索引也會列出來，要的話 --allow ".git/*"。
- 抓不到：指令結束之後才由背景行程寫的檔。

結束碼：0 沒有允許清單外的變動；3 有（含讀不到而無法確認的）；run 時被包住的指令失敗就傳出它的結束碼（變動清單照印）；
        127 找不到要包住的指令；2 用法錯誤或讀不到快照。成功字樣只在全部比完之後、最後一行印。
"""
import argparse
import fnmatch
import hashlib
import json
import os
import posixpath
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fsretry import retry  # 防毒短暫鎖住剛寫好的檔時等一下再試（FR-34）

SPEC = 1
BUILTIN_IGNORE_DIRS = ("__pycache__", ".pytest_cache", ".ruff_cache")
APPEND_ONLY_FILES = ("*.log",)  # 預設：新增或只在後面附加不算失敗；刪除、清空、改寫照算
WILDCARDS = "*?["
EXIT_CHANGED = 3
EXIT_USAGE = 2
EXIT_NOT_FOUND = 127
KIND_LABEL = {"added": "新增", "modified": "修改", "deleted": "刪除", "unverified": "無法確認"}
CHUNK = 1 << 20


class SnapshotError(Exception):
    """快照檔讀不到或格式不對。"""


# ---- 比對 glob ----

def _rel_candidates(rel):
    """相對路徑本身與每一層上層資料夾：out/sub/a.json → out/sub/a.json、out、out/sub。"""
    parts = rel.split("/")
    yield rel
    for i in range(1, len(parts)):
        yield "/".join(parts[:i])


def _rel_key(p):
    """相對路徑的比對鍵：去掉 ./ 與多餘的分隔字元（Windows 的 \\ 也算分隔），再照系統規則統一大小寫。"""
    if os.name == "nt":
        p = p.replace("\\", "/")
    return os.path.normcase(posixpath.normpath(p))


def _under(path, prefix):
    """path 是 prefix 本身或在它底下（兩邊都已經是比對鍵）。"""
    return path == prefix or path.startswith(prefix.rstrip(os.sep) + os.sep)


def _is_abs(g):
    return os.path.isabs(g) or (os.name == "nt" and g[:1] in ("/", "\\"))


def matches(globs, rel, abspath, anywhere=False):
    """--allow／--ignore 的比對（規則見檔頭）。anywhere=True（--ignore）時，不含萬用字元的名稱也比對任一層的名稱。"""
    if not globs:
        return False
    rel_k, abs_k = _rel_key(rel), os.path.normcase(abspath)
    name = rel.rsplit("/", 1)[-1]
    for g in map(str, globs):
        if not g:
            continue
        # 字面路徑：路徑本身或它底下；[id] 這類字面的方括號也在這裡對上
        if _is_abs(g):
            if _under(abs_k, os.path.normcase(os.path.abspath(g))):
                return True
        else:
            gk = _rel_key(g)
            if gk != "." and not gk.startswith(".." + os.sep) and _under(rel_k, gk):
                return True
        wild = any(ch in g for ch in WILDCARDS)
        if (wild or anywhere) and fnmatch.fnmatch(name, g):
            return True
        if wild and (fnmatch.fnmatch(abspath, g) or any(fnmatch.fnmatch(c, g) for c in _rel_candidates(rel))):
            return True
    return False


def _append_only(rel):
    name = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, g) for g in APPEND_ONLY_FILES)


# ---- 快照 ----

def _is_link(entry):
    """符號連結或 Windows junction（Python 3.11 的 DirEntry 沒有 is_junction）。"""
    if entry.is_symlink():
        return True
    try:
        tag = getattr(entry.stat(follow_symlinks=False), "st_reparse_tag", 0)
    except OSError:
        return False
    return tag == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1)


def _sha256(path, prefix_len=None):
    """整個檔的 SHA-256。給 prefix_len 時同一次讀檔另外算前 prefix_len 個位元組的雜湊，回傳 (整檔, 前段或 None)。"""
    h = hashlib.sha256()
    prefix, seen = None, 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            if prefix_len is not None and prefix is None and seen + len(chunk) >= prefix_len:
                cut = prefix_len - seen
                h.update(chunk[:cut])
                prefix = h.copy().hexdigest()
                h.update(chunk[cut:])
            else:
                h.update(chunk)
            seen += len(chunk)
    return h.hexdigest() if prefix_len is None else (h.hexdigest(), prefix)


def _iter_entries(root, ignores, defaults=True):
    """走過一個根目錄，產生 (相對路徑, 絕對路徑, DirEntry 或 None)。內建忽略與 --ignore 的資料夾整個跳過。"""
    if os.path.isfile(root) or (os.path.islink(root) and not os.path.isdir(root)):
        yield os.path.basename(root), root, None
        return
    if not os.path.isdir(root):
        return
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as e:
            rel = os.path.relpath(d, root).replace(os.sep, "/")
            yield rel, d, e
            continue
        for e in entries:
            rel = os.path.relpath(e.path, root).replace(os.sep, "/")
            if not _is_link(e) and e.is_dir(follow_symlinks=False):
                if (defaults and e.name in BUILTIN_IGNORE_DIRS) or matches(ignores, rel, e.path, anywhere=True):
                    continue
                stack.append(e.path)
                continue
            if matches(ignores, rel, e.path, anywhere=True):
                continue
            yield rel, e.path, e


def _record(path, entry, prev, full_hash, counter, append_check=False):
    """一個檔的紀錄：大小、修改時間、SHA-256；連結記指向哪裡；讀不到記原因。
    append_check（*.log）：檔變大時另外記之前那段的雜湊（prefix_sha256），比對時看是不是只在後面附加。"""
    try:
        st = entry.stat(follow_symlinks=False) if entry is not None else os.stat(path, follow_symlinks=False)
    except OSError as e:
        return {"error": f"讀不到檔案資訊：{e}"}
    rec = {"size": st.st_size, "mtime_ns": st.st_mtime_ns}
    is_link = stat.S_ISLNK(st.st_mode) or (
        getattr(st, "st_reparse_tag", 0) == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1))
    if is_link:
        try:
            rec["link"] = os.readlink(path)
        except OSError as e:
            rec["error"] = f"讀不到連結：{e}"
        return rec
    if (not full_hash and prev and prev.get("sha256") and prev.get("size") == rec["size"]
            and prev.get("mtime_ns") == rec["mtime_ns"]):
        rec["sha256"] = prev["sha256"]
        counter["reused"] += 1
        return rec
    prefix_len = None
    if (append_check and prev and prev.get("sha256") and isinstance(prev.get("size"), int)
            and rec["size"] > prev["size"]):
        prefix_len = prev["size"]
    try:
        if prefix_len is None:
            rec["sha256"] = retry(_sha256, path)
        else:
            rec["sha256"], prefix = retry(_sha256, path, prefix_len)
            if prefix is not None:
                rec["prefix_size"], rec["prefix_sha256"] = prefix_len, prefix
        counter["hashed"] += 1
    except OSError as e:
        rec["error"] = f"讀不到內容：{e}"
    return rec


def take_snapshot(roots, ignores=(), prev=None, full_hash=False, exclude=(), defaults=True):
    """掃過每個根目錄。prev 是之前的快照（拿來預篩與判斷 log 附加），exclude 是不記的絕對路徑（例如快照檔自己）。
    defaults=False（--no-default-ignore）：快取資料夾也記，log 附加也算變動。"""
    excluded = {os.path.normcase(os.path.abspath(p)) for p in exclude}
    prev_files = {os.path.normcase(k): v for k, v in (prev or {}).get("files", {}).items()}
    counter = {"hashed": 0, "reused": 0}
    files, seen = {}, set()
    root_info = []
    for idx, raw in enumerate(roots):
        root = os.path.abspath(str(raw))
        root_info.append({"path": root, "exists": os.path.exists(root)})
        for rel, path, entry in _iter_entries(root, list(ignores), defaults):
            key = os.path.normcase(path)
            if key in excluded or key in seen:
                continue
            seen.add(key)
            if isinstance(entry, OSError):
                files[path] = {"root": idx, "rel": rel, "error": f"讀不到資料夾：{entry}"}
                continue
            rec = _record(path, entry, prev_files.get(key), full_hash, counter,
                          append_check=defaults and _append_only(rel))
            files[path] = {"root": idx, "rel": rel, **rec}
    return {
        "spec": SPEC,
        "tool": "fs_guard",
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "roots": root_info,
        "ignore": list(ignores),
        "default_ignore": bool(defaults),
        "files": files,
        "stats": counter,
    }


def load_snapshot(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SnapshotError(f"讀不到快照 {path}：{e}") from e
    if not isinstance(data, dict) or data.get("tool") != "fs_guard" or data.get("spec") != SPEC:
        raise SnapshotError(f"讀不到快照 {path}：不是 fs_guard 第 {SPEC} 版的快照")
    if not isinstance(data.get("roots"), list) or not isinstance(data.get("files"), dict):
        raise SnapshotError(f"讀不到快照 {path}：少了 roots 或 files")
    return data


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    retry(tmp.write_text, json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    retry(os.replace, tmp, path)


# ---- 比對 ----

def _same(b, a):
    """(一樣嗎, 備註)。兩邊都有雜湊就比雜湊；連結比指向；有一邊讀不到就退回比大小與修改時間；
    連大小與修改時間都沒有（資料夾不能列出、檔案資訊讀不到）回傳 None：無法確認，不能當成一樣。"""
    if "link" in b or "link" in a:
        return b.get("link") == a.get("link"), ""
    if b.get("sha256") and a.get("sha256"):
        return b["sha256"] == a["sha256"], ""
    if any(x.get(k) is None for x in (b, a) for k in ("size", "mtime_ns")):
        return None, "讀不到檔案資訊，無法確認有沒有變動"
    note = "讀不到內容，只比大小與修改時間"
    return (b.get("size") == a.get("size") and b.get("mtime_ns") == a.get("mtime_ns")), note


def _appended(b, a):
    """log 只在後面附加：變大了，而且之前那段的雜湊跟之前整個檔一樣。"""
    return bool(b.get("sha256") and isinstance(b.get("size"), int) and isinstance(a.get("size"), int)
                and a["size"] > b["size"] and a.get("prefix_size") == b["size"]
                and a.get("prefix_sha256") == b["sha256"])


def compare(before, after, allow=(), defaults=None):
    """defaults：*.log 新增或只附加算內建允許；沒給就照之前那份快照的設定（--no-default-ignore 記在快照裡）。"""
    if defaults is None:
        defaults = before.get("default_ignore", True) is not False
    bf, af = before["files"], after["files"]
    # Windows 路徑不分大小寫：C:\ 與 c:\ 的快照要對得上
    bk = {os.path.normcase(p): p for p in bf}
    ak = {os.path.normcase(p): p for p in af}
    allowed, unallowed, unreadable, default_allowed = [], [], [], []
    for key in sorted(set(bk) | set(ak)):
        bp, ap = bk.get(key), ak.get(key)
        b, a = (bf[bp] if bp else None), (af[ap] if ap else None)
        path = ap or bp
        note = ""
        if b is None:
            kind = "added"
        elif a is None:
            kind = "deleted"
        else:
            same, note = _same(b, a)
            if same:
                if note:
                    unreadable.append(path)
                continue
            kind = "unverified" if same is None else "modified"
        rel = (a or b).get("rel", os.path.basename(path))
        item = {"kind": kind, "path": path, "rel": rel}
        if note:
            item["note"] = note
        if matches(allow, rel, path):
            allowed.append(item)
        elif defaults and _append_only(rel) and (kind == "added" or (kind == "modified" and _appended(b, a))):
            default_allowed.append(item)
        else:
            unallowed.append(item)
    return {"allowed": allowed, "unallowed": unallowed, "unreadable": unreadable, "default_allowed": default_allowed}


def _change_lines(items):
    out = []
    for c in items:
        extra = f"（{c['note']}）" if c.get("note") else ""
        out.append(f"  {KIND_LABEL[c['kind']]}  {c['path']}{extra}")
    return out


def format_report(before, after, result, command_rc=None, command=None):
    lines = []
    roots = after.get("roots") or before.get("roots") or []
    lines.append(f"fs_guard：監看 {len(roots)} 個根目錄，之前 {len(before['files'])} 個檔、之後 {len(after['files'])} 個檔"
                 f"（重算雜湊 {after.get('stats', {}).get('hashed', 0)} 個，大小與修改時間沒變而沿用 "
                 f"{after.get('stats', {}).get('reused', 0)} 個）")
    before_exists = {r["path"]: r.get("exists") for r in before.get("roots", [])}
    for r in roots:
        tag = "" if before_exists.get(r["path"], r.get("exists")) else "（之前不存在）"
        lines.append(f"  根目錄：{r['path']}{tag}")
    if command is not None:
        lines.append(f"被包住的指令：{' '.join(command)}")
        lines.append(f"被包住的指令結束碼 {command_rc}")
    if result["allowed"]:
        lines.append(f"允許的變動 {len(result['allowed'])} 筆（--allow，不算失敗）：")
        lines += _change_lines(result["allowed"])
    if result.get("default_allowed"):
        lines.append(f"內建允許的 log 變動 {len(result['default_allowed'])} 筆（*.log 新增或只在後面附加，不算失敗；"
                     "刪除、清空、改寫照算；--no-default-ignore 關掉）：")
        lines += [f"  {'新增' if c['kind'] == 'added' else '附加'}日誌  {c['path']}" for c in result["default_allowed"]]
    if result["unreadable"]:
        lines.append(f"讀不到內容、只比大小與修改時間的檔 {len(result['unreadable'])} 個：")
        lines += [f"  {p}" for p in result["unreadable"]]
    if result["unallowed"]:
        lines.append(f"允許清單外的變動 {len(result['unallowed'])} 筆：")
        lines += _change_lines(result["unallowed"])
    # 結論只在全部比完之後、最後一行印
    n = len(result["unallowed"])
    failed_cmd = command is not None and command_rc != 0
    if n:
        unknown = sum(1 for c in result["unallowed"] if c["kind"] == "unverified")
        parts = [f"{n - unknown} 筆允許清單外的變動"] if n - unknown else []
        if unknown:
            parts.append(f"{unknown} 筆讀不到、無法確認有沒有變動（不能背書沒改檔）")
        verdict = f"fs_guard：有 {'、'.join(parts)}"
        if failed_cmd:
            verdict += f"；被包住的指令也失敗（結束碼 {command_rc}，照傳出）"
    elif failed_cmd:
        verdict = f"fs_guard：被包住的指令失敗（結束碼 {command_rc}，照傳出）；沒有允許清單外的變動"
    else:
        verdict = "fs_guard：沒有允許清單外的變動"
    lines.append(verdict)
    return "\n".join(lines)


def exit_code(result, command_rc=None):
    if command_rc not in (None, 0):
        return command_rc
    return EXIT_CHANGED if result["unallowed"] else 0


# ---- 子指令 ----

def cmd_snapshot(args):
    out = os.path.abspath(args.out)
    snap = take_snapshot(args.roots, args.ignore, exclude=[out, out + ".tmp"], defaults=not args.no_default_ignore)
    write_json(out, snap)
    print(f"fs_guard：快照寫在 {out}（{len(snap['roots'])} 個根目錄、{len(snap['files'])} 個檔）")
    return 0


def cmd_diff(args):
    try:
        before = load_snapshot(args.before)
        if args.after:
            after = load_snapshot(args.after)
        else:
            roots = [r["path"] for r in before["roots"]]
            own = [os.path.abspath(args.before), os.path.abspath(args.before) + ".tmp"]
            after = take_snapshot(roots, before.get("ignore", []), prev=before, full_hash=args.full_hash, exclude=own,
                                  defaults=before.get("default_ignore", True) is not False)
    except SnapshotError as e:
        print(f"fs_guard：{e}", file=sys.stderr)
        return EXIT_USAGE
    result = compare(before, after, args.allow)
    if args.json:
        print(json.dumps({**result, "exit": exit_code(result)}, ensure_ascii=False, indent=1))
    else:
        print(format_report(before, after, result))
    return exit_code(result)


def run_guarded(watch, command, allow=(), ignore=(), full_hash=False, report=None, runner=None, defaults=True):
    """包住一個指令：前後各快照一次。回傳 (結束碼, 報告文字, 結果)。"""
    exclude = [os.path.abspath(report), os.path.abspath(report) + ".tmp"] if report else []
    before = take_snapshot(watch, ignore, exclude=exclude, defaults=defaults)
    exe = shutil.which(command[0])
    if exe is None and not os.path.exists(command[0]):
        text = f"fs_guard：找不到要包住的指令：{command[0]}"
        return EXIT_NOT_FOUND, text, None
    sys.stdout.flush()
    try:
        if runner is not None:
            rc = runner(command)
        else:
            rc = subprocess.run([exe or command[0], *command[1:]], check=False).returncode
    except KeyboardInterrupt:
        rc = 130
    except OSError as e:
        return EXIT_NOT_FOUND, f"fs_guard：要包住的指令跑不起來：{e}", None
    # prev 一律傳：--full-hash 只關掉沿用雜湊，判斷 log 是不是只附加還是要之前的大小與雜湊
    after = take_snapshot(watch, ignore, prev=before, full_hash=full_hash, exclude=exclude, defaults=defaults)
    result = compare(before, after, allow)
    code = exit_code(result, rc)
    if report:
        write_json(report, {**result, "command": command, "command_exit": rc, "exit": code,
                            "roots": after["roots"], "stats": after["stats"]})
    return code, format_report(before, after, result, rc, command), result


def cmd_run(args, command):
    if not command:
        print("fs_guard：沒有要包住的指令。用法：fs_guard.py run --watch <根目錄…> [--allow <glob>…] -- <指令…>",
              file=sys.stderr)
        return EXIT_USAGE
    if not args.watch:
        print("fs_guard：至少要一個 --watch <根目錄>", file=sys.stderr)
        return EXIT_USAGE
    code, text, _ = run_guarded(args.watch, command, args.allow, args.ignore, args.full_hash, args.report,
                                defaults=not args.no_default_ignore)
    print(text)
    return code


# ---- 自我測試 ----

def selftest():
    failures = []

    def ok(name, cond):
        print(f"{'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="fs_guard-") as td:
        base = Path(td)
        root = base / "proj"
        (root / "private" / "data").mkdir(parents=True)
        live = root / "private" / "data" / "snapshot.json"
        live.write_text("LIVE", encoding="utf-8")
        (root / "keep.txt").write_text("k", encoding="utf-8")
        gone = root / "gone.txt"
        gone.write_text("g", encoding="utf-8")
        touched = root / "touched.txt"
        touched.write_text("t", encoding="utf-8")

        before = take_snapshot([root])
        ok("快照記下每個檔的 SHA-256", len(before["files"]) == 4
           and all(len(v["sha256"]) == 64 for v in before["files"].values()))

        live.write_text("OFFLINE", encoding="utf-8")
        gone.unlink()
        (root / "out").mkdir()
        (root / "out" / "report.json").write_text("{}", encoding="utf-8")
        (root / "new.lock").write_text("pid", encoding="utf-8")
        (root / "__pycache__").mkdir()
        (root / "__pycache__" / "m.pyc").write_bytes(b"x")
        (root / "pkg" / ".pytest_cache").mkdir(parents=True)
        (root / "pkg" / ".pytest_cache" / "v").write_text("x", encoding="utf-8")
        (root / "run.log").write_text("x", encoding="utf-8")
        t = time.time() + 300
        os.utime(touched, (t, t))

        after = take_snapshot([root], prev=before)
        res = compare(before, after, allow=["out/*"])
        got = {(c["kind"], c["rel"]) for c in res["unallowed"]}
        ok("抓到修改、刪除、新增（被 .gitignore 的資料夾也一樣）",
           got == {("modified", "private/data/snapshot.json"), ("deleted", "gone.txt"), ("added", "new.lock")})
        ok("--allow 的變動另外列，不算失敗", [c["rel"] for c in res["allowed"]] == ["out/report.json"])
        ok("內建忽略 __pycache__、.pytest_cache、*.log", not any(
            "pyc" in c["rel"] or "pytest_cache" in c["rel"] or c["rel"].endswith(".log")
            for c in res["allowed"] + res["unallowed"]))
        ok("只碰修改時間不算變動", not any(c["rel"] == "touched.txt" for c in res["unallowed"]))
        ok("預篩：大小與修改時間沒變的檔沿用雜湊", after["stats"]["reused"] >= 1)

        missing = base / "home" / ".demo-bot"
        b2 = take_snapshot([missing])
        ok("根目錄不存在當成空的", b2["files"] == {} and b2["roots"][0]["exists"] is False)
        (missing / "local-locks").mkdir(parents=True)
        (missing / "local-locks" / "run.lock").write_text("1", encoding="utf-8")
        r2 = compare(b2, take_snapshot([missing]))
        ok("根目錄之後才出現，裡面的檔算新增", [(c["kind"], c["rel"]) for c in r2["unallowed"]]
           == [("added", "local-locks/run.lock")])

        same = root / "same.bin"
        same.write_bytes(b"AAAA")
        b3 = take_snapshot([root])
        st = os.stat(same)
        same.write_bytes(b"BBBB")
        os.utime(same, ns=(st.st_atime_ns, st.st_mtime_ns))
        fast = compare(b3, take_snapshot([root], prev=b3))
        full = compare(b3, take_snapshot([root], prev=b3, full_hash=True))
        ok("大小與修改時間都被還原：預篩看不到、--full-hash 抓得到",
           not fast["unallowed"] and [c["rel"] for c in full["unallowed"]] == ["same.bin"])

        def writer(cmd):
            (root / "written-by-cmd.txt").write_text("x", encoding="utf-8")
            return 0

        code, text, _ = run_guarded([root], [sys.executable, "-c", "pass"], runner=writer)
        ok("run：允許清單外有變動就 exit 3，清單在成功字樣之前",
           code == EXIT_CHANGED and "written-by-cmd.txt" in text and text.splitlines()[-1].startswith("fs_guard：有 1 筆"))
        code, text, _ = run_guarded([root], [sys.executable, "-c", "pass"], runner=lambda cmd: 5)
        ok("run：被包住的指令失敗就傳出它的結束碼", code == 5 and "結束碼 5" in text)
        code, text, _ = run_guarded([root], [sys.executable, "-c", "pass"], runner=lambda cmd: 0)
        ok("run：沒有變動時 exit 0，成功字樣在最後一行",
           code == 0 and text.splitlines()[-1] == "fs_guard：沒有允許清單外的變動")
        code, _, _ = run_guarded([root], ["omnikit-no-such-command-xyz"])
        ok("run：找不到指令 exit 127", code == EXIT_NOT_FOUND)

        snap_file = root / "before.json"
        write_json(snap_file, take_snapshot([root], exclude=[snap_file]))
        loaded = load_snapshot(snap_file)
        again = take_snapshot([root], prev=loaded, exclude=[snap_file])
        ok("快照檔放在根目錄裡，diff 不把它當成新增", not compare(loaded, again)["unallowed"])
        bad = base / "bad.json"
        bad.write_text("{oops", encoding="utf-8")
        try:
            load_snapshot(bad)
            ok("讀不到快照要報錯，不能當成沒變動", False)
        except SnapshotError:
            ok("讀不到快照要報錯，不能當成沒變動", True)

        ok("glob：上層資料夾名稱、檔名、`*` 跨資料夾都對得上",
           matches(["out"], "out/sub/a.json", "/x/out/sub/a.json")
           and matches(["*.tmp"], "a/b/c.tmp", "/x/a/b/c.tmp")
           and matches(["out/*"], "out/sub/a.json", "/x/out/sub/a.json")
           and not matches(["out/*"], "outside/a.json", "/x/outside/a.json"))
        ok("--allow 字面路徑：只比根目錄底下那一個，不比子資料夾同名檔；字面的 [id] 對得上",
           matches(["report.md"], "report.md", "/x/report.md")
           and not matches(["report.md"], "private/data/report.md", "/x/private/data/report.md")
           and matches(["brackets/[id]/out.json"], "brackets/[id]/out.json", "/x/brackets/[id]/out.json"))

        logs = base / "logs"
        logs.mkdir()
        (logs / "audit.log").write_text("a\n", encoding="utf-8")
        (logs / "app.log").write_text("a\n", encoding="utf-8")
        b4 = take_snapshot([logs])
        (logs / "audit.log").unlink()
        with open(logs / "app.log", "a", encoding="utf-8") as f:
            f.write("b\n")
        r4 = compare(b4, take_snapshot([logs], prev=b4))
        ok("*.log：附加算內建允許，刪除照算允許清單外的變動",
           [c["rel"] for c in r4["default_allowed"]] == ["app.log"]
           and [(c["kind"], c["rel"]) for c in r4["unallowed"]] == [("deleted", "audit.log")])

        locked = {"spec": SPEC, "tool": "fs_guard", "roots": [], "files": {
            "/x/locked": {"root": 0, "rel": "locked", "error": "讀不到資料夾：Permission denied"}}}
        r5 = compare(locked, json.loads(json.dumps(locked)))
        ok("前後都讀不到：列為無法確認，exit 3", exit_code(r5) == EXIT_CHANGED
           and [c["kind"] for c in r5["unallowed"]] == ["unverified"])

    print(f"\nfs_guard.py selftest：{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    command = []
    if "--" in argv:
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1:]

    ap = argparse.ArgumentParser(description="副作用量測：指令前後各做一次檔案快照（SHA-256），允許清單外有變動就 exit 非 0")
    ap.add_argument("--selftest", action="store_true", help="離線自我測試")
    sub = ap.add_subparsers(dest="cmd")

    p_snap = sub.add_parser("snapshot", help="記下根目錄底下每個檔的大小、修改時間與 SHA-256")
    p_snap.add_argument("roots", nargs="+", help="要監看的根目錄（可以還不存在）")
    p_snap.add_argument("--out", required=True, help="快照寫到哪個 JSON 檔")
    p_snap.add_argument("--ignore", action="append", default=[], help="不記錄的 glob（可重複）")
    p_snap.add_argument("--no-default-ignore", action="store_true",
                        help="不用內建忽略：快取資料夾照記，*.log 附加也算變動（設定記在快照裡）")

    allow_help = "允許變動的路徑或 glob（可重複）；不含萬用字元的是字面路徑：絕對路徑，或相對於根目錄的路徑"
    p_diff = sub.add_parser("diff", help="跟快照比：列出新增、修改、刪除")
    p_diff.add_argument("before", help="之前的快照")
    p_diff.add_argument("after", nargs="?", help="之後的快照；不給就照快照裡的根目錄現在再掃一次")
    p_diff.add_argument("--allow", action="append", default=[], help=allow_help)
    p_diff.add_argument("--full-hash", action="store_true", help="不預篩，每個檔都重算雜湊")
    p_diff.add_argument("--json", action="store_true", help="輸出 JSON")

    p_run = sub.add_parser("run", help="包住一個指令，前後各快照一次")
    p_run.add_argument("--watch", action="append", default=[], help="要監看的根目錄（可重複，可以還不存在）")
    p_run.add_argument("--allow", action="append", default=[], help=allow_help)
    p_run.add_argument("--ignore", action="append", default=[], help="不記錄的 glob（可重複）")
    p_run.add_argument("--full-hash", action="store_true", help="不預篩，每個檔都重算雜湊")
    p_run.add_argument("--no-default-ignore", action="store_true",
                       help="不用內建忽略：快取資料夾照記，*.log 附加也算變動")
    p_run.add_argument("--report", help="另外把結果寫成 JSON 檔")

    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "snapshot":
        return cmd_snapshot(args)
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "run":
        return cmd_run(args, command)
    ap.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
