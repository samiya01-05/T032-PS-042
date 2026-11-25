# T032-PS-042: FASTag Toll and Violation Engine

Team **T032**: Sai Kushal S (1AT24CD065), Samiya (1AT24CD066), Section CSDS B.
Problem statement **PS-042**. Command-file driven toll back-end, pure Python 3.10+, standard library only (nothing to install).

## What it does

Reads plazas, tariffs, tags, AVC history, monthly passes, banks and a command file. For every lane transaction it decides fee, discount, penalty, payment mode and tag status; it also handles top-ups and reversals and settles daily with each issuer bank.

## Steps to run

1. Install Python 3.10 or newer (check with `python --version`; on Windows `py --version` also works).
2. Download or clone this repository and open a terminal in its folder (the one containing `run_all.py`).
3. Run everything:

       python run_all.py

   Results appear in `output/`. To run one pack only:

       python -m src.main sample_data output     # PS-042 pack (the main one)
       python -m src.main data output            # teachers' reads/recharges/passes pack

4. Run the full test suite (214 tests, all must pass):

       python -m unittest discover -s tests -t .

   (`python -m pytest tests -q` also works if pytest is installed.)

## Output files

| File | Content |
|---|---|
| `output/ps042/decision_log.csv` | **Decision log**: one row per transaction (17 columns: fee, discount, penalty, amount, payment mode, decision, balance, tag status, rule ids) |
| `output/ps042/settlement.csv` | Daily settlement: one row per issuer bank plus CONCESSIONAIRE |
| `output/ps042/tag_events.csv` | Top-ups and reversals |
| `output/dataset/*.csv` | Results for the teachers' reads/recharges/passes pack |

The output files committed here were produced by `python run_all.py` on the supplied sample data.

## Repository contents

| Path | Content |
|---|---|
| `docs/DESIGN.pdf` | **Design document**: business-rule register BR-01 to BR-16, precedence, edge cases, boundary decisions (source: `docs/DESIGN.md`) |
| `tests/` | **Full test suite**: 214 unit and end-to-end tests |
| `src/` | Engine and pipeline modules |
| `sample_data/` | PS-042 input pack (plazas, tariffs, tags, AVC history, passes, banks, `commands.txt`) |
| `data/` | Teachers' input pack |
| `output/` | Generated results, including the decision log |

## Precedence

hotlist, blacklist, waiver, pass, resident, return journey, night discount; then penalty and balance check. The AVC class check runs right after the hotlist check because the fee depends on the charged class. Details: `docs/DESIGN.pdf`.

## Who built what

| Member A (Samiya): decision engine (BR-01 to 06, 09, 10, 15) | Member B (Sai Kushal S): data, money, I/O (BR-07, 08, 11 to 14, 16) |
|---|---|
| `payment.py`, `tariff.py`, `violation.py`, `returns.py`, `passes.py`, `resident.py`, `discounts.py`, `decision_log.py`, `rules_config.py` | `loader.py`, `parser.py`, `state.py`, `status.py`, `topup.py`, `reversal.py`, `settlement.py`, `writers.py`, `invariants.py`, `main.py` |

Contract between them: `process_txn(state, cmd) -> TxnResult`.

## Rules the brief leaves open

Four choices are named flags in `src/rules_config.py` (teachers' pack: `src/ds_config.py`); each is listed in section 5 of the design document.


## Project Demo Video

Watch our FASTag Toll and Violation Engine demonstration:

https://drive.google.com/file/d/1T7eBe8Mbt4p9_CwdXQAkfworQQmNfsq3/view?usp=sharing
