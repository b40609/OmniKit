# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""OmniKit 的狀態資料夾在 ~/.omnikit，以及把舊位置（%LOCALAPPDATA%\\omnikit）的狀態搬過來、合併成一份。

為什麼不放 %LOCALAPPDATA%\\omnikit（2026-11-18 在這台實測）：
從 Microsoft Store／MSIX 封裝的 app（例如 Claude 桌面版）的對話裡跑 OmniKit，子程序（bash、uv、python）也在
那個 app 的檔案虛擬化底下：在 AppData 底下新建的資料夾，會寫到 %LOCALAPPDATA%\\Packages\\<套件>\\LocalCache\\Local\\…。
封裝裡看到的是兩份疊在一起（同名的檔以封裝那份為準），終端機、T3 Code、Codex 看不到封裝那份，
於是同一台有兩份狀態：從不同地方跑，看到的接上狀態、安裝紀錄都不一樣。
家目錄（%USERPROFILE%）不在 AppData，不會被轉存，誰寫的大家都看得到；Claude Code（~/.claude）、Codex（~/.codex）、
Antigravity（~/.gemini）、T3 Code（~/.t3）也都放在家目錄。環境變數 OMNIKIT_STATE_DIR 可以改位置（測試、CI 用）。

搬家（migrate）：install.ps1、uninstall.ps1、agents.py（sync、connect 等會寫入的指令）、profiles.py 與 git hook
（.githooks/sync-data.sh）會先跑；開新對話的 hook（home_watch.py）看到舊位置還有東西，就在背景跑 agents.py sync。
doctor 只回報。步驟：
1. 找舊位置：每個封裝的副本 %LOCALAPPDATA%\\Packages\\*\\LocalCache\\Local\\omnikit，以及 %LOCALAPPDATA%\\omnikit。
2. 照這個順序整個搬到 ~/.omnikit/legacy/<時間>/<來源>/：先搬封裝副本，再搬 %LOCALAPPDATA%\\omnikit。
   在封裝裡跑時，同名的檔只看得到封裝那份；封裝副本搬走之後，%LOCALAPPDATA%\\omnikit 看到的才是真實那份。
   搬不動（檔案被鎖住、不同磁碟）就複製一份、原處不動，並記下當時每個檔的大小與時間，下次只合併之後改過的檔。
3. 合併進 ~/.omnikit（~/.omnikit 原本就有的也算一份）：
   - 內容一樣：一份。
   - .jsonl、.log：每一行都留（去掉重複）；.jsonl 每一行都有 ts 就照 ts 排序。
   - .json（最上層是物件）：以最新的為準，舊的有、新的沒有的鍵補進來；同一個鍵值不同就列成衝突。
     字串清單（安裝紀錄裝了哪些工具、接上了哪些設定目錄）取聯集並列出來：agent 的設定檔不在 AppData，
     兩份狀態記的是同一批檔案，任何一份記過的都要算（移除時才拿得乾淨）。
   - symlink、junction 不跟進去、不搬內容，列出來。
   - 其他檔：最新的為準，其他版本列成衝突。
   - git repo（例如交接用的 status）：不逐檔合併。~/.omnikit 已經有就用它，沒有就用最近有動靜的那份；
     其他份有沒 push 的 commit 或還沒 commit 的變更，列成衝突。
   衝突不會丟資料：每一份都留在 ~/.omnikit/legacy/<時間>/。結果記在 ~/.omnikit/migrate.json。

用法：uv run engine/scripts/statedir.py [status|migrate] [--json] [--quiet]
      uv run engine/scripts/statedir.py --selftest
