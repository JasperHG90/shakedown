"""The three checks, plus the precondition that makes them meaningful."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from skeval.models import Case, Harness
from skeval.runner import Conversation


class Status(StrEnum):
    """What a check concluded."""

    PASS = "pass"
    FAIL = "fail"
    UNSUPPORTED = "unsupported"
    NOT_TRIGGERED = "not_triggered"


class Result(BaseModel):
    """One check's verdict."""

    name: str
    status: Status
    reason: str

    @property
    def ok(self) -> bool:
        """Whether this counts as a pass."""
        return self.status is Status.PASS

    @property
    def scored(self) -> bool:
        """Whether this belongs in a pass rate."""
        return self.status in (Status.PASS, Status.FAIL)


def skill_fired(convo: Conversation, harness: Harness, skill_name: str) -> Result:
    """Did the skill activate? If not, the run measured the base model."""
    if convo.skill_fired(harness, skill_name):
        return Result(name="skill_fired", status=Status.PASS, reason=f"{skill_name} activated")
    return Result(
        name="skill_fired",
        status=Status.NOT_TRIGGERED,
        reason=f"{skill_name} never activated; this run measured the base model",
    )


def tool_used(convo: Conversation, needle: str | None) -> Result:
    """Was the CLI invoked, and not denied?

    A tool call in a transcript is a request. A denied command still emits
    the call, so matching the transcript alone reports it as executed.
    """
    if not needle:
        return Result(
            name="tool_used", status=Status.UNSUPPORTED, reason="this case declares no tool"
        )
    calls = convo.called(needle)
    if not calls:
        return Result(
            name="tool_used", status=Status.FAIL, reason=f"no tool call mentions {needle}"
        )
    denied = set(convo.denied())
    if denied and all(c.name in denied for c in calls):
        return Result(
            name="tool_used",
            status=Status.FAIL,
            reason=f"{needle} was requested but denied ({', '.join(sorted(denied))}); "
            "check the harness permission flags",
        )
    return Result(name="tool_used", status=Status.PASS, reason=f"invoked {needle}")


def artifact_created(convo: Conversation, case: Case) -> Result:
    """Did the expected file appear, non-empty?"""
    path = convo.workspace / case.artifact
    if not path.is_file():
        return Result(
            name="artifact_created",
            status=Status.FAIL,
            reason=f"no {case.artifact} in the workspace",
        )
    if not path.read_text().strip():
        return Result(
            name="artifact_created", status=Status.FAIL, reason=f"{case.artifact} is empty"
        )
    return Result(name="artifact_created", status=Status.PASS, reason=f"{case.artifact} written")


def inputs_resolved(convo: Conversation, case: Case, harness: Harness) -> Result:
    """Were withheld inputs requested, and did the answers reach the artifact?

    The artifact is the proof. A reply is supplied only in answer to a
    question, so its presence means the harness asked, accepted, and acted.
    """
    if not case.answers:
        return Result(
            name="inputs_resolved", status=Status.UNSUPPORTED, reason="this case withholds nothing"
        )
    if not harness.supports_resume:
        return Result(
            name="inputs_resolved",
            status=Status.UNSUPPORTED,
            reason=f"{harness.name} declares no resume command",
        )
    if not convo.given:
        return Result(
            name="inputs_resolved",
            status=Status.FAIL,
            reason="the harness never asked, so no reply was supplied",
        )
    path = convo.workspace / case.artifact
    text = path.read_text() if path.is_file() else ""
    if missing := [r for r in convo.given if r not in text]:
        return Result(
            name="inputs_resolved",
            status=Status.FAIL,
            reason=f"replies absent from {case.artifact}: {', '.join(missing)}",
        )
    return Result(
        name="inputs_resolved", status=Status.PASS, reason=f"every reply appears in {case.artifact}"
    )


def run_all(convo: Conversation, case: Case, harness: Harness, skill_name: str) -> list[Result]:
    """The precondition and the three checks."""
    fired = skill_fired(convo, harness, skill_name)
    if fired.status is Status.NOT_TRIGGERED:
        return [
            fired,
            *(
                Result(name=n, status=Status.NOT_TRIGGERED, reason="skill never activated")
                for n in ("tool_used", "artifact_created", "inputs_resolved")
            ),
        ]
    return [
        fired,
        tool_used(convo, case.tool),
        artifact_created(convo, case),
        inputs_resolved(convo, case, harness),
    ]
