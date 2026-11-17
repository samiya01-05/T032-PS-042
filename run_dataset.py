"""Usage:  python run_dataset.py <data_dir> <out_dir>

Reads <data_dir>/commands.txt and runs the commands in file order.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import dataset_engine as de  # noqa: E402


def main(data_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    engine = None
    with open(os.path.join(data_dir, "commands.txt"), encoding="utf-8") as f:
        lines = [ln.strip() for ln in f]
    for ln in lines:
        if not ln or ln.startswith("#"):
            continue
        cmd, *args = [a.strip() for a in ln.split("|")]
        p = lambda name: os.path.join(data_dir, name)  # noqa: E731
        if cmd == "LOAD_TAGS":
            engine = de.Engine(de.load_tags(p(args[0])))
        elif cmd == "PROCESS_EVENTS":
            engine.process_events(de.read_rows(p(args[0])), de.read_rows(p(args[1])),
                                  de.read_rows(p(args[2])))
            de.write_csv(os.path.join(out_dir, "read_log.csv"), de.READ_COLS, engine.read_log)
            de.write_csv(os.path.join(out_dir, "recharge_log.csv"), de.RECHARGE_COLS, engine.recharge_log)
            de.write_csv(os.path.join(out_dir, "pass_log.csv"), de.PASS_COLS, engine.pass_log)
        elif cmd == "PRINT_DAILY_COLLECTION":
            rows = engine.daily_collection(date.fromisoformat(args[0]), date.fromisoformat(args[1]))
            de.write_csv(os.path.join(out_dir, "daily_collection.csv"), de.DAILY_COLS, rows)
        elif cmd == "PRINT_STATEMENTS":
            de.write_csv(os.path.join(out_dir, "statements.csv"), de.STATEMENT_COLS,
                         engine.statements(args[0]))
        else:
            print(f"Unknown command skipped: {cmd}", file=sys.stderr)
    print(f"Done. Files written to {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python run_dataset.py <data_dir> <out_dir>")
    main(sys.argv[1], sys.argv[2])
