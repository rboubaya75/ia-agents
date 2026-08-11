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
        "aws_cloudwatch_log_group",
        "aws_cognito_user_pool",
        "aws_cognito_user_pool_client",
        "aws_dynamodb_table",
        "aws_ecr_repository",
        "aws_ecs_cluster",
        "aws_ecs_service",
        "aws_iam_openid_connect_provider",
        "aws_iam_policy",
        "aws_iam_role",
        "aws_iam_role_policy",
        "aws_iam_role_policy_attachment",
        "aws_kms_alias",
        "aws_kms_key",
        "aws_lambda_function",
        "aws_lambda_permission",
        "aws_lb",
        "aws_nat_gateway",
        "aws_s3_bucket",
        "aws_s3_bucket_policy",
        "aws_subnet",
        "aws_vpc",
        "aws_vpc_endpoint",
        "aws_wafv2_web_acl",
    }
)

# aws_ecs_task_definition is deliberately absent: Terraform reports a new revision as a
# replacement, so listing it here would block every image update.

# ---------------------------------------------------------------------------
# Platform guard rules — V2-LLD-001 §16.6
#
# Three are boolean, two are numeric bounds. The numeric ones are checked on the
# plan, therefore on the values actually applied, which is what distinguishes them
# from a Terraform variable `validation` block: a tfvars overriding one side of the
# §7.3 invariant without the other is exactly the case a per-variable check misses.
# ---------------------------------------------------------------------------

GUARD_RULES_REFERENCE = "V2-LLD-001 §16.6"

CMK_RESOURCE_TYPE = "aws_kms_key"
REST_API_RESOURCE_TYPE = "aws_api_gateway_rest_api"

# Rule 4 checks presence only. The plan can establish that a mechanism exists; it cannot
# establish that it is effective. Correctness is demonstrated by the direct-call proof of
# §15, and its content belongs to V2-LLD-005.
#
# `aws_api_gateway_rest_api_policy` used to count here. It no longer does. A resource
# policy cannot carry the requirement under either of its two available forms: it cannot
# read the secret header CloudFront injects, because `aws:RequestHeader` is not a global
# condition key; and `aws:SourceIp` is evaluated against the *end client* address rather
# than the CloudFront edge that relays the request, so a deny on the CloudFront prefix
# list refuses every request instead of only the direct ones. Counting the policy made
# this rule attest a mechanism that did not exist — the exact false green rule 4 is meant
# to prevent.
SINGLE_PATH_MECHANISM_TYPES = frozenset(
    {
        "aws_wafv2_web_acl_association",
    }
)

ALB_IDLE_TIMEOUT_CEILING_SECONDS = 300
SSE_KEEPALIVE_MULTIPLIER = 4
JWKS_STALE_TOLERANCE_CEILING_SECONDS = 86400


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


def plan_variables(plan: dict[str, Any]) -> dict[str, Any]:
    raw = plan.get("variables") or {}
    if not isinstance(raw, dict):
        raise ValueError("Terraform plan JSON variables must be an object.")
    return {str(name): entry["value"] for name, entry in raw.items() if isinstance(entry, dict) and "value" in entry}


def managed_changes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    resource_changes = plan.get("resource_changes", [])
    if not isinstance(resource_changes, list):
        raise ValueError("Terraform plan JSON resource_changes must be a list.")
    return [item for item in resource_changes if isinstance(item, dict) and item.get("mode", "managed") == "managed"]


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def change_action(item: dict[str, Any]) -> str:
    change = item.get("change") or {}
    actions = change.get("actions") or []
    if not isinstance(actions, list) or not all(isinstance(action, str) for action in actions):
        return "other"
    return classify_actions(actions)


def rule(number: str, title: str, status: str, detail: str) -> dict[str, str]:
    return {"number": number, "title": title, "status": status, "detail": detail}


def _rule_ingestion_service_stays_v3(variables: dict[str, Any]) -> dict[str, str]:
    title = "`enable_ingestion_service` is never true in a V2 environment"
    if "enable_ingestion_service" not in variables:
        return rule("1", title, "skipped", "variable not declared in this stack")
    value = variables["enable_ingestion_service"]
    if value is True:
        return rule("1", title, "fail", "the applicative ingestion pipeline is V3 (V2-ADR-019); V2 ingests through Knowledge Bases")
    return rule("1", title, "pass", f"value `{value}`")


def _rule_log_cmk_preserved(changes: list[dict[str, Any]]) -> dict[str, str]:
    # Scope is every CMK of the plan, not only the log one: a key the guard cannot
    # positively identify as *not* being the log CMK must be treated as if it were.
    title = "the log group CMK is neither deleted nor disabled by the plan"
    keys = [item for item in changes if item.get("type") == CMK_RESOURCE_TYPE]
    if not keys:
        return rule("2", title, "skipped", f"no `{CMK_RESOURCE_TYPE}` in this plan")

    offences: list[str] = []
    for item in keys:
        address = str(item.get("address", "unknown"))
        action = change_action(item)
        if action in {"delete", "replace"}:
            offences.append(f"`{address}` {action}")
            continue
        after = (item.get("change") or {}).get("after")
        if isinstance(after, dict) and after.get("is_enabled") is False:
            offences.append(f"`{address}` disabled")

    if offences:
        return rule(
            "2",
            title,
            "fail",
            f"{', '.join(offences)} — losing the key makes the erasure journal unreadable, therefore the replay impossible",
        )
    return rule("2", title, "pass", f"{len(keys)} CMK inspected")


