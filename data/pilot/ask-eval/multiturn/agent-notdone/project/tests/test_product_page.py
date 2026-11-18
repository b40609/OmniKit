import unittest

from product_page import price_label


class ProductPageTest(unittest.TestCase):
    def test_price_with_tax(self):
        self.assertEqual(price_label({"price": 1000}), "NT$1,050")


if __name__ == "__main__":
    unittest.main()
