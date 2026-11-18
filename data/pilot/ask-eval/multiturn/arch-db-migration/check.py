import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
import shutil
import sqlite3
import subprocess
import tempfile

PEOPLE = [("a@x.com", "王小明", "小明", "王"), ("b@x.com", "林美華", "美華", "林"),
          ("c@x.com", "歐陽娜娜", "娜娜", "歐陽"), ("d@x.com", "John Smith", "John", "Smith"),
          ("e@x.com", "李", "李", ""), ("f@x.com", "Anne Marie Lee", "Anne Marie", "Lee"),
          ("g@x.com", "司馬光", "光", "司馬"), ("h@x.com", "陳大文", "大文", "陳")]


def norm(v):
    return (v or "").strip()


def check():
    ws = checklib.workspace()
    with tempfile.TemporaryDirectory(prefix="chk-mig-", ignore_cleanup_errors=True) as tmp:
        copy = pathlib.Path(tmp) / "ws"
        shutil.copytree(ws, copy, ignore=shutil.ignore_patterns(".git", "*.db", "__pycache__"))
        db = pathlib.Path(tmp) / "app.db"
        # 只套用 001，塞舊資料，模擬線上現況
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE schema_migrations (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, "
                     "full_name TEXT NOT NULL)")
        conn.execute("INSERT INTO schema_migrations VALUES ('001_create_users')")
        conn.executemany("INSERT INTO users (email, full_name) VALUES (?, ?)", [(e, f) for e, f, _, _ in PEOPLE])
        conn.commit()
        conn.close()
        for attempt in (1, 2):
            p = subprocess.run([sys.executable, "-B", "manage.py", "migrate", "--db", str(db)], cwd=copy,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            if p.returncode != 0:
                what = "跑資料庫更新（migrate）就出錯" if attempt == 1 else "資料庫更新跑第二次就出錯"
                return [(what, (p.stderr or p.stdout)[-300:])]
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        if not {"first_name", "last_name"} <= cols:
            return [("資料表裡還是沒有 first_name、last_name", f"欄位 {sorted(cols)}")]
        if "full_name" not in cols:
            return [("舊的 full_name 不見了，電子報排程跟 API 會壞", f"欄位 {sorted(cols)}")]
        rows = {r["email"]: dict(r) for r in conn.execute("SELECT * FROM users")}
        if len(rows) != len(PEOPLE):
            return [("更新完會員少了幾筆", f"{len(rows)} 筆")]
        for e, full, first, last in PEOPLE:
            r = rows[e]
            if norm(r["full_name"]) != full:
                return [("有會員的全名被改掉了", f"{e} {r['full_name']!r}")]
            if (norm(r["first_name"]), norm(r["last_name"])) != (first, last):
                return [(f"「{full}」拆出來的姓、名不對（姓={r['last_name']!r}、名={r['first_name']!r}）",
                         f"{full}: 期望 名={first} 姓={last}")]
        sys.path.insert(0, str(copy))
        from app.api import create_user, get_user
        from jobs.newsletter import recipients
        try:
            uid = create_user(conn, "new@x.com", "歐陽靖")
            u = get_user(conn, uid)
        except Exception as ex:  # noqa: BLE001
            return [("新會員註冊會出錯", f"{type(ex).__name__}: {ex}")]
        if (norm(u.get("first_name")), norm(u.get("last_name"))) != ("靖", "歐陽"):
            return [("新註冊的會員沒有拆好姓跟名", f"{u}")]
        if norm(u.get("full_name")) != "歐陽靖":
            return [("新註冊的會員全名沒存到", f"{u}")]
        if len(recipients(conn)) != len(PEOPLE) + 1:
            return [("電子報排程的收件人名單不對", "recipients 數量不對")]
    return []


checklib.run(check)
