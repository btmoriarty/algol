# Changelog

## Unreleased

- Policy model (build plan step 4): `skills/algol/tools/compile_policy.py`, a stdlib-only compiler that validates `.algol/policy.toml` and emits the four artifacts (REVIEW.md, scanner-rules.json, routing.json, catalog.json). Deterministic output; provenance via a source content hash. Schema and rules in `skills/algol/references/policy-model.md`. Fixture plus 10 unittests in `tests/`. Floor: Python 3.11+ (tomllib), tomli fallback for older Python.
- First collector, brevlint (build plan step 5): `skills/algol/tools/brevlint.py` emits deterministic evidence rows for style and brevity (long lines, trailing whitespace, blank-line runs, leftover markers). The shared evidence-row shape lives in `evidence.py`; policy-glob selection with globstar in `pathmatch.py` (reused by later collectors and the router). Collector contract in `skills/algol/references/collectors.md`. 15 more unittests; a collector reports and never gates.
- Router (build plan step 6): `skills/algol/tools/router.py`, recommend-only. Reads `routing.json` and a change, recommends the engine per matched standard, escalates to the deep tier on matched undo-cost classes (reversibility routing, A13), orders deepest first, and never auto-launches. Doc in `skills/algol/references/router.md`. 10 more unittests; compile-then-route verified end to end.
- seclint (build plan step 8): `skills/algol/tools/seclint.py`, the Algol-native security collector. Deterministic, CWE-tagged starter rules (hardcoded secrets, eval/exec, os.system, shell=True, pickle, unsafe yaml.load, verify=False, unverified SSL, weak hash), each with its own confidence. Secret matches are masked; `seclint:ignore` skips a line; an `unless` pattern suppresses per line. Extensible via `--rules-file`. 10 more unittests. Reasoning-heavy security judgment stays out of the collector, by design.
- Reconcile and the governed record (build plan step 7): `skills/algol/tools/record.py` (Finding / Observation / Disposition model, verification tiers, reopens-if A14, deterministic serialization, event log) and `skills/algol/tools/reconcile.py` (merge collector rows and a gauntlet run record into one record, exact correlation, dispositions preserved across re-reconcile). Never silently upgrades a heuristic to verified; that invariant is tested. Doc in `skills/algol/references/reconcile-and-record.md`. 17 more unittests, 52 total. Closes the local spine: policy, collector, router, record.

## 0.0.1 (2026-07-22)

- Repo scaffold. Sets up the CONVENTIONS shape: README, LICENSE, build.sh, VERSION, skills/algol/, docs/. No components built yet.
- Design of record: docs/DESIGN.md (the v3 ReviewOps brief). v1 is local-only; policy-review ships in v1; the deep tier routes to gauntlet.
