"""Config schema and the skill under test."""

from __future__ import annotations

import os
import re
import tomllib
from functools import lru_cache, partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_NAME = "shakedown.toml"
CASES_NAME = "cases.toml"
#: Where cases live when they live outside the skill: `shakedowns/` beside
#: the skill or above it, holding one `<slug>.cases.toml` per skill.
CASES_DIR = "shakedowns"
CASES_SUFFIX = ".cases.toml"
#: The cases schema this build reads and writes. Bumped when a change to
#: the file's shape would make an older reader measure the wrong thing.
CASES_VERSION = 1
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class ConfigError(Exception):
    """The config or the skill is unusable."""


class Events(BaseModel):
    """Where a tool call sits in this harness's output.

    Unknown keys are refused. A typo here would otherwise parse into a
    default, find no tool calls, and fail every check for a reason nobody
    could see.
    """

    model_config = ConfigDict(extra="forbid")

    container: str = ""
    discriminator: str = "type"
    tool_marker: str = "tool_use"
    name_key: str = "name"
    args_key: str = "input"
    text_key: str = "text"
    text_marker: str = "text"


class Harness(BaseModel):
    """One harness, described entirely by config. Unknown keys are refused."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    start: list[str]
    resume: list[str] = Field(default_factory=list)
    skills: str
    activation_tool: str = "Skill"
    image: str = ""
    dockerfile: str = ""
    events: Events = Field(default_factory=Events)
    env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one_environment(self) -> Harness:
        """A container is built from one thing or pulled from another."""
        if self.image and self.dockerfile:
            raise ValueError(
                "declare either `image` or `dockerfile`, not both: "
                "an image is pulled, a dockerfile is built"
            )
        return self

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
    """A question pattern and the reply to give it. Unknown keys refused."""

    model_config = ConfigDict(extra="forbid")

    match: re.Pattern[str]
    reply: str


class Artifact(BaseModel):
    """A file the skill must produce, and optionally what must be in it.

    Unknown keys are refused: `contain` for `contains` would otherwise
    degrade the check to "the file exists" and still report a pass.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    contains: list[str] = Field(default_factory=list)


class Case(BaseModel):
    """One measured scenario. Unknown keys are refused.

    TOML gives a bare key written after a table to that table, so a
    top-level key such as `fixtures` placed below the first `[[case]]`
    lands here instead. Ignoring it seeded no double and let the real
    command run for real.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    prompt: str
    artifacts: list[Artifact] = Field(default_factory=list)
    #: The CLI the skill must go through, if it has one. Omit for a skill
    #: that writes the artifact itself; the tool check then reports
    #: unsupported rather than failing.
    tool: str | None = None
    answers: list[Answer] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _one_or_many(cls, data: Any) -> Any:
        """Accept `artifact = "X"` as shorthand for a single artifact."""
        if isinstance(data, dict) and "artifact" in data:
            data = dict(data)
            single = data.pop("artifact")
            entry = {"path": single} if isinstance(single, str) else single
            data.setdefault("artifacts", []).insert(0, entry)
        return data


class CasesFile(BaseModel):
    """A cases file's own keys, refusing any it does not know.

    Parsed as a model rather than read out of the raw dict, so a typo'd
    `fixture` fails here instead of seeding no double and letting the real
    command run for real. `skill` and `fixtures` are file-level: TOML gives
    a bare key written after a table to that table, so one placed below the
    first `[[case]]` is refused by `Case` rather than landing here.
    """

    model_config = ConfigDict(extra="forbid")

    #: The schema this file is written against. The default is a literal 1
    #: rather than the current version: an absent key means the file was
    #: written before versioning existed, and that is true forever, not
    #: "whatever this build happens to be".
    version: int = 1
    skill: str = ""
    #: One directory, or several. Several is how a double shared between
    #: skills combines with the ones only this skill needs.
    fixtures: list[str] = Field(default_factory=list)
    case: list[Case] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _readable(cls, value: int) -> int:
        """Refuse the future, accept the past.

        A newer file read by an older build would have its unknown keys
        dropped, and a dropped key is a check that quietly measures
        nothing. An older file has no such problem, so refusing one would
        turn every schema bump into a breaking release for every cases
        file already written.
        """
        if value > CASES_VERSION:
            raise ValueError(
                f"version {value} is newer than this build reads "
                f"(it understands up to version {CASES_VERSION}); upgrade shakedown"
            )
        if value < 1:
            raise ValueError(f"version {value} is not a version; the first one is 1")
        return value

    @field_validator("fixtures", mode="before")
    @classmethod
    def _one_or_many(cls, value: object) -> object:
        """Accept `fixtures = "dir"` as shorthand for a single directory.

        Normalized here rather than by an accessor, so every reader
        downstream gets a list and no caller has to know about the
        shorthand.
        """
        if isinstance(value, str):
            return [value] if value else []
        return value


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
    """shakedown.toml: harnesses and the matrix."""

    #: Both default to empty so a config with no harness yet still loads.
    #: `init` can write one before you have chosen a harness, and the
    #: commands that need one say so rather than failing to parse.
    harness: dict[str, Harness] = Field(default_factory=dict)
    matrix: list[MatrixEntry] = Field(default_factory=list)
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
    """The skill under test: the directory that ships, and its cases.

    ``path`` is only ever what a user installs. The cases measuring it may
    sit outside that directory, and usually should.
    """

    path: Path
    name: str
    cases: list[Case]
    #: The schema its cases file declared, so a report can say what was read.
    version: int = CASES_VERSION
    #: Stand-ins the cases supply: executables that shadow the real thing on
    #: PATH. Declared beside the cases, never inside the skill, because a
    #: fake `gh` is something the skill is measured with rather than
    #: something it ships. Seeded in order, so a directory listed later
    #: overrides a same-named stand-in from one listed earlier: shared
    #: doubles first, the ones only this skill needs after.
    fixtures: list[Path] = Field(default_factory=list)

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
    """Nearest shakedown.toml, searching upward."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise ConfigError(f"no {CONFIG_NAME} found in {here} or any parent")


