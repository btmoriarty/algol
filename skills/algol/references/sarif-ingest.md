# SARIF ingest

SARIF is the format the standard tools already emit: CodeQL, Semgrep, bandit,
gitleaks, ruff, and most scanners can write it. `tools/sarif_adapter.py` reads a
SARIF log and produces the same evidence-row shape the native collectors emit,
so reconcile folds any of those tools into the record through the existing
`--collector` path, with no code written per tool. This is the change that makes
Algol a complement to the tools a project runs rather than a competitor to them.

The honest boundary is unchanged. A SARIF result is a tool signal, not a proof,
so its row enters reconcile as `heuristic`, the same tier a collector's row gets.
Nothing here can reach `verified`; only a deterministic verifier does that.

## Mapping

| SARIF | Algol evidence row |
|-------|--------------------|
| `runs[].tool.driver.name` | slugged into the `rule_id` prefix, so it becomes the finding's `source` (e.g. `semgrep-oss`, `codeql`) |
| `result.ruleId` (or `ruleIndex`, or `rule.id`) | the rest of `rule_id`; this is the finding's `claim`, so two tools flagging the same rule at the same spot merge |
| `physicalLocation.artifactLocation.uri` | `file` (uri scheme stripped, percent-decoding applied) |
| `region.startLine` / `startColumn` | `line` / `col` (default 1 when absent) |
| `region.snippet.text` | `evidence`; falls back to the message, then the rule id |
| `message.text` (or a `message.id` resolved against the rule) | `message` |
| `result.rank`, else `properties.security-severity`, else `level` | `confidence`; informational only, since the tier is fixed at heuristic |

A result with more than one physical location yields one row per location, so
every anchor the tool gave is kept.

## What is dropped, and counted

The adapter never invents a location, a rule, or a verdict. It drops a result
rather than guess, and reports the count on stderr so a silent truncation never
reads as full coverage:

- `suppressions` non-empty: the tool already suppressed it; a baseline decision
  is not re-litigated in the record.
- `kind` of `pass` or `notApplicable`: the check did not fire.
- `level` below `--min-level` (default `note`, so `none` is dropped).
- no physical location: nothing to key a finding on.

Malformed SARIF fails closed: a non-object root, a missing or non-list `runs`,
or an unknown `--min-level` raises a named error and a non-zero exit. An empty
`runs` list is valid and yields zero rows, not an error.

## Usage

```
python skills/algol/tools/sarif_adapter.py results.sarif [more.sarif ...] \
    [--standard security] [--min-level note] [--out rows.json]

python skills/algol/tools/reconcile.py --collector rows.json --out .algol/record.json
```

`--standard` sets the policy axis the rows map to (default `security`, which is
what most SARIF-emitting scanners cover). Pass several SARIF files at once to
merge multiple tools in one pass; run twice into the same record with `--base`
to accumulate across tools while preserving your dispositions.
