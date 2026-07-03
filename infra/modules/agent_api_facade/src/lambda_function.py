from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("agent-api-facade")
logger.setLevel(getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))

RUNTIME_READY = os.getenv("RUNTIME_READY", "false").lower() == "true"
RUNTIME_ARN = os.getenv("AGENT_RUNTIME_ARN", "")
RUNTIME_ENDPOINT = os.getenv("AGENT_RUNTIME_ENDPOINT_NAME", "default")
DENIED_KEYS = {"actorId", "actor_id", "userId", "user_id", "tenantId", "tenant_id", "trustedIdentity", "trusted_identity"}


def http(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def body_from(event: Dict[str, Any]) -> Dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raise ValueError("Unsupported request encoding.")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def subject_from(event: Dict[str, Any]) -> str:
    ctx = event.get("requestContext") or {}
    auth = ctx.get("authorizer") or {}
    jwt = auth.get("jwt") or {}
    claims = jwt.get("claims") or {}
    subject = claims.get("sub") if isinstance(claims, dict) else None
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("Authenticated subject is missing.")
    return subject.strip()


def validate(data: Dict[str, Any]) -> None:
    if any(key in data for key in DENIED_KEYS):
        raise ValueError("Identity fields are not accepted from the browser.")
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required.")


def session_id(event: Dict[str, Any], data: Dict[str, Any]) -> str:
    provided = data.get("sessionId") or data.get("session_id")
    if isinstance(provided, str) and len(provided) >= 33:
        return provided
    request_id = (event.get("requestContext") or {}).get("requestId") or uuid.uuid4().hex
    return f"session-{request_id}-{uuid.uuid4().hex}"


def runtime_payload(event: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(data)
    payload["sessionId"] = session_id(event, data)
    payload["trustedIdentity"] = {"actorId": subject_from(event)}
    return payload


def read_payload(value: Any) -> Any:
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
        return {"status": "runtime_not_ready", "message": "Agent runtime is not deployed or not activated yet."}

    agentcore = boto3.client("bedrock-agentcore")
    encoded = json.dumps(payload).encode("utf-8")
    common = {"agentRuntimeArn": RUNTIME_ARN, "runtimeSessionId": payload["sessionId"], "payload": encoded}

    try:
        result = agentcore.invoke_agent_runtime(qualifier=RUNTIME_ENDPOINT, **common)
    except TypeError:
        result = agentcore.invoke_agent_runtime(**common)

    return read_payload(result.get("payload"))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        data = body_from(event)
        validate(data)
        result = call_runtime(runtime_payload(event, data))
        return http(200, {"result": result})
    except ValueError as exc:
        logger.warning("bad_request: %s", exc)
        return http(400, {"error": "bad_request", "message": str(exc)})
    except ClientError as exc:
        logger.exception("runtime_error")
        code = exc.response.get("Error", {}).get("Code", "ClientError")
        return http(502, {"error": "runtime_error", "code": code})
    except Exception:
        logger.exception("unexpected_error")
        return http(500, {"error": "internal_error"})
