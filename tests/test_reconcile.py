"""Tests for reconcile, with the never-upgrade invariant at the center."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import reconcile as rc  # noqa: E402
import record as rec  # noqa: E402


def collector_row(rule_id="brevlint/long-line", file="a.py", line=3, msg="m", ev="e"):
    return {"rule_id": rule_id, "file": file, "line": line, "standard": "brevity",
            "confidence": 1.0, "evidence": ev, "message": msg, "col": 1}


class TestReconcile(unittest.TestCase):
    def test_collector_rows_are_heuristic(self) -> None:
        obs_set = rc._collector_observations([collector_row()])
        record = rc.reconcile([obs_set])
        self.assertEqual(len(record.findings), 1)
        f = record.findings[0]
        self.assertEqual(f.status, "heuristic")
        self.assertEqual(f.observations[0].source, "brevlint")

    def test_never_upgrades_heuristic(self) -> None:
        # Same (file, line, claim) seen by a collector and by gauntlet.
        col = rc._collector_observations([collector_row(rule_id="seclint/x", file="a.py", line=5)])
        run = {
            "verdict": "CONDITIONAL",
            "findings": [{"file": "a.py", "line": 5, "claim": "seclint/x", "tier": "verified",
                          "evidence": "[V a.py:5]", "message": "confirmed"}],
            "conditions": ["reopens if the guard is removed"],
        }
        gobs, deep = rc._gauntlet_observations(run)
        record = rc.reconcile([col, gobs], deep_tier=deep)
        self.assertEqual(len(record.findings), 1)
        f = record.findings[0]
        # The finding is verified because a verified SOURCE says so...
        self.assertEqual(f.status, "model_corroborated")
        # ...but the heuristic observation is still present and still heuristic.
        tiers = sorted(o.tier for o in f.observations)
        self.assertEqual(tiers, ["heuristic", "model_corroborated"])
        self.assertEqual(record.deep_tier["verdict"], "CONDITIONAL")

    def test_distinct_claims_stay_separate(self) -> None:
        rows = [collector_row(rule_id="brevlint/long-line", line=3),
                collector_row(rule_id="brevlint/todo-marker", line=3)]
        record = rc.reconcile([rc._collector_observations(rows)])
        self.assertEqual(len(record.findings), 2)

    def test_missing_gauntlet_tier_defaults_conservative(self) -> None:
        run = {"verdict": "GO", "findings": [{"file": "a.py", "line": 1, "claim": "c"}], "conditions": []}
        gobs, _ = rc._gauntlet_observations(run)
        record = rc.reconcile([gobs])
        self.assertEqual(record.findings[0].status, "heuristic")  # never invents "verified"

    def test_dedupe_identical_observation_on_rereconcile(self) -> None:
        obs_set = rc._collector_observations([collector_row()])
        first = rc.reconcile([obs_set])
        again = rc.reconcile([obs_set], base=first)
        self.assertEqual(len(again.findings[0].observations), 1)

    def test_base_disposition_preserved(self) -> None:
        obs_set = rc._collector_observations([collector_row()])
        base = rc.reconcile([obs_set])
        fid = base.findings[0].id
        rec.set_disposition(base, fid, "accept", "fine", reopens_if=["if it grows"])
        merged = rc.reconcile([obs_set], base=base)
        self.assertIsNotNone(merged.findings[0].disposition)
        self.assertEqual(merged.findings[0].disposition.state, "accept")
        self.assertEqual(merged.findings[0].disposition.reopens_if, ["if it grows"])


class TestCli(unittest.TestCase):
    def test_end_to_end_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rows = root / "rows.json"
            rows.write_text(json.dumps([collector_row()]), encoding="utf-8")
            out = root / "record.json"
            code = rc.main(["--collector", str(rows), "--out", str(out)])
            self.assertEqual(code, 0)
            record = rec.Record.from_json(out.read_text())
            self.assertEqual(len(record.findings), 1)

    def test_nothing_to_reconcile_errors(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rc.main(["--out", str(Path(d) / "r.json")]), 2)


if __name__ == "__main__":
    unittest.main()
