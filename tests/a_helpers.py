"""Builders for Member A's decision-engine tests (PS-042 rules on B's state objects)."""
from datetime import date, datetime
from decimal import Decimal as D

from src.models import (AvcEvent, Bank, CLASS_ORDER, Pass, Plaza, Tag, Tariff, TxnCommand)
from src.state import EngineState

T0 = datetime(2026, 10, 12, 8, 0, 0)
FEES = {"PLZ-01": {"CAR": "85", "LCV": "140", "BUS_TRUCK": "285", "3_AXLE": "310",
                   "4-6_AXLE": "445", "OVERSIZE": "545"},
        "PLZ-02": {"CAR": "95", "LCV": "150", "BUS_TRUCK": "300", "3_AXLE": "320",
                   "4-6_AXLE": "460", "OVERSIZE": "560"}}


def tag(cls="CAR", status="ACTIVE", bal="1000", commercial=None, resident=False,
        plaza=None, dist=None, tag_id="T1"):
    if commercial is None:
        commercial = cls != "CAR"
    return Tag(tag_id=tag_id, vehicle_no="KA01AB1234", vehicle_class=cls, commercial=commercial,
               issuer_bank="BNK-01", balance=D(bal), status=status, resident_flag=resident,
               resident_plaza_id=plaza, resident_distance_km=None if dist is None else D(str(dist)))


def commuter(left=50, plaza="PLZ-01", start=date(2026, 10, 1), end=date(2026, 10, 30), tag_id="T1"):
    return Pass("MPS-1", tag_id, plaza, "COMMUTER_50", start, end, 50, 50 - left, D("0"))


def resident_pass(plaza="PLZ-01", start=date(2026, 10, 1), end=date(2026, 10, 31), tag_id="T1"):
    return Pass("MPS-R", tag_id, plaza, "RESIDENT_MONTHLY", start, end, None, None, D("340"))


def state(*tags, passes=(), avc=()):
    banks = {"BNK-01": Bank("BNK-01", "Bank 1")}
    plazas = {p: Plaza(p, p, "NH", D("38")) for p in FEES}
    tariffs = {(p, c): Tariff(p, c, D(FEES[p][c]), D("0")) for p in FEES for c in CLASS_ORDER}
    return EngineState(banks, plazas, tariffs, {t.tag_id: t for t in tags}, list(passes), list(avc))


def txn(ts, avc=None, q=0, flag=False, n=1, plaza="PLZ-01", tag_id="T1"):
    return TxnCommand(line_no=n, txn_id=f"X{n}", ts=ts, plaza_id=plaza, lane="L1", tag_id=tag_id,
                      avc_class=avc, queue_s=D(str(q)), queue_flag=flag)


def history(tag_id, ts, detected, plaza="PLZ-01"):
    return AvcEvent(tag_id, ts, plaza, detected)
