"""Golden-path executable regression for the acme worked example.

Runs the real tools end to end and fails when their commands, streams, fields, or
values diverge from these expectations. gauntlet is external; a checked run-record
fixture (tests/fixtures/gaunt.json) stands in for the external run.
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
REOPEN = "if the file ships with the TODO"


def run(args, cwd):
    return subprocess.run([sys.executable, *args], cwd=str(cwd), capture_output=True, text=True)


def load_record_module():
    spec = importlib.util.spec_from_file_location("algol_record_gp", TOOLS / "record.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
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

        r = run([self.t("router.py"), "--routing", ".algol/compiled/routing.json",
                 "--changed", "src/auth.py", "db/migrations/001_init.py", "docs/readme.md"], d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, "")
        recs = {x["engine"]: x for x in json.loads(r.stdout)["recommendations"]}
        self.assertEqual(set(recs), {"gauntlet", "policy-review", "brevlint", "seclint"})
        self.assertTrue(recs["gauntlet"]["escalation"])
        self.assertEqual(recs["gauntlet"]["reasons"], ["undo_cost:irreversible"])
        self.assertEqual(recs["gauntlet"]["paths"], ["db/migrations/001_init.py"])
        self.assertFalse(recs["seclint"]["escalation"])
        self.assertNotEqual(run([self.t("router.py"), "--changed", "x"], d).returncode, 0)

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

        r = run([self.t("reconcile.py"), "--collector", "sec.json", "--collector", "brev.json",
                 "--out", ".algol/record.json"], d)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr.splitlines(), ["reconcile: wrote 4 findings to .algol/record.json"])
        rec = json.loads((d / ".algol" / "record.json").read_text())
        self.assertEqual([f["status"] for f in rec["findings"]], ["heuristic"] * 4)

        r = run([self.t("reconcile.py"), "--gauntlet", str(FIXTURES / "gaunt.json"),
                 "--base", ".algol/record.json", "--out", ".algol/record.json"], d)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertEqual(r.stderr.splitlines(), ["reconcile: wrote 5 findings to .algol/record.json"])
        rec = json.loads((d / ".algol" / "record.json").read_text())
        self.assertEqual([row for row in self.rows(rec) if row[0] != "migration/destructive"],
                         sorted([("seclint/hardcoded-password", "src/auth.py", 1, "heuristic"),
                                 ("seclint/aws-access-key", "src/auth.py", 2, "heuristic"),
                                 ("seclint/os-system", "src/auth.py", 4, "heuristic"),
                                 ("brevlint/todo-marker", "docs/readme.md", 5, "heuristic")]))
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
