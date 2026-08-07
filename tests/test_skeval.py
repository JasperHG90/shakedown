"""Offline tests. No subprocess, no spend."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from skeval.checks import Result, Status, artifact_created, inputs_resolved, run_all, tool_used
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
from skeval.report import MARKER, Report, RunRecord
from skeval.runner import Conversation, _match

REPO = Path(__file__).resolve().parents[1]
NESTED = Events(container="message.content")
FLAT = Events(name_key="tool_name", args_key="parameters")
GEMINI = Events(
    name_key="tool_name", args_key="parameters", text_marker="message", text_key="content"
)


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


def test_a_flat_harness_echoing_the_prompt_is_not_the_agent_speaking() -> None:
    """Otherwise a prompt mentioning "owner" answers a question never asked."""
    turn = parse(
        [
            {"type": "message", "role": "user", "content": "Write a plan. Owner: platform-team."},
            {"type": "message", "role": "assistant", "content": "What is the title?"},
        ],
        GEMINI,
    )
    assert turn.texts == ["What is the title?"]


def test_a_reply_streamed_in_fragments_stays_one_sentence() -> None:
    """A newline join would split it, and `.` in a pattern does not cross one."""
    turn = parse(
        [
            {"type": "message", "role": "assistant", "content": "What should"},
            {"type": "message", "role": "assistant", "content": " the file be named?"},
        ],
        GEMINI,
    )
    assert re.search(r"(?i)what.*named", turn.said())


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

    # Asserted by shape, not by listing them: harnesses get added, and a
    # hardcoded list turns every addition into an unrelated test failure.
    labels = [t.label for t in config.targets()]
    assert labels, "the matrix must produce at least one target"
    assert len(labels) == len(set(labels)), "a duplicate label averages two runs together"
    for target in config.targets():
        # A label may name a provider rather than the harness: pointing one
        # harness at another backend is the whole point of the override.
        assert target.harness.name in config.harness
        assert target.model
    assert "claude-code" in config.harness

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


def test_markdown_summarizes_a_green_run() -> None:
    """The PR comment leads with the verdict, then the per-target table."""
    report = Report(skill="write-plan", runs=[record(Status.PASS), record(Status.PASS)])
    written = report.markdown()

    assert written.startswith(MARKER), "the marker lets a rerun edit its own comment"
    assert "### skeval: `write-plan`" in written
    assert "**2/2 scenarios passed** (PASS)" in written
    assert "| target | tool_used |" in written
    assert "| t | 100% (2) |" in written
    assert "<details>" not in written, "nothing failed, so there is nothing to fold away"
    assert "not isolated" in written


def test_markdown_names_every_failure() -> None:
    """A red comment has to say which check, on which case, and why."""
    bad = RunRecord(
        target="claude-code/opus",
        model="opus",
        case="missing-owner",
        run=2,
        results=[
            Result(name="tool_used", status=Status.PASS, reason="invoked planctl"),
            Result(
                name="artifact_created", status=Status.FAIL, reason="PLAN.md lacks platform-team"
            ),
        ],
    )
    written = Report(skill="write-plan", runs=[record(Status.PASS), bad]).markdown()

    assert "(FAIL: 1)" in written
    assert "<details><summary>1 failing scenario</summary>" in written
    assert "- **missing-owner** run 2 on `claude-code/opus`" in written
    assert "  - `artifact_created`: PLAN.md lacks platform-team" in written
    assert "`tool_used`: invoked planctl" not in written, "passing checks are not failures"


def test_markdown_refuses_to_imply_a_pass_when_nothing_ran() -> None:
    """Zero rows is a distinct outcome, never a green comment."""
    written = Report(skill="write-plan").markdown()
    assert "No scenarios ran." in written
    assert "passed" not in written


def test_markdown_reports_an_unscored_dimension_as_not_applicable() -> None:
    """A rate needs a denominator, and unsupported gives none."""
    written = Report(skill="s", runs=[record(Status.UNSUPPORTED)]).markdown()
    assert "| t | n/a |" in written


# --- the github action ----------------------------------------------------


ACTION = REPO / ".github" / "actions" / "skeval" / "action.yml"


def action() -> dict[str, Any]:
    """The composite action, parsed."""
    import yaml

    return dict(yaml.safe_load(ACTION.read_text()))


def test_the_action_only_calls_commands_and_flags_that_exist() -> None:
    """The action is CI's entry point, and CI is where a typo is expensive.

    Renaming a command or a flag has to fail here rather than in someone's
    pipeline.
    """
    from typer.testing import CliRunner

    from skeval.cli import app

    step = next(s for s in action()["runs"]["steps"] if s.get("id") == "measure")["run"]

    runner = CliRunner()
    for command in ("run", "summary"):
        assert f"skeval {command}" in step or f"args=({command} " in step
        assert runner.invoke(app, [command, "--help"]).exit_code == 0

    used = set(re.findall(r"--[a-z-]+", step))
    helped = runner.invoke(app, ["run", "--help"]).output
    for flag in used:
        assert flag in helped, f"{flag} is not a flag of `skeval run`"


def test_the_action_installs_from_the_package_root() -> None:
    """The action sits in a subdirectory, so it walks up to find the package.

    Moving either the action or the package silently breaks that walk, and
    the failure would only appear in someone's CI.
    """
    step = next(s for s in action()["runs"]["steps"] if s.get("name") == "Install skeval")["run"]
    walk = re.search(r"GITHUB_ACTION_PATH/((?:\.\./)*\.\.)", step)
    assert walk, "the install step must walk up to the package root"

    resolved = (ACTION.parent / walk.group(1)).resolve()
    assert resolved == REPO.resolve()
    assert (resolved / "pyproject.toml").is_file()


def test_the_documented_uses_path_points_at_the_action() -> None:
    """The docs are where a user copies from, so a stale path breaks everyone."""
    docs = (REPO / "GETTING_STARTED.md").read_text()
    quoted = re.search(r"uses: \S+/(\.github\S*)@", docs)
    assert quoted, "the CI section must show a `uses:` line"
    assert (REPO / quoted.group(1) / "action.yml") == ACTION


def test_the_actions_comment_marker_matches_the_one_it_looks_for() -> None:
    """A drifted marker posts a fresh comment per push instead of editing."""
    script = next(s for s in action()["runs"]["steps"] if "github-script" in s.get("uses", ""))[
        "with"
    ]["script"]
    assert f"'{MARKER}'" in script
    assert Report(skill="s").markdown().startswith(MARKER)


def test_the_action_reports_even_when_the_matrix_fails() -> None:
    """A red run is exactly when the numbers are worth reading."""
    steps = {s.get("name", ""): s for s in action()["runs"]["steps"]}
    assert "always()" in steps["Upload the report"]["if"]
    assert "always()" in steps["Comment on the pull request"]["if"]
    # The failure is re-raised at the end rather than aborting the step.
    assert "always()" in steps["Fail if the matrix failed"]["if"]
    assert "exit-code" in steps["Fail if the matrix failed"]["if"]


# --- fixtures on disk -----------------------------------------------------


def test_the_add_harness_skill_documents_a_config_that_loads(tmp_path: Path) -> None:
    """A skill that teaches an invalid config is worse than no skill.

    The example block is extracted and loaded, so a renamed or removed
    field breaks this test rather than someone's afternoon.
    """
    skill = REPO / "skills" / "add-harness" / "SKILL.md"
    blocks = re.findall(r"```toml\n(.*?)```", skill.read_text(), re.DOTALL)
    assert blocks, "the skill must show a config"

    written = tmp_path / "skeval.toml"
    written.write_text(blocks[0])
    loaded = load_config(written)

    built = loaded.harness["my-harness"]
    assert built.start[0] == "my-agent"
    assert "{prompt}" in built.start
    assert built.supports_resume
    assert built.skills == ".my-agent/skills"
    assert [t.label for t in loaded.targets()] == ["my-harness/some-model"]
    # env is a reference, never a literal secret.
    assert built.env == {"MY_AGENT_TOKEN": "${MY_AGENT_TOKEN}"}


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


def test_init_scaffolds_something_skeval_can_actually_load(tmp_path: Path) -> None:
    """A scaffold that does not parse is worse than no scaffold."""
    from skeval.scaffold import scaffold

    written = scaffold(tmp_path / "my-skill", tmp_path / "skeval.toml")
    assert len(written) == 4

    loaded = load_config(tmp_path / "skeval.toml")
    assert "claude-code" in loaded.harness
    assert [t.label for t in loaded.targets()] == ["claude-code/claude-opus-5"]

    built = load_skill(tmp_path / "my-skill")
    assert built.name == "my-skill"
    assert [c.name for c in built.cases] == ["fully-specified", "missing-author"]
    # The withheld fact drives every dimension: it must be asked for, it must
    # reach the artifact, and the artifact must come from the CLI.
    withheld = built.cases[1]
    assert withheld.answers[0].reply == "platform-team"
    assert withheld.answers[0].match.search("Who is the author?")
    assert withheld.tool == "notectl"
    assert withheld.artifacts[0].path == "NOTE.md"


def test_the_scaffolded_cli_writes_the_artifact(tmp_path: Path) -> None:
    """The deterministic half has to work, or every case fails on setup."""
    import subprocess

    from skeval.scaffold import scaffold

    scaffold(tmp_path / "my-skill", tmp_path / "skeval.toml")
    done = subprocess.run(
        [
            str(tmp_path / "my-skill" / "bin" / "notectl"),
            "write",
            "--subject",
            "Q4 rollout",
            "--author",
            "platform-team",
            "--dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    written = (tmp_path / "NOTE.md").read_text()
    assert "Q4 rollout" in written
    assert "platform-team" in written


def test_init_refuses_to_overwrite(tmp_path: Path) -> None:
    """Refuse rather than guess: a scaffold must never eat existing work."""
    from skeval.scaffold import scaffold

    scaffold(tmp_path / "my-skill", tmp_path / "skeval.toml")
    (tmp_path / "my-skill" / "SKILL.md").write_text("mine")

    with pytest.raises(FileExistsError, match=r"SKILL\.md"):
        scaffold(tmp_path / "my-skill", tmp_path / "skeval.toml")
    assert (tmp_path / "my-skill" / "SKILL.md").read_text() == "mine"


def test_a_harness_declares_one_environment_not_two() -> None:
    """An image is pulled and a dockerfile is built. Both is a contradiction."""
    with pytest.raises(ValidationError, match="not both"):
        Harness(
            start=["x"],
            skills=".s",
            image="python:3.12-slim",
            dockerfile="fake.Dockerfile",
        )


def test_a_removed_config_key_is_refused_rather_than_ignored(tmp_path: Path) -> None:
    """`install` used to exist. Silently dropping it would look like it worked."""
    written = tmp_path / "skeval.toml"
    written.write_text(
        '[harness.h]\nstart = ["x"]\nskills = ".s"\n'
        'install = "npm i -g something"\n\n'
        '[[matrix]]\nharness = "h"\nmodels = ["m"]\n'
    )
    with pytest.raises(ConfigError, match="install"):
        load_config(written)


def test_a_dockerfile_that_is_not_there_fails_at_load(tmp_path: Path) -> None:
    """Better than a build error deep inside the first scenario."""
    written = tmp_path / "skeval.toml"
    written.write_text(
        '[harness.h]\nstart = ["x"]\nskills = ".s"\n'
        'dockerfile = "nope.Dockerfile"\n\n'
        '[[matrix]]\nharness = "h"\nmodels = ["m"]\n'
    )
    with pytest.raises(ConfigError, match="no dockerfile at"):
        load_config(written)


def test_a_dockerfile_path_is_relative_to_the_config() -> None:
    """CI runs from the repo root while the config may live elsewhere."""
    loaded = load_config(FAKE / "container-dockerfile.toml")
    resolved = Path(loaded.harness["fake"].dockerfile)
    assert resolved.is_absolute()
    assert resolved == (FAKE / "fake.Dockerfile").resolve()


# --- end to end, against a fake harness -----------------------------------

FAKE = REPO / "tests" / "fake"


def _e2e(tmp_path: Path, *extra: str, skill: Path = FAKE / "skill") -> tuple[int, dict[str, Any]]:
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
            str(skill),
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
    (tmp_path / "stdout.txt").write_text(done.stdout)
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


def test_a_green_run_still_prints_its_scores(tmp_path: Path) -> None:
    """Rendering from the fixture teardown put it inside pytest's capture,
    so a passing run printed nothing and only failures showed a table."""
    _e2e(tmp_path)
    printed = (tmp_path / "stdout.txt").read_text()
    assert "skeval" in printed
    assert "tool_used" in printed, "the scores table must survive a green run"
    assert "report:" in printed


def test_a_non_interactive_run_prints_no_spinner(tmp_path: Path) -> None:
    """CI has no terminal to animate, and a log full of frames helps nobody."""
    _e2e(tmp_path)
    printed = (tmp_path / "stdout.txt").read_text()
    assert not set(printed) & set("\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f")
    # The status character pytest writes per test survives when no spinner
    # is competing for the line.
    assert "100%" in printed


def test_the_report_carries_enough_to_debug_a_run(tmp_path: Path) -> None:
    """Scores say a run failed. Detail says what the harness actually did."""
    _, report = _e2e(tmp_path)
    run = next(r for r in report["runs"] if r["case"] == "missing-owner")

    assert run["prompt"]
    assert run["duration_s"] > 0
    assert len(run["detail"]) == run["turns"]

    first = run["detail"][0]
    assert first["argv"][0].endswith("agent"), "the exact command is recoverable"
    assert first["exit_code"] == 0
    assert any(c["name"] == "Skill" for c in first["tool_calls"])
    assert report["summary"]["runs"] == len(report["runs"])
    assert report["summary"]["failures"] == []


def test_a_failing_run_names_what_failed_and_keeps_the_evidence(tmp_path: Path) -> None:
    """A red run is only useful if it says which check, why, and where."""
    skill = tmp_path / "skill"
    shutil.copytree(FAKE / "skill", skill)
    (skill / "cases.toml").write_text(
        "[[case]]\n"
        'name = "doomed"\n'
        'prompt = "Write a plan. owner: platform-team. title: billing."\n'
        'tool = "notatool"\n'
        "\n[[case.artifacts]]\n"
        'path = "OUT.md"\n'
        'contains = ["never written"]\n'
    )
    _, report = _e2e(tmp_path / "out", skill=skill)

    summary = report["summary"]
    assert (summary["runs"], summary["ok"], summary["failed"]) == (2, 0, 2)

    failure = summary["failures"][0]
    assert failure["case"] == "doomed"
    assert failure["failed"] == ["tool_used", "artifact_created"]
    assert "notatool" in failure["reasons"][0]
    assert "never written" in failure["reasons"][1]

    # The workspace survives a failure, and the stream it names is on disk.
    assert Path(failure["workspace"]).is_dir()
    assert all(Path(s).is_file() for s in failure["streams"])

    run = report["runs"][0]
    assert run["ok"] is False
    assert run["workspace_kept"] is True
    assert run["detail"][0]["tool_calls"], "the calls it did make are recorded"


def test_end_to_end_parallel_matches_serial(tmp_path: Path) -> None:
    """Workers shard the report; the controller merges it back."""
    serial_calls, serial = _e2e(tmp_path / "a")
    parallel_calls, parallel = _e2e(tmp_path / "b", "-n", "4")
    assert serial_calls == parallel_calls
    assert len(serial["runs"]) == len(parallel["runs"]) == 6
    assert serial["scores"] == parallel["scores"]


def test_shards_from_an_interrupted_run_are_not_counted(tmp_path: Path) -> None:
    """Otherwise a killed run's numbers reappear inside the next one's."""
    where = tmp_path / "a"
    where.mkdir(parents=True)
    stale = (where / "report.json").with_suffix(".shards")
    stale.mkdir()
    (stale / "gw99.json").write_text(
        Report(skill="ghost", sandbox="tmp", isolated=False)
        .model_copy(
            update={
                "runs": [
                    RunRecord(
                        target="t",
                        model="m",
                        case="ghost-case",
                        run=0,
                        prompt="p",
                        turns=1,
                        results=[Result(name="skill_fired", status=Status.PASS, reason="r")],
                    )
                ]
            }
        )
        .model_dump_json()
    )

    _, report = _e2e(where, "-n", "4")
    assert len(report["runs"]) == 6
    assert "ghost-case" not in {r["case"] for r in report["runs"]}


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


# --- the container backend ------------------------------------------------


def _docker_available() -> bool:
    import shutil
    import subprocess

    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


needs_docker = pytest.mark.skipif(not _docker_available(), reason="docker is not available")


@needs_docker
@pytest.mark.parametrize("config", ["container.toml", "container-dockerfile.toml"])
def test_container_backend_runs_and_isolates(tmp_path: Path, config: str) -> None:
    """The container backend executes a real conversation and reports isolated.

    Run twice: once against a pulled `image`, once against a built
    `dockerfile`. Both must reach the same place, since they are two ways of
    declaring one environment.

    Uses the fake harness, so this costs nothing and needs no credentials.
    A real harness additionally needs its CLI in the image and credentials
    passed as env: OAuth tokens on the host are not visible inside.
    """
    import os
    import subprocess

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
            str(FAKE / config),
            "--skill",
            str(FAKE / "skill"),
            "--sandbox",
            "container",
            "--report",
            str(report),
            "-q",
        ],
        cwd=REPO,
        env={**os.environ, "FAKE_COUNTER": "/work/count.txt"},
        capture_output=True,
        text=True,
    )
    assert report.is_file(), done.stdout + done.stderr

    payload = json.loads(report.read_text())
    assert payload["sandbox"] == "container"
    assert payload["isolated"] is True
    assert len(payload["runs"]) == 3

    # Multi-turn resume must work inside the container, not only on the host.
    turns = {r["case"]: r["turns"] for r in payload["runs"]}
    assert turns["missing-both"] == 3
    assert {r["name"]: r["status"] for r in payload["runs"][0]["results"]}["skill_fired"] == "pass"


def test_the_answers_are_not_seeded_with_the_skill(tmp_path: Path) -> None:
    """`cases.toml` holds the replies and the expected strings.

    A model that reads it can satisfy `inputs_resolved` without ever being
    asked, which is the one thing that check claims to prove.
    """
    from skeval.sandbox import TempSandbox

    box = TempSandbox(harness(skills=".x/skills"))
    try:
        box.seed(harness(skills=".x/skills"), load_skill(REPO / "examples/scaffold-service"))
        seeded = box.path / ".x/skills/scaffold-service"
        assert (seeded / "SKILL.md").is_file(), "the skill itself still has to arrive"
        assert not (seeded / "cases.toml").exists()
        assert not (seeded / "README.md").exists()
        assert (box.path / "bin/scaffoldctl").is_file()
    finally:
        box.cleanup()


@needs_docker
def test_the_container_separates_stdout_from_stderr(tmp_path: Path) -> None:
    """Merged streams put a warning inside the JSON and the parse fails."""
    from skeval.sandbox import create

    box = create(
        load_config(FAKE / "container.toml").harness["fake"],
        load_skill(FAKE / "skill"),
        backend="container",
    )
    try:
        _, out, err = box.exec(["sh", "-c", "echo the-stream; echo a-warning >&2"], {}, 60.0)
    finally:
        box.cleanup()

    assert out.strip() == "the-stream"
    assert "a-warning" in err
    assert "a-warning" not in out, "a warning in the stream makes it unparseable"


@needs_docker
def test_the_container_does_not_inherit_the_host_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """`HOME = "${HOME}"` expands to a path the image does not have."""
    from skeval.sandbox import WORK, create

    monkeypatch.setenv("FAKE_COUNTER", "/work/count.txt")
    declared = load_config(FAKE / "container.toml").harness["fake"]
    box = create(declared, load_skill(FAKE / "skill"), backend="container")
    try:
        leaky = {**declared.environment(), "HOME": "/Users/nobody"}
        _, out, _ = box.exec(["sh", "-c", "echo HOME=$HOME; ls -d $HOME"], leaky, 60.0)
    finally:
        box.cleanup()

    assert f"HOME={WORK}" in out, out
    assert "/Users/nobody" not in out, out


@needs_docker
def test_the_container_keeps_its_own_path_and_finds_the_seeded_bin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The host's PATH names directories the image does not have.

    Exporting it would also shadow the seeded ``bin/``, because one
    ``export`` takes the last assignment for a name. The other container
    test cannot catch that: its config invokes the harness by absolute
    path, so PATH never has to be right.
    """
    from skeval.sandbox import create

    monkeypatch.setenv("FAKE_COUNTER", "/work/count.txt")
    harness_under_test = load_config(FAKE / "container.toml").harness["fake"]
    box = create(harness_under_test, load_skill(FAKE / "skill"), backend="container")
    try:
        leaky = {**harness_under_test.environment(), "PATH": "/host-only-does-not-exist"}
        _, out, _ = box.exec(["sh", "-c", "command -v agent; echo PATH=$PATH"], leaky, 60.0)
    finally:
        box.cleanup()

    assert "/work/bin/agent" in out, out
    assert "/host-only-does-not-exist" not in out, out
    assert "/usr/bin" in out, "the image's own PATH survived"


