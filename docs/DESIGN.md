---
title: "PS-042 FASTag Toll and Violation Engine: Design Document"
subtitle: "Team T032: Sai Kushal S (1AT24CD065), Samiya (1AT24CD066), CSDS B"
---

# 1. Overview

A command-file-driven toll back-end in pure Python 3.10+ (standard library only, no UI). It reads plazas, tariffs, tags, AVC history, monthly passes, banks and a command file; it decides every lane transaction (fee, discount, penalty, payment mode, tag status), applies top-ups and reversals, and settles daily with the issuer banks.

**Outputs** (folder `output/ps042/`): `decision_log.csv` (one row per transaction, 17 columns), `settlement.csv` (daily, one row per issuer bank plus CONCESSIONAIRE), `tag_events.csv` (top-ups and reversals).

**Split of work.** Member A (Samiya): decision engine (BR-01 to 06, 09, 10, 15). Member B (Sai Kushal S): data loading, tag status and money gates, top-up, reversal, settlement, writers, invariants (BR-07, 08, 11 to 14, 16).

## 1.1 Architecture

| Layer | Modules | Job |
|---|---|---|
| Input | `loader.py`, `parser.py` | read the CSV files and parse command lines (`TXN`, `TOPUP`, `REVERSE`, `PRINT_LOG`, `PRINT_SETTLEMENT`) |
| State | `models.py`, `state.py` | tags, plazas, tariffs, passes, balances; one `EngineState` per run |
| Decision engine (A) | `payment.py`, `tariff.py`, `violation.py`, `returns.py`, `passes.py`, `resident.py`, `discounts.py`, `decision_log.py`, `rules_config.py` | `process_txn(state, cmd) -> TxnResult` |
| Money gates (B) | `status.py` | hotlist reject, blacklist charge, charge-or-decline; the only code that changes a balance |
| Events (B) | `topup.py`, `reversal.py` | top-up and 48-hour reversal |
| Settlement (B) | `settlement.py` | daily bank/concessionaire split |
| Output (B) | `writers.py`, `invariants.py`, `main.py` | write the CSVs, check the totals add up |

Flow: `main.py` reads commands in file order. For each `TXN` it calls `process_txn`; the result is stored and later settled. `TOPUP` and `REVERSE` change balances and produce tag events. At the end `settlement.py` builds the daily rows and `invariants.py` checks them.

# 2. Business-rule register

| ID | Rule | Code |
|---|---|---|
| BR-01 | Fee = tariff of the (plaza, charged class). Base plaza: CAR 85, LCV 140, BUS_TRUCK 285, 3_AXLE 310, 4-6_AXLE 445, OVERSIZE 545; other plazas use their own table | `tariff.py` |
| BR-02 | Return journey: same tag, same plaza, within 24 h of the first crossing is charged 50%; only once per 24 h | `returns.py`, `discounts.py` |
| BR-03 | Monthly pass: 50 journeys, 30 days, one plaza; unused journeys lapse; a pass journey is consumed before the return rule | `passes.py` |
| BR-04 | Local resident: resident flag, this plaza, within 20 km, non-commercial class, valid resident pass: free | `resident.py` |
| BR-05 | AVC mismatch: detected class higher than tag class means charge the detected class plus Rs 100; lower means charge the tag class | `violation.py` |
| BR-06 | 3rd higher-class mismatch within 30 days: tag marked for re-verification, detected class charged, no penalty | `violation.py` |
| BR-07 | Low balance (balance less than fee): declined, vehicle pays 2x fee in cash, tag becomes LOW_BALANCE | `status.py` |
| BR-08 | Blacklisted tag: vehicle pays 2x fee in cash | `status.py` |
| BR-09 | Hotlisted (stolen) tag: transaction REJECTED, no fee, barrier stays down | `payment.py`, `status.py` |
| BR-10 | Night discount: 22:00 to 06:00, commercial classes, 10% off after the return discount, never with a pass | `discounts.py` |
| BR-11 | Settlement fees: issuer bank gets 1% of each successful tag transaction; switch fee 0.25% | `settlement.py` |
| BR-12 | Cash penalties (decline and blacklist cash) are 100% concessionaire revenue | `settlement.py` |
| BR-13 | Daily settlement: one row per issuer bank plus a CONCESSIONAIRE row; net = gross - bank fee - switch fee - reversals (+ cash penalties for the concessionaire) | `settlement.py`, `invariants.py` |
| BR-14 | Reversal: within 48 h refunds the tag and reverses the settlement lines; after 48 h logged as DISPUTE, no refund | `reversal.py` |
| BR-15 | Queue waiver: queue time more than 10 s and the more-than-100 m flag set: free, WAIVED | `payment.py` |
| BR-16 | Top-up: minimum Rs 100; lifting the balance above Rs 200 (CAR) or Rs 500 (others) restores ACTIVE immediately | `topup.py` |

