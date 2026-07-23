# Algol v1.1 task 2: the golden-path fixture, build brief and test

Draft for review, not yet applied to the repo. This has two parts, and only the first is drafted here:

1. **An executable regression** for the golden-path values. It runs the real tools and fails when their commands, streams, fields, or values diverge from the test expectations. This is drafted and verified below.
2. **A document binding.** A separate check that compares the captured values with the worked-example blocks in the one-pager and the golden-path spec, so a docs-only edit also fails CI. This is specified below and is a required part of task 2. It lands with the doc update to `model_corroborated` (after task 1), because binding to docs that still read `verified` while the test asserts `model_corroborated` would be incoherent.

The earlier draft of this brief called part 1 "documentation binding." That was an overclaim of exactly the kind this work exists to catch: the test binds the tools to values inside the test, not to the documents. A docs-only mistake would still pass. Corrected here.

Depends on task 1 (the `model_corroborated` tier). The test asserts the migration reads `model_corroborated`, so it is green only after task 1 is applied.

Validation run, 2026-07-23: this test was run against a throwaway copy of the repo with task 1 applied, alongside the full tier suite. All 34 tests passed, including the strengthened golden path.

## What the regression asserts (exact, not selective)

- compile: exact four `wrote ...` stdout lines, empty stderr, four artifacts on disk.
- router: the full `recommendations` list by exact equality (all four engines, in order, with exact `escalation`, `reasons`, and `paths`), the exact `note`, `default_used` false, empty stderr, and a nonzero exit without `--routing`.
- collectors: empty stdout, exact single-line stderr, and a nonzero exit when run without `--rules` and without files. (`--root` has a default, so it is not a required flag; the earlier "fails without --root" is not a real assertion.)
- reconcile, collectors: empty stdout, exact stderr count, the exact four finding rows (claim, file, line, status) as a sorted set, and one observation per finding.
- reconcile, gauntlet fold-in (the clean form, `--gauntlet` plus `--base`, no repeated collectors, so no duplicate observations): empty stdout, exact stderr count of five, the four collector rows unchanged, one observation per finding, no `verified` status or tier anywhere, no `policy-review` observation, and the migration finding as exactly one gauntlet observation at line 2 with status `model_corroborated`.
- disposition: `set_disposition` returns a `Disposition`, prints nothing to stdout or stderr, persists state, rationale, reopen condition, and actor across a reload, and leaves the finding `heuristic`.

The record module is loaded through `importlib` under a unique name (registered in `sys.modules` for dataclass resolution), so it does not pollute `sys.path` or shadow a generic `record` module in the full suite.

## Canonical values (one source of truth)

These exact strings must match across the test, the Markdown one-pager, the HTML one-pager, and the golden-path spec. The document binding checks them.

- disposition rationale: `known, tracked in the docs ticket`
- disposition reopen condition: `if the file ships with the TODO`
- finding rows (claim, file, line, status): `seclint/hardcoded-password src/auth.py:1`, `seclint/aws-access-key src/auth.py:2`, `seclint/os-system src/auth.py:4`, `brevlint/todo-marker docs/readme.md:5`, all `heuristic`; plus `migration/destructive db/migrations/001_init.py:2` `model_corroborated` after the fold-in.

Note a real drift the capture exposed: the record sorts findings by id, and the one-pager currently lists the three seclint rows in a different order than the tool emits. When the docs are updated for the binding, use the tool's order or a stable sort, not a hand-picked order.

## Two honesty points the fixture encodes

- **gauntlet is external.** A checked gauntlet run-record fixture, `tests/fixtures/gaunt.json`, stands in for the external run; passing it through the adapter establishes compatibility, not that gauntlet produced it. Do not present it as an executed gauntlet.
- **policy-review is recommended, not run.** The router recommends it, and the test asserts that. The example does not run it, and the record has no policy-review observation, which the test also asserts.

## Files to add

### `tests/fixtures/gaunt.json`

```
{
  "verdict": "NO-GO",
  "findings": [
    {"file": "db/migrations/001_init.py", "line": 2, "claim": "migration/destructive",
     "evidence": "[V db/migrations/001_init.py:2] DROP TABLE users, irreversible",
     "message": "destructive migration"}
  ],
  "conditions": ["reopens if the DROP is removed or guarded behind a reversible migration"]
}
```

### `tests/test_golden_path.py`

