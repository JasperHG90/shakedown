"""Offline tests. No subprocess, no spend, so this is a real gate."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from skillconf.checks import Status, artifact_created, inputs_resolved, run_all, tool_used
from skillconf.config import Answer, Case, ConfigError, Events, Harness, load
from skillconf.events import StreamError, parse, read
from skillconf.runner import Conversation
from skillconf.sandbox import create

REPO = Path(__file__).resolve().parents[1]

NESTED = Events(container="message.content")
FLAT = Events(name_key="tool_name", args_key="parameters")


def harness(**kw: object) -> Harness:
    """Return a harness with sensible defaults."""
    base: dict[str, object] = {
        "name": "h",
        "start": "bin -p {prompt}",
        "resume": "bin -p {reply} --resume {sid}",
        "skill_dest": ".x/skills/{name}",
        "events": NESTED,
        "tools": {},
    }
    base.update(kw)
    return Harness(**base)  # type: ignore[arg-type]


def convo(
    workspace: Path, calls: list[tuple[str, dict[str, str]]], given: list[str]
) -> Conversation:
    """Return a conversation carrying the given tool calls."""
    from skillconf.events import ToolCall, Turn

    turn = Turn(tool_calls=[ToolCall(n, a) for n, a in calls])
    return Conversation(turns=[turn], given=given, workspace=workspace)


# --- events ---------------------------------------------------------------


def test_nested_and_flat_shapes_yield_the_same_call() -> None:
    """One optional descent covers both known harnesses.

    Same information, different depth and different key names. If these
    diverge, every downstream check becomes harness-specific.
    """
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


def test_one_record_carrying_several_calls_yields_several() -> None:
    """Cardinality is not cosmetic.

    A harness batches parallel calls into one record. Counting records
    instead of blocks under-reports, and a check that depends on ordering
    then reads the run backwards.
    """
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


def test_text_blocks_are_collected() -> None:
    """Assistant text is what an answer pattern matches against."""
    turn = parse(
        [{"type": "assistant", "message": {"content": [{"type": "text", "text": "Who owns it?"}]}}],
        NESTED,
    )
    assert "Who owns it?" in turn.said()


def test_skills_offered_is_captured() -> None:
    """Runtime visibility, which a static inventory cannot prove."""
    turn = parse([{"type": "system", "subtype": "init", "skills": ["write-plan", "debug"]}], NESTED)
    assert "write-plan" in turn.skills_offered


def test_truncated_stream_raises(tmp_path: Path) -> None:
    """A partial result is worse than none, because it gets scored."""
    bad = tmp_path / "s.jsonl"
    bad.write_text('{"type": "assistant"}\n{"type": "assi')
    with pytest.raises(StreamError):
        read(bad)


# --- config ---------------------------------------------------------------


def test_shipped_config_loads() -> None:
    """The config in the repo is valid."""
    config = load(REPO / "skillconf.toml")
    assert config.skill_name == "write-plan"
    assert config.targets and config.cases


def test_prompt_stays_one_argument() -> None:
    """Substitution happens after splitting, so a prompt cannot inject flags."""
    argv = harness().render("bin -p {prompt}", prompt="a b --rm -rf /")
    assert argv == ["bin", "-p", "a b --rm -rf /"]


def test_missing_env_var_fails_loudly() -> None:
    """Silently dropping a declared variable would change what ran."""
    h = harness(env={"TOKEN": "${DEFINITELY_NOT_SET_XYZ}"})
    with pytest.raises(ConfigError, match="DEFINITELY_NOT_SET_XYZ"):
        h.environment()


def test_environment_is_declared_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing is inherited. A leaked variable is a leaked configuration."""
    monkeypatch.setenv("SOME_DEVELOPER_THING", "leaked")
    env = harness(env={}).environment()
    assert "SOME_DEVELOPER_THING" not in env
    assert set(env) == {"PATH"}


def test_unknown_harness_in_matrix_is_named(tmp_path: Path) -> None:
    """A typo should say what it was."""
    p = tmp_path / "skillconf.toml"
    p.write_text(
        '[skill]\npath="."\nname="s"\n'
        '[harness.a]\nstart="x"\nskills={dest="d/{name}"}\n'
        '[[matrix]]\nharness="nope"\nmodels=["m"]\n'
        '[[case]]\nprompt="p"\nartifact="A"\n'
    )
    with pytest.raises(ConfigError, match="nope"):
        load(p)


