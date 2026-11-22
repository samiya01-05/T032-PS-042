import unittest
from datetime import datetime
from decimal import Decimal as D

from src.discounts import apply_discounts, is_night


def at(h, m=0, s=0):
    return datetime(2026, 10, 12, h, m, s)


class DiscountTests(unittest.TestCase):
    def test_ec06_night_window_boundaries(self):
        self.assertFalse(is_night(at(21, 59, 59)))
        self.assertTrue(is_night(at(22, 0, 0)))
        self.assertTrue(is_night(at(5, 59, 59)))
        self.assertFalse(is_night(at(6, 0, 0)))

    def test_no_discount(self):
        self.assertEqual(apply_discounts(D("285"), False, at(12), True),
                         (D("285.00"), "NONE", D("0.00")))

    def test_return_only(self):
        self.assertEqual(apply_discounts(D("85"), True, at(12), False),
                         (D("42.50"), "RETURN", D("42.50")))

    def test_night_only_for_commercial(self):
        self.assertEqual(apply_discounts(D("285"), False, at(22), True),
                         (D("256.50"), "NIGHT", D("28.50")))

    def test_night_ignored_for_non_commercial(self):
        self.assertEqual(apply_discounts(D("85"), False, at(23), False)[1], "NONE")

    def test_return_then_night_is_applied_in_that_order(self):
        # 285 x 0.5 = 142.50, then x 0.9 = 128.25
        self.assertEqual(apply_discounts(D("285"), True, at(23), True),
                         (D("128.25"), "RETURN+NIGHT", D("156.75")))

    def test_rounding_is_half_up_once(self):
        # 155 x 0.5 = 77.50 ; x 0.9 = 69.75 (no early rounding)
        self.assertEqual(apply_discounts(D("155"), True, at(23), True)[0], D("69.75"))
        # 85 x 0.5 x 0.9 = 38.25
        self.assertEqual(apply_discounts(D("85"), True, at(23), True)[0], D("38.25"))


if __name__ == "__main__":
    unittest.main()
