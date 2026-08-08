"""The hooks the two plugins share. Offline: no harness, no spend.

Loaded by path rather than imported, because the scripts ship inside the
plugins rather than in the package: they have to keep working when a user
installs the plugin without installing this repo.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/scripts/shakedown_hooks.py"


def load() -> ModuleType:
    """The hook script, as a module."""
    spec = importlib.util.spec_from_file_location("shakedown_hooks", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `@dataclass` resolves annotations through
    # `sys.modules[cls.__module__]`, which is not there yet otherwise.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hooks = load()


def _skill(root: Path) -> Path:
    made = root / "my-skill"
    made.mkdir(parents=True)
    (made / "SKILL.md").write_text("---\nname: my-skill\ndescription: d\n---\n")
    return made


def _cases(root: Path, body: str) -> Path:
    (root / "shakedowns").mkdir(exist_ok=True)
    written = root / "shakedowns" / "my-skill.cases.toml"
    written.write_text(body)
    return written


def test_a_declared_variable_that_is_unset_is_named(tmp_path: Path) -> None:
    """shakedown treats it as an error, and meets you at load with it.

    Load is a confusing place to learn that a token is missing, and by
    then the command that told you was a paid one.
    """
    (tmp_path / "shakedown.toml").write_text(
        '[harness.x]\nstart = ["x"]\nskills = ".x"\n\n'
        '[harness.x.env]\nTOKEN = "${SHAKEDOWN_TEST_ABSENT}"\n\n'
        '[[matrix]]\nharness = "x"\nmodels = ["m"]\n'
    )
    absent = hooks.missing_variables(tmp_path / "shakedown.toml")
    assert absent == ["SHAKEDOWN_TEST_ABSENT"]


def test_a_declared_variable_that_is_set_is_not_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise every session opens with a warning nobody can act on."""
    monkeypatch.setenv("SHAKEDOWN_TEST_PRESENT", "x")
    (tmp_path / "shakedown.toml").write_text(
        '[harness.x]\nstart = ["x"]\nskills = ".x"\n\n'
        '[harness.x.env]\nTOKEN = "${SHAKEDOWN_TEST_PRESENT}"\n\n'
        '[[matrix]]\nharness = "x"\nmodels = ["m"]\n'
    )
    assert hooks.missing_variables(tmp_path / "shakedown.toml") == []


def test_the_warning_explains_why_a_set_variable_looks_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook runs in a non-interactive shell, which reads neither
    `~/.zshrc` nor `~/.bashrc`.

    Someone whose terminal plainly has the variable is otherwise told it is
    missing, cannot reconcile that with what they just echoed, and turns
    the hook off. Naming the actual cause is the difference between a
    warning that is actionable and one that is insulting.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHAKEDOWN_TEST_INTERACTIVE_ONLY", raising=False)
    monkeypatch.setattr(hooks, "installed", lambda: True)
    (tmp_path / "shakedown.toml").write_text(
        '[harness.x]\nstart = ["x"]\nskills = ".x"\n\n'
        '[harness.x.env]\nTOKEN = "${SHAKEDOWN_TEST_INTERACTIVE_ONLY}"\n\n'
        '[[matrix]]\nharness = "x"\nmodels = ["m"]\n'
    )

    said = hooks.session_start().say

    assert "SHAKEDOWN_TEST_INTERACTIVE_ONLY" in said
    assert "zshenv" in said, "the remedy has to be a file every shell reads"


def test_a_matrix_override_is_read_too(tmp_path: Path) -> None:
    """`[matrix.env]` is where the gateway token lives, and it is declared
    the same way, so missing it there fails a run just as hard."""
    (tmp_path / "shakedown.toml").write_text(
        '[harness.x]\nstart = ["x"]\nskills = ".x"\n\n'
        '[[matrix]]\nharness = "x"\nmodels = ["m"]\n\n'
        '[matrix.env]\nTOKEN = "${SHAKEDOWN_TEST_GATEWAY}"\n'
    )
    assert hooks.missing_variables(tmp_path / "shakedown.toml") == ["SHAKEDOWN_TEST_GATEWAY"]


def test_an_unparseable_config_warns_about_nothing(tmp_path: Path) -> None:
    """A hook that raises on a half-written file wedges the session."""
    (tmp_path / "shakedown.toml").write_text("this is not toml {{{")
    assert hooks.missing_variables(tmp_path / "shakedown.toml") == []


def test_the_gate_blocks_a_run_whose_cases_cannot_load(tmp_path: Path) -> None:
    """The check is free and certain, so the spend buys nothing."""
    _skill(tmp_path)
    broken = _cases(
        tmp_path, 'skill = "../my-skill"\nfixture = "../x"\n[[case]]\nname="c"\nprompt="p"\n'
    )

    verdict = hooks.decide_run(f"shakedown case run {broken}")

    assert verdict.code == hooks.BLOCK
    assert "does not load" in verdict.say


