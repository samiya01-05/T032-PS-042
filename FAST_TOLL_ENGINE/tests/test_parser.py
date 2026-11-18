import os
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal

from src.models import (PrintLogCommand, PrintSettlementCommand, ReverseCommand, TopupCommand,
                        TxnCommand)
from src.parser import ParseError, parse_commands, parse_line

TXN = "TXN|TXN-00009|2026-10-12 08:15:00|PLZ-01|L03|34161FA8001FDAE972D40D87|CAR|6|false"


class ParseLineTests(unittest.TestCase):
    def test_comments_and_blank_lines_are_ignored(self):
        self.assertIsNone(parse_line("# a comment", 1))
        self.assertIsNone(parse_line("", 2))
        self.assertIsNone(parse_line("   ", 3))

    def test_txn_all_fields(self):
        c = parse_line(TXN, 11)
        self.assertIsInstance(c, TxnCommand)
        self.assertEqual(c.line_no, 11)
        self.assertEqual(c.txn_id, "TXN-00009")
        self.assertEqual(c.ts, datetime(2026, 10, 12, 8, 15, 0))
        self.assertEqual((c.plaza_id, c.lane, c.avc_class), ("PLZ-01", "L03", "CAR"))
        self.assertEqual(c.queue_s, Decimal("6"))
        self.assertFalse(c.queue_flag)

    def test_queue_flag_true(self):
        c = parse_line(TXN.replace("|false", "|true"), 1)
        self.assertTrue(c.queue_flag)

    def test_empty_arguments_mean_not_supplied(self):
        c = parse_line("TXN|T1|2026-10-12 08:15:00|PLZ-01||TAG1|||", 1)
        self.assertIsNone(c.lane)
        self.assertIsNone(c.avc_class)
        self.assertIsNone(c.queue_s)
        self.assertFalse(c.queue_flag)

    def test_missing_trailing_arguments_are_padded(self):
        c = parse_line("TXN|T1|2026-10-12 08:15:00|PLZ-01|L1|TAG1", 1)
        self.assertIsNone(c.avc_class)
        self.assertFalse(c.queue_flag)

    def test_topup(self):
        c = parse_line("TOPUP|34161FA80008AD364FECE981|2026-10-13 09:00:00|150.00", 74)
        self.assertIsInstance(c, TopupCommand)
        self.assertEqual(c.amount, Decimal("150.00"))
        self.assertEqual(c.ts, datetime(2026, 10, 13, 9, 0, 0))

    def test_reverse(self):
        c = parse_line("REVERSE|TXN-00020|2026-10-14 12:00:00", 139)
        self.assertIsInstance(c, ReverseCommand)
        self.assertEqual(c.txn_id, "TXN-00020")

    def test_prints(self):
        self.assertIsInstance(parse_line("PRINT_LOG|2026-10-12", 1), PrintLogCommand)
        c = parse_line("PRINT_SETTLEMENT|2026-10-12", 1)
        self.assertIsInstance(c, PrintSettlementCommand)
        self.assertEqual(c.day, date(2026, 10, 12))

    def test_windows_line_ending_is_fine(self):
        self.assertEqual(parse_line("PRINT_LOG|2026-10-12\r\n", 1).day, date(2026, 10, 12))

    def test_unknown_command(self):
        with self.assertRaises(ParseError) as ctx:
            parse_line("REFUND|X|2026-10-12 08:00:00", 7)
        self.assertIn("line 7", str(ctx.exception))

    def test_too_many_arguments(self):
        with self.assertRaises(ParseError):
            parse_line("REVERSE|TXN-1|2026-10-12 08:00:00|extra", 1)

    def test_required_argument_missing(self):
        with self.assertRaises(ParseError):
            parse_line("TOPUP||2026-10-12 08:00:00|100.00", 1)

    def test_bad_timestamp_amount_flag_date(self):
        with self.assertRaises(ParseError):
            parse_line("REVERSE|TXN-1|12/10/2026", 1)
        with self.assertRaises(ParseError):
            parse_line("TOPUP|T1|2026-10-12 08:00:00|abc", 1)
        with self.assertRaises(ParseError):
            parse_line(TXN.replace("|false", "|maybe"), 1)
        with self.assertRaises(ParseError):
            parse_line("PRINT_LOG|not-a-date", 1)


class ParseFileTests(unittest.TestCase):
    def test_order_and_physical_line_numbers_are_kept(self):
        text = "# header\n\nREVERSE|TXN-1|2026-10-12 09:00:00\n# mid\nPRINT_LOG|2026-10-12\n"
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "commands.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            cmds = parse_commands(path)
        self.assertEqual([type(c) for c in cmds], [ReverseCommand, PrintLogCommand])
        self.assertEqual([c.line_no for c in cmds], [3, 5])


if __name__ == "__main__":
    unittest.main()
