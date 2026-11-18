"""BR-05 / BR-06: AVC class mismatch, Rs 100 penalty, 3-in-30-days re-verification."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from models import rank

PENALTY = Decimal("100.00")
WINDOW = timedelta(days=30)
LIMIT = 3                       # the 3rd mismatch in the window triggers re-verification


class AvcTracker:
    def __init__(self, seed=None):
        """seed: iterable of (tag_id, datetime) from avc_history.csv (higher-class mismatches)."""
        self.hist = defaultdict(list)
        for tag_id, ts in sorted(seed or [], key=lambda x: x[1]):
            self.hist[tag_id].append(ts)

    def evaluate(self, tag_id, ts, tag_cls, detected_cls):
        """Return (charged_class, penalty, mismatch, reverify).

        - same or lower detected class: charge the tag class, no penalty, not counted
        - higher detected class: charge detected class; counts as a mismatch
            * 3rd mismatch within 30 days (day 30 inclusive, current one counted):
              no penalty, reverify = True
            * otherwise Rs 100 penalty
        """
        if rank(detected_cls) <= rank(tag_cls):
            return tag_cls, Decimal("0.00"), False, False

        recent = [t for t in self.hist[tag_id] if timedelta(0) <= ts - t <= WINDOW]
        self.hist[tag_id].append(ts)
        if len(recent) + 1 >= LIMIT:
            return detected_cls, Decimal("0.00"), True, True
        return detected_cls, PENALTY, True, False
