"""Container entrypoint for the Secure AgentCore Runtime.

The HTTP server must become healthy independently from external MCP availability.
Gateway discovery remains lazy and is performed inside the invocation path, where
its bounded retry and error handling already apply.

The pinned MCP SDK exposes ``streamable_http_client`` for callers that provide an
existing ``httpx.AsyncClient``. The deprecated ``streamablehttp_client`` alias has
a different signature and cannot accept ``http_client``.
"""

from __future__ import annotations

from mcp.client.streamable_http import streamable_http_client

from . import phase_4_robust as runtime

# phase_4_robust resolves this module global when the lazy MCP transport starts.
# Override the deprecated alias with the SDK API compatible with http_client=.
runtime.streamablehttp_client = streamable_http_client
app = runtime.app


def main() -> None:
    """Start the AgentCore HTTP application without blocking on MCP prewarm."""

    app.run()


if __name__ == "__main__":
    main()
