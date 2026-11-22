"""
reversal.py  --  handles  REVERSE|txn_id|ts  (a wrong deduction being undone).

Rules (BR-14):
  * within 48 hours (inclusive: exactly 48:00:00 still counts) -> REFUNDED:
    money goes back to the tag and the settlement lines are reversed
  * after 48 hours -> DISPUTE: only logged, NO refund
  * only a real deduction from the tag can be reversed (cash / free / rejected cannot)
"""
from __future__ import annotations

from datetime import timedelta

from src.models import EventResult, ReverseCommand, ReversalRecord, TagEvent, round_paisa
from src.settlement import fee_split
from src.state import EngineState

REVERSAL_WINDOW = timedelta(hours=48)
WINDOW_IS_INCLUSIVE = True      # exactly 48 h counts as "within 48 hours"


def process_reverse(state: EngineState, cmd: ReverseCommand) -> TagEvent:
    result = state.results_by_id.get(cmd.txn_id)

    if result is None:
        return _log(state, TagEvent(cmd.ts, "REVERSE", cmd.txn_id, EventResult.REJECTED,
                                    None, None, "UNKNOWN_TXN"))

    tag = state.get_tag(result.tag_id)
    amount = round_paisa(result.tag_amount)

    if result.reversed:
        return _log(state, TagEvent(cmd.ts, "REVERSE", cmd.txn_id, EventResult.REJECTED,
                                    amount, tag.balance if tag else None, "ALREADY_REVERSED"))
    if amount <= 0:
        return _log(state, TagEvent(cmd.ts, "REVERSE", cmd.txn_id, EventResult.REJECTED,
                                    amount, tag.balance if tag else None, "NO_TAG_DEDUCTION"))

    elapsed = cmd.ts - result.ts
    if elapsed < timedelta(0):
        return _log(state, TagEvent(cmd.ts, "REVERSE", cmd.txn_id, EventResult.REJECTED,
                                    amount, tag.balance, "REVERSE_BEFORE_TXN"))

    within = elapsed <= REVERSAL_WINDOW if WINDOW_IS_INCLUSIVE else elapsed < REVERSAL_WINDOW
    if not within:
        return _log(state, TagEvent(cmd.ts, "REVERSE", cmd.txn_id, EventResult.DISPUTE,
                                    amount, tag.balance, "AFTER_48H_DISPUTE_LOGGED"))

    # ---- accepted: refund the tag and remember it for settlement
    tag.balance += amount
    result.reversed = True
    bank_fee, switch = fee_split(amount)
    state.reversal_log.append(ReversalRecord(
        day=cmd.ts.date(), txn_id=cmd.txn_id, bank_id=result.bank_id,
        amount=amount, net_value=amount - bank_fee - switch))
    return _log(state, TagEvent(cmd.ts, "REVERSE", cmd.txn_id, EventResult.REFUNDED,
                                amount, tag.balance, "WITHIN_48H"))


def _log(state: EngineState, event: TagEvent) -> TagEvent:
    state.record_event(event)
    return event
