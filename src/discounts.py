"""BR-02 / BR-10: return (50%) and night (10%) discounts."""
from __future__ import annotations

from decimal import Decimal

from src import rules_config as cfg
from src.models import DiscountType, round_paisa


def is_night(ts) -> bool:
    """22:00:00 <= t < 06:00:00 (so 22:00:00 is night, 06:00:00 is not)."""
    t = ts.time()
    return t >= cfg.NIGHT_START or t < cfg.NIGHT_END


def apply_discounts(base, is_return: bool, ts, commercial: bool):
    """Return (fee, discount_type, discount_amount).

    The night discount is applied AFTER the return discount. Passes and residents never reach
    this function, so they are never night-discounted. Rounded once, at the end.
    """
    base = Decimal(base)
    fee = base
    kinds = []
    if is_return:
        fee = fee * cfg.RETURN_FACTOR
        kinds.append("RETURN")
    if commercial and is_night(ts):
        fee = fee * cfg.NIGHT_FACTOR
        kinds.append("NIGHT")
    fee = round_paisa(fee)
    if not kinds:
        dtype = DiscountType.NONE
    elif len(kinds) == 2:
        dtype = DiscountType.RETURN_NIGHT
    else:
        dtype = kinds[0]
    return fee, dtype, round_paisa(base - fee)
