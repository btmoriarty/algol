# Deep tier

The deep tier routes fully to gauntlet. Algol builds no panel and no arbitrator;
it consumes gauntlet's output. gauntlet already ships a computed verdict you
cannot hand-set, tiered evidence, a dissent-preserving Conflict Ledger, and a
blind-certified arbitrator. Reinventing that would cut against compose before
build. gauntlet is GPL-3.0, so Algol consumes its run record and does not import
its code.

Tool: `skills/algol/tools/gauntlet_adapter.py`. It is the single place that parses
a gauntlet run record; reconcile imports it, so the contract lives in one file.

## What Algol reads

A subset of the gauntlet run record:

- verdict: GO, CONDITIONAL, NO-GO, or SKIPPED when gauntlet's own triage declined
  to run.
- findings: each with file, line, claim, and either an explicit tier or a
  `[V]` / `[I]` / `[H]` evidence tag. `[V]` maps to verified, `[I]` to inference,
  `[H]` to hypothesis. A finding with no stated tier defaults to heuristic; Algol
  never invents "verified" from a source that did not claim it.
- conditions: the reopens-if conditions gauntlet recorded. They seed the record's
  reopens-if (A14), so a human dispositioning the change can adopt them.

## Router alignment (no double-triage)

The router recommends gauntlet on undo-cost, and a human runs it. gauntlet then
runs its own triage and may still skip. That run-or-skip call is gauntlet's, not
Algol's. When it skips, the run record says so, and the adapter records the skip
reason under the record's `deep_tier` block rather than dropping it. Algol does
not re-triage what gauntlet already triaged.

## How it lands in the record

The adapter returns observations (folded into findings by the same exact
correlation reconcile uses for collectors) plus a `deep_tier` block: source,
verdict, conditions, reopens_if_seeds, and, when skipped, the skip reason. A
gauntlet finding that shares a line with a collector's heuristic row becomes one
finding whose status is verified because gauntlet verified it, while the
heuristic observation stays heuristic. That is the never-upgrade invariant across
the shallow and deep tiers.

## Boundary

gauntlet's own Step-8 reconcile is for external safety gates within one review,
and its ledger is per-run lens telemetry. Neither is Algol's cross-engine
reconcile or its governed record across the repo's history. gauntlet is one
source Algol reconciles alongside the collectors, `/code-review`, and `ultra`.
