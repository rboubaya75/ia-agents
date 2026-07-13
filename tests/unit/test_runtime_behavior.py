from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import time
import unittest
from unittest.mock import MagicMock, Mock

import httpx

os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "test",
        "AWS_SECRET_ACCESS_KEY": "test",
        "AWS_SESSION_TOKEN": "test",
        "AWS_DEFAULT_REGION": "eu-west-3",
        "AWS_REGION": "eu-west-3",
        "AWS_EC2_METADATA_DISABLED": "true",
        "MEMORY_ID": "",
        "GATEWAY_URL": "https://bedrock-agentcore.eu-west-3.amazonaws.com/gateways/test/mcp",
        "GATEWAY_AUTH_MODE": "aws_iam",
        "REQUIRE_MCP_TOOLS": "true",
    }
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "deploy-agentcore" / "agents" / "phase_4.py"
)
SPEC = importlib.util.spec_from_file_location("secure_runtime_behavior", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load Runtime module from {MODULE_PATH}")

runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)

SESSION_ID = "sid-v1-" + ("a" * 64)
OPERATION_ID = "76e6f404-49de-4dc4-9c60-f2c25a0de91f"
REQUEST_ID = "request-1"


def payload(**overrides: object) -> dict:
    value = {
        "prompt": " Plan a trip ",
        "sessionId": SESSION_ID,
        "operationId": OPERATION_ID,
        "requestId": REQUEST_ID,
        "deadlineEpochMs": int(time.time() * 1000) + 30_000,
        "trustedIdentity": {"actorId": "user-123"},
    }
    value.update(overrides)
    return value


class RuntimeBehaviorTests(unittest.TestCase):
    def test_validate_request_accepts_only_facade_contract(self) -> None:
        request = runtime.validate_request(payload())

        self.assertEqual(request.prompt, "Plan a trip")
        self.assertEqual(request.session_id, SESSION_ID)
        self.assertEqual(request.actor_id, "user-123")
        self.assertEqual(request.operation_id, OPERATION_ID)
        self.assertEqual(request.request_id, REQUEST_ID)

    def test_validate_request_rejects_extra_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "Untrusted identity fields"):
            runtime.validate_request(payload(userId="attacker"))

    def test_validate_request_rejects_extended_trusted_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "server-generated trustedIdentity"):
            runtime.validate_request(
                payload(
                    trustedIdentity={
                        "actorId": "user-123",
                        "groups": ["admin"],
                    }
                )
            )

    def test_validate_request_rejects_expired_deadline(self) -> None:
        with self.assertRaisesRegex(TimeoutError, "deadline"):
            runtime.validate_request(
                payload(deadlineEpochMs=int(time.time() * 1000) - 1)
            )

    def test_sigv4_auth_signs_agentcore_gateway_request(self) -> None:
        auth = runtime.AgentCoreSigV4Auth("eu-west-3")
        request = httpx.Request(
            "POST",
            "https://bedrock-agentcore.eu-west-3.amazonaws.com/gateways/test/mcp",
            headers={"content-type": "application/json"},
            content=b'{"jsonrpc":"2.0"}',
        )

        signed_request = next(auth.auth_flow(request))
        authorization = signed_request.headers.get("authorization", "")

        self.assertTrue(authorization.startswith("AWS4-HMAC-SHA256 Credential="))
        self.assertIn("/eu-west-3/bedrock-agentcore/aws4_request", authorization)
        self.assertIn("x-amz-date", signed_request.headers)
        self.assertEqual(signed_request.headers.get("x-amz-security-token"), "test")

    def test_mcp_provider_reuses_then_reconnects_client(self) -> None:
        created_clients: list[Mock] = []
        original_client = runtime.MCPClient
        original_get_all = runtime.get_all_mcp_tools

        def client_factory(_transport_factory):
            client = MagicMock()
            client.__enter__.return_value = client
            client.__exit__.return_value = None
            created_clients.append(client)
            return client

        runtime.MCPClient = client_factory
        runtime.get_all_mcp_tools = Mock(return_value=["create_trip"])
        provider = runtime.MCPToolProvider()
        try:
            self.assertEqual(provider.get_tools(), ["create_trip"])
            self.assertEqual(provider.get_tools(), ["create_trip"])
            self.assertEqual(len(created_clients), 1)

            provider.reset("test_disconnect")
            self.assertEqual(provider.get_tools(), ["create_trip"])
            self.assertEqual(len(created_clients), 2)
            created_clients[0].__exit__.assert_called_once()
        finally:
            provider.close()
            runtime.MCPClient = original_client
            runtime.get_all_mcp_tools = original_get_all

    def test_retryable_mcp_error_detection_checks_wrapped_transport(self) -> None:
        outer = RuntimeError("agent failed")
        outer.__cause__ = httpx.ReadError("connection closed")
        self.assertTrue(runtime.is_retryable_mcp_error(outer))
        self.assertTrue(
            runtime.is_retryable_mcp_error(RuntimeError("MCP session is closed"))
        )
        self.assertFalse(runtime.is_retryable_mcp_error(ValueError("invalid prompt")))

    def test_runtime_retries_mcp_failure_once_with_same_operation(self) -> None:
        original_initialize = runtime.initialize_mcp_tools
        original_invoke_once = runtime.invoke_agent_once
        original_reset = runtime.reset_mcp_tools

        initialize_mock = Mock(side_effect=[["tool-a"], ["tool-b"]])
        invoke_mock = Mock(side_effect=[RuntimeError("MCP transport closed"), "ok"])
        reset_mock = Mock()
        runtime.initialize_mcp_tools = initialize_mock
        runtime.invoke_agent_once = invoke_mock
        runtime.reset_mcp_tools = reset_mock
        try:
            result = asyncio.run(runtime.invoke(payload()))
        finally:
            runtime.initialize_mcp_tools = original_initialize
            runtime.invoke_agent_once = original_invoke_once
            runtime.reset_mcp_tools = original_reset

        self.assertEqual(result, "ok")
        self.assertEqual(initialize_mock.call_count, 2)
        reset_mock.assert_called_once()
        self.assertEqual(
            invoke_mock.call_args_list[0].args[0].operation_id, OPERATION_ID
        )
        self.assertEqual(
            invoke_mock.call_args_list[1].args[0].operation_id, OPERATION_ID
        )


if __name__ == "__main__":
    unittest.main()
