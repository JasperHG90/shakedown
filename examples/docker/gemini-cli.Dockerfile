# Point a harness at this with:
#   [harness.gemini-cli]
#   dockerfile = "examples/docker/gemini-cli.Dockerfile"

FROM node:22-slim

# Pin the harness. Its version is part of what you are measuring.
ARG GEMINI_VERSION=0.47.0
RUN npm install -g @google/gemini-cli@${GEMINI_VERSION}

# Whatever your skills need at runtime. Keep this in step with the other
# harness images, or a skill measures differently on each for reasons that
# have nothing to do with the harness.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Convenience only: shakedown cds here itself, and sets HOME and PATH,
# so an image that omits this still works.
WORKDIR /work
