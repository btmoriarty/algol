#!/usr/bin/env python3
"""The evidence row: the one shape every Algol collector emits.

A collector reviews nothing and decides nothing. It emits deterministic
structured evidence that reconcile later folds into the record. Keeping the
shape in one place means seclint, brevlint, and any later collector speak the
same language, and reconcile parses one thing.

A row is a single observation tied to a location, a standard, and a confidence.
For a deterministic mechanical match the confidence is 1.0; the field exists so
a later, less certain collector can report honestly instead of overclaiming.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class EvidenceRow:
    rule_id: str        # e.g. "brevlint/long-line"
    file: str           # path as given to the collector
    line: int           # 1-based
    standard: str       # the policy axis this maps to, e.g. "brevity"
    confidence: float   # 0.0 to 1.0; deterministic mechanical match is 1.0
    evidence: str       # the matched text, trimmed
    message: str = ""   # human-readable statement of what was found
    col: int = 1        # 1-based

    def to_dict(self) -> dict:
        return asdict(self)


def _sort_key(r: EvidenceRow) -> tuple:
    return (r.file, r.line, r.col, r.rule_id)


def rows_to_json(rows) -> str:
    """Serialize rows deterministically: sorted, sorted keys, trailing newline."""
    ordered = sorted(rows, key=_sort_key)
    return json.dumps([r.to_dict() for r in ordered], indent=2, sort_keys=True) + "\n"
