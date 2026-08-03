from agents.models import AgentErrorCode


class AgentBudgetError(Exception):
    def __init__(self, code: AgentErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class BudgetExceededError(AgentBudgetError):
    def __init__(self, message: str) -> None:
        super().__init__(AgentErrorCode.BUDGET_EXCEEDED, message)


class DeadlineExceededError(AgentBudgetError):
    def __init__(self, message: str = "Deadline exceeded") -> None:
        super().__init__(AgentErrorCode.DEADLINE_EXCEEDED, message)


class ToolDeniedError(Exception):
    pass


class AgentFallbackError(Exception):
    pass
