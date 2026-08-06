# Getting started

Evaluate your own skill, on the harnesses you care about.

## 1. Install

```bash
uv sync
```

## 2. Make your skill a self-contained directory

`skeval` takes one path. Everything it needs lives under it:

```
my-skill/
  SKILL.md          required. `name` in the front-matter is the skill's identity
  cases.toml        required. what to measure
  bin/              optional. executables the skill expects on PATH
```

Nothing is configured about your skill anywhere else. No name, no bin path,
no registration. Just the directory.

## 3. Write `cases.toml`

A case is a prompt and what must be true afterwards. Three things get
checked, and each is optional: a case declares only what applies to it.

| check | declared by | omitted means |
|---|---|---|
| tool use | `tool` | `unsupported` |
| asking for input | `[[case.answers]]` | `unsupported` |
| artifacts exist, with the right content | `artifact` / `[[case.artifacts]]` | `unsupported` |

`skill_fired` always applies: it is the precondition, not a dimension.

`tool` names a CLI the skill must go through. Omit it for a skill that
writes the artifact itself.

```toml
[[case]]
name     = "fully-specified"
prompt   = "Write a project plan. Title: Billing migration. Owner: platform-team."
artifact = "PLAN.md"
tool     = "planctl"        # optional
```

Without `tool`, the tool check reports `unsupported` rather than failing,
the same way a harness that cannot resume is not marked down for it.

To measure whether your skill **asks** for what it was not told, withhold
something and say how to answer:

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

`match` triggers the reply. The proof is that `platform-team` ends up in
`PLAN.md`: that string is supplied only in answer to a question, so it
cannot appear unless the harness asked, accepted, and acted.

### Several artifacts, and what must be in them

`artifact = "X"` is shorthand. The long form takes a list, and each entry
may require content:

```toml
[[case]]
name   = "scaffold"
prompt = "Scaffold the billing service."
tool   = "scaffoldctl"

  [[case.artifacts]]
  path     = "src/billing/__init__.py"

  [[case.artifacts]]
  path     = "README.md"
  contains = ["billing", "platform-team"]
```

Every declared artifact must exist, be non-empty, and contain each of its
`contains` strings. A missing file or a missing string is named in the
failure.

### Asking for input

Add a `[[case.answers]]` block per fact you withhold. One unused match is
supplied per turn, so a case withholding two things runs three turns and
both replies must reach the artifact:

```toml
[[case]]
name     = "missing-both"
prompt   = "Write a project plan."
artifact = "PLAN.md"

  [[case.answers]]
  match = "(?i)\\bowner\\b"
  reply = "platform-team"

  [[case.answers]]
  match = "(?i)\\btitle\\b"
  reply = "Billing migration"
```

## 4. Check your harness

```bash
uv run skeval doctor
```

```
             claude-code
  # prerequisite                    detail
  1 headless run                 ok exit 0
  2 skill surfaced at runtime     ok activated and ran the marker
  3 output parsed                 ok 1 tool calls, 3 texts
  4 session resume               ok 2 turns
  5 no TTY required              ok ran without a terminal
  6 environment visibility       ok 16 other skills visible; built-ins expected

qualifies
```

`doctor` runs a canary skill whose only instruction is to run
`echo skeval-ok`. Seeing that call is only possible if the harness ran
headless, discovered the skill, surfaced it to the model, followed it, and
emitted parseable output.

## 5. Run it

```bash
uv run skeval run ./my-skill
uv run skeval run ./my-skill --repeat 5 --parallel 5
uv run skeval run ./my-skill --harness claude-code --case missing-owner
uv run skeval run ./my-skill --sandbox container
```

Every run is independent, so `--parallel` spreads them across processes.
The report is merged back into one artifact.

### Sandboxes

`tmp` (default) runs on the host. Fast, and **not isolated**: the harness
can see your installed skills and MCP servers. The report records
`isolated: false` so the numbers are read with that in mind.

`container` runs inside the harness's `image`, which has no developer
configuration to pick up, and pins the harness version as a property of
the image.

The container needs two things your host run gets for free:

