from typing import Iterator, Protocol

from agents.models import AgentRequest, AgentResult, AgentStreamEvent


class AgentAdapter(Protocol):
    """
    Abstraction du framework agentique (V2-ADR-005, P-04).
    Le code domaine ne dépend que de cette interface, jamais de strands.* directement.
    Seul agents/adapter/ est autorisé à importer strands.*.
    """

    def invoke(self, request: AgentRequest) -> AgentResult:
        """Blocking invocation — returns a complete result."""
        ...

    def invoke_stream(self, request: AgentRequest) -> Iterator[AgentStreamEvent]:
        """
        Streaming invocation — yields domain events.
        MUST always terminate with exactly one terminal event: Done | Cancelled | Error.
        The `: ping` keep-alive is emitted by FastAPI, never by the adapter.
        """
        ...
