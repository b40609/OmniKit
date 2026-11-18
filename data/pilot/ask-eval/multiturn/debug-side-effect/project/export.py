"""匯出報表：手機顯示成 0912-345-678。"""
from validators import normalize_phone


def format_phone(raw):
    phone = normalize_phone(raw)
    if phone is None:
        return ""
    return f"{phone[:4]}-{phone[4:7]}-{phone[7:]}"


def export_rows(db):
    return [[uid, rec["name"], format_phone(rec["phone"])] for uid, rec in sorted(db.items())]
