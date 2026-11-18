import csv
import os
from datetime import date
from decimal import Decimal as D

import pytest

import dataset_engine as de


def tag(tid="T1", cls="CAR", bal="1000", local=False, exempt=False):
    b = D(bal)
    return de.TagState(tid, cls, b, local, exempt, balance=b)


def run(tags, reads=(), recharges=(), passes=()):
    e = de.Engine({t.tag_id: t for t in tags})
    e.process_events(list(reads), list(recharges), list(passes))
    return e


def rd(ts, tid="T1", lane="L1", det="CAR"):
    return {"timestamp": ts, "tag_id": tid, "lane": lane, "detected_class": det}


def rc(ts, amt, tid="T1"):
    return {"timestamp": ts, "tag_id": tid, "amount": amt}


def ps(ts, kind, tid="T1"):
    return {"timestamp": ts, "tag_id": tid, "pass_type": kind}


def test_ec1_return_at_exactly_24h():
    e = run([tag()], [rd("2026-10-08 08:15:00"), rd("2026-10-09 08:15:00")])
    assert [r["outcome"] for r in e.read_log] == ["SINGLE", "RETURN"]
    assert e.read_log[1]["fare"] == D("32.50")


def test_ec2_balance_equal_to_fare_then_negative_blacklists():
    e = run([tag(bal="65")], [rd("2026-10-01 10:00:00"), rd("2026-10-03 10:00:00"),
                              rd("2026-10-05 10:00:00")])
    a, b, c = e.read_log
    assert (a["balance_after"], a["flags"]) == (D("0"), "LOW_BALANCE")
    assert (b["balance_after"], b["flags"]) == (D("-65"), "BLACKLISTED")
    assert (c["outcome"], c["fare"], c["balance_after"]) == ("CASH_BLACKLISTED", D("130.00"), D("-65"))


def test_ec4_recharge_to_exactly_zero_stays_blacklisted_then_restores():
    e = run([tag("T", "MAV", "245")],
            [rd("2026-10-02 07:00:00", "T", det="MAV"), rd("2026-10-03 07:00:00", "T", det="MAV"),
             rd("2026-10-05 07:00:00", "T", det="MAV")],
            [rc("2026-10-02 12:00:00", "100.00", "T"), rc("2026-10-04 12:00:00", "500.00", "T")])
    assert e.read_log[0]["balance_after"] == D("-100")
    assert e.recharge_log[0]["balance_after"] == D("0")
    assert e.read_log[1]["outcome"] == "CASH_BLACKLISTED"
    assert e.read_log[2]["outcome"] == "SINGLE" and e.read_log[2]["balance_after"] == D("155")


def test_ec3_mid_month_pass_full_price_valid_to_month_end():
    e = run([tag(local=True)], passes=[ps("2026-10-15 09:40:00", "MONTHLY_LOCAL")])
    r = e.pass_log[0]
    assert (r["status"], r["price"], r["valid_from"], r["valid_to"]) == \
        ("SOLD", D("330"), "2026-10-15", "2026-10-31")


def test_trap1_non_local_rejected():
    e = run([tag()], passes=[ps("2026-10-02 10:05:00", "MONTHLY_LOCAL")])
    assert e.pass_log[0]["status"] == "REJECTED"


def test_trap2_trip_pass_covers_50_then_charges():
    reads = [rd(f"2026-10-{d:02d} 12:00:00", det="BUS_TRUCK") for d in range(1, 31)]
    reads += [rd(f"2026-10-{d:02d} 15:00:00", det="BUS_TRUCK") for d in range(1, 31)]
    e = run([tag(cls="BUS_TRUCK", bal="20000")], reads, passes=[ps("2026-10-01 00:00:00", "TRIP_50")])
    outs = [r["outcome"] for r in e.read_log]
    assert outs.count("PASS") == 50
    assert e.pass_log[0]["price"] == D("6600")          # 30 x 220


def test_trap3_duplicates_and_boundary():
    e = run([tag()], [rd("2026-10-03 22:10:02"), rd("2026-10-03 22:10:47"),
                      rd("2026-10-03 22:12:03")])       # +45 s ignored, +121 s counts
    assert [r["outcome"] for r in e.read_log] == ["SINGLE", "DUPLICATE_IGNORED", "RETURN"]
    e = run([tag()], [rd("2026-10-05 16:09:49", lane="L2"), rd("2026-10-05 16:11:49", lane="L2")])
    assert e.read_log[1]["outcome"] == "DUPLICATE_IGNORED"      # DUP_INCLUSIVE = True


def test_duplicate_is_per_lane():
    e = run([tag()], [rd("2026-10-03 22:10:02", lane="L1"), rd("2026-10-03 22:10:30", lane="L2")])
    assert e.read_log[1]["outcome"] == "RETURN"


def test_trap4_lower_detected_charges_registered_class():
    e = run([tag(cls="BUS_TRUCK")], [rd("2026-10-03 12:00:00", det="LCV")])
    r = e.read_log[0]
    assert (r["fare"], r["penalty"], r["flags"]) == (D("220.00"), D("0.00"), "")


