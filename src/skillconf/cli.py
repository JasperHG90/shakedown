"""A thin front for pytest. Convenience, never a wall.

Three rules: it shells pytest rather than reimplementing it, bare `pytest`
keeps working so CI can use either, and unknown arguments pass straight
through so the CLI never becomes the reason a pytest feature is
unreachable.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from skillconf.config import ConfigError, load

TESTS = Path(__file__).parent / "conformance.py"


def _run(args: argparse.Namespace, passthrough: list[str]) -> int:
    """Translate friendly flags into pytest arguments and exec pytest."""
    argv = [sys.executable, "-m", "pytest", str(TESTS), "-m", "live"]
    if args.harness:
        argv += ["--harness", args.harness]
    if args.repeat:
        argv += ["--repeat", str(args.repeat)]
    if args.case:
        argv += ["-k", args.case]
    if args.keep:
        argv += ["--keep-workspaces"]
    if args.config:
        argv += ["--skillconf-config", args.config]
    return subprocess.run([*argv, *passthrough], check=False).returncode


def _doctor(args: argparse.Namespace, _passthrough: list[str]) -> int:
    """Verify a harness meets the five prerequisites."""
    from skillconf.doctor import diagnose, render

    config = load(Path(args.config) if args.config else None)
    names = [args.harness] if args.harness else list(config.harnesses)
    worst = 0
    for name in names:
        if name not in config.harnesses:
            print(
                f"unknown harness {name!r}; known: {', '.join(config.harnesses)}", file=sys.stderr
            )
            return 2
        harness = config.harnesses[name]
        model = next((t.model for t in config.targets if t.harness.name == name), "")
        checks = diagnose(harness, model=model)
        print(render(name, checks))
        if any(c.required and not c.ok for c in checks):
            worst = 1
    return worst


def _init(args: argparse.Namespace, _passthrough: list[str]) -> int:
    """Scaffold a config next to an example skill."""
    target = Path(args.config or "skillconf.toml")
    if target.exists():
        print(f"{target} already exists; edit it instead", file=sys.stderr)
        return 1
    template = Path(__file__).parent / "templates" / "skillconf.toml"
    target.write_text(template.read_text())
    print(f"wrote {target}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a subcommand."""
    parser = argparse.ArgumentParser(prog="skillconf", description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=None, help="path to skillconf.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the conformance matrix (spends money)")
    run.add_argument("--harness", default=None)
    run.add_argument("--case", default=None, help="substring of a case name")
    run.add_argument("--repeat", type=int, default=None)
    run.add_argument("--keep", action="store_true", help="keep every workspace")
    run.set_defaults(func=_run)

    doctor = sub.add_parser("doctor", help="check a harness against the five prerequisites")
    doctor.add_argument("--harness", default=None)
    doctor.set_defaults(func=_doctor)

    init = sub.add_parser("init", help="scaffold a skillconf.toml")
    init.set_defaults(func=_init)

    known, passthrough = parser.parse_known_args(argv)
    # Everything after a bare `--` is pytest's, verbatim.
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    try:
        return int(known.func(known, passthrough))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
