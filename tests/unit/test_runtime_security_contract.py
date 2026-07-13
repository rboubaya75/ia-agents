from __future__ import annotations

import ast
from pathlib import Path
import unittest

RUNTIME_PATH = Path(__file__).resolve().parents[2] / "deploy-agentcore" / "agents" / "phase_4.py"
SOURCE = RUNTIME_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


class RuntimeSecurityContractTests(unittest.TestCase):
    def test_runtime_source_is_valid_python(self) -> None:
        compile(SOURCE, str(RUNTIME_PATH), "exec")

    def test_runtime_no_longer_decodes_browser_jwt(self) -> None:
        forbidden_fragments = (
            "_decode_jwt_claims_unverified",
            "Authorization header",
            "Runtime-validated JWT",
            "import base64",
            "import requests",
        )
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, SOURCE)

    def test_runtime_requires_server_generated_trusted_identity(self) -> None:
        self.assertIn('ALLOWED_REQUEST_FIELDS = {"prompt", "sessionId", "trustedIdentity"}', SOURCE)
        self.assertIn('set(trusted_identity) != {"actorId"}', SOURCE)
        self.assertIn("A server-generated trustedIdentity is required.", SOURCE)

    def test_runtime_signs_gateway_calls_with_sigv4(self) -> None:
        self.assertIn("class AgentCoreSigV4Auth", SOURCE)
        self.assertIn('SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", self.region)', SOURCE)
        self.assertIn('GATEWAY_AUTH_MODE != "aws_iam"', SOURCE)

    def test_all_tools_are_gateway_governed(self) -> None:
        self.assertNotIn("from ddgs import", SOURCE)
        self.assertNotIn("def web_search", SOURCE)
        self.assertNotIn("@tool", SOURCE)
        self.assertIn("tools = initialize_mcp_tools()", SOURCE)

    def test_mcp_initialization_is_fail_closed_and_retryable(self) -> None:
        section = SOURCE.split("def initialize_mcp_tools", 1)[1].split("def response_text", 1)[0]
        success_path = section.split("try:", 1)[1].split("except Exception", 1)[0]
        failure_path = section.split("except Exception", 1)[1]

        self.assertIn("with _mcp_init_lock", section)
        self.assertIn("if REQUIRE_MCP_TOOLS and not candidate_tools", success_path)
        self.assertLess(success_path.index("candidate_tools ="), success_path.index("_mcp_initialized = True"))
        self.assertIn("_mcp_initialized = False", failure_path)
        self.assertIn("if REQUIRE_MCP_TOOLS", failure_path)
        self.assertIn("raise", failure_path)

    def test_tool_identity_is_overwritten_by_runtime(self) -> None:
        self.assertIn('tool_input["userId"] = self.actor_id', SOURCE)

    def test_no_eval_or_exec_calls(self) -> None:
        for node in ast.walk(TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"eval", "exec"})


if __name__ == "__main__":
    unittest.main()
