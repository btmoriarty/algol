# Algol v1.1 task 3: the DIY comparison, build brief and harness

Draft for review, not yet applied to the repo. This task compares a representative DIY result merger with Algol's reconciliation and record model. Both arms receive the same controlled engine-output fixtures. The harness measures structured governance behavior, not review quality, and covers the merge and record layer only.

Validation run, 2026-07-23: the three tests in this draft passed in the stated throwaway environment with task 1 applied; the full repository suite has not yet been reported here. The engine outputs are controlled fixtures rather than review runs.

## What changed across drafts

Draft 1 was rigged: its Arm A treated a missing confidence as `1.0`, so the "confidence 1.0" headline was manufactured by the baseline, not by the shared engine outputs. Draft 2 fixed the fairness but faked the report, writing mostly hard-coded conclusions to a temp file that teardown deleted. This version uses a defender-oriented Arm A, exercises reconciliation through its public CLI, derives each comparison result from the executed harness, and writes the complete result as structured JSON through a reusable command.

## The honesty problem, stated first

This harness is only worth anything if Arm A is the strongest implementation still describable as a small DIY merger. I built Arm A and I am invested in Algol, which is a conflict. Arm A should get a review from someone whose instinct is to defend the DIY approach before this is used publicly. The finding is narrow on purpose: a competent team can rebuild these behaviors; the comparison identifies which behaviors Algol supplies through one schema and tests together, and what a DIY implementation would need to add.

## Design

Both arms are fed the identical engine outputs. Arm A preserves each source observation but has no shared evidence-tier vocabulary and no structured disposition record. Algol is exercised through the public `reconcile.py` CLI and the record library the walkthrough uses for dispositions (`record.py`). Every observed value in the report is derived from running the two arms; only the stated limitation text is a fixed caveat. Outcomes are checked directly, so no model grader is needed: reviewing is held constant, only governance varies.

## What the run actually shows

Scenario: a scanner hit (`seclint/os-system`, confidence 0.6) and a model-panel `[V]` anchor land on the same claim at `src/auth.py:3`.

- **No normalized evidence tier.** Arm A preserves both source observations but has no shared field that distinguishes a scanner signal from model-panel corroboration. Algol records the scanner observation as `heuristic` and the model-panel observation as `model_corroborated`. Neither observation is `verified`.
- **No native structured disposition record.** Arm A's merge artifact has no structured fields for disposition state, rationale, actor, or reopen conditions. A team could store these elsewhere, such as PR comments or a `waivers.json`, or extend the artifact. Algol includes them in the record and preserves them across serialization, with the finding's tier unchanged.

The comparison does not claim that a DIY implementation cannot provide these behaviors. It identifies which behaviors Algol supplies through one schema and tests together, and what a DIY implementation would need to add.

## Files to add

Three files under `tests/`: the fair Arm A, a report generator whose evaluators the tests reuse, and the tests. Arm A groups by `(file, line, claim)`, preserves each source observation, and keeps a missing confidence as `None`.

### `tests/diy/arm_a_merge.py` (fair Arm A, pending a defender's review)

```python
"""Representative DIY merge.

Groups equivalent findings and preserves each source observation. It does not
normalize observations into a shared evidence-tier vocabulary and does not
provide a structured disposition record.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


def _read_json(path: str) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def merge(collector_paths: list[str], gauntlet_path: str | None = None) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, str], dict[str, Any]] = {}

    def add(*, file, line, claim, source, confidence, message, evidence):
        key = (file, line, claim)
        group = groups.setdefault(key, {"file": file, "line": line, "claim": claim, "observations": []})
        group["observations"].append(
            {"source": source, "confidence": confidence, "message": message, "evidence": evidence})

    for path in collector_paths:
        for row in _read_json(path):
            c = row.get("confidence")
            add(file=row["file"], line=row["line"], claim=row["rule_id"],
                source=row["rule_id"].split("/", 1)[0],
                confidence=float(c) if c is not None else None,
                message=row.get("message", ""), evidence=row.get("evidence", ""))
    if gauntlet_path:
        for f in _read_json(gauntlet_path).get("findings", []):
            c = f.get("confidence")
            add(file=f["file"], line=f["line"], claim=f["claim"], source="gauntlet",
                confidence=float(c) if c is not None else None,
                message=f.get("message", ""), evidence=f.get("evidence", ""))
    return list(groups.values())
```

### `tests/diy/run_comparison.py` (the report generator; evaluators shared with the tests)

