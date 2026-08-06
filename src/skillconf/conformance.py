"""The conformance tests themselves.

One test per (target, case, run). Marked `live` because each one spends
money against a real harness, so `pytest` alone never fires them by
accident.
"""

from __future__ import annotations

import pytest

from skillconf.checks import Result, Status

pytestmark = pytest.mark.live


def _one(results: list[Result], name: str) -> Result:
    """Return the named check."""
    return next(r for r in results if r.name == name)


def test_skill_fired(conformance: list[Result]) -> None:
    """The skill activated at runtime.

    A precondition rather than a score. When this fails the run measured the
    base model, and the three checks below are reported NOT_TRIGGERED so a
    trigger-rate problem cannot masquerade as a conformance regression.
    """
    result = _one(conformance, "skill_fired")
    assert result.ok, result.reason


def test_tool_used(conformance: list[Result]) -> None:
    """The deterministic CLI was invoked rather than imitated."""
    result = _one(conformance, "tool_used")
    if result.status is Status.NOT_TRIGGERED:
        pytest.skip(result.reason)
    assert result.ok, result.reason


def test_artifact_created(conformance: list[Result]) -> None:
    """The expected artifact appeared and is non-empty."""
    result = _one(conformance, "artifact_created")
    if result.status is Status.NOT_TRIGGERED:
        pytest.skip(result.reason)
    assert result.ok, result.reason


def test_inputs_resolved(conformance: list[Result]) -> None:
    """Withheld inputs were requested, and the answers reached the artifact."""
    result = _one(conformance, "inputs_resolved")
    if result.status in (Status.NOT_TRIGGERED, Status.UNSUPPORTED):
        pytest.skip(result.reason)
    assert result.ok, result.reason
