# Policy model

The core of Algol. A project's review standards live in a versioned, path-scoped
`.algol/policy.toml`, and the compiler turns that one file into the instructions
every other component reads. A change to the policy is a dated, reviewable diff
of how the project reviews.

Tool: `skills/algol/tools/compile_policy.py`. Stdlib only. Floor is Python 3.11+
(`tomllib` in the standard library); on older Python it falls back to the `tomli`
backport if installed.

## Schema

```toml
[meta]
version = "0"          # policy schema version (string)
project = "name"       # optional label

[[undo_cost]]          # zero or more classes
class = "irreversible"
paths = ["db/migrations/**", "api/public/**"]
escalate_to = "gauntlet"

[[standard]]           # one or more
axis = "security"      # open-ended; not a fixed set
paths = ["**/*.py"]
engine = "seclint"     # must be a known engine
notes = ""             # optional

[router]
default = "skip"       # engine for a change that matches no standard
```

Known engines: `seclint`, `brevlint` (Algol-native deterministic collectors),
`policy-review` (the model pass), `/code-review`, `ultra` (Claude Code),
`gauntlet` (the deep tier), `evidence-locked-uat`, `applying-formal-rigor`
(composed disciplines), and `skip`.

## What the compiler emits

Into `.algol/compiled/` (or `--out DIR`):

1. `REVIEW.md`: review instructions, human and model readable. Per standard, which axis is reviewed on which paths via which engine, the undo-cost escalations, the default, and the floor. Carries the source policy sha256.
2. `scanner-rules.json`: path globs per deterministic collector (`seclint`, `brevlint` only), for the collectors to consume.
3. `routing.json`: the routing criteria, the standards, the undo-cost classes, and the default, machine-readable for the router.
4. `catalog.json`: an index, project, policy version, axes, engines, undo-cost classes, standard count, and the source policy sha256.

## Rules the compiler enforces (hard errors, named)

- `meta.version` is a required string.
- At least one `[[standard]]`; each has a non-empty `axis`, a non-empty `paths` list of strings, and an `engine` in the known set.
- Each `[[undo_cost]]` has a non-empty `class` (unique), a non-empty `paths` list, and an `escalate_to` in the known set.
- `router.default`, when present, is in the known set.

A malformed policy exits non-zero with a message naming the exact field.

## Determinism

Compiled output carries no wall-clock timestamp, and JSON is sorted, so
recompiling an unchanged policy produces byte-identical artifacts and the
compiled files diff cleanly. Provenance is the content hash of the source
policy, not a timestamp.

## Usage

```
python skills/algol/tools/compile_policy.py .algol/policy.toml
python skills/algol/tools/compile_policy.py .algol/policy.toml --out build/algol
```

Tests: `python -m unittest discover -s tests`.
