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
  harness or model underneath it changes?
</p>

## Why this exists

You wrote a skill and it works. Then the harness ships a new version, or a
teammate runs it on a different one, and it quietly stops working — the CLI
never gets called, the file never gets written, the question never gets
asked. Nothing crashes. You just get a worse answer.

Here is one real run of `examples/scaffold-service` against three targets,
three cases each — the same run the GIF further down was recorded from:

| target | skill_fired | tool_used | artifact_created | inputs_resolved |
|---|---|---|---|---|
| `claude-code/claude-opus-5` | 3/3 | 3/3 | 3/3 | 1/1 |
| `gemini-cli/gemini-3.6-flash` | 3/3 | 3/3 | 2/3 | **0/1** |
| `ollama-cloud/gpt-oss:120b` | 3/3 | 3/3 | 2/3 | **0/1** |

All three fired the skill every time and called the CLI every time. Two of
them then made up the answer to a question the skill told them to ask.
Gemini's own words, from the transcript:

> Since this is a non-interactive CI/headless environment, I will use my
> best judgment: **Owner:** `jasperginn` (retrieved from the system's Git
> user configuration), **Port:** `8080`

The owner was supposed to be `payments-team`, and the harness only had to
ask. Nothing crashed, `tool_used` is 100%, and the file is wrong.

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

Two more things it is careful about:

- **Isolation is reported, never assumed.** Two sandboxes: `tmp` (default,
  fast, **not isolated**) and `container` (isolated, built from an image or
  a Dockerfile). The report records which one ran, so a number is never read
  as isolated when it was not.
- **A harness is never marked down for a capability it lacks.** One that
  cannot resume a session gets `unsupported` on `inputs_resolved`, not a
  failure.

## Quick start

You need [`uv`](https://docs.astral.sh/uv/) and at least one harness CLI on
your `PATH`.

**Trim `skeval.toml` before your first run.** It ships three targets —
Claude Code, Gemini CLI, and Claude Code pointed at Ollama Cloud through a
gateway. The third names a private host and wants `BIFROST_CC_VIRTUAL_KEY`,
and a declared variable that is unset is an error rather than an empty
string, so leaving it in fails a third of the matrix for everyone but its
author. Delete the targets you cannot reach.

```bash
uv sync
uv run pytest                          # no spend. pulls an image for the container tests.
uv run skeval doctor                   # is the harness usable? spends a little.
uv run skeval run examples/write-plan  # the matrix. spends money.
```

Then point it at your own skill:

```bash
uv run skeval init ./my-skill          # scaffold a skill that already passes
uv run skeval run ./my-skill --repeat 5 -j 5
```

The skill under test is a path, and nothing about it is configured anywhere
else. `skeval.toml` describes harnesses only.

## See it run

`skeval doctor` runs a canary skill through the harness and reports what it
observed:

![skeval doctor reporting six rows for the claude-code harness, all ok, verdict qualifies](assets/doctor.gif)

```
claude-code
  1  headless run                 ok  exit 0
  2  skill surfaced at runtime    ok  activated and ran the marker
  3  output parsed                ok  1 tool calls, 3 texts
  4  session resume               ok  2 turns
  5  no TTY required              ok  ran without a terminal
  6  environment visibility       ok  16 other skills visible; built-ins expected

qualifies
```

`skeval run` executes the matrix and prints a pass rate per target and
dimension, plus a warning when the sandbox was not isolated:

![skeval run executing the scaffold-service example across three targets, with a scores table and a failures table naming the two runs that failed](assets/run.gif)

Every run also writes `skeval-report.json` with the per-run detail behind
those numbers, including the argv, the tool calls, and the kept workspace
for anything that failed. `skeval summary` renders that as markdown for a PR
comment.

## Examples

Two skills and the images they can run in, all runnable as-is:

- [`examples/write-plan`](examples/write-plan) — the smallest useful shape.
  One artifact, two cases, one withheld fact.
- [`examples/scaffold-service`](examples/scaffold-service) — three cases,
  three artifacts with content expectations, two withheld facts, and a case
  that needs three CLI calls in a row.
- [`examples/docker`](examples/docker) — the images the `container` sandbox
  builds from, and what has to go in one.

## Adding a harness

Add a `[harness.*]` block **and** a `[[matrix]]` entry naming it — the
matrix is where the model comes from, and `doctor` reads it too. Then run
`doctor --harness <name>`, which puts a canary skill through the harness.
It takes a harness name, not a matrix label, so there is nothing to point
it at for a target that only exists as an env override. Its only
instruction is to ask one question and then run `echo skeval-ok`:

| # | prerequisite | required | how it is decided |
|---|---|---|---|
| 1 | headless run | yes | the process exited 0 and did not time out |
| 2 | skill surfaced at runtime | yes | the canary activated *and* the marker ran |
| 3 | output parsed | yes | the stream yielded tool calls or text |
| 4 | session resume | no | the conversation reached a second turn |
| 5 | no TTY required | yes | it exited 0 with no terminal attached |
| 6 | environment visibility | — | reports what else the model could see |

Five prerequisites, four of them required, and a sixth row that is context
rather than a verdict. A harness that cannot resume still qualifies, with
`inputs_resolved` marked unsupported. Row 6 cannot fail: it names the other
skills in scope, which on the `tmp` sandbox is usually your own.

Getting the canary call back at all is only possible if the harness ran
headless, discovered the skill, surfaced it to the model, followed it, and
emitted parseable output.

Verified so far: **Claude Code** and **Gemini CLI**. The two disagree about
almost everything — flags, where skills live, what the activation tool is
called, whether records are nested — and none of that reaches the skill
under test.

Claude Code also talks to anything Anthropic-shaped, so a gateway in front
of open models makes them targets too. That is what the `ollama-cloud` row
above is: the same harness, a `label`, and two environment variables.

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
path, and why `doctor` asserts on what the model saw.

## Layout

```
src/skeval/
  models.py       TOML -> Harness, Case, Target, Skill
  sandbox.py      temp dir or container; skill and bin seeded in
  runner.py       one turn = one subprocess; multi-turn is re-invocation
  events.py       two stream shapes -> ToolCall, text, denials
  checks.py       the precondition and the three checks
  conformance.py  the parametrized test the CLI runs
  plugin.py       pytest fixtures, parametrization, report sharding
  report.py       the JSON artifact and the scores in it
  console.py      the tables
  banner.py       the header
  doctor.py       the six prerequisites, decided by running them
  scaffold.py     what `skeval init` writes
  cli.py          a thin front for pytest
examples/
  write-plan/      SKILL.md, cases.toml, bin/planctl
  scaffold-service/  SKILL.md, cases.toml, bin/scaffoldctl
  docker/          images for the container sandbox
```

`pytest` works directly, and `skeval run` is a front for it. Positional
arguments are passed through; its own flags are not, so reach for `pytest`
when you want `-x` or `--lf`:

```bash
uv run pytest src/skeval/conformance.py -m live --skill examples/write-plan -x
```

## Contributing

Issues and pull requests are welcome. The useful contribution right now is a
third harness: add a `[harness.*]` block and a `[[matrix]]` entry, run
`doctor`, and open a PR with the output — including the checks that failed.
A harness that does not qualify is still worth knowing about.

Run `uv run pytest` before you push. It spends nothing on models; the
container tests want a running Docker and skip without one.
