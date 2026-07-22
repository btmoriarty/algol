# Composition: routing axes out

Algol routes two axes to existing disciplines rather than rebuilding them, per
compose before build. Both are consumed the same way as gauntlet: a thin
translator turns the real tool's output into a documented result shape, and an
adapter folds it into the record.

Tool: `skills/algol/tools/compose_adapter.py`. reconcile ingests both via
`--uat` and `--rigor`.

## Testing -> evidence-locked-uat

A blinded verifier whose deterministic judge never rounds INCONCLUSIVE up to
PASS. The adapter honors that:

- FAIL findings enter as verified, because the judge is deterministic.
- INCONCLUSIVE findings are clamped to hypothesis regardless of any over-claimed
  tier in the input, and an inconclusive verdict with no findings still surfaces
  one that says "not a pass". Inconclusive never reads as verified or pass.
- PASS with no findings produces nothing to disposition.

## Efficiency -> applying-formal-rigor

Lens 4 derives a Big-O bound from named theory rather than guessing it. A derived
claim is reasoned, not mechanically verified, so it enters as inference by
default. brevlint still owns style and brevity; only the hard complexity claims
route here.

## The result shape

```
{"axis": "testing" | "efficiency",
 "verdict": "...",
 "findings": [{"file", "line", "claim", "evidence", "message", "confidence", "tier"?}]}
```

## Usage

```
python skills/algol/tools/reconcile.py \
    --collector rows.json --uat uat-result.json --rigor rigor-result.json \
    --out .algol/record.json
```

## Why route out

evidence-locked-uat and applying-formal-rigor already ship the discipline, the
blinded verifier, and the derivation. Algol keeps only what they lack: versioned
policy, cross-source reconcile, and a governed record. Rebuilding them would be
reinvention, and worse, a second-rate copy that drifts.
