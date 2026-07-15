"""Container entrypoint for the Secure AgentCore Runtime.

The HTTP server must become healthy independently from external MCP availability.
Gateway discovery remains lazy and is performed inside the invocation path, where
its bounded retry and error handling already apply.
"""

from __future__ import annotations

from . import phase_4_robust as runtime
from .memory_support import configure_runtime_memory

configure_runtime_memory(runtime.base)
app = runtime.app


def main() -> None:
    """Start the AgentCore HTTP application without blocking on MCP prewarm."""

    app.run()


if __name__ == "__main__":
    main()
