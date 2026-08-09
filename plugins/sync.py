#!/usr/bin/env python3
"""Copy the shared pieces into each plugin, so each one stands alone.

Both harnesses install a plugin by copying its directory and nothing
else. A hook command reaching outside that directory — `${ROOT}/../` —
therefore points at nothing once installed, and on the pre-tool hook that
failure exits 2, which is the block code: every shell command in the
session refused, by a plugin meant to save money.

So the script and the skills are vendored into each plugin rather than
shared by reference. That means copies, and copies drift, which is what
`test_plugins_are_in_sync` is for: it fails and tells you to run this.

    python plugins/sync.py            # write the copies
    python plugins/sync.py --check    # fail if they are stale
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS = (REPO / "plugins/claude-code", REPO / "plugins/gemini")
#: Canonical source, and where it lands inside every plugin.
SHARED = {
    REPO / "plugins/scripts/shakedown_hooks.py": Path("scripts/shakedown_hooks.py"),
    REPO / "skills/add-harness": Path("skills/add-harness"),
    REPO / "skills/analyze-results": Path("skills/analyze-results"),
    REPO / "skills/create-cases": Path("skills/create-cases"),
}


def pairs() -> list[tuple[Path, Path]]:
    """Every (source, destination) the vendoring covers."""
    return [(source, plugin / where) for plugin in PLUGINS for source, where in SHARED.items()]


def stale() -> list[Path]:
    """Destinations that do not match their source."""
    behind = []
    for source, destination in pairs():
        if source.is_dir():
            same = destination.is_dir() and not _differs(source, destination)
        else:
            same = destination.is_file() and filecmp.cmp(source, destination, shallow=False)
        if not same:
            behind.append(destination)
    return behind


def _differs(source: Path, destination: Path) -> bool:
    """Whether two trees hold different files, contents included."""
    found = filecmp.dircmp(source, destination)
    if found.left_only or found.right_only or found.funny_files:
        return True
    _, mismatch, errors = filecmp.cmpfiles(source, destination, found.common_files, shallow=False)
    if mismatch or errors:
        return True
    return any(_differs(source / name, destination / name) for name in found.common_dirs)


def sync() -> list[Path]:
    """Write every copy. Returns what it wrote."""
    written = []
    for source, destination in pairs():
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.rmtree(destination, ignore_errors=True)
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        written.append(destination)
    return written


def main(argv: list[str]) -> int:
    """Sync, or report what a sync would change."""
    if "--check" in argv:
        if behind := stale():
            named = "\n  ".join(str(path.relative_to(REPO)) for path in behind)
            print(f"stale, run `python plugins/sync.py`:\n  {named}", file=sys.stderr)
            return 1
        print("plugins are in sync")
        return 0

    for path in sync():
        print(f"  + {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
