"""Config schema and the skill under test."""

from __future__ import annotations

import os
import re
import tomllib
from functools import lru_cache, partial
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

CONFIG_NAME = "skeval.toml"
CASES_NAME = "cases.toml"
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class ConfigError(Exception):
    """The config or the skill is unusable."""


class Events(BaseModel):
    """Where a tool call sits in this harness's output."""

    container: str = ""
    discriminator: str = "type"
    tool_marker: str = "tool_use"
    name_key: str = "name"
    args_key: str = "input"
    text_key: str = "text"
    text_marker: str = "text"


class Harness(BaseModel):
    """One harness, described entirely by config."""

    name: str = ""
    start: list[str]
    resume: list[str] = Field(default_factory=list)
    skills: str
    activation_tool: str = "Skill"
    image: str = ""
    install: str = ""
    events: Events = Field(default_factory=Events)
    env: dict[str, str] = Field(default_factory=dict)

    @property
    def supports_resume(self) -> bool:
        """Whether this harness can continue a session."""
        return bool(self.resume)

    def render(self, template: list[str], **slots: str) -> list[str]:
        """Argv with ``{slots}`` substituted. Args are a list, so a prompt is
        always exactly one argument and cannot inject a flag."""
        return [_substitute(token, slots) for token in template]

    def environment(self) -> dict[str, str]:
        """Declared variables only. Nothing is inherited."""
        out = {
            key: _VAR.sub(partial(_host, harness=self.name, key=key), value)
            for key, value in self.env.items()
        }
        out.setdefault("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
        return out


class Answer(BaseModel):
    """A question pattern and the reply to give it."""

    match: re.Pattern[str]
    reply: str


class Case(BaseModel):
    """One measured scenario."""

    name: str
    prompt: str
    artifact: str
    #: The CLI the skill must go through, if it has one. Omit for a skill
    #: that writes the artifact itself; the tool check then reports
    #: unsupported rather than failing.
    tool: str | None = None
    answers: list[Answer] = Field(default_factory=list)


class MatrixEntry(BaseModel):
    """A harness and the models to run it with."""

    harness: str
    models: list[str]
    label: str = ""
    env: dict[str, str] = Field(default_factory=dict)


class Target(BaseModel):
    """One harness and model to measure."""

    harness: Harness
    model: str
    label: str


class Config(BaseModel):
    """skeval.toml: harnesses and the matrix."""

    harness: dict[str, Harness]
    matrix: list[MatrixEntry]
    repeat: int = 1

    @field_validator("harness")
    @classmethod
    def _name_them(cls, value: dict[str, Harness]) -> dict[str, Harness]:
        for key, harness in value.items():
            harness.name = key
        return value

    @model_validator(mode="after")
    def _matrix_resolves(self) -> Config:
        for entry in self.matrix:
            if entry.harness not in self.harness:
                known = ", ".join(self.harness)
                raise ValueError(
                    f"matrix references unknown harness {entry.harness!r}; known: {known}"
                )
        return self

    def targets(self) -> list[Target]:
        """Expand the matrix. An env override yields a distinct harness."""
        out = []
        for entry in self.matrix:
            base = self.harness[entry.harness]
            harness = (
                base
                if not entry.env
                else base.model_copy(update={"env": {**base.env, **entry.env}})
            )
            for model in entry.models:
                prefix = entry.label or entry.harness
                out.append(Target(harness=harness, model=model, label=f"{prefix}/{model}"))
        return out


class Skill(BaseModel):
    """The skill under test: one self-contained directory."""

    path: Path
    name: str
    cases: list[Case]

    @property
    def bin_dir(self) -> Path | None:
        """Executables the skill expects on PATH, if it ships any."""
        candidate = self.path / "bin"
        return candidate if candidate.is_dir() else None


def _substitute(token: str, slots: dict[str, str]) -> str:
    for key, value in slots.items():
        token = token.replace("{" + key + "}", value)
    return token


def _host(match: re.Match[str], *, harness: str, key: str) -> str:
    found = os.environ.get(match.group(1))
    if found is None:
        raise ConfigError(f"{harness}.env.{key} references ${{{match.group(1)}}}, which is not set")
    return found


def find_config(start: Path | None = None) -> Path:
    """Nearest skeval.toml, searching upward."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise ConfigError(f"no {CONFIG_NAME} found in {here} or any parent")


def load_config(path: Path | None = None) -> Config:
    """Load and validate skeval.toml."""
    path = path or find_config()
    try:
        return Config.model_validate(tomllib.loads(path.read_text()))
    except Exception as exc:
        raise ConfigError(f"{path}: {exc}") from exc


@lru_cache(maxsize=32)
def _front_matter_name(skill_md: Path, mtime: float) -> str:
    del mtime
    match = _FRONT_MATTER.match(skill_md.read_text())
    if not match:
        raise ConfigError(f"{skill_md} has no front-matter block")
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "name" and value.strip():
            return value.strip()
    raise ConfigError(f"{skill_md} front-matter declares no `name`")


def load_skill(path: Path) -> Skill:
    """Load a skill directory: SKILL.md, its cases, and any bin/."""
    path = path.resolve()
    skill_md = path / "SKILL.md"
    if not skill_md.is_file():
        raise ConfigError(f"{path} has no SKILL.md")

    cases_file = path / CASES_NAME
    if not cases_file.is_file():
        raise ConfigError(f"{path} has no {CASES_NAME}")
    raw = tomllib.loads(cases_file.read_text())
    try:
        cases = [Case.model_validate(entry) for entry in raw.get("case", [])]
    except Exception as exc:
        raise ConfigError(f"{cases_file}: {exc}") from exc
    if not cases:
        raise ConfigError(f"{cases_file} declares no [[case]] blocks")

    return Skill(
        path=path,
        name=_front_matter_name(skill_md, skill_md.stat().st_mtime),
        cases=cases,
    )
