# Point a harness at this with:
#   [harness.opencode]
#   dockerfile = "examples/docker/opencode.Dockerfile"

FROM node:22-slim

# Pin the harness. Its version is part of what you are measuring.
ARG OPENCODE_VERSION=1.18.15
RUN npm install -g opencode-ai@${OPENCODE_VERSION}

# Whatever your skills need at runtime. Keep this in step with the other
# harness images, or a skill measures differently on each for reasons that
# have nothing to do with the harness.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
