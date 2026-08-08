"""A thin front for pytest."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from shakedown.console import checks_table, console
from shakedown.models import CASES_DIR, ConfigError, Harness, load_config
from shakedown.report import REPORT_NAME
from shakedown.scaffold import HARNESSES, scaffold

if TYPE_CHECKING:
    from shakedown.doctor import Diagnosis

# No no_args_is_help: click would print the help and exit before the callback
# runs, and the banner would never appear.
app = typer.Typer(
    add_completion=True,
    no_args_is_help=False,
    help="Smoke-test agent skills across harnesses and models.",
)
case_app = typer.Typer(
    add_completion=True, help="Work with a cases file: check it, or run it.", no_args_is_help=True
)
app.add_typer(case_app, name="case")
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


@case_app.command("run")
def case_run(
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


@case_app.command("validate")
def case_validate(
    path: Annotated[Path, typer.Argument(help="the cases file, or the skill whose cases to check")],
) -> None:
    """Check a cases file without running anything. Spends nothing."""
    from shakedown.models import load_skill

    try:
        skill = load_skill(path)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc

    console.print(f"[green]ok[/] {skill.name}: {len(skill.cases)} case(s), version {skill.version}")
    seen: set[str] = set()
    for case in skill.cases:
        checks = [
            "tool_used" if case.tool else "",
            "artifact_created" if case.artifacts else "",
            # Answers alone prove nothing: the reply reaching an artifact is
            # the evidence, so with no artifact the run reports unsupported.
            # Saying otherwise here would certify a case that measures
            # nothing, which is the one thing this command exists to catch.
            "inputs_resolved" if case.answers and case.artifacts else "",
        ]
        measured = ", ".join(c for c in checks if c) or "[yellow]nothing but skill_fired[/]"
        console.print(f"  [cyan]{case.name}[/]: {measured}")
        if case.answers and not case.artifacts:
            console.print(
                "    [yellow]answers with no artifact:[/] the reply has nowhere to land, "
                "so asking is measured as unsupported"
            )
        if case.name in seen:
            console.print(f"    [yellow]duplicate name:[/] two cases called {case.name!r}")
        seen.add(case.name)
        # `--case` becomes pytest's `-k`, which parses an expression: a name
        # with a space or a keyword in it cannot be selected.
        if unselectable := _unselectable(case.name):
            console.print(f"    [yellow]{unselectable}:[/] `--case {case.name}` will not select it")
    for fixture in skill.fixtures:
        console.print(f"  [dim]fixtures:[/] {fixture}")


def _unselectable(name: str) -> str:
    """Why pytest's `-k` could not take this case name, if it could not."""
    if any(ch.isspace() for ch in name):
        return "whitespace in the name"
    if name in {"not", "and", "or"}:
        return "a `-k` keyword as the name"
    return ""


@app.command()
def init(
    harness: Annotated[
        list[str] | None,
        typer.Option(
            "--harness",
            help="a harness to describe; repeat for several. " + ", ".join(HARNESSES),
        ),
    ] = None,
    config: Annotated[Path, typer.Option("--config", help="where to write shakedown.toml")] = Path(
        "shakedown.toml"
    ),
) -> None:
    """Scaffold a config, and the directory cases live in.

    Name no harness and the config is a stub that still parses; name
    several and each gets a block and a matrix entry.
    """
    try:
        written = scaffold(config, harness or [])
    except (ValueError, FileExistsError, OSError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(2) from exc

    for path in written:
        console.print(f"  [green]+[/] {path}")
    console.print(
        f"\nnext: [cyan]shakedown doctor[/], then write "
        f"[cyan]{CASES_DIR}/<slug>.cases.toml[/] naming the skill it measures"
    )


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
    report: Annotated[Path, typer.Argument(help="a report written by `shakedown case run`")] = Path(
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
    if not names:
        # A config with no harness parses, so this is a real state rather
        # than a broken file. Exiting 0 in silence would read as "every
        # harness qualifies".
        console.print(
            "[red]no harnesses in the config[/], so there is nothing to check. "
            "Add one with `shakedown init --harness <name>`, or write your own."
        )
        raise typer.Exit(2)
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
