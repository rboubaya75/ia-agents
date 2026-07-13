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
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "4000"))

ALLOWED_KEYS = {"prompt", "sessionId"}
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{33,128}$")

_agentcore = boto3.client(
    "bedrock-agentcore",
    config=Config(
        connect_timeout=3,
        read_timeout=max(1, REQUEST_TIMEOUT_SECONDS - 3),
        retries={"mode": "standard", "total_max_attempts": 1},
    ),
)


class RuntimeUnavailableError(RuntimeError):
    pass


class RuntimeResponseError(RuntimeError):
    pass


def safe_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else "unknown"


def http(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
        },
        "body": json.dumps(body, separators=(",", ":")),
    }


def body_from(event: Dict[str, Any]) -> Dict[str, Any]:
    if event.get("isBase64Encoded"):
        raise ValueError("Unsupported request encoding.")

    raw = event.get("body")
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
        raise ValueError("Authenticated JWT claims are missing.")
    return claims


def actor_id_from(event: Dict[str, Any]) -> str:
    claims = claims_from(event)

    if claims.get("token_use") != "access":
        raise ValueError("A Cognito access token is required.")

    if not EXPECTED_CLIENT_ID or claims.get("client_id") != EXPECTED_CLIENT_ID:
        raise ValueError("JWT client_id is not authorized.")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("Authenticated subject is missing.")
    return subject.strip()


def validate_payload(data: Dict[str, Any]) -> tuple[str, str]:
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

    return prompt, session_id


def runtime_payload(prompt: str, session_id: str, actor_id: str) -> Dict[str, Any]:
    return {
        "prompt": prompt,
        "sessionId": session_id,
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


def call_runtime(payload: Dict[str, Any]) -> Any:
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
    request_id = getattr(context, "aws_request_id", "unknown")
    actor_id = ""
    session_id = ""

    try:
        data = body_from(event)
        prompt, session_id = validate_payload(data)
        actor_id = actor_id_from(event)

        result = call_runtime(runtime_payload(prompt, session_id, actor_id))
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        logger.info(
            json.dumps(
                {
                    "event": "facade_invocation",
                    "request_id": request_id,
                    "actor_hash": safe_hash(actor_id),
                    "session_hash": safe_hash(session_id),
                    "duration_ms": duration_ms,
                    "status": "success",
                }
            )
        )
        return http(200, {"message": message_from(result), "sessionId": session_id})

    except ValueError as exc:
        logger.warning(
            json.dumps(
                {
                    "event": "facade_rejected",
                    "request_id": request_id,
                    "actor_hash": safe_hash(actor_id),
                    "session_hash": safe_hash(session_id),
                    "reason": str(exc),
                }
            )
        )
        return http(400, {"error": "bad_request", "message": str(exc)})
    except RuntimeUnavailableError:
        logger.warning(json.dumps({"event": "runtime_unavailable", "request_id": request_id}))
        return http(503, {"error": "runtime_unavailable"})
    except RuntimeResponseError as exc:
        logger.error(
            json.dumps(
                {
                    "event": "runtime_invalid_response",
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                }
            )
        )
        return http(502, {"error": "runtime_invalid_response"})
    except ReadTimeoutError:
        logger.warning(json.dumps({"event": "runtime_timeout", "request_id": request_id}))
        return http(504, {"error": "runtime_timeout", "message": "Agent request timed out."})
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "ClientError")
        status = 429 if code in {"ThrottlingException", "TooManyRequestsException"} else 502
        logger.error(json.dumps({"event": "runtime_client_error", "request_id": request_id, "error_code": code}))
        return http(status, {"error": "runtime_error", "code": code})
    except BotoCoreError as exc:
        logger.error(
            json.dumps(
                {
                    "event": "runtime_transport_error",
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                }
            )
        )
        return http(502, {"error": "runtime_transport_error"})
    except Exception as exc:
        logger.error(
            json.dumps(
                {
                    "event": "facade_unexpected_error",
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                }
            )
        )
        return http(500, {"error": "internal_error"})
