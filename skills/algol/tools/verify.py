#!/usr/bin/env python3
"""verify: raise one finding's tier through the verifying engine, in two steps.

Algol's honesty about heuristic-vs-verified only matters if `verified` is
reachable. It is, but only through a deterministic verifier: an evidence-locked-uat
FAIL reaches `verified`; the gauntlet corroborates and reaches `model_corroborated`.
This harness makes that a targeted, one-finding loop, the same shape as
policy-review:

  1. prompt: given a finding id, assemble the exact request to hand the verifier,
     pre-keyed to that finding so its answer correlates back.
  2. ingest: fold the verifier's output into the record and report the tier
     change for that finding. It never invents a tier: the adapters cap each
     source (uat FAIL -> verified, gauntlet [V] -> model_corroborated), and if
     the verifier did not address the finding, its tier does not move.

The floor holds: Algol assembles and folds; a human runs the engine.

Floor: Python 3.11+, stdlib only (siblings: record, reconcile, compose_adapter,
gauntlet_adapter).

Usage:
  python verify.py prompt --finding <id>                 # assemble the request
  python verify.py ingest out.json --finding <id>        # fold it in, report the raise
  python verify.py prompt --finding <id> --engine gauntlet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reconcile as rc  # noqa: E402
import compose_adapter as ca  # noqa: E402
import gauntlet_adapter as ga  # noqa: E402
from record import Record, TIER_RANK  # noqa: E402

ENGINES = ("uat", "gauntlet")


class VerifyError(Exception):
    """Bad input to verify, raised with a named reason so it fails closed."""


def _load_record(path: Path) -> Record:
    if not path.is_file():
        raise VerifyError(f"record not found: {path}")
    return Record.from_json(path.read_text(encoding="utf-8"))


def _find(record: Record, fid: str):
    f = record.by_id().get(fid)
    if f is None:
        raise VerifyError(f"no finding with id {fid} in the record")
    return f


def build_prompt(record: Record, fid: str, engine: str) -> str:
    f = _find(record, fid)
    ev = "; ".join(f"{o.source}:{o.message or o.evidence}" for o in f.observations) or "(none)"
    lines: list[str] = []
    if engine == "uat":
        lines += [
            "You are the deterministic verifier (evidence-locked-uat).",
            "Establish the claim below by reproduction and keep the evidence.",
            "FAIL means you reproduced the defect (it becomes verified).",
            "INCONCLUSIVE if you could not reproduce it; never round that up to PASS.",
        ]
        schema = {
            "axis": "testing",
            "verdict": "FAIL | PASS | INCONCLUSIVE",
            "findings": [{"file": f.file, "line": f.line, "claim": f.claim,
                          "evidence": "<verbatim reproduction, required for FAIL>",
                          "message": "<what you established>", "confidence": 1.0}],
        }
    else:  # gauntlet
        lines += [
            "You are the deep tier (gauntlet). Corroborate or refute the claim below.",
            "A corroborated finding carries a [V ...] evidence anchor and reaches",
            "model_corroborated (a panel corroborates; it does not deterministically verify).",
        ]
        schema = {
            "verdict": "GO | CONDITIONAL | NO-GO",
            "findings": [{"file": f.file, "line": f.line, "claim": f.claim,
                          "evidence": f"[V {f.file}:{f.line}] <why>",
                          "message": "<verdict rationale>"}],
            "conditions": ["<reopens-if condition>"],
        }
    lines += [
        "",
        f"Finding to verify (id {fid}, currently {f.status}):",
        f"  {f.file}:{f.line}  {f.claim}",
        f"  evidence so far: {ev}",
        "",
        "Return ONLY this JSON object, keyed to the finding above so it correlates:",
        json.dumps(schema, indent=2),
    ]
    return "\n".join(lines) + "\n"


def apply_result(base: Record, fid: str, engine: str, output: dict) -> tuple[Record, str, str, bool]:
    """Fold a verifier's output into base, targeting fid. Returns
    (record, before_tier, after_tier, addressed) where addressed is whether the
    output carried an observation at the finding's own (file, line, claim)."""
    if not isinstance(output, dict):
        raise VerifyError("verifier output is not a JSON object")
    target = _find(base, fid)
    before = target.status
    key = (target.file, target.line, target.claim)

    deep = None
    if engine == "uat":
        obs = ca.parse_uat(output)
    elif engine == "gauntlet":
        result = ga.parse_run_record(output)
        obs = result.observations()
        deep = result.deep_tier()
    else:
        raise VerifyError(f"unknown engine: {engine}")

    addressed = any(k == key for k, _ in obs)
    record = rc.reconcile([obs], base=base, deep_tier=deep)
    after = record.by_id()[fid].status
    return record, before, after, addressed


def _cmd_prompt(args) -> int:
    record = _load_record(args.record)
    text = build_prompt(record, args.finding, args.engine)
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
        print(f"verify: wrote prompt to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def _cmd_ingest(args) -> int:
    base = _load_record(args.record)
    try:
        output = json.loads(args.output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"verify: cannot read verifier output: {exc}", file=sys.stderr)
        return 2
    record, before, after, addressed = apply_result(base, args.finding, args.engine, output)

    out = args.out if args.out is not None else args.record
    if not args.dry_run:
        out.write_text(record.to_json(), encoding="utf-8")

    if not addressed:
        print(f"verify: the verifier output did not address {args.finding} "
              f"(no finding at its file:line:claim); tier unchanged ({after})", file=sys.stderr)
    elif TIER_RANK[after] > TIER_RANK[before]:
        note = " (verified)" if after == "verified" else ""
        print(f"verify: {args.finding} raised {before} -> {after}{note}", file=sys.stderr)
    else:
        print(f"verify: {args.finding} unchanged ({after}); the verifier did not establish a higher tier",
              file=sys.stderr)
    print(f"verify: {'wrote' if not args.dry_run else 'would write'} record to {out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="raise a finding's tier via the verifying engine.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prompt", help="assemble the verification request for a finding")
    p.add_argument("--record", type=Path, default=Path(".algol/record.json"))
    p.add_argument("--finding", required=True, help="finding id to verify")
    p.add_argument("--engine", choices=ENGINES, default="uat")
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(func=_cmd_prompt)

    g = sub.add_parser("ingest", help="fold the verifier's output in and report the tier change")
    g.add_argument("output", type=Path, help="the verifier's output JSON")
    g.add_argument("--record", type=Path, default=Path(".algol/record.json"))
    g.add_argument("--finding", required=True, help="finding id being verified")
    g.add_argument("--engine", choices=ENGINES, default="uat")
    g.add_argument("--out", type=Path, default=None)
    g.add_argument("--dry-run", action="store_true")
    g.set_defaults(func=_cmd_ingest)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except VerifyError as exc:
        print(f"verify: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
