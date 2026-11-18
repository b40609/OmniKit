"""python manage.py migrate [--db 路徑]：依序套用 migrations/ 裡還沒套用的檔案。

每個 migration 是 migrations/NNN_名稱.py，裡面有 up(conn)。套用過的記在 schema_migrations。
"""
import argparse
import importlib.util
import pathlib

from app.db import connect

HERE = pathlib.Path(__file__).resolve().parent


def migrate(db_path):
    conn = connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    for f in sorted((HERE / "migrations").glob("[0-9]*.py")):
        if f.stem in done:
            continue
        spec = importlib.util.spec_from_file_location(f.stem, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.up(conn)
        conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (f.stem,))
        conn.commit()
        print(f"applied {f.stem}")
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["migrate"])
    ap.add_argument("--db", default=str(HERE / "app.db"))
    migrate(ap.parse_args().db)
