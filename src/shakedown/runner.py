"""A conversation is a sequence of subprocess calls.

Multi-turn is re-invocation via --session-id and --resume, not a
bidirectional stream, so every turn is a plain process.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from pathlib import Path

import stamina
from pydantic import BaseModel, Field

from shakedown.events import StreamError, ToolCall, Turn, parse, read
from shakedown.models import Case, Harness
from shakedown.sandbox import Sandbox

TURN_CAP = 6
#: How much of a turn's stderr the report carries.
TAIL_CHARS = 500
#: Harnesses return transient upstream errors ("the model returned an empty
#: response"). Retried rather than scored as a skill failure.
RETRY_MARKERS = ("empty response", "temporarily unavailable", "rate limit", "overloaded")


class TransientHarnessError(Exception):
    """The harness failed for a reason that is not the skill's fault."""


class Conversation(BaseModel):
    """Every turn of one run, plus the replies supplied."""

    turns: list[Turn] = Field(default_factory=list)
    given: list[str] = Field(default_factory=list)
    workspace: Path = Path()
    timed_out: bool = False
    #: Whether the conversation ended with a reply still owed and nothing
    #: matching what was said. Reporting that as "never asked" is a guess.
    #: That no pattern fired is the fact.
    unmatched: bool = False
    #: The tail of what was said when it did. A turn of nothing but tool
    #: calls says nothing at all, so an empty tail is still a stall and
    #: `unmatched` is what carries it.
    unmatched_tail: str = ""

    @property
    def first(self) -> Turn:
        """The opening turn."""
        return self.turns[0]

    def tool_calls(self) -> list[ToolCall]:
        """Every tool call across every turn."""
        return [c for t in self.turns for c in t.tool_calls]

    def called(self, needle: str) -> list[ToolCall]:
        """Calls across all turns mentioning ``needle``."""
        return [c for t in self.turns for c in t.called(needle)]

    def denied(self) -> list[str]:
        """Tools the harness refused to run."""
        return [d for t in self.turns for d in t.denied]

    def skill_fired(self, harness: Harness, skill_name: str) -> bool:
        """Whether the skill activated at runtime."""
        for call in self.tool_calls():
            if harness.activation_tool in call.name and (
                skill_name in call.text() or not call.args
            ):
                return True
        return any(skill_name in t.skills_offered for t in self.turns)


def _tail(diagnosis: str, stderr: str) -> str:
    """The end of ``stderr``, with ``diagnosis`` kept whole in front of it.

    Joining the two and slicing the pair from the end dropped the diagnosis
    exactly when the harness was chatty, which is when it was worth having.
    So the diagnosis gets its space first and stderr takes what is left.

    Parameters
    ----------
    diagnosis :
        Why the stream could not be read, or empty if it could.
    stderr :
        What the harness wrote to stderr, already stripped.

    Returns
    -------
    str
        At most ``TAIL_CHARS`` characters.
    """
    if not diagnosis:
        return stderr[-TAIL_CHARS:]
    room = TAIL_CHARS - len(diagnosis) - 1
    if room <= 0:
        return diagnosis[:TAIL_CHARS]
    return "\n".join(filter(None, (diagnosis, stderr[-room:])))


def _once(
    box: Sandbox, harness: Harness, argv: list[str], stem: str, timeout_s: float
) -> tuple[Turn, bool]:
    """Run the harness once and read what it produced.

    Returns the turn, and whether it timed out.
    """
    started = time.monotonic()
    code, stdout, stderr = box.exec(argv, harness.environment(), timeout_s)
    elapsed = time.monotonic() - started

    out_path = box.path / f".shakedown-{stem}.jsonl"
    out_path.write_text(stdout)
    (box.path / f".shakedown-{stem}.err").write_text(stderr)

    blob = f"{stdout}\n{stderr}".lower()
    if code != 0 and any(marker in blob for marker in RETRY_MARKERS):
        raise TransientHarnessError(stderr.strip()[:200] or "transient harness error")

    # A harness that prints prose, or a warning line, or anything else that is
    # not newline-delimited JSON is a harness that produced no events — not a
    # crashed process. Raising here ended the whole invocation on a traceback,
    # so `doctor` never got to say which prerequisite failed and a live matrix
    # lost every row after the first bad stream.
    #
    # Only `read` is caught. The failures `parse` raises are the config's, not
    # the harness's — an `args_key` pointed one level off — and swallowing
    # those would turn a loud crash into a run that scored zero everywhere and
    # skipped, which is the outcome that raise exists to prevent.
    try:
        records = read(out_path)
        unparsed = ""
    except StreamError as exc:
        records = []
        unparsed = str(exc)

    turn = parse(records, harness.events)
    turn.exit_code = code
    # Recorded per turn as well as per conversation: a later turn timing
    # out must not be reported against the opening one.
    turn.timed_out = code == -1
    turn.argv = argv
    turn.duration_s = round(elapsed, 2)
    turn.stream = str(out_path)
    turn.stderr_tail = _tail(unparsed, stderr.strip())
    return turn, code == -1


def _turn(
    box: Sandbox, harness: Harness, argv: list[str], stem: str, timeout_s: float
) -> tuple[Turn, bool]:
    """``_once``, retried while the harness fails for reasons of its own."""
    for attempt in stamina.retry_context(on=TransientHarnessError, attempts=3, wait_initial=2.0):
        with attempt:
            return _once(box, harness, argv, stem, timeout_s)
    raise TransientHarnessError("exhausted retries")


def converse(
    box: Sandbox,
    harness: Harness,
    case: Case,
    *,
    model: str,
    timeout_s: float = 300.0,
    notify: Callable[[int], None] | None = None,
) -> Conversation:
    """Run ``case`` to completion, answering questions as they arrive.

    ``notify`` is called with the index of each turn about to start. A turn
    is a whole model round trip, so it is the only unit slow enough to be
    worth reporting, and the caller decides what to say about it.
    """
    sid = str(uuid.uuid4())
    convo = Conversation(workspace=box.path)

    if notify:
        notify(0)
    argv = harness.render(harness.start, prompt=case.prompt, model=model, sid=sid)
    turn, convo.timed_out = _turn(box, harness, argv, "turn0", timeout_s)
    convo.turns.append(turn)

    if not harness.supports_resume:
        return convo

    for index in range(1, TURN_CAP):
        if convo.timed_out:
            break
        # Each answer is supplied once. The trigger word survives into later
        # turns, so matching without this re-answers until the cap.
        reply = _match(turn.said(), case, convo.given)
        if reply is None:
            # Three things end the loop here, and only one is a finding: a
            # reply still owed. A case that withholds nothing, or one whose
            # every answer landed, stopped because it was finished.
            if any(a.reply not in convo.given for a in case.answers):
                convo.unmatched = True
                convo.unmatched_tail = turn.said()[-500:]
            break
        convo.given.append(reply)
        if notify:
            notify(index)
        argv = harness.render(harness.resume, reply=reply, model=model, sid=sid)
        turn, convo.timed_out = _turn(box, harness, argv, f"turn{index}", timeout_s)
        convo.turns.append(turn)

    return convo


def _match(said: str, case: Case, already: list[str]) -> str | None:
    for answer in case.answers:
        if answer.reply not in already and answer.match.search(said):
            return answer.reply
    return None


__all__ = ["Conversation", "StreamError", "TransientHarnessError", "converse"]
