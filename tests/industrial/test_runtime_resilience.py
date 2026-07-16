from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import unittest
from unittest.mock import MagicMock, Mock, patch

from _industrial_helpers import (
    json_log_events,
    load_runtime,
    runtime_payload,
    serialized_log_messages,
)

runtime = load_runtime()


class RuntimeResilienceIndustrialTests(unittest.TestCase):
    def test_v1_res_001_retry_occurs_once_before_any_mutation(self) -> None:
        initialize = Mock(side_effect=[["tool-first"], ["tool-second"]])
        invoke_once = Mock(side_effect=[RuntimeError("MCP connection closed"), "ok"])
        reset = Mock()
        logger = Mock()

        with (
            patch.object(runtime, "initialize_mcp_tools", initialize),
            patch.object(runtime, "invoke_agent_once", invoke_once),
            patch.object(runtime, "reset_mcp_tools", reset),
            patch.object(runtime.base, "logger", logger),
        ):
            result = asyncio.run(runtime.invoke(runtime_payload()))

        self.assertEqual(result, "ok")
        self.assertEqual(initialize.call_count, 2)
        self.assertEqual(invoke_once.call_count, 2)
        reset.assert_called_once_with("RuntimeError")

        events = json_log_events(logger)
        retry = next(event for event in events if event.get("event") == "mcp_retry")
        outcome = next(
            event
            for event in events
            if event.get("event") == "agent_invocation"
            and event.get("status") == "success"
        )
        self.assertFalse(retry["mutation_started"])
        self.assertEqual(outcome["mcp_retry_count"], 1)

        logs = serialized_log_messages(logger)
        self.assertNotIn("industrial-actor-raw", logs)
        self.assertNotIn("sid-v1-" + ("a" * 64), logs)
        self.assertNotIn("76e6f404-49de-4dc4-9c60-f2c25a0de91f", logs)
        self.assertNotIn("Plan a trip", logs)
        self.assertIn("industrial-request-1", logs)

    def test_v1_res_002_second_failure_is_not_retried_a_third_time(self) -> None:
        initialize = Mock(side_effect=[["tool-first"], ["tool-second"]])
        invoke_once = Mock(
            side_effect=[
                RuntimeError("MCP connection closed"),
                RuntimeError("MCP gateway connection closed again"),
            ]
        )
        reset = Mock()
        logger = Mock()

        with (
            patch.object(runtime, "initialize_mcp_tools", initialize),
            patch.object(runtime, "invoke_agent_once", invoke_once),
            patch.object(runtime, "reset_mcp_tools", reset),
            patch.object(runtime.base, "logger", logger),
        ):
            with self.assertRaisesRegex(RuntimeError, "closed again"):
                asyncio.run(runtime.invoke(runtime_payload()))

        self.assertEqual(initialize.call_count, 2)
        self.assertEqual(invoke_once.call_count, 2)
        reset.assert_called_once_with("RuntimeError")
        events = json_log_events(logger)
        outcome = next(
            event
            for event in events
            if event.get("event") == "agent_invocation"
            and event.get("status") == "error"
        )
        self.assertEqual(outcome["mcp_retry_count"], 1)
        self.assertEqual(outcome["error_type"], "RuntimeError")
        self.assertNotIn("closed again", json.dumps(outcome))

    def test_v1_res_003_non_retryable_failure_is_never_reconnected(self) -> None:
        initialize = Mock(return_value=["tool"])
        invoke_once = Mock(side_effect=ValueError("model validation rejected"))
        reset = Mock()

        with (
            patch.object(runtime, "initialize_mcp_tools", initialize),
            patch.object(runtime, "invoke_agent_once", invoke_once),
            patch.object(runtime, "reset_mcp_tools", reset),
            patch.object(runtime.base, "logger", Mock()),
        ):
            with self.assertRaisesRegex(ValueError, "model validation"):
                asyncio.run(runtime.invoke(runtime_payload()))

        initialize.assert_called_once()
        invoke_once.assert_called_once()
        reset.assert_not_called()

    def test_v1_res_004_confirmed_mutation_failure_is_never_replayed(self) -> None:
        initialize = Mock(return_value=["create_trip"])
        reset = Mock()

        def fail_after_side_effect(_request, _tools, state):
            state.mutation_started = True
            raise RuntimeError("MCP transport closed after tool execution")

        with (
            patch.object(runtime, "initialize_mcp_tools", initialize),
            patch.object(runtime, "invoke_agent_once", fail_after_side_effect),
            patch.object(runtime, "reset_mcp_tools", reset),
            patch.object(runtime.base, "logger", Mock()),
        ):
            with self.assertRaisesRegex(RuntimeError, "after tool execution"):
                asyncio.run(
                    runtime.invoke(
                        runtime_payload("Je confirme la création du voyage")
                    )
                )

        initialize.assert_called_once()
        reset.assert_not_called()

    def test_v1_res_005_expired_retry_budget_blocks_second_attempt(self) -> None:
        initialize = Mock(return_value=["tool"])
        invoke_once = Mock(side_effect=RuntimeError("MCP connection closed"))
        reset = Mock()

        def controlled_deadline(_deadline, minimum_remaining_ms=0):
            if minimum_remaining_ms == 1000:
                raise TimeoutError("Request deadline exceeded.")
            return 5000

        with (
            patch.object(runtime, "initialize_mcp_tools", initialize),
            patch.object(runtime, "invoke_agent_once", invoke_once),
            patch.object(runtime, "reset_mcp_tools", reset),
            patch.object(
                runtime.base,
                "ensure_deadline_remaining",
                side_effect=controlled_deadline,
            ),
            patch.object(runtime.base, "logger", Mock()),
        ):
            with self.assertRaisesRegex(TimeoutError, "deadline exceeded"):
                asyncio.run(runtime.invoke(runtime_payload()))

        initialize.assert_called_once()
        invoke_once.assert_called_once()
        reset.assert_called_once_with("RuntimeError")

    def test_v1_res_006_parallel_tool_requests_initialize_one_client(self) -> None:
        provider = runtime.base.MCPToolProvider()
        client = MagicMock()
        client.__enter__.return_value = client
        tools = ["create_trip", "get_trips"]
        client_factory = Mock(return_value=client)
        list_tools = Mock(return_value=tools)
        logger = Mock()

        with (
            patch.object(runtime.base, "MCPClient", client_factory),
            patch.object(runtime.base, "get_all_mcp_tools", list_tools),
            patch.object(runtime.base, "GATEWAY_URL", "https://gateway.test/mcp"),
            patch.object(runtime.base, "GATEWAY_AUTH_MODE", "aws_iam"),
            patch.object(runtime.base, "REQUIRE_MCP_TOOLS", True),
            patch.object(runtime.base, "logger", logger),
        ):
            with ThreadPoolExecutor(max_workers=16) as executor:
                results = list(executor.map(lambda _index: provider.get_tools(), range(64)))
            provider.close()

        self.assertTrue(all(result == tools for result in results))
        client_factory.assert_called_once()
        list_tools.assert_called_once_with(client)
        client.__enter__.assert_called_once()
        client.__exit__.assert_called_once()
        events = json_log_events(logger)
        self.assertEqual(
            sum(event.get("event") == "gateway_tools_loaded" for event in events),
            1,
        )

    def test_v1_res_007_reset_closes_client_and_clears_cached_tools(self) -> None:
        provider = runtime.base.MCPToolProvider()
        client = MagicMock()
        provider._client = client
        provider._tools = ["tool"]
        provider._initialized = True
        logger = Mock()

        with patch.object(runtime.base, "logger", logger):
            provider.reset("fault_injection")

        client.__exit__.assert_called_once_with(None, None, None)
        self.assertIsNone(provider._client)
        self.assertEqual(provider._tools, [])
        self.assertFalse(provider._initialized)
        events = json_log_events(logger)
        self.assertIn(
            {"event": "gateway_tools_reset", "reason": "fault_injection"},
            events,
        )


if __name__ == "__main__":
    unittest.main()
