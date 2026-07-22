#!/usr/bin/env python3
"""brevlint: a deterministic style-and-brevity evidence collector.

The first Algol collector. It reviews nothing and gates nothing; it walks the
files it is given and emits evidence rows (see evidence.py) for mechanical
brevity and hygiene signals. Its output is deterministic, so the same input
always yields the same rows.

Rule set is a starter, meant to grow: long lines, trailing whitespace, runs of
blank lines, and leftover TODO markers. Each row maps to the policy axis passed
in (default "brevity").

Floor: Python 3.11+, stdlib only (evidence.py is a sibling module).

Usage:
  python brevlint.py FILE [FILE ...] [--standard brevity] [--max-line 100]
  python brevlint.py --rules scanner-rules.json --root DIR
Writes a JSON array of evidence rows to stdout, or to --out FILE.
Exit code is 0 whether or not findings are emitted: a collector reports, it
does not gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import EvidenceRow, rows_to_json  # noqa: E402
from pathmatch import iter_matching_files  # noqa: E402

DEFAULT_MAX_LINE = 100
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX)\b")
TRAILING_WS_RE = re.compile(r"[ \t]+$")


def lint_text(path: str, text: str, standard: str, max_line: int) -> list[EvidenceRow]:
    rows: list[EvidenceRow] = []
    lines = text.split("\n")
    blank_run = 0
    for i, line in enumerate(lines, start=1):
        # long line
        if len(line) > max_line:
            rows.append(
                EvidenceRow(
                    rule_id="brevlint/long-line",
                    file=path,
                    line=i,
                    col=max_line + 1,
                    standard=standard,
                    confidence=1.0,
                    evidence=line[:max_line] + "...",
                    message=f"line is {len(line)} chars; over the {max_line} limit",
                )
            )
        # trailing whitespace
        m = TRAILING_WS_RE.search(line)
        if m:
            rows.append(
                EvidenceRow(
                    rule_id="brevlint/trailing-whitespace",
                    file=path,
                    line=i,
                    col=m.start() + 1,
                    standard=standard,
                    confidence=1.0,
                    evidence=repr(line[m.start():]),
                    message="trailing whitespace",
                )
            )
        # leftover markers
        tm = TODO_RE.search(line)
        if tm:
            rows.append(
                EvidenceRow(
                    rule_id="brevlint/todo-marker",
                    file=path,
                    line=i,
                    col=tm.start() + 1,
                    standard=standard,
                    confidence=1.0,
                    evidence=line.strip()[:80],
                    message=f"leftover {tm.group(0)} marker",
                )
            )
        # runs of blank lines: report the third and beyond
        if line.strip() == "":
            blank_run += 1
            if blank_run >= 3:
                rows.append(
                    EvidenceRow(
                        rule_id="brevlint/blank-run",
                        file=path,
                        line=i,
                        standard=standard,
                        confidence=1.0,
                        evidence="",
                        message="three or more consecutive blank lines",
                    )
                )
        else:
            blank_run = 0
    return rows


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None  # binary or unreadable: a text collector skips it


def _resolve_from_rules(rules_path: Path, root: Path) -> list[Path]:
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    globs = data.get("collectors", {}).get("brevlint", [])
    return iter_matching_files(root, globs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="brevlint: style-and-brevity evidence collector.")
    parser.add_argument("files", nargs="*", type=Path, help="files to lint")
    parser.add_argument("--standard", default="brevity", help="policy axis these rows map to")
    parser.add_argument("--max-line", type=int, default=DEFAULT_MAX_LINE, help="max line length")
    parser.add_argument("--rules", type=Path, default=None, help="scanner-rules.json from the compiler")
    parser.add_argument("--root", type=Path, default=Path("."), help="root to resolve --rules globs")
    parser.add_argument("--out", type=Path, default=None, help="write JSON here (default: stdout)")
    args = parser.parse_args(argv)

    targets: list[Path] = list(args.files)
    if args.rules is not None:
        if not args.rules.is_file():
            print(f"brevlint: rules not found: {args.rules}", file=sys.stderr)
            return 2
        targets.extend(_resolve_from_rules(args.rules, args.root))
    if not targets:
        print("brevlint: no files given (pass files, or --rules with --root)", file=sys.stderr)
        return 2

    rows: list[EvidenceRow] = []
    for path in targets:
        text = _read_text(path)
        if text is None:
            continue
        rows.extend(lint_text(str(path), text, args.standard, args.max_line))

    output = rows_to_json(rows)
    if args.out is not None:
        args.out.write_text(output, encoding="utf-8")
        print(f"brevlint: wrote {len(rows)} rows to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
