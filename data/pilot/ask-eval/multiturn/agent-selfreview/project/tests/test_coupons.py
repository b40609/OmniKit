import unittest
from datetime import date

from coupons import apply_coupon

TODAY = date(2026, 11, 18)


class CouponTest(unittest.TestCase):
    def test_fixed(self):
        c = {"kind": "fixed", "value": 100, "min_spend": 500, "expires": date(2026, 12, 31)}
        self.assertEqual(apply_coupon(800, c, TODAY), 700)

    def test_not_enough(self):
        c = {"kind": "fixed", "value": 100, "min_spend": 500, "expires": date(2026, 12, 31)}
        self.assertEqual(apply_coupon(300, c, TODAY), 300)


if __name__ == "__main__":
    unittest.main()
