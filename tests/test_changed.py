"""Tests for changed: the git-diff file lister. The git call is not unit-tested
here (the golden path exercises real git); these cover the pure argument and
parse logic.

Run: python -m unittest discover -s tests
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import changed  # noqa: E402


class TestParseNames(unittest.TestCase):
    def test_strips_and_drops_blanks(self) -> None:
        self.assertEqual(changed._parse_names("a.py\n\n  b.js \n"), ["a.py", "b.js"])

    def test_empty(self) -> None:
        self.assertEqual(changed._parse_names(""), [])


class TestGitDiffArgs(unittest.TestCase):
    def test_staged(self) -> None:
        args = changed._git_diff_args(None, None, True)
        self.assertIn("--cached", args)
        self.assertIn("--diff-filter=d", args)
        self.assertIn("--relative", args)

    def test_pr_range_is_triple_dot(self) -> None:
        args = changed._git_diff_args("origin/main", "HEAD", False)
        self.assertIn("origin/main...HEAD", args)

    def test_base_only_is_worktree(self) -> None:
        args = changed._git_diff_args("origin/main", None, False)
        self.assertIn("origin/main", args)
        self.assertNotIn("origin/main...", " ".join(args))

    def test_staged_wins_over_base(self) -> None:
        args = changed._git_diff_args("origin/main", "HEAD", True)
        self.assertIn("--cached", args)
        self.assertNotIn("origin/main...HEAD", args)


if __name__ == "__main__":
    unittest.main()