@pytest.mark.parametrize("width", [1, 8, 14, 16, 17, 18, 40, 56, 80, 120, 200])
def test_the_banner_never_wraps_onto_the_logo(width: int) -> None:
    """A wrapped status line would land on top of the mark beside it.

    Measured in cells, which is what a terminal wraps on.
    """
    from rich.cells import cell_len

    from skeval.banner import banner

    for line in banner(width).plain.splitlines():
        assert cell_len(line) <= width, line


def test_a_wide_character_path_is_measured_in_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CJK path is half as many characters as columns, and would wrap."""
    from rich.cells import cell_len

    from skeval.banner import banner

    wide = tmp_path / ("日本語のディレクトリ" * 3)
    wide.mkdir()
    monkeypatch.chdir(wide)

    for line in banner(80).plain.splitlines():
        assert cell_len(line) <= 80, line


def test_the_banner_survives_a_deleted_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build step that removes the directory you are in must not crash skeval."""
    import os

    from skeval.banner import banner

    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    os.rmdir(gone)

    assert "skeval v" in banner(80).plain


def test_a_broken_config_is_not_reported_as_a_missing_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`skeval init` is the wrong advice when the config exists but will not load."""
    from skeval.banner import banner

    (tmp_path / "skeval.toml").write_text("this is not toml [[[\n")
    monkeypatch.chdir(tmp_path)

    shown = banner(200).plain
    assert "no skeval.toml" not in shown
    assert "not loadable" in shown


def test_the_banner_shows_the_version_the_tagline_and_where_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the banner is answering "what am I about to run, and where"."""
    from skeval.banner import banner, version

    monkeypatch.chdir(tmp_path)
    shown = banner(200).plain

    assert f"skeval v{version()}" in shown
    assert "Harness conformance testing for agent skills." in shown
    # No config here, so the banner has to say so rather than stay silent.
    assert "no skeval.toml" in shown
    assert str(tmp_path) in shown


