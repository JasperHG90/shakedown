"""Harness output, normalized."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from skeval.models import Events


class StreamError(Exception):
    """The output could not be parsed."""


class ToolCall(BaseModel):
    """One tool invocation."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)

    def text(self) -> str:
        """Argument values as one searchable string."""
        return " ".join(str(v) for v in self.args.values())


class Turn(BaseModel):
    """What one harness invocation produced."""

    tool_calls: list[ToolCall] = Field(default_factory=list)
    texts: list[str] = Field(default_factory=list)
    skills_offered: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    exit_code: int = 0
    argv: list[str] = Field(default_factory=list)
    duration_s: float = 0.0
    stream: str = ""
    stderr_tail: str = ""

    def said(self) -> str:
        """Everything the agent said, as one line to match a question against.

        Joined with a space, not a newline: a harness that streams a reply in
        fragments would otherwise split a sentence, and ``.`` in an answer
        pattern does not cross a newline.
        """
        return " ".join(self.texts)

    def called(self, needle: str) -> list[ToolCall]:
        """Calls whose name or arguments mention ``needle``."""
        return [c for c in self.tool_calls if needle in c.name or needle in c.text()]


def read(path: Path) -> list[dict[str, Any]]:
    """Parse newline-delimited JSON. A truncated stream raises."""
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
    if not path:
        return [record]
    node: Any = record
    for part in path.split("."):
        if not isinstance(node, dict):
            return []
        node = node.get(part)
    return [b for b in node if isinstance(b, dict)] if isinstance(node, list) else []


def parse(records: list[dict[str, Any]], spec: Events) -> Turn:
    """Raw records to the neutral shape."""
    turn = Turn()
    for record in records:
        offered = record.get("skills")
        if isinstance(offered, list):
            turn.skills_offered = [str(s) for s in offered]

        for denial in record.get("permission_denials") or []:
            name = denial.get("tool_name", denial) if isinstance(denial, dict) else denial
            turn.denied.append(str(name))

        for block in _descend(record, spec.container):
            # A flat harness tags every message with a role, and its echo of
            # the prompt is not something the agent said. Counting it lets a
            # case whose own prompt mentions "owner" answer a question the
            # harness never asked.
            if block.get("role") == "user":
                continue
            kind = block.get(spec.discriminator)
            if kind == spec.tool_marker:
                turn.tool_calls.append(
                    ToolCall(
                        name=str(block.get(spec.name_key, "")),
                        args=dict(block.get(spec.args_key, {}) or {}),
                    )
                )
            elif kind == spec.text_marker and (text := str(block.get(spec.text_key, ""))):
                turn.texts.append(text)

        # Role-tagged text lives outside the container. The prompt echo the
        # harness emits as role=user must not count as something it said.
        content = record.get(spec.text_key) or record.get("content")
        if (
            spec.container
            and record.get("role") == "assistant"
            and isinstance(content, str)
            and content
        ):
            turn.texts.append(content)

    return turn
