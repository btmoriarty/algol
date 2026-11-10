"""Tests for changed: the git-diff file lister. These cover the pure argument
and parse logic, plus one real-git regression for non-ASCII paths.

Run: python -m unittest discover -s tests
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import changed  # noqa: E402


class TestParseNames(unittest.TestCase):
    def test_splits_nul_terminated_verbatim(self) -> None:
        self.assertEqual(changed._parse_names("a.py\0 b c.js\0café.py\0"), ["a.py", " b c.js", "café.py"])

    def test_empty(self) -> None:
        self.assertEqual(changed._parse_names(""), [])


class TestGitDiffArgs(unittest.TestCase):
    def test_staged(self) -> None:
        args = changed._git_diff_args(None, None, True)
        self.assertIn("--cached", args)
        self.assertIn("--diff-filter=d", args)
        self.assertIn("--relative", args)
        self.assertIn("-z", args)

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


@unittest.skipUnless(shutil.which("git"), "git not installed")
class TestRealGit(unittest.TestCase):
    def test_non_ascii_and_spaced_paths_survive(self) -> None:
        # Regression: without -z, git quoted "café.py" as "caf\303\251.py", the
        # is_file() check failed, and the file vanished from the change.
        with tempfile.TemporaryDirectory() as d:
            def git(*a):
                subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
            git("init", "-q")
            git("-c", "user.email=t@example.com", "-c", "user.name=t",
                "commit", "-q", "--allow-empty", "-m", "base")
            for name in ("café.py", "with space.py", "plain.py"):
                (Path(d) / name).write_text("x = 1\n", encoding="utf-8")
            git("add", "-A")
            self.assertEqual(sorted(changed.changed_files(d, staged=True)),
                             ["café.py", "plain.py", "with space.py"])


if __name__ == "__main__":
    unittest.main()
