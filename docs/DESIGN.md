# Algol v3 brief (ReviewOps control plane)

Status: draft, 2026-07-22. Supersedes the v2 suite brief. Write to this model before any code. Inputs folded in from docs/algol-v3-inputs.md; every item there is addressed or declined below. Scope decisions settled with Brian on 2026-07-22 are marked SETTLED.

## What Algol is

A project-controlled policy, routing, and governance layer that sits above the review engines rather than being one. It reviews nothing itself. It reads the project's versioned review standards, decides which engine handles a given change (route), merges every engine's findings into one record without silently upgrading a heuristic to verified (reconcile), and preserves each human decision with the conditions that would reopen it (the governed record). Finding bugs is the engines' job; deciding what gets reviewed and recording what was decided is Algol's. Category: ReviewOps for Claude Code. It is the human-oversight thesis applied to code review, in tool form.

## Why it exists

Claude Code already ships strong reviewers (`/code-review` and `ultra`), and the ecosystem is filling with more (epistemic-skills, reflect, cc10x). The gap is not another reviewer. It is that a project has no owned, versioned account of what its review standards are, which engine should see which change, how findings from different sources reconcile, and what was decided and why. Algol owns that account. The differentiator, stated plainly and defended against every prior-art overlap below: project-versioned policy, cross-source reconciliation, and a persistent governed decision record across the repo's history. Nothing in the wild ships all three.

What a user gets from it, concretely. You stop deciding review depth by gut. Today you eyeball a diff and guess whether it is worth `ultra` or a skip; Algol routes by policy and undo-cost, so a schema migration or a payments change escalates on its own and a typo fix does not burn a deep review. The rule is written down, not in your head on a good day. You get one record instead of scattered findings: `/code-review`, `ultra`, and a security scan each say their piece, and Algol reconciles them into a single record and never quietly turns a heuristic guess into a verified result, so you can see what was actually checked versus what was estimated. And your decisions do not evaporate: a "won't fix" carries the one or two conditions that would reopen it, so months later you know why you waved it through, and it comes back when the thing that made it safe stops being true. The standards themselves are a versioned file a new contributor inherits, not tribal memory.

Who will not get much from it: a solo weekend project where you are the whole policy. Algol earns its place when more than one person, or more than one engine, is reviewing, and when a wrong call is expensive to undo.

## Scope for v1

SETTLED 2026-07-22:

- v1 is local-only. Algol governs the review paths run locally: its own evidence collectors (seclint, brevlint), policy-review, `/code-review`, and `/code-review ultra`. v1 does not touch the managed GitHub Code Review check-run that posts automatically on a pull request. That wrap is v2, added after v1 is tested (see v2 below).
- policy-review ships in v1. The model pass that checks a change against the project's own standards is in the first release, not deferred.
- Draft-from-inputs now; specific spots still need a close repo read before code. Those are flagged inline with READ-BEFORE-CODE.

## Components

Four pieces, all governed by policy. None of them is a general bug hunt.

1. Evidence collectors: seclint and brevlint. Deterministic. They emit structured evidence rows (`rule_id`, `file`, `line`, `evidence`, `standard`, `confidence`), not full reviews. seclint is security; brevlint is style and brevity. seclint stays Algol-native because the composed sets below do not cover security scanning; its rule set draws from OWASP / CWE / MITRE (READ-BEFORE-CODE: AgriciDaniel/claude-cybersecurity for the rule catalog).

2. policy-review (in v1). A model pass that checks the change against the project's own versioned standards, not a general bug hunt. It reads the compiled policy (below) and reports only deviations from what the project declared it cares about.

3. router. Recommends, does not auto-launch. From policy plus the change's undo-cost it recommends one of: skip, a collector pass, policy-review, `/code-review`, or `ultra`. It routes to the right discipline, not only to the right depth. READ-BEFORE-CODE: the `using-epistemic-skills` router and cc10x's anti-anchored router are the two models to read against this design before code.

