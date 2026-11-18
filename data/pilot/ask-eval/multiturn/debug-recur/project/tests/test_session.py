import unittest

from auth.session import create_session, is_valid


class SessionTest(unittest.TestCase):
    def test_new_session_lasts_8_hours(self):
        s = create_session("amy", at=0)
        self.assertTrue(is_valid(s, at=8 * 60 * 60 - 1))
        self.assertFalse(is_valid(s, at=8 * 60 * 60 + 1))


if __name__ == "__main__":
    unittest.main()
