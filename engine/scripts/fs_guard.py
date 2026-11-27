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
  uv run engine/scripts/fs_guard.py snapshot <根目錄…> --out before.json [--ignore <glob>…]
  uv run engine/scripts/fs_guard.py diff before.json [after.json] [--allow <glob>…] [--full-hash] [--json]
  uv run engine/scripts/fs_guard.py run --watch <根目錄…> [--allow <glob>…] [--ignore <glob>…] [--full-hash] \\
      [--report <檔>] -- <指令…>
  uv run engine/scripts/fs_guard.py --selftest

  diff 只給 before.json 時，照快照裡記的根目錄現在再掃一次來比；給兩個檔就比兩份快照。

比對規則：
- 只比內容雜湊，不比修改時間：只碰時間戳不算變動。
- 預篩：之後那次快照，大小與修改時間都跟之前一樣就沿用之前的雜湊、不重讀，大目錄才跑得快；
  --full-hash 一律重讀（大小與修改時間都被刻意還原的改寫，只有 --full-hash 抓得到）。
- 內建忽略：__pycache__、.pytest_cache、.ruff_cache 資料夾與 *.log 檔。其他用 --ignore（不記錄）
  或 --allow（照列出來，但不算失敗）。
- glob 用 fnmatch：「相對於根目錄的路徑」、它的上層資料夾、絕對路徑、檔名任一個對上就算；`*` 可以跨資料夾；
  Windows 不分大小寫。例：--allow "out/*"、--allow out、--allow "*.tmp"。
- 根目錄不存在也可以監看（當成空的），之後出現的檔都算新增。
- 符號連結與 junction 不跟進，只記它指向哪裡。
- 讀不到內容的檔（被鎖住、沒權限）記下原因，只比大小與修改時間，並在輸出標明。
- .git 資料夾不在內建忽略：監看 repo 根目錄時，git 指令改了索引也會列出來，要的話 --allow ".git/*"。
- 抓不到：指令結束之後才由背景行程寫的檔。

結束碼：0 沒有允許清單外的變動；3 有；run 時被包住的指令失敗就傳出它的結束碼（變動清單照印）；
        127 找不到要包住的指令；2 用法錯誤或讀不到快照。成功字樣只在全部比完之後、最後一行印。
