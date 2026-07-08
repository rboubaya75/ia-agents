#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

RUNTIME_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,47}$")
ENDPOINT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
IMAGE_TAG_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
ECR_URI_PATTERN = re.compile(
    r"^(?P<account>[0-9]{12})\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com/(?P<repository>[A-Za-z0-9._/-]+)$"
)
SUPPORTED_AGENTCORE_PLATFORM = "linux/arm64"


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight checks for the test application deployment workflow.")
    parser.add_argument("--mode", required=True, choices=["frontend-only", "image-only", "runtime-only", "full"])
    parser.add_argument("--requested-image-tag", required=True)
    parser.add_argument("--resolved-image-tag", required=True)
    parser.add_argument("--image-platform", required=True)
    parser.add_argument("--ecr-repository-url", default="")
    parser.add_argument("--runtime-name", default="")
    parser.add_argument("--runtime-role-arn", default="")
    parser.add_argument("--model-id", default="")
    parser.add_argument("--endpoint-name", default="default")
    parser.add_argument("--region", required=True)
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--frontend-bucket-name", default="")
    parser.add_argument("--cloudfront-distribution-id", default="")
    parser.add_argument("--cognito-user-pool-id", default="")
    parser.add_argument("--cognito-web-client-id", default="")
    return parser.parse_args()


def normalize_runtime_name(raw_name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name or not name[0].isalpha():
        name = f"A_{name}"
    return name[:48]


def ecr_repository_name(ecr_url: str) -> Optional[str]:
    match = ECR_URI_PATTERN.match(ecr_url)
    if not match:
        return None
    return match.group("repository")


def check_frontend(options: argparse.Namespace, result: CheckResult) -> None:
    if options.mode not in {"frontend-only", "full"}:
        return

    required = {
        "frontend_bucket_name": options.frontend_bucket_name,
        "cloudfront_distribution_id": options.cloudfront_distribution_id,
        "cognito_user_pool_id": options.cognito_user_pool_id,
        "cognito_web_client_id": options.cognito_web_client_id,
    }

    # In full mode the native Runtime JWT invoke URL is created/refreshed by the
    # Terraform apply later in the workflow, before the frontend .env is generated.
    if options.mode == "frontend-only":
        required["api_base_url"] = options.api_base_url

    missing = [name for name, value in required.items() if not value]
    if missing:
        result.error(f"Missing frontend outputs: {', '.join(missing)}")


def check_image(options: argparse.Namespace, result: CheckResult) -> None:
    if options.mode not in {"image-only", "full", "runtime-only"}:
        return

    if not IMAGE_TAG_PATTERN.match(options.requested_image_tag):
        result.error(f"Invalid requested image tag: {options.requested_image_tag}")
    if not IMAGE_TAG_PATTERN.match(options.resolved_image_tag):
        result.error(f"Invalid resolved image tag: {options.resolved_image_tag}")

    if options.mode in {"image-only", "full"} and options.image_platform != SUPPORTED_AGENTCORE_PLATFORM:
        result.error(
            f"AgentCore Runtime image must be built for {SUPPORTED_AGENTCORE_PLATFORM}; got {options.image_platform}"
        )

    if options.mode == "runtime-only" and options.requested_image_tag == "test":
        result.error(
            "runtime-only requires an explicit existing immutable image tag. "
            "Use full or image-only when requested image_tag=test so the workflow can build a unique tag first."
        )

    repository_name = ecr_repository_name(options.ecr_repository_url)
    if not repository_name:
        result.error(f"Invalid ECR repository URL: {options.ecr_repository_url}")
        return

    if options.mode in {"image-only", "full"}:
        check_ecr_tag(options, repository_name, result)


def check_ecr_tag(options: argparse.Namespace, repository_name: str, result: CheckResult) -> None:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except Exception as exc:  # pragma: no cover - defensive in CI
        result.warn(f"Unable to import boto3 for ECR preflight: {exc}")
        return

    ecr = boto3.client("ecr", region_name=options.region)
    try:
        repo = ecr.describe_repositories(repositoryNames=[repository_name])["repositories"][0]
        tag_mutability = repo.get("imageTagMutability", "UNKNOWN")
        print(f"ECR repository: {repository_name}")
        print(f"ECR image tag mutability: {tag_mutability}")
    except ClientError as exc:
        result.warn(f"Unable to describe ECR repository {repository_name}: {exc.response.get('Error', {}).get('Code')}")
        return

    try:
        ecr.describe_images(repositoryName=repository_name, imageIds=[{"imageTag": options.resolved_image_tag}])
        if tag_mutability == "IMMUTABLE":
            result.error(
                f"ECR image tag already exists and repository is immutable: {repository_name}:{options.resolved_image_tag}"
            )
        else:
            result.warn(f"ECR image tag already exists and will be overwritten: {repository_name}:{options.resolved_image_tag}")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code not in {"ImageNotFoundException"}:
            result.warn(f"Unable to check ECR tag {options.resolved_image_tag}: {code}")


def check_runtime(options: argparse.Namespace, result: CheckResult) -> None:
    if options.mode not in {"runtime-only", "full"}:
        return

    normalized = normalize_runtime_name(options.runtime_name)
    print(f"AgentCore runtime name: {options.runtime_name} -> {normalized}")
    if not RUNTIME_NAME_PATTERN.match(normalized):
        result.error(f"Invalid AgentCore runtime name after normalization: {normalized}")

    if not ENDPOINT_NAME_PATTERN.match(options.endpoint_name):
        result.error(f"Invalid endpoint name: {options.endpoint_name}")

    if not options.runtime_role_arn.startswith("arn:") or ":role/" not in options.runtime_role_arn:
        result.error(f"Invalid runtime execution role ARN: {options.runtime_role_arn}")

    if not options.model_id:
        result.error("Missing AgentCore runtime model id")
    elif options.model_id.startswith("us.") and not options.region.startswith("us-"):
        result.warn(
            f"Model id looks like a US cross-region inference profile ({options.model_id}) while runtime region is {options.region}. "
            "Verify Bedrock model access before E2E tests."
        )

    try:
        import boto3
    except Exception as exc:  # pragma: no cover - defensive in CI
        result.warn(f"Unable to import boto3 for AgentCore SDK preflight: {exc}")
        return
    services = set(boto3.session.Session(region_name=options.region).get_available_services())
    if "bedrock-agentcore-control" not in services:
        result.error("Installed boto3/botocore does not expose bedrock-agentcore-control service.")
    if "bedrock-agentcore" not in services:
        result.warn("Installed boto3/botocore does not expose bedrock-agentcore runtime service for Lambda-style invocation checks.")


def print_result(result: CheckResult) -> int:
    for warning in result.warnings:
        print(f"::warning::{warning}")
    if result.errors:
        for error in result.errors:
            print(f"::error::{error}")
        print(f"Preflight failed with {len(result.errors)} error(s) and {len(result.warnings)} warning(s).")
        return 1
    print(f"Preflight passed with {len(result.warnings)} warning(s).")
    return 0


def main() -> int:
    options = parse_args()
    result = CheckResult()
    print(f"Application deploy mode: {options.mode}")
    print(f"Requested image tag: {options.requested_image_tag}")
    print(f"Resolved image tag: {options.resolved_image_tag}")
    print(f"Image platform: {options.image_platform}")

    check_frontend(options, result)
    check_image(options, result)
    check_runtime(options, result)
    return print_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
