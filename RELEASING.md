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
- The cheat sheet renders to `docs/CHEATSHEET.pdf` from `docs/CHEATSHEET.html`
  (Letter landscape, background graphics on). Re-render at the release, and
  remove `docs/CHEATSHEET.pdf.stale` once it is current.