4. reconcile. Merges findings from every source into one record. Keeps an ultra-verified finding distinct from a heuristic one. Never silently upgrades a heuristic to verified. This is the mechanism the whole tool is built to protect.

The governed record is the output of reconcile plus the human's dispositions: a project-owned, versioned decision record that persists across the repo's history.

## Policy model (the core product)

Versioned, path-scoped standards in `.algol/policy.toml`, compiled into the artifacts each component needs: review instructions (for example a generated REVIEW.md), scanner rules, routing criteria, and a catalog. Standards are open-ended. Security, efficiency, and brevity are examples, not a fixed spine; a project declares what it cares about and scopes it by path. Policy is the thing under version control, so a change to how the project reviews is itself a reviewable, dated diff.

## Router: how a change is routed

The router reads policy and two signals about the change, and recommends an engine.

- Axis match. Which declared standards the change touches (security paths, hot paths, public surface), routing to the collector or discipline that covers that axis.
- Undo-cost (A13, reversibility routing). The router carries an undo-cost signal. Irreversible changes escalate to the deep tier or to `ultra` even without another flag: deleting user data, a public API, a schema migration, payments. Modeled on reflect's one-way vs two-way door. A live instance of the stakes-to-scrutiny idea already ships in code-foundations (ryanthedev), whose adaptive gate policy picks its depth by risk and routes security-sensitive phases to a majority-vote review; Algol differs by keying on undo-cost specifically and living in the router, not a fixed per-phase build gate. A PreToolUse hook is the concrete enforcement point (see the hooks note under Composition).

Testing and efficiency are routed out, not built (see Composition).

## Deep tier: refute and reconcile

For high-undo-cost or policy-flagged changes the router escalates to a deep tier that argues the change rather than scores it.