- **The CLI in the image.** Set `image` and `install`.
- **Credentials as env.** OAuth tokens on your host are not visible inside
  the container, so a harness that authenticates by browser login needs an
  API key declared in `[harness.*.env]` instead.

## 6. Read the report

`skeval-report.json` carries every run and the scores derived from them:

```json
{
  "skill": "write-plan",
  "sandbox": "tmp",
  "isolated": false,
  "runs": [
    {
      "target": "claude-code/claude-opus-5",
      "case": "missing-owner",
      "run": 0,
      "turns": 2,
      "asked": ["platform-team"],
      "results": [{"name": "tool_used", "status": "pass", "reason": "invoked planctl"}]
    }
  ],
  "scores": {
    "claude-code/claude-opus-5": {
      "tool_used": {"passed": 3, "scored": 3, "rate": 1.0, "unsupported": 0, "not_triggered": 0}
    }
  }
}
```

`unsupported` and `not_triggered` stay out of `rate`. A harness that cannot
resume a session is not marked down for it, and a run where the skill never
activated measured the base model rather than your skill.

---

# Adding your own harness

Any binary qualifies if it can do five things. `doctor` verifies each by
running them.

| # | prerequisite | required |
|---|---|---|
| 1 | headless run with a prompt, exits on its own | yes |
| 2 | loads a skill from a directory you control | yes |
| 3 | machine-readable output with tool calls and text | yes |
| 4 | continue a session | no |
| 5 | runs without a TTY | yes |

Missing 4 means the `inputs_resolved` check reports `unsupported`. It is
never a failure.

## The block

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

image   = "ghcr.io/you/my-agent:1.2.3"
install = "npm i -g my-agent@1.2.3"

[harness.my-harness.env]
MY_AGENT_TOKEN = "${MY_AGENT_TOKEN}"

[harness.my-harness.events]
container = "message.content"

[[matrix]]
harness = "my-harness"
models  = ["some-model"]
```

**Commands are lists**, so a prompt is always exactly one argument and can
never inject a flag. Slots: `{prompt}`, `{reply}`, `{model}`, `{sid}`.

**`skills`** is the directory the harness scans, relative to the workspace.
Your skill is copied to `<skills>/<name>/`.

**`env` is declared-only.** The sandbox sees these variables and nothing
else. Values come from the host via `${VAR}`; the TOML holds references,
never secrets.

**`activation_tool`** is the substring identifying a skill-activation call,
so `skeval` can tell "the skill never fired" from "it fired and failed".

## `events`: where a tool call sits

Two shapes exist in the wild. Both are config.

| harness | shape | setting |
|---|---|---|
| Claude Code | nested in `message.content[]` | `container = "message.content"` |
| Gemini CLI | top level | omit `container` |

Full set, with defaults:

```toml
[harness.my-harness.events]
container     = ""            # dotted path to a list; omit if flat
discriminator = "type"
tool_marker   = "tool_use"
name_key      = "name"
args_key      = "input"
text_key      = "text"
text_marker   = "text"
```

If your harness fits neither, `doctor` fails at step 3 rather than scoring
zero silently.

## Point a harness at a different provider

Same harness, different backing model. This is what isolates harness
quality from model quality.

```toml
[[matrix]]
harness = "claude-code"
label   = "claude-code/glm-4.6"
models  = ["glm-4.6"]
env     = { ANTHROPIC_BASE_URL = "https://open.bigmodel.cn/api/anthropic",
            ANTHROPIC_AUTH_TOKEN = "${GLM_TOKEN}" }
```

An `env` override produces a distinct label, because comparing across
backends under one name would be meaningless.

## Two traps

**Do not use an isolation flag that disables skills.** Claude Code's
`--safe-mode` turns off skills, plugins, and MCP servers, which includes
the thing being measured. Isolation is the sandbox's job. Use
`--sandbox container`.

**A static inventory does not prove runtime visibility.**
`claude --plugin-dir X plugin details` reported `Skills (1)` for a run whose
init event showed the skill absent from the model's list. That is why the
skill is copied into the harness's own discovery directory, and why
`doctor` asserts on what the model actually did.
