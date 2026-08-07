"""Does this harness qualify? Answered by running it."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from shakedown.models import Answer, Artifact, Case, Harness, Skill
from shakedown.runner import Conversation, converse
from shakedown.sandbox import create

CANARY_DIR = Path(__file__).parent / "canary"
CANARY_NAME = "shakedown-canary"
MARKER = "shakedown-ok"

CANARY_CASE = Case(
    name="canary",
    prompt="Run the canary check.",
    artifacts=[Artifact(path="canary.txt")],
    tool=MARKER,
    answers=[Answer(match=re.compile("(?i)which|what.*name|file name"), reply="canary.txt")],
)


class Check(BaseModel):
    """One prerequisite and whether it held."""

    number: int
    name: str
    ok: bool
    detail: str
    required: bool = True


class Diagnosis(BaseModel):
    """What doctor found, and where to look."""

    harness: str
    checks: list[Check]
    workspace: str

    @property
    def blocking(self) -> list[Check]:
        """Required prerequisites that failed."""
        return [c for c in self.checks if c.required and not c.ok]

    @property
    def degraded(self) -> list[Check]:
        """Optional prerequisites that failed."""
        return [c for c in self.checks if not c.required and not c.ok]

    @property
    def qualifies(self) -> bool:
        """Whether the harness can be measured at all."""
        return not self.blocking

    def verdict(self) -> str:
        """One line saying whether the harness qualifies."""
        if self.blocking:
            return (
                f"[red]does not qualify[/]: blocked on {', '.join(c.name for c in self.blocking)}"
            )
        if self.degraded:
            return "[yellow]qualifies[/] with inputs_resolved unsupported"
        return "[green]qualifies[/]"


#: What each canary turn actually exercises. One conversation settles every
#: prerequisite, so progress is reported per turn rather than per check:
#: claiming to "check prerequisite 3" would describe work that never
#: happens separately.
TURN_LABELS = (
    "running the canary: headless run, skill discovery, output parsing",
    "resuming the session",
)


def diagnose(
    harness: Harness,
    *,
    model: str,
    backend: str = "tmp",
    notify: Callable[[str], None] | None = None,
) -> Diagnosis:
    """Run the canary and report on the prerequisites."""
    skill = Skill(path=CANARY_DIR, name=CANARY_NAME, cases=[CANARY_CASE])
    if notify:
        notify(f"preparing the {backend} sandbox")
    box = create(harness, skill, backend=backend, keep=True)

    def announce(index: int) -> None:
        if notify:
            notify(TURN_LABELS[index] if index < len(TURN_LABELS) else f"turn {index + 1}")

    convo = converse(box, harness, CANARY_CASE, model=model, timeout_s=180.0, notify=announce)
    return Diagnosis(
        harness=harness.name, checks=verdict_on(convo, harness), workspace=str(box.path)
    )


def verdict_on(convo: Conversation, harness: Harness) -> list[Check]:
    """What one canary conversation says about the prerequisites.

    Separate from ``diagnose`` because the reading is worth testing and the
    running costs money.
    """
    first = convo.first

    fired = convo.skill_fired(harness, CANARY_NAME)
    ran_marker = bool(convo.called(MARKER))
    other = [s for s in first.skills_offered if s != CANARY_NAME]

    checks = [
        Check(
            number=1,
            name="headless run",
            ok=first.exit_code == 0 and not first.timed_out,
            detail="timed out" if first.timed_out else f"exit {first.exit_code}",
        ),
        Check(
            number=2,
            name="skill surfaced at runtime",
            ok=fired and ran_marker,
            detail="activated and ran the marker"
            if fired and ran_marker
            else "never activated"
            if not fired
            else f"activated but never ran {MARKER!r}",
        ),
        Check(
            number=3,
            name="output parsed",
            ok=bool(first.tool_calls or first.texts),
            detail=f"{len(first.tool_calls)} tool calls, {len(first.texts)} texts",
        ),
        Check(
            number=4,
            name="session resume",
            ok=len(convo.turns) > 1 or not harness.supports_resume,
            detail=f"{len(convo.turns)} turns",
            required=False,
        ),
        Check(
            number=5,
            name="no TTY required",
            ok=first.exit_code == 0,
            detail="ran without a terminal",
        ),
        Check(
            number=6,
            name="environment visibility",
            ok=True,
            detail="only the skill under test"
            if not other
            else f"{len(other)} other skills visible; built-ins expected",
            required=False,
        ),
    ]
    return checks
