"""Member A's orchestrator: the precedence, the edge cases and the extra traps."""
import unittest
from datetime import datetime, timedelta
from decimal import Decimal as D
from unittest import mock

from src import rules_config as cfg
from src.models import AvcEvent
from src.payment import marked_for_reverification, memory_for, process_txn
from src.state import DataError
from src.writers import DECISION_LOG_COLUMNS, decision_row
from tests.a_helpers import T0, commuter, history, resident_pass, state, tag, txn


def run(s, *txns):
    return [process_txn(s, t) for t in txns]


class PrecedenceTests(unittest.TestCase):
    def test_hotlisted_is_rejected_and_nothing_else_happens(self):
        s = state(tag(status="HOTLISTED"))
        r = process_txn(s, txn(T0, avc="LCV"))
        self.assertEqual((r.decision, r.amount, r.payment_mode), ("REJECTED", D("0"), "NONE"))
        self.assertEqual((r.rule_ids, r.balance_after), ("BR-09", D("1000")))
        # a hotlisted crossing must not count as a mismatch either
        self.assertEqual(len(memory_for(s).avc.hist["T1"]), 0)

    def test_plain_charge(self):
        r = process_txn(state(tag()), txn(T0))
        self.assertEqual((r.decision, r.amount, r.payment_mode), ("CHARGED", D("85.00"), "TAG"))
        self.assertEqual((r.balance_after, r.rule_ids), (D("915.00"), "BR-01"))

    def test_ec08_waiver_on_blacklisted_tag_still_pays_double_cash(self):
        r = process_txn(state(tag(status="BLACKLISTED")), txn(T0, q=30, flag=True))
        self.assertEqual((r.decision, r.amount, r.payment_mode), ("BLACKLIST_CASH", D("170.00"), "CASH"))
        self.assertEqual(r.penalty, D("85.00"))
        self.assertEqual(r.rule_ids, "BR-01;BR-08")

    def test_waiver_boundaries(self):
        d = lambda q, f: process_txn(state(tag()), txn(T0, q=q, flag=f)).decision  # noqa: E731
        self.assertEqual(d(10, True), "CHARGED")        # exactly 10 s is not "exceeds"
        self.assertEqual(d(11, True), "WAIVED")
        self.assertEqual(d("10.01", True), "WAIVED")
        self.assertEqual(d(30, False), "CHARGED")       # no >100 m flag

    def test_waived_is_free_and_does_not_start_a_return_window(self):
        s = state(tag())
        a, b = run(s, txn(T0, q=30, flag=True), txn(T0 + timedelta(hours=1), n=2))
        self.assertEqual((a.decision, a.amount, a.balance_after), ("WAIVED", D("0"), D("1000")))
        self.assertEqual(b.discount_type, "NONE")

    def test_pass_is_consumed_before_the_return_rule(self):
        p = commuter()
        s = state(tag(), passes=[p])
        a, b = run(s, txn(T0), txn(T0 + timedelta(hours=2), n=2))
        self.assertEqual((a.decision, b.decision), ("PASS", "PASS"))
        self.assertEqual(p.journeys_used, 2)

    def test_ec02_last_pass_journey_then_return_within_24h(self):
        p = commuter(left=1)
        s = state(tag(), passes=[p])
        a, b = run(s, txn(T0), txn(T0 + timedelta(hours=10), n=2))
        self.assertEqual((a.decision, a.amount), ("PASS", D("0")))
        self.assertEqual(p.journeys_used, 50)
        self.assertEqual((b.decision, b.discount_type, b.amount), ("CHARGED", "RETURN", D("42.50")))

    def test_pass_beats_night_and_return(self):
        s = state(tag("BUS_TRUCK"), passes=[commuter()])
        r = process_txn(s, txn(datetime(2026, 10, 12, 23, 0, 0), avc="BUS_TRUCK"))
        self.assertEqual((r.decision, r.amount, r.discount_type), ("PASS", D("0"), "NONE"))

    def test_expired_pass_means_a_normal_charge(self):
        s = state(tag(), passes=[commuter(end=T0.date() - timedelta(days=1))])
        self.assertEqual(process_txn(s, txn(T0)).decision, "CHARGED")

    def test_pass_at_another_plaza_does_not_apply(self):
        s = state(tag(), passes=[commuter(plaza="PLZ-02")])
        self.assertEqual(process_txn(s, txn(T0, plaza="PLZ-01")).decision, "CHARGED")

    def test_pass_beats_resident(self):
        s = state(tag(resident=True, plaza="PLZ-01", dist=5),
                  passes=[commuter(), resident_pass()])
        self.assertEqual(process_txn(s, txn(T0)).decision, "PASS")


