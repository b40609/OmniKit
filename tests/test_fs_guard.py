"""副作用量測（engine/scripts/fs_guard.py）的 pytest。

D10 改動 3：唯讀審查跑測試時，git status 看不到被 .gitignore 的資料夾與家目錄底下的設定資料夾，
兩份審查都會寫「沒改檔」。fs_guard 在指令前後各做一次 SHA-256 快照，允許清單外有變動就印出清單並 exit 非 0。

前兩個是設計裡的重現測試（案例泛化成 demo-bot、daily-job），其餘是邊界。
所有目錄都在 tmp_path 裡造，不碰真實的家目錄。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "engine" / "scripts" / "fs_guard.py"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def fs_guard(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=ENV, timeout=120, check=False)


def py(code):
    """被包住的指令：用同一個 Python 跑一小段程式。"""
    return [sys.executable, "-c", code]


def change_lines(stdout):
    """報告裡的變動清單：「  新增  路徑」「  修改  路徑」「  刪除  路徑」。"""
    return [ln for ln in stdout.splitlines() if ln.startswith(("  新增  ", "  修改  ", "  刪除  "))]


def guard_run(watch, cmd, allow=(), extra=()):
    args = ["run"]
    for w in watch:
        args += ["--watch", w]
    for a in allow:
        args += ["--allow", a]
    return fs_guard(*args, *extra, "--", *cmd)


# ---- 設計的 2 個重現測試 ----

def test_offline_test_overwrites_gitignored_data_file(tmp_path):
    """離線測試覆寫被 .gitignore 的資料檔：git status 乾淨，fs_guard 要抓到。"""
    repo = tmp_path / "daily-job"
    live = repo / "private" / "data" / "daily_snapshot.json"
    live.parent.mkdir(parents=True)
    live.write_text('{"source": "live"}', encoding="utf-8")
    (repo / ".gitignore").write_text("private/\n", encoding="utf-8")

    r = guard_run([repo / "private" / "data"],
                  py(f"open(r'{live}', 'w', encoding='utf-8').write('{{\"source\": \"offline-test\"}}')"))

    assert r.returncode != 0, r.stdout + r.stderr
    assert "daily_snapshot.json" in r.stdout          # 訊號：允許清單外的檔案雜湊變了
    assert "修改" in r.stdout
    assert "沒有允許清單外的變動" not in r.stdout
    # 對照：同一個變動，git status 看不到（這正是兩份審查都說「沒改檔」的原因）。
    # CI 的暫存路徑刻意很長、含空白與中文，git 要 core.longpaths；git 建不了 repo 時只略過這段對照，fs_guard 的斷言照樣算
    git = ["git", "-c", "core.longpaths=true"]
    if shutil.which("git") and subprocess.run([*git, "init", "-q", str(repo)], capture_output=True,
                                              check=False).returncode == 0:
        st = subprocess.run([*git, "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
                            capture_output=True, text=True, check=True)
        assert "daily_snapshot.json" not in st.stdout


def test_integration_test_writes_home_config_dir(tmp_path):
    """整合測試寫進家目錄的設定資料夾（例如 ~/.demo-bot/local-locks）：監看根目錄原本不存在也要抓到新增。"""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    config_dir = fake_home / ".demo-bot"              # 跑之前不存在
    lock = config_dir / "local-locks" / "run-0001.lock"

    r = guard_run([config_dir],
                  py(f"import pathlib; p = pathlib.Path(r'{lock}'); p.parent.mkdir(parents=True); p.write_text('pid')"))

    assert r.returncode != 0, r.stdout + r.stderr
    assert "local-locks" in r.stdout                  # 訊號：監看根目錄下多了檔
    assert "run-0001.lock" in r.stdout
    assert "新增" in r.stdout


# ---- 指令本身的結束碼 ----

def test_wrapped_command_failure_exit_code_is_passed_through(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    r = guard_run([root], py("import sys; sys.exit(7)"))
    assert r.returncode == 7, r.stdout + r.stderr
    assert "結束碼 7" in r.stdout


def test_failed_command_that_also_writes_keeps_its_exit_code_and_lists_changes(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    target = root / "half-written.json"
    r = guard_run([root], py(f"import sys; open(r'{target}', 'w').write('x'); sys.exit(5)"))
    assert r.returncode == 5, r.stdout + r.stderr
    assert "half-written.json" in r.stdout


def test_clean_command_exits_zero_and_success_text_is_last(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    (root / "keep.txt").write_text("same", encoding="utf-8")
    r = guard_run([root], py("print('only reading')"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "only reading" in r.stdout                 # 被包住的指令輸出照常出現
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert "沒有允許清單外的變動" in lines[-1]          # 成功字樣只在最後一行


def test_missing_command_is_usage_error(tmp_path):
    r = fs_guard("run", "--watch", tmp_path, "--")
    assert r.returncode == 2
    assert "沒有要包住的指令" in r.stdout + r.stderr


def test_command_not_found_exits_127(tmp_path):
    r = guard_run([tmp_path], ["omnikit-no-such-command-xyz"])
    assert r.returncode == 127, r.stdout + r.stderr


# ---- 允許清單、內建忽略、只碰時間戳 ----

def test_allow_globs_and_builtin_ignores(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    code = (
        "import pathlib, sys\n"
        f"r = pathlib.Path(r'{root}')\n"
        "for rel in ['out/report.json', '__pycache__/m.cpython-311.pyc', 'pkg/__pycache__/n.pyc',\n"
        "            '.pytest_cache/v/cache/lastfailed', '.ruff_cache/0.1/x', 'run.log', 'logs/app.log']:\n"
        "    p = r / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('x')\n"
    )
    r = guard_run([root], py(code), allow=["out/*"])
    assert r.returncode == 0, r.stdout + r.stderr
    listed = "\n".join(change_lines(r.stdout))       # 只看變動清單（報告開頭會印出被包住的指令全文）
    assert "report.json" in listed                    # 允許的變動也要列出來，但不算失敗
    for ignored in ("m.cpython-311.pyc", "n.pyc", "lastfailed", "ruff_cache", "run.log", "app.log"):
        assert ignored not in listed


def test_allow_does_not_hide_other_changes(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    code = (f"import pathlib; r = pathlib.Path(r'{root}'); (r / 'out').mkdir(); (r / 'out' / 'a.json').write_text('1');"
            " (r / 'settings.json').write_text('2')")
    r = guard_run([root], py(code), allow=["out/*"])
    assert r.returncode == 3, r.stdout + r.stderr
    assert "settings.json" in r.stdout


def test_touch_only_is_not_a_change(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    f = root / "data.csv"
    f.write_text("a,b\n", encoding="utf-8")
    r = guard_run([root], py(f"import os, time; t = time.time() + 120; os.utime(r'{f}', (t, t))"))
    assert r.returncode == 0, r.stdout + r.stderr


# ---- snapshot 與 diff ----

def test_snapshot_then_diff_reports_added_modified_deleted(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    (root / "mod.txt").write_text("v1", encoding="utf-8")
    (root / "del.txt").write_text("bye", encoding="utf-8")
    snap = root / "before.json"                      # 快照檔放在監看根目錄裡，diff 不能把它當成新增
    r = fs_guard("snapshot", root, "--out", snap)
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(snap.read_text(encoding="utf-8"))
    assert data["spec"] == 1 and data["files"]
    assert all(len(v["sha256"]) == 64 for v in data["files"].values())

    (root / "mod.txt").write_text("v2", encoding="utf-8")
    (root / "del.txt").unlink()
    (root / "new.txt").write_text("hi", encoding="utf-8")

    r = fs_guard("diff", snap)
    assert r.returncode == 3, r.stdout + r.stderr
    out = r.stdout
    assert "新增" in out and "new.txt" in out
    assert "修改" in out and "mod.txt" in out
    assert "刪除" in out and "del.txt" in out
    assert "before.json" not in out

    rj = fs_guard("diff", snap, "--json")
    rep = json.loads(rj.stdout)
    kinds = {Path(c["path"]).name: c["kind"] for c in rep["unallowed"]}
    assert kinds == {"new.txt": "added", "mod.txt": "modified", "del.txt": "deleted"}


def test_diff_two_snapshot_files(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    (root / "a.txt").write_text("1", encoding="utf-8")
    before = tmp_path / "b.json"
    after = tmp_path / "a.json"
    assert fs_guard("snapshot", root, "--out", before).returncode == 0
    assert fs_guard("snapshot", root, "--out", after).returncode == 0
    r = fs_guard("diff", before, after)
    assert r.returncode == 0, r.stdout + r.stderr


def test_unreadable_snapshot_is_an_error_not_clean(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    r = fs_guard("diff", bad)
    assert r.returncode not in (0, 3)
    assert "讀不到快照" in r.stdout + r.stderr
    assert "沒有允許清單外的變動" not in r.stdout


def test_prefilter_skips_rehash_unless_full_hash(tmp_path):
    """大小與修改時間都沒變就不重算雜湊（預篩）；--full-hash 一律重算。這是有意的取捨，測試把它寫清楚。"""
    root = tmp_path / "w"
    root.mkdir()
    f = root / "same-size.bin"
    f.write_bytes(b"AAAA")
    code = (f"import os; st = os.stat(r'{f}'); open(r'{f}', 'wb').write(b'BBBB');"
            f" os.utime(r'{f}', ns=(st.st_atime_ns, st.st_mtime_ns))")
    r_fast = guard_run([root], py(code))
    assert r_fast.returncode == 0, r_fast.stdout + r_fast.stderr   # 預篩看不到：大小、修改時間都被還原
    r_full = guard_run([root], py(code.replace("BBBB", "CCCC")), extra=["--full-hash"])
    assert r_full.returncode == 3, r_full.stdout + r_full.stderr
    assert "same-size.bin" in r_full.stdout


def test_selftest_passes():
    r = fs_guard("--selftest")
    assert r.returncode == 0, r.stdout + r.stderr


# ---- 審查修正 D10-R-04：--allow 純檔名跨子資料夾放行、*.log 刪改不報 ----

def report_of(tmp_path, name="rep.json"):
    return json.loads((tmp_path / name).read_text(encoding="utf-8"))


def test_review_reproduction_allow_report_md_overwrite_private_and_delete_audit_log(tmp_path):
    """D10-R-04 原始重現：照政策 --allow report.md，指令卻覆寫 private/data/report.md 並刪掉 audit.log，不能 exit 0。"""
    root = tmp_path / "proj"
    (root / "private" / "data").mkdir(parents=True)
    (root / "private" / "data" / "report.md").write_text("real", encoding="utf-8")
    (root / "audit.log").write_text("2026-11-27 login\n", encoding="utf-8")
    code = (f"import os, pathlib; r = pathlib.Path(r'{root}'); (r / 'private' / 'data' / 'report.md').write_text('forged');"
            " os.remove(r / 'audit.log')")
    r = guard_run([root], py(code), allow=["report.md"])
    assert r.returncode != 0, r.stdout + r.stderr
    assert "沒有允許清單外的變動" not in r.stdout


def test_allow_plain_filename_does_not_cover_same_name_in_subdirectory(tmp_path):
    """D10-R-04 之 1：不含萬用字元的相對路徑只比對根目錄底下的那一個（與它的絕對路徑），不比對子資料夾裡的同名檔。"""
    root = tmp_path / "proj"
    (root / "private" / "data").mkdir(parents=True)
    (root / "private" / "data" / "report.md").write_text("real", encoding="utf-8")
    code = (f"import pathlib; r = pathlib.Path(r'{root}'); (r / 'report.md').write_text('deliverable');"
            " (r / 'private' / 'data' / 'report.md').write_text('forged')")
    r = guard_run([root], py(code), allow=["report.md"], extra=["--report", tmp_path / "rep.json"])
    assert r.returncode == 3, r.stdout + r.stderr
    rep = report_of(tmp_path)
    assert [c["rel"] for c in rep["allowed"]] == ["report.md"]
    assert [c["rel"] for c in rep["unallowed"]] == ["private/data/report.md"]


@pytest.mark.parametrize("how", ["absolute", "dot-relative", "backslash-relative"])
def test_allow_exact_path_forms(tmp_path, how):
    """交付檔可以寫絕對路徑、./ 開頭或反斜線的相對路徑；都只放行那一個檔。"""
    root = tmp_path / "proj"
    (root / "reports").mkdir(parents=True)
    (root / "other" / "reports").mkdir(parents=True)
    allow = {"absolute": str(root / "reports" / "out.md"), "dot-relative": "./reports/out.md",
             "backslash-relative": "reports\\out.md"}[how]
    if how == "backslash-relative" and os.name != "nt":
        pytest.skip("反斜線只在 Windows 是路徑分隔字元")
    code = (f"import pathlib; r = pathlib.Path(r'{root}'); (r / 'reports' / 'out.md').write_text('a');"
            " (r / 'other' / 'reports' / 'out.md').write_text('b')")
    r = guard_run([root], py(code), allow=[allow], extra=["--report", tmp_path / "rep.json"])
    assert r.returncode == 3, r.stdout + r.stderr
    rep = report_of(tmp_path)
    assert [c["rel"] for c in rep["allowed"]] == ["reports/out.md"]
    assert [c["rel"] for c in rep["unallowed"]] == ["other/reports/out.md"]


@pytest.mark.parametrize("action", ["delete", "clear", "rewrite-longer", "rewrite-same-size"])
def test_deleting_or_rewriting_a_log_is_reported_by_default(tmp_path, action):
    """D10-R-04 之 2：*.log 不能整個忽略；刪除、清空、改寫稽核 log 都要報（不加任何旗標）。"""
    root = tmp_path / "proj"
    root.mkdir()
    log = root / "audit.log"
    log.write_text("2026-11-27 login\n", encoding="utf-8")
    code = {
        "delete": f"import os; os.remove(r'{log}')",
        "clear": f"open(r'{log}', 'w').close()",
        "rewrite-longer": f"open(r'{log}', 'w').write('2026-11-27 nothing happened here\\n')",
        "rewrite-same-size": f"open(r'{log}', 'w').write('2026-11-27 LOGIN\\n')",
    }[action]
    r = guard_run([root], py(code))
    assert r.returncode == 3, r.stdout + r.stderr
    assert "audit.log" in "\n".join(change_lines(r.stdout))


def test_log_in_subfolder_named_like_a_log_is_not_ignored(tmp_path):
    """D10-R-04 之 2：以 .log 結尾的資料夾不是 log 檔，裡面的檔照常比對。"""
    root = tmp_path / "proj"
    (root / "data.log").mkdir(parents=True)
    target = root / "data.log" / "settings.json"
    target.write_text("{}", encoding="utf-8")
    r = guard_run([root], py(f"open(r'{target}', 'w').write('{{\"x\": 1}}')"))
    assert r.returncode == 3, r.stdout + r.stderr
    assert "settings.json" in r.stdout


def test_new_or_appended_logs_are_still_not_failures(tmp_path):
    """預設照舊：測試跑出新的 log、或在既有 log 後面附加，不算失敗（另外列出，不混進變動清單）。"""
    root = tmp_path / "proj"
    root.mkdir()
    log = root / "app.log"
    log.write_text("line 1\n", encoding="utf-8")
    code = (f"open(r'{log}', 'a').write('line 2\\n'); import pathlib;"
            f" p = pathlib.Path(r'{root}') / 'logs' / 'run.log'; p.parent.mkdir(); p.write_text('x')")
    r = guard_run([root], py(code))
    assert r.returncode == 0, r.stdout + r.stderr
    assert not change_lines(r.stdout)


def test_no_default_ignore_counts_logs_and_caches(tmp_path):
    """--no-default-ignore：內建的忽略（快取資料夾）與 log 附加的預設放行都關掉，全部照算。"""
    root = tmp_path / "proj"
    root.mkdir()
    log = root / "app.log"
    log.write_text("line 1\n", encoding="utf-8")
    code = (f"open(r'{log}', 'a').write('line 2\\n'); import pathlib;"
            f" p = pathlib.Path(r'{root}') / '__pycache__' / 'm.pyc'; p.parent.mkdir(); p.write_bytes(b'x')")
    r = guard_run([root], py(code), extra=["--no-default-ignore"])
    assert r.returncode == 3, r.stdout + r.stderr
    listed = "\n".join(change_lines(r.stdout))
    assert "app.log" in listed and "m.pyc" in listed


# ---- 審查修正 D10-R-05：字面 [ ] 路徑、Windows 磁碟機大小寫 ----

def test_allow_literal_path_with_brackets(tmp_path):
    """D10-R-05 之 1：路徑裡的 [id] 是字面的資料夾名稱，不能被 fnmatch 當成字元集而比對失敗。"""
    root = tmp_path / "w"
    (root / "brackets" / "[id]").mkdir(parents=True)
    target = root / "brackets" / "[id]" / "out.json"
    r = guard_run([root], py(f"open(r'{target}', 'w').write('x')"), allow=[str(target)])
    assert r.returncode == 0, r.stdout + r.stderr
    r = guard_run([root], py(f"open(r'{target}', 'w').write('y')"), allow=["brackets/[id]/out.json"])
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(os.name != "nt", reason="只有 Windows 的路徑不分大小寫")
def test_drive_letter_case_is_not_a_change(tmp_path):
    """D10-R-05 之 2：C:\\ 與 c:\\ 是同一個路徑；兩份快照的根目錄寫法不同，不能把全部檔案報成刪除加新增。"""
    root = tmp_path / "w"
    root.mkdir()
    (root / "a.txt").write_text("1", encoding="utf-8")
    s = str(root)
    upper, lower = s[0].upper() + s[1:], s[0].lower() + s[1:]
    assert fs_guard("snapshot", upper, "--out", tmp_path / "up.json").returncode == 0
    assert fs_guard("snapshot", lower, "--out", tmp_path / "low.json").returncode == 0
    r = fs_guard("diff", tmp_path / "up.json", tmp_path / "low.json")
    assert r.returncode == 0, r.stdout + r.stderr
    r = guard_run([upper], py(f"open(r'{lower}\\a.txt', 'w').write('2')"), allow=[f"{lower}\\a.txt"])
    assert r.returncode == 0, r.stdout + r.stderr


# ---- 審查修正 D10-R-06：前後都讀不到，不能背書沒變動 ----

def fake_snapshot(files):
    return {"spec": 1, "tool": "fs_guard", "created": "2026-11-27T00:00:00+00:00",
            "roots": [{"path": str(Path("/demo/root").resolve()), "exists": True}], "ignore": [], "files": files}


@pytest.mark.parametrize("entry", [
    {"rel": "locked", "error": "讀不到資料夾：Permission denied"},
    {"rel": "locked.json", "error": "讀不到檔案資訊：Permission denied"},
])
def test_unreadable_before_and_after_is_not_endorsed(tmp_path, entry):
    """D10-R-06：資料夾或檔案前後都讀不到（沒有大小與修改時間），不能因為 None == None 就當成沒變動、exit 0。"""
    path = str(Path("/demo/root").resolve() / entry["rel"])
    snap = fake_snapshot({path: {"root": 0, **entry}})
    for name in ("b.json", "a.json"):
        (tmp_path / name).write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    r = fs_guard("diff", tmp_path / "b.json", tmp_path / "a.json")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "沒有允許清單外的變動" not in r.stdout
    assert entry["rel"] in r.stdout

    sys.path.insert(0, str(SCRIPT.parent))
    import fs_guard as fg

    res = fg.compare(snap, json.loads(json.dumps(snap)))
    assert fg.exit_code(res) != 0


def test_content_unreadable_but_stat_same_is_still_only_a_note(tmp_path):
    """對照：讀不到內容（被鎖住）但大小與修改時間都在，照舊只比大小與修改時間並標明，不算失敗。"""
    path = str(Path("/demo/root").resolve() / "busy.db")
    entry = {"root": 0, "rel": "busy.db", "size": 10, "mtime_ns": 1, "error": "讀不到內容：locked"}
    snap = fake_snapshot({path: entry})
    for name in ("b.json", "a.json"):
        (tmp_path / name).write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    r = fs_guard("diff", tmp_path / "b.json", tmp_path / "a.json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "只比大小與修改時間" in r.stdout


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="用 chmod 造讀不到的資料夾，只在非 root 的 POSIX 跑")
def test_unreadable_directory_during_run_is_not_endorsed(tmp_path):
    root = tmp_path / "w"
    locked = root / "locked"
    locked.mkdir(parents=True)
    (locked / "a.txt").write_text("1", encoding="utf-8")
    os.chmod(locked, 0)
    try:
        r = guard_run([root], py("pass"))
    finally:
        os.chmod(locked, 0o755)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "沒有允許清單外的變動" not in r.stdout
