import random
import unittest

from ws_client.backoff import Backoff


class BackoffTest(unittest.TestCase):
    def test_first_delay(self):
        b = Backoff(jitter=0)
        self.assertEqual(b.next_delay(), 1)
        self.assertEqual(b.next_delay(), 2)

    def test_cap_without_jitter(self):
        b = Backoff(jitter=0)
        for _ in range(10):
            d = b.next_delay()
        self.assertEqual(d, 30)


if __name__ == "__main__":
    unittest.main()
