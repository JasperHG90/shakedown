---
name: create-cases
description: >-
  Author a shakedown cases file (`shakedowns/<slug>.cases.toml`) for an
  existing agent skill: read the skill, turn what it promises into cases,
  supply fixtures for the commands it must not really run, and check the
  result with `shakedown case validate`. Use this whenever someone wants to
  measure, smoke-test, or add conformance cases for a skill, asks "how do I
  test this skill", points at a SKILL.md and wants cases written, or is
  editing a `.cases.toml`. Use it even when they only name the skill
  ("write cases for connect-agent-to-hub") without mentioning shakedown or
  TOML.
---

# Writing cases for a skill

A cases file says what a skill promises and how to tell whether it kept the
promise. shakedown then runs the skill on every harness and model you ship
to and reports which promises survive.

Everything here is one file plus, sometimes, a directory of stand-ins. You
are writing both, then proving they load.

## Step 1: Find the skill

The user may have named it already ("write cases for
`skills/connect-agent-to-hub`"). If not, ask for the path, and offer what
you can see: `ls skills/` or a `**/SKILL.md` glob usually finds the
candidates, and a short list is easier to answer than an open question.

Read its `SKILL.md` completely before writing anything. You are looking for
four things, and the rest of this skill is what to do with them:

- **What it produces.** A file, usually. That is `artifact_created`.
- **What it goes through.** A CLI the skill tells the agent to run rather
  than doing the work itself. That is `tool_used`.
- **What it needs from the user.** Anything the skill says to ask for
  rather than guess. That is `inputs_resolved`.
- **What it calls that reaches the world.** `gh`, `kubectl`, `aws`, `curl`.
  Those decide whether you need fixtures.

## Step 2: Map the promises onto the three checks

shakedown measures at most three things per case, plus one precondition it
always checks: did the skill activate at all. A case declares only the
checks that apply to it, and one it does not declare reports `unsupported`
rather than failing. Do not invent a check to fill a column.

| The skill promises | The case declares |
|---|---|
| writes `PLAN.md` | `[[case.artifacts]]` with `path`, and `contains` for the values that must land in it |
| goes through `planctl` | `tool = "planctl"` |
| asks before guessing the owner | `[[case.answers]]` with a `match` pattern and the `reply` |

An answer needs somewhere to land. `inputs_resolved` is proved by the
reply appearing in an artifact, so a case with `answers` and no
`[[case.artifacts]]` measures nothing at all — `case validate` will say so.

`tool` is a substring, matched against a call's name **and its arguments**.
A tool whose name turns up in what the skill writes is satisfied by the
writing: `tool = "shakedown"` passes on a `Write` to `shakedown.toml`, with
the CLI never run. Name enough of the command to rule that out —
`tool = "shakedown doctor"` — and check it against a plausible transcript
before believing it.

**Double every backslash in `match`.** It is a TOML basic string, where
`\b` is a backspace character rather than a word boundary, so
`match = "(?i)\bowner\b"` compiles to a pattern that can never fire. The
case then passes validation, costs a real run, and fails with "no `match`
fired", quoting back a question the agent asked plainly. The fault is in
this file.

```toml
[[case]]
name   = "withholds-the-owner"
prompt = "Write a project plan titled Billing migration."
tool   = "planctl"

  [[case.artifacts]]
  path     = "PLAN.md"
  contains = ["platform-team"]

  [[case.answers]]
  match = "(?i)\\bowner\\b|who owns"
  reply = "platform-team"
```

`match` has to be loose enough to catch the question however the agent
phrases it, and `reply` has to be a string that could appear no other way.
`platform-team` reaching `PLAN.md` proves the harness asked; a reply of
`yes` proves nothing.

Two or three cases is usually right, and they should differ in kind rather
than in wording:

1. **Fully specified.** Everything the skill needs is in the prompt. This
   measures whether it does the job at all.
2. **Something withheld.** Leave out one fact the skill says it must ask
   for, and supply the reply through `answers`. The proof is that the reply
   reaches the artifact: it is only ever given in answer to a question, so
   it cannot appear unless the harness asked. This is the case that catches
   a model inventing a plausible value, which is the most expensive failure
   a skill has, because the output looks right.
3. **A judgment call.** Where the skill maps the user's words onto its own
   categories — an environment onto a tier, a description onto a type.

### Make `contains` fail when the answer is wrong

This is where most cases are too weak. A `contains` that names a value
alone passes whichever slot it landed in, so a skill that put production
into the test tier still scores 100%. Assert the pairing, across the
newline if the format has one:

```toml
contains = ["  test:\n    backend: https://…/checkout-test-4417/…"]
```

Before you believe a case, ask what a plausible wrong answer looks like and
check that the case rejects it. If you cannot think of one, the case is
probably measuring the format rather than the judgment.

## Step 3: Decide what must not really run

A skill that clones a repository, opens a pull request, or calls a cloud
API cannot be measured by letting it do those things: it needs credentials
the sandbox has not got, and a run that did authenticate would leave real
side effects behind.

Search the skill and its scripts for what it shells out to, and show the
user the list rather than deciding for them:

```bash
grep -rnoE '\b(gh|git|kubectl|aws|gcloud|terraform|curl|docker)\b' <skill-dir> | sort -u
```

Then ask, as a decision rather than a prose question, which of these should
be replaced. Some should not: `git` operating on a local clone is real work
worth measuring, and faking it would measure the fake.

`fixtures` names a directory of stand-in executables, seeded into the
sandbox's `bin/` ahead of everything else on PATH. Several directories are
allowed and later wins, so a double shared between skills combines with the
ones only this skill needs:

```toml
fixtures = ["fixtures/common", "fixtures/register-service"]
```

Fixtures live beside the cases, never inside the skill — a fake `gh`
shipped in `<skill>/bin/` installs onto the machine of everyone who uses
the skill, and shakedown refuses a `fixtures` path that points inside.

### Writing a double that does not lie

A double is only useful if a broken skill still fails. Four rules earn
that, and each one comes from a way a double has quietly passed a bad run:

- **Fake the boundary, not the work.** Replace only what leaves the
  machine. If the skill clones and edits a repository, serve the clone from
  a local repository the double builds on first call, and let real `git` do
  the branch, the diff and the commit.
- **Die on anything unrecognized.** A double that exits 0 for a verb it
  does not answer hands the skill an empty success, and the run gets scored
  on it.
- **Leave the evidence where checks can read it.** A skill that works in a
  temp directory it deletes leaves nothing to assert on. Have the double
  copy the result into the workspace — `pr/`, say — and point the artifact
  check there.
- **Record the calls.** Appending each invocation to a log file in the
  workspace turns "did it try" into something a `contains` can check, and
  tells you what happened when a run fails.

The double locates the workspace itself, so the same one works for any
skill:

```bash
WORK="$(cd "$(dirname "$0")/.." && pwd)"
```

Recording is then one line at the top:

```bash
echo "$(basename "$0") $*" >> "$WORK/$(basename "$0")-calls.log"
```

Write each double at `shakedowns/fixtures/<slug>/<command>` — the directory
the `fixtures` key names, resolved relative to the cases file — and make it
executable. Nothing checks the bit for you, and a double at mode 644 does
not fall through to the real command: the shell refuses it outright, and
the run fails with an error naming neither the fixture nor the permission.

```bash
chmod +x shakedowns/fixtures/<slug>/*
```

### Check the call log like any other file

The log is a file in the workspace, so an artifact check reads it:

```toml
  [[case.artifacts]]
  path = "gh-calls.log"
  contains = ["pr create --base main --head register-checkout"]
```

Check the log for what the result cannot show. `register-checkout` is a
branch name only `registerctl` builds, so an agent that ignored the CLI and
ran `git` and `gh pr create` by hand fails here while `pr/services/checkout.yaml`
still matches. That is stricter than `tool`, which passes on
`registerctl --help`. Where the artifact already carries the evidence,
checking the log repeats it and breaks whenever the CLI changes its flags.

Two things the log cannot do:

- **It is not the command line.** `echo "$*"` joins the arguments with
  spaces and throws the quoting away, so `--title "Register checkout"` is
  logged unquoted and `--body ""` disappears. Match unquoted text, and never
  let a substring straddle an argument that might contain a space.
- **It must not go in a case that declares `answers`.** `inputs_resolved`
  looks for the reply across every artifact the case declares. A log holding
  the command line lets a reply prove itself by appearing in an argument the
  skill *passed*, when the check exists to prove it reached what the skill
  *produced*.

Leave temp paths and generated titles out of the substring — they change
between runs.

## Step 4: Ask what you missed

You have read one file and grepped for command names. The user knows things
you cannot see: a service that must be reachable, a config the skill reads,
an environment variable, a second CLI invoked only on a branch you did not
notice. Ask plainly what else the skill depends on before you call the file
done — this catches more than another pass over the source would.

## Step 5: Write it, then prove it loads

Write to `shakedowns/<slug>.cases.toml`, where `<slug>` is the skill
directory's name. `skill` and `fixtures` are file-level keys and belong
above the first `[[case]]`: TOML gives a bare key written after a table to
that table, so one placed below it silently becomes part of that case.

```toml
version = 1
skill   = "../skills/my-skill"

[[case]]
name   = "fully-specified"
prompt = "…"
tool   = "myctl"

  [[case.artifacts]]
  path     = "OUT.md"
  contains = ["…"]
```

Then check it, which costs nothing:

```bash
shakedown case validate shakedowns/<slug>.cases.toml
```

It prints each case and the checks it measures. This is free and
deterministic, so run it after every edit rather than once at the end, and
do not offer the paid run until it is clean.

Read all of what it says, not just the exit code:

- **It exits 2.** The file does not load. The message names the key and,
  where there is one, the remedy — a `fixtures` path that is not a
  directory, a `skill` that resolves to something without a `SKILL.md`, a
  key placed under a `[[case]]` that belongs above the first one. Fix and
  re-run; do not work around it by deleting the key.
- **A case measures "nothing but skill_fired".** It will pass no matter
  what the skill does. Give it something to prove, or delete it.
- **"answers with no artifact".** The reply has nowhere to land, so asking
  is not measured. Add the artifact the answer should reach.
- **A name it warns about.** Whitespace or a duplicate means `--case`
  cannot select that case later.

## Step 6: Offer to run it

Everything so far worked on files alone, which is why no harness was needed
to get here — cases are often written on a machine that never runs them.
Running is different, so check the ground before offering it:

```bash
command -v <the harness CLI named in shakedown.toml>
```

A missing binary makes the offer a waste of the operator's time, and the
failure it produces reads like a broken skill rather than an absent CLI.
If none is installed, say which one the config names and stop there; the
cases file is still finished and still worth committing. Same if there is
no `shakedown.toml` to be found: the run needs one, and `init` writes it.

Then offer rather than assume, and say roughly what it will cost: one model
round trip per case per target, plus a second turn for any case that
withholds something.

```bash
shakedown case run shakedowns/<slug>.cases.toml --harness <one> --keep
```

Narrow to one harness first. `--keep` leaves the workspaces, which is what
makes a failure diagnosable.

Read the outcome before changing anything, because the three failures want
different fixes:

- **`not_triggered` ("never activated").** Nothing was measured, so treat
  this as a harness question before a skill question. On Claude Code the
  run's `.shakedown-turn0.jsonl` opens with an init event listing the
  skills the model was offered: if yours is missing from it, the sandbox
  or the harness config is at fault, not your description. Other harnesses
  do not emit that list, so there read the tool calls instead and see
  whether the activation tool was called at all. A skill that was offered
  and activated never reports `not_triggered`, so if you are staring at
  this status with the name in the init list, suspect a mismatch between
  the directory name and the `name` in the front matter.
- **`tool_used` failed.** Either the model did the work itself, which is a
  real finding about the skill, or the CLI was not on PATH, which is yours
  to fix.
- **`artifact_created` failed.** Read the file the run actually produced
  before assuming the skill is wrong. Half the time the case asserted a
  format detail the skill never promised.

Iterate until it passes for the right reason. A green run whose cases could
not have failed is worse than a red one, because it gets believed.
