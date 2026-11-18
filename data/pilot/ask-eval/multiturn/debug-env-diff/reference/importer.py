"""匯入客戶上傳的訂單 CSV。"""
import csv
import io


def parse_csv(path):
    """讀 CSV，回傳每列一個 dict（key 是表頭）。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(io.StringIO(f.read())) if any(row.values())]


def total_amount(rows):
    return sum(int(r["amount"]) for r in rows)
