import unittest
from datetime import date
from decimal import Decimal

from src.models import ReverseCommand, parse_ts
from src.reversal import process_reverse
from src.settlement import compute_settlement, fee_split
from tests.helpers import charge_tag, make_result, make_state, make_tag

D = Decimal
DAY = date(2026, 10, 12)


def row(rows, party):
    return next(r for r in rows if r.party_id == party)


class FeeSplitTests(unittest.TestCase):
    def test_one_percent_and_quarter_percent(self):
        self.assertEqual(fee_split(D("100.00")), (D("1.00"), D("0.25")))

    def test_switch_fee_rounds_half_up(self):
        # 85 * 0.0025 = 0.2125 -> 0.21 ; 90 * 0.0025 = 0.225 -> 0.23
        self.assertEqual(fee_split(D("85.00")), (D("0.85"), D("0.21")))
        self.assertEqual(fee_split(D("90.00")), (D("0.90"), D("0.23")))


class DailySettlementTests(unittest.TestCase):
    def test_single_charged_txn(self):
        s = make_state(make_tag(balance="1000.00"))
        charge_tag(s, "TAG1", "85.00", "TXN-1", "2026-10-12 08:00:00")
        rows = compute_settlement(s, DAY)
        b = row(rows, "BNK-01")
        self.assertEqual((b.successful_txns, b.gross_tag_amount), (1, D("85.00")))
        self.assertEqual((b.bank_fee, b.switch_fee, b.net_amount),
                         (D("0.85"), D("0.21"), D("83.94")))
        c = row(rows, "CONCESSIONAIRE")
        self.assertEqual((c.successful_txns, c.gross_tag_amount, c.net_amount),
                         (1, D("85.00"), D("83.94")))

    def test_every_bank_and_the_concessionaire_get_a_row(self):
        s = make_state(make_tag())
        rows = compute_settlement(s, DAY)
        self.assertEqual([r.party_id for r in rows],
                         ["BNK-01", "BNK-02", "BNK-03", "BNK-04", "CONCESSIONAIRE"])
        self.assertTrue(all(r.gross_tag_amount == 0 and r.net_amount == 0 for r in rows))

    def test_cash_is_100_percent_concessionaire_revenue(self):
        s = make_state(make_tag())
        s.record_result(make_result(txn_id="TXN-C", amount="170.00", decision="DECLINED_CASH",
                                    mode="CASH"))
        s.record_result(make_result(txn_id="TXN-B", amount="570.00", decision="BLACKLIST_CASH",
                                    mode="CASH"))
        rows = compute_settlement(s, DAY)
        self.assertEqual(row(rows, "BNK-01").cash_penalties, D("0.00"))
        c = row(rows, "CONCESSIONAIRE")
        self.assertEqual((c.cash_penalties, c.gross_tag_amount, c.net_amount),
                         (D("740.00"), D("0.00"), D("740.00")))

    def test_free_decisions_do_not_count(self):
        s = make_state(make_tag())
        for i, d in enumerate(["PASS", "RESIDENT", "WAIVED", "REJECTED"]):
            s.record_result(make_result(txn_id=f"T{i}", amount="0.00", decision=d,
                                        mode="NONE" if d == "REJECTED" else "TAG"))
        self.assertEqual(row(compute_settlement(s, DAY), "CONCESSIONAIRE").successful_txns, 0)

    def test_only_the_requested_date_is_counted(self):
        s = make_state(make_tag(balance="1000.00"))
        charge_tag(s, "TAG1", "85.00", "TXN-1", "2026-10-12 23:59:59")
        charge_tag(s, "TAG1", "85.00", "TXN-2", "2026-10-13 00:00:00")
        self.assertEqual(row(compute_settlement(s, DAY), "BNK-01").successful_txns, 1)
        self.assertEqual(row(compute_settlement(s, date(2026, 10, 13)), "BNK-01").successful_txns, 1)

    def test_each_bank_gets_its_own_tags(self):
        s = make_state(make_tag("A", bank="BNK-01"), make_tag("B", bank="BNK-03"))
        charge_tag(s, "A", "85.00", "T1", "2026-10-12 08:00:00")
        charge_tag(s, "B", "100.00", "T2", "2026-10-12 09:00:00")
        rows = compute_settlement(s, DAY)
        self.assertEqual(row(rows, "BNK-01").gross_tag_amount, D("85.00"))
        self.assertEqual(row(rows, "BNK-03").gross_tag_amount, D("100.00"))
        self.assertEqual(row(rows, "BNK-02").gross_tag_amount, D("0.00"))
        self.assertEqual(row(rows, "CONCESSIONAIRE").gross_tag_amount, D("185.00"))

    def test_concessionaire_net_is_bank_nets_plus_cash(self):
        s = make_state(make_tag("A", bank="BNK-01"))
        charge_tag(s, "A", "85.00", "T1", "2026-10-12 08:00:00")
        s.record_result(make_result(txn_id="TC", amount="170.00", decision="DECLINED_CASH",
                                    mode="CASH"))
        c = row(compute_settlement(s, DAY), "CONCESSIONAIRE")
        self.assertEqual(c.net_amount, D("83.94") + D("170.00"))


class ReversalInSettlementTests(unittest.TestCase):
    def test_same_day_reversal_cancels_the_net(self):
        s = make_state(make_tag(balance="1000.00"))
        charge_tag(s, "TAG1", "85.00", "TXN-1", "2026-10-12 08:00:00")
        process_reverse(s, ReverseCommand(1, "TXN-1", parse_ts("2026-10-12 10:00:00")))
        b = row(compute_settlement(s, DAY), "BNK-01")
        self.assertEqual((b.reversals, b.net_amount), (D("83.94"), D("0.00")))

    def test_later_reversal_shows_on_its_own_date_only(self):
        s = make_state(make_tag(balance="1000.00"))
        charge_tag(s, "TAG1", "85.00", "TXN-1", "2026-10-12 08:00:00")
        process_reverse(s, ReverseCommand(1, "TXN-1", parse_ts("2026-10-13 10:00:00")))
        day1 = row(compute_settlement(s, DAY), "BNK-01")
        day2 = row(compute_settlement(s, date(2026, 10, 13)), "BNK-01")
        self.assertEqual((day1.reversals, day1.net_amount), (D("0.00"), D("83.94")))
        self.assertEqual((day2.reversals, day2.net_amount), (D("83.94"), D("-83.94")))

    def test_dispute_does_not_touch_settlement(self):
        s = make_state(make_tag(balance="1000.00"))
        charge_tag(s, "TAG1", "85.00", "TXN-1", "2026-10-12 08:00:00")
        process_reverse(s, ReverseCommand(1, "TXN-1", parse_ts("2026-10-15 08:00:00")))
        self.assertEqual(row(compute_settlement(s, date(2026, 10, 15)), "BNK-01").reversals,
                         D("0.00"))


if __name__ == "__main__":
    unittest.main()
