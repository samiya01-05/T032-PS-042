"""Shared data model (write together with Member B, then freeze).

All money is Decimal. money() is the ONLY place where rounding happens.
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

# Lowest to highest. A "higher" class is one that appears later in this list.
CLASS_ORDER = ["CAR", "LCV", "BUS_TRUCK", "3_AXLE", "4-6_AXLE", "OVERSIZE"]
ZERO = Decimal("0.00")

# Separator used when several rule ids are written into the rule_ids column.
RULE_SEP = ";"

# Decision values (confirm the exact spelling against your README enums).
HOTLIST_REJECTED = "REJECTED"
BLACKLIST_CASH = "BLACKLIST_CASH"
WAIVED = "WAIVED"
PASS = "PASS"
RESIDENT = "RESIDENT"
CHARGED = "CHARGED"
DECLINED_CASH = "DECLINED_CASH"


def rank(cls: str) -> int:
    """Position of a vehicle class in CLASS_ORDER (unknown class -> clear error)."""
    try:
        return CLASS_ORDER.index(cls)
    except ValueError:
        raise ValueError(f"Unknown vehicle class: {cls!r}") from None


def money(x) -> Decimal:
    """Round to 2 decimals, half-up. The only rounding function in the project."""
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Tag:
    tag_id: str
    vehicle_class: str
    bank: str
    balance: Decimal
    status: str                      # ACTIVE / LOW_BALANCE / BLACKLISTED / HOTLISTED
    resident: bool = False
    commercial: bool = False         # the tag's own commercial flag (if the CSV has one)
    distance_km: Optional[Decimal] = None   # residence distance to the plaza
    reverify: bool = False


@dataclass
class Txn:
    txn_id: str
    ts: datetime
    tag_id: str
    plaza_id: str
    detected_class: str
    queue_s: float = 0
    queue_flag: bool = False
    distance_km: Optional[Decimal] = None   # overrides Tag.distance_km when given


@dataclass
class Result:
    """One decision_log row (17 columns) plus what settlement needs."""
    txn_id: str
    ts: datetime
    tag_id: str
    plaza_id: str
    tag_class: str
    detected_class: str
    charged_class: str
    base_fee: Decimal = ZERO
    discount_type: str = "NONE"
    discount_amount: Decimal = ZERO
    penalty: Decimal = ZERO
    amount: Decimal = ZERO
    payment_mode: str = "NONE"       # NONE / TAG / CASH
    decision: str = ""
    balance_after: Decimal = ZERO
    tag_status_after: str = ""
    rules: List[str] = field(default_factory=list)

    @property
    def rule_ids(self) -> str:
        return RULE_SEP.join(self.rules)
