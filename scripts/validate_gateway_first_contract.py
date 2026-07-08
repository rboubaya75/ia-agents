#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate native AgentCore Runtime JWT deployment contract.")
    parser.add_argument("--mode", required=True, choices=["frontend-only", "image-only", "runtime-only", "full"])
    parser.add_argument("--api-base-url", default="")
    parser.add_argument("--agent-runtime-invoke-url", default="")
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

    print("Native Runtime JWT target: Browser -> AgentCore Runtime direct HTTPS invoke.")
    print("Tools path remains: Runtime -> AgentCore Gateway MCP -> tools.")

    if options.mode == "image-only":
        print("Image-only mode does not require Runtime JWT outputs.")
        return 0

    if options.mode in {"frontend-only", "full"}:
        if not is_https_url(options.agent_runtime_invoke_url):
            return fail("agent_runtime_invoke_url must be an HTTPS AgentCore Runtime invocation URL.")

    if options.mode not in {"runtime-only", "full"}:
        print("Runtime control-plane contract not required for this mode.")
        return 0

    missing = []
    if not is_https_url(options.agent_runtime_invoke_url):
        missing.append("agent_runtime_invoke_url")
    if not is_https_url(options.agentcore_gateway_mcp_url):
        missing.append("agentcore_gateway_mcp_url")
    if not options.agentcore_memory_id:
        missing.append("agentcore_memory_id")
    if not options.runtime_arn:
        missing.append("runtime_arn")

    if options.enforce and missing:
        return fail(
            "Missing native Runtime JWT Terraform outputs: "
            + ", ".join(missing)
            + ". Runtime must expose direct invoke URL, MCP tools gateway and Memory before runtime/full deploy."
        )

    if missing:
        print("WARNING: Native Runtime JWT outputs are incomplete: " + ", ".join(missing))
        print("Deploy will continue because enforcement is disabled.")

    if options.agentcore_gateway_url:
        print("WARNING: agentcore_gateway_url is set but user ingress should no longer proxy through AgentCore Gateway.")

    print("Native Runtime JWT contract validation completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
