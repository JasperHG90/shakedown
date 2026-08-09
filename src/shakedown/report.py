"""The JSON artifact: per-run detail and per-target scores."""

from __future__ import annotations

import json
import warnings
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from shakedown.checks import Result, Status

REPORT_NAME = "shakedown-report.json"
#: Identifies shakedown's own PR comment, so a rerun edits it instead of
#: adding another.
MARKER = "<!-- shakedown-report -->"


class TurnRecord(BaseModel):
    """What one harness invocation did, enough to debug a failure from."""

    index: int
    argv: list[str]
    exit_code: int
    duration_s: float
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    said: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    stream: str = ""
    stderr_tail: str = ""


class RunRecord(BaseModel):
    """One (target, case, run) and how it scored."""

    target: str
    model: str
    case: str
    run: int
    prompt: str = ""
    results: list[Result]
    turns: int = 0
    asked: list[str] = Field(default_factory=list)
    workspace: str = ""
    workspace_kept: bool = False
    duration_s: float = 0.0
    detail: list[TurnRecord] = Field(default_factory=list)

    @property
    def triggered(self) -> bool:
        """Whether the skill activated at all."""
        return all(r.status is not Status.NOT_TRIGGERED for r in self.results)

    @property
    def failed(self) -> list[str]:
        """Names of the checks that failed."""
        return [r.name for r in self.results if r.status is Status.FAIL]

    @property
    def ok(self) -> bool:
        """Whether nothing failed."""
        return not self.failed


#: Runs per case below which a mixed rate is not worth reading as one.
#: A nagging threshold, not a statistical one: ten runs still leave 8/10
#: spanning roughly half the time to almost always, and closing that to
#: ten points either way takes a hundred. Ten is where a live matrix stops
#: being cheap, so it is where the caution stops — not where the number
#: becomes trustworthy.
THIN = 10


class Score(BaseModel):
    """Counts for one (target, dimension), pooled over that target's cases."""

    passed: int = 0
    scored: int = 0
    unsupported: int = 0
    not_triggered: int = 0
    #: Scored runs behind the thinnest case in the pool. `scored` grows
    #: with the number of cases as readily as with `--repeat`, so five
    #: cases run twice reads as ten runs of evidence when it is two runs
    #: of each of five different things. This is what says how hard any
    #: one of them was actually tried.
    per_case: int = 0

    @property
    def rate(self) -> float | None:
        """Pass rate over scored runs, or None if nothing was scored."""
        return self.passed / self.scored if self.scored else None

    @property
    def mixed(self) -> bool:
        """Whether the rate is neither none of the runs nor all of them."""
        return 0 < self.passed < self.scored


