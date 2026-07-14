from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from mcp.client.streamable_http import streamable_http_client


ROOT = Path(__file__).resolve().parents[2]
ROBUST_RUNTIME = ROOT / "deploy-agentcore" / "agents" / "phase_4_robust.py"


class MCPTransportCompatibilityTests(unittest.TestCase):
    def test_streamable_http_client_accepts_preconfigured_http_client(self) -> None:
        parameters = inspect.signature(streamable_http_client).parameters

        self.assertIn("http_client", parameters)

    def test_robust_runtime_uses_current_streamable_http_api(self) -> None:
        source = ROBUST_RUNTIME.read_text(encoding="utf-8")

        self.assertIn(
            "from mcp.client.streamable_http import streamable_http_client",
            source,
        )
        self.assertIn("streamable_http_client(", source)
        self.assertIn("http_client=client", source)
        self.assertNotIn("streamablehttp_client", source)


if __name__ == "__main__":
    unittest.main()
