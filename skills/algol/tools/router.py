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
    # Strip a leading "./" prefix only. Not str.lstrip("./"), which would eat the
    # leading dot of a dotfile path like ".github/workflows/ci.yml".
    out = []
    for p in paths:
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        out.append(p)
    return out


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


def command_for(engine: str, paths, ctx: dict) -> str | None:
    """The copy-pasteable command to run an engine on paths, or None for skip.
    ctx carries `tools`, `compiled`, `root` as strings. External or composed
    engines get a commented how-to rather than a fake one-liner, because a human
    runs them and then folds the result in."""
    tools, compiled, root = ctx["tools"], ctx["compiled"], ctx["root"]
    p = " ".join(paths)
    if engine == "skip":
        return None
    if engine == "seclint":
        return f"python {tools}/seclint.py --rules {compiled}/scanner-rules.json --root {root} {p}"
    if engine == "brevlint":
        return f"python {tools}/brevlint.py --rules {compiled}/scanner-rules.json --root {root} {p}"
    if engine == "policy-review":
        return f"python {tools}/policy_review.py prompt --review {compiled}/REVIEW.md --changed {p} --out prompt.txt"
    if engine == "/code-review":
        return f"/code-review {p}"
    if engine == "ultra":
        return f"/code-review ultra {p}"
    if engine == "gauntlet":
        return (f"# run gauntlet on: {p}\n"
                f"# then: python {tools}/verify.py ingest <run>.json --finding <id> --engine gauntlet")
    if engine == "evidence-locked-uat":
        return (f"# run evidence-locked-uat on: {p}\n"
                f"# then: python {tools}/verify.py ingest <result>.json --finding <id> --engine uat")
    if engine == "applying-formal-rigor":
        return (f"# run applying-formal-rigor on: {p}\n"
                f"# then: python {tools}/reconcile.py --rigor <result>.json --base .algol/record.json --out .algol/record.json")
    return f"# {engine}: run on {p}"


def is_low_risk(result: dict) -> bool:
    """True when the change matched nothing and fell through to a skip default:
    the low-risk case the router should be silent about."""
    recs = result.get("recommendations", [])
    return bool(result.get("default_used")) and all(r["engine"] == "skip" for r in recs)


def render_commands(result: dict, ctx: dict) -> str:
    """Copy-pasteable command block for a recommendation, deepest first. Empty
    string on a low-risk change, so wiring the router into every diff is quiet."""
    if is_low_risk(result):
        return ""
    lines: list[str] = []
    for r in result.get("recommendations", []):
        cmd = command_for(r["engine"], r["paths"], ctx)
        if cmd is None:
            continue
        tag = " [escalated: undo-cost]" if r.get("escalation") else ""
        lines.append(f"# {r['engine']}{tag} ({', '.join(r.get('reasons', []))})")
        lines.extend(cmd.splitlines())
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n") if lines else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="router: recommend how a change is reviewed.")
    parser.add_argument("--routing", type=Path, required=True, help="routing.json from the compiler")
    parser.add_argument("--changed", nargs="*", default=[], help="changed file paths")
    parser.add_argument("--changed-from", type=Path, default=None, help="file with one changed path per line")
    parser.add_argument("--format", choices=("json", "commands"), default="json",
                        help="json (default) or copy-pasteable commands, silent on a low-risk change")
    parser.add_argument("--root", type=Path, default=None, help="project root for command rendering (default: inferred)")
    parser.add_argument("--out", type=Path, default=None, help="write here (default: stdout)")
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

    if args.format == "commands":
        root = args.root or args.routing.resolve().parent.parent.parent
        ctx = {"tools": str(Path(__file__).resolve().parent),
               "compiled": str(args.routing.parent), "root": str(root)}
        block = render_commands(result, ctx)
        if not block.strip():
            print("router: nothing to review (low-risk change)", file=sys.stderr)
            return 0
        if args.out is not None:
            args.out.write_text(block, encoding="utf-8")
            print(f"router: wrote commands to {args.out}", file=sys.stderr)
        else:
            sys.stdout.write(block)
        return 0

    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.write_text(output, encoding="utf-8")
        print(f"router: wrote recommendation to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
