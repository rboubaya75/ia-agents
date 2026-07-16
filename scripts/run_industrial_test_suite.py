#!/usr/bin/env python3
"""Run industrial V1 contracts and emit a redacted JSON evidence report."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import sys
import time
from typing import Any
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDUSTRIAL_TESTS = ROOT / "tests" / "industrial"
CASE_PATTERN = re.compile(r"test_(v1_[a-z]+_\d{3})_", re.IGNORECASE)


@dataclass(frozen=True)
class CaseEvidence:
    caseId: str
    testId: str
    status: str
    durationMs: float
    errorType: str | None = None
    skipReason: str | None = None


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, stream: Any, descriptions: bool, verbosity: int):
        super().__init__(stream, descriptions, verbosity)
        self.case_evidence: list[CaseEvidence] = []
        self._started: dict[str, float] = {}

    def startTest(self, test: unittest.case.TestCase) -> None:
        self._started[test.id()] = time.perf_counter()
        super().startTest(test)

    @staticmethod
    def _case_id(test: unittest.case.TestCase) -> str:
        method_name = getattr(test, "_testMethodName", "")
        match = CASE_PATTERN.search(method_name)
        if match is None:
            return "UNMAPPED"
        return match.group(1).upper().replace("_", "-")

    def _duration_ms(self, test: unittest.case.TestCase) -> float:
        started = self._started.pop(test.id(), time.perf_counter())
        return round((time.perf_counter() - started) * 1000, 3)

    def _record(
        self,
        test: unittest.case.TestCase,
        status: str,
        *,
        error_type: str | None = None,
        skip_reason: str | None = None,
    ) -> None:
        self.case_evidence.append(
            CaseEvidence(
                caseId=self._case_id(test),
                testId=test.id(),
                status=status,
                durationMs=self._duration_ms(test),
                errorType=error_type,
                skipReason=skip_reason,
            )
        )

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        super().addSuccess(test)
        self._record(test, "PASS")

    def addFailure(self, test: unittest.case.TestCase, err: Any) -> None:
        super().addFailure(test, err)
        self._record(test, "FAIL", error_type=err[0].__name__)

    def addError(self, test: unittest.case.TestCase, err: Any) -> None:
        super().addError(test, err)
        self._record(test, "ERROR", error_type=err[0].__name__)

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self._record(test, "SKIP", skip_reason=reason[:160])

    def addExpectedFailure(self, test: unittest.case.TestCase, err: Any) -> None:
        super().addExpectedFailure(test, err)
        self._record(test, "EXPECTED_FAILURE", error_type=err[0].__name__)

    def addUnexpectedSuccess(self, test: unittest.case.TestCase) -> None:
        super().addUnexpectedSuccess(test)
        self._record(test, "UNEXPECTED_SUCCESS")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-skips",
        action="store_true",
        help="Do not fail the command when a test is skipped.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sys.path.insert(0, str(INDUSTRIAL_TESTS))

    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(INDUSTRIAL_TESTS),
        pattern="test_*.py",
    )
    runner = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult)
    result = runner.run(suite)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)

    statuses: dict[str, int] = {}
    for case in result.case_evidence:
        statuses[case.status] = statuses.get(case.status, 0) + 1

    evidence = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gitSha": os.getenv("GITHUB_SHA", "local"),
        "environment": {
            "python": platform.python_version(),
            "os": platform.system(),
            "architecture": platform.machine(),
            "timezone": os.getenv("TZ", "UTC"),
        },
        "suite": {
            "name": "Secure AgentCore V1 Industrial Test Suite",
            "testsDiscovered": suite.countTestCases(),
            "testsRun": result.testsRun,
            "durationMs": duration_ms,
            "statusCounts": statuses,
            "successful": result.wasSuccessful(),
        },
        "cases": [asdict(case) for case in result.case_evidence],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    skipped = statuses.get("SKIP", 0)
    failed = not result.wasSuccessful() or (skipped > 0 and not args.allow_skips)
    print(
        json.dumps(
            {
                "event": "industrial_test_suite_completed",
                "tests": result.testsRun,
                "passed": statuses.get("PASS", 0),
                "failed": statuses.get("FAIL", 0),
                "errors": statuses.get("ERROR", 0),
                "skipped": skipped,
                "durationMs": duration_ms,
                "evidence": str(args.output),
            },
            separators=(",", ":"),
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
