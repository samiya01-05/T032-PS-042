from datetime import datetime, timedelta
from decimal import Decimal as D

from violation import AvcTracker

T0 = datetime(2026, 10, 12, 8, 0, 0)


def test_same_class_no_mismatch():
    assert AvcTracker().evaluate("T", T0, "CAR", "CAR") == ("CAR", D("0.00"), False, False)


def test_lower_detected_charges_tag_class_no_penalty():
    assert AvcTracker().evaluate("T", T0, "BUS_TRUCK", "LCV") == ("BUS_TRUCK", D("0.00"), False, False)


def test_higher_detected_charges_detected_plus_100():
    assert AvcTracker().evaluate("T", T0, "CAR", "LCV") == ("LCV", D("100.00"), True, False)


def test_third_mismatch_on_day_30_reverifies_no_penalty():     # EC-04
    a = AvcTracker()
    a.evaluate("T", T0, "CAR", "LCV")
    a.evaluate("T", T0 + timedelta(days=10), "CAR", "LCV")
    assert a.evaluate("T", T0 + timedelta(days=30), "CAR", "LCV") == ("LCV", D("0.00"), True, True)


def test_third_mismatch_after_day_30_is_just_a_penalty():
    a = AvcTracker()
    a.evaluate("T", T0, "CAR", "LCV")
    a.evaluate("T", T0 + timedelta(days=10), "CAR", "LCV")
    r = a.evaluate("T", T0 + timedelta(days=30, seconds=1), "CAR", "LCV")
    assert r == ("LCV", D("100.00"), True, False)    # first one fell out; only 2 in window


def test_lower_mismatches_do_not_count():
    a = AvcTracker()
    for i in range(5):
        a.evaluate("T", T0 + timedelta(days=i), "BUS_TRUCK", "CAR")
    assert a.evaluate("T", T0 + timedelta(days=6), "CAR", "LCV")[1] == D("100.00")


def test_seed_from_avc_history_counts():
    a = AvcTracker(seed=[("T", T0 - timedelta(days=5)), ("T", T0 - timedelta(days=2))])
    assert a.evaluate("T", T0, "CAR", "LCV")[3] is True


def test_tags_are_independent():
    a = AvcTracker()
    a.evaluate("A", T0, "CAR", "LCV")
    a.evaluate("A", T0, "CAR", "LCV")
    assert a.evaluate("B", T0, "CAR", "LCV")[1] == D("100.00")