def _rule_streaming_timeout_invariant(variables: dict[str, Any]) -> dict[str, str]:
    title = "`sse_keepalive_seconds` x 4 <= `alb_idle_timeout_seconds` < 300"
    keepalive = as_number(variables.get("sse_keepalive_seconds"))
    idle = as_number(variables.get("alb_idle_timeout_seconds"))
    if keepalive is None or idle is None:
        return rule("3", title, "skipped", "at least one of the two variables is absent from this stack")

    problems: list[str] = []
    if keepalive * SSE_KEEPALIVE_MULTIPLIER > idle:
        problems.append(f"keep-alive too sparse ({keepalive:g} x {SSE_KEEPALIVE_MULTIPLIER} > {idle:g}): the stream drops")
    if idle >= ALB_IDLE_TIMEOUT_CEILING_SECONDS:
        problems.append(f"idle ALB {idle:g} >= {ALB_IDLE_TIMEOUT_CEILING_SECONDS}: the cut moves to API Gateway, outside our observability")

    if problems:
        return rule("3", title, "fail", "; ".join(problems))
    return rule("3", title, "pass", f"keep-alive {keepalive:g} s, idle ALB {idle:g} s")


def _rule_single_path_mechanism(changes: list[dict[str, Any]]) -> dict[str, str]:
    title = "a CloudFront to API Gateway single path mechanism is present in the plan"
    rest_apis = [
        item
        for item in changes
        if item.get("type") == REST_API_RESOURCE_TYPE and change_action(item) != "delete"
    ]
    if not rest_apis:
        return rule("4", title, "skipped", f"no `{REST_API_RESOURCE_TYPE}` retained by this plan")

    mechanisms = [
        item
        for item in changes
        if item.get("type") in SINGLE_PATH_MECHANISM_TYPES and change_action(item) != "delete"
    ]
    if not mechanisms:
        return rule(
            "4",
            title,
            "skipped",
            "precondition 9 unmet, reported as such rather than blocking: the only mechanism able "
            "to carry it is a WAF rule on the CloudFront secret header, and that is subordinate to "
            "precondition 8 (V2-ADR-016, V2-LLD-001 §7.4). The endpoint stays directly reachable, "
            "which keeps the CloudFront-borne controls advisory — a documented, accepted gap, not "
            "a satisfied requirement",
        )
    return rule("4", title, "pass", f"{len(mechanisms)} mechanism(s) present, effectiveness proven out of plan")


def _rule_jwks_stale_tolerance(variables: dict[str, Any]) -> dict[str, str]:
    title = f"`jwks_stale_tolerance_seconds` <= {JWKS_STALE_TOLERANCE_CEILING_SECONDS}"
    tolerance = as_number(variables.get("jwks_stale_tolerance_seconds"))
    if tolerance is None:
        return rule("5", title, "skipped", "variable not declared in this stack")
    if tolerance > JWKS_STALE_TOLERANCE_CEILING_SECONDS:
        return rule(
            "5",
            title,
            "fail",
            f"{tolerance:g} s — V2-ADR-020 bounds the tolerance in hours, never days: beyond it a durably "
            "unreachable JWKS would keep tokens accepted on non-revocable keys",
        )
    return rule("5", title, "pass", f"{tolerance:g} s")


def evaluate_guard_rules(plan: dict[str, Any]) -> list[dict[str, str]]:
    variables = plan_variables(plan)
    changes = managed_changes(plan)
    return [
        _rule_ingestion_service_stays_v3(variables),
        _rule_log_cmk_preserved(changes),
        _rule_streaming_timeout_invariant(variables),
        _rule_single_path_mechanism(changes),
        _rule_jwks_stale_tolerance(variables),
    ]


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

    guard_rules = evaluate_guard_rules(plan)
    failed_rules = [item for item in guard_rules if item["status"] == "fail"]

    lines.extend(["", f"## Platform guard rules ({GUARD_RULES_REFERENCE})", ""])
    lines.extend(["| # | Rule | Status | Detail |", "|---|---|---|---|"])
    for item in guard_rules:
        lines.append(f"| {item['number']} | {item['title']} | {item['status']} | {item['detail']} |")

    lines.extend(["", "## Decision", ""])
    if policy == "enforce-critical" and (blocked_changes or failed_rules):
        reasons = []
        if blocked_changes:
            reasons.append("critical resource deletion or replacement detected")
        if failed_rules:
            reasons.append(f"{len(failed_rules)} platform guard rule(s) violated")
        lines.append(f"**BLOCKED** — {'; '.join(reasons)}.")
    elif failed_rules:
        lines.append(f"**REVIEW REQUIRED** — {len(failed_rules)} platform guard rule(s) violated, reported only.")
    elif destructive_changes:
        lines.append("**REVIEW REQUIRED** — destructive changes are present.")
    else:
        lines.append("**PASS** — no destructive changes detected, every platform guard rule satisfied or not applicable.")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if policy == "enforce-critical" and (blocked_changes or failed_rules):
        for item in blocked_changes:
            print(
                f"ERROR: blocked Terraform {item['action']} on critical resource "
                f"{item['address']} ({item['type']}).",
                file=sys.stderr,
            )
        for item in failed_rules:
            print(
                f"ERROR: guard rule {item['number']} violated ({GUARD_RULES_REFERENCE}): "
                f"{item['title']} — {item['detail']}",
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
