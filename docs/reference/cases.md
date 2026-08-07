# `cases.toml`

A case is a prompt and what must be true afterwards. `cases.toml` sits
beside `SKILL.md` in the skill directory and must declare at least one
`[[case]]` block.

Every check is optional. A case declares only what applies to it, and a
check it does not declare reports `unsupported` rather than failing.

| Key | Type | Default | Declares | Omitting it means |
|---|---|---|---|---|
| `name` | string | required | The case's identity, matched by `--case` | — |
| `prompt` | string | required | What the agent is asked | — |
| `tool` | string | none | The CLI the skill must go through | `tool_used` reports `unsupported` |
| `artifact` | string or table | none | Shorthand for one entry in `artifacts` | — |
| `[[case.artifacts]]` | array of tables | `[]` | Files that must appear | `artifact_created` reports `unsupported` |
| `[[case.answers]]` | array of tables | `[]` | Facts withheld from the prompt, and how to answer when asked | `inputs_resolved` reports `unsupported` |

```toml
[[case]]
name     = "fully-specified"
prompt   = "Write a project plan. Title: Billing migration. Owner: platform-team."
artifact = "PLAN.md"
tool     = "planctl"
```

## `tool`

The name of a command the skill is supposed to shell out to, not the name
of the harness's tool. `tool = "planctl"` is matched against both a tool
call's name and its argument text, so it finds `planctl` inside a `Bash`
command on one harness and inside a `run_shell_command` on another.

The check also reads the harness's denial records: a call that was requested
and refused fails with "was requested but denied" rather than counting as
used.

## `[[case.artifacts]]`

| Key | Type | Default | Description |
|---|---|---|---|
| `path` | string | required | File path, relative to the workspace |
| `contains` | list of strings | `[]` | Substrings that must appear in the file |

Every declared artifact must exist, be non-empty after stripping
whitespace, and contain each of its `contains` strings. A missing file or a
missing string is named in the failure reason.

```toml
[[case]]
name   = "scaffold"
prompt = "Scaffold the billing service."
tool   = "scaffoldctl"

  [[case.artifacts]]
  path = "src/billing/__init__.py"

  [[case.artifacts]]
  path     = "README.md"
  contains = ["billing", "platform-team"]
```

`artifact = "PLAN.md"` is shorthand for a single `[[case.artifacts]]` entry
with no `contains`. `artifact = { path = "PLAN.md", contains = ["x"] }`
works too. The shorthand entry is placed first.

## `[[case.answers]]`

| Key | Type | Default | Description |
|---|---|---|---|
| `match` | regex string | required | Pattern searched in what the agent said |
| `reply` | string | required | The answer supplied when `match` hits |

Withhold something the skill needs from the `prompt`, then say how to answer
when the harness asks for it.

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

`match` only decides *when* to reply. The evidence is `reply` appearing in
the artifact, because that string is supplied nowhere else in the run. See
[What shakedown measures](../explanation/what-shakedown-measures.md#the-artifact-is-the-proof).

Each answer is supplied at most once per run, even though its trigger word
usually survives into later turns.

A case may withhold several facts. One unused match is answered per turn, so
a case withholding two things takes three turns:

```toml
[[case.answers]]
match = "(?i)\\bowner\\b"
reply = "platform-team"

[[case.answers]]
match = "(?i)\\btitle\\b"
reply = "Billing migration"
```

Both replies must reach the artifacts for the check to pass.

### When `inputs_resolved` reports `unsupported`

| Situation | Why |
|---|---|
| The case declares no `answers` | Nothing was withheld |
| The harness declares no `resume` command | It cannot physically be asked a follow-up |
| The case declares `answers` but no artifacts | The harness asked and was answered, but nothing can prove the answer was used |

## Limits

A conversation stops after 6 turns, so a case cannot withhold more than five
facts and still expect them all answered.

Each turn is bounded by `--timeout`, 300 seconds by default. A turn that
hits the wall clock ends the conversation.

A harness that fails with a transient upstream error — an empty response, a
rate limit, an overloaded model — is retried up to three times rather than
scored as a skill failure.

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: measure your own skill](../how-to/measure-your-own-skill.md)
- [Reference: `shakedown.toml`](configuration.md)
- [Explanation: what shakedown measures](../explanation/what-shakedown-measures.md)
