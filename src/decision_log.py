"""Turns a Result into one decision_log.csv row (17 columns).

If your README orders or names the columns differently, change COLUMNS only.
"""
from models import Result

TS_FORMAT = "%Y-%m-%d %H:%M:%S"

COLUMNS = [
    "txn_id", "timestamp", "tag_id", "plaza_id", "tag_class", "detected_class",
    "charged_class", "base_fee", "discount_type", "discount_amount", "penalty",
    "amount", "payment_mode", "decision", "balance_after", "tag_status_after",
    "rule_ids",
]


def _fmt(v):
    if hasattr(v, "quantize"):              # Decimal -> always 2 decimals
        return f"{v:.2f}"
    return str(v)


def to_row(r: Result) -> list:
    values = {
        "txn_id": r.txn_id,
        "timestamp": r.ts.strftime(TS_FORMAT),
        "tag_id": r.tag_id,
        "plaza_id": r.plaza_id,
        "tag_class": r.tag_class,
        "detected_class": r.detected_class,
        "charged_class": r.charged_class,
        "base_fee": r.base_fee,
        "discount_type": r.discount_type,
        "discount_amount": r.discount_amount,
        "penalty": r.penalty,
        "amount": r.amount,
        "payment_mode": r.payment_mode,
        "decision": r.decision,
        "balance_after": r.balance_after,
        "tag_status_after": r.tag_status_after,
        "rule_ids": r.rule_ids,
    }
    return [_fmt(values[c]) for c in COLUMNS]
