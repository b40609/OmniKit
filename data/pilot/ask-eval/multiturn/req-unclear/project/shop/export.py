"""匯出報表。"""
from shop.orders import load_orders


def export_report(month, path, orders=None):
    """把某個月份（例如 "2026-10"）的訂單匯出到 path。orders 沒給就用 load_orders()。"""
    raise NotImplementedError
