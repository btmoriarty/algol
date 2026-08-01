#!/usr/bin/env python3
"""init: drop the strong starter policy into a project.

A cold first run is only worthless if the project starts from nothing. init
writes `.algol/policy.toml` from the shipped starter, which already routes the
high-undo-cost surfaces (auth, migrations, money, public API, infra, CI) to a
deeper engine, so the router does something useful before anyone has tuned a
thing. It refuses to clobber an existing policy unless --force, because that file
is the project's owned account of how it reviews.

Floor: Python 3.11+, stdlib only (compile_policy.py is a sibling module).

Usage:
  python init.py --root . --project myapp            # write .algol/policy.toml
  python init.py --root . --project myapp --compile  # ...and compile it
  python init.py --root . --force                    # overwrite an existing policy
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The starter ships alongside SKILL.md, one level up from tools/.
STARTER = Path(__file__).resolve().parent.parent / "starter-policy.toml"
_PLACEHOLDER = "__PROJECT__"


def init_policy(root: str | Path, project: str | None = None, force: bool = False) -> Path:
    """Write the starter to <root>/.algol/policy.toml. Returns the path.
    Raises FileExistsError if it exists and force is False."""
    root = Path(root)
    dest = root / ".algol" / "policy.toml"
    if dest.exists() and not force:
        raise FileExistsError(str(dest))
    if not STARTER.is_file():
        raise FileNotFoundError(f"starter policy missing: {STARTER}")
    name = project or root.resolve().name or "project"
    text = STARTER.read_text(encoding="utf-8").replace(_PLACEHOLDER, name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="write the strong starter policy into a project.")
    parser.add_argument("--root", type=Path, default=Path("."), help="project root (default: .)")
    parser.add_argument("--project", default=None, help="project name (default: the root dir name)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing policy")
    parser.add_argument("--compile", action="store_true", help="also compile the policy after writing")
    args = parser.parse_args(argv)

    try:
        dest = init_policy(args.root, args.project, args.force)
    except FileExistsError:
        print(f"init: {args.root / '.algol' / 'policy.toml'} already exists; use --force to overwrite",
              file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"init: {exc}", file=sys.stderr)
        return 2
    print(f"init: wrote {dest}")

    if args.compile:
        import compile_policy
        out_dir = dest.parent / "compiled"
        try:
            written = compile_policy.compile_policy(dest, out_dir)
        except compile_policy.PolicyError as exc:
            print(f"init: policy error: {exc}", file=sys.stderr)
            return 1
        for p in written:
            print(f"init: compiled {p}")

    print("init: next, edit .algol/policy.toml for your repo, then run the gate on a change:")
    print("  python skills/algol/tools/gate.py --base <main>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
