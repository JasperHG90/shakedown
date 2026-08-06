"""Running a conversation as a sequence of subprocess calls.

Multi-turn is re-invocation, not a bidirectional stream. Both known
harnesses expose a session id and a resume flag, so turn two is just
another process. That is uniform across harnesses, needs no per-harness
stdin encoding, and every turn is trivially testable.
"""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from skillconf.config import Case, Harness
from skillconf.events import ToolCall, Turn, parse, read

DEFAULT_TURN_CAP = 6


@dataclass
class Conversation:
    """Every turn of one run, plus the replies that were supplied."""

    turns: list[Turn] = field(default_factory=list)
    given: list[str] = field(default_factory=list)
    workspace: Path = Path()
    timed_out: bool = False

    @property
    def first(self) -> Turn:
        """Return the opening turn."""
        return self.turns[0]

    def tool_calls(self) -> list[ToolCall]:
        """Return every tool call across every turn."""
        return [c for t in self.turns for c in t.tool_calls]

    def called(self, needle: str) -> list[ToolCall]:
        """Return calls across all turns mentioning ``needle``."""
        return [c for t in self.turns for c in t.called(needle)]

    def denied(self) -> list[str]:
        """Return every tool the harness refused to run."""
        return [d for t in self.turns for d in t.denied]

    def skill_fired(self, harness: Harness, skill_name: str) -> bool:
        """Return whether the skill was activated at runtime.

        Runtime activation, never a static inventory: a harness can report
        a skill as loaded while the model never sees it.
        """
        for call in self.tool_calls():
            if harness.activation_tool in call.name and skill_name in call.text():
                return True
            if harness.activation_tool in call.name and not call.args:
                return True
        return any(skill_name in t.skills_offered for t in self.turns)


def _turn(
    harness: Harness,
    argv: list[str],
    workspace: Path,
    stem: str,
    timeout_s: float,
) -> tuple[Turn, bool]:
    """Run one invocation, returning the parsed turn and whether it timed out."""
    out_path = workspace / f".skillconf-{stem}.jsonl"
    err_path = workspace / f".skillconf-{stem}.err"
    timed_out = False

    env = harness.environment()
    # The sandbox's own bin first, so the agent resolves the CLI by name
    # exactly as a user would, without the host's PATH leaking in.
    env["PATH"] = f"{workspace / 'bin'}:{env['PATH']}"

    with out_path.open("w") as out, err_path.open("w") as err:
        try:
            completed = subprocess.run(
                argv,
                cwd=workspace,
                env=env,
                # Closed explicitly. An inherited stdin makes some harnesses
                # wait on data that never arrives.
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                timeout=timeout_s,
                check=False,
            )
            code = completed.returncode
        except subprocess.TimeoutExpired:
            code, timed_out = -1, True

    turn = parse(read(out_path), harness.events)
    turn.exit_code = code
    turn.raw = out_path
    return turn, timed_out


def converse(
    harness: Harness,
    case: Case,
    workspace: Path,
    *,
    model: str,
    timeout_s: float = 300.0,
    turn_cap: int = DEFAULT_TURN_CAP,
) -> Conversation:
    """Run ``case`` to completion, answering questions as they arrive.

    The loop never needs a harness to block for input. It runs a turn, sees
    whether the output matched an answer pattern, and if so runs another. A
    harness that invents values rather than asking simply never receives a
    reply, and the artifact will not contain one.
    """
    sid = str(uuid.uuid4())
    convo = Conversation(workspace=workspace)

    argv = harness.render(harness.start, prompt=case.prompt, model=model, sid=sid)
    turn, convo.timed_out = _turn(harness, argv, workspace, "turn0", timeout_s)
    convo.turns.append(turn)

    if not harness.supports_resume():
        return convo

    for index in range(1, turn_cap):
        if convo.timed_out:
            break
        # Each answer is supplied at most once. The word that triggered it
        # usually survives into later turns ("the owner is platform-team"),
        # so matching without this re-answers the same question until the
        # turn cap, which looks like a stuck harness and costs real money.
        reply = _match(turn.said(), case, already=convo.given)
        if reply is None:
            break
        convo.given.append(reply)
        argv = harness.render(harness.resume, reply=reply, model=model, sid=sid)
        turn, convo.timed_out = _turn(harness, argv, workspace, f"turn{index}", timeout_s)
        convo.turns.append(turn)

    return convo


def _match(said: str, case: Case, already: list[str]) -> str | None:
    """Return the reply for the first unused answer pattern the text matches."""
    for answer in case.answers:
        if answer.reply in already:
            continue
        if answer.match.search(said):
            return answer.reply
    return None
