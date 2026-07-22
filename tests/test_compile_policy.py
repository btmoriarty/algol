"""Tests for the Algol policy compiler.

Run: python -m unittest discover -s tests
(Python 3.11+ for tomllib; on older Python, pip install tomli.)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import compile_policy as cp  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "sample-policy.toml"


class TestParse(unittest.TestCase):
    def _load(self, text: str) -> dict:
        # Parse TOML text the same way the compiler does.
        return cp.tomllib.loads(text)

    def test_sample_policy_parses(self) -> None:
        data = self._load(FIXTURE.read_text(encoding="utf-8"))
        policy = cp.parse_policy(data)
        self.assertEqual(policy.version, "0")
        self.assertEqual(policy.project, "example")
        self.assertEqual(policy.default_engine, "skip")
        self.assertGreaterEqual(len(policy.standards), 1)
        self.assertEqual(policy.undo_cost[0].cls, "irreversible")
        self.assertEqual(policy.undo_cost[0].escalate_to, "gauntlet")

    def test_missing_version_fails(self) -> None:
        data = self._load('[[standard]]\naxis="a"\npaths=["x"]\nengine="skip"\n')
        with self.assertRaises(cp.PolicyError):
            cp.parse_policy(data)

    def test_unknown_engine_fails(self) -> None:
        data = self._load(
            '[meta]\nversion="0"\n[[standard]]\naxis="a"\npaths=["x"]\nengine="nope"\n'
        )
        with self.assertRaises(cp.PolicyError):
            cp.parse_policy(data)

    def test_empty_paths_fails(self) -> None:
        data = self._load(
            '[meta]\nversion="0"\n[[standard]]\naxis="a"\npaths=[]\nengine="skip"\n'
        )
        with self.assertRaises(cp.PolicyError):
            cp.parse_policy(data)

    def test_no_standards_fails(self) -> None:
        data = self._load('[meta]\nversion="0"\n')
        with self.assertRaises(cp.PolicyError):
            cp.parse_policy(data)

    def test_duplicate_undo_class_fails(self) -> None:
        text = (
            '[meta]\nversion="0"\n'
            '[[undo_cost]]\nclass="x"\npaths=["a"]\nescalate_to="gauntlet"\n'
            '[[undo_cost]]\nclass="x"\npaths=["b"]\nescalate_to="ultra"\n'
            '[[standard]]\naxis="a"\npaths=["x"]\nengine="skip"\n'
        )
        with self.assertRaises(cp.PolicyError):
            cp.parse_policy(self._load(text))


class TestCompileArtifacts(unittest.TestCase):
    def test_emits_four_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "compiled"
            written = cp.compile_policy(FIXTURE, out)
            names = {p.name for p in written}
            self.assertEqual(
                names,
                {"REVIEW.md", "scanner-rules.json", "routing.json", "catalog.json"},
            )
            for p in written:
                self.assertTrue(p.is_file(), f"{p} not written")

    def test_scanner_rules_only_collectors(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "compiled"
            cp.compile_policy(FIXTURE, out)
            rules = json.loads((out / "scanner-rules.json").read_text())["collectors"]
            self.assertEqual(set(rules.keys()), {"brevlint", "seclint"})
            self.assertIn("**/*.py", rules["seclint"])
            self.assertIn("docs/**", rules["brevlint"])

    def test_catalog_has_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "compiled"
            cp.compile_policy(FIXTURE, out)
            cat = json.loads((out / "catalog.json").read_text())
            self.assertEqual(len(cat["source_policy_sha256"]), 64)
            self.assertIn("security", cat["axes"])

    def test_deterministic_output(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            cp.compile_policy(FIXTURE, a)
            cp.compile_policy(FIXTURE, b)
            for name in ("REVIEW.md", "scanner-rules.json", "routing.json", "catalog.json"):
                self.assertEqual(
                    (a / name).read_text(),
                    (b / name).read_text(),
                    f"{name} is not deterministic",
                )


if __name__ == "__main__":
    unittest.main()
