# Measure your own skill

Turn a skill you already ship into one shakedown can run.

## Prerequisites

- shakedown installed, and `shakedown doctor` reports `qualifies` for at
  least one harness.
- A skill with a `SKILL.md` that has `name` in its front matter.

## Procedure

### 1. Make the skill a self-contained directory

shakedown takes one path, and everything it needs lives under it:

```
my-skill/
  SKILL.md      required. `name` in the front matter is the skill's identity
  cases.toml    required. what to measure
  bin/          optional. executables the skill expects on PATH
```

Nothing about your skill is registered anywhere else. No name, no bin path,
no entry in `shakedown.toml`. Just the directory.

Anything in `bin/` is copied into the workspace and put on PATH, so a skill
that shells out to its own CLI works without installing anything.

### 2. Write the first case

A case is a prompt and what must be true afterwards.

```toml
[[case]]
name     = "fully-specified"
prompt   = "Write a project plan. Title: Billing migration. Owner: platform-team."
artifact = "PLAN.md"
tool     = "planctl"
```

Declare only what applies. `tool` names a CLI the skill must go through —
omit it for a skill that writes its own file, and the tool check reports
`unsupported` instead of failing.

### 3. Measure whether it asks

This is the check worth the effort, and it needs a case built for it.
Withhold something the skill needs, and say how to answer when asked:

```toml
[[case]]
name     = "missing-owner"
prompt   = "Write a project plan titled Billing migration."
artifact = "PLAN.md"
tool     = "planctl"

  [[case.answers]]
  match = "(?i)\\bowner\\b|who owns"
  reply = "platform-team"
```

Two things to get right:

- **`match` must be loose enough to catch the question as the agent phrases
  it.** "Who owns this?" and "What is the owner?" are both plausible, which
  is why the example is an alternation, case-insensitive.
- **`reply` must be a string that could not appear otherwise.** It is the
  evidence: `platform-team` reaching `PLAN.md` proves the harness asked,
  because that string is supplied nowhere else. A reply like `yes` proves
  nothing.

### 4. Run it

```bash
shakedown run ./my-skill
```

Start with one target and one repeat while you get the cases right. Widen
after:

```bash
shakedown run ./my-skill --repeat 5 --parallel 5
```

`--parallel` changes wall clock, not the number of model calls.

## Verification

You want the first run to be *informative*, not green. Check three things:

1. **`skill_fired` is 100%.** If not, nothing else on the row means
   anything — the run measured the bare model. Fix the skill's description
   before reading any other number.
2. **No dimension is entirely `n/a`.** A column of `n/a` means no case
   declared that check, so you are not measuring it.
3. **A deliberate break moves the right number.** Delete the instruction
   that tells the agent to use your CLI, rerun one case, and confirm
   `tool_used` drops while `artifact_created` holds.

## Troubleshooting

**`skill_fired` is 0%.** The harness never surfaced the skill. Check the
front-matter `description` — that is what the model matches a request
against — and confirm `doctor` row 2 passes for this harness.

**`inputs_resolved` fails but the agent clearly asked.** Either `match`
missed the phrasing, or the reply never reached the file. Open the failing
run's workspace and read `.shakedown-turn0.jsonl` to see what the agent
actually said.

**`tool_used` says "was requested but denied".** The harness refused the
call. Add the permission flag to `start` in `shakedown.toml` — for Claude
Code that is `--allowedTools` and `--permission-mode`.

**A case hangs.** Each turn is bounded by `--timeout`, 300 seconds by
default. Lower it while iterating: `shakedown run ./my-skill -- --timeout 60`.

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: add a harness](add-a-harness.md)
- [Reference: `cases.toml`](../reference/cases.md)
- [Explanation: what shakedown measures](../explanation/what-shakedown-measures.md)
