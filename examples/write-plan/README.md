# write-plan

The smallest useful example: one skill, two cases, one artifact. Start
here, then read [`scaffold-service`](../scaffold-service) for the fuller
shape.

```bash
uv run skeval run examples/write-plan
```

## The skill

`write-plan` writes `PLAN.md`. A plan needs two facts — a title and an
owner — and the skill is told to ask for whichever one it was not given,
and never to invent it. `PLAN.md` is written only by `bin/planctl`, never
by the model's own file tools.

Splitting it that way is what makes the run measurable. `planctl` renders a
fixed template and refuses to overwrite, so the contents of `PLAN.md` are
evidence about the harness rather than about the model's prose.

## The two cases

| case | what it measures |
|---|---|
| `fully-specified` | Both facts are in the prompt. The skill should fire, call `planctl`, and write the file without asking anything. |
| `missing-owner` | The owner is withheld and `platform-team` is waiting as an answer. It counts only if that string ends up inside `PLAN.md`. |

The second case is the interesting one. skeval never parses the question or
checks the ordering — the artifact settles it. A reply is only ever handed
over in answer to something the harness asked, so `platform-team` appearing
in `PLAN.md` means the harness asked, accepted the answer, and acted on it.

`inputs_resolved` reports `n/a` for the first case: it withholds nothing, so
there is nothing to resolve.

## Files

```
SKILL.md        the skill under test
cases.toml      the two cases
bin/planctl     the deterministic half it must call
```
