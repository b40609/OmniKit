import pathlib
import unittest

from importer import parse_csv, total_amount

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "sample.csv"


class ImporterTest(unittest.TestCase):
    def test_parse_sample(self):
        rows = parse_csv(DATA)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["order_id"], "A001")

    def test_total(self):
        self.assertEqual(total_amount([{"amount": "100"}, {"amount": "250"}]), 350)


if __name__ == "__main__":
    unittest.main()
