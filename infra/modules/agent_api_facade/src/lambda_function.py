from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

logger = logging.getLogger("agent-api-facade")
logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))

RUNTIME_READY = os.getenv("RUNTIME_READY", "false").lower() == "true"
RUNTIME_ARN = os.getenv("AGENT_RUNTIME_ARN", "")
RUNTIME_ENDPOINT = os.getenv("AGENT_RUNTIME_ENDPOINT_NAME", "default")
EXPECTED_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "28"))
RUNTIME_CONNECT_TIMEOUT_SECONDS = int(os.getenv("RUNTIME_CONNECT_TIMEOUT_SECONDS", "2"))
RUNTIME_READ_TIMEOUT_SECONDS = int(os.getenv("RUNTIME_READ_TIMEOUT_SECONDS", "23"))
RUNTIME_DEADLINE_SAFETY_MS = int(os.getenv("RUNTIME_DEADLINE_SAFETY_MS", "1500"))
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", "16384"))
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "4000"))

if REQUEST_TIMEOUT_SECONDS < 8:
    raise RuntimeError("REQUEST_TIMEOUT_SECONDS must be at least 8 seconds.")
if RUNTIME_CONNECT_TIMEOUT_SECONDS < 1 or RUNTIME_READ_TIMEOUT_SECONDS < 1:
    raise RuntimeError("Runtime transport timeouts must be positive.")
if (
    RUNTIME_CONNECT_TIMEOUT_SECONDS + RUNTIME_READ_TIMEOUT_SECONDS
    > REQUEST_TIMEOUT_SECONDS - 2
):
    raise RuntimeError(
        "Runtime transport budget must leave at least two seconds for facade processing."
    )
if (
    RUNTIME_DEADLINE_SAFETY_MS < 250
    or RUNTIME_DEADLINE_SAFETY_MS >= RUNTIME_READ_TIMEOUT_SECONDS * 1000
):
    raise RuntimeError(
        "RUNTIME_DEADLINE_SAFETY_MS must leave a positive Runtime execution window."
    )
if MAX_BODY_BYTES < 1024:
    raise RuntimeError("MAX_BODY_BYTES must be at least 1024 bytes.")

ALLOWED_KEYS = {"prompt", "sessionId", "operationId"}
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{33,128}$")
OPERATION_ID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
INTERNAL_SESSION_PREFIX = "sid-v1-"
GENERIC_AGENT_ERROR = "The agent request could not be completed."


def agentcore_config() -> Config:
    return Config(
        connect_timeout=RUNTIME_CONNECT_TIMEOUT_SECONDS,
        read_timeout=RUNTIME_READ_TIMEOUT_SECONDS,
        retries={"mode": "standard", "total_max_attempts": 1},
    )


_agentcore = boto3.client("bedrock-agentcore", config=agentcore_config())


class AuthorizationError(ValueError):
    pass


class PayloadTooLargeError(ValueError):
    pass


class RuntimeUnavailableError(RuntimeError):
    pass


class RuntimeResponseError(RuntimeError):
    pass


def safe_hash(value: str) -> str:
    return (
        hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else "unknown"
    )


def derive_internal_session_id(actor_id: str, external_session_id: str) -> str:
    """Create an opaque actor-scoped session identifier for AgentCore Runtime."""
    material = json.dumps(
        ["agentcore-session-v1", actor_id, external_session_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return INTERNAL_SESSION_PREFIX + hashlib.sha256(material).hexdigest()


def derive_deadline_epoch_ms() -> int:
    runtime_budget_ms = RUNTIME_READ_TIMEOUT_SECONDS * 1000 - RUNTIME_DEADLINE_SAFETY_MS
    return int(time.time() * 1000) + runtime_budget_ms


def http(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
        },
        "body": json.dumps(body, separators=(",", ":")),
    }


def service_error(
    status: int, error: str, request_id: str, **details: Any
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "error": error,
        "message": GENERIC_AGENT_ERROR,
        "requestId": request_id,
    }
    body.update(
        {key: value for key, value in details.items() if value not in (None, "")}
    )
    return http(status, body)


def _body_bytes(raw: Any) -> bytes:
    if isinstance(raw, str):
        return raw.encode("utf-8")
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    return b""


def body_from(event: Dict[str, Any]) -> Dict[str, Any]:
    if event.get("isBase64Encoded"):
        raise ValueError("Unsupported request encoding.")

    raw = event.get("body")
    encoded = _body_bytes(raw)
    if encoded and len(encoded) > MAX_BODY_BYTES:
        raise PayloadTooLargeError(
            f"Request body must be {MAX_BODY_BYTES} bytes or fewer."
        )

    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ValueError("Request body must be a JSON object.")

    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def claims_from(event: Dict[str, Any]) -> Dict[str, Any]:
    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}
    jwt = authorizer.get("jwt") or {}
    claims = jwt.get("claims") or {}
    if not isinstance(claims, dict):
        raise AuthorizationError("Authenticated JWT claims are missing.")
    return claims


