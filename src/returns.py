"""BR-02: return-journey window per (tag, plaza). 50% off, once per 24 hours."""
from __future__ import annotations

from datetime import timedelta

from src import rules_config as cfg


class ReturnTracker:
    def __init__(self):
        self.anchor = {}        # (tag_id, plaza_id) -> time of the "first" crossing

    def active(self, key, ts) -> bool:
        """True if a return discount is available now (exactly 24 h still counts: EC-01)."""
        a = self.anchor.get(key)
        if a is None:
            return False
        gap = ts - a
        if gap < timedelta(0):
            return False
        return gap <= cfg.RETURN_WINDOW if cfg.RETURN_WINDOW_INCLUSIVE else gap < cfg.RETURN_WINDOW

    def consume(self, key):
        """The return was used: the next crossing is full fare and starts a new window."""
        self.anchor.pop(key, None)

    def start(self, key, ts):
        """Record a first crossing. Never extends a window that is still open."""
        if not self.active(key, ts):
            self.anchor[key] = ts