class ReturnJourneyTests(unittest.TestCase):
    def test_ec01_return_at_exactly_24h(self):
        s = state(tag())
        a, b = run(s, txn(T0), txn(T0 + timedelta(hours=24), n=2))
        self.assertEqual((b.discount_type, b.amount, b.rule_ids), ("RETURN", D("42.50"), "BR-01;BR-02"))

    def test_one_second_after_24h_is_full_fare(self):
        s = state(tag())
        b = run(s, txn(T0), txn(T0 + timedelta(hours=24, seconds=1), n=2))[1]
        self.assertEqual((b.discount_type, b.amount), ("NONE", D("85.00")))

    def test_only_once_per_24_hours(self):
        s = state(tag())
        c = run(s, txn(T0), txn(T0 + timedelta(hours=2), n=2), txn(T0 + timedelta(hours=4), n=3))[2]
        self.assertEqual((c.discount_type, c.amount), ("NONE", D("85.00")))

    def test_other_plaza_has_its_own_tariff_and_its_own_window(self):
        s = state(tag())
        b = run(s, txn(T0), txn(T0 + timedelta(hours=1), n=2, plaza="PLZ-02"))[1]
        self.assertEqual((b.base_fee, b.discount_type), (D("95"), "NONE"))


class BalanceTests(unittest.TestCase):
    def test_ec03_balance_exactly_equal_to_fee_is_charged(self):
        r = process_txn(state(tag(bal="85")), txn(T0))
        self.assertEqual((r.decision, r.balance_after, r.tag_status_after), ("CHARGED", D("0"), "ACTIVE"))

    def test_one_paisa_short_is_declined_to_cash_at_double(self):
        r = process_txn(state(tag(bal="84.99")), txn(T0))
        self.assertEqual((r.decision, r.payment_mode, r.amount), ("DECLINED_CASH", "CASH", D("170.00")))
        self.assertEqual((r.penalty, r.tag_status_after, r.balance_after),
                         (D("85.00"), "LOW_BALANCE", D("84.99")))
        self.assertEqual(r.rule_ids, "BR-01;BR-07")

    def test_balance_must_cover_fee_plus_mismatch_penalty(self):
        ok = process_txn(state(tag(bal="240")), txn(T0, avc="LCV"))
        self.assertEqual((ok.decision, ok.amount, ok.balance_after), ("CHARGED", D("240.00"), D("0")))
        no = process_txn(state(tag(bal="239.99")), txn(T0, avc="LCV"))
        self.assertEqual((no.decision, no.amount), ("DECLINED_CASH", D("280.00")))   # 2 x 140

    def test_decline_can_be_configured_to_double_the_penalty_too(self):
        with mock.patch.object(cfg, "DECLINE_INCLUDES_PENALTY", True):
            no = process_txn(state(tag(bal="100")), txn(T0, avc="LCV"))
        self.assertEqual(no.amount, D("480.00"))                                      # 2 x 240

    def test_balance_carries_between_transactions(self):
        s = state(tag(bal="100"))
        b = run(s, txn(T0), txn(T0 + timedelta(days=2), n=2))[1]                      # 15 left
        self.assertEqual((b.decision, s.tags["T1"].status), ("DECLINED_CASH", "LOW_BALANCE"))

    def test_low_balance_tag_with_enough_money_is_still_charged(self):
        r = process_txn(state(tag(status="LOW_BALANCE", bal="500")), txn(T0))
        self.assertEqual((r.decision, r.tag_status_after), ("CHARGED", "LOW_BALANCE"))


