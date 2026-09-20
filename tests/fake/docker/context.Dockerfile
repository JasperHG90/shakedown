# Built by the container test with a widened `context`, so this COPY
# reaches a file outside its own directory. That copy is the whole point:
# with the default context it fails, which is the bug `context` fixes.
FROM python:3.12-slim
COPY skill/SKILL.md /shakedown-copied-from-context
WORKDIR /work
