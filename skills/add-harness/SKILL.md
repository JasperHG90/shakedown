---
name: add-harness
description: >-
  Add a new agent harness (opencode, Gemini CLI, Codex, Amp, a local
  Ollama-backed runner, or any CLI that loads skills) to a shakedown config
  so its skill conformance can be measured, and diagnose a harness that
  `shakedown doctor` reports as not qualifying. Use this whenever someone
  wants shakedown to run against a harness it does not yet support, asks why
  a harness fails doctor, asks how to point an existing harness at a
  different model or provider, or is editing the `[harness.*]` block of a
  shakedown.toml. Use it even when they only name the tool ("can this test
  opencode?") without mentioning config or TOML.
---

# Adding a harness to shakedown

A harness is described entirely by config. No code is written to support
one, so this task is: find the flags, write the block, run `doctor`, and fix
whatever it names.

The reason `doctor` exists is that a harness can look configured and still
be measuring nothing. Every prerequisite below is verified by watching what
the agent actually did, never by reading a help string or an inventory
command.

## Step 1: Check the binary can do the five things

A harness qualifies if it can do these. Four are required.

| # | prerequisite | required | if missing |
|---|---|---|---|
| 1 | run headless from a prompt and exit on its own | yes | unusable |
| 2 | load a skill from a directory you control | yes | unusable |
| 3 | emit machine-readable output with tool calls and text | yes | unusable, unless it can export the transcript afterwards (Step 3) |
| 4 | continue a session | no | `inputs_resolved` reports `unsupported` |
| 5 | run without a TTY | yes | unusable |
| 6 | what else the model could see | reported only | nothing |

Read the binary's `--help` and find the flag for each. What you are looking
for, in the usual naming:

- A non-interactive or print flag (`-p`, `--prompt`, `run`).
- An output format flag naming JSON or stream-json. Newline-delimited JSON
  is what shakedown parses.
- A session identifier flag, and a resume flag that takes it.
- A model flag, so the same harness can be measured against several models.
- A permission or approval flag, discussed in Step 4.

Prerequisite 4 being optional is deliberate. A harness must never *fail* a
dimension it cannot physically support, so a harness with no resume is
reported as unsupported with a reason, and its other checks stay comparable
against everything else.

## Step 2: Write the block

```toml
[harness.my-harness]
start = [
  "my-agent", "run", "{prompt}",
  "--json",
  "--model", "{model}",
  "--session", "{sid}",
]
resume = [
  "my-agent", "run", "{reply}",
  "--json",
  "--model", "{model}",
  "--resume", "{sid}",
]
skills = ".my-agent/skills"
activation_tool = "Skill"

# Exactly one of these, and only for `--sandbox container`:
image      = "ghcr.io/you/my-agent:1.2.3"
# dockerfile = "docker/my-agent.Dockerfile"

[harness.my-harness.env]
MY_AGENT_TOKEN = "${MY_AGENT_TOKEN}"

[[matrix]]
harness = "my-harness"
models  = ["some-model"]
```

**Commands are lists, not strings.** Each token is one argument, so a prompt
containing a quote or a leading dash stays a prompt and can never become a
flag. Substitution slots are `{prompt}`, `{reply}`, `{model}`, and `{sid}`.

**`skills`** is the directory this harness scans for skills, relative to the
workspace. The skill under test is copied to `<skills>/<name>/`. Use the
harness's own discovery path, the one it would find a skill in with no flags
at all.

**`activation_tool`** is the substring identifying a skill-activation call
in this harness's output, `Skill` on Claude Code and `activate_skill` on
Gemini. It is what separates "the skill never fired" from "it fired and
failed". Without it a run where the model ignored the skill and improvised
scores as an ordinary failure, and the number then describes the base model
rather than the skill.

**`env` is declared-only.** The sandbox gets these variables and nothing
else, which is what makes host contamination structurally impossible rather
than something a flag suppresses. Values come from the host through `${VAR}`
so the TOML holds references, never secrets.

**`image` or `dockerfile`** is needed only for `--sandbox container`, and
declaring both is refused. Use `image` when you already build and push one,
and `dockerfile` when you would rather keep the environment in the repo.
Either way it holds the harness plus whatever the skills need at runtime,
because a skill whose `bin/` cannot execute fails checks for reasons that
have nothing to do with the skill. See `examples/docker/` for one per
shipped harness.

The path is relative to `shakedown.toml`, and it is built once per run
rather than per scenario.

## Step 3: Tell shakedown where the tool calls are

Harnesses put tool calls at different depths. This is the one shape
question, and it is config rather than code.

Run the harness once by hand with its JSON flag and look at a line
containing a tool call. Then choose:

- **Nested**: the call sits inside a list under a dotted path, as Claude
  Code's does in `message.content[]`. Set `container = "message.content"`.
- **Flat**: the call is a top-level record, as Gemini CLI's is. Omit
  `container` entirely.

Since this is a genuine fork with a short list of answers, present it as a
decision rather than a prose question, and show the harness's own output as
the preview so the choice is made against evidence.

The remaining keys are renames, and the defaults match Claude Code:

```toml
[harness.my-harness.events]
container     = ""            # dotted path to a list; omit if flat
discriminator = "type"        # the key naming a block's kind
tool_marker   = "tool_use"    # that key's value on a tool call
name_key      = "name"
args_key      = "input"
text_key      = "text"
text_marker   = "text"
```

The four that name a key — `discriminator`, `name_key`, `args_key`,
`text_key` — may each be a dotted path, which covers a flat record that
still buries what you need. opencode's tool call is top-level but carries
its name and arguments under a `part` object, so it reads `name_key =
"part.tool"` and `args_key = "part.state.input"`. (`tool_marker` and
`text_marker` are values compared against, not keys, so a dot in one does
nothing.)

A harness matching neither shape fails at `doctor` step 3, loudly, instead
of silently scoring zero everywhere.

### When the harness prints prose and nothing else

Some agents stream no events at all. Hermes prints only its final answer,
so there is nothing to parse while it works. Before writing it off, check
whether it can hand over the transcript afterwards: `hermes sessions
export --format trace` writes Claude Code JSONL, and a start command may
be two commands.

```toml
start = [
  "sh", "-c",
  "hermes -z \"$1\" -m \"$2\" >&2 && hermes sessions export --format trace --no-redact -",
  "hermes", "{prompt}", "{model}",
]
```

The prompt stays a positional argument (`$1`) rather than being pasted
into the script, so it is still exactly one argument and still cannot
become a flag. Check what the export does to the transcript on the way
out, too: Hermes redacts tool arguments unless told not to, and those
arguments are what `tool_used` reads. Send the harness's own prose to
stderr rather than `/dev/null`: a run that fails for its own reasons then
says why, instead of scoring as a skill that never fired.

## Step 4: Let the harness run the tool

Most harnesses refuse tool calls by default, and a refusal still appears in
the transcript as a call. A config that omits the permission flag therefore
produces runs where the CLI was requested, denied, and never executed.

shakedown reads the harness's denial records and fails `tool_used` with "was
requested but denied", so this shows up as a diagnosis rather than a silent
wrong number. Fix it in `start` and `resume` by allowing the tools the skill
needs.

Watch for a permission mode that covers file writes but not shell commands.
Claude Code's `acceptEdits` allows `Write` while still prompting for `Bash`,
so a skill that shells out to its CLI is denied under it.

## Step 5: Run doctor until it qualifies

```bash
shakedown doctor --harness my-harness
```

`doctor` runs a canary skill that asks one question, then runs
`echo shakedown-ok`. Seeing that shell call is only possible if the harness
ran headless, discovered the skill, surfaced it to the model, followed it,
and emitted parseable output, so one cheap task settles prerequisites 1, 2,
3 and 5 at once. The question is there to force a second turn, which
settles 4.

```
             my-harness
  # prerequisite                    detail
  1 headless run                 ok exit 0
  2 skill surfaced at runtime  FAIL never activated
  3 output parsed                ok 1 tool calls, 3 texts
  4 session resume               ok 2 turns
  5 no TTY required              ok ran without a terminal
  6 environment visibility       ok 16 other skills visible

does not qualify: blocked on skill surfaced at runtime
```

Work the failing number:

- **1 fails**: the command needs a headless flag, or it is waiting on input.
  A hang shows as a timeout rather than a non-zero exit.
- **2 fails with "never activated"**: `skills` points somewhere the harness
  does not scan. Check the canary landed there, in the workspace `doctor`
  prints at the end.
- **2 fails with "activated but never ran"**: discovery works and permission
  does not. Go back to Step 4.
- **3 fails**: the output is not newline-delimited JSON, or `events` does
  not match its shape. Go back to Step 3.
- **4 fails**: the resume flag did not carry the session. Some harnesses
  resume by literal `latest` rather than an id, which is safe here because
  the sandbox holds exactly one session. If the harness genuinely cannot
  resume, delete the `resume` line and let the check report `unsupported`.
- **6** never blocks. It reports how many other skills the model could see,
  which on the `tmp` sandbox includes everything installed on the host. Use
  `--sandbox container` when that contamination matters.

If `doctor` prints "has no `[[matrix]]` entry, so there is no model to
check it with", the harness is described but nothing names a model for it.
Add a `[[matrix]]` entry, or pass `--model` for a one-off check.

### Qualifying on `tmp` does not mean qualifying in a container

The sandbox is part of what you are configuring, and prerequisite 2 is a
different question in each. A harness can surface the skill perfectly on
`tmp` and never surface it in a container, because the container has a
different filesystem, a different `HOME`, and none of the host's
configuration. Every run then reports "never activated" and the skill
looks broken when the sandbox is at fault.

So if you intend to use `--sandbox container`, qualify it there too —
**but only once the credential is declared**, because a container inherits
nothing:

```toml
[harness.my-harness.env]
MY_AGENT_TOKEN = "${MY_AGENT_TOKEN}"
```

Without that, `doctor --sandbox container` fails on authentication, which
tells you nothing about discovery and is easy to misread as a harness that
does not qualify. Get the credential in first, confirm the harness runs at
all in the image, and only then trust what prerequisite 2 says there. A
subscription login is the awkward case: on macOS it lives in the Keychain
rather than in a file, so no amount of mounting carries it in and the
harness needs a token it can read from the environment.

## Pointing an existing harness at a different provider

Same binary, different model behind it. This is what separates harness
quality from model quality, so it is worth setting up.

```toml
[[matrix]]
harness = "claude-code"
label   = "claude-code/glm-4.6"
models  = ["glm-4.6"]
env     = { ANTHROPIC_BASE_URL = "https://open.bigmodel.cn/api/anthropic",
            ANTHROPIC_AUTH_TOKEN = "${GLM_TOKEN}" }
```

Give it a `label`. An `env` override changes what is behind the harness, and
comparing two backends under one name would silently average them together.

## Two traps worth naming

**Do not reach for an isolation flag that disables skills.** Claude Code's
`--safe-mode` lists skills among the customizations it turns off, so a run
using it never shows the skill to the model, and the result reads as "this
harness ignores instructions". Isolation belongs to the sandbox. Use
`--sandbox container`.

**A static inventory does not prove runtime visibility.**
`claude --plugin-dir X plugin details` reported `Skills (1)` for a run whose
init event showed the skill absent from the model's list. That is why the
skill is copied into the harness's own discovery directory, and why `doctor`
asserts on what the model did rather than on what a subcommand claims.
