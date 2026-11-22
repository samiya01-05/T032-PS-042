"""
rules_config.py  --  every PS-042 rule choice the brief leaves open, in ONE place.

Flip a value here and re-run; no other file needs editing.  Each choice is also
explained in docs/DESIGN.md (section 5).
"""
from datetime import time, timedelta
from decimal import Decimal

# ---- BR-05 / BR-06: AVC mismatch
MISMATCH_PENALTY = Decimal("100.00")
MISMATCH_WINDOW = timedelta(days=30)       # 3rd higher-class mismatch inside this window
MISMATCH_WINDOW_INCLUSIVE = True           # day 30 exactly still counts (EC-04)
MISMATCH_LIMIT = 3

# ---- BR-02: return journey
RETURN_WINDOW = timedelta(hours=24)
RETURN_WINDOW_INCLUSIVE = True             # exactly 24:00:00 is still a return (EC-01)
RETURN_FACTOR = Decimal("0.5")

# ---- BR-10: night discount
NIGHT_FACTOR = Decimal("0.9")
NIGHT_START = time(22, 0, 0)               # inclusive (EC-06)
NIGHT_END = time(6, 0, 0)                  # exclusive

# ---- BR-04: resident exemption
RESIDENT_LIMIT_KM = Decimal("20")          # <= 20 km qualifies (exactly 20.0 is eligible)

# ---- BR-15: queue waiver
QUEUE_SECONDS = Decimal("10")              # strictly MORE than this (10 s is not waived)

# ---- choices the brief does not settle
# commercial = tag flag OR the charged class is not CAR (a CAR detected as LCV is commercial).
COMMERCIAL_BY_CHARGED_CLASS = True
# A commuter pass covers the crossing even when the AVC detected a HIGHER class.
PASS_COVERS_HIGHER_CLASS = True
# Declined (low balance) cash = 2 x discounted fee. True: 2 x (fee + mismatch penalty).
DECLINE_INCLUDES_PENALTY = False
