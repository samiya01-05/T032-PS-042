"""Small builders so each test file stays short and readable."""
from datetime import datetime
from decimal import Decimal

from src.models import (
    Bank, Plaza, Tag, Tariff, TxnResult, CLASS_ORDER, parse_ts,
)
from src.state import EngineState

FEES = {"CAR": "85.00", "LCV": "140.00", "BUS_TRUCK": "285.00",
        "3_AXLE": "310.00", "4-6_AXLE": "445.00", "OVERSIZE": "545.00"}


def make_tag(tag_id="TAG1", cls="CAR", bank="BNK-01", balance="1000.00", status="ACTIVE",
             commercial=False):
    return Tag(tag_id=tag_id, vehicle_no="KA01AB1234", vehicle_class=cls, commercial=commercial,
               issuer_bank=bank, balance=Decimal(balance), status=status, resident_flag=False,
               resident_plaza_id=None, resident_distance_km=None)


def make_state(*tags):
    banks = {f"BNK-0{i}": Bank(f"BNK-0{i}", f"Bank {i}") for i in range(1, 5)}
    plazas = {"PLZ-01": Plaza("PLZ-01", "Base", "NH-75", Decimal("38.0"))}
    tariffs = {("PLZ-01", c): Tariff("PLZ-01", c, Decimal(FEES[c]), Decimal("0.00"))
               for c in CLASS_ORDER}
    return EngineState(banks, plazas, tariffs, {t.tag_id: t for t in tags}, [], [])


def make_result(txn_id="TXN-1", ts="2026-10-12 08:00:00", tag_id="TAG1", amount="85.00",
                decision="CHARGED", mode="TAG", bank="BNK-01", balance_after="915.00",
                status="ACTIVE"):
    amount = Decimal(amount)
    return TxnResult(
        txn_id=txn_id, ts=parse_ts(ts), plaza_id="PLZ-01", tag_id=tag_id, tag_class="CAR",
        avc_class="CAR", charged_class="CAR", base_fee=amount, discount_type="NONE",
        discount_amount=Decimal("0.00"), penalty=Decimal("0.00"), amount=amount,
        payment_mode=mode, decision=decision, balance_after=Decimal(balance_after),
        tag_status_after=status, rule_ids="BR-01", bank_id=bank)


def charge_tag(state, tag_id, amount, txn_id, ts):
    """Deduct from the tag AND record a CHARGED result (keeps balances consistent)."""
    tag = state.get_tag(tag_id)
    tag.balance -= Decimal(amount)
    res = make_result(txn_id=txn_id, ts=ts, tag_id=tag_id, amount=amount, bank=tag.issuer_bank,
                      balance_after=str(tag.balance))
    state.record_result(res)
    return res
