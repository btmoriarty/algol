#!/usr/bin/env python3
"""policy-review: check a change against the project's own standards.

policy-review is a model pass, not deterministic code and not a general bug
hunt. It reads the compiled review instructions (REVIEW.md) and a change, and
reports only where the change deviates from what the project declared it cares
about. The judgment runs when a model is pointed at the assembled prompt; this
tool is the deterministic harness around it.

Two subcommands:

  prompt   assemble the instruction: the discipline, the compiled standards, the
           change, and the required output schema. Feed the result to a model.
  ingest   validate a model's finding-set output (fail closed on anything
           malformed) and normalize it into the evidence-row shape reconcile
           consumes, source "policy-review".

A model pass is reasoned, not mechanically verified, so its rows enter reconcile
as heuristic like any other collector's. Only the deep tier or an ultra pass can
raise a finding to verified; policy-review never claims that.

Floor: Python 3.11+, stdlib only (evidence.py is a sibling module).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import EvidenceRow, rows_to_json  # noqa: E402

FINDING_SET_SCHEMA = {
    "finding_set": 1,
    "findings": [
        {
            "file": "src/example.py",
            "line": 42,
            "axis": "security",
            "evidence": "verbatim snippet or a file:line anchor from the change",
            "message": "how this deviates from the stated standard",
            "confidence": 0.7,
        }
    ],
}

INSTRUCTION = """\
You are performing policy-review for Algol. This is not a general bug hunt.

Your only job: report where the change deviates from the project's declared
review standards below. If the change meets the standards, return an empty
findings list. Do not report style, taste, or issues the standards do not name.

Rules:
- Judge only against the declared standards. A real bug that no standard covers
  is out of scope here.
- Every finding cites a verbatim snippet or a file:line anchor from the change
  as its evidence. No anchor, no finding.
- Assign a confidence from 0.0 to 1.0. You are reasoning, not verifying; do not
  claim certainty you do not have.
- Output ONLY a single JSON object matching the schema. No prose outside it.
"""


class ReviewOutputError(Exception):
    """The model output did not match the finding-set schema."""


def assemble_prompt(review_md: str, change_text: str) -> str:
    schema = json.dumps(FINDING_SET_SCHEMA, indent=2)
    return (
        INSTRUCTION
        + "\n## Declared standards (compiled)\n\n"
        + review_md.strip()
        + "\n\n## The change\n\n"
        + change_text.strip()
        + "\n\n## Required output schema\n\n"
        + schema
        + "\n"
    )


def validate_finding_set(obj: object) -> list[dict]:
    if not isinstance(obj, dict):
        raise ReviewOutputError("output must be a JSON object")
    findings = obj.get("findings")
    if not isinstance(findings, list):
        raise ReviewOutputError("output.findings must be a list (empty is allowed)")
    for i, f in enumerate(findings):
        where = f"findings[{i}]"
        if not isinstance(f, dict):
            raise ReviewOutputError(f"{where}: must be an object")
        for key, typ in (("file", str), ("axis", str), ("evidence", str), ("message", str)):
            if not isinstance(f.get(key), typ) or not f.get(key):
                raise ReviewOutputError(f"{where}.{key}: required non-empty {typ.__name__}")
        if not isinstance(f.get("line"), int) or f["line"] < 0:
            raise ReviewOutputError(f"{where}.line: required non-negative integer")
        c = f.get("confidence")
        if not isinstance(c, (int, float)) or not (0.0 <= float(c) <= 1.0):
            raise ReviewOutputError(f"{where}.confidence: required number in [0.0, 1.0]")
    return findings


def normalize(findings: list[dict]) -> list[EvidenceRow]:
    rows: list[EvidenceRow] = []
    for f in findings:
        rows.append(
            EvidenceRow(
                rule_id=f"policy-review/{f['axis']}",
                file=f["file"],
                line=int(f["line"]),
                standard=f["axis"],
                confidence=float(f["confidence"]),
                evidence=f["evidence"],
                message=f["message"],
            )
        )
    return rows


def _read_change(changed: list[Path], diff: Path | None) -> str:
    parts: list[str] = []
    for p in changed:
        try:
            body = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        parts.append(f"### {p}\n\n```\n{body}\n```")
    if diff is not None:
        parts.append("### diff\n\n```\n" + diff.read_text(encoding="utf-8") + "\n```")
    return "\n\n".join(parts)


def _cmd_prompt(args) -> int:
    if not args.review.is_file():
        print(f"policy-review: review not found: {args.review}", file=sys.stderr)
        return 2
    change_text = _read_change(list(args.changed), args.diff)
    if not change_text.strip():
        print("policy-review: no change given (pass --changed or --diff)", file=sys.stderr)
        return 2
    prompt = assemble_prompt(args.review.read_text(encoding="utf-8"), change_text)
    if args.out is not None:
        args.out.write_text(prompt, encoding="utf-8")
        print(f"policy-review: wrote prompt to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(prompt)
    return 0


def _cmd_ingest(args) -> int:
    if not args.output.is_file():
        print(f"policy-review: model output not found: {args.output}", file=sys.stderr)
        return 2
    try:
        obj = json.loads(args.output.read_text(encoding="utf-8"))
        findings = validate_finding_set(obj)
    except (json.JSONDecodeError, ReviewOutputError) as e:
        print(f"policy-review: invalid model output: {e}", file=sys.stderr)
        return 1
    rows = normalize(findings)
    text = rows_to_json(rows)
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
        print(f"policy-review: wrote {len(rows)} rows to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="policy-review harness: assemble the prompt, ingest the output.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prompt", help="assemble the review prompt for a model")
    p.add_argument("--review", type=Path, required=True, help="compiled REVIEW.md")
    p.add_argument("--changed", nargs="*", type=Path, default=[], help="changed files to embed")
    p.add_argument("--diff", type=Path, default=None, help="a diff file to embed")
    p.add_argument("--out", type=Path, default=None, help="write prompt here (default: stdout)")
    p.set_defaults(func=_cmd_prompt)

    g = sub.add_parser("ingest", help="validate model output and normalize to evidence rows")
    g.add_argument("output", type=Path, help="the model's finding-set JSON")
    g.add_argument("--out", type=Path, default=None, help="write evidence rows here (default: stdout)")
    g.set_defaults(func=_cmd_ingest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