class MismatchTests(unittest.TestCase):
    def test_higher_detected_class_adds_the_penalty(self):
        r = process_txn(state(tag()), txn(T0, avc="LCV"))
        self.assertEqual((r.charged_class, r.base_fee, r.penalty, r.amount),
                         ("LCV", D("140"), D("100.00"), D("240.00")))
        self.assertEqual(r.rule_ids, "BR-01;BR-05")

    def test_lower_detected_class_charges_the_tag_class(self):
        r = process_txn(state(tag("BUS_TRUCK")), txn(T0, avc="CAR"))
        self.assertEqual((r.charged_class, r.amount, r.penalty), ("BUS_TRUCK", D("285.00"), D("0")))
        self.assertEqual(r.rule_ids, "BR-01")

    def test_missing_avc_reading_means_the_tag_class(self):
        r = process_txn(state(tag()), txn(T0, avc=None))
        self.assertEqual((r.charged_class, r.amount), ("CAR", D("85.00")))

    def test_ec04_third_mismatch_on_day_30_has_no_penalty_and_flags_reverification(self):
        s = state(tag())
        a, b, c = run(s, txn(T0, "LCV", n=1), txn(T0 + timedelta(days=10), "LCV", n=2),
                      txn(T0 + timedelta(days=30), "LCV", n=3))
        self.assertEqual((a.penalty, b.penalty, c.penalty), (D("100"), D("100"), D("0.00")))
        self.assertEqual(c.amount, D("140.00"))
        self.assertIn("BR-06", c.rule_ids)
        self.assertTrue(marked_for_reverification(s, "T1"))

    def test_ec04_uses_avc_history_from_before_the_run(self):
        hist = [history("T1", datetime(2026, 9, 14, 8, 0, 0), "LCV"),
                history("T1", datetime(2026, 9, 28, 8, 0, 0), "LCV")]
        s = state(tag(), avc=hist)
        r = process_txn(s, txn(datetime(2026, 10, 14, 8, 0, 0), "LCV"))     # day 30 exactly
        self.assertEqual((r.penalty, r.amount), (D("0.00"), D("140.00")))
        self.assertIn("BR-06", r.rule_ids)

    def test_history_events_that_were_not_higher_class_are_ignored(self):
        hist = [AvcEvent("T1", T0 - timedelta(days=3), "PLZ-01", "CAR"),
                AvcEvent("T1", T0 - timedelta(days=2), "PLZ-01", "CAR")]
        r = process_txn(state(tag(), avc=hist), txn(T0, "LCV"))
        self.assertEqual(r.penalty, D("100.00"))

    def test_waived_and_blacklisted_crossings_still_count_as_mismatches(self):
        s = state(tag())
        run(s, txn(T0, "LCV", q=30, flag=True, n=1), txn(T0 + timedelta(days=1), "LCV", n=2))
        r = process_txn(s, txn(T0 + timedelta(days=2), "LCV", n=3))
        self.assertIn("BR-06", r.rule_ids)

    def test_commuter_pass_covers_a_higher_class_crossing_by_default(self):
        p = commuter()
        r = process_txn(state(tag(), passes=[p]), txn(T0, "LCV"))
        self.assertEqual((r.decision, r.amount, r.charged_class), ("PASS", D("0"), "LCV"))
        self.assertEqual(r.rule_ids, "BR-01;BR-05;BR-03")

    def test_pass_coverage_of_higher_class_is_configurable(self):
        with mock.patch.object(cfg, "PASS_COVERS_HIGHER_CLASS", False):
            r = process_txn(state(tag(), passes=[commuter()]), txn(T0, "LCV"))
        self.assertEqual((r.decision, r.amount), ("CHARGED", D("240.00")))


