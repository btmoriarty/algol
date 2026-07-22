#!/usr/bin/env python3
"""Compile an Algol policy file into the four review artifacts.

Algol's core product is the policy. This tool reads a versioned, path-scoped
`.algol/policy.toml` and compiles it into:

  1. REVIEW.md        review instructions (human and model readable)
  2. scanner-rules.json  path globs per deterministic collector (seclint, brevlint)
  3. routing.json     routing criteria (standards, undo-cost classes, default)
  4. catalog.json     an index of axes, engines, and a content hash of the source

The compiler reviews nothing. It only turns policy into the instructions the
router, collectors, and record consume. Output is deterministic: no wall-clock
timestamp is written, so compiled artifacts diff cleanly.

Floor: Python 3.11+ (tomllib in the standard library, zero dependencies). On
older Python it falls back to the `tomli` backport if installed.

Usage:
  python compile_policy.py <policy.toml> [--out DIR]
Default output directory is `.algol/compiled/` next to the policy file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - pre-3.11 fallback
    import tomli as tomllib  # type: ignore

# The engines Algol can route to. seclint and brevlint are Algol-native
# deterministic collectors; policy-review is the model pass; /code-review and
# ultra are Claude Code's reviewers; gauntlet is the deep tier; the last two are
# composed-in disciplines; skip means no review.
COLLECTORS = {"seclint", "brevlint"}
KNOWN_ENGINES = COLLECTORS | {
    "policy-review",
    "/code-review",
    "ultra",
    "gauntlet",
    "evidence-locked-uat",
    "applying-formal-rigor",
    "skip",
}


class PolicyError(Exception):
    """A malformed policy. Raised with a message naming the exact problem."""


@dataclass
class Standard:
    axis: str
    paths: list[str]
    engine: str
    notes: str = ""


@dataclass
class UndoCost:
    cls: str
    paths: list[str]
    escalate_to: str


@dataclass
class Policy:
    version: str
    project: str
    standards: list[Standard] = field(default_factory=list)
    undo_cost: list[UndoCost] = field(default_factory=list)
    default_engine: str = "skip"


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise PolicyError(msg)


def _str_list(value: object, where: str) -> list[str]:
    _require(
        isinstance(value, list) and all(isinstance(x, str) for x in value),
        f"{where}: expected a list of strings",
    )
    _require(len(value) > 0, f"{where}: list must not be empty")  # type: ignore[arg-type]
    return list(value)  # type: ignore[return-value]


def parse_policy(data: dict) -> Policy:
    meta = data.get("meta", {})
    _require(isinstance(meta, dict), "meta: expected a table")
    version = meta.get("version")
    _require(isinstance(version, str), "meta.version: required string (policy schema version)")
    project = meta.get("project", "")
    _require(isinstance(project, str), "meta.project: must be a string")

    standards: list[Standard] = []
    raw_standards = data.get("standard", [])
    _require(isinstance(raw_standards, list), "standard: expected an array of tables")
    for i, s in enumerate(raw_standards):
        where = f"standard[{i}]"
        _require(isinstance(s, dict), f"{where}: expected a table")
        axis = s.get("axis")
        _require(isinstance(axis, str) and axis, f"{where}.axis: required non-empty string")
        engine = s.get("engine")
        _require(
            isinstance(engine, str) and engine in KNOWN_ENGINES,
            f"{where}.engine: must be one of {sorted(KNOWN_ENGINES)}",
        )
        paths = _str_list(s.get("paths"), f"{where}.paths")
        notes = s.get("notes", "")
        _require(isinstance(notes, str), f"{where}.notes: must be a string")
        standards.append(Standard(axis=axis, paths=paths, engine=engine, notes=notes))
    _require(len(standards) > 0, "policy must declare at least one [[standard]]")

    undo_cost: list[UndoCost] = []
    raw_undo = data.get("undo_cost", [])
    _require(isinstance(raw_undo, list), "undo_cost: expected an array of tables")
    seen_classes: set[str] = set()
    for i, u in enumerate(raw_undo):
        where = f"undo_cost[{i}]"
        _require(isinstance(u, dict), f"{where}: expected a table")
        cls = u.get("class")
        _require(isinstance(cls, str) and cls, f"{where}.class: required non-empty string")
        _require(cls not in seen_classes, f"{where}.class: duplicate class '{cls}'")
        seen_classes.add(cls)
        escalate_to = u.get("escalate_to")
        _require(
            isinstance(escalate_to, str) and escalate_to in KNOWN_ENGINES,
            f"{where}.escalate_to: must be one of {sorted(KNOWN_ENGINES)}",
        )
        paths = _str_list(u.get("paths"), f"{where}.paths")
        undo_cost.append(UndoCost(cls=cls, paths=paths, escalate_to=escalate_to))

    router = data.get("router", {})
    _require(isinstance(router, dict), "router: expected a table")
    default_engine = router.get("default", "skip")
    _require(
        isinstance(default_engine, str) and default_engine in KNOWN_ENGINES,
        f"router.default: must be one of {sorted(KNOWN_ENGINES)}",
    )

    return Policy(
        version=version,
        project=project,
        standards=standards,
        undo_cost=undo_cost,
        default_engine=default_engine,
    )


def _dump_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_review_md(policy: Policy, source_sha: str) -> str:
    lines: list[str] = []
    lines.append("# Review instructions (compiled)")
    lines.append("")
    lines.append(
        "Generated by Algol from the project policy. Do not edit by hand; "
        "edit the policy and recompile. Source policy sha256: " + source_sha + "."
    )
    lines.append("")
    lines.append("Algol reviews nothing itself. These instructions say which axis")
    lines.append("each change is reviewed for and which engine covers it.")
    lines.append("")
    lines.append("## Standards")
    lines.append("")
    for s in policy.standards:
        paths = ", ".join(f"`{p}`" for p in s.paths)
        line = f"- {s.axis}: on {paths}, review via `{s.engine}`."
        if s.notes:
            line += f" {s.notes}"
        lines.append(line)
    lines.append("")
    if policy.undo_cost:
        lines.append("## Undo-cost escalation")
        lines.append("")
        for u in policy.undo_cost:
            paths = ", ".join(f"`{p}`" for p in u.paths)
            lines.append(
                f"- {u.cls}: a change touching {paths} escalates to `{u.escalate_to}`, "
                "even without another flag."
            )
        lines.append("")
    lines.append("## Default")
    lines.append("")
    lines.append(f"A change matching no standard defaults to `{policy.default_engine}`.")
    lines.append("")
    lines.append("## The floor")
    lines.append("")
    lines.append(
        "The tool proposes; a human decides and runs the engine. A heuristic is "
        "never silently upgraded to verified."
    )
    lines.append("")
    return "\n".join(lines)


def build_scanner_rules(policy: Policy) -> dict:
    """Path globs per deterministic collector, for the collectors to consume."""
    rules: dict[str, list[str]] = {c: [] for c in sorted(COLLECTORS)}
    for s in policy.standards:
        if s.engine in COLLECTORS:
            for p in s.paths:
                if p not in rules[s.engine]:
                    rules[s.engine].append(p)
    return {"collectors": rules}


def build_routing(policy: Policy) -> dict:
    return {
        "default": policy.default_engine,
        "standards": [
            {"axis": s.axis, "paths": s.paths, "engine": s.engine} for s in policy.standards
        ],
        "undo_cost": [
            {"class": u.cls, "paths": u.paths, "escalate_to": u.escalate_to}
            for u in policy.undo_cost
        ],
    }


def build_catalog(policy: Policy, source_sha: str) -> dict:
    axes = sorted({s.axis for s in policy.standards})
    engines = sorted({s.engine for s in policy.standards})
    return {
        "project": policy.project,
        "policy_version": policy.version,
        "source_policy_sha256": source_sha,
        "axes": axes,
        "engines": engines,
        "undo_cost_classes": [u.cls for u in policy.undo_cost],
        "standard_count": len(policy.standards),
    }


def compile_policy(policy_path: Path, out_dir: Path) -> list[Path]:
    raw = policy_path.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    data = tomllib.loads(raw.decode("utf-8"))
    policy = parse_policy(data)

    out_dir.mkdir(parents=True, exist_ok=True)
    review_md = out_dir / "REVIEW.md"
    scanner = out_dir / "scanner-rules.json"
    routing = out_dir / "routing.json"
    catalog = out_dir / "catalog.json"

    review_md.write_text(render_review_md(policy, source_sha), encoding="utf-8")
    _dump_json(scanner, build_scanner_rules(policy))
    _dump_json(routing, build_routing(policy))
    _dump_json(catalog, build_catalog(policy, source_sha))
    return [review_md, scanner, routing, catalog]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile an Algol policy into review artifacts.")
    parser.add_argument("policy", type=Path, help="path to .algol/policy.toml")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory (default: .algol/compiled/ next to the policy)",
    )
    args = parser.parse_args(argv)

    policy_path: Path = args.policy
    if not policy_path.is_file():
        print(f"algol: policy not found: {policy_path}", file=sys.stderr)
        return 2
    out_dir: Path = args.out or (policy_path.parent / "compiled")

    try:
        written = compile_policy(policy_path, out_dir)
    except PolicyError as e:
        print(f"algol: policy error: {e}", file=sys.stderr)
        return 1
    except tomllib.TOMLDecodeError as e:
        print(f"algol: could not parse TOML: {e}", file=sys.stderr)
        return 1

    for p in written:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
