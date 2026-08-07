"""The logo and the one-glance status block shown on a bare `skeval`."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import TYPE_CHECKING

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console

TAGLINE = "Harness conformance testing for agent skills."

# The mark is two overlapping squares with the overlap filled: a skill run
# through two harnesses, scored on where they agree.
SIZE = 14
_SQUARES = ((0, 9), (4, 13))  # (first, last) row and column of each square
_FILL = (5, 8)  # the overlap, minus the borders that enclose it

# The logo's navy would vanish on a dark terminal, so the outline is a slate
# that reads on both. The fill keeps the brand green.
OUTLINE = "#94a3b8"
FILL = "#22a06b"

# Half blocks: one character carries two pixels, so a pixel comes out square.
_UPPER, _LOWER = "▀", "▄"

# Space between the mark and the text beside it.
GUTTER = 3


def version() -> str:
    """Installed skeval version, or ``dev`` when running from a source tree."""
    try:
        return importlib.metadata.version("skeval")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def _pixel(row: int, col: int) -> str | None:
    """Color of one logo pixel, or ``None`` where the logo is transparent."""
    for first, last in _SQUARES:
        on_square = first <= row <= last and first <= col <= last
        if on_square and (row in (first, last) or col in (first, last)):
            return OUTLINE
    if _FILL[0] <= row <= _FILL[1] and _FILL[0] <= col <= _FILL[1]:
        return FILL
    return None


def logo() -> list[Text]:
    """The mark, one ``Text`` per terminal line."""
    lines = []
    for top in range(0, SIZE, 2):
        line = Text()
        for col in range(SIZE):
            upper, lower = _pixel(top, col), _pixel(top + 1, col)
            if upper and lower:
                line.append(_UPPER, Style(color=upper, bgcolor=lower))
            elif upper:
                line.append(_UPPER, Style(color=upper))
            elif lower:
                line.append(_LOWER, Style(color=lower))
            else:
                line.append(" ")
        lines.append(line)
    return lines


def _config_line() -> Text:
    """What config skeval would use from here, or what is wrong with it."""
    from skeval.models import ConfigError, find_config, load_config

    try:
        path = find_config()
    except (ConfigError, OSError):
        return Text("no skeval.toml here — run ", style="yellow").append(
            "skeval init", style="bold yellow"
        )

    # Just the name when the config is in this directory; the whole path when
    # the upward search found it somewhere else, since that is a surprise.
    where = path.name if path.parent == _cwd() else _short(path)
    try:
        loaded = load_config(path)
    except ConfigError:
        # A config that exists but does not load is a different problem from
        # no config at all, and `skeval init` would refuse to overwrite it.
        return Text(f"{where} is not loadable — run ", style="red").append(
            "skeval doctor", style="bold red"
        )

    harnesses = len(loaded.harness)
    targets = len(loaded.targets())
    return Text(
        f"{where} · {harnesses} harness{'es' if harnesses != 1 else ''}"
        f" · {targets} target{'s' if targets != 1 else ''}",
        style="dim",
    )


def _cwd() -> Path | None:
    """The working directory, or ``None`` when it has been deleted under us."""
    try:
        return Path.cwd()
    except OSError:
        return None


def _short(path: Path) -> str:
    """``path`` with the home directory collapsed to ``~``."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except (ValueError, OSError):
        return str(path)


def status_lines() -> list[Text]:
    """The lines printed beside the logo."""
    here = _cwd()
    return [
        Text(f"skeval v{version()}", style="bold"),
        Text(TAGLINE, style="dim"),
        _config_line(),
        Text(_short(here) if here else "(working directory is gone)", style="dim"),
    ]


def _head(line: Text, width: int) -> Text:
    """The first ``width`` cells of ``line``."""
    used = 0
    for index, char in enumerate(line.plain):
        used += cell_len(char)
        if used > width:
            return line[:index]
    return line


def _tail(line: Text, width: int) -> Text:
    """The last ``width`` cells of ``line``."""
    used = 0
    plain = line.plain
    for index in range(len(plain) - 1, -1, -1):
        used += cell_len(plain[index])
        if used > width:
            return line[index + 1 :]
    return line


def _fit(line: Text, width: int) -> Text:
    """Trim ``line`` to ``width`` cells. A wrapped line would step on the logo.

    A path keeps its tail, where the directory you are actually in sits;
    a sentence keeps its head, where it starts. Cells, not characters: a CJK
    path is half as many characters as it is columns, and counting characters
    would let it wrap.
    """
    if width < 1:
        return Text()
    if line.cell_len <= width:
        return line
    ellipsis = Text("…", style="dim")
    if "/" in line.plain:
        return ellipsis.append_text(_tail(line, width - 1))
    return _head(line, width - 1).append_text(ellipsis)


def banner(width: int | None = None) -> Text:
    """The logo and the status lines, side by side, trimmed to ``width``.

    In a terminal too narrow for both, the words win and the mark is dropped.
    """
    left = logo()
    right = status_lines()
    if width is None:
        room = max(line.cell_len for line in right)
    else:
        room = width - SIZE - GUTTER
        if room < 1 and width < SIZE:
            return Text("\n").join(_fit(line, width) for line in right)

    # Sit the text in the middle of the mark rather than at its top edge, and
    # keep going past the mark if the status ever outgrows it.
    rows = max(len(left), len(right))
    top = max((len(left) - len(right)) // 2, 0)

    out = Text()
    for row in range(rows):
        out.append_text(left[row] if row < len(left) else Text(" " * SIZE))
        index = row - top
        if room >= 1 and 0 <= index < len(right):
            out.append(" " * GUTTER).append_text(_fit(right[index], room))
        if row < rows - 1:
            # Rich prints the last newline itself, and a second one would
            # leave a stray blank line under the mark.
            out.append("\n")
    return out


def print_banner(console: Console) -> None:
    """Print the banner, unless the output is a pipe or a file.

    A redirected `skeval` is being read by a script or a log, and block
    characters would be noise there.
    """
    if not console.is_terminal:
        return
    console.print(banner(console.width))
    console.rule(style=FILL)
    console.print()