def load_config(path: Path | None = None) -> Config:
    """Load and validate shakedown.toml."""
    path = path or find_config()
    try:
        loaded = Config.model_validate(tomllib.loads(path.read_text()))
    except Exception as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    # Anchored to the config file, not the working directory, so the same
    # config works whether CI runs from the repo root or anywhere else.
    for harness in loaded.harness.values():
        if harness.dockerfile:
            resolved = (path.parent / harness.dockerfile).resolve()
            if not resolved.is_file():
                raise ConfigError(f"{path}: harness {harness.name}: no dockerfile at {resolved}")
            harness.dockerfile = str(resolved)
    return loaded


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


def find_cases(skill_dir: Path) -> Path:
    """The cases for this skill, in resolution order.

    1. ``shakedowns/<slug>.cases.toml``, beside the skill or anywhere
       above it. Cases are what the skill is measured against, not part of
       what ships, so this is where they belong.
    2. ``<skill>/cases.toml``, for a skill that keeps them inside.

    Searching upward rather than in one fixed place means a repo may hold
    its `shakedowns/` at the root, beside the skills, or both.
    """
    slug = skill_dir.name
    for directory in (skill_dir, *skill_dir.parents):
        candidate = directory / CASES_DIR / f"{slug}{CASES_SUFFIX}"
        if candidate.is_file():
            return candidate

    inside = skill_dir / CASES_NAME
    if inside.is_file():
        return inside

    raise ConfigError(
        f"no cases for {skill_dir}: expected {CASES_DIR}/{slug}{CASES_SUFFIX} "
        f"beside it or above it, or {CASES_NAME} inside it"
    )


def load_skill(path: Path) -> Skill:
    """Load the skill under test, from its directory or from its cases.

    A cases file names the skill it measures, so either end resolves to
    the same pair.
    """
    path = path.resolve()
    if path.is_file():
        return _from_cases(path)

    skill_md = path / "SKILL.md"
    if not skill_md.is_file():
        raise ConfigError(f"{path} has no SKILL.md")
    return _build(path, find_cases(path))


def _read_cases(cases_file: Path) -> CasesFile:
    """The cases file, validated. A key it does not know is refused.

    `skill` and `fixtures` are file-level keys and have to sit above the
    first `[[case]]`: TOML gives a bare key written after a table to that
    table, so one placed below it is refused by `Case` instead, and the
    message says which key.
    """
    try:
        return CasesFile.model_validate(tomllib.loads(cases_file.read_text()))
    except Exception as exc:
        hint = ""
        if "fixtures" in str(exc) or "skill" in str(exc):
            hint = (
                "\n`skill` and `fixtures` belong above the first [[case]]; "
                "written below one, TOML reads them as part of that case."
            )
        raise ConfigError(f"{cases_file}: {exc}{hint}") from exc


def _from_cases(cases_file: Path) -> Skill:
    """Load the skill a cases file points at."""
    declared = _read_cases(cases_file)
    if not declared.skill:
        raise ConfigError(
            f"{cases_file} declares no `skill`, so there is nothing to measure. "
            "Name the skill directory it tests, relative to this file."
        )
    # Relative to the cases file, not the working directory: the pair moves
    # together and is run from wherever CI happens to start.
    skill_dir = (cases_file.parent / declared.skill).resolve()
    if not (skill_dir / "SKILL.md").is_file():
        raise ConfigError(f"{cases_file}: `skill` names {skill_dir}, which has no SKILL.md")
    return _build(skill_dir, cases_file)


def _build(skill_dir: Path, cases_file: Path) -> Skill:
    """One skill directory and the cases measuring it."""
    skill_md = skill_dir / "SKILL.md"
    declared = _read_cases(cases_file)
    if not declared.case:
        raise ConfigError(f"{cases_file} declares no [[case]] blocks")

    fixtures = []
    for named in declared.fixtures:
        resolved = (cases_file.parent / named).resolve()
        if not resolved.is_dir():
            raise ConfigError(
                f"{cases_file}: `fixtures` names {resolved}, which is not a directory"
            )
        # A double inside the skill ships to everyone who installs it, which
        # is the one thing keeping fixtures beside the cases prevents.
        if resolved == skill_dir or skill_dir in resolved.parents:
            raise ConfigError(
                f"{cases_file}: `fixtures` names {resolved}, which is inside the skill. "
                "Stand-ins belong beside the cases: one inside the skill ships with it."
            )
        # And a directory holding the skill would be seeded whole, carrying
        # the cases file into the sandbox with it. A model that reads its
        # own answers passes `inputs_resolved` without being asked, which
        # is the one thing that check claims to rule out.
        if resolved in skill_dir.parents:
            raise ConfigError(
                f"{cases_file}: `fixtures` names {resolved}, which contains the skill. "
                "Name a directory of stand-ins, not a tree holding the skill and its cases."
            )
        fixtures.append(resolved)

    return Skill(
        path=skill_dir,
        name=_front_matter_name(skill_md, skill_md.stat().st_mtime),
        cases=declared.case,
        fixtures=fixtures,
        version=declared.version,
    )
