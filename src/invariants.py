"""
invariants.py  --  self-checks that catch bugs without needing expected outputs.

check_invariants(state) returns a list of problem strings (empty list = all good).
"""
from __future__ import annotations

from decimal import Decimal
from typing import List

from src.models import Decision, EventResult, PayMode, round_paisa
from src.state import EngineState

# decision -> payment_mode that must go with it
EXPECTED_MODE = {
    Decision.CHARGED: PayMode.TAG,
    Decision.DECLINED_CASH: PayMode.CASH,
    Decision.BLACKLIST_CASH: PayMode.CASH,
    Decision.REJECTED: PayMode.NONE,
}
ZERO_AMOUNT_DECISIONS = {Decision.REJECTED, Decision.WAIVED, Decision.PASS, Decision.RESIDENT}


def check_invariants(state: EngineState) -> List[str]:
    problems: List[str] = []

    # 1. no tag may end with a negative balance
    for tag in state.tags.values():
        if tag.balance < 0:
            problems.append(f"negative balance on tag {tag.tag_id}: {tag.balance}")

    # 2. the balance trail adds up:  opening + top-ups + refunds - tag deductions == balance
    expected = dict(state.opening_balances)
    for e in state.tag_events:
        if e.command == "TOPUP" and e.result == EventResult.SUCCESS and e.reference in expected:
            expected[e.reference] += e.amount
        if e.command == "REVERSE" and e.result == EventResult.REFUNDED:
            res = state.results_by_id.get(e.reference)
            if res is not None and res.tag_id in expected:
                expected[res.tag_id] += e.amount
    for r in state.results:
        if r.tag_id in expected:
            expected[r.tag_id] -= r.tag_amount
    for tag_id, want in expected.items():
        have = state.tags[tag_id].balance
        if round_paisa(want) != round_paisa(have):
            problems.append(f"balance trail mismatch on {tag_id}: expected {want}, found {have}")

    # 3. each decision row is internally sensible
    for r in state.results:
        mode = EXPECTED_MODE.get(r.decision)
        if mode is not None and r.payment_mode != mode:
            problems.append(f"{r.txn_id}: decision {r.decision} should have payment_mode {mode}, "
                            f"got {r.payment_mode}")
        if r.decision in ZERO_AMOUNT_DECISIONS and r.amount != 0:
            problems.append(f"{r.txn_id}: decision {r.decision} must have amount 0, got {r.amount}")
        if r.amount < 0:
            problems.append(f"{r.txn_id}: negative amount {r.amount}")

    # 4. settlement blocks reconcile: concessionaire net = bank nets + cash penalties
    rows = state.settlement_rows
    for i in range(0, len(rows)):
        if rows[i].party_id == "CONCESSIONAIRE":
            bank_net = sum((s.net_amount for s in rows[:i] if s.day == rows[i].day
                            and s.party_id != "CONCESSIONAIRE"), Decimal("0"))
            if round_paisa(bank_net + rows[i].cash_penalties) != round_paisa(rows[i].net_amount):
                problems.append(f"settlement {rows[i].day}: concessionaire net does not add up")

    return problems
