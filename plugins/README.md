# Plugins

The same three hooks for Claude Code and for Gemini CLI, over one set of
scripts. Two copies of a warning drift and then disagree about what the
tool does, so `scripts/shakedown_hooks.py` is the only implementation and
each manifest is a few lines pointing at it.

## Install

```bash
# Claude Code
claude --plugin-dir ./plugins/claude-code

# Gemini CLI
gemini extensions link ./plugins/gemini
```

Both read the shared scripts through their own root variable
(`${CLAUDE_PLUGIN_ROOT}`, `${extensionPath}`), which resolves to the plugin
directory, so the scripts are one level up at `plugins/scripts/`.

That is why the install commands are these two and not the obvious ones.
`claude plugin install` takes a name from a marketplace, not a path.
`gemini extensions install` copies the directory into
`~/.gemini/extensions/`, which leaves the `../scripts` reference pointing
at nothing; `link` resolves the root back to the clone, so it keeps
working. Publishing either plugin standalone would mean vendoring the
script into it.

Both root variables are substituted as plain text into a command the
harness then hands to a shell, so the path is quoted in every hook. Without
the quotes, a clone in a directory whose name contains a space makes
`python3` fail to find the script — and on the `PreToolUse` hook, that
failure exits 2, which is the block code. Every shell command in the
session would be refused.

## What the hooks do

Every one of them is free. They read files, parse TOML, and at most run
`shakedown case validate`, which spends nothing — a hook that cost money
is a hook nobody can afford to leave on.

| Moment | Claude Code | Gemini | What it says |
|---|---|---|---|
| session opens | `SessionStart` | `SessionStart` | shakedown is not installed, or the config declares a variable you have not exported |
| a file is written | `PostToolUse` | `AfterTool` | a cases file does not load, a case measures nothing, or a fixture is not executable |
| before a shell command | `PreToolUse` | `BeforeTool` | **blocks** `case run` when its cases file cannot load; warns otherwise |

A blocking hook speaks on stderr, which both harnesses show to the model.
The warnings cannot: before a tool call, plain output reaches nobody on
Claude Code, and after one it reaches only transcript mode. So the two
tool hooks answer with JSON instead — `systemMessage` for the operator,
and `additionalContext` so the model knows what it just wrote is broken.

Gemini names the same moments differently, and its own bundle ships the
mapping (`PreToolUse: "BeforeTool"`, `PostToolUse: "AfterTool"`). A Claude
event name in the Gemini manifest parses and then never fires, which is
why a test pins each manifest to its own vocabulary.

### Why only one of them blocks

Exit 2 stops the command and shows the message to the model. That is worth
doing exactly when the spend is certainly wasted, and a cases file that
does not load is the one case where it is: the check is free, the answer is
deterministic, and a run against an unloadable file cannot produce a
number.

Everything else warns. A case that measures nothing but `skill_fired` is a
weak case rather than a broken one, and whether to spend on it is yours to
decide. `--sandbox container` with Docker stopped fails in seconds without
spending, so blocking buys nothing.

The escape hatch matters here: a hook cannot be bypassed for one
invocation, so if a block is ever wrong the only way past it is turning the
hook off. That is the argument for keeping the blocking set to one
unambiguous condition.

### A warning that looks wrong but is not

`~/.zshrc` and `~/.bashrc` are read by interactive shells only. A hook is
not one, and neither is a tool your editor launches, so a token exported
from there is invisible to both while being plainly present in your
terminal. The session hook says so rather than flatly claiming the
variable is unset, and names the file that would actually fix it:
`~/.zshenv` for zsh, or whatever `$BASH_ENV` points at for bash. Not
`~/.profile` — that is login shells only, so it would leave the problem
exactly where it was. Getting this wrong is how a hook earns being turned
off on its first day.

### The one they catch that you would not

`shakedown.toml` declares its credentials as `${VAR}` references, and an
unset declared variable is an error rather than an empty string — on
purpose, because silently dropping it would change what ran. The cost is
that you meet the problem at load, inside a command you were charged for.
The session hook reads the config and names the missing variables before
you start.

## Working on them

```bash
uv run pytest tests/test_plugin_hooks.py -q
```

The tests load the script by path rather than importing it, because it
ships inside the plugin rather than in the package and has to keep working
for someone who installed the plugin alone. They also assert that every
hook name a manifest invokes exists in the script, that each manifest uses
its own harness's event names, and that both point at the file that is
actually there.

One failure mode worth knowing about, since it is pinned by a test: an
older `shakedown` exits 2 on `case validate` with click's "No such command
'case'" — the same exit code a rejected cases file produces. Without a
capability probe the gate reads a stale install as every file being broken
and blocks every run.
