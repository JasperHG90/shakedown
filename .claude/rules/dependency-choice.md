---
name: dependency-choice
description: When to stay on the standard library and when to take a well-chosen third-party dependency. Read before writing utility code or adding a package.
paths: ["**/*.py", "**/pyproject.toml"]
---

The standard library is the answer when it already does the job: `pathlib`,
`json`, `dataclasses`, `subprocess`, `datetime`, `itertools`, `argparse` for a
couple of flags. Reach outside it when the alternative is hand-rolling a
subsystem. Boilerplate you write by hand is code you own, test, document, and
eventually get wrong — a retry loop without jitter, a cache without eviction, a
config parser that ignores a typo'd key.

| Hand-rolled subsystem | Use |
|---|---|
| dict-shaped parsing and validation | `pydantic`, `pydantic-settings` |
| `urllib.request` plumbing | `httpx` |
| a retry `while` loop | `tenacity` |
| a dict with manual expiry | `cachetools` |
| a CLI past a couple of flags | `typer` or `click` |
| ad-hoc `print` diagnostics | `structlog`, `rich` |

`testcontainers` belongs alongside these for integration tests, with a caveat
none of the others carry: it needs a running Docker daemon on every machine and
CI runner, so it buys fidelity with infrastructure rather than by deleting code.

<constraint name="justify-zero-dependency">
Write dependency-free code only when something concrete forces it: the artifact
runs under an interpreter you do not control (a git hook, a bootstrap script, a
locked-down CI image), it gets vendored into someone else's tree, or it is a
library published for others to install — there, every dependency you take is
imposed on every downstream consumer and their resolver. "It feels cleaner with
no deps" is not that constraint, and neither is "it's only a single file": PEP
723 inline metadata plus `uv run` gives a one-file script its own dependencies
with no install step.
</constraint>

Before adding a package, check that it is maintained, ships type hints, does one
job, drags in no transitive tree larger than the problem, and carries a license
and CVE history that survive review. Add it with `uv add` so it lands in
`pyproject.toml` (see the uv-installer rule).
