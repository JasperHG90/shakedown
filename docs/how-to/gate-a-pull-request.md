# Gate a pull request

Run the matrix on every change to your skill, post the scores to the PR, and
fail the job when a scenario fails.

## Prerequisites

- A skill directory and a `shakedown.toml` committed to the repository.
- An API key for the harness, stored as a repository secret.
- A rough idea of the bill: every scenario is a live model call, so the cost
  is targets × cases × `repeat`.

## Procedure

### 1. Add the workflow

```yaml
name: shakedown

on:
  pull_request:
    paths: ["my-skill/**", "shakedown.toml"]

jobs:
  measure:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write      # required to post the comment
    steps:
      - uses: actions/checkout@v4

      # Install the harness yourself. It is your dependency, and pinning the
      # version matters because the version is what you are measuring.
      - run: npm i -g @anthropic-ai/claude-code@2.1.220

      - uses: JasperHG90/shakedown/.github/actions/shakedown@v1
        with:
          skill: ./my-skill
          repeat: "5"
          parallel: "5"
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

The action does not install harnesses. Covering npm, brew, curl, a pinned
runtime, and each one's authentication is not something a single input does
better than a step.

### 2. Declare the credential in your config

This is the step people miss. The sandbox gets the variables you declare and
nothing else, so a secret in the workflow is only half of it:

```toml
[harness.claude-code.env]
ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"
```

Without that line the harness starts unauthenticated, every run reports
`not_triggered`, and the rate is empty rather than zero. That is intended: a
run that measured nothing is not a pass.

## Verification

Open a pull request that touches the skill. You should get:

- **A comment on the PR**, with a table of pass rates per target and a
  folded list naming every failing case and reason. It is edited in place on
  each push rather than added to.
- **The JSON report as a build artifact**, so a failure is debuggable from
  the `argv`, tool calls, and agent text of every turn.
- **The same table in the job summary**, visible without opening a comment.

The job fails when any scenario fails, but the report is uploaded and the
comment posted first. A red run is exactly when the numbers are worth
reading.

## Inputs

| Input | Default | Description |
|---|---|---|
| `skill` | required | Path to the skill directory, or to the cases file naming it |
| `config` | discovered | Path to `shakedown.toml` |
| `harness` | all | Only targets whose label contains this |
| `case` | all | Only cases whose name contains this |
| `repeat` | from config | Runs per target and case |
| `parallel` | `1` | Runs at a time |
| `sandbox` | `tmp` | `container` for isolation |
| `report` | `shakedown-report.json` | Where the JSON lands |
| `python-version` | `3.12` | Python that runs shakedown, not the harness |
| `comment` | `true` | Post to the PR. Ignored outside a pull request |
| `artifact-name` | `shakedown-report` | Name of the uploaded artifact |
| `github-token` | `${{ github.token }}` | Needs `pull-requests: write` |

Outputs: `report`, `passed`, `failed`, and `markdown`.

## Keeping the bill down

Two levers, and they compose:

- **`paths:`** so the workflow only fires when the skill or the config
  changes.
- **A smaller `repeat` on pull requests than on a nightly schedule.** Five
  repeats on a nightly and one on a PR is a common split.

`parallel` costs the same and finishes sooner — it changes wall clock, not
the number of calls.

## Troubleshooting

**Every run reports `not_triggered`.** The harness is unauthenticated. See
step 2; the variable has to be named in `[harness.*.env]`, not only in the
workflow.

**The comment never appears.** The job needs `pull-requests: write`, and
`comment` is ignored outside a pull request event.

**Two comments instead of one.** The action finds its previous comment by
the `<!-- shakedown-report -->` marker on the first line. A comment written
before you upgraded shakedown carries the old marker and will not be
matched; delete it once.

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: isolate runs in a container](isolate-runs-in-a-container.md)
- [Reference: the JSON report](../reference/report.md)
- [Explanation: what shakedown measures](../explanation/what-shakedown-measures.md#four-statuses-not-two)
