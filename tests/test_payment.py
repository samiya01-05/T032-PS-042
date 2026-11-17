from datetime import datetime, timedelta
from decimal import Decimal as D

import decision_log
from helpers import T0, make_ctx, txn
from passes import Pass
from payment import process_txn


def test_hotlisted_rejected():
    r = process_txn(txn(T0), make_ctx(status="HOTLISTED"))
    assert (r.decision, r.amount, r.payment_mode) == ("REJECTED", D("0"), "NONE")
    assert r.rule_ids == "BR-09" and r.balance_after == D("1000")


def test_plain_charge():
    r = process_txn(txn(T0), make_ctx())
    assert (r.decision, r.amount, r.payment_mode) == ("CHARGED", D("85.00"), "TAG")
    assert r.balance_after == D("915.00") and r.rule_ids == "BR-01"


def test_ec01_return_at_exactly_24h():
    c = make_ctx()
    process_txn(txn(T0), c)
    r = process_txn(txn(T0 + timedelta(hours=24), n=2), c)
    assert r.discount_type == "RETURN" and r.amount == D("42.50")
    assert "BR-02" in r.rules


def test_return_only_once_per_24h():
    c = make_ctx()
    process_txn(txn(T0), c)
    process_txn(txn(T0 + timedelta(hours=2), n=2), c)
    r = process_txn(txn(T0 + timedelta(hours=4), n=3), c)
    assert r.discount_type == "NONE" and r.amount == D("85.00")


def test_ec02_last_pass_journey_then_return():
    p = Pass.from_purchase("T1", "P1", T0 - timedelta(days=1))
    p.journeys_used = 49
    c = make_ctx(passes=[p])
    r1 = process_txn(txn(T0), c)
    r2 = process_txn(txn(T0 + timedelta(hours=10), n=2), c)
    assert r1.decision == "PASS" and r1.amount == D("0")
    assert p.journeys_used == 50
    assert r2.decision == "CHARGED" and r2.discount_type == "RETURN" and r2.amount == D("42.50")


def test_pass_beats_night_and_return():
    p = Pass.from_purchase("T1", "P1", T0 - timedelta(days=1))
    c = make_ctx("BUS_TRUCK", passes=[p])
    r = process_txn(txn(datetime(2026, 10, 12, 23, 0, 0), "BUS_TRUCK"), c)
    assert r.decision == "PASS" and r.amount == D("0") and r.discount_type == "NONE"


def test_ec03_balance_equal_to_fee():
    r = process_txn(txn(T0), make_ctx(bal="85"))
    assert r.decision == "CHARGED" and r.balance_after == D("0")
    assert r.tag_status_after == "ACTIVE"


def test_low_balance_declined_cash_double():
    r = process_txn(txn(T0), make_ctx(bal="84.99"))
    assert (r.decision, r.payment_mode, r.amount) == ("DECLINED_CASH", "CASH", D("170.00"))
    assert r.penalty == D("85.00") and r.tag_status_after == "LOW_BALANCE"
    assert r.balance_after == D("84.99") and "BR-07" in r.rules


def test_ec04_third_mismatch_day_30():
    c = make_ctx()
    process_txn(txn(T0, "LCV", n=1), c)
    process_txn(txn(T0 + timedelta(days=10), "LCV", n=2), c)
    r = process_txn(txn(T0 + timedelta(days=30), "LCV", n=3), c)
    assert r.penalty == D("0.00") and r.amount == D("140.00")
    assert c.tags["T1"].reverify and "BR-06" in r.rules


def test_mismatch_higher_penalty_added():
    r = process_txn(txn(T0, "LCV"), make_ctx())
    assert r.charged_class == "LCV" and r.base_fee == D("140")
    assert r.penalty == D("100.00") and r.amount == D("240.00")


def test_mismatch_lower_charges_tag_class():
    r = process_txn(txn(T0, "CAR"), make_ctx("BUS_TRUCK"))
    assert r.charged_class == "BUS_TRUCK" and r.amount == D("285.00") and r.penalty == D("0")