# --- sandbox --------------------------------------------------------------


def test_sandbox_seeds_the_skill_where_the_harness_looks(tmp_path: Path) -> None:
    """Copy into the discovery path, not a load-from-here flag."""
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: s\n---\n")
    box = create(harness(), skill, "s", keep=True)
    assert (box.path / ".x/skills/s/SKILL.md").is_file()
    box.keep = False
    box.cleanup()


def test_sandbox_copies_the_bin_directory(tmp_path: Path) -> None:
    """The agent must resolve the CLI by name, as a user would."""
    skill, binsrc = tmp_path / "skill", tmp_path / "bin"
    skill.mkdir()
    binsrc.mkdir()
    (skill / "SKILL.md").write_text("x")
    (binsrc / "planctl").write_text("#!/bin/sh\n")
    box = create(harness(), skill, "s", bin_dir=binsrc, keep=True)
    assert (box.path / "bin" / "planctl").is_file()
    box.keep = False
    box.cleanup()


# --- checks ---------------------------------------------------------------


def test_tool_used_matches_arguments_not_only_names(tmp_path: Path) -> None:
    """Tool names differ per harness; the command does not."""
    c = convo(tmp_path, [("Bash", {"command": "planctl write --title x"})], [])
    assert tool_used(c, "planctl").ok


def test_tool_used_fails_when_the_cli_was_never_invoked(tmp_path: Path) -> None:
    """Writing the artifact by hand must not pass."""
    c = convo(tmp_path, [("Write", {"file_path": "PLAN.md"})], [])
    assert not tool_used(c, "planctl").ok


def test_artifact_must_exist_and_be_non_empty(tmp_path: Path) -> None:
    """An empty file is not an artifact."""
    case = Case(name="c", prompt="p", artifact="PLAN.md")
    c = convo(tmp_path, [], [])
    assert not artifact_created(c, case).ok
    (tmp_path / "PLAN.md").write_text("   ")
    assert not artifact_created(c, case).ok
    (tmp_path / "PLAN.md").write_text("# real")
    assert artifact_created(c, case).ok


def test_inputs_resolved_needs_the_reply_in_the_artifact(tmp_path: Path) -> None:
    """The artifact is the proof, not the transcript.

    A reply is supplied only in answer to a question, so its presence in
    the artifact means the harness asked, accepted, and acted.
    """
    case = Case("c", "p", "PLAN.md", (Answer(re.compile("owner"), "platform-team"),))
    c = convo(tmp_path, [], ["platform-team"])

    (tmp_path / "PLAN.md").write_text("# Plan\nOwner: someone-else\n")
    assert not inputs_resolved(c, case, harness()).ok

    (tmp_path / "PLAN.md").write_text("# Plan\nOwner: platform-team\n")
    assert inputs_resolved(c, case, harness()).ok


def test_never_asking_fails_rather_than_erroring(tmp_path: Path) -> None:
    """A harness that invents values instead of asking is the measurement."""
    case = Case("c", "p", "PLAN.md", (Answer(re.compile("owner"), "platform-team"),))
    result = inputs_resolved(convo(tmp_path, [], []), case, harness())
    assert result.status is Status.FAIL
    assert "never asked" in result.reason


def test_a_harness_without_resume_is_unsupported_not_failed(tmp_path: Path) -> None:
    """A harness is never marked down for a capability it does not have."""
    case = Case("c", "p", "PLAN.md", (Answer(re.compile("owner"), "x"),))
    result = inputs_resolved(convo(tmp_path, [], []), case, harness(resume=""))
    assert result.status is Status.UNSUPPORTED
    assert not result.scored


def test_a_skill_that_never_fired_is_not_triggered_not_failed(tmp_path: Path) -> None:
    """Triggering belongs to skill-creator.

    Folding a trigger-rate problem into a conformance score contaminates
    both numbers, so every check reports NOT_TRIGGERED and none is scored.
    """
    case = Case("c", "p", "PLAN.md")
    results = run_all(convo(tmp_path, [], []), case, harness(), "write-plan", "planctl")
    assert all(r.status is Status.NOT_TRIGGERED for r in results)
    assert not any(r.scored for r in results)


