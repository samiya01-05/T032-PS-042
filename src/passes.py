"""BR-03 (commuter pass, 50 journeys) and the resident pass lookup used by BR-04.

Works on Member B's `Pass` objects (state.passes): purchase_date / valid_to are DATES and
both days are inclusive; journeys_used starts at journeys_used_opening and is updated here.
"""
from __future__ import annotations

from typing import Optional

from src.models import Pass
from src.state import EngineState

COMMUTER = "COMMUTER_50"
RESIDENT = "RESIDENT_MONTHLY"
DEFAULT_JOURNEYS = 50


def journeys_total(p: Pass) -> int:
    return p.journeys_total if p.journeys_total is not None else DEFAULT_JOURNEYS


def journeys_used(p: Pass) -> int:
    return p.journeys_used or 0


def journeys_left(p: Pass) -> int:
    return journeys_total(p) - journeys_used(p)


def valid_at(p: Pass, plaza_id: str, ts) -> bool:
    """Right plaza and purchase_date <= day <= valid_to (the pass lapses after valid_to)."""
    return p.plaza_id == plaza_id and p.purchase_date <= ts.date() <= p.valid_to


def find_commuter(state: EngineState, tag_id: str, plaza_id: str, ts) -> Optional[Pass]:
    """A usable commuter pass: right plaza, inside its dates, journeys left."""
    for p in state.passes_for(tag_id):
        if p.pass_type == COMMUTER and valid_at(p, plaza_id, ts) and journeys_left(p) > 0:
            return p
    return None


def find_resident(state: EngineState, tag_id: str, plaza_id: str, ts) -> Optional[Pass]:
    """A valid resident pass at this plaza (unlimited crossings, so no counter)."""
    for p in state.passes_for(tag_id):
        if p.pass_type == RESIDENT and valid_at(p, plaza_id, ts):
            return p
    return None


def consume_journey(p: Pass) -> None:
    p.journeys_used = journeys_used(p) + 1
