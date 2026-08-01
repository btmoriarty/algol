#!/usr/bin/env python3
"""gate: run Algol over one change and fold it into the persistent record.

This is the per-change (per-PR) entry point. Given a change and a compiled
policy, it does only what Algol is allowed to do on its own, and recommends the
rest:

  - routes the change (router): which engines it should get, deep-tier
    escalation on undo-cost. Recommends; it does not launch them.
  - runs the deterministic collectors on the changed files only (not the whole
    repo), so a diff is cheap.
  - reconciles the collector rows into the existing record with --base, so a
    human's prior dispositions and their reopens-if conditions survive.

Then it reports the run-over-run delta, which is the point: on the second run
the new findings are few, and the decisions you already made are still there.
The heavier engines (policy-review, /code-review, ultra, gauntlet) are the
human's to run from the recommendations, and their results fold in via reconcile
like any other source.

Floor: Python 3.11+, stdlib only (siblings: router, seclint, brevlint,
reconcile, record, pathmatch, changed).

Usage:
  python gate.py --base origin/main                      # diff base..worktree
  python gate.py --base origin/main --head HEAD          # PR range
  python gate.py --changed sage/api.py sage/app.js       # explicit files
  python gate.py --base origin/main --dry-run            # preview, do not write
Reads .algol/compiled/ and .algol/record.json by default; writes the updated
record back unless --dry-run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import router  # noqa: E402
import seclint  # noqa: E402
import brevlint  # noqa: E402
import reconcile as rc  # noqa: E402
from record import Record  # noqa: E402
from pathmatch import matches  # noqa: E402
import changed as changed_mod  # noqa: E402

# Which axis each native collector's rows map to, and how to run it.
_DEFAULT_MAX_LINE = 100


def _run_collector(name: str, rel: str, text: str):
    if name == "seclint":
        return seclint.lint_text(rel, text, "security", seclint.DEFAULT_RULES)
    if name == "brevlint":
        return brevlint.lint_text(rel, text, "brevity", _DEFAULT_MAX_LINE)
    return []  # unknown collector: nothing to run here


def _norm(paths) -> list[str]:
    out = []
    for p in paths:
        p = str(p).replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        out.append(p)
    return out


def run_gate(root: Path, routing: dict, scanner: dict, changed: list[str],
             base: Record | None) -> tuple[Record, dict]:
    """Route the change, collect on the changed files, reconcile into base.
    Returns (record, summary). Pure except reading the changed files' text."""
    root = Path(root)
    changed = _norm(changed)

    recommendations = router.recommend(routing, changed)

    collectors = scanner.get("collectors", {})
    obs_sets = []
    run_keys: set[tuple] = set()          # (file, line, rule_id) seen this run
    collected: dict[str, int] = {}
    for name, globs in collectors.items():
        in_scope = [c for c in changed if any(matches(g, c) for g in globs)]
        rows = []
        for rel in in_scope:
            fp = root / rel
            try:
                text = fp.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rows.extend(_run_collector(name, rel, text))
        collected[name] = len(rows)
        if rows:
            dicts = [r.to_dict() for r in rows]
            for d in dicts:
                run_keys.add((d["file"], int(d["line"]), d["rule_id"]))
            obs_sets.append(rc._collector_observations(dicts))

    base_ids = set(base.by_id()) if base else set()
    record = rc.reconcile(obs_sets, base=base)

    after = record.by_id()
    new_ids = [fid for fid in after if fid not in base_ids]
    carried_ids = [fid for fid in after if fid in base_ids]
    carried_disposed = [fid for fid in carried_ids if after[fid].disposition is not None]
    # A disposed finding whose location fired again this run: the decision still
    # applies, but its reopens-if is worth a fresh look given the change.
    reappeared = [
        fid for fid in carried_disposed
        if (after[fid].file, after[fid].line, after[fid].claim) in run_keys
    ]

    summary = {
        "changed_files": len(changed),
        "collected": collected,
        "recommendations": [
            {"engine": r["engine"], "escalation": r["escalation"], "paths": r["paths"]}
            for r in recommendations["recommendations"]
        ],
        "new": sorted(new_ids),
        "carried": sorted(carried_ids),
        "carried_with_disposition": sorted(carried_disposed),
        "reappeared_disposed": sorted(reappeared),
    }
    return record, summary