```python
"""Derive the Algol vs DIY comparison from an executed run and write it as JSON.

Usage: python3 tests/diy/run_comparison.py [--out PATH]   (default: stdout)
Every observed value below is derived from running the two arms; only the stated
limitation text is a fixed caveat. Requires the model_corroborated tier (v1.1 task 1).
"""
from __future__ import annotations
import argparse, importlib.util, json, subprocess, sys, tempfile, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOLS = REPO / "skills" / "algol" / "tools"

SEC = [{"rule_id": "seclint/os-system", "file": "src/auth.py", "line": 3, "standard": "security",
        "confidence": 0.6, "evidence": "os.system(", "message": "shell command via os.system", "col": 1}]
GAUNT = {"verdict": "NO-GO", "findings": [
    {"file": "src/auth.py", "line": 3, "claim": "seclint/os-system",
     "evidence": "[V src/auth.py:3] reachable with attacker-controlled input", "message": "confirmed reachable"}],
    "conditions": ["reopens if the call becomes unreachable"]}


def _load_record():
    spec = importlib.util.spec_from_file_location("algol_record_diy_gen", TOOLS / "record.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def run_arms():
    d = Path(tempfile.mkdtemp())
    (d / "sec.json").write_text(json.dumps(SEC))
    (d / "gaunt.json").write_text(json.dumps(GAUNT))
    sys.path.insert(0, str(HERE))
    import arm_a_merge
    arm_a = arm_a_merge.merge([str(d / "sec.json")], str(d / "gaunt.json"))
    out = d / "record.json"
    r = subprocess.run([sys.executable, str(TOOLS / "reconcile.py"), "--collector", str(d / "sec.json"),
                        "--gauntlet", str(d / "gaunt.json"), "--out", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("reconcile failed: " + r.stderr)
    return arm_a, out, d


def evaluate_evidence_mode(arm_a, algol_record):
    f = algol_record["findings"][0]
    return {
        "mode": "normalized_evidence_tier",
        "arm_a": {
            "observations": sorted((o["source"], o["confidence"]) for o in arm_a[0]["observations"]),
            "has_normalized_tier": any("tier" in o for o in arm_a[0]["observations"]),
        },
        "algol": {
            "observations": sorted((o["source"], o["tier"]) for o in f["observations"]),
            "status": f["status"],
        },
        "native_capability": {
            "arm_a": any("tier" in o for o in arm_a[0]["observations"]),
            "algol": all("tier" in o for o in f["observations"]),
        },
        "limitation": "Arm A could add a tier vocabulary",
    }


def evaluate_disposition_mode(arm_a, algol_record_path, recmod):
    rr = recmod.Record.from_json(Path(algol_record_path).read_text())
    recmod.set_disposition(rr, rr.findings[0].id, "accept", "reachable only in a dev path",
                           reopens_if=["if it reaches a prod path"], by="brian")
    back = recmod.Record.from_json(rr.to_json())
    d2 = back.findings[0].disposition
    return {
        "mode": "native_structured_disposition",
        "arm_a": {"has_disposition": "disposition" in arm_a[0]},
        "algol": {"state": d2.state, "rationale": d2.rationale, "reopens_if": d2.reopens_if,
                  "by": d2.by, "status_after_disposition": back.findings[0].status},
        "native_capability": {"arm_a": "disposition" in arm_a[0], "algol": d2 is not None},
        "limitation": "a team could store decisions elsewhere (PR comments, waivers.json) or extend the artifact",
    }


def build_report():
    arm_a, rec_path, d = run_arms()
    try:
        record = json.loads(rec_path.read_text())
        recmod = _load_record()
        return [evaluate_evidence_mode(arm_a, record),
                evaluate_disposition_mode(arm_a, rec_path, recmod)]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="derive the Algol vs DIY comparison result")
    p.add_argument("--out", type=Path, default=None, help="write JSON here (default: stdout)")
    args = p.parse_args(argv)
    report = json.dumps(build_report(), indent=2)
    if args.out is not None:
        args.out.write_text(report + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `tests/test_diy_comparison.py`

```python
"""A controlled comparison of two governance approaches, same engine outputs.

Arm A is a representative DIY merge (tests/diy/arm_a_merge.py). Algol is exercised
through its public reconcile CLI and the record library the walkthrough uses. Both
arms receive identical controlled engine-output fixtures; these are fixtures, not
review runs. The tests and the report share the same evaluators in run_comparison.py.
Covers the merge and record layer only. Requires the model_corroborated tier (task 1).
"""
from __future__ import annotations
import json, sys, shutil, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIY = Path(__file__).resolve().parent / "diy"


def remove_module(name):
    sys.modules.pop(name, None)


