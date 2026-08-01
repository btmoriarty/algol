"""Tests for verify: the targeted raise-to-verified loop.

The invariants: only a deterministic verifier (uat FAIL) reaches verified;
gauntlet reaches model_corroborated; a verifier that does not address the
finding leaves its tier alone; the harness never invents a tier.

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

import verify  # noqa: E402
import record as rec  # noqa: E402


def heuristic_record(file="a.py", line=7, claim="seclint/weak-hash") -> rec.Record:
    obs = rec.Observation(source="seclint", tier="heuristic", confidence=0.4,
                          evidence="hashlib.md5(", message="weak hash")
    return rec.Record(findings=[rec.Finding(file, line, claim, [obs])])


def target(record: rec.Record):
    f = record.findings[0]
    return f.id, f.file, f.line, f.claim


class TestPrompt(unittest.TestCase):
    def test_prompt_names_finding_and_schema(self) -> None:
        r = heuristic_record()
        fid, file, line, claim = target(r)
        text = verify.build_prompt(r, fid, "uat")
        self.assertIn(f"{file}:{line}", text)
        self.assertIn(claim, text)
        self.assertIn("FAIL", text)
        self.assertIn("evidence-locked-uat", text)

    def test_gauntlet_prompt_mentions_anchor(self) -> None:
        r = heuristic_record()
        fid, *_ = target(r)
        text = verify.build_prompt(r, fid, "gauntlet")
        self.assertIn("[V", text)
        self.assertIn("model_corroborated", text)

    def test_unknown_finding_raises(self) -> None:
        with self.assertRaises(verify.VerifyError):
            verify.build_prompt(heuristic_record(), "deadbeef", "uat")


class TestApplyResult(unittest.TestCase):
    def test_uat_fail_raises_to_verified(self) -> None:
        r = heuristic_record()
        fid, file, line, claim = target(r)
        out = {"axis": "testing", "verdict": "FAIL",
               "findings": [{"file": file, "line": line, "claim": claim,
                             "evidence": "reproduced with input X", "message": "confirmed"}]}
        record, before, after, addressed = verify.apply_result(r, fid, "uat", out)
        self.assertEqual(before, "heuristic")
        self.assertEqual(after, "verified")
        self.assertTrue(addressed)

    def test_gauntlet_reaches_model_corroborated_not_verified(self) -> None:
        r = heuristic_record()
        fid, file, line, claim = target(r)
        out = {"verdict": "NO-GO",
               "findings": [{"file": file, "line": line, "claim": claim,
                             "evidence": f"[V {file}:{line}] panel agreed", "message": "bad"}],
               "conditions": ["reopens if the guard is removed"]}
        record, before, after, addressed = verify.apply_result(r, fid, "gauntlet", out)
        self.assertEqual(after, "model_corroborated")
        self.assertTrue(addressed)

    def test_uat_inconclusive_does_not_raise(self) -> None:
        r = heuristic_record()
        fid, file, line, claim = target(r)
        out = {"axis": "testing", "verdict": "INCONCLUSIVE",
               "findings": [{"file": file, "line": line, "claim": claim,
                             "evidence": "", "message": "could not reproduce"}]}
        record, before, after, addressed = verify.apply_result(r, fid, "uat", out)
        self.assertEqual(after, "heuristic")  # never rounded up

    def test_unaddressed_finding_unchanged(self) -> None:
        r = heuristic_record()
        fid, file, line, claim = target(r)
        # Verifier answers about a different location.
        out = {"axis": "testing", "verdict": "FAIL",
               "findings": [{"file": "other.py", "line": 1, "claim": "x", "evidence": "e"}]}
        record, before, after, addressed = verify.apply_result(r, fid, "uat", out)
        self.assertFalse(addressed)
        self.assertEqual(after, "heuristic")

    def test_non_object_output_raises(self) -> None:
        r = heuristic_record()
        fid, *_ = target(r)
        with self.assertRaises(verify.VerifyError):
            verify.apply_result(r, fid, "uat", [1, 2, 3])


class TestCli(unittest.TestCase):
    def _write_record(self, tmp: Path) -> tuple[Path, str, tuple]:
        r = heuristic_record()
        fid, file, line, claim = target(r)
        p = tmp / "record.json"
        p.write_text(r.to_json())
        return p, fid, (file, line, claim)

    def test_ingest_writes_and_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            recpath, fid, (file, line, claim) = self._write_record(tmp)
            out = tmp / "uat.json"
            out.write_text(json.dumps({"verdict": "FAIL",
                "findings": [{"file": file, "line": line, "claim": claim, "evidence": "repro"}]}))
            code = verify.main(["ingest", str(out), "--record", str(recpath), "--finding", fid])
            self.assertEqual(code, 0)
            after = rec.Record.from_json(recpath.read_text()).by_id()[fid].status
            self.assertEqual(after, "verified")

    def test_ingest_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            recpath, fid, (file, line, claim) = self._write_record(tmp)
            before = rec.Record.from_json(recpath.read_text()).by_id()[fid].status
            out = tmp / "uat.json"
            out.write_text(json.dumps({"verdict": "FAIL",
                "findings": [{"file": file, "line": line, "claim": claim, "evidence": "repro"}]}))
            code = verify.main(["ingest", str(out), "--record", str(recpath),
                                "--finding", fid, "--dry-run"])
            self.assertEqual(code, 0)
            self.assertEqual(rec.Record.from_json(recpath.read_text()).by_id()[fid].status, before)

    def test_prompt_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            recpath, fid, _ = self._write_record(tmp)
            code = verify.main(["prompt", "--record", str(recpath), "--finding", fid,
                                "--out", str(tmp / "req.txt")])
            self.assertEqual(code, 0)
            self.assertIn("uat", (tmp / "req.txt").read_text())


if __name__ == "__main__":
    unittest.main()
