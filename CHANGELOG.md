# Changelog

## Unreleased

- Policy model (build plan step 4): `skills/algol/tools/compile_policy.py`, a stdlib-only compiler that validates `.algol/policy.toml` and emits the four artifacts (REVIEW.md, scanner-rules.json, routing.json, catalog.json). Deterministic output; provenance via a source content hash. Schema and rules in `skills/algol/references/policy-model.md`. Fixture plus 10 unittests in `tests/`. Floor: Python 3.11+ (tomllib), tomli fallback for older Python.
- First collector, brevlint (build plan step 5): `skills/algol/tools/brevlint.py` emits deterministic evidence rows for style and brevity (long lines, trailing whitespace, blank-line runs, leftover markers). The shared evidence-row shape lives in `evidence.py`; policy-glob selection with globstar in `pathmatch.py` (reused by later collectors and the router). Collector contract in `skills/algol/references/collectors.md`. 15 more unittests; a collector reports and never gates.

## 0.0.1 (2026-07-22)

- Repo scaffold. Sets up the CONVENTIONS shape: README, LICENSE, build.sh, VERSION, skills/algol/, docs/. No components built yet.
- Design of record: docs/DESIGN.md (the v3 ReviewOps brief). v1 is local-only; policy-review ships in v1; the deep tier routes to gauntlet.
