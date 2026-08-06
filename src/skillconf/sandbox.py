"""Where a run happens, and what it is allowed to see.

The sandbox is not only isolation, it is deletion: inside one, the harness
has no developer configuration to pick up, so nothing needs a flag to
suppress it. That matters because the obvious flag for the job, Claude
Code's ``--safe-mode``, disables skills, which is the thing being measured.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from skillconf.config import Harness


@dataclass
class Sandbox:
    """An ephemeral working directory with the skill seeded into it."""

    path: Path
    keep: bool = False

    def cleanup(self) -> None:
        """Remove the sandbox unless it is being kept for inspection."""
        if not self.keep:
            shutil.rmtree(self.path, ignore_errors=True)


def create(
    harness: Harness,
    skill_dir: Path,
    skill_name: str,
    *,
    bin_dir: Path | None = None,
    keep: bool = False,
) -> Sandbox:
    """Return a sandbox with ``skill_dir`` seeded where ``harness`` looks.

    Seeding by copy rather than by a load-from-here flag, because a flag can
    load a skill without the model ever seeing it: a probe found
    ``--plugin-dir`` reporting a loaded plugin whose skill was absent from
    the model's skill list. A copy into the harness's own discovery path is
    the mechanism a real user would use.
    """
    root = Path(tempfile.mkdtemp(prefix=f"skillconf-{harness.name}-"))
    dest = root / harness.skill_dest.format(name=skill_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_dir, dest, dirs_exist_ok=True)
    if bin_dir is not None:
        shutil.copytree(bin_dir, root / "bin", dirs_exist_ok=True)
    return Sandbox(path=root, keep=keep)
