"""
state.py  --  the engine's memory.

EngineState keeps every table and every result so far.  Member A's code reads
tags/passes/avc_history/tariffs from here; Member B's code (topup, reversal,
settlement) reads and updates it.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from src.models import (
    AvcEvent, Bank, Pass, Plaza, ReversalRecord, SettlementRow, Tag, TagEvent,
    Tariff, TxnResult,
)


class DataError(Exception):
    """Raised for bad / inconsistent input data (message says what and where)."""


class EngineState:
    def __init__(
        self,
        banks: Dict[str, Bank],
        plazas: Dict[str, Plaza],
        tariffs: Dict[Tuple[str, str], Tariff],
        tags: Dict[str, Tag],
        passes: List[Pass],
        avc_history: List[AvcEvent],
    ) -> None:
        self.banks = banks
        self.plazas = plazas
        self.tariffs = tariffs
        self.tags = tags
        self.passes = passes
        self.avc_history = avc_history

        # Snapshot used later by invariants.py to prove the balances add up.
        self.opening_balances: Dict[str, Decimal] = {t.tag_id: t.balance for t in tags.values()}

        self.results: List[TxnResult] = []                 # decision log, in command order
        self.results_by_id: Dict[str, TxnResult] = {}
        self.tag_events: List[TagEvent] = []               # topups + reversals
        self.reversal_log: List[ReversalRecord] = []       # accepted reversals
        self.settlement_rows: List[SettlementRow] = []     # one block per PRINT_SETTLEMENT

        # Memory of the decision engine (AVC mismatch history, return-journey windows).
        # It lives here so it is created once per run and never rebuilt per transaction.
        self.engine_memory: Dict[str, object] = {}

    # ----- lookups
    def get_tag(self, tag_id: str) -> Optional[Tag]:
        return self.tags.get(tag_id)

    def passes_for(self, tag_id: str) -> List[Pass]:
        return [p for p in self.passes if p.tag_id == tag_id]

    def fee_for(self, plaza_id: str, vehicle_class: str) -> Decimal:
        try:
            return self.tariffs[(plaza_id, vehicle_class)].single_journey_fee
        except KeyError:
            raise DataError(f"No tariff for plaza {plaza_id!r} class {vehicle_class!r}")

    # ----- recording
    def record_result(self, result: TxnResult) -> None:
        """Store one TXN outcome (Member A's engine returns it, main.py stores it)."""
        if result.txn_id in self.results_by_id:
            raise DataError(f"Duplicate txn_id {result.txn_id}")
        if not result.bank_id:
            tag = self.tags.get(result.tag_id)
            result.bank_id = tag.issuer_bank if tag else ""
        self.results.append(result)
        self.results_by_id[result.txn_id] = result

    def record_event(self, event: TagEvent) -> None:
        self.tag_events.append(event)
