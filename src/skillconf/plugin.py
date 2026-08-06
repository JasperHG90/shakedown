"""The pytest plugin: one test per (target, case, repeat).

pytest is the runner, so `-k`, `-x`, `-n`, `--lf`, and every other plugin
keep working. There is no bespoke reporting format to learn.
"""

from __future__ import annotations

from typing import Any

import pytest

from skillconf.checks import Status, run_all
from skillconf.config import Case, Config, Target, load
from skillconf.runner import converse
from skillconf.sandbox import create


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register skillconf's options."""
    group = parser.getgroup("skillconf")
    group.addoption("--skillconf-config", default=None, help="path to skillconf.toml")
    group.addoption("--harness", default=None, help="only targets whose label contains this")
    group.addoption("--repeat", type=int, default=None, help="runs per (target, case)")
    group.addoption("--timeout", type=float, default=300.0, help="seconds per turn")
    group.addoption(
        "--keep-workspaces",
        action="store_true",
        help="keep sandboxes for inspection (failures are kept regardless)",
    )


@pytest.fixture(scope="session")
def skillconf(request: pytest.FixtureRequest) -> Config:
    """Return the loaded config."""
    path = request.config.getoption("--skillconf-config")
    from pathlib import Path

    return load(Path(path) if path else None)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize conformance tests over target x case x repeat."""
    needed = {"target", "case"} & set(metafunc.fixturenames)
    if not needed:
        return

    from pathlib import Path

    path = metafunc.config.getoption("--skillconf-config")
    try:
        config = load(Path(path) if path else None)
    except Exception:
        return

    only = metafunc.config.getoption("--harness")
    targets = [t for t in config.targets if not only or only in t.label]
    repeat = metafunc.config.getoption("--repeat") or config.repeat

    if "target" in metafunc.fixturenames:
        metafunc.parametrize("target", targets, ids=[t.label for t in targets])
    if "case" in metafunc.fixturenames:
        metafunc.parametrize("case", config.cases, ids=[c.name for c in config.cases])
    if "run_index" in metafunc.fixturenames:
        metafunc.parametrize("run_index", range(repeat), ids=[f"run{i}" for i in range(repeat)])


@pytest.fixture
def conformance(
    request: pytest.FixtureRequest, skillconf: Config, target: Target, case: Case
) -> Any:
    """Run one case against one target and return the check results.

    The sandbox is kept when anything failed, because a failure whose
    evidence was deleted is unactionable.
    """
    keep = bool(request.config.getoption("--keep-workspaces"))
    box = create(
        target.harness,
        skillconf.skill_dir,
        skillconf.skill_name,
        bin_dir=skillconf.bin_dir,
        keep=keep,
    )
    convo = converse(
        target.harness,
        case,
        box.path,
        model=target.model,
        timeout_s=float(request.config.getoption("--timeout")),
    )
    results = run_all(
        convo, case, target.harness, skillconf.skill_name, tool_needle=skillconf.skill_name
    )

    if any(r.status is Status.FAIL for r in results):
        box.keep = True
    request.addfinalizer(box.cleanup)

    if box.keep:
        print(f"\nworkspace kept: {box.path}")
    return results
