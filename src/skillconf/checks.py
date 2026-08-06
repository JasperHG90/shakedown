"""The three checks, plus the precondition that makes them meaningful.

Each returns a Result carrying a reason, because "assertion failed" in CI at
3am costs more than it saves.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skillconf.config import Case, Harness
from skillconf.runner import Conversation


class Status(Enum):
    """What a check concluded."""

    PASS = "pass"
    FAIL = "fail"
    #: The harness cannot physically do this. Never a failure: a harness
    #: must not be marked down for a capability it does not have.
    UNSUPPORTED = "unsupported"
    #: The skill never activated, so this check measured nothing.
    NOT_TRIGGERED = "not_triggered"


@dataclass(frozen=True)
class Result:
    """One check's verdict."""

    name: str
    status: Status
    reason: str

    @property
    def ok(self) -> bool:
        """Return whether this counts as a pass for gating."""
        return self.status is Status.PASS

    @property
    def scored(self) -> bool:
        """Return whether this belongs in a pass rate at all."""
        return self.status in (Status.PASS, Status.FAIL)


def skill_fired(convo: Conversation, harness: Harness, skill_name: str) -> Result:
    """Precondition: did the skill activate at runtime?

    If it never fired, the three checks below measure the base model rather
    than the skill. Triggering belongs to skill-creator; folding a trigger
    problem into a conformance score contaminates both numbers.
    """
    if convo.skill_fired(harness, skill_name):
        return Result("skill_fired", Status.PASS, f"{skill_name} activated")
    return Result(
        "skill_fired",
        Status.NOT_TRIGGERED,
        f"{skill_name} never activated; the run measured the base model, not the skill",
    )


def tool_used(convo: Conversation, needle: str) -> Result:
    """Was the deterministic CLI invoked, rather than imitated or blocked?

    A tool call in a transcript is a REQUEST. A harness that denies it still
    emits the call, so matching the transcript alone reports a command that
    never ran as a command that did. Measured: a run whose only `planctl`
    call came back "This command requires approval" scored a pass here
    while the artifact was never created.
    """
    calls = convo.called(needle)
    if not calls:
        return Result("tool_used", Status.FAIL, f"no tool call mentions {needle}")
    denied = convo.denied()
    if denied and not any(c.name not in denied for c in calls):
        return Result(
            "tool_used",
            Status.FAIL,
            f"{needle} was requested but the harness denied it ({', '.join(sorted(set(denied)))}); "
            "check the permission flags in the harness command",
        )
    return Result("tool_used", Status.PASS, f"invoked {needle}")


def artifact_created(convo: Conversation, case: Case) -> Result:
    """Did the expected file appear, and is it non-empty?"""
    path = convo.workspace / case.artifact
    if not path.is_file():
        return Result("artifact_created", Status.FAIL, f"no {case.artifact} in the workspace")
    if not path.read_text().strip():
        return Result("artifact_created", Status.FAIL, f"{case.artifact} is empty")
    return Result("artifact_created", Status.PASS, f"{case.artifact} written")


def inputs_resolved(convo: Conversation, case: Case, harness: Harness) -> Result:
    """Were the withheld inputs requested, and did the answers get used?

    The proof is the artifact, not the transcript. A reply is supplied only
    in response to a question, so a reply appearing in the artifact means
    the harness asked, accepted the answer, and acted on it. No question
    parsing and no ordering check required: the artifact cannot contain a
    value that was first revealed on turn three.
    """
    if not case.answers:
        return Result("inputs_resolved", Status.UNSUPPORTED, "this case withholds nothing")
    if not harness.supports_resume():
        return Result(
            "inputs_resolved",
            Status.UNSUPPORTED,
            f"{harness.name} declares no resume command, so a reply cannot be delivered",
        )
    if not convo.given:
        return Result(
            "inputs_resolved",
            Status.FAIL,
            "the harness never asked, so no reply was supplied",
        )

    path = convo.workspace / case.artifact
    text = path.read_text() if path.is_file() else ""
    missing = [r for r in convo.given if r not in text]
    if missing:
        return Result(
            "inputs_resolved",
            Status.FAIL,
            f"replies absent from {case.artifact}: {', '.join(missing)}",
        )
    return Result("inputs_resolved", Status.PASS, f"every reply appears in {case.artifact}")


def run_all(
    convo: Conversation, case: Case, harness: Harness, skill_name: str, tool_needle: str
) -> list[Result]:
    """Return the precondition and the three checks.

    When the skill never fired, the three are reported NOT_TRIGGERED rather
    than failed, so a trigger-rate problem cannot masquerade as a
    conformance regression.
    """
    fired = skill_fired(convo, harness, skill_name)
    if fired.status is Status.NOT_TRIGGERED:
        return [
            fired,
            *(
                Result(name, Status.NOT_TRIGGERED, "skill never activated")
                for name in ("tool_used", "artifact_created", "inputs_resolved")
            ),
        ]
    return [
        fired,
        tool_used(convo, tool_needle),
        artifact_created(convo, case),
        inputs_resolved(convo, case, harness),
    ]
