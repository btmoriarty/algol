# Algol overview

For review. A current, honest account of the whole tool: what it is, how it is built, what is shipped, and what is still drafted. Where the repo and a drafted change disagree, this describes the repo and flags the draft.

Status: v0.10.0, local scope, with no public remote. The repository has 98 tests across 13 files: brevlint 9, compile_policy 10, compose_adapter 7, gauntlet_adapter 7, hooks 8, pathmatch 6, policy_review 11, reconcile 8, record 10, router 10, seclint 10, tier_ceilings 1, and golden_path 1. An independent acceptance audit passed, as recorded in docs/ACCEPTANCE.md. On Python 3.11 or later it uses the standard-library `tomllib` module, and it falls back to the `tomli` backport where `tomllib` is unavailable. Version 1.0.0 is reserved until after the managed GitHub check-run, planned for v2, and a public release. Of the v1.1 work, the tier change and the golden-path regression are applied and shipped in 0.10.0; only the DIY comparison harness remains drafted.

## What it is

Algol is a project-controlled policy, routing, reconciliation, and governance layer for code review. It runs deterministic collectors and a model-based policy review against the project's versioned standards. It routes broader review to supported engines, ingests findings from supported sources, reconciles those findings without silently promoting a weaker evidence tier, and records human dispositions and any reopening conditions. Algol does not perform a general-purpose bug hunt or auto-launch review engines.

## Why it exists, and who it is for

Algol is designed to sit above code-review engines rather than replace them. It gives a project an owned, versioned account of its review standards, which engine should see a change, how findings from different sources reconcile, and what was decided and why. It combines three functions: project-versioned policy, cross-source reconciliation, and a persistent governed decision record across the repo's history.

Algol is intended for projects with multiple reviewers or review engines, especially where an incorrect review decision is costly to reverse. A single-person project with a simple review policy may not need it.

## Architecture: the components

Twelve modules ship under `skills/algol/tools/`. Policy-aware components consume the compiled policy; `evidence.py` and `pathmatch.py` are shared helpers. None performs a general-purpose bug hunt.

- `compile_policy.py`: validates `.algol/policy.toml` and writes four artifacts, `REVIEW.md`, `scanner-rules.json`, `routing.json`, and `catalog.json`, with a source SHA-256 hash for provenance. Standards are versioned, path-scoped, and open-ended; a change to how the project reviews is a dated, reviewable diff.
- `seclint.py` and `brevlint.py`: deterministic evidence collectors. They emit evidence rows (`rule_id`, `file`, `line`, `col`, `evidence`, `standard`, `confidence`, `message`), not prose reviews. seclint is security (CWE-tagged starter rules, masked secrets, per-line ignores); brevlint is style and brevity. A collector reports and never gates.
- `policy_review.py`: a model pass that checks a change against the project's own standards, not a general bug hunt. Two steps: `prompt` assembles the discipline plus the compiled REVIEW.md plus the change; `ingest` validates the model's finding-set, failing closed on anything malformed, and normalizes it into rows that reconcile takes as heuristic.
- `router.py`: recommend-only. From policy and the change's undo-cost it recommends `skip`, a collector pass, policy-review, `/code-review`, or `ultra`; it orders recommendations deepest-first and never auto-launches. An irreversible undo-cost class recommends the policy's `escalate_to` engine and sets the `escalation` flag.
- `reconcile.py` and `record.py`: the reconciliation and governed-record components. reconcile folds collector rows, a gauntlet run record, and the composed disciplines into one record, grouping observations that share the exact `(file, line, claim)` key into one finding; record holds the Finding, Observation, and Disposition model, the verification tiers, reopens-if conditions, and deterministic serialization. It never silently upgrades a weaker tier, and that invariant is tested.
- `gauntlet_adapter.py`: the single parser for a gauntlet run record (the deep tier). Algol builds no panel; the deep tier routes fully to gauntlet.
- `compose_adapter.py`: routes the testing axis to evidence-locked-uat and hard efficiency to applying-formal-rigor, and ingests their results.
- `hooks.py`: two non-modifying Claude Code hooks. A PreToolUse guard warns on a write to an irreversible path; a PostToolUse hook runs the collectors on the touched file and reports counts. The hooks report and never modify a file.
- `evidence.py` and `pathmatch.py`: the shared evidence-row shape and globstar path matching, reused by the collectors and the router.

## The evidence-tier model

Findings carry a verification tier that comes from a source, never from merging. A finding's status is the highest tier among its observations, and it is never synthesized.

