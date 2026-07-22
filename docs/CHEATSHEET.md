# Algol cheat sheet

Provisional (v0.0.1 scaffold). Commands are not built yet; this is the intended shape, kept honest so it can be checked against what ships.

Ethos: Algol reviews nothing. It governs what gets reviewed and records what was decided. A heuristic is never silently upgraded to verified.

| Mode | Say something like | What you get |
|------|--------------------|--------------|
| Set policy | "set up review policy for this repo" | A starter `.algol/policy.toml`, path-scoped, compiled into review instructions, scanner rules, and routing criteria |
| Route a change | "how should this change be reviewed" | A recommendation (skip, a collector, policy-review, `/code-review`, or `ultra`), with the undo-cost that drove it. It recommends; you run it |
| Collect evidence | "run the collectors on this diff" | Structured rows from seclint and brevlint (rule_id, file, line, evidence, standard, confidence), not a prose review |
| Check policy | "does this change meet our standards" | policy-review: deviations from what the project declared it cares about, nothing more |
| Reconcile | "pull the findings into one record" | One record, verified kept distinct from heuristic, correlated claims counted once |
| Record a decision | "accept this finding" / "won't fix, reopens if..." | A governed record entry with reopens-if conditions, versioned with the repo |
| Deep review | "gauntlet this" (high undo-cost changes) | Routes to gauntlet; its computed verdict and Conflict Ledger fold into the record |

Your data: your own repository. Policy and the record are plain files under version control. Algol sends nothing on its own.

The floor: the tool proposes; a human decides and runs the engine. No finding originates in Algol except the deterministic collector rows.
