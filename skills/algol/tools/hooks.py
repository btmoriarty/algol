#!/usr/bin/env python3
"""Algol hooks: guard before a write, lint and report after one.

Two hooks, both non-modifying. They never edit a file, so they never fire a
system-reminder diff back into the context; a formatter-style hook that rewrites
files is exactly the context-bloat trap this avoids (A17). Auto-fixes, if ever,
run between sessions, not here.

  pretooluse   A guard. Before a write to a path in an irreversible undo-cost
               class, warn and recommend the deep tier. This is the concrete
               enforcement point for reversibility routing (A13). It advises by
               default; set ALGOL_GUARD_BLOCK=1 to make it block instead.
  posttooluse  A reporter. After a write, run the deterministic collectors on the
               touched file and print concise counts plus a few rows. It reports;
               it does not gate and does not modify.

Wire these into Claude Code via hooks.json (see the example alongside this file).
The decision and report logic are pure functions, so they are tested directly;
the CLI is a thin stdin/stdout adapter to the harness hook contract.

Floor: Python 3.11+, stdlib only (pathmatch, brevlint, seclint are siblings).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pathmatch import matches  # noqa: E402
import brevlint  # noqa: E402
import seclint  # noqa: E402

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
MAX_REPORT_ROWS = 5


def guard_decision(tool_name: str, path: str, routing: dict) -> dict:
    """Advise on a write. Returns {"decision": "allow"} or a warn with the class
    and the engine to escalate to. Pure; the CLI decides allow vs block."""
    if tool_name not in WRITE_TOOLS or not path:
        return {"decision": "allow"}
    rel = path.replace("\\", "/").lstrip("./")
    for u in routing.get("undo_cost", []):
        globs = u.get("paths", [])
        if any(matches(g, rel) for g in globs) or any(matches(g, path) for g in globs):
            return {
                "decision": "warn",
                "class": u.get("class", ""),
                "escalate_to": u.get("escalate_to", "gauntlet"),
                "reason": (
                    f"{rel} is in the '{u.get('class', '')}' undo-cost class; "
                    f"recommend {u.get('escalate_to', 'gauntlet')} before this change."
                ),
            }
    return {"decision": "allow"}


def collect_report(path: str, standard_security: str = "security", standard_brevity: str = "brevity") -> dict:
    """Run the deterministic collectors on one file and summarize. Non-modifying."""
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return {"file": path, "readable": False, "counts": {}, "rows": []}
    sec = seclint.lint_text(path, text, standard_security, seclint.DEFAULT_RULES)
    brev = brevlint.lint_text(path, text, standard_brevity, brevlint.DEFAULT_MAX_LINE)
    rows = [r.to_dict() for r in (sec + brev)]
    return {
        "file": path,
        "readable": True,
        "counts": {"seclint": len(sec), "brevlint": len(brev)},
        "rows": rows[:MAX_REPORT_ROWS],
        "truncated": max(0, len(rows) - MAX_REPORT_ROWS),
    }


def _load_routing() -> dict:
    path = Path(os.environ.get("ALGOL_ROUTING", ".algol/compiled/routing.json"))
    if not path.is_file():
        return {"undo_cost": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _file_path_from_payload(payload: dict) -> str:
    ti = payload.get("tool_input", {})
    return ti.get("file_path") or ti.get("path") or ""


def _cmd_pretooluse(payload: dict) -> int:
    decision = guard_decision(payload.get("tool_name", ""), _file_path_from_payload(payload), _load_routing())
    block = os.environ.get("ALGOL_GUARD_BLOCK") == "1"
    if decision["decision"] == "warn":
        sys.stderr.write("algol guard: " + decision["reason"] + "\n")
        print(json.dumps(decision))
        return 2 if block else 0  # exit 2 is the block signal in the harness contract
    print(json.dumps(decision))
    return 0


def _cmd_posttooluse(payload: dict) -> int:
    path = _file_path_from_payload(payload)
    if not path:
        print(json.dumps({"decision": "allow"}))
        return 0
    report = collect_report(path)
    c = report.get("counts", {})
    if c.get("seclint") or c.get("brevlint"):
        sys.stderr.write(
            f"algol: {c.get('seclint', 0)} security, {c.get('brevlint', 0)} brevity signal(s) in {path}\n"
        )
    print(json.dumps(report))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("pretooluse", "posttooluse"):
        print("usage: hooks.py {pretooluse|posttooluse}  (payload JSON on stdin)", file=sys.stderr)
        return 2
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    return _cmd_pretooluse(payload) if argv[0] == "pretooluse" else _cmd_posttooluse(payload)


if __name__ == "__main__":
    raise SystemExit(main())
