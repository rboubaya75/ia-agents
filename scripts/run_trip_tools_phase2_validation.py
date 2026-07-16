#!/usr/bin/env python3
"""Run the focused Trip Tools Phase 2 contracts and emit JSON evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from typing import Any


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.outcomes: list[dict[str, str]] = []

    @staticmethod
    def _name(test: unittest.case.TestCase) -> str:
        return test.id().rsplit(".", 1)[-1]

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        super().addSuccess(test)
        self.outcomes.append({"test": self._name(test), "status": "PASS"})

    def addFailure(self, test: unittest.case.TestCase, err: Any) -> None:
        super().addFailure(test, err)
        self.outcomes.append({"test": self._name(test), "status": "FAIL"})

    def addError(self, test: unittest.case.TestCase, err: Any) -> None:
        super().addError(test, err)
        self.outcomes.append({"test": self._name(test), "status": "ERROR"})

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self.outcomes.append({"test": self._name(test), "status": "SKIP"})


class EvidenceRunner(unittest.TextTestRunner):
    resultclass = EvidenceResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("trip-tools-phase2-results.json"),
        help="JSON evidence output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    suite = unittest.defaultTestLoader.discover(
        "tests/unit", pattern="test_trip_tools_phase2.py"
    )
    result = EvidenceRunner(verbosity=2).run(suite)
    assert isinstance(result, EvidenceResult)

    evidence = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "scope": "trip-tools-phase2-contracts",
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "testsRun": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "outcomes": sorted(result.outcomes, key=lambda item: item["test"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
