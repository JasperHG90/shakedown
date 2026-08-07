# Your first run

You will scaffold a skill, check that your harness can be measured at all,
run the skill against it, and read the matrix that comes back.

This costs real money — every scenario is a live model call. The scaffolded
skill has two cases, so one run is two calls. Expect a few cents.

## Prerequisites

- shakedown installed, and `shakedown --version` prints a version.
  See [Install shakedown](../how-to/install.md).
- Claude Code on your PATH, authenticated. The scaffold targets it by
  default. Any other harness works too, but you will edit
  `shakedown.toml` first — see [Add a harness](../how-to/add-a-harness.md).

## 1. Scaffold a skill

Make an empty directory and scaffold into it:

```bash
mkdir shakedown-tutorial && cd shakedown-tutorial
shakedown init
```

```
  + my-skill/SKILL.md
  + my-skill/bin/notectl
  + shakedown.toml
  + shakedowns/my-skill.cases.toml

next: shakedown doctor, then shakedown run my-skill
```

Four files. Two of them are the skill, the part a user would install:

```
my-skill/
  SKILL.md      what the agent is told to do
  bin/notectl   the CLI the skill must go through
```

The third, `shakedowns/my-skill.cases.toml`, is what the skill is measured
against. It sits outside the skill for the same reason tests sit outside
the code they test, and it names its subject at the top:

```toml
skill = "../my-skill"
```

The fourth, `shakedown.toml`, describes the harness. Nothing in it mentions
your skill — the skill is a path you pass on the command line.

This scaffold is not a template with holes in it. It is a working skill that
asks for what it was not told and writes its file through `notectl`, so your
first run measures something real.

## 2. Check the harness

Before measuring a skill, find out whether the harness can be measured at
all:

```bash
shakedown doctor
```

```
             claude-code
  # prerequisite                     detail
  1 headless run                 ok  exit 0
  2 skill surfaced at runtime     ok  activated and ran the marker
  3 output parsed                 ok  1 tool calls, 3 texts
  4 session resume                ok  2 turns
  5 no TTY required               ok  ran without a terminal
  6 environment visibility        ok  16 other skills visible; built-ins expected

qualifies
```

`doctor` ships its own tiny canary skill whose only instruction is to run
`echo shakedown-ok`. Seeing that shell call is only possible if the harness
ran without a terminal, found the skill, showed it to the model, followed
it, and printed output shakedown could parse. That one shell call settles
rows 1, 2, 3 and 5 at once; the second turn settles row 4.

If the last line says `qualifies`, continue. If it names a failing row, fix
that before measuring anything — a harness that fails row 2 will score your
skill zero for reasons that have nothing to do with your skill.

Row 6 never fails. It reports how many other skills the model could see,
which on the default sandbox is usually your own installed ones.

## 3. Run the skill

```bash
shakedown run my-skill
```

Two cases, one target, so two live calls. It takes a minute or two:

```
                                       shakedown
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━┳━━━━━━━━┳━━━━━━┳━━━━━┳━━━━━━━━━━━━━━━┓
┃ target                    ┃ dimension        ┃ n ┃ passed ┃ rate ┃ n/a ┃ not triggered ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━╇━━━━━━━━╇━━━━━━╇━━━━━╇━━━━━━━━━━━━━━━┩
│ claude-code/claude-opus-5 │ artifact_created │ 2 │      2 │ 100% │   0 │             0 │
│ claude-code/claude-opus-5 │ inputs_resolved  │ 1 │      1 │ 100% │   1 │             0 │
│ claude-code/claude-opus-5 │ skill_fired      │ 2 │      2 │ 100% │   0 │             0 │
│ claude-code/claude-opus-5 │ tool_used        │ 2 │      2 │ 100% │   0 │             0 │
└───────────────────────────┴──────────────────┴───┴────────┴──────┴─────┴───────────────┘
      sandbox not isolated: numbers include whatever else the harness could see
report: shakedown-report.json
2 passed in 46.69s
```

Read a row as one question asked of one target.

