"""Offline tests. No subprocess, no spend."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from skeval.checks import Status, artifact_created, inputs_resolved, run_all, tool_used
from skeval.events import StreamError, ToolCall, Turn, parse, read
from skeval.models import (
    Answer,
    Case,
    ConfigError,
    Events,
    Harness,
    load_config,
    load_skill,
)
from skeval.report import Report, RunRecord
from skeval.runner import Conversation, _match

REPO = Path(__file__).resolve().parents[1]
NESTED = Events(container="message.content")
FLAT = Events(name_key="tool_name", args_key="parameters")


def harness(**kw: Any) -> Harness:
    """A harness with defaults."""
    return Harness(
        **{
            "name": "h",
            "start": ["bin", "-p", "{prompt}"],
            "resume": ["bin", "-p", "{reply}", "--resume", "{sid}"],
            "skills": ".x/skills",
            **kw,
        }
    )


def convo(
    ws: Path, calls: list[tuple[str, dict[str, str]]], given: list[str], **kw: Any
) -> Conversation:
    """A conversation carrying the given tool calls."""
    turn = Turn(tool_calls=[ToolCall(name=n, args=a) for n, a in calls], **kw)
    return Conversation(turns=[turn], given=given, workspace=ws)


def case(**kw: Any) -> Case:
    """A case with defaults. Pass artifact=None to drop the default file."""
    fields: dict[str, Any] = {"name": "c", "prompt": "p", "artifact": "PLAN.md", "tool": "planctl"}
    fields.update(kw)
    if fields.get("artifact") is None:
        fields.pop("artifact")
    return Case(**fields)


# --- events ---------------------------------------------------------------


def test_nested_and_flat_shapes_agree() -> None:
    """One optional descent covers both known harnesses."""
    nested = parse(
        [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {"command": "planctl write"}}
                    ]
                },
            }
        ],
        NESTED,
    )
    flat = parse(
        [
            {
                "type": "tool_use",
                "tool_name": "run_shell_command",
                "parameters": {"command": "planctl write"},
            }
        ],
        FLAT,
    )
    assert len(nested.tool_calls) == len(flat.tool_calls) == 1
    assert nested.called("planctl") and flat.called("planctl")


def test_one_record_may_carry_several_calls() -> None:
    """Counting records instead of blocks under-reports."""
    turn = parse(
        [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {}},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "planctl"}},
                    ]
                },
            }
        ],
        NESTED,
    )
    assert len(turn.tool_calls) == 2


def test_denials_are_parsed() -> None:
    """Reported structurally by the harness, so use that."""
    turn = parse([{"type": "result", "permission_denials": [{"tool_name": "Bash"}]}], NESTED)
    assert turn.denied == ["Bash"]


def test_truncated_stream_raises(tmp_path: Path) -> None:
    """A partial result is worse than none, because it gets scored."""
    bad = tmp_path / "s.jsonl"
    bad.write_text('{"type": "assistant"}\n{"type": "assi')
    with pytest.raises(StreamError):
        read(bad)


# --- config ---------------------------------------------------------------


def test_shipped_config_and_skill_load() -> None:
    """Both files in the repo are valid."""
    config = load_config(REPO / "skeval.toml")
    skill = load_skill(REPO / "examples/write-plan")
    assert [t.label for t in config.targets()] == ["claude-code/claude-opus-5"]
    assert skill.name == "write-plan"
    assert skill.bin_dir is not None


def test_skill_name_comes_from_front_matter(tmp_path: Path) -> None:
    """The path is the only input; the name is read from the skill."""
    (tmp_path / "SKILL.md").write_text("---\nname: my-skill\ndescription: d\n---\nbody\n")
    (tmp_path / "cases.toml").write_text('[[case]]\nname="c"\nprompt="p"\nartifact="A"\ntool="t"\n')
    assert load_skill(tmp_path).name == "my-skill"


def test_a_skill_without_front_matter_is_refused(tmp_path: Path) -> None:
    """A nameless skill cannot be seeded anywhere."""
    (tmp_path / "SKILL.md").write_text("no front matter\n")
    (tmp_path / "cases.toml").write_text('[[case]]\nname="c"\nprompt="p"\nartifact="A"\ntool="t"\n')
    with pytest.raises(ConfigError, match="front-matter"):
        load_skill(tmp_path)


def test_a_skill_without_cases_is_refused(tmp_path: Path) -> None:
    """Nothing to measure is an error, not an empty pass."""
    (tmp_path / "SKILL.md").write_text("---\nname: s\n---\n")
    with pytest.raises(ConfigError, match=r"cases\.toml"):
        load_skill(tmp_path)


def test_prompt_stays_one_argument() -> None:
    """Substitution after splitting, so a prompt cannot inject flags."""
    assert harness().render(["bin", "-p", "{prompt}"], prompt="a b --rm -rf /") == [
        "bin",
        "-p",
        "a b --rm -rf /",
    ]


def test_environment_is_declared_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing is inherited."""
    monkeypatch.setenv("SOME_DEVELOPER_THING", "leaked")
    assert set(harness(env={}).environment()) == {"PATH"}


