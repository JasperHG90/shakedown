"""`shakedown init`: a config and a starter skill.

The scaffold is runnable rather than illustrative, and shaped after
`examples/write-plan`: a skill that must ask for what it was not given and
must go through a CLI to write its artifact. `shakedown run ./my-skill` is
therefore a real measurement on the first try, not a template to fill in.
"""

from __future__ import annotations

from pathlib import Path

from shakedown.models import CASES_DIR, CASES_SUFFIX

CONFIG = """\
# Harnesses only. The skill under test is a path given to the entrypoint.

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

[harness.claude-code.events]
container = "message.content"

[[matrix]]
harness = "claude-code"
models  = ["claude-opus-5"]
"""

SKILL = """\
---
name: {name}
description: Write a short note (NOTE.md) recording a subject and its author. \
Use when someone asks to jot down, record, or write up a note.
---

# {name}

A note needs two facts: what it is about, and who wrote it.

## Ask for what you were not given

Take whatever the request already supplies. For anything missing, ask the
user before writing, and wait for their answer.

Do not invent a value and do not substitute a placeholder like "TBD".

## Write it with notectl, never yourself

`NOTE.md` is written only by the CLI:

```
notectl write --subject <subject> --author <author>
```

Do not create or edit `NOTE.md` with your own file-writing tools, and do
not write it through a shell redirect. The CLI owns the file's format.
"""

CASES = """\
# The skill these cases measure, relative to this file. Cases are what the
# skill is measured against rather than part of what ships, so they live
# out here. A skill that keeps `cases.toml` inside itself still works;
# this location is simply looked for first.
skill = "../{name}"

# A case is a prompt and what must be true afterwards.
# Every check is optional: declare only what applies.

[[case]]
name     = "fully-specified"
prompt   = "Write a note about the Q4 rollout. Author: platform-team."
artifact = "NOTE.md"
tool     = "notectl"

# Withhold something the skill needs, and say how to answer when asked.
# The proof is that the reply reaches the artifact: it is supplied only in
# answer to a question, so it cannot appear unless the harness asked.
[[case]]
name   = "missing-author"
prompt = "Write a note about the Q4 rollout."
tool   = "notectl"

  [[case.artifacts]]
  path     = "NOTE.md"
  contains = ["Q4 rollout"]

  [[case.answers]]
  match = "(?i)\\\\bauthor\\\\b|who wrote|who is writing"
  reply = "platform-team"
"""

CLI = '''\
#!/usr/bin/env python3
"""Render NOTE.md from a fixed template. The deterministic half."""

import argparse
import sys
from pathlib import Path

TEMPLATE = """# {subject}

- **Author:** {author}
"""


def main() -> int:
    """Write NOTE.md, or refuse."""
    p = argparse.ArgumentParser(prog="notectl")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--subject", required=True)
    w.add_argument("--author", required=True)
    w.add_argument("--dir", default=".")
    a = p.parse_args()

    target = Path(a.dir) / "NOTE.md"
    if target.exists():
        print(f"{target} exists; refusing to overwrite", file=sys.stderr)
        return 3
    target.write_text(TEMPLATE.format(subject=a.subject, author=a.author))
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def scaffold(skill_dir: Path, config: Path) -> list[Path]:
    """Write the config and the starter skill. Refuses to overwrite."""
    files = {
        skill_dir / "SKILL.md": SKILL.format(name=skill_dir.name),
        skill_dir.parent / CASES_DIR / f"{skill_dir.name}{CASES_SUFFIX}": CASES.format(
            name=skill_dir.name
        ),
        skill_dir / "bin" / "notectl": CLI,
    }
    if not config.exists():
        files[config] = CONFIG

    if clashes := sorted(str(p) for p in files if p.exists()):
        raise FileExistsError("refusing to overwrite: " + ", ".join(clashes))

    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (skill_dir / "bin" / "notectl").chmod(0o755)
    return sorted(files)
