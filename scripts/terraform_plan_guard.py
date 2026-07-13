#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

METADATA_SCHEMA_VERSION = 1
CRITICAL_RESOURCE_TYPE_PREFIXES = ("aws_bedrockagentcore_",)

CRITICAL_RESOURCE_TYPES = frozenset(
    {
        "aws_apigatewayv2_api",
        "aws_apigatewayv2_authorizer",
        "aws_apigatewayv2_integration",
        "aws_apigatewayv2_route",
        "aws_apigatewayv2_stage",
        "aws_bedrockagentcore_agent_runtime",
        "aws_bedrockagentcore_agent_runtime_endpoint",
        "aws_bedrockagentcore_gateway",
        "aws_bedrockagentcore_gateway_target",
        "aws_bedrockagentcore_memory",
        "aws_bedrockagentcore_resource_policy",
        "aws_cloudfront_distribution",
        "aws_cloudfront_origin_access_control",
        "aws_cognito_user_pool",
        "aws_cognito_user_pool_client",
        "aws_dynamodb_table",
        "aws_ecr_repository",
        "aws_iam_openid_connect_provider",
        "aws_iam_policy",
        "aws_iam_role",
        "aws_iam_role_policy",
        "aws_iam_role_policy_attachment",
        "aws_kms_key",
        "aws_lambda_function",
        "aws_lambda_permission",
        "aws_s3_bucket",
        "aws_s3_bucket_policy",
        "aws_wafv2_web_acl",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze and verify Terraform plan artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze Terraform plan JSON and enforce safety policy.")
    analyze.add_argument("--plan-json", required=True)
    analyze.add_argument("--summary-output", required=True)
    analyze.add_argument(
        "--policy",
        choices=("enforce-critical", "report-only"),
        default="enforce-critical",
    )

    record = subparsers.add_parser("record", help="Create immutable metadata for a Terraform plan artifact.")
    record.add_argument("--plan", required=True)
    record.add_argument("--metadata-output", required=True)
    record.add_argument("--commit-sha", required=True)
    record.add_argument("--stack-path", required=True)
    record.add_argument("--run-id", required=True)
    record.add_argument("--terraform-version", required=True)

    verify = subparsers.add_parser("verify", help="Verify plan metadata and binary digest before apply.")
    verify.add_argument("--plan", required=True)
    verify.add_argument("--metadata", required=True)
    verify.add_argument("--expected-commit-sha", required=True)
    verify.add_argument("--expected-stack-path", required=True)
    verify.add_argument("--expected-run-id", required=True)
    verify.add_argument("--expected-terraform-version", required=True)

    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_actions(actions: list[str]) -> str:
    action_set = set(actions)
    if "create" in action_set and "delete" in action_set:
        return "replace"
    for action in ("delete", "create", "update", "read", "no-op"):
        if action in action_set:
            return action
    return "other"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def is_critical_resource_type(resource_type: str) -> bool:
    return resource_type in CRITICAL_RESOURCE_TYPES or resource_type.startswith(CRITICAL_RESOURCE_TYPE_PREFIXES)


def analyze_plan(plan_path: Path, summary_path: Path, policy: str) -> int:
    plan = load_json(plan_path)
    resource_changes = plan.get("resource_changes", [])
    if not isinstance(resource_changes, list):
        raise ValueError("Terraform plan JSON resource_changes must be a list.")

    counts: Counter[str] = Counter()
    destructive_changes: list[dict[str, str]] = []
    blocked_changes: list[dict[str, str]] = []

    for item in resource_changes:
        if not isinstance(item, dict) or item.get("mode", "managed") != "managed":
            continue
        change = item.get("change") or {}
        actions = change.get("actions") or []
        if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
            raise ValueError("Terraform resource change actions must be a list of strings.")

        classification = classify_actions(actions)
        counts[classification] += 1
        if classification not in {"delete", "replace"}:
            continue

        resource = {
            "address": str(item.get("address", "unknown")),
            "type": str(item.get("type", "unknown")),
            "action": classification,
        }
        destructive_changes.append(resource)
        if is_critical_resource_type(resource["type"]):
            blocked_changes.append(resource)

    lines = [
        "# Terraform plan safety summary",
        "",
        f"Policy: `{policy}`",
        "",
        "| Action | Count |",
        "|---|---:|",
    ]
    for action in ("create", "update", "delete", "replace", "read", "no-op", "other"):
        lines.append(f"| {action} | {counts[action]} |")

    lines.extend(["", "## Destructive changes", ""])
    if destructive_changes:
        lines.extend(["| Address | Type | Action | Critical |", "|---|---|---|---|"])
        blocked_addresses = {item["address"] for item in blocked_changes}
        for item in destructive_changes:
            critical = "yes" if item["address"] in blocked_addresses else "no"
            lines.append(
                f"| `{item['address']}` | `{item['type']}` | `{item['action']}` | {critical} |"
            )
    else:
        lines.append("No delete or replacement action detected.")

    lines.extend(["", "## Decision", ""])
    if policy == "enforce-critical" and blocked_changes:
        lines.append("**BLOCKED** — critical resource deletion or replacement detected.")
    elif destructive_changes:
        lines.append("**REVIEW REQUIRED** — destructive changes are present.")
    else:
        lines.append("**PASS** — no destructive changes detected.")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if policy == "enforce-critical" and blocked_changes:
        for item in blocked_changes:
            print(
                f"ERROR: blocked Terraform {item['action']} on critical resource "
                f"{item['address']} ({item['type']}).",
                file=sys.stderr,
            )
        return 1
    return 0


def record_metadata(
    plan_path: Path,
    metadata_path: Path,
    commit_sha: str,
    stack_path: str,
    run_id: str,
    terraform_version: str,
) -> int:
    if not plan_path.is_file():
        print(f"ERROR: Terraform plan file is missing: {plan_path}", file=sys.stderr)
        return 1

    metadata = {
        "schemaVersion": METADATA_SCHEMA_VERSION,
        "commitSha": commit_sha,
        "stackPath": stack_path,
        "runId": run_id,
        "terraformVersion": terraform_version,
        "planFile": plan_path.name,
        "planSha256": sha256_file(plan_path),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Recorded Terraform plan metadata: {metadata_path}")
    return 0


def verify_metadata(
    plan_path: Path,
    metadata_path: Path,
    expected_commit_sha: str,
    expected_stack_path: str,
    expected_run_id: str,
    expected_terraform_version: str,
) -> int:
    if not plan_path.is_file():
        print(f"ERROR: Terraform plan file is missing: {plan_path}", file=sys.stderr)
        return 1

    try:
        metadata = load_json(metadata_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    expected = {
        "schemaVersion": METADATA_SCHEMA_VERSION,
        "commitSha": expected_commit_sha,
        "stackPath": expected_stack_path,
        "runId": expected_run_id,
        "terraformVersion": expected_terraform_version,
        "planFile": plan_path.name,
        "planSha256": sha256_file(plan_path),
    }

    errors: list[str] = []
    for field, expected_value in expected.items():
        actual_value = metadata.get(field)
        if actual_value != expected_value:
            errors.append(f"{field}: expected {expected_value!r}, got {actual_value!r}")

    if errors:
        print("ERROR: Terraform plan artifact verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Terraform plan artifact verified for "
        f"commit {expected_commit_sha}, stack {expected_stack_path}, run {expected_run_id}."
    )
    return 0


def main() -> int:
    options = parse_args()
    try:
        if options.command == "analyze":
            return analyze_plan(Path(options.plan_json), Path(options.summary_output), options.policy)
        if options.command == "record":
            return record_metadata(
                Path(options.plan),
                Path(options.metadata_output),
                options.commit_sha,
                options.stack_path,
                options.run_id,
                options.terraform_version,
            )
        if options.command == "verify":
            return verify_metadata(
                Path(options.plan),
                Path(options.metadata),
                options.expected_commit_sha,
                options.expected_stack_path,
                options.expected_run_id,
                options.expected_terraform_version,
            )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(f"Unhandled command: {options.command}")


if __name__ == "__main__":
    raise SystemExit(main())
