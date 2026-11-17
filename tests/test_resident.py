from decimal import Decimal as D
from types import SimpleNamespace as NS

from resident import is_commercial, resident_eligible

PASS_OBJ = object()


def tag(resident=True, commercial=False):
    return NS(resident=resident, commercial=commercial)


def test_eligible_at_exactly_20km():
    assert resident_eligible(tag(), False, D("20.0"), PASS_OBJ)


def test_not_eligible_just_over_20km():
    assert not resident_eligible(tag(), False, D("20.01"), PASS_OBJ)


def test_commercial_not_eligible():                    # EC-05
    assert not resident_eligible(tag(), True, D("5"), PASS_OBJ)


def test_needs_resident_flag():
    assert not resident_eligible(tag(resident=False), False, D("5"), PASS_OBJ)


def test_needs_valid_pass():
    assert not resident_eligible(tag(), False, D("5"), None)


def test_needs_distance():
    assert not resident_eligible(tag(), False, None, PASS_OBJ)


def test_is_commercial():
    assert not is_commercial(tag(), "CAR")
    assert is_commercial(tag(), "LCV")
    assert is_commercial(tag(commercial=True), "CAR")
