from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Iterator

from agents.models import (
    AgentError,
    AgentErrorCode,
    AgentRequest,
    AgentResult,
    AgentStreamEvent,
    StreamDelta,
    StreamDone,
    StreamError,
    StreamMeta,
)

logger = logging.getLogger(__name__)

_INTERNAL_SESSION_PREFIX = "sid-v1-"

# V1 validate_request rejects deadlineEpochMs beyond now + 120_000 ms. The margin
# absorbs clock drift between the FastAPI task and Runtime, which do not share a clock.
_V1_MAX_DEADLINE_MS = 120_000
_CLOCK_DRIFT_MARGIN_MS = 5_000
_DEADLINE_MAX_MS = _V1_MAX_DEADLINE_MS - _CLOCK_DRIFT_MARGIN_MS

# The socket must never outlive the deadline handed to Runtime: past that point Runtime
# is supposed to have stopped, and waiting longer only pins the calling thread.
_MAX_READ_TIMEOUT_SECONDS = _DEADLINE_MAX_MS // 1000


def _safe_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else "unknown"


def _derive_internal_session_id(actor_id: str, external_session_id: str) -> str:
    """Opaque actor-scoped session identifier accepted by AgentCore Runtime V1."""
    material = json.dumps(
        ["agentcore-session-v1", actor_id, external_session_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return _INTERNAL_SESSION_PREFIX + hashlib.sha256(material).hexdigest()


def _read_payload(value: Any) -> Any:
    if value is None:
        raise RuntimeError("Agent Runtime response body is missing.")
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


def _message_from(result: Any) -> str:
    if isinstance(result, str) and result.strip():
        return result.strip()
    if isinstance(result, dict):
        for key in ("message", "response", "result"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise RuntimeError("Agent Runtime response does not contain a message.")


def _to_stream_error(exc: Exception) -> StreamError:
    try:
        from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

        if isinstance(exc, ReadTimeoutError):
            return StreamError(error=AgentError(
                code=AgentErrorCode.DEADLINE_EXCEEDED,
                message="Agent Runtime timed out.",
            ))
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"ThrottlingException", "TooManyRequestsException"}:
                return StreamError(error=AgentError(
                    code=AgentErrorCode.MODEL_THROTTLED,
                    message="Agent Runtime throttled the request.",
                ))
        if isinstance(exc, BotoCoreError):
            logger.error("Agent Runtime transport error: %s", exc)
            return StreamError(error=AgentError(
                code=AgentErrorCode.INTERNAL_ERROR,
                message="Agent Runtime transport error.",
            ))
    except ImportError:
        pass
    logger.error("Agent Runtime unexpected error: %s", type(exc).__name__, exc_info=exc)
    return StreamError(error=AgentError(
        code=AgentErrorCode.INTERNAL_ERROR,
        message="Agent Runtime error.",
    ))


class AgentCoreRuntimeAdapter:
    """
    Calls AgentCore Runtime V1 via boto3 invoke_agent_runtime.

    streaming="emulated": V1 returns a plain str, not a stream (LLD-003 §7.3).
    trustedIdentity carries only actorId: V1 validate_request rejects any extra key.
    input_tokens/output_tokens are 0: V1 does not surface usage metadata.
    The boto3 client is constructed lazily so CI can import this module without
    AWS credentials or a configured region.

    read_timeout_seconds bounds how long one call pins its worker thread. Cancellation
    does not reach an in-flight invoke_agent_runtime call (AgentRequest carries no
    cancellation token), so a client that disconnects leaves the thread busy until this
    timeout expires — lowering it bounds that exposure, raising it allows longer agent
    runs. It is capped at the deadline handed to Runtime, never above it.
    """

    def __init__(
        self,
        runtime_arn: str,
        endpoint_name: str = "default",
        connect_timeout_seconds: int = 5,
        read_timeout_seconds: int = _MAX_READ_TIMEOUT_SECONDS,
    ) -> None:
        self._runtime_arn = runtime_arn
        self._endpoint_name = endpoint_name
        self._connect_timeout = max(1, connect_timeout_seconds)
        self._read_timeout = max(1, min(read_timeout_seconds, _MAX_READ_TIMEOUT_SECONDS))
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-agentcore",
                config=Config(
                    connect_timeout=self._connect_timeout,
                    read_timeout=self._read_timeout,
                    # No SDK retry: the deadline is the only bound, and a silent retry
                    # would spend a budget the caller already accounted for.
                    retries={"mode": "standard", "total_max_attempts": 1},
                ),
            )
        return self._client

    def _error_result(self, request: AgentRequest, error: AgentError) -> AgentResult:
        return AgentResult(
            answer="",
            turn_count=0,
            input_tokens=0,
            output_tokens=0,
            tool_calls_count=0,
            budget_exhausted=False,
            # No answer was produced by the model, so the run cannot be called nominal.
            degraded=True,
            served_invocation_id=request.config.invocation_id or "agentcore-v1",
            error=error,
        )

    def invoke(self, request: AgentRequest) -> AgentResult:
        """Blocking invocation, built on invoke_stream so both paths share one contract.

        The Protocol declares invoke() alongside invoke_stream(); an adapter that only
        honours one of them fails in production on a caller CI never exercises.
        """
        for event in self.invoke_stream(request):
            if isinstance(event, StreamDone):
                return event.result
            if isinstance(event, StreamError):
                return self._error_result(request, event.error)

        # invoke_stream always emits one terminal event; this closes the type hole
        # rather than letting a silent None escape as an AgentResult.
        logger.error("adapter stream ended without a terminal event")
        return self._error_result(request, AgentError(
            code=AgentErrorCode.INTERNAL_ERROR,
            message="Agent ended without a terminal event",
        ))

    def invoke_stream(self, request: AgentRequest) -> Iterator[AgentStreamEvent]:
        op_id = request.operation_context.operation_id
        # StreamMeta first — client knows the effective mode before the first model call.
        yield StreamMeta(streaming="emulated", operation_id=op_id)

        actor_id = request.trusted_identity.actor_id
        session_id = _derive_internal_session_id(actor_id, request.runtime_session_id)

        now_ms = int(time.time() * 1000)
        deadline_ms = min(
            request.operation_context.deadline_epoch_ms,
            now_ms + _DEADLINE_MAX_MS,
        )

        payload = {
            "prompt": request.message,
            "sessionId": session_id,
            "operationId": op_id,
            "requestId": request.operation_context.request_id,
            "deadlineEpochMs": deadline_ms,
            # Exactly {"actorId"} — V1 validate_request rejects tenantId or any other key.
            "trustedIdentity": {"actorId": actor_id},
        }

        try:
            client = self._get_client()
            raw = client.invoke_agent_runtime(
                agentRuntimeArn=self._runtime_arn,
                qualifier=self._endpoint_name,
                runtimeSessionId=session_id,
                contentType="application/json",
                accept="application/json",
                payload=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            )
            status_code = int(raw.get("statusCode", 200))
            if status_code >= 400:
                raise RuntimeError(f"Agent Runtime returned status {status_code}.")
            result_data = _read_payload(raw.get("response") or raw.get("payload"))
            answer = _message_from(result_data)
        except Exception as exc:
            # Errors are emitted, never raised: orchestrator would overwrite the code.
            yield _to_stream_error(exc)
            return

        yield StreamDelta(text=answer)
        yield StreamDone(result=AgentResult(
            answer=answer,
            turn_count=1,
            input_tokens=0,
            output_tokens=0,
            tool_calls_count=0,
            budget_exhausted=False,
            degraded=False,
            served_invocation_id=request.config.invocation_id or "agentcore-v1",
        ))
