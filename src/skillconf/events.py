"""Two stream shapes, one normalized result.

A tool call differs across harnesses in three ways: key names, depth, and
cardinality. Key names are config. Depth is one optional descent. Cardinality
is the one that bites: a single Claude record can carry several tool_use
blocks, so anything counting records instead of blocks is wrong in a way that
looks fine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skillconf.config import Events


class StreamError(Exception):
    """The output could not be parsed, so nothing may be concluded from it."""


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation, with the harness's own name kept for diagnostics."""

    name: str
    args: dict[str, Any]

    def text(self) -> str:
        """Return the argument values as one searchable string."""
        return " ".join(str(v) for v in self.args.values())


@dataclass
class Turn:
    """What one harness invocation produced."""

    tool_calls: list[ToolCall] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    skills_offered: list[str] = field(default_factory=list)
    #: Tools the harness refused to run. A call in the transcript is a
    #: REQUEST; without this, a denied command reads as an executed one.
    denied: list[str] = field(default_factory=list)
    exit_code: int = 0
    raw: Path | None = None

    def said(self) -> str:
        """Return everything the agent said, joined."""
        return "\n".join(self.texts)

    def called(self, needle: str) -> list[ToolCall]:
        """Return tool calls whose name or arguments mention ``needle``."""
        return [c for c in self.tool_calls if needle in c.name or needle in c.text()]


def read(path: Path) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON.

    A truncated stream raises rather than yielding a partial result. A
    plausible partial result is worse than none, because it gets scored.
    """
    records = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StreamError(f"{path}:{number} is not valid JSON: {exc}") from exc
        if isinstance(record, dict):
            records.append(record)
    return records


def _descend(record: dict[str, Any], path: str) -> list[dict[str, Any]]:
    """Return the list at ``path``, or the record itself when path is empty."""
    if not path:
        return [record]
    node: Any = record
    for part in path.split("."):
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    if isinstance(node, list):
        return [b for b in node if isinstance(b, dict)]
    return []


def parse(records: list[dict[str, Any]], spec: Events) -> Turn:
    """Turn raw records into the neutral shape."""
    turn = Turn()
    for record in records:
        # Skill inventory, wherever the harness advertises it. Runtime
        # visibility is the only thing that counts: a static plugin
        # inventory can report a skill the model never sees.
        offered = record.get("skills")
        if isinstance(offered, list):
            turn.skills_offered = [str(s) for s in offered]

        for denial in record.get("permission_denials") or []:
            if isinstance(denial, dict):
                turn.denied.append(str(denial.get("tool_name", denial)))
            else:
                turn.denied.append(str(denial))

        for block in _descend(record, spec.container):
            kind = block.get(spec.discriminator)
            if kind == spec.tool_marker:
                turn.tool_calls.append(
                    ToolCall(
                        name=str(block.get(spec.name_key, "")),
                        args=dict(block.get(spec.args_key, {}) or {}),
                    )
                )
            elif kind == spec.text_marker:
                text = str(block.get(spec.text_key, ""))
                if text:
                    turn.texts.append(text)

        # Harnesses that stream text outside the container (Gemini's
        # role-tagged messages) still need collecting, and the prompt echo
        # they emit as role=user must not be attributed to the agent.
        if spec.container and record.get("role") == "assistant":
            content = record.get(spec.text_key) or record.get("content")
            if isinstance(content, str) and content:
                turn.texts.append(content)
    return turn
