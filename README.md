# Algol

A project-controlled policy, routing, and governance layer that sits above code-review engines rather than being one. Algol reviews nothing itself. It reads the project's versioned review standards, decides which engine handles a given change, reconciles every engine's findings into one record without silently upgrading a heuristic to verified, and preserves each human decision with the conditions that would reopen it. Category: ReviewOps for Claude Code.

Status: v0.10.0, local scope. The design of record is [docs/DESIGN.md](docs/DESIGN.md); the acceptance record is [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).

## Who it is for

A project where more than one person, or more than one engine, reviews code, and where a wrong call is expensive to undo. A solo weekend project where you are the whole policy will not get much from it.

## What you get

You stop deciding review depth by gut. Algol routes by policy and undo-cost, so a schema migration or a payments change escalates on its own and a typo fix does not burn a deep review. You get one record instead of scattered findings across `/code-review`, `ultra`, and a security scan, and it never quietly turns a heuristic guess into a verified result, so you can see what was checked versus what was estimated. Your decisions do not evaporate: a "won't fix" carries the one or two conditions that would reopen it, and the standards themselves are a versioned file a new contributor inherits.

## Why these defaults

I built Algol around one rule: never silently upgrade a heuristic to verified. Every other default follows from it. Findings carry their source and their verification status, kept distinct. The router recommends and never auto-launches, so a human runs the engine. The deep tier routes out to gauntlet rather than reinventing a panel, because a reviewer worth trusting is one that derives its verdict rather than asserting it. Standards are open-ended: security, efficiency, and brevity are examples, not a fixed spine. You declare what your project cares about in `.algol/policy.toml` and scope it by path. To customize, edit that file; a change to how you review is then a dated, reviewable diff.

## Why this exists

Claude Code already ships strong reviewers, and the ecosystem is filling with more. The gap is not another reviewer. It is that a project has no owned, versioned account of how it reviews: which standards it cares about, which change goes to which engine, how findings reconcile, and what was decided and why. Algol owns that account. It is the human-oversight question pointed at code review: the tool proves, the human decides.

## Install

Clone the repo and run the tools directly (Python 3.11+, standard library only). Package the skill bundle with `./build.sh`, which produces `algol.skill`. A shared skills standard and a marketplace plugin are post-release (see docs/DESIGN.md).

Quick start:

```
python skills/algol/tools/compile_policy.py .algol/policy.toml
python skills/algol/tools/router.py --routing .algol/compiled/routing.json --changed src/a.py
python skills/algol/tools/brevlint.py --rules .algol/compiled/scanner-rules.json --root . --out rows.json
python skills/algol/tools/reconcile.py --collector rows.json --out .algol/record.json
```

An example policy is at [docs/policy.example.toml](docs/policy.example.toml).

## Data handling

Algol runs against your own repository and the review engines you already use. Its record and policy live in your project as plain files under version control. It sends nothing anywhere on its own. The optional external cross-family adjudication in the deep tier (a gauntlet feature) is manual and operator-gated; Algol does not wire it in v1.

## Cheat sheet

[docs/CHEATSHEET.md](docs/CHEATSHEET.md).
