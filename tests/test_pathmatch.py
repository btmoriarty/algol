"""Tests for pathmatch: policy-glob semantics with globstar."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

from pathmatch import matches, iter_matching_files  # noqa: E402


class TestMatches(unittest.TestCase):
    def test_dir_globstar_matches_files_below(self) -> None:
        self.assertTrue(matches("docs/**", "docs/note.md"))
        self.assertTrue(matches("docs/**", "docs/sub/deep.md"))
        self.assertFalse(matches("docs/**", "src/note.md"))

    def test_leading_globstar_matches_root_and_depth(self) -> None:
        self.assertTrue(matches("**/*.py", "a.py"))
        self.assertTrue(matches("**/*.py", "src/a.py"))
        self.assertTrue(matches("**/*.py", "src/deep/a.py"))
        self.assertFalse(matches("**/*.py", "a.txt"))

    def test_single_star_stops_at_slash(self) -> None:
        self.assertTrue(matches("src/*.ts", "src/a.ts"))
        self.assertFalse(matches("src/*.ts", "src/deep/a.ts"))

    def test_question_mark(self) -> None:
        self.assertTrue(matches("f?.md", "fa.md"))
        self.assertFalse(matches("f?.md", "f/.md"))


class TestIterMatchingFiles(unittest.TestCase):
    def test_walks_and_dedupes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs").mkdir()
            (root / "docs" / "a.md").write_text("x", encoding="utf-8")
            (root / "docs" / "b.txt").write_text("x", encoding="utf-8")
            (root / "top.md").write_text("x", encoding="utf-8")
            hits = iter_matching_files(root, ["docs/**", "**/*.md"])
            rels = sorted(p.relative_to(root).as_posix() for p in hits)
            self.assertEqual(rels, ["docs/a.md", "docs/b.txt", "top.md"])

    def test_empty_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(iter_matching_files(Path(d), []), [])


if __name__ == "__main__":
    unittest.main()
