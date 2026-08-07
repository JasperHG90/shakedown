# Point a harness at this with:
#   [harness.claude-code]
#   dockerfile = "examples/docker/claude-code.Dockerfile"

FROM node:22-slim

# Pin the harness. Its version is part of what you are measuring.
ARG CLAUDE_VERSION=2.1.220
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_VERSION}

# Whatever your skills need at runtime. The example skill's `planctl` is a
# Python script, so without python3 it cannot execute.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# shakedown mounts the workspace here.
WORKDIR /work
