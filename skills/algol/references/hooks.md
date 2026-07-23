# Hooks

Two Claude Code hooks let a mechanical check run whether the model remembers or
not. Both are non-modifying: they never edit a file, so they never fire a
system-reminder diff back into the context. A formatter-style hook that rewrites
files is the context-bloat trap this avoids (A17); any auto-fix runs between
sessions, not in a hook.

Tool: `skills/algol/tools/hooks.py`. Example wiring: `hooks.example.json`
alongside it.

## pretooluse: the guard

Before a write (Write, Edit, MultiEdit, NotebookEdit), the guard checks the
target path against the policy's undo-cost classes in the compiled
`routing.json`. A write to an irreversible path warns and recommends the deep
tier. This is the concrete enforcement point for reversibility routing (A13).

It advises by default and prints its decision. Set `ALGOL_GUARD_BLOCK=1` to make
it block the write instead (exit 2, the harness block signal). Point it at the
compiled routing with `ALGOL_ROUTING`.

## posttooluse: the reporter

After a write, it runs the deterministic collectors (seclint, brevlint) on the
touched file and prints concise counts plus at most a few rows. It reports and
does not gate, and it does not modify the file. The row cap keeps the output
small on purpose.

## Wiring

`hooks.example.json` shows the PreToolUse and PostToolUse entries. Copy it into
your Claude Code hooks config and adjust the paths to your layout. The decision
and report logic are pure functions (`guard_decision`, `collect_report`), so they
are tested directly; the CLI is a thin stdin/stdout adapter to the hook contract.

## The floor

The guard advises unless you opt into blocking; the reporter never gates. Neither
hook edits a file. Enforcement of an irreversible op is the one place Algol will
stop an action before it runs, and even that is opt-in.
