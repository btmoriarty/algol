"""Tests for the composed-discipline adapters (uat, rigor)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import compose_adapter as ca  # noqa: E402


def finding(**over):
    f = {"file": "a.py", "line": 3, "claim": "test:login", "evidence": "e", "message": "m", "confidence": 1.0}
    f.update(over)
    return f


class TestUat(unittest.TestCase):
    def test_pass_no_findings_is_empty(self) -> None:
        self.assertEqual(ca.parse_uat({"verdict": "PASS", "findings": []}), [])

    def test_fail_is_verified(self) -> None:
        obs = ca.parse_uat({"verdict": "FAIL", "findings": [finding()]})
        self.assertEqual(obs[0][1].tier, "verified")
        self.assertEqual(obs[0][1].source, "evidence-locked-uat")

    def test_inconclusive_is_never_rounded_up(self) -> None:
        # Even if the input over-claims a verified tier, INCONCLUSIVE clamps to hypothesis.
        obs = ca.parse_uat({"verdict": "INCONCLUSIVE", "findings": [finding(tier="verified")]})
        self.assertEqual(obs[0][1].tier, "hypothesis")

    def test_inconclusive_without_findings_still_surfaces(self) -> None:
        obs = ca.parse_uat({"verdict": "INCONCLUSIVE", "findings": []})
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0][1].tier, "hypothesis")
        self.assertIn("not a pass", obs[0][1].message)


class TestRigor(unittest.TestCase):
    def test_derived_is_inference(self) -> None:
        obs = ca.parse_rigor({"axis": "efficiency", "findings": [finding(claim="bigO", message="O(n^2) on hot path")]})
        self.assertEqual(obs[0][1].tier, "inference")
        self.assertEqual(obs[0][1].source, "applying-formal-rigor")

    def test_explicit_tier_respected_when_valid(self) -> None:
        obs = ca.parse_rigor({"findings": [finding(tier="hypothesis")]})
        self.assertEqual(obs[0][1].tier, "hypothesis")


class TestReconcileIntegration(unittest.TestCase):
    def test_reconcile_ingests_uat_and_rigor(self) -> None:
        import json
        import tempfile
        import reconcile as rc
        import record as rec

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            uat = root / "uat.json"
            uat.write_text(json.dumps({"verdict": "FAIL", "findings": [finding(claim="test:x")]}), encoding="utf-8")
            rigor = root / "rigor.json"
            rigor.write_text(json.dumps({"findings": [finding(claim="bigO", line=9)]}), encoding="utf-8")
            out = root / "record.json"
            code = rc.main(["--uat", str(uat), "--rigor", str(rigor), "--out", str(out)])
            self.assertEqual(code, 0)
            record = rec.Record.from_json(out.read_text())
            sources = {o.source for f in record.findings for o in f.observations}
            self.assertEqual(sources, {"evidence-locked-uat", "applying-formal-rigor"})


if __name__ == "__main__":
    unittest.main()