"""
import argparse
import fnmatch
import hashlib
import json
import os
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
BUILTIN_IGNORE_FILES = ("*.log",)
EXIT_CHANGED = 3
EXIT_USAGE = 2
EXIT_NOT_FOUND = 127
KIND_LABEL = {"added": "新增", "modified": "修改", "deleted": "刪除"}
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


def matches(globs, rel, abspath):
    if not globs:
        return False
    name = rel.rsplit("/", 1)[-1]
    for g in globs:
        if fnmatch.fnmatch(name, g) or fnmatch.fnmatch(abspath, g):
            return True
        if any(fnmatch.fnmatch(c, g) for c in _rel_candidates(rel)):
            return True
    return False


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


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_entries(root, ignores):
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
                if e.name in BUILTIN_IGNORE_DIRS or matches(ignores, rel, e.path):
                    continue
                stack.append(e.path)
                continue
            if matches(BUILTIN_IGNORE_FILES, rel, e.path) or matches(ignores, rel, e.path):
                continue
            yield rel, e.path, e


def _record(path, entry, prev, full_hash, counter):
    """一個檔的紀錄：大小、修改時間、SHA-256；連結記指向哪裡；讀不到記原因。"""
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
    try:
        rec["sha256"] = retry(_sha256, path)
        counter["hashed"] += 1
    except OSError as e:
        rec["error"] = f"讀不到內容：{e}"
    return rec


def take_snapshot(roots, ignores=(), prev=None, full_hash=False, exclude=()):
    """掃過每個根目錄。prev 是之前的快照（拿來預篩），exclude 是不記的絕對路徑（例如快照檔自己）。"""
    excluded = {os.path.normcase(os.path.abspath(p)) for p in exclude}
    prev_files = (prev or {}).get("files", {})
    counter = {"hashed": 0, "reused": 0}
    files = {}
    root_info = []
    for idx, raw in enumerate(roots):
        root = os.path.abspath(str(raw))
        root_info.append({"path": root, "exists": os.path.exists(root)})
        for rel, path, entry in _iter_entries(root, list(ignores)):
            if os.path.normcase(path) in excluded or path in files:
                continue
            if isinstance(entry, OSError):
                files[path] = {"root": idx, "rel": rel, "error": f"讀不到資料夾：{entry}"}
                continue
            rec = _record(path, entry, prev_files.get(path), full_hash, counter)
            files[path] = {"root": idx, "rel": rel, **rec}
    return {
        "spec": SPEC,
        "tool": "fs_guard",
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "roots": root_info,
        "ignore": list(ignores),
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
    """(一樣嗎, 備註)。兩邊都有雜湊就比雜湊；連結比指向；有一邊讀不到就退回比大小與修改時間。"""
    if "link" in b or "link" in a:
        return b.get("link") == a.get("link"), ""
    if b.get("sha256") and a.get("sha256"):
        return b["sha256"] == a["sha256"], ""
    note = "讀不到內容，只比大小與修改時間"
    return (b.get("size") == a.get("size") and b.get("mtime_ns") == a.get("mtime_ns")), note


def compare(before, after, allow=()):
    bf, af = before["files"], after["files"]
    allowed, unallowed, unreadable = [], [], []
    for path in sorted(set(bf) | set(af)):
        b, a = bf.get(path), af.get(path)
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
            kind = "modified"
        rel = (a or b).get("rel", os.path.basename(path))
        item = {"kind": kind, "path": path, "rel": rel}
        if note:
            item["note"] = note
        (allowed if matches(allow, rel, path) else unallowed).append(item)
    return {"allowed": allowed, "unallowed": unallowed, "unreadable": unreadable}


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
        verdict = f"fs_guard：有 {n} 筆允許清單外的變動"
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
    snap = take_snapshot(args.roots, args.ignore, exclude=[out, out + ".tmp"])
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
            after = take_snapshot(roots, before.get("ignore", []), prev=None if args.full_hash else before,
                                  full_hash=args.full_hash, exclude=own)
    except SnapshotError as e:
        print(f"fs_guard：{e}", file=sys.stderr)
        return EXIT_USAGE
    result = compare(before, after, args.allow)
    if args.json:
        print(json.dumps({**result, "exit": exit_code(result)}, ensure_ascii=False, indent=1))
    else:
        print(format_report(before, after, result))
    return exit_code(result)


def run_guarded(watch, command, allow=(), ignore=(), full_hash=False, report=None, runner=None):
    """包住一個指令：前後各快照一次。回傳 (結束碼, 報告文字, 結果)。"""
    exclude = [os.path.abspath(report), os.path.abspath(report) + ".tmp"] if report else []
    before = take_snapshot(watch, ignore, exclude=exclude)
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
    after = take_snapshot(watch, ignore, prev=None if full_hash else before, full_hash=full_hash, exclude=exclude)
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
    code, text, _ = run_guarded(args.watch, command, args.allow, args.ignore, args.full_hash, args.report)
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

    p_diff = sub.add_parser("diff", help="跟快照比：列出新增、修改、刪除")
    p_diff.add_argument("before", help="之前的快照")
    p_diff.add_argument("after", nargs="?", help="之後的快照；不給就照快照裡的根目錄現在再掃一次")
    p_diff.add_argument("--allow", action="append", default=[], help="允許變動的 glob（可重複）")
    p_diff.add_argument("--full-hash", action="store_true", help="不預篩，每個檔都重算雜湊")
    p_diff.add_argument("--json", action="store_true", help="輸出 JSON")

    p_run = sub.add_parser("run", help="包住一個指令，前後各快照一次")
    p_run.add_argument("--watch", action="append", default=[], help="要監看的根目錄（可重複，可以還不存在）")
    p_run.add_argument("--allow", action="append", default=[], help="允許變動的 glob（可重複）")
    p_run.add_argument("--ignore", action="append", default=[], help="不記錄的 glob（可重複）")
    p_run.add_argument("--full-hash", action="store_true", help="不預篩，每個檔都重算雜湊")
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
