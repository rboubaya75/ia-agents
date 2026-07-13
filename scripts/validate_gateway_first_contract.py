#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the API Gateway security facade deployment contract.")
    parser.add_argument("--mode", required=True, choices=["frontend-only", "image-only", "runtime-only", "full"])
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--agent-runtime-invoke-url", default="")
    parser.add_argument("--agentcore-gateway-mcp-url", default="")
    parser.add_argument("--agentcore-memory-id", default="")
    parser.add_argument("--runtime-arn", default="")
    parser.add_argument("--facade-function-name", default="")
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


def is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def is_runtime_url(value: str) -> bool:
    parsed = urlparse(value)
    return is_https_url(value) and parsed.netloc.startswith("bedrock-agentcore.") and "/runtimes/" in parsed.path


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def main() -> int:
    options = parse_args()

    print("Ingress target: Browser -> API Gateway JWT -> Lambda security facade -> AgentCore Runtime IAM.")
    print("Tools path: Runtime -> AgentCore Gateway MCP -> tools.")

    if options.mode == "image-only":
        print("Image-only mode does not require deployed ingress or Runtime outputs.")
        return 0

    missing: list[str] = []

    if options.mode in {"frontend-only", "full"}:
        if not is_https_url(options.api_base_url):
            missing.append("api_base_url")
        elif "bedrock-agentcore" in urlparse(options.api_base_url).netloc:
            return fail("api_base_url must reference API Gateway or an application custom domain, not AgentCore Runtime.")

    if options.mode in {"runtime-only", "full"}:
        if not is_runtime_url(options.agent_runtime_invoke_url):
            missing.append("agent_runtime_invoke_url")
        if not is_https_url(options.agentcore_gateway_mcp_url):
            missing.append("agentcore_gateway_mcp_url")
        if not options.agentcore_memory_id:
            missing.append("agentcore_memory_id")
        if not options.runtime_arn:
            missing.append("runtime_arn")
        if not options.facade_function_name:
            missing.append("facade_function_name")

    if options.enforce and missing:
        return fail("Missing secure facade contract outputs: " + ", ".join(missing))

    if missing:
        print("WARNING: Secure facade outputs are incomplete: " + ", ".join(missing))
        print("Deployment continues because enforcement is disabled.")

    print("Secure facade contract validation completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
