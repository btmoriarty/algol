# Algol v1 acceptance

Date: 2026-07-22. The v1 acceptance criteria from the design brief (docs/DESIGN.md),
each checked against the code and tests by an independent audit. Result: all pass,
95 tests green.

## Criteria

| # | Criterion | Result | Where | Evidence |
|---|-----------|--------|-------|----------|
| 1 | Policy compiles to four artifacts (REVIEW.md, scanner rules, routing, catalog) | pass | compile_policy.py | `compile_policy` writes exactly the four; `test_emits_four_artifacts`, `test_deterministic_output`. |
| 2 | Collectors emit structured evidence rows, not prose | pass | evidence.py, seclint.py, brevlint.py | `EvidenceRow` (rule_id, file, line, standard, confidence, evidence, message, col); both collectors build rows and serialize via `rows_to_json`. |
| 3 | policy-review reports only deviations from declared standards, not a bug hunt | pass | policy_review.py | The discipline states it is not a general bug hunt, judges only against the standards, returns an empty list when the change conforms; `ingest` fails closed on malformed output. |
| 4 | Router recommends (never launches), escalates on undo-cost | pass | router.py | `NOTE` says it does not launch; `test_recommend_only_note`; undo-cost adds the deep tier on top of axis engines; `test_undo_cost_escalates_and_adds_deep_tier`. |
| 5 | reconcile makes one record, keeps verified distinct from heuristic, never silently upgrades | pass | reconcile.py, record.py | collector rows enter heuristic; `Finding.status` is the max tier among observations, never synthesized; `test_never_upgrades_heuristic` keeps the heuristic observation intact alongside a verified one. |
| 6 | Record carries reopens-if and flags dispositions lacking them (A14) | pass | record.py | `Disposition.reopens_if`; `dispositions_without_reopens`; reconcile warns when any exist; `test_dispositions_without_reopens_flagged`. |
| 7 | Deep tier routes to gauntlet; adapter maps tiers without inventing verified | pass | gauntlet_adapter.py | `[V]/[I]/[H]` mapping, missing tier defaults to heuristic; conditions seed reopens-if; `test_missing_defaults_heuristic_never_verified`. |
| 8 | Docs and shipped prose pass voicelint | pass | all .md | 15 files, 0 errors and 0 warnings each. |

## Test suite

```
Ran 95 tests in 0.015s
OK
```

## Notes

- The audit found nothing failing. Each criterion is implemented in code, not asserted in a comment, and each is backed by a test that exercises the behavior it claims.
- voicelint runs against its built-in default profile (no project voice config is wired into this repo). The prose passes; if a project voice profile is wanted later, it can be added.
- The router does not hardcode a fixed menu; it recommends whatever engines the policy declares, and all the named categories are routable.

## Deferred (not gating v1)

- The blind-test convention (A1) and harness (A2), a with-versus-without result graded by a separate model, is deferred. It is the honesty proof point and belongs on the roadmap, not the v1 gate.
- The managed GitHub Code Review check-run is v2.
- Distribution and discoverability (the public remote, marketplace, socialization) are post-1.0.
