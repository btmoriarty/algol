#!/usr/bin/env python3
"""decide: record a human disposition on a finding in the record.

The record holds findings; this is the command a human uses to attach a
decision to one. A disposition is accept, suppress, or defer, with a rationale
and the one to three conditions that would reopen it (reopens-if). A decision
with no reopens-if is a permanent verdict, which the model exists to prevent,
so decide refuses one unless --no-reopens says it is meant.

Each decision is also appended to an event log (JSONL, next to the record by
default) with a UTC timestamp. The record stays timestamp-free and diffable;
the log is the temporal account of who decided what, and when.

Floor: Python 3.11+, stdlib only (record.py is a sibling module).

Usage:
  python decide.py list [--record .algol/record.json] [--undecided]
  python decide.py set <finding-id> --state {accept,suppress,defer} \\
      --rationale TEXT --reopens-if TEXT [--reopens-if TEXT ...] [--by NAME] \\
      [--record .algol/record.json] [--events .algol/events.jsonl]
A finding id may be shortened to any unique prefix of six or more characters.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import DISPOSITION_STATES, Record, append_event, set_disposition  # noqa: E402

MAX_REOPENS = 3
MIN_PREFIX = 6


def resolve_id(record: Record, given: str) -> str:
    """The full finding id for `given`, an id or a unique prefix of it. Raises
    KeyError with a reason when there is no match or more than one."""
    ids = list(record.by_id())
    if given in ids:
        return given
    if len(given) < MIN_PREFIX:
        raise KeyError(f"no finding with id {given} (a prefix needs {MIN_PREFIX}+ characters)")
    hits = [i for i in ids if i.startswith(given)]
    if not hits:
        raise KeyError(f"no finding with id {given}")
    if len(hits) > 1:
        raise KeyError(f"id prefix {given} matches {len(hits)} findings; give more characters")
    return hits[0]


def _cmd_list(args) -> int:
    record = Record.from_json(args.record.read_text(encoding="utf-8"))
    for f in sorted(record.findings, key=lambda f: (f.file, f.line, f.claim)):
        if args.undecided and f.disposition is not None:
            continue
        state = f.disposition.state if f.disposition else "undecided"
        floor = " floor" if f.is_floor else ""
        print(f"{f.id}  {state:<9}  {f.status}{floor}  {f.file}:{f.line}  {f.claim}")
    return 0


def _cmd_set(args) -> int:
    reopens = [c.strip() for c in args.reopens_if if c.strip()]
    if len(reopens) > MAX_REOPENS:
        print(f"decide: at most {MAX_REOPENS} reopens-if conditions; keep the ones that matter",
              file=sys.stderr)
        return 2
    if not reopens and not args.no_reopens:
        print("decide: give at least one --reopens-if condition, or pass --no-reopens "
              "to record a permanent verdict on purpose", file=sys.stderr)
        return 2
    if not args.rationale.strip():
        print("decide: --rationale must not be empty", file=sys.stderr)
        return 2

    record = Record.from_json(args.record.read_text(encoding="utf-8"))
    try:
        fid = resolve_id(record, args.finding)
    except KeyError as exc:
        print(f"decide: {exc.args[0]}", file=sys.stderr)
        return 2
    finding = record.by_id()[fid]
    previous = finding.disposition.state if finding.disposition else None
    set_disposition(record, fid, args.state, args.rationale.strip(), reopens, by=args.by)
    args.record.write_text(record.to_json(), encoding="utf-8")

    events = args.events if args.events is not None else args.record.parent / "events.jsonl"
    append_event(events, {
        "event": "disposition",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "finding": fid,
        "file": finding.file,
        "line": finding.line,
        "claim": finding.claim,
        "state": args.state,
        "previous": previous,
        "rationale": args.rationale.strip(),
        "reopens_if": reopens,
        "by": args.by,
    })
    print(f"decide: {fid} {finding.file}:{finding.line} {finding.claim} -> {args.state}", file=sys.stderr)
    if not reopens:
        print("decide: warning: recorded with no reopens-if condition (a permanent verdict)",
              file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="record a human decision on a finding.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list findings with their ids and decisions")
    p_list.add_argument("--record", type=Path, default=Path(".algol/record.json"))
    p_list.add_argument("--undecided", action="store_true", help="only findings with no disposition")

    p_set = sub.add_parser("set", help="attach a disposition to one finding")
    p_set.add_argument("finding", help="finding id, or a unique prefix of six or more characters")
    p_set.add_argument("--state", required=True, choices=DISPOSITION_STATES)
    p_set.add_argument("--rationale", required=True, help="why, in a sentence")
    p_set.add_argument("--reopens-if", action="append", default=[],
                       help="a condition that would reopen the decision (one to three)")
    p_set.add_argument("--no-reopens", action="store_true",
                       help="allow a decision with no reopens-if condition")
    p_set.add_argument("--by", default="", help="who decided")
    p_set.add_argument("--record", type=Path, default=Path(".algol/record.json"))
    p_set.add_argument("--events", type=Path, default=None,
                       help="event log to append to (default: events.jsonl beside the record)")

    args = parser.parse_args(argv)
    if not args.record.is_file():
        print(f"decide: record not found: {args.record}", file=sys.stderr)
        return 2
    return _cmd_list(args) if args.cmd == "list" else _cmd_set(args)


if __name__ == "__main__":
    raise SystemExit(main())
