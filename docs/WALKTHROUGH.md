# Walkthrough

A full pass on a small project, the way you would use Algol after cloning it from
GitHub. Every command and output below is real. Assume you cloned Algol to
`~/tools/algol` and your project is `acme`; the examples use `$ALGOL` for the
clone path.

```
export ALGOL=~/tools/algol
```

## The project

```
acme/
  .algol/policy.toml
  src/auth.py                 # a hardcoded key and an os.system call
  db/migrations/001_init.py   # a destructive migration (irreversible path)
  docs/readme.md              # a leftover TODO
```

`.algol/policy.toml`:

```toml
[meta]
version = "0"
project = "acme"

[[undo_cost]]
class = "irreversible"
paths = ["db/migrations/**"]
escalate_to = "gauntlet"

[[standard]]
axis = "security"
paths = ["src/**/*.py"]
engine = "seclint"

[[standard]]
axis = "brevity"
paths = ["docs/**"]
engine = "brevlint"

[[standard]]
axis = "policy"
paths = ["**"]
engine = "policy-review"

[router]
default = "skip"
```

## Step 1: compile the policy

```
python3 $ALGOL/skills/algol/tools/compile_policy.py .algol/policy.toml
```

Writes `.algol/compiled/`: `REVIEW.md`, `scanner-rules.json`, `routing.json`,
`catalog.json`. `REVIEW.md` is the human-readable version of your standards, with
the floor printed at the bottom.

## Step 2: ask how a change should be reviewed

You changed three files. The router recommends; it does not run anything.

```
python3 $ALGOL/skills/algol/tools/router.py --routing .algol/compiled/routing.json \
  --changed src/auth.py db/migrations/001_init.py docs/readme.md
```

```
  -> gauntlet (escalation)  because undo_cost:irreversible
  -> policy-review          because standard:policy
  -> brevlint               because standard:brevity
  -> seclint                because standard:security
  note: Recommendation only. Algol does not launch an engine; a human runs it.
```

The migration escalated to the deep tier on undo-cost alone. The `.py` and the
doc pulled in the collectors and the policy pass.

## Step 3: run the collectors

```
python3 $ALGOL/skills/algol/tools/seclint.py  --rules .algol/compiled/scanner-rules.json --root . --out sec.json
python3 $ALGOL/skills/algol/tools/brevlint.py --rules .algol/compiled/scanner-rules.json --root . --out brev.json
```

seclint (secrets masked):

```
seclint/hardcoded-password | src/auth.py line 1 | API_...[redacted]
seclint/aws-access-key     | src/auth.py line 1 | AKIA...[redacted]
seclint/os-system          | src/auth.py line 3 | os.system(
```

## Step 4: reconcile into one record

```
python3 $ALGOL/skills/algol/tools/reconcile.py --collector sec.json --collector brev.json --out .algol/record.json
```

Every finding enters as `heuristic`: a collector rule firing is a signal, not a
proven defect.

## Step 5: fold in the deep tier

gauntlet ran on the migration and returned a NO-GO with a verified finding. Its
run record folds into the same record.

```
python3 $ALGOL/skills/algol/tools/reconcile.py \
  --collector sec.json --collector brev.json --gauntlet gaunt.json \
  --base .algol/record.json --out .algol/record.json
```

```
deep-tier verdict: NO-GO
reopens-if seeds : ['reopens if the DROP is removed or guarded behind a reversible migration']
migration finding: verified (from gauntlet)
```

The migration finding reads `verified` because gauntlet verified it. A collector
row on the same line would stay `heuristic` next to it; Algol never turns a
heuristic into verified on its own.

## Step 6: decide, with a reopens-if

There is no disposition command yet, so you use the record library directly:

```python
import sys; sys.path.insert(0, "PATH/TO/algol/skills/algol/tools")
import record as rec
r = rec.Record.from_json(open(".algol/record.json").read())
todo = [f for f in r.findings if f.claim == "brevlint/todo-marker"][0]
rec.set_disposition(r, todo.id, "accept", "known, tracked in the docs ticket",
                    reopens_if=["if the file ships to users with the TODO still present"], by="brian")
open(".algol/record.json", "w").write(r.to_json())
print(rec.dispositions_without_reopens(r) or "no permanent decisions")
```

The record is a plain file you commit. A decision without a reopens-if is
flagged, because a permanent verdict by default is what the record exists to
prevent.

## Step 7: the guard (optional)

Wire `hooks.py` (see `hooks.example.json`) so a write to an irreversible path
warns before it happens:

```
echo '{"tool_name":"Write","tool_input":{"file_path":"db/migrations/002_add.py"}}' \
  | ALGOL_ROUTING=.algol/compiled/routing.json python3 $ALGOL/skills/algol/tools/hooks.py pretooluse
```

```
algol guard: db/migrations/002_add.py is in the 'irreversible' undo-cost class; recommend gauntlet before this change.
```

## A note on globs

Scope your standard globs to what you mean. A broad `**/*.md` will also lint the
compiled `.algol/compiled/REVIEW.md`; keep docs standards on `docs/**` or exclude
the compiled directory, so the collectors see your files, not Algol's output.
```
