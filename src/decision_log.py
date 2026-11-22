"""Builds one decision_log row (a TxnResult) and its rule_ids string (Member A).

The CSV text itself is produced by Member B's src/writers.py (decision_row).
"""
from __future__ import annotations

from decimal import Decimal
from typing import List

from src.models import RULE_SEP, TxnCommand, TxnResult, Tag
from src.status import GateOutcome

ZERO = Decimal("0.00")


def rule_ids(rules: List[str]) -> str:
    """Rule ids in the order they were applied, without repeats: 'BR-01;BR-05'."""
    seen = []
    for r in rules:
        if r not in seen:
            seen.append(r)
    return RULE_SEP.join(seen)


def build_result(cmd: TxnCommand, tag: Tag, charged_class: str, base_fee: Decimal,
                 out: GateOutcome, rules: List[str], discount_type: str = "NONE",
                 discount_amount: Decimal = ZERO, penalty: Decimal = None) -> TxnResult:
    """Fill every decision_log field. `penalty` overrides the gate's penalty (used when a
    mismatch penalty was added to a CHARGED row)."""
    return TxnResult(
        txn_id=cmd.txn_id, ts=cmd.ts, plaza_id=cmd.plaza_id, tag_id=tag.tag_id,
        tag_class=tag.vehicle_class, avc_class=cmd.avc_class, charged_class=charged_class,
        base_fee=base_fee, discount_type=discount_type, discount_amount=discount_amount,
        penalty=out.penalty if penalty is None else penalty, amount=out.amount,
        payment_mode=out.payment_mode, decision=out.decision, balance_after=out.balance_after,
        tag_status_after=out.status_after, rule_ids=rule_ids(rules), bank_id=tag.issuer_bank)
