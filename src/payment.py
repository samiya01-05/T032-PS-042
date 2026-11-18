"""The orchestrator. Precedence (BR-order from the brief):

 1 hotlist -> 2 (AVC class bookkeeping) -> 3 blacklist -> 4 queue waiver ->
 5 commuter pass -> 6 resident -> 7 return discount -> 8 night discount ->
 9 penalty + balance check.
"""
from dataclasses import dataclass

from discounts import apply_discounts
from models import (BLACKLIST_CASH, CHARGED, DECLINED_CASH, HOTLIST_REJECTED, PASS,
                    RESIDENT, WAIVED, ZERO, Result, money)
from resident import is_commercial, resident_eligible

QUEUE_SECONDS = 10        # strictly more than this ...


@dataclass
class Context:
    """One Context for the whole run. Never rebuild it per line: it holds the state."""
    tags: dict            # tag_id -> Tag
    tariff: object        # Tariff
    passes: object        # PassBook
    avc: object           # AvcTracker
    returns: object       # ReturnTracker


# --- balance helpers: Member B's status.py can replace these two ---------------
def deduct(tag, amount):
    tag.balance -= amount


def mark_low_balance(tag):
    tag.status = "LOW_BALANCE"
# -------------------------------------------------------------------------------


def process_txn(txn, ctx) -> Result:
    tag = ctx.tags[txn.tag_id]
    key = (tag.tag_id, txn.plaza_id)
    r = Result(txn.txn_id, txn.ts, tag.tag_id, txn.plaza_id,
               tag.vehicle_class, txn.detected_class, tag.vehicle_class)

    def done(decision, mode="NONE", amount=ZERO):
        r.decision, r.payment_mode, r.amount = decision, mode, amount
        r.balance_after = tag.balance
        r.tag_status_after = tag.status
        return r

    # 1. HOTLISTED: barrier stays down, no fee, nothing else is evaluated
    if tag.status == "HOTLISTED":
        r.rules.append("BR-09")
        return done(HOTLIST_REJECTED)

    # 2. Charged class and AVC mismatch bookkeeping (not a decision by itself)
    charged, penalty, mismatch, reverify = ctx.avc.evaluate(
        tag.tag_id, txn.ts, tag.vehicle_class, txn.detected_class)
    r.charged_class = charged
    base = ctx.tariff.fee(txn.plaza_id, charged)
    r.base_fee = base
    r.rules.append("BR-01")
    if mismatch:
        r.rules.append("BR-05")
    if reverify:
        tag.reverify = True
        r.rules.append("BR-06")

    # 3. BLACKLISTED: 2x base fee in cash. Beats the waiver (EC-08).
    if tag.status == "BLACKLISTED":
        cash = money(base * 2)
        r.penalty = cash - base
        r.rules.append("BR-08")
        return done(BLACKLIST_CASH, "CASH", cash)

    # 4. Queue waiver: strictly more than 10 s AND the >100 m flag
    if txn.queue_flag and txn.queue_s > QUEUE_SECONDS:
        r.rules.append("BR-15")
        return done(WAIVED)

    # 5. Commuter pass (consumed BEFORE the return rule is considered)
    p = ctx.passes.commuter(tag.tag_id, txn.plaza_id, txn.ts)
    if p is not None:
        p.journeys_used += 1
        ctx.returns.start(key, txn.ts)        # a pass crossing can be the "first" (EC-02)
        r.rules.append("BR-03")
        return done(PASS)

    # 6. Resident exemption (commercial classes are never eligible)
    commercial = is_commercial(tag, charged)
    rp = ctx.passes.resident(tag.tag_id, txn.plaza_id, txn.ts)
    dist = txn.distance_km if txn.distance_km is not None else tag.distance_km
    if resident_eligible(tag, commercial, dist, rp):
        r.rules.append("BR-04")
        return done(RESIDENT)

    # 7 + 8. Return discount, then night discount
    is_return = ctx.returns.active(key, txn.ts)
    fee, dtype, disc = apply_discounts(base, is_return, txn.ts, commercial)
    r.discount_type, r.discount_amount = dtype, disc
    if is_return:
        r.rules.append("BR-02")
    if "NIGHT" in dtype:
        r.rules.append("BR-10")

    # 9. Penalty, then balance check (balance == amount succeeds: EC-03)
    total = fee + penalty
    r.penalty = penalty
    if tag.balance >= total:
        deduct(tag, total)
        if is_return:
            ctx.returns.consume(key)
        else:
            ctx.returns.start(key, txn.ts)
        return done(CHARGED, "TAG", total)

    # Declined: vehicle pays double the (discounted) fee in cash, tag -> LOW_BALANCE
    cash = money(fee * 2)
    r.penalty = cash - fee
    mark_low_balance(tag)
    r.rules.append("BR-07")
    return done(DECLINED_CASH, "CASH", cash)
