"""Tests for router command rendering and low-risk silence (roadmap 6).

The router still recommends and never launches; these check it now emits a
copy-pasteable command per recommendation, and stays silent when a change is
low-risk (matched nothing, fell through to skip).

Run: python -m unittest discover -s tests
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import router  # noqa: E402

CTX = {"tools": "/T", "compiled": "/C", "root": "/R"}

FULL = {"default": "skip",
        "standards": [
            {"axis": "security", "engine": "seclint", "paths": ["**/*.py"]},
            {"axis": "policy", "engine": "policy-review", "paths": ["**"]},
        ],
        "undo_cost": [{"class": "irreversible", "escalate_to": "gauntlet", "paths": ["db/**"]}]}

BARE = {"default": "skip",
        "standards": [{"axis": "security", "engine": "seclint", "paths": ["**/*.py"]}],
        "undo_cost": []}


class TestCommandFor(unittest.TestCase):
    def test_skip_has_no_command(self) -> None:
        self.assertIsNone(router.command_for("skip", [], CTX))

    def test_seclint_command(self) -> None:
        cmd = router.command_for("seclint", ["a.py"], CTX)
        self.assertIn("/T/seclint.py", cmd)
        self.assertIn("--rules /C/scanner-rules.json", cmd)
        self.assertIn("--root /R", cmd)
        self.assertIn("a.py", cmd)

    def test_slash_commands(self) -> None:
        self.assertEqual(router.command_for("/code-review", ["a.py"], CTX), "/code-review a.py")
        self.assertEqual(router.command_for("ultra", ["a.py"], CTX), "/code-review ultra a.py")

    def test_external_engine_is_a_how_to(self) -> None:
        cmd = router.command_for("gauntlet", ["a.py"], CTX)
        self.assertTrue(cmd.startswith("#"))
        self.assertIn("verify.py ingest", cmd)


class TestRenderAndLowRisk(unittest.TestCase):
    def test_low_risk_detection(self) -> None:
        self.assertTrue(router.is_low_risk(router.recommend(BARE, ["notes.txt"])))
        self.assertFalse(router.is_low_risk(router.recommend(BARE, ["a.py"])))

    def test_render_has_commands_deepest_first(self) -> None:
        block = router.render_commands(router.recommend(FULL, ["db/x.py"]), CTX)
        self.assertIn("gauntlet", block)
        self.assertIn("/T/seclint.py", block)
        self.assertIn("/T/policy_review.py", block)
        # gauntlet is deepest, so its comment header appears before seclint's command
        self.assertLess(block.index("gauntlet"), block.index("/T/seclint.py"))

    def test_low_risk_renders_empty(self) -> None:
        self.assertEqual(router.render_commands(router.recommend(BARE, ["notes.txt"]), CTX), "")


class TestCli(unittest.TestCase):
    def _routing_file(self, tmp: Path, routing: dict) -> Path:
        p = tmp / "routing.json"
        p.write_text(json.dumps(routing))
        return p

    def test_commands_format_prints_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rp = self._routing_file(Path(tmp), BARE)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = router.main(["--routing", str(rp), "--changed", "a.py",
                                    "--format", "commands", "--root", "/R"])
            self.assertEqual(code, 0)
            self.assertIn("seclint.py", buf.getvalue())

    def test_commands_format_silent_on_low_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rp = self._routing_file(Path(tmp), BARE)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = router.main(["--routing", str(rp), "--changed", "notes.txt",
                                    "--format", "commands"])
            self.assertEqual(code, 0)
            self.assertEqual(buf.getvalue(), "")  # nothing on stdout: silent


if __name__ == "__main__":
    unittest.main()
