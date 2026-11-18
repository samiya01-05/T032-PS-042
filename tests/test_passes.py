from datetime import datetime, timedelta

from passes import Pass, PassBook, end_of_day

T0 = datetime(2026, 10, 12, 8, 0, 0)


def book(**kw):
    return PassBook([Pass.from_purchase("T1", "P1", T0, **kw)])


def test_valid_pass_found():
    assert book().commuter("T1", "P1", T0 + timedelta(days=1)) is not None


def test_wrong_plaza_not_valid():
    assert book().commuter("T1", "P2", T0 + timedelta(days=1)) is None


def test_expired_after_30_days():
    assert book().commuter("T1", "P1", T0 + timedelta(days=30, seconds=1)) is None
    assert book().commuter("T1", "P1", T0 + timedelta(days=30)) is not None


def test_before_purchase_not_valid():
    assert book().commuter("T1", "P1", T0 - timedelta(seconds=1)) is None


def test_exhausted_pass_not_returned():
    b = book()
    p = b.commuter("T1", "P1", T0)
    p.journeys_used = 50
    assert b.commuter("T1", "P1", T0) is None


def test_unknown_tag_is_safe():
    assert book().commuter("NOPE", "P1", T0) is None


def test_resident_pass_is_separate_kind():
    b = PassBook([Pass.from_purchase("T1", "P1", T0, kind="RESIDENT_MONTHLY")])
    assert b.commuter("T1", "P1", T0) is None
    assert b.resident("T1", "P1", T0) is not None


def test_end_of_day_helper():
    assert end_of_day(datetime(2026, 10, 31).date()) == datetime(2026, 10, 31, 23, 59, 59)
