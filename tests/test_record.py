"""Tests for the governed record model."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import record as rec  # noqa: E402


def obs(tier="heuristic", source="brevlint", msg="m", ev="e"):
    return rec.Observation(source=source, tier=tier, confidence=1.0, evidence=ev, message=msg)


class TestFinding(unittest.TestCase):
    def test_id_deterministic(self) -> None:
        a = rec.Finding("f.py", 3, "brevlint/long-line")
        b = rec.Finding("f.py", 3, "brevlint/long-line")
        self.assertEqual(a.id, b.id)
        self.assertNotEqual(a.id, rec.Finding("f.py", 4, "brevlint/long-line").id)

    def test_status_is_highest_tier(self) -> None:
        f = rec.Finding("f.py", 3, "c", observations=[obs("heuristic"), obs("verified", source="evidence-locked-uat")])
        self.assertEqual(f.status, "verified")

    def test_status_empty_is_hypothesis(self) -> None:
        self.assertEqual(rec.Finding("f.py", 1, "c").status, "hypothesis")

    def test_unknown_tier_raises(self) -> None:
        with self.assertRaises(ValueError):
            rec.Observation(source="x", tier="bogus", confidence=1.0, evidence="e")


class TestDisposition(unittest.TestCase):
    def test_set_and_unknown_id(self) -> None:
        r = rec.Record(findings=[rec.Finding("f.py", 3, "c", observations=[obs()])])
        fid = r.findings[0].id
        rec.set_disposition(r, fid, "accept", "looks fine", reopens_if=["if the API becomes public"])
        self.assertEqual(r.findings[0].disposition.state, "accept")
        with self.assertRaises(KeyError):
            rec.set_disposition(r, "deadbeef", "accept", "x")

    def test_unknown_state_raises(self) -> None:
        with self.assertRaises(ValueError):
            rec.Disposition(state="ignore", rationale="x")

    def test_dispositions_without_reopens_flagged(self) -> None:
        r = rec.Record(findings=[rec.Finding("f.py", 3, "c", observations=[obs()])])
        fid = r.findings[0].id
        rec.set_disposition(r, fid, "suppress", "noise", reopens_if=[])
        self.assertEqual(rec.dispositions_without_reopens(r), [fid])


class TestSerialization(unittest.TestCase):
    def test_round_trip(self) -> None:
        r = rec.Record(
            findings=[rec.Finding("f.py", 3, "c", observations=[obs("heuristic"), obs("verified", "evidence-locked-uat")])],
            deep_tier={"source": "gauntlet", "verdict": "CONDITIONAL", "conditions": ["reopens if X"]},
        )
        fid = r.findings[0].id
        rec.set_disposition(r, fid, "defer", "later", reopens_if=["if it ships"], by="brian")
        back = rec.Record.from_json(r.to_json())
        self.assertEqual(back.to_json(), r.to_json())
        self.assertEqual(back.findings[0].disposition.state, "defer")
        self.assertEqual(back.findings[0].status, "verified")
        self.assertEqual(back.deep_tier["verdict"], "CONDITIONAL")

    def test_json_deterministic(self) -> None:
        f1 = rec.Finding("z.py", 9, "c", observations=[obs()])
        f2 = rec.Finding("a.py", 1, "c", observations=[obs()])
        r_a = rec.Record(findings=[f1, f2])
        r_b = rec.Record(findings=[f2, f1])
        self.assertEqual(r_a.to_json(), r_b.to_json())


if __name__ == "__main__":
    unittest.main()


class TestModelCorroboratedOrdering(unittest.TestCase):
    def test_model_corroborated_below_verified(self) -> None:
        both = rec.Finding("f.py", 3, "c", observations=[obs("model_corroborated", source="gauntlet"),
                                                          obs("verified", source="evidence-locked-uat")])
        self.assertEqual(both.status, "verified")
        model_only = rec.Finding("f.py", 4, "c2", observations=[obs("model_corroborated", source="gauntlet")])
        self.assertEqual(model_only.status, "model_corroborated")