def test_the_gate_allows_a_run_whose_cases_load(tmp_path: Path) -> None:
    """Blocking a good run would make the hook the thing to turn off."""
    _skill(tmp_path)
    fine = _cases(
        tmp_path,
        'skill = "../my-skill"\n[[case]]\nname="c"\nprompt="p"\ntool="t"\nartifact="A"\n',
    )

    assert hooks.decide_run(f"shakedown case run {fine}").code == hooks.ALLOW


def test_a_weak_case_warns_rather_than_blocks(tmp_path: Path) -> None:
    """Whether to spend on a case that cannot fail is the operator's call."""
    _skill(tmp_path)
    weak = _cases(tmp_path, 'skill = "../my-skill"\n[[case]]\nname="c"\nprompt="p"\n')

    verdict = hooks.decide_run(f"shakedown case run {weak}")

    assert verdict.code == hooks.ALLOW
    assert "measures nothing" in verdict.say


def test_an_installed_cli_without_case_validate_blocks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An older build exits 2 with "No such command 'case'".

    That is the same code a rejected cases file uses, so without the
    capability probe a stale install reads as every file being broken and
    the gate blocks every run.
    """
    _skill(tmp_path)
    broken = _cases(
        tmp_path, 'skill = "../my-skill"\nfixture = "../x"\n[[case]]\nname="c"\nprompt="p"\n'
    )
    monkeypatch.setattr(hooks, "can_validate", lambda: False)

    assert hooks.decide_run(f"shakedown case run {broken}").code == hooks.ALLOW


def test_a_command_that_is_not_a_run_is_left_alone() -> None:
    """The gate sits on every Bash call, so it has to be quiet."""
    assert hooks.before_bash({"tool_input": {"command": "ls -la"}}).code == hooks.ALLOW
    assert hooks.before_bash({"tool_input": {"command": "ls -la"}}).say == ""


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("shakedown case run ./my-skill", ["./my-skill"]),
        ("shakedown case run my-skill", ["my-skill"]),
        ("shakedown case run shakedowns/x.cases.toml", ["shakedowns/x.cases.toml"]),
        ("uv run shakedown case run examples/write-plan", ["examples/write-plan"]),
        ("cd sub && shakedown case run ./my-skill", ["./my-skill"]),
        ("shakedown case run --harness claude-code ./my-skill", ["./my-skill"]),
        ("shakedown case run --keep ./my-skill", ["./my-skill"]),
        ("shakedown case run -j 4 ./my-skill", ["./my-skill"]),
        ("shakedown case run ./a && shakedown case run ./b", ["./a", "./b"]),
        ("shakedown case run ./my-skill -- -x", ["./my-skill"]),
    ],
)
def test_the_argument_is_found_by_position(command: str, expected: list[str]) -> None:
    """`case run` takes a skill directory or a cases file, and the docs all
    pass the directory.

    The first version of this matched a `shakedowns/*.cases.toml` path in
    the command text, so the form every tutorial teaches sailed straight
    past the gate and spent the money.
    """
    assert hooks.targets_of(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "echo 'next: shakedown case run ./my-skill' >> NOTES.md",
        "git commit -m 'docs: explain shakedown case run ./my-skill'",
        "grep -rn 'shakedown case run' .",
        "ls -la",
        "shakedown doctor --harness claude-code",
        "shakedown case validate ./my-skill",
    ],
)
def test_merely_mentioning_the_command_is_not_running_it(command: str) -> None:
    """A hook cannot be bypassed for one call, so a false block stops work.

    Writing about a broken cases file, committing it, and grepping for it
    all happen in exactly the window where it is broken.
    """
    assert hooks.targets_of(command) == []


def test_an_argument_that_is_not_here_is_not_judged(tmp_path: Path) -> None:
    """The command may `cd` first, or name something built later.

    Blocking on a path this process cannot see would be guessing.
    """
    assert hooks.decide_run("shakedown case run ./nowhere-at-all").code == hooks.ALLOW


def test_can_validate_sees_through_an_older_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """click answers an unknown subcommand with exit 2, the same code a
    rejected cases file gets.

    Told apart by asking whether the subcommand exists at all. A stub on
    PATH is the only way to pin this: with the real CLI current, the
    branch is never taken and the test would pass on nothing.
    """
    stale = tmp_path / "bin"
    stale.mkdir()
    (stale / "shakedown").write_text(
        "#!/bin/sh\necho \"Error: No such command 'case'.\" >&2\nexit 2\n"
    )
    (stale / "shakedown").chmod(0o755)
    monkeypatch.setenv("PATH", str(stale))

    assert hooks.installed(), "the stub is on PATH"
    assert not hooks.can_validate()


def test_a_stale_cli_blocks_nothing_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the probe, exercised through the real path."""
    _skill(tmp_path)
    broken = _cases(
        tmp_path, 'skill = "../my-skill"\nfixture = "../x"\n[[case]]\nname="c"\nprompt="p"\n'
    )
    stale = tmp_path / "bin"
    stale.mkdir()
    (stale / "shakedown").write_text(
        "#!/bin/sh\necho \"Error: No such command 'case'.\" >&2\nexit 2\n"
    )
    (stale / "shakedown").chmod(0o755)
    monkeypatch.setenv("PATH", str(stale))

    assert hooks.decide_run(f"shakedown case run {broken}").code == hooks.ALLOW


