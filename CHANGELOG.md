# Changelog

## Unreleased

- Policy model (build plan step 4): `skills/algol/tools/compile_policy.py`, a stdlib-only compiler that validates `.algol/policy.toml` and emits the four artifacts (REVIEW.md, scanner-rules.json, routing.json, catalog.json). Deterministic output; provenance via a source content hash. Schema and rules in `skills/algol/references/policy-model.md`. Fixture plus 10 unittests in `tests/`. Floor: Python 3.11+ (tomllib), tomli fallback for older Python.

## 0.0.1 (2026-07-22)

- Repo scaffold. Sets up the CONVENTIONS shape: README, LICENSE, build.sh, VERSION, skills/algol/, docs/. No components built yet.
- Design of record: docs/DESIGN.md (the v3 ReviewOps brief). v1 is local-only; policy-review ships in v1; the deep tier routes to gauntlet.
