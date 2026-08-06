"""Everything harness-specific, loaded from TOML.

The framework knows how to run a command and assert on what came back. It
knows nothing about any particular harness. That knowledge lives here, in
data, so adding a harness is filling out a config rather than writing code.
"""

from __future__ import annotations

import os
import re
import shlex
import tomllib
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

CONFIG_NAME = "skillconf.toml"
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(Exception):
    """The config is unusable, and the message says which part."""


@dataclass(frozen=True)
class Events:
    """Where a tool call lives in this harness's output.

    ``container`` is one optional descent: "reach into this list, if
    present". Claude nests tool calls inside ``message.content``; Gemini
    emits them at the top level. One optional path covers both without
    shipping a query language, and a harness that fits neither fails
    loudly at `doctor` rather than scoring zero in silence.
    """

    container: str = ""
    discriminator: str = "type"
    tool_marker: str = "tool_use"
    name_key: str = "name"
    args_key: str = "input"
    text_key: str = "text"
    text_marker: str = "text"


@dataclass(frozen=True)
class Harness:
    """One harness, entirely described by configuration."""

    name: str
    start: str
    resume: str
    skill_dest: str
    events: Events
    tools: dict[str, str]
    env: dict[str, str] = field(default_factory=dict)
    #: Substring identifying a skill-activation call, so the framework can
    #: tell "the skill never fired" from "the skill fired and failed".
    activation_tool: str = "Skill"

    def supports_resume(self) -> bool:
        """Return whether this harness can continue a session."""
        return bool(self.resume)

    def render(self, template: str, **slots: str) -> list[str]:
        """Return argv for ``template`` with ``{slots}`` substituted.

        Substitution happens after splitting, so a prompt containing spaces
        or quotes stays exactly one argument and cannot inject flags.
        """
        argv = []
        for token in shlex.split(template):
            for key, value in slots.items():
                token = token.replace("{" + key + "}", value)
            argv.append(token)
        return argv

    def environment(self) -> dict[str, str]:
        """Return the run's environment: declared variables and nothing else.

        Not inherited. A harness that picks up the developer's shell also
        picks up their MCP servers, their installed skills, and their model
        overrides, none of which the user being measured has.
        """
        resolved: dict[str, str] = {}
        for key, raw in self.env.items():
            resolved[key] = _VAR.sub(partial(self._expand, key=key), raw)
        # PATH is not configuration, it is how a subprocess finds a binary.
        resolved.setdefault("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
        return resolved

    def _expand(self, match: re.Match[str], *, key: str) -> str:
        """Return the host value for one ${VAR}, or say which one is missing."""
        found = os.environ.get(match.group(1))
        if found is None:
            raise ConfigError(
                f"{self.name}.env.{key} references ${{{match.group(1)}}}, "
                "which is not set in this shell"
            )
        return found


@dataclass(frozen=True)
class Answer:
    """A question pattern and the reply to give it."""

    match: re.Pattern[str]
    reply: str


@dataclass(frozen=True)
class Case:
    """One measured scenario."""

    name: str
    prompt: str
    artifact: str
    answers: tuple[Answer, ...] = ()


@dataclass(frozen=True)
class Target:
    """One (harness, model) pair to measure."""

    harness: Harness
    model: str
    label: str


@dataclass(frozen=True)
class Config:
    """A whole skillconf.toml."""

    root: Path
    skill_dir: Path
    skill_name: str
    #: Optional directory of executables the skill expects on PATH. Copied
    #: into the sandbox so the agent finds the CLI by name, as a user would.
    bin_dir: Path | None
    harnesses: dict[str, Harness]
    cases: tuple[Case, ...]
    targets: tuple[Target, ...]
    repeat: int = 1


def find(start: Path | None = None) -> Path:
    """Return the nearest skillconf.toml, searching upward."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise ConfigError(f"no {CONFIG_NAME} found in {here} or any parent")


def load(path: Path | None = None) -> Config:
    """Load and validate a config."""
    path = path or find()
    raw = tomllib.loads(path.read_text())
    root = path.parent

    harnesses = {name: _harness(name, block) for name, block in raw.get("harness", {}).items()}
    if not harnesses:
        raise ConfigError(f"{path} declares no [harness.*] blocks")

    cases = tuple(_case(entry, i) for i, entry in enumerate(raw.get("case", [])))
    if not cases:
        raise ConfigError(f"{path} declares no [[case]] blocks")

    targets = tuple(_targets(raw.get("matrix", []), harnesses))
    if not targets:
        raise ConfigError(f"{path} declares no [[matrix]] entries")

    skill = raw.get("skill", {})
    if "path" not in skill or "name" not in skill:
        raise ConfigError(f"{path} needs a [skill] block with `path` and `name`")

    return Config(
        root=root,
        skill_dir=(root / skill["path"]).resolve(),
        skill_name=str(skill["name"]),
        bin_dir=(root / skill["bin"]).resolve() if skill.get("bin") else None,
        harnesses=harnesses,
        cases=cases,
        targets=targets,
        repeat=int(raw.get("repeat", 1)),
    )


def _harness(name: str, block: dict[str, Any]) -> Harness:
    """Build one Harness, naming any missing required key."""
    for required in ("start", "skills"):
        if required not in block:
            raise ConfigError(f"harness.{name} is missing `{required}`")
    skills = dict(block["skills"])
    if "dest" not in skills:
        raise ConfigError(f"harness.{name}.skills needs `dest` (where to seed the skill)")
    return Harness(
        name=name,
        start=str(block["start"]),
        resume=str(block.get("resume", "")),
        skill_dest=str(skills["dest"]),
        events=Events(**dict(block.get("events", {}))),
        tools={str(k): str(v) for k, v in dict(block.get("tools", {})).items()},
        env={str(k): str(v) for k, v in dict(block.get("env", {})).items()},
        activation_tool=str(block.get("activation_tool", "Skill")),
    )


def _case(entry: dict[str, Any], index: int) -> Case:
    """Build one Case."""
    for required in ("prompt", "artifact"):
        if required not in entry:
            raise ConfigError(f"case #{index} is missing `{required}`")
    answers = tuple(
        Answer(match=re.compile(str(a["match"])), reply=str(a["reply"]))
        for a in entry.get("answers", [])
    )
    return Case(
        name=str(entry.get("name", f"case-{index}")),
        prompt=str(entry["prompt"]),
        artifact=str(entry["artifact"]),
        answers=answers,
    )


def _targets(entries: list[dict[str, Any]], harnesses: dict[str, Harness]) -> list[Target]:
    """Expand matrix entries into (harness, model) targets.

    A per-entry `env` override produces a distinct harness, because pointing
    a harness at another provider changes what is being measured and must
    not silently share a label with the original.
    """
    out = []
    for entry in entries:
        name = str(entry.get("harness", ""))
        if name not in harnesses:
            raise ConfigError(f"matrix references unknown harness {name!r}")
        base = harnesses[name]
        override = {str(k): str(v) for k, v in dict(entry.get("env", {})).items()}
        harness = (
            base if not override else Harness(**{**base.__dict__, "env": {**base.env, **override}})
        )
        for model in entry.get("models", []):
            prefix = str(entry.get("label", name))
            out.append(Target(harness=harness, model=str(model), label=f"{prefix}/{model}"))
    return out
