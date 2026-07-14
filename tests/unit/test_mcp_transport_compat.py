from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from mcp.client.streamable_http import (
    streamable_http_client,
    streamablehttp_client,
)


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "deploy-agentcore" / "agents" / "entrypoint.py"
RUNTIME = ROOT / "deploy-agentcore" / "agents" / "phase_4_robust.py"


class McpTransportCompatibilityTests(unittest.TestCase):
    def test_pinned_sdk_client_accepts_injected_http_client(self) -> None:
        current_parameters = inspect.signature(streamable_http_client).parameters
        deprecated_parameters = inspect.signature(streamablehttp_client).parameters

        self.assertIn("http_client", current_parameters)
        self.assertNotIn("http_client", deprecated_parameters)

    def test_container_entrypoint_overrides_deprecated_runtime_alias(self) -> None:
        entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
        runtime = RUNTIME.read_text(encoding="utf-8")

        self.assertIn("http_client=client", runtime)
        self.assertIn(
            "runtime.streamablehttp_client = streamable_http_client",
            entrypoint,
        )
        self.assertIn("from mcp.client.streamable_http import streamable_http_client", entrypoint)


if __name__ == "__main__":
    unittest.main()
