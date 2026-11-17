from datetime import datetime
from decimal import Decimal as D

from models import Tag, Txn
from passes import PassBook
from payment import Context
from returns import ReturnTracker
from tariff import Tariff
from violation import AvcTracker

T0 = datetime(2026, 10, 12, 8, 0, 0)

FEES = [("P1", "CAR", 85), ("P1", "LCV", 140), ("P1", "BUS_TRUCK", 285),
        ("P1", "3_AXLE", 310), ("P1", "4-6_AXLE", 445), ("P1", "OVERSIZE", 545),
        ("P2", "CAR", 95)]


def make_ctx(cls="CAR", status="ACTIVE", bal="1000", resident=False,
             commercial=False, dist=None, passes=(), seed=None):
    tag = Tag("T1", cls, "B1", D(bal), status, resident=resident,
              commercial=commercial, distance_km=None if dist is None else D(str(dist)))
    return Context({"T1": tag}, Tariff(FEES), PassBook(list(passes)),
                   AvcTracker(seed), ReturnTracker())


def txn(ts, detected="CAR", q=0, flag=False, n=1, plaza="P1"):
    return Txn(f"X{n}", ts, "T1", plaza, detected, q, flag)
