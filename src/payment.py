"""
payment.py  --  Member A's orchestrator.   Contract with main.py:

    process_txn(state: EngineState, cmd: TxnCommand) -> TxnResult

Precedence (the brief): hotlist, blacklist, waiver, pass, resident, return journey, night.

    1  HOTLISTED         -> REJECTED, no fee                                  (BR-09)
    2  AVC class         -> charged class, mismatch bookkeeping (not a decision)  (BR-01/05/06)
    3  BLACKLISTED       -> 2 x base fee in cash (beats the waiver: EC-08)    (BR-08)
    4  queue waiver      -> WAIVED, free                                      (BR-15)
    5  commuter pass     -> PASS, free, one journey used                      (BR-03)
    6  resident          -> RESIDENT, free                                    (BR-04)
    7  return journey    -> fee x 0.5                                         (BR-02)
    8  night discount    -> x 0.9, commercial only                            (BR-10)
    9  penalty + balance -> CHARGED, or DECLINED_CASH (2 x fee) + LOW_BALANCE (BR-07)

Money moves through Member B's gates in status.py; A never edits a balance directly.
"""
from __future__ import annotations

from decimal import Decimal

from src import rules_config as cfg
from src.decision_log import build_result
from src.discounts import apply_discounts
from src.models import CLASS_ORDER, Decision, PayMode, Status, TxnCommand, TxnResult
from src.passes import consume_journey, find_commuter, find_resident
from src.resident import is_commercial, resident_eligible
from src.state import DataError, EngineState
from src.status import (GateOutcome, blacklist_charge, charge_tag_or_decline, decline_cash,
                        hotlist_reject)
from src.tariff import base_fee as lookup_fee
from src.tariff import is_higher
from src.returns import ReturnTracker
from src.violation import AvcTracker

ZERO = Decimal("0.00")
MEMORY_KEY = "decision_engine"


class _Memory:
    """State that must survive between transactions (one per run)."""

    def __init__(self, state: EngineState) -> None:
        seed = []
        for ev in state.avc_history:                      # earlier higher-class mismatches
            tag = state.get_tag(ev.tag_id)
            if tag is not None and is_higher(ev.detected_class, tag.vehicle_class):
                seed.append((ev.tag_id, ev.ts))
        self.avc = AvcTracker(seed)
        self.returns = ReturnTracker()
        self.reverify = set()          # tag ids marked for re-verification (BR-06)


def memory_for(state: EngineState) -> _Memory:
    mem = state.engine_memory.get(MEMORY_KEY)
    if mem is None:
        mem = _Memory(state)
        state.engine_memory[MEMORY_KEY] = mem
    return mem


def marked_for_reverification(state: EngineState, tag_id: str) -> bool:
    """True once a tag has had its 3rd higher-class mismatch inside 30 days (BR-06)."""
    return tag_id in memory_for(state).reverify


def _free(tag, decision: str) -> GateOutcome:
    """Outcome for WAIVED / PASS / RESIDENT: nothing is taken from anybody."""
    return GateOutcome(decision, PayMode.NONE, ZERO, ZERO, tag.balance, tag.status)


def process_txn(state: EngineState, cmd: TxnCommand) -> TxnResult:
    tag = state.get_tag(cmd.tag_id)
    if tag is None:
        raise DataError(f"line {cmd.line_no}: unknown tag {cmd.tag_id}")
    detected = cmd.avc_class or tag.vehicle_class          # no AVC reading -> assume tag class
    if detected not in CLASS_ORDER:
        raise DataError(f"line {cmd.line_no}: unknown AVC class {detected!r}")

    mem = memory_for(state)
    key = (tag.tag_id, cmd.plaza_id)
    rules = []

    # 1. HOTLISTED: barrier stays down, nothing else is looked at
    if tag.status == Status.HOTLISTED:
        rules.append("BR-09")
        return build_result(cmd, tag, tag.vehicle_class, ZERO, hotlist_reject(tag), rules)

    # 2. charged class + mismatch bookkeeping
    charged, penalty, mismatch, reverify = mem.avc.evaluate(
        tag.tag_id, cmd.ts, tag.vehicle_class, detected)
    base = lookup_fee(state, cmd.plaza_id, charged)
    rules.append("BR-01")
    if mismatch:
        rules.append("BR-05")
    if reverify:
        mem.reverify.add(tag.tag_id)
        rules.append("BR-06")

    # 3. BLACKLISTED: 2 x base fee in cash (the waiver does not rescue it: EC-08)
    if tag.status == Status.BLACKLISTED:
        rules.append("BR-08")
        return build_result(cmd, tag, charged, base, blacklist_charge(tag, base), rules)

    # 4. queue waiver: strictly more than 10 s AND the >100 m flag
    if cmd.queue_flag and cmd.queue_s is not None and cmd.queue_s > cfg.QUEUE_SECONDS:
        rules.append("BR-15")
        return build_result(cmd, tag, charged, base, _free(tag, Decision.WAIVED), rules)

    # 5. commuter pass: consumed BEFORE the return rule; a pass crossing can be the "first"
    if not mismatch or cfg.PASS_COVERS_HIGHER_CLASS:
        p = find_commuter(state, tag.tag_id, cmd.plaza_id, cmd.ts)
        if p is not None:
            consume_journey(p)
            mem.returns.start(key, cmd.ts)                 # EC-02
            rules.append("BR-03")
            return build_result(cmd, tag, charged, base, _free(tag, Decision.PASS), rules)

    # 6. local resident exemption (commercial classes never qualify: EC-05)
    commercial = is_commercial(tag, charged)
    rp = find_resident(state, tag.tag_id, cmd.plaza_id, cmd.ts)
    if resident_eligible(tag, cmd.plaza_id, commercial, rp):
        rules.append("BR-04")
        return build_result(cmd, tag, charged, base, _free(tag, Decision.RESIDENT), rules)

    # 7 + 8. return discount, then night discount
    is_return = mem.returns.active(key, cmd.ts)
    fee, dtype, disc = apply_discounts(base, is_return, cmd.ts, commercial)
    if is_return:
        rules.append("BR-02")
    if "NIGHT" in dtype:
        rules.append("BR-10")

    # 9. add the mismatch penalty, then the balance check (balance == amount succeeds: EC-03)
    total = fee + penalty
    if tag.balance >= total:
        out = charge_tag_or_decline(tag, total)
        if is_return:
            mem.returns.consume(key)
        else:
            mem.returns.start(key, cmd.ts)
        return build_result(cmd, tag, charged, base, out, rules, dtype, disc, penalty=penalty)

    rules.append("BR-07")
    out = decline_cash(tag, total if cfg.DECLINE_INCLUDES_PENALTY else fee)
    return build_result(cmd, tag, charged, base, out, rules, dtype, disc)