def actor_id_from(event: Dict[str, Any]) -> str:
    claims = claims_from(event)
    if claims.get("token_use") != "access":
        raise AuthorizationError("A Cognito access token is required.")
    if not EXPECTED_CLIENT_ID or claims.get("client_id") != EXPECTED_CLIENT_ID:
        raise AuthorizationError("JWT client_id is not authorized.")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise AuthorizationError("Authenticated subject is missing.")
    return subject.strip()


def validate_payload(data: Dict[str, Any]) -> tuple[str, str, str]:
    unexpected = sorted(set(data) - ALLOWED_KEYS)
    if unexpected:
        raise ValueError("Unsupported request fields: " + ", ".join(unexpected))

    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required.")
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"prompt must be {MAX_PROMPT_CHARS} characters or fewer.")

    session_id = data.get("sessionId")
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("sessionId must contain 33 to 128 safe characters.")

    operation_id = data.get("operationId")
    if not isinstance(operation_id, str) or not OPERATION_ID_PATTERN.fullmatch(
        operation_id
    ):
        raise ValueError("operationId must be a UUID.")

    return prompt, session_id, operation_id.lower()


def runtime_payload(
    prompt: str,
    internal_session_id: str,
    actor_id: str,
    operation_id: str,
    request_id: str,
    deadline_epoch_ms: int,
) -> Dict[str, Any]:
    return {
        "prompt": prompt,
        "sessionId": internal_session_id,
        "operationId": operation_id,
        "requestId": request_id,
        "deadlineEpochMs": deadline_epoch_ms,
        "trustedIdentity": {"actorId": actor_id},
    }


def read_payload(value: Any) -> Any:
    if value is None:
        raise RuntimeResponseError("Agent Runtime response body is missing.")
    if hasattr(value, "read"):
        value = value.read()
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def call_runtime(payload: Dict[str, Any], request_id: str) -> Any:
    if not RUNTIME_READY or not RUNTIME_ARN:
        raise RuntimeUnavailableError("Agent Runtime is not ready.")
    result = _agentcore.invoke_agent_runtime(
        agentRuntimeArn=RUNTIME_ARN,
        qualifier=RUNTIME_ENDPOINT,
        runtimeSessionId=payload["sessionId"],
        contentType="application/json",
        accept="application/json",
        payload=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )
    status_code = int(result.get("statusCode", 200))
    content_type = str(result.get("contentType", "unknown"))
    logger.info(
        json.dumps(
            {
                "event": "runtime_response_metadata",
                "request_id": request_id,
                "status_code": status_code,
                "content_type": content_type,
                "runtime_endpoint": RUNTIME_ENDPOINT,
                "runtime_arn_hash": safe_hash(RUNTIME_ARN),
            }
        )
    )
    if status_code >= 400:
        raise RuntimeResponseError(f"Agent Runtime returned status {status_code}.")
    return read_payload(result.get("response") or result.get("payload"))


