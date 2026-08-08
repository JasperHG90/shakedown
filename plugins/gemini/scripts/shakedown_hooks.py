#!/usr/bin/env python3
"""Hook bodies shared by the Claude Code plugin and the Gemini extension.

One implementation behind two manifests, because two copies of a warning
drift and then disagree about what the tool does.

Every hook here is free: it reads files, parses TOML, and at most runs
`shakedown case validate`, which spends nothing. A hook that cost money
would be a hook nobody could afford to leave on.

Invoked as `shakedown_hooks.py <hook>` with the harness's JSON event on
stdin. The two harnesses name their events differently — Gemini ships the
mapping in its own bundle, `PreToolUse: "BeforeTool"`, `PostToolUse:
"AfterTool"` — but the payloads agree on the fields used here, and a field
that is missing is treated as absent rather than fatal.

Exit codes follow the Claude Code contract, which Gemini shares: 0 allows,
2 blocks and shows stderr to the model. Only one condition blocks. See
`decide_run`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

INSTALL = "uv tool install git+https://github.com/JasperHG90/shakedown"
#: `${VAR}` in a harness's declared environment.
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
#: `case run` options that swallow the token after them, so the argument
#: hunt below does not mistake a flag's value for the skill.
TAKES_A_VALUE = frozenset(
    {"--config", "--harness", "--case", "--repeat", "--sandbox", "--report", "--parallel", "-j"}
)

ALLOW, BLOCK = 0, 2


@dataclass(frozen=True)
class Verdict:
    """What a hook decided, and why."""

    code: int = ALLOW
    say: str = ""

    def emit(self, event_name: str = "") -> int:
        """Put the message somewhere it will actually be read.

        Which stream reaches anyone depends on the event, and getting it
        wrong is silent — the hook runs, the warning is composed, and
        nobody ever sees it:

        - A blocking exit shows stderr to the model. That one is simple.
        - `SessionStart` shows plain stdout to the model, so say it plainly.
        - Before a tool call, plain stdout is shown to nobody at all; after
          one, only in transcript mode. So those return JSON instead, where
          `systemMessage` is surfaced to the operator, and
          `additionalContext` puts it in front of the model.
        """
        if not self.say:
            return self.code
        if self.code:
            print(self.say, file=sys.stderr)
        elif event_name:
            speak: dict[str, object] = {"systemMessage": self.say}
            if event_name == "PostToolUse":
                speak["hookSpecificOutput"] = {
                    "hookEventName": event_name,
                    "additionalContext": self.say,
                }
            print(json.dumps(speak))
        else:
            print(self.say)
        return self.code


def event() -> dict[str, object]:
    """The harness's JSON event, or nothing if it sent none.

    Anything that is not an object is read as no event: a harness sending
    a list or a bare string is not something to guess at, and every
    reader below expects to look keys up.
    """
    try:
        parsed = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def config_at(start: Path | None = None) -> Path | None:
    """The nearest `shakedown.toml`, searching upward. None if there is none."""
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / "shakedown.toml"
        if candidate.is_file():
            return candidate
    return None


def installed() -> bool:
    """Whether the CLI this whole plugin is about is on PATH."""
    return shutil.which("shakedown") is not None


def missing_variables(config: Path) -> list[str]:
    """Unset `${VAR}`s that a run could actually reach.

    shakedown treats an unset declared variable as an error rather than an
    empty string, because silently dropping it would change what ran. It
    raises per target, while the sandbox is being built — after the run has
    started, and inside a command you are paying for. Saying it at session
    start is the point of this hook.

    Only variables a target could reach are reported. `${VAR}` is expanded
    in `Harness.environment()`, which runs for targets the matrix produces,
    so a harness no `[[matrix]]` entry names cannot fail a run no matter
    what it declares. This repo ships two such harnesses as worked
    examples, and reporting their tokens would be a warning nobody can act
    on — which is how a session hook earns being turned off.
    """
    try:
        parsed = tomllib.loads(config.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return []

    harnesses = parsed.get("harness")
    described = harnesses if isinstance(harnesses, dict) else {}
    entries = [entry for entry in parsed.get("matrix", []) if isinstance(entry, dict)]

    wanted: list[str] = []
    for entry in entries:
        harness = described.get(str(entry.get("harness")))
        declared = harness.get("env") if isinstance(harness, dict) else None
        # A matrix override replaces the harness's value for that key, so
        # the base one need not be set when the override supplies it.
        merged = dict(declared) if isinstance(declared, dict) else {}
        override = entry.get("env")
        if isinstance(override, dict):
            merged.update(override)
        wanted += [name for value in merged.values() for name in VAR.findall(str(value))]
    return sorted({name for name in wanted if name not in os.environ})


def session_start() -> Verdict:
    """Say what is missing before anything is spent on finding out."""
    if not installed():
        return Verdict(
            ALLOW,
            "shakedown is not on the PATH this hook sees. If your terminal has it, the "
            "directory is added by `~/.zshrc` or `~/.bashrc`, which only interactive "
            "shells read. Put it in `~/.zshenv` for zsh, or a file named by `$BASH_ENV` "
            f"for bash. Otherwise install it:\n  {INSTALL}",
        )

    config = config_at()
    if config is None:
        return Verdict(ALLOW, "shakedown: no shakedown.toml here. `shakedown init` writes one.")

    if absent := missing_variables(config):
        named = ", ".join(absent)
        plural = "is" if len(absent) == 1 else "are"
        return Verdict(
            ALLOW,
            f"shakedown: {config.name} declares {named} on a target in the matrix, "
            f"which {plural} not set here. An unset declared variable is an error rather "
            "than an empty string, so the run fails once it reaches that target — after "
            "it has started.\n"
            "If your terminal has it, it is exported somewhere only interactive shells "
            "read — `~/.zshrc` or `~/.bashrc`. A hook is not one, and neither is a tool "
            "your editor launches. Export it from `~/.zshenv` for zsh, or from a file "
            "named by `$BASH_ENV` for bash, which non-interactive shells do read.",
        )
    return Verdict()


def can_validate() -> bool:
    """Whether the installed CLI has `case validate` at all.

    An older build exits 2 with click's "No such command 'case'", the same
    code a rejected cases file uses. Without this probe a stale install
    reads as every file being broken, and the gate below blocks every run
    for a reason that has nothing to do with the run.
    """
    try:
        done = subprocess.run(
            ["shakedown", "case", "validate", "--help"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def validate(path: Path) -> subprocess.CompletedProcess[str]:
    """Run the free check on one cases file."""
    return subprocess.run(
        ["shakedown", "case", "validate", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def written(payload: dict[str, object]) -> Path | None:
    """The file a Write or Edit just produced, if the event names one."""
    tool_input = payload.get("tool_input")
    named = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    return Path(str(named)) if named else None


def after_write(payload: dict[str, object]) -> Verdict:
    """Check a cases file as soon as it is written, and fixtures for the bit."""
    path = written(payload)
    if path is None:
        return Verdict()

    if path.match("*.cases.toml"):
        if not installed() or not can_validate():
            return Verdict()
        done = validate(path)
        if done.returncode:
            return Verdict(ALLOW, f"shakedown: {path.name} does not load yet.\n{done.stdout}")
        if "nothing but skill_fired" in done.stdout:
            return Verdict(ALLOW, f"shakedown: a case measures nothing.\n{done.stdout}")
        return Verdict()

    # A double at mode 644 is not skipped in favour of the real command:
    # the shell refuses it, and the run fails naming neither the fixture
    # nor the bit.
    a_fixture = "shakedowns/fixtures/" in path.as_posix() and path.is_file()
    if a_fixture and not os.access(path, os.X_OK):
        return Verdict(
            ALLOW,
            f"shakedown: {path.name} is a fixture but is not executable, so the "
            f"shell will refuse it rather than fall through to the real command. "
            f"chmod +x {path}",
        )
    return Verdict()


def targets_of(command: str) -> list[str]:
    """Every argument a `shakedown case run` in this command would measure.

    Parsed rather than pattern-matched, for two reasons the regex this
    replaces got wrong in both directions. `case run` takes "the skill
    under test, or the cases file naming it", and every example in the
    docs passes the directory — so matching a `*.cases.toml` path missed
    the common form entirely. And searching the raw string for the words
    matched them inside `git commit -m "… case run …"`, blocking a commit.

    Splitting the way a shell does fixes both: a quoted mention is one
    token and cannot match the three-token sequence, and the argument is
    found by position instead of by shape.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:  # unbalanced quotes: not something to judge
        return []

    found: list[str] = []
    index = 0
    while index + 2 < len(tokens):
        run_here = (
            Path(tokens[index]).name == "shakedown"
            and tokens[index + 1] == "case"
            and tokens[index + 2] == "run"
        )
        if not run_here:
            index += 1
            continue

        after = index + 3
        while after < len(tokens):
            token = tokens[after]
            if token == "--":
                after += 1
                continue
            if token.startswith("-"):
                after += 2 if token in TAKES_A_VALUE else 1
                continue
            found.append(token)
            break
        index = after + 1
    return found


