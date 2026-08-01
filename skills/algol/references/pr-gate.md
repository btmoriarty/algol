# The per-change gate

Algol is a per-change tool, and the gate is where a change goes through it. Two
pieces: `tools/changed.py` names a change's files from git, and `tools/gate.py`
runs the change through the policy and folds the result into the persistent
record. The value shows on the second run: the findings you already decided are
still decided, and only genuinely new ones surface.

## changed.py

Lists the files in a change, as paths relative to `--root` (the directory the
policy globs are relative to, where `.algol/` lives), so they line up with the
compiled artifacts even when the repo root is a level up. Deleted files are
dropped; only existing paths are returned.

```
python skills/algol/tools/changed.py --root . --base origin/main              # base..worktree
python skills/algol/tools/changed.py --root . --base origin/main --head HEAD  # PR range base...head
python skills/algol/tools/changed.py --root . --staged                        # the staged index
```

## gate.py

Given a change and the compiled policy, the gate does only what Algol is allowed
to do on its own, and recommends the rest:

- **routes** the change (router): which engines it should get, deep-tier
  escalation on undo-cost. It recommends; it does not launch them.
- **collects** on the changed files only, not the whole repo, so a diff is
  cheap. Rows enter as heuristic, like any collector's.
- **reconciles** into the existing record with the collector rows as a `--base`
  merge, so prior human dispositions and their reopens-if conditions survive.

Then it reports the run-over-run delta:

- **new**: findings not in the prior record.
- **carried**: findings already in the record, kept with their decision.
- **carried_with_disposition**: of those, the ones a human already decided; the
  decision is preserved untouched.
- **reappeared_disposed**: a decided finding whose location fired again in this
  run. The decision still stands, but the change is a reason to re-read its
  reopens-if.

The heavier engines (policy-review, `/code-review`, ultra, gauntlet) stay the
human's to run from the recommendations; their output folds back in through
reconcile like any other source. The floor holds: the tool proposes and runs
only the deterministic collectors; a human decides and runs the engines.

```
python skills/algol/tools/gate.py --base origin/main               # diff base..worktree
python skills/algol/tools/gate.py --base origin/main --head HEAD    # PR range
python skills/algol/tools/gate.py --changed src/a.py src/b.js       # explicit files
python skills/algol/tools/gate.py --base origin/main --dry-run      # preview, do not write
```

Defaults: reads `.algol/compiled/` and `.algol/record.json`, writes the updated
record back unless `--dry-run`. `--root` defaults to two levels up from
`--compiled`. Wire it as a pre-merge check so every change passes the gate and
the record is the project's running account of what was found and decided.
