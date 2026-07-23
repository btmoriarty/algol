#!/usr/bin/env python3
"""compose adapters: consume composed-discipline results into the record.

Algol routes two axes out rather than rebuilding them:

  testing     -> evidence-locked-uat, a blinded verifier whose deterministic judge
                 never rounds INCONCLUSIVE up to PASS
  efficiency  -> applying-formal-rigor, whose lens 4 derives a Big-O bound rather
                 than guessing it

Like the gauntlet adapter, these parse a documented minimal result shape into
observations reconcile folds into the record. A thin translator from each real
tool's output feeds this shape; Algol does not reimplement the disciplines.

The result shape (both):
  {"axis": "testing"|"efficiency",
   "verdict": "...",                      # optional, discipline-specific
   "findings": [{"file","line","claim","evidence","message","confidence","tier"?}]}

Floor: Python 3.11+, stdlib only (record.py is a sibling module).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import Observation, TIER_RANK  # noqa: E402

Key = tuple  # (file, line, claim)


def _key(f: dict) -> Key:
    return (f.get("file", ""), int(f.get("line", 0)), f.get("claim", ""))


def _obs(source: str, tier: str, f: dict) -> Observation:
    return Observation(
        source=source,
        tier=tier,
        confidence=float(f.get("confidence", 1.0)),
        evidence=f.get("evidence", ""),
        message=f.get("message", ""),
    )


def parse_uat(result: dict) -> list[tuple[Key, Observation]]:
    """evidence-locked-uat. FAIL is verified (a deterministic judge). INCONCLUSIVE
    is never rounded up: its findings are clamped to hypothesis regardless of any
    over-claimed tier, and an inconclusive verdict with no findings still surfaces
    one. PASS with no findings produces nothing to disposition."""
    verdict = str(result.get("verdict", "")).upper()
    findings = result.get("findings", [])
    obs: list[tuple[Key, Observation]] = []

    for f in findings:
        tier = f.get("tier")
        if tier not in TIER_RANK:
            tier = {"FAIL": "verified", "INCONCLUSIVE": "hypothesis"}.get(verdict, "heuristic")
        if verdict == "INCONCLUSIVE":
            tier = "hypothesis"  # never let inconclusive read as verified or pass
        obs.append((_key(f), _obs("evidence-locked-uat", tier, f)))

    if verdict == "INCONCLUSIVE" and not findings:
        synthetic = {"file": "", "line": 0, "claim": "evidence-locked-uat/inconclusive",
                     "evidence": "", "message": "verifier inconclusive; not a pass", "confidence": 1.0}
        obs.append((_key(synthetic), _obs("evidence-locked-uat", "hypothesis", synthetic)))
    return obs


def parse_rigor(result: dict) -> list[tuple[Key, Observation]]:
    """applying-formal-rigor. A derived complexity claim is reasoned from named
    theory, so it enters as inference by default, not verified."""
    obs: list[tuple[Key, Observation]] = []
    for f in result.get("findings", []):
        tier = f.get("tier")
        if tier not in TIER_RANK:
            tier = "inference"
        # rigor derives from theory; it never deterministically verifies. Cap at inference.
        if TIER_RANK[tier] > TIER_RANK["inference"]:
            tier = "inference"
        obs.append((_key(f), _obs("applying-formal-rigor", tier, f)))
    return obs