Tiers in the repo, lowest to highest: `hypothesis`, `heuristic`, `inference`, `model_corroborated`, `verified`. A collector row is always `heuristic`. A gauntlet `[V]` anchor reads `model_corroborated`, an evidence-locked-uat FAIL reads `verified`, and applying-formal-rigor derives `inference`. Per-source ceilings enforce this: collectors cap at `heuristic`, rigor at `inference`, gauntlet at `model_corroborated`, and only a deterministic verifier (evidence-locked-uat) reaches `verified`. So a model panel's own verdict never reads as a deterministic `verified`. That was a real overclaim in 0.9.0, where a gauntlet `[V]` read `verified`, and it is closed in 0.10.0.

## The governed record

reconcile writes one record per change. Each finding keeps its source and its verification tier, kept distinct. The human then attaches a disposition, `accept`, `suppress`, or `defer`, with a rationale and zero to three conditions that would reopen it. A disposition with no reopening condition is allowed but flagged, because a permanent verdict by default is what the record exists to prevent. The record is a plain file versioned with the repo, so what a project decided and why is a diffable part of its history. There is no disposition CLI yet; a decision is recorded through the record library.

## Routing and undo-cost

The router reads the compiled routing criteria and two signals: which declared standards the change touches, and its undo-cost. An irreversible undo-cost class recommends the policy's `escalate_to` engine and sets the `escalation` flag. The router recommends a route and records its reason; a human runs the selected engine.

## Composition

Algol builds the project-specific policy, routing, reconciliation, and record layer. The deep tier routes to gauntlet (epistemic-skills). Algol consumes the gauntlet run record and maps its verdict and conditions into the governed record. The testing axis routes to evidence-locked-uat, the hard-efficiency axis to applying-formal-rigor. Gauntlet and the epistemic skills are GPL-3.0, so Algol consumes their output and does not import their code. Security stays Algol-native.

## Scope and what is not built

The v1 scope is local-only and is currently shipped as v0.10.0. Algol governs locally run collectors, policy-review, `/code-review`, and `ultra`. It does not integrate with the managed GitHub check-run that posts on a pull request; that integration is planned for v2. Algol does not auto-launch an engine or perform a general-purpose bug hunt. It does not include a native testlint or hard-efficiency heuristic; those axes route to composed tools. Marketplace distribution and a blind-test result table remain on the roadmap.

## v1.1 status

The v1.1 work was three tasks. Two are applied and shipped in 0.10.0:

1. The `model_corroborated` tier and per-source ceilings (docs/v1.1-tier-brief.md). Applied to `record.py`, `gauntlet_adapter.py`, and `compose_adapter.py`, with a tier-ceiling test.
2. A golden-path executable regression (docs/golden-path-fixture-brief.md): `tests/test_golden_path.py` runs the real tools end to end and asserts exact commands, streams, fields, and values, with a checked gauntlet fixture. Its second part, a document binding that also fails CI on a docs-only drift, is specified but not yet built.

One remains drafted:

3. A DIY comparison harness, specified in docs/diy-comparison-brief.md: an Arm A merge versus Algol's reconcile and record, using the same engine outputs and producing a report from the executed run. It compares only the merge and record layers. Its Arm A design has not yet been reviewed by someone defending the DIY baseline, so it is not applied and not ready for public use.

## Known limitations and open items

- The one-pager's worked example is not yet bound to the tool by the document-binding check (v1.1 task 2, part 2 is specified, not built). Until it is, treat the one-pager transcript as unverified against the current tool.
- The DIY comparison proves two narrow, real capability differences, not the broad claim that Algol beats the full review-engine-plus-CLAUDE.md-plus-script workflow. Policy and routing modes are not yet compared, and its Arm A needs a defender's review.
- No public remote, no managed check-run, no marketplace distribution, no blind-test result table yet.
- The public repository and release packaging are not yet established.

## Docs map

- docs/DESIGN.md: the design of record.
- docs/WALKTHROUGH.md: the acme worked example, real commands.
- docs/ACCEPTANCE.md: the independent acceptance audit.
- docs/CHEATSHEET.md: the one-page cheat sheet.
- docs/one-pager.md and docs/one-pager.html: the styled one-pager files.
- docs/golden-path-spec.md: the golden-path fixture spec; the executable regression is applied (tests/test_golden_path.py), the document binding is specified, not built.
- docs/v1.1-tier-brief.md, docs/golden-path-fixture-brief.md, and docs/diy-comparison-brief.md: the v1.1 task briefs (the tier and golden-path tasks are applied; the DIY comparison is drafted).
- docs/diy-comparison-spec.md: the comparison design.
- docs/policy.example.toml: a starter policy.
