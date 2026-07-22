"""Tests for brevlint, the style-and-brevity collector.

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

import brevlint  # noqa: E402
from evidence import EvidenceRow, rows_to_json  # noqa: E402


class TestLintText(unittest.TestCase):
    def _rule_ids(self, rows):
        return {r.rule_id for r in rows}

    def test_long_line(self) -> None:
        text = "x" * 120
        rows = brevlint.lint_text("f.txt", text, "brevity", 100)
        self.assertIn("brevlint/long-line", self._rule_ids(rows))
        row = next(r for r in rows if r.rule_id == "brevlint/long-line")
        self.assertEqual(row.line, 1)
        self.assertEqual(row.standard, "brevity")
        self.assertEqual(row.confidence, 1.0)

    def test_clean_text_no_rows(self) -> None:
        text = "short line\nanother short line\n"
        rows = brevlint.lint_text("f.txt", text, "brevity", 100)
        self.assertEqual(rows, [])

    def test_trailing_whitespace(self) -> None:
        rows = brevlint.lint_text("f.txt", "ok   \n", "brevity", 100)
        self.assertIn("brevlint/trailing-whitespace", self._rule_ids(rows))

    def test_todo_marker(self) -> None:
        rows = brevlint.lint_text("f.txt", "# TODO fix this\n", "brevity", 100)
        self.assertIn("brevlint/todo-marker", self._rule_ids(rows))

    def test_blank_run(self) -> None:
        rows = brevlint.lint_text("f.txt", "a\n\n\n\nb\n", "brevity", 100)
        self.assertIn("brevlint/blank-run", self._rule_ids(rows))

    def test_max_line_configurable(self) -> None:
        text = "x" * 50
        self.assertEqual(brevlint.lint_text("f.txt", text, "brevity", 100), [])
        rows = brevlint.lint_text("f.txt", text, "brevity", 40)
        self.assertIn("brevlint/long-line", self._rule_ids(rows))


class TestSerialization(unittest.TestCase):
    def test_rows_to_json_deterministic_and_sorted(self) -> None:
        rows = [
            EvidenceRow("brevlint/b", "z.txt", 2, "brevity", 1.0, "e"),
            EvidenceRow("brevlint/a", "a.txt", 5, "brevity", 1.0, "e"),
        ]
        out1 = rows_to_json(rows)
        out2 = rows_to_json(list(reversed(rows)))
        self.assertEqual(out1, out2)  # order-independent
        parsed = json.loads(out1)
        self.assertEqual(parsed[0]["file"], "a.txt")  # sorted by file first
        self.assertEqual(
            set(parsed[0].keys()),
            {"rule_id", "file", "line", "col", "standard", "confidence", "evidence", "message"},
        )


class TestCli(unittest.TestCase):
    def test_resolves_from_scanner_rules(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            target = root / "docs" / "note.md"
            target.write_text("x" * 130 + "\n", encoding="utf-8")
            rules = root / "scanner-rules.json"
            rules.write_text(
                json.dumps({"collectors": {"brevlint": ["docs/**"], "seclint": []}}),
                encoding="utf-8",
            )
            out = root / "rows.json"
            code = brevlint.main(["--rules", str(rules), "--root", str(root), "--out", str(out)])
            self.assertEqual(code, 0)
            rows = json.loads(out.read_text())
            self.assertTrue(any(r["rule_id"] == "brevlint/long-line" for r in rows))

    def test_no_files_errors(self) -> None:
        self.assertEqual(brevlint.main([]), 2)


if __name__ == "__main__":
    unittest.main()
