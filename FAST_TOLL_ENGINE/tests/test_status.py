import unittest
from decimal import Decimal

from src.models import Decision, PayMode, Status
from src.status import (blacklist_charge, charge_tag_or_decline, hotlist_reject,
                        restore_threshold, status_after_topup)
from tests.helpers import make_tag

D = Decimal


class ChargeOrDeclineTests(unittest.TestCase):
    def test_enough_balance_is_charged(self):
        tag = make_tag(balance="600.00")
        out = charge_tag_or_decline(tag, D("85.00"))
        self.assertEqual((out.decision, out.payment_mode, out.amount), ("CHARGED", "TAG", D("85.00")))
        self.assertEqual(tag.balance, D("515.00"))
        self.assertEqual(out.balance_after, D("515.00"))
        self.assertEqual(out.penalty, D("0.00"))

    def test_ec03_balance_exactly_equal_to_fee_succeeds(self):
        tag = make_tag(cls="LCV", balance="140.00")
        out = charge_tag_or_decline(tag, D("140.00"))
        self.assertEqual(out.decision, Decision.CHARGED)
        self.assertEqual(tag.balance, D("0.00"))
        self.assertEqual(tag.status, Status.ACTIVE)

    def test_one_paisa_short_is_declined(self):
        tag = make_tag(balance="84.99")
        out = charge_tag_or_decline(tag, D("85.00"))
        self.assertEqual(out.decision, Decision.DECLINED_CASH)

    def test_decline_charges_double_in_cash_and_sets_low_balance(self):
        tag = make_tag(balance="30.00")
        out = charge_tag_or_decline(tag, D("85.00"))
        self.assertEqual((out.decision, out.payment_mode), ("DECLINED_CASH", "CASH"))
        self.assertEqual(out.amount, D("170.00"))
        self.assertEqual(out.penalty, D("85.00"))        # the extra over the plain fee
        self.assertEqual(tag.balance, D("30.00"))        # tag untouched
        self.assertEqual(tag.status, Status.LOW_BALANCE)
        self.assertEqual(out.status_after, Status.LOW_BALANCE)

    def test_low_balance_tag_with_enough_money_is_still_charged(self):
        tag = make_tag(balance="180.00", status=Status.LOW_BALANCE)
        out = charge_tag_or_decline(tag, D("85.00"))
        self.assertEqual(out.decision, Decision.CHARGED)
        self.assertEqual(tag.status, Status.LOW_BALANCE)  # only a top-up can restore ACTIVE

    def test_rounding_is_half_up(self):
        tag = make_tag(balance="0.00")
        out = charge_tag_or_decline(tag, D("42.505"))
        self.assertEqual(out.amount, D("85.02"))          # 42.51 * 2


class HotlistBlacklistTests(unittest.TestCase):
    def test_hotlist_rejects_with_no_fee(self):
        tag = make_tag(status=Status.HOTLISTED, balance="500.00")
        out = hotlist_reject(tag)
        self.assertEqual((out.decision, out.payment_mode, out.amount),
                         ("REJECTED", PayMode.NONE, D("0.00")))
        self.assertEqual(tag.balance, D("500.00"))

    def test_blacklist_pays_double_cash_and_balance_untouched(self):
        tag = make_tag(cls="BUS_TRUCK", status=Status.BLACKLISTED, balance="9000.00")
        out = blacklist_charge(tag, D("285.00"))
        self.assertEqual((out.decision, out.payment_mode, out.amount),
                         ("BLACKLIST_CASH", "CASH", D("570.00")))
        self.assertEqual(out.penalty, D("285.00"))
        self.assertEqual(tag.balance, D("9000.00"))
        self.assertEqual(tag.status, Status.BLACKLISTED)

    def test_declined_blacklisted_status_is_not_overwritten(self):
        tag = make_tag(balance="0.00", status=Status.BLACKLISTED)
        charge_tag_or_decline(tag, D("85.00"))
        self.assertEqual(tag.status, Status.BLACKLISTED)


class ThresholdTests(unittest.TestCase):
    def test_thresholds_by_class(self):
        self.assertEqual(restore_threshold(make_tag(cls="CAR")), D("200.00"))
        self.assertEqual(restore_threshold(make_tag(cls="LCV")), D("500.00"))
        self.assertEqual(restore_threshold(make_tag(cls="OVERSIZE")), D("500.00"))

    def test_must_be_strictly_above_threshold(self):
        tag = make_tag(balance="200.00", status=Status.LOW_BALANCE)
        self.assertEqual(status_after_topup(tag), Status.LOW_BALANCE)
        tag.balance = D("200.01")
        self.assertEqual(status_after_topup(tag), Status.ACTIVE)

    def test_non_car_needs_500(self):
        tag = make_tag(cls="LCV", balance="500.00", status=Status.LOW_BALANCE)
        self.assertEqual(status_after_topup(tag), Status.LOW_BALANCE)
        tag.balance = D("500.01")
        self.assertEqual(status_after_topup(tag), Status.ACTIVE)

    def test_blacklisted_and_active_do_not_change(self):
        self.assertEqual(status_after_topup(make_tag(status=Status.BLACKLISTED, balance="9999")),
                         Status.BLACKLISTED)
        self.assertEqual(status_after_topup(make_tag(status=Status.ACTIVE, balance="1")),
                         Status.ACTIVE)


if __name__ == "__main__":
    unittest.main()
