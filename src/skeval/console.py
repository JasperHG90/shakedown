"""Shared console and the rendering helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table
from rich.text import Text

from skeval.report import Score

if TYPE_CHECKING:
    from skeval.doctor import Check

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
    table = Table(title="skeval", title_style="bold", header_style="bold")
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
    if not isolated:
        table.caption = "sandbox not isolated: numbers include whatever else the harness could see"
        table.caption_style = "yellow"
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
