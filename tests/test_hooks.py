"""Tests for the Algol hooks: guard decision and collector report."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import hooks  # noqa: E402

ROUTING = {"undo_cost": [{"class": "irreversible", "paths": ["db/migrations/**"], "escalate_to": "gauntlet"}]}


class TestGuard(unittest.TestCase):
    def test_non_write_tool_allows(self) -> None:
        self.assertEqual(hooks.guard_decision("Read", "db/migrations/1.py", ROUTING)["decision"], "allow")

    def test_write_to_irreversible_warns(self) -> None:
        d = hooks.guard_decision("Write", "db/migrations/007.py", ROUTING)
        self.assertEqual(d["decision"], "warn")
        self.assertEqual(d["escalate_to"], "gauntlet")
        self.assertEqual(d["class"], "irreversible")

    def test_write_to_ordinary_path_allows(self) -> None:
        self.assertEqual(hooks.guard_decision("Write", "src/util.py", ROUTING)["decision"], "allow")

    # Regression: Claude Code passes absolute paths, and lstrip("./") left them
    # absolute, so repo-relative globs never matched and a `**/` glob matched
    # folders above the repo.
    def test_absolute_path_inside_repo_matches_relative_glob(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "db" / "migrations" / "007.py")
            self.assertEqual(hooks.guard_decision("Write", path, ROUTING, root=d)["decision"], "warn")

    def test_glob_does_not_match_parent_folder_outside_repo(self) -> None:
        routing = {"undo_cost": [{"class": "irreversible", "paths": ["**/auth*/**"]}]}
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "authority-service" / "repo"
            repo.mkdir(parents=True)
            inside = str(repo / "README.md")
            self.assertEqual(hooks.guard_decision("Write", inside, routing, root=repo)["decision"], "allow")
            in_auth = str(repo / "src" / "auth" / "login.py")
            self.assertEqual(hooks.guard_decision("Write", in_auth, routing, root=repo)["decision"], "warn")

    def test_absolute_path_outside_repo_allows(self) -> None:
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as other:
            path = str(Path(other) / "db" / "migrations" / "007.py")
            self.assertEqual(hooks.guard_decision("Write", path, ROUTING, root=repo)["decision"], "allow")

    def test_dotfile_relative_path_keeps_its_dot(self) -> None:
        routing = {"undo_cost": [{"class": "operational", "paths": [".github/workflows/**"]}]}
        d = hooks.guard_decision("Edit", "./.github/workflows/ci.yml", routing)
        self.assertEqual(d["decision"], "warn")

    def test_routing_path_follows_project_root_not_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            saved = {k: os.environ.pop(k, None) for k in ("ALGOL_ROUTING",)}
            try:
                self.assertEqual(hooks.routing_path(Path(d)), Path(d) / ".algol" / "compiled" / "routing.json")
            finally:
                for k, v in saved.items():
                    if v is not None:
                        os.environ[k] = v

    def test_empty_path_allows(self) -> None:
        self.assertEqual(hooks.guard_decision("Write", "", ROUTING)["decision"], "allow")


class TestReport(unittest.TestCase):
    def test_counts_signals_non_modifying(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "app.py"
            original = "key = 'AKIAIOSFODNN7EXAMPLE'\n" + "x" * 130 + "\n"
            f.write_text(original, encoding="utf-8")
            report = hooks.collect_report(str(f))
            self.assertTrue(report["readable"])
            self.assertGreaterEqual(report["counts"]["seclint"], 1)
            self.assertGreaterEqual(report["counts"]["brevlint"], 1)
            # the hook does not modify the file
            self.assertEqual(f.read_text(encoding="utf-8"), original)

    def test_unreadable_file(self) -> None:
        report = hooks.collect_report("/no/such/file.py")
        self.assertFalse(report["readable"])

    def test_report_truncates(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "many.py"
            f.write_text("\n".join("x" * 130 for _ in range(20)) + "\n", encoding="utf-8")
            report = hooks.collect_report(str(f))
            self.assertLessEqual(len(report["rows"]), hooks.MAX_REPORT_ROWS)
            self.assertGreater(report["truncated"], 0)


class TestPayload(unittest.TestCase):
    def test_file_path_extraction(self) -> None:
        self.assertEqual(hooks._file_path_from_payload({"tool_input": {"file_path": "a.py"}}), "a.py")
        self.assertEqual(hooks._file_path_from_payload({"tool_input": {"path": "b.py"}}), "b.py")
        self.assertEqual(hooks._file_path_from_payload({}), "")


if __name__ == "__main__":
    unittest.main()