- **`skill_fired`** — did your skill activate? If not, the run measured the
  bare model and the other three rows mean nothing.
- **`tool_used`** — did the agent go through `notectl`, instead of writing
  the file itself?
- **`artifact_created`** — does `NOTE.md` exist, non-empty, with the
  content the case demanded?
- **`inputs_resolved`** — the `missing-author` case never says who the
  author is. Did the harness ask, and did the answer reach the file?

The `n/a` column is why `inputs_resolved` shows `n` of 1 rather than 2: only
one of the two cases withholds anything, so the other is not scored on a
question it never asked. A check that does not apply is reported, never
counted against you.

The warning under the table is honest bookkeeping. The default sandbox is a
temporary directory on your machine, so the harness could see your other
installed skills. [Run in a container](../how-to/isolate-runs-in-a-container.md)
when you want that removed.

## 4. Make it fail

A green matrix on the first try tells you little. Break the skill and watch
the number move.

Open `my-skill/SKILL.md` and delete the whole `## Write it with notectl,
never yourself` section — the part telling the agent it may not write the
file itself. Save, and run one case:

```bash
shakedown run my-skill --case fully-specified
```

The agent now has no reason to use the CLI, and writes `NOTE.md` itself:

```
F                                                                          [100%]
==================================== FAILURES ====================================
______ test_conformance[claude-code/claude-opus-5-fully-specified-run0] ______
tool_used: no tool call mentions notectl

                                    shakedown
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━┳━━━━━━━━┳━━━━━━┳━━━━━┳━━━━━━━━━━━━━━━┓
┃ target                    ┃ dimension        ┃ n ┃ passed ┃ rate ┃ n/a ┃ not triggered ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━╇━━━━━━━━╇━━━━━━╇━━━━━╇━━━━━━━━━━━━━━━┩
│ claude-code/claude-opus-5 │ artifact_created │ 1 │      1 │ 100% │   0 │             0 │
│ claude-code/claude-opus-5 │ inputs_resolved  │ 0 │      0 │    — │   1 │             0 │
│ claude-code/claude-opus-5 │ skill_fired      │ 1 │      1 │ 100% │   0 │             0 │
│ claude-code/claude-opus-5 │ tool_used        │ 1 │      0 │   0% │   0 │             0 │
└───────────────────────────┴──────────────────┴───┴────────┴──────┴─────┴───────────────┘
        sandbox not isolated: numbers include whatever else the harness could see
                                     failures
┏━━━━━━━━━━━━━━━━━┳━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ case            ┃ run ┃ failed    ┃ reason                        ┃ workspace     ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ fully-specified │ 0   │ tool_used │ no tool call mentions notectl │ /var/folders… │
└─────────────────┴─────┴───────────┴───────────────────────────────┴───────────────┘
report: shakedown-report.json
1 failed, 1 deselected in 14.94s
```

`artifact_created` still passes — the file is there and it looks fine. Only
`tool_used` moved. That gap is the whole point: the output looked right and
the procedure was wrong, and nothing crashed to tell you.

`inputs_resolved` shows `—` because `--case fully-specified` selected the
one case that withholds nothing, so there was no question to ask.

Because the run failed, its workspace is kept. Open the path in the
`workspace` column and you will find the `NOTE.md` the agent wrote and the
raw harness output next to it.

Put the deleted section back before moving on.

## What you built

A skill measured against a real harness, and a failure you caused on purpose
and then read off a table. You also have `shakedown-report.json` in the
current directory, carrying every turn of every run: the exact `argv`, the
tool calls, and what the agent said.

## Next steps

- [Measure your own skill](../how-to/measure-your-own-skill.md) — replace
  the scaffold with the thing you actually ship.
- [Add a harness](../how-to/add-a-harness.md) — measure a second one, which
  is the point of the tool.
- [What shakedown measures](../explanation/what-shakedown-measures.md) — why
  the artifact, and not the transcript, settles the question.
- [The JSON report](../reference/report.md) — every field in the file you
  just produced.
