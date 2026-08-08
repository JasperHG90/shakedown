# `cases.toml`

A case is a prompt and what must be true afterwards. A cases file must
declare at least one `[[case]]` block.

## Where it lives

Cases are what a skill is measured against, not part of what a user
installs, so they belong outside the skill directory. Two locations are
looked for, in this order:

1. `shakedowns/<slug>.cases.toml`, beside the skill directory or anywhere
   above it, where `<slug>` is the skill directory's name. The file names
   the skill it measures with a `skill` key.
2. `cases.toml` inside the skill directory, for a skill that keeps them
   there. No `skill` key: it is already beside its subject.

```toml
# shakedowns/write-plan.cases.toml
skill = "../examples/write-plan"
```

The path is relative to the cases file, so the pair moves together. Either
end is a usable argument: `shakedown case run examples/write-plan` and
`shakedown case run shakedowns/write-plan.cases.toml` resolve to the same pair.

Searching upward means one `shakedowns/` at a repo root covers every skill
nested under it, and a skill with a stale `cases.toml` still inside is not
measured by it while the outer file exists.

## `version`

The schema the file is written against. A file without one reads as
version 1, which is what a file written before versioning existed is.

```toml
version = 1
```

A version **newer** than the build reading it is refused, because an old
reader cannot know what changed. An unknown *key* it would refuse anyway,
since a cases file forbids keys it does not recognize — the case this
guards is subtler: a key that still parses but now means something else,
which an old reader would act on with the old meaning and report a pass
for a check the author did not write.

An **older** version always loads. Refusing one would make every schema
bump a breaking change for every cases file already written, which is the
opposite of what recording a version is for.

## What a case declares

Every check is optional. A case declares only what applies to it, and a
check it does not declare reports `unsupported` rather than failing.

| Key | Type | Default | Declares | Omitting it means |
|---|---|---|---|---|
| `version` | int | `1` | The cases schema this file is written against | Read as version 1 |
| `skill` | string | required outside the skill | The skill directory these cases measure, relative to this file | Resolved from the skill's own directory instead |
| `fixtures` | string or list | none | Directories of stand-in executables, seeded onto PATH ahead of the real ones, in the order given. See [fixtures](#fixtures) | The skill calls the real commands |
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

## `fixtures`

A directory of executables copied into the sandbox's `bin/` after the
skill's own, so a stand-in of the same name shadows it. `bin/` is first on
PATH, so it also shadows anything installed on the machine or in the image.

```toml
fixtures = "fixtures/register-service"
```

Several directories are allowed, and they are copied in the order written,
so a later one overrides a same-named stand-in from an earlier one. That
is how a double shared between skills combines with the ones only this
skill needs:

```toml
fixtures = ["fixtures/common", "fixtures/register-service"]
```

Sharing needs nothing else: two cases files naming the same directory both
get it. A shared double has to locate the workspace itself rather than
assume one skill's layout — `WORK="$(cd "$(dirname "$0")/.." && pwd)"`
does it, since `bin/` is where it was seeded — and anything it builds
belongs in that workspace, which is per run, so two skills cannot collide.

This is how a skill with side effects gets measured. `register-service`
clones a shared repository, edits it, commits, pushes, and opens a pull
request, and every one of those that leaves the machine goes through `gh`.
Its cases supply a `gh` that clones from a local repository the double
builds on first call, records each invocation to `gh-calls.log`, and prints
a pull request URL without opening one. `git` is left alone, so the branch,
the diff against `origin/main`, and the commit are all real.

A double is not a way to skip the interesting part. It is what makes the
interesting part checkable: the skill's own clone is a temp directory it
deletes on exit, so the double exports the pushed branch to `pr/` where
`[[case.artifacts]]` can read it. Asserting on `pr/services/checkout.yaml`
says more than a real pull request URL ever could.

Fixtures live beside the cases, never inside the skill. A fake `gh` shipped
in `<skill>/bin/` would install onto the machines of everyone who uses the
skill.

The path is relative to the cases file, and it must not point inside the
skill: a double shipped in `<skill>/bin/` installs onto the machine of
everyone who uses the skill. Both that and a `fixtures` naming a directory
that is not there are refused at load, because seeding no double silently
would let the real command run for real.

`fixtures` and `skill` are file-level keys and belong **above the first
`[[case]]`**. TOML gives a bare key written after a table to that table, so
one placed below it belongs to that case, and is refused with the key named
rather than ignored.

A double should fail on any call it does not recognize. Exiting 0 for an
unknown verb hands the skill an empty success, and the run gets scored on
it.

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
