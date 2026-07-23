"""Supported-source tier ceilings: only a deterministic verifier reaches verified."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))
import reconcile as rc  # noqa: E402
import gauntlet_adapter as ga  # noqa: E402
import compose_adapter as ca  # noqa: E402


class TestTierCeilings(unittest.TestCase):
    def test_supported_source_ceilings(self) -> None:
        # Feed each adapter input that over-claims "verified"; assert its ceiling.
        row = {"rule_id": "seclint/x", "file": "a.py", "line": 1, "standard": "security",
               "confidence": 1.0, "evidence": "[V a.py:1]", "message": "m", "col": 1}
        self.assertEqual(rc._collector_observations([row])[0][1].tier, "heuristic")

        rig = ca.parse_rigor({"findings": [{"file": "a.py", "line": 1, "claim": "c", "tier": "verified"}]})
        self.assertEqual(rig[0][1].tier, "inference")

        g = ga.parse_run_record({"verdict": "NO-GO", "findings": [
            {"file": "a.py", "line": 1, "claim": "c", "tier": "verified", "evidence": "[V a.py:1]"}]}).observations()
        self.assertEqual(g[0][1].tier, "model_corroborated")

        u = ca.parse_uat({"verdict": "FAIL", "findings": [{"file": "a.py", "line": 1, "claim": "c"}]})
        self.assertEqual(u[0][1].tier, "verified")


if __name__ == "__main__":
    unittest.main()
