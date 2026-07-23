# Algol cheat sheet

v0.10.0. Algol governs what gets reviewed and records what was
decided. A heuristic is never silently upgraded to verified.

| Step | Command | What you get |
|------|---------|--------------|
| Compile policy | `compile_policy.py .algol/policy.toml` | REVIEW.md, scanner-rules.json, routing.json, catalog.json |
| Route a change | `router.py --routing routing.json --changed <paths>` | A recommendation per matched standard, deep-tier escalation on undo-cost. Recommends; you run it |
| Collect (brevity) | `brevlint.py --rules scanner-rules.json --root .` | Deterministic style and brevity evidence rows |
| Collect (security) | `seclint.py --rules scanner-rules.json --root .` | CWE-tagged security evidence rows, secrets masked |
| Policy check | `policy_review.py prompt --review REVIEW.md --changed <files>` | A model-pass prompt; feed it to a model, then `ingest` the result |
| Reconcile | `reconcile.py --collector rows.json [--gauntlet run.json] --out record.json` | One record, verified kept distinct from heuristic |
| Deep tier | route to gauntlet, then `reconcile.py --gauntlet run-record.json` | Its verdict and Conflict Ledger fold into the record |
| Guard and report | wire `hooks.py` via hooks.example.json | A reversibility guard before a write, a collector report after |

All tools are stdlib-only Python 3.11+. Full flags: `--help` on any tool, or the
`references/` doc for each component.

Your data: your own repository. Policy and the record are plain files under
version control. Algol sends nothing on its own.

The floor: the tool proposes; a human decides and runs the engine. No finding
originates in Algol except the deterministic collector rows.