def test_missing_env_var_is_named() -> None:
    """Silently dropping a declared variable would change what ran."""
    with pytest.raises(ConfigError, match="DEFINITELY_NOT_SET_XYZ"):
        harness(env={"T": "${DEFINITELY_NOT_SET_XYZ}"}).environment()


def test_matrix_referencing_an_unknown_harness_is_refused(tmp_path: Path) -> None:
    """A typo should say what it was."""
    p = tmp_path / "skeval.toml"
    p.write_text('[harness.a]\nstart=["x"]\nskills="d"\n[[matrix]]\nharness="nope"\nmodels=["m"]\n')
    with pytest.raises(ConfigError, match="nope"):
        load_config(p)


def test_env_override_yields_a_distinct_target() -> None:
    """Pointing a harness at another provider changes what is measured."""
    config = load_config(REPO / "skeval.toml")
    entry = config.matrix[0].model_copy(
        update={"env": {"ANTHROPIC_BASE_URL": "https://x"}, "label": "claude-code/other"}
    )
    config = config.model_copy(update={"matrix": [*config.matrix, entry]})
    labels = [t.label for t in config.targets()]
    assert "claude-code/other/claude-opus-5" in labels


# --- checks ---------------------------------------------------------------


def test_tool_used_matches_arguments_not_only_names(tmp_path: Path) -> None:
    """Tool names differ per harness; the command does not."""
    assert tool_used(convo(tmp_path, [("Bash", {"command": "planctl write"})], []), "planctl").ok


def test_a_denied_call_is_not_a_used_tool(tmp_path: Path) -> None:
    """A tool call is a request, not proof of execution."""
    c = convo(tmp_path, [("Bash", {"command": "planctl write"})], [], denied=["Bash"])
    result = tool_used(c, "planctl")
    assert not result.ok and "denied" in result.reason


def test_an_unrelated_denial_does_not_condemn_an_executed_call(tmp_path: Path) -> None:
    """One denied tool must not fail a different, executed one."""
    c = convo(tmp_path, [("Bash", {"command": "planctl write"})], [], denied=["WebFetch"])
    assert tool_used(c, "planctl").ok


def test_artifact_must_exist_and_be_non_empty(tmp_path: Path) -> None:
    """An empty file is not an artifact."""
    c = convo(tmp_path, [], [])
    assert not artifact_created(c, case()).ok
    (tmp_path / "PLAN.md").write_text("  ")
    assert not artifact_created(c, case()).ok
    (tmp_path / "PLAN.md").write_text("# real")
    assert artifact_created(c, case()).ok


def test_every_expected_artifact_must_appear(tmp_path: Path) -> None:
    """A case may require several files; a missing one is named."""
    spec = case(artifacts=[{"path": "A.md"}, {"path": "B.md"}], artifact=None)
    c = convo(tmp_path, [], [])
    (tmp_path / "A.md").write_text("a")
    result = artifact_created(c, spec)
    assert not result.ok and "B.md was not created" in result.reason
    (tmp_path / "B.md").write_text("b")
    assert artifact_created(c, spec).ok


