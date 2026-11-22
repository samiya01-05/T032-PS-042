"""BR-01: charged class and fee lookup (Member A).

The fee table itself is loaded by Member B (state.tariffs); this module decides WHICH
class is charged and reads the fee through state.fee_for().
"""
from __future__ import annotations

from decimal import Decimal

from src.models import rank
from src.state import EngineState


def is_higher(detected: str, registered: str) -> bool:
    return rank(detected) > rank(registered)


def is_lower(detected: str, registered: str) -> bool:
    return rank(detected) < rank(registered)


def base_fee(state: EngineState, plaza_id: str, charged_class: str) -> Decimal:
    """Single-journey fee of `charged_class` at `plaza_id` (BR-01)."""
    return state.fee_for(plaza_id, charged_class)
