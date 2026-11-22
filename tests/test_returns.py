import unittest
from datetime import datetime, timedelta

from src.returns import ReturnTracker

T0 = datetime(2026, 10, 12, 8, 0, 0)
K = ("T1", "PLZ-01")


class ReturnTests(unittest.TestCase):
    def test_no_anchor_means_no_return(self):
        self.assertFalse(ReturnTracker().active(K, T0))

    def test_ec01_exactly_24h_is_a_return(self):
        r = ReturnTracker()
        r.start(K, T0)
        self.assertTrue(r.active(K, T0 + timedelta(hours=24)))

    def test_one_second_after_24h_is_not_a_return(self):
        r = ReturnTracker()
        r.start(K, T0)
        self.assertFalse(r.active(K, T0 + timedelta(hours=24, seconds=1)))

    def test_consume_makes_next_crossing_full_fare(self):
        r = ReturnTracker()
        r.start(K, T0)
        r.consume(K)
        self.assertFalse(r.active(K, T0 + timedelta(hours=1)))

    def test_start_does_not_extend_an_open_window(self):
        r = ReturnTracker()
        r.start(K, T0)
        r.start(K, T0 + timedelta(hours=10))
        self.assertEqual(r.anchor[K], T0)

    def test_expired_window_is_replaced(self):
        r = ReturnTracker()
        r.start(K, T0)
        later = T0 + timedelta(hours=30)
        r.start(K, later)
        self.assertEqual(r.anchor[K], later)

    def test_plazas_are_separate(self):
        r = ReturnTracker()
        r.start(K, T0)
        self.assertFalse(r.active(("T1", "PLZ-02"), T0 + timedelta(hours=1)))

    def test_tags_are_separate(self):
        r = ReturnTracker()
        r.start(K, T0)
        self.assertFalse(r.active(("T2", "PLZ-01"), T0 + timedelta(hours=1)))


if __name__ == "__main__":
    unittest.main()
