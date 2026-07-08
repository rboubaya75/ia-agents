#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Gateway-first deployment contract before/after deploy.")
    parser.add_argument("--mode", required=True, choices=["frontend-only", "image-only", "runtime-only", "full"])
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--agentcore-gateway-url", default="")
    parser.add_argument("--agentcore-gateway-mcp-url", default="")
    parser.add_argument("--agentcore-memory-id", default="")
    parser.add_argument("--runtime-arn", default="")
    parser.add_argument("--enforce", action="store_true")
    return parser.parse_args()


def is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def main() -> int:
    options = parse_args()

    print("Gateway-first target: Browser -> API Gateway -> AgentCore Gateway -> Runtime")
    print("Gateway-first tools: Runtime -> AgentCore Gateway MCP -> tools")

    if options.mode == "image-only":
        print("Image-only mode does not require Gateway-first runtime outputs.")
        return 0

    if options.mode in {"frontend-only", "full"}:
        if not is_https_url(options.api_base_url):
            return fail("api_base_url must be an HTTPS Amazon API Gateway URL or an approved HTTPS custom domain.")

    if options.mode not in {"runtime-only", "full"}:
        print("Runtime Gateway contract not required for this mode.")
        return 0

    missing = []
    if not is_https_url(options.agentcore_gateway_url):
        missing.append("agentcore_gateway_url")
    if not is_https_url(options.agentcore_gateway_mcp_url):
        missing.append("agentcore_gateway_mcp_url")
    if not options.agentcore_memory_id:
        missing.append("agentcore_memory_id")

    if options.enforce and missing:
        return fail(
            "Missing Gateway-first Terraform outputs: "
            + ", ".join(missing)
            + ". Add AgentCore Gateway, MCP endpoint, HTTP Runtime Target and Memory outputs before runtime/full deploy."
        )

    if missing:
        print("WARNING: Gateway-first outputs are incomplete: " + ", ".join(missing))
        print("Runtime deploy will continue because enforcement is disabled.")

    if options.runtime_arn:
        print("Runtime ARN output present.")

    print("Gateway-first contract validation completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
