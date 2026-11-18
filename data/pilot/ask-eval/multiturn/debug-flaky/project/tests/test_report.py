import unittest

from report import top_customers, totals_by_customer

ORDERS = [
    {"customer": "chen", "amount": 300},
    {"customer": "lin", "amount": 500},
    {"customer": "wang", "amount": 300},
    {"customer": "huang", "amount": 300},
    {"customer": "lin", "amount": 100},
]


class ReportTest(unittest.TestCase):
    def test_totals(self):
        self.assertEqual(totals_by_customer(ORDERS)["lin"], 600)

    def test_top_customers(self):
        self.assertEqual(top_customers(ORDERS, 3), ["lin", "chen", "huang"])


if __name__ == "__main__":
    unittest.main()
