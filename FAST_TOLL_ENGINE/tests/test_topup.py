import unittest
from datetime import datetime
from decimal import Decimal

from src.models import EventResult, Status, TopupCommand
from src.topup import process_topup
from tests.helpers import make_state, make_tag

D = Decimal


def cmd(tag_id, amount, ts=datetime(2026, 10, 13, 9, 0, 0)):
    return TopupCommand(1, tag_id, ts, D(amount))


class TopupTests(unittest.TestCase):
    def test_minimum_is_100(self):
        s = make_state(make_tag(balance="500.00"))
        e = process_topup(s, cmd("TAG1", "99.99"))
        self.assertEqual((e.result, e.reason), (EventResult.REJECTED, "BELOW_MINIMUM_100"))
        self.assertEqual(s.tags["TAG1"].balance, D("500.00"))
        e = process_topup(s, cmd("TAG1", "100.00"))
        self.assertEqual(e.result, EventResult.SUCCESS)
        self.assertEqual(s.tags["TAG1"].balance, D("600.00"))

    def test_rs_50_topup_from_the_sample_pack_is_rejected(self):
        s = make_state(make_tag(balance="2360.00"))
        e = process_topup(s, cmd("TAG1", "50.00"))
        self.assertEqual(e.result, EventResult.REJECTED)
        self.assertEqual(e.balance_after, D("2360.00"))

    def test_low_balance_chain_from_the_readme(self):
        # CAR tag at 30.00 and LOW_BALANCE: +150 -> 180 still LOW, +300 -> 480 ACTIVE
        s = make_state(make_tag(balance="30.00", status=Status.LOW_BALANCE))
        e1 = process_topup(s, cmd("TAG1", "150.00"))
        self.assertEqual((e1.balance_after, e1.reason), (D("180.00"), "STILL_LOW_BALANCE"))
        self.assertEqual(s.tags["TAG1"].status, Status.LOW_BALANCE)
        e2 = process_topup(s, cmd("TAG1", "300.00"))
        self.assertEqual((e2.balance_after, e2.reason), (D("480.00"), "STATUS_RESTORED_ACTIVE"))
        self.assertEqual(s.tags["TAG1"].status, Status.ACTIVE)

    def test_non_car_needs_more_than_500(self):
        s = make_state(make_tag(cls="LCV", balance="100.00", status=Status.LOW_BALANCE))
        process_topup(s, cmd("TAG1", "400.00"))             # exactly 500 -> not above
        self.assertEqual(s.tags["TAG1"].status, Status.LOW_BALANCE)
        process_topup(s, cmd("TAG1", "100.00"))             # 600 -> above
        self.assertEqual(s.tags["TAG1"].status, Status.ACTIVE)

    def test_active_tag_stays_active_with_reason_ok(self):
        s = make_state(make_tag(balance="1000.00"))
        e = process_topup(s, cmd("TAG1", "200.00"))
        self.assertEqual(e.reason, "OK")

    def test_blacklisted_tag_gets_money_but_keeps_status(self):
        s = make_state(make_tag(balance="0.00", status=Status.BLACKLISTED))
        process_topup(s, cmd("TAG1", "1000.00"))
        self.assertEqual(s.tags["TAG1"].balance, D("1000.00"))
        self.assertEqual(s.tags["TAG1"].status, Status.BLACKLISTED)

    def test_unknown_tag(self):
        s = make_state(make_tag())
        e = process_topup(s, cmd("NOPE", "500.00"))
        self.assertEqual((e.result, e.reason, e.balance_after), (EventResult.REJECTED, "UNKNOWN_TAG", None))

    def test_every_outcome_is_logged_in_order(self):
        s = make_state(make_tag())
        process_topup(s, cmd("TAG1", "50.00"))
        process_topup(s, cmd("TAG1", "500.00"))
        self.assertEqual([e.result for e in s.tag_events],
                         [EventResult.REJECTED, EventResult.SUCCESS])
        self.assertTrue(all(e.command == "TOPUP" for e in s.tag_events))


if __name__ == "__main__":
    unittest.main()
