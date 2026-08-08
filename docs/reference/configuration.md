# `shakedown.toml`

Harnesses and the matrix. Nothing about the skill under test belongs here —
that is a path you pass to `shakedown case run`.

shakedown looks for `shakedown.toml` in the working directory, then in each
parent, and uses the first one it finds. `--config` overrides the search.

| Key | Type | Default | Description |
|---|---|---|---|
| `[harness.<name>]` | table | required | One block per harness. See [harness](#harnessname) |
| `[[matrix]]` | array of tables | required | What to actually run. See [matrix](#matrix) |
| `repeat` | int | `1` | Runs per target and case, unless `--repeat` overrides it |

Unknown keys are refused inside `[harness.*]` and `[harness.*.events]`. A
typo would otherwise parse into a default, find no tool calls, and fail
every check for a reason nobody could see.

## `[harness.<name>]`

The table key is the harness name. It is what `--harness` matches and what
appears in target labels.

| Key | Type | Default | Description |
|---|---|---|---|
| `start` | list of strings | required | Command that starts a run |
| `resume` | list of strings | `[]` | Command that continues a session. Omitting it makes `inputs_resolved` report `unsupported` |
| `skills` | string | required | Directory this harness scans for skills, relative to the workspace |
| `activation_tool` | string | `"Skill"` | Substring identifying a skill-activation call in this harness's output |
| `image` | string | `""` | Prebuilt image for `--sandbox container` |
| `dockerfile` | string | `""` | Dockerfile to build for `--sandbox container`, relative to `shakedown.toml` |
| `env` | table of strings | `{}` | The only variables the sandbox gets |
| `events` | table | defaults below | Where a tool call sits in this harness's output |

Declaring both `image` and `dockerfile` is an error: one is pulled, the
other is built. A `dockerfile` that does not exist fails at config load,
naming the resolved path.

### Command templates

`start` and `resume` are lists, never strings. Each element is exactly one
argument, so a prompt containing a quote or a leading dash stays a prompt
and cannot become a flag.

Four slots are substituted anywhere in an element:

| Slot | Meaning | Available in |
|---|---|---|
| `{prompt}` | The case's prompt | `start` |
| `{reply}` | The answer to the harness's question | `resume` |
| `{model}` | The model from the matrix entry | both |
| `{sid}` | A session id shakedown generates | both |

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
```

The skill under test is copied to `<skills>/<name>/` inside the workspace,
where `<name>` is the `name` from the skill's front matter.

### `[harness.<name>.env]`

The sandbox starts with an empty environment and gets these variables and
nothing else. `PATH` is added for you if you do not declare it.

Values may reference host variables with `${VAR}`. The TOML holds
references, never secrets. A referenced variable that is unset is an error
at load time, not an empty string.

```toml
[harness.claude-code.env]
HOME = "${HOME}"
ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"
```

Reports record key names only; values never appear in output.

### `[harness.<name>.events]`

Where a tool call sits in this harness's newline-delimited JSON.

| Key | Type | Default | Description |
|---|---|---|---|
| `container` | string | `""` | Dotted path to a list of blocks. Omit when records are flat |
| `discriminator` | string | `"type"` | Key naming a block's kind |
| `tool_marker` | string | `"tool_use"` | That key's value on a tool call |
| `name_key` | string | `"name"` | Where the tool name sits |
| `args_key` | string | `"input"` | Where the arguments sit |
| `text_key` | string | `"text"` | Where agent text sits |
| `text_marker` | string | `"text"` | The discriminator's value on a text block |

Every key except `container` may itself be a dotted path, which covers a
flat record that still buries what you need.

| Harness | Shape | Setting |
|---|---|---|
| Claude Code | Nested in `message.content[]` | `container = "message.content"` |
| Gemini CLI | Top-level records | omit `container` |
| opencode | Top-level, but nested under `part` | `name_key = "part.tool"`, `args_key = "part.state.input"` |

## `[[matrix]]`

One entry per harness you want to run, listing the models to run it with.

| Key | Type | Default | Description |
|---|---|---|---|
| `harness` | string | required | Must name a `[harness.*]` block |
| `models` | list of strings | required | One target per model |
| `label` | string | the harness name | Prefix for this entry's target labels |
| `env` | table of strings | `{}` | Merged over the harness's `env` for this entry only |

A target's label is `<label or harness>/<model>`. A harness defined but
never named in the matrix is valid and simply does not run — useful for
shipping a worked example someone else can switch on.

```toml
[[matrix]]
harness = "claude-code"
models  = ["claude-opus-5", "claude-sonnet-5"]
```

### Pointing one harness at another provider

An `env` override produces a distinct harness, so the same CLI can be
measured against a different backing model:

```toml
[[matrix]]
harness = "claude-code"
label   = "ollama-cloud"
models  = ["gpt-oss:120b"]

[matrix.env]
ANTHROPIC_BASE_URL   = "https://your-gateway.example/anthropic"
ANTHROPIC_AUTH_TOKEN = "${GATEWAY_TOKEN}"
```

This yields the label `ollama-cloud/gpt-oss:120b`. Set `label` to the
provider alone, not to `harness/model` — the model is appended for you, so
`label = "claude-code/gpt-oss:120b"` would produce
`claude-code/gpt-oss:120b/gpt-oss:120b`.

Without a `label`, both entries would read `claude-code` and you would be
averaging two backends into one number.

`[matrix.env]` attaches to the `[[matrix]]` entry above it.

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: add a harness](../how-to/add-a-harness.md)
- [Reference: `cases.toml`](cases.md)
- [Explanation: design decisions](../explanation/design-decisions.md#the-environment-is-empty-by-default)
