"""Event engine for the teachers' dataset (reads / recharges / passes).

Events from the three files are merged by timestamp. Ties: PASS, RECHARGE, READ.

Read precedence:
  duplicate -> exempt -> blacklisted (cash) -> pass -> return/night discount + penalty
"""
import calendar
import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import ds_config as cfg
from discounts import apply_discounts
from models import money
from returns import ReturnTracker

ZERO = Decimal("0.00")
TS = "%Y-%m-%d %H:%M:%S"
PRIORITY = {"PASS": 0, "RECHARGE": 1, "READ": 2}


def rank(cls):
    return cfg.CLASS_ORDER.index(cls)


def low_threshold(cls):
    return cfg.LOW_BALANCE_CAR if cls == "CAR" else cfg.LOW_BALANCE_OTHER


def month_end(ts):
    last = calendar.monthrange(ts.year, ts.month)[1]
    return datetime(ts.year, ts.month, last, 23, 59, 59)


@dataclass
class PassState:
    kind: str
    valid_from: datetime
    valid_to: datetime
    trips_used: int = 0

    def usable(self, ts):
        if not (self.valid_from <= ts <= self.valid_to):
            return False
        return self.kind == "MONTHLY_LOCAL" or self.trips_used < cfg.TRIP_PASS_TRIPS


@dataclass
class TagState:
    tag_id: str
    cls: str
    opening: Decimal
    local: bool
    exempt: bool
    balance: Decimal = ZERO
    status: str = "ACTIVE"            # ACTIVE / LOW_BALANCE / BLACKLISTED
    reverify: bool = False
    pass_: Optional[PassState] = None
    mism: list = field(default_factory=list)
    last_read: dict = field(default_factory=dict)
    history: list = field(default_factory=list)   # snapshots for statements


