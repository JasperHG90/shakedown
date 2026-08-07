# CLI

| Command | Does | Spends money |
|---|---|---|
| `shakedown` | Prints the banner and the help | no |
| [`shakedown run`](#shakedown-run) | Runs the matrix | yes |
| [`shakedown init`](#shakedown-init) | Scaffolds a config and a starter skill | no |
| [`shakedown doctor`](#shakedown-doctor) | Checks a harness against the prerequisites | yes, a little |
| [`shakedown summary`](#shakedown-summary) | Renders a report as markdown | no |

Global option: `--version` prints the version and exits.

Run from a clone rather than a tool install? Prefix everything with
`uv run`.

## `shakedown run`

```
shakedown run [OPTIONS] SKILL [PYTEST_ARGS]...
```

Runs every case in `SKILL` against every target in the matrix.

| Argument | Type | Default | Description |
|---|---|---|---|
| `SKILL` | path | required | The skill directory (`SKILL.md`, optional `bin/`), or the cases file naming it. See [where cases live](cases.md#where-it-lives) |
| `PYTEST_ARGS` | strings | none | Passed through to pytest. See [passing pytest arguments](#passing-pytest-arguments) |

| Option | Type | Default | Description |
|---|---|---|---|
| `--config` | path | nearest `shakedown.toml`, searching upward | Config to load |
| `--harness` | string | all | Only targets whose label contains this substring |
| `--case` | string | all | Only cases whose name contains this substring |
| `--repeat` | int | `repeat` in the config, else 1 | Runs per target and case |
| `--sandbox` | `tmp` or `container` | `tmp` | Where each run happens |
| `--report` | path | `shakedown-report.json` | Where the JSON report lands |
| `--parallel`, `-j` | int | `1` | Runs at a time |
| `--keep` | flag | off | Keep every workspace, not only failing ones |

**Exit code** is pytest's: `0` when every scenario passed, non-zero
otherwise.

```bash
shakedown run ./my-skill
shakedown run ./my-skill --repeat 5 --parallel 5
shakedown run ./my-skill --harness gemini-cli --case missing-owner
shakedown run ./my-skill --sandbox container
```

### Passing pytest arguments

`shakedown run` is a thin front for pytest, but it does not accept unknown
options — click rejects them before they reach pytest. Put them after `--`:

```bash
shakedown run ./my-skill -- -x --pdb
shakedown run ./my-skill -- --timeout 600
```

Everything after `--` goes to pytest untouched, including
[pytest-level options](#pytest-options) that have no CLI flag of their own.

## `shakedown init`

```
shakedown init [OPTIONS] [SKILL]
```

Writes a starter skill and, unless one already exists, a config. The skill
is a working one shaped after the bundled example, so the first
`shakedown run` is a real measurement rather than a template to fill in.

| Argument | Type | Default | Description |
|---|---|---|---|
| `SKILL` | path | `my-skill` | Where to scaffold the skill |

| Option | Type | Default | Description |
|---|---|---|---|
| `--config` | path | `shakedown.toml` | Where to write the config |

Writes `SKILL.md` and an executable `bin/notectl` under `SKILL`, the cases
as `shakedowns/<SKILL>.cases.toml` beside it, plus the config if it is
absent.

**Exit code** `2` if any target file already exists. Nothing is overwritten,
ever; the error names every clash.

## `shakedown doctor`

```
shakedown doctor [OPTIONS]
```

Runs a built-in canary skill through each harness and reports which
prerequisites it meets. Costs one or two model calls per harness.

| Option | Type | Default | Description |
|---|---|---|---|
| `--config` | path | nearest `shakedown.toml` | Config to load |
| `--harness` | string | every harness in the config | Check only this harness, by exact name |
| `--sandbox` | `tmp` or `container` | `tmp` | Where the canary runs |

**Exit codes**

| Code | Meaning |
|---|---|
| `0` | Every harness checked qualifies |
| `1` | At least one does not |
| `2` | The config would not load, or `--harness` named an unknown harness |

The six rows it prints are described in
[What shakedown measures](../explanation/what-shakedown-measures.md#the-harness-has-to-qualify-first).

## `shakedown summary`

```
shakedown summary [REPORT]
```

Prints a report as markdown, for a PR comment or a CI job summary.

| Argument | Type | Default | Description |
|---|---|---|---|
| `REPORT` | path | `shakedown-report.json` | A report written by `shakedown run` |

**Exit code** `2` if the file does not exist.

The output starts with `<!-- shakedown-report -->`, which is how the bundled
GitHub action finds its own previous comment and edits it instead of adding
another.

## pytest options

`shakedown run` shells out to pytest with shakedown's plugin loaded. Running
pytest directly is fully supported and takes these options:

| Option | Type | Default | Description |
|---|---|---|---|
| `--skill` | path | none | The skill under test |
| `--shakedown-config` | path | discovered | Path to `shakedown.toml` |
| `--harness` | string | all | Only targets whose label contains this |
| `--repeat` | int | from config | Runs per target and case |
| `--timeout` | float | `300.0` | Seconds per turn |
| `--sandbox` | `tmp` or `container` | `tmp` | Where each run happens |
| `--report` | path | `shakedown-report.json` | Where the report lands |
| `--keep-workspaces` | flag | off | Keep every workspace |

`--timeout` has no `shakedown run` flag of its own. It bounds a single turn,
which is the unit that actually hangs, and reaches pytest through `--`.

```bash
uv run pytest src/shakedown/conformance.py -m live --skill ./my-skill -x
```

The `live` marker is what separates scenarios that spend money from the
offline test suite, and it is deselected by default.

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: measure your own skill](../how-to/measure-your-own-skill.md)
- [Reference: `shakedown.toml`](configuration.md)
- [Explanation: design decisions](../explanation/design-decisions.md#the-cli-is-a-thin-front-for-pytest)
