"""Shared console and the rendering helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from shakedown.report import THIN, Score

if TYPE_CHECKING:
    from shakedown.doctor import Check

console = Console()

_MARK = {
    "pass": ("[green]pass[/]", "green"),
    "fail": ("[red]fail[/]", "red"),
    "unsupported": ("[dim]n/a[/]", "dim"),
    "not_triggered": ("[yellow]not triggered[/]", "yellow"),
}


def status_text(status: str) -> str:
    """Colored label for a check status."""
    return _MARK.get(status, (status, ""))[0]


def scores_table(scores: dict[str, dict[str, Score]], *, isolated: bool) -> Table:
    """A table of per-target, per-dimension scores."""
    table = Table(title="shakedown", title_style="bold", header_style="bold")
    for column in ("target", "dimension", "n", "passed", "rate", "n/a", "not triggered"):
        table.add_column(
            column, justify="right" if column not in ("target", "dimension") else "left"
        )

    for target, dims in sorted(scores.items()):
        for dim, score in sorted(dims.items()):
            rate = score.rate
            if rate is None:
                shown = Text("—", style="dim")
            else:
                style = "green" if rate == 1 else "yellow" if rate >= 0.5 else "red"
                shown = Text(f"{rate:.0%}", style=style)
            table.add_row(
                target,
                dim,
                str(score.scored),
                str(score.passed),
                shown,
                str(score.unsupported),
                str(score.not_triggered),
            )
    notes = []
    if not isolated:
        notes.append("sandbox not isolated: numbers include whatever else the harness could see")
    if thin := _thin_rates(scores):
        notes.append(
            f"{thin}: a mixed rate over so few runs is noise as often as signal — "
            "raise --repeat before acting on it"
        )
    if notes:
        table.caption = "\n".join(notes)
        table.caption_style = "yellow"
    return table


def _thin_rates(scores: dict[str, dict[str, Score]]) -> str:
    """Targets and dimensions whose mixed rate rests on too few runs each.

    Counted per case rather than over the pooled `scored`, because five
    cases run twice also totals ten and is nothing like ten attempts at
    any one of them — and because raising `--repeat` would otherwise
    silence the caution by growing a number the caution was never about.

    Only the mixed rates. Not because `0%` and `100%` are better evidence
    — three passes out of three is consistent with a true rate near a
    third — but because at the default single repeat every dimension is
    one or the other, and a caption that always shows is furniture.
    """
    thin = {
        f"{target} {dim}"
        for target, dims in scores.items()
        for dim, score in dims.items()
        if score.mixed and score.per_case < THIN
    }
    return ", ".join(sorted(thin))


def failures_table(failures: list[dict[str, Any]]) -> Table:
    """What failed, why, and where the evidence is."""
    table = Table(title="failures", title_style="bold red", header_style="bold")
    for column in ("case", "run", "failed", "reason", "workspace"):
        table.add_column(column, overflow="fold")
    for failure in failures:
        table.add_row(
            str(failure["case"]),
            str(failure["run"]),
            Text(", ".join(failure["failed"]), style="red"),
            "; ".join(failure["reasons"]),
            Text(failure["workspace"] or "(cleaned)", style="dim"),
        )
    return table


def checks_table(name: str, checks: list[Check]) -> Table:
    """A table of doctor's prerequisite checks."""
    table = Table(title=name, title_style="bold", header_style="bold", show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("prerequisite")
    table.add_column("", justify="center")
    table.add_column("detail", style="dim")
    for check in checks:
        mark = (
            "[green]ok[/]" if check.ok else ("[red]FAIL[/]" if check.required else "[yellow]--[/]")
        )
        table.add_row(str(check.number), check.name, mark, check.detail)
    return table
