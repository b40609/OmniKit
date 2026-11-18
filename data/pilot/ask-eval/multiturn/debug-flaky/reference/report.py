"""業務報表：消費金額前幾名的客戶。"""


def totals_by_customer(orders):
    totals = {}
    for o in orders:
        totals[o["customer"]] = totals.get(o["customer"], 0) + o["amount"]
    return totals


def top_customers(orders, n=3):
    """回傳消費金額前 n 名的客戶名稱。同額時依名稱排序。"""
    totals = totals_by_customer(orders)
    return sorted(totals, key=lambda c: (-totals[c], c))[:n]
