# Algol overview

This is an account of the whole tool: what it is, how it is built, what is shipped, and what is still drafted. Where the repo and a drafted change disagree, this describes the repo and flags the draft.

Status: v0.16.0 plus the unreleased fixes listed in CHANGELOG.md, public at github.com/btmoriarty/algol. The v1 review scope is local-only, described below. As of 2026-11-10 the repository has 210 tests across 21 files; run `python3 -m unittest discover -s tests` for the current count. An independent acceptance audit of v1 passed, as recorded in docs/ACCEPTANCE.md. On Python 3.11 or later it uses the standard-library `tomllib` module, and it falls back to the `tomli` backport where `tomllib` is unavailable. Version 1.0.0 is reserved until after the managed GitHub check-run, which is planned for v2.

## What it is

Algol is a project-controlled policy, routing, reconciliation, and governance layer for code review. It runs deterministic collectors and a model-based policy review against the project's versioned standards. It routes broader review to supported engines, ingests findings from supported sources, reconciles those findings, never promoting a weaker evidence tier without notice, and records human dispositions and any reopening conditions. Algol does not perform a general-purpose bug hunt or auto-launch review engines.

## Why it exists, and who it is for

Algol is designed to sit above code-review engines rather than replace them. It gives a project an owned, versioned account of its review standards, which engine should see a change, how findings from different sources reconcile, and what was decided and why. It combines three functions: project-versioned policy, cross-source reconciliation, and a persistent governed decision record across the repo's history.

Algol is intended for projects with multiple reviewers or review engines, especially where an incorrect review decision is costly to reverse. A single-person project with a simple review policy may not need it.

## Architecture: the components

Eighteen modules ship under `skills/algol/tools/`. Policy-aware components consume the compiled policy; `evidence.py` and `pathmatch.py` are shared helpers. None performs a general-purpose bug hunt.

- `compile_policy.py`: validates `.algol/policy.toml` and writes four artifacts, `REVIEW.md`, `scanner-rules.json`, `routing.json`, and `catalog.json`, with a source SHA-256 hash for provenance. Unknown top-level tables are an error, so a misspelled table cannot drop a section silently. `init.py` drops the shipped starter policy into a project.
- `seclint.py` and `brevlint.py`: deterministic evidence collectors. They emit evidence rows (`rule_id`, `file`, `line`, `col`, `evidence`, `standard`, `confidence`, `message`), not prose reviews, and name each file relative to the repo root. seclint is security (CWE-tagged starter rules, masked secrets, per-line ignores); brevlint is style and brevity. A collector reports and never gates. A finding from the collectors alone is labeled `floor` and kept out of the way of a real engine's finding.
- `sarif_adapter.py`: converts any tool's SARIF output (CodeQL, Semgrep, bandit, gitleaks, ruff) into evidence rows, with the tool name as the source.
- `policy_review.py`: a model pass that checks a change against the project's own standards, not a general bug hunt. Two steps: `prompt` assembles the discipline plus the compiled REVIEW.md plus the change; `ingest` validates the model's finding-set, failing closed on anything malformed, and normalizes it into rows that reconcile takes as heuristic.
- `router.py`: recommend-only. From the compiled policy and the changed paths it recommends the engine the policy declares for each matched standard: `skip`, `brevlint`, `seclint`, `policy-review`, `/code-review`, `ultra`, `gauntlet`, `evidence-locked-uat`, or `applying-formal-rigor`. It orders recommendations deepest-first and never auto-launches. An undo-cost class adds the policy's `escalate_to` engine and sets the `escalation` flag. `--format commands` prints a shell-quoted command per recommendation and stays silent on a low-risk change.
- `changed.py` and `gate.py`: the per-change entry point. `changed.py` lists a change's files from git; `gate.py` routes the change, runs the collectors on those files only, reconciles into the record with prior dispositions kept, and reports what is new, carried, and reappeared.
- `reconcile.py` and `record.py`: the reconciliation and governed-record components. reconcile folds collector and SARIF rows, policy-review output, a gauntlet run record, and the composed verifiers' results into one record. Observations that share `(file, line, claim)` are one finding. A finding's id is set once and persisted, and a finding whose code moved to a new line, with identical evidence, keeps its id and disposition. reconcile refuses to replace an existing record without `--base`. record holds the Finding, Observation, and Disposition model, the verification tiers, reopens-if conditions, and deterministic serialization.
- `decide.py`: records a human disposition on a finding by id, requires one to three reopens-if conditions unless a permanent verdict is declared, and appends a timestamped event to `events.jsonl`.
- `verify.py`: raises one finding's tier through the verifying engine. An evidence-locked-uat FAIL reaches `verified`; gauntlet reaches `model_corroborated`.
- `gauntlet_adapter.py`: the single parser for a gauntlet run record (the deep tier). Algol builds no panel; the deep tier routes fully to gauntlet.
- `compose_adapter.py`: parses and normalizes results from `evidence-locked-uat` and `applying-formal-rigor`, which reconcile ingests through `--uat` and `--rigor`.
- `hooks.py`: two non-modifying Claude Code hooks. A PreToolUse guard warns on a write to a path in an undo-cost class, matching the path relative to the repo root; a PostToolUse hook runs the collectors on the touched file and reports counts. The hooks report and never modify a file.
- `evidence.py` and `pathmatch.py`: the shared evidence-row shape, globstar path matching, and repo-relative path handling, reused by the collectors, the router, the gate, and the hooks.

