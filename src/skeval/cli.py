"""A thin front for pytest."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from skeval.console import checks_table, console
from skeval.models import ConfigError, Harness, load_config
from skeval.report import REPORT_NAME

if TYPE_CHECKING:
    from skeval.doctor import Diagnosis

# No no_args_is_help: click would print the help and exit before the callback
# runs, and the banner would never appear.
app = typer.Typer(add_completion=False)
TESTS = Path(__file__).parent / "conformance.py"


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="print the version and exit")] = False,
) -> None:
    """Harness conformance testing for agent skills."""
    from skeval import banner

    if version:
        print(banner.version())
        raise typer.Exit(0)
    if ctx.invoked_subcommand is None:
        banner.print_banner(console)
        # Echoed rather than rich-printed: the help text is click's, and
        # square brackets in it are not markup.
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


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
    elif console.is_terminal:
        # Capture would swallow the live progress. Nothing in a conformance
        # run prints except skeval itself, so there is nothing to capture.
        # Parallel runs opt out: several workers would fight over one line.
        argv += ["-s"]
    if keep:
        argv += ["--keep-workspaces"]
    raise typer.Exit(subprocess.run([*argv, *(pytest_args or [])], check=False).returncode)


@app.command()
def init(
    skill: Annotated[Path, typer.Argument(help="where to scaffold the skill")] = Path("my-skill"),
    config: Annotated[Path, typer.Option("--config", help="where to write skeval.toml")] = Path(
        "skeval.toml"
    ),
) -> None:
    """Scaffold a config and a skill that already passes."""
    from skeval.scaffold import scaffold

    try:
        written = scaffold(skill, config)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc

    for path in written:
        console.print(f"  [green]+[/] {path}")
    console.print(f"\nnext: [cyan]skeval doctor[/], then [cyan]skeval run {skill}[/]")


def _diagnose(name: str, harness: Harness, *, model: str, sandbox: str) -> Diagnosis:
    """Run the canary behind a spinner.

    A canary turn is a whole model round trip, so without this the command
    looks hung for the better part of a minute.
    """
    from skeval.doctor import diagnose

    label = f"[cyan]{name}[/]"
    with console.status(f"{label}: starting", spinner="dots") as spinner:
        return diagnose(
            harness,
            model=model,
            backend=sandbox,
            notify=lambda step: spinner.update(f"{label}: {step}"),
        )


@app.command()
def summary(
    report: Annotated[Path, typer.Argument(help="a report written by `skeval run`")] = Path(
        REPORT_NAME
    ),
) -> None:
    """Render a report as markdown, for a PR comment or a job summary."""
    from skeval.report import Report

    if not report.is_file():
        console.print(f"[red]no report at {report}[/]")
        raise typer.Exit(2)
    # Printed rather than rich-rendered: the destination is a Markdown box
    # on GitHub, so styling it here would only corrupt it.
    print(Report.model_validate_json(report.read_text()).markdown(), end="")


@app.command()
def doctor(
    config: Annotated[Path | None, typer.Option("--config")] = None,
    harness: Annotated[str | None, typer.Option(help="only this harness")] = None,
    sandbox: Annotated[str, typer.Option(help="tmp or container")] = "tmp",
) -> None:
    """Check a harness against the prerequisites."""
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
        found = _diagnose(name, loaded.harness[name], model=model, sandbox=sandbox)
        console.print(checks_table(name, found.checks))
        console.print(found.verdict())
        console.print(f"[dim]canary workspace: {found.workspace}[/]")
        if not found.qualifies:
            worst = 1
    raise typer.Exit(worst)


def main() -> None:
    """Entry point."""
    app()