def message_from(result: Any) -> str:
    if isinstance(result, str) and result.strip():
        return result.strip()
    if isinstance(result, dict):
        for key in ("message", "response", "result"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise RuntimeResponseError("Agent Runtime response does not contain a message.")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    started = time.monotonic()
    request_id = str(getattr(context, "aws_request_id", "unknown"))[:128]
    actor_id = ""
    external_session_id = ""
    internal_session_id = ""
    operation_id = ""
    try:
        data = body_from(event)
        prompt, external_session_id, operation_id = validate_payload(data)
        actor_id = actor_id_from(event)
        internal_session_id = derive_internal_session_id(actor_id, external_session_id)
        deadline_epoch_ms = derive_deadline_epoch_ms()
        payload = runtime_payload(
            prompt,
            internal_session_id,
            actor_id,
            operation_id,
            request_id,
            deadline_epoch_ms,
        )
        result = call_runtime(payload, request_id)
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        logger.info(
            json.dumps(
                {
                    "event": "facade_invocation",
                    "request_id": request_id,
                    "actor_hash": safe_hash(actor_id),
                    "session_hash": safe_hash(external_session_id),
                    "runtime_session_hash": safe_hash(internal_session_id),
                    "operation_hash": safe_hash(operation_id),
                    "duration_ms": duration_ms,
                    "status": "success",
                }
            )
        )
        return http(
            200,
            {
                "message": message_from(result),
                "sessionId": external_session_id,
                "operationId": operation_id,
                "requestId": request_id,
            },
        )
    except PayloadTooLargeError as exc:
        logger.warning(
            json.dumps({"event": "facade_payload_too_large", "request_id": request_id})
        )
        return http(
            413,
            {
                "error": "payload_too_large",
                "message": str(exc),
                "requestId": request_id,
            },
        )
    except AuthorizationError as exc:
        logger.warning(
            json.dumps(
                {
                    "event": "facade_authorization_rejected",
                    "request_id": request_id,
                    "reason": str(exc),
                }
            )
        )
        return http(403, {"error": "forbidden", "requestId": request_id})
    except ValueError as exc:
        logger.warning(
            json.dumps(
                {
                    "event": "facade_rejected",
                    "request_id": request_id,
                    "actor_hash": safe_hash(actor_id),
                    "session_hash": safe_hash(external_session_id),
                    "operation_hash": safe_hash(operation_id),
                    "reason": str(exc),
                }
            )
        )
        return http(
            400, {"error": "bad_request", "message": str(exc), "requestId": request_id}
        )
    except RuntimeUnavailableError:
        logger.warning(
            json.dumps({"event": "runtime_unavailable", "request_id": request_id})
        )
        return service_error(503, "runtime_unavailable", request_id)
    except RuntimeResponseError as exc:
        logger.error(
            json.dumps(
                {
                    "event": "runtime_invalid_response",
                    "request_id": request_id,
                    "operation_hash": safe_hash(operation_id),
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                    "runtime_endpoint": RUNTIME_ENDPOINT,
                }
            )
        )
        return service_error(502, "runtime_invalid_response", request_id)
    except ReadTimeoutError:
        logger.warning(
            json.dumps(
                {
                    "event": "runtime_timeout",
                    "request_id": request_id,
                    "operation_hash": safe_hash(operation_id),
                }
            )
        )
        return http(
            504,
            {
                "error": "runtime_timeout",
                "message": "Agent request timed out.",
                "requestId": request_id,
                "operationId": operation_id,
            },
        )
    except ClientError as exc:
        error = exc.response.get("Error", {})
        metadata = exc.response.get("ResponseMetadata", {})
        code = error.get("Code", "ClientError")
        status = (
            429 if code in {"ThrottlingException", "TooManyRequestsException"} else 502
        )
        logger.error(
            json.dumps(
                {
                    "event": "runtime_client_error",
                    "request_id": request_id,
                    "operation_hash": safe_hash(operation_id),
                    "error_code": code,
                    "http_status": metadata.get("HTTPStatusCode"),
                    "aws_request_id": metadata.get("RequestId"),
                    "runtime_endpoint": RUNTIME_ENDPOINT,
                    "runtime_arn_hash": safe_hash(RUNTIME_ARN),
                }
            )
        )
        return service_error(status, "runtime_error", request_id, code=code)
    except BotoCoreError as exc:
        logger.error(
            json.dumps(
                {
                    "event": "runtime_transport_error",
                    "request_id": request_id,
                    "operation_hash": safe_hash(operation_id),
                    "error_type": type(exc).__name__,
                    "runtime_endpoint": RUNTIME_ENDPOINT,
                }
            )
        )
        return service_error(502, "runtime_transport_error", request_id)
    except Exception as exc:
        logger.error(
            json.dumps(
                {
                    "event": "facade_unexpected_error",
                    "request_id": request_id,
                    "operation_hash": safe_hash(operation_id),
                    "error_type": type(exc).__name__,
                }
            )
        )
        return service_error(500, "internal_error", request_id)
