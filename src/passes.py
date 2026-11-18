"""BR-03 (commuter pass) and the pass records used by BR-04 (resident pass)."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


def end_of_day(d: date) -> datetime:
    """Use when a CSV gives only a valid_to DATE: the pass lasts until 23:59:59 that day."""
    return datetime.combine(d, time(23, 59, 59))


@dataclass
class Pass:
    tag_id: str
    plaza_id: str
    kind: str                     # COMMUTER_50 / RESIDENT_MONTHLY
    valid_from: datetime
    valid_to: datetime
    journeys_total: int = 50
    journeys_used: int = 0

    @classmethod
    def from_purchase(cls, tag_id, plaza_id, purchase_ts, kind="COMMUTER_50", total=50):
        """A pass is valid for 30 days from purchase."""
        return cls(tag_id, plaza_id, kind, purchase_ts, purchase_ts + timedelta(days=30), total)

    def valid_at(self, plaza_id, ts) -> bool:
        return self.plaza_id == plaza_id and self.valid_from <= ts <= self.valid_to

    @property
    def journeys_left(self) -> int:
        return self.journeys_total - self.journeys_used


class PassBook:
    def __init__(self, passes):
        self.by_tag = defaultdict(list)
        for p in passes:
            self.by_tag[p.tag_id].append(p)

    def commuter(self, tag_id, plaza_id, ts):
        """A usable commuter pass: right plaza, inside its dates, journeys left."""
        for p in self.by_tag.get(tag_id, []):
            if (p.kind == "COMMUTER_50" and p.valid_at(plaza_id, ts)
                    and p.journeys_used < p.journeys_total):
                return p
        return None

    def resident(self, tag_id, plaza_id, ts):
        """A valid resident pass (unlimited crossings, so no journey counter)."""
        for p in self.by_tag.get(tag_id, []):
            if p.kind == "RESIDENT_MONTHLY" and p.valid_at(plaza_id, ts):
                return p
        return None
