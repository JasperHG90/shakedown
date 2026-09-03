---
name: analyze-results
description: >-
  Read a shakedown report (`shakedown-report.json`) and say which file to
  open: the measured skill's own `SKILL.md`, the
  `shakedowns/<slug>.cases.toml` holding its cases, the harness block in
  `shakedown.toml`, or a flag on the run itself. Use this whenever someone
  has run `shakedown case run` and wants to know what a number means or
  what to do about it, pastes a report or the PR comment rendered from one,
  asks why `skill_fired`, `tool_used`, `artifact_created` or
  `inputs_resolved` came out low, asks whether a rate is worth acting on,
  or says a conformance run failed and they cannot tell whose fault it is.
  Use it even when they only quote the percentage ("my skill scores 60% on
  inputs_resolved, now what") without naming shakedown or the report file.
---

# Reading a shakedown report

A report is a handful of percentages, and the operator's question is never
what the number is. It is which file to open.

`inputs_resolved: 60%` has two completely different causes. The skill
guessed a value it was supposed to ask for, which is a defect in the
skill's `SKILL.md`. Or the agent did ask, in words the case's `match`
pattern never covered, which is a defect in
`shakedowns/<slug>.cases.toml`. Those are different files, usually owned by
different people, and one of them is not broken at all. The report holds
enough to tell them apart, so a diagnosis that ends at "consider improving
the skill" has thrown away the only thing that made the run worth paying
for. **Every finding you report ends at a path.**

## The report is self-sufficient

You do not need the workspace, and you do not need the run to have been
made with `--keep`. `runs[].detail[].said` is an array of the text the
agent produced on that turn, and it is there for every turn of every run,
kept or not. That plus the `reason` on each result is the whole basis for
the routing below.

Two things do depend on the workspace surviving:

- `runs[].workspace_kept` says whether it did. A run with a check in
  `fail` always keeps its workspace, so anything you route below is on
  disk. Everything else is deleted unless the operator passed `--keep`,
  and that includes a run where the skill never activated, since
  `not_triggered` is not a failure. The one row where you would most like
  a workspace is the one least likely to have one.
- `runs[].detail[].stream` points at the raw newline-delimited JSON for
  that turn. It is written as an empty string when the workspace was
  cleaned rather than left as a path to a directory that no longer exists,
  so an empty `stream` means "cleaned up", not "nothing was recorded". Read
  `said` instead, which is still there.

Open the raw stream only when `said` and the reasons leave you guessing.
It is the same conversation with the framing left on.

## Step 1: Check whether the skill fired, before reading anything else

A run where the skill never activated measured the bare model. Every other
number on that row describes something you did not write, so it is not
merely unreliable, it is about a different subject. Settle this first and
report nothing else about that target until it is fixed.

**`skill_fired` never reads 0%.** The check returns `pass` or
`not_triggered`, and `not_triggered` stays out of the rate, so the column
reads `100%` or `n/a` no matter how many runs failed to activate. Read the
counts, not the rate:

```bash
jq '.scores | map_values(.skill_fired)' shakedown-report.json
jq '.summary.not_triggered' shakedown-report.json
```

- `not_triggered` at 0 across every target: the skill fired everywhere.
  Move on to Step 2.
- `rate: null` with `not_triggered` equal to that target's run count:
  nothing fired there at all.
- `rate: 1.0` with `not_triggered` above 0: some runs fired and some did
  not. This is the case worth catching, because the row reads `100%` and
  looks clean. Every other rate on it was computed over the runs that
  fired and silently excludes the rest.

`summary.ok` counts a run where the skill never activated as ok, because
`ok` means no check reported `fail` and `not_triggered` is not a failure.
So a report reading `ok: 7` of 11 can be seven runs that proved something
and can be five, and the operator's sense of how bad the run was comes
from that line. Subtract `summary.not_triggered` from it before you quote
it back.

Then route it, because "fix your description" is wrong most of the time
here:

| What the report shows | Open |
|---|---|
| No target fired, on any case | `shakedown.toml`: every harness's `skills` path and `activation_tool` |
| One target fired, another never did | The silent harness's block alone: same two keys, read against the one that worked |
| A target fired for one case and not another | The skill's `SKILL.md` front-matter `description` |

Confirm either of the first two with `shakedown doctor --harness <name>`
before editing, and read row 2 of what it prints. It runs a canary skill
and reports whether the harness surfaced it, which separates a broken
`skills` path from a description nobody matched.

Only the third row is a skill problem. A `description` is matched against
the request, so a description that is too narrow fails on the prompts it
does not cover and succeeds on the ones it does. A skill the harness never
surfaced fails uniformly, and no amount of rewriting the description will
move it.

## Step 2: Route each failure to a file

Work from `summary.failures[]`. Each entry carries `case`, `run`, `target`,
`failed` (the check names) and `reasons` (parallel to it). The reason
strings below are the ones shakedown emits, so match on them.

```bash
jq '.summary.failures[] | {case, target, failed, reasons}' shakedown-report.json
```

A run usually fails two checks at once, and one of them is a consequence
of the other. `artifact_created` in particular rarely fails on its own:
the file is missing because the tool was denied, or because the run
stalled waiting on a reply. Route the run by the check that explains it
and report the other as downstream rather than as a second finding, so the
operator gets one file to open instead of two. When `artifact_created`
does fail alone, its reason names the file and what it lacked, and that is
a question about the case's `contains` as often as about the skill: read
the file in the kept workspace before deciding which.

### `tool_used`: "was requested but denied"

The harness refused the call. The skill did its job and never got to run.

Open **`shakedown.toml`**, the `start` argv for that harness, and the
`resume` argv beside it, since a denial on turn two fails the same way.
`runs[].detail[].denied` names what was refused, which tells you what to
allow. For Claude Code that is `--allowedTools` and `--permission-mode`.

Watch for a permission mode that covers file writes but not shell
commands. `acceptEdits` allows `Write` and still prompts for `Bash`, so a
skill that shells out to its CLI is denied under it while a skill that
writes its own file passes. That asymmetry is why this failure gets
misread as a skill defect.

The other `tool_used` failure, "no tool call mentions X", is not this one.
It means no call was made at all: either the model did the work itself,
which is a real finding about the skill, or the CLI was not on PATH, which
is the operator's to fix.

### `inputs_resolved`: "no `match` fired"

A reply was still owed and nothing the agent said matched any remaining
pattern. Match the reason from its start, not from its ending: this
section covers only a reason opening ``no `match` fired for``. A reason
opening `X went unsupplied` ends in the same words about nothing being
written and means close to the opposite, so it is under the six-turn cap
below.

The reason quotes the ending, and `runs[].unmatched_tail` holds
the same text unwrapped, up to the last 500 characters the agent said.
**This is the single most useful field in the file.** Read it before
forming any opinion.

```bash
jq -r '.runs[] | select(.unmatched_tail != "") | "\(.case) run\(.run): \(.unmatched_tail)"' \
  shakedown-report.json
```

What the tail says decides the file:

- **The tail is a question.** The agent asked and the pattern missed it.
  Open **`shakedowns/<slug>.cases.toml`** and widen the `match` for that
  answer until it covers the phrasing you just read.
- **The tail is not a question.** The agent stopped, refused, or wandered.
  Open the skill's **`SKILL.md`** and look at what it says about asking.
- **The tail is empty.** The turn produced tool calls and no text, so
  there was nothing to quote. A run like this does not come back from the
  filter above, so find it by its reason and not by its tail. Go to the
  raw `stream`, or rerun that one case.

Before widening a pattern, check it can fire at all. `match` is a TOML
basic string, so `match = "(?i)\bowner\b"` compiles `\b` as a backspace
character rather than a word boundary and can never match anything. The
case validates, costs a real run, and fails here quoting a question the
agent asked perfectly plainly. Doubling the backslashes is the whole fix.

**shakedown deliberately does not call this a question that was never
asked, and neither should you.** Matching cannot separate "asked in words
your pattern missed" from "never asked, guessed instead". The check
reports the fact, that no pattern fired, and leaves the judgment to
whoever reads the tail. Preserve that when you write it up: say what the
agent ended on and what you conclude from it, rather than reporting a
confident story the report does not support.

Note also that for some skills, refusing to proceed and writing nothing is
the correct outcome. "no `match` fired for X, and nothing was written" can
be a skill behaving exactly as designed against a case that assumed it
would carry on. Check what the skill promises before calling this a bug.

### `inputs_resolved`: the reply never reached the artifact

Two reasons say this, and they route to different files. A third reads
almost like the first and is neither: `PLAN.md was written with X still
unsupplied` is the six-turn cap, below.

**"X was never supplied, yet PLAN.md was written anyway"**. The file
arrived without the answer. The agent either guessed a value or asked past
the pattern and carried on regardless. Read `unmatched_tail` to tell
which: a tail that announces a chosen default ("I set the owner to
engineering-team") is a guess, and that is the expensive failure, because
the output looks right. Open the skill's **`SKILL.md`** and find what it
says about asking. Half the time there is no such rule and the fix is to
write one. The other half the rule is already there, stated plainly, and
was overridden anyway: then the edit is placement, not force. Move the
prohibition into the step where the value is actually used, because a rule
in an earlier section has been read and passed by the time the agent is
building the command. Adding another emphatic sentence to a rule already
being ignored changes nothing.

If the tail is a question instead, the `match` in the cases file missed it
*and* the skill went ahead without an answer. Both files are at fault, and
the skill's half is the more serious of the two.

**"replies absent from the artifacts: X"**. Different failure entirely.
The reply *was* supplied, so `runs[].replies` lists it and the harness
asked and was answered. The answer then did not land in the file. Either
the skill discarded it, which is a **`SKILL.md`** problem, or the
`contains` in **`shakedowns/<slug>.cases.toml`** asserts a form the skill
never writes, such as a label the skill spells differently. Read the
artifact in the kept workspace before deciding.

### `inputs_resolved`: the six-turn cap

Two reasons come from here, and both mimic a section above:

- `X went unsupplied, and nothing was written`
- `PLAN.md was written with X still unsupplied`

A conversation stops after six turns, which is one opening turn and five
replies, so a case withholding six or more facts runs out of turns with
one still owed. Nothing failed to match. The run simply ended, and the
agent's last words were never put to a pattern at all.

That makes these the one branch where the tail carries nothing and is
*supposed* to. `unmatched_tail` is empty by construction here, so an empty
tail is not evidence the agent said nothing, and reading it as a silent
stall inverts the diagnosis. Neither the `match` patterns nor the skill's
rule about asking is implicated: no pattern was tried and no question went
unanswered.

Open **`shakedowns/<slug>.cases.toml`** and count the `[[case.answers]]`
blocks on that case. More than five cannot all be supplied. Split the case
or withhold fewer facts. Nothing in the skill needs to change, and a run
that also shows a written artifact does not mean the agent guessed: the
file was produced before the turns ran out.

### `inputs_resolved`: "the run timed out"

Evidence about nothing. The reason says so itself, so do not read the row
as a skill that failed to ask.

Find what hung. `runs[].detail[]` with `exit_code` of `-1` is the turn
that timed out, its `duration_s` sits at the ceiling, and `tool_calls` on
that turn shows what it was doing when the clock ran out.

```bash
jq '.runs[] | select(any(.detail[]; .exit_code == -1)) | {case, run, duration_s}' \
  shakedown-report.json
```

Two fixes. What the turn was doing when it stopped decides which:

- **The last `tool_calls` entry shells out to a command the cases file
  supplies.** It hung on a fixture. A double that waits on stdin, or
  shells out to something that does, never returns and burns the whole
  timeout on every run. Open that fixture, under the directory the cases
  file's `fixtures` key names, and read `stderr_tail` on the turn too.
- **Anything else.** The turn was working and 300 seconds was not enough.
  Raise the bound, as below.

`--timeout` has no flag of its own on `shakedown case run`. It bounds one
turn rather than the whole run, so it reaches pytest after `--`:

```bash
shakedown case run ./my-skill -- --timeout 600
```

Expect the turn to hold nothing much: no useful tool calls, `said` empty
because the agent never finished a sentence, `stderr_tail` empty because
the harness was killed rather than failing. Say the report cannot settle
it rather than inventing a cause, then rerun that one case at a *lower*
timeout. A hang caught in 60 seconds costs a fifth of one caught at the
default, and a turn that was genuinely working still shows what it got
through before the shorter clock stopped it.

### A mixed rate resting on too few runs

Not a defect, and not a file to open. This one exists so that nobody
rewrites a working skill to chase noise.

**It restrains what you say about the rate, not what you do about a
failure you have diagnosed.** A single run carrying `denied: ["Bash"]` is
a fact about that run, and it stays worth fixing whether the column above
it reads 89% or 8%. Everything in Step 2 came from a named run and a
quoted reason, so none of it is weakened here. What this section forbids
is the other kind of finding: the one whose whole evidence is that a
percentage looked low.

`scores.<target>.<dimension>.per_case` counts the scored runs behind the
*thinnest* case in that pool. That is the number that says whether a rate
is worth acting on, and the `scored` count is not: five cases run twice
also totals ten, while being two attempts at each of five different
things.

Being a floor, it describes the pool rather than any one case. One case
run once drags `per_case` to 1 for every dimension while a sibling case
was tried twenty times, so read it as "this pool contains something
barely tried" and count the runs per case yourself before deciding which
case that was.

Mind the denominator too. `scored` excludes `unsupported`, so a target
showing `scored: 5, unsupported: 4` produced nine runs and rated five of
them, and `inputs_resolved: 40%` there is two passes out of five rather
than out of nine. Quote the rate the report computed rather than dividing
again from the run count.

```bash
jq '.scores | map_values(with_entries(select(.value.rate != null and
  .value.rate > 0 and .value.rate < 1 and .value.per_case < 10)))' shakedown-report.json
```

Anything that survives that filter is a mixed rate over fewer than ten
runs per case. Report it as a hint, name the number, and say what it would
take to settle it:

```bash
shakedown case run ./my-skill --case missing-owner --harness claude-code --repeat 20 -j 5
```

Narrow to the one case and the one target actually in question. Every
repeat is another live model call per case per target, so widening the
matrix twenty times buys mostly numbers nobody asked about. Ten is where
the caution stops because that is where a live matrix stops being cheap,
not because ten runs make a rate trustworthy: eight in ten is still
consistent with anything from about half the time to almost always.

Say plainly that the rate alone warrants no edit. An operator who came
for a verdict will otherwise fix something, and a skill rewritten against
four runs is a skill rewritten against a coin flip. If Step 2 already
routed a diagnosed failure inside that same pool, name it here as the
thing to fix and the rate as the thing to leave alone, so the two do not
read as one recommendation.

## Step 3: Write it up

Lead with the ordering, then one finding per symptom. For each one give
the evidence you read, the file, and the edit:

```
skill_fired: gemini-cli/gemini-2.5-pro never activated on either run
(not_triggered: 2, rate: n/a), so nothing else on that row was measured.
claude-code fired on all 9.

1. inputs_resolved 40% on claude-code, missing-owner run 0
   Evidence  no `match` fired for platform-team; the agent ended on
             "who should be listed as the responsible party?"
   File      shakedowns/write-plan.cases.toml
   Edit      the answer's `match` covers "owner", not "responsible
             party". Widen the alternation.
```

Two habits keep this honest. Quote the report rather than paraphrasing it,
because the distinction between "asked past your pattern" and "guessed" is
carried in the agent's exact words. And when the evidence does not settle
which of two files is at fault, say both and say what would separate them,
rather than picking the likelier one and presenting it as a finding.
