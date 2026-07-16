from __future__ import annotations

import json
from pathlib import Path
import re
import unittest
from unittest.mock import Mock, patch

from _industrial_helpers import (
    ROOT,
    extract_hcl_block,
    json_log_events,
    load_facade,
    load_runtime,
    runtime_payload,
    serialized_log_messages,
)

runtime = load_runtime()
facade = load_facade()

RUNTIME_TF = (ROOT / "infra" / "environments" / "test" / "agentcore_native.tf").read_text(
    encoding="utf-8"
)
FACADE_TF = (
    ROOT / "infra" / "modules" / "agent_api_facade" / "main.tf"
).read_text(encoding="utf-8")
TRIP_TOOLS_TF = (
    ROOT / "infra" / "modules" / "trip_tools_lambda" / "main.tf"
).read_text(encoding="utf-8")
API_GATEWAY_TF = (
    ROOT / "infra" / "modules" / "api_gateway_agent_ingress" / "main.tf"
).read_text(encoding="utf-8")
FRONTEND_CHAT = (
    ROOT / "frontend" / "src" / "services" / "chatService.ts"
).read_text(encoding="utf-8")
RUNTIME_SOURCE = (
    ROOT / "deploy-agentcore" / "agents" / "phase_4_robust.py"
).read_text(encoding="utf-8")
MEMORY_SOURCE = (
    ROOT / "deploy-agentcore" / "agents" / "memory_support.py"
).read_text(encoding="utf-8")
TRIP_SOURCE = (
    ROOT / "deploy-agentcore" / "lambda_function_phase2.py"
).read_text(encoding="utf-8")
FACADE_SOURCE = (
    ROOT
    / "infra"
    / "modules"
    / "agent_api_facade"
    / "src"
    / "lambda_function.py"
).read_text(encoding="utf-8")


def statement_slice(source: str, sid: str) -> str:
    marker = f' sid    = "{sid}"'
    start = source.find(marker)
    if start < 0:
        marker = f'sid    = "{sid}"'
        start = source.find(marker)
    if start < 0:
        raise AssertionError(f"IAM statement not found: {sid}")
    end = source.find("\n  }", start)
    if end < 0:
        raise AssertionError(f"IAM statement not terminated: {sid}")
    return source[start:end]


class IamBoundaryIndustrialTests(unittest.TestCase):
    def test_v1_iam_001_runtime_policy_allows_only_facade_and_denies_others(self) -> None:
        block = extract_hcl_block(
            RUNTIME_TF,
            'data "aws_iam_policy_document" "agent_runtime_invocation_boundary"',
        )
        self.assertIn('sid     = "AllowOnlySecurityFacadeRole"', block)
        self.assertIn('identifiers = [module.agent_api_facade.role_arn]', block)
        self.assertIn('sid     = "DenyOtherRuntimeInvokers"', block)
        self.assertIn('test     = "ArnNotEquals"', block)
        self.assertIn('variable = "aws:PrincipalArn"', block)
        self.assertIn('values   = [module.agent_api_facade.role_arn]', block)
        self.assertIn('sid     = "DenyUnverifiedRuntimeUserDelegation"', block)
        self.assertEqual(block.count('"bedrock-agentcore:InvokeAgentRuntime"'), 2)
        self.assertEqual(block.count('"bedrock-agentcore:InvokeAgentRuntimeForUser"'), 1)
        self.assertNotIn('resources = ["*"]', block)

    def test_v1_iam_002_gateway_policy_allows_only_runtime_and_denies_others(self) -> None:
        block = extract_hcl_block(
            RUNTIME_TF,
            'data "aws_iam_policy_document" "tools_gateway_invocation_boundary"',
        )
        self.assertIn('sid     = "AllowOnlyRuntimeRole"', block)
        self.assertIn('identifiers = [aws_iam_role.agentcore_runtime.arn]', block)
        self.assertIn('sid     = "DenyOtherGatewayInvokers"', block)
        self.assertIn('values   = [aws_iam_role.agentcore_runtime.arn]', block)
        self.assertEqual(block.count('"bedrock-agentcore:InvokeGateway"'), 2)
        self.assertNotIn('resources = ["*"]', block)

    def test_v1_iam_003_facade_can_only_invoke_configured_runtime(self) -> None:
        block = extract_hcl_block(
            FACADE_TF,
            'data "aws_iam_policy_document" "runtime_invoke"',
        )
        self.assertIn('sid     = "InvokeOnlyConfiguredAgentRuntime"', block)
        self.assertIn('actions = ["bedrock-agentcore:InvokeAgentRuntime"]', block)
        self.assertIn('var.agent_runtime_arn', block)
        self.assertIn('sid     = "DenyUnverifiedRuntimeUserDelegation"', block)
        self.assertIn(
            'actions = ["bedrock-agentcore:InvokeAgentRuntimeForUser"]', block
        )
        self.assertNotIn('resources = ["*"]', block)
        self.assertNotIn('bedrock:*', block)

    def test_v1_iam_004_trip_tools_use_exact_table_and_hmac_key(self) -> None:
        execution = extract_hcl_block(
            TRIP_TOOLS_TF,
            'data "aws_iam_policy_document" "execution"',
        )
        table = statement_slice(execution, "ReadWriteOwnTripsTable")
        hmac_key = statement_slice(execution, "UsePaginationHmacKey")

        expected_dynamodb_actions = {
            "dynamodb:GetItem",
            "dynamodb:PutItem",
            "dynamodb:Query",
            "dynamodb:UpdateItem",
            "dynamodb:TransactWriteItems",
        }
        actual_dynamodb_actions = set(re.findall(r'"(dynamodb:[A-Za-z]+)"', table))
        self.assertEqual(actual_dynamodb_actions, expected_dynamodb_actions)
        self.assertIn('resources = [var.trips_table_arn]', table)
        self.assertNotIn('dynamodb:Scan', table)
        self.assertNotIn('dynamodb:DeleteItem', table)
        self.assertNotIn('"*"', table)

        self.assertEqual(
            set(re.findall(r'"(kms:[A-Za-z]+)"', hmac_key)),
            {"kms:GenerateMac", "kms:VerifyMac"},
        )
        self.assertIn('resources = [aws_kms_key.pagination_hmac.arn]', hmac_key)
        self.assertNotIn('"*"', hmac_key)


