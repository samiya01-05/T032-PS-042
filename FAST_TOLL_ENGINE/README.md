# FAST_TOLL_ENGINE - Member B part (PS-042, Team T032)

Member B owns: data loading, command parsing, shared state, balance/status gates,
top-up, reversal, settlement, CSV writers, the command loop (CLI) and invariant checks.
Member A plugs in `src/payment.py` (+ tariff/violation/returns/passes/resident/discounts/decision_log).

## Run (from this folder, Python 3.10+)
    python -m src.main sample_data output --stub     # temporary stub engine (before A is ready)
    python -m src.main sample_data output            # real engine (needs src/payment.py)

## Test
    python -m unittest discover -s tests -t .

## Contract with Member A
    src/payment.py must expose:  process_txn(state: EngineState, cmd: TxnCommand) -> TxnResult
    A calls B's gates in src/status.py:
        hotlist_reject(tag), blacklist_charge(tag, fee), charge_tag_or_decline(tag, fee)
    `fee` = the amount that would be deducted from the tag.
    src/stub_engine.py is a throw-away example of such a handler; delete it when A is done.
