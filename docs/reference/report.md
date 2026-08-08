# The JSON report

Every `shakedown case run` writes one JSON file, `shakedown-report.json` by
default. It carries the same numbers the terminal printed, plus everything
needed to debug a failure without rerunning it.

| Top-level key | Type | Description |
|---|---|---|
| `skill` | string | The skill's name, from its front matter |
| `created_at` | string | ISO 8601 timestamp, UTC |
| `sandbox` | string | `tmp` or `container` |
| `isolated` | bool | `true` only for `container` |
| `summary` | object | Counts and every failure. See [summary](#summary) |
| `runs` | array | One entry per (target, case, repeat). See [runs](#runs) |
| `scores` | object | Pass rates per target and dimension. See [scores](#scores) |

## `summary`

Answers "did it pass, and if not, what broke", without reading `runs`.

| Key | Type | Description |
|---|---|---|
| `runs` | int | Total scenarios |
| `ok` | int | Scenarios where nothing failed |
| `failed` | int | Scenarios with at least one failing check |
| `not_triggered` | int | Scenarios where the skill never activated |
| `duration_s` | float | Sum of every scenario's wall clock |
| `failures` | array | One entry per failing scenario |

Each entry in `failures` carries `target`, `case`, `run`, `failed` (the
check names), `reasons` (parallel to `failed`), `workspace` (or `null` when
it was cleaned up), and `streams` (the raw harness output per turn).

```json
{
  "runs": 1,
  "ok": 0,
  "failed": 1,
  "not_triggered": 0,
  "duration_s": 14.91,
  "failures": [
    {
      "target": "claude-code/claude-opus-5",
      "case": "fully-specified",
      "run": 0,
      "failed": ["tool_used"],
      "reasons": ["no tool call mentions notectl"],
      "workspace": "/var/folders/.../shakedown-claude-code-burl0_h9",
      "streams": [".../shakedown-claude-code-burl0_h9/.shakedown-turn0.jsonl"]
    }
  ]
}
```

## `runs`

| Key | Type | Description |
|---|---|---|
| `target` | string | The label, `<harness-or-label>/<model>` |
| `model` | string | The model alone |
| `case` | string | The case's `name` |
| `run` | int | Repeat index, from 0 |
| `prompt` | string | What the agent was asked |
| `results` | array | One per check. See [results](#results) |
| `turns` | int | Harness invocations this scenario took |
| `asked` | array of strings | Replies supplied in answer to the harness's questions |
| `workspace` | string | Directory the run happened in |
| `workspace_kept` | bool | Whether it still exists |
| `duration_s` | float | Wall clock for the scenario |
| `detail` | array | One per turn. See [detail](#detail) |
| `ok` | bool | Whether nothing failed |
| `failed` | array of strings | Names of failing checks |

A failing run keeps its workspace, so its artifacts and raw streams stay on
disk. Passing runs are deleted unless you pass `--keep`.

### `results`

| Key | Type | Description |
|---|---|---|
| `name` | string | `skill_fired`, `tool_used`, `artifact_created`, or `inputs_resolved` |
| `status` | string | `pass`, `fail`, `unsupported`, or `not_triggered` |
| `reason` | string | Why, in words |

```json
[
  {"name": "skill_fired", "status": "pass", "reason": "my-skill activated"},
  {"name": "tool_used", "status": "fail", "reason": "no tool call mentions notectl"},
  {"name": "artifact_created", "status": "pass", "reason": "NOTE.md written"},
  {"name": "inputs_resolved", "status": "unsupported", "reason": "this case withholds nothing"}
]
```

Only `pass` and `fail` count toward a rate. See
[What shakedown measures](../explanation/what-shakedown-measures.md#four-statuses-not-two).

### `detail`

What the harness actually did, per turn.

| Key | Type | Description |
|---|---|---|
| `index` | int | Turn number, from 0 |
| `argv` | array of strings | The exact command, so a failure is reproducible by hand |
| `exit_code` | int | The harness's exit status. `-1` means the turn timed out |
| `duration_s` | float | Wall clock for the turn |
| `tool_calls` | array | Each with `name` and `args` |
| `said` | array of strings | What the agent wrote as text |
| `denied` | array of strings | Tools the harness refused to run |
| `stream` | string | Path to the raw newline-delimited JSON |
| `stderr_tail` | string | Last 500 characters of stderr |

`denied` is the difference between a skill that did not try to run the CLI
and one that was not allowed to.

## `scores`

Counts per target, per dimension.

| Key | Type | Description |
|---|---|---|
| `passed` | int | Checks that passed |
| `scored` | int | Checks that counted, so passes plus failures |
| `unsupported` | int | Checks that did not apply |
| `not_triggered` | int | Checks skipped because the skill never activated |
| `rate` | float or null | `passed / scored`, or `null` when nothing was scored |

```json
{
  "claude-code/claude-opus-5": {
    "tool_used": {"passed": 0, "scored": 1, "unsupported": 0, "not_triggered": 0, "rate": 0.0},
    "artifact_created": {"passed": 1, "scored": 1, "unsupported": 0, "not_triggered": 0, "rate": 1.0}
  }
}
```

`unsupported` and `not_triggered` stay out of `rate`. A harness that cannot
resume a session is not marked down for it, and a run where the skill never
activated measured the base model rather than your skill.

`passed` and `scored` are the whole input to a statistical gate — a Wilson
bound or a Fisher exact non-inferiority test — which is why shakedown ships
the counts and no opinion about what a regression is.

## Rendering it as markdown

```bash
shakedown summary shakedown-report.json
```

Prints a table of rates per target, a folded list of failing scenarios, and
a `<!-- shakedown-report -->` marker on the first line so a CI job can find
and edit its own previous comment.

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: gate a pull request](../how-to/gate-a-pull-request.md)
- [Reference: CLI](cli.md)
- [Explanation: what shakedown measures](../explanation/what-shakedown-measures.md)
