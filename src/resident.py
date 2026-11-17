"""BR-04: local resident exemption (EC-05 and the exactly-20.0-km case)."""
from decimal import Decimal

LIMIT_KM = Decimal("20")


def is_commercial(tag, charged_class: str) -> bool:
    """Commercial = the tag is flagged commercial OR the class is not CAR."""
    return bool(tag.commercial) or charged_class != "CAR"


def resident_eligible(tag, commercial: bool, distance_km, resident_pass) -> bool:
    return bool(
        tag.resident
        and not commercial
        and resident_pass is not None           # a valid pass for THIS plaza and date
        and distance_km is not None
        and Decimal(str(distance_km)) <= LIMIT_KM   # exactly 20.0 km qualifies
    )
