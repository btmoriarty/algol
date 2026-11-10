# Releasing

A version lives in four places. Bump all four in the same commit, or they drift
(as they did up to 0.16.0, where the README status line and the plugin manifest
were left behind).

1. `VERSION`
2. `CHANGELOG.md` (a new dated entry at the top)
3. `README.md` (the `Status: vX.Y.Z` line)
4. `.claude-plugin/plugin.json` (the `version` field)

Then tag and push:

```
git tag vX.Y.Z
git push origin vX.Y.Z
```

Notes:

- CI rebuilds `algol.skill` on a push to the default branch, so do not commit the
  bundle in feature commits; let CI own it.
- Keep the doc-sync set current with every feature: `README.md`,
  `docs/one-pager.md`, `docs/one-pager.html`, `docs/OVERVIEW.md`,
  `docs/what-algol-does.html`, and `docs/CHEATSHEET.md`.
- The cheat sheet renders to `docs/CHEATSHEET.pdf` from `docs/CHEATSHEET.html`
  (Letter landscape, background graphics on). Render it once per release, when
  the whole batch is complete and tested, not per feature. The committed PDF
  predates the current HTML styling and is due for a re-render at the next
  release.
