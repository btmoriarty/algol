"""Tests for the strong starter policy and init.

The starter is a shipped asset, so a broken one would poison every cold start;
these guard that it compiles and that its undo-cost globs escalate the surfaces
that recur across projects, while a benign file does not escalate.

Run: python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import init as init_mod  # noqa: E402
import compile_policy as cp  # noqa: E402
import router  # noqa: E402

STARTER = REPO / "skills" / "algol" / "starter-policy.toml"


def _compiled_routing(tmp: Path) -> dict:
    dest = init_mod.init_policy(tmp, project="demo")
    out = dest.parent / "compiled"
    cp.compile_policy(dest, out)
    return json.loads((out / "routing.json").read_text())


def _engines(routing: dict, path: str) -> dict:
    recs = router.recommend(routing, [path])["recommendations"]
    return {r["engine"]: r for r in recs}


class TestStarterCompiles(unittest.TestCase):
    def test_shipped_starter_exists_and_parses(self) -> None:
        self.assertTrue(STARTER.is_file())
        # The literal template (placeholder intact) must still be valid TOML+policy.
        import tomllib
        data = tomllib.loads(STARTER.read_text(encoding="utf-8"))
        policy = cp.parse_policy(data)
        self.assertGreaterEqual(len(policy.standards), 1)
        classes = {u.cls for u in policy.undo_cost}
        self.assertEqual(classes, {"irreversible", "operational"})

    def test_compiles_to_four_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = init_mod.init_policy(tmp, project="demo")
            written = cp.compile_policy(dest, dest.parent / "compiled")
            self.assertEqual(len(written), 4)


class TestStarterRouting(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.routing = _compiled_routing(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_auth_escalates_to_gauntlet(self) -> None:
        e = _engines(self.routing, "app/auth/login.py")
        self.assertIn("gauntlet", e)
        self.assertTrue(e["gauntlet"]["escalation"])

    def test_migration_escalates_to_gauntlet(self) -> None:
        self.assertIn("gauntlet", _engines(self.routing, "db/migrations/0001_init.py"))

    def test_billing_escalates_to_gauntlet(self) -> None:
        self.assertIn("gauntlet", _engines(self.routing, "services/billing/charge.py"))

    def test_infra_escalates_to_code_review(self) -> None:
        e = _engines(self.routing, "infra/main.tf")
        self.assertIn("/code-review", e)
        self.assertTrue(e["/code-review"]["escalation"])

    def test_ci_workflow_escalates_to_code_review(self) -> None:
        self.assertIn("/code-review", _engines(self.routing, ".github/workflows/ci.yml"))

    def test_dockerfile_escalates_to_code_review(self) -> None:
        self.assertIn("/code-review", _engines(self.routing, "deploy/Dockerfile"))

    def test_ordinary_code_no_escalation(self) -> None:
        e = _engines(self.routing, "src/util.py")
        self.assertNotIn("gauntlet", e)
        self.assertNotIn("/code-review", e)
        self.assertIn("seclint", e)          # still gets the security floor
        self.assertIn("policy-review", e)

    def test_docs_get_brevlint_not_escalated(self) -> None:
        e = _engines(self.routing, "README.md")
        self.assertIn("brevlint", e)
        self.assertNotIn("gauntlet", e)


class TestInit(unittest.TestCase):
    def test_writes_policy_with_project_substituted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = init_mod.init_policy(tmp, project="myapp")
            text = dest.read_text()
            self.assertIn('project = "myapp"', text)
            self.assertNotIn("__PROJECT__", text)

    def test_project_defaults_to_root_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "coolproj"
            sub.mkdir()
            dest = init_mod.init_policy(sub)
            self.assertIn('project = "coolproj"', dest.read_text())

    def test_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_mod.init_policy(tmp, project="a")
            with self.assertRaises(FileExistsError):
                init_mod.init_policy(tmp, project="b")

    def test_force_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_mod.init_policy(tmp, project="a")
            dest = init_mod.init_policy(tmp, project="b", force=True)
            self.assertIn('project = "b"', dest.read_text())

    def test_main_refuses_existing_returns_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_mod.init_policy(tmp, project="a")
            code = init_mod.main(["--root", tmp])
            self.assertEqual(code, 1)

    def test_main_compile_produces_routing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code = init_mod.main(["--root", tmp, "--project", "z", "--compile"])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / ".algol" / "compiled" / "routing.json").is_file())


if __name__ == "__main__":
    unittest.main()
