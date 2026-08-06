# skeval: harness conformance testing for agent skills

**One sentence:** given a harness and a model, does the same query produce
the same procedural outcome?

Not "is my skill any good". That question already has a maintained answer
(see [Prior art](#prior-art)). This tool answers a different one: your skill
works on Claude Code, so does it also work on Gemini CLI, on opencode, on
Claude Code pointed at a cheaper model? And does it keep working next week?

The motivating observation is that harnesses differ measurably at following
instructions, and that difference is invisible if you only ever test one.

## The evidence this design rests on

Probed 2026-08-06 with a skill whose only instruction is "ask the user
where to write the file, and do not guess". Both harnesses, byte-identical
`SKILL.md`:

| harness | skill fired | asked | wrote anything |
|---|---|---|---|
| claude-code | `Skill{ask-path}` | plain text, after probing for `AskUserQuestion` | no |
| gemini-cli | `activate_skill{ask-path}` | plain text | no |

Both ask. Neither invents. So the third check has signal on both, and
multi-turn is a first-class concept rather than a Claude-only extra.
Gemini's `--resume` carries context across turns.

Three findings shaped the architecture, and two of them came from getting
the measurement wrong first:

- **`--safe-mode` disables the thing under test.** Its own help lists
  skills among the customizations it turns off. An early probe used it as
  an isolation mechanism and produced a run where the skill was never
  visible to the model, which read as "the harness ignores instructions".
  Isolation is the container's job. No harness flag substitutes for it.
- **A static inventory does not prove runtime visibility.**
  `claude --plugin-dir X plugin details` reported `Skills (1)` for a run
  whose init event showed the skill absent from the model's skill list.
  Conformance must assert visibility at runtime: the init event, or an
  actual skill-activation call.
- **Tool calls sit at different depths per harness**, though both emit
  newline-delimited JSON with a `type` discriminator.

## Prior art

**`skill-creator`** (Anthropic, official, ships with Claude Code) covers
skill quality: trigger rate, description optimization, blind A/B between
skill versions, variance analysis. It is the right tool for "does my skill
fire, and is the description good". It shells `claude -p` only and has no
notion of a second harness, CI, or regression gating.

**promptfoo** covers prompt and model comparison with repeats, thresholds,
and a web viewer. Driving a second harness through it requires a custom
provider, and the results then need translating back out of its schema.

Neither answers the cross-harness conformance question. This tool does only
that, and defers skill quality to `skill-creator`.

## What is measured

Three checks, scored independently because they fail independently.

**1. Tool use.** The deterministic CLI was invoked, rather than the agent
producing an equivalent-looking result itself.

The proof is a filesystem fact, not a transcript claim. The CLI writes a
receipt beside its output containing a digest of the exact bytes it wrote.
An agent that hand-writes the artifact produces a perfectly good artifact
and no receipt.

This matters because tool names are harness-specific (`Bash` versus
`run_shell_command`), so a transcript match is a harness-specific check
wearing a general name. The receipt is identical everywhere.

Limit, stated plainly: the receipt catches a shortcut, not a forgery. The
digest carries no secret, so a receipt can be fabricated by an agent that
chooses to. That is out of the threat model.

**2. Artifact created.** The expected file exists and is well formed. A
file test, the least interesting of the three, and the only one that would
survive naive implementation.

**3. Inputs requested and resolved.** The prompt deliberately withholds
something the skill needs. The harness must ask, accept the answer, and use
it.

The proof is again the artifact. If `platform-team` is supplied *only* in
reply to a question, and the artifact ends up containing `platform-team`,
the loop demonstrably closed. That string exists nowhere else in the run.

This removes the need to parse questions, track topics, or check ordering.
An artifact cannot contain a value that was first revealed on turn three
unless the harness asked on turn two.

A harness that invents values instead of asking never receives the reply,
so the artifact never contains it, and the check fails. **That failure is
the measurement**, not an error to work around.

**0. Did the skill fire at all?** A precondition, not a fourth score.

If the skill never activated, the three checks measure nothing and the run
is reported `NOT_TRIGGERED` rather than failed. Triggering is
`skill-creator`'s domain, and folding a trigger-rate problem into a
conformance number contaminates both.

Both harnesses expose this cheaply: a `Skill` call on Claude Code, an
`activate_skill` call on Gemini, and the skill's presence in the init
event's skill list.

## Architecture

```
pytest                        the runner. no bespoke CLI, no second
  │                           reporting format, -k and -n for free
  ▼
plugin.py                     parametrize over harness x model x case x N
  ▼
sandbox                       container (default) or tempdir
  │                           empty env + declared vars only
  ▼
runner.py                     render command template, exec, capture
  │                           one turn = one subprocess
  ▼
events.py                     two known stream shapes -> ToolCall, text
  ▼
checks.py                     the three assertions
```

Config lives in `skeval.toml`. Harness behavior lives in the harness.
The framework runs things and asserts on what came back.

### Code budget

| module | lines |
|---|---|
| `config.py` | ~60 |
| `sandbox.py` | ~90 |
| `runner.py` | ~50 |
| `events.py` | ~70 |
| `checks.py` | ~90 |
| `plugin.py` | ~80 |
| **total** | **~440** |

Plus the example skill and its CLI. The statistical gate, if adopted, adds
roughly 350 (see [Open questions](#open-questions)).

This budget is a design constraint, not an estimate. A predecessor of this
tool reached 2,807 lines of production code by absorbing concerns that
belong to the harness or to the container.

## The harness contract

A harness qualifies if it can do these five things. Each maps to config,
and each is verified empirically before anyone trusts a measurement.

| # | prerequisite | required | if missing |
|---|---|---|---|
| 1 | headless run with a prompt, exits on its own | yes | unusable |
| 2 | loads a skill from a path you control | yes | unusable |
| 3 | machine-readable output with tool calls and text | yes | unusable |
| 4 | continue a session (`--resume` / `--session-id`) | no | check 3 reported `unsupported` |
| 5 | runs without a TTY | yes | unusable |

Prerequisite 4 is optional on purpose. A harness must never *fail* a
dimension it cannot physically support: it is reported as unsupported with
a reason, so the other two checks stay comparable across everything.

### `doctor`

```
skeval doctor --harness opencode
```

The framework ships a **canary skill** whose entire content instructs the
agent to run `echo skeval-ok`. Seeing that shell call in the output is
only possible if the harness ran headless, loaded a skill, followed it, and
emitted parseable output. One cheap task verifies prerequisites 1, 2, 3,
and 5 at once. A second turn verifies 4.

```
opencode
  1. headless run ................ ok (exit 0, 4.2s)
  2. skill loaded ................ ok (canary fired)
  3. output parsed ............... ok (3 tool calls, 2 texts)
  4. session resume .............. FAIL (turn 2 has no memory of turn 1)
  5. no TTY required ............. ok

  qualifies: yes, with inputs_resolved unsupported
```

This is what makes "add any harness whose config can be filled out" a
thirty-second answer instead of a confusing eval run.

## Configuration

```toml
[harness.claude-code]
image  = "ghcr.io/you/claude-code:2.1.220"
start  = "claude -p {prompt} --output-format stream-json --verbose --session-id {sid}"
resume = "claude -p {reply}  --output-format stream-json --verbose --resume {sid}"
skills = { mode = "flag", flag = "--plugin-dir {dir}" }

[harness.claude-code.env]
ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"

[harness.claude-code.events]
container     = "message.content"   # dotted path to a list; omit if flat
discriminator = "type"
tool_marker   = "tool_use"
name_key      = "name"
args_key      = "input"
text_key      = "text"

[harness.claude-code.tools]
shell = "Bash"
write = "Write"
read  = "Read"
```

Gemini differs only in values, including omitting `container`:

```toml
[harness.gemini-cli]
image  = "ghcr.io/you/gemini-cli:0.47.0"
start  = "gemini -p {prompt} -o stream-json --approval-mode yolo --skip-trust --session-id {sid}"
resume = "gemini -p {reply}  -o stream-json --approval-mode yolo --skip-trust --resume latest"
skills = { mode = "copy", dest = ".gemini/skills/{name}" }

[harness.gemini-cli.tools]
shell = "run_shell_command"
write = "write_file"
read  = "read_file"
```

### Events: one optional descent, not a query language

A tool call differs across harnesses in three ways: key names, depth, and
cardinality. Key names are trivially config. Depth and cardinality are not,
and expressing them in TOML would mean shipping a path-query evaluator, at
which point the config becomes an untestable program.

The compromise is one optional container path: "descend into this list, if
present". Claude sets `container = "message.content"`; Gemini omits it.
That covers both known shapes and most plausible third ones in about ten
lines. A harness that genuinely does not fit fails at `doctor` step 3,
loudly, rather than scoring zero silently.

Cardinality is not cosmetic. One Claude record can carry several tool_use
blocks. A predecessor counted records where it should have counted blocks,
and a question asked after the artifact was written scored as though it
came first.

### Matrix

```toml
[[matrix]]
harness = "claude-code"
models  = ["claude-opus-5", "claude-sonnet-5"]

[[matrix]]
harness = "gemini-cli"
models  = ["gemini-3.5-flash"]

[[matrix]]
harness = "claude-code"
label   = "claude-code/glm-4.6"
models  = ["glm-4.6"]
env     = { ANTHROPIC_BASE_URL = "https://open.bigmodel.cn/api/anthropic",
            ANTHROPIC_AUTH_TOKEN = "${GLM_TOKEN}" }
```

The third entry is the interesting one. Same harness, different backing
provider, which isolates harness quality from model quality: how much of a
harness's advantage is its scaffolding rather than the model behind it.

### Cases

```toml
[[case]]
name    = "missing-owner"
prompt  = "Write a project plan. Title: Billing migration. Milestone: 2026-Q4."
artifact = "PLAN.md"

[[case.answers]]
match = "(?i)\\bowner\\b|who owns"
reply = "platform-team"
```

`match` is a trigger for replying, not the evidence. The evidence is
`reply` appearing in the artifact.

## The CLI is a thin front for pytest

`skeval` translates friendly flags into pytest arguments and gets out of
the way. It is a convenience, never a wall.

```bash
skeval init                          # scaffold config + example skill
skeval doctor --harness gemini-cli   # verify the five prerequisites
skeval run                           # the whole matrix
skeval run --harness gemini-cli --repeat 5
skeval run --case missing-owner --sandbox tmp
skeval run -- -x --pdb               # everything after -- goes to pytest
```

Three rules keep it honest:

- **It shells `pytest`, it does not reimplement it.** `-k`, `-n`, `-x`,
  `--lf`, and every plugin keep working.
- **Bare `pytest` must keep working.** The CLI is optional sugar, so CI can
  use either and a contributor who reaches for pytest directly is not
  fighting the tool.
- **Unknown arguments pass through** rather than erroring, so the CLI never
  becomes the reason a pytest feature is unreachable.

That keeps it at roughly 60 lines: argument translation, config discovery,
and the `doctor` and `init` subcommands, which are the only two that are not
tests.

## Sandbox

Container by default, tempdir for fast local iteration, same interface.

The container is not only isolation, it is *deletion*. Inside one, the
harness has no host configuration to leak, which removes the need for
`--safe-mode`, config-root overrides, and an isolation assertion. It also
pins the harness version as a property of the image rather than a flag
someone has to remember.

```dockerfile
FROM node:22-slim
ARG CLAUDE_VERSION=2.1.220
RUN npm i -g @anthropic-ai/claude-code@${CLAUDE_VERSION}
```

One image per harness version. Bring your own image for your own harness.

## Environment

**The sandbox starts with an empty environment plus exactly what is
declared.** Nothing is inherited.

This is what makes the contamination finding structurally impossible rather
than something a flag suppresses. It also makes runs reproducible: two
machines with different shells produce the same environment.

Two rules follow:

- **Env is part of run identity.** A different `ANTHROPIC_BASE_URL` is a
  different provider and must appear in the label, or you will silently
  compare across backends.
- **Values never appear in output.** Not in reports, not in verdicts, not
  in CI comments. The TOML holds `${VAR}` references. Values come from the
  host at run time, and reports record key names only.

## Multi-turn is re-invocation

Both known harnesses expose `--session-id` and `--resume`, so a
conversation is a sequence of subprocess calls rather than a bidirectional
stream:

```python
events = run(h.start, prompt=case.prompt, sid=sid)
for _ in range(turn_cap):
    reply = match_answer(assistant_text(events), case.answers)
    if reply is None:
        break
    given.append(reply)
    events = run(h.resume, reply=reply, sid=sid)
```

Gemini's `--resume` takes `latest` rather than a UUID, which is safe
precisely because the sandbox is per-run and holds exactly one session.

This is uniform across harnesses, needs no per-harness stdin encoding, and
every turn is a plain subprocess that is trivial to test. A predecessor
implemented a bidirectional streaming driver that worked on one harness and
was never exercised against a real stream.

## Adding a harness is a skill

`skills/add-harness/SKILL.md` walks the five prerequisites, writes the TOML
block, runs `doctor`, and iterates until the harness qualifies or reports
exactly which prerequisite it fails.

Following the convention that a discrete operator decision gets a
structured prompt rather than a prose question:

| step | shape |
|---|---|
| skill install mode: `flag` or `copy` | fork, ask |
| events shape: flat, nested, or custom | fork, ask, with the harness's own output as preview |
| command template | prose, it is written rather than chosen |
| tool-name map | prose, derived from a `doctor` run then confirmed |

The framework's own onboarding being a skill makes it the first dogfood
case. If `add-harness` cannot reliably elicit a harness config across two
harnesses, that is itself a finding.

## Out of scope

Deliberately not the framework's concern:

- **Skill quality.** Trigger rate, description optimization, A/B between
  skill versions. Use `skill-creator`.
- **Isolation mechanics.** The container's job.
- **Model routing.** If a harness fans out to auxiliary models that is its
  business. Pin `--model` and record what it reports.
- **Permissions and approval modes.** A flag in `start`, nothing more.
- **Cost normalization.** Reported if the harness reports it, absent
  otherwise, never inferred. A number in no unit is worse than no number.

## Open questions

**Q1. Does either harness ask, under an under-specified prompt, headlessly?**
Unverified. Decides whether check 3 has signal on either harness or whether
both simply invent values. Costs about $0.20 to settle and should be
settled before check 3 is built.

**Q2. Does the statistical gate come along?**
A predecessor carried an absolute floor plus a non-inferiority test against
a committed baseline, quoting a Wilson lower bound. Roughly 350 lines.

The argument for: gating on a point-estimate difference at small N is a
coin flip. At a true pass rate of 0.9 with N=5, P(5/5) is 0.59, so 41% of
unregressed runs score 4/5 and fail against a 5/5 baseline. A team switches
that gate off within a week.

The argument against: plain pytest with `--repeat` is a tenth of the code
and may be enough until real variance is known.

**Q3. Do harnesses need per-case timeouts, or is one global enough?**
Unknown until real runs exist across more than two harnesses.

## Non-negotiables

Carried from the predecessor because each was learned by being wrong:

- **Refuse rather than guess.** No invented prices, no default floors, no
  fabricated citations. Where the system cannot know something it says so
  and stops.
- **Never fold infrastructure failure into a quality score.** An expired
  credential, a timeout, a model mismatch: none are the skill's fault, and
  none belong in a pass rate.
- **A missing measurement is not a pass.** Zero rows, zero attempts, and an
  unresolvable baseline reference each fail loudly and distinctly.
- **State limits in the same document as the numbers.** Quote a lower
  confidence bound rather than a point estimate.
