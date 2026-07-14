"""Container entrypoint for the Secure AgentCore Runtime.

The HTTP server must become healthy independently from external MCP availability.
Gateway discovery remains lazy and is performed inside the invocation path, where
its bounded retry and error handling already apply.
"""

from __future__ import annotations

from .phase_4_robust import app


def main() -> None:
    """Start the AgentCore HTTP application without blocking on MCP prewarm."""

    app.run()


if __name__ == "__main__":
    main()
