import unittest

from export import export_rows
from profile import save_profile


class ProfileExportTest(unittest.TestCase):
    def test_profile_stores_10_digits(self):
        db = {}
        self.assertEqual(save_profile(db, 1, {"name": "Amy", "phone": "0912-345-678"})["phone"], "0912345678")

    def test_export_format(self):
        db = {1: {"name": "Amy", "phone": "0912345678"}}
        self.assertEqual(export_rows(db), [[1, "Amy", "0912-345-678"]])


if __name__ == "__main__":
    unittest.main()
