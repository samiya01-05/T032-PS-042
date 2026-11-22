"""
main.py  --  the command loop.  Reads commands.txt in FILE ORDER and sends each
command to the right module:

    TXN               -> Member A's process_txn(state, cmd)  (result is stored)
    TOPUP             -> topup.process_topup
    REVERSE           -> reversal.process_reverse
    PRINT_LOG         -> prints that day's decision log to the console
    PRINT_SETTLEMENT  -> computes + prints that day's settlement

At the end it writes decision_log.csv, settlement.csv and tag_events.csv.

Run (from the project root):
    python -m src.main sample_data output            # PS-042 pack, Member A's src/payment.py
    python -m src.main data output                   # teachers' reads/recharges/passes pack
    python -m src.main sample_data output --stub     # temporary stub engine (testing only)
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Callable, Optional

from src import reversal, topup
from src.invariants import check_invariants
from src.loader import load_state
from src.models import (
    PrintLogCommand, PrintSettlementCommand, ReverseCommand, TopupCommand, TxnCommand, TxnResult,
)
from src.parser import parse_commands
from src.settlement import compute_settlement
from src.state import EngineState
from src.writers import (
    format_decision_log_for_day, format_settlement, write_decision_log, write_settlement,
    write_tag_events,
)

TxnHandler = Callable[[EngineState, TxnCommand], TxnResult]


def _default_handler() -> TxnHandler:
    try:
        from src.payment import process_txn      # Member A's module
    except ModuleNotFoundError as exc:
        if exc.name == "src.payment":
            raise RuntimeError("src/payment.py (Member A) not found. "
                               "Add it, or run with --stub to use the temporary stub engine.")
        raise
    return process_txn


def run(data_dir: str, out_dir: str, process_txn: Optional[TxnHandler] = None,
        printer: Callable[[str], None] = print) -> EngineState:
    state = load_state(data_dir)
    commands = parse_commands(os.path.join(data_dir, "commands.txt"))
    handler = process_txn or _default_handler()

    for cmd in commands:                                  # strictly in file order
        if isinstance(cmd, TxnCommand):
            state.record_result(handler(state, cmd))
        elif isinstance(cmd, TopupCommand):
            topup.process_topup(state, cmd)
        elif isinstance(cmd, ReverseCommand):
            reversal.process_reverse(state, cmd)
        elif isinstance(cmd, PrintLogCommand):
            printer(format_decision_log_for_day(state.results, cmd.day))
        elif isinstance(cmd, PrintSettlementCommand):
            rows = compute_settlement(state, cmd.day)
            state.settlement_rows.extend(rows)
            printer(format_settlement(rows))

    write_decision_log(os.path.join(out_dir, "decision_log.csv"), state.results)
    write_settlement(os.path.join(out_dir, "settlement.csv"), state.settlement_rows)
    write_tag_events(os.path.join(out_dir, "tag_events.csv"), state.tag_events)

    problems = check_invariants(state)
    if problems:
        printer("INVARIANT PROBLEMS:\n  " + "\n  ".join(problems))
    else:
        printer("Invariant checks passed.")
    return state


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FASTag toll engine (Member B pipeline)")
    ap.add_argument("data_dir", help="folder with the CSVs and commands.txt")
    ap.add_argument("out_dir", help="folder for decision_log.csv, settlement.csv, tag_events.csv")
    ap.add_argument("--stub", action="store_true", help="use the temporary stub engine")
    args = ap.parse_args(argv)

    # A folder with reads.csv but no banks.csv is the teachers' reads/recharges/passes pack.
    has = lambda name: os.path.isfile(os.path.join(args.data_dir, name))  # noqa: E731
    if has("reads.csv") and not has("banks.csv"):
        from src.dataset_runner import run_dataset
        run_dataset(args.data_dir, args.out_dir)
        return 0

    handler = None
    if args.stub:
        from src.stub_engine import process_txn
        handler = process_txn
    state = run(args.data_dir, args.out_dir, handler)
    print(f"Done: {len(state.results)} transactions, {len(state.tag_events)} tag events, "
          f"{len(state.settlement_rows)} settlement rows -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
