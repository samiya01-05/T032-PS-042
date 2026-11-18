"""Runs the whole pipeline on the real sample pack using the temporary stub engine."""
import csv
import os
import tempfile
import unittest

from src.main import run
from src.parser import parse_commands
from src.models import TxnCommand
from src.stub_engine import process_txn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "sample_data")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@unittest.skipUnless(os.path.isdir(SAMPLE), "sample_data folder not present")
class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        cls.printed = []
        cls.state = run(SAMPLE, cls.out, process_txn, printer=cls.printed.append)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_row_counts(self):
        self.assertEqual(len(read_csv(os.path.join(self.out, "decision_log.csv"))), 250)
        self.assertEqual(len(read_csv(os.path.join(self.out, "tag_events.csv"))), 15)   # 10 + 5
        self.assertEqual(len(read_csv(os.path.join(self.out, "settlement.csv"))), 25)   # 5 x 5

    def test_decision_log_is_in_command_order(self):
        want = [c.txn_id for c in parse_commands(os.path.join(SAMPLE, "commands.txt"))
                if isinstance(c, TxnCommand)]
        got = [r["txn_id"] for r in read_csv(os.path.join(self.out, "decision_log.csv"))]
        self.assertEqual(got, want)

    def test_invariants_hold(self):
        self.assertIn("Invariant checks passed.", self.printed)

    def test_five_logs_and_five_settlements_were_printed(self):
        self.assertEqual(sum(1 for p in self.printed if p.startswith("=== TRANSACTION")), 5)
        self.assertEqual(sum(1 for p in self.printed if p.startswith("=== DAILY SETTLEMENT")), 5)

    def test_reversal_outcomes_from_the_sample_pack(self):
        ev = {e["reference"]: e for e in read_csv(os.path.join(self.out, "tag_events.csv"))
              if e["command"] == "REVERSE"}
        self.assertEqual(ev["TXN-00038"]["result"], "REFUNDED")
        self.assertEqual(ev["TXN-00020"]["result"], "REFUNDED")     # EC-07: exactly 48 h
        self.assertEqual(ev["TXN-00027"]["result"], "REFUNDED")     # 47 h 59 m 59 s
        self.assertEqual(ev["TXN-00108"]["result"], "REFUNDED")
        self.assertEqual(ev["TXN-00058"]["result"], "DISPUTE")      # 50 h

    def test_topup_outcomes_from_the_sample_pack(self):
        top = [e for e in read_csv(os.path.join(self.out, "tag_events.csv"))
               if e["command"] == "TOPUP"]
        self.assertEqual(len(top), 10)
        rejected = [e for e in top if e["result"] == "REJECTED"]
        self.assertEqual([e["amount"] for e in rejected], ["50.00"])  # the Rs 50 top-up
        chain = [e for e in top if e["reference"] == "34161FA80008AD364FECE981"]
        self.assertEqual([e["reason"] for e in chain],
                         ["STILL_LOW_BALANCE", "STATUS_RESTORED_ACTIVE"])

    def test_settlement_blocks_end_with_the_concessionaire(self):
        rows = read_csv(os.path.join(self.out, "settlement.csv"))
        for i in range(4, 25, 5):
            self.assertEqual(rows[i]["party_id"], "CONCESSIONAIRE")
        self.assertEqual(rows[0]["date"], "2026-10-12")
        self.assertEqual(rows[-1]["date"], "2026-10-16")

    def test_running_twice_gives_identical_files(self):
        with tempfile.TemporaryDirectory() as second:
            run(SAMPLE, second, process_txn, printer=lambda s: None)
            for name in ("decision_log.csv", "settlement.csv", "tag_events.csv"):
                with open(os.path.join(self.out, name), "rb") as a, \
                        open(os.path.join(second, name), "rb") as b:
                    self.assertEqual(a.read(), b.read(), name)

    def test_injected_handler_is_called_once_per_txn(self):
        calls = []

        def spy(state, cmd):
            calls.append(cmd.txn_id)
            return process_txn(state, cmd)

        with tempfile.TemporaryDirectory() as third:
            run(SAMPLE, third, spy, printer=lambda s: None)
        self.assertEqual(len(calls), 250)


if __name__ == "__main__":
    unittest.main()
