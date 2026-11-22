"""The whole merged pipeline (B's loader/top-up/reversal/settlement + A's decision engine)
on the real PS-042 sample pack. Pins the planted edge cases to exact results."""
import csv
import os
import tempfile
import unittest
from decimal import Decimal as D

from src.main import run
from src.payment import marked_for_reverification

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "sample_data")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@unittest.skipUnless(os.path.isdir(SAMPLE), "sample_data folder not present")
class MergedPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.printed = []
        cls.state = run(SAMPLE, cls.tmp.name, printer=cls.printed.append)     # the REAL engine
        cls.log = {r["txn_id"]: r for r in read_csv(os.path.join(cls.tmp.name, "decision_log.csv"))}
        cls.events = {e["reference"]: e for e in read_csv(os.path.join(cls.tmp.name, "tag_events.csv"))
                      if e["command"] == "REVERSE"}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def row(self, txn_id):
        return self.log[txn_id]

    # ---- shape
    def test_row_counts_and_invariants(self):
        self.assertEqual(len(self.log), 250)
        self.assertEqual(len(read_csv(os.path.join(self.tmp.name, "tag_events.csv"))), 15)
        self.assertEqual(len(read_csv(os.path.join(self.tmp.name, "settlement.csv"))), 25)
        self.assertIn("Invariant checks passed.", self.printed)

    def test_every_decision_is_a_known_value(self):
        known = {"CHARGED", "PASS", "RESIDENT", "WAIVED", "DECLINED_CASH", "BLACKLIST_CASH", "REJECTED"}
        self.assertLessEqual({r["decision"] for r in self.log.values()}, known)

    def test_every_row_has_a_rule_id_and_two_decimal_money(self):
        for r in self.log.values():
            self.assertTrue(r["rule_ids"].startswith("BR-"), r["txn_id"])
            for col in ("base_fee", "discount_amount", "penalty", "amount", "balance_after"):
                self.assertRegex(r[col], r"^-?\d+\.\d{2}$", f"{r['txn_id']} {col}")

    # ---- edge cases
    def test_ec01_return_at_exactly_24_hours(self):
        first, second = self.row("TXN-00009"), self.row("TXN-00066")
        self.assertEqual((first["ts"], second["ts"]), ("2026-10-12 08:15:00", "2026-10-13 08:15:00"))
        self.assertEqual((second["discount_type"], second["amount"]), ("RETURN", "42.50"))

    def test_ec02_last_pass_journey_then_a_return_within_24_hours(self):
        self.assertEqual((self.row("TXN-00068")["decision"], self.row("TXN-00068")["amount"]), ("PASS", "0.00"))
        r = self.row("TXN-00096")
        self.assertEqual((r["decision"], r["discount_type"], r["amount"]), ("CHARGED", "RETURN", "37.50"))

    def test_ec03_balance_exactly_equal_to_the_fee_is_charged_not_declined(self):
        r = self.row("TXN-00123")                  # balance 140.00 == LCV fee 140.00
        self.assertEqual((r["decision"], r["amount"], r["balance_after"]), ("CHARGED", "140.00", "0.00"))

    def test_ec04_third_mismatch_on_day_30_has_no_penalty(self):
        r = self.row("TXN-00117")
        self.assertEqual((r["penalty"], r["amount"], r["charged_class"]), ("0.00", "340.00", "3_AXLE"))
        self.assertIn("BR-06", r["rule_ids"])
        self.assertTrue(marked_for_reverification(self.state, r["tag_id"]))

    def test_ec05_resident_tags(self):
        self.assertEqual(self.row("TXN-00024")["decision"], "RESIDENT")      # CAR at exactly 20.0 km
        self.assertEqual(self.row("TXN-00010")["decision"], "CHARGED")       # resident LCV = commercial
        self.assertEqual(self.row("TXN-00018")["decision"], "CHARGED")       # resident CAR detected LCV
        self.assertEqual(self.row("TXN-00018")["amount"], "255.00")          # 155 + Rs 100

    def test_ec06_bus_truck_at_2200(self):
        self.assertEqual(self.row("TXN-00204")["discount_type"], "NONE")    # 21:59:59
        r = self.row("TXN-00205")                                             # 22:00:00
        self.assertEqual((r["discount_type"], r["amount"]), ("NIGHT", "283.50"))

    def test_ec07_reversal_boundaries(self):
        self.assertEqual(self.events["TXN-00020"]["result"], "REFUNDED")     # exactly 48 h
        self.assertEqual(self.events["TXN-00027"]["result"], "REFUNDED")     # 47 h 59 m 59 s
        self.assertEqual(self.events["TXN-00058"]["result"], "DISPUTE")      # 50 h

    def test_ec08_waiver_on_a_blacklisted_tag(self):
        r = self.row("TXN-00146")
        self.assertEqual((r["decision"], r["payment_mode"], r["amount"]), ("BLACKLIST_CASH", "CASH", "570.00"))

    def test_queue_waiver_boundary(self):
        self.assertEqual(self.row("TXN-00171")["decision"], "CHARGED")       # exactly 10 s
        self.assertEqual(self.row("TXN-00188")["decision"], "WAIVED")        # 11 s

    def test_hotlisted_tag_is_rejected_with_no_fee(self):
        r = self.row("TXN-00063")
        self.assertEqual((r["decision"], r["amount"], r["payment_mode"]), ("REJECTED", "0.00", "NONE"))

    def test_low_balance_decline_pays_double_in_cash(self):
        r = self.row("TXN-00013")
        self.assertEqual((r["decision"], r["amount"], r["tag_status_after"]),
                         ("DECLINED_CASH", "190.00", "LOW_BALANCE"))

    # ---- money
    def test_settlement_cash_penalties_equal_the_cash_rows(self):
        cash = {}
        for r in self.log.values():
            if r["payment_mode"] == "CASH":
                cash[r["ts"][:10]] = cash.get(r["ts"][:10], D("0")) + D(r["amount"])
        for s in read_csv(os.path.join(self.tmp.name, "settlement.csv")):
            if s["party_id"] == "CONCESSIONAIRE":
                self.assertEqual(D(s["cash_penalties"]), cash.get(s["date"], D("0")), s["date"])

    def test_waived_pass_resident_and_rejected_rows_move_no_money(self):
        for r in self.log.values():
            if r["decision"] in ("WAIVED", "PASS", "RESIDENT", "REJECTED"):
                self.assertEqual((r["amount"], r["payment_mode"]), ("0.00", "NONE"), r["txn_id"])


if __name__ == "__main__":
    unittest.main()
