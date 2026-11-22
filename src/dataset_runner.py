"""
dataset_runner.py  --  runs the teachers' dataset (tags / reads / recharges / passes).

commands.txt of that pack:   LOAD_TAGS | PROCESS_EVENTS | PRINT_DAILY_COLLECTION | PRINT_STATEMENTS
Writes: read_log.csv, recharge_log.csv, pass_log.csv, daily_collection.csv, statements.csv
"""
from __future__ import annotations

import os
from datetime import date
from typing import Callable

from src import dataset_engine as de


def run_dataset(data_dir: str, out_dir: str, printer: Callable[[str], None] = print):
    os.makedirs(out_dir, exist_ok=True)
    engine = None
    with open(os.path.join(data_dir, "commands.txt"), encoding="utf-8-sig") as handle:
        lines = [ln.strip() for ln in handle]

    def path(name):
        return os.path.join(data_dir, name)

    for line in lines:
        if not line or line.startswith("#"):
            continue
        cmd, *args = [a.strip() for a in line.split("|")]
        cmd = cmd.upper()
        if cmd == "LOAD_TAGS":
            engine = de.Engine(de.load_tags(path(args[0])))
        elif engine is None:
            raise RuntimeError(f"{cmd}: LOAD_TAGS must come first in commands.txt")
        elif cmd == "PROCESS_EVENTS":
            engine.process_events(de.read_rows(path(args[0])), de.read_rows(path(args[1])),
                                  de.read_rows(path(args[2])))
            de.write_csv(os.path.join(out_dir, "read_log.csv"), de.READ_COLS, engine.read_log)
            de.write_csv(os.path.join(out_dir, "recharge_log.csv"), de.RECHARGE_COLS,
                         engine.recharge_log)
            de.write_csv(os.path.join(out_dir, "pass_log.csv"), de.PASS_COLS, engine.pass_log)
        elif cmd == "PRINT_DAILY_COLLECTION":
            rows = engine.daily_collection(date.fromisoformat(args[0]), date.fromisoformat(args[1]))
            de.write_csv(os.path.join(out_dir, "daily_collection.csv"), de.DAILY_COLS, rows)
        elif cmd == "PRINT_STATEMENTS":
            de.write_csv(os.path.join(out_dir, "statements.csv"), de.STATEMENT_COLS,
                         engine.statements(args[0]))
        else:
            printer(f"Unknown command skipped: {cmd}")
    if engine is None:
        raise RuntimeError("commands.txt has no LOAD_TAGS command")
    printer(f"Dataset run done: {len(engine.read_log)} reads, {len(engine.recharge_log)} recharges, "
            f"{len(engine.pass_log)} passes -> {out_dir}")
    return engine
