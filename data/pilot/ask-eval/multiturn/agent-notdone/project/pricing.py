"""價格與稅。"""
from decimal import ROUND_HALF_UP, Decimal

TAX_RATE = Decimal("0.05")


def with_tax(amount):
    """未稅金額 -> 含稅金額（四捨五入到整數元）。"""
    return int((Decimal(str(amount)) * (1 + TAX_RATE)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