def _print_summary(summary: dict, record: Record, out: Path, wrote: bool) -> None:
    e = sys.stderr
    print(f"gate: {summary['changed_files']} changed file(s); "
          f"collectors: {summary['collected']}", file=e)
    if summary["recommendations"]:
        print("gate: recommended engines (run these yourself):", file=e)
        for r in summary["recommendations"]:
            tag = " [escalated: undo-cost]" if r["escalation"] else ""
            print(f"  - {r['engine']}{tag}: {', '.join(r['paths']) or '(default)'}", file=e)
    print(f"gate: {len(summary['new'])} new finding(s), "
          f"{len(summary['carried'])} carried "
          f"({len(summary['carried_with_disposition'])} with your prior disposition preserved)",
          file=e)
    if summary["reappeared_disposed"]:
        print("gate: a disposed finding fired again; re-check its reopens-if:", file=e)
        by_id = record.by_id()
        for fid in summary["reappeared_disposed"]:
            f = by_id[fid]
            conds = "; ".join(f.disposition.reopens_if) if f.disposition else ""
            print(f"  - {f.file}:{f.line} {f.claim} [{f.disposition.state}] reopens-if: {conds or '(none set)'}", file=e)
    print(f"gate: {'wrote' if wrote else 'would write'} record to {out}", file=e)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="run Algol over one change into the record.")
    parser.add_argument("--compiled", type=Path, default=Path(".algol/compiled"),
                        help="dir with routing.json and scanner-rules.json")
    parser.add_argument("--root", type=Path, default=None,
                        help="project root the paths are relative to (default: two levels up from --compiled)")
    parser.add_argument("--changed", nargs="*", default=None, help="explicit changed paths (skip git)")
    parser.add_argument("--changed-from", type=Path, default=None, help="file with one changed path per line")
    parser.add_argument("--base", default=None, help="base ref for git diff (base..worktree, or with --head a PR range)")
    parser.add_argument("--head", default=None, help="head ref; with --base uses base...head")
    parser.add_argument("--staged", action="store_true", help="use the staged index for the diff")
    parser.add_argument("--record", type=Path, default=Path(".algol/record.json"),
                        help="record to merge into and update (created if absent)")
    parser.add_argument("--out", type=Path, default=None, help="where to write (default: the --record path)")
    parser.add_argument("--dry-run", action="store_true", help="do not write the record")
    args = parser.parse_args(argv)

    routing_path = args.compiled / "routing.json"
    scanner_path = args.compiled / "scanner-rules.json"
    for p in (routing_path, scanner_path):
        if not p.is_file():
            print(f"gate: compiled artifact not found: {p} (run compile_policy.py first)", file=sys.stderr)
            return 2
    routing = json.loads(routing_path.read_text(encoding="utf-8"))
    scanner = json.loads(scanner_path.read_text(encoding="utf-8"))

    root = args.root if args.root is not None else args.compiled.resolve().parent.parent

    # Resolve the change.
    changed: list[str] = []
    if args.changed is not None:
        changed = list(args.changed)
    elif args.changed_from is not None:
        if not args.changed_from.is_file():
            print(f"gate: changed-from not found: {args.changed_from}", file=sys.stderr)
            return 2
        changed = [ln.strip() for ln in args.changed_from.read_text(encoding="utf-8").splitlines() if ln.strip()]
    elif args.staged or args.base:
        try:
            changed = changed_mod.changed_files(root, args.base, args.head, args.staged)
        except RuntimeError as exc:
            print(f"gate: {exc}", file=sys.stderr)
            return 2
    else:
        print("gate: pass --changed, --changed-from, --base, or --staged", file=sys.stderr)
        return 2

    if not changed:
        print("gate: no changed files; nothing to do", file=sys.stderr)
        return 0

    base = Record.from_json(args.record.read_text(encoding="utf-8")) if args.record.is_file() else None
    record, summary = run_gate(root, routing, scanner, changed, base)

    out = args.out if args.out is not None else args.record
    if not args.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(record.to_json(), encoding="utf-8")
    _print_summary(summary, record, out, wrote=not args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
