import time

from agents.exceptions import BudgetExceededError, DeadlineExceededError
from agents.models import AgentBudget, AgentErrorCode


class BudgetGuard:
    def __init__(self, budget: AgentBudget) -> None:
        self._budget = budget
        self._turns = 0
        self._tool_calls = 0
        self._tokens = 0

    def check_deadline(self) -> None:
        if int(time.time() * 1000) >= self._budget.deadline_epoch_ms:
            raise DeadlineExceededError()

    def check_turns(self) -> None:
        if self._turns >= self._budget.max_turns:
            raise BudgetExceededError(f"max_turns={self._budget.max_turns} reached")

    def check_tool_calls(self) -> None:
        if self._tool_calls >= self._budget.max_tool_calls:
            raise BudgetExceededError(f"max_tool_calls={self._budget.max_tool_calls} reached")

    def add_turn(self) -> None:
        self._turns += 1

    def add_tool_call(self) -> None:
        self._tool_calls += 1

    def add_tokens(self, n: int) -> None:
        self._tokens += n
        if self._tokens > self._budget.max_tokens:
            raise BudgetExceededError(f"max_tokens={self._budget.max_tokens} reached")
