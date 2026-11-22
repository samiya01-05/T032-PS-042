"""BR-05 / BR-06: AVC class mismatch, Rs 100 penalty, 3-in-30-days re-verification."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from src import rules_config as cfg
from src.models import rank

ZERO = Decimal("0.00")


class AvcTracker:
    def __init__(self, seed=None):
        """seed: iterable of (tag_id, datetime) of earlier HIGHER-class mismatches
        (from avc_history.csv)."""
        self.hist = defaultdict(list)
        for tag_id, ts in sorted(seed or [], key=lambda item: item[1]):
            self.hist[tag_id].append(ts)

    def _in_window(self, gap: timedelta) -> bool:
        if gap < timedelta(0):
            return False
        return gap <= cfg.MISMATCH_WINDOW if cfg.MISMATCH_WINDOW_INCLUSIVE else gap < cfg.MISMATCH_WINDOW

    def evaluate(self, tag_id, ts, tag_cls, detected_cls):
        """Return (charged_class, penalty, mismatch, reverify).

        * same or LOWER detected class: charge the tag class, no penalty, not counted.
        * HIGHER detected class: charge the detected class; it counts as a mismatch.
            - the 3rd one inside the window: NO penalty, tag marked for re-verification
            - otherwise: Rs 100 penalty
        """
        if rank(detected_cls) <= rank(tag_cls):
            return tag_cls, ZERO, False, False

        recent = [t for t in self.hist[tag_id] if self._in_window(ts - t)]
        self.hist[tag_id].append(ts)
        if len(recent) + 1 >= cfg.MISMATCH_LIMIT:
            return detected_cls, ZERO, True, True
        return detected_cls, cfg.MISMATCH_PENALTY, True, False
