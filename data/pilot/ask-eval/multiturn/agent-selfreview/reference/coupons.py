"""優惠券（參考修法）。"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def can_use(coupon, subtotal, today):
    return subtotal >= coupon.get("min_spend", 0) and today <= coupon["expires"]


def apply_coupon(subtotal, coupon, today=None):
    today = today or date.today()
    if not can_use(coupon, subtotal, today):
        return subtotal
    if coupon["kind"] == "percent":
        result = Decimal(subtotal) * (100 - Decimal(coupon["value"])) / 100
    else:
        result = Decimal(subtotal) - Decimal(coupon["value"])
    return max(0, int(result.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
