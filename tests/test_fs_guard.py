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
    # 對照：同一個變動，git status 看不到（這正是兩份審查都說「沒改檔」的原因）
    if shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        st = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
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
