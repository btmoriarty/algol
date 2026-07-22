#!/usr/bin/env python3
"""router: recommend how a change should be reviewed. It never launches anything.

The router reads the compiled routing criteria (`routing.json` from the policy
compiler) and a change (a list of changed file paths), and recommends which
engine covers each standard the change touches. Irreversible changes escalate to
the deep tier on undo-cost alone, even without another flag (reversibility
routing). The router recommends; a human runs the engine.

A change touching several axes gets several recommendations; reconcile merges the
engines' findings later. Escalation adds the deep tier on top of the axis
engines, it does not replace them.

Floor: Python 3.11+, stdlib only (pathmatch.py is a sibling module).

Usage:
  python router.py --routing routing.json --changed src/a.py docs/b.md
  python router.py --routing routing.json --changed-from changed.txt
Writes a JSON recommendation to stdout, or to --out FILE. Exit 0 always: it
recommends, it does not gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pathmatch import matches  # noqa: E402

# Depth ladder, only for ordering the recommendations so the deepest sits first.
RANK = {
    "skip": 0,
    "brevlint": 1,
    "seclint": 1,
    "policy-review": 2,
    "evidence-locked-uat": 2,
    "applying-formal-rigor": 2,
    "/code-review": 3,
    "ultra": 4,
    "gauntlet": 5,
}

NOTE = "Recommendation only. Algol does not launch an engine; a human runs it."


def _norm(paths) -> list[str]:
    return [p.replace("\\", "/").lstrip("./") if p not in ("", ".") else p for p in paths]


def recommend(routing: dict, changed) -> dict:
    changed = _norm(list(changed))
    # engine -> {"reasons": set, "paths": set, "escalation": bool}
    acc: dict[str, dict] = {}

    def add(engine: str, reason: str, paths, escalation: bool) -> None:
        slot = acc.setdefault(engine, {"reasons": set(), "paths": set(), "escalation": False})
        slot["reasons"].add(reason)
        slot["paths"].update(paths)
        slot["escalation"] = slot["escalation"] or escalation

    for std in routing.get("standards", []):
        globs = std.get("paths", [])
        hit = [c for c in changed if any(matches(g, c) for g in globs)]
        if hit:
            add(std["engine"], f"standard:{std.get('axis', '?')}", hit, False)

    for u in routing.get("undo_cost", []):
        globs = u.get("paths", [])
        hit = [c for c in changed if any(matches(g, c) for g in globs)]
        if hit:
            add(u["escalate_to"], f"undo_cost:{u.get('class', '?')}", hit, True)

    if not acc:
        default = routing.get("default", "skip")
        return {
            "change": changed,
            "recommendations": [
                {"engine": default, "reasons": ["default"], "paths": [], "escalation": False}
            ],
            "default_used": True,
            "note": NOTE,
        }

    recs = [
        {
            "engine": engine,
            "reasons": sorted(slot["reasons"]),
            "paths": sorted(slot["paths"]),
            "escalation": slot["escalation"],
        }
        for engine, slot in acc.items()
    ]
    # deepest first, then by engine name for a stable order
    recs.sort(key=lambda r: (-RANK.get(r["engine"], 0), r["engine"]))
    return {"change": changed, "recommendations": recs, "default_used": False, "note": NOTE}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="router: recommend how a change is reviewed.")
    parser.add_argument("--routing", type=Path, required=True, help="routing.json from the compiler")
    parser.add_argument("--changed", nargs="*", default=[], help="changed file paths")
    parser.add_argument("--changed-from", type=Path, default=None, help="file with one changed path per line")
    parser.add_argument("--out", type=Path, default=None, help="write JSON here (default: stdout)")
    args = parser.parse_args(argv)

    if not args.routing.is_file():
        print(f"router: routing not found: {args.routing}", file=sys.stderr)
        return 2
    routing = json.loads(args.routing.read_text(encoding="utf-8"))

    changed: list[str] = list(args.changed)
    if args.changed_from is not None:
        if not args.changed_from.is_file():
            print(f"router: changed-from not found: {args.changed_from}", file=sys.stderr)
            return 2
        changed.extend(
            line.strip() for line in args.changed_from.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    if not changed:
        print("router: no changed paths (pass --changed or --changed-from)", file=sys.stderr)
        return 2

    result = recommend(routing, changed)
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.write_text(output, encoding="utf-8")
        print(f"router: wrote recommendation to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
