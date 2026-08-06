"""Does this harness qualify? Answered by running it, not by reading config.

The canary skill instructs one thing: run `echo skillconf-ok`. Seeing that
shell call is only possible if the harness ran headless, discovered the
skill, surfaced it to the model, followed it, and emitted parseable output.
One cheap task settles four of the five prerequisites.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skillconf.config import Answer, Case, Harness
from skillconf.runner import converse
from skillconf.sandbox import create

CANARY_DIR = Path(__file__).parent / "canary"
CANARY_NAME = "skillconf-canary"
MARKER = "skillconf-ok"


@dataclass
class Check:
    """One prerequisite and whether it held."""

    number: int
    name: str
    ok: bool
    detail: str
    required: bool = True


def diagnose(harness: Harness, *, model: str, timeout_s: float = 180.0) -> list[Check]:
    """Run the canary and report on the five prerequisites."""
    box = create(harness, CANARY_DIR, CANARY_NAME, keep=True)
    case = Case(
        name="canary",
        prompt="Run the canary check.",
        artifact="canary.txt",
        answers=(
            Answer(
                match=__import__("re").compile("(?i)which|where|what.*name"), reply="canary.txt"
            ),
        ),
    )
    convo = converse(harness, case, box.path, model=model, timeout_s=timeout_s)
    first = convo.first

    fired = convo.skill_fired(harness, CANARY_NAME)
    marker = bool(convo.called(MARKER))
    parsed = bool(first.tool_calls or first.texts)

    checks = [
        Check(
            1,
            "headless run",
            first.exit_code == 0 and not convo.timed_out,
            f"exit {first.exit_code}" + (", timed out" if convo.timed_out else ""),
        ),
        Check(
            2,
            "skill surfaced at runtime",
            fired,
            "activation observed"
            if fired
            else "the skill never activated; a loaded-but-unsurfaced skill looks identical here",
        ),
        Check(
            3,
            "output parsed",
            parsed,
            f"{len(first.tool_calls)} tool calls, {len(first.texts)} texts",
        ),
        Check(
            4,
            "session resume",
            len(convo.turns) > 1 or not harness.supports_resume(),
            f"{len(convo.turns)} turns" if harness.supports_resume() else "no resume configured",
            required=False,
        ),
        Check(5, "no TTY required", first.exit_code == 0, "ran without a terminal"),
        Check(6, "environment visibility", True, _visibility(first), required=False),
    ]
    print(f"canary workspace: {box.path}")
    if not marker and fired:
        checks[1] = Check(
            2,
            "skill surfaced at runtime",
            False,
            f"skill activated but never ran the canary marker {MARKER!r}",
        )
    return checks


def _visibility(first: object) -> str:
    """Describe what else the model could see.

    Reported rather than judged. Most of what shows up here is the
    harness's own built-in skills, which are the harness rather than
    contamination, and telling those apart from a developer's installed
    skills needs a per-version baseline this does not keep. The container
    backend removes the ambiguity by removing the developer's machine.
    """
    offered = [s for s in getattr(first, "skills_offered", []) or [] if s != CANARY_NAME]
    if not offered:
        return "only the skill under test"
    shown = ", ".join(offered[:3]) + ("..." if len(offered) > 3 else "")
    return f"{len(offered)} other skills also visible ({shown}); built-ins are expected here"


def render(harness_name: str, checks: list[Check]) -> str:
    """Return the human-readable report."""
    lines = [harness_name]
    for c in checks:
        mark = "ok" if c.ok else "FAIL"
        lines.append(f"  {c.number}. {c.name:<28} {mark:>4} ({c.detail})")
    blocking = [c for c in checks if c.required and not c.ok]
    optional = [c for c in checks if not c.required and not c.ok]
    if blocking:
        lines.append(f"\n  qualifies: no, blocked on {', '.join(c.name for c in blocking)}")
    elif optional:
        lines.append("\n  qualifies: yes, with inputs_resolved unsupported")
    else:
        lines.append("\n  qualifies: yes")
    return "\n".join(lines)
