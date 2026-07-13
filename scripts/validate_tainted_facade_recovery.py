#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ADDRESS = "module.agent_api_facade.aws_lambda_function.this"
RESOURCE_TYPE = "aws_lambda_function"
FUNCTION_NAME = "wildrydes-test-agent-invocation-facade"
RUNTIME = "python3.12"
HANDLER = "lambda_function.handler"
ARCHITECTURES = ["arm64"]
STABLE_FIELDS = ("function_name", "role", "handler", "runtime", "architectures")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def is_destructive(actions: Any) -> bool:
    return isinstance(actions, list) and "delete" in actions


def inspect_plan(plan: dict[str, Any]) -> dict[str, str]:
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("Terraform resource_changes must be a list.")

    destructive = []
    for item in changes:
        if not isinstance(item, dict) or item.get("mode", "managed") != "managed":
            continue
        change = item.get("change") or {}
        if is_destructive(change.get("actions")):
            destructive.append(item)

    if len(destructive) != 1:
        raise ValueError(f"Expected exactly one destructive change, found {len(destructive)}.")

    item = destructive[0]
    if item.get("address") != ADDRESS or item.get("type") != RESOURCE_TYPE:
        raise ValueError(f"Only the exact test facade may be recovered; got {item.get('address')} ({item.get('type')}).")
    if item.get("action_reason") != "replace_because_tainted":
        raise ValueError(f"Replacement reason must be replace_because_tainted, got {item.get('action_reason')!r}.")

    change = item.get("change") or {}
    actions = set(change.get("actions") or [])
    if actions != {"create", "delete"}:
        raise ValueError(f"Expected a replacement action, got {sorted(actions)}.")
    if change.get("replace_paths") not in (None, []):
        raise ValueError(f"Provider force-replacement paths are present: {change.get('replace_paths')!r}.")

    before = change.get("before")
    after = change.get("after")
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("Terraform before/after values are required.")
    for field in STABLE_FIELDS:
        if before.get(field) in (None, "", []) or after.get(field) in (None, "", []):
            raise ValueError(f"Stable field {field} is missing.")
        if before.get(field) != after.get(field):
            raise ValueError(f"Stable field {field} changes during replacement.")

    expected = {
        "function_name": FUNCTION_NAME,
        "runtime": RUNTIME,
        "handler": HANDLER,
        "architectures": ARCHITECTURES,
    }
    for field, expected_value in expected.items():
        if after.get(field) != expected_value:
            raise ValueError(f"Field {field} does not match the approved facade contract.")

    return {
        "address": ADDRESS,
        "function_name": FUNCTION_NAME,
        "role": str(after["role"]),
        "runtime": RUNTIME,
        "handler": HANDLER,
        "architectures": ",".join(ARCHITECTURES),
    }


def verify_aws(configuration: dict[str, Any], expected_role: str) -> None:
    expected = {
        "FunctionName": FUNCTION_NAME,
        "Runtime": RUNTIME,
        "Handler": HANDLER,
        "Architectures": ARCHITECTURES,
        "Role": expected_role,
        "State": "Active",
        "LastUpdateStatus": "Successful",
    }
    errors = [
        f"{field}: expected {value!r}, got {configuration.get(field)!r}"
        for field, value in expected.items()
        if configuration.get(field) != value
    ]
    if errors:
        raise ValueError("AWS Lambda configuration is not safe to untaint: " + "; ".join(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the one-time test facade taint recovery contract.")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect-plan")
    inspect.add_argument("--plan-json", required=True)
    inspect.add_argument("--github-output")
    verify = sub.add_parser("verify-aws")
    verify.add_argument("--configuration-json", required=True)
    verify.add_argument("--expected-role", required=True)
    return parser.parse_args()


def main() -> int:
    options = parse_args()
    try:
        if options.command == "inspect-plan":
            result = inspect_plan(load_json(Path(options.plan_json)))
            print(json.dumps(result, indent=2, sort_keys=True))
            if options.github_output:
                output = Path(options.github_output)
                with output.open("a", encoding="utf-8") as handle:
                    for key, value in result.items():
                        handle.write(f"{key}={value}\n")
            return 0
        if options.command == "verify-aws":
            verify_aws(load_json(Path(options.configuration_json)), options.expected_role)
            print("AWS Lambda facade configuration is active and matches the taint recovery contract.")
            return 0
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(options.command)


if __name__ == "__main__":
    raise SystemExit(main())
