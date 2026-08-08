"""`shakedown init`: a config for one harness, and somewhere to put cases.

It writes no skill. The skill under test is yours and already exists; what
a fresh repository is missing is the harness description and the directory
cases live in. Writing a specimen skill instead meant the first run
measured a scaffold nobody shipped.
"""

from __future__ import annotations

from pathlib import Path

from shakedown.models import CASES_DIR

_HEADER = """\
# Harnesses only. The skill under test is a path given to the entrypoint,
# and its cases live in `{cases_dir}/<slug>.cases.toml`.
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


def scaffold(config: Path, harness: str) -> list[Path]:
    """Write the config and the cases directory. Refuses to overwrite.

    The cases directory is always `shakedowns/`, beside the config, and is
    not configurable: `find_cases` looks for that name and nothing else, so
    a scaffold that wrote anywhere else would produce a layout the rest of
    the tool cannot discover.

    The `.gitkeep` is what makes it survive a clone. An empty directory is
    not a thing git records, and a `shakedowns/` that vanishes takes the
    convention with it.
    """
    if harness not in HARNESSES:
        known = ", ".join(HARNESSES)
        raise ValueError(f"unknown harness {harness!r}; choose one of: {known}")

    files = {
        config: _HEADER.format(cases_dir=CASES_DIR) + "\n" + HARNESSES[harness],
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
