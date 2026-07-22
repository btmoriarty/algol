#!/usr/bin/env python3
"""reconcile: merge findings from every source into one record.

reconcile takes the deterministic rows from the collectors and, optionally, a
gauntlet run record, and folds them into a single Record. It is the mechanism
the whole tool is built to protect:

  - It keeps every source's observation, with that source's verification tier.
  - It never silently upgrades a heuristic to verified. A collector row enters
    as "heuristic" and stays "heuristic"; a finding is only "verified" when a
    source that verified it (a gauntlet [V] anchor) says so.
  - Re-running against an existing record preserves the human dispositions and
    their reopens-if conditions, so the record persists across a repo's history.

Correlation is exact: observations sharing (file, line, claim) are one finding;
a collector's claim is its rule_id. Distinct claims on the same line stay
distinct, rather than being over-merged.

Floor: Python 3.11+, stdlib only (record.py is a sibling module).

Usage:
  python reconcile.py --collector rows.json [--collector more.json] \
      [--gauntlet run-record.json] [--base record.json] --out record.json
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
    TIER_RANK,
    dispositions_without_reopens,
)

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
    obs: list[tuple[Key, Observation]] = []
    for f in run.get("findings", []):
        tier = f.get("tier", "heuristic")  # trust the source; default conservative, never invent "verified"
        if tier not in TIER_RANK:
            tier = "heuristic"
        key = (f["file"], int(f["line"]), f.get("claim", ""))
        obs.append(
            (
                key,
                Observation(
                    source="gauntlet",
                    tier=tier,
                    confidence=float(f.get("confidence", 1.0)),
                    evidence=f.get("evidence", ""),
                    message=f.get("message", ""),
                ),
            )
        )
    deep = {
        "source": "gauntlet",
        "verdict": run.get("verdict", ""),
        "conditions": list(run.get("conditions", [])),
    }
    return obs, deep


def _same_observation(a: Observation, b: Observation) -> bool:
    return (a.source, a.tier, a.message, a.evidence) == (b.source, b.tier, b.message, b.evidence)


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
            )

    for obs_set in observation_sets:
        for key, obs in obs_set:
            f = findings.get(key)
            if f is None:
                f = Finding(file=key[0], line=key[1], claim=key[2], observations=[])
                findings[key] = f
            if not any(_same_observation(obs, existing) for existing in f.observations):
                f.observations.append(obs)

    record = Record(findings=list(findings.values()), deep_tier=deep_tier or (base.deep_tier if base else None))
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="reconcile findings into one record.")
    parser.add_argument("--collector", action="append", type=Path, default=[], help="a collector rows JSON file")
    parser.add_argument("--gauntlet", type=Path, default=None, help="a gauntlet run-record JSON file")
    parser.add_argument("--base", type=Path, default=None, help="an existing record.json to merge into")
    parser.add_argument("--out", type=Path, required=True, help="where to write the reconciled record")
    args = parser.parse_args(argv)

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
