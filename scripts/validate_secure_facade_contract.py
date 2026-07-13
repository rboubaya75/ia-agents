#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEFAULT_STACK_PATH = Path("infra/environments/test")
DEPLOYMENT_MODES = ("frontend-only", "image-only", "runtime-only", "full")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the secure AgentCore V1 deployment contract for a deployment mode.")
    parser.add_argument("--mode", required=True, choices=DEPLOYMENT_MODES)
    parser.add_argument("--stack-path", default=str(DEFAULT_STACK_PATH))
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--agent-invoke-url", default="")
    parser.add_argument("--agent-runtime-invoke-url", default="")
    parser.add_argument("--agentcore-gateway-mcp-url", default="")
    parser.add_argument("--agentcore-memory-id", default="")
    parser.add_argument("--runtime-arn", default="")
    parser.add_argument("--facade-function-name", default="")
    parser.add_argument("--trip-tools-function-name", default="")
    parser.add_argument("--trip-tools-target-id", default="")
    parser.add_argument("--secure-facade-ready", default="")
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


def terraform_output(stack_path: Path, name: str) -> str:
    if not stack_path.is_dir() or shutil.which("terraform") is None:
        return ""
    result = subprocess.run(
        ["terraform", f"-chdir={stack_path}", "output", "-raw", name],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def resolved(options: argparse.Namespace, argument: str, output_name: str) -> str:
    value = getattr(options, argument)
    return value.strip() if value else terraform_output(Path(options.stack_path), output_name)


def is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def is_runtime_url(value: str) -> bool:
    parsed = urlparse(value)
    query = parse_qs(parsed.query, keep_blank_values=True)
    qualifiers = query.get("qualifier", [])
    return (
        is_https_url(value)
        and parsed.netloc.startswith("bedrock-agentcore.")
        and "/runtimes/" in parsed.path
        and set(query) == {"qualifier"}
        and len(qualifiers) == 1
        and bool(qualifiers[0].strip())
    )


def is_agent_invoke_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        is_https_url(value)
        and parsed.path.rstrip("/") == "/agent/invoke"
        and "bedrock-agentcore" not in parsed.netloc
    )


def validate_public_ingress(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if not is_https_url(values["api_base_url"]):
        errors.append("service_url must be a valid HTTPS API Gateway URL")
    elif "bedrock-agentcore" in urlparse(values["api_base_url"]).netloc:
        errors.append("service_url must never reference AgentCore Runtime directly")

    if not is_agent_invoke_url(values["agent_invoke_url"]):
        errors.append("agent_invoke_url must be an HTTPS /agent/invoke application endpoint")

    if values["api_base_url"] and values["agent_invoke_url"]:
        if urlparse(values["api_base_url"]).netloc != urlparse(values["agent_invoke_url"]).netloc:
            errors.append("service_url and agent_invoke_url must use the same API host")

    if not values["facade_function_name"]:
        errors.append("facade_function_name is missing")
    return errors


def validate_runtime_contract(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if not is_runtime_url(values["agent_runtime_invoke_url"]):
        errors.append("agent_runtime_invoke_url must remain a valid technical IAM Runtime URL")
    if values["agent_runtime_invoke_url"] == values["agent_invoke_url"]:
        errors.append("the browser endpoint must not equal the technical Runtime endpoint")

    if not is_https_url(values["agentcore_gateway_mcp_url"]):
        errors.append("agentcore_gateway_mcp_url is missing or invalid")
    if not values["agentcore_memory_id"]:
        errors.append("agentcore_memory_id is missing")
    if not values["runtime_arn"].startswith("arn:") or ":runtime/" not in values["runtime_arn"]:
        errors.append("runtime_arn is missing or invalid")
    if not values["trip_tools_function_name"]:
        errors.append("trip_tools_function_name is missing")
    if not values["trip_tools_target_id"]:
        errors.append("trip_tools_target_id is missing")
    if values["secure_facade_ready"].lower() != "true":
        errors.append("secure_facade_ready is not true")
    return errors


def validate_contract(mode: str, values: dict[str, str]) -> list[str]:
    if mode not in DEPLOYMENT_MODES:
        return [f"unsupported deployment mode: {mode}"]
    if mode == "image-only":
        return []

    errors = validate_public_ingress(values)
    if mode in {"runtime-only", "full"}:
        errors.extend(validate_runtime_contract(values))
    return errors


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def main() -> int:
    options = parse_args()

    print("Ingress: Browser -> API Gateway JWT -> Lambda security facade -> AgentCore Runtime IAM.")
    print("Tools: Runtime IAM -> AgentCore Gateway MCP -> Trip tools Lambda -> DynamoDB.")

    if options.mode == "image-only":
        print("Image-only mode does not require deployed application outputs.")
        return 0

    values = {
        "api_base_url": resolved(options, "api_base_url", "service_url"),
        "agent_invoke_url": resolved(options, "agent_invoke_url", "agent_invoke_url"),
        "agent_runtime_invoke_url": resolved(options, "agent_runtime_invoke_url", "agent_runtime_invoke_url"),
        "agentcore_gateway_mcp_url": resolved(options, "agentcore_gateway_mcp_url", "agentcore_gateway_mcp_url"),
        "agentcore_memory_id": resolved(options, "agentcore_memory_id", "agentcore_memory_id"),
        "runtime_arn": resolved(options, "runtime_arn", "agent_runtime_arn"),
        "facade_function_name": resolved(options, "facade_function_name", "agent_api_facade_function_name"),
        "trip_tools_function_name": resolved(options, "trip_tools_function_name", "trip_tools_lambda_function_name"),
        "trip_tools_target_id": resolved(options, "trip_tools_target_id", "agentcore_trip_tools_target_id"),
        "secure_facade_ready": resolved(options, "secure_facade_ready", "secure_facade_ready"),
    }

    errors = validate_contract(options.mode, values)
    if errors and options.enforce:
        return fail("Secure V1 contract failed: " + "; ".join(errors))
    for error in errors:
        print(f"WARNING: {error}")

    if options.mode == "frontend-only":
        print("Frontend-only mode validated the public API facade contract; Runtime readiness is not changed by this deployment.")
    else:
        print("Complete secure Runtime contract validated.")
    print(f"Secure V1 contract validation completed with {len(errors)} warning(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
