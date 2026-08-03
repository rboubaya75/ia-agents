import logging
from typing import Iterator

from agents.exceptions import AgentBudgetError, DeadlineExceededError
from agents.interface import AgentAdapter
from agents.models import (
    AgentError,
    AgentErrorCode,
    AgentRequest,
    AgentStreamEvent,
    StreamCancelled,
    StreamDone,
    StreamError,
)
from agents.domain.budget_guard import BudgetGuard

logger = logging.getLogger(__name__)

_TERMINAL_EVENTS = (StreamDone, StreamCancelled, StreamError)


class Orchestrator:
    """
    Orchestrateur applicatif unique (V2-ADR-005).
    Applique les budgets avant d'invoquer l'adapter.
    Pas de multi-agent sans amendement ADR (P-01/P-02).
    """

    def __init__(self, adapter: AgentAdapter) -> None:
        self._adapter = adapter

    def run_stream(self, request: AgentRequest) -> Iterator[AgentStreamEvent]:
        guard = BudgetGuard(request.budget)
        op_id = request.operation_context.operation_id
        terminal_seen = False

        try:
            guard.check_deadline()
            for event in self._adapter.invoke_stream(request):
                if isinstance(event, _TERMINAL_EVENTS):
                    terminal_seen = True
                yield event
        except DeadlineExceededError:
            logger.warning("deadline exceeded for operation %s", op_id)
            if not terminal_seen:
                yield StreamError(error=AgentError(
                    code=AgentErrorCode.DEADLINE_EXCEEDED,
                    message="Operation deadline exceeded",
                ))
            return
        except AgentBudgetError as exc:
            logger.warning("budget exceeded for operation %s: %s", op_id, exc)
            if not terminal_seen:
                yield StreamError(error=AgentError(code=exc.code, message=str(exc)))
            return
        except Exception:
            logger.error("orchestrator error for operation %s", op_id, exc_info=True)
            if not terminal_seen:
                yield StreamError(error=AgentError(
                    code=AgentErrorCode.INTERNAL_ERROR,
                    message="Internal agent error",
                ))
            return

        # The stream contract (interface.py) requires exactly one terminal event. An
        # adapter that ends without one leaves the client waiting on its own timeout,
        # so the orchestrator closes the stream itself rather than trusting the adapter.
        if not terminal_seen:
            logger.error("adapter ended without a terminal event for operation %s", op_id)
            yield StreamError(error=AgentError(
                code=AgentErrorCode.INTERNAL_ERROR,
                message="Agent ended without a terminal event",
            ))