class TestDIYComparison(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(DIY))
        self.addCleanup(lambda: str(DIY) in sys.path and sys.path.remove(str(DIY)))
        for name in ("arm_a_merge", "run_comparison", "algol_record_diy_gen"):
            self.addCleanup(remove_module, name)
        import run_comparison
        self.gen = run_comparison

    def run_arms(self):
        arm_a, rec_path, d = self.gen.run_arms()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return arm_a, json.loads(Path(rec_path).read_text()), rec_path

    def test_mode1_normalized_evidence_tier(self):
        arm_a, rec, _ = self.run_arms()
        self.assertEqual(len(arm_a), 1)
        self.assertEqual(sorted((o["source"], o["confidence"]) for o in arm_a[0]["observations"]),
                         [("gauntlet", None), ("seclint", 0.6)])
        self.assertFalse(any("tier" in o for o in arm_a[0]["observations"]))
        self.assertEqual(len(rec["findings"]), 1)
        f = rec["findings"][0]
        self.assertEqual((f["claim"], f["file"], f["line"]), ("seclint/os-system", "src/auth.py", 3))
        self.assertEqual(sorted((o["source"], o["tier"]) for o in f["observations"]),
                         [("gauntlet", "model_corroborated"), ("seclint", "heuristic")])
        self.assertNotIn("verified", [o["tier"] for o in f["observations"]])
        self.assertEqual(f["status"], "model_corroborated")

    def test_mode2_native_structured_disposition(self):
        arm_a, _, rec_path = self.run_arms()
        for field in ("disposition", "rationale", "reopens_if", "by"):
            self.assertNotIn(field, arm_a[0])
        recmod = self.gen._load_record()
        res = self.gen.evaluate_disposition_mode(arm_a, rec_path, recmod)["algol"]
        self.assertEqual((res["state"], res["rationale"], res["reopens_if"], res["by"], res["status_after_disposition"]),
                         ("accept", "reachable only in a dev path", ["if it reaches a prod path"], "brian", "model_corroborated"))
        rr = recmod.Record.from_json(Path(rec_path).read_text())
        disp = recmod.set_disposition(rr, rr.findings[0].id, "accept", "x", reopens_if=["y"], by="z")
        self.assertIsInstance(disp, recmod.Disposition)

    def test_report_derived_from_execution(self):
        report = self.gen.build_report()
        modes = {m["mode"]: m for m in report}
        self.assertEqual(set(modes), {"normalized_evidence_tier", "native_structured_disposition"})
        ev = modes["normalized_evidence_tier"]
        self.assertEqual(ev["native_capability"], {"arm_a": False, "algol": True})
        self.assertEqual(ev["algol"]["observations"],
                         [("gauntlet", "model_corroborated"), ("seclint", "heuristic")])
        self.assertFalse(ev["arm_a"]["has_normalized_tier"])
        di = modes["native_structured_disposition"]
        self.assertEqual(di["native_capability"], {"arm_a": False, "algol": True})
        self.assertEqual(di["algol"]["status_after_disposition"], "model_corroborated")
        self.assertTrue(all("limitation" in m for m in report))


if __name__ == "__main__":
    unittest.main()
```

## Modes still to add (each needs a defender-designed Arm A)

- **Scrutiny by accident.** Compares routing, not merge behavior. A reasonable Arm A includes a fixed command or a simple path conditional. Compare a fixed DIY rule, a modest DIY path conditional, and Algol's policy and undo-cost router. Publish a tie if the modest conditional handles the planted migration; the difference may be standardization, policy compilation, explainable reasons, or reuse, not the bare possibility of routing.
- **Two sources of truth.** A maintenance property: the bar in CLAUDE.md and the scanner config drift; Algol compiles both from one policy input. A DIY defender may generate one artifact from the other, a legitimate near-tie. Report the implementation cost rather than declare it equivalent to adopting all of Algol.
- **A produced finding dropped.** Excluded until Algol holds an expected-engine manifest and detects an absent required result. Today it does not, so the mode would compare a broken Arm A with a correct Algol.

## Honesty guards (the point, not a footnote)

- Arm A should be the strongest implementation still reasonably describable as a small DIY merger. A DIY-defender reviews it before public use.
- Publish the ties. Where a fair Arm A matches a mode, or where matching it means reimplementing an Algol mechanism, say so.
- Name the cost. Algol adds a policy file and a per-change loop; a reader judges whether their project clears the bar.
- This is a governance comparison, not a claim that Algol reviews better. Reviewing is held constant.

## Scope, stated plainly

These tests compare a small DIY result merger with Algol's reconciliation and record model. `CLAUDE.md` is not created, read, or tested; no policy compilation or routing is compared. The broader question, whether Algol is better than the complete review engine plus CLAUDE.md plus small script workflow, can be answered only after the policy and routing modes are added.

## Revised acceptance criteria

1. Arm A receives a defender's review before public use.
2. Missing confidence is never interpreted as `1.0`, and the test asserts the confidence values.
3. Arm A preserves source-specific observations and uses the grouping key `(file, line, claim)`.
4. Both arms receive semantically identical fixture records.
5. Algol is exercised through public commands or the documented library surface.
6. The evidence test checks the exact finding identity, sources, and tiers.
7. The disposition test checks state, rationale, reopen condition, actor, and unchanged status after reload.
8. Claims are limited to the merge and record layer until CLAUDE.md, policy compilation, and routing are tested.
9. A reusable report command derives a machine-readable result from the executed outcomes for every mode. It writes the result to stdout or a requested persistent path and includes the observed values and stated limitations. The tests call the same evaluators.
10. The missing-output mode is excluded unless Algol can detect an expected but absent engine result.
11. Public documentation states that the engine outputs are controlled fixtures.
12. The full suite passes from a clean checkout after tasks 1 and 2.

## Out of scope

Modes that turn on model-review quality rather than governance; those need a blind grader. Running the model reviewers for real (held constant as fixtures here).