def test_an_artifact_may_require_content(tmp_path: Path) -> None:
    """Existing is not enough when the case says what must be in it."""
    spec = case(
        artifacts=[{"path": "A.md", "contains": ["billing", "platform-team"]}], artifact=None
    )
    c = convo(tmp_path, [], [])
    (tmp_path / "A.md").write_text("# billing\n")
    result = artifact_created(c, spec)
    assert not result.ok and "lacks platform-team" in result.reason
    (tmp_path / "A.md").write_text("# billing\nOwner: platform-team\n")
    assert artifact_created(c, spec).ok


def test_a_case_expecting_no_artifact_is_unsupported(tmp_path: Path) -> None:
    """Some skills produce no file at all."""
    spec = case(artifacts=[], artifact=None)
    assert artifact_created(convo(tmp_path, [], []), spec).status is Status.UNSUPPORTED


def test_replies_may_land_in_any_expected_artifact(tmp_path: Path) -> None:
    """Which file carries the answer is the skill's business, not ours."""
    spec = case(
        artifacts=[{"path": "A.md"}, {"path": "B.md"}],
        artifact=None,
        answers=[Answer(match=re.compile("owner"), reply="platform-team")],
    )
    (tmp_path / "A.md").write_text("nothing here")
    (tmp_path / "B.md").write_text("Owner: platform-team")
    assert inputs_resolved(convo(tmp_path, [], ["platform-team"]), spec, harness()).ok


def test_inputs_resolved_needs_the_reply_in_the_artifact(tmp_path: Path) -> None:
    """The artifact is the proof, not the transcript."""
    spec = case(answers=[Answer(match=re.compile("owner"), reply="platform-team")])
    c = convo(tmp_path, [], ["platform-team"])
    (tmp_path / "PLAN.md").write_text("Owner: someone-else")
    assert not inputs_resolved(c, spec, harness()).ok
    (tmp_path / "PLAN.md").write_text("Owner: platform-team")
    assert inputs_resolved(c, spec, harness()).ok


def test_asking_without_an_artifact_cannot_prove_use(tmp_path: Path) -> None:
    """It asked and was answered, but nothing shows the answer was used."""
    spec = case(
        artifacts=[],
        artifact=None,
        answers=[Answer(match=re.compile("owner"), reply="platform-team")],
    )
    result = inputs_resolved(convo(tmp_path, [], ["platform-team"]), spec, harness())
    assert result.status is Status.UNSUPPORTED
    assert "nothing to prove" in result.reason


def test_never_asking_fails(tmp_path: Path) -> None:
    """A harness that invents values instead of asking is the measurement."""
    spec = case(answers=[Answer(match=re.compile("owner"), reply="x")])
    result = inputs_resolved(convo(tmp_path, [], []), spec, harness())
    assert result.status is Status.FAIL and "never asked" in result.reason


def test_a_harness_without_resume_is_unsupported(tmp_path: Path) -> None:
    """Never marked down for a capability it does not have."""
    spec = case(answers=[Answer(match=re.compile("owner"), reply="x")])
    result = inputs_resolved(convo(tmp_path, [], []), spec, harness(resume=[]))
    assert result.status is Status.UNSUPPORTED and not result.scored


def test_a_skill_that_never_fired_is_not_scored(tmp_path: Path) -> None:
    """Triggering belongs to skill-creator."""
    results = run_all(convo(tmp_path, [], []), case(), harness(), "write-plan")
    assert all(r.status is Status.NOT_TRIGGERED for r in results)
    assert not any(r.scored for r in results)


