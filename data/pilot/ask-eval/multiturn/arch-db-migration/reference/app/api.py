"""會員 API。"""
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "split_mig", pathlib.Path(__file__).resolve().parent.parent / "migrations" / "002_split_full_name.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def get_user(conn, user_id):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_user(conn, email, full_name):
    first, last = _mod.split_name(full_name)
    cur = conn.execute("INSERT INTO users (email, full_name, first_name, last_name) VALUES (?, ?, ?, ?)",
                       (email, full_name, first, last))
    conn.commit()
    return cur.lastrowid
