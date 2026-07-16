#!/usr/bin/env python3
"""Validate project Markdown files without external dependencies."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

LOCAL_LINK_PATTERN = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+")
REQUIRED_STATUS_TOKENS = {"NON TESTÉ", "PASS DÉCLARÉ", "PASS PROUVÉ", "FAIL"}


def validate_file(path: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not lines or not lines[0].startswith("# "):
        errors.append(f"{path}: missing level-1 title")
    if text and not text.endswith("\n"):
        errors.append(f"{path}: missing final newline")

    previous_heading_level = 0
    in_fence = False
    for line_number, line in enumerate(lines, start=1):
        if line.startswith("```"):
            in_fence = not in_fence
        if line.rstrip() != line:
            errors.append(f"{path}:{line_number}: trailing whitespace")
        if "\t" in line:
            errors.append(f"{path}:{line_number}: tab character")
        if not in_fence:
            match = HEADING_PATTERN.match(line)
            if match:
                level = len(match.group(1))
                if previous_heading_level and level > previous_heading_level + 1:
                    errors.append(
                        f"{path}:{line_number}: heading jumps from "
                        f"H{previous_heading_level} to H{level}"
                    )
                previous_heading_level = level

    if in_fence:
        errors.append(f"{path}: unclosed fenced code block")

    for link in LOCAL_LINK_PATTERN.findall(text):
        target_text = link.split("#", 1)[0]
        if not target_text:
            continue
        target = (path.parent / target_text).resolve()
        try:
            target.relative_to(repo_root.resolve())
        except ValueError:
            errors.append(f"{path}: local link escapes repository: {link}")
            continue
        if not target.exists():
            errors.append(f"{path}: broken local link: {link}")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)

    repo_root = Path.cwd().resolve()
    errors: list[str] = []
    for path in args.paths:
        if not path.exists():
            errors.append(f"{path}: file does not exist")
            continue
        errors.extend(validate_file(path, repo_root))

    detailed = Path("docs/validation/V1-MEMORY-SECURITY-TESTS-FR.md")
    if detailed in args.paths and detailed.exists():
        text = detailed.read_text(encoding="utf-8")
        missing = sorted(token for token in REQUIRED_STATUS_TOKENS if token not in text)
        if missing:
            errors.append(
                f"{detailed}: missing validation status tokens: {', '.join(missing)}"
            )
        forbidden = "Principe démontré :"
        if forbidden in text:
            errors.append(
                f"{detailed}: ambiguous evidence claim remains: {forbidden}"
            )

    if errors:
        print("Markdown validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(args.paths)} Markdown files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
