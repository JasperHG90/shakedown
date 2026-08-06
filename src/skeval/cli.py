"""A thin front for pytest."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer

from skeval.console import checks_table, console
from skeval.models import ConfigError, load_config
from skeval.report import REPORT_NAME

app = typer.Typer(add_completion=False, help="Harness conformance testing for agent skills.")
TESTS = Path(__file__).parent / "conformance.py"


@app.command()
def run(
    skill: Annotated[Path, typer.Argument(help="path to the skill under test")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
    harness: Annotated[str | None, typer.Option(help="only targets matching this")] = None,
    case: Annotated[str | None, typer.Option(help="substring of a case name")] = None,
    repeat: Annotated[int | None, typer.Option(help="runs per target and case")] = None,
    sandbox: Annotated[str, typer.Option(help="tmp or container")] = "tmp",
    report: Annotated[Path, typer.Option(help="where to write the JSON report")] = Path(
        REPORT_NAME
    ),
    parallel: Annotated[int, typer.Option("--parallel", "-j", help="runs at a time")] = 1,
    keep: Annotated[bool, typer.Option("--keep", help="keep every workspace")] = False,
    pytest_args: Annotated[list[str] | None, typer.Argument(help="passed to pytest")] = None,
) -> None:
    """Run the conformance matrix. Spends money."""
    argv = [
        sys.executable,
        "-m",
        "pytest",
        str(TESTS),
        "-m",
        "live",
        "--skill",
        str(skill),
        "--sandbox",
        sandbox,
        "--report",
        str(report),
    ]
    if config:
        argv += ["--skeval-config", str(config)]
    if harness:
        argv += ["--harness", harness]
    if case:
        argv += ["-k", case]
    if repeat:
        argv += ["--repeat", str(repeat)]
    if parallel > 1:
        argv += ["-n", str(parallel), "--dist", "loadgroup"]
    if keep:
        argv += ["--keep-workspaces"]
    raise typer.Exit(subprocess.run([*argv, *(pytest_args or [])], check=False).returncode)


@app.command()
def doctor(
    config: Annotated[Path | None, typer.Option("--config")] = None,
    harness: Annotated[str | None, typer.Option(help="only this harness")] = None,
    sandbox: Annotated[str, typer.Option(help="tmp or container")] = "tmp",
) -> None:
    """Check a harness against the prerequisites."""
    from skeval.doctor import diagnose

    try:
        loaded = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc

    names = [harness] if harness else list(loaded.harness)
    worst = 0
    for name in names:
        if name not in loaded.harness:
            console.print(f"[red]unknown harness {name!r}[/]")
            raise typer.Exit(2)
        model = next((t.model for t in loaded.targets() if t.harness.name == name), "")
        found = diagnose(loaded.harness[name], model=model, backend=sandbox)
        console.print(checks_table(name, found.checks))
        console.print(found.verdict())
        console.print(f"[dim]canary workspace: {found.workspace}[/]")
        if not found.qualifies:
            worst = 1
    raise typer.Exit(worst)


def main() -> None:
    """Entry point."""
    app()
