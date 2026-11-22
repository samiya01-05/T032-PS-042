import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D

from src.violation import AvcTracker

T0 = datetime(2026, 10, 12, 8, 0, 0)
Z = D("0.00")


class ViolationTests(unittest.TestCase):
    def test_same_class_no_mismatch(self):
        self.assertEqual(AvcTracker().evaluate("T", T0, "CAR", "CAR"), ("CAR", Z, False, False))

    def test_lower_detected_charges_tag_class_no_penalty(self):
        self.assertEqual(AvcTracker().evaluate("T", T0, "BUS_TRUCK", "LCV"),
                         ("BUS_TRUCK", Z, False, False))

    def test_higher_detected_charges_detected_plus_100(self):
        self.assertEqual(AvcTracker().evaluate("T", T0, "CAR", "LCV"),
                         ("LCV", D("100.00"), True, False))

    def test_ec04_third_mismatch_on_day_30_reverifies_no_penalty(self):
        a = AvcTracker()
        a.evaluate("T", T0, "CAR", "LCV")
        a.evaluate("T", T0 + timedelta(days=10), "CAR", "LCV")
        self.assertEqual(a.evaluate("T", T0 + timedelta(days=30), "CAR", "LCV"),
                         ("LCV", Z, True, True))

    def test_third_mismatch_one_second_after_day_30_is_a_normal_penalty(self):
        a = AvcTracker()
        a.evaluate("T", T0, "CAR", "LCV")
        a.evaluate("T", T0 + timedelta(days=10), "CAR", "LCV")
        self.assertEqual(a.evaluate("T", T0 + timedelta(days=30, seconds=1), "CAR", "LCV"),
                         ("LCV", D("100.00"), True, False))

    def test_lower_mismatches_do_not_count(self):
        a = AvcTracker()
        for i in range(5):
            a.evaluate("T", T0 + timedelta(days=i), "BUS_TRUCK", "CAR")
        self.assertEqual(a.evaluate("T", T0 + timedelta(days=6), "CAR", "LCV")[1], D("100.00"))

    def test_seed_from_avc_history_counts(self):
        a = AvcTracker(seed=[("T", T0 - timedelta(days=5)), ("T", T0 - timedelta(days=2))])
        self.assertTrue(a.evaluate("T", T0, "CAR", "LCV")[3])

    def test_seed_is_sorted(self):
        a = AvcTracker(seed=[("T", T0 - timedelta(days=2)), ("T", T0 - timedelta(days=5))])
        self.assertEqual(a.hist["T"], sorted(a.hist["T"]))

    def test_tags_are_independent(self):
        a = AvcTracker()
        a.evaluate("A", T0, "CAR", "LCV")
        a.evaluate("A", T0, "CAR", "LCV")
        self.assertEqual(a.evaluate("B", T0, "CAR", "LCV")[1], D("100.00"))

    def test_unknown_class_gives_clear_error(self):
        with self.assertRaises(ValueError):
            AvcTracker().evaluate("T", T0, "CAR", "TRUCKZILLA")


if __name__ == "__main__":
    unittest.main()
