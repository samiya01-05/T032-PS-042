"""BR-02 / BR-10: return (50%) and night (10%) discounts."""
from datetime import time
from decimal import Decimal

from models import money

RETURN_FACTOR = Decimal("0.5")
NIGHT_FACTOR = Decimal("0.9")


def is_night(ts) -> bool:
    """22:00:00 <= t < 06:00:00 (so 22:00:00 is night, 06:00:00 is not)."""
    t = ts.time()
    return t >= time(22, 0, 0) or t < time(6, 0, 0)


def apply_discounts(base, is_return: bool, ts, commercial: bool):
    """Return (fee, discount_type, discount_amount).

    The night discount is applied AFTER the return discount. It is never given
    to passes or residents because those never reach this function.
    Rounded once, at the end.
    """
    fee = Decimal(base)
    kinds = []
    if is_return:
        fee = fee * RETURN_FACTOR
        kinds.append("RETURN")
    if commercial and is_night(ts):
        fee = fee * NIGHT_FACTOR
        kinds.append("NIGHT")
    fee = money(fee)
    return fee, ("+".join(kinds) or "NONE"), money(base - fee)
