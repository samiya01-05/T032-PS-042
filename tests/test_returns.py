from datetime import datetime, timedelta

from returns import ReturnTracker

T0 = datetime(2026, 10, 12, 8, 0, 0)
K = ("T1", "P1")


def test_no_anchor_means_no_return():
    assert not ReturnTracker().active(K, T0)


def test_exactly_24h_is_return():                  # EC-01
    r = ReturnTracker()
    r.start(K, T0)
    assert r.active(K, T0 + timedelta(hours=24))


def test_one_second_after_24h_is_not_return():
    r = ReturnTracker()
    r.start(K, T0)
    assert not r.active(K, T0 + timedelta(hours=24, seconds=1))


def test_consume_makes_next_crossing_full_fare():
    r = ReturnTracker()
    r.start(K, T0)
    r.consume(K)
    assert not r.active(K, T0 + timedelta(hours=1))


def test_start_does_not_extend_open_window():
    r = ReturnTracker()
    r.start(K, T0)
    r.start(K, T0 + timedelta(hours=10))
    assert r.anchor[K] == T0


def test_expired_window_is_replaced():
    r = ReturnTracker()
    r.start(K, T0)
    later = T0 + timedelta(hours=30)
    r.start(K, later)
    assert r.anchor[K] == later


def test_plazas_are_separate():
    r = ReturnTracker()
    r.start(K, T0)
    assert not r.active(("T1", "P2"), T0 + timedelta(hours=1))