```python
"""Golden-path executable regression for the acme worked example.

Runs the real tools end to end and fails when their commands, streams, fields, or
values diverge from these expectations. gauntlet is external; a checked run-record
fixture (tests/fixtures/gaunt.json) stands in for the external run. This binds the
tools to the values here; a separate check must compare these values with the
rendered documents. Requires the model_corroborated tier (v1.1 task 1).
"""
from __future__ import annotations
import importlib.util, json, subprocess, sys, tempfile, shutil, unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "skills" / "algol" / "tools"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

POLICY = '''[meta]
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
'''
AUTH = ('API_KEY = "sk_live_9aQ2exampleSecretValue0001nope"\n'
        'AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'
        'import os\n'
        'os.system("echo building")\n')
MIGRATION = 'def upgrade():\n    execute("DROP TABLE users")\n'
README = '# acme\n\nSetup instructions.\n\nTODO: document the deploy step\n'

REOPEN = "if the file ships with the TODO"  # canonical, must match the docs

EXPECTED_RECS = [
    {"engine": "gauntlet", "escalation": True,
     "paths": ["db/migrations/001_init.py"], "reasons": ["undo_cost:irreversible"]},
    {"engine": "policy-review", "escalation": False,
     "paths": ["db/migrations/001_init.py", "docs/readme.md", "src/auth.py"], "reasons": ["standard:policy"]},
    {"engine": "brevlint", "escalation": False,
     "paths": ["docs/readme.md"], "reasons": ["standard:brevity"]},
    {"engine": "seclint", "escalation": False,
     "paths": ["src/auth.py"], "reasons": ["standard:security"]},
]
EXPECTED_COLLECTOR_ROWS = sorted([
    ("seclint/hardcoded-password", "src/auth.py", 1, "heuristic"),
    ("seclint/aws-access-key", "src/auth.py", 2, "heuristic"),
    ("seclint/os-system", "src/auth.py", 4, "heuristic"),
    ("brevlint/todo-marker", "docs/readme.md", 5, "heuristic"),
])


def run(args, cwd):
    return subprocess.run([sys.executable, *args], cwd=str(cwd), capture_output=True, text=True)


def load_record_module():
    spec = importlib.util.spec_from_file_location("algol_record_gp", TOOLS / "record.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # needed for dataclass __module__ resolution
    spec.loader.exec_module(mod)
    return mod


class TestGoldenPath(unittest.TestCase):
    def setUp(self) -> None:
        self.d = Path(tempfile.mkdtemp())
        (self.d / ".algol").mkdir()
        (self.d / "src").mkdir()
        (self.d / "db" / "migrations").mkdir(parents=True)
        (self.d / "docs").mkdir()
        (self.d / ".algol" / "policy.toml").write_text(POLICY)
        (self.d / "src" / "auth.py").write_text(AUTH)
        (self.d / "db" / "migrations" / "001_init.py").write_text(MIGRATION)
        (self.d / "docs" / "readme.md").write_text(README)

    def tearDown(self) -> None:
        shutil.rmtree(self.d, ignore_errors=True)

    def t(self, name: str) -> str:
        return str(TOOLS / name)

    def rows(self, rec):
        return sorted((f["claim"], f["file"], f["line"], f["status"]) for f in rec["findings"])

    def test_golden_path(self) -> None:
        d = self.d
        # 1. compile: exact stdout, empty stderr, four artifacts
        r = run([self.t("compile_policy.py"), ".algol/policy.toml"], d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        self.assertEqual(r.stdout.splitlines(), [
            "wrote .algol/compiled/REVIEW.md",
            "wrote .algol/compiled/scanner-rules.json",
            "wrote .algol/compiled/routing.json",
            "wrote .algol/compiled/catalog.json"])
        for f in ("REVIEW.md", "scanner-rules.json", "routing.json", "catalog.json"):
            self.assertTrue((d / ".algol" / "compiled" / f).is_file())

        # 2. router: exact JSON, empty stderr, required flag
        r = run([self.t("router.py"), "--routing", ".algol/compiled/routing.json",
                 "--changed", "src/auth.py", "db/migrations/001_init.py", "docs/readme.md"], d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        payload = json.loads(r.stdout)
        self.assertEqual(payload["recommendations"], EXPECTED_RECS)
        self.assertEqual(payload["note"], "Recommendation only. Algol does not launch an engine; a human runs it.")
        self.assertEqual(payload["default_used"], False)
        self.assertNotEqual(run([self.t("router.py"), "--changed", "x"], d).returncode, 0)

        # 3. collectors: empty stdout, exact stderr; and they fail without --rules/files
        r = run([self.t("seclint.py"), "--rules", ".algol/compiled/scanner-rules.json",
                 "--root", ".", "--out", "sec.json"], d)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr.splitlines(), ["seclint: wrote 3 rows to sec.json"])
        r = run([self.t("brevlint.py"), "--rules", ".algol/compiled/scanner-rules.json",
                 "--root", ".", "--out", "brev.json"], d)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr.splitlines(), ["brevlint: wrote 1 rows to brev.json"])
        self.assertNotEqual(run([self.t("seclint.py"), "--root", "."], d).returncode, 0)
        self.assertNotEqual(run([self.t("brevlint.py"), "--root", "."], d).returncode, 0)

        # 4. reconcile collectors: empty stdout, exact stderr, exact four heuristic rows
        r = run([self.t("reconcile.py"), "--collector", "sec.json", "--collector", "brev.json",
                 "--out", ".algol/record.json"], d)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr.splitlines(), ["reconcile: wrote 4 findings to .algol/record.json"])
        rec = json.loads((d / ".algol" / "record.json").read_text())
        self.assertEqual(self.rows(rec), EXPECTED_COLLECTOR_ROWS)
        self.assertTrue(all(len(f["observations"]) == 1 for f in rec["findings"]))

        # 5. fold in the gauntlet fixture (clean form: --gauntlet + --base)
        r = run([self.t("reconcile.py"), "--gauntlet", str(FIXTURES / "gaunt.json"),
                 "--base", ".algol/record.json", "--out", ".algol/record.json"], d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr.splitlines(), ["reconcile: wrote 5 findings to .algol/record.json"])
        rec = json.loads((d / ".algol" / "record.json").read_text())
        self.assertEqual([row for row in self.rows(rec) if row[0] != "migration/destructive"],
                         EXPECTED_COLLECTOR_ROWS)
        self.assertTrue(all(len(f["observations"]) == 1 for f in rec["findings"]))
        self.assertNotIn("verified", [f["status"] for f in rec["findings"]])
        self.assertNotIn("verified", [o["tier"] for f in rec["findings"] for o in f["observations"]])
        self.assertNotIn("policy-review", [o["source"] for f in rec["findings"] for o in f["observations"]])
        mig = [f for f in rec["findings"] if f["claim"] == "migration/destructive"]
        self.assertEqual(len(mig), 1)
        mig = mig[0]
        self.assertEqual((mig["file"], mig["line"], mig["status"]),
                         ("db/migrations/001_init.py", 2, "model_corroborated"))
        self.assertEqual(mig["observations"][0]["source"], "gauntlet")
        self.assertEqual(mig["observations"][0]["tier"], "model_corroborated")

        # 6. disposition: returns a Disposition, silent, persists all fields, tier unchanged
        recmod = load_record_module()
        rr = recmod.Record.from_json((d / ".algol" / "record.json").read_text())
        todo = [f for f in rr.findings if f.claim == "brevlint/todo-marker"][0]
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            disp = recmod.set_disposition(rr, todo.id, "accept", "known, tracked in the docs ticket",
                                          reopens_if=[REOPEN], by="brian")
        self.assertIsInstance(disp, recmod.Disposition)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        (d / ".algol" / "record.json").write_text(rr.to_json())
        back = recmod.Record.from_json((d / ".algol" / "record.json").read_text())
        t2 = [f for f in back.findings if f.claim == "brevlint/todo-marker"][0]
        self.assertEqual(t2.disposition.state, "accept")
        self.assertEqual(t2.disposition.rationale, "known, tracked in the docs ticket")
        self.assertEqual(t2.disposition.reopens_if, [REOPEN])
        self.assertEqual(t2.disposition.by, "brian")
        self.assertEqual(t2.status, "heuristic")


if __name__ == "__main__":
    unittest.main()
```

