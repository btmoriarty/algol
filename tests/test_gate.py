"""Tests for gate, the per-change entry point.

The headline test is persistence: run the gate, disposition a finding, run
again, and the decision survives while no finding is re-reported as new. That is
the second-run behavior roadmap item 2 exists to make visible.

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

import gate  # noqa: E402
import record as rec  # noqa: E402


ROUTING = {
    "default": "skip",
    "standards": [{"axis": "security", "engine": "seclint", "paths": ["**/*.py"]}],
    "undo_cost": [{"class": "irreversible", "escalate_to": "gauntlet", "paths": ["migrations/**"]}],
}
SCANNER = {"collectors": {"seclint": ["**/*.py"]}}


def project(tmp: str) -> Path:
    root = Path(tmp)
    comp = root / ".algol" / "compiled"
    comp.mkdir(parents=True)
    (comp / "routing.json").write_text(json.dumps(ROUTING))
    (comp / "scanner-rules.json").write_text(json.dumps(SCANNER))
    return root


class TestFirstRun(unittest.TestCase):
    def test_collects_and_reports_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "a.py").write_text("x = eval(user_input)\n")  # seclint/eval-exec
            record, summary = gate.run_gate(root, ROUTING, SCANNER, ["a.py"], None)
            self.assertGreaterEqual(summary["collected"]["seclint"], 1)
            self.assertEqual(len(summary["new"]), len(record.findings))
            self.assertGreaterEqual(len(summary["new"]), 1)
            self.assertEqual(record.findings[0].status, "heuristic")  # never upgraded

    def test_out_of_scope_file_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "README.md").write_text("nothing dangerous here\n")
            record, summary = gate.run_gate(root, ROUTING, SCANNER, ["README.md"], None)
            self.assertEqual(summary["collected"].get("seclint", 0), 0)
            self.assertEqual(summary["new"], [])


class TestPersistence(unittest.TestCase):
    def test_disposition_survives_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "a.py").write_text("x = eval(user_input)\n")

            record1, _ = gate.run_gate(root, ROUTING, SCANNER, ["a.py"], None)
            fid = record1.findings[0].id
            rec.set_disposition(record1, fid, "suppress", "not user-controlled",
                                ["input becomes user-controlled"])

            record2, summary2 = gate.run_gate(root, ROUTING, SCANNER, ["a.py"], record1)

            # nothing new; the finding is carried, its decision preserved
            self.assertEqual(summary2["new"], [])
            self.assertIn(fid, summary2["carried_with_disposition"])
            self.assertIn(fid, summary2["reappeared_disposed"])
            disp = record2.by_id()[fid].disposition
            self.assertEqual(disp.state, "suppress")
            self.assertEqual(disp.reopens_if, ["input becomes user-controlled"])

    def test_new_finding_on_second_run_is_new_old_is_carried(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "a.py").write_text("x = eval(user_input)\n")
            record1, _ = gate.run_gate(root, ROUTING, SCANNER, ["a.py"], None)
            old = record1.findings[0].id

            (root / "b.py").write_text("import os\nos.system(cmd)\n")  # seclint/os-system
            record2, summary2 = gate.run_gate(root, ROUTING, SCANNER, ["a.py", "b.py"], record1)

            self.assertEqual(len(summary2["new"]), 1)
            self.assertIn(old, summary2["carried"])
            self.assertNotIn(old, summary2["new"])


class TestRouting(unittest.TestCase):
    def test_undo_cost_escalates_to_gauntlet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "migrations").mkdir()
            (root / "migrations" / "001.py").write_text("pass\n")
            _, summary = gate.run_gate(root, ROUTING, SCANNER, ["migrations/001.py"], None)
            engines = {r["engine"]: r for r in summary["recommendations"]}
            self.assertIn("gauntlet", engines)
            self.assertTrue(engines["gauntlet"]["escalation"])


class TestCli(unittest.TestCase):
    def test_main_writes_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "a.py").write_text("x = eval(user_input)\n")
            comp = root / ".algol" / "compiled"
            recpath = root / ".algol" / "record.json"
            code = gate.main([
                "--compiled", str(comp), "--root", str(root),
                "--changed", "a.py", "--record", str(recpath),
            ])
            self.assertEqual(code, 0)
            self.assertTrue(recpath.is_file())
            obj = json.loads(recpath.read_text())
            self.assertGreaterEqual(len(obj["findings"]), 1)

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "a.py").write_text("x = eval(user_input)\n")
            comp = root / ".algol" / "compiled"
            recpath = root / ".algol" / "record.json"
            code = gate.main([
                "--compiled", str(comp), "--root", str(root),
                "--changed", "a.py", "--record", str(recpath), "--dry-run",
            ])
            self.assertEqual(code, 0)
            self.assertFalse(recpath.is_file())


if __name__ == "__main__":
    unittest.main()
