import time
from typing import Iterator

from agents.models import (
    AgentErrorCode,
    AgentRequest,
    AgentResult,
    AgentStreamEvent,
    StreamDelta,
    StreamDone,
    StreamError,
    StreamMeta,
    AgentError,
)


class StubAdapter:
    """
    Local stub — simulates AgentCore Runtime without any AWS dependency.
    Implements AgentAdapter Protocol. Replace with StrandsAdapter for production.
    No import of strands.* — this file is allowed to stay in adapter/ but
    the P-04 lint rule only targets framework imports, not this stub.
    """

    def invoke(self, request: AgentRequest) -> AgentResult:
        result = AgentResult(
            answer=f"[stub] Received: {request.message[:120]}",
            turn_count=1,
            input_tokens=0,
            output_tokens=0,
            tool_calls_count=0,
            budget_exhausted=False,
            degraded=True,      # served by the stub, never by a real model
            served_invocation_id=request.config.invocation_id or "stub",
        )
        return result

    def invoke_stream(self, request: AgentRequest) -> Iterator[AgentStreamEvent]:
        op_id = request.operation_context.operation_id

        # StreamMeta is first — declares the effective streaming mode before the first
        # model call so the client can adapt its UX immediately (LLD-003 §3.2.1).
        yield StreamMeta(streaming="emulated", operation_id=op_id)

        # Check deadline before doing any work (budget_guard already did this, but
        # the adapter checks again so it can emit a proper terminal event).
        now_ms = int(time.time() * 1000)
        if now_ms >= request.budget.deadline_epoch_ms:
            yield StreamError(error=AgentError(
                code=AgentErrorCode.DEADLINE_EXCEEDED,
                message="Deadline reached before processing",
            ))
            return

        # Simulate a streamed reply fragment by fragment.
        fragments = [
            "[stub] ",
            f"Session {request.runtime_session_id[:8]}. ",
            f"Message reçu : {request.message[:120]}",
        ]
        for fragment in fragments:
            yield StreamDelta(text=fragment)

        yield StreamDone(result=AgentResult(
            answer="".join(fragments),
            turn_count=1,
            input_tokens=0,
            output_tokens=0,
            tool_calls_count=0,
            budget_exhausted=False,
            degraded=True,      # degraded=True: served by stub, not a real model
            served_invocation_id=request.config.invocation_id or "stub",
        ))
