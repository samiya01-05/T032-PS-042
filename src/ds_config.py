"""All dataset-specific numbers and every uncertain rule choice live here.

Change a value here and re-run: nothing else needs editing.
"""
from decimal import Decimal as D

# Single-trip rates for this plaza (README: 65 / 105 / 220 / 345)
RATES = {"CAR": D("65"), "LCV": D("105"), "BUS_TRUCK": D("220"), "MAV": D("345")}
CLASS_ORDER = ["CAR", "LCV", "BUS_TRUCK", "MAV"]          # lowest -> highest

# Passes
MONTHLY_LOCAL_PRICE = D("330")        # local-resident CAR only; valid purchase -> month end
TRIP_PASS_TRIPS = 50                  # TRIP_50: 50 free crossings
TRIP_PASS_PRICE_MULT = 30             # price = 30 x single rate of the registered class

# Recharge / balance
MIN_RECHARGE = D("100")
LOW_BALANCE_CAR = D("200")            # LOW_BALANCE while balance <= this (CAR)
LOW_BALANCE_OTHER = D("500")          # ... or this (other classes)

# AVC mismatch
MISMATCH_PENALTY = D("100")
MISMATCH_WINDOW_DAYS = 30             # 3rd higher mismatch inside this window: no penalty

# Duplicate reads (same tag, same lane)
DUP_WINDOW_S = 120
DUP_INCLUSIVE = True                  # True: a read exactly 120 s later is still a duplicate

# --- Rule choices the README/brief do not settle (flip to change) ---------------
NIGHT_DISCOUNT = True                 # PS-042 brief: commercial classes, 22:00-06:00, 10%
PASS_SALES_AS_CASH = True             # pass price counts as cash collected / cash_paid
EXEMPT_MISMATCH_PENALTY = False       # EC5: exempt tag, higher class -> no penalty, no REVERIFY
