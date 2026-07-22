"""Tests for the router: recommend-only routing with undo-cost escalation."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import router  # noqa: E402

ROUTING = {
    "default": "skip",
    "standards": [
        {"axis": "security", "paths": ["**/*.py"], "engine": "seclint"},
        {"axis": "brevity", "paths": ["docs/**"], "engine": "brevlint"},
        {"axis": "policy", "paths": ["**"], "engine": "policy-review"},
    ],
    "undo_cost": [
        {"class": "irreversible", "paths": ["db/migrations/**"], "escalate_to": "gauntlet"},
    ],
}


def engines(result):
    return [r["engine"] for r in result["recommendations"]]


class TestRecommend(unittest.TestCase):
    def test_no_match_uses_default(self) -> None:
        result = router.recommend(ROUTING, ["README.rst"])
        # README.rst matches the "**" policy standard, so policy-review fires.
        self.assertIn("policy-review", engines(result))

    def test_true_no_match_uses_default(self) -> None:
        routing = {"default": "skip", "standards": [
            {"axis": "security", "paths": ["**/*.py"], "engine": "seclint"}], "undo_cost": []}
        result = router.recommend(routing, ["notes.md"])
        self.assertTrue(result["default_used"])
        self.assertEqual(engines(result), ["skip"])

    def test_security_change_recommends_seclint(self) -> None:
        result = router.recommend(ROUTING, ["src/app.py"])
        self.assertIn("seclint", engines(result))
        self.assertIn("policy-review", engines(result))  # ** also matches

    def test_multi_axis_change(self) -> None:
        result = router.recommend(ROUTING, ["src/app.py", "docs/guide.md"])
        self.assertEqual(set(engines(result)), {"seclint", "brevlint", "policy-review"})

    def test_undo_cost_escalates_and_adds_deep_tier(self) -> None:
        result = router.recommend(ROUTING, ["db/migrations/001.py"])
        eng = engines(result)
        self.assertEqual(eng[0], "gauntlet")  # deepest first
        gaunt = next(r for r in result["recommendations"] if r["engine"] == "gauntlet")
        self.assertTrue(gaunt["escalation"])
        self.assertIn("undo_cost:irreversible", gaunt["reasons"])
        # the .py file also triggers seclint and policy-review; escalation adds, not replaces
        self.assertIn("seclint", eng)

    def test_deepest_first_ordering(self) -> None:
        result = router.recommend(ROUTING, ["db/migrations/001.py", "docs/x.md"])
        ranks = [router.RANK.get(e, 0) for e in engines(result)]
        self.assertEqual(ranks, sorted(ranks, reverse=True))

    def test_recommend_only_note(self) -> None:
        result = router.recommend(ROUTING, ["src/app.py"])
        self.assertIn("does not launch", result["note"])


class TestCli(unittest.TestCase):
    def test_cli_changed_from(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            routing = root / "routing.json"
            routing.write_text(json.dumps(ROUTING), encoding="utf-8")
            changed = root / "changed.txt"
            changed.write_text("db/migrations/001.py\n", encoding="utf-8")
            out = root / "rec.json"
            code = router.main(["--routing", str(routing), "--changed-from", str(changed), "--out", str(out)])
            self.assertEqual(code, 0)
            result = json.loads(out.read_text())
            self.assertEqual(result["recommendations"][0]["engine"], "gauntlet")

    def test_missing_routing_errors(self) -> None:
        self.assertEqual(router.main(["--routing", "/nope/routing.json", "--changed", "a.py"]), 2)

    def test_no_changed_errors(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            routing = Path(d) / "routing.json"
            routing.write_text(json.dumps(ROUTING), encoding="utf-8")
            self.assertEqual(router.main(["--routing", str(routing)]), 2)


if __name__ == "__main__":
    unittest.main()
