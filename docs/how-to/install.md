# Install shakedown

shakedown is not on PyPI. It installs from GitHub.

## Prerequisites

- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/getting-started/installation/).
- At least one agent harness on your PATH — `claude`, `gemini`, or
  whichever one you plan to measure. shakedown runs harnesses; it does not
  install them.
- Docker, only if you plan to use `--sandbox container`.

## Install the command

```bash
uv tool install git+https://github.com/JasperHG90/shakedown
```

This puts a `shakedown` executable on your PATH with its own isolated
dependencies. Check it:

```bash
shakedown --version
```

```
0.1.0
```

If the shell cannot find the command, uv installed it somewhere not on your
PATH. Fix that once:

```bash
uv tool update-shell
```

## Run it once without installing

To try it before committing to an install:

```bash
uvx --from git+https://github.com/JasperHG90/shakedown shakedown doctor
```

`uvx` downloads into a temporary environment and throws it away afterwards.

## Install from a clone

Clone instead if you want the bundled example skills, the Dockerfiles, or
the source:

```bash
git clone https://github.com/JasperHG90/shakedown
cd shakedown
uv sync
uv run shakedown --version
```

From a clone, every command in these docs gets a `uv run` prefix:
`uv run shakedown doctor` rather than `shakedown doctor`.

## Pin a version

A tag or a commit sha after `@` pins what you get, which is what you want in
CI:

```bash
uv tool install git+https://github.com/JasperHG90/shakedown@v0.1.0
```

## Upgrade and uninstall

```bash
uv tool upgrade shakedown
uv tool uninstall shakedown
```

## Troubleshooting

**`pip install shakedown` installs something else.** The name `shakedown` on
PyPI belongs to an unrelated package last touched in 2013. Install from the
git URL above.

**`shakedown doctor` reports a harness it cannot find.** shakedown runs
whatever `start` names in `shakedown.toml`, so the harness CLI has to be
installed and on your PATH first. Install it the way its own project
documents, then run `doctor` again.

**Everything reports `not_triggered`.** The harness started but was not
authenticated. The sandbox gets only the variables you declare, so the
credential has to be named in the harness block. See
[`shakedown.toml`](../reference/configuration.md#harnessnameenv).

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: measure your own skill](measure-your-own-skill.md)
- [Reference: CLI](../reference/cli.md)
- [Explanation: design decisions](../explanation/design-decisions.md)
