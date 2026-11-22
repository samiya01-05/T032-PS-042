import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from src.models import EventResult, ReverseCommand, parse_ts
from src.reversal import process_reverse
from tests.helpers import charge_tag, make_result, make_state, make_tag

D = Decimal
TXN_TS = "2026-10-12 12:00:00"


def reverse_at(state, txn_id, ts):
    return process_reverse(state, ReverseCommand(1, txn_id, parse_ts(ts)))


def setup(balance="1000.00"):
    s = make_state(make_tag(balance=balance))
    charge_tag(s, "TAG1", "85.00", "TXN-1", TXN_TS)       # balance -> 915.00
    return s


class ReversalWindowTests(unittest.TestCase):
    def test_within_48h_refunds_the_tag(self):
        s = setup()
        e = reverse_at(s, "TXN-1", "2026-10-12 22:35:01")
        self.assertEqual((e.result, e.reason), (EventResult.REFUNDED, "WITHIN_48H"))
        self.assertEqual((e.amount, e.balance_after), (D("85.00"), D("1000.00")))
        self.assertEqual(s.tags["TAG1"].balance, D("1000.00"))
        self.assertTrue(s.results_by_id["TXN-1"].reversed)

    def test_ec07_exactly_48h_counts_as_within(self):
        s = setup()
        e = reverse_at(s, "TXN-1", "2026-10-14 12:00:00")
        self.assertEqual(e.result, EventResult.REFUNDED)

    def test_47h_59m_59s_is_within(self):
        s = setup()
        e = reverse_at(s, "TXN-1", "2026-10-14 11:59:59")
        self.assertEqual(e.result, EventResult.REFUNDED)

    def test_48h_and_1s_is_a_dispute_not_a_refund(self):
        s = setup()
        e = reverse_at(s, "TXN-1", "2026-10-14 12:00:01")
        self.assertEqual((e.result, e.reason), (EventResult.DISPUTE, "AFTER_48H_DISPUTE_LOGGED"))
        self.assertEqual(s.tags["TAG1"].balance, D("915.00"))      # no refund
        self.assertEqual(e.balance_after, D("915.00"))
        self.assertFalse(s.results_by_id["TXN-1"].reversed)
        self.assertEqual(s.reversal_log, [])

    def test_50_hours_is_a_dispute(self):
        s = setup()
        e = reverse_at(s, "TXN-1", "2026-10-14 14:00:00")
        self.assertEqual(e.result, EventResult.DISPUTE)


class ReversalRejectionTests(unittest.TestCase):
    def test_unknown_txn(self):
        s = setup()
        e = reverse_at(s, "TXN-404", "2026-10-12 13:00:00")
        self.assertEqual((e.result, e.reason, e.amount), (EventResult.REJECTED, "UNKNOWN_TXN", None))

    def test_cannot_reverse_twice(self):
        s = setup()
        reverse_at(s, "TXN-1", "2026-10-12 13:00:00")
        e = reverse_at(s, "TXN-1", "2026-10-12 14:00:00")
        self.assertEqual((e.result, e.reason), (EventResult.REJECTED, "ALREADY_REVERSED"))
        self.assertEqual(s.tags["TAG1"].balance, D("1000.00"))      # refunded only once

    def test_cash_transaction_has_nothing_to_refund(self):
        s = make_state(make_tag())
        s.record_result(make_result(txn_id="TXN-C", amount="170.00", decision="DECLINED_CASH",
                                    mode="CASH"))
        e = reverse_at(s, "TXN-C", "2026-10-12 13:00:00")
        self.assertEqual((e.result, e.reason), (EventResult.REJECTED, "NO_TAG_DEDUCTION"))

    def test_free_crossing_has_nothing_to_refund(self):
        s = make_state(make_tag())
        s.record_result(make_result(txn_id="TXN-W", amount="0.00", decision="WAIVED", mode="TAG"))
        e = reverse_at(s, "TXN-W", "2026-10-12 13:00:00")
        self.assertEqual(e.reason, "NO_TAG_DEDUCTION")

    def test_reverse_before_the_transaction(self):
        s = setup()
        e = reverse_at(s, "TXN-1", "2026-10-12 11:00:00")
        self.assertEqual(e.reason, "REVERSE_BEFORE_TXN")


class ReversalSettlementTests(unittest.TestCase):
    def test_accepted_reversal_is_remembered_for_settlement(self):
        s = setup()
        reverse_at(s, "TXN-1", "2026-10-13 09:00:00")
        rec = s.reversal_log[0]
        self.assertEqual((rec.txn_id, rec.bank_id, rec.amount), ("TXN-1", "BNK-01", D("85.00")))
        self.assertEqual(rec.day.isoformat(), "2026-10-13")         # date of the REVERSE command
        self.assertEqual(rec.net_value, D("83.94"))                 # 85.00 - 0.85 - 0.21


if __name__ == "__main__":
    unittest.main()
