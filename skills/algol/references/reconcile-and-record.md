# Reconcile and the governed record

The record is the point of Algol. reconcile fills it; a human dispositions it;
it persists on disk under version control, so what a project decided and why is
part of its history.

Tools: `skills/algol/tools/record.py` (the model) and
`skills/algol/tools/reconcile.py` (the merge).

## The model (record.py)

A Record holds Findings. A Finding is a claim at a location, carrying every
Observation that produced it and, once a human decides, a Disposition.

- Observation: source, verification tier, confidence, evidence, message. A tier
  is one of hypothesis, heuristic, inference, verified, ordered low to high.
- Finding.status is the highest tier among its observations. This is honest
  because a tier comes from a source, never from merging: a finding is
  "verified" only when a source that verified it says so.
- Disposition: state (accept, suppress, defer), rationale, and reopens-if, the
  one to three conditions that would reopen the decision (A14). A disposition
  with no reopens-if is allowed but flagged by `dispositions_without_reopens`,
  because a permanent verdict by default is what the model exists to prevent.

The record serializes deterministically: findings sorted by id, sorted keys, no
wall-clock timestamp, so it diffs cleanly. An `append_event` helper writes a
separate JSONL event log, which is temporal by design and kept apart from the
diffable record.

## The merge (reconcile.py)

reconcile takes the collectors' rows and, optionally, a gauntlet run record, and
folds them into one Record.

- Correlation is exact: observations sharing (file, line, claim) are one
  finding. A collector's claim is its rule_id. Distinct claims on the same line
  stay distinct rather than being over-merged.
- It never silently upgrades. A collector row enters as heuristic and stays
  heuristic. A gauntlet finding enters at the tier the source states; a missing
  tier defaults to heuristic, never to verified. The invariant is the point of
  the tool.
- Re-running against an existing record (`--base`) preserves the human
  dispositions and their reopens-if conditions, and de-duplicates identical
  observations, so the record persists across the repo's history instead of
  being rebuilt each run.
- A gauntlet run's verdict and conditions attach to the record under
  `deep_tier`; the conditions are the natural seed for a finding's reopens-if.

## Usage

```
python skills/algol/tools/reconcile.py \
    --collector rows-brevlint.json --collector rows-seclint.json \
    --gauntlet run-record.json --base .algol/record.json \
    --out .algol/record.json
```

## The spine

With this in place the local path runs end to end: the policy compiles, a
collector emits evidence against it, the router recommends an engine, and
reconcile folds the results into one governed record. seclint, policy-review,
and the gauntlet adapter extend the same spine.
