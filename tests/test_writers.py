import csv
import os
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal

from src.models import EventResult, SettlementRow, TagEvent, fmt_money
from src.writers import (DECISION_LOG_COLUMNS, SETTLEMENT_COLUMNS, TAG_EVENT_COLUMNS,
                         decision_row, event_row, format_decision_log_for_day, format_settlement,
                         format_table, settlement_row, write_decision_log, write_settlement,
                         write_tag_events)
from tests.helpers import make_result

D = Decimal


class FormatTests(unittest.TestCase):
    def test_money_always_two_decimals(self):
        self.assertEqual(fmt_money(D("85")), "85.00")
        self.assertEqual(fmt_money(D("0.2125")), "0.21")
        self.assertEqual(fmt_money(D("0.225")), "0.23")
        self.assertEqual(fmt_money(D("1234.5")), "1234.50")      # no commas
        self.assertEqual(fmt_money(D("0")), "0.00")

    def test_column_order_is_the_binding_one(self):
        self.assertEqual(DECISION_LOG_COLUMNS[:6], ["txn_id", "ts", "plaza_id", "tag_id",
                                                    "tag_class", "avc_class"])
        self.assertEqual(len(DECISION_LOG_COLUMNS), 17)
        self.assertEqual(SETTLEMENT_COLUMNS[-1], "net_amount")
        self.assertEqual(TAG_EVENT_COLUMNS, ["ts", "command", "reference", "result", "amount",
                                             "balance_after", "reason"])

    def test_decision_row_matches_columns(self):
        r = make_result()
        row = decision_row(r)
        self.assertEqual(len(row), len(DECISION_LOG_COLUMNS))
        self.assertEqual(row[0], "TXN-1")
        self.assertEqual(row[1], "2026-10-12 08:00:00")
        self.assertEqual(row[DECISION_LOG_COLUMNS.index("amount")], "85.00")
        self.assertEqual(row[DECISION_LOG_COLUMNS.index("balance_after")], "915.00")

    def test_missing_avc_class_is_blank(self):
        r = make_result()
        r.avc_class = None
        self.assertEqual(decision_row(r)[DECISION_LOG_COLUMNS.index("avc_class")], "")

    def test_event_row_blank_for_not_applicable(self):
        e = TagEvent(datetime(2026, 10, 12, 8, 0, 0), "REVERSE", "TXN-9", EventResult.REJECTED,
                     None, None, "UNKNOWN_TXN")
        self.assertEqual(event_row(e), ["2026-10-12 08:00:00", "REVERSE", "TXN-9", "REJECTED",
                                        "", "", "UNKNOWN_TXN"])

    def test_settlement_row(self):
        s = SettlementRow(date(2026, 10, 12), "BNK-01", 3, D("255"), D("2.55"), D("0.64"),
                          D("0"), D("0"), D("251.81"))
        self.assertEqual(settlement_row(s), ["2026-10-12", "BNK-01", "3", "255.00", "2.55",
                                             "0.64", "0.00", "0.00", "251.81"])


class FileTests(unittest.TestCase):
    def test_files_have_header_and_rows_and_unix_newlines(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = os.path.join(d, "out", "decision_log.csv")        # folder is created for us
            write_decision_log(p1, [make_result(), make_result(txn_id="TXN-2")])
            with open(p1, newline="", encoding="utf-8") as f:
                raw = f.read()
            self.assertNotIn("\r", raw)
            rows = list(csv.reader(raw.splitlines()))
            self.assertEqual(rows[0], DECISION_LOG_COLUMNS)
            self.assertEqual([r[0] for r in rows[1:]], ["TXN-1", "TXN-2"])

            p2 = os.path.join(d, "settlement.csv")
            write_settlement(p2, [SettlementRow(date(2026, 10, 12), "CONCESSIONAIRE", 0, D(0),
                                                D(0), D(0), D(0), D(0), D(0))])
            with open(p2, newline="", encoding="utf-8") as f:
                self.assertEqual(next(csv.reader(f)), SETTLEMENT_COLUMNS)

            p3 = os.path.join(d, "tag_events.csv")
            write_tag_events(p3, [])                                # empty list -> header only
            with open(p3, newline="", encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), ",".join(TAG_EVENT_COLUMNS))


class ConsoleTests(unittest.TestCase):
    def test_table_is_aligned(self):
        text = format_table(["a", "bbb"], [["1", "2"], ["333", "4"]])
        lines = text.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[1].startswith("---"))

    def test_log_for_day_filters_by_date(self):
        results = [make_result(txn_id="A", ts="2026-10-12 08:00:00"),
                   make_result(txn_id="B", ts="2026-10-13 08:00:00")]
        text = format_decision_log_for_day(results, date(2026, 10, 12))
        self.assertIn("(1 txns)", text)
        self.assertIn("A ", text)
        self.assertNotIn("B  ", text.split("\n", 1)[1].split("\n", 2)[2])

    def test_settlement_print_has_title(self):
        s = SettlementRow(date(2026, 10, 12), "BNK-01", 0, D(0), D(0), D(0), D(0), D(0), D(0))
        self.assertIn("DAILY SETTLEMENT 2026-10-12", format_settlement([s]))


if __name__ == "__main__":
    unittest.main()
