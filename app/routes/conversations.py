import asyncio
import json
import logging
import threading
import time
from typing import Any, AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.deps import bearer_claims
from app.state import PendingOperation, cancel_registry
from agents.adapter.stub_adapter import StubAdapter
from agents.domain.orchestrator import Orchestrator
from agents.models import (
    AgentBudget,
    AgentConfig,
    AgentErrorCode,
    AgentRequest,
    AgentStreamEvent,
    CancellationCause,
    OperationContext,
    RetrievalContext,
    StreamCancelled,
    StreamCitation,
    StreamDelta,
    StreamDone,
    StreamError,
    StreamMeta,
    TrustedIdentity,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

def _build_orchestrator() -> Orchestrator:
    if settings.agentcore_runtime_arn:
        from agents.adapter.agentcore_runtime_adapter import AgentCoreRuntimeAdapter
        return Orchestrator(AgentCoreRuntimeAdapter(
            runtime_arn=settings.agentcore_runtime_arn,
            endpoint_name=settings.agent_runtime_endpoint_name,
        ))
    return Orchestrator(StubAdapter())


_orchestrator = _build_orchestrator()


class MessageRequest(BaseModel):
    # Bounded so a single request cannot pin an unbounded amount of memory, and so an
    # oversized prompt is refused at the edge rather than by the model provider.
    # Upper bound matches V1 MAX_PROMPT_CHARS — larger values are rejected by Runtime.
    message: str = Field(min_length=1, max_length=4000)


def _resolve_tenant(actor_id: str) -> str:
    # Stub: tenant_id = actor_id until the V2-LLD-005 §3.4 registry is implemented.
    return actor_id


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _serialize(ev: AgentStreamEvent) -> str:
    if isinstance(ev, StreamMeta):
        return _sse("meta", {"streaming": ev.streaming, "operationId": ev.operation_id})
    if isinstance(ev, StreamDelta):
        return _sse("delta", {"text": ev.text})
    if isinstance(ev, StreamCitation):
        return _sse("citation", {"citations": list(ev.citations)})
    if isinstance(ev, StreamDone):
        r = ev.result
        return _sse("done", {
            "answer": r.answer,
            "turnCount": r.turn_count,
            "inputTokens": r.input_tokens,
            "outputTokens": r.output_tokens,
            "toolCallsCount": r.tool_calls_count,
            "budgetExhausted": r.budget_exhausted,
            "degraded": r.degraded,
            "servedInvocationId": r.served_invocation_id,
        })
    if isinstance(ev, StreamCancelled):
        r = ev.result
        return _sse("cancelled", {
            "cause": ev.cause.value,
            "inputTokens": r.input_tokens,
            "outputTokens": r.output_tokens,
        })
    if isinstance(ev, StreamError):
        return _sse("error", {
            "code": ev.error.code.value,
            "message": ev.error.message,
        })
    # Dropping an event silently would leave the client short of the stream contract.
    logger.error("no SSE serialisation for stream event %s", type(ev).__name__)
    return ""


def _is_terminal(ev: AgentStreamEvent) -> bool:
    return isinstance(ev, (StreamDone, StreamCancelled, StreamError))


async def _event_stream(
    request: AgentRequest,
    cancel_event: asyncio.Event,
) -> AsyncGenerator[str, None]:
    keepalive = settings.sse_keepalive_seconds
    queue: asyncio.Queue[AgentStreamEvent | BaseException | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _post(item: AgentStreamEvent | BaseException | None) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:
            # Loop already closed (server shutdown): nobody is left to read the event.
            pass

    def _run_sync() -> None:
        try:
            for ev in _orchestrator.run_stream(request):
                _post(ev)
                if cancel_event.is_set():
                    return
        except BaseException as exc:
            _post(exc)
        finally:
            _post(None)

    thread = threading.Thread(target=_run_sync, daemon=True)
    thread.start()

    # The cancellation flag is awaited alongside the queue rather than polled between
    # events: polling would delay a cancel by up to one keep-alive interval whenever the
    # agent is quiet, which is exactly when a client is most likely to cancel.
    next_event = asyncio.ensure_future(queue.get())
    cancelled = asyncio.ensure_future(cancel_event.wait())

    try:
        while True:
            done, _ = await asyncio.wait(
                {next_event, cancelled},
                timeout=keepalive,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if cancelled in done:
                # Token counts are unknown here: the adapter reports usage with its
                # terminal event, which a cancelled run never reaches. Lot B replaces
                # this with the partial usage carried by the adapter's StreamCancelled.
                yield _sse("cancelled", {
                    "cause": CancellationCause.CLIENT.value,
                    "inputTokens": 0,
                    "outputTokens": 0,
                })
                return

            if not done:
                # An SSE comment keeps the ALB idle timer from closing a quiet stream
                # (V2-LLD-001 §7.3).
                yield ": ping\n\n"
                continue

            item = next_event.result()
            next_event = asyncio.ensure_future(queue.get())

            if item is None:
                return
            if isinstance(item, BaseException):
                logger.error("agent worker thread failed", exc_info=item)
                yield _sse("error", {
                    "code": AgentErrorCode.INTERNAL_ERROR.value,
                    "message": "Internal agent error",
                })
                return

            chunk = _serialize(item)
            if chunk:
                yield chunk
            if _is_terminal(item):
                return
    finally:
        next_event.cancel()
        cancelled.cancel()
        # Signal the worker thread on every exit path — normal end, cancellation, or
        # client disconnect. The thread is not joined: it observes the flag between
        # events and exits on its own.
        cancel_event.set()
        cancel_registry.pop(request.operation_context.operation_id, None)


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    body: MessageRequest,
    conversation_id: str = Path(min_length=1, max_length=128),
    claims: dict[str, Any] = Depends(bearer_claims),
) -> StreamingResponse:
    actor_id: str = claims["sub"]
    tenant_id = _resolve_tenant(actor_id)
    operation_id = str(uuid4())
    request_id = str(uuid4())
    deadline_ms = int((time.time() + settings.agent_deadline_seconds) * 1000)

    cancel_event = asyncio.Event()
    cancel_registry[operation_id] = PendingOperation(
        actor_id=actor_id,
        cancel_event=cancel_event,
    )

    request = AgentRequest(
        message=body.message,
        runtime_session_id=conversation_id,
        trusted_identity=TrustedIdentity(actor_id=actor_id, tenant_id=tenant_id),
        operation_context=OperationContext(
            operation_id=operation_id,
            request_id=request_id,
            deadline_epoch_ms=deadline_ms,
        ),
        retrieval_context=RetrievalContext(
            status="skipped",
            chunks=(),
            chunk_count=0,
            policy="v1",
        ),
        budget=AgentBudget(
            max_turns=settings.agent_max_turns,
            max_tool_calls=settings.agent_max_tool_calls,
            max_tokens=settings.agent_max_tokens,
            deadline_epoch_ms=deadline_ms,
        ),
        config=AgentConfig(
            invocation_id=settings.bedrock_invocation_id,
            fallback_invocation_id=None,
            prompt_version=settings.agent_prompt_version,
            tool_allowlist=[],
        ),
    )

    return StreamingResponse(
        _event_stream(request, cancel_event),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Operation-Id": operation_id,
        },
    )