def test_trap5_recharge_below_minimum():
    e = run([tag()], recharges=[rc("2026-10-06 12:30:00", "50.00")])
    assert e.recharge_log[0]["status"] == "REJECTED_MINIMUM"
    assert e.recharge_log[0]["balance_after"] == D("1000")


def test_trap6_higher_detected_rate_penalty_reverify():
    e = run([tag(cls="LCV")], [rd("2026-10-02 12:00:00", det="BUS_TRUCK")])
    r = e.read_log[0]
    assert (r["fare"], r["penalty"], r["balance_after"], r["flags"]) == \
        (D("220.00"), D("100.00"), D("680.00"), "MISMATCH")
    assert e.statements("2026-10")[0]["status"] == "REVERIFY"


def test_third_mismatch_in_30_days_has_no_penalty():
    reads = [rd("2026-10-01 12:00:00", det="LCV"), rd("2026-10-11 12:00:00", det="LCV"),
             rd("2026-10-31 12:00:00", det="LCV")]
    e = run([tag()], reads)
    assert [r["penalty"] for r in e.read_log] == [D("100"), D("100"), D("0")]


def test_ec5_exempt_mismatch_is_free_and_not_reverify():
    e = run([tag(cls="LCV", exempt=True)], [rd("2026-10-18 21:30:02", det="BUS_TRUCK")])
    r = e.read_log[0]
    assert (r["outcome"], r["fare"], r["penalty"], r["flags"]) == ("EXEMPT", D("0"), D("0"), "MISMATCH")
    assert e.statements("2026-10")[0]["status"] == "ACTIVE"


def test_local_car_detected_commercial_is_not_covered_by_pass():
    e = run([tag(local=True)], [rd("2026-10-16 12:00:00", det="LCV")],
            passes=[ps("2026-10-01 00:00:00", "MONTHLY_LOCAL")])
    assert e.read_log[0]["outcome"] == "SINGLE" and e.read_log[0]["penalty"] == D("100")


def test_pass_crossing_starts_return_window():
    e = run([tag(local=True)], [rd("2026-10-01 08:00:00")],
            passes=[ps("2026-10-01 00:00:00", "MONTHLY_LOCAL")])
    assert e.read_log[0]["outcome"] == "PASS"


def test_same_timestamp_order_pass_recharge_read():
    e = run([tag(bal="0")], reads=[rd("2026-10-01 08:00:00")],
            recharges=[rc("2026-10-01 08:00:00", "500.00")],
            passes=[ps("2026-10-01 08:00:00", "TRIP_50")])
    assert e.read_log[0]["outcome"] == "PASS"            # pass processed before the read


def test_night_discount_for_commercial_only():
    e = run([tag("A", "LCV"), tag("B", "CAR")],
            [rd("2026-10-01 23:00:00", "A", det="LCV"), rd("2026-10-01 23:00:01", "B")])
    assert e.read_log[0]["fare"] == D("94.50") and e.read_log[1]["fare"] == D("65.00")


def test_statement_and_daily_reconcile():
    e = run([tag(bal="500")], [rd("2026-10-01 08:00:00"), rd("2026-10-01 20:00:00", det="LCV")],
            [rc("2026-10-02 08:00:00", "100.00")])
    s = e.statements("2026-10")[0]
    assert s["closing_balance"] == s["opening_balance"] + s["recharges"] - s["fare_charged"] - s["penalties"]
    d = e.daily_collection(date(2026, 10, 1), date(2026, 10, 2))
    assert len(d) == 2 and d[0]["reads"] == 2 and d[0]["total_collection"] == d[0]["tag_collection"] + d[0]["penalties"]


# ---- the real dataset (runs only if ./data is present) -------------------------
DATA = os.path.join(os.path.dirname(__file__), "..", "data")


@pytest.mark.skipif(not os.path.exists(os.path.join(DATA, "reads.csv")), reason="no data folder")
def test_real_dataset_row_counts_and_reconciliation():
    e = de.Engine(de.load_tags(os.path.join(DATA, "tags.csv")))
    e.process_events(de.read_rows(os.path.join(DATA, "reads.csv")),
                     de.read_rows(os.path.join(DATA, "recharges.csv")),
                     de.read_rows(os.path.join(DATA, "passes.csv")))
    assert len(e.read_log) == 5404 and len(e.recharge_log) == 146 and len(e.pass_log) == 61
    for r in e.statements("2026-10"):
        assert r["closing_balance"] == r["opening_balance"] + r["recharges"] - r["fare_charged"] - r["penalties"]
    assert sum(r["penalty"] for r in e.read_log) == D("4000.00")        # 40 mismatches
    rows = {i + 2: r for i, r in enumerate(e.read_log)}
    assert rows[1272]["outcome"] == "SINGLE" and rows[1457]["outcome"] == "RETURN"   # EC1
