# shakedown documentation

Four kinds of page, because you arrive with one of four questions.

| You want to | Read |
|---|---|
| Learn the tool by using it | [Tutorial: your first run](tutorials/first-run.md) |
| Get a specific job done | [How-to guides](#how-to-guides) |
| Look something up | [Reference](#reference) |
| Understand why it works this way | [Explanation](#explanation) |

New here? Start with the tutorial. It takes about ten minutes and costs a
few cents of model spend.

## Tutorial

- [Your first run](tutorials/first-run.md) — build a small skill, check a
  harness, measure the skill, and read the matrix it prints.

## How-to guides

- [Install shakedown](how-to/install.md)
- [Measure your own skill](how-to/measure-your-own-skill.md)
- [Add a harness](how-to/add-a-harness.md)
- [Isolate runs in a container](how-to/isolate-runs-in-a-container.md)
- [Gate a pull request](how-to/gate-a-pull-request.md)

## Reference

- [CLI](reference/cli.md) — every command and flag
- [`shakedown.toml`](reference/configuration.md) — harnesses and the matrix
- [`cases.toml`](reference/cases.md) — what a case declares
- [The JSON report](reference/report.md) — every field shakedown writes

## Explanation

- [What shakedown measures](explanation/what-shakedown-measures.md) — the
  four checks, and why the artifact is the proof
- [Design decisions](explanation/design-decisions.md) — the sandbox, the
  empty environment, multi-turn as re-invocation, and what was rejected
