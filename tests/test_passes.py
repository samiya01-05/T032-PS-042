import unittest
from datetime import date, datetime, timedelta

from src.passes import (consume_journey, find_commuter, find_resident, journeys_left, valid_at)
from tests.a_helpers import commuter, resident_pass, state, tag

T0 = datetime(2026, 10, 12, 8, 0, 0)


def st(*passes):
    return state(tag(), passes=passes)


class PassTests(unittest.TestCase):
    def test_valid_commuter_pass_found(self):
        self.assertIsNotNone(find_commuter(st(commuter()), "T1", "PLZ-01", T0))

    def test_wrong_plaza_not_valid(self):
        self.assertIsNone(find_commuter(st(commuter()), "T1", "PLZ-02", T0))

    def test_valid_to_day_is_inclusive_and_next_day_lapses(self):
        p = commuter(end=date(2026, 10, 12))
        self.assertIsNotNone(find_commuter(st(p), "T1", "PLZ-01", datetime(2026, 10, 12, 23, 59, 59)))
        self.assertIsNone(find_commuter(st(p), "T1", "PLZ-01", datetime(2026, 10, 13, 0, 0, 0)))

    def test_before_purchase_date_not_valid(self):
        p = commuter(start=date(2026, 10, 13))
        self.assertIsNone(find_commuter(st(p), "T1", "PLZ-01", T0))

    def test_exhausted_pass_not_returned(self):
        self.assertIsNone(find_commuter(st(commuter(left=0)), "T1", "PLZ-01", T0))

    def test_last_journey_then_exhausted(self):
        p = commuter(left=1)
        s = st(p)
        found = find_commuter(s, "T1", "PLZ-01", T0)
        consume_journey(found)
        self.assertEqual(journeys_left(p), 0)
        self.assertIsNone(find_commuter(s, "T1", "PLZ-01", T0 + timedelta(hours=1)))

    def test_unknown_tag_is_safe(self):
        self.assertIsNone(find_commuter(st(commuter()), "NOPE", "PLZ-01", T0))

    def test_resident_pass_is_a_separate_kind(self):
        s = st(resident_pass())
        self.assertIsNone(find_commuter(s, "T1", "PLZ-01", T0))
        self.assertIsNotNone(find_resident(s, "T1", "PLZ-01", T0))

    def test_resident_pass_valid_at(self):
        self.assertTrue(valid_at(resident_pass(), "PLZ-01", T0))
        self.assertFalse(valid_at(resident_pass(), "PLZ-03", T0))

    def test_missing_counters_default_to_fifty_and_zero(self):
        p = commuter()
        p.journeys_total = None
        p.journeys_used = None
        self.assertEqual(journeys_left(p), 50)


if __name__ == "__main__":
    unittest.main()
