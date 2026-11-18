"""
models.py  --  SHARED by Member A and Member B (agree on this on day 1, then freeze).

Holds the plain data containers (dataclasses), the allowed text values
(Decision, PayMode, ...), and tiny money/time helpers.

Rule of thumb: ALL money is a decimal.Decimal, never a float.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"

# Cheapest -> most expensive class. A uses this to say "detected class is higher".
CLASS_ORDER = ["CAR", "LCV", "BUS_TRUCK", "3_AXLE", "4-6_AXLE", "OVERSIZE"]

CONCESSIONAIRE_ID = "CONCESSIONAIRE"


class Status:
    ACTIVE = "ACTIVE"
    LOW_BALANCE = "LOW_BALANCE"
    BLACKLISTED = "BLACKLISTED"
    HOTLISTED = "HOTLISTED"


class Decision:
    CHARGED = "CHARGED"
    PASS = "PASS"
    RESIDENT = "RESIDENT"
    WAIVED = "WAIVED"
    DECLINED_CASH = "DECLINED_CASH"
    BLACKLIST_CASH = "BLACKLIST_CASH"
    REJECTED = "REJECTED"


class PayMode:
    TAG = "TAG"
    CASH = "CASH"
    NONE = "NONE"


class DiscountType:
    RETURN = "RETURN"
    NIGHT = "NIGHT"
    RETURN_NIGHT = "RETURN+NIGHT"
    NONE = "NONE"


class EventResult:
    """Values for the `result` column of tag_events.csv."""
    SUCCESS = "SUCCESS"      # top-up accepted
    REFUNDED = "REFUNDED"    # reversal accepted (within 48 h)
    DISPUTE = "DISPUTE"      # reversal after 48 h -> logged, not refunded
    REJECTED = "REJECTED"    # anything refused


# ---------------------------------------------------------------- money / time helpers
def money(value) -> Decimal:
    """Turn '85.00' / 85 / Decimal into a Decimal (no float surprises)."""
    return Decimal(str(value).strip())


def round_paisa(value) -> Decimal:
    """Round half-up to 2 decimals (the one and only rounding rule)."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt_money(value) -> str:
    """Decimal -> '85.00' (always 2 places, no commas, no symbol)."""
    return format(round_paisa(value), "f")


def parse_ts(text: str) -> datetime:
    return datetime.strptime(text.strip(), TS_FORMAT)


def parse_date(text: str) -> date:
    return datetime.strptime(text.strip(), DATE_FORMAT).date()


def fmt_ts(value: datetime) -> str:
    return value.strftime(TS_FORMAT)


# ---------------------------------------------------------------- reference data
@dataclass
class Bank:
    bank_id: str
    bank_name: str


@dataclass
class Plaza:
    plaza_id: str
    plaza_name: str
    highway: str
    nearest_plaza_km: Decimal


@dataclass
class Tariff:
    plaza_id: str
    vehicle_class: str
    single_journey_fee: Decimal
    monthly_pass_fee: Decimal


@dataclass
class Tag:
    """Mutable: balance and status change while commands are processed."""
    tag_id: str
    vehicle_no: str
    vehicle_class: str
    commercial: bool
    issuer_bank: str
    balance: Decimal
    status: str
    resident_flag: bool
    resident_plaza_id: Optional[str]
    resident_distance_km: Optional[Decimal]


@dataclass
class Pass:
    pass_id: str
    tag_id: str
    plaza_id: str
    pass_type: str                    # COMMUTER_50 or RESIDENT_MONTHLY
    purchase_date: date
    valid_to: date
    journeys_total: Optional[int]     # COMMUTER_50 only
    journeys_used: Optional[int]      # starts at journeys_used_opening
    amount_paid: Decimal


@dataclass
class AvcEvent:
    tag_id: str
    ts: datetime
    plaza_id: str
    detected_class: str


# ---------------------------------------------------------------- commands (parser output)
@dataclass
class TxnCommand:
    line_no: int
    txn_id: str
    ts: datetime
    plaza_id: str
    lane: Optional[str]
    tag_id: str
    avc_class: Optional[str]
    queue_s: Optional[Decimal]
    queue_flag: bool


@dataclass
class TopupCommand:
    line_no: int
    tag_id: str
    ts: datetime
    amount: Decimal


@dataclass
class ReverseCommand:
    line_no: int
    txn_id: str
    ts: datetime


@dataclass
class PrintLogCommand:
    line_no: int
    day: date


@dataclass
class PrintSettlementCommand:
    line_no: int
    day: date


# ---------------------------------------------------------------- results
@dataclass
class TxnResult:
    """One decision_log row. Member A builds it; Member B stores/settles it."""
    txn_id: str
    ts: datetime
    plaza_id: str
    tag_id: str
    tag_class: str
    avc_class: Optional[str]
    charged_class: Optional[str]
    base_fee: Decimal
    discount_type: str
    discount_amount: Decimal
    penalty: Decimal
    amount: Decimal
    payment_mode: str
    decision: str
    balance_after: Decimal
    tag_status_after: str
    rule_ids: str
    bank_id: str = ""
    reversed: bool = False

    @property
    def tag_amount(self) -> Decimal:
        """Money actually taken from the tag (what the bank settles)."""
        if self.payment_mode == PayMode.TAG and self.decision == Decision.CHARGED:
            return self.amount
        return Decimal("0.00")

    @property
    def cash_amount(self) -> Decimal:
        """Money collected in cash at the lane (100% concessionaire revenue)."""
        if self.payment_mode == PayMode.CASH:
            return self.amount
        return Decimal("0.00")


@dataclass
class TagEvent:
    """One tag_events.csv row (a TOPUP or REVERSE outcome)."""
    ts: datetime
    command: str                       # TOPUP or REVERSE
    reference: str                     # tag_id for TOPUP, txn_id for REVERSE
    result: str
    amount: Optional[Decimal]
    balance_after: Optional[Decimal]
    reason: str


@dataclass
class ReversalRecord:
    """Remembers an accepted reversal so settlement can take it back out."""
    day: date                          # date the REVERSE command ran
    txn_id: str
    bank_id: str
    amount: Decimal                    # refunded to the tag
    net_value: Decimal                 # amount - bank_fee - switch_fee of that txn


@dataclass
class SettlementRow:
    day: date
    party_id: str
    successful_txns: int
    gross_tag_amount: Decimal
    bank_fee: Decimal
    switch_fee: Decimal
    reversals: Decimal
    cash_penalties: Decimal
    net_amount: Decimal
