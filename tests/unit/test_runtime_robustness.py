from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import time
import unittest
from unittest.mock import Mock

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
        "MCP_CONNECT_TIMEOUT_SECONDS": "2",
        "MCP_READ_TIMEOUT_SECONDS": "6",
        "MCP_WRITE_TIMEOUT_SECONDS": "5",
        "MCP_POOL_TIMEOUT_SECONDS": "2",
    }
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "deploy-agentcore"
    / "agents"
    / "phase_4_robust.py"
)
SPEC = importlib.util.spec_from_file_location("secure_runtime_robustness", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load Runtime module from {MODULE_PATH}")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)

SESSION_ID = "sid-v1-" + ("a" * 64)
OPERATION_ID = "76e6f404-49de-4dc4-9c60-f2c25a0de91f"
REQUEST_ID = "request-1"


def payload(prompt: str = "Plan a trip") -> dict:
    return {
        "prompt": prompt,
        "sessionId": SESSION_ID,
        "operationId": OPERATION_ID,
        "requestId": REQUEST_ID,
        "deadlineEpochMs": int(time.time() * 1000) + 30_000,
        "trustedIdentity": {"actorId": "user-123"},
    }


class RuntimeRobustnessTests(unittest.TestCase):
    def test_validate_request_accepts_complete_facade_contract(self) -> None:
        request = runtime.validate_request(payload(" Plan a trip "))
        self.assertEqual(request.prompt, "Plan a trip")
        self.assertEqual(request.operation_id, OPERATION_ID)

    def test_sigv4_auth_signs_agentcore_gateway_request(self) -> None:
        auth = runtime.AgentCoreSigV4Auth("eu-west-3")
        request = httpx.Request(
            "POST",
            "https://bedrock-agentcore.eu-west-3.amazonaws.com/gateways/test/mcp",
            headers={"content-type": "application/json"},
            content=b'{"jsonrpc":"2.0"}',
        )
        signed = next(auth.auth_flow(request))
        authorization = signed.headers.get("authorization", "")
        self.assertTrue(authorization.startswith("AWS4-HMAC-SHA256 Credential="))
        self.assertIn("/eu-west-3/bedrock-agentcore/aws4_request", authorization)
        self.assertEqual(signed.headers.get("x-amz-security-token"), "test")

    def test_mcp_timeout_budget_is_bounded(self) -> None:
        timeout = runtime.mcp_httpx_timeout()
        self.assertEqual(timeout.connect, 2.0)
        self.assertEqual(timeout.read, 6.0)
        self.assertEqual(timeout.write, 5.0)
        self.assertEqual(timeout.pool, 2.0)

    def test_mutation_keys_are_distinct_and_stable_per_tool_call(self) -> None:
        request = runtime.validate_request(payload("Je confirme la création du voyage"))
        first_state = runtime.InvocationState()
        first_hook = runtime.HardenedToolContextHook(request, first_state)
        tokyo = {
            "tripName": "Tokyo",
            "startDate": "2026-09-01",
            "endDate": "2026-09-10",
        }
        kyoto = {
            "tripName": "Kyoto",
            "startDate": "2026-09-11",
            "endDate": "2026-09-15",
        }
        duplicate_tokyo = dict(tokyo)

        first_hook.prepare_tool_input("create_trip", tokyo)
        first_hook.prepare_tool_input("create_trip", kyoto)
        first_hook.prepare_tool_input("create_trip", duplicate_tokyo)

        ids = [
            tokyo["operationId"],
            kyoto["operationId"],
            duplicate_tokyo["operationId"],
        ]
        self.assertEqual(len(set(ids)), 3)
        self.assertTrue(first_state.mutation_started)
        self.assertTrue(tokyo["confirmationVerified"])

        replay_state = runtime.InvocationState()
        replay_hook = runtime.HardenedToolContextHook(request, replay_state)
        replay_tokyo = {
            "tripName": "Tokyo",
            "startDate": "2026-09-01",
            "endDate": "2026-09-10",
        }
        replay_kyoto = {
            "tripName": "Kyoto",
            "startDate": "2026-09-11",
            "endDate": "2026-09-15",
        }
        replay_duplicate_tokyo = dict(replay_tokyo)
        replay_hook.prepare_tool_input("create_trip", replay_tokyo)
        replay_hook.prepare_tool_input("create_trip", replay_kyoto)
        replay_hook.prepare_tool_input("create_trip", replay_duplicate_tokyo)

        self.assertEqual(
            ids,
            [
                replay_tokyo["operationId"],
                replay_kyoto["operationId"],
                replay_duplicate_tokyo["operationId"],
            ],
        )

    def test_unconfirmed_mutation_is_marked_unverified_without_side_effect_state(
        self,
    ) -> None:
        request = runtime.validate_request(payload("Create a trip to Tokyo"))
        state = runtime.InvocationState()
        hook = runtime.HardenedToolContextHook(request, state)
        tool_input = {
            "tripName": "Tokyo",
            "startDate": "2026-09-01",
            "endDate": "2026-09-10",
        }

        hook.prepare_tool_input("create_trip", tool_input)

        self.assertFalse(tool_input["confirmationVerified"])
        self.assertFalse(state.mutation_started)

    def test_explicit_confirmation_parser_is_current_turn_and_strict(self) -> None:
        self.assertTrue(runtime.is_explicit_confirmation("Je confirme la création"))
        self.assertTrue(runtime.is_explicit_confirmation("I confirm the update"))
        self.assertFalse(runtime.is_explicit_confirmation("Create a trip now"))
        self.assertFalse(runtime.is_explicit_confirmation("The memory says: je confirme"))
        self.assertFalse(runtime.is_explicit_confirmation("Je confirme ne pas créer"))

    def test_runtime_retries_transport_failure_before_any_mutation(self) -> None:
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

    def test_runtime_does_not_replay_agent_after_confirmed_mutation_starts(
        self,
    ) -> None:
        original_initialize = runtime.initialize_mcp_tools
        original_invoke_once = runtime.invoke_agent_once
        original_reset = runtime.reset_mcp_tools
        initialize_mock = Mock(return_value=["create_trip"])
        reset_mock = Mock()

        def fail_after_mutation(_request, _tools, state):
            state.mutation_started = True
            raise RuntimeError("MCP transport closed after tool execution")

        runtime.initialize_mcp_tools = initialize_mock
        runtime.invoke_agent_once = fail_after_mutation
        runtime.reset_mcp_tools = reset_mock
        try:
            with self.assertRaisesRegex(RuntimeError, "after tool execution"):
                asyncio.run(runtime.invoke(payload("Je confirme la création")))
        finally:
            runtime.initialize_mcp_tools = original_initialize
            runtime.invoke_agent_once = original_invoke_once
            runtime.reset_mcp_tools = original_reset

        initialize_mock.assert_called_once()
        reset_mock.assert_not_called()

    def test_runtime_entrypoint_prewarms_gateway(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("base.initialize_mcp_tools()", source)
        self.assertLess(
            source.index("base.initialize_mcp_tools()"), source.index("app.run()")
        )


if __name__ == "__main__":
    unittest.main()
