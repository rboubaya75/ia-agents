"""Bounded transport adapter for the Secure V1 AgentCore Runtime."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.client.streamable_http import streamablehttp_client

try:
    from . import phase_4 as base
except ImportError:  # direct file loading in unit tests
    import importlib.util
    from pathlib import Path

    base_path = Path(__file__).with_name("phase_4.py")
    base_spec = importlib.util.spec_from_file_location("secure_runtime_base", base_path)
    if base_spec is None or base_spec.loader is None:
        raise RuntimeError(f"Unable to load Runtime base module from {base_path}")
    base = importlib.util.module_from_spec(base_spec)
    base_spec.loader.exec_module(base)

MCP_CONNECT_TIMEOUT_SECONDS = float(os.getenv("MCP_CONNECT_TIMEOUT_SECONDS", "2"))
MCP_READ_TIMEOUT_SECONDS = float(os.getenv("MCP_READ_TIMEOUT_SECONDS", "6"))
MCP_WRITE_TIMEOUT_SECONDS = float(os.getenv("MCP_WRITE_TIMEOUT_SECONDS", "5"))
MCP_POOL_TIMEOUT_SECONDS = float(os.getenv("MCP_POOL_TIMEOUT_SECONDS", "2"))

for timeout_name, timeout_value in {
    "MCP_CONNECT_TIMEOUT_SECONDS": MCP_CONNECT_TIMEOUT_SECONDS,
    "MCP_READ_TIMEOUT_SECONDS": MCP_READ_TIMEOUT_SECONDS,
    "MCP_WRITE_TIMEOUT_SECONDS": MCP_WRITE_TIMEOUT_SECONDS,
    "MCP_POOL_TIMEOUT_SECONDS": MCP_POOL_TIMEOUT_SECONDS,
}.items():
    if timeout_value <= 0 or timeout_value > 20:
        raise RuntimeError(
            f"{timeout_name} must be greater than 0 and at most 20 seconds."
        )

if "get_trips is paginated" not in base.PHASE4_SYSTEM_PROMPT_BASE:
    base.PHASE4_SYSTEM_PROMPT_BASE += (
        "- get_trips is paginated: use nextToken only when another page is needed.\n"
    )


def mcp_httpx_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=MCP_CONNECT_TIMEOUT_SECONDS,
        read=MCP_READ_TIMEOUT_SECONDS,
        write=MCP_WRITE_TIMEOUT_SECONDS,
        pool=MCP_POOL_TIMEOUT_SECONDS,
    )


@asynccontextmanager
async def create_iam_mcp_transport(gateway_url: str):
    async with httpx.AsyncClient(
        auth=base.AgentCoreSigV4Auth(base.REGION),
        timeout=mcp_httpx_timeout(),
    ) as client:
        async with streamablehttp_client(gateway_url, http_client=client) as streams:
            yield streams


base.create_iam_mcp_transport = create_iam_mcp_transport
app = base.app
invoke = base.invoke


def __getattr__(name: str) -> Any:
    return getattr(base, name)


if __name__ == "__main__":
    base.initialize_mcp_tools()
    app.run()
