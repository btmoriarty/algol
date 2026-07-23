# Golden-path fixture and README example, spec

Single source of truth for the acme worked example. The README example must be generated from, or continuously tested against, this fixture, so a changed CLI flag, output stream, field name, or evidence mapping fails a test rather than rotting in the docs.

**Status: the in-repo path below was verified by a real run on 2026-07-23** (Python 3.10 with the `tomli` backport, since the tools want 3.11 `tomllib`). Every stdout, stderr, and file value shown here is captured from that run, not reconstructed. The one unrun step is the external `gauntlet` deep tier; see the gaps.

## Two source gaps the fixture must still close
- The exact `gauntlet` invocation and how its run record reaches `gaunt.json` are not documented. The fixture must run a real gauntlet invocation or ship a validated `gaunt.json` with provenance. `gauntlet ...` is not a command and must never be shown as one.
- Without gauntlet, the in-repo tools produce **four heuristic findings and no verified finding**. A `verified` (soon `model_corroborated`) row on the migration appears only when a real gauntlet record is folded in. Do not show one otherwise.

## Fixture files (the acme project)
`.algol/policy.toml`:
```
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
`src/auth.py` (hardcoded credential on line 1, AWS key on line 2, os.system on line 4); `db/migrations/001_init.py` (a `DROP TABLE users`); `docs/readme.md` (a `TODO` on line 5).

## Verified command sequence (captured output, stdout and stderr kept distinct)

Point `ALGOL` at your own algol clone once; every command below uses `$ALGOL` and runs from the project (acme) directory. Do not hard-code a home directory.
```
ALGOL=<path to your algol clone>
```

1. Compile. Prints four lines to **stdout**:
```
$ python3 $ALGOL/skills/algol/tools/compile_policy.py .algol/policy.toml
wrote .algol/compiled/REVIEW.md
wrote .algol/compiled/scanner-rules.json
wrote .algol/compiled/routing.json
wrote .algol/compiled/catalog.json
```

2. Route. Writes **JSON to stdout**, exit 0. This is the real output, not an arrow rendering:
```
$ python3 $ALGOL/skills/algol/tools/router.py --routing .algol/compiled/routing.json \
    --changed src/auth.py db/migrations/001_init.py docs/readme.md
{
  "change": ["src/auth.py", "db/migrations/001_init.py", "docs/readme.md"],
  "default_used": false,
  "note": "Recommendation only. Algol does not launch an engine; a human runs it.",
  "recommendations": [
    {"engine": "gauntlet",      "escalation": true,  "paths": ["db/migrations/001_init.py"], "reasons": ["undo_cost:irreversible"]},
    {"engine": "policy-review", "escalation": false, "paths": ["db/migrations/001_init.py", "docs/readme.md", "src/auth.py"], "reasons": ["standard:policy"]},
    {"engine": "brevlint",      "escalation": false, "paths": ["docs/readme.md"], "reasons": ["standard:brevity"]},
    {"engine": "seclint",       "escalation": false, "paths": ["src/auth.py"], "reasons": ["standard:security"]}
  ]
}
```
The `escalation` field is a boolean; the tool's word is "escalation", there is no "(recommend)" label. A human rendering into `-> engine (escalation) because ...` lines must be labeled as a rendering, not raw output.

3. Collectors. Each writes its rows to `--out` and prints only to **stderr**; stdout is empty. `--rules` and `--root` are required.
```
$ python3 $ALGOL/skills/algol/tools/seclint.py  --rules .algol/compiled/scanner-rules.json --root . --out sec.json
[stderr] seclint: wrote 3 rows to sec.json
$ python3 $ALGOL/skills/algol/tools/brevlint.py --rules .algol/compiled/scanner-rules.json --root . --out brev.json
[stderr] brevlint: wrote 1 rows to brev.json
```
`sec.json` (excerpt): `seclint/hardcoded-password` at src/auth.py:1 (confidence 0.5, evidence `API_...[redacted]`); `seclint/aws-access-key` at src/auth.py:2 (0.9, `AKIA...[redacted]`); `seclint/os-system` at src/auth.py:4 (0.6, `os.system(`). `brev.json`: `brevlint/todo-marker` at docs/readme.md:5.
The router also recommends `policy-review`; it is not run here (see gaps). Do not claim every recommended engine ran.

4. Reconcile. Writes the record JSON to `--out`; **stdout is empty**; the count goes to **stderr**:
```
$ python3 $ALGOL/skills/algol/tools/reconcile.py --collector sec.json --collector brev.json --out .algol/record.json
[stderr] reconcile: wrote 4 findings to .algol/record.json
```
Rendered excerpt of `.algol/record.json` (record content, not reconcile stdout), all four findings `heuristic` because no gauntlet was folded in:
```
seclint/hardcoded-password  src/auth.py:1     status=heuristic
seclint/aws-access-key      src/auth.py:2     status=heuristic
seclint/os-system           src/auth.py:4     status=heuristic
brevlint/todo-marker        docs/readme.md:5  status=heuristic
```
(Fold in a real gauntlet record with a second `reconcile ... --gauntlet gaunt.json --base .algol/record.json` to get the migration finding. Its status is `verified` now, `model_corroborated` after the decided tier change.)

5. Disposition, through the Python record API (there is no disposition command yet). `set_disposition` returns the Disposition object and prints nothing:
```python
import sys; sys.path.insert(0, "<ALGOL>/skills/algol/tools")
import record as rec
r = rec.Record.from_json(open(".algol/record.json").read())
todo = [f for f in r.findings if f.claim == "brevlint/todo-marker"][0]
rec.set_disposition(r, todo.id, "accept", "known, tracked in the docs ticket",
                    reopens_if=["if the file ships to users with the TODO still present"], by="brian")
open(".algol/record.json", "w").write(r.to_json())
```
On reload, the finding persists: `state=accept`, `rationale="known, tracked in the docs ticket"`, `reopens_if=["if the file ships to users with the TODO still present"]`, `by="brian"`; `dispositions_without_reopens` returns empty. The signature is `set_disposition(record, finding_id, state, rationale, reopens_if=None, by="")`; the target is `todo.id`, not a bare object; no status table is printed.

## Fixture assertions (from the round-4 review, condensed)
1. Every displayed shell command runs in a temporary clean checkout: no `...`, no unexplained PATH install, no file the fixture did not create or supply.
2. Compile exits 0 and creates exactly `REVIEW.md`, `scanner-rules.json`, `routing.json`, `catalog.json`, and prints the four `wrote ...` lines to stdout.
3. `router.py` without `--routing` fails argument validation; the README command includes it.
4. The valid route command exits 0 even when it recommends gauntlet (recommend, not gate).
5. Router stdout parses as JSON; a test rejects arrow-formatted text presented as raw router output.
6. The router JSON recommends exactly gauntlet, policy-review, brevlint, seclint for these paths.
7. The gauntlet recommendation has `escalation: true`; docs use "escalation", never a fabricated "(recommend)".
8. Each recommendation carries the expected reason and matching paths (gauntlet has `undo_cost:irreversible`; policy-review present because `standard:policy` matches `**`).
9. Both collector commands include `--rules`, `--root`, `--out`; abbreviated commands fail and create no output files.
10. `sec.json` has the three findings at src/auth.py lines 1, 2, 4 with the expected claims and redacted evidence.
11. `brev.json` has `brevlint/todo-marker` at docs/readme.md line 5.
12. Every collector finding is `heuristic`; stdout empty, count on stderr.
13. policy-review is either run and reconciled, or the abridgment is asserted explicitly.
14. A real gauntlet command runs, or a checked `gaunt.json` with provenance is supplied; `gauntlet ...` is rejected as a command.
15. The collectors-only reconcile creates `.algol/record.json` and prints `reconcile: wrote 4 findings ...` to stderr, nothing to stdout.
16. The gauntlet fold includes `--base .algol/record.json` and preserves all collector findings.
17. A per-finding table shown as raw reconcile stdout is rejected; that content is a record excerpt.
18. The merged record contains the three seclint findings and the brevlint finding (plus the migration finding only when gauntlet is folded in).
19. Merging collector observations never raises status above `heuristic`.
20. With gauntlet folded in, the migration finding carries the gauntlet observation with the `[V]` basis; status is `verified` now, `model_corroborated` after the tier change; keep asserting the source observation and basis.
21. The merged record exposes the deep-tier verdict and reopen seed, or the renderer is labeled an excerpt.
22. The disposition target is found by the full claim `brevlint/todo-marker` and passes `todo.id`, not the object.
23. The call is `rec.set_disposition(r, todo.id, "accept", rationale, reopens_if=[...], by="brian")`.
24. After serialize and reload, the finding retains state accept, the exact rationale, the exact reopen condition, and actor brian.
25. Disposition summaries are labeled record renderings, never shown as output returned by `set_disposition`.
26. Rail engine count, included records, scanner count, and basis agree with the fixture record.
27. The operational summary shows policy compile before routing and does not claim an omitted reviewer was run.
28. The README example is generated from or continuously tested against this fixture; a changed flag, stream, field, or mapping fails the doc test.
