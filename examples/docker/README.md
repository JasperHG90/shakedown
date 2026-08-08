# Container images for the harnesses

The `container` sandbox needs an environment to run a harness in. A harness
declares one of two things, never both:

```toml
image      = "node:22-slim"                        # pulled as-is
dockerfile = "examples/docker/claude-code.Dockerfile"  # built once, then cached
```

An image is right when the harness CLI is already in it. A dockerfile is
right when you have to install the CLI, which is the usual case — and it
lets you pin the version, so the harness you measured is the harness you
can go back to.

```bash
uv run shakedown case run examples/write-plan --sandbox container
```

The build runs at most once per process, keyed on the dockerfile's mtime.
Editing one rebuilds it; nothing else does.

## Why bother

The default `tmp` sandbox is a temp directory on your machine. It is fast,
and it is **not isolated**: the harness can still see your global config,
your other skills, and your credentials. A number from it measures your
laptop as much as the harness. The report records which sandbox ran, so the
two never get confused.

A container has no developer configuration to pick up, so nothing needs a
flag to suppress it — which matters, because the obvious flag for that job
in Claude Code, `--safe-mode`, also turns off skills.

## What goes in one

Two things, and keep them in step across images:

1. **The harness CLI, pinned.** Its version is part of what you measure.
2. **Whatever your skills need at runtime** — `bash`, `python3`, `git`, and
   whatever their own CLIs call. A skill that finds Python in one image and
   not another measures the image, not the harness.

## What does not go in one

The workspace is shakedown's to arrange, and every command it runs starts
with:

```sh
mkdir -p /work/.home && cd /work && export PATH=/work/bin:$PATH HOME=/work/.home …
```

So `WORKDIR`, `ENV HOME` and `ENV PATH` are all overridden and none of them
are needed. The shipped images set `WORKDIR /work` because it makes poking
around by hand pleasant, not because anything requires it.

`HOME` is deliberately a subdirectory of the mount rather than the mount
itself. A harness discovers project skills under `<cwd>/.claude`, so a HOME
equal to the cwd makes that same directory the *user* config directory too:
the harness files its own state there, reads the seeded skill as a user
skill, and — with Claude Code's `--setting-sources project` — never
surfaces it. Every run then reports "never activated" and the skill takes
the blame for the sandbox.

One thing that can genuinely break an image: a `USER` that cannot write the
bind mount. Artifacts are written into `/work`, so if the run cannot write
there, every `artifact_created` fails for a reason that has nothing to do
with the skill. Whether a non-root user can write it depends on the host,
so if you drop privileges, check with `shakedown doctor --sandbox
container` before trusting a matrix.

## Credentials

Nothing is inherited. The container gets only what the harness declares in
`[harness.*.env]`, plus the image's own `PATH`. OAuth tokens sitting in your
home directory are not visible inside, so a harness that authenticates that
way needs an API key passed explicitly:

```toml
[harness.claude-code.env]
ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"
```

A declared variable that is unset on the host is an error rather than an
empty string, because silently dropping it would change what ran.

### On a Claude subscription

An API key is separate billing. To run the container on the subscription you
already pay for, mint a long-lived token on the host and declare that:

```bash
export CLAUDE_CODE_OAUTH_TOKEN=$(claude setup-token)
```

```toml
[harness.claude-code.env]
CLAUDE_CODE_OAUTH_TOKEN = "${CLAUDE_CODE_OAUTH_TOKEN}"
```

Keep it a `${VAR}` reference. A token pasted into the TOML is committed, and
one baked into an image ships to whoever pulls it.

On macOS the subscription login lives in the Keychain rather than in a file
under `$HOME`, which is why mounting a home directory into the container does
not carry it and the token is the way in. Drop `HOME = "${HOME}"` for
container runs while you are there: the container sets `HOME=/work` itself,
and pointing it at your own home is the contamination the container is for.

Check it before spending a matrix run:

```bash
shakedown doctor --harness claude-code --sandbox container
```
