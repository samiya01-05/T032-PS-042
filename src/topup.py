"""
topup.py  --  handles the  TOPUP|tag_id|ts|amount  command.

Rules (BR-16): minimum Rs 100; a top-up that lifts a LOW_BALANCE tag ABOVE its
threshold (Rs 200 CAR / Rs 500 others) makes it ACTIVE immediately.
"""
from __future__ import annotations

from decimal import Decimal

from src.models import EventResult, TagEvent, TopupCommand, round_paisa
from src.state import EngineState
from src.status import status_after_topup
from src.models import Status

MIN_TOPUP = Decimal("100.00")


def process_topup(state: EngineState, cmd: TopupCommand) -> TagEvent:
    amount = round_paisa(cmd.amount)
    tag = state.get_tag(cmd.tag_id)

    if tag is None:
        event = TagEvent(cmd.ts, "TOPUP", cmd.tag_id, EventResult.REJECTED, amount, None,
                         "UNKNOWN_TAG")
    elif amount < MIN_TOPUP:
        event = TagEvent(cmd.ts, "TOPUP", cmd.tag_id, EventResult.REJECTED, amount, tag.balance,
                         "BELOW_MINIMUM_100")
    else:
        old_status = tag.status
        tag.balance += amount
        tag.status = status_after_topup(tag)
        if old_status == Status.LOW_BALANCE and tag.status == Status.ACTIVE:
            reason = "STATUS_RESTORED_ACTIVE"
        elif tag.status == Status.LOW_BALANCE:
            reason = "STILL_LOW_BALANCE"
        else:
            reason = "OK"
        event = TagEvent(cmd.ts, "TOPUP", cmd.tag_id, EventResult.SUCCESS, amount, tag.balance,
                         reason)

    state.record_event(event)
    return event
