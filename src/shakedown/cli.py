"""A thin front for pytest."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from shakedown.console import checks_table, console
from shakedown.models import ConfigError, Harness, load_config
from shakedown.report import REPORT_NAME

if TYPE_CHECKING:
    from shakedown.doctor import Diagnosis

# No no_args_is_help: click would print the help and exit before the callback
# runs, and the banner would never appear.
app = typer.Typer(add_completion=False)
TESTS = Path(__file__).parent / "conformance.py"


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="print the version and exit")] = False,
) -> None:
    """Smoke-test agent skills across harnesses and models."""
    from shakedown import banner

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
    skill: Annotated[
        Path, typer.Argument(help="the skill under test, or the cases file naming it")
    ],
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
    """Run the matrix. Spends money."""
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
        argv += ["--shakedown-config", str(config)]
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
        # run prints except shakedown itself, so there is nothing to capture.
        # Parallel runs opt out: several workers would fight over one line.
        argv += ["-s"]
    if keep:
        argv += ["--keep-workspaces"]
    raise typer.Exit(subprocess.run([*argv, *(pytest_args or [])], check=False).returncode)


@app.command()
def init(
    skill: Annotated[Path, typer.Argument(help="where to scaffold the skill")] = Path("my-skill"),
    config: Annotated[Path, typer.Option("--config", help="where to write shakedown.toml")] = Path(
        "shakedown.toml"
    ),
) -> None:
    """Scaffold a config and a skill that already passes."""
    from shakedown.scaffold import scaffold

    try:
        written = scaffold(skill, config)
    except FileExistsError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc

    for path in written:
        console.print(f"  [green]+[/] {path}")
    console.print(f"\nnext: [cyan]shakedown doctor[/], then [cyan]shakedown run {skill}[/]")


def _diagnose(name: str, harness: Harness, *, model: str, sandbox: str) -> Diagnosis:
    """Run the canary behind a spinner.

    A canary turn is a whole model round trip, so without this the command
    looks hung for the better part of a minute.
    """
    from shakedown.doctor import diagnose

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
    report: Annotated[Path, typer.Argument(help="a report written by `shakedown run`")] = Path(
        REPORT_NAME
    ),
) -> None:
    """Render a report as markdown, for a PR comment or a job summary."""
    from shakedown.report import Report

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
    model: Annotated[
        str | None, typer.Option(help="the model to check with; defaults to the matrix")
    ] = None,
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
        # A harness the matrix does not name is a worked example, not a
        # target. Running it with an empty model would answer a question
        # nobody asked: every check fails, and the verdict blames the
        # harness for a model that was never chosen.
        chosen = model or next((t.model for t in loaded.targets() if t.harness.name == name), "")
        if not chosen:
            console.print(
                f"[red]harness {name!r} has no [[matrix]] entry, so there is no model "
                "to check it with. Add one, or pass --model.[/]"
            )
            raise typer.Exit(2)
        found = _diagnose(name, loaded.harness[name], model=chosen, sandbox=sandbox)
        console.print(checks_table(name, found.checks))
        console.print(found.verdict())
        console.print(f"[dim]canary workspace: {found.workspace}[/]")
        if not found.qualifies:
            worst = 1
    raise typer.Exit(worst)


def main() -> None:
    """Entry point."""
    app()
