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

## Copy-pasteable commands, silent on low-risk

`--format commands` renders the recommendation as the exact command to run each
engine, deepest first, with the changed paths filled in: the real one-liner for
the collectors and policy-review, the slash command for `/code-review` and
`ultra`, and a commented how-to for the external and composed engines (gauntlet,
evidence-locked-uat, applying-formal-rigor) that a human runs and then folds in.
So the decision is one keystroke, not a lookup. The floor is unchanged: these are
commands to run, not commands run for you.

On a low-risk change (one that matched no standard and fell through to a `skip`
default) it prints nothing to stdout and a single `nothing to review` line to
stderr, so wiring the router into every diff stays near-zero cost. `is_low_risk`
and `render_commands` are the reusable pieces; the gate uses `command_for` to
print the command under each recommended engine.

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
