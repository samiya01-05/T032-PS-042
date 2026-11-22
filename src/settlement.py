"""
settlement.py  --  daily money split between issuer banks and the concessionaire.

Per transaction (amounts rounded half-up to the paisa, then added up):
    bank_fee   = 1%    of the tag amount     (goes to the issuer bank)
    switch_fee = 0.25% of the tag amount     (switch cost, paid by the concessionaire)
    cash penalties (DECLINED_CASH / BLACKLIST_CASH) = 100% concessionaire revenue

One row per bank (all banks, even with zero activity) + one CONCESSIONAIRE row.

Bank row    net_amount = gross - bank_fee - switch_fee - reversals
CONCESSIONAIRE row: totals of all bank rows, and
            net_amount = sum(bank net amounts) + cash_penalties

`reversals` = settlement value taken back on THIS date by accepted REVERSE commands
(refunded amount minus the fee lines that are reversed with it).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

from src.models import CONCESSIONAIRE_ID, SettlementRow, round_paisa
from src.state import EngineState

BANK_FEE_RATE = Decimal("0.01")
SWITCH_FEE_RATE = Decimal("0.0025")
ZERO = Decimal("0.00")

# Which decisions count in `successful_txns`.  Default: tag-paid, charged crossings.
# (Pass / resident / waived crossings take no money from the tag.)  Change here if the
# organisers say otherwise.
COUNTED_DECISIONS = {"CHARGED"}


def fee_split(amount: Decimal) -> Tuple[Decimal, Decimal]:
    """(bank_fee, switch_fee) for one tag amount."""
    return round_paisa(amount * BANK_FEE_RATE), round_paisa(amount * SWITCH_FEE_RATE)


def compute_settlement(state: EngineState, day: date) -> List[SettlementRow]:
    acc: Dict[str, dict] = {
        bank_id: dict(n=0, gross=ZERO, bank_fee=ZERO, switch=ZERO, rev=ZERO)
        for bank_id in sorted(state.banks)
    }
    cash_total = ZERO

    for r in state.results:
        if r.ts.date() != day:
            continue
        cash_total += r.cash_amount
        if r.decision in COUNTED_DECISIONS and r.bank_id in acc:
            a = acc[r.bank_id]
            bank_fee, switch = fee_split(r.tag_amount)
            a["n"] += 1
            a["gross"] += r.tag_amount
            a["bank_fee"] += bank_fee
            a["switch"] += switch

    for rec in state.reversal_log:
        if rec.day == day and rec.bank_id in acc:
            acc[rec.bank_id]["rev"] += rec.net_value

    rows: List[SettlementRow] = []
    tot = dict(n=0, gross=ZERO, bank_fee=ZERO, switch=ZERO, rev=ZERO, net=ZERO)
    for bank_id, a in acc.items():
        net = a["gross"] - a["bank_fee"] - a["switch"] - a["rev"]
        rows.append(SettlementRow(day, bank_id, a["n"], a["gross"], a["bank_fee"], a["switch"],
                                  a["rev"], ZERO, net))
        for key in ("n", "gross", "bank_fee", "switch", "rev"):
            tot[key] += a[key]
        tot["net"] += net

    rows.append(SettlementRow(day, CONCESSIONAIRE_ID, tot["n"], tot["gross"], tot["bank_fee"],
                              tot["switch"], tot["rev"], cash_total, tot["net"] + cash_total))
    return rows
