# skillconf

Given a harness and a model, does the same query produce the same
procedural outcome?

Not "is my skill any good". [`skill-creator`][sc] answers that, and
answers it better. This asks whether a skill that works on one harness
also works on another, and whether it keeps working.

[sc]: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator

Design and rationale: [`DESIGN.md`](DESIGN.md).

## Status

MVP. Claude Code only. Tempdir sandbox; the container backend described in
the design is not built yet, so runs are **not fully isolated** and
`doctor` reports what else was visible.

## Try it

```bash
uv sync
uv run pytest                 # 28 offline tests, no spend
uv run skillconf doctor       # verify the harness, one cheap task
uv run skillconf run          # the matrix. spends money.
```

`doctor` on this machine:

```
claude-code
  1. headless run                   ok (exit 0)
  2. skill surfaced at runtime      ok (activation observed)
  3. output parsed                  ok (1 tool calls, 3 texts)
  4. session resume                 ok (2 turns)
  5. no TTY required                ok (ran without a terminal)
  6. environment visibility         ok (16 other skills visible; built-ins expected)

  qualifies: yes
```

## What it checks

**0. Did the skill fire?** A precondition. If it never activated, the run
measured the base model, and the three checks report `NOT_TRIGGERED`
rather than failing. Triggering is `skill-creator`'s job, and folding a
trigger problem into a conformance number contaminates both.

**1. Tool use.** The deterministic CLI was invoked, and **not denied**. A
tool call in a transcript is a request, not proof of execution.

**2. Artifact created.** The expected file exists and is non-empty.

**3. Inputs requested and resolved.** The prompt withholds something the
skill needs. The proof is the artifact: a reply is supplied only in answer
to a question, so a reply appearing in the artifact means the harness
asked, accepted, and acted. No question parsing, no ordering check.

## Adding a harness

Fill in a `[harness.*]` block and run `doctor`. It verifies five
prerequisites empirically with a canary skill whose only instruction is to
run `echo skillconf-ok`. Seeing that call is only possible if the harness
ran headless, discovered the skill, surfaced it to the model, followed it,
and emitted parseable output.

A harness that cannot resume a session is reported `unsupported` on check
3, never failed. It is not marked down for a capability it lacks.

## Two traps this repo learned the hard way

**`--safe-mode` disables the thing under test.** It was used as an
isolation mechanism, and produced a run where the skill was never visible
to the model. That read as "the harness ignores instructions". Isolation
is the sandbox's job; no harness flag substitutes for it.

**A static inventory does not prove runtime visibility.**
`claude --plugin-dir X plugin details` reported `Skills (1)` for a run
whose init event showed the skill absent from the model's list. Only
runtime activation counts.

Both are why the skill is seeded by copy into the harness's own discovery
path, and why `doctor` asserts on what the model actually saw.

## Layout

```
src/skillconf/
  config.py     TOML -> Harness, Case, Target
  sandbox.py    ephemeral workspace, skill and bin seeded in
  runner.py     one turn = one subprocess; multi-turn is re-invocation
  events.py     two stream shapes -> ToolCall, text, denials
  checks.py     the precondition and the three checks
  plugin.py     pytest fixtures and parametrization
  cli.py        a thin front for pytest
  doctor.py     the five prerequisites, verified by running them
examples/write-plan/
  skill/        the skill under test
  bin/planctl   the deterministic half it must call
```

`pytest` works directly; the CLI is optional sugar and passes unknown
arguments straight through.
