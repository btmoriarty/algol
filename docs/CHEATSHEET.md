# Algol cheat sheet

v0.16.0. Algol governs what gets reviewed and records what was
decided. A heuristic is never upgraded to verified without notice.

| Step | Command | What you get |
|------|---------|--------------|
| Start | `init.py --root . --project NAME --compile` | The strong starter policy (auth, migrations, money, public API, infra, CI already routed) plus compiled artifacts |
| Compile policy | `compile_policy.py .algol/policy.toml` | REVIEW.md, scanner-rules.json, routing.json, catalog.json |
| Gate a change | `gate.py --base main` | Route + collect the changed files + reconcile into the record: new vs carried, prior dispositions preserved. Silent on a low-risk diff |
| Route a change | `router.py --routing routing.json --changed <paths>` | A recommendation per matched standard, deep-tier escalation on undo-cost. `--format commands` for copy-pasteable commands, silent on low-risk |
| Collect (security/brevity) | `seclint.py` / `brevlint.py --rules scanner-rules.json --root .` | Deterministic evidence rows (CWE-tagged for seclint, secrets masked). The silent floor: never a peer of a real engine's finding |
| Ingest SARIF | `sarif_adapter.py results.sarif --out rows.json` | Any standard tool (CodeQL, Semgrep, bandit, gitleaks) as evidence rows, tool name as source |
| Policy check | `policy_review.py prompt --review REVIEW.md --changed <files>` | A model-pass prompt; feed it to a model, then `ingest` the result |
| Reconcile | `reconcile.py --collector rows.json [--gauntlet run.json] --out record.json` | One record, verified kept distinct from heuristic |
| Raise to verified | `verify.py prompt --finding <id>`, then `verify.py ingest out.json --finding <id>` | Raise one finding via the verifier: uat FAIL to verified, gauntlet to model_corroborated. Never invents a tier |
| Deep tier | route to gauntlet, then `reconcile.py --gauntlet run-record.json` | Its verdict and conditions fold into the record |
| Guard and report | wire `hooks.py` via hooks.example.json | A reversibility guard before a write, a collector report after |

All tools are stdlib-only Python 3.11+. Full flags: `--help` on any tool, or the
`references/` doc for each component.

Your data: your own repository. Policy and the record are plain files under
version control. Algol sends nothing on its own.

The floor: the tool proposes; a human decides and runs the engine. No finding
originates in Algol except the deterministic collector rows.
