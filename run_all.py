"""
run_all.py  --  one command that runs BOTH data packs and checks the results.

    python run_all.py                    # sample_data -> output/ps042 , data -> output/dataset
    python run_all.py <ps042_dir> <dataset_dir> <out_dir>

Exit code 0 only if every invariant / reconciliation check passes.
"""
import csv
import os
import sys
from decimal import Decimal

from src.dataset_runner import run_dataset
from src.main import run

ROOT = os.path.dirname(os.path.abspath(__file__))


def read(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def check_dataset(out):
    problems = []
    for r in read(os.path.join(out, "statements.csv")):
        want = (Decimal(r["opening_balance"]) + Decimal(r["recharges"])
                - Decimal(r["fare_charged"]) - Decimal(r["penalties"]))
        if want != Decimal(r["closing_balance"]):
            problems.append(f"statement does not add up for {r['tag_id']}")
    for r in read(os.path.join(out, "daily_collection.csv")):
        parts = sum(int(r[k]) for k in ("duplicates_ignored", "exempt_crossings",
                                        "pass_crossings", "paid_crossings"))
        if parts != int(r["reads"]):
            problems.append(f"daily reads do not add up on {r['date']}")
        total = Decimal(r["tag_collection"]) + Decimal(r["cash_collection"]) + Decimal(r["penalties"])
        if total != Decimal(r["total_collection"]):
            problems.append(f"daily total does not add up on {r['date']}")
    return problems


def main(argv):
    ps_dir = argv[1] if len(argv) > 1 else os.path.join(ROOT, "sample_data")
    ds_dir = argv[2] if len(argv) > 2 else os.path.join(ROOT, "data")
    out = argv[3] if len(argv) > 3 else os.path.join(ROOT, "output")
    failed = False

    if os.path.isdir(ps_dir):
        print("=" * 70 + "\nPS-042 pack:", ps_dir)
        quiet = []
        state = run(ps_dir, os.path.join(out, "ps042"), printer=quiet.append)
        bad = [m for m in quiet if m.startswith("INVARIANT")]
        print(f"  {len(state.results)} transactions, {len(state.tag_events)} tag events, "
              f"{len(state.settlement_rows)} settlement rows")
        print("  invariants:", "FAILED" if bad else "passed")
        for m in bad:
            print(m)
        failed |= bool(bad)
    else:
        print("PS-042 folder not found, skipped:", ps_dir)

    if os.path.isdir(ds_dir):
        print("=" * 70 + "\nTeachers' dataset:", ds_dir)
        run_dataset(ds_dir, os.path.join(out, "dataset"), printer=lambda m: print(" ", m))
        problems = check_dataset(os.path.join(out, "dataset"))
        print("  reconciliation:", "FAILED" if problems else "passed")
        for p in problems[:10]:
            print("  ", p)
        failed |= bool(problems)
    else:
        print("Dataset folder not found, skipped:", ds_dir)

    print("=" * 70 + "\nOutput folder:", out)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
