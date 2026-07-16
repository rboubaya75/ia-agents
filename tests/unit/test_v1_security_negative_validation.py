from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "run_v1_security_negative_validation.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("v1_security_negative", SCRIPT_PATH)
if SCRIPT_SPEC is None or SCRIPT_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
security = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = security
SCRIPT_SPEC.loader.exec_module(security)

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
FACADE_PATH = (
    ROOT
    / "infra"
    / "modules"
    / "agent_api_facade"
    / "src"
    / "lambda_function.py"
)
FACADE_SPEC = importlib.util.spec_from_file_location(
    "phase3_agent_api_facade", FACADE_PATH
)
if FACADE_SPEC is None or FACADE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load {FACADE_PATH}")
facade = importlib.util.module_from_spec(FACADE_SPEC)
sys.modules[FACADE_SPEC.name] = facade
FACADE_SPEC.loader.exec_module(facade)

API_URL = "https://api.example.test/agent/invoke"
ALLOWED_ORIGIN = "https://frontend.example.test"
FORBIDDEN_ORIGIN = "https://attacker.example.test"
ACCESS_TOKEN = "access-token-sensitive"
ID_TOKEN = "id-token-sensitive"


class Context:
    aws_request_id = "request-phase3"


class FakeTransport:
    def __init__(self, *, echo_forbidden: bool = False) -> None:
        self.echo_forbidden = echo_forbidden

    def __call__(self, method, url, headers, body, timeout):
        del url, body, timeout
        lower = {str(key).lower(): str(value) for key, value in headers.items()}
        if method == "OPTIONS":
            origin = lower.get("origin")
            if origin == ALLOWED_ORIGIN or self.echo_forbidden:
                return security.HttpResponse(
                    204,
                    {
                        "access-control-allow-origin": origin,
                        "access-control-allow-methods": "POST,OPTIONS",
                    },
                    b"",
                )
            return security.HttpResponse(204, {}, b"")

        auth = lower.get("authorization", "")
        if auth == f"Bearer {ACCESS_TOKEN}":
            return security.HttpResponse(
                400,
                {"access-control-allow-origin": ALLOWED_ORIGIN},
                b'{"error":"bad_request","requestId":"request-phase3"}',
            )
        if auth == f"Bearer {ID_TOKEN}":
            return security.HttpResponse(403, {}, b'{"error":"forbidden"}')
        return security.HttpResponse(401, {}, b'{"message":"Unauthorized"}')