class ObservabilityIndustrialTests(unittest.TestCase):
    def test_v1_obs_001_invocation_log_schema_is_correlated_and_redacted(self) -> None:
        request = runtime.validate_request(runtime_payload())
        logger = Mock()
        sensitive_error = RuntimeError("raw-private-runtime-message")

        with patch.object(runtime.base, "logger", logger):
            runtime.base.log_invocation(
                request,
                1234.567,
                "error",
                mcp_retry_count=1,
                error=sensitive_error,
            )

        events = json_log_events(logger)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(
            set(event),
            {
                "event",
                "request_id",
                "session_hash",
                "actor_hash",
                "operation_hash",
                "duration_ms",
                "mcp_retry_count",
                "status",
                "error_type",
            },
        )
        self.assertEqual(event["event"], "agent_invocation")
        self.assertEqual(event["request_id"], "industrial-request-1")
        self.assertEqual(event["duration_ms"], 1234.57)
        self.assertEqual(event["error_type"], "RuntimeError")

        serialized = json.dumps(event, sort_keys=True)
        self.assertNotIn("industrial-actor-raw", serialized)
        self.assertNotIn("sid-v1-" + ("a" * 64), serialized)
        self.assertNotIn("76e6f404-49de-4dc4-9c60-f2c25a0de91f", serialized)
        self.assertNotIn("raw-private-runtime-message", serialized)

    def test_v1_obs_002_tool_context_log_exposes_only_hashes_and_correlation(self) -> None:
        request = runtime.validate_request(
            runtime_payload("Je confirme la création du voyage")
        )
        logger = Mock()
        state = runtime.InvocationState()
        hook = runtime.HardenedToolContextHook(request, state)
        tool_input = {
            "tripName": "Industrial Paris",
            "startDate": "2026-10-01",
            "endDate": "2026-10-04",
            "userId": "attacker-user",
            "requestId": "attacker-request",
            "operationId": "attacker-operation",
        }

        with patch.object(runtime.base, "logger", logger):
            hook.prepare_tool_input("create_trip", tool_input)

        self.assertEqual(tool_input["userId"], request.actor_id)
        self.assertEqual(tool_input["requestId"], request.request_id)
        self.assertEqual(tool_input["deadlineEpochMs"], request.deadline_epoch_ms)
        self.assertTrue(tool_input["confirmationVerified"])
        self.assertTrue(state.mutation_started)

        event = next(
            event
            for event in json_log_events(logger)
            if event.get("event") == "tool_context_injection"
        )
        self.assertEqual(event["request_id"], request.request_id)
        self.assertEqual(event["tool"], "create_trip")
        logs = serialized_log_messages(logger)
        for forbidden in (
            request.actor_id,
            request.operation_id,
            "attacker-user",
            "attacker-request",
            "attacker-operation",
            "Industrial Paris",
        ):
            self.assertNotIn(forbidden, logs)

    def test_v1_obs_003_required_event_catalog_is_present_in_production_sources(self) -> None:
        expected_by_source = {
            FACADE_SOURCE: {
                "facade_invocation",
                "facade_authorization_rejected",
                "runtime_timeout",
                "runtime_client_error",
            },
            RUNTIME_SOURCE: {
                "request_accepted",
                "mcp_retry",
                "agent_invocation",
                "tool_context_injection",
            },
            MEMORY_SOURCE: {
                "memory_retrieval_empty",
                "memory_retrieved",
                "memory_retrieval_failed",
                "memory_saved",
                "memory_save_failed",
            },
            TRIP_SOURCE: {
                "trip_tool_invocation",
                "trips_listed",
                "trip_read",
                "trip_mutation_outcome",
                "trip_validation_rejected",
                "trip_idempotency_conflict",
            },
        }
        for source, events in expected_by_source.items():
            for event in events:
                with self.subTest(event=event):
                    self.assertIn(f'"event": "{event}"', source)


