#!/usr/bin/env python3
"""sarif_adapter: turn any tool's SARIF output into Algol evidence rows.

SARIF is the format CodeQL, Semgrep, bandit, gitleaks, ruff, and most scanners
already emit. This adapter reads a SARIF log and produces the same evidence-row
shape the native collectors emit, so reconcile folds a standard tool's findings
into the record through the existing --collector path, with no bespoke code per
tool. The record's source becomes the real tool name (semgrep, codeql, ...),
taken from the SARIF driver.

The honest boundary holds. A SARIF result is a tool signal, not a proof, so its
row enters reconcile as heuristic like any collector's. The adapter never
invents a location, a rule, or a verdict: a result with no physical location is
skipped and counted, not guessed at.

Two hygiene features, mirroring seclint. A result the tool already suppressed
(a non-empty `suppressions` array) is dropped, so a baseline decision is not
re-litigated in the record. A result whose `kind` says it did not fire (`pass`,
`notApplicable`) is dropped, so a passing check never lands as a finding.

Floor: Python 3.11+, stdlib only (evidence.py is a sibling module).

Usage:
  python sarif_adapter.py results.sarif [more.sarif ...] \
      [--standard security] [--min-level note] [--out rows.json]

Then feed the rows to reconcile like any collector:
  python reconcile.py --collector rows.json --out .algol/record.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import EvidenceRow, rows_to_json  # noqa: E402

# SARIF severity levels, lowest to highest. "none" is informational.
_LEVEL_RANK = {"none": 0, "note": 1, "warning": 2, "error": 3}
# The SARIF default when neither the result nor the rule states a level.
_DEFAULT_LEVEL = "warning"
# A level with no numeric signal maps to this confidence. reconcile enters every
# row as heuristic regardless; the number only preserves the tool's own emphasis.
_LEVEL_CONFIDENCE = {"none": 0.3, "note": 0.4, "warning": 0.6, "error": 0.85}
# Result kinds that mean the check did not raise a finding.
_NON_FINDING_KINDS = {"pass", "notApplicable"}

_EVIDENCE_MAX = 200


class SarifError(ValueError):
    """Malformed SARIF. Raised with a named reason so a bad file fails closed."""


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "sarif"


def _clean_uri(uri: str) -> str:
    if not uri:
        return ""
    u = unquote(uri)
    if u.startswith("file://"):
        u = u[len("file://"):]
    if u.startswith("./"):
        u = u[2:]
    return u


def _rule_index(driver: dict) -> tuple[list[dict], dict[str, dict]]:
    """Map rules by position (for ruleIndex) and by id (for ruleId)."""
    rules = driver.get("rules") or []
    by_id: dict[str, dict] = {}
    for r in rules:
        if isinstance(r, dict) and r.get("id"):
            by_id[str(r["id"])] = r
    return rules, by_id


def _lookup_rule(result: dict, rules: list[dict], by_id: dict[str, dict]) -> dict:
    idx = result.get("ruleIndex")
    if isinstance(idx, int) and 0 <= idx < len(rules) and isinstance(rules[idx], dict):
        return rules[idx]
    rid = result.get("ruleId")
    if rid is None and isinstance(result.get("rule"), dict):
        rid = result["rule"].get("id")
    if rid is not None:
        return by_id.get(str(rid), {})
    return {}


def _rule_id(result: dict, rule: dict) -> str:
    rid = result.get("ruleId")
    if rid is None and isinstance(result.get("rule"), dict):
        rid = result["rule"].get("id")
    if rid is None:
        rid = rule.get("id")
    return str(rid) if rid is not None else "unknown"


def _level(result: dict, rule: dict) -> str:
    lvl = result.get("level")
    if not lvl:
        cfg = rule.get("defaultConfiguration") or {}
        lvl = cfg.get("level")
    return lvl if lvl in _LEVEL_RANK else _DEFAULT_LEVEL


def _confidence(result: dict, level: str) -> float:
    rank = result.get("rank")
    if isinstance(rank, (int, float)) and rank >= 0:
        return max(0.0, min(1.0, float(rank) / 100.0))
    props = result.get("properties") or {}
    sev = props.get("security-severity")
    if sev is not None:
        try:
            return max(0.0, min(1.0, float(sev) / 10.0))
        except (TypeError, ValueError):
            pass
    return _LEVEL_CONFIDENCE.get(level, 0.5)


def _message_text(result: dict, rule: dict) -> str:
    m = result.get("message")
    if isinstance(m, dict):
        if m.get("text"):
            return str(m["text"]).strip()
        mid = m.get("id")
        if mid:
            strings = rule.get("messageStrings") or {}
            entry = strings.get(mid)
            if isinstance(entry, dict) and entry.get("text"):
                return str(entry["text"]).strip()  # argument substitution skipped, best-effort
    elif isinstance(m, str):
        return m.strip()
    return ""


def _physical_locations(result: dict) -> list[tuple[str, int, int, str]]:
    """Return (file, line, col, snippet) per physical location, in document order."""
    out: list[tuple[str, int, int, str]] = []
    for loc in result.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        phys = loc.get("physicalLocation")
        if not isinstance(phys, dict):
            continue
        art = phys.get("artifactLocation") or {}
        uri = _clean_uri(str(art.get("uri", "")))
        if not uri:
            continue
        region = phys.get("region") or {}
        line = region.get("startLine")
        line = int(line) if isinstance(line, int) and line > 0 else 1
        col = region.get("startColumn")
        col = int(col) if isinstance(col, int) and col > 0 else 1
        snippet = ""
        snip = region.get("snippet") or {}
        if isinstance(snip, dict) and snip.get("text"):
            snippet = str(snip["text"]).strip()
        out.append((uri, line, col, snippet))
    return out


def _suppressed(result: dict) -> bool:
    sup = result.get("suppressions")
    return isinstance(sup, list) and len(sup) > 0


def _one_line(text: str, limit: int = _EVIDENCE_MAX) -> str:
    flat = " ".join(text.split())
    return flat[:limit]


def parse_sarif(doc: dict, standard: str = "security", min_level: str = "note") -> tuple[list[EvidenceRow], dict]:
    """Convert a parsed SARIF document into evidence rows.

    Returns (rows, stats). stats counts what was dropped and why, so a silent
    truncation never reads as full coverage. Fails closed on a malformed doc.
    """
    if not isinstance(doc, dict):
        raise SarifError("SARIF root is not an object")
    runs = doc.get("runs")
    if runs is None:
        raise SarifError("SARIF has no 'runs' key")
    if not isinstance(runs, list):
        raise SarifError("SARIF 'runs' is not a list")
    if min_level not in _LEVEL_RANK:
        raise SarifError(f"unknown --min-level: {min_level}")

    floor = _LEVEL_RANK[min_level]
    rows: list[EvidenceRow] = []
    stats = {"results": 0, "rows": 0, "suppressed": 0,
             "below_level": 0, "no_location": 0, "non_finding": 0}

    for run in runs:
        if not isinstance(run, dict):
            continue
        driver = ((run.get("tool") or {}).get("driver") or {})
        tool = _slug(driver.get("name", "sarif"))
        rules, by_id = _rule_index(driver)

        for result in run.get("results") or []:
            if not isinstance(result, dict):
                continue
            stats["results"] += 1

            kind = result.get("kind")
            if isinstance(kind, str) and kind in _NON_FINDING_KINDS:
                stats["non_finding"] += 1
                continue
            if _suppressed(result):
                stats["suppressed"] += 1
                continue

            rule = _lookup_rule(result, rules, by_id)
            level = _level(result, rule)
            if _LEVEL_RANK[level] < floor:
                stats["below_level"] += 1
                continue

            locations = _physical_locations(result)
            if not locations:
                stats["no_location"] += 1
                continue

            rid = _rule_id(result, rule)
            rule_id = f"{tool}/{rid}"
            message = _message_text(result, rule)
            confidence = _confidence(result, level)

            for uri, line, col, snippet in locations:
                evidence = snippet or _one_line(message) or rid
                rows.append(EvidenceRow(
                    rule_id=rule_id,
                    file=uri,
                    line=line,
                    standard=standard,
                    confidence=confidence,
                    evidence=evidence,
                    message=message,
                    col=col,
                ))

    stats["rows"] = len(rows)
    return rows, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="convert SARIF into Algol evidence rows.")
    parser.add_argument("files", nargs="+", type=Path, help="SARIF file(s) to convert")
    parser.add_argument("--standard", default="security", help="policy axis these rows map to")
    parser.add_argument("--min-level", default="note", choices=sorted(_LEVEL_RANK),
                        help="drop results below this SARIF level (default: note)")
    parser.add_argument("--out", type=Path, default=None, help="write JSON here (default: stdout)")
    args = parser.parse_args(argv)

    all_rows: list[EvidenceRow] = []
    total = {"results": 0, "rows": 0, "suppressed": 0,
             "below_level": 0, "no_location": 0, "non_finding": 0}
    for fpath in args.files:
        if not fpath.is_file():
            print(f"sarif_adapter: file not found: {fpath}", file=sys.stderr)
            return 2
        try:
            doc = json.loads(fpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"sarif_adapter: {fpath}: not valid JSON: {exc}", file=sys.stderr)
            return 2
        try:
            rows, stats = parse_sarif(doc, standard=args.standard, min_level=args.min_level)
        except SarifError as exc:
            print(f"sarif_adapter: {fpath}: {exc}", file=sys.stderr)
            return 2
        all_rows.extend(rows)
        for k in total:
            total[k] += stats[k]

    payload = rows_to_json(all_rows)
    if args.out is not None:
        args.out.write_text(payload, encoding="utf-8")
        where = str(args.out)
    else:
        sys.stdout.write(payload)
        where = "stdout"

    dropped = total["suppressed"] + total["below_level"] + total["no_location"] + total["non_finding"]
    msg = (f"sarif_adapter: wrote {total['rows']} rows to {where} "
           f"from {total['results']} results ({dropped} dropped: "
           f"{total['suppressed']} suppressed, {total['below_level']} below-level, "
           f"{total['no_location']} no-location, {total['non_finding']} non-finding)")
    print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
