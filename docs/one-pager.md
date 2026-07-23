# Algol

**Review control plane for Claude Code.** v0.10.0, local scope.

Algol is the policy, evidence, and decision layer around your Claude Code reviews. It does not perform a general-purpose bug hunt. It reads your versioned review standards, recommends a review depth per change by policy and undo-cost, reconciles findings from supported sources into one record without ever promoting a heuristic to verified, and keeps each human decision with the conditions that would reopen it. The rule everything follows from: a source supplies the strength, Algol preserves it and never silently upgrades a heuristic to verified, and the human decides.

**Who it is for:** a team on Claude Code running more than one review tool, on changes costly to reverse, such as security, infrastructure, permissions, and data migrations. A solo weekend project will not get much from it.

## What you get

1. **Review depth by policy, not gut.** An irreversible change, a migration or a payments path, draws a deep-review recommendation on undo-cost alone; a typo does not.
2. **One result record after the engines run,** each finding with its source and basis kept.
3. **Each finding keeps the strength its source gave it.** A scanner hit stays heuristic; a model panel raises a finding to model_corroborated; verified is reserved for a deterministic verifier. Two guesses agreeing never make verified.
4. **A disposition keeps its rationale** and the conditions that would reopen it. A missing reopen condition is allowed, and flagged.
5. **The review bar is a versioned, path-scoped file** a contributor can read, changed by a reviewable diff.

## Worked example (captured from a real run, 2026-07-23)

The acme project has a hardcoded key and an `os.system` call in `src/auth.py`, a `DROP TABLE` in `db/migrations/001_init.py`, and a `TODO` in `docs/readme.md`.

Compile the policy (four lines to stdout):
```
$ python3 .../compile_policy.py .algol/policy.toml
wrote .algol/compiled/REVIEW.md
wrote .algol/compiled/scanner-rules.json
wrote .algol/compiled/routing.json
wrote .algol/compiled/catalog.json
```
Route the change. The router writes JSON to stdout and exits 0; it recommends, it does not run anything:
```
$ python3 .../router.py --routing .algol/compiled/routing.json \
    --changed src/auth.py db/migrations/001_init.py docs/readme.md
{ "recommendations": [
    {"engine":"gauntlet","escalation":true,"paths":["db/migrations/001_init.py"],"reasons":["undo_cost:irreversible"]},
    {"engine":"policy-review","escalation":false,"paths":["...","docs/readme.md","src/auth.py"],"reasons":["standard:policy"]},
    {"engine":"brevlint","escalation":false,"paths":["docs/readme.md"],"reasons":["standard:brevity"]},
    {"engine":"seclint","escalation":false,"paths":["src/auth.py"],"reasons":["standard:security"]} ],
  "note":"Recommendation only. Algol does not launch an engine; a human runs it." }
```
Run the collectors it recommends. Each writes a file and prints only to stderr:
```
$ python3 .../seclint.py  --rules .algol/compiled/scanner-rules.json --root . --out sec.json
[stderr] seclint: wrote 3 rows to sec.json
$ python3 .../brevlint.py --rules .algol/compiled/scanner-rules.json --root . --out brev.json
[stderr] brevlint: wrote 1 rows to brev.json
```
Reconcile into one record. Stdout is empty; the count goes to stderr; the statuses live in the record file:
```
$ python3 .../reconcile.py --collector sec.json --collector brev.json --out .algol/record.json
[stderr] reconcile: wrote 4 findings to .algol/record.json
```
Record excerpt (`.algol/record.json`), all four heuristic because no gauntlet was folded in:
```
seclint/hardcoded-password  src/auth.py:1     heuristic
seclint/aws-access-key      src/auth.py:2     heuristic
seclint/os-system           src/auth.py:4     heuristic
brevlint/todo-marker        docs/readme.md:5  heuristic
```
Record a decision through the Python record API (there is no disposition command yet); it persists on reload with state, rationale, reopen condition, and actor:
```python
rec.set_disposition(r, todo.id, "accept", "known, tracked in the docs ticket",
                    reopens_if=["if the file ships to users with the TODO still present"], by="brian")
```

**The honest gap.** The in-repo tools produce four heuristic findings. The migration reads `model_corroborated` only when a real `gauntlet` record is folded in with a second `reconcile ... --gauntlet gaunt.json --base .algol/record.json`. That external step does not run in this harness, so it is not shown. A `verified` finding requires a deterministic verifier.

## What it asks, and where it pays off

Write one `.algol/policy.toml` and evolve it through reviewed diffs. Per change: run the router, run the reviewers it recommends, reconcile their outputs, record your decision. Algol adds no new reviewer.

## Status and honesty

v0.10.0, local, 98 tests, an independent acceptance audit passed. The `model_corroborated` tier is shipped: a gauntlet `[V]` anchor reads `model_corroborated`, not `verified`. This one-pager's commands and outputs are captured from a real run (the full fixture and assertions are in `docs/golden-path-spec.md`); the gauntlet deep tier is the one step not run here.
