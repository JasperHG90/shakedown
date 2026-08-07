# Built by the container test. Deliberately trivial: the point is that a
# dockerfile is built and run at all, not what is in it.
FROM python:3.12-slim
RUN echo built-by-shakedown > /shakedown-built
WORKDIR /work