class ResidentTests(unittest.TestCase):
    def resident_state(self, cls="CAR", dist="6.5", plaza="PLZ-01"):
        return state(tag(cls, resident=True, plaza=plaza, dist=dist), passes=[resident_pass()])

    def test_resident_car_is_free(self):
        r = process_txn(self.resident_state(), txn(T0))
        self.assertEqual((r.decision, r.amount, r.rule_ids), ("RESIDENT", D("0"), "BR-01;BR-04"))
        self.assertEqual(r.balance_after, D("1000"))

    def test_resident_exactly_20_km_is_eligible(self):
        self.assertEqual(process_txn(self.resident_state(dist="20.0"), txn(T0)).decision, "RESIDENT")

    def test_resident_over_20_km_pays(self):
        self.assertEqual(process_txn(self.resident_state(dist="20.5"), txn(T0)).decision, "CHARGED")

    def test_ec05_resident_tag_on_a_commercial_class_pays(self):
        r = process_txn(self.resident_state(cls="LCV"), txn(T0, avc="LCV"))
        self.assertEqual((r.decision, r.amount), ("CHARGED", D("140.00")))

    def test_resident_car_detected_as_a_commercial_class_pays_class_plus_penalty(self):
        r = process_txn(self.resident_state(), txn(T0, avc="LCV"))
        self.assertEqual((r.decision, r.amount), ("CHARGED", D("240.00")))

    def test_resident_exemption_applies_only_at_the_registered_plaza(self):
        self.assertEqual(process_txn(self.resident_state(), txn(T0, plaza="PLZ-02")).decision, "CHARGED")

    def test_resident_without_a_valid_pass_pays(self):
        s = state(tag(resident=True, plaza="PLZ-01", dist=5))
        self.assertEqual(process_txn(s, txn(T0)).decision, "CHARGED")


class NightDiscountTests(unittest.TestCase):
    def test_ec06_bus_truck_at_exactly_2200_gets_the_night_discount(self):
        r = process_txn(state(tag("BUS_TRUCK")), txn(datetime(2026, 10, 12, 22, 0, 0), "BUS_TRUCK"))
        self.assertEqual((r.discount_type, r.discount_amount, r.amount, r.rule_ids),
                         ("NIGHT", D("28.50"), D("256.50"), "BR-01;BR-10"))

    def test_one_second_before_2200_no_discount(self):
        r = process_txn(state(tag("BUS_TRUCK")), txn(datetime(2026, 10, 12, 21, 59, 59), "BUS_TRUCK"))
        self.assertEqual((r.discount_type, r.amount), ("NONE", D("285.00")))

    def test_0600_is_not_night(self):
        r = process_txn(state(tag("BUS_TRUCK")), txn(datetime(2026, 10, 12, 6, 0, 0), "BUS_TRUCK"))
        self.assertEqual(r.discount_type, "NONE")

    def test_cars_get_no_night_discount(self):
        r = process_txn(state(tag()), txn(datetime(2026, 10, 12, 23, 0, 0)))
        self.assertEqual((r.discount_type, r.amount), ("NONE", D("85.00")))

    def test_a_commercially_flagged_car_gets_the_night_discount(self):
        r = process_txn(state(tag(commercial=True)), txn(datetime(2026, 10, 12, 23, 0, 0)))
        self.assertEqual((r.discount_type, r.amount), ("NIGHT", D("76.50")))

    def test_return_and_night_combined(self):
        s = state(tag("BUS_TRUCK"))
        b = run(s, txn(datetime(2026, 10, 12, 20, 0, 0), "BUS_TRUCK"),
                txn(datetime(2026, 10, 12, 23, 0, 0), "BUS_TRUCK", n=2))[1]
        self.assertEqual((b.discount_type, b.amount, b.rule_ids), ("RETURN+NIGHT", D("128.25"), "BR-01;BR-02;BR-10"))


class ContractTests(unittest.TestCase):
    def test_decision_row_has_all_17_columns(self):
        r = process_txn(state(tag()), txn(T0))
        row = decision_row(r)
        self.assertEqual(len(row), 17)
        self.assertEqual(len(DECISION_LOG_COLUMNS), 17)
        self.assertEqual((row[0], row[1], row[-1]), ("X1", "2026-10-12 08:00:00", "BR-01"))

    def test_unknown_tag_is_a_data_error(self):
        with self.assertRaises(DataError):
            process_txn(state(tag()), txn(T0, tag_id="NOPE"))

    def test_unknown_avc_class_is_a_data_error(self):
        with self.assertRaises(DataError):
            process_txn(state(tag()), txn(T0, avc="SPACESHIP"))

    def test_engine_memory_is_created_once_per_state(self):
        s = state(tag())
        self.assertIs(memory_for(s), memory_for(s))

    def test_the_result_carries_the_issuer_bank(self):
        self.assertEqual(process_txn(state(tag()), txn(T0)).bank_id, "BNK-01")


if __name__ == "__main__":
    unittest.main()
