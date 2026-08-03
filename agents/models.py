from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Budget and invocation config (LLD-003 §3.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentBudget:
    max_turns: int
    max_tool_calls: int
    max_tokens: int
    deadline_epoch_ms: int


@dataclass(frozen=True)
class AgentConfig:
    invocation_id: str          # opaque Bedrock invocation ID (V2-ADR-012)
    fallback_invocation_id: Optional[str]
    prompt_version: str
    tool_allowlist: list[str]   # empty list = no tools (Lot A)


# ---------------------------------------------------------------------------
# Identity and context (LLD-003 §3.2, V2-ADR-006)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TrustedIdentity:
    actor_id: str               # JWT sub, transmitted as-is (V2-LLD-005 §3.1)
    tenant_id: str              # resolved server-side (V2-LLD-005 §3.4)


@dataclass(frozen=True)
class OperationContext:
    operation_id: str
    request_id: str
    deadline_epoch_ms: int


@dataclass(frozen=True)
class RetrievalContext:
    status: str                 # "ok" | "degraded" | "skipped"
    chunks: tuple[dict, ...]
    chunk_count: int
    policy: str
    trust: str = "untrusted"   # immutable by frozen — content is untrusted data


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentRequest:
    message: str
    runtime_session_id: str
    trusted_identity: TrustedIdentity
    operation_context: OperationContext
    retrieval_context: RetrievalContext
    budget: AgentBudget
    config: AgentConfig


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class AgentErrorCode(Enum):
    BUDGET_EXCEEDED = "budget_exceeded"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    TOOL_DENIED = "tool_denied"
    MODEL_THROTTLED = "model_throttled"
    TOOL_UNAVAILABLE = "tool_unavailable"
    MEMORY_UNAVAILABLE = "memory_unavailable"
    # Catch-all for a failure the agent cannot attribute. Distinct from BUDGET_EXCEEDED:
    # a client that retries on a budget error must not retry on an internal one.
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class AgentError:
    code: AgentErrorCode
    message: str


class CancellationCause(Enum):
    CLIENT = "client"
    DEADLINE = "deadline"
    OPERATOR = "operator"


@dataclass
class AgentResult:
    answer: str
    turn_count: int
    input_tokens: int           # billed separately by Bedrock (V2-ADR-012)
    output_tokens: int
    tool_calls_count: int
    budget_exhausted: bool
    degraded: bool
    served_invocation_id: str   # effective invocation ID (V2-ADR-012)
    error: Optional[AgentError] = None
    cancelled: Optional[CancellationCause] = None

    @property
    def tokens_used(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# Streaming events (V2-ADR-011, LLD-003 §3.2.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StreamMeta:
    streaming: str              # "native" | "emulated" — effective mode, never aspirational
    operation_id: str


@dataclass(frozen=True)
class StreamDelta:
    text: str


@dataclass(frozen=True)
class StreamCitation:
    citations: tuple[dict, ...]


@dataclass(frozen=True)
class StreamDone:
    result: AgentResult


@dataclass(frozen=True)
class StreamCancelled:
    cause: CancellationCause
    result: AgentResult


@dataclass(frozen=True)
class StreamError:
    error: AgentError


AgentStreamEvent = (
    StreamMeta | StreamDelta | StreamCitation
    | StreamDone | StreamCancelled | StreamError
)
