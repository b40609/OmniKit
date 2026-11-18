"""匯出報表。"""
import csv

from shop.orders import load_orders


def export_report(month, path, orders=None):
    orders = load_orders() if orders is None else orders
    rows = sorted((o for o in orders if o["date"].startswith(month + "-") and o["status"] != "cancelled"),
                  key=lambda o: (o["date"], o["id"]))
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["訂單編號", "日期", "客戶", "金額"])
        for o in rows:
            w.writerow([o["id"], o["date"], o["customer"], int(round(o["amount"]))])
