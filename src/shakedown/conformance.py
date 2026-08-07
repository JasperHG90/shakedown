"""The conformance test. Marked live: each run spends money.

One test per (target, case, run), not one per check. The four checks share
a single harness execution, and splitting them across tests made pytest run
the harness once per check.
"""

from __future__ import annotations

import pytest

from shakedown.checks import Result, Status

pytestmark = pytest.mark.live


def test_conformance(conformance: list[Result]) -> None:
    """The skill fired, used its tool, produced its artifact, and resolved inputs."""
    failed = [r for r in conformance if r.status is Status.FAIL]
    triggered = next(r for r in conformance if r.name == "skill_fired")

    if triggered.status is Status.NOT_TRIGGERED:
        pytest.skip(triggered.reason)
    if failed:
        pytest.fail("\n".join(f"{r.name}: {r.reason}" for r in failed), pytrace=False)
