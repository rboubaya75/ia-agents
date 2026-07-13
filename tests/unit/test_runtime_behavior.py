from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest

import httpx

os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing-access-key",
    "AWS_SECRET_ACCESS_KEY": "testing-secret-key",
    "AWS_SESSION_TOKEN": "testing-session-token",
    "AWS_DEFAULT_REGION": "eu-west-3",
    "AWS_REGION": "eu-west-3",
    "AWS_EC2_METADATA_DISABLED": "true",
    "MEMORY_ID": "",
    "GATEWAY_URL": "https://bedrock-agentcore.eu-west-3.amazonaws.com/gateways/test/mcp",
    "GATEWAY_AUTH_MODE": "aws_iam",
    "REQUIRE_MCP_TOOLS": "true",
    "MCP_CONNECT_TIMEOUT_SECONDS": "2",
    "MCP_READ_TIMEOUT_SECONDS": "6",
    "MCP_WRITE_TIMEOUT_SECONDS": "5",
    "MCP_POOL_TIMEOUT_SECONDS": "2",
})

MODULE_PATH = Path(__file__).resolve().parents[2] / "deploy-agentcore" / "agents" / "phase_4_robust.py"
SPEC = importlib.util.spec_from_file_location("secure_runtime_robustness", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load Runtime module from {MODULE_PATH}")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)
SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"


class RuntimeBehaviorTests(unittest.TestCase):
    def test_validate_request_accepts_only_facade_contract(self) -> None:
        prompt, session_id, actor_id = runtime.validate_request({
            "prompt": " Plan a trip ", "sessionId": SESSION_ID, "trustedIdentity": {"actorId": "user-123"}
        })
        self.assertEqual((prompt, session_id, actor_id), ("Plan a trip", SESSION_ID, "user-123"))

    def test_validate_request_rejects_extra_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "Untrusted identity fields"):
            runtime.validate_request({
                "prompt": "Plan a trip", "sessionId": SESSION_ID,
                "trustedIdentity": {"actorId": "user-123"}, "userId": "attacker"
            })

    def test_validate_request_rejects_extended_trusted_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "server-generated trustedIdentity"):
            runtime.validate_request({
                "prompt": "Plan a trip", "sessionId": SESSION_ID,
                "trustedIdentity": {"actorId": "user-123", "groups": ["admin"]},
            })

    def test_sigv4_auth_signs_agentcore_gateway_request(self) -> None:
        auth = runtime.AgentCoreSigV4Auth("eu-west-3")
        request = httpx.Request(
            "POST", "https://bedrock-agentcore.eu-west-3.amazonaws.com/gateways/test/mcp",
            headers={"content-type": "application/json"}, content=b'{"jsonrpc":"2.0"}'
        )
        signed = next(auth.auth_flow(request))
        authorization = signed.headers.get("authorization", "")
        self.assertTrue(authorization.startswith("AWS4-HMAC-SHA256 Credential="))
        self.assertIn("/eu-west-3/bedrock-agentcore/aws4_request", authorization)
        self.assertIn("x-amz-date", signed.headers)
        self.assertEqual(signed.headers.get("x-amz-security-token"), "testing-session-token")

    def test_mcp_timeout_budget_is_bounded(self) -> None:
        timeout = runtime.mcp_httpx_timeout()
        self.assertEqual(timeout.connect, 2.0)
        self.assertEqual(timeout.read, 6.0)
        self.assertEqual(timeout.write, 5.0)
        self.assertEqual(timeout.pool, 2.0)
        self.assertIn("get_trips is paginated", runtime.PHASE4_SYSTEM_PROMPT_BASE)


if __name__ == "__main__":
    unittest.main()