"""
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fsretry import retry  # noqa: E402  同一個資料夾：防毒短暫鎖住檔案時等一下再試

ENV = "OMNIKIT_STATE_DIR"
NAME = "omnikit"
LEGACY = "legacy"            # ~/.omnikit/legacy/<時間>/<來源>/：搬過來的舊位置，原封不動
RECORD = "migrate.json"      # 每次搬家的結果、留在原處的來源當時的樣子
LOCK = ".migrate.lock"
STALE_LOCK = 600             # 秒：鎖檔超過這麼久，當作上次搬到一半當掉
KEEP_RUNS = 20
GIT_TIMEOUT = 20


def state_dir(environ=None, home=None):
    """狀態資料夾：OMNIKIT_STATE_DIR，沒設就是 ~/.omnikit。"""
    environ = os.environ if environ is None else environ
    if environ.get(ENV):
        return Path(environ[ENV])
    return (Path(home) if home is not None else Path.home()) / ".omnikit"


STATE = state_dir()


def local_appdata(environ=None):
    environ = os.environ if environ is None else environ
    value = environ.get("LOCALAPPDATA")
    return Path(value) if value else None


def _same(a, b):
    try:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
    except (OSError, ValueError):
        return False


def _inside(path, folder):
    a, b = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def candidates(state=None, environ=None):
    """舊位置 [(標籤, 路徑)]，封裝副本在前、%LOCALAPPDATA%\\omnikit 在最後（原因見最上面第 2 點）。
    不管有沒有東西都列；跟狀態資料夾同一個（OMNIKIT_STATE_DIR 指到舊位置）就不列。"""
    state = STATE if state is None else state
    local = local_appdata(environ)
    if local is None:
        return []
    found = []
    try:
        packages = sorted((local / "Packages").iterdir(), key=lambda p: p.name.lower())
    except OSError:
        packages = []
    for pkg in packages:
        found.append((f"package-{pkg.name}", pkg / "LocalCache" / "Local" / NAME))
    found.append(("localappdata", local / NAME))
    return [(label, path) for label, path in found if not _inside(path, state) and not _inside(state, path)]


def files_of(root):
    """{相對路徑（/ 分隔）: (大小, 修改時間 ns)}；讀不到的略過。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in filenames:
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except OSError:
                continue
            out[p.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def load_record(state):
    try:
        doc = json.loads((state / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    doc.setdefault("runs", [])
    doc.setdefault("left", {})
    return doc


def new_files(path, left):
    """這個舊位置還沒合併過的檔：上次複製後原處沒動的（大小、時間都一樣）不算。"""
    seen = left.get(str(path)) or {}
    return {rel: sig for rel, sig in files_of(path).items() if list(sig) != list(seen.get(rel, []))}


def pending(state=None, environ=None):
    """還沒合併的舊位置 [(標籤, 路徑, 檔數)]。"""
    state = STATE if state is None else state
    left = load_record(state)["left"]
    out = []
    for label, path in candidates(state, environ):
        if path.is_dir():
            n = len(new_files(path, left))
            if n:
                out.append((label, path, n))
    return out


# ---------- 合併 ----------

@dataclass
class Result:
    state: Path
    backup: Path | None = None
    sources: list = field(default_factory=list)    # {"label", "path", "moved", "files", "error"?}
    written: list = field(default_factory=list)    # 寫進狀態資料夾的相對路徑
    conflicts: list = field(default_factory=list)  # 給人看的一行說明
    skipped: str = ""                               # 沒有跑的原因（例如另一個搬家正在跑）

    @property
    def changed(self):
        return bool(self.sources)

    def lines(self):
        if self.skipped:
            return [f"狀態資料夾：{self.skipped}"]
        if not self.sources:
            return []
        out = [f"狀態檔改放 {self.state}（不放 %LOCALAPPDATA%：從 Claude 桌面版這類封裝的 app 裡跑時會被轉存成另一份）"]
        for s in self.sources:
            how = "搬過來" if s["moved"] else "複製過來（原處搬不動，留著）"
            out.append(f"  {how}：{s['path']}（{s['files']} 個檔）" + (f"；{s['error']}" if s.get("error") else ""))
        out.append(f"  合併 {len(self.written)} 個檔；舊位置原封不動備份在 {self.backup}")
        if self.conflicts:
            out.append(f"  有 {len(self.conflicts)} 個地方兩份不一樣，用了較新的（另一份在備份裡）：")
            out += [f"    - {c}" for c in self.conflicts]
        return out


def _short(value, limit=80):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _read(path):
    return retry(path.read_bytes)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".migrating")
    retry(tmp.write_bytes, data)
    retry(os.replace, tmp, path)


def _lines(data):
    return data.decode("utf-8", errors="surrogateescape").splitlines()


def merge_lines(versions, jsonl):
    """每一行都留、去掉重複；舊的檔先。jsonl 每一行都有字串 ts 就照 ts 排序（同 ts 保持原順序）。"""
    seen, out = set(), []
    for _label, _mtime, data in sorted(versions, key=lambda v: v[1]):
        for line in _lines(data):
            if line.strip() and line not in seen:
                seen.add(line)
                out.append(line)
    if jsonl:
        try:
            keys = [json.loads(line)["ts"] for line in out]
            if all(isinstance(k, str) for k in keys):
                out = [line for _, line in sorted(zip(keys, out), key=lambda kv: kv[0])]
        except (ValueError, KeyError, TypeError):
            pass
    return ("\n".join(out) + "\n").encode("utf-8", errors="surrogateescape")


def _scalars(value):
    return isinstance(value, list) and all(isinstance(x, (str, int, float, bool)) or x is None for x in value)


def merge_dict(base, other, label, base_label, where, conflicts):
    """把 other 有、base 沒有的鍵補進 base（遞迴）；值不同就記衝突，base 為準。回傳有沒有補。
    兩邊都是字串、數字的清單（安裝紀錄裝了哪些工具、接上了哪些設定目錄）取聯集：agent 的設定檔不在 AppData、
    兩份狀態寫的是同一批檔案，任何一份記過的都是 OmniKit 真的寫過、移除時要拿掉的。"""
    added = False
    for key, value in other.items():
        path = f"{where}.{key}" if where else str(key)
        if key not in base:
            base[key] = value
            added = True
        elif isinstance(base[key], dict) and isinstance(value, dict):
            added = merge_dict(base[key], value, label, base_label, path, conflicts) or added
        elif _scalars(base[key]) and _scalars(value) and base[key] != value:
            extra = [x for x in value if x not in base[key]]
            if extra:
                base[key] = base[key] + extra
                added = True
                conflicts.append(f"{path}：兩份不一樣，取聯集（{label} 多了 {_short(extra)}）")
        elif base[key] != value:
            conflicts.append(f"{path}：用 {base_label} 的 {_short(base[key])}；{label} 是 {_short(value)}")
    return added


def merge_file(rel, versions):
    """versions：[(標籤, 修改時間 ns, bytes)]。回傳（要寫的 bytes, 衝突說明清單）。"""
    distinct = {}
    for label, mtime, data in versions:
        distinct.setdefault(data, []).append((label, mtime))
    newest = max(versions, key=lambda v: (v[1], v[0] == "state"))
    if len(distinct) == 1:
        return newest[2], []
    suffix = Path(rel).suffix.lower()
    if suffix in (".jsonl", ".log"):
        return merge_lines(versions, suffix == ".jsonl"), []
    if suffix == ".json":
        try:
            parsed = [(label, mtime, json.loads(data.decode("utf-8-sig"))) for label, mtime, data in versions]
        except ValueError:
            parsed = None
        if parsed and all(isinstance(doc, dict) for _, _, doc in parsed):
            order = sorted(parsed, key=lambda v: (v[1], v[0] == "state"), reverse=True)
            base_label, _, base = order[0]
            base = json.loads(json.dumps(base))
            notes, added = [], False
            for label, _, doc in order[1:]:
                added = merge_dict(base, doc, label, base_label, "", notes) or added
            out = (json.dumps(base, ensure_ascii=False, indent=2) + "\n").encode("utf-8") if added else newest[2]
            return out, [f"{rel} 的 {n}" for n in dict.fromkeys(notes)]
    others = sorted({label for label, _, data in versions if data != newest[2]})
    return newest[2], [f"{rel}：用 {newest[0]} 的（較新）；{'、'.join(others)} 的版本不一樣"]


def git_state(path, run=subprocess.run):
    """（沒 push 的 commit 數, 有沒有還沒 commit 的變更）；查不到就回傳 None。"""
    try:
        r = run(["git", "-C", str(path), "status", "--porcelain=v1", "--branch"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    lines = r.stdout.splitlines()
    head = lines[0] if lines and lines[0].startswith("## ") else ""
    ahead = 0
    if "[ahead " in head:
        try:
            ahead = int(head.split("[ahead ", 1)[1].split("]", 1)[0].split(",", 1)[0])
        except ValueError:
            ahead = 0
    if head and "..." not in head and not head.startswith("## HEAD"):
        ahead = -1  # 沒有上游：不知道有沒有 push 過
    return ahead, any(line and not line.startswith("## ") for line in lines)


def activity(repo):
    """git repo 最近有動靜的時間：.git 裡幾個常變的檔，取最新的。"""
    best = 0
    for name in ("logs/HEAD", "index", "HEAD", "FETCH_HEAD", "ORIG_HEAD"):
        try:
            best = max(best, (repo / ".git" / name).stat().st_mtime_ns)
        except OSError:
            pass
    return best


def _junction(path):
    """Path.is_junction 要 Python 3.12；3.11 在 Windows 看 reparse point 屬性（junction 也是一種）。"""
    if hasattr(path, "is_junction"):
        return path.is_junction()
    attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) and not path.is_symlink()


def _link(path):
    """symlink 或 junction（reparse point）：不跟進去、不搬內容（可能指到別的封裝或已經不在的地方）。"""
    try:
        return path.is_symlink() or _junction(path)
    except OSError:
        return True


def walk(root):
    """（{相對路徑: 檔案}, {相對路徑: git repo 資料夾}, [略過的連結]）。git repo 不往下走。"""
    files, repos, links = {}, {}, []
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        rel = d.relative_to(root)
        if rel.parts and (d / ".git").exists():
            repos[rel.as_posix()] = d
            dirnames[:] = []
            continue
        links += [(rel / n).as_posix() for n in dirnames + filenames if _link(d / n)]
        dirnames[:] = sorted(n for n in dirnames if not _link(d / n) and not (not rel.parts and n == LEGACY))
        for name in filenames:
            if (not rel.parts and name in (RECORD, LOCK)) or name.endswith(".migrating") or _link(d / name):
                continue
            files[(rel / name).as_posix()] = d / name
    return files, repos, links


def _copytree(src, dest):
    """複製整個資料夾：symlink 照連結複製，junction 不跟進去（copytree 會把 junction 當一般資料夾）。"""
    shutil.copytree(src, dest, symlinks=True, copy_function=lambda s, d: retry(shutil.copy2, s, d),
                    ignore=lambda folder, names: [n for n in names if _junction(Path(folder, n))])


def take(src, dest, rename=os.rename):
    """把舊位置整個搬到 dest；搬不動就複製（原處留著）。回傳（有沒有搬走, 錯誤說明）。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        retry(rename, src, dest)
        return True, ""
    except OSError as e:
        first = f"搬不動（{e.__class__.__name__}: {e}）"
    try:
        _copytree(src, dest)
        return False, first
    except shutil.Error as e:
        return False, f"{first}；複製時有 {len(e.args[0]) if e.args else '?'} 個檔讀不到，下次再試"
    except OSError as e:
        return False, f"{first}；也複製不了（{e}）"


class _Lock:
    def __init__(self, state, now):
        self.path, self.now, self.held = state / LOCK, now, False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    stale = self.now - self.path.stat().st_mtime > STALE_LOCK
                except OSError:
                    stale = True
                if not stale:
                    return False
                try:
                    self.path.unlink()
                except OSError:
                    return False
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self.held = True
            return True
        return False

    def __exit__(self, *exc):
        if self.held:
            try:
                self.path.unlink()
            except OSError:
                pass


def migrate(state=None, environ=None, now=None, rename=os.rename, run=subprocess.run):
    """把舊位置的狀態搬進狀態資料夾並合併（見最上面）。沒有舊位置就什麼都不做。"""
    state = STATE if state is None else state
    now = time.time() if now is None else now
    result = Result(state=state)
    if not pending(state, environ):
        return result
    with _Lock(state, now) as held:
        if not held:
            result.skipped = f"另一個搬家正在跑（{state / LOCK}），這次先不動"
            return result
        record = load_record(state)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
        backup = state / LEGACY / stamp
        n = 1
        while backup.exists():
            n += 1
            backup = state / LEGACY / f"{stamp}-{n}"
        result.backup = backup
        copies = []
        for label, path in candidates(state, environ):
            if not path.is_dir():
                continue
            fresh = new_files(path, record["left"])
            if not fresh:
                continue
            before = files_of(path)
            dest = backup / label
            moved, error = take(path, dest, rename)
            if not dest.is_dir():
                result.sources.append({"label": label, "path": str(path), "moved": False, "files": 0,
                                       "error": error})
                continue
            if moved:
                record["left"].pop(str(path), None)
            else:
                # 原處留著：上次已經合併過、之後沒動的檔不再算一份（免得舊資料蓋回來）
                for rel in set(before) - set(fresh):
                    try:
                        (dest / rel).unlink()
                    except OSError:
                        pass
                record["left"][str(path)] = {rel: list(sig) for rel, sig in before.items()}
            copies.append((label, dest))
            entry = {"label": label, "path": str(path), "moved": moved, "files": len(fresh)}
            if error:
                entry["error"] = error
            result.sources.append(entry)

        files, repos = {}, {}
        for label, root in copies:
            f, r, links = walk(root)
            for rel, p in f.items():
                files.setdefault(rel, []).append((label, p))
            for rel, p in r.items():
                repos.setdefault(rel, []).append((label, p))
            result.conflicts += [f"{rel}（{label} 那份）是連結（symlink 或 junction），沒有搬內容；原本的在備份裡"
                                 for rel in links]
        # git repo 裡的檔不逐檔合併
        files = {rel: v for rel, v in files.items() if not any(rel.startswith(r + "/") for r in repos)}

        for rel, found in sorted(files.items()):
            target = state / rel
            versions = []
            for label, p in found:
                try:
                    versions.append((label, p.stat().st_mtime_ns, _read(p)))
                except OSError:
                    continue
            current = None
            if target.is_file():
                try:
                    current = _read(target)
                    versions.append(("state", target.stat().st_mtime_ns, current))
                except OSError:
                    continue
            if not versions:
                continue
            data, notes = merge_file(rel, versions)
            result.conflicts += notes
            if data != current:
                _write(target, data)
                newest = max(v[1] for v in versions)
                try:
                    if len({v[2] for v in versions}) == 1:
                        os.utime(target, ns=(newest, newest))  # 原封不動搬過來的，保留修改時間
                except OSError:
                    pass
                result.written.append(rel)

        for rel, found in sorted(repos.items()):
            target = state / rel
            losers = list(found)
            if not (target / ".git").exists():
                if target.exists():
                    result.conflicts.append(f"{rel}：狀態資料夾裡已經有同名的資料夾但不是 git repo，沒有搬；舊的在備份裡")
                    continue
                label, chosen = max(found, key=lambda lp: activity(lp[1]))
                _copytree(chosen, target)
                result.written.append(rel + "/")
                losers = [(lb, p) for lb, p in found if p != chosen]
            for label, p in losers:
                st = git_state(p, run)
                if st is None:
                    result.conflicts.append(f"{rel}（{label} 那份）：查不到 git 狀態，請自己確認有沒有沒 push 的 commit：{p}")
                elif st[0] or st[1]:
                    what = "、".join(x for x in (
                        f"{st[0]} 個沒 push 的 commit" if st[0] > 0 else ("沒有設定上游" if st[0] < 0 else ""),
                        "還沒 commit 的變更" if st[1] else "") if x)
                    result.conflicts.append(f"{rel}（{label} 那份）有{what}，沒有合併進來：{p}")

        record["runs"] = (record["runs"] + [{
            "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
            "backup": str(backup), "sources": result.sources, "written": len(result.written),
            "conflicts": result.conflicts}])[-KEEP_RUNS:]
        _write(state / RECORD, (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return result


def lines_for(result):
    """給 install／sync 印的訊息（沒搬就是空的）。"""
    return result.lines()


def report(state=None, environ=None):
    """doctor 用：[(ok, 項目, 說明)]。"""
    state = STATE if state is None else state
    rows = [(True, "狀態資料夾", str(state))]
    waiting = pending(state, environ)
    for label, path, n in waiting:
        kind = f"封裝 app（{label.removeprefix('package-')}）轉存的副本" if label.startswith("package-") else "舊位置"
        rows.append((False, "舊位置還有沒合併的狀態",
                     f"{path}：{kind}，{n} 個檔跟 {state} 是分開的兩份；"
                     f"跑 uv run engine/scripts/statedir.py migrate 合併（agents.py sync、install.ps1 也會先合併）"))
    runs = load_record(state)["runs"]
    if runs and runs[-1].get("conflicts"):
        last = runs[-1]
        rows.append((True, "上次合併的衝突",
                     f"{last.get('at')} 合併時有 {len(last['conflicts'])} 個地方兩份不一樣，用了較新的；"
                     f"另一份在 {last.get('backup')}（細節在 {state / RECORD}）"))
    return rows


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def check(label, ok):
        print(f"{'通過' if ok else '失敗'}：{label}")
        if not ok:
            failures.append(label)

    def put(path, content, mtime=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        if mtime is not None:
            os.utime(path, (mtime, mtime))

    def fake_git(out):
        return lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, out, "")

    clean = fake_git("## main...origin/main\n")
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        home, local = tmp / "home", tmp / "AppData" / "Local"
        env = {"LOCALAPPDATA": str(local)}
        check("沒設 OMNIKIT_STATE_DIR：放家目錄的 .omnikit", state_dir({}, home) == home / ".omnikit")
        check("OMNIKIT_STATE_DIR 可以改位置", state_dir({ENV: str(tmp / "x")}, home) == tmp / "x")
        state = state_dir({}, home)
        real = local / NAME
        pkg = local / "Packages" / "Claude_abc" / "LocalCache" / "Local" / NAME
        (local / "Packages" / "Other_x" / "LocalCache" / "Local").mkdir(parents=True)
        check("沒有舊位置：什麼都不做", not migrate(state, env, 1000, run=clean).changed and not state.exists())

        # 真實那份（終端機、T3 寫的）與封裝副本（Claude 桌面版裡寫的）
        put(real / "agents.json", json.dumps({"agents": ["claude-code"], "homes": [], "mcp": {"a": 1, "only_real": 2}}), 100)
        put(pkg / "agents.json", json.dumps({"agents": ["claude-code"], "homes": ["k"], "mcp": {"a": 9}, "skills": {}}), 200)
        put(pkg / "install-record.json", '{"files": ["x"]}', 150)
        put(real / "edition.json", '{"edition": "maintainer", "date": "2026-11-13"}', 300)
        put(pkg / "edition.json", '{"edition": "maintainer", "date": "2026-11-05"}', 50)
        put(real / "profile.json", '{"profile": "ryan"}\n', 10)
        put(pkg / "profile.json", '{"profile": "ryan"}\n', 20)
        put(real / "dispatch" / "log.jsonl", '{"ts": "2026-11-17T10:00:00", "n": 1}\n{"ts": "2026-11-18T03:00:00", "n": 3}\n', 100)
        put(pkg / "dispatch" / "log.jsonl", '{"ts": "2026-11-17T10:00:00", "n": 1}\n{"ts": "2026-11-18T01:00:00", "n": 2}\n', 200)
        put(real / "rules" / "AGENTS.md", "# 舊\n", 100)
        put(pkg / "rules" / "AGENTS.md", "# 新\n", 200)
        put(pkg / "pool" / "catalog.json", "[1, 2]", 100)
        put(real / "install-record.json", '{"files": ["y", "x"], "paths": ["C:/x/uv"]}', 120)
        outside = tmp / "elsewhere"
        put(outside / "secret.txt", "不該被搬")
        linked = False
        try:
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(real / "jn"))
            else:
                os.symlink(outside, real / "jn", target_is_directory=True)
            linked = True
        except (OSError, ImportError, AttributeError):
            pass
        for root, mt, who in ((real, 500, "real"), (pkg, 100, "pkg")):
            put(root / "status" / ".git" / "HEAD", "ref: refs/heads/main\n", mt)
            put(root / "status" / "README.md", f"from {who}\n", mt)
        check("找到兩個舊位置：封裝副本在前、%LOCALAPPDATA% 在最後",
              [lb for lb, _, _ in pending(state, env)] == ["package-Claude_abc", "localappdata"])
        gits = []

        def git_run(cmd, **kw):
            gits.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "## main...origin/main [ahead 2]\n M x\n", "")

        res = migrate(state, env, 1000, run=git_run)
        merged = json.loads((state / "agents.json").read_text(encoding="utf-8"))
        check("兩個舊位置都搬走（只剩備份）", not real.exists() and not pkg.exists()
              and (res.backup / "localappdata" / "agents.json").is_file() and (res.backup / "package-Claude_abc").is_dir())
        check("JSON：以較新的為準，舊的多的鍵補進來", merged["homes"] == ["k"] and merged["mcp"] == {"a": 9, "only_real": 2}
              and merged["skills"] == {})
        check("JSON：值不同列成衝突", any("agents.json 的 mcp.a" in c for c in res.conflicts))
        record = json.loads((state / "install-record.json").read_text(encoding="utf-8"))
        check("JSON 的字串清單取聯集並列出來（安裝紀錄只累加）", record == {"files": ["x", "y"], "paths": ["C:/x/uv"]}
              and any(c.startswith("install-record.json 的 files：兩份不一樣，取聯集") for c in res.conflicts))
        check("只有一邊有的檔照搬", (state / "pool" / "catalog.json").is_file())
        check("junction／symlink 不跟進去，列出來", not linked or (not (state / "jn").exists()
              and not (state / "jn" / "secret.txt").exists() and (outside / "secret.txt").is_file()
              and any(c.startswith("jn（localappdata 那份）是連結") for c in res.conflicts)))
        check("內容一樣：不算衝突", not any("profile.json" in c for c in res.conflicts)
              and (state / "profile.json").read_text(encoding="utf-8") == '{"profile": "ryan"}\n')
        log = (state / "dispatch" / "log.jsonl").read_text(encoding="utf-8").splitlines()
        check("jsonl：每一行都留、去重、照 ts 排序", [json.loads(x)["n"] for x in log] == [1, 2, 3])
        check("其他檔：較新的為準並列衝突", (state / "rules" / "AGENTS.md").read_text(encoding="utf-8") == "# 新\n"
              and any(c.startswith("rules/AGENTS.md") for c in res.conflicts))
        check("JSON 純值不同（edition 的 date）：用較新的", json.loads((state / "edition.json").read_text(encoding="utf-8"))["date"]
              == "2026-11-13")
        check("git repo：用最近有動靜的那份，不逐檔混", (state / "status" / "README.md").read_text(encoding="utf-8")
              == "from real\n" and (state / "status" / ".git" / "HEAD").is_file())
        check("git repo：另一份有沒 push 的 commit 列成衝突", any("status（package-Claude_abc 那份）有2 個沒 push" in c
                                                          for c in res.conflicts) and len(gits) == 1)
        check("結果記在 migrate.json", load_record(state)["runs"][-1]["written"] == len(res.written) and res.written)
        check("訊息說明搬到哪、衝突幾個", any(str(state) in x for x in res.lines()) and any("兩份不一樣" in x for x in res.lines()))
        check("搬完之後沒有待合併的", pending(state, env) == [] and not migrate(state, env, 2000, run=clean).changed)
        check("doctor：沒有舊位置時只列狀態資料夾與上次的衝突",
              [r[0] for r in report(state, env)] == [True, True] and "上次合併" in report(state, env)[1][1])

        # 搬完之後，舊版的程式又寫回舊位置：下次合併進來，狀態資料夾裡較新的不被蓋掉
        put(state / "agents.json", json.dumps({"agents": ["claude-code", "codex"], "homes": ["k"]}), 5000)
        put(real / "agents.json", json.dumps({"agents": ["claude-code"], "late": True}), 4000)
        put(real / "dispatch" / "log.jsonl", '{"ts": "2026-11-19T00:00:00", "n": 4}\n', 4000)
        rows = report(state, env)
        check("doctor：舊位置又有東西就回報失敗", [r[0] for r in rows].count(False) == 1
              and "statedir.py migrate" in [r for r in rows if not r[0]][0][2])
        res2 = migrate(state, env, 6000, run=clean)
        again = json.loads((state / "agents.json").read_text(encoding="utf-8"))
        check("狀態資料夾較新：它為準，舊位置多的鍵補進來", again["agents"] == ["claude-code", "codex"] and again["late"] is True)
        check("jsonl 接在後面", [json.loads(x)["n"] for x in (state / "dispatch" / "log.jsonl").read_text(
            encoding="utf-8").splitlines()] == [1, 2, 3, 4] and res2.backup != res.backup)

        # 搬不動（被鎖住）：複製、原處留著；沒改過的不再合併，改過的才合併
        put(real / "notes.md", "第一版\n", 7000)
        put(real / "keep.md", "不會再動\n", 7000)

        def locked_rename(src, dst):
            raise PermissionError(32, "檔案正由另一個程序使用")

        import fsretry
        old_sleep, fsretry.sleep = fsretry.sleep, lambda s: None
        try:
            res3 = migrate(state, env, 8000, rename=locked_rename, run=clean)
            check("搬不動：複製過來、原處留著", real.exists() and (state / "notes.md").read_text(encoding="utf-8") == "第一版\n"
                  and res3.sources[0]["moved"] is False and "搬不動" in res3.sources[0]["error"])
            check("搬不動：原處沒改過就不再算待合併", pending(state, env) == [])
            put(state / "keep.md", "在新位置改過\n", 9500)
            put(real / "notes.md", "第二版\n", 9000)
            check("原處改過的檔才算待合併", [n for _, _, n in pending(state, env)] == [1])
            migrate(state, env, 10000, rename=locked_rename, run=clean)
            check("只合併改過的，沒改過的不會蓋回來", (state / "notes.md").read_text(encoding="utf-8") == "第二版\n"
                  and (state / "keep.md").read_text(encoding="utf-8") == "在新位置改過\n")
        finally:
            fsretry.sleep = old_sleep

        # 另一個搬家正在跑：這次不動
        put(real / "late.txt", "x", 11000)
        (state / LOCK).write_text("1", encoding="utf-8")
        res4 = migrate(state, env, time.time(), run=clean)
        check("鎖住時不動、說明原因", not res4.changed and "另一個搬家正在跑" in res4.skipped and real.exists())
        os.utime(state / LOCK, (time.time() - STALE_LOCK - 5,) * 2)
        check("鎖檔太舊：當作上次當掉，照常搬", migrate(state, env, time.time(), run=clean).changed and not (state / LOCK).exists())

        # 狀態資料夾就是舊位置（OMNIKIT_STATE_DIR 指過去）：不搬自己
        check("狀態資料夾指到舊位置時不把自己當來源", candidates(real, env) == [
            ("package-Claude_abc", pkg), ("package-Other_x", local / "Packages" / "Other_x" / "LocalCache" / "Local" / NAME)])
        check("沒有 LOCALAPPDATA（非 Windows）：沒有舊位置", candidates(state, {}) == [])

    print(f"\n{'全部通過' if not failures else f'{len(failures)} 項失敗'}")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="OmniKit 的狀態資料夾與搬家（見最上面的說明）")
    parser.add_argument("command", nargs="?", choices=["status", "migrate"], default="status")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="沒有搬東西就不印")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.command == "migrate":
        res = migrate()
        if args.json:
            print(json.dumps({"state": str(res.state), "backup": str(res.backup) if res.backup else None,
                              "sources": res.sources, "written": res.written, "conflicts": res.conflicts,
                              "skipped": res.skipped}, ensure_ascii=False, indent=2))
        elif res.lines():
            print("\n".join(res.lines()))
        elif not args.quiet:
            print(f"狀態資料夾：{res.state}；沒有要搬的舊位置")
        return 0
    rows = report()
    if args.json:
        print(json.dumps([{"ok": ok, "item": item, "detail": detail} for ok, item, detail in rows], ensure_ascii=False, indent=2))
    else:
        for ok, item, detail in rows:
            print(f"{'✓' if ok else '✗'} {item}：{detail}")
    return 0 if all(ok for ok, _, _ in rows) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
