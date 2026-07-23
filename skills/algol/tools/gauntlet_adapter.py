#!/usr/bin/env python3
"""gauntlet adapter: consume a gauntlet run record into the Algol record.

The deep tier routes fully to gauntlet. Algol builds no panel and no arbitrator;
it consumes gauntlet's output. This adapter is the single place that parses a
gauntlet run record, maps its evidence tiers onto Algol's, and hands reconcile
observations plus a deep-tier block. reconcile imports it, so the contract lives
in one file.

What Algol reads from a run record (a subset of the full gauntlet-run-record):

  verdict     GO / CONDITIONAL / NO-GO, or SKIPPED when gauntlet's own triage
              declined to run (the run-or-skip call is gauntlet's, not Algol's)
  findings    each with file, line, claim, and either an explicit tier or a
              [V]/[I]/[H] evidence tag. [V] is a gauntlet-local anchor label; it
              maps to Algol's model_corroborated (a model panel corroborates, it
              does not deterministically verify), [I] inference, [H] hypothesis. A
              missing tier defaults to heuristic. gauntlet never reaches "verified":
              an explicit "verified" clamps to model_corroborated.
  conditions  the "reopens if" conditions gauntlet recorded; these seed the
              record's reopens-if (A14)

Floor: Python 3.11+, stdlib only (record.py is a sibling module).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import Observation, TIER_RANK  # noqa: E402

Key = tuple  # (file, line, claim)

# gauntlet evidence tags to Algol tiers.
TAG_TO_TIER = {"[V": "model_corroborated", "[I": "inference", "[H": "hypothesis"}


def _tier_of(finding: dict) -> str:
    explicit = finding.get("tier")
    if isinstance(explicit, str) and explicit in TIER_RANK:
        tier = explicit
    else:
        tier = "heuristic"  # never invent a stronger tier from a source that did not state it
        ev = finding.get("evidence", "")
        if isinstance(ev, str):
            for tag, mapped in TAG_TO_TIER.items():
                if ev.lstrip().startswith(tag):
                    tier = mapped
                    break
    # gauntlet is a model panel: it corroborates, it never deterministically verifies.
    if tier == "verified":
        tier = "model_corroborated"
    return tier


@dataclass
class GauntletResult:
    verdict: str
    conditions: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    _observations: list[tuple[Key, Observation]] = field(default_factory=list)

    def observations(self) -> list[tuple[Key, Observation]]:
        return list(self._observations)

    def deep_tier(self) -> dict:
        block = {
            "source": "gauntlet",
            "verdict": self.verdict,
            "conditions": list(self.conditions),
            "reopens_if_seeds": list(self.conditions),
        }
        if self.skipped:
            block["skipped"] = True
            block["skip_reason"] = self.skip_reason
        return block


def parse_run_record(run: dict) -> GauntletResult:
    verdict = str(run.get("verdict", ""))
    # gauntlet's own triage may skip; that call is gauntlet's, and Algol records it.
    skipped = bool(run.get("skipped")) or verdict.upper() == "SKIPPED"
    skip_reason = str(run.get("skip_reason", "")) if skipped else ""

    observations: list[tuple[Key, Observation]] = []
    if not skipped:
        for f in run.get("findings", []):
            key = (f["file"], int(f["line"]), f.get("claim", ""))
            observations.append(
                (
                    key,
                    Observation(
                        source="gauntlet",
                        tier=_tier_of(f),
                        confidence=float(f.get("confidence", 1.0)),
                        evidence=f.get("evidence", ""),
                        message=f.get("message", ""),
                    ),
                )
            )
    return GauntletResult(
        verdict=verdict,
        conditions=list(run.get("conditions", [])),
        skipped=skipped,
        skip_reason=skip_reason,
        _observations=observations,
    )