class SecurityNegativeHarnessTests(unittest.TestCase):
    def test_catalog_covers_all_forbidden_fields_and_boundaries(self) -> None:
        cases = {item["case"] for item in security.catalog()}
        for field, _ in security.FORBIDDEN_FIELDS:
            self.assertIn(f"inject_{field}", cases)
        self.assertTrue(
            {
                "http_no_jwt",
                "http_malformed_jwt",
                "http_id_token",
                "cors_allowed_preflight",
                "cors_forbidden_preflight",
                "runtime_direct_invoke_denied",
            }.issubset(cases)
        )

    def test_http_suite_passes_and_never_records_tokens(self) -> None:
        results = security.run_http_probes(
            api_url=API_URL,
            allowed_origin=ALLOWED_ORIGIN,
            forbidden_origin=FORBIDDEN_ORIGIN,
            access_token=ACCESS_TOKEN,
            id_token=ID_TOKEN,
            require_authenticated_cases=True,
            require_id_token=True,
            transport=FakeTransport(),
        )
        self.assertTrue(results)
        self.assertTrue(all(result.status == "PASS" for result in results))
        evidence = security.build_evidence(
            results=results,
            api_url=API_URL,
            allowed_origin=ALLOWED_ORIGIN,
            code_sha="sha-test",
        )
        security.ensure_redacted(evidence, (ACCESS_TOKEN, ID_TOKEN))
        serialized = json.dumps(evidence)
        self.assertNotIn(ACCESS_TOKEN, serialized)
        self.assertNotIn(ID_TOKEN, serialized)
        self.assertNotIn("security-probe-actor", serialized)
        self.assertNotIn("security-probe-user", serialized)

    def test_network_failure_becomes_redacted_status_zero(self) -> None:
        with patch.object(
            security.request,
            "urlopen",
            side_effect=security.error.URLError("private-network-detail"),
        ):
            response = security.urllib_transport(
                "POST",
                API_URL,
                {"authorization": f"Bearer {ACCESS_TOKEN}"},
                b'{}',
                1.0,
            )
        self.assertEqual(response.status, 0)
        self.assertEqual(response.headers, {})
        self.assertEqual(response.body, b"")
        serialized = repr(security.asdict(response))
        self.assertNotIn("private-network-detail", serialized)
        self.assertNotIn(ACCESS_TOKEN, serialized)

    def test_forbidden_origin_echo_is_a_failure(self) -> None:
        results = security.run_http_probes(
            api_url=API_URL,
            allowed_origin=ALLOWED_ORIGIN,
            forbidden_origin=FORBIDDEN_ORIGIN,
            access_token=ACCESS_TOKEN,
            id_token=ID_TOKEN,
            transport=FakeTransport(echo_forbidden=True),
        )
        forbidden = next(
            result for result in results if result.case == "cors_forbidden_preflight"
        )
        self.assertEqual(forbidden.status, "FAIL")

    def test_required_authenticated_cases_fail_closed_without_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "Authenticated cases require"):
            security.run_http_probes(
                api_url=API_URL,
                allowed_origin=ALLOWED_ORIGIN,
                forbidden_origin=FORBIDDEN_ORIGIN,
                access_token=None,
                id_token=ID_TOKEN,
                require_authenticated_cases=True,
                transport=FakeTransport(),
            )

    def test_api_gateway_cors_and_jwt_contract_is_fail_closed(self) -> None:
        source = (
            ROOT / "infra" / "modules" / "api_gateway_agent_ingress" / "main.tf"
        ).read_text(encoding="utf-8")
        self.assertIn("allow_credentials = false", source)
        self.assertIn('allow_methods     = ["OPTIONS", "POST"]', source)
        self.assertIn("allow_origins     = var.allowed_origins", source)
        self.assertIn(
            'identity_sources = ["$request.header.Authorization"]', source
        )
        self.assertIn('authorization_type = "JWT"', source)
        self.assertNotIn('allow_origins     = ["*"]', source)

    def test_runtime_resource_policy_contract_is_explicit(self) -> None:
        source = (
            ROOT / "infra" / "environments" / "test" / "agentcore_native.tf"
        ).read_text(encoding="utf-8")
        self.assertIn('sid     = "AllowOnlySecurityFacadeRole"', source)
        self.assertIn('sid     = "DenyOtherRuntimeInvokers"', source)
        self.assertIn('actions = ["bedrock-agentcore:InvokeAgentRuntime"]', source)
        self.assertIn('variable = "aws:PrincipalArn"', source)
        self.assertIn("values   = [module.agent_api_facade.role_arn]", source)

    def test_runtime_direct_invoke_access_denied_passes(self) -> None:
        client = Mock()
        client.invoke_agent_runtime.side_effect = ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "private details",
                },
                "ResponseMetadata": {"HTTPStatusCode": 403},
            },
            "InvokeAgentRuntime",
        )
        result = security.run_runtime_deny_probe(
            runtime_client=client,
            runtime_arn="arn:aws:bedrock-agentcore:eu-west-3:123456789012:runtime/test",
            endpoint_name="default",
        )
        self.assertEqual(result.status, "PASS")
        self.assertNotIn("private details", json.dumps(security.asdict(result)))

    def test_runtime_direct_invoke_success_is_a_failure(self) -> None:
        client = Mock()
        client.invoke_agent_runtime.return_value = {
            "statusCode": 200,
            "response": io.BytesIO(b"secret"),
        }
        result = security.run_runtime_deny_probe(
            runtime_client=client,
            runtime_arn="arn:aws:bedrock-agentcore:eu-west-3:123456789012:runtime/test",
            endpoint_name="default",
        )
        self.assertEqual(result.status, "FAIL")
        self.assertNotIn("secret", json.dumps(security.asdict(result)))


class FacadeNegativeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        facade._agentcore = Mock()

    @staticmethod
    def event(body: dict, claims: dict | None = None) -> dict:
        return {
            "body": json.dumps(body),
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": claims
                        or {
                            "sub": "user-phase3",
                            "client_id": "client-123",
                            "token_use": "access",
                        }
                    }
                }
            },
        }

    @staticmethod
    def base_body() -> dict:
        return {
            "prompt": "hello",
            "sessionId": "550e8400-e29b-41d4-a716-446655440000",
            "operationId": "76e6f404-49de-4dc4-9c60-f2c25a0de91f",
        }

    def test_facade_rejects_every_forbidden_field_before_runtime(self) -> None:
        for field, value in security.FORBIDDEN_FIELDS:
            with self.subTest(field=field):
                body = self.base_body()
                body[field] = value
                response = facade.handler(self.event(body), Context())
                self.assertEqual(response["statusCode"], 400)
        facade._agentcore.invoke_agent_runtime.assert_not_called()

    def test_rejection_log_does_not_contain_injected_values(self) -> None:
        body = self.base_body()
        body["actorId"] = "raw-sensitive-actor-value"
        with self.assertLogs("agent-api-facade", level=logging.WARNING) as captured:
            response = facade.handler(self.event(body), Context())
        self.assertEqual(response["statusCode"], 400)
        self.assertNotIn("raw-sensitive-actor-value", "\n".join(captured.output))

    def test_token_use_client_and_subject_fail_closed(self) -> None:
        invalid_claims = (
            {"sub": "user", "client_id": "client-123", "token_use": "id"},
            {"sub": "user", "client_id": "other-client", "token_use": "access"},
            {"client_id": "client-123", "token_use": "access"},
        )
        for claims in invalid_claims:
            with self.subTest(claims=claims):
                response = facade.handler(
                    self.event(self.base_body(), claims), Context()
                )
                self.assertEqual(response["statusCode"], 403)
        facade._agentcore.invoke_agent_runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
