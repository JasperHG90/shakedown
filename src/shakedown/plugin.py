"""pytest plugin: one test per (target, case, run), plus the JSON report."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from rich.status import Status as Spinner

from shakedown.checks import Result, Status, run_all
from shakedown.console import console, failures_table, scores_table
from shakedown.models import Case, Config, Skill, Target, load_config, load_skill
from shakedown.report import REPORT_NAME, Report, RunRecord, TurnRecord
from shakedown.runner import converse
from shakedown.sandbox import create

#: Where the in-process report hangs, so the terminal hook can find it.
REPORT = pytest.StashKey[Report]()
#: This session's private shard directory.
SHARDS = pytest.StashKey[Path]()
#: The live spinner, and [done, total] scenarios.
PROGRESS = pytest.StashKey[Spinner]()
TALLY = pytest.StashKey[list[int]]()


def _spinner(config: pytest.Config) -> Spinner | None:
    """The live spinner, if this session has one."""
    return config.stash.get(PROGRESS, None)


def _say(config: pytest.Config, text: str) -> None:
    """Update the spinner, if anything is watching."""
    if status := _spinner(config):
        done, total = config.stash[TALLY]
        status.update(f"[dim]{done}/{total}[/] {text}")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Clear last session's shards, and start the spinner if one is wanted.

    A run is minutes of silence otherwise: one scenario is a whole model
    round trip per turn. Capture has to be off for the animation to reach
    the terminal rather than a discarded buffer, which is why `shakedown
    case run` passes `-s`. Under xdist the workers share one terminal, so the
    controller stays quiet rather than interleaving several spinners.
    """
    config = session.config
    if _worker_id(config) or config.option.capture != "no" or not console.is_terminal:
        return
    config.stash[TALLY] = [0, 0]
    status = console.status("starting", spinner="dots")
    status.start()
    config.stash[PROGRESS] = status


def pytest_collection_finish(session: pytest.Session) -> None:
    """Now the denominator is known."""
    if _spinner(session.config):
        session.config.stash[TALLY][1] = len(session.items)


@pytest.hookimpl(wrapper=True)
def pytest_report_teststatus(
    report: pytest.CollectReport | pytest.TestReport, config: pytest.Config
) -> Generator[None, tuple[str, str, str], tuple[str, str, str]]:
    """Drop pytest's inline status character while the spinner is live.

    Both write to the same line, so the stray `.` or `s` lands inside the
    spinner's text. The counts and the failure summary are untouched: only
    the per-test character goes.
    """
    category, short, verbose = yield
    if _spinner(config):
        return category, "", verbose
    return category, short, verbose


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register shakedown's options."""
    group = parser.getgroup("shakedown")
    group.addoption("--skill", default=None, help="path to the skill under test")
    group.addoption("--shakedown-config", default=None, help="path to shakedown.toml")
    group.addoption("--harness", default=None, help="only targets whose label contains this")
    group.addoption("--repeat", type=int, default=None, help="runs per (target, case)")
    group.addoption("--timeout", type=float, default=300.0, help="seconds per turn")
    group.addoption("--sandbox", default="tmp", choices=("tmp", "container"))
    group.addoption("--report", default=REPORT_NAME, help="where to write the JSON report")
    group.addoption("--keep-workspaces", action="store_true")


def _worker_id(config: pytest.Config) -> str:
    """xdist worker id, or "" on the controller."""
    return str(getattr(config, "workerinput", {}).get("workerid", ""))


#: Passed to xdist workers, which inherit the controller's environment.
SHARD_ENV = "SHAKEDOWN_SHARD_DIR"


def pytest_configure(config: pytest.Config) -> None:
    """Give this session a private directory for its shards.

    Deriving it from the report path put it next to the report, where a run
    killed mid-flight left it behind for the next run to merge as if those
    results were current, and where two runs in one directory consumed each
    other's shards. A fresh temp directory per session cannot do either.

    Created before xdist spawns its workers, so they inherit the path. Only
    a worker reads what it inherited: any other child process, such as a
    nested pytest, gets its own directory rather than writing into its
    parent's and being merged into someone else's numbers.
    """
    inherited = os.environ.get(SHARD_ENV)
    if _worker_id(config) and inherited:
        config.stash[SHARDS] = Path(inherited)
        return
    fresh = tempfile.mkdtemp(prefix="shakedown-shards-")
    os.environ[SHARD_ENV] = fresh
    config.stash[SHARDS] = Path(fresh)


