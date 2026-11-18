"""
status.py  --  the balance / status "gates" that Member A's payment.py calls.

Member A decides WHAT the fee is (class, discounts, penalty ...).
These functions decide WHAT HAPPENS TO THE TAG AND THE MONEY:

    hotlist_reject(tag)            -> barrier stays down, no fee
    blacklist_charge(tag, fee)     -> vehicle pays 2x fee in cash
    charge_tag_or_decline(tag,fee) -> deduct from tag, or decline + 2x cash + LOW_BALANCE

Each returns a GateOutcome that A copies into the decision_log row.
`fee` always means "the amount that would be deducted from the tag".
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.models import Decision, PayMode, Status, Tag, round_paisa

CAR_RESTORE_THRESHOLD = Decimal("200.00")     # balance must go ABOVE this (CAR tags)
OTHER_RESTORE_THRESHOLD = Decimal("500.00")   # ... or ABOVE this (all other classes)
ZERO = Decimal("0.00")


@dataclass
class GateOutcome:
    decision: str
    payment_mode: str
    amount: Decimal          # money collected (tag or cash)
    penalty: Decimal         # extra paid over the plain fee (cash cases); 0 for CHARGED
    balance_after: Decimal
    status_after: str


def restore_threshold(tag: Tag) -> Decimal:
    """Rs 200 for CAR tags, Rs 500 for every other class."""
    return CAR_RESTORE_THRESHOLD if tag.vehicle_class == "CAR" else OTHER_RESTORE_THRESHOLD


def double_fee(fee: Decimal) -> Decimal:
    return round_paisa(fee * 2)


def hotlist_reject(tag: Tag) -> GateOutcome:
    """HOTLISTED (stolen) tag: logged, barrier stays down, nothing charged."""
    return GateOutcome(Decision.REJECTED, PayMode.NONE, ZERO, ZERO, tag.balance, tag.status)


def blacklist_charge(tag: Tag, fee: Decimal) -> GateOutcome:
    """BLACKLISTED tag: the vehicle pays 2x fee in cash; the tag balance is untouched."""
    fee = round_paisa(fee)
    cash = double_fee(fee)
    return GateOutcome(Decision.BLACKLIST_CASH, PayMode.CASH, cash, cash - fee,
                       tag.balance, tag.status)


def charge_tag_or_decline(tag: Tag, fee: Decimal) -> GateOutcome:
    """
    balance >= fee  -> CHARGED: take `fee` from the tag (balance exactly equal is fine).
    balance <  fee  -> DECLINED_CASH: vehicle pays 2x fee in cash, tag becomes LOW_BALANCE.
    """
    fee = round_paisa(fee)
    if tag.balance >= fee:
        tag.balance -= fee
        return GateOutcome(Decision.CHARGED, PayMode.TAG, fee, ZERO, tag.balance, tag.status)

    cash = double_fee(fee)
    if tag.status not in (Status.BLACKLISTED, Status.HOTLISTED):
        tag.status = Status.LOW_BALANCE
    return GateOutcome(Decision.DECLINED_CASH, PayMode.CASH, cash, cash - fee,
                       tag.balance, tag.status)


def status_after_topup(tag: Tag) -> str:
    """
    A LOW_BALANCE tag returns to ACTIVE only when its balance is strictly ABOVE the
    threshold.  Blacklisted / hotlisted tags never change here.
    """
    if tag.status == Status.LOW_BALANCE and tag.balance > restore_threshold(tag):
        return Status.ACTIVE
    return tag.status
