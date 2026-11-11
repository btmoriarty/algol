#!/usr/bin/env python3
"""reconcile: merge findings from every source into one record.

reconcile takes the deterministic rows from the collectors and, optionally, a
gauntlet run record, and folds them into a single Record. It is the mechanism
the whole tool is built to protect:

  - It keeps every source's observation, with that source's verification tier.
  - It never silently upgrades a heuristic to verified. A collector row enters
    as "heuristic" and stays "heuristic". A finding is "verified" only when a
    deterministic verifier (an evidence-locked-uat FAIL) says so; a gauntlet
    [V] anchor reaches "model_corroborated", never "verified".
  - Re-running against an existing record preserves the human dispositions and
    their reopens-if conditions, so the record persists across a repo's history.

Correlation: observations sharing (file, line, claim) are one finding; a
collector's claim is its rule_id. Distinct claims on the same line stay
distinct, rather than being over-merged.

Line moves: when an observation's (file, line, claim) matches nothing in the
base record, reconcile looks for a base finding with the same file and claim,
not matched in place in this run, that carries an observation with identical
non-empty evidence text. If one exists, the finding is re-anchored to the new
line (nearest old line wins a tie) and keeps its id, observations, and
disposition. Edited code is a new finding: changed evidence does not re-anchor.

Floor: Python 3.11+, stdlib only (record.py is a sibling module).

Usage:
  python reconcile.py --collector rows.json [--collector more.json] \
      [--gauntlet run-record.json] [--base record.json] --out record.json

The first run writes a new record. Every later run passes the existing record
as --base, so its dispositions carry forward. reconcile refuses to replace an
existing --out without --base, because that would erase every disposition in
it; pass --overwrite to replace it on purpose.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import (  # noqa: E402
    Finding,
    Observation,
    Record,
    dispositions_without_reopens,
    location_id,
)
from gauntlet_adapter import parse_run_record  # noqa: E402
from compose_adapter import parse_uat, parse_rigor  # noqa: E402

Key = tuple  # (file, line, claim)


def _collector_observations(rows: list[dict]) -> list[tuple[Key, Observation]]:
    out: list[tuple[Key, Observation]] = []
    for r in rows:
        rule_id = r["rule_id"]
        source = rule_id.split("/", 1)[0]
        key = (r["file"], int(r["line"]), rule_id)
        obs = Observation(
            source=source,
            tier="heuristic",  # a deterministic rule firing is a signal, not a proven defect
            confidence=float(r.get("confidence", 1.0)),
            evidence=r.get("evidence", ""),
            message=r.get("message", ""),
        )
        out.append((key, obs))
    return out


def _gauntlet_observations(run: dict) -> tuple[list[tuple[Key, Observation]], dict]:
    """Parse a gauntlet run record via the adapter (the single gauntlet parser)."""
    result = parse_run_record(run)
    return result.observations(), result.deep_tier()


def _same_observation(a: Observation, b: Observation) -> bool:
    return (a.source, a.tier, a.message, a.evidence) == (b.source, b.tier, b.message, b.evidence)


def _reanchor(findings: dict[Key, Finding], incoming: list[tuple[Key, Observation]]) -> None:
    """Move base findings whose code moved to their new line, in place.

    A base finding is a candidate when no incoming observation hits its exact
    key, or when the only observations that hit it carry different evidence
    (new code landed on its old line). An incoming key with no exact match
    takes the candidate with the same file and claim whose observations share a
    non-empty evidence string with it, nearest old line first. Each candidate
    moves at most once; one that does not move stays where it was."""
    hits: dict[Key, list[Observation]] = {}
    evidence: dict[Key, set[str]] = {}
    for key, obs in incoming:
        if key in findings:
            hits.setdefault(key, []).append(obs)
        elif obs.evidence:
            evidence.setdefault(key, set()).add(obs.evidence)

    def displaced(bk: Key) -> bool:
        old = {o.evidence for o in findings[bk].observations}
        return all(o.evidence and o.evidence not in old for o in hits[bk])

    candidates = {bk for bk in findings if bk not in hits or displaced(bk)}
    for key in sorted(evidence):
        pool = [
            bk for bk in candidates
            if bk[0] == key[0] and bk[2] == key[2]
            and any(o.evidence in evidence[key] for o in findings[bk].observations)
        ]
        if not pool:
            continue
        bk = min(pool, key=lambda b: (abs(b[1] - key[1]), b[1]))
        candidates.discard(bk)
        moved = findings.pop(bk)
        moved.line = key[1]
        findings[key] = moved


def reconcile(
    observation_sets: list[list[tuple[Key, Observation]]],
    base: Record | None = None,
    deep_tier: dict | None = None,
) -> Record:
    findings: dict[Key, Finding] = {}
    if base is not None:
        for f in base.findings:
            findings[(f.file, f.line, f.claim)] = Finding(
                file=f.file,
                line=f.line,
                claim=f.claim,
                observations=list(f.observations),
                disposition=f.disposition,  # preserve the human decision
                stable_id=f.id,             # identity survives a line move
            )

    incoming = [(key, obs) for obs_set in observation_sets for key, obs in obs_set]
    _reanchor(findings, incoming)

    used_ids = {f.id for f in findings.values()}
    for key, obs in incoming:
        f = findings.get(key)
        if f is None:
            salt = 0
            while location_id(*key, salt=salt) in used_ids:
                salt += 1
            f = Finding(file=key[0], line=key[1], claim=key[2], observations=[],
                        stable_id=location_id(*key, salt=salt))
            used_ids.add(f.id)
            findings[key] = f
        if not any(_same_observation(obs, existing) for existing in f.observations):
            f.observations.append(obs)

    record = Record(findings=list(findings.values()), deep_tier=deep_tier or (base.deep_tier if base else None))
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="reconcile findings into one record.")
    parser.add_argument("--collector", action="append", type=Path, default=[], help="a collector rows JSON file")
    parser.add_argument("--gauntlet", type=Path, default=None, help="a gauntlet run-record JSON file")
    parser.add_argument("--uat", type=Path, default=None, help="an evidence-locked-uat result JSON file")
    parser.add_argument("--rigor", type=Path, default=None, help="an applying-formal-rigor result JSON file")
    parser.add_argument("--base", type=Path, default=None, help="an existing record.json to merge into")
    parser.add_argument("--out", type=Path, required=True, help="where to write the reconciled record")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing --out without merging it (erases its dispositions)")
    args = parser.parse_args(argv)

    if args.base is None and args.out.exists() and not args.overwrite:
        print(
            f"reconcile: {args.out} already exists; pass --base {args.out} to merge into it "
            "and keep its dispositions, or --overwrite to replace it",
            file=sys.stderr,
        )
        return 2

    observation_sets: list[list[tuple[Key, Observation]]] = []
    for cpath in args.collector:
        if not cpath.is_file():
            print(f"reconcile: collector rows not found: {cpath}", file=sys.stderr)
            return 2
        rows = json.loads(cpath.read_text(encoding="utf-8"))
        observation_sets.append(_collector_observations(rows))

    deep = None
    if args.gauntlet is not None:
        if not args.gauntlet.is_file():
            print(f"reconcile: gauntlet record not found: {args.gauntlet}", file=sys.stderr)
            return 2
        run = json.loads(args.gauntlet.read_text(encoding="utf-8"))
        gobs, deep = _gauntlet_observations(run)
        observation_sets.append(gobs)

    for flag, parse in (("uat", parse_uat), ("rigor", parse_rigor)):
        path = getattr(args, flag)
        if path is not None:
            if not path.is_file():
                print(f"reconcile: {flag} result not found: {path}", file=sys.stderr)
                return 2
            observation_sets.append(parse(json.loads(path.read_text(encoding="utf-8"))))

    base = None
    if args.base is not None:
        if not args.base.is_file():
            print(f"reconcile: base record not found: {args.base}", file=sys.stderr)
            return 2
        base = Record.from_json(args.base.read_text(encoding="utf-8"))

    if not observation_sets and base is None:
        print("reconcile: nothing to reconcile (pass --collector, --gauntlet, or --base)", file=sys.stderr)
        return 2

    record = reconcile(observation_sets, base=base, deep_tier=deep)
    args.out.write_text(record.to_json(), encoding="utf-8")

    open_verdicts = dispositions_without_reopens(record)
    print(f"reconcile: wrote {len(record.findings)} findings to {args.out}", file=sys.stderr)
    if open_verdicts:
        print(
            f"reconcile: warning: {len(open_verdicts)} disposition(s) have no reopens-if condition",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
