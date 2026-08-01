#!/usr/bin/env python3
"""changed: list a change's files, so the rest of Algol can run on a diff.

Algol is a per-change tool, but the collectors and the router need to be told
what changed. This reads that from git: a PR range (base...head), a branch vs
the working tree, or the staged index. Paths come back relative to --root (the
directory the policy globs are relative to, where `.algol/` lives), so they line
up with `routing.json` and `scanner-rules.json` even when the repo root is a
level up.

Deleted files are excluded (there is nothing to scan), and only paths that
exist under --root are returned.

Floor: Python 3.11+, stdlib only.

Usage:
  python changed.py --root . --base origin/main                 # base..worktree
  python changed.py --root . --base origin/main --head HEAD     # PR range base...head
  python changed.py --root . --staged                           # the staged index
Writes one path per line to stdout (or --out); feed it to router --changed-from
or to gate.py.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _parse_names(output: str) -> list[str]:
    return [ln.strip() for ln in output.splitlines() if ln.strip()]


def _git_diff_args(base: str | None, head: str | None, staged: bool) -> list[str]:
    # --relative makes paths relative to the -C directory; --diff-filter=d drops
    # deletions; --name-only is all we need.
    args = ["diff", "--name-only", "--relative", "--diff-filter=d"]
    if staged:
        args.append("--cached")
    elif base and head:
        args.append(f"{base}...{head}")  # triple-dot: what head added since base
    elif base:
        args.append(base)                # base vs the working tree
    return args


def changed_files(root: str | Path = ".", base: str | None = None,
                  head: str | None = None, staged: bool = False) -> list[str]:
    """Return changed files as paths relative to root. Raises RuntimeError if git
    fails (not a repo, unknown ref)."""
    root = Path(root)
    cmd = ["git", "-C", str(root), *_git_diff_args(base, head, staged)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr.strip() or proc.stdout.strip()}")
    names = _parse_names(proc.stdout)
    return [n for n in names if (root / n).is_file()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="list a change's files for Algol.")
    parser.add_argument("--root", type=Path, default=Path("."), help="dir the paths are relative to (where .algol/ lives)")
    parser.add_argument("--base", default=None, help="base ref (base..worktree, or base...head with --head)")
    parser.add_argument("--head", default=None, help="head ref; with --base, uses the PR range base...head")
    parser.add_argument("--staged", action="store_true", help="use the staged index instead of a ref")
    parser.add_argument("--out", type=Path, default=None, help="write here (default: stdout)")
    args = parser.parse_args(argv)

    if not args.staged and not args.base:
        print("changed: pass --base REF (optionally --head), or --staged", file=sys.stderr)
        return 2
    try:
        files = changed_files(args.root, args.base, args.head, args.staged)
    except RuntimeError as exc:
        print(f"changed: {exc}", file=sys.stderr)
        return 2

    payload = "".join(f"{p}\n" for p in files)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        print(f"changed: wrote {len(files)} paths to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