def _shard_dir(config: pytest.Config) -> Path:
    return config.stash[SHARDS]


def _config(pytest_config: pytest.Config) -> Config:
    path = pytest_config.getoption("--shakedown-config")
    return load_config(Path(path) if path else None)


def _skill(pytest_config: pytest.Config) -> Skill:
    path = pytest_config.getoption("--skill")
    if not path:
        raise pytest.UsageError(
            "--skill is required (the skill under test, or the cases file naming it)"
        )
    return load_skill(Path(path))


@pytest.fixture(scope="session")
def config(request: pytest.FixtureRequest) -> Config:
    """The loaded shakedown.toml."""
    return _config(request.config)


@pytest.fixture(scope="session")
def skill(request: pytest.FixtureRequest) -> Skill:
    """The skill under test."""
    return _skill(request.config)


@pytest.fixture(scope="session")
def report(request: pytest.FixtureRequest) -> Report:
    """The report, held in memory and sharded to disk as runs complete."""
    skill_under_test = _skill(request.config)
    built = Report(
        skill=skill_under_test.name,
        sandbox=str(request.config.getoption("--sandbox")),
        isolated=request.config.getoption("--sandbox") == "container",
    )
    request.config.stash[REPORT] = built
    return built


def _shard(config: pytest.Config, built: Report) -> None:
    """Write this worker's shard, if this process is a worker.

    Runs are independent, so xdist spreads them across processes and each
    worker keeps its own shard for the controller to merge. The write
    happens after every run rather than at session teardown: a worker that
    goes away without running its finalizers took its results with it, and
    the report then under-counts a run that actually happened.
    """
    worker = _worker_id(config)
    if not worker:
        return
    shards = _shard_dir(config)
    shards.mkdir(parents=True, exist_ok=True)
    # Rewritten after every run, so a half-written file is a live hazard,
    # not a rare one. Write beside the target and rename: a reader sees the
    # previous complete shard or the new one, never a truncated middle.
    scratch = shards / f"{worker}.json.part"
    scratch.write_text(built.model_dump_json())
    os.replace(scratch, shards / f"{worker}.json")


def _collect(config: pytest.Config) -> Report | None:
    """This session's report: the workers' shards, or what ran in process."""
    shards = _shard_dir(config)
    files = sorted(shards.glob("*.json")) if shards.is_dir() else []
    if not files:
        return config.stash.get(REPORT, None)
    merged = Report.merge(files)
    for file in files:
        file.unlink()
    shutil.rmtree(shards, ignore_errors=True)
    return merged


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Write the artifact and render the tables.

    Printing from the fixture's teardown put it inside pytest's capture,
    which discards it when the run is green: scores appeared only on
    failure. This hook runs with capture suspended.
    """
    config = terminalreporter.config
    if spinner := _spinner(config):
        spinner.stop()
    if _worker_id(config):
        return
    built = _collect(config)
    shutil.rmtree(config.stash[SHARDS], ignore_errors=True)
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
    where = f"[cyan]{target.label}[/] {case.name} run{run_index}"
    _say(request.config, f"{where}: preparing")
    convo = converse(
        box,
        target.harness,
        case,
        model=target.model,
        timeout_s=float(request.config.getoption("--timeout")),
        notify=lambda turn: _say(request.config, f"{where}: turn {turn + 1}"),
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

    _shard(request.config, report)

    request.addfinalizer(box.cleanup)
    if spinner := _spinner(request.config):
        request.config.stash[TALLY][0] += 1
        spinner.update(
            f"[dim]{request.config.stash[TALLY][0]}/{request.config.stash[TALLY][1]}[/] done"
        )
    return results