def test_a_fired_skill_is_scored_normally(tmp_path: Path) -> None:
    """Activation is observed from a runtime call, not a static inventory."""
    case = Case("c", "p", "PLAN.md")
    (tmp_path / "PLAN.md").write_text("# Plan")
    c = convo(
        tmp_path,
        [("Skill", {"skill": "write-plan"}), ("Bash", {"command": "planctl write"})],
        [],
    )
    results = run_all(c, case, harness(), "write-plan", "planctl")
    assert {r.name for r in results if r.ok} >= {"skill_fired", "tool_used", "artifact_created"}


# --- fixtures on disk -----------------------------------------------------


def test_canary_skill_is_well_formed() -> None:
    """doctor's whole verdict rests on this file."""
    text = (REPO / "src/skillconf/canary/SKILL.md").read_text()
    assert "skillconf-ok" in text
    assert text.startswith("---")


def test_example_skill_forbids_writing_the_artifact_directly() -> None:
    """The example must exercise the behavior the tool measures."""
    text = (REPO / "examples/write-plan/skill/SKILL.md").read_text()
    assert "planctl write" in text
    assert "Do not create or edit" in text


def test_planctl_writes_and_refuses_to_overwrite(tmp_path: Path) -> None:
    """The deterministic half stays deterministic."""
    import subprocess

    cli = REPO / "examples/write-plan/bin/planctl"
    args = [str(cli), "write", "--title", "T", "--owner", "O", "--dir", str(tmp_path)]
    assert subprocess.run(args, capture_output=True).returncode == 0
    assert "Owner:** O" in (tmp_path / "PLAN.md").read_text()
    assert subprocess.run(args, capture_output=True).returncode == 3


def test_config_template_matches_the_shipped_config() -> None:
    """`skillconf init` must scaffold something that actually loads."""
    shipped = (REPO / "skillconf.toml").read_text()
    template = (REPO / "src/skillconf/templates/skillconf.toml").read_text()
    assert json.dumps(shipped) == json.dumps(template)


def test_a_denied_call_is_not_a_used_tool(tmp_path: Path) -> None:
    """A tool call is a request, not proof of execution.

    Found live: `--permission-mode acceptEdits` auto-approves edits but not
    Bash, so `planctl write` appeared in the transcript, came back "This
    command requires approval", and never ran. tool_used passed while the
    artifact was never created.
    """
    from skillconf.events import ToolCall, Turn

    turn = Turn(
        tool_calls=[ToolCall("Bash", {"command": "planctl write --title x"})],
        denied=["Bash"],
    )
    c = Conversation(turns=[turn], workspace=tmp_path)
    result = tool_used(c, "planctl")
    assert not result.ok
    assert "denied" in result.reason


def test_an_allowed_call_alongside_a_denial_still_passes(tmp_path: Path) -> None:
    """One denied tool must not condemn a different, executed one."""
    from skillconf.events import ToolCall, Turn

    turn = Turn(
        tool_calls=[ToolCall("Bash", {"command": "planctl write"})],
        denied=["WebFetch"],
    )
    assert tool_used(Conversation(turns=[turn], workspace=tmp_path), "planctl").ok


def test_denials_are_parsed_from_the_stream() -> None:
    """The harness reports them structurally; use that, not prose matching."""
    turn = parse([{"type": "result", "permission_denials": [{"tool_name": "Bash"}]}], NESTED)
    assert turn.denied == ["Bash"]


def test_each_answer_is_supplied_at_most_once() -> None:
    """Otherwise the loop re-answers until the turn cap, burning real money.

    Found live: the trigger word survives into later turns ("the owner is
    platform-team"), so a naive match replied five times to one question.
    """
    from skillconf.runner import _match

    case = Case("c", "p", "A", (Answer(re.compile("(?i)owner"), "platform-team"),))
    said = "Who is the owner? ... the owner is platform-team"
    assert _match(said, case, already=[]) == "platform-team"
    assert _match(said, case, already=["platform-team"]) is None
