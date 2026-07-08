#!/usr/bin/env python3
"""P0 contract checks for API Gateway -> AgentCore Gateway -> Runtime.

This script is intentionally generic. It does not create AWS resources.
It validates the exposed HTTP contract once the P0 route is available.

Example:
  python3 scripts/p0_gateway_contract_check.py \
    --api-url https://example.execute-api.eu-west-3.amazonaws.com/p0/agent/invoke \
    --token "$COGNITO_ACCESS_TOKEN" \
    --cases tests/p0/identity-contract-cases.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class CheckResult:
    case_id: str
    expected_acceptance: bool
    status_code: int
    ok: bool
    elapsed_ms: int
    response_preview: str


def load_cases(path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data.get("positiveCases", []), data.get("negativeCases", [])


def redact(text: str) -> str:
    if not text:
        return ""
    trimmed = text.replace("\n", " ").replace("\r", " ")
    return trimmed[:500]


def call_api(api_url: str, token: str, payload: Dict[str, Any], timeout: int) -> Tuple[int, str, int]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Correlation-Id": f"p0-{int(time.time())}",
        },
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            elapsed_ms = int((time.time() - started) * 1000)
            return response.status, raw, elapsed_ms
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        elapsed_ms = int((time.time() - started) * 1000)
        return exc.code, raw, elapsed_ms


def run_positive(api_url: str, token: str, cases: Iterable[Dict[str, Any]], timeout: int) -> List[CheckResult]:
    results: List[CheckResult] = []
    for case in cases:
        case_id = case["id"]
        status, body, elapsed_ms = call_api(api_url, token, case["body"], timeout)
        ok = 200 <= status < 300
        results.append(
            CheckResult(
                case_id=case_id,
                expected_acceptance=True,
                status_code=status,
                ok=ok,
                elapsed_ms=elapsed_ms,
                response_preview=redact(body),
            )
        )
    return results


def run_negative(api_url: str, token: str, cases: Iterable[Dict[str, Any]], timeout: int) -> List[CheckResult]:
    results: List[CheckResult] = []
    for case in cases:
        case_id = case["id"]
        expected_codes = set(case.get("expected", {}).get("statusCodes", [400, 403]))
        status, body, elapsed_ms = call_api(api_url, token, case["body"], timeout)
        ok = status in expected_codes
        results.append(
            CheckResult(
                case_id=case_id,
                expected_acceptance=False,
                status_code=status,
                ok=ok,
                elapsed_ms=elapsed_ms,
                response_preview=redact(body),
            )
        )
    return results


def print_results(results: List[CheckResult]) -> None:
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(
            f"{status} {result.case_id} "
            f"expected_acceptance={result.expected_acceptance} "
            f"status_code={result.status_code} "
            f"elapsed_ms={result.elapsed_ms} "
            f"response_preview={result.response_preview!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run P0 Gateway identity contract checks.")
    parser.add_argument("--api-url", required=True, help="API Gateway route URL to test.")
    parser.add_argument("--token", required=True, help="Cognito access or ID token. Never printed.")
    parser.add_argument("--cases", default="tests/p0/identity-contract-cases.json", help="Path to JSON test cases.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    positives, negatives = load_cases(args.cases)
    results = []
    results.extend(run_positive(args.api_url, args.token, positives, args.timeout))
    results.extend(run_negative(args.api_url, args.token, negatives, args.timeout))

    print_results(results)
    failed = [result for result in results if not result.ok]
    if failed:
        print(f"P0 contract check failed: {len(failed)} failing case(s).", file=sys.stderr)
        return 1

    print("P0 contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
