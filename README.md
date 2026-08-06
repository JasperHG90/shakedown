<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/icons/logo-dark.png">
    <img src="assets/icons/logo.png" width="170"
         alt="skeval logo: two overlapping squares with their intersection filled in green">
  </picture>
</p>

<h1 align="center">skeval</h1>

<p align="center">
  Conformance testing for agent skills: does your skill still work when the
  harness underneath it changes?
</p>

## Why this exists

You wrote a skill and it works. Then the harness ships a new version, or a
teammate runs it on a different one, and it quietly stops working — the CLI
never gets called, the file never gets written, the question never gets
asked. Nothing crashes. You just get a worse answer.

`skeval` runs your skill against every harness and model you care about and
reports what actually happened in each. Not opinions about the prose — the
procedural outcome.

This is not "is my skill any good". [`skill-creator`][sc] answers that, and
answers it better. This asks whether a skill that works in one place also
works in another, and whether it keeps working.

[sc]: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator

## What it checks

Every case declares only the checks that apply to it. Four things get
measured:

- **Did the skill fire?** A precondition, not a check. If it never
  activated, the run measured the base model, so the other three report
  `NOT_TRIGGERED` instead of failing. A trigger problem folded into a
  conformance number contaminates both.
- **Was the tool used?** The deterministic CLI was invoked, **and not
  denied**. A tool call in a transcript is a request, not proof it ran.
- **Was the artifact created?** The expected file exists, is non-empty, and
  contains what the case said it should.
- **Were withheld inputs asked for and resolved?** The prompt leaves out
  something the skill needs. The artifact is the proof: a reply is only ever
  supplied in answer to a question, so a reply showing up in the artifact
  means the harness asked, accepted, and acted. No question parsing, no
  ordering check.

Two other things it gets right:

- **Isolation is reported, never assumed.** Two sandboxes: `tmp` (default,
  fast, **not isolated**) and `container` (isolated, verified against a fake
  harness). The report records which one ran, so a number is never read as
  isolated when it was not.
- **A harness is never marked down for a capability it lacks.** One that
  cannot resume a session gets `unsupported` on `inputs_resolved`, not a
  failure.

## Quick start

You need [`uv`](https://docs.astral.sh/uv/) and at least one harness CLI on
your `PATH`.

```bash
uv sync
uv run pytest                          # offline. no spend.
uv run skeval doctor                   # is the harness usable at all?
uv run skeval run examples/write-plan  # the matrix. spends money.
```

Then point it at your own skill:

```bash
uv run skeval init ./my-skill          # scaffold a skill that already passes
uv run skeval run ./my-skill --repeat 5 -j 5
```

The skill under test is a path, and nothing about it is configured anywhere
else. `skeval.toml` describes harnesses only.

[`GETTING_STARTED.md`](GETTING_STARTED.md) walks through evaluating your own
skill and adding your own harness. Design and rationale live in
[`DESIGN.md`](DESIGN.md).

## See it run

`skeval doctor` checks a harness against six prerequisites before you spend
anything on it:

![skeval doctor running six prerequisite checks against the claude-code harness, all passing](assets/doctor.gif)

`skeval run` executes the matrix and prints a pass rate per target and
dimension, plus a warning when the sandbox was not isolated:

![skeval run executing the write-plan example and printing a results table at 100% across four dimensions](assets/run.gif)

Every run also writes `skeval-report.json` with the per-run detail behind
those numbers.

## Adding a harness

Fill in a `[harness.*]` block in `skeval.toml` and run `doctor`. It verifies
six prerequisites empirically, using a canary skill whose only instruction is
to run `echo skeval-ok`:

| # | prerequisite | why it matters |
|---|---|---|
| 1 | headless run | no TTY, no interactive session |
| 2 | skill surfaced at runtime | the model actually saw it |
| 3 | output parsed | the stream shape is one skeval understands |
| 4 | session resume | multi-turn cases are possible |
| 5 | no TTY required | it runs in CI |
| 6 | environment visibility | you know what else was in scope |

Seeing that canary call come back is only possible if the harness ran
headless, discovered the skill, surfaced it to the model, followed it, and
emitted parseable output. Claude Code is the only harness verified so far.

## Two traps this repo learned the hard way

**`--safe-mode` disables the thing under test.** It got used as an isolation
mechanism and produced a run where the skill was never visible to the model.
That read as "the harness ignores instructions". Isolation is the sandbox's
job; no harness flag substitutes for it.

**A static inventory does not prove runtime visibility.** `claude
--plugin-dir X plugin details` reported `Skills (1)` for a run whose init
event showed the skill absent from the model's list. Only runtime activation
counts.

Both are why the skill is seeded by copy into the harness's own discovery
path, and why `doctor` asserts on what the model actually saw.

## Layout

```
src/skeval/
  config.py     TOML -> Harness, Case, Target
  sandbox.py    ephemeral workspace, skill and bin seeded in
  runner.py     one turn = one subprocess; multi-turn is re-invocation
  events.py     two stream shapes -> ToolCall, text, denials
  checks.py     the precondition and the three checks
  plugin.py     pytest fixtures and parametrization
  cli.py        a thin front for pytest
  doctor.py     the six prerequisites, verified by running them
examples/write-plan/
  skill/        the skill under test
  bin/planctl   the deterministic half it must call
```

`pytest` works directly; the CLI is optional sugar and passes unknown
arguments straight through.

## Contributing

Issues and pull requests are welcome. The useful contribution right now is a
new harness: add a `[harness.*]` block, run `doctor`, and open a PR with the
output — including the checks that failed. A harness that does not qualify is
still worth knowing about.

Run `uv run pytest` before you push. It is offline and spends nothing.
