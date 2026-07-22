# Algol architecture

The component model, in brief. The full design of record is `docs/DESIGN.md` in the repo root. As each component is built, its protocol lands here in `references/` as its own file.

## Control plane, not a reviewer

Algol owns four things and reviews nothing: policy (what the project's standards are), routing (which engine sees a change), reconciliation (merging findings into one record), and the governed record (what was decided and what would reopen it).

## Components

- Policy model: `.algol/policy.toml`, versioned and path-scoped, compiled into review instructions, scanner rules, routing criteria, and a catalog. This is the core product.
- Evidence collectors: seclint (security, Algol-native) and brevlint (style and brevity). Deterministic. They emit structured rows (rule_id, file, line, evidence, standard, confidence), not prose reviews.
- policy-review: a model pass against the project's declared standards. Ships in v1.
- router: recommends an engine from policy and an undo-cost signal. Irreversible changes escalate on their own. Recommends, never auto-launches.
- reconcile: merges every source into one record, keeps ultra-verified distinct from heuristic, never upgrades silently. Built on an evidence-required rule: a finding needs a verbatim file:line or it is demoted.
- Governed record: reconciled findings plus each disposition and its reopens-if conditions, on disk, versioned with the repo, in a namespace outside the harness sensitive-file gate.
- Deep tier: routes to gauntlet (composed, not rebuilt) and consumes its run record.

## Compose, do not rebuild

Testing routes to evidence-locked-uat; hard efficiency claims route to applying-formal-rigor; the deep-tier panel routes to gauntlet. Security stays Algol-native. Algol keeps only what those lack: versioned policy, cross-source reconcile, and a governed record across the repo's history.

## v1 boundary

Local-only: the engines run locally (collectors, policy-review, `/code-review`, `ultra`). Wrapping the managed GitHub Code Review check-run is v2.
