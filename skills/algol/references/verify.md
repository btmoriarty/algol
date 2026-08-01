# Raising a finding to verified

Algol keeps `verified` distinct from `heuristic` on purpose, and never upgrades
one silently. The flip side of that honesty is that `verified` has to be
reachable, through the one thing that earns it: a deterministic verifier.
`tools/verify.py` makes that a targeted, one-finding loop, the same two-step
shape as policy-review.

Only two tiers are reachable here, by source:

- **evidence-locked-uat**, a deterministic verifier: a FAIL (a reproduced defect,
  with the reproduction kept as evidence) reaches `verified`. INCONCLUSIVE is
  never rounded up.
- **gauntlet**, the deep tier: a corroborated finding (a `[V ...]` anchor) reaches
  `model_corroborated`. A panel corroborates; it does not deterministically
  verify, so it stops one rung below verified.

## The two steps

1. **prompt**: assemble the request for a specific finding, pre-keyed to it so the
   verifier's answer correlates back.

   ```
   python skills/algol/tools/verify.py prompt --finding <id>            # uat (default)
   python skills/algol/tools/verify.py prompt --finding <id> --engine gauntlet
   ```

   The output states the discipline, the finding (`file:line`, claim, current
   tier, evidence so far), and the exact JSON schema to return, with the
   finding's own `file`/`line`/`claim` filled in.

2. **ingest**: fold the verifier's output into the record and report the tier
   change for that finding.

   ```
   python skills/algol/tools/verify.py ingest out.json --finding <id> [--engine ...] [--dry-run]
   ```

   It reads the record (`.algol/record.json` by default), parses the output
   through the right adapter (which caps the tier: uat FAIL to verified, gauntlet
   to model_corroborated, and never invents one), reconciles it in as a `--base`
   merge, and prints one of:

   - `<id> raised heuristic -> verified` (a real raise),
   - `<id> unchanged (<tier>)` (the verifier did not establish a higher tier), or
   - a warning that the output did not address the finding (no observation at its
     `file:line:claim`), so nothing moved.

## Why targeted

reconcile already ingests uat and gauntlet results wholesale. verify adds the
loop around one finding: it assembles the exact request, checks the answer
correlates to that finding, and reports the tier delta, so "raise this to
verified" is one command in and one command out. The floor holds: Algol
assembles and folds; a human runs the engine.
