from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import Mock

from botocore.exceptions import ClientError, ReadTimeoutError

os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "eu-west-3",
        "AWS_EC2_METADATA_DISABLED": "true",
        "RUNTIME_READY": "true",
        "AGENT_RUNTIME_ARN": "arn:aws:bedrock-agentcore:eu-west-3:123456789012:runtime/test",
        "AGENT_RUNTIME_ENDPOINT_NAME": "default",
        "COGNITO_CLIENT_ID": "client-123",
        "REQUEST_TIMEOUT_SECONDS": "28",
        "RUNTIME_CONNECT_TIMEOUT_SECONDS": "2",
        "RUNTIME_READ_TIMEOUT_SECONDS": "23",
        "RUNTIME_DEADLINE_SAFETY_MS": "1500",
        "MAX_BODY_BYTES": "16384",
    }
)

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "infra"
    / "modules"
    / "agent_api_facade"
    / "src"
    / "lambda_function.py"
)
SPEC = importlib.util.spec_from_file_location("agent_api_facade_lambda", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load facade module from {MODULE_PATH}")
facade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(facade)
SESSION_ID = "550e8400-e29b-41d4-a716-446655440000"
OPERATION_ID = "76e6f404-49de-4dc4-9c60-f2c25a0de91f"


def request_body(prompt: str = "hello") -> dict:
    return {"prompt": prompt, "sessionId": SESSION_ID, "operationId": OPERATION_ID}


def event(body: dict, claims: dict | None = None) -> dict:
    return raw_event(json.dumps(body), claims)


def raw_event(body: str, claims: dict | None = None) -> dict:
    return {
        "body": body,
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": claims
                    or {
                        "sub": "user-1",
                        "client_id": "client-123",
                        "token_use": "access",
                    }
                }
            }
        },
    }


class Context:
    aws_request_id = "request-1"


class AgentApiFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        facade._agentcore = Mock()

    @staticmethod
    def response_body(response: dict) -> dict:
        return json.loads(response["body"])

    def test_success_injects_server_context_and_scoped_session(self) -> None:
        facade._agentcore.invoke_agent_runtime.return_value = {
            "statusCode": 200,
            "contentType": "application/json",
            "response": b'{"message":"ok"}',
        }
        before_ms = int(time.time() * 1000)

        response = facade.handler(event(request_body(" hello ")), Context())

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            self.response_body(response),
            {
                "message": "ok",
                "sessionId": SESSION_ID,
                "operationId": OPERATION_ID,
                "requestId": "request-1",
            },
        )
        invoke_args = facade._agentcore.invoke_agent_runtime.call_args.kwargs
        runtime_payload = json.loads(invoke_args["payload"])
        expected = facade.derive_internal_session_id("user-1", SESSION_ID)
        self.assertEqual(invoke_args["qualifier"], "default")
        self.assertEqual(invoke_args["runtimeSessionId"], expected)
        self.assertEqual(runtime_payload["prompt"], "hello")
        self.assertEqual(runtime_payload["sessionId"], expected)
        self.assertEqual(runtime_payload["operationId"], OPERATION_ID)
        self.assertEqual(runtime_payload["requestId"], "request-1")
        self.assertGreater(runtime_payload["deadlineEpochMs"], before_ms)
        self.assertLessEqual(
            runtime_payload["deadlineEpochMs"],
            before_ms + facade.RUNTIME_READ_TIMEOUT_SECONDS * 1000,
        )
        self.assertEqual(runtime_payload["trustedIdentity"]["actorId"], "user-1")
        self.assertNotIn(SESSION_ID, invoke_args["payload"].decode("utf-8"))

    def test_internal_session_is_deterministic_and_actor_scoped(self) -> None:
        first = facade.derive_internal_session_id("user-1", SESSION_ID)
        second = facade.derive_internal_session_id("user-1", SESSION_ID)
        other = facade.derive_internal_session_id("user-2", SESSION_ID)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertRegex(first, r"^sid-v1-[a-f0-9]{64}$")
        self.assertTrue(facade.SESSION_ID_PATTERN.fullmatch(first))

    def test_rejects_client_supplied_identity(self) -> None:
        body = request_body()
        body["actorId"] = "attacker"
        response = facade.handler(event(body), Context())
        self.assertEqual(response["statusCode"], 400)
        facade._agentcore.invoke_agent_runtime.assert_not_called()

    def test_rejects_unknown_model_override(self) -> None:
        body = request_body()
        body["modelOverride"] = "arbitrary"
        response = facade.handler(event(body), Context())
        self.assertEqual(response["statusCode"], 400)
        facade._agentcore.invoke_agent_runtime.assert_not_called()

    def test_rejects_missing_or_invalid_operation_id(self) -> None:
        missing = request_body()
        missing.pop("operationId")
        invalid = request_body()
        invalid["operationId"] = "not-a-uuid"
        for body in (missing, invalid):
            with self.subTest(body=body):
                response = facade.handler(event(body), Context())
                self.assertEqual(response["statusCode"], 400)
        facade._agentcore.invoke_agent_runtime.assert_not_called()

    def test_rejects_id_token_with_403(self) -> None:
        response = facade.handler(
            event(
                request_body(),
                {"sub": "user-1", "client_id": "client-123", "token_use": "id"},
            ),
            Context(),
        )
        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(self.response_body(response)["error"], "forbidden")

    def test_rejects_wrong_cognito_client_with_403(self) -> None:
        response = facade.handler(
            event(
                request_body(),
                {"sub": "user-1", "client_id": "other-client", "token_use": "access"},
            ),
            Context(),
        )
        self.assertEqual(response["statusCode"], 403)

    def test_rejects_missing_subject_with_403(self) -> None:
        response = facade.handler(
            event(request_body(), {"client_id": "client-123", "token_use": "access"}),
            Context(),
        )
        self.assertEqual(response["statusCode"], 403)

    def test_rejects_short_session(self) -> None:
        body = request_body()
        body["sessionId"] = "short"
        self.assertEqual(facade.handler(event(body), Context())["statusCode"], 400)

    def test_rejects_oversized_utf8_body_with_413_before_json_validation(self) -> None:
        body = '{"padding":"' + ("é" * facade.MAX_BODY_BYTES) + '"}'
        response = facade.handler(raw_event(body), Context())
        self.assertEqual(response["statusCode"], 413)
        self.assertEqual(self.response_body(response)["error"], "payload_too_large")
        facade._agentcore.invoke_agent_runtime.assert_not_called()

    def test_runtime_transport_and_deadline_budgets_leave_facade_overhead(self) -> None:
        config = facade.agentcore_config()
        self.assertEqual(config.connect_timeout, 2)
        self.assertEqual(config.read_timeout, 23)
        self.assertLessEqual(
            config.connect_timeout + config.read_timeout,
            facade.REQUEST_TIMEOUT_SECONDS - 2,
        )
        self.assertGreater(
            facade.RUNTIME_READ_TIMEOUT_SECONDS * 1000,
            facade.RUNTIME_DEADLINE_SAFETY_MS,
        )

    def test_returns_503_with_safe_correlation_when_runtime_is_not_ready(self) -> None:
        previous = facade.RUNTIME_READY
        facade.RUNTIME_READY = False
        try:
            response = facade.handler(event(request_body()), Context())
        finally:
            facade.RUNTIME_READY = previous
        body = self.response_body(response)
        self.assertEqual(response["statusCode"], 503)
        self.assertEqual(body["requestId"], "request-1")
        self.assertEqual(body["message"], facade.GENERIC_AGENT_ERROR)

    def test_maps_runtime_throttling_to_429_with_reference(self) -> None:
        facade._agentcore.invoke_agent_runtime.side_effect = ClientError(
            {
                "Error": {"Code": "ThrottlingException", "Message": "throttled"},
                "ResponseMetadata": {"HTTPStatusCode": 429, "RequestId": "aws-request-1"},
            },
            "InvokeAgentRuntime",
        )
        response = facade.handler(event(request_body()), Context())
        body = self.response_body(response)
        self.assertEqual(response["statusCode"], 429)
        self.assertEqual(body["code"], "ThrottlingException")
        self.assertEqual(body["requestId"], "request-1")
        self.assertNotIn("throttled", response["body"])

    def test_maps_runtime_client_error_to_502_with_safe_code_and_reference(self) -> None:
        facade._agentcore.invoke_agent_runtime.side_effect = ClientError(
            {
                "Error": {
                    "Code": "RuntimeClientError",
                    "Message": "private runtime details",
                },
                "ResponseMetadata": {"HTTPStatusCode": 403, "RequestId": "aws-request-2"},
            },
            "InvokeAgentRuntime",
        )
        response = facade.handler(event(request_body()), Context())
        body = self.response_body(response)
        self.assertEqual(response["statusCode"], 502)
        self.assertEqual(body["code"], "RuntimeClientError")
        self.assertEqual(body["requestId"], "request-1")
        self.assertNotIn("private runtime details", response["body"])

    def test_maps_runtime_timeout_to_504_with_reference_and_operation_id(self) -> None:
        facade._agentcore.invoke_agent_runtime.side_effect = ReadTimeoutError(
            endpoint_url="https://bedrock-agentcore.eu-west-3.amazonaws.com"
        )
        response = facade.handler(event(request_body()), Context())
        body = self.response_body(response)
        self.assertEqual(response["statusCode"], 504)
        self.assertEqual(body["requestId"], "request-1")
        self.assertEqual(body["operationId"], OPERATION_ID)

    def test_rejects_runtime_response_without_message_with_reference(self) -> None:
        facade._agentcore.invoke_agent_runtime.return_value = {
            "statusCode": 200,
            "response": b'{"unexpected":"value"}',
        }
        response = facade.handler(event(request_body()), Context())
        self.assertEqual(response["statusCode"], 502)
        self.assertEqual(self.response_body(response)["requestId"], "request-1")


if __name__ == "__main__":
    unittest.main()
