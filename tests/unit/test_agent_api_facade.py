from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
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
        "AGENT_RUNTIME_ENDPOINT_NAME": "DEFAULT",
        "COGNITO_CLIENT_ID": "client-123",
        "REQUEST_TIMEOUT_SECONDS": "28",
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


def event(body: dict, claims: dict | None = None) -> dict:
    return {
        "body": json.dumps(body),
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

    def test_success_injects_server_derived_actor_identity_and_scoped_session(self) -> None:
        facade._agentcore.invoke_agent_runtime.return_value = {
            "statusCode": 200,
            "response": b'{"message":"ok"}',
        }

        response = facade.handler(
            event({"prompt": " hello ", "sessionId": SESSION_ID}),
            Context(),
        )

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(self.response_body(response), {"message": "ok", "sessionId": SESSION_ID})

        invoke_args = facade._agentcore.invoke_agent_runtime.call_args.kwargs
        runtime_payload = json.loads(invoke_args["payload"])
        expected_internal_session = facade.derive_internal_session_id("user-1", SESSION_ID)

        self.assertEqual(invoke_args["qualifier"], "DEFAULT")
        self.assertEqual(invoke_args["runtimeSessionId"], expected_internal_session)
        self.assertEqual(runtime_payload["prompt"], "hello")
        self.assertEqual(runtime_payload["sessionId"], expected_internal_session)
        self.assertEqual(runtime_payload["trustedIdentity"]["actorId"], "user-1")
        self.assertNotIn(SESSION_ID, invoke_args["payload"].decode("utf-8"))

    def test_internal_session_is_deterministic_for_same_actor_and_external_session(self) -> None:
        first = facade.derive_internal_session_id("user-1", SESSION_ID)
        second = facade.derive_internal_session_id("user-1", SESSION_ID)

        self.assertEqual(first, second)
        self.assertRegex(first, r"^sid-v1-[a-f0-9]{64}$")
        self.assertTrue(facade.SESSION_ID_PATTERN.fullmatch(first))
        self.assertNotIn("user-1", first)
        self.assertNotIn(SESSION_ID, first)

    def test_internal_session_isolated_between_actors(self) -> None:
        user_a = facade.derive_internal_session_id("user-a", SESSION_ID)
        user_b = facade.derive_internal_session_id("user-b", SESSION_ID)

        self.assertNotEqual(user_a, user_b)

    def test_same_external_session_invokes_distinct_runtime_sessions_for_two_users(self) -> None:
        facade._agentcore.invoke_agent_runtime.return_value = {
            "statusCode": 200,
            "response": b'{"message":"ok"}',
        }

        for actor_id in ("user-a", "user-b"):
            response = facade.handler(
                event(
                    {"prompt": "hello", "sessionId": SESSION_ID},
                    {"sub": actor_id, "client_id": "client-123", "token_use": "access"},
                ),
                Context(),
            )
            self.assertEqual(response["statusCode"], 200)

        first_call, second_call = facade._agentcore.invoke_agent_runtime.call_args_list
        first_runtime_session = first_call.kwargs["runtimeSessionId"]
        second_runtime_session = second_call.kwargs["runtimeSessionId"]

        self.assertNotEqual(first_runtime_session, second_runtime_session)
        self.assertEqual(first_runtime_session, facade.derive_internal_session_id("user-a", SESSION_ID))
        self.assertEqual(second_runtime_session, facade.derive_internal_session_id("user-b", SESSION_ID))

    def test_rejects_client_supplied_identity(self) -> None:
        response = facade.handler(
            event({"prompt": "hello", "sessionId": SESSION_ID, "actorId": "attacker"}),
            Context(),
        )
        self.assertEqual(response["statusCode"], 400)
        facade._agentcore.invoke_agent_runtime.assert_not_called()

    def test_rejects_unknown_model_override(self) -> None:
        response = facade.handler(
            event({"prompt": "hello", "sessionId": SESSION_ID, "modelOverride": "arbitrary"}),
            Context(),
        )
        self.assertEqual(response["statusCode"], 400)
        facade._agentcore.invoke_agent_runtime.assert_not_called()

    def test_rejects_id_token_with_403(self) -> None:
        response = facade.handler(
            event(
                {"prompt": "hello", "sessionId": SESSION_ID},
                {"sub": "user-1", "client_id": "client-123", "token_use": "id"},
            ),
            Context(),
        )
        self.assertEqual(response["statusCode"], 403)
        self.assertEqual(self.response_body(response), {"error": "forbidden"})

    def test_rejects_wrong_cognito_client_with_403(self) -> None:
        response = facade.handler(
            event(
                {"prompt": "hello", "sessionId": SESSION_ID},
                {"sub": "user-1", "client_id": "other-client", "token_use": "access"},
            ),
            Context(),
        )
        self.assertEqual(response["statusCode"], 403)

    def test_rejects_missing_subject_with_403(self) -> None:
        response = facade.handler(
            event(
                {"prompt": "hello", "sessionId": SESSION_ID},
                {"client_id": "client-123", "token_use": "access"},
            ),
            Context(),
        )
        self.assertEqual(response["statusCode"], 403)

    def test_rejects_short_session(self) -> None:
        response = facade.handler(
            event({"prompt": "hello", "sessionId": "short"}),
            Context(),
        )
        self.assertEqual(response["statusCode"], 400)

    def test_returns_503_when_runtime_is_not_ready(self) -> None:
        previous = facade.RUNTIME_READY
        facade.RUNTIME_READY = False
        try:
            response = facade.handler(
                event({"prompt": "hello", "sessionId": SESSION_ID}),
                Context(),
            )
        finally:
            facade.RUNTIME_READY = previous
        self.assertEqual(response["statusCode"], 503)

    def test_maps_runtime_throttling_to_429(self) -> None:
        facade._agentcore.invoke_agent_runtime.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "throttled"}},
            "InvokeAgentRuntime",
        )
        response = facade.handler(
            event({"prompt": "hello", "sessionId": SESSION_ID}),
            Context(),
        )
        self.assertEqual(response["statusCode"], 429)

    def test_maps_runtime_timeout_to_504(self) -> None:
        facade._agentcore.invoke_agent_runtime.side_effect = ReadTimeoutError(
            endpoint_url="https://bedrock-agentcore.eu-west-3.amazonaws.com"
        )
        response = facade.handler(
            event({"prompt": "hello", "sessionId": SESSION_ID}),
            Context(),
        )
        self.assertEqual(response["statusCode"], 504)

    def test_rejects_runtime_response_without_message(self) -> None:
        facade._agentcore.invoke_agent_runtime.return_value = {
            "statusCode": 200,
            "response": b'{"unexpected":"value"}',
        }
        response = facade.handler(
            event({"prompt": "hello", "sessionId": SESSION_ID}),
            Context(),
        )
        self.assertEqual(response["statusCode"], 502)


if __name__ == "__main__":
    unittest.main()
