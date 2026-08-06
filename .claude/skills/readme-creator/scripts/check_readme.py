#!/usr/bin/env python3
"""Validate a README.md against the readme-creator structural rules."""

import re
import sys
from pathlib import Path

# Section labels we expect, in rough order of appearance.
SECTIONS = [
    (r"(?i)^#{1,2}\s+(why|vision|purpose|about|what|problem)"),
    (r"(?i)^#{1,2}\s+(features|capabilities|what it does)"),
    (r"(?i)^#{1,2}\s+(quick[\s-]?start|getting[\s-]started|usage|how to use|try it)"),
    (r"(?i)^#{1,2}\s+(install|installation|setup|requirements)"),
    (r"(?i)^#{1,2}\s+(screenshots?|how[- ]?to|examples?|demo|tutorial)"),
    (r"(?i)^#{1,2}\s+(contributing|development|dev|contributors|license)"),
]

JARGON = {"CLI", "API", "SDK", "JWT", "ORM", "SQL", "HTTP", "URL", "JSON", "YAML"}


def check_logo(text: str) -> tuple[bool, str]:
    """Return (passed, message) for logo placement."""
    first_lines = "\n".join(text.splitlines()[:25])
    if re.search(r'<p\s+align\s*=\s*["\']center["\']', first_lines) and re.search(
        r'<img\s+[^>]*src\s*=\s*["\'][^"\']*logo[^"\']*["\']', first_lines
    ):
        return True, "Logo found centered near top."
    if re.search(r'<img\s+[^>]*src\s*=\s*["\'][^"\']*logo[^"\']*["\']', first_lines):
        return (
            False,
            "Logo image found near top but not centered. Wrap it in <p align='center'>.",
        )
    return False, "No centered logo found in the first 25 lines."


def check_section_order(text: str) -> tuple[bool, str]:
    """Return (passed, message) for ladder-of-abstraction section order."""
    lines = text.splitlines()
    found_indices: list[int] = []
    for pattern in SECTIONS:
        for idx, line in enumerate(lines):
            if re.search(pattern, line):
                found_indices.append(idx)
                break

    if len(found_indices) < 3:
        return (
            False,
            f"Only {len(found_indices)} ladder sections detected; expected at least 3.",
        )

    if found_indices == sorted(found_indices):
        return True, f"Ladder sections appear in order ({len(found_indices)} found)."
    return False, "Ladder sections appear out of order."


def check_install_codeblock(text: str) -> tuple[bool, str]:
    if re.search(r"(?i)^#{1,2}\s+(install|installation|setup)", text, re.MULTILINE):
        match = re.search(
            r"(?i)^#{1,2}\s+(install|installation|setup).*?(```+\w*\n.*?)\n```+",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if not match:
            return False, "Install section is missing a fenced code block."
    return True, "Install section has a fenced code block or no install section exists."


def check_code_languages(text: str) -> tuple[bool, list[str]]:
    """Return (passed, warnings) for code blocks without language tags."""
    warnings: list[str] = []
    for match in re.finditer(r"```(\s*)\n", text):
        if match.group(1).strip() == "":
            line_no = text[: match.start()].count("\n") + 1
            warnings.append(f"Code block without language tag at line {line_no}.")
    return len(warnings) == 0, warnings


def check_heading_hierarchy(text: str) -> tuple[bool, list[str]]:
    """Return (passed, warnings) for skipped heading levels."""
    warnings: list[str] = []
    prev = 0
    for match in re.finditer(r"^(#{1,6})\s+", text, re.MULTILINE):
        level = len(match.group(1))
        line_no = text[: match.start()].count("\n") + 1
        if prev and level > prev + 1:
            warnings.append(
                f"Heading level jumps from {prev} to {level} at line {line_no}."
            )
        prev = level
    return len(warnings) == 0, warnings


def check_jargon(text: str) -> tuple[bool, list[str]]:
    """Flag acronyms that appear without being spelled out earlier."""
    warnings: list[str] = []
    paragraphs = text.split("\n\n")
    for acronym in JARGON:
        pattern = re.compile(rf"\b{acronym}\b")
        for para in paragraphs:
            if pattern.search(para):
                # Simple heuristic: acronym is OK if the paragraph also contains the
                # spelled-out form nearby (naive check).
                if not re.search(
                    rf"(?i)({acronym.lower()})\b.*?(\b{acronym}\b)|(\b{acronym}\b).*?(\b{acronym.lower()}\b)",
                    para,
                ):
                    line_no = text.find(para.splitlines()[0])
                    if line_no >= 0:
                        line_no = text[:line_no].count("\n") + 1
                        warnings.append(
                            f"Acronym '{acronym}' at line {line_no} may need definition."
                        )
                break
    return len(warnings) == 0, warnings


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <README.md>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 2

    text = path.read_text(encoding="utf-8")
    results: list[tuple[str, bool, str | list[str]]] = []

    results.append(("Logo placement", *check_logo(text)))
    results.append(("Section order", *check_section_order(text)))
    results.append(("Install code block", *check_install_codeblock(text)))
    results.append(("Code languages", *check_code_languages(text)))
    results.append(("Heading hierarchy", *check_heading_hierarchy(text)))
    results.append(("Jargon definitions", *check_jargon(text)))

    hard_fail = False
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {name}")
        if isinstance(detail, list):
            for item in detail:
                print(f"  - {item}")
        elif detail:
            print(f"  - {detail}")
        if not passed and name in {"Logo placement", "Section order"}:
            hard_fail = True

    print()
    if hard_fail:
        print("Hard failures detected (logo or section order).")
        return 1
    print("Structural checks complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
