"""Tests for seclint, the security collector."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import seclint  # noqa: E402


def ids(rows):
    return {r.rule_id for r in rows}


def lint(text):
    return seclint.lint_text("f.py", text, "security", seclint.DEFAULT_RULES)


class TestRules(unittest.TestCase):
    def test_aws_key_detected_and_masked(self) -> None:
        rows = lint("key = 'AKIAIOSFODNN7EXAMPLE'\n")
        self.assertIn("seclint/aws-access-key", ids(rows))
        row = next(r for r in rows if r.rule_id == "seclint/aws-access-key")
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", row.evidence)  # masked
        self.assertIn("redacted", row.evidence)

    def test_hardcoded_password_masked(self) -> None:
        rows = lint('password = "hunter2secret"\n')
        self.assertIn("seclint/hardcoded-password", ids(rows))
        row = next(r for r in rows if r.rule_id == "seclint/hardcoded-password")
        self.assertNotIn("hunter2secret", row.evidence)

    def test_message_carries_cwe(self) -> None:
        rows = lint("os.system(cmd)\n")
        row = next(r for r in rows if r.rule_id == "seclint/os-system")
        self.assertIn("CWE-78", row.message)
        self.assertEqual(row.standard, "security")

    def test_yaml_unless_suppresses_safe_loader(self) -> None:
        self.assertIn("seclint/yaml-unsafe-load", ids(lint("data = yaml.load(f)\n")))
        self.assertNotIn(
            "seclint/yaml-unsafe-load",
            ids(lint("data = yaml.load(f, Loader=yaml.SafeLoader)\n")),
        )

    def test_ignore_marker_skips_line(self) -> None:
        rows = lint("os.system(cmd)  # seclint:ignore\n")
        self.assertEqual(rows, [])

    def test_verify_false_and_pickle(self) -> None:
        self.assertIn("seclint/tls-verify-disabled", ids(lint("requests.get(u, verify=False)\n")))
        self.assertIn("seclint/pickle-load", ids(lint("obj = pickle.loads(blob)\n")))

    def test_clean_code_no_rows(self) -> None:
        self.assertEqual(lint("x = compute(a, b)\nreturn x\n"), [])

    def test_confidence_is_per_rule(self) -> None:
        row = next(r for r in lint("h = hashlib.md5(b)\n") if r.rule_id == "seclint/weak-hash")
        self.assertEqual(row.confidence, 0.4)


class TestCli(unittest.TestCase):
    def test_rules_file_extends_defaults(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "code.py"
            target.write_text("banned_call()\n", encoding="utf-8")
            extra = root / "extra.json"
            extra.write_text(
                json.dumps([{"id": "seclint/banned", "regex": r"banned_call",
                             "message": "banned", "cwe": "CWE-000", "confidence": 1.0}]),
                encoding="utf-8",
            )
            out = root / "rows.json"
            code = seclint.main(["--rules-file", str(extra), str(target), "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertIn("seclint/banned", out.read_text())

    def test_no_files_errors(self) -> None:
        self.assertEqual(seclint.main([]), 2)


if __name__ == "__main__":
    unittest.main()
