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
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from functools import cache
from pathlib import Path

from shakedown.models import CASES_NAME, Harness, Skill

WORK = "/work"

#: Files that live beside a skill for shakedown's benefit, not the model's.
#: Seeding them would hand the model the answers it is being measured on.
NOT_THE_SKILL = (CASES_NAME, "README.md")

#: Variables that describe the host. A container has its own.
HOST_ONLY = frozenset({"PATH", "HOME"})


def _text(chunk: bytes | None) -> str:
    """Decode one half of a demuxed exec stream."""
    return chunk.decode() if chunk else ""


@cache
def _image_for(name: str, image: str, dockerfile: str, stamp: float) -> str:
    """The image to run this harness in, built at most once per process.

    A sandbox is created per scenario, so building or installing here would
    repeat on every case, every repeat, every target. Cached on the
    dockerfile's mtime, so editing it rebuilds and nothing else does.
    """
    del stamp
    if image:
        return image
    if not dockerfile:
        raise RuntimeError(
            f"harness {name} declares neither `image` nor `dockerfile`, "
            "so there is nothing to run a container from"
        )

    from testcontainers.core.image import DockerImage

    path = Path(dockerfile)
    built = DockerImage(
        path=path.parent,
        dockerfile_path=path.name,
        tag=f"shakedown-{name}:latest",
        clean_up=False,
    ).build()
    return str(built)


def image_for(harness: Harness) -> str:
    """Resolve this harness to a runnable image."""
    stamp = Path(harness.dockerfile).stat().st_mtime if harness.dockerfile else 0.0
    return _image_for(harness.name, harness.image, harness.dockerfile, stamp)


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
        """Copy the skill where the harness discovers it, plus any bin/.

        `bin/` holds the skill's own executables and then the cases'
        fixtures, and sits ahead of everything on PATH.

        Everything shakedown keeps beside the skill is left out. ``cases.toml``
        holds the replies to the withheld inputs and the exact strings each
        artifact is checked for: a model that reads it can pass without
        being asked anything, which is the one thing ``inputs_resolved``
        claims to rule out. A README beside it gives the same game away in
        prose.
        """
        dest = self.path / harness.skills / skill.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            skill.path, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*NOT_THE_SKILL)
        )
        if skill.bin_dir:
            shutil.copytree(skill.bin_dir, self.path / "bin", dirs_exist_ok=True)
        # Last, so a stand-in shadows the real thing of the same name: a
        # skill that shells out to `gh` is measured against a `gh` that
        # records the call rather than opening the pull request.
        if skill.fixtures:
            shutil.copytree(skill.fixtures, self.path / "bin", dirs_exist_ok=True)


class TempSandbox(Sandbox):
    """A temp directory on the host. Fast, and not isolated."""

    def __init__(self, harness: Harness, *, keep: bool = False) -> None:
        self.path = Path(tempfile.mkdtemp(prefix=f"shakedown-{harness.name}-"))
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
    """A container from the harness's image or dockerfile. Isolated."""

    def __init__(self, harness: Harness, *, keep: bool = False) -> None:
        from testcontainers.core.container import DockerContainer

        image = image_for(harness)
        self.path = Path(tempfile.mkdtemp(prefix=f"shakedown-{harness.name}-"))
        self.keep = keep
        self._container = (
            DockerContainer(image)
            .with_volume_mapping(str(self.path), WORK, "rw")
            .with_command("sleep infinity")
        )
        self._container.start()

    def _sh(self, command: str, timeout_s: float) -> tuple[int, str, str]:
        """Run ``command`` in the container, keeping stdout and stderr apart.

        testcontainers' own ``exec`` merges the two. A harness writes its
        stream to stdout and its warnings to stderr, so merging them puts a
        line of prose in the middle of the JSON and the parse fails on a
        run that was otherwise fine.

        Docker's exec has no deadline of its own, so ``timeout_s`` is
        enforced from this side and the container is killed to stop the
        work. Wrapping the command in the image's ``timeout`` would be
        neater, but would only work on images that ship one.

        Returns the same ``(-1, "", "timed out")`` as the host sandbox when
        the deadline passes, so the runner treats both backends alike.
        """
        container = self._container.get_wrapped_container()

        def run() -> tuple[int, str, str]:
            result = container.exec_run(["sh", "-lc", command], demux=True)
            out, err = result.output
            return int(result.exit_code), _text(out), _text(err)

        pool = ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(run).result(timeout=timeout_s)
        except FutureTimeout:
            with contextlib.suppress(Exception):
                container.kill()
            return -1, "", "timed out"
        finally:
            # The worker is still blocked in exec_run until the kill lands,
            # so do not wait for it: the caller has its answer.
            pool.shutdown(wait=False)

    def exec(self, argv: list[str], env: dict[str, str], timeout_s: float) -> tuple[int, str, str]:
        """Run inside the container with only the declared environment.

        ``PATH`` and ``HOME`` are not passed through. Both name host
        directories the image does not have, and a single ``export`` takes
        the last assignment for a name, so exporting them would replace the
        container's own PATH — hiding the seeded ``bin/`` — and point HOME
        at a path nothing can write to. The container gets ``/work`` for
        both, which is the mount and is writable.
        """
        declared = {key: value for key, value in env.items() if key not in HOST_ONLY}
        exports = " ".join(f"{key}={shlex.quote(value)}" for key, value in declared.items())
        joined = shlex.join(argv)
        return self._sh(
            f"cd {WORK} && export PATH={WORK}/bin:$PATH HOME={WORK} {exports} && {joined}",
            timeout_s,
        )

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