*(BR numbers beyond the brief's text are our own numbering of its settlement, reversal and top-up lines.)*

# 3. Precedence

The brief fixes the order **hotlist, blacklist, waiver, pass, resident, return journey, night discount**. The code applies it like this:

1. **Hotlist**: REJECTED, nothing else is looked at.
2. **AVC bookkeeping** (not a decision): find the charged class, record the mismatch.
3. **Blacklist**: 2x base fee in cash. It beats the waiver (EC-08): a long queue does not excuse a blacklisted tag.
4. **Queue waiver**: free.
5. **Pass**: free, one journey used, before the return rule.
6. **Resident**: free if all five conditions hold.
7. **Return journey**: 50%.
8. **Night discount**: a further 10% on the already halved fee, commercial only.
9. **Penalty and balance**: add the mismatch penalty; if balance is at least the amount, charge the tag; otherwise decline, 2x fee in cash, tag becomes LOW_BALANCE.

*Why this order:* the more final a condition is, the earlier it sits. Pass, resident and waived crossings are free, so discounts never reach them; that is why night is "not combined with passes" without extra code. The AVC class is found right after the hotlist check because every later step needs the charged class for the fee.

# 4. Edge cases and what the engine does

All are pinned by tests on the real sample pack (`tests/test_end_to_end_real.py`).

| Edge case | Transaction | Result |
|---|---|---|
| EC-01 return at exactly 24 h | TXN-00009 then TXN-00066 (08:15:00 both days) | RETURN, 42.50 |
| EC-02 last pass journey, then return in 24 h | TXN-00068 then TXN-00096 | PASS (0.00), then RETURN 37.50 |
| EC-03 balance equals fee | TXN-00123 (balance 140.00, LCV fee 140.00) | CHARGED, balance 0.00 |
| EC-04 3rd mismatch on day 30 | TXN-00117 | 3_AXLE 340.00, penalty 0.00, BR-06, tag flagged |
| EC-05 resident tag, commercial class | TXN-00010 (LCV), TXN-00018 (CAR detected LCV) | CHARGED; 255.00 = 155 + 100. TXN-00024 (CAR at exactly 20.0 km) is RESIDENT |
| EC-06 BUS_TRUCK at 22:00 | TXN-00204 (21:59:59), TXN-00205 (22:00:00) | no discount; NIGHT 283.50 |
| EC-07 reversal at exactly 48 h | TXN-00020 (48 h), TXN-00027 (47 h 59 m 59 s), TXN-00058 (50 h) | REFUNDED, REFUNDED, DISPUTE |
| EC-08 waiver on blacklisted tag | TXN-00146 | BLACKLIST_CASH 570.00, not WAIVED |

# 5. Boundary decisions

| # | Question | Decision |
|---|---|---|
| 1 | "Within 24 h" | inclusive: exactly 24:00:00 is a return, 24:00:01 is not |
| 2 | Return anchor | a paid or pass crossing starts the window; using the return closes it; the next crossing is full fare and starts a new window; an open window is never extended |
| 3 | Cash, waived, rejected crossings | do not start a window |
| 4 | Pass crossing as "first" | yes (EC-02) |
| 5 | Night window | 22:00:00 inclusive to 06:00:00 exclusive |
| 6 | 3 mismatches in 30 days | inclusive 30 days; the current mismatch counts; only higher-class mismatches count; history is seeded from `avc_history.csv` |
| 7 | Commercial | tag flag is true, or charged class is not CAR |
| 8 | Balance check | balance at least fee + penalty succeeds |
| 9 | Queue waiver | strictly more than 10 s and flag set |
| 10 | Pass validity | purchase date to valid-to date, both inclusive; one plaza |
| 11 | Reversal window | 48 h inclusive |
| 12 | Rounding | Decimal, half-up to the paisa; fees rounded per transaction, then added |

**Choices where the brief is silent** (each is one flag in `src/rules_config.py` or `src/ds_config.py`; to confirm with the evaluators):

- After a return discount is used, the next crossing starts a new 24 h window (row 2).
- A cash decline charges 2x the (discounted) fee only; the Rs 100 mismatch penalty is dropped (`DECLINE_INCLUDES_PENALTY`).
- A pass or resident exemption still covers a car detected as a higher class (`PASS_COVERS_HIGHER_CLASS`).
- A resident CAR detected as a commercial class is charged and not exempt (`COMMERCIAL_BY_CHARGED_CLASS`).

# 6. Money rules

- **Charged:** balance is reduced by the amount; status may become LOW_BALANCE when under the threshold.
- **Declined (BR-07):** nothing leaves the tag; vehicle pays 2x fee in cash; tag set to LOW_BALANCE.
- **Blacklisted (BR-08):** 2x base fee in cash; balance untouched.
- **Top-up (BR-16):** below Rs 100 is REJECTED (`BELOW_MINIMUM_100`). Otherwise the balance rises; if the tag was LOW_BALANCE and is now above its threshold the status becomes ACTIVE (`STATUS_RESTORED_ACTIVE`), else `STILL_LOW_BALANCE`.
- **Reversal (BR-14):** only a real tag deduction can be reversed. Within 48 h the tag is refunded and the bank fee and switch fee lines of that transaction are taken back; after 48 h it is logged as a dispute.
- **Settlement (BR-11 to 13):** per issuer bank and day: successful tag transactions, gross, bank fee (1%), switch fee (0.25%), reversals, net. The CONCESSIONAIRE row sums the bank rows and adds cash penalties.

Worked example (12 Oct, BNK-01): gross 1899.00, bank fee 19.00, switch fee 4.74, net 1875.26.

# 7. Decision log format

17 columns: `txn_id, ts, plaza_id, tag_id, tag_class, avc_class, charged_class, base_fee, discount_type, discount_amount, penalty, amount, payment_mode, decision, balance_after, tag_status_after, rule_ids`.

- `decision` is one of CHARGED, PASS, RESIDENT, WAIVED, DECLINED_CASH, BLACKLIST_CASH, REJECTED.
- `discount_type` is NONE, RETURN, NIGHT or RETURN+NIGHT; `discount_amount` is base fee minus discounted fee.
- `penalty` is the mismatch penalty on CHARGED rows; on cash rows it is the cash paid minus the fee it was doubled from.
- `rule_ids` lists the rules applied in order, joined with `;`, for example `BR-01;BR-05;BR-02`.
- PASS, RESIDENT, WAIVED and REJECTED rows move no money: amount 0.00, payment mode NONE.

# 8. Teachers' reads / recharges / passes pack

The project also runs the second data pack (`data/`: tags, reads, recharges, passes). `python -m src.main data output` detects it (a `reads.csv` without `banks.csv`) and writes `read_log`, `recharge_log`, `pass_log`, `daily_collection` and `statements` to `output/dataset/`. Its own rates and every uncertain choice (duplicate window, night discount, pass-sale cash) are named flags in `src/ds_config.py`.

# 9. Testing

214 automated tests (`python -m unittest discover -s tests -t .`):

- unit tests per module (tariff, violation, returns, passes, resident, discounts, payment, top-up, reversal, settlement, parser, loader);
- an end-to-end test on the real PS-042 sample pack pinning each edge case above and the settlement and invariant checks;
- tests for the teachers' pack engine;
- the pipeline was also run on 150 randomly altered PS-042 packs and 40 altered dataset packs; every run finished without errors and passed the invariant checks.

# 10. How to run

    python run_all.py
    python -m src.main sample_data output
    python -m unittest discover -s tests -t .
