"""python seed.py [--db 路徑]：建一份測試資料庫（先跑 migrate 再塞假資料）。"""
import argparse
import pathlib

from app.db import connect
from manage import migrate

HERE = pathlib.Path(__file__).resolve().parent
PEOPLE = [("ming@example.com", "王小明"), ("mei@example.com", "林美華"), ("nana@example.com", "歐陽娜娜"),
          ("john@example.com", "John Smith"), ("li@example.com", "李"), ("anne@example.com", "Anne Marie Lee")]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(HERE / "app.db"))
    db = ap.parse_args().db
    migrate(db)
    conn = connect(db)
    conn.executemany("INSERT OR IGNORE INTO users (email, full_name) VALUES (?, ?)", PEOPLE)
    conn.commit()
