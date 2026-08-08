# Isolate runs in a container

The default sandbox is a temporary directory on your machine, so the harness
can see whatever else you have installed. Run in a container to remove that.

## Prerequisites

- Docker running.
- An API key for the harness. Browser-login credentials live in your host
  keychain and are not visible inside a container.

## Procedure

### 1. Give the harness an environment

Declare exactly one of `image` or `dockerfile` in the harness block.
Declaring both is refused: one is pulled, the other is built.

```toml
[harness.claude-code]
# either
image = "ghcr.io/you/claude-code:2.1.220"
# or
dockerfile = "examples/docker/claude-code.Dockerfile"
```

A `dockerfile` path is resolved relative to `shakedown.toml`, not to your
working directory, so the same config works whether CI runs from the repo
root or anywhere else. It is built once per run rather than per scenario.

The image holds the harness and whatever your skills need at runtime. A
skill whose `bin/` cannot execute fails its checks for reasons that have
nothing to do with the skill — if your CLI is a Python script, Python has to
be in there.

```dockerfile
FROM node:22-slim
ARG CLAUDE_VERSION=2.1.220
RUN npm i -g @anthropic-ai/claude-code@${CLAUDE_VERSION}
```

Pinning the version is the point: it makes the harness version a property of
the image rather than a flag someone has to remember.

### 2. Pass credentials as environment

The container inherits nothing, so the credential has to be declared:

```toml
[harness.claude-code.env]
ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"
```

Drop `HOME = "${HOME}"` if you had it. A host home directory means nothing
inside the container, and the whole reason to run there is that no host
configuration exists to leak.

On a Claude subscription an API key is separate billing, so mint a
long-lived token on the host and declare that instead:

```bash
export CLAUDE_CODE_OAUTH_TOKEN=$(claude setup-token)
```

```toml
[harness.claude-code.env]
CLAUDE_CODE_OAUTH_TOKEN = "${CLAUDE_CODE_OAUTH_TOKEN}"
```

On macOS that login lives in the Keychain rather than in a file under
`$HOME`, so no amount of mounting carries it in. Keep the value a `${VAR}`
reference: a token written into the TOML gets committed.

### 3. Run

```bash
shakedown doctor --sandbox container --harness claude-code
shakedown run ./my-skill --sandbox container
```

Check with `doctor` first. A broken image fails every scenario, and finding
that out from one canary is cheaper than from a full matrix.

## Verification

The "sandbox not isolated" warning under the results table is gone, and the
report records:

```json
{"sandbox": "container", "isolated": true}
```

`doctor` row 6 should also report far fewer visible skills than it does on
the host — your own installed ones are no longer in scope.

## Troubleshooting

**Every run reports `not_triggered`.** Almost always an unauthenticated
harness. On the host it worked because the harness found your login; in the
container it has only what `[harness.*.env]` declares.

**`no dockerfile at ...`.** The path is resolved against `shakedown.toml`.
The error names the resolved path — check it against where the file actually
is.

**The skill's `bin/` fails to run.** Its interpreter is missing from the
image. `examples/docker/` has one Dockerfile per shipped harness to copy
from.

**It is slower than `tmp`.** The image builds once per run. That is the
trade: `tmp` is fast and honest about not being isolated, `container` is
slower and actually is.

## See also

- [Tutorial: your first run](../tutorials/first-run.md)
- [How-to: add a harness](add-a-harness.md)
- [Reference: `shakedown.toml`](../reference/configuration.md#harnessname)
- [Explanation: why the default is a temp directory](../explanation/design-decisions.md#the-sandbox-default-is-a-temp-directory-not-a-container)
