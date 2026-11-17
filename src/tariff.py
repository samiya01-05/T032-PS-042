"""BR-01: fee lookup by plaza and vehicle class, plus class comparison."""
from decimal import Decimal

from models import rank


def is_higher(detected: str, registered: str) -> bool:
    return rank(detected) > rank(registered)


def is_lower(detected: str, registered: str) -> bool:
    return rank(detected) < rank(registered)


class Tariff:
    def __init__(self, rows):
        """rows: iterable of (plaza_id, vehicle_class, single_fee)."""
        self.fees = {(p, c): Decimal(str(f)) for p, c, f in rows}

    def fee(self, plaza_id: str, cls: str) -> Decimal:
        try:
            return self.fees[(plaza_id, cls)]
        except KeyError:
            raise KeyError(f"No tariff for plaza={plaza_id!r}, class={cls!r}") from None
