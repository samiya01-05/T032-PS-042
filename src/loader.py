"""
loader.py  --  reads the 6 CSV files into model objects and builds EngineState.

Only ONE public function matters:  load_state(data_dir)
"""
from __future__ import annotations

import csv
import os
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from src.models import (
    AvcEvent, Bank, Pass, Plaza, Tag, Tariff, CLASS_ORDER, parse_date, parse_ts,
)
from src.state import DataError, EngineState

STATUSES = {"ACTIVE", "LOW_BALANCE", "BLACKLISTED", "HOTLISTED"}


def _read_csv(data_dir: str, filename: str, required: List[str]) -> List[dict]:
    path = os.path.join(data_dir, filename)
    if not os.path.isfile(path):
        raise DataError(f"Missing input file: {path}")
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise DataError(f"{filename}: missing column(s) {missing}")
        rows = []
        for row in reader:
            # strip stray spaces; skip fully blank lines
            clean = {k: (v or "").strip() for k, v in row.items() if k is not None}
            if any(clean.values()):
                rows.append(clean)
        return rows


def _dec(value: str, where: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise DataError(f"{where}: {value!r} is not a number")


def _opt_dec(value: str, where: str) -> Optional[Decimal]:
    return _dec(value, where) if value != "" else None


def _bool(value: str, where: str) -> bool:
    v = value.lower()
    if v == "true":
        return True
    if v == "false":
        return False
    raise DataError(f"{where}: {value!r} is not true/false")


def _opt_int(value: str, where: str) -> Optional[int]:
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        raise DataError(f"{where}: {value!r} is not a whole number")


def load_state(data_dir: str) -> EngineState:
    banks: Dict[str, Bank] = {}
    for r in _read_csv(data_dir, "banks.csv", ["bank_id", "bank_name"]):
        banks[r["bank_id"]] = Bank(r["bank_id"], r["bank_name"])

    plazas: Dict[str, Plaza] = {}
    for i, r in enumerate(_read_csv(data_dir, "plazas.csv",
                                    ["plaza_id", "plaza_name", "highway", "nearest_plaza_km"]), 1):
        plazas[r["plaza_id"]] = Plaza(
            r["plaza_id"], r["plaza_name"], r["highway"],
            _dec(r["nearest_plaza_km"], f"plazas.csv row {i}"))

    tariffs = {}
    for i, r in enumerate(_read_csv(data_dir, "plaza_tariffs.csv",
                                    ["plaza_id", "vehicle_class", "single_journey_fee",
                                     "monthly_pass_fee"]), 1):
        where = f"plaza_tariffs.csv row {i}"
        if r["plaza_id"] not in plazas:
            raise DataError(f"{where}: unknown plaza {r['plaza_id']}")
        if r["vehicle_class"] not in CLASS_ORDER:
            raise DataError(f"{where}: unknown vehicle class {r['vehicle_class']}")
        tariffs[(r["plaza_id"], r["vehicle_class"])] = Tariff(
            r["plaza_id"], r["vehicle_class"],
            _dec(r["single_journey_fee"], where), _dec(r["monthly_pass_fee"], where))

    tags: Dict[str, Tag] = {}
    for i, r in enumerate(_read_csv(data_dir, "tags.csv",
                                    ["tag_id", "vehicle_no", "vehicle_class", "commercial",
                                     "issuer_bank", "balance", "status", "resident_flag",
                                     "resident_plaza_id", "resident_distance_km"]), 1):
        where = f"tags.csv row {i}"
        if r["issuer_bank"] not in banks:
            raise DataError(f"{where}: unknown bank {r['issuer_bank']}")
        if r["status"] not in STATUSES:
            raise DataError(f"{where}: unknown status {r['status']}")
        if r["vehicle_class"] not in CLASS_ORDER:
            raise DataError(f"{where}: unknown vehicle class {r['vehicle_class']}")
        if r["tag_id"] in tags:
            raise DataError(f"{where}: duplicate tag_id {r['tag_id']}")
        tags[r["tag_id"]] = Tag(
            tag_id=r["tag_id"], vehicle_no=r["vehicle_no"], vehicle_class=r["vehicle_class"],
            commercial=_bool(r["commercial"], where), issuer_bank=r["issuer_bank"],
            balance=_dec(r["balance"], where), status=r["status"],
            resident_flag=_bool(r["resident_flag"], where),
            resident_plaza_id=r["resident_plaza_id"] or None,
            resident_distance_km=_opt_dec(r["resident_distance_km"], where))

    passes: List[Pass] = []
    for i, r in enumerate(_read_csv(data_dir, "monthly_passes.csv",
                                    ["pass_id", "tag_id", "plaza_id", "pass_type", "purchase_date",
                                     "valid_to", "journeys_total", "journeys_used_opening",
                                     "amount_paid"]), 1):
        where = f"monthly_passes.csv row {i}"
        if r["tag_id"] not in tags:
            raise DataError(f"{where}: unknown tag {r['tag_id']}")
        if r["plaza_id"] not in plazas:
            raise DataError(f"{where}: unknown plaza {r['plaza_id']}")
        passes.append(Pass(
            pass_id=r["pass_id"], tag_id=r["tag_id"], plaza_id=r["plaza_id"],
            pass_type=r["pass_type"], purchase_date=parse_date(r["purchase_date"]),
            valid_to=parse_date(r["valid_to"]),
            journeys_total=_opt_int(r["journeys_total"], where),
            journeys_used=_opt_int(r["journeys_used_opening"], where),
            amount_paid=_dec(r["amount_paid"], where)))

    avc: List[AvcEvent] = []
    for i, r in enumerate(_read_csv(data_dir, "avc_history.csv",
                                    ["tag_id", "txn_ts", "plaza_id", "detected_class"]), 1):
        where = f"avc_history.csv row {i}"
        if r["tag_id"] not in tags:
            raise DataError(f"{where}: unknown tag {r['tag_id']}")
        avc.append(AvcEvent(r["tag_id"], parse_ts(r["txn_ts"]), r["plaza_id"], r["detected_class"]))

    return EngineState(banks, plazas, tariffs, tags, passes, avc)
