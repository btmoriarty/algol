---
name: algol
description: Govern code review for a project instead of performing it. Triggers when setting up or running Algol, defining or compiling review policy in .algol/policy.toml, routing a change to the right review engine by policy and undo-cost, reconciling findings from /code-review, ultra, gauntlet, or the deterministic collectors into one record, or recording a review decision with reopens-if conditions. Not a reviewer itself.
---

# Algol

Govern what gets reviewed and record what was decided. Algol reviews nothing itself.

Algol reads a project's versioned review standards, routes each change to the right engine per policy and undo-cost, reconciles every engine's findings into one record without silently upgrading a heuristic to verified, and preserves each human decision with the conditions that would reopen it.

Status: scaffold. No components built yet. This SKILL.md is a placeholder that names the pieces; the protocols land in `references/` as each component is built. See `references/architecture.md` for the component model and `docs/DESIGN.md` in the repo for the full design.

## The pieces (to be built)

- Policy model: versioned, path-scoped standards in `.algol/policy.toml`, compiled into review instructions, scanner rules, routing criteria, and a catalog.
- Evidence collectors: seclint and brevlint, deterministic, emitting structured evidence rows.
- policy-review: a model pass that checks a change against the project's own standards, not a general bug hunt.
- router: recommends skip, a collector, policy-review, `/code-review`, or `ultra` from policy and undo-cost. Recommends, never auto-launches.
- reconcile: merges findings into one record, keeps verified distinct from heuristic, never upgrades silently.
- Governed record: the reconciled findings plus each human disposition and its reopens-if conditions, versioned with the repo.
- Deep tier: routes to gauntlet for high-undo-cost changes and consumes its run record.

## The floor

The tool proposes; a human decides and runs the engine. No finding originates in Algol except the deterministic collector rows. A heuristic is never silently upgraded to verified.
