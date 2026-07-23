# Algol release checklist

Private now, public later. This is the single source of truth for the flip, so the release does not turn into another round. Recipes are for Brian's terminal and use full absolute paths.

## Now: create the private remote and push

The GitHub connector cannot push the workflow file (its token lacks the workflow scope) or the `algol.skill` binary, so create and push from a terminal.

```
gh repo create btmoriarty/algol --private --source=/Users/moriarty/code/algol --remote=origin --push
```

If you prefer the UI: create a private repo `btmoriarty/algol`, then:

```
cd /Users/moriarty/code/algol
git remote add origin git@github.com:btmoriarty/algol.git
git push -u origin master
```

The CI workflow at `/Users/moriarty/code/algol/.github/workflows/build.yml` goes up with this push. It runs the full test suite on every push and pull request, and rebuilds `algol.skill` on the default branch. Confirm the first Actions run is green.

## Gate: done in the working tree (2026-07-23)

Applied and verified locally (98 tests green):

- [x] v1.1 task 1: the `model_corroborated` tier and per-source ceilings. A gauntlet `[V]` reads `model_corroborated`; only a deterministic verifier reaches `verified`.
- [x] v1.1 task 2, part one: the golden-path executable regression (`tests/test_golden_path.py`, `tests/fixtures/gaunt.json`).
- [x] Docs synced to `model_corroborated`: `README.md`, `docs/one-pager.md`, `docs/one-pager.html`, `docs/OVERVIEW.md`, `docs/CHEATSHEET.md`.
- [x] Cheat sheet rendered: `docs/CHEATSHEET.html` and `docs/CHEATSHEET.pdf`.
- [x] `VERSION` bumped to `0.10.0`; dated `CHANGELOG.md` entry added.

Still open, and none is a public blocker:

- [ ] Confirm CI is green on the remote after the first push. CI also rebuilds `algol.skill`, which is stale in the working tree (the sandbox could not repackage the binary).
- [ ] The golden-path document binding (task 2, part two) is specified, not built.
- [ ] The DIY comparison harness (task 3) needs a DIY-defender review before public use.

## Flip the switch: make public

```
gh repo edit btmoriarty/algol --visibility public --accept-visibility-change-consequences
```

Or in the UI: Settings, General, Change repository visibility, Public.

Then:

- Move the Algol row to Shipped in `/Users/moriarty/code/toolbench/QUEUE.md`.
- Socialize per the queue: Pherkad announces first, then the Algol write-up. Every draft passes voicelint.

## What stays after v1

- The managed GitHub check-run wrap (v2).
- The DIY comparison harness (task 3), after a DIY-defender reviews Arm A.
- Marketplace distribution and the blind-test result table.
