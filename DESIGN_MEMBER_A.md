# PS-042 FASTag Toll and Violation Engine: Member A design section

Team T032. Covers the decision engine: BR-01 to 06, 09, 10, 15.

## 1. Business-rule register (Member A rules)

| ID | Rule | Where in code |
|---|---|---|
| BR-01 | Fee = tariff for (plaza, charged class) | `tariff.py` |
| BR-02 | Return journey: same tag, same plaza, within 24 h (inclusive) of the first crossing = 50%, once per 24 h | `returns.py`, `discounts.py` |
| BR-03 | Commuter pass: 50 journeys, 30 days, one plaza. Consumed before the return rule. Unused journeys lapse. | `passes.py` |
| BR-04 | Resident exemption: resident tag, non-commercial, valid resident pass, distance <= 20 km | `resident.py` |
| BR-05 | AVC mismatch: detected higher = charge detected class + Rs 100; detected lower = charge tag class | `violation.py` |
| BR-06 | 3rd higher mismatch within 30 days: charge detected class, no penalty, tag marked for re-verification | `violation.py` |
| BR-09 | Hotlisted: REJECTED, no fee, barrier stays down | `payment.py` |
| BR-10 | Night discount: 22:00:00 <= t < 06:00:00, commercial only, 10% after the return discount, never with a pass | `discounts.py` |
| BR-15 | Queue waiver: queue_s > 10 and the >100 m flag set = free, WAIVED | `payment.py` |

Member B owns BR-07, 08, 11 to 14, 16. `payment.py` applies BR-07 (low-balance decline) and BR-08 (blacklist cash) inline so the engine runs on its own; B's `status.py` can replace the two helpers `deduct` and `mark_low_balance`.

## 2. Precedence (what to say when asked)

The brief fixes: hotlist, blacklist, waiver, pass, resident, return journey, night discount. The code applies them in this order:

1. **Hotlist** -> REJECTED. Stolen tag: nothing else is looked at.
2. **AVC bookkeeping** (not a decision): find the charged class and update mismatch history.
3. **Blacklist** -> 2x base fee in cash. It outranks the waiver (EC-08): a queue does not excuse a blacklisted tag.
4. **Queue waiver** -> free.
5. **Pass** -> free, one journey used. Consumed before return rule.
6. **Resident** -> free, if every condition holds.
7. **Return journey** -> 50%.
8. **Night discount** -> a further 10% (on the already halved fee), commercial only.
9. **Penalty and balance**: add the AVC penalty. If balance >= amount, charge the tag; else decline, 2x fee in cash, tag becomes LOW_BALANCE.

Why this order: the more serious or more final a condition is, the earlier it sits. A pass or resident crossing is free, so discounts never reach it. That is why night is "not combined with passes" without any extra code.

## 3. Boundary decisions and defaults

| # | Question | Default |
|---|---|---|
| 1 | "Within 24 h" | inclusive: exactly 24:00:00 is a return (EC-01); 24:00:01 is not |
| 2 | Return anchor | a paid or pass crossing starts the window; using the return closes it; the next crossing is full fare and starts a new window |
| 3 | Do cash, waived, rejected crossings start a window? | No. Only tag-paid and pass crossings do |
| 4 | Pass crossing as "first" | Yes (EC-02: last pass journey, then return within 24 h = 50%) |
| 5 | Night window | 22:00:00 inclusive to 06:00:00 exclusive |
| 6 | 3 mismatches in 30 days | window is inclusive of exactly 30 days; current mismatch counts (EC-04) |
| 7 | Which mismatches count | only higher-class ones |
| 8 | Commercial | tag flag, or charged class not CAR |
| 9 | Balance check | balance >= fee + penalty succeeds (EC-03) |
| 10 | Blacklist cash | 2x base fee; no mismatch penalty added; log `penalty` = cash - base fee |
| 11 | Declined cash | 2x discounted fee; mismatch penalty dropped; `penalty` = cash - discounted fee |
| 12 | Pass / resident / waived rows | amount 0, discount_type NONE, no penalty; mismatch still recorded in history |
| 13 | Rounding | Decimal, half-up, once, after both discounts |
| 14 | Pass validity | valid_from <= t <= valid_to, at its own plaza only |
| 15 | Resident distance | `Txn.distance_km` if given, else `Tag.distance_km` |

Rows 3, 10, 11 and 12 are guesses where the brief is silent. Each is a one-place change in `payment.py`.

## 4. Decision log

17 columns, set in `decision_log.COLUMNS`: txn_id, timestamp, tag_id, plaza_id, tag_class, detected_class, charged_class, base_fee, discount_type, discount_amount, penalty, amount, payment_mode, decision, balance_after, tag_status_after, rule_ids. `rule_ids` is joined with `;` (`RULE_SEP` in `models.py`). Rename or reorder against the real README.

## 5. Dataset engine (reads / recharges / passes)

Files: `src/ds_config.py` (numbers + every uncertain choice), `src/dataset_engine.py` (engine, reports, writers), `run_dataset.py` (CLI: `python run_dataset.py data output`).

Events from the three files are merged by timestamp. Ties: PASS, RECHARGE, READ.

Read precedence: duplicate -> exempt -> blacklisted -> pass -> return/night discount + penalty -> balance.

| Rule | Implementation |
|---|---|
| Rates | CAR 65, LCV 105, BUS_TRUCK 220, MAV 345 (`RATES`) |
| Duplicate | same tag + same lane, gap <= 120 s vs the last accepted read: DUPLICATE_IGNORED (`DUP_INCLUSIVE`) |
| Exempt | fare 0, EXEMPT. Higher-class mismatch: flag MISMATCH only, no penalty, no REVERIFY (EC5) |
| Blacklisted | CASH_BLACKLISTED, cash = 2 x charged-class rate, balance unchanged |
| Pass | covers the class it was bought for. Detected class higher than registered: pass does not apply |
| MONTHLY_LOCAL | local-resident CAR only (else REJECTED), Rs 330, purchase date to month end, unlimited |
| TRIP_50 | price 30 x registered rate, 50 free crossings, then normal fares (TRAP2) |
| Return | 50% within 24 h (inclusive) of the first crossing, once; pass crossings count as first |
| Night | commercial class (not CAR), 22:00 <= t < 06:00, 10% after return (`NIGHT_DISCOUNT`) |
| Higher mismatch | higher rate + Rs 100 + REVERIFY; 3rd inside 30 days: no penalty |
| Lower mismatch | registered rate, no penalty, no flag |
| Balance | fare is always deducted and may go negative. < 0: BLACKLISTED. <= 200 (CAR) / 500 (others) after a charge: LOW_BALANCE |
| Recharge | < 100: REJECTED_MINIMUM. Blacklist lifts only when balance > 0 (exactly 0 stays) |
| Cash collection | lane cash + pass sales (`PASS_SALES_AS_CASH`) |
| Statement status | BLACKLISTED > REVERIFY > ACTIVE_PASS > ACTIVE (at month end) |
