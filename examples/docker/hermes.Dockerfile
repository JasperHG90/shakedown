# Point a harness at this with:
#   [harness.hermes]
#   dockerfile = "examples/docker/hermes.Dockerfile"

FROM python:3.12-slim

# Pin the harness. Its version is part of what you are measuring.
ARG HERMES_VERSION=0.19.0

# git is here twice over: the skills need it at runtime, and pip needs it to
# resolve any VCS dependency Hermes pulls.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir hermes-agent==${HERMES_VERSION}

# Convenience only: shakedown cds here itself, and sets HOME and PATH,
# so an image that omits this still works.
WORKDIR /work
