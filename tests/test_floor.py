"""Tests for the silent floor: native-collector-only findings are labeled floor
and reported quietly, never as a peer of a real engine's finding. Provenance is
still kept; this is a presentation label.

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

import record as rec  # noqa: E402
import gate  # noqa: E402


def obs(source, tier="heuristic"):
    return rec.Observation(source=source, tier=tier, confidence=0.7, evidence="e", message="m")


class TestFloorLabel(unittest.TestCase):
    def test_collector_only_is_floor(self) -> None:
        f = rec.Finding("a.py", 1, "seclint/weak-hash", [obs("seclint")])
        self.assertTrue(f.is_floor)

    def test_external_tool_is_not_floor(self) -> None:
        # A Semgrep finding via SARIF is heuristic too, but it is real signal.
        f = rec.Finding("a.py", 1, "semgrep/x", [obs("semgrep")])
        self.assertFalse(f.is_floor)

    def test_mixed_is_not_floor(self) -> None:
        f = rec.Finding("a.py", 1, "c", [obs("seclint"), obs("gauntlet", "model_corroborated")])
        self.assertFalse(f.is_floor)

    def test_no_observations_is_not_floor(self) -> None:
        self.assertFalse(rec.Finding("a.py", 1, "c").is_floor)

    def test_floor_in_to_dict(self) -> None:
        floor = rec.Finding("a.py", 1, "brevlint/long-line", [obs("brevlint")])
        signal = rec.Finding("a.py", 2, "policy-review/x", [obs("policy-review")])
        self.assertTrue(floor.to_dict()["floor"])
        self.assertFalse(signal.to_dict()["floor"])

    def test_partition_floor(self) -> None:
        r = rec.Record(findings=[
            rec.Finding("a.py", 1, "seclint/x", [obs("seclint")]),
            rec.Finding("a.py", 2, "semgrep/y", [obs("semgrep")]),
        ])
        signal, floor = r.partition_floor()
        self.assertEqual([f.claim for f in signal], ["semgrep/y"])
        self.assertEqual([f.claim for f in floor], ["seclint/x"])


ROUTING = {"default": "skip",
           "standards": [{"axis": "security", "engine": "seclint", "paths": ["**/*.py"]}],
           "undo_cost": []}
SCANNER = {"collectors": {"seclint": ["**/*.py"]}}


def project(tmp: str) -> Path:
    root = Path(tmp)
    (root / ".algol" / "compiled").mkdir(parents=True)
    return root


class TestGateFloor(unittest.TestCase):
    def test_collector_findings_report_as_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "a.py").write_text("x = eval(user_input)\n")
            _, summary = gate.run_gate(root, ROUTING, SCANNER, ["a.py"], None)
            # The gate runs only collectors, so its own findings are all floor.
            self.assertEqual(summary["new_signal"], [])
            self.assertGreaterEqual(len(summary["new_floor"]), 1)
            self.assertEqual(sorted(summary["new_floor"]), sorted(summary["new"]))

    def test_signal_from_base_is_carried_not_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = project(tmp)
            (root / "a.py").write_text("x = eval(user_input)\n")
            # Base record already holds a real engine's finding elsewhere.
            base = rec.Record(findings=[
                rec.Finding("sig.py", 9, "semgrep/sqli", [obs("semgrep")]),
            ])
            sig_id = base.findings[0].id
            record, summary = gate.run_gate(root, ROUTING, SCANNER, ["a.py"], base)
            self.assertIn(sig_id, summary["carried"])
            self.assertNotIn(sig_id, summary["new_floor"])
            self.assertFalse(record.by_id()[sig_id].is_floor)


if __name__ == "__main__":
    unittest.main()