def test_a_fired_skill_is_scored(tmp_path: Path) -> None:
    """Activation observed from a runtime call."""
    (tmp_path / "PLAN.md").write_text("# Plan")
    c = convo(tmp_path, [("Skill", {"skill": "write-plan"}), ("Bash", {"command": "planctl"})], [])
    results = run_all(c, case(), harness(), "write-plan")
    assert {r.name for r in results if r.ok} >= {"skill_fired", "tool_used", "artifact_created"}


def test_each_answer_is_supplied_once() -> None:
    """The trigger word survives into later turns."""
    spec = case(answers=[Answer(match=re.compile("(?i)owner"), reply="platform-team")])
    said = "Who is the owner? ... the owner is platform-team"
    assert _match(said, spec, []) == "platform-team"
    assert _match(said, spec, ["platform-team"]) is None


# --- report ---------------------------------------------------------------


def record(status: Status, name: str = "tool_used", target: str = "t") -> RunRecord:
    """A run record carrying one result."""
    from skeval.checks import Result

    return RunRecord(
        target=target,
        model="m",
        case="c",
        run=0,
        results=[Result(name=name, status=status, reason="r")],
    )


def test_scores_separate_scored_from_unscored() -> None:
    """Unsupported and not-triggered stay out of the rate."""
    report = Report(
        skill="s",
        runs=[
            record(Status.PASS),
            record(Status.FAIL),
            record(Status.UNSUPPORTED),
            record(Status.NOT_TRIGGERED),
        ],
    )
    score = report.scores()["t"]["tool_used"]
    assert (score.passed, score.scored) == (1, 2)
    assert score.rate == 0.5
    assert (score.unsupported, score.not_triggered) == (1, 1)


def test_a_dimension_with_nothing_scored_has_no_rate() -> None:
    """No runs supports no claim."""
    report = Report(skill="s", runs=[record(Status.NOT_TRIGGERED)])
    assert report.scores()["t"]["tool_used"].rate is None


def test_report_writes_scores_into_the_artifact(tmp_path: Path) -> None:
    """The JSON is the deliverable, not a rendering of it."""
    report = Report(skill="s", runs=[record(Status.PASS), record(Status.FAIL)])
    payload = json.loads(report.write(tmp_path / "r.json").read_text())
    assert payload["skill"] == "s"
    assert payload["scores"]["t"]["tool_used"]["rate"] == 0.5
    assert len(payload["runs"]) == 2
    assert payload["isolated"] is False


# --- fixtures on disk -----------------------------------------------------


def test_canary_is_a_loadable_skill() -> None:
    """doctor's whole verdict rests on it."""
    canary = load_skill(REPO / "src/skeval/canary")
    assert canary.name == "skeval-canary"
    assert "skeval-ok" in (canary.path / "SKILL.md").read_text()


def test_example_skill_forbids_writing_the_artifact_directly() -> None:
    """The example must exercise the behavior the tool measures."""
    text = (REPO / "examples/write-plan/SKILL.md").read_text()
    assert "planctl write" in text and "Do not create or edit" in text


def test_planctl_writes_and_refuses_to_overwrite(tmp_path: Path) -> None:
    """The deterministic half stays deterministic."""
    import subprocess

    cli = REPO / "examples/write-plan/bin/planctl"
    args = [str(cli), "write", "--title", "T", "--owner", "O", "--dir", str(tmp_path)]
    assert subprocess.run(args, capture_output=True).returncode == 0
    assert "Owner:** O" in (tmp_path / "PLAN.md").read_text()
    assert subprocess.run(args, capture_output=True).returncode == 3


def test_harness_requires_start_and_skills() -> None:
    """Pydantic reports the missing field rather than failing later."""
    with pytest.raises(ValidationError):
        Harness(start=["x"])  # type: ignore[call-arg]


# --- end to end, against a fake harness -----------------------------------

FAKE = REPO / "tests" / "fake"


