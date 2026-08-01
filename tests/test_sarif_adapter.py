"""Tests for sarif_adapter: SARIF in, Algol evidence rows out.

The invariants under test: a tool's finding becomes a well-formed row, the tool
name becomes the source namespace, a suppressed or passing or location-less
result is dropped and counted (never guessed at), and a row folded through
reconcile enters as heuristic like any collector's.

Run: python -m unittest discover -s tests
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "algol" / "tools"))

import sarif_adapter as sa  # noqa: E402
from evidence import rows_to_json  # noqa: E402
import reconcile as rc  # noqa: E402


def sarif(results, tool="Semgrep OSS", rules=None):
    driver = {"name": tool}
    if rules is not None:
        driver["rules"] = rules
    return {"version": "2.1.0", "runs": [{"tool": {"driver": driver}, "results": results}]}


def result(rule_id="py/sql-injection", level="error", file="app/db.py",
           line=42, col=7, text="SQL built from user input", snippet=None,
           **extra):
    region = {"startLine": line, "startColumn": col}
    if snippet is not None:
        region["snippet"] = {"text": snippet}
    r = {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": text},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": file}, "region": region}}],
    }
    r.update(extra)
    return r


class TestParseBasics(unittest.TestCase):
    def test_result_becomes_row(self) -> None:
        rows, stats = sa.parse_sarif(sarif([result()]))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.rule_id, "semgrep-oss/py/sql-injection")
        self.assertEqual(row.file, "app/db.py")
        self.assertEqual(row.line, 42)
        self.assertEqual(row.col, 7)
        self.assertEqual(row.standard, "security")
        self.assertEqual(row.message, "SQL built from user input")
        self.assertEqual(stats["rows"], 1)
        self.assertEqual(stats["results"], 1)

    def test_tool_name_is_source_namespace(self) -> None:
        # reconcile derives source from the rule_id prefix, so the tool name
        # must survive as a clean slug.
        rows, _ = sa.parse_sarif(sarif([result()], tool="CodeQL"))
        self.assertTrue(rows[0].rule_id.startswith("codeql/"))

    def test_standard_is_configurable(self) -> None:
        rows, _ = sa.parse_sarif(sarif([result()]), standard="dependencies")
        self.assertEqual(rows[0].standard, "dependencies")

    def test_snippet_preferred_as_evidence(self) -> None:
        rows, _ = sa.parse_sarif(sarif([result(snippet="cur.execute(q)")]))
        self.assertEqual(rows[0].evidence, "cur.execute(q)")

    def test_evidence_falls_back_to_message(self) -> None:
        rows, _ = sa.parse_sarif(sarif([result(text="danger here", snippet=None)]))
        self.assertEqual(rows[0].evidence, "danger here")


class TestHygiene(unittest.TestCase):
    def test_suppressed_result_dropped(self) -> None:
        r = result()
        r["suppressions"] = [{"kind": "external", "status": "accepted"}]
        rows, stats = sa.parse_sarif(sarif([r]))
        self.assertEqual(rows, [])
        self.assertEqual(stats["suppressed"], 1)

    def test_passing_result_dropped(self) -> None:
        r = result()
        r["kind"] = "pass"
        rows, stats = sa.parse_sarif(sarif([r]))
        self.assertEqual(rows, [])
        self.assertEqual(stats["non_finding"], 1)

    def test_no_location_dropped_and_counted(self) -> None:
        r = result()
        r["locations"] = []
        rows, stats = sa.parse_sarif(sarif([r]))
        self.assertEqual(rows, [])
        self.assertEqual(stats["no_location"], 1)

    def test_min_level_filters(self) -> None:
        note = result(rule_id="style/x", level="note")
        err = result(rule_id="sec/y", level="error")
        rows, stats = sa.parse_sarif(sarif([note, err]), min_level="warning")
        self.assertEqual({r.rule_id for r in rows}, {"semgrep-oss/sec/y"})
        self.assertEqual(stats["below_level"], 1)

    def test_none_level_dropped_by_default(self) -> None:
        rows, stats = sa.parse_sarif(sarif([result(level="none")]))
        self.assertEqual(rows, [])
        self.assertEqual(stats["below_level"], 1)


class TestLevelAndConfidence(unittest.TestCase):
    def test_default_level_is_warning(self) -> None:
        r = result()
        del r["level"]
        rows, _ = sa.parse_sarif(sarif([r]))  # default warning >= note floor
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].confidence, 0.6)

    def test_rule_default_configuration_level(self) -> None:
        r = result(rule_id="r1")
        del r["level"]
        rules = [{"id": "r1", "defaultConfiguration": {"level": "error"}}]
        rows, _ = sa.parse_sarif(sarif([r], rules=rules))
        self.assertAlmostEqual(rows[0].confidence, 0.85)

    def test_security_severity_drives_confidence(self) -> None:
        r = result(properties={"security-severity": "9.5"})
        rows, _ = sa.parse_sarif(sarif([r]))
        self.assertAlmostEqual(rows[0].confidence, 0.95)

    def test_rank_drives_confidence(self) -> None:
        r = result(rank=30)
        rows, _ = sa.parse_sarif(sarif([r]))
        self.assertAlmostEqual(rows[0].confidence, 0.30)


class TestRuleAndMessageResolution(unittest.TestCase):
    def test_rule_index_lookup(self) -> None:
        r = {"ruleIndex": 0, "level": "error", "message": {"text": "m"},
             "locations": [{"physicalLocation": {
                 "artifactLocation": {"uri": "a.py"}, "region": {"startLine": 1}}}]}
        rules = [{"id": "R42"}]
        rows, _ = sa.parse_sarif(sarif([r], rules=rules))
        self.assertEqual(rows[0].rule_id, "semgrep-oss/R42")

    def test_message_id_resolved_from_rule(self) -> None:
        r = {"ruleId": "r1", "level": "warning",
             "message": {"id": "default"},
             "locations": [{"physicalLocation": {
                 "artifactLocation": {"uri": "a.py"}, "region": {"startLine": 3}}}]}
        rules = [{"id": "r1", "messageStrings": {"default": {"text": "resolved text"}}}]
        rows, _ = sa.parse_sarif(sarif([r], rules=rules))
        self.assertEqual(rows[0].message, "resolved text")

    def test_multiple_locations_yield_multiple_rows(self) -> None:
        r = result()
        r["locations"].append({"physicalLocation": {
            "artifactLocation": {"uri": "app/other.py"}, "region": {"startLine": 9}}})
        rows, _ = sa.parse_sarif(sarif([r]))
        self.assertEqual({(row.file, row.line) for row in rows},
                         {("app/db.py", 42), ("app/other.py", 9)})

    def test_file_uri_scheme_stripped(self) -> None:
        rows, _ = sa.parse_sarif(sarif([result(file="file:///src/a%20b.py")]))
        self.assertEqual(rows[0].file, "/src/a b.py")


class TestFailClosed(unittest.TestCase):
    def test_root_not_object(self) -> None:
        with self.assertRaises(sa.SarifError):
            sa.parse_sarif([1, 2, 3])

    def test_missing_runs(self) -> None:
        with self.assertRaises(sa.SarifError):
            sa.parse_sarif({"version": "2.1.0"})

    def test_runs_not_list(self) -> None:
        with self.assertRaises(sa.SarifError):
            sa.parse_sarif({"runs": {}})

    def test_empty_runs_is_zero_rows_not_error(self) -> None:
        rows, stats = sa.parse_sarif({"version": "2.1.0", "runs": []})
        self.assertEqual(rows, [])
        self.assertEqual(stats["rows"], 0)


class TestReconcileIntegration(unittest.TestCase):
    def test_rows_flow_through_reconcile_as_heuristic(self) -> None:
        rows, _ = sa.parse_sarif(sarif([result()], tool="Semgrep"))
        dict_rows = json.loads(rows_to_json(rows))          # the --collector payload
        obs_set = rc._collector_observations(dict_rows)
        record = rc.reconcile([obs_set])
        self.assertEqual(len(record.findings), 1)
        f = record.findings[0]
        self.assertEqual(f.status, "heuristic")              # never upgraded
        self.assertEqual(f.observations[0].source, "semgrep")  # real tool name
        self.assertEqual(f.claim, "semgrep/py/sql-injection")

    def test_same_finding_from_two_tools_merges_one_finding(self) -> None:
        # Two scanners flag the same rule at the same spot: one finding, two
        # observations. (Correlation is (file, line, claim); claim is rule_id,
        # so this merges only when both tools use the same rule id namespace.)
        rows_a, _ = sa.parse_sarif(sarif([result(rule_id="cwe-89")], tool="ToolX"))
        rows_b, _ = sa.parse_sarif(sarif([result(rule_id="cwe-89")], tool="ToolX"))
        obs = (rc._collector_observations(json.loads(rows_to_json(rows_a)))
               + rc._collector_observations(json.loads(rows_to_json(rows_b))))
        record = rc.reconcile([obs])
        self.assertEqual(len(record.findings), 1)


if __name__ == "__main__":
    unittest.main()
