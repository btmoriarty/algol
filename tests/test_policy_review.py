"""Tests for the policy-review harness (schema, normalize, prompt, CLI)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import policy_review as pr  # noqa: E402


def good_finding(**over):
    f = {"file": "src/a.py", "line": 5, "axis": "security",
         "evidence": "query(raw_input)", "message": "input not parameterized", "confidence": 0.7}
    f.update(over)
    return f


class TestValidate(unittest.TestCase):
    def test_empty_findings_ok(self) -> None:
        self.assertEqual(pr.validate_finding_set({"findings": []}), [])

    def test_valid_finding(self) -> None:
        findings = pr.validate_finding_set({"findings": [good_finding()]})
        self.assertEqual(len(findings), 1)

    def test_not_object_fails(self) -> None:
        with self.assertRaises(pr.ReviewOutputError):
            pr.validate_finding_set([good_finding()])

    def test_missing_field_fails(self) -> None:
        bad = good_finding()
        del bad["evidence"]
        with self.assertRaises(pr.ReviewOutputError):
            pr.validate_finding_set({"findings": [bad]})

    def test_bad_confidence_fails(self) -> None:
        with self.assertRaises(pr.ReviewOutputError):
            pr.validate_finding_set({"findings": [good_finding(confidence=2.0)]})

    def test_bad_line_fails(self) -> None:
        with self.assertRaises(pr.ReviewOutputError):
            pr.validate_finding_set({"findings": [good_finding(line=-1)]})


class TestNormalize(unittest.TestCase):
    def test_rows_shape(self) -> None:
        rows = pr.normalize([good_finding()])
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r.rule_id, "policy-review/security")
        self.assertEqual(r.standard, "security")
        self.assertEqual(r.confidence, 0.7)

    def test_normalized_rows_are_reconcilable_as_heuristic(self) -> None:
        # A policy-review row flows through reconcile's collector path as heuristic.
        import reconcile as rc
        rows = json.loads(pr.rows_to_json(pr.normalize([good_finding()])))
        record = rc.reconcile([rc._collector_observations(rows)])
        self.assertEqual(record.findings[0].status, "heuristic")
        self.assertEqual(record.findings[0].observations[0].source, "policy-review")


class TestPrompt(unittest.TestCase):
    def test_prompt_includes_parts(self) -> None:
        prompt = pr.assemble_prompt("STANDARDS-HERE", "CHANGE-HERE")
        self.assertIn("not a general bug hunt", prompt)
        self.assertIn("STANDARDS-HERE", prompt)
        self.assertIn("CHANGE-HERE", prompt)
        self.assertIn("Required output schema", prompt)


class TestCli(unittest.TestCase):
    def test_prompt_then_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            review = root / "REVIEW.md"
            review.write_text("- security: on **/*.py, review via seclint.\n", encoding="utf-8")
            changed = root / "a.py"
            changed.write_text("query(raw_input)\n", encoding="utf-8")
            prompt_out = root / "prompt.txt"
            self.assertEqual(
                pr.main(["prompt", "--review", str(review), "--changed", str(changed), "--out", str(prompt_out)]),
                0,
            )
            self.assertIn("query(raw_input)", prompt_out.read_text())

            model_out = root / "out.json"
            model_out.write_text(json.dumps({"findings": [good_finding()]}), encoding="utf-8")
            rows_out = root / "rows.json"
            self.assertEqual(pr.main(["ingest", str(model_out), "--out", str(rows_out)]), 0)
            rows = json.loads(rows_out.read_text())
            self.assertEqual(rows[0]["rule_id"], "policy-review/security")

    def test_ingest_malformed_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{ not json", encoding="utf-8")
            self.assertEqual(pr.main(["ingest", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
