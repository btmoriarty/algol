#!/usr/bin/env python3
"""Path glob matching for policy globs, with globstar (`**`) semantics.

Policy authors write globs like `docs/**` (everything under docs) and
`**/*.py` (every .py at any depth, including the root). Python's stdlib glob and
pathlib.match do not agree with that intuition, so Algol translates a policy
glob to a regex once and matches relative POSIX paths against it.

Shared by the collectors (brevlint, seclint) and later the router, so path
selection means the same thing everywhere.

Rules:
  **/   matches zero or more directories
  **    matches any characters, slashes included
  *     matches any characters except a slash
  ?     matches a single character except a slash
Everything else is literal.
"""
from __future__ import annotations

import re
from pathlib import Path


def glob_to_regex(pattern: str) -> re.Pattern:
    i, n = 0, len(pattern)
    out = ""
    while i < n:
        if pattern[i : i + 3] == "**/":
            out += "(?:.*/)?"
            i += 3
        elif pattern[i : i + 2] == "**":
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile("^" + out + "$")


def matches(pattern: str, rel_posix_path: str) -> bool:
    return glob_to_regex(pattern).match(rel_posix_path) is not None


def iter_matching_files(root: Path, patterns) -> list[Path]:
    """Every file under root whose relative POSIX path matches any pattern.

    Returns a sorted, de-duplicated list, so output is deterministic.
    """
    regexes = [glob_to_regex(p) for p in patterns]
    if not regexes:
        return []
    found: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(r.match(rel) for r in regexes):
            found.append(p)
    return found
