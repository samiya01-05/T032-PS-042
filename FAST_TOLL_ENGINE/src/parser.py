"""
parser.py  --  turns commands.txt into a list of command objects, IN FILE ORDER.

Line format:  COMMAND_NAME|arg1|arg2|...
  * lines starting with '#' are comments, blank lines are ignored
  * an empty argument (two '|' next to each other) means "not supplied" -> None
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import List, Optional, Union

from src.models import (
    PrintLogCommand, PrintSettlementCommand, ReverseCommand, TopupCommand, TxnCommand,
    parse_date, parse_ts,
)

Command = Union[TxnCommand, TopupCommand, ReverseCommand, PrintLogCommand, PrintSettlementCommand]

# command name -> how many arguments it takes
ARG_COUNTS = {"TXN": 8, "TOPUP": 3, "REVERSE": 2, "PRINT_LOG": 1, "PRINT_SETTLEMENT": 1}


class ParseError(Exception):
    pass


def _need(value: Optional[str], name: str, line_no: int) -> str:
    if value is None:
        raise ParseError(f"line {line_no}: required argument '{name}' is empty")
    return value


def _ts(value: Optional[str], name: str, line_no: int):
    try:
        return parse_ts(_need(value, name, line_no))
    except ValueError:
        raise ParseError(f"line {line_no}: bad timestamp for '{name}': {value!r}")


def _decimal(value: Optional[str], name: str, line_no: int) -> Decimal:
    try:
        return Decimal(_need(value, name, line_no))
    except InvalidOperation:
        raise ParseError(f"line {line_no}: '{name}' is not a number: {value!r}")


def parse_line(line: str, line_no: int) -> Optional[Command]:
    """Parse ONE line. Returns None for comments / blank lines."""
    text = line.strip()
    if not text or text.startswith("#"):
        return None

    parts = [p.strip() for p in text.split("|")]
    name = parts[0].upper()
    if name not in ARG_COUNTS:
        raise ParseError(f"line {line_no}: unknown command {parts[0]!r}")

    args: List[Optional[str]] = [p if p != "" else None for p in parts[1:]]
    expected = ARG_COUNTS[name]
    if len(args) > expected:
        raise ParseError(f"line {line_no}: {name} takes {expected} arguments, got {len(args)}")
    args += [None] * (expected - len(args))      # tolerate missing trailing arguments

    if name == "TXN":
        txn_id, ts, plaza_id, lane, tag_id, avc_class, queue_s, queue_flag = args
        flag = (queue_flag or "false").lower()
        if flag not in ("true", "false"):
            raise ParseError(f"line {line_no}: queue_flag must be true/false, got {queue_flag!r}")
        return TxnCommand(
            line_no=line_no,
            txn_id=_need(txn_id, "txn_id", line_no),
            ts=_ts(ts, "ts", line_no),
            plaza_id=_need(plaza_id, "plaza_id", line_no),
            lane=lane,
            tag_id=_need(tag_id, "tag_id", line_no),
            avc_class=avc_class,
            queue_s=_decimal(queue_s, "queue_s", line_no) if queue_s is not None else None,
            queue_flag=(flag == "true"),
        )
    if name == "TOPUP":
        tag_id, ts, amount = args
        return TopupCommand(line_no, _need(tag_id, "tag_id", line_no),
                            _ts(ts, "ts", line_no), _decimal(amount, "amount", line_no))
    if name == "REVERSE":
        txn_id, ts = args
        return ReverseCommand(line_no, _need(txn_id, "txn_id", line_no), _ts(ts, "ts", line_no))

    # PRINT_LOG / PRINT_SETTLEMENT
    try:
        day = parse_date(_need(args[0], "date", line_no))
    except ValueError:
        raise ParseError(f"line {line_no}: bad date {args[0]!r}")
    return PrintLogCommand(line_no, day) if name == "PRINT_LOG" else PrintSettlementCommand(line_no, day)


def parse_commands(path: str) -> List[Command]:
    """Parse the whole file; physical line numbers are kept for error messages."""
    commands: List[Command] = []
    with open(path, encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):
            cmd = parse_line(line, line_no)
            if cmd is not None:
                commands.append(cmd)
    return commands
