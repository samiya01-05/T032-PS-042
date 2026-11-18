"""BR-02: return-journey window per (tag, plaza). 50% off, once per 24 hours."""
from datetime import timedelta

DAY = timedelta(hours=24)


class ReturnTracker:
    def __init__(self):
        self.anchor = {}        # (tag_id, plaza_id) -> time of the "first" crossing

    def active(self, key, ts) -> bool:
        """True if a return discount is available now. Exactly 24h still counts (EC-01)."""
        a = self.anchor.get(key)
        return a is not None and timedelta(0) <= ts - a <= DAY

    def consume(self, key):
        """The return was used: the next crossing is full fare and starts a new window."""
        self.anchor.pop(key, None)

    def start(self, key, ts):
        """Record a first crossing. Never extends a window that is still open."""
        if not self.active(key, ts):
            self.anchor[key] = ts