def test_ec05_resident_on_commercial_class_not_exempt():
    p = Pass.from_purchase("T1", "P1", T0 - timedelta(days=1), kind="RESIDENT_MONTHLY")
    c = make_ctx("LCV", resident=True, dist=5, passes=[p])
    r = process_txn(txn(T0, "LCV"), c)
    assert r.decision == "CHARGED" and r.amount == D("140.00")


def test_resident_car_exempt_at_exactly_20km():
    p = Pass.from_purchase("T1", "P1", T0 - timedelta(days=1), kind="RESIDENT_MONTHLY")
    r = process_txn(txn(T0), make_ctx(resident=True, dist="20.0", passes=[p]))
    assert r.decision == "RESIDENT" and r.amount == D("0") and r.rule_ids == "BR-01;BR-04"


def test_resident_over_20km_pays():
    p = Pass.from_purchase("T1", "P1", T0 - timedelta(days=1), kind="RESIDENT_MONTHLY")
    r = process_txn(txn(T0), make_ctx(resident=True, dist="20.5", passes=[p]))
    assert r.decision == "CHARGED"


def test_ec06_bus_truck_at_2200():
    r = process_txn(txn(datetime(2026, 10, 12, 22, 0, 0), "BUS_TRUCK"), make_ctx("BUS_TRUCK"))
    assert r.discount_type == "NIGHT" and r.amount == D("256.50")


def test_night_not_given_to_car():
    r = process_txn(txn(datetime(2026, 10, 12, 23, 0, 0)), make_ctx())
    assert r.discount_type == "NONE" and r.amount == D("85.00")


def test_return_plus_night_combined():
    c = make_ctx("BUS_TRUCK")
    process_txn(txn(datetime(2026, 10, 12, 20, 0, 0), "BUS_TRUCK"), c)
    r = process_txn(txn(datetime(2026, 10, 12, 23, 0, 0), "BUS_TRUCK", n=2), c)
    assert r.discount_type == "RETURN+NIGHT" and r.amount == D("128.25")


def test_ec08_waiver_on_blacklisted_still_cash():
    r = process_txn(txn(T0, q=30, flag=True), make_ctx(status="BLACKLISTED"))
    assert r.decision == "BLACKLIST_CASH" and r.amount == D("170.00") and r.payment_mode == "CASH"


def test_waiver_boundaries():
    assert process_txn(txn(T0, q=10, flag=True), make_ctx()).decision == "CHARGED"
    assert process_txn(txn(T0, q=11, flag=True), make_ctx()).decision == "WAIVED"
    assert process_txn(txn(T0, q=30, flag=False), make_ctx()).decision == "CHARGED"


def test_waived_changes_nothing_else():
    c = make_ctx()
    r = process_txn(txn(T0, q=30, flag=True), c)
    assert r.amount == D("0") and r.balance_after == D("1000")
    # a waived crossing is not a "first" crossing, so no return discount later
    assert process_txn(txn(T0 + timedelta(hours=1), n=2), c).discount_type == "NONE"


def test_other_plaza_uses_own_tariff_and_own_return_window():
    c = make_ctx()
    process_txn(txn(T0), c)
    r = process_txn(txn(T0 + timedelta(hours=1), n=2, plaza="P2"), c)
    assert r.base_fee == D("95") and r.discount_type == "NONE"


def test_balance_carries_between_transactions():
    c = make_ctx(bal="100")
    process_txn(txn(T0), c)
    r = process_txn(txn(T0 + timedelta(days=2), n=2), c)   # 15 left, fee 85
    assert r.decision == "DECLINED_CASH" and c.tags["T1"].status == "LOW_BALANCE"


def test_decision_log_row_has_17_columns():
    r = process_txn(txn(T0), make_ctx())
    row = decision_log.to_row(r)
    assert len(row) == 17 == len(decision_log.COLUMNS)
    assert row[0] == "X1" and row[1] == "2026-10-12 08:00:00"
    assert row[decision_log.COLUMNS.index("amount")] == "85.00"
    assert row[-1] == "BR-01"
