# Algol vs DIY comparison, spec

The differentiation proof. Every review of Algol scored differentiation lowest and asked the same question: why is this better than a code-review tool plus a CLAUDE.md plus a small merge script a disciplined team could write? This spec defines a fair, blind-graded head-to-head that answers it with captured evidence, or shows where it does not.

## The question, stated precisely
Not "is Algol a better reviewer." Algol reviews nothing; reviewing is routed out. The question is whether the governance layer (policy routing, cross-source reconciliation, a decision record) catches failures that the do-it-yourself combination silently lets through. If a competent DIY setup catches them too, say so.

## What it isolates
Both arms use the same review engines on the same inputs. The only variable is the governance layer. This keeps the test about governance, not about which reviewer is smarter.

- **Arm A (DIY):** the engines, plus a real `CLAUDE.md`/`REVIEW.md` with the project's standards, plus a small, competent merge script (on the order of a couple hundred lines) that collects the engines' outputs into one place. Written to be fair, not a strawman. If a reasonable team would add a guard, add it.
- **Arm B (Algol):** the same engines, governed by `.algol/policy.toml`, the router, `reconcile`, and the record.

## Failure modes to demonstrate
Each is a planted situation in the fixture repo. For each, record what Arm A produces and what Arm B produces, and grade whether the failure was silently let through. Note, per failure mode, whether a competent Arm A could catch it with more glue, and how much.

1. **A heuristic treated as proof.** A scanner hit and a model reviewer point at the same line and agree. Arm A's merge, lacking a tier model, reports one high-confidence finding. Arm B keeps it `heuristic`, because no source verified it; agreement is not verification.
2. **A produced finding dropped.** One engine's output is present but not wired into the merge (the exact bug our own one-pager shipped four times). Arm A's record silently omits it. Arm B's reconcile takes every produced record, and a missing one is visible, not silent.
3. **A decision with no memory.** A finding is accepted as "won't fix" in a PR comment. Six months later the reason is gone and the same finding returns. Arm A has no record of why or of what would reopen it. Arm B's disposition carries the rationale and the reopen condition, and flags a decision that has none.
4. **Scrutiny by accident.** An irreversible change (a schema migration, a payments path) and a trivial change arrive together. Arm A's prose instructions cannot route; whoever looks picks depth by gut, and on a tired afternoon the risky change gets the skim. Arm B's router escalates the irreversible change on undo-cost alone.
5. **Two sources of truth for the standard.** The security bar stated in `CLAUDE.md` and the scanner's own config drift apart over time. Arm A has two places to keep in sync. Arm B compiles one policy into both the review instructions and the scanner rules, so the standard has one home and a change is one diff.

Pick the strongest three to four to build first. Two and three are the most defensible; one is the sharpest on the honesty thesis.

## Fixtures
A small repo with each situation planted deliberately, fictional and labeled as fixtures (no personal data, per conventions). Each planted item has a known correct outcome, so grading is against ground truth, not opinion. Reuse the acme golden-path fixture infrastructure where it fits.

## Method
1. Run both arms on the same fixtures. Capture real stdout, stderr, and the record or merged output each produces. No hand-authored transcripts (see CONVENTIONS "Shown output is generated, never hand-written").
2. Present both arms' final artifacts to a blind grader, a separate model that is not told which arm is which, with a rubric per failure mode.
3. The grader marks, per failure mode: caught, silently let through, or false alarm. It cites the specific line in the arm's output that sets the mark.
4. Report a table: failure mode by arm by outcome, with the evidence line for each.

## Grading rubric
For each failure mode the grader answers, from the artifacts alone:
- Was the risky or dropped or over-trusted item surfaced at all?
- Was a heuristic reported as verified or high-confidence without a verifying source?
- Was a produced finding missing from the final record?
- Was a human decision preserved with its reason and reopen condition?
- Did the irreversible change get a depth matched to its undo-cost?

## Honesty guards (these are the point, not a footnote)
- Arm A is built to win. If a reasonable engineer would add a check, it goes in. A rigged DIY arm proves nothing.
- Publish the ties and the losses. Where Arm A catches a failure as well as Arm B, that is a real result and it ships in the table. A wins-only comparison is marketing (see A1, the blind-test convention).
- The grader is blind and cites evidence; no arm is scored on reputation.
- Name the cost. Arm B adds a policy file and a per-change loop. If a failure mode is only caught at the price of that overhead, say so, so a reader can judge whether their project clears the bar.

## Deliverable and success criteria
- A comparison doc with the table, the captured artifacts, and the blind grader's per-mode marks with evidence.
- Bound to a test, like the golden-path fixture: the comparison regenerates from a clean checkout so it cannot rot.
- Success is honest, not lopsided: Algol is worth adopting over DIY if it catches at least a few of these failure modes that a competent Arm A silently lets through, at a stated cost. If it does not, the finding is that Algol's value is narrower than claimed, and the positioning changes to match.

## Sequencing
Shares fixture infrastructure with the golden-path fixture (Algol v1.1), so build it alongside or right after. It is the evidence behind the README's differentiation section, which no reviewer has yet been able to accept on assertion.