def test_writing_a_broken_cases_file_says_so(tmp_path: Path) -> None:
    """The moment it is written is the cheapest moment to hear about it."""
    _skill(tmp_path)
    broken = _cases(
        tmp_path, 'skill = "../my-skill"\nfixture = "../x"\n[[case]]\nname="c"\nprompt="p"\n'
    )

    verdict = hooks.after_write({"tool_input": {"file_path": str(broken)}})

    assert verdict.code == hooks.ALLOW
    assert "does not load yet" in verdict.say


def test_writing_a_good_cases_file_says_nothing(tmp_path: Path) -> None:
    """Every Write goes through here, so silence is the common case."""
    _skill(tmp_path)
    fine = _cases(
        tmp_path,
        'skill = "../my-skill"\n[[case]]\nname="c"\nprompt="p"\ntool="t"\nartifact="A"\n',
    )

    assert hooks.after_write({"tool_input": {"file_path": str(fine)}}).say == ""


def test_a_tool_event_returns_its_warning_where_the_model_reads_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An allowing exit prints to stdout, which for a tool event goes to
    the transcript and nobody sees it.

    The documented way back is `additionalContext`, so a warning composed
    and then discarded is the failure worth pinning.
    """
    hooks.Verdict(hooks.ALLOW, "something worth knowing").emit("PostToolUse")

    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert payload["hookSpecificOutput"]["additionalContext"] == "something worth knowing"


def test_a_blocking_verdict_speaks_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    """Exit 2 is the one case where stderr is what reaches the model."""
    hooks.Verdict(hooks.BLOCK, "no").emit("PreToolUse")

    caught = capsys.readouterr()
    assert caught.err.strip() == "no"
    assert caught.out == ""


def test_session_start_speaks_plainly(capsys: pytest.CaptureFixture[str]) -> None:
    """Its stdout already reaches the model, so wrapping it would only
    show the operator a line of JSON."""
    hooks.Verdict(hooks.ALLOW, "plain words").emit("")

    assert capsys.readouterr().out.strip() == "plain words"


def test_a_fixture_that_cannot_execute_is_named(tmp_path: Path) -> None:
    """The shell refuses a 644 double rather than falling through, and the
    error names neither the fixture nor the bit."""
    fixture = tmp_path / "shakedowns" / "fixtures" / "my-skill" / "gh"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("#!/bin/sh\n")
    fixture.chmod(0o644)

    verdict = hooks.after_write({"tool_input": {"file_path": str(fixture)}})

    assert verdict.code == hooks.ALLOW
    assert "not executable" in verdict.say


def test_an_executable_fixture_says_nothing(tmp_path: Path) -> None:
    """The common case has to be silent, or the hook is noise."""
    fixture = tmp_path / "shakedowns" / "fixtures" / "my-skill" / "gh"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("#!/bin/sh\n")
    fixture.chmod(0o755)

    assert hooks.after_write({"tool_input": {"file_path": str(fixture)}}).say == ""


def test_a_hook_that_raises_does_not_wedge_the_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bug in here must never stop someone working."""

    def boom(_: dict[str, Any]) -> None:
        raise RuntimeError("bang")

    monkeypatch.setitem(hooks.HOOKS, "after-write", boom)
    monkeypatch.setattr("sys.stdin", type("S", (), {"read": staticmethod(lambda: "{}")})())

    assert hooks.main(["x", "after-write"]) == hooks.ALLOW
    assert "bang" in capsys.readouterr().err