def _e2e(tmp_path: Path, *extra: str) -> tuple[int, dict[str, Any]]:
    """Run the whole pipeline against the fake harness. No network, no cost."""
    import os
    import subprocess

    tmp_path.mkdir(parents=True, exist_ok=True)
    counter = tmp_path / "count.txt"
    report = tmp_path / "report.json"
    done = subprocess.run(
        [
            "python",
            "-m",
            "pytest",
            str(REPO / "src/skeval/conformance.py"),
            "-m",
            "live",
            "--skeval-config",
            str(FAKE / "skeval.toml"),
            "--skill",
            str(FAKE / "skill"),
            "--repeat",
            "2",
            "--report",
            str(report),
            "-q",
            *extra,
        ],
        cwd=REPO,
        env={**os.environ, "FAKE_COUNTER": str(counter)},
        capture_output=True,
        text=True,
    )
    assert report.is_file(), done.stdout + done.stderr
    invocations = len(counter.read_text().splitlines()) if counter.exists() else 0
    return invocations, json.loads(report.read_text())


def test_end_to_end_runs_each_scenario_once(tmp_path: Path) -> None:
    """Three cases at repeat 2 is six scenarios, not six times four.

    An earlier design put each check in its own test, so pytest invoked the
    harness once per check: four times the money for one measurement.
    """
    invocations, report = _e2e(tmp_path)
    assert len(report["runs"]) == 6
    # Per repeat: 1 turn specified, 2 missing-owner, 3 missing-both.
    assert invocations == 12


def test_a_case_may_ask_for_several_things(tmp_path: Path) -> None:
    """Answers is a list, and one unused match is supplied per turn."""
    _, report = _e2e(tmp_path)
    asked = {r["case"]: r["asked"] for r in report["runs"]}
    turns = {r["case"]: r["turns"] for r in report["runs"]}

    assert asked["missing-both"] == ["platform-team", "billing"]
    assert turns["missing-both"] == 3
    assert asked["missing-owner"] == ["platform-team"]
    assert asked["specified"] == []

    resolved = [
        r
        for r in report["runs"]
        if r["case"] == "missing-both"
        for x in r["results"]
        if x["name"] == "inputs_resolved" and x["status"] == "pass"
    ]
    assert resolved, "both replies must reach the artifact"


def test_end_to_end_scores_every_dimension(tmp_path: Path) -> None:
    """The artifact carries per-run detail and derived scores."""
    _, report = _e2e(tmp_path)
    scores = report["scores"]["fake/m1"]
    assert scores["tool_used"]["rate"] == 1.0
    # Four cases withhold something across two repeats; two withhold nothing.
    assert scores["inputs_resolved"]["scored"] == 4
    assert scores["inputs_resolved"]["unsupported"] == 2


def test_end_to_end_parallel_matches_serial(tmp_path: Path) -> None:
    """Workers shard the report; the controller merges it back."""
    serial_calls, serial = _e2e(tmp_path / "a")
    parallel_calls, parallel = _e2e(tmp_path / "b", "-n", "4")
    assert serial_calls == parallel_calls
    assert len(serial["runs"]) == len(parallel["runs"]) == 6
    assert serial["scores"] == parallel["scores"]


def test_a_case_without_a_tool_is_unsupported_not_failed(tmp_path: Path) -> None:
    """Plenty of skills write the artifact themselves and shell out to nothing.

    Same shape as a harness with no resume: a check that does not apply is
    reported, never counted against the skill.
    """
    spec = case(tool=None)
    result = tool_used(convo(tmp_path, [], []), spec.tool)
    assert result.status is Status.UNSUPPORTED
    assert not result.scored


def test_a_toolless_case_still_scores_the_other_dimensions(tmp_path: Path) -> None:
    """Dropping the tool must not drop the artifact check with it."""
    (tmp_path / "PLAN.md").write_text("# Plan")
    c = convo(
        tmp_path, [("Skill", {"skill": "write-plan"}), ("Write", {"file_path": "PLAN.md"})], []
    )
    results = {r.name: r.status for r in run_all(c, case(tool=None), harness(), "write-plan")}
    assert results["skill_fired"] is Status.PASS
    assert results["artifact_created"] is Status.PASS
    assert results["tool_used"] is Status.UNSUPPORTED
