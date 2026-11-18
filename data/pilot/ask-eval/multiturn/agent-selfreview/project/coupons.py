"""優惠券。

規則：
- kind="percent"：value 是折扣百分比，例如 10 代表打九折（折掉 10%）。
- kind="fixed"：value 是折抵金額（元）。
- min_spend：小計「達到」這個金額（含）才能用。
- expires：到期日（date），當天整天都還能用。
- 折完的金額最低 0 元，不會變負的；結果四捨五入到整數元。
"""
from datetime import date


def can_use(coupon, subtotal, today):
    if subtotal > coupon.get("min_spend", 0) and today < coupon["expires"]:
        return True
    return False


def apply_coupon(subtotal, coupon, today=None):
    """回傳折扣後的金額；不能用就回傳原小計。"""
    today = today or date.today()
    if not can_use(coupon, subtotal, today):
        return subtotal
    if coupon["kind"] == "percent":
        return round(subtotal - coupon["value"])
    return round(subtotal - coupon["value"])