def test_an_unknown_hook_name_allows(capsys: pytest.CaptureFixture[str]) -> None:
    """A manifest naming a hook that went away must not block either."""
    assert hooks.main(["x", "no-such-hook"]) == hooks.ALLOW
    assert "known:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "manifest",
    [
        REPO / "plugins/claude-code/hooks/hooks.json",
        REPO / "plugins/gemini/hooks/hooks.json",
    ],
    ids=["claude-code", "gemini"],
)
def test_a_manifest_names_hooks_that_exist(manifest: Path) -> None:
    """A typo'd hook name is a hook that silently never runs."""
    declared = json.loads(manifest.read_text())["hooks"]
    named = [
        entry["command"].rsplit(maxsplit=1)[-1]
        for group in declared.values()
        for matcher in group
        for entry in matcher["hooks"]
    ]
    assert named, "a manifest with no hooks is a plugin that does nothing"
    for name in named:
        assert name in hooks.HOOKS, (
            f"{manifest.name} runs {name!r}, which the script has no arm for"
        )


@pytest.mark.parametrize(
    ("manifest", "events"),
    [
        (
            REPO / "plugins/claude-code/hooks/hooks.json",
            {"SessionStart", "PreToolUse", "PostToolUse"},
        ),
        (REPO / "plugins/gemini/hooks/hooks.json", {"SessionStart", "BeforeTool", "AfterTool"}),
    ],
    ids=["claude-code", "gemini"],
)
def test_each_manifest_uses_its_own_harness_event_names(manifest: Path, events: set[str]) -> None:
    """The two harnesses name the same moments differently.

    Gemini ships the mapping in its own bundle: `PreToolUse: "BeforeTool"`,
    `PostToolUse: "AfterTool"`. A Claude event name in the Gemini manifest
    parses and never fires.
    """
    assert set(json.loads(manifest.read_text())["hooks"]) == events


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        (
            REPO / "plugins/claude-code/hooks/hooks.json",
            {"PostToolUse": "Write|Edit", "PreToolUse": "Bash"},
        ),
        (
            REPO / "plugins/gemini/hooks/hooks.json",
            {"AfterTool": "write_file|replace", "BeforeTool": "run_shell_command"},
        ),
    ],
    ids=["claude-code", "gemini"],
)
def test_each_manifest_matches_its_own_harness_tool_names(
    manifest: Path, expected: dict[str, str]
) -> None:
    """A matcher that never matches is a hook that silently never runs.

    Nothing warns about it: the manifest is valid, the plugin loads, and
    the hook simply does not fire. The two harnesses call the same tools
    different things — Gemini's own migration table maps `Edit` to
    `replace` and `Bash` to `run_shell_command` — so a Claude tool name
    left in the Gemini manifest is dead config that looks alive.
    """
    declared = json.loads(manifest.read_text())["hooks"]
    found = {
        event: matcher["matcher"]
        for event, group in declared.items()
        for matcher in group
        if "matcher" in matcher
    }
    assert found == expected


@pytest.mark.parametrize(
    "manifest",
    [
        REPO / "plugins/claude-code/hooks/hooks.json",
        REPO / "plugins/gemini/hooks/hooks.json",
    ],
    ids=["claude-code", "gemini"],
)
def test_the_script_path_is_quoted_in_every_command(manifest: Path) -> None:
    """Both harnesses substitute the root as text, then run a shell.

    Unquoted, a clone under a directory with a space in its name makes
    `python3` fail to open the script. On the pre-tool hook that failure
    exits 2 — the block code — so every shell command in the session is
    refused by a plugin meant to save money.
    """
    for group in json.loads(manifest.read_text())["hooks"].values():
        for matcher in group:
            for entry in matcher["hooks"]:
                command = entry["command"]
                assert '"${' in command, f"unquoted root variable in {command!r}"
                assert command.count('"') == 2, f"the path has to be one quoted word: {command!r}"


@pytest.mark.parametrize(
    "manifest",
    [
        REPO / "plugins/claude-code/hooks/hooks.json",
        REPO / "plugins/gemini/hooks/hooks.json",
    ],
    ids=["claude-code", "gemini"],
)
def test_a_manifest_points_at_the_script_that_is_there(manifest: Path) -> None:
    """Both resolve their own root variable to the same shared script."""
    roots = {
        "${CLAUDE_PLUGIN_ROOT}": manifest.parent.parent,
        "${extensionPath}": manifest.parent.parent,
    }
    for group in json.loads(manifest.read_text())["hooks"].values():
        for matcher in group:
            for entry in matcher["hooks"]:
                command = entry["command"]
                for variable, root in roots.items():
                    command = command.replace(variable, str(root))
                path = Path(shlex.split(command)[1])
                assert path.resolve() == SCRIPT, f"{manifest.name} points at {path}"


def test_the_script_runs_as_a_program(tmp_path: Path) -> None:
    """The manifests invoke it as a file, so it has to work that way."""
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "session-start"],
        input="{}",
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
        check=False,
    )
    assert done.returncode == hooks.ALLOW, done.stderr
