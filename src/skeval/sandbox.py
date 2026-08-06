"""Where a run happens: a container, or a temp directory.

A container has no developer configuration to pick up, so nothing needs a
flag to suppress it. That matters because the obvious flag for the job,
Claude Code's ``--safe-mode``, disables skills.
"""

from __future__ import annotations

import contextlib
import shlex
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from skeval.models import Harness, Skill

WORK = "/work"


class Sandbox(ABC):
    """A workspace the harness runs in."""

    path: Path
    keep: bool = False

    @abstractmethod
    def exec(self, argv: list[str], env: dict[str, str], timeout_s: float) -> tuple[int, str, str]:
        """Run ``argv`` and return (exit code, stdout, stderr)."""

    @abstractmethod
    def cleanup(self) -> None:
        """Release the sandbox."""

    def seed(self, harness: Harness, skill: Skill) -> None:
        """Copy the skill where the harness discovers it, plus any bin/."""
        dest = self.path / harness.skills / skill.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill.path, dest, dirs_exist_ok=True)
        if skill.bin_dir:
            shutil.copytree(skill.bin_dir, self.path / "bin", dirs_exist_ok=True)


class TempSandbox(Sandbox):
    """A temp directory on the host. Fast, and not isolated."""

    def __init__(self, harness: Harness, *, keep: bool = False) -> None:
        self.path = Path(tempfile.mkdtemp(prefix=f"skeval-{harness.name}-"))
        self.keep = keep

    def exec(self, argv: list[str], env: dict[str, str], timeout_s: float) -> tuple[int, str, str]:
        """Run on the host, in the sandbox directory."""
        env = {**env, "PATH": f"{self.path / 'bin'}:{env.get('PATH', '')}"}
        try:
            done = subprocess.run(
                argv,
                cwd=self.path,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return -1, "", "timed out"
        return done.returncode, done.stdout, done.stderr

    def cleanup(self) -> None:
        """Remove the directory unless it is being kept."""
        if not self.keep:
            shutil.rmtree(self.path, ignore_errors=True)


class ContainerSandbox(Sandbox):
    """A container built from the harness's image. Isolated."""

    def __init__(self, harness: Harness, *, keep: bool = False) -> None:
        from testcontainers.core.container import DockerContainer

        if not harness.image:
            raise RuntimeError(f"harness {harness.name} declares no image")
        self.path = Path(tempfile.mkdtemp(prefix=f"skeval-{harness.name}-"))
        self.keep = keep
        self._container = (
            DockerContainer(harness.image)
            .with_volume_mapping(str(self.path), WORK, "rw")
            .with_command("sleep infinity")
        )
        self._container.start()
        if harness.install:
            self._sh(harness.install)

    def _sh(self, command: str) -> tuple[int, str, str]:
        code, output = self._container.exec(["sh", "-lc", command])
        text = output.decode() if isinstance(output, bytes) else str(output)
        return code, text, ""

    def exec(self, argv: list[str], env: dict[str, str], timeout_s: float) -> tuple[int, str, str]:
        """Run inside the container with only the declared environment."""
        del timeout_s
        exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
        joined = shlex.join(argv)
        return self._sh(f"cd {WORK} && export PATH={WORK}/bin:$PATH {exports} && {joined}")

    def cleanup(self) -> None:
        """Stop the container and remove the mounted directory."""
        with contextlib.suppress(Exception):
            self._container.stop()
        if not self.keep:
            shutil.rmtree(self.path, ignore_errors=True)


def create(harness: Harness, skill: Skill, *, backend: str = "tmp", keep: bool = False) -> Sandbox:
    """Build a sandbox and seed the skill into it."""
    box: Sandbox = (
        ContainerSandbox(harness, keep=keep)
        if backend == "container"
        else TempSandbox(harness, keep=keep)
    )
    box.seed(harness, skill)
    return box