class PerformanceAndFrontendIndustrialTests(unittest.TestCase):
    def test_v1_perf_001_timeout_chain_is_strictly_nested(self) -> None:
        frontend_ms = int(
            re.search(r"const REQUEST_TIMEOUT = (\d+);", FRONTEND_CHAT).group(1)
        )
        api_gateway_ms = int(
            re.search(r"timeout_milliseconds\s+=\s+(\d+)", API_GATEWAY_TF).group(1)
        )
        facade_ms = facade.REQUEST_TIMEOUT_SECONDS * 1000
        facade_transport_ms = (
            facade.RUNTIME_CONNECT_TIMEOUT_SECONDS + facade.RUNTIME_READ_TIMEOUT_SECONDS
        ) * 1000
        runtime_deadline_ms = (
            facade.RUNTIME_READ_TIMEOUT_SECONDS * 1000
            - facade.RUNTIME_DEADLINE_SAFETY_MS
        )
        mcp_read_ms = int(runtime.MCP_READ_TIMEOUT_SECONDS * 1000)
        trip_lambda_ms = int(
            re.search(r"\n\s+timeout\s+=\s+(\d+)", TRIP_TOOLS_TF).group(1)
        ) * 1000

        self.assertGreater(frontend_ms, api_gateway_ms)
        self.assertGreater(api_gateway_ms, facade_ms)
        self.assertGreater(facade_ms, facade_transport_ms)
        self.assertGreater(facade_transport_ms, runtime_deadline_ms)
        self.assertGreater(runtime_deadline_ms, mcp_read_ms)
        self.assertGreater(mcp_read_ms, trip_lambda_ms)
        self.assertLessEqual(runtime.MCP_CONNECT_TIMEOUT_SECONDS, 2)
        self.assertLessEqual(runtime.MCP_POOL_TIMEOUT_SECONDS, 2)

    def test_v1_fe_001_authentication_retry_is_unique_and_keeps_operation_id(self) -> None:
        call = "invokeAgent(prompt, sessionId, operationId, accessToken, controller.signal)"
        self.assertEqual(FRONTEND_CHAT.count("if (response.status === 401)"), 1)
        self.assertEqual(FRONTEND_CHAT.count(call), 2)
        self.assertIn("existingOperationId ?? uuidv4()", FRONTEND_CHAT)
        self.assertIn("isAmbiguousStatus(response.status)", FRONTEND_CHAT)
        self.assertIn("status === 408", FRONTEND_CHAT)
        self.assertIn("status === 425", FRONTEND_CHAT)
        self.assertIn("status === 429", FRONTEND_CHAT)
        self.assertIn("status >= 500", FRONTEND_CHAT)

    def test_v1_fe_002_browser_bundle_contract_never_references_runtime_endpoint(self) -> None:
        self.assertIn("VITE_AGENT_INVOKE_URL", FRONTEND_CHAT)
        self.assertNotIn("VITE_AGENT_RUNTIME", FRONTEND_CHAT)
        self.assertNotIn("agent_runtime_invoke_url", FRONTEND_CHAT)
        self.assertNotIn("bedrock-agentcore", FRONTEND_CHAT)


if __name__ == "__main__":
    unittest.main()
