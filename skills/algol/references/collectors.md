# Evidence collectors

A collector reviews nothing and gates nothing. It walks the files it is given
and emits deterministic structured evidence that reconcile later folds into the
record. seclint and brevlint are the two Algol-native collectors; both speak the
same evidence-row shape so reconcile parses one thing.

## The evidence row

Defined once in `skills/algol/tools/evidence.py` (`EvidenceRow`):

| field | meaning |
|-------|---------|
| rule_id | the rule that fired, namespaced, e.g. `brevlint/long-line` |
| file | path as given to the collector |
| line | 1-based line number |
| col | 1-based column (default 1) |
| standard | the policy axis this maps to, e.g. `brevity` |
| confidence | 0.0 to 1.0; a deterministic mechanical match is 1.0 |
| evidence | the matched text, trimmed |
| message | a human-readable statement of what was found |

`rows_to_json` serializes a list of rows deterministically: sorted by
(file, line, col, rule_id), sorted keys, trailing newline. Same input, same
bytes. The `confidence` field is why reconcile can keep a collector's rows
distinct from an ultra-verified result and never silently upgrade one to the
other.

## Path selection

Collectors select files from the compiled `scanner-rules.json` (the compiler's
per-collector globs) via `skills/algol/tools/pathmatch.py`, which gives policy
globs their intuitive meaning: `docs/**` is everything under docs, `**/*.py` is
every .py at any depth including the root. The router will reuse the same
matcher, so a path means the same thing to policy, collectors, and routing.

## brevlint

`skills/algol/tools/brevlint.py`. Style and brevity. Starter rule set, meant to
grow: long lines (over a configurable max), trailing whitespace, runs of three
or more blank lines, and leftover TODO / FIXME / XXX markers. Maps rows to the
axis passed in (default `brevity`).

```
python skills/algol/tools/brevlint.py FILE [FILE ...] [--max-line 100]
python skills/algol/tools/brevlint.py --rules .algol/compiled/scanner-rules.json --root .
```

Exit code is 0 whether or not rows are emitted. A collector reports; it does not
gate. That decision belongs to the router and the record.

## seclint

`skills/algol/tools/seclint.py`. Security, the Algol-native axis. A deterministic
collector emitting evidence rows, each tagged with a CWE. Starter rule set drawn
from the CWE Top 25 and OWASP material, meant to grow: hardcoded secrets, dynamic
code execution, shell calls, unsafe deserialization (pickle, unsafe yaml.load),
disabled TLS verification, and weak hashing. Each rule carries its own
confidence, the collector's view of how likely the match is a real problem;
reconcile still enters every row as heuristic.

Two hygiene features. Matches for secret rules are masked, so a secret never
lands in the record. A line carrying `seclint:ignore` is skipped, the
framework-false-positive escape hatch. A rule may also carry an `unless` pattern
that suppresses it on the same line (how `yaml.load` is cleared when a safe
loader is named).

```
python skills/algol/tools/seclint.py FILE [FILE ...]
python skills/algol/tools/seclint.py --rules .algol/compiled/scanner-rules.json --root .
python skills/algol/tools/seclint.py FILE --rules-file extra-rules.json
```

The reasoning-heavy security judgment (business-logic flaws, missing controls,
attack-path chaining) is not in the collector. It routes to a model pass, so the
collector never claims a verdict it cannot derive.
