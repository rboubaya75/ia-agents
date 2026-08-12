"""Tests unitaires de AgentCoreRuntimeAdapter.

Idiome du depot : unittest, client boto3 remplace par Mock() sur l'attribut
d'instance _client, variables d'environnement non necessaires (pas d'import
Settings). Modele : tests/unit/test_agent_api_facade.py.
"""

from __future__ import annotations

import json
import time
import unittest
from dataclasses import replace
from unittest.mock import Mock

import agents.adapter.agentcore_runtime_adapter as adapter_module
from agents.adapter.agentcore_runtime_adapter import AgentCoreRuntimeAdapter
from agents.models import (
    AgentBudget,
    AgentConfig,
    AgentErrorCode,
    AgentRequest,
    OperationContext,
    RetrievalContext,
    StreamDelta,
    StreamDone,
    StreamError,
    StreamMeta,
    TrustedIdentity,
)

CONVERSATION_ID = "test-conversation-external-123"
ACTOR_ID = "user-actor-abc"
OPERATION_ID = "12345678-1234-4234-8234-123456789abc"
REQUEST_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
RUNTIME_ARN = "arn:aws:bedrock-agentcore:eu-west-1:123456789012:agent-runtime/test"


def make_request(message: str = "hello") -> AgentRequest:
    now_ms = int(time.time() * 1000)
    return AgentRequest(
        message=message,
        runtime_session_id=CONVERSATION_ID,
        trusted_identity=TrustedIdentity(actor_id=ACTOR_ID, tenant_id=ACTOR_ID),
        operation_context=OperationContext(
            operation_id=OPERATION_ID,
            request_id=REQUEST_ID,
            deadline_epoch_ms=now_ms + 30_000,
        ),
        retrieval_context=RetrievalContext(
            status="skipped", chunks=(), chunk_count=0, policy="v1"
        ),
        budget=AgentBudget(
            max_turns=10,
            max_tool_calls=20,
            max_tokens=8192,
            deadline_epoch_ms=now_ms + 30_000,
        ),
        config=AgentConfig(
            invocation_id="inv-1",
            fallback_invocation_id=None,
            prompt_version="v1",
            tool_allowlist=[],
        ),
    )


def ok_response(body: bytes = b'"model answer"') -> dict:
    return {"statusCode": 200, "response": body}


class AgentCoreRuntimeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = AgentCoreRuntimeAdapter(
            runtime_arn=RUNTIME_ARN, endpoint_name="default"
        )
        self.mock_client = Mock()
        self.adapter._client = self.mock_client

    def _events(self, request=None):
        return list(self.adapter.invoke_stream(request or make_request()))

    # ------------------------------------------------------------------
    # Contract: StreamMeta must be the first event
    # ------------------------------------------------------------------

    def test_meta_is_first_event(self) -> None:
        self.mock_client.invoke_agent_runtime.return_value = ok_response()
        events = self._events()
        self.assertIsInstance(events[0], StreamMeta)
        self.assertEqual(events[0].streaming, "emulated")
        self.assertEqual(events[0].operation_id, OPERATION_ID)

    # ------------------------------------------------------------------
    # Contract: exactly one terminal event
    # ------------------------------------------------------------------

    def test_exactly_one_terminal_event_on_success(self) -> None:
        self.mock_client.invoke_agent_runtime.return_value = ok_response()
        events = self._events()
        terminal = [e for e in events if isinstance(e, (StreamDone, StreamError))]
        self.assertEqual(len(terminal), 1)

    def test_exactly_one_terminal_event_on_error(self) -> None:
        self.mock_client.invoke_agent_runtime.side_effect = RuntimeError("boom")
        events = self._events()
        terminal = [e for e in events if isinstance(e, (StreamDone, StreamError))]
        self.assertEqual(len(terminal), 1)

    # ------------------------------------------------------------------
    # Contract: V1 payload fields — exact set, no extras
    # ------------------------------------------------------------------

    def test_payload_has_exact_v1_field_set(self) -> None:
        self.mock_client.invoke_agent_runtime.return_value = ok_response()
        self._events()
        call_kwargs = self.mock_client.invoke_agent_runtime.call_args.kwargs
        payload = json.loads(call_kwargs["payload"])
        self.assertEqual(
            set(payload.keys()),
            {"prompt", "sessionId", "operationId", "requestId", "deadlineEpochMs", "trustedIdentity"},
        )

    def test_trusted_identity_has_only_actor_id(self) -> None:
        self.mock_client.invoke_agent_runtime.return_value = ok_response()
        self._events()
        payload = json.loads(
            self.mock_client.invoke_agent_runtime.call_args.kwargs["payload"]
        )
        self.assertEqual(set(payload["trustedIdentity"].keys()), {"actorId"})
        self.assertEqual(payload["trustedIdentity"]["actorId"], ACTOR_ID)

    def test_session_id_is_derived_not_raw_conversation_id(self) -> None:
        self.mock_client.invoke_agent_runtime.return_value = ok_response()
        self._events()
        payload = json.loads(
            self.mock_client.invoke_agent_runtime.call_args.kwargs["payload"]
        )
        self.assertNotEqual(payload["sessionId"], CONVERSATION_ID)
        self.assertRegex(payload["sessionId"], r"^sid-v1-[a-f0-9]{64}$")

    def test_operation_id_passes_through(self) -> None:
        self.mock_client.invoke_agent_runtime.return_value = ok_response()
        self._events()
        payload = json.loads(
            self.mock_client.invoke_agent_runtime.call_args.kwargs["payload"]
        )
        self.assertEqual(payload["operationId"], OPERATION_ID)

    # ------------------------------------------------------------------
    # Contract: session ID is deterministic and actor-scoped
    # ------------------------------------------------------------------

    def test_session_id_is_deterministic(self) -> None:
        a = adapter_module._derive_internal_session_id(ACTOR_ID, CONVERSATION_ID)
        b = adapter_module._derive_internal_session_id(ACTOR_ID, CONVERSATION_ID)
        self.assertEqual(a, b)

    def test_session_id_is_actor_scoped(self) -> None:
        a = adapter_module._derive_internal_session_id(ACTOR_ID, CONVERSATION_ID)
        b = adapter_module._derive_internal_session_id("other-user", CONVERSATION_ID)
        self.assertNotEqual(a, b)

    # ------------------------------------------------------------------
    # Contract: deadline clamped to now + 115 s
    # ------------------------------------------------------------------

    def _sent_deadline_for(self, offset_ms: int) -> tuple[int, int]:
        """Invoke with a deadline offset_ms in the future; return (now_ms, sent)."""
        self.mock_client.invoke_agent_runtime.return_value = ok_response()
        req = make_request()
        now_ms = int(time.time() * 1000)
        req = replace(
            req,
            operation_context=replace(
                req.operation_context, deadline_epoch_ms=now_ms + offset_ms
            ),
        )
        self._events(request=req)
        payload = json.loads(
            self.mock_client.invoke_agent_runtime.call_args.kwargs["payload"]
        )
        return now_ms, payload["deadlineEpochMs"]

    def test_deadline_clamped_when_request_deadline_far(self) -> None:
        # 10 minutes out. V1 rejects anything beyond now + 120 s, so the adapter must
        # cut it down rather than let Runtime refuse the call.
        now_ms, sent = self._sent_deadline_for(600_000)
        self.assertLessEqual(sent, now_ms + 115_000 + 500)
        # Lower bound too: a clamp that collapsed to "now" would pass an upper-bound-only
        # assertion while leaving Runtime no time to answer.
        self.assertGreaterEqual(sent, now_ms + 115_000 - 500)

    def test_deadline_not_clamped_when_request_deadline_near(self) -> None:
        # 30 s is inside the V1 window: the caller's own budget must survive untouched.
        now_ms, sent = self._sent_deadline_for(30_000)
        self.assertGreaterEqual(sent, now_ms + 30_000 - 500)
        self.assertLessEqual(sent, now_ms + 30_000 + 500)

    def test_deadline_never_exceeds_v1_ceiling(self) -> None:
        for offset in (0, 60_000, 119_000, 120_000, 3_600_000):
            with self.subTest(offset=offset):
                now_ms, sent = self._sent_deadline_for(offset)
                self.assertLessEqual(sent, now_ms + 120_000)

    # ------------------------------------------------------------------
    # Contract: success path emits meta → delta → done, degraded=False
    # ------------------------------------------------------------------

    def test_success_event_sequence(self) -> None:
        self.mock_client.invoke_agent_runtime.return_value = ok_response(b'"model answer"')
        events = self._events()
        self.assertIsInstance(events[0], StreamMeta)
        self.assertIsInstance(events[1], StreamDelta)
        self.assertIsInstance(events[2], StreamDone)
        self.assertEqual(events[1].text, "model answer")
        self.assertEqual(events[2].result.answer, "model answer")
        self.assertFalse(events[2].result.degraded)

    # ------------------------------------------------------------------
    # Contract: exception → StreamError (never raised)
    # ------------------------------------------------------------------

    def test_throttling_maps_to_model_throttled(self) -> None:
        from botocore.exceptions import ClientError
        err = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}, "ResponseMetadata": {"HTTPStatusCode": 429}}
        self.mock_client.invoke_agent_runtime.side_effect = ClientError(err, "InvokeAgentRuntime")
        events = self._events()
        last = events[-1]
        self.assertIsInstance(last, StreamError)
        self.assertEqual(last.error.code, AgentErrorCode.MODEL_THROTTLED)

    def test_too_many_requests_maps_to_model_throttled(self) -> None:
        from botocore.exceptions import ClientError
        err = {"Error": {"Code": "TooManyRequestsException", "Message": "Slow down"}, "ResponseMetadata": {"HTTPStatusCode": 429}}
        self.mock_client.invoke_agent_runtime.side_effect = ClientError(err, "InvokeAgentRuntime")
        events = self._events()
        self.assertEqual(events[-1].error.code, AgentErrorCode.MODEL_THROTTLED)

    def test_read_timeout_maps_to_deadline_exceeded(self) -> None:
        from botocore.exceptions import ReadTimeoutError
        self.mock_client.invoke_agent_runtime.side_effect = ReadTimeoutError(endpoint_url="http://test")
        events = self._events()
        self.assertIsInstance(events[-1], StreamError)
        self.assertEqual(events[-1].error.code, AgentErrorCode.DEADLINE_EXCEEDED)

    def test_generic_exception_maps_to_internal_error(self) -> None:
        self.mock_client.invoke_agent_runtime.side_effect = RuntimeError("unexpected")
        events = self._events()
        self.assertIsInstance(events[-1], StreamError)
        self.assertEqual(events[-1].error.code, AgentErrorCode.INTERNAL_ERROR)

    # ------------------------------------------------------------------
    # Contract: invoke() honours the Protocol, not just invoke_stream()
    # ------------------------------------------------------------------

    def test_invoke_returns_result_on_success(self) -> None:
        self.mock_client.invoke_agent_runtime.return_value = ok_response(b'"model answer"')
        result = self.adapter.invoke(make_request())
        self.assertEqual(result.answer, "model answer")
        self.assertFalse(result.degraded)
        self.assertIsNone(result.error)

    def test_invoke_returns_error_result_instead_of_raising(self) -> None:
        self.mock_client.invoke_agent_runtime.side_effect = RuntimeError("boom")
        result = self.adapter.invoke(make_request())
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, AgentErrorCode.INTERNAL_ERROR)
        self.assertTrue(result.degraded)

    # ------------------------------------------------------------------
    # Contract: the socket never outlives the deadline handed to Runtime
    # ------------------------------------------------------------------

    def test_read_timeout_capped_at_deadline_window(self) -> None:
        greedy = AgentCoreRuntimeAdapter(
            runtime_arn=RUNTIME_ARN, read_timeout_seconds=9999
        )
        self.assertLessEqual(greedy._read_timeout, 115)

    def test_read_timeout_honours_lower_operator_value(self) -> None:
        tight = AgentCoreRuntimeAdapter(runtime_arn=RUNTIME_ARN, read_timeout_seconds=30)
        self.assertEqual(tight._read_timeout, 30)

    def test_timeouts_stay_positive(self) -> None:
        degenerate = AgentCoreRuntimeAdapter(
            runtime_arn=RUNTIME_ARN, connect_timeout_seconds=0, read_timeout_seconds=0
        )
        self.assertGreaterEqual(degenerate._connect_timeout, 1)
        self.assertGreaterEqual(degenerate._read_timeout, 1)


if __name__ == "__main__":
    unittest.main()
