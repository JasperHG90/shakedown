"""`shakedown init`: a config for the harnesses you name, and somewhere to
put cases.

It writes no skill. The skill under test is yours and already exists; what
a fresh repository is missing is the harness description and the directory
cases live in. Writing a specimen skill instead meant the first run
measured a scaffold nobody shipped.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from shakedown.models import CASES_DIR

_HEADER = """\
# Harnesses only. The skill under test is a path given to the entrypoint,
# and its cases live in `{cases_dir}/<slug>.cases.toml`.
"""

#: What a config says when no harness was chosen. It parses, so `case
#: validate` and the rest still work; the commands that need a harness say
#: what is missing rather than failing on a file that will not load.
_NO_HARNESS = """\
# No harness yet. Add one with `shakedown init --harness <name>` in a fresh
# directory to see a worked block, or write your own with the `add-harness`
# skill. Known to `init`: {known}.
"""

CLAUDE_CODE = """\
[harness.claude-code]
start = [
  "claude", "-p", "{prompt}",
  "--output-format", "stream-json", "--verbose",
  "--model", "{model}",
  "--allowedTools", "Bash", "Write", "Read", "Skill",
  "--permission-mode", "acceptEdits",
  "--setting-sources", "project",
  "--session-id", "{sid}",
]
resume = [
  "claude", "-p", "{reply}",
  "--output-format", "stream-json", "--verbose",
  "--model", "{model}",
  "--allowedTools", "Bash", "Write", "Read", "Skill",
  "--permission-mode", "acceptEdits",
  "--setting-sources", "project",
  "--resume", "{sid}",
]
skills = ".claude/skills"
activation_tool = "Skill"
# For `--sandbox container`, declare exactly one of:
#   image      = "ghcr.io/you/claude-code:2.1.220"
#   dockerfile = "docker/claude-code.Dockerfile"

[harness.claude-code.env]
# `tmp` only: your own home, which is what makes that sandbox fast and
# not isolated. A container ignores it and sets its own HOME inside the
# workspace.
HOME = "${HOME}"
# In a container nothing is inherited, and on macOS a subscription login
# lives in the Keychain rather than under $HOME. Mint a token instead:
#   export CLAUDE_CODE_OAUTH_TOKEN=$(claude setup-token)
# CLAUDE_CODE_OAUTH_TOKEN = "${CLAUDE_CODE_OAUTH_TOKEN}"

[harness.claude-code.events]
container = "message.content"

[[matrix]]
harness = "claude-code"
models  = ["claude-opus-5"]
"""

GEMINI_CLI = """\
[harness.gemini-cli]
start = [
  "gemini", "-p", "{prompt}",
  "--output-format", "stream-json",
  "--model", "{model}",
  "--approval-mode", "yolo",
  "--skip-trust",
  "--session-id", "{sid}",
]
resume = [
  "gemini", "-p", "{reply}",
  "--output-format", "stream-json",
  "--model", "{model}",
  "--approval-mode", "yolo",
  "--skip-trust",
  "--resume", "{sid}",
]
skills = ".gemini/skills"
activation_tool = "activate_skill"
# For `--sandbox container`, declare exactly one of:
#   image      = "ghcr.io/you/gemini-cli:0.47.0"
#   dockerfile = "docker/gemini-cli.Dockerfile"

[harness.gemini-cli.env]
# `tmp` only: your own home, which is what makes that sandbox fast and
# not isolated. A container ignores it and sets its own HOME inside the
# workspace.
HOME = "${HOME}"

# Flat records, not blocks nested under a message. Leaving `container`
# unset is what selects that shape.
[harness.gemini-cli.events]
discriminator = "type"
tool_marker   = "tool_use"
name_key      = "tool_name"
args_key      = "parameters"
text_marker   = "message"
text_key      = "content"

[[matrix]]
harness = "gemini-cli"
models  = ["gemini-3.6-flash"]
"""

OPENCODE = """\
# opencode has no flag to set the session id, so the id shakedown generates
# never reaches it and `--continue` resumes instead. That is safe because a
# sandbox is a fresh directory holding exactly one session.
[harness.opencode]
start = [
  "opencode", "run", "{prompt}",
  "--format", "json",
  "--model", "{model}",
  "--auto",
]
resume = [
  "opencode", "run", "{reply}",
  "--format", "json",
  "--model", "{model}",
  "--auto",
  "--continue",
]
skills = ".opencode/skills"
activation_tool = "skill"
# For `--sandbox container`, declare exactly one of:
#   image      = "ghcr.io/you/opencode:1.18.15"
#   dockerfile = "docker/opencode.Dockerfile"

[harness.opencode.env]
# `tmp` only: your own home, which is what makes that sandbox fast and
# not isolated. A container ignores it and sets its own HOME inside the
# workspace.
HOME = "${HOME}"

# The call is a top-level record, but its name and arguments sit under a
# `part` object, so those keys are dotted paths.
[harness.opencode.events]
name_key = "part.tool"
args_key = "part.state.input"
text_key = "part.text"

[[matrix]]
harness = "opencode"
models  = ["opencode/big-pickle"]
"""

#: The harnesses `init` can write. Adding one is a block here plus a name.
HARNESSES = {
    "claude-code": CLAUDE_CODE,
    "gemini-cli": GEMINI_CLI,
    "opencode": OPENCODE,
}


def scaffold(config: Path, harnesses: Sequence[str] = ()) -> list[Path]:
    """Write the config and the cases directory. Refuses to overwrite.

    Any number of harnesses, including none. None is a real starting point:
    the config still parses, so the free commands work, and you add a
    harness when you know which one you are shipping to. Several is the
    normal end state, since measuring one harness answers nothing about
    the next.

    The cases directory is always `shakedowns/`, beside the config, and is
    not configurable: `find_cases` looks for that name and nothing else, so
    a scaffold that wrote anywhere else would produce a layout the rest of
    the tool cannot discover.

    The `.gitkeep` is what makes it survive a clone. An empty directory is
    not a thing git records, and a `shakedowns/` that vanishes takes the
    convention with it.
    """
    # A bare string is a sequence of characters, so it would be read as one
    # unknown harness per letter. Refuse rather than report that.
    if isinstance(harnesses, str):
        raise TypeError(f"harnesses is a list of names, not {harnesses!r}")

    known = ", ".join(HARNESSES)
    # Every name checked before anything is written, so a typo in the
    # second `--harness` does not leave a config holding only the first.
    if unknown := [name for name in harnesses if name not in HARNESSES]:
        named = ", ".join(repr(name) for name in unknown)
        raise ValueError(f"unknown harness {named}; choose from: {known}")

    # Deduplicated, in the order given: two blocks for one harness is a
    # config that will not load.
    chosen = list(dict.fromkeys(harnesses))
    body = "\n".join(HARNESSES[name] for name in chosen) or _NO_HARNESS.format(known=known)

    files = {
        config: _HEADER.format(cases_dir=CASES_DIR) + "\n" + body,
        config.parent / CASES_DIR / ".gitkeep": "",
    }
    if clashes := sorted(str(p) for p in files if p.exists()):
        raise FileExistsError("refusing to overwrite: " + ", ".join(clashes))

    # Directories first: a write that fails halfway leaves a config behind
    # that the retry then refuses to overwrite, wedging the user.
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
    for path, text in files.items():
        path.write_text(text)
    return sorted(files)


__all__ = ["CASES_DIR", "HARNESSES", "scaffold"]
