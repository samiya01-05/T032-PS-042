"""
stub_engine.py  --  TEMPORARY stand-in for Member A's src/payment.py.

It exists only so Member B can run and test the whole pipeline before A is finished.
It applies just:  hotlist -> blacklist -> plain tariff fee (tag class) -> balance gate.
It does NOT do AVC mismatches, passes, resident, waiver, return or night rules.

Real contract (what A's payment.py must provide):

    def process_txn(state: EngineState, cmd: TxnCommand) -> TxnResult
"""
from __future__ import annotations

from decimal import Decimal

from src.models import DiscountType, Status, TxnCommand, TxnResult
from src.state import DataError, EngineState
from src.status import blacklist_charge, charge_tag_or_decline, hotlist_reject

ZERO = Decimal("0.00")


def process_txn(state: EngineState, cmd: TxnCommand) -> TxnResult:
    tag = state.get_tag(cmd.tag_id)
    if tag is None:
        raise DataError(f"line {cmd.line_no}: unknown tag {cmd.tag_id}")

    fee = state.fee_for(cmd.plaza_id, tag.vehicle_class)

    if tag.status == Status.HOTLISTED:
        out = hotlist_reject(tag)
        base = ZERO
        rules = "BR-09"
    elif tag.status == Status.BLACKLISTED:
        out = blacklist_charge(tag, fee)
        base = fee
        rules = "BR-08"
    else:
        out = charge_tag_or_decline(tag, fee)
        base = fee
        rules = "BR-01" if out.decision == "CHARGED" else "BR-01;BR-07"

    return TxnResult(
        txn_id=cmd.txn_id, ts=cmd.ts, plaza_id=cmd.plaza_id, tag_id=tag.tag_id,
        tag_class=tag.vehicle_class, avc_class=cmd.avc_class, charged_class=tag.vehicle_class,
        base_fee=base, discount_type=DiscountType.NONE, discount_amount=ZERO, penalty=out.penalty,
        amount=out.amount, payment_mode=out.payment_mode, decision=out.decision,
        balance_after=out.balance_after, tag_status_after=out.status_after, rule_ids=rules,
        bank_id=tag.issuer_bank,
    )