## Part 2: the document binding (required, lands with the doc update)

Generating the document snippet from the captured run is the preferred binding. Alternatively, this test parses and compares the marked worked-example blocks in the documents. Assertions that do not inspect the documents cannot detect a docs-only drift, so one of these must ship as part of task 2, when the docs move to `model_corroborated`.

Mechanism (generate-and-compare):

- A helper builds a canonical worked-example block (the exact commands, stream labels, record rows, and disposition values) from a live run, as plain text.
- `docs/golden-path-spec.md` carries that block between markers `<!-- GOLDEN-PATH:BEGIN -->` and `<!-- GOLDEN-PATH:END -->`. A test asserts the marked region equals the generated block (whitespace-normalized); a small `--update` script regenerates it.
- The Markdown one-pager carries the same marked block, checked the same way.
- The HTML one-pager is styled, so full-text equality is impractical. Instead the test asserts each canonical value (each command line, each stderr line, each finding row, the disposition values) appears in the page's text. Weaker, but it catches a value that drifts.

Until part 2 ships, the module docstring and this brief must not claim that a docs-only drift fails CI; the wording above is corrected accordingly.

## CI wiring

The suite runs with `python3 -m unittest` from the repo root. Confirm the build workflow runs the unit tests, not only voicelint and the bundle rebuild. If it does not, add a test step, so both the regression and the document binding gate the build.

## Acceptance

1. Task 1 is applied and the full suite passes.
2. The golden-path run executes from a clean checkout.
3. Compile stdout and stderr are exact.
4. Router JSON, order, note, recommendation fields, reasons, paths, and escalation values are exact.
5. Router fails without `--routing`.
6. Both collectors fail without `--rules` and files. (`--root` is optional; it defaults to the current directory.)
7. Collector stdout and stderr are exact.
8. The first record contains the exact four finding claims, paths, lines, and `heuristic` statuses.
9. The gauntlet fold-in adds exactly one migration finding at line 2 with status `model_corroborated`, from one gauntlet observation.
10. No finding or observation reads `verified`.
11. No collector observation is duplicated.
12. Policy-review is recommended but has no observation in the record.
13. Disposition returns a `Disposition`, emits no output, persists all supplied fields, and leaves status `heuristic`.
14. The Markdown one-pager, HTML one-pager, and golden-path spec are generated from, or directly compared with, the captured values.
15. The repository's required CI workflow runs this test and the document binding.

## Out of scope

The DIY comparison (task 3).
