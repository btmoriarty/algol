---
name: algol
description: Govern code review for a project instead of performing it. Triggers when setting up or running Algol, defining or compiling review policy in .algol/policy.toml, routing a change to the right review engine by policy and undo-cost, reconciling findings from /code-review, ultra, gauntlet, or the deterministic collectors into one record, or recording a review decision with reopens-if conditions. Not a reviewer itself.
---

# Algol

Govern what gets reviewed and record what was decided. Algol reviews nothing itself.

Algol reads a project's versioned review standards, routes each change to the right engine per policy and undo-cost, reconciles every engine's findings into one record without silently upgrading a heuristic to verified, and preserves each human decision with the conditions that would reopen it.

v0.9.0, local scope. See `docs/DESIGN.md` for the full design and each `references/` file for a component's protocol.

## The pieces

- Policy model: versioned, path-scoped standards in `.algol/policy.toml`, compiled into review instructions, scanner rules, routing criteria, and a catalog. `tools/compile_policy.py`, `references/policy-model.md`.
- Starter policy + init: `tools/init.py` drops the shipped strong default (`starter-policy.toml`), which routes the high-undo-cost surfaces (auth, migrations, money, public API, infra, CI) out of the box, so a cold first run is useful before any tuning. `references/policy-model.md`.
- Evidence collectors: seclint (security) and brevlint (style and brevity), deterministic, emitting structured evidence rows. They are the silent floor: a finding from collectors alone is labeled `floor` and demoted in presentation, never shown as a peer of a real engine's finding. `tools/seclint.py`, `tools/brevlint.py`, `references/collectors.md`.
- policy-review: a model-pass harness that checks a change against the project's own standards, not a general bug hunt. `tools/policy_review.py`, `references/policy-review.md`.
- router: recommends skip, a collector, policy-review, `/code-review`, or `ultra` from policy and undo-cost, and escalates to the deep tier on undo-cost. Recommends, never auto-launches. `tools/router.py`, `references/router.md`.
- reconcile and the record: merges findings into one governed record, keeps verified distinct from heuristic, never upgrades silently, carries reopens-if on each disposition. `tools/reconcile.py`, `tools/record.py`, `references/reconcile-and-record.md`.
- verify: a targeted, one-finding loop to raise a finding's tier through the verifying engine (uat FAIL reaches verified; gauntlet reaches model_corroborated). prompt assembles the request; ingest folds it in and reports the tier change. `tools/verify.py`, `references/verify.md`.
- SARIF ingest: converts any standard tool's SARIF output (CodeQL, Semgrep, bandit, gitleaks, ruff) into evidence rows reconcile takes through `--collector`, with the tool name as the finding's source. `tools/sarif_adapter.py`, `references/sarif-ingest.md`.
- The per-change gate: `changed.py` names a change's files from git; `gate.py` routes the change, runs the collectors on just those files, and reconciles into the record so prior dispositions survive and only new findings surface. `tools/changed.py`, `tools/gate.py`, `references/pr-gate.md`.
- Deep tier: routes to gauntlet and consumes its run record. `tools/gauntlet_adapter.py`, `references/deep-tier.md`.
- Composed axes: testing to evidence-locked-uat, efficiency to applying-formal-rigor. `tools/compose_adapter.py`, `references/composition.md`.
- Hooks: a non-modifying reversibility guard and a collector reporter. `tools/hooks.py`, `references/hooks.md`.

## The floor

The tool proposes; a human decides and runs the engine. No finding originates in Algol except the deterministic collector rows. A heuristic is never silently upgraded to verified.
