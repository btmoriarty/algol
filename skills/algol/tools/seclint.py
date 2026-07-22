#!/usr/bin/env python3
"""seclint: a deterministic security evidence collector.

The Algol-native security collector. Same contract as brevlint: it reviews
nothing and gates nothing; it walks the files it is given and emits evidence
rows (see evidence.py) for pattern-level security signals, each tagged with a
CWE. A row is a signal, not a proven defect; reconcile enters it as heuristic,
and the reasoning-heavy security judgment (business-logic flaws, attack-path
chaining) belongs to a model pass, not to this collector.

Rule set is a starter drawn from the CWE Top 25 and OWASP material, meant to
grow: hardcoded secrets, dangerous calls, unsafe deserialization, disabled TLS
verification, and weak hashing. Each rule carries a confidence, its own view of
how likely the match is a real problem.

Two hygiene features: matches for secret rules are masked, so a secret never
lands in the record; and a line carrying `seclint:ignore` is skipped, the
framework-false-positive escape hatch.

Floor: Python 3.11+, stdlib only (evidence.py, pathmatch.py are siblings).

Usage:
  python seclint.py FILE [FILE ...]
  python seclint.py --rules scanner-rules.json --root .
  python seclint.py FILE --rules-file extra-rules.json
Writes a JSON array of evidence rows to stdout, or to --out FILE. Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence import EvidenceRow, rows_to_json  # noqa: E402
from pathmatch import iter_matching_files  # noqa: E402

IGNORE_MARKER = "seclint:ignore"

# Each rule: id, regex, message, cwe, confidence, optional "unless" regex that
# suppresses the match on the same line, optional "mask" to redact the match.
DEFAULT_RULES: list[dict] = [
    {"id": "seclint/aws-access-key", "regex": r"AKIA[0-9A-Z]{16}",
     "message": "possible AWS access key id", "cwe": "CWE-798", "confidence": 0.9, "mask": True},
    {"id": "seclint/private-key", "regex": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
     "message": "private key material in source", "cwe": "CWE-798", "confidence": 0.95},
    {"id": "seclint/hardcoded-password",
     "regex": r"(?i)(?:password|passwd|pwd|secret|api_?key)\s*[=:]\s*['\"][^'\"]{3,}['\"]",
     "message": "possible hardcoded credential", "cwe": "CWE-798", "confidence": 0.5, "mask": True},
    {"id": "seclint/eval-exec", "regex": r"\b(?:eval|exec)\s*\(",
     "message": "dynamic code execution", "cwe": "CWE-95", "confidence": 0.5},
    {"id": "seclint/os-system", "regex": r"\bos\.system\s*\(",
     "message": "shell command via os.system", "cwe": "CWE-78", "confidence": 0.6},
    {"id": "seclint/subprocess-shell", "regex": r"shell\s*=\s*True",
     "message": "subprocess with shell=True", "cwe": "CWE-78", "confidence": 0.6},
    {"id": "seclint/pickle-load", "regex": r"\bpickle\.(?:load|loads)\s*\(",
     "message": "unsafe deserialization via pickle", "cwe": "CWE-502", "confidence": 0.6},
    {"id": "seclint/yaml-unsafe-load", "regex": r"\byaml\.load\s*\(", "unless": r"Safe",
     "message": "yaml.load without a safe loader", "cwe": "CWE-502", "confidence": 0.6},
    {"id": "seclint/tls-verify-disabled", "regex": r"verify\s*=\s*False",
     "message": "TLS verification disabled", "cwe": "CWE-295", "confidence": 0.7},
    {"id": "seclint/unverified-ssl", "regex": r"_create_unverified_context",
     "message": "unverified SSL context", "cwe": "CWE-295", "confidence": 0.8},
    {"id": "seclint/weak-hash", "regex": r"\bhashlib\.(?:md5|sha1)\s*\(",
     "message": "weak hash for security use", "cwe": "CWE-327", "confidence": 0.4},
]


def _compile(rules: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in rules:
        c = dict(r)
        c["_re"] = re.compile(r["regex"])
        c["_unless"] = re.compile(r["unless"]) if r.get("unless") else None
        out.append(c)
    return out


def _mask(text: str) -> str:
    text = text.strip()
    return (text[:4] + "...[redacted]") if len(text) > 4 else "[redacted]"


def lint_text(path: str, text: str, standard: str, rules: list[dict]) -> list[EvidenceRow]:
    compiled = _compile(rules)
    rows: list[EvidenceRow] = []
    for i, line in enumerate(text.split("\n"), start=1):
        if IGNORE_MARKER in line:
            continue
        for rule in compiled:
            if rule["_unless"] is not None and rule["_unless"].search(line):
                continue
            m = rule["_re"].search(line)
            if not m:
                continue
            matched = m.group(0)
            evidence = _mask(matched) if rule.get("mask") else matched
            rows.append(
                EvidenceRow(
                    rule_id=rule["id"],
                    file=path,
                    line=i,
                    col=m.start() + 1,
                    standard=standard,
                    confidence=float(rule["confidence"]),
                    evidence=evidence,
                    message=f"{rule['message']} ({rule['cwe']})",
                )
            )
    return rows


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _resolve_from_rules(rules_path: Path, root: Path) -> list[Path]:
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    globs = data.get("collectors", {}).get("seclint", [])
    return iter_matching_files(root, globs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="seclint: security evidence collector.")
    parser.add_argument("files", nargs="*", type=Path, help="files to scan")
    parser.add_argument("--standard", default="security", help="policy axis these rows map to")
    parser.add_argument("--rules", type=Path, default=None, help="scanner-rules.json from the compiler")
    parser.add_argument("--root", type=Path, default=Path("."), help="root to resolve --rules globs")
    parser.add_argument("--rules-file", type=Path, default=None, help="extra rules JSON to add to the defaults")
    parser.add_argument("--out", type=Path, default=None, help="write JSON here (default: stdout)")
    args = parser.parse_args(argv)

    rules = list(DEFAULT_RULES)
    if args.rules_file is not None:
        if not args.rules_file.is_file():
            print(f"seclint: rules-file not found: {args.rules_file}", file=sys.stderr)
            return 2
        rules.extend(json.loads(args.rules_file.read_text(encoding="utf-8")))

    targets: list[Path] = list(args.files)
    if args.rules is not None:
        if not args.rules.is_file():
            print(f"seclint: rules not found: {args.rules}", file=sys.stderr)
            return 2
        targets.extend(_resolve_from_rules(args.rules, args.root))
    if not targets:
        print("seclint: no files given (pass files, or --rules with --root)", file=sys.stderr)
        return 2

    rows: list[EvidenceRow] = []
    for path in targets:
        text = _read_text(path)
        if text is None:
            continue
        rows.extend(lint_text(str(path), text, args.standard, rules))

    output = rows_to_json(rows)
    if args.out is not None:
        args.out.write_text(output, encoding="utf-8")
        print(f"seclint: wrote {len(rows)} rows to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