class Report(BaseModel):
    """Everything a run produced."""

    skill: str
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sandbox: str = "tmp"
    isolated: bool = False
    runs: list[RunRecord] = Field(default_factory=list)

    def failures(self) -> list[dict[str, Any]]:
        """Every failing run, with what failed and where to look."""
        return [
            {
                "target": r.target,
                "case": r.case,
                "run": r.run,
                "failed": r.failed,
                "reasons": [x.reason for x in r.results if x.status is Status.FAIL],
                "workspace": r.workspace if r.workspace_kept else None,
                "streams": [t.stream for t in r.detail],
            }
            for r in self.runs
            if r.failed
        ]

    def summary(self) -> dict[str, Any]:
        """Counts, and enough to find the failures without reading every run."""
        return {
            "runs": len(self.runs),
            "ok": sum(1 for r in self.runs if r.ok),
            "failed": sum(1 for r in self.runs if r.failed),
            "not_triggered": sum(1 for r in self.runs if not r.triggered),
            "duration_s": round(sum(r.duration_s for r in self.runs), 2),
            "failures": self.failures(),
        }

    def scores(self) -> dict[str, dict[str, Score]]:
        """Counts per target, per dimension."""
        out: dict[str, dict[str, Score]] = defaultdict(lambda: defaultdict(Score))
        by_case: dict[tuple[str, str, str], int] = defaultdict(int)
        for record in self.runs:
            for result in record.results:
                score = out[record.target][result.name]
                if result.status is Status.PASS:
                    score.passed += 1
                    score.scored += 1
                elif result.status is Status.FAIL:
                    score.scored += 1
                elif result.status is Status.UNSUPPORTED:
                    score.unsupported += 1
                else:
                    score.not_triggered += 1
                if result.status in (Status.PASS, Status.FAIL):
                    by_case[record.target, result.name, record.case] += 1

        thinnest: dict[tuple[str, str], int] = {}
        for (target, dimension, _case), count in by_case.items():
            key = (target, dimension)
            thinnest[key] = min(thinnest.get(key, count), count)
        for (target, dimension), count in thinnest.items():
            out[target][dimension].per_case = count
        return {t: dict(d) for t, d in out.items()}

    def markdown(self) -> str:
        """The report as a PR comment.

        Dimensions are columns and targets are rows, because the question a
        reviewer has is "did anything get worse on any harness", and that
        reads across a row.
        """
        counts = self.summary()
        head = MARKER + f"\n### shakedown: `{self.skill}`\n"

        if not self.runs:
            return head + "\nNo scenarios ran.\n"

        verdict = "PASS" if not counts["failed"] else f"FAIL: {counts['failed']}"
        head += (
            f"\n**{counts['ok']}/{counts['runs']} scenarios passed** "
            f"({verdict}) in {counts['duration_s']:.0f}s.\n\n"
        )

        scores = self.scores()
        dims = sorted({d for by_target in scores.values() for d in by_target})
        rows = ["| target | " + " | ".join(dims) + " |", "|---" * (len(dims) + 1) + "|"]
        for target in sorted(scores):
            cells = []
            for dim in dims:
                score = scores[target].get(dim)
                if score is None or score.rate is None:
                    cells.append("n/a")
                else:
                    cells.append(f"{score.rate:.0%} ({score.scored})")
            rows.append(f"| {target} | " + " | ".join(cells) + " |")
        body = head + "\n".join(rows) + "\n"

        if failures := self.failures():
            listed = "\n".join(
                f"- **{f['case']}** run {f['run']} on `{f['target']}`\n"
                + "\n".join(
                    f"  - `{name}`: {reason}"
                    for name, reason in zip(f["failed"], f["reasons"], strict=True)
                )
                for f in failures
            )
            body += (
                f"\n<details><summary>{len(failures)} failing scenario"
                f"{'' if len(failures) == 1 else 's'}</summary>\n\n{listed}\n\n</details>\n"
            )

        note = "not isolated, so the numbers include whatever else the harness could see"
        body += f"\n<sub>sandbox: `{self.sandbox}`"
        body += f" ({note})</sub>\n" if not self.isolated else "</sub>\n"

        # The reader of a PR comment did not run the matrix and does not
        # know the repeat count, so a percentage here is read straighter
        # than the same percentage in the terminal that produced it.
        if thin := sorted(
            f"`{target}` {dim}"
            for target, dims in scores.items()
            for dim, score in dims.items()
            if score.mixed and score.per_case < THIN
        ):
            body += (
                f"\n<sub>{', '.join(thin)}: a mixed rate over fewer than {THIN} runs "
                "per case, so read it as a hint rather than a frequency.</sub>\n"
            )
        return body

    @classmethod
    def merge(cls, shards: list[Path]) -> Report:
        """Combine per-worker shards into one report.

        A shard that will not parse is skipped rather than raised on. It
        means one worker died mid-write; losing its runs is bad, and
        losing every other worker's runs along with it is worse.
        """
        loaded = []
        for shard in sorted(shards):
            try:
                loaded.append(cls.model_validate_json(shard.read_text()))
            except ValueError:
                warnings.warn(f"unreadable shard {shard.name}; its runs are missing", stacklevel=2)
        if not loaded:
            raise ValueError("no shards to merge")
        first = loaded[0]
        return first.model_copy(update={"runs": [r for shard in loaded for r in shard.runs]})

    def write(self, path: Path) -> Path:
        """Write the artifact, scores included."""
        payload = self.model_dump(mode="json")
        payload["summary"] = self.summary()
        for record, dumped in zip(self.runs, payload["runs"], strict=True):
            dumped["ok"] = record.ok
            dumped["failed"] = record.failed
        payload["scores"] = {
            target: {dim: score.model_dump() | {"rate": score.rate} for dim, score in dims.items()}
            for target, dims in self.scores().items()
        }
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return path
