"""
writers.py  --  writes the three evaluation CSVs and the console print-outs.

Formats (from the README): header row, money with exactly 2 decimals (no commas,
no symbol), timestamps 'YYYY-MM-DD HH:MM:SS', dates 'YYYY-MM-DD'.
Files use '\n' line endings, UTF-8.
"""
from __future__ import annotations

import csv
import os
from typing import Iterable, List, Optional

from src.models import (
    DATE_FORMAT, SettlementRow, TagEvent, TxnResult, fmt_money, fmt_ts,
)

DECISION_LOG_COLUMNS = [
    "txn_id", "ts", "plaza_id", "tag_id", "tag_class", "avc_class", "charged_class",
    "base_fee", "discount_type", "discount_amount", "penalty", "amount", "payment_mode",
    "decision", "balance_after", "tag_status_after", "rule_ids",
]
SETTLEMENT_COLUMNS = [
    "date", "party_id", "successful_txns", "gross_tag_amount", "bank_fee", "switch_fee",
    "reversals", "cash_penalties", "net_amount",
]
TAG_EVENT_COLUMNS = ["ts", "command", "reference", "result", "amount", "balance_after", "reason"]


def _money_or_blank(value) -> str:
    return "" if value is None else fmt_money(value)


def decision_row(r: TxnResult) -> List[str]:
    return [
        r.txn_id, fmt_ts(r.ts), r.plaza_id, r.tag_id, r.tag_class, r.avc_class or "",
        r.charged_class or "", fmt_money(r.base_fee), r.discount_type,
        fmt_money(r.discount_amount), fmt_money(r.penalty), fmt_money(r.amount),
        r.payment_mode, r.decision, fmt_money(r.balance_after), r.tag_status_after, r.rule_ids,
    ]


def settlement_row(s: SettlementRow) -> List[str]:
    return [
        s.day.strftime(DATE_FORMAT), s.party_id, str(s.successful_txns),
        fmt_money(s.gross_tag_amount), fmt_money(s.bank_fee), fmt_money(s.switch_fee),
        fmt_money(s.reversals), fmt_money(s.cash_penalties), fmt_money(s.net_amount),
    ]


def event_row(e: TagEvent) -> List[str]:
    return [
        fmt_ts(e.ts), e.command, e.reference, e.result,
        _money_or_blank(e.amount), _money_or_blank(e.balance_after), e.reason,
    ]


def _write_csv(path: str, header: List[str], rows: Iterable[List[str]]) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_decision_log(path: str, results: Iterable[TxnResult]) -> None:
    _write_csv(path, DECISION_LOG_COLUMNS, (decision_row(r) for r in results))


def write_settlement(path: str, rows: Iterable[SettlementRow]) -> None:
    _write_csv(path, SETTLEMENT_COLUMNS, (settlement_row(s) for s in rows))


def write_tag_events(path: str, events: Iterable[TagEvent]) -> None:
    _write_csv(path, TAG_EVENT_COLUMNS, (event_row(e) for e in events))


# ---------------------------------------------------------------- console output
def format_table(header: List[str], rows: List[List[str]]) -> str:
    """Simple aligned text table for PRINT_LOG / PRINT_SETTLEMENT."""
    widths = [len(h) for h in header]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = lambda cells: "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)).rstrip()
    return "\n".join([line(header), line(["-" * w for w in widths])] + [line(r) for r in rows])


def format_decision_log_for_day(results: List[TxnResult], day) -> str:
    rows = [decision_row(r) for r in results if r.ts.date() == day]
    title = f"=== TRANSACTION DECISION LOG {day.strftime(DATE_FORMAT)} ({len(rows)} txns) ==="
    return title + "\n" + format_table(DECISION_LOG_COLUMNS, rows)


def format_settlement(rows: List[SettlementRow]) -> str:
    day = rows[0].day.strftime(DATE_FORMAT) if rows else "?"
    return (f"=== DAILY SETTLEMENT {day} ===\n"
            + format_table(SETTLEMENT_COLUMNS, [settlement_row(s) for s in rows]))