def test_the_banner_counts_the_matrix_it_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """From a configured directory it reports the config, not the missing one."""
    from skeval.banner import banner

    monkeypatch.chdir(FAKE)
    shown = banner(200).plain
    assert "no skeval.toml" not in shown
    assert "skeval.toml" in shown
    assert "harness" in shown and "target" in shown


def test_the_banner_stays_out_of_a_pipe() -> None:
    """Redirected output is read by a script or a log; block art is noise there."""
    from rich.console import Console

    from skeval.banner import print_banner

    piped = Console(force_terminal=False, width=100)
    with piped.capture() as capture:
        print_banner(piped)
    assert capture.get() == ""

    terminal = Console(force_terminal=True, width=100)
    with terminal.capture() as capture:
        print_banner(terminal)
    assert "skeval v" in capture.get()


def test_a_bare_skeval_prints_the_help_and_succeeds() -> None:
    """`skeval` with no arguments is a question, not a mistake."""
    from typer.testing import CliRunner

    from skeval.cli import app

    # The real entrypoint takes its name from argv[0]; CliRunner would call
    # the root group "root" unless told what it is invoked as.
    done = CliRunner().invoke(app, [], prog_name="skeval")
    assert done.exit_code == 0
    assert "Usage: skeval" in done.output
    for command in ("run", "init", "summary", "doctor"):
        assert command in done.output


def test_a_bare_skeval_leads_with_the_banner_in_a_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The banner is the point of a bare `skeval`, so pin it to the command.

    CliRunner's stdout is a pipe, so without forcing a terminal the banner
    suppresses itself and this command has no test at all.
    """
    from rich.console import Console
    from typer.testing import CliRunner

    from skeval import cli

    monkeypatch.setattr(cli, "console", Console(force_terminal=True, width=100))
    output = CliRunner().invoke(cli.app, [], prog_name="skeval").output
    assert "skeval v" in output
    assert output.index("skeval v") < output.index("Usage: skeval")


def test_version_prints_just_the_version() -> None:
    """A version flag feeds a script, so it prints the number and nothing else."""
    from typer.testing import CliRunner

    from skeval.banner import version
    from skeval.cli import app

    done = CliRunner().invoke(app, ["--version"])
    assert done.exit_code == 0
    assert done.output.strip() == version()