## The evidence-tier model

Findings carry a verification tier that comes from a source, never from merging. A finding's status is the highest tier among its observations, and it is never synthesized.

Tiers in the repo, lowest to highest: `hypothesis`, `heuristic`, `inference`, `model_corroborated`, `verified`. A collector or SARIF row is always `heuristic`. A gauntlet `[V]` anchor reads `model_corroborated`, an evidence-locked-uat FAIL reads `verified`, and applying-formal-rigor derives `inference`. Per-source ceilings enforce this: collectors cap at `heuristic`, rigor at `inference`, gauntlet at `model_corroborated`, and only a deterministic verifier (evidence-locked-uat) reaches `verified`. So a model panel's own verdict never reads as a deterministic `verified`. That was a real overclaim in 0.9.

## The governed record

reconcile and the gate write one record per project, versioned with the repo. Each finding keeps its source and its verification tier, kept distinct. A human attaches a disposition with `decide.py`: `accept`, `suppress`, or `defer`, with a rationale and one to three conditions that would reopen it. A disposition with no reopening condition needs an explicit flag and is then marked, because a permanent verdict by default is what the record exists to prevent. Findings are not retired automatically, because the gate collects on changed files only and cannot tell a fixed finding from one it did not scan.

## Routing and undo-cost

The router reads the compiled routing criteria and two signals: which declared standards the change touches, and its undo-cost. An undo-cost class recommends the policy's `escalate_to` engine and sets the `escalation` flag. The router recommends a route and records its reason; a human runs the selected engine.

## Composition

Algol builds the project-specific policy, routing, reconciliation, and record layer. The deep tier routes to gauntlet (epistemic-skills). Algol consumes the gauntlet run record and maps its verdict and conditions into the governed record. The testing axis routes to evidence-locked-uat, the hard-efficiency axis to applying-formal-rigor. Gauntlet and the epistemic skills are GPL-3.0, so Algol consumes their output and does not import their code. Security stays Algol-native.

## Scope and what is not built

The v1 scope is local-only. Algol routes to locally run collectors, policy-review, `/code-review`, and `ultra`. `/code-review` and `ultra` have no adapter into reconcile yet; their findings enter as hand-written evidence rows at `heuristic`. Algol does not integrate with the managed GitHub check-run that posts on a pull request; that integration is planned for v2. It does not auto-launch an engine or perform a general-purpose bug hunt. It does not include a native testlint or hard-efficiency heuristic; those axes route to composed tools. Marketplace distribution and a blind-test result table remain on the roadmap.

## Known limitations and open items

- The golden-path executable regression (`tests/test_golden_path.py`) runs the real tools end to end. Its second part, a document binding that would also fail CI on a docs-only drift, is specified in docs/golden-path-spec.md and not built, so the one-pager transcript is not checked against the current tool.
- A DIY comparison harness is specified in docs/diy-comparison-spec.md and not built. A throwaway implementation of the draft showed two narrow capability differences; it did not establish that Algol outperforms a review-engine-plus-CLAUDE.md-plus-script workflow.
- Line-move tracking relies on each source's evidence text. seclint keeps only the matched snippet, so a removed hit and a new identical one in the same file can share an identity; the gate lists that finding under its reappeared dispositions.
- The committed `docs/CHEATSHEET.pdf` predates the current cheat-sheet HTML and is due for a re-render at the next release.
- No managed check-run, no marketplace distribution, and no blind-test result table yet.

## Docs map

- docs/DESIGN.md: the design of record, as written before the code.
- docs/WALKTHROUGH.md: the acme worked example, real commands.
- docs/ACCEPTANCE.md: the independent v1 acceptance audit.
- docs/CHEATSHEET.md: the one-page cheat sheet.
- docs/one-pager.md and docs/one-pager.html: the styled one-pager files.
- docs/what-algol-does.html: the plain-language explainer.
- docs/golden-path-spec.md: the golden-path fixture spec.
- docs/diy-comparison-spec.md: the comparison design.
- docs/archive/: the v1.1 build briefs, kept as design history.
- docs/policy.example.toml: a small illustrative policy. The shipped starter is skills/algol/starter-policy.toml.
- skills/algol/references/: one reference per component.
