"""An `LLMProvider` wrapper that enforces a `UsageBudget` (ADR-0018).

Sits directly around each concrete adapter, so cost is attributed to the model that actually answered and a
`FallbackProvider` failover is charged at the fallback's price. `BudgetExceededError` is not a
`ProviderUnavailableError`, so the fallback layer lets it propagate instead of trying another model.
"""

from collections.abc import Iterator, Sequence

from ombuds.platform.ai.budget import UsageBudget
from ombuds.platform.ai.providers.base import LLMProvider, ProviderTurn
from ombuds.platform.ai.schemas.tool_calls import ToolDefinition
from ombuds.platform.ai.streaming import StreamEvent, TurnDone


class BudgetedProvider:
    """Refuses a turn once `budget` is spent; otherwise delegates to `inner` and charges the reported usage."""

    def __init__(self, inner: LLMProvider, model: str, budget: UsageBudget) -> None:
        self._inner = inner
        self._model = model
        self._budget = budget

    def run_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> ProviderTurn:
        self._budget.check()
        turn = self._inner.run_turn(messages, tools, system=system)
        self._budget.charge(self._model, turn.usage)
        return turn

    def stream_turn(
        self, messages: list[dict[str, object]], tools: Sequence[ToolDefinition], *, system: str
    ) -> Iterator[StreamEvent]:
        self._budget.check()
        for event in self._inner.stream_turn(messages, tools, system=system):
            if isinstance(event, TurnDone):
                self._budget.charge(self._model, event.usage)
            yield event
