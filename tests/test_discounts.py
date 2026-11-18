from datetime import datetime
from decimal import Decimal as D

from discounts import apply_discounts, is_night


def at(h, m=0, s=0):
    return datetime(2026, 10, 12, h, m, s)


def test_night_window_boundaries():                     # EC-06
    assert not is_night(at(21, 59, 59))
    assert is_night(at(22, 0, 0))
    assert is_night(at(5, 59, 59))
    assert not is_night(at(6, 0, 0))


def test_no_discount():
    assert apply_discounts(D("285"), False, at(12), True) == (D("285.00"), "NONE", D("0.00"))


def test_return_only():
    assert apply_discounts(D("85"), True, at(12), False) == (D("42.50"), "RETURN", D("42.50"))


def test_night_only_commercial():
    assert apply_discounts(D("285"), False, at(22), True) == (D("256.50"), "NIGHT", D("28.50"))


def test_night_ignored_for_non_commercial():
    assert apply_discounts(D("85"), False, at(23), False)[1] == "NONE"


def test_return_then_night():
    # 285 * 0.5 = 142.5, then * 0.9 = 128.25
    assert apply_discounts(D("285"), True, at(23), True) == (D("128.25"), "RETURN+NIGHT", D("156.75"))