def load_tags(path):
    tags = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bal = Decimal(r["opening_balance"])
            tags[r["tag_id"]] = TagState(
                r["tag_id"], r["registered_class"], bal,
                r["local_resident"].strip().lower() == "true",
                r["exempt"].strip().lower() == "true", balance=bal)
    return tags


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Engine:
    def __init__(self, tags):
        self.tags = tags
        self.returns = ReturnTracker()
        self.read_log, self.recharge_log, self.pass_log = [], [], []
        self.stats = defaultdict(lambda: defaultdict(Decimal))   # (tag, 'YYYY-MM') -> sums
        self.pass_sales = []                                      # (date, price)

    # ------------------------------------------------------------------ run
    def process_events(self, reads, recharges, passes):
        events = []
        n = 0
        for kind, rows in (("READ", reads), ("RECHARGE", recharges), ("PASS", passes)):
            for r in rows:
                ts = datetime.strptime(r["timestamp"], TS)
                events.append((ts, PRIORITY[kind], n, kind, r))
                n += 1
        events.sort(key=lambda e: (e[0], e[1], e[2]))
        for ts, _, _, kind, r in events:
            {"READ": self._read, "RECHARGE": self._recharge, "PASS": self._pass}[kind](ts, r)
        # README: read_log is in reads.csv order, which equals timestamp order
        return self

    # ------------------------------------------------------------- helpers
    def _snap(self, st, ts):
        p = st.pass_
        st.history.append((ts, st.balance, st.status, st.reverify,
                           None if p is None else (p.kind, p.valid_to,
                                                   cfg.TRIP_PASS_TRIPS - p.trips_used)))

    def _stat(self, st, ts):
        return self.stats[(st.tag_id, ts.strftime("%Y-%m"))]

    def _flags(self, st, mismatch):
        out = []
        if st.status == "LOW_BALANCE":
            out.append("LOW_BALANCE")
        if st.status == "BLACKLISTED":
            out.append("BLACKLISTED")
        if mismatch:
            out.append("MISMATCH")
        return ";".join(out)

    def _mismatch_penalty(self, st, ts):
        """Record a higher-class mismatch. 3rd inside the window: no penalty."""
        window = timedelta(days=cfg.MISMATCH_WINDOW_DAYS)
        recent = [t for t in st.mism if timedelta(0) <= ts - t <= window]
        st.mism.append(ts)
        st.reverify = True
        return ZERO if len(recent) + 1 >= 3 else cfg.MISMATCH_PENALTY

    def _log_read(self, ts, st, lane, det, outcome, fare, penalty, mismatch, tag_fare=ZERO, cash=ZERO):
        self.read_log.append({
            "timestamp": ts.strftime(TS), "tag_id": st.tag_id, "lane": lane,
            "registered_class": st.cls, "detected_class": det, "outcome": outcome,
            "fare": fare, "penalty": penalty, "balance_after": st.balance,
            "flags": "" if outcome == "DUPLICATE_IGNORED" else self._flags(st, mismatch),
            "_date": ts.date(), "_tag": tag_fare, "_cash": cash,
        })

    # --------------------------------------------------------------- reads
    def _read(self, ts, row):
        tid, lane, det = row["tag_id"], row["lane"], row["detected_class"]
        st = self.tags[tid]

        # 1. duplicate suppression: same tag + same lane within the window
        last = st.last_read.get(lane)
        if last is not None:
            gap = (ts - last).total_seconds()
            if gap < cfg.DUP_WINDOW_S or (cfg.DUP_INCLUSIVE and gap == cfg.DUP_WINDOW_S):
                self._log_read(ts, st, lane, det, "DUPLICATE_IGNORED", ZERO, ZERO, False)
                return
        st.last_read[lane] = ts

        stat = self._stat(st, ts)
        stat["crossings"] += 1
        higher = rank(det) > rank(st.cls)
        charged = det if higher else st.cls        # lower detected -> tag class (TRAP4)
        base = cfg.RATES[charged]
        key = (tid,)

        # 2. exempt: fare 0, still logged. EC5 choice: no penalty, no REVERIFY.
        if st.exempt:
            if higher and cfg.EXEMPT_MISMATCH_PENALTY:
                pen = self._mismatch_penalty(st, ts)
                st.balance -= pen
                stat["penalties"] += pen
                self._log_read(ts, st, lane, det, "EXEMPT", ZERO, pen, True)
            else:
                self._log_read(ts, st, lane, det, "EXEMPT", ZERO, ZERO, higher)
            self._snap(st, ts)
            return

        # 3. blacklisted: cash 2x the charged-class rate, balance untouched
        if st.status == "BLACKLISTED":
            if higher:
                self._mismatch_penalty(st, ts)
            cash = money(base * 2)
            stat["cash_paid"] += cash
            self._log_read(ts, st, lane, det, "CASH_BLACKLISTED", cash, ZERO, higher, cash=cash)
            self._snap(st, ts)
            return

        # 4. pass: covers the class it was bought for (not a higher detected class)
        p = st.pass_
        if p is not None and not higher and p.usable(ts):
            if p.kind == "TRIP_50":
                p.trips_used += 1
            self.returns.start(key, ts)             # a pass crossing can be the "first"
            self._log_read(ts, st, lane, det, "PASS", ZERO, ZERO, False)
            self._snap(st, ts)
            return

        # 5. normal fare: return discount, then night discount, then penalty
        is_return = self.returns.active(key, ts)
        commercial = charged != "CAR"
        fee, _, _ = apply_discounts(base, is_return, ts, commercial and cfg.NIGHT_DISCOUNT)
        pen = self._mismatch_penalty(st, ts) if higher else ZERO
        st.balance -= fee + pen                     # may go negative (EC2, EC4)
        if is_return:
            self.returns.consume(key)
        else:
            self.returns.start(key, ts)
        if st.balance < 0:
            st.status = "BLACKLISTED"
        elif st.balance <= low_threshold(st.cls):
            st.status = "LOW_BALANCE"
        stat["fare_charged"] += fee
        stat["penalties"] += pen
        self._log_read(ts, st, lane, det, "RETURN" if is_return else "SINGLE",
                       fee, pen, higher, tag_fare=fee)
        self._snap(st, ts)

    # ------------------------------------------------------------ recharge
    def _recharge(self, ts, row):
        tid = row["tag_id"]
        amount = Decimal(row["amount"])
        st = self.tags.get(tid)
        base = {"timestamp": ts.strftime(TS), "tag_id": tid, "amount": amount}
        if st is None:
            self.recharge_log.append({**base, "status": "REJECTED_UNKNOWN_TAG", "balance_after": ZERO})
            return
        if amount < cfg.MIN_RECHARGE:
            self.recharge_log.append({**base, "status": "REJECTED_MINIMUM", "balance_after": st.balance})
            return
        st.balance += amount
        self._stat(st, ts)["recharges"] += amount
        if st.status == "BLACKLISTED":
            if st.balance > 0:                      # exactly 0 stays blacklisted (EC4)
                st.status = "LOW_BALANCE" if st.balance <= low_threshold(st.cls) else "ACTIVE"
        elif st.status == "LOW_BALANCE" and st.balance > low_threshold(st.cls):
            st.status = "ACTIVE"
        self.recharge_log.append({**base, "status": "OK", "balance_after": st.balance})
        self._snap(st, ts)

    # ---------------------------------------------------------------- pass
    def _pass(self, ts, row):
        tid, kind = row["tag_id"], row["pass_type"]
        st = self.tags.get(tid)
        rej = {"timestamp": ts.strftime(TS), "tag_id": tid, "pass_type": kind,
               "status": "REJECTED", "price": ZERO, "valid_from": "", "valid_to": ""}
        if st is None:
            self.pass_log.append(rej)
            return
        if kind == "MONTHLY_LOCAL":
            if not (st.local and st.cls == "CAR"):  # TRAP1
                self.pass_log.append(rej)
                return
            price = cfg.MONTHLY_LOCAL_PRICE
        elif kind == "TRIP_50":
            price = money(cfg.RATES[st.cls] * cfg.TRIP_PASS_PRICE_MULT)
        else:
            self.pass_log.append(rej)
            return
        if st.pass_ is not None and st.pass_.usable(ts):   # one active pass at a time
            self.pass_log.append(rej)
            return
        end = month_end(ts)
        st.pass_ = PassState(kind, ts, end)
        self.pass_log.append({**rej, "status": "SOLD", "price": price,
                              "valid_from": ts.strftime("%Y-%m-%d"),
                              "valid_to": end.strftime("%Y-%m-%d")})
        self.pass_sales.append((ts.date(), price))
        stat = self._stat(st, ts)
        if cfg.PASS_SALES_AS_CASH:
            stat["cash_paid"] += price
        self._snap(st, ts)

    # -------------------------------------------------------------- reports
    def daily_collection(self, d_from, d_to):
        days = {}
        d = d_from
        while d <= d_to:
            days[d] = defaultdict(Decimal)
            d += timedelta(days=1)
        for r in self.read_log:
            day = days.get(r["_date"])
            if day is None:
                continue
            day["reads"] += 1
            o = r["outcome"]
            if o == "DUPLICATE_IGNORED":
                day["dups"] += 1
            elif o == "EXEMPT":
                day["exempt"] += 1
            elif o == "PASS":
                day["pass"] += 1
            else:
                day["paid"] += 1
            day["tag"] += r["_tag"]
            day["cash"] += r["_cash"]
            day["pen"] += r["penalty"] if o in ("SINGLE", "RETURN", "EXEMPT") else ZERO
        if cfg.PASS_SALES_AS_CASH:
            for dt, price in self.pass_sales:
                if dt in days:
                    days[dt]["cash"] += price
        rows = []
        for d, v in days.items():
            total = v["tag"] + v["cash"] + v["pen"]
            rows.append({"date": d.isoformat(), "reads": int(v["reads"]),
                         "duplicates_ignored": int(v["dups"]), "exempt_crossings": int(v["exempt"]),
                         "pass_crossings": int(v["pass"]), "paid_crossings": int(v["paid"]),
                         "tag_collection": v["tag"], "cash_collection": v["cash"],
                         "penalties": v["pen"], "total_collection": total})
        return rows

    def statements(self, month):
        y, m = map(int, month.split("-"))
        start = datetime(y, m, 1)
        end = month_end(start)
        rows = []
        for tid in sorted(self.tags):
            st = self.tags[tid]
            opening, closing = st.opening, st.opening
            snap = None
            for h in st.history:
                if h[0] < start:
                    opening = h[1]
                if h[0] <= end:
                    closing, snap = h[1], h
            s = self.stats.get((tid, month), {})
            if snap is None:
                status = "ACTIVE"
            else:
                _, _, stat, rev, pinfo = snap
                active_pass = pinfo is not None and pinfo[1] >= end and \
                    (pinfo[0] == "MONTHLY_LOCAL" or pinfo[2] > 0)
                status = ("BLACKLISTED" if stat == "BLACKLISTED" else
                          "REVERIFY" if rev else "ACTIVE_PASS" if active_pass else "ACTIVE")
            rows.append({
                "month": month, "tag_id": tid, "registered_class": st.cls,
                "opening_balance": opening, "crossings": int(s.get("crossings", 0)),
                "fare_charged": s.get("fare_charged", ZERO), "penalties": s.get("penalties", ZERO),
                "cash_paid": s.get("cash_paid", ZERO), "recharges": s.get("recharges", ZERO),
                "closing_balance": closing, "status": status})
        return rows


# ----------------------------------------------------------------- writers
def _fmt(v):
    return f"{v:.2f}" if isinstance(v, Decimal) else str(v)


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([_fmt(r[c]) for c in columns])


READ_COLS = ["timestamp", "tag_id", "lane", "registered_class", "detected_class",
             "outcome", "fare", "penalty", "balance_after", "flags"]
RECHARGE_COLS = ["timestamp", "tag_id", "amount", "status", "balance_after"]
PASS_COLS = ["timestamp", "tag_id", "pass_type", "status", "price", "valid_from", "valid_to"]
DAILY_COLS = ["date", "reads", "duplicates_ignored", "exempt_crossings", "pass_crossings",
              "paid_crossings", "tag_collection", "cash_collection", "penalties", "total_collection"]
STATEMENT_COLS = ["month", "tag_id", "registered_class", "opening_balance", "crossings",
                  "fare_charged", "penalties", "cash_paid", "recharges", "closing_balance", "status"]