def decide_run(command: str) -> Verdict:
    """Whether to let a `shakedown case run` proceed.

    Blocks on exactly one thing: cases that do not load. That is free to
    know, certain, and means the spend buys nothing. Everything else
    warns, because a weak case or a stopped Docker is a judgment call or a
    fast failure rather than wasted money.
    """
    weak = ""
    if installed() and can_validate():
        for named in targets_of(command):
            path = Path(named)
            # A path that is not here cannot be judged from here — the
            # command may `cd` first, or name something built later.
            if not path.exists():
                continue
            done = validate(path)
            if done.returncode:
                return Verdict(
                    BLOCK,
                    f"shakedown: {named} does not load, so this run cannot measure "
                    f"anything.\n{done.stdout or done.stderr}",
                )
            if "nothing but skill_fired" in done.stdout:
                weak = (
                    f"shakedown: a case in {named} measures nothing but whether the "
                    "skill fired; it will pass whatever the skill does."
                )

    if "--sandbox container" in command and not _docker_up():
        return Verdict(
            ALLOW,
            "shakedown: --sandbox container, but Docker is not answering. The run will "
            "fail before it spends anything.",
        )
    return Verdict(ALLOW, weak)


def _docker_up() -> bool:
    """Whether a container backend could start at all."""
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def before_bash(payload: dict[str, object]) -> Verdict:
    """Gate the one command in this tool that spends money."""
    tool_input = payload.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not targets_of(str(command)):
        return Verdict()
    return decide_run(str(command))


HOOKS = {
    "session-start": lambda _: session_start(),
    "after-write": after_write,
    "before-bash": before_bash,
}

#: The event each hook answers, which decides how an allowing message has
#: to be returned. Empty for `SessionStart`, whose stdout already reaches
#: the model.
SPEAKS_AS = {
    "session-start": "",
    "after-write": "PostToolUse",
    "before-bash": "PreToolUse",
}


def main(argv: list[str]) -> int:
    """Dispatch, and never wedge the session on a bug in here."""
    name = argv[1] if len(argv) > 1 else ""
    hook = HOOKS.get(name)
    if hook is None:
        print(f"unknown hook {name!r}; known: {', '.join(HOOKS)}", file=sys.stderr)
        return ALLOW
    try:
        return hook(event()).emit(SPEAKS_AS.get(name, ""))
    except Exception as exc:
        print(f"shakedown hook {name} failed: {exc}", file=sys.stderr)
        return ALLOW


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
