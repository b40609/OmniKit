import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "_lib"))
import checklib  # noqa: E402
from datetime import date

T = date(2026, 11, 18)
P10 = {"kind": "percent", "value": 10, "min_spend": 1000, "expires": date(2026, 12, 31)}
F200 = {"kind": "fixed", "value": 200, "min_spend": 0, "expires": date(2026, 12, 31)}
CASES = [
    (1000, P10, T, 900, "客人買剛好 1,000 元，用「滿 1,000 打九折」的券還是說不能用"),
    (1500, P10, T, 1350, "打九折的券，折掉的金額還是怪怪的"),
    (2345, {**P10, "value": 15}, T, 1993, "打八五折的券，算出來的金額不對"),
    (999, P10, T, 999, "不到 1,000 元的也能用「滿 1,000」的券了"),
    (1200, {**P10, "expires": T}, T, 1080, "到期日當天用券，系統還是說過期了"),
    (1200, {**P10, "expires": date(2026, 11, 17)}, T, 1200, "已經過期的券竟然還能用"),
    (150, F200, T, 0, "折完變成負的金額還是會出現"),
    (800, F200, T, 600, "折抵 200 元的券算錯了"),
]


def check():
    checklib.workspace()
    from coupons import apply_coupon
    for subtotal, coupon, today, want, symptom in CASES:
        try:
            got = apply_coupon(subtotal, dict(coupon), today)
        except Exception as e:  # noqa: BLE001
            return [(symptom, f"{subtotal} {coupon}: {type(e).__name__} {e}")]
        if got != want:
            return [(symptom, f"{subtotal} {coupon} -> {got}，期望 {want}")]
    return []


checklib.run(check)
