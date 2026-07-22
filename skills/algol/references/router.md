# Router

The router recommends how a change should be reviewed. It launches nothing. A
human reads the recommendation and runs the engine.

Tool: `skills/algol/tools/router.py`. Reads the compiled `routing.json` and a
change (a list of changed file paths), reuses `pathmatch.py` for glob matching,
and returns a recommendation.

## What it does

For each declared standard whose globs match a changed path, it recommends that
standard's engine and names the axis and the matching files. For each undo-cost
class whose globs match, it escalates to the class's engine (the deep tier) and
flags the entry as an escalation. Escalation adds the deep tier on top of the
axis engines; it does not replace them, because reconcile merges every engine's
findings later. A change that matches no standard falls to the policy default.

## Output

A JSON object: the normalized change, a `recommendations` list, `default_used`,
and a note that this is a recommendation only. Each recommendation carries the
engine, its reasons (`standard:<axis>` or `undo_cost:<class>`), the matching
paths, and an `escalation` flag. Recommendations are ordered deepest first by a
fixed depth ladder (skip, collectors, policy-review, `/code-review`, `ultra`,
gauntlet), then by engine name, so the order is stable and diffable.

## Reversibility routing (A13)

The undo-cost classes in the policy are how irreversible changes earn extra
scrutiny on their own: a change touching an irreversible path (a schema
migration, a public API, payments) escalates to the deep tier even without
another flag. Model: the one-way vs two-way door.

## The floor

The router recommends and never auto-launches. Exit code is 0 whether or not it
recommends anything; routing is advice, not a gate.

## Usage

```
python skills/algol/tools/router.py --routing .algol/compiled/routing.json --changed src/a.py docs/b.md
python skills/algol/tools/router.py --routing .algol/compiled/routing.json --changed-from changed.txt
```

`changed.txt` is one changed path per line, for example the output of
`git diff --name-only`. The router does not run git itself.
