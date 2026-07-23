"""Tests for the gauntlet adapter: tier mapping, conditions, skip."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import gauntlet_adapter as ga  # noqa: E402


class TestTierMapping(unittest.TestCase):
    def test_explicit_verified_clamps_other_tiers_win(self) -> None:
        # gauntlet cannot deterministically verify; an explicit "verified" clamps.
        self.assertEqual(ga._tier_of({"tier": "verified", "evidence": "[H] guess"}), "model_corroborated")
        # a non-verified explicit tier is still honored.
        self.assertEqual(ga._tier_of({"tier": "inference", "evidence": "[H]"}), "inference")
        # the new tier is accepted directly; a bare explicit "verified" still clamps.
        self.assertEqual(ga._tier_of({"tier": "model_corroborated"}), "model_corroborated")
        self.assertEqual(ga._tier_of({"tier": "verified"}), "model_corroborated")

    def test_evidence_tag_v_i_h(self) -> None:
        self.assertEqual(ga._tier_of({"evidence": "[V src/a.py:10] anchored"}), "model_corroborated")
        self.assertEqual(ga._tier_of({"evidence": "[I <- V] inferred"}), "inference")
        self.assertEqual(ga._tier_of({"evidence": "[H] hypothesis"}), "hypothesis")

    def test_missing_defaults_heuristic_never_verified(self) -> None:
        self.assertEqual(ga._tier_of({"evidence": "no tag here"}), "heuristic")
        self.assertEqual(ga._tier_of({}), "heuristic")

    def test_unknown_explicit_tier_falls_back(self) -> None:
        self.assertEqual(ga._tier_of({"tier": "bogus", "evidence": "plain"}), "heuristic")


class TestParse(unittest.TestCase):
    def test_verdict_and_conditions_seed_reopens_if(self) -> None:
        run = {
            "verdict": "CONDITIONAL",
            "findings": [{"file": "a.py", "line": 5, "claim": "c", "evidence": "[V a.py:5]", "message": "m"}],
            "conditions": ["reopens if the input becomes user-controlled"],
        }
        result = ga.parse_run_record(run)
        self.assertEqual(result.verdict, "CONDITIONAL")
        obs = result.observations()
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0][1].tier, "model_corroborated")
        deep = result.deep_tier()
        self.assertEqual(deep["reopens_if_seeds"], ["reopens if the input becomes user-controlled"])
        self.assertNotIn("skipped", deep)

    def test_skip_records_reason_and_no_findings(self) -> None:
        run = {"verdict": "SKIPPED", "skip_reason": "Q1 failed: change is reversible", "findings": [{"file": "x", "line": 1}]}
        result = ga.parse_run_record(run)
        self.assertTrue(result.skipped)
        self.assertEqual(result.observations(), [])
        deep = result.deep_tier()
        self.assertTrue(deep["skipped"])
        self.assertIn("reversible", deep["skip_reason"])


class TestReconcileIntegration(unittest.TestCase):
    def test_reconcile_uses_adapter(self) -> None:
        import reconcile as rc
        run = {
            "verdict": "NO-GO",
            "findings": [{"file": "a.py", "line": 9, "claim": "c", "evidence": "[V a.py:9]", "message": "bad"}],
            "conditions": ["reopens if refactored"],
        }
        gobs, deep = rc._gauntlet_observations(run)
        record = rc.reconcile([gobs], deep_tier=deep)
        self.assertEqual(record.findings[0].status, "model_corroborated")
        self.assertEqual(record.deep_tier["verdict"], "NO-GO")
        self.assertEqual(record.deep_tier["reopens_if_seeds"], ["reopens if refactored"])


if __name__ == "__main__":
    unittest.main()