SETTLED 2026-07-22 (after reading gauntlet's full orchestration): the deep tier routes fully to gauntlet (epistemic-skills). Algol builds no panel and no native arbitrator in v1. gauntlet already ships a computed GO / CONDITIONAL / NO-GO you cannot hand-set, tiered evidence ([V path:line] mechanically verified and hash-bound, [I] inference, [H] hypothesis at zero weight), a dissent-preserving Conflict Ledger, oracle-adequacy and fail-closed checks, and a blind-certified arbitrator (10 of 10 against planted defect classes). GPL-3.0, so Algol consumes its output and does not import its code.

- Lean-blind adversary (A12) is satisfied by gauntlet, not built by Algol. gauntlet runs its lenses isolated behind a barrier so they never see each other before arbitration, and its arbitrator is blind-certified. A12 becomes "route to gauntlet, which enforces it."
- Handoff: Algol consumes gauntlet's `run-record.json` (`gauntlet-run-record@1`), maps its verdict and P1/P2 conditions into the governed record, seeds reopens-if (A14) from those conditions, and maps its [V]/[I]/[H] tiers onto the verified-vs-heuristic distinction in reconcile.
- Router alignment: gauntlet auto-fires on the same signals Algol's router escalates on and runs its own triage that can still skip. Algol routes to gauntlet and lets gauntlet's triage make the final run-or-skip call, recording the skip reason in the record. No double-triage.
- Boundary: gauntlet's Step-8 reconcile is for external safety gates within one review and its ledger is per-run lens telemetry; neither is Algol's cross-engine reconcile or its governed record across the repo's history. gauntlet is one source Algol reconciles alongside `/code-review`, `ultra`, and the collectors.

## The governed record

reconcile writes one record per change. Each finding carries its source and its verification status (heuristic vs ultra-verified), kept distinct. Then the human's disposition is recorded, and:

- Reopens-if (A14). Each accepted, suppressed, or deferred finding records the one to three conditions that would reopen it, so a disposition is not permanent by default. Modeled on reflect's "this flips if".

The record is versioned with the repo. That persistence across history is Algol's tie to the oversight work and part of what no composed tool provides.

## Composition (compose before build, per CONVENTIONS)

Algol composes with the ecosystem and builds only the differentiated part. The whole epistemic-skills relationship is one decision, settled here: Algol routes to those disciplines and reconciles their verdicts; it does not reinvent them. License caution: epistemic-skills is GPL-3.0; route to it as installed skills, borrow patterns, do not copy its code into Algol or the copyleft follows.

- Testing axis: route to evidence-locked-uat, a blinded verifier that judges "done" from evidence with a deterministic script and never rounds INCONCLUSIVE up to PASS. Do not build a separate testlint. Testing is a first-class routing axis in v1.
- Efficiency axis: route the hard complexity claims to applying-formal-rigor lens 4 (a full Big-O derivation). brevlint stays for style and brevity only; efficiency claims derive, they are not heuristics.
- Security axis: Algol-native (seclint plus security policy). The composed sets do not cover it.
- Router pattern: model on the using-epistemic-skills router and cc10x's anti-anchoring.
- Hooks: ship Algol's mechanical checks as Claude Code hooks so a check runs whether the model remembers or not. Keep hooks non-modifying (lint and report); a PreToolUse guard is where reversibility routing (A13) is enforced. See A17 in QUEUE.md for the context-bloat caveat on modifying hooks.

## v1 acceptance

- `.algol/policy.toml` compiles to review instructions, scanner rules, routing criteria, and a catalog.
- seclint and brevlint emit structured evidence rows, not prose reviews.
- policy-review reports only deviations from declared standards.
- router recommends (never auto-launches) skip / collector / policy-review / `/code-review` / `ultra`, and escalates on undo-cost.
- reconcile produces one record, keeps ultra-verified distinct from heuristic, and never upgrades silently.
- the record carries reopens-if conditions on every disposition.
- deep tier runs a lean-blind adversary.
- docs and any shipped prose pass voicelint.

## Non-goals (v1)

- Algol does not review code itself; no finding originates in Algol except the deterministic collector rows.
- No auto-launch of an engine; the router recommends and the human runs it.
- No general bug hunt in policy-review.
- No testlint and no efficiency heuristic; those axes route out.
- No managed GitHub check-run integration (that is v2).

## v2 and later (deferred, not declined)

- Wrap the managed GitHub Code Review check-run: ingest and reconcile its findings into the same record, with the GitHub API access and token scope that requires. Added after v1 is tested end to end.
- Distribution (A8): ship as a marketplace plugin with auto-update, plus the shared `~/.agents` open standard, using reflect and epistemic-skills as the template.

## Open items carried

- Repo and token names. Proposed: github.com/btmoriarty/algol; confirm before repo creation.
- (CLOSED 2026-07-22) Deep-tier routing: full gauntlet, no native arbitrator in v1. See Deep tier.

## Inputs ledger (from docs/algol-v3-inputs.md)

- A12 lean-blind adversary: satisfied by routing to gauntlet, not Algol-built (Deep tier).
- A13 reversibility routing: addressed (Router).
- A14 reopens-if: addressed (Governed record).
- A15 calibration overlap: not Algol; belongs to row 4, noted only.
- A16 dogfood a decision gate: meta, out of scope for the brief; left in QUEUE.md as optional.
- epistemic-skills compose-not-rebuild: addressed (Composition), the single decision made.
- Testing axis to evidence-locked-uat: addressed.
- Efficiency to applying-formal-rigor lens 4: addressed.
- Security Algol-native: addressed.
- Router model: addressed, with READ-BEFORE-CODE.
- Deep-tier reads (gauntlet, agent-council): done 2026-07-22; routing locked to full gauntlet.
- seclint rule source (claude-cybersecurity): flagged READ-BEFORE-CODE.
- v1 boundary: SETTLED local-only.
- policy-review timing: SETTLED v1.
- A8 distribution: deferred to v2 with the marketplace template.
