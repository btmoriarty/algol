#!/usr/bin/env python3
"""The governed record: one place where findings and human decisions persist.

reconcile writes findings here; a human attaches a disposition to each. The
record lives on disk as a plain file under version control, so what a project
decided and why is a diffable part of its history.

Two invariants define the model:

  1. Provenance is never lost. A finding keeps every observation that produced
     it, each with its source and its verification tier. Merging observations
     never relabels one; a heuristic stays heuristic.
  2. A disposition is not permanent. Each accept, suppress, or defer records the
     one to three conditions that would reopen it (reopens-if). A decision with
     no reopens-if is allowed but flagged, because a permanent verdict is the
     thing this model exists to prevent.

Floor: Python 3.11+, stdlib only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict

# Verification tiers, lowest to highest. A tier comes from a source, never from
# merging. "verified" means a deterministic verifier directly established the
# claimed condition and kept the evidence to reproduce it (an evidence-locked-uat
# FAIL is the reference). "model_corroborated" means a model panel independently
# supported the finding but did not deterministically establish it (a gauntlet [V]
# anchor). "heuristic" is a deterministic collector rule firing, a signal, not a
# proven defect.
TIERS = ("hypothesis", "heuristic", "inference", "model_corroborated", "verified")
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

DISPOSITION_STATES = ("accept", "suppress", "defer")


@dataclass(frozen=True)
class Observation:
    source: str          # e.g. "brevlint", "gauntlet"
    tier: str            # one of TIERS
    confidence: float    # 0.0 to 1.0
    evidence: str
    message: str = ""

    def __post_init__(self) -> None:
        if self.tier not in TIER_RANK:
            raise ValueError(f"unknown tier: {self.tier}")


@dataclass
class Disposition:
    state: str                       # one of DISPOSITION_STATES
    rationale: str
    reopens_if: list[str] = field(default_factory=list)
    by: str = ""

    def __post_init__(self) -> None:
        if self.state not in DISPOSITION_STATES:
            raise ValueError(f"unknown disposition state: {self.state}")


@dataclass
class Finding:
    file: str
    line: int
    claim: str
    observations: list[Observation] = field(default_factory=list)
    disposition: Disposition | None = None

    @property
    def id(self) -> str:
        key = f"{self.file}:{self.line}:{self.claim}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

    @property
    def status(self) -> str:
        """Highest tier among observations. Honest because tiers come from
        sources, not from merging. 'verified' appears only when a deterministic
        verifier is present; 'model_corroborated' when a model panel is the
        strongest source. Neither is synthesized by merging."""
        if not self.observations:
            return "hypothesis"
        return max((o.tier for o in self.observations), key=lambda t: TIER_RANK[t])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file": self.file,
            "line": self.line,
            "claim": self.claim,
            "status": self.status,
            "observations": [asdict(o) for o in sorted(self.observations, key=_obs_key)],
            "disposition": asdict(self.disposition) if self.disposition else None,
        }


def _obs_key(o: Observation) -> tuple:
    return (o.source, o.tier, o.message, o.evidence)


@dataclass
class Record:
    findings: list[Finding] = field(default_factory=list)
    deep_tier: dict | None = None   # a gauntlet verdict + conditions, if any

    def by_id(self) -> dict[str, Finding]:
        return {f.id: f for f in self.findings}

    def to_json(self) -> str:
        obj = {
            "algol_record": 1,
            "findings": [f.to_dict() for f in sorted(self.findings, key=lambda f: f.id)],
            "deep_tier": self.deep_tier,
        }
        return json.dumps(obj, indent=2, sort_keys=True) + "\n"

    @staticmethod
    def from_json(text: str) -> "Record":
        obj = json.loads(text)
        findings: list[Finding] = []
        for f in obj.get("findings", []):
            obs = [
                Observation(
                    source=o["source"],
                    tier=o["tier"],
                    confidence=o.get("confidence", 1.0),
                    evidence=o.get("evidence", ""),
                    message=o.get("message", ""),
                )
                for o in f.get("observations", [])
            ]
            disp = None
            d = f.get("disposition")
            if d:
                disp = Disposition(
                    state=d["state"],
                    rationale=d.get("rationale", ""),
                    reopens_if=list(d.get("reopens_if", [])),
                    by=d.get("by", ""),
                )
            findings.append(
                Finding(file=f["file"], line=f["line"], claim=f["claim"], observations=obs, disposition=disp)
            )
        return Record(findings=findings, deep_tier=obj.get("deep_tier"))


def set_disposition(
    record: Record,
    finding_id: str,
    state: str,
    rationale: str,
    reopens_if: list[str] | None = None,
    by: str = "",
) -> Disposition:
    """Attach a disposition to a finding. Returns it. Raises if the id is unknown."""
    finding = record.by_id().get(finding_id)
    if finding is None:
        raise KeyError(f"no finding with id {finding_id}")
    disp = Disposition(state=state, rationale=rationale, reopens_if=list(reopens_if or []), by=by)
    finding.disposition = disp
    return disp


def dispositions_without_reopens(record: Record) -> list[str]:
    """Finding ids whose disposition has no reopens-if condition. A permanent
    verdict by default is exactly what the model warns about."""
    return [
        f.id
        for f in record.findings
        if f.disposition is not None and not f.disposition.reopens_if
    ]


def append_event(path, event: dict) -> None:
    """Append one JSON line to the record event log. The log is temporal by
    design, so a caller may include a timestamp; the record file itself stays
    timestamp-free and diffable."""
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")
