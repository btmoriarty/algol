"""Tests for decide, the command that records a human disposition.

Regression for the gap where the record documented dispositions and an event
log, but no command wrote either, and the reopens-if rule was not enforced.

Run: python -m unittest discover -s tests
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import decide  # noqa: E402
import reconcile as rc  # noqa: E402
import record as rec  # noqa: E402


def make_record(d: Path) -> tuple[Path, str]:
    rows = [{"rule_id": "seclint/eval-exec", "file": "a.py", "line": 1, "standard": "security",
             "confidence": 0.9, "evidence": "eval(", "message": "eval", "col": 1}]
    record = rc.reconcile([rc._collector_observations(rows)])
    path = d / ".algol" / "record.json"
    path.parent.mkdir(parents=True)
    path.write_text(record.to_json(), encoding="utf-8")
    return path, record.findings[0].id


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = decide.main(argv)
    return code, out.getvalue(), err.getvalue()


class TestSet(unittest.TestCase):
    def test_records_disposition_and_event(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path, fid = make_record(Path(d))
            code, _, _ = run(["set", fid[:8], "--state", "suppress", "--rationale", "not user input",
                              "--reopens-if", "input becomes user-controlled", "--by", "reviewer",
                              "--record", str(path)])
            self.assertEqual(code, 0)
            disp = rec.Record.from_json(path.read_text()).by_id()[fid].disposition
            self.assertEqual((disp.state, disp.by), ("suppress", "reviewer"))
            self.assertEqual(disp.reopens_if, ["input becomes user-controlled"])
            events = (path.parent / "events.jsonl").read_text().splitlines()
            self.assertEqual(len(events), 1)
            ev = json.loads(events[0])
            self.assertEqual((ev["event"], ev["finding"], ev["state"], ev["previous"]),
                             ("disposition", fid, "suppress", None))
            self.assertIn("at", ev)

    def test_requires_reopens_if_unless_waived(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path, fid = make_record(Path(d))
            before = path.read_text()
            code, _, err = run(["set", fid, "--state", "accept", "--rationale", "ok", "--record", str(path)])
            self.assertEqual(code, 2)
            self.assertIn("--no-reopens", err)
            self.assertEqual(path.read_text(), before)
            code, _, err = run(["set", fid, "--state", "accept", "--rationale", "ok", "--no-reopens",
                                "--record", str(path)])
            self.assertEqual(code, 0)
            self.assertIn("permanent verdict", err)

    def test_more_than_three_conditions_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path, fid = make_record(Path(d))
            argv = ["set", fid, "--state", "defer", "--rationale", "later", "--record", str(path)]
            for i in range(4):
                argv += ["--reopens-if", f"condition {i}"]
            self.assertEqual(run(argv)[0], 2)

    def test_unknown_or_short_id_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path, fid = make_record(Path(d))
            base = ["--state", "accept", "--rationale", "ok", "--reopens-if", "x", "--record", str(path)]
            self.assertEqual(run(["set", "ffffffffffff", *base])[0], 2)
            self.assertEqual(run(["set", fid[:3], *base])[0], 2)


class TestList(unittest.TestCase):
    def test_lists_ids_and_filters_undecided(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path, fid = make_record(Path(d))
            code, out, _ = run(["list", "--record", str(path)])
            self.assertEqual(code, 0)
            self.assertIn(fid, out)
            self.assertIn("undecided", out)
            run(["set", fid, "--state", "accept", "--rationale", "ok", "--reopens-if", "x",
                 "--record", str(path)])
            self.assertEqual(run(["list", "--undecided", "--record", str(path)])[1], "")


class TestGatePointsAtDecide(unittest.TestCase):
    def test_gate_prints_ids_a_human_can_pass_to_decide(self) -> None:
        import gate
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            comp = root / ".algol" / "compiled"
            comp.mkdir(parents=True)
            (comp / "routing.json").write_text(json.dumps({
                "default": "skip", "undo_cost": [],
                "standards": [{"axis": "security", "engine": "seclint", "paths": ["**/*.py"]}]}))
            (comp / "scanner-rules.json").write_text(json.dumps({"collectors": {"seclint": ["**/*.py"]}}))
            (root / "a.py").write_text("x = eval(user_input)\n")
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                code = gate.main(["--compiled", str(comp), "--changed", "a.py", "--show-floor"])
            self.assertEqual(code, 0)
            record = rec.Record.from_json((root / ".algol" / "record.json").read_text())
            fid = record.findings[0].id
            self.assertIn(fid, err.getvalue())
            self.assertEqual(run(["set", fid, "--state", "accept", "--rationale", "ok",
                                  "--reopens-if", "x", "--record",
                                  str(root / ".algol" / "record.json")])[0], 0)


class TestAppendEvent(unittest.TestCase):
    def test_appends_one_json_line_per_event(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "sub" / "events.jsonl"
            rec.append_event(log, {"b": 2, "a": 1})
            rec.append_event(log, {"c": 3})
            lines = log.read_text().splitlines()
            self.assertEqual([json.loads(x) for x in lines], [{"a": 1, "b": 2}, {"c": 3}])


if __name__ == "__main__":
    unittest.main()
