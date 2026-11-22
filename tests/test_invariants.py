import unittest
from datetime import date
from decimal import Decimal

from src.invariants import check_invariants
from src.models import EventResult, ReverseCommand, TopupCommand, parse_ts
from src.reversal import process_reverse
from src.settlement import compute_settlement
from src.topup import process_topup
from tests.helpers import charge_tag, make_result, make_state, make_tag

D = Decimal


class InvariantTests(unittest.TestCase):
    def test_clean_run_has_no_problems(self):
        s = make_state(make_tag(balance="1000.00"))
        charge_tag(s, "TAG1", "85.00", "T1", "2026-10-12 08:00:00")
        process_topup(s, TopupCommand(1, "TAG1", parse_ts("2026-10-12 09:00:00"), D("500.00")))
        process_reverse(s, ReverseCommand(2, "T1", parse_ts("2026-10-12 10:00:00")))
        s.settlement_rows.extend(compute_settlement(s, date(2026, 10, 12)))
        self.assertEqual(check_invariants(s), [])

    def test_negative_balance_is_flagged(self):
        s = make_state(make_tag(balance="-1.00"))
        self.assertTrue(any("negative balance" in p for p in check_invariants(s)))

    def test_balance_trail_mismatch_is_flagged(self):
        s = make_state(make_tag(balance="1000.00"))
        charge_tag(s, "TAG1", "85.00", "T1", "2026-10-12 08:00:00")
        s.tags["TAG1"].balance += D("10.00")                  # money appears from nowhere
        self.assertTrue(any("balance trail" in p for p in check_invariants(s)))

    def test_wrong_payment_mode_is_flagged(self):
        s = make_state(make_tag())
        s.record_result(make_result(txn_id="X", decision="DECLINED_CASH", mode="TAG"))
        self.assertTrue(any("payment_mode" in p for p in check_invariants(s)))

    def test_free_decision_with_an_amount_is_flagged(self):
        s = make_state(make_tag())
        s.record_result(make_result(txn_id="X", decision="WAIVED", mode="TAG", amount="10.00"))
        self.assertTrue(any("must have amount 0" in p for p in check_invariants(s)))


if __name__ == "__main__":
    unittest.main()
