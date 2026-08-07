# Add a harness

Measure your skill on a second agent CLI. No code is written to support one
— a harness is described entirely by config.

## Prerequisites

- The harness CLI installed and on your PATH.
- Its `--help` output, or its docs.
- shakedown installed.

## Procedure

### 1. Find the flags

`doctor` reports six rows. Four are required, one is optional, and the last
is context rather than a verdict. Read the harness's `--help` and find the
flag for each:

| # | Row | Required | Look for |
|---|---|---|---|
| 1 | Runs headless from a prompt | yes | `-p`, `--prompt`, `run` |
| 2 | Loads a skill from a directory | yes | its own skills path, usually `~/.<agent>/skills` |
| 3 | Machine-readable output | yes | `--json`, `--output-format stream-json` |
| 4 | Continues a session | no | a session id flag, and a resume flag that takes it |
| 5 | Runs without a TTY | yes | nothing to find; `doctor` decides this |
| 6 | What else the model could see | context | nothing to find; reported only |

Also find its permission or approval flag. Most harnesses refuse tool calls
by default, and a refusal still appears in the transcript as a call.

A harness missing row 4 still qualifies and is not marked down — the
`inputs_resolved` check reports `unsupported`. Row 6 cannot fail.

### 2. Write the block

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

[harness.my-harness.env]
MY_AGENT_TOKEN = "${MY_AGENT_TOKEN}"

[[matrix]]
harness = "my-harness"
models  = ["some-model"]
```

Commands are lists, not strings: each element is one argument, so a prompt
containing a quote or a leading dash stays a prompt. Slots are `{prompt}`,
`{reply}`, `{model}`, and `{sid}`.

`activation_tool` is the substring that identifies a skill-activation call —
`Skill` on Claude Code, `activate_skill` on Gemini CLI. Without it a run
where the model ignored the skill scores as an ordinary failure, and the
number then describes the base model rather than your skill.

Every key is documented in
[`shakedown.toml`](../reference/configuration.md#harnessname).

### 3. Tell shakedown where the tool calls are

Run the harness once by hand with its JSON flag and look at a line
containing a tool call. Two shapes exist:

| Shape | Looks like | Setting |
|---|---|---|
| Nested | the call sits in a list under a dotted path, as Claude Code's does in `message.content[]` | `container = "message.content"` |
| Flat | the call is a top-level record, as Gemini CLI's is | omit `container` |

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

Any of them except `container` may itself be a dotted path, which covers a
flat record that still buries what you need. opencode's call is top-level
but carries its name and arguments under a `part` object, so it reads
`name_key = "part.tool"` and `args_key = "part.state.input"`.

### 4. Run doctor until it qualifies

```bash
shakedown doctor --harness my-harness
```

Iterate on the block until the last line reads `qualifies`. `doctor` decides
each row by running the harness, never by reading a help string.

## Verification

```
qualifies
```

A harness that qualifies can be added to the matrix and trusted. One that
fails a required row will produce numbers about its own plumbing.

## Troubleshooting

**Row 2 fails: the skill was never surfaced.** The skill is copied into the
directory `skills` names. If that is not the directory the harness scans
unaided, nothing will find it. Do not reach for a plugin-directory flag —
`claude --plugin-dir X plugin details` reported `Skills (1)` for a run whose
init event showed the skill absent from the model's list. Copying into the
harness's own discovery path is the only mode observed to work.

**Row 3 fails: output not parsed.** The events block does not match this
harness's shape. Re-read a real line of its output and check `container`
first, then the key names.

**Everything is denied.** Add the harness's permission flag to `start`. The
`tool_used` check reports "was requested but denied" precisely so this is
diagnosable rather than silent.

**Do not use an isolation flag that disables skills.** Claude Code's
`--safe-mode` turns off skills, plugins, and MCP servers, which includes the
thing being measured. Isolation is the sandbox's job — see
[Isolate runs in a container](isolate-runs-in-a-container.md).

## Point one harness at another provider

The same CLI against a different backing model isolates harness quality from
model quality:

```toml
[[matrix]]
harness = "claude-code"
label   = "ollama-cloud"
models  = ["gpt-oss:120b"]

[matrix.env]
ANTHROPIC_BASE_URL   = "https://your-gateway.example/anthropic"
ANTHROPIC_AUTH_TOKEN = "${GATEWAY_TOKEN}"
```

Set `label` to the provider alone; the model is appended for you, giving
`ollama-cloud/gpt-oss:120b`. Without a label both entries would read
`claude-code` and you would be averaging two backends into one number.

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: isolate runs in a container](isolate-runs-in-a-container.md)
- [Reference: `shakedown.toml`](../reference/configuration.md)
- [Explanation: design decisions](../explanation/design-decisions.md#one-optional-descent-not-a-query-language)
