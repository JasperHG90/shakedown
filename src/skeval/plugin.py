"""pytest plugin: one test per (target, case, run), plus the JSON report."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from skeval.checks import Result, Status, run_all
from skeval.console import console, failures_table, scores_table
from skeval.models import Case, Config, Skill, Target, load_config, load_skill
from skeval.report import REPORT_NAME, Report, RunRecord, TurnRecord
from skeval.runner import converse
from skeval.sandbox import create

#: Where the in-process report hangs, so the terminal hook can find it.
REPORT = pytest.StashKey[Report]()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register skeval's options."""
    group = parser.getgroup("skeval")
    group.addoption("--skill", default=None, help="path to the skill under test")
    group.addoption("--skeval-config", default=None, help="path to skeval.toml")
    group.addoption("--harness", default=None, help="only targets whose label contains this")
    group.addoption("--repeat", type=int, default=None, help="runs per (target, case)")
    group.addoption("--timeout", type=float, default=300.0, help="seconds per turn")
    group.addoption("--sandbox", default="tmp", choices=("tmp", "container"))
    group.addoption("--report", default=REPORT_NAME, help="where to write the JSON report")
    group.addoption("--keep-workspaces", action="store_true")


def _worker_id(config: pytest.Config) -> str:
    """xdist worker id, or "" on the controller."""
    return str(getattr(config, "workerinput", {}).get("workerid", ""))


def _shard_dir(config: pytest.Config) -> Path:
    return Path(str(config.getoption("--report"))).with_suffix(".shards")


def _config(pytest_config: pytest.Config) -> Config:
    path = pytest_config.getoption("--skeval-config")
    return load_config(Path(path) if path else None)


def _skill(pytest_config: pytest.Config) -> Skill:
    path = pytest_config.getoption("--skill")
    if not path:
        raise pytest.UsageError("--skill is required (path to the skill under test)")
    return load_skill(Path(path))


@pytest.fixture(scope="session")
def config(request: pytest.FixtureRequest) -> Config:
    """The loaded skeval.toml."""
    return _config(request.config)


@pytest.fixture(scope="session")
def skill(request: pytest.FixtureRequest) -> Skill:
    """The skill under test."""
    return _skill(request.config)


@pytest.fixture(scope="session")
def report(request: pytest.FixtureRequest) -> Iterator[Report]:
    """The report, written at session end."""
    skill_under_test = _skill(request.config)
    built = Report(
        skill=skill_under_test.name,
        sandbox=str(request.config.getoption("--sandbox")),
        isolated=request.config.getoption("--sandbox") == "container",
    )
    request.config.stash[REPORT] = built
    yield built

    worker = _worker_id(request.config)
    if worker:
        # Runs are independent, so xdist spreads them across processes. Each
        # worker writes a shard; the controller merges them at session end.
        shards = _shard_dir(request.config)
        shards.mkdir(parents=True, exist_ok=True)
        (shards / f"{worker}.json").write_text(built.model_dump_json())


def _collect(config: pytest.Config) -> Report | None:
    """This session's report: the workers' shards, or what ran in process."""
    shards = _shard_dir(config)
    files = sorted(shards.glob("*.json")) if shards.is_dir() else []
    if not files:
        return config.stash.get(REPORT, None)
    merged = Report.merge(files)
    for file in files:
        file.unlink()
    shards.rmdir()
    return merged


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Write the artifact and render the tables.

    Printing from the fixture's teardown put it inside pytest's capture,
    which discards it when the run is green: scores appeared only on
    failure. This hook runs with capture suspended.
    """
    config = terminalreporter.config
    if _worker_id(config):
        return
    built = _collect(config)
    if built is None or not built.runs:
        return
    path = built.write(Path(str(config.getoption("--report"))))
    console.print()
    console.print(scores_table(built.scores(), isolated=built.isolated))
    if failures := built.failures():
        console.print(failures_table(failures))
    console.print(f"report: [cyan]{path}[/]")


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize over target x case x run."""
    if not {"target", "case"} & set(metafunc.fixturenames):
        return
    try:
        config = _config(metafunc.config)
        skill = _skill(metafunc.config)
    except Exception:
        return

    only = metafunc.config.getoption("--harness")
    targets = [t for t in config.targets() if not only or only in t.label]
    repeat = metafunc.config.getoption("--repeat") or config.repeat

    if "target" in metafunc.fixturenames:
        metafunc.parametrize("target", targets, ids=[t.label for t in targets])
    if "case" in metafunc.fixturenames:
        metafunc.parametrize("case", skill.cases, ids=[c.name for c in skill.cases])
    if "run_index" in metafunc.fixturenames:
        metafunc.parametrize("run_index", range(repeat), ids=[f"run{i}" for i in range(repeat)])


@pytest.fixture
def conformance(
    request: pytest.FixtureRequest,
    skill: Skill,
    report: Report,
    target: Target,
    case: Case,
    run_index: int,
) -> list[Result]:
    """Run one case against one target and record the result."""
    keep = bool(request.config.getoption("--keep-workspaces"))
    box = create(
        target.harness,
        skill,
        backend=str(request.config.getoption("--sandbox")),
        keep=keep,
    )
    convo = converse(
        box,
        target.harness,
        case,
        model=target.model,
        timeout_s=float(request.config.getoption("--timeout")),
    )
    results = run_all(convo, case, target.harness, skill.name)

    failed = any(r.status is Status.FAIL for r in results)
    if failed:
        box.keep = True

    report.runs.append(
        RunRecord(
            target=target.label,
            model=target.model,
            case=case.name,
            run=run_index,
            prompt=case.prompt,
            results=results,
            turns=len(convo.turns),
            asked=convo.given,
            workspace=str(box.path),
            workspace_kept=box.keep,
            duration_s=round(sum(t.duration_s for t in convo.turns), 2),
            detail=[
                TurnRecord(
                    index=i,
                    argv=t.argv,
                    exit_code=t.exit_code,
                    duration_s=t.duration_s,
                    tool_calls=[{"name": c.name, "args": c.args} for c in t.tool_calls],
                    said=t.texts,
                    denied=t.denied,
                    stream=t.stream if box.keep else "",
                    stderr_tail=t.stderr_tail,
                )
                for i, t in enumerate(convo.turns)
            ],
        )
    )

    request.addfinalizer(box.cleanup)
    return results
