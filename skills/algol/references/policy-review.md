# policy-review

A model pass that checks a change against the project's own declared standards.
It is not a general bug hunt. It reports only where the change deviates from what
the policy said the project cares about; a real bug that no standard names is out
of scope here, and belongs to another engine.

Tool: `skills/algol/tools/policy_review.py`. It is the deterministic harness
around a model pass: it assembles the prompt and it validates and normalizes the
model's output. The judgment itself runs when a model is pointed at the prompt.

## Why a harness, not a script

The collectors are deterministic, so they are pure code. policy-review reasons,
so the reasoning runs in a model and the code does the parts that must be exact:
building the input and enforcing the output shape. That split keeps the honest
boundary. A model pass is reasoned, not verified, so its rows enter reconcile as
heuristic like any collector's; only the deep tier or an ultra pass raises a
finding to verified. policy-review never claims that.

## The two steps

1. prompt: assemble the discipline, the compiled `REVIEW.md` standards, and the
   change, plus the required output schema.

   ```
   python skills/algol/tools/policy_review.py prompt \
       --review .algol/compiled/REVIEW.md --changed src/a.py --out prompt.txt
   ```

2. ingest: validate the model's finding-set output and normalize it into the
   evidence-row shape reconcile consumes (source `policy-review`).

   ```
   python skills/algol/tools/policy_review.py ingest model-output.json --out rows.json
   ```

## Output schema (finding-set)

A single JSON object with a `findings` list. Each finding: `file`, `line`,
`axis`, `evidence` (a verbatim snippet or file:line anchor, required, no anchor
no finding), `message` (how it deviates), and `confidence` in [0.0, 1.0]. An
empty list means the change met the standards.

## Fail closed

`ingest` rejects anything malformed with a named error and a non-zero exit: not
an object, a bad type, a missing field, a confidence out of range, a negative
line. A model that returns garbage does not silently produce an empty or partial
record.

## The discipline (what the prompt enforces)

Judge only against the declared standards. Cite a verbatim anchor for every
finding. Assign an honest confidence; you are reasoning, not verifying. Return
only the JSON object, no prose around it. Meeting the standards means an empty
findings list, not an invented concern.
