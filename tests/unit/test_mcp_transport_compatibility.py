from __future__ import annotations

from inspect import signature
from pathlib import Path
import unittest

from mcp.client.streamable_http import streamable_http_client


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "deploy-agentcore" / "agents" / "phase_4_robust.py"
REQUIREMENTS = ROOT / "deploy-agentcore" / "requirements.txt"


class MCPTransportCompatibilityTests(unittest.TestCase):
    def test_installed_mcp_client_accepts_preconfigured_http_client(self) -> None:
        parameters = signature(streamable_http_client).parameters

        self.assertIn("http_client", parameters)
        self.assertTrue(parameters["http_client"].kind.name.startswith("KEYWORD"))

    def test_runtime_uses_supported_non_deprecated_client(self) -> None:
        source = RUNTIME.read_text(encoding="utf-8")

        self.assertIn(
            "from mcp.client.streamable_http import streamable_http_client",
            source,
        )
        self.assertIn(
            "streamable_http_client(gateway_url, http_client=client)",
            source,
        )
        self.assertNotIn("streamablehttp_client", source)

    def test_mcp_version_remains_explicitly_pinned(self) -> None:
        requirements = REQUIREMENTS.read_text(encoding="utf-8")

        self.assertIn("mcp==1.28.1", requirements)


if __name__ == "__main__":
    unittest.main()
