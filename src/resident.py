"""BR-04: local resident exemption (EC-05 and the exactly-20.0-km case)."""
from __future__ import annotations

from src import rules_config as cfg
from src.models import Tag


def is_commercial(tag: Tag, charged_class: str) -> bool:
    """Commercial = the tag is flagged commercial, or (default) the charged class is not CAR."""
    if tag.commercial:
        return True
    return cfg.COMMERCIAL_BY_CHARGED_CLASS and charged_class != "CAR"


def resident_eligible(tag: Tag, plaza_id: str, commercial: bool, resident_pass) -> bool:
    """All five must hold: resident flag, this plaza, <= 20 km, non-commercial, valid pass."""
    return bool(
        tag.resident_flag
        and tag.resident_plaza_id == plaza_id
        and tag.resident_distance_km is not None
        and tag.resident_distance_km <= cfg.RESIDENT_LIMIT_KM      # exactly 20.0 km qualifies
        and not commercial
        and resident_pass is not None
    )
